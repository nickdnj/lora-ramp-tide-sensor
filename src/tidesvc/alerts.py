"""Alert engine (ARCHITECTURE 6.8; E8.1-E8.3, E9.3).

Evaluated every 60 s. Alerts are de-duplicated by ``kind`` while open, each one
stores its clear condition, and notification is by email only. A process
restart reloads open alerts from the database and does not re-send them.

Interpretation of "2 consecutive evaluations" for the surge rules: two
consecutive *new readings* whose residual is at or above the threshold (the
engine ticks every 60 s but the residual only changes every 5 min, so counting
ticks would make the rule meaningless).
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import sqlite3
from dataclasses import dataclass

from . import energy as energymod
from . import health, tempest
from .noaa import load_predictor, reference_residual
from .notify import Notifier, NotifyError
from .timeutil import iso, local_date

log = logging.getLogger("tidesvc.alerts")


@dataclass(frozen=True)
class Rule:
    kind: str
    severity: str
    clear_condition: str
    notify: bool = True


def rules(cfg) -> dict[str, Rule]:
    a = cfg.alerts
    return {r.kind: r for r in [
        Rule("SURGE_WARNING", "warning",
             f"residual below +{a.surge_warning_clear_m:.2f} m for {a.clear_hold_s // 60} min"),
        Rule("SURGE_SEVERE", "severe",
             f"residual below +{a.surge_severe_clear_m:.2f} m for {a.clear_hold_s // 60} min"),
        Rule("RAPID_RISE", "warning",
             f"excess rise below {a.excess_rise_clear_m_per_h:.2f} m/h for {a.clear_hold_s // 60} min"),
        Rule("SURGE_WATCH", "advisory",
             f"residual below +{a.surge_watch_clear_m:.2f} m, or pressure/wind context false for 1 h"),
        Rule("NODE_SILENT", "health", "next valid reading"),
        Rule("GATEWAY_DOWN", "health", "gateway link restored"),
        Rule("REPEATER_SILENT", "health", "any repeater evidence heard (relayed frame, advert or status)"),
        Rule("LOW_BATTERY", "health",
             f"vbat >= {a.low_batt_clear_mv / 1000:.2f} V and projected days to empty >= 21"),
        Rule("ENERGY_DEFICIT", "health", "14-day energy verdict marginal or better"),
        Rule("ENERGY_NEGATIVE_STREAK", "early_warning", "first qualifying day with net_mah >= 0"),
        Rule("SENSOR_QUALITY", "health", "fewer than 2 of the last 12 readings with pitch_sd > 0.2 deg"),
        Rule("OUT_OF_RANGE", "health", "3 consecutive in-range readings"),
        Rule("PREDICTION_UNAVAILABLE", "health", "cached predictions cover now + 24 h again"),
        Rule("CALIBRATION_DRIFT", "health", "proposed calibration approved or rejected via the CLI"),
        Rule("TEMPEST_UNAVAILABLE", "status", "Tempest ok again", notify=False),
    ]}


class AlertEngine:
    def __init__(self, conn: sqlite3.Connection, cfg, notifier: Notifier | None) -> None:
        self.conn = conn
        self.cfg = cfg
        self.notifier = notifier
        self.rules = rules(cfg)
        self._last_t: float | None = None  # last derived row (t) consumed by the surge rules
        self._consec = {"SURGE_WARNING": 0, "SURGE_SEVERE": 0}
        self._below_since: dict[str, float | None] = {"SURGE_WARNING": None, "SURGE_SEVERE": None,
                                                      "RAPID_RISE": None}
        self._watch_ctx_false_since: float | None = None
        row = conn.execute("SELECT MAX(t) FROM derived WHERE live=1").fetchone()
        self._last_t = row[0] if row else None

    # ------------------------------------------------------------------ helpers
    def open_alert(self, kind: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM alerts WHERE kind=? AND cleared_at IS NULL ORDER BY id DESC LIMIT 1",
                                 (kind,)).fetchone()

    def _open(self, kind: str, now: float, value: float | None, threshold: float | None, ctx: dict) -> bool:
        if self.open_alert(kind) is not None:
            return False
        r = self.rules[kind]
        self.conn.execute(
            "INSERT INTO alerts(kind, severity, opened_at, clear_condition, value, threshold, context_json, notify) "
            "VALUES (?,?,?,?,?,?,?,?)", (kind, r.severity, now, r.clear_condition, value, threshold,
                                         json.dumps(ctx, default=str), int(r.notify)))
        log.info("alert open %s value=%s", kind, value)
        return True

    def _clear(self, kind: str, now: float) -> bool:
        row = self.open_alert(kind)
        if row is None:
            return False
        self.conn.execute("UPDATE alerts SET cleared_at=? WHERE id=?", (now, row["id"]))
        log.info("alert clear %s", kind)
        return True

    def _set(self, kind: str, active: bool, clear: bool, now: float, value=None, threshold=None,
             ctx: dict | None = None) -> None:
        if active:
            self._open(kind, now, value, threshold, ctx or {})
        elif clear:
            self._clear(kind, now)

    # ------------------------------------------------------------------ evaluation
    def evaluate(self, now: float) -> None:
        self._surge_rules(now)
        self._health_rules(now)
        self._notify_pending(now)

    def _surge_context(self, now: float) -> dict:
        ctx = {"sandy_hook_residual_m": reference_residual(self.conn, self.cfg.noaa.observed_reference, now)}
        w = tempest.context(self.conn, self.cfg, now)
        ctx["weather_context"] = w
        return ctx

    def _surge_rules(self, now: float) -> None:
        a = self.cfg.alerts
        q = "SELECT * FROM derived WHERE live=1 AND valid=1 AND t <= ?"
        args: list = [now]
        if self._last_t is not None:
            q += " AND t > ?"
            args.append(self._last_t)
        new_rows = self.conn.execute(q + " ORDER BY t", args).fetchall()
        for r in new_rows:
            self._last_t = r["t"]
            res = r["residual_m"]
            if res is not None:
                for kind, thr, clr in (("SURGE_WARNING", a.surge_warning_m, a.surge_warning_clear_m),
                                       ("SURGE_SEVERE", a.surge_severe_m, a.surge_severe_clear_m)):
                    self._consec[kind] = self._consec[kind] + 1 if res >= thr else 0
                    if self._consec[kind] >= 2:
                        self._open(kind, now, res, thr, {**self._surge_context(now), "reading_t": r["t"]})
                    if res < clr:
                        if self._below_since[kind] is None:
                            self._below_since[kind] = r["t"]
                        if r["t"] - self._below_since[kind] >= a.clear_hold_s:
                            self._clear(kind, now)
                    else:
                        self._below_since[kind] = None
            ex = r["excess_rise_mph"]
            if ex is not None:
                if ex >= a.excess_rise_m_per_h:
                    self._open("RAPID_RISE", now, ex, a.excess_rise_m_per_h,
                               {**self._surge_context(now), "reading_t": r["t"]})
                if ex < a.excess_rise_clear_m_per_h:
                    if self._below_since["RAPID_RISE"] is None:
                        self._below_since["RAPID_RISE"] = r["t"]
                    if r["t"] - self._below_since["RAPID_RISE"] >= a.clear_hold_s:
                        self._clear("RAPID_RISE", now)
                else:
                    self._below_since["RAPID_RISE"] = None
            self._surge_watch(now, res)

    def _surge_watch(self, now: float, res: float | None) -> None:
        a, tc = self.cfg.alerts, self.cfg.tempest
        ctx = tempest.context(self.conn, self.cfg, now)
        if ctx["status"] != "ok" or res is None:
            return  # only evaluated when Tempest is ok
        dp = ctx["pressure_change_3h_hpa"]
        cond = (dp is not None and dp <= -tc.pressure_drop_3h_hpa) or bool(ctx["onshore_wind_sustained"])
        if cond:
            self._watch_ctx_false_since = None
        elif self._watch_ctx_false_since is None:
            self._watch_ctx_false_since = now
        if res >= a.surge_watch_m and cond:
            self._open("SURGE_WATCH", now, res, a.surge_watch_m, {"weather_context": ctx})
        elif res < a.surge_watch_clear_m or (self._watch_ctx_false_since is not None
                                             and now - self._watch_ctx_false_since >= 3600):
            self._clear("SURGE_WATCH", now)

    def _health_rules(self, now: float) -> None:
        cfg, a = self.cfg, self.cfg.alerts
        node = health.node_status(self.conn, cfg, now)
        gw = health.gateway_status(self.conn, now)
        rep = health.repeater_status(self.conn, cfg, now)

        # NODE_SILENT
        silent = node["age_s"] is not None and node["age_s"] > cfg.node.silent_alert_after_s
        self._set("NODE_SILENT", silent, node["status"] == "ok", now, node["age_s"],
                  cfg.node.silent_alert_after_s, {"last_valid_at": iso(node["last_valid_at"])})

        # GATEWAY_DOWN
        gw_down = gw["status"] == "error" and gw["since"] is not None and now - gw["since"] > a.gateway_down_after_s
        self._set("GATEWAY_DOWN", gw_down, gw["status"] == "ok", now,
                  None if gw["since"] is None else now - gw["since"], a.gateway_down_after_s,
                  {"detail": gw["detail"]})

        # REPEATER_SILENT (suppressed while GATEWAY_DOWN is open)
        rep_silent = gw["status"] == "ok" and rep["status"] == "silent" and self.open_alert("GATEWAY_DOWN") is None
        hint = "Node is also silent: check the repeater first." if node["status"] != "ok" else \
            "Node frames still arrive (gateway hears the node directly)."
        self._set("REPEATER_SILENT", rep_silent, rep["status"] == "ok", now,
                  None if rep["last_evidence_at"] is None else now - rep["last_evidence_at"],
                  cfg.repeater.silent_after_s, {"hint": hint, "last_evidence_at": iso(rep["last_evidence_at"])})

        # LOW_BATTERY
        last3 = self.conn.execute("SELECT vbat_mv FROM readings WHERE t <= ? AND vbat_mv IS NOT NULL "
                                  "ORDER BY t DESC LIMIT 3", (now,)).fetchall()
        v = [r[0] for r in last3]
        if self._verdict_cache is None or self._energy_due(now):
            self.refresh_energy(now)  # the scheduler also refreshes right after each daily rollup
        verdict = self._verdict_cache
        proj = verdict["projected_days_to_empty"] if verdict else None
        low = (len(v) == 3 and all(x < a.low_batt_mv for x in v)) or (proj is not None and proj < 14)
        ok = bool(v) and v[0] >= a.low_batt_clear_mv and (proj is None or proj >= 21)
        self._set("LOW_BATTERY", low, ok, now, (v[0] / 1000.0) if v else None, a.low_batt_mv / 1000.0,
                  {"projected_days_to_empty": proj})

        # ENERGY_DEFICIT / ENERGY_NEGATIVE_STREAK
        if verdict:
            self._set("ENERGY_DEFICIT", verdict["assessment"] == "deficit",
                      verdict["assessment"] in ("marginal", "surplus"), now, verdict["energy_ratio"], 1.0,
                      {"verdict": verdict})
            streak = verdict["negative_streak_days"]
            self._set("ENERGY_NEGATIVE_STREAK", streak >= cfg.energy.negative_streak_days, streak == 0, now,
                      streak, cfg.energy.negative_streak_days, {"early_warning": True})

        # SENSOR_QUALITY / OUT_OF_RANGE
        last12 = self.conn.execute(
            "SELECT r.pitch_sd_deg, r.flags, d.invalid_reason FROM readings r JOIN derived d ON d.reading_id=r.id "
            "WHERE d.live=1 AND r.t <= ? ORDER BY r.t DESC LIMIT 12", (now,)).fetchall()
        if last12:
            n_hi = sum(1 for r in last12 if (r[0] or 0) > a.sensor_quality_sd_deg)
            sensor_err = bool(last12[0][1] & (1 << 7))
            self._set("SENSOR_QUALITY", n_hi >= 6 or sensor_err, n_hi < 2 and not sensor_err, now, n_hi, 6, {})
            oor = [r[2] in ("out_of_range", "out_of_envelope") for r in last12[:3]]
            self._set("OUT_OF_RANGE", len(oor) == 3 and all(oor), len(oor) == 3 and not any(oor), now,
                      sum(oor), 3, {})

        # PREDICTION_UNAVAILABLE
        pred = load_predictor(self.conn, cfg.noaa.prediction_station, now - 2 * 86400)
        covered = pred.covers(now) and pred.covers(now + a.prediction_lookahead_s)
        self._set("PREDICTION_UNAVAILABLE", not covered, covered, now, None, None,
                  {"covers_until": iso(pred.covers_until)})

        # CALIBRATION_DRIFT
        prop = self.conn.execute("SELECT id, fit_stats_json FROM calibrations WHERE status='proposed' "
                                 "ORDER BY id DESC LIMIT 1").fetchone()
        self._set("CALIBRATION_DRIFT", prop is not None, prop is None, now, None, None,
                  {"proposed_id": prop[0] if prop else None,
                   "fit": json.loads(prop[1]) if prop and prop[1] else None})

        # TEMPEST_UNAVAILABLE (status only, no email)
        if cfg.tempest.enabled:
            ts = tempest.tempest_status(self.conn, cfg, now)
            since = ts.get("since")
            bad = ts["status"] in ("error", "stale") and since is not None and now - since > 3600
            self._set("TEMPEST_UNAVAILABLE", bad, ts["status"] == "ok", now, None, None, {"status": ts})

    _verdict_cache: dict | None = None
    _verdict_day: object = None

    def _energy_due(self, now: float) -> bool:
        d = local_date(now)
        if self._verdict_day != d:
            self._verdict_day = d
            return True
        return False

    def refresh_energy(self, now: float) -> dict:
        self._verdict_cache = energymod.verdict(self.conn, self.cfg, now)
        self._verdict_day = local_date(now)
        return self._verdict_cache

    # ------------------------------------------------------------------ email
    def _notify_pending(self, now: float) -> None:
        if self.notifier is None:
            return
        rows = self.conn.execute("SELECT * FROM alerts WHERE notify=1 AND notified_at IS NULL AND "
                                 "notify_attempts < 20 ORDER BY id").fetchall()
        for r in rows:
            subject, body = format_email(r, self.cfg)
            try:
                self.notifier.send(subject, body)
                self.conn.execute("UPDATE alerts SET notified_at=?, notify_attempts=notify_attempts+1 WHERE id=?",
                                  (now, r["id"]))
            except NotifyError as e:
                log.warning("alert email failed (will retry): %s", e)
                self.conn.execute("UPDATE alerts SET notify_attempts=notify_attempts+1 WHERE id=?", (r["id"],))


def format_email(r: sqlite3.Row, cfg) -> tuple[str, str]:
    ctx = json.loads(r["context_json"] or "{}")
    tag = {"advisory": "[advisory] ", "early_warning": "[early warning] "}.get(r["severity"], "")
    val = r["value"]
    vtxt = "" if val is None else f": value {val:.3f}" if isinstance(val, float) else f": value {val}"
    subject = f"[tide] {tag}{r['kind']} opened{vtxt}"
    lines = [
        f"Alert: {r['kind']} ({r['severity']})",
        f"Opened: {iso(r['opened_at'])}",
        f"Value: {val}  Threshold: {r['threshold']}",
        f"Clears when: {r['clear_condition']}",
    ]
    if r["kind"].startswith("SURGE") or r["kind"] == "RAPID_RISE":
        sh = ctx.get("sandy_hook_residual_m")
        lines.append("Sandy Hook 8531680 residual: " + ("unavailable" if sh is None else f"{sh:+.2f} m"))
        w = ctx.get("weather_context") or {}
        if w.get("status") == "ok":
            lines.append(f"Tempest: pressure change 3 h {w.get('pressure_change_3h_hpa')} hPa, "
                         f"inverse barometer {w.get('inverse_barometer_m')} m, "
                         f"onshore wind sustained {w.get('onshore_wind_sustained')}")
        else:
            lines.append("Tempest context unavailable")
    if r["kind"] == "REPEATER_SILENT":
        lines.append(ctx.get("hint", ""))
    if r["kind"] == "ENERGY_NEGATIVE_STREAK":
        lines.append("Early warning only: the 14-day verdict is the official solar answer.")
    if r["kind"] == "SURGE_WATCH":
        lines.append("Advisory: Tempest context plus a modest residual. Not a PRD surge alert.")
    lines.append("")
    lines.append("Predicted values are predictions, not observations.")
    return subject, "\n".join(lines)


def open_alerts(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM alerts WHERE cleared_at IS NULL ORDER BY opened_at").fetchall()


_ = _dt  # keep import for type users
