"""Calibration (ARCHITECTURE 6.5, ADR-009; E6.4, E6.5).

theta0 is fixed from the install level check (node pitch minus reference
digital-level angle). Only h0 (offset) and L_eff (scale) are ever fitted.

- Install fit: >= 2 tape observations (bulkhead mark -> float reference) at tide
  states >= 0.5 m apart. level relative to the mark = -freeboard. Datum is
  'bulkhead_mark' until tied.
- Datum tie: calm-day matched extremes (observed, centred smoothing, within
  +/-90 min of each NOAA predicted extreme) shift h0 into MLLW. L_eff unchanged.
- Monthly refit: the same matched-extremes set over the last 30 days, least
  squares for (h0, L_eff). Applied automatically if |dh0| <= 0.05 m and
  |dL/L| <= 3%; otherwise stored as 'proposed' (raises CALIBRATION_DRIFT via the
  alert engine) until ``approve``/``reject``.

Spec gap SV-C7 (DEV-PLAN 7 item 6), proposal implemented here: a monthly refit
needs >= 12 matched calm-day extremes (about 3 calm days' worth) and both
extreme types; a datum tie needs >= 4. Below that nothing is fitted or applied.
"""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import asdict, dataclass

from .derive import Calibration, Deriver, centred_series, find_extreme_near, load_calibrations, calibration_at, median
from .noaa import load_predictor
from .timeutil import local_date, local_day_bounds

# Install envelope: accept levels from (lowest tape level - below) to
# (highest tape level + above). Wide on purpose: the envelope must not reject a
# real surge (ARCHITECTURE's +/-0.5 deg margin is only ~6.6 cm of level).
ENVELOPE_BELOW_M = 1.0
ENVELOPE_ABOVE_M = 2.0


class CalibrationError(ValueError):
    pass


# --------------------------------------------------------------------------- observations
def node_pitch_at(conn: sqlite3.Connection, t: float, half_window_s: float = 600, min_n: int = 3,
                  max_sd_deg: float = 0.25) -> tuple[float, int]:
    rows = conn.execute(
        "SELECT pitch_deg, pitch_sd_deg, flags FROM readings WHERE t BETWEEN ? AND ? AND pitch_deg IS NOT NULL",
        (t - half_window_s, t + half_window_s)).fetchall()
    good = [r[0] for r in rows if (r[2] & ((1 << 7) | (1 << 10) | (1 << 3))) == 0 and (r[1] or 0) <= max_sd_deg]
    if len(good) < min_n:
        raise CalibrationError(f"need >= {min_n} good packets around the observation, found {len(good)}")
    return median(good), len(good)


def add_observation(conn: sqlite3.Connection, t: float, kind: str, *, freeboard_m: float | None = None,
                    angle_deg: float | None = None, pitch_deg: float | None = None, note: str = "") -> int:
    if kind not in ("tape", "level_check"):
        raise CalibrationError("kind must be 'tape' or 'level_check'")
    if kind == "tape" and freeboard_m is None:
        raise CalibrationError("tape observation needs freeboard_m")
    if kind == "level_check" and angle_deg is None:
        raise CalibrationError("level_check observation needs angle_deg (reference digital level)")
    if pitch_deg is None:
        pitch_deg, _ = node_pitch_at(conn, t)
    cur = conn.execute(
        "INSERT INTO cal_observations(t, kind, freeboard_m, angle_deg, pitch_deg, note) VALUES (?,?,?,?,?,?)",
        (t, kind, freeboard_m, angle_deg, pitch_deg, note))
    return int(cur.lastrowid)


def _insert_cal(conn: sqlite3.Connection, now: float, valid_from: float, theta0: float, h0: float, l_eff: float,
                k_t: float, pmin: float | None, pmax: float | None, method: str, status: str, datum: str,
                stats: dict) -> int:
    cur = conn.execute(
        "INSERT INTO calibrations(created_at, valid_from, theta0_deg, h0_m, l_eff_m, k_t, pitch_min_deg, "
        "pitch_max_deg, method, status, datum, fit_stats_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (now, valid_from, theta0, h0, l_eff, k_t, pmin, pmax, method, status, datum, json.dumps(stats)))
    return int(cur.lastrowid)


def _envelope(theta0: float, h0: float, l_eff: float, lvl_lo: float, lvl_hi: float) -> tuple[float, float]:
    def pitch_for(level: float) -> float:
        x = max(-1.0, min(1.0, (level - h0) / l_eff))
        return theta0 + math.degrees(math.asin(x))
    return pitch_for(lvl_lo), pitch_for(lvl_hi)


# --------------------------------------------------------------------------- install
def fit_install(conn: sqlite3.Connection, cfg, now: float, valid_from: float | None = None,
                k_t: float = 0.0) -> int:
    obs = conn.execute("SELECT * FROM cal_observations ORDER BY t").fetchall()
    checks = [o for o in obs if o["kind"] == "level_check"]
    tapes = [o for o in obs if o["kind"] == "tape"]
    if not checks:
        raise CalibrationError("no level_check observation: theta0 must come from the install level reading")
    lc = checks[-1]
    theta0 = lc["pitch_deg"] - lc["angle_deg"]
    if len(tapes) < 2:
        raise CalibrationError("need >= 2 tape observations")
    ys = [-o["freeboard_m"] for o in tapes]
    if max(ys) - min(ys) < cfg.calibration.min_install_span_m:
        raise CalibrationError(
            f"tape observations span {max(ys) - min(ys):.3f} m < {cfg.calibration.min_install_span_m} m")
    ss = [math.sin(math.radians(o["pitch_deg"] - theta0)) for o in tapes]
    n = len(ys)
    ms, my = sum(ss) / n, sum(ys) / n
    den = sum((s - ms) ** 2 for s in ss)
    l_eff = sum((s - ms) * (y - my) for s, y in zip(ss, ys)) / den
    h0 = my - l_eff * ms
    resid = [y - (h0 + l_eff * s) for s, y in zip(ss, ys)]
    pmin, pmax = _envelope(theta0, h0, l_eff, min(ys) - ENVELOPE_BELOW_M, max(ys) + ENVELOPE_ABOVE_M)
    stats = {"n_tape": n, "span_m": max(ys) - min(ys), "residuals_m": resid, "theta0_from_obs": lc["id"],
             "tape_obs": [o["id"] for o in tapes]}
    vf = valid_from if valid_from is not None else min(o["t"] for o in obs)
    return _insert_cal(conn, now, vf, theta0, h0, l_eff, k_t, pmin, pmax, "install", "active",
                       "bulkhead_mark", stats)


# --------------------------------------------------------------------------- matched extremes
@dataclass(frozen=True)
class MatchedExtreme:
    pred_t: float
    pred_v: float
    obs_t: float
    obs_v: float
    type: str
    s_obs: float  # sin(pitch - theta0) at the observed extreme

    @property
    def dt_min(self) -> float:
        return (self.obs_t - self.pred_t) / 60.0


def calm_days(conn: sqlite3.Connection, station: str, t0: float, t1: float, threshold_m: float,
              min_points: int = 120) -> set:
    rows = conn.execute(
        "SELECT t, v, pred_v FROM noaa_observations WHERE station=? AND t>=? AND t<=? AND v IS NOT NULL "
        "AND pred_v IS NOT NULL", (station, t0 - 86400, t1 + 86400)).fetchall()
    by_day: dict = {}
    for r in rows:
        by_day.setdefault(local_date(r[0]), []).append(abs(r[1] - r[2]))
    return {d for d, res in by_day.items() if len(res) >= min_points and max(res) < threshold_m}


def matched_extremes(conn: sqlite3.Connection, cfg, cal: Calibration, t0: float, t1: float,
                     require_calm: bool = True) -> list[MatchedExtreme]:
    c = cfg.calibration
    pred = load_predictor(conn, cfg.noaa.prediction_station)
    series = centred_series(conn, t0 - 4 * 3600, t1 + 4 * 3600, c.window_min, c.min_points, cal=cal)
    sts = [p[0] for p in series]
    svs = [p[1] for p in series]
    calm = calm_days(conn, cfg.noaa.observed_reference, t0, t1, c.calm_residual_m) if require_calm else None
    out = []
    for e in pred.extremes_between(t0, t1):
        if calm is not None and local_date(e.t) not in calm:
            continue
        ob = find_extreme_near(sts, svs, e.t, e.type, search_s=c.match_window_min * 60 + 3600)
        if ob is None or abs(ob.t - e.t) > c.match_window_min * 60:
            continue
        out.append(MatchedExtreme(pred_t=e.t, pred_v=e.v, obs_t=ob.t, obs_v=ob.v, type=e.type,
                                  s_obs=(ob.v - cal.h0_m) / cal.l_eff_m))
    return out


# --------------------------------------------------------------------------- datum tie
def datum_tie(conn: sqlite3.Connection, cfg, deriver: Deriver, now: float, t0: float, t1: float,
              valid_from: float | None = None, reprocess: bool = True) -> dict:
    cals = load_calibrations(conn)
    cal = calibration_at(cals, t1)
    if cal is None:
        raise CalibrationError("no active calibration to tie")
    pairs = matched_extremes(conn, cfg, cal, t0, t1)
    need = cfg.calibration.min_matched_extremes_datum
    if len(pairs) < need:
        return {"applied": False, "reason": f"only {len(pairs)} matched calm-day extremes (need {need})",
                "n": len(pairs)}
    shift = sum(p.pred_v - p.obs_v for p in pairs) / len(pairs)  # least squares for h0 only
    vf = valid_from if valid_from is not None else cal.valid_from
    stats = {"n": len(pairs), "shift_m": shift, "pairs": [asdict(p) for p in pairs], "window": [t0, t1],
             "based_on": cal.id}
    pmin, pmax = cal.pitch_min_deg, cal.pitch_max_deg
    cid = _insert_cal(conn, now, vf, cal.theta0_deg, cal.h0_m + shift, cal.l_eff_m, cal.k_t, pmin, pmax,
                      "datum_tie", "active", "MLLW", stats)
    deriver.invalidate()
    if reprocess:
        deriver.reprocess(vf)
    return {"applied": True, "calibration_id": cid, "shift_m": shift, "n": len(pairs)}


# --------------------------------------------------------------------------- monthly refit
def within_bounds(dh0_m: float, dl_rel: float, ccfg) -> bool:
    """Auto-apply bounds: |dh0| <= 0.05 m and |dL/L| <= 3% (inclusive)."""
    return abs(dh0_m) <= ccfg.refit_h0_m + 1e-12 and abs(dl_rel) <= ccfg.refit_l_eff_rel + 1e-12


def monthly_refit(conn: sqlite3.Connection, cfg, deriver: Deriver, now: float) -> dict:
    c = cfg.calibration
    cals = load_calibrations(conn)
    cal = calibration_at(cals, now)
    if cal is None or not cal.datum_tied:
        return {"applied": False, "status": "skipped", "reason": "no datum-tied calibration active"}
    t0 = now - c.refit_days * 86400
    pairs = matched_extremes(conn, cfg, cal, t0, now)
    types = {p.type for p in pairs}
    if len(pairs) < c.min_matched_extremes_refit or types != {"H", "L"}:
        return {"applied": False, "status": "skipped",
                "reason": f"{len(pairs)} matched calm-day extremes (need {c.min_matched_extremes_refit}, both H and L)",
                "n": len(pairs)}
    ss = [p.s_obs for p in pairs]
    ys = [p.pred_v for p in pairs]
    n = len(ss)
    ms, my = sum(ss) / n, sum(ys) / n
    den = sum((s - ms) ** 2 for s in ss)
    l_new = sum((s - ms) * (y - my) for s, y in zip(ss, ys)) / den
    h_new = my - l_new * ms
    rms = math.sqrt(sum((y - (h_new + l_new * s)) ** 2 for s, y in zip(ss, ys)) / n)
    dh = h_new - cal.h0_m
    dl_rel = (l_new - cal.l_eff_m) / cal.l_eff_m
    within = within_bounds(dh, dl_rel, c)
    stats = {"n": n, "dh0_m": dh, "dl_rel": dl_rel, "rms_m": rms, "based_on": cal.id,
             "bounds": {"h0_m": c.refit_h0_m, "l_eff_rel": c.refit_l_eff_rel}, "within_bounds": within,
             "window": [t0, now]}
    status = "active" if within else "proposed"
    cid = _insert_cal(conn, now, now, cal.theta0_deg, h_new, l_new, cal.k_t, cal.pitch_min_deg,
                      cal.pitch_max_deg, "monthly_refit", status, "MLLW", stats)
    deriver.invalidate()
    return {"applied": within, "status": status, "calibration_id": cid, "dh0_m": dh, "dl_rel": dl_rel,
            "n": n, "rms_m": rms}


def approve(conn: sqlite3.Connection, cal_id: int, deriver: Deriver | None = None) -> None:
    row = conn.execute("SELECT status FROM calibrations WHERE id=?", (cal_id,)).fetchone()
    if row is None or row[0] != "proposed":
        raise CalibrationError(f"calibration {cal_id} is not proposed")
    conn.execute("UPDATE calibrations SET status='active' WHERE id=?", (cal_id,))
    if deriver is not None:
        deriver.invalidate()


def reject(conn: sqlite3.Connection, cal_id: int) -> None:
    row = conn.execute("SELECT status FROM calibrations WHERE id=?", (cal_id,)).fetchone()
    if row is None or row[0] != "proposed":
        raise CalibrationError(f"calibration {cal_id} is not proposed")
    conn.execute("UPDATE calibrations SET status='rejected' WHERE id=?", (cal_id,))


def is_refit_due(now: float, last_run: float | None) -> bool:
    """Monthly refit: the 1st of the month at 03:00 local, once."""
    import datetime as _dt

    from .timeutil import LOCAL_TZ

    d = _dt.datetime.fromtimestamp(now, LOCAL_TZ)
    sched = _dt.datetime(d.year, d.month, 1, 3, 0, tzinfo=LOCAL_TZ).timestamp()
    return now >= sched and (last_run is None or last_run < sched)


__all__ = ["add_observation", "fit_install", "datum_tie", "monthly_refit", "approve", "reject",
           "matched_extremes", "calm_days", "node_pitch_at", "CalibrationError", "is_refit_due",
           "local_day_bounds"]
