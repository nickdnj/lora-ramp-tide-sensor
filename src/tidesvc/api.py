"""Read-only JSON API (ARCHITECTURE 7; ADR-007, ADR-010).

- Every response has a top-level ``status``; non-ok responses carry
  ``error: {code, message}``.
- No demo data, ever: a value that cannot be computed is null. Predicted values
  never stand in for observed ones; the last good observation appears only
  inside a labelled ``last_good`` object.
- ``/api/v1/level/current`` returns HTTP 503 when the level is stale or
  unavailable. Composite/history endpoints return 200 with per-component status.
- Only GET routes exist. All writes are CLI-only.
"""

from __future__ import annotations

import datetime as _dt
import sqlite3
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, PlainTextResponse

from . import codec, energy, export, health, tempest
from . import db as dbmod
from .derive import calibration_at, load_calibrations, ls_slope
from .noaa import load_predictor, reference_residual
from .timeutil import Clock, SystemClock, iso, parse_iso

DATUM_MLLW = "MLLW (tied to NOAA 8531942 predicted extremes; not surveyed)"
DATUM_MARK = "relative to the bulkhead reference mark (not yet tied to MLLW)"


def _r(v: float | None, nd: int = 3) -> float | None:
    return None if v is None else round(v, nd)


def _flags(bits: int | None) -> list[str]:
    return [n for b, n in codec.FLAG_NAMES.items() if (bits or 0) & b]


def _err(code: str, message: str) -> dict:
    return {"code": code, "message": message}


class Views:
    """Pure view builders: (conn, cfg, now) -> (http_status, body)."""

    def __init__(self, cfg) -> None:
        self.cfg = cfg

    # ------------------------------------------------------------------ shared
    def _cal(self, conn, now):
        return calibration_at(load_calibrations(conn), now)

    def _pred(self, conn, now, t0=None, t1=None):
        return load_predictor(conn, self.cfg.noaa.prediction_station,
                              t0 if t0 is not None else now - 3 * 86400, t1 if t1 is not None else now + 8 * 86400)

    def _noaa(self, conn, now) -> dict:
        comp = dbmod.get_component(conn, "noaa")
        pred = self._pred(conn, now)
        out: dict[str, Any] = {"status": comp["status"] if comp else "error",
                               "predictions_cover_until": iso(pred.covers_until)}
        if comp is None:
            out["error"] = _err("NOAA_NOT_FETCHED", "predictions not fetched yet")
        elif comp["status"] != "ok":
            out["error"] = _err(comp["detail"].get("code", "NOAA_FETCH_FAILED"), comp["detail"].get("message", ""))
        if not pred.covers(now):
            out["status"] = "error"
            out["error"] = _err("PREDICTION_UNAVAILABLE", "no cached published prediction covers now")
        return out

    def _components(self, conn, now) -> dict:
        cfg = self.cfg
        gw = health.gateway_status(conn, now)
        rep = health.repeater_status(conn, cfg, now)
        node = health.node_status(conn, cfg, now)
        cal = self._cal(conn, now)
        calc = ({"status": "ok", "version": cal.id, "datum": cal.datum, "method": cal.method}
                if cal else {"status": "error", "error": _err("NO_CALIBRATION", "no active calibration")})
        if cal is not None and not cal.datum_tied:
            calc["note"] = "datum not tied to MLLW yet; residual unavailable"
        ts = tempest.tempest_status(conn, cfg, now)
        return {
            "gateway": {"status": "error" if gw["status"] == "unknown" else gw["status"],
                        **({"error": _err("GATEWAY_LINK", gw["detail"].get("message", "no link"))}
                           if gw["status"] != "ok" else {})},
            "repeater": {"status": rep["status"], "last_evidence_at": iso(rep["last_evidence_at"])},
            "node": {"status": node["status"], "age_s": node["age_s"]},
            "noaa": self._noaa(conn, now),
            "tempest": {k: v for k, v in ts.items() if k in ("status", "error")},
            "calibration": calc,
        }

    # ------------------------------------------------------------------ endpoints
    def status(self, conn, now):
        comps = self._components(conn, now)
        required = ["gateway", "node", "noaa", "calibration"]
        bad = [k for k in required if comps[k]["status"] != "ok"] + \
              (["repeater"] if comps["repeater"]["status"] == "silent" else [])
        return 200, {"status": "ok" if not bad else "degraded", "as_of": iso(now), "components": comps}

    def _last_good(self, conn, now) -> dict | None:
        row = conn.execute("SELECT * FROM derived WHERE valid=1 AND live=1 AND level_smooth_m IS NOT NULL AND t<=? "
                           "ORDER BY t DESC LIMIT 1", (now,)).fetchone()
        if row is None:
            return None
        return {"at": iso(row["t"]), "level_m": _r(row["level_smooth_m"]), "residual_m": _r(row["residual_m"])}

    def _trend(self, conn, t: float) -> tuple[float | None, str | None]:
        rows = conn.execute("SELECT t, level_smooth_m FROM derived WHERE valid=1 AND live=1 AND "
                            "level_smooth_m IS NOT NULL AND t > ? AND t <= ? ORDER BY t", (t - 3600, t)).fetchall()
        if len(rows) < 4:
            return None, None
        rate = ls_slope([r[0] for r in rows], [r[1] for r in rows])
        return rate, "rising" if rate > 0.02 else "falling" if rate < -0.02 else "steady"

    def level_current(self, conn, now):
        cfg = self.cfg
        comps = self._components(conn, now)
        compact = {k: v["status"] for k, v in comps.items() if k in ("gateway", "repeater", "node", "noaa", "tempest")}
        pred = self._pred(conn, now)
        predicted_now = pred.predict(now)
        cal = self._cal(conn, now)
        base = {"level_m": None, "level_raw_m": None, "residual_m": None, "predicted_m": _r(predicted_now),
                "predicted_note": "prediction for now (NOAA 8531942 hi/lo, half-cosine); not an observation",
                "components": compact}
        if cal is None:
            return 503, {"status": "error", "error": _err("NO_CALIBRATION", "No active calibration."), **base,
                         "last_good": None}
        row = health.last_valid_live(conn, now)
        last_good = self._last_good(conn, now)
        if row is None:
            return 503, {"status": "error", "error": _err("NO_DATA", "No valid reading received yet."), **base,
                         "last_good": last_good}
        age = now - row["t"]
        if age > cfg.node.stale_after_s:
            return 503, {"status": "stale", "error": _err(
                "NODE_STALE", f"No valid reading for {int(age // 60)} min (stale after {cfg.node.stale_after_s // 60} min)."),
                **base, "last_good": last_good}
        if row["level_smooth_m"] is None:
            return 503, {"status": "insufficient_data", "error": _err(
                "INSUFFICIENT_POINTS", f"Fewer than {cfg.calibration.min_points} valid readings in the "
                                       f"{cfg.calibration.window_min}-min window."), **base, "last_good": last_good}
        rd = conn.execute("SELECT pitch_sd_deg, flags FROM readings WHERE id=?", (row["reading_id"],)).fetchone()
        rate, direction = self._trend(conn, row["t"])
        n_pts = conn.execute("SELECT COUNT(*) FROM derived WHERE valid=1 AND live=1 AND t > ? AND t <= ?",
                             (row["t"] - cfg.calibration.window_min * 60, row["t"])).fetchone()[0]
        cal_row = self._cal(conn, row["t"])
        residual_status = "ok" if row["residual_m"] is not None else "error"
        body = {
            "status": "ok", "as_of": iso(row["t"]), "age_s": round(age),
            "level_m": _r(row["level_smooth_m"]), "level_raw_m": _r(row["level_raw_m"]),
            "datum": DATUM_MLLW if cal_row and cal_row.datum_tied else DATUM_MARK,
            "smoothing": {"method": "trailing_median", "window_min": cfg.calibration.window_min, "n_points": n_pts},
            "trend": {"rate_m_per_h": _r(rate), "direction": direction,
                      "excess_over_predicted_m_per_h": _r(row["excess_rise_mph"])},
            "predicted_m": _r(row["predicted_m"]),
            "predicted_note": "prediction at as_of (NOAA 8531942 hi/lo, half-cosine); not an observation",
            "residual_m": _r(row["residual_m"]), "residual_status": residual_status,
            "calibration": {"version": cal_row.id if cal_row else None,
                            "valid_from": iso(cal_row.valid_from) if cal_row else None},
            "quality": {"pitch_sd_deg": _r(rd["pitch_sd_deg"]), "flags": _flags(rd["flags"])},
            "weather_context": tempest.context(conn, cfg, now),
            "components": compact,
        }
        if residual_status != "ok":
            reason = row["residual_reason"] or "unavailable"
            body["residual_error"] = _err(reason.upper(), {
                "datum_not_tied": "Datum not tied to MLLW yet (needs calm-day matched extremes).",
                "prediction_unavailable": "No cached NOAA prediction brackets this time.",
            }.get(reason, reason))
        return 200, body

    def level_history(self, conn, now, t0: float, t1: float, resolution: str):
        rows = conn.execute(
            "SELECT d.*, r.time_source FROM derived d JOIN readings r ON r.id=d.reading_id WHERE d.t>=? AND d.t<=? "
            "ORDER BY d.t", (t0, t1)).fetchall()
        if resolution == "raw":
            series = []
            for r in rows:
                ok = r["valid"] == 1
                series.append({"t": iso(r["t"]), "level_m": _r(r["level_smooth_m"]) if ok else None,
                               "level_raw_m": _r(r["level_raw_m"]) if ok else None,
                               "predicted_m": _r(r["predicted_m"]), "residual_m": _r(r["residual_m"]) if ok else None,
                               "valid": ok, "reason": None if ok else r["invalid_reason"],
                               "time_source": r["time_source"]})
        else:
            step = {"5m": 300, "30m": 1800, "1h": 3600}.get(resolution)
            if step is None:
                return 400, {"status": "error", "error": _err("BAD_RESOLUTION", "resolution must be raw|5m|30m|1h")}
            from .derive import median
            pred = self._pred(conn, now, t0 - 86400, t1 + 86400)
            buckets: dict[int, list[float]] = {}
            for r in rows:
                if r["valid"] == 1 and r["level_raw_m"] is not None:
                    buckets.setdefault(int((r["t"] - t0) // step), []).append(r["level_raw_m"])
            series = []
            k = 0
            while t0 + k * step <= t1:
                c = t0 + (k + 0.5) * step
                vals = buckets.get(k)
                series.append({"t": iso(t0 + k * step), "level_m": _r(median(vals)) if vals else None,
                               "n": len(vals) if vals else 0, "predicted_m": _r(pred.predict(c)),
                               "valid": bool(vals), "reason": None if vals else "missing_packet"})
                k += 1
        return 200, {"status": "ok", "from": iso(t0), "to": iso(t1), "resolution": resolution,
                     "predicted_note": "predicted_m is a NOAA prediction, not an observation", "series": series}

    def residual(self, conn, now, hours: float):
        cfg = self.cfg
        t0 = now - hours * 3600
        rows = conn.execute("SELECT * FROM derived WHERE live=1 AND t>=? AND t<=? ORDER BY t DESC", (t0, now)).fetchall()
        series = []
        prev_t = now
        for r in rows:
            gap = prev_t - r["t"]
            k = 1
            while gap > 1.5 * cfg.node.interval_s and k * cfg.node.interval_s < gap - cfg.node.interval_s / 2:
                series.append({"t": iso(prev_t - k * cfg.node.interval_s), "residual_m": None, "valid": False,
                               "reason": "missing_packet"})
                k += 1
            ok = r["valid"] == 1 and r["residual_m"] is not None
            series.append({"t": iso(r["t"]), "residual_m": _r(r["residual_m"]) if ok else None, "valid": ok,
                           **({} if ok else {"reason": r["invalid_reason"] or r["residual_reason"]})})
            prev_t = r["t"]
        node = health.node_status(conn, cfg, now)
        last = health.last_valid_live(conn, now)
        pred = self._pred(conn, now)
        comp = dbmod.get_component(conn, "noaa")
        current = None
        if last is not None and node["status"] == "ok":
            a = cfg.alerts
            res = last["residual_m"]
            level = "none"
            if res is not None:
                level = "severe" if res >= a.surge_severe_m else "warning" if res >= a.surge_warning_m else "none"
            current = {"at": iso(last["t"]), "residual_m": _r(res), "excess_rise_m_per_h": _r(last["excess_rise_mph"]),
                       "alert_level": level}
        sh = reference_residual(conn, cfg.noaa.observed_reference, now)
        body = {
            "status": "ok" if current is not None and current["residual_m"] is not None else "stale"
            if node["status"] != "ok" else "error",
            "current": current,
            "series": series,
            "prediction_source": {"station": cfg.noaa.prediction_station, "method": "hilo_half_cosine",
                                  "fetched_at": iso(comp["detail"].get("last_success_at")) if comp else None,
                                  "covers_until": iso(pred.covers_until)},
            "reference": {"sandy_hook_8531680": {"status": "ok" if sh is not None else "error",
                                                 "residual_m": _r(sh)}},
            "weather_context": tempest.context(conn, cfg, now),
        }
        if body["status"] != "ok":
            body["error"] = (_err("NODE_STALE", "No current valid reading.") if node["status"] != "ok" else
                             _err("RESIDUAL_UNAVAILABLE", (last["residual_reason"] if last else None) or "unavailable"))
        return 200, body

    def predictions(self, conn, now, t0: float, t1: float):
        pred = self._pred(conn, now, t0 - 2 * 86400, t1 + 2 * 86400)
        ext = [{"t": iso(e.t), "v": e.v, "type": e.type} for e in pred.extremes_between(t0, t1)]
        series = []
        t = t0
        while t <= t1:
            series.append({"t": iso(t), "predicted_m": _r(pred.predict(t))})
            t += 600
        st = "ok" if pred.covers(t0) and pred.covers(t1) else "error"
        body = {"status": st, "station": self.cfg.noaa.prediction_station, "datum": "MLLW",
                "method": "hilo_half_cosine", "kind": "prediction", "extremes": ext, "series": series}
        if st != "ok":
            body["error"] = _err("PREDICTION_UNAVAILABLE", "cached predictions do not cover the whole range")
        return 200, body

    def node_health(self, conn, now):
        cfg = self.cfg
        last = health.last_reading(conn, now)
        if last is None:
            return 200, {"status": "error", "error": _err("NO_DATA", "No packet received yet."), "node_id": None,
                         "last_packet_at": None, "repeater": health.repeater_status(conn, cfg, now),
                         "gateway": health.gateway_status(conn, now)}
        age = now - last["rx_at"]
        t24 = now - 86400
        recv = conn.execute("SELECT COUNT(*) FROM readings WHERE t>? AND t<=?", (t24, now)).fetchone()[0]
        dups = conn.execute("SELECT COUNT(*) FROM packets_raw WHERE parse_status='duplicate' AND rx_at>? AND rx_at<=?",
                            (t24, now)).fetchone()[0]
        bad = conn.execute("SELECT COUNT(*) FROM packets_raw WHERE parse_status NOT IN ('ok','duplicate','wrong_channel',"
                           "'wrong_data_type') AND rx_at>? AND rx_at<=?", (t24, now)).fetchone()[0]
        expected = 86400 // cfg.node.interval_s
        seq_exp = 0
        for g in conn.execute("SELECT boot_count, MIN(seq), MAX(seq), COUNT(*) FROM readings WHERE t>? AND t<=? "
                              "GROUP BY boot_count", (t24, now)).fetchall():
            seq_exp += (g[2] - g[1] + 1)
        chg = last["chg_bits"] or 0
        flags = last["flags"] or 0
        charger = ("latch_fault" if chg & codec.CHG_LATCH_FAULT else "cold_inhibit" if chg & codec.CHG_COLD_INHIBIT
                   else "charging" if chg & codec.CHG_CHRG else "done" if chg & codec.CHG_DONE else "idle")
        bstate = "critical" if flags & codec.F_CRITICAL_BATT else "low" if flags & codec.F_LOW_BATT else "normal"
        soc = energy.soc_estimate(conn, cfg, now)
        gw = health.gateway_status(conn, now)
        rep = health.repeater_status(conn, cfg, now)
        node = health.node_status(conn, cfg, now)
        return 200, {
            "status": node["status"] if node["status"] != "silent" else "stale",
            "node_id": last["node_id"], "last_packet_at": iso(last["rx_at"]), "age_s": round(age),
            "seq": last["seq"], "boot_count": last["boot_count"],
            "link": {"snr_db": last["snr_db"], "path_len": last["path_len"],
                     "last_24h": {"received": recv, "expected": expected,
                                  "delivery_pct": round(100.0 * recv / expected, 2),
                                  "seq_based_delivery_pct": round(100.0 * recv / seq_exp, 2) if seq_exp else None,
                                  "duplicates": dups, "bad_frames": bad}},
            "sensor": {"pitch_deg": last["pitch_deg"], "pitch_sd_deg": last["pitch_sd_deg"],
                       "roll_deg": last["roll_deg"], "temp_c": last["temp_c"], "flags": _flags(flags)},
            "battery": {"voltage_v": None if last["vbat_mv"] is None else last["vbat_mv"] / 1000.0, "state": bstate,
                        "charger": charger, "cold_charge_inhibit": bool(chg & codec.CHG_COLD_INHIBIT),
                        "soc_est_pct": soc["soc_est_pct"]},
            "repeater": {"status": rep["status"], "last_relayed_frame_at": iso(rep["last_relayed_frame_at"]),
                         "last_advert_at": iso(rep["last_advert_at"]), "batt_mv": rep["batt_mv"]},
            "gateway": {"status": gw["status"], "transport": cfg.radio.transport,
                        "port": cfg.radio.port if cfg.radio.transport == "serial" else cfg.radio.host,
                        "connected_since": iso(gw["detail"].get("connected_since")) if gw["status"] == "ok" else None},
        }

    def node_energy(self, conn, now, days: int):
        cfg = self.cfg
        from .timeutil import local_date
        end = local_date(now)
        rows = conn.execute("SELECT * FROM energy_daily WHERE date >= ? AND date < ? ORDER BY date DESC",
                            ((end - _dt.timedelta(days=days)).isoformat(), end.isoformat())).fetchall()
        v = energy.verdict(conn, cfg, now)
        soc = energy.soc_estimate(conn, cfg, now)
        daily = [{
            "date": r["date"], "harvest_mah": _r(r["harvest_mah"], 1), "harvest_mwh": _r(r["harvest_mwh"], 0),
            "consumption_est_mah": _r(r["consumption_est_mah"], 2), "net_mah": _r(r["net_mah"], 1),
            "coverage_pct": _r(r["coverage_pct"], 1), "panel_peak_ma": _r(r["panel_peak_ma"], 1),
            "vbat_rest_v": _r(r["vbat_rest_v"]), "vbat_min_v": _r(r["vbat_min_v"]), "vbat_max_v": _r(r["vbat_max_v"]),
            "reached_full": bool(r["reached_full"]), "charging_h": _r(r["charging_h"], 2),
            "charge_inhibit_cold_h": _r(r["charge_inhibit_cold_h"], 2), "temp_min_c": _r(r["temp_min_c"], 1),
            "no_sun": (r["harvest_mah"] or 0) < 1.0 and (r["charge_inhibit_cold_h"] or 0) == 0,
            "i_sleep_ua": r["i_sleep_ua"], "i_awake_ma": _r(r["i_awake_ma"], 2)} for r in rows]
        st = "ok" if v["assessment"] != "insufficient_data" else "insufficient_data"
        body = {"status": st, "verdict": v,
                "battery": {"capacity_mah": cfg.energy.capacity_mah, "soc_est_pct": soc["soc_est_pct"],
                            "soc_anchor": (f"DONE at {iso(soc['soc_anchor']['at'])}" if soc["soc_anchor"] else None)},
                "daily": daily}
        if st != "ok":
            body["error"] = _err("INSUFFICIENT_DATA", f"fewer than {cfg.energy.min_verdict_days} days at "
                                                      f">= {cfg.energy.min_coverage_pct:g}% coverage")
        return 200, body

    def energy_samples(self, conn, now, t0: float, t1: float):
        rows = conn.execute("SELECT t, vbat_mv, vpanel_mv, ipanel_ma, chg_bits, temp_c, awake_ms_prev, flags FROM "
                            "readings WHERE t>=? AND t<=? ORDER BY t", (t0, t1)).fetchall()
        return 200, {"status": "ok", "samples": [{
            "t": iso(r["t"]), "vbat_v": None if r["vbat_mv"] is None else r["vbat_mv"] / 1000.0,
            "vpanel_v": None if r["vpanel_mv"] is None else r["vpanel_mv"] / 1000.0, "ipanel_ma": r["ipanel_ma"],
            "chg": [n for b, n in codec.CHG_NAMES.items() if (r["chg_bits"] or 0) & b], "temp_c": r["temp_c"],
            "awake_ms_prev": r["awake_ms_prev"]} for r in rows]}

    def weather_current(self, conn, now):
        cfg = self.cfg
        ts = tempest.tempest_status(conn, cfg, now)
        if ts["status"] != "ok":
            return 200, {"status": ts["status"], "error": ts.get("error"), "pressure": None, "wind": None,
                         "rain": None, "air_temp_c": None}
        o = conn.execute("SELECT * FROM tempest_obs ORDER BY obs_at DESC LIMIT 1").fetchone()
        ctx = tempest.context(conn, cfg, now)
        lo, hi = cfg.tempest.onshore_sector_deg
        return 200, {
            "status": "ok", "source": "tempest_rest", "station_id": cfg.tempest.station_id,
            "obs_at": iso(o["obs_at"]), "age_s": round(now - o["obs_at"]),
            "pressure": {"sea_level_hpa": o["slp_hpa"], "station_hpa": o["station_hpa"],
                         "change_3h_hpa": ctx["pressure_change_3h_hpa"], "inverse_barometer_m": ctx["inverse_barometer_m"]},
            "wind": {"avg_mps": o["wind_avg"], "gust_mps": o["wind_gust"], "dir_deg": o["wind_dir"],
                     "onshore_now": None if o["wind_dir"] is None else bool(lo <= o["wind_dir"] <= hi),
                     "sustained_6h": {"mean_mps": ctx["wind_6h_mean_mps"], "mean_dir_deg": ctx["wind_6h_mean_dir_deg"],
                                      "onshore_sustained": ctx["onshore_wind_sustained"], "sector_deg": [lo, hi],
                                      "threshold_mps": cfg.tempest.onshore_min_mps}},
            "rain": {"last_1h_mm": o["rain_1h_mm"], "today_mm": o["rain_day_mm"]},
            "air_temp_c": o["air_c"]}

    def alerts(self, conn, now, state: str, since: float | None):
        q = "SELECT * FROM alerts WHERE 1=1"
        args: list = []
        if state == "open":
            q += " AND cleared_at IS NULL"
        if since is not None:
            q += " AND opened_at >= ?"
            args.append(since)
        rows = conn.execute(q + " ORDER BY opened_at DESC", args).fetchall()
        import json
        return 200, {"status": "ok", "alerts": [{
            "id": r["id"], "kind": r["kind"], "severity": r["severity"], "opened_at": iso(r["opened_at"]),
            "cleared_at": iso(r["cleared_at"]), "state": "open" if r["cleared_at"] is None else "cleared",
            "clear_condition": r["clear_condition"], "value": r["value"], "threshold": r["threshold"],
            "notified_at": iso(r["notified_at"]), "context": json.loads(r["context_json"] or "{}")} for r in rows]}

    def calibration(self, conn, now):
        import json
        rows = conn.execute("SELECT * FROM calibrations ORDER BY id").fetchall()
        active = self._cal(conn, now)
        items = [{"id": r["id"], "created_at": iso(r["created_at"]), "valid_from": iso(r["valid_from"]),
                  "theta0_deg": r["theta0_deg"], "h0_m": r["h0_m"], "l_eff_m": r["l_eff_m"], "k_t": r["k_t"],
                  "pitch_envelope_deg": [r["pitch_min_deg"], r["pitch_max_deg"]], "method": r["method"],
                  "status": r["status"], "datum": r["datum"],
                  "fit_stats": json.loads(r["fit_stats_json"] or "{}")} for r in rows]
        for it in items:
            it["fit_stats"].pop("pairs", None)
        if active is None:
            return 200, {"status": "error", "error": _err("NO_CALIBRATION", "no active calibration"), "active": None,
                         "history": items}
        return 200, {"status": "ok", "active": next(i for i in items if i["id"] == active.id), "history": items,
                     "datum": DATUM_MLLW if active.datum_tied else DATUM_MARK}


def create_app(cfg, db_path: str, clock: Clock | None = None) -> FastAPI:
    clock = clock or SystemClock()
    views = Views(cfg)
    app = FastAPI(title="tidesvc", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None)

    def run(fn, *a):
        conn = dbmod.connect_ro(db_path)
        try:
            code, body = fn(conn, clock.now(), *a)
        finally:
            conn.close()
        return JSONResponse(body, status_code=code)

    def _t(s: str | None, default: float) -> float:
        return parse_iso(s) if s else default

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/api/v1/status")
    def status():
        return run(views.status)

    @app.get("/api/v1/level/current")
    def level_current():
        return run(views.level_current)

    @app.get("/api/v1/level/history")
    def level_history(from_: str | None = Query(None, alias="from"), to: str | None = None, resolution: str = "raw"):
        now = clock.now()
        return run(views.level_history, _t(from_, now - 86400), _t(to, now), resolution)

    @app.get("/api/v1/residual")
    def residual(hours: float = 48):
        return run(views.residual, max(1.0, min(hours, 24 * 31)))

    @app.get("/api/v1/predictions")
    def predictions(from_: str | None = Query(None, alias="from"), to: str | None = None):
        now = clock.now()
        return run(views.predictions, _t(from_, now - 86400), _t(to, now + 2 * 86400))

    @app.get("/api/v1/node/health")
    def node_health():
        return run(views.node_health)

    @app.get("/api/v1/node/energy")
    def node_energy(days: int = 30):
        return run(views.node_energy, max(1, min(days, 400)))

    @app.get("/api/v1/node/energy/samples")
    def energy_samples(from_: str | None = Query(None, alias="from"), to: str | None = None):
        now = clock.now()
        return run(views.energy_samples, _t(from_, now - 86400), _t(to, now))

    @app.get("/api/v1/weather/current")
    def weather_current():
        return run(views.weather_current)

    @app.get("/api/v1/alerts")
    def alerts(state: str = "open", since: str | None = None):
        return run(views.alerts, state, parse_iso(since) if since else None)

    @app.get("/api/v1/calibration")
    def calibration():
        return run(views.calibration)

    @app.get("/api/v1/export/{day}.csv")
    def export_csv(day: str):
        try:
            d = _dt.date.fromisoformat(day)
        except ValueError:
            return JSONResponse({"status": "error", "error": _err("BAD_DATE", "use YYYY-MM-DD")}, status_code=400)
        conn = dbmod.connect_ro(db_path)
        try:
            text = export.daily_csv(conn, d, cfg.node.interval_s)
        finally:
            conn.close()
        return PlainTextResponse(text, media_type="text/csv")

    return app


__all__ = ["create_app", "Views", "sqlite3"]
