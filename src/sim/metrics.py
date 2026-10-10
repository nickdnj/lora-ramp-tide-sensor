"""Acceptance metrics computed from a finished simulation (truth vs what the
service stored and served)."""

from __future__ import annotations

import datetime as _dt
import json
import math
import sqlite3

import numpy as np

from tidesvc import energy as energymod
from tidesvc.derive import centred_median, find_extreme_near
from tidesvc.timeutil import iso, local_day_bounds

from .engine import SimResult


def _stats(err) -> dict:
    e = np.asarray(err, dtype=float)
    if len(e) == 0:
        return {"n": 0}
    return {"n": int(len(e)), "rms_cm": float(np.sqrt(np.mean(e ** 2)) * 100), "bias_cm": float(np.mean(e) * 100),
            "p95_abs_cm": float(np.percentile(np.abs(e), 95) * 100), "max_abs_cm": float(np.max(np.abs(e)) * 100)}


def accuracy(r: SimResult, conn: sqlite3.Connection) -> dict:
    tie_t = r.events["install"]["datum_tie_t"]
    rows = conn.execute("SELECT d.t, d.level_raw_m, d.level_smooth_m, d.live, d.valid, d.residual_m, r.t AS rt "
                        "FROM derived d JOIN readings r ON r.id=d.reading_id WHERE d.t >= ? ORDER BY d.t",
                        (tie_t,)).fetchall()
    w = r.world
    live = [x for x in rows if x["live"] == 1 and x["valid"] == 1 and x["level_smooth_m"] is not None]
    t = np.array([x["t"] for x in live])
    smooth = np.array([x["level_smooth_m"] for x in live])
    out = {"window": [iso(tie_t), iso(r.t1)]}
    out["live_trailing_vs_truth_now"] = _stats(smooth - w.water(t))
    out["live_trailing_vs_truth_window_centre"] = _stats(smooth - w.water(t - 750.0))
    valid = [x for x in rows if x["valid"] == 1 and x["level_raw_m"] is not None]
    tv = np.array([x["t"] for x in valid])
    raw = np.array([x["level_raw_m"] for x in valid])
    out["raw_per_reading"] = _stats(raw - w.water(tv))
    cen = centred_median(list(tv), list(raw), 30, 4)
    ct = np.array([c[0] for c in cen])
    cv = np.array([c[1] for c in cen])
    out["centred_30min"] = _stats(cv - w.water(ct))
    # truth residual vs service residual (both lag-matched)
    res = [(x["t"], x["residual_m"]) for x in live if x["residual_m"] is not None]
    if res:
        rt = np.array([a for a, _ in res])
        rv = np.array([b for _, b in res])
        true_res = w.residual(rt - 750.0)
        out["residual_vs_true_residual"] = _stats(rv - true_res)
    out["_series"] = {"t": tv, "raw": raw, "ct": ct, "cv": cv, "lt": t, "smooth": smooth}
    return out


def hilo_timing(r: SimResult, acc: dict) -> dict:
    s = acc["_series"]
    w = r.world
    t0, t1 = r.events["install"]["datum_tie_t"], r.t1 - 6 * 3600
    # true extremes of the real water (astro + surge + weather), from a fine grid
    tg = np.arange(t0, t1, 60.0)
    v = w.water(tg)
    d = np.diff(v)
    true_ext = []
    for i in range(1, len(d)):
        if (d[i - 1] > 0 >= d[i]) or (d[i - 1] < 0 <= d[i]):
            typ = "H" if d[i - 1] > 0 else "L"
            # ignore weather-noise wiggles: require a real extreme over +/-2 h
            lo, hi = max(0, i - 120), min(len(v), i + 120)
            seg = v[lo:hi]
            if (typ == "H" and v[i] >= seg.max() - 1e-9) or (typ == "L" and v[i] <= seg.min() + 1e-9):
                true_ext.append((tg[i], v[i], typ))
    dts, dvs, missing = [], [], 0
    pred_dts = []
    noaa = {round(e[0]): e for e in w.astro_extremes(t0 - 3600, t1 + 3600)}
    for te, ve, typ in true_ext:
        ob = find_extreme_near(list(s["ct"]), list(s["cv"]), te, typ)
        if ob is None or abs(ob.t - te) > 90 * 60:
            missing += 1
            continue
        dts.append((ob.t - te) / 60.0)
        dvs.append((ob.v - ve) * 100.0)
        near = min(noaa.values(), key=lambda e: abs(e[0] - te))
        pred_dts.append((ob.t - near[0]) / 60.0)
    a = np.abs(np.array(dts))
    return {"n_true_extremes": len(true_ext), "n_found": len(dts), "n_missing": missing,
            "dt_min_mean": float(np.mean(dts)) if dts else None,
            "dt_min_rms": float(np.sqrt(np.mean(np.square(dts)))) if dts else None,
            "dt_min_max_abs": float(a.max()) if dts else None,
            "dt_min_p95_abs": float(np.percentile(a, 95)) if dts else None,
            "height_cm_rms": float(np.sqrt(np.mean(np.square(dvs)))) if dvs else None,
            "height_cm_max_abs": float(np.max(np.abs(dvs))) if dvs else None,
            "vs_noaa_predicted_dt_min_rms": float(np.sqrt(np.mean(np.square(pred_dts)))) if pred_dts else None}


def surge(r: SimResult, conn: sqlite3.Connection) -> dict:
    if not r.events["surges"]:
        return {"present": False}
    w = r.world
    peak_t, peak_m = r.events["surges"][0]
    tg = np.arange(peak_t - 2 * 86400, peak_t + 2 * 86400, 60.0)
    true_res = w.residual(tg)
    out = {"present": True, "peak_t": iso(peak_t), "peak_true_m": float(true_res.max())}
    for kind, thr in (("SURGE_WARNING", 0.30), ("SURGE_SEVERE", 0.60), ("RAPID_RISE", None)):
        row = conn.execute("SELECT * FROM alerts WHERE kind=? AND opened_at BETWEEN ? AND ? ORDER BY opened_at "
                           "LIMIT 1", (kind, peak_t - 2 * 86400, peak_t + 2 * 86400)).fetchone()
        d = {"opened_at": iso(row["opened_at"]) if row else None, "cleared_at": iso(row["cleared_at"]) if row else None,
             "value": row["value"] if row else None}
        if thr is not None:
            idx = np.argmax(true_res >= thr) if (true_res >= thr).any() else None
            cross = float(tg[idx]) if idx is not None else None
            d["true_cross_at"] = iso(cross)
            d["latency_min"] = (row["opened_at"] - cross) / 60.0 if row and cross else None
            below = tg[(tg > peak_t) & (true_res < thr - 0.10)]
            d["true_clear_level_at"] = iso(float(below[0])) if len(below) else None
        else:
            slope = np.gradient(true_res, tg) * 3600
            d["true_max_rate_m_per_h"] = float(slope.max())
            d["true_rate_above_0.15_at"] = iso(float(tg[np.argmax(slope >= 0.15)])) if (slope >= 0.15).any() else None
            if row and (slope >= 0.15).any():
                d["latency_min"] = (row["opened_at"] - float(tg[np.argmax(slope >= 0.15)])) / 60.0
        out[kind] = d
    m = conn.execute("SELECT MAX(residual_m) FROM derived WHERE live=1 AND t BETWEEN ? AND ?",
                     (peak_t - 86400, peak_t + 86400)).fetchone()[0]
    out["measured_peak_residual_m"] = m
    n_emails = sum(1 for s, _ in r.notifier.sent if "SURGE" in s or "RAPID_RISE" in s)
    out["surge_emails"] = n_emails
    return out


def outage(r: SimResult, conn: sqlite3.Connection) -> dict:
    out = {}
    for a, b in r.radio.repeater_outages:
        last_before = conn.execute("SELECT MAX(t) FROM derived WHERE live=1 AND valid=1 AND t < ?", (a + 60,)).fetchone()[0]
        probes = [p for p in r.probes if a <= p.t <= b]
        stale_from = (last_before or a) + r.cfg.node.stale_after_s
        after_stale = [p for p in probes if p.t > stale_from + 1]
        before_stale = [p for p in probes if p.t <= stale_from]
        alerts = {k: conn.execute("SELECT opened_at, cleared_at FROM alerts WHERE kind=? AND opened_at BETWEEN ? AND ?",
                                  (k, a, b + 3600)).fetchone() for k in ("NODE_SILENT", "REPEATER_SILENT")}
        readings_inside = conn.execute("SELECT COUNT(*) FROM readings WHERE t > ? AND t < ?", (a + 5, b)).fetchone()[0]
        out["repeater_outage"] = {
            "window": [iso(a), iso(b)], "hours": (b - a) / 3600,
            "probes_in_window": len(probes),
            "probes_after_stale_threshold": len(after_stale),
            "of_which_503": sum(1 for p in after_stale if p.code == 503),
            "of_which_level_null": sum(1 for p in after_stale if p.level_m is None),
            "of_which_last_good_labelled": sum(1 for p in after_stale if p.last_good_at),
            "status_values": sorted({p.status for p in after_stale}),
            "probes_before_stale_200": sum(1 for p in before_stale if p.code == 200),
            "readings_stored_inside_window": readings_inside,
            "NODE_SILENT_opened_after_min": (alerts["NODE_SILENT"][0] - (last_before or a)) / 60 if alerts["NODE_SILENT"] else None,
            "REPEATER_SILENT_opened_after_h": (alerts["REPEATER_SILENT"][0] - a) / 3600 if alerts["REPEATER_SILENT"] else None,
            "REPEATER_SILENT_cleared": bool(alerts["REPEATER_SILENT"] and alerts["REPEATER_SILENT"][1]),
        }
    for a, b in r.radio.host_disconnects:
        bf = conn.execute("SELECT COUNT(*) FROM readings WHERE time_source='backfilled' AND rx_at BETWEEN ? AND ?",
                          (b, b + 60)).fetchone()[0]
        gd = conn.execute("SELECT opened_at, cleared_at FROM alerts WHERE kind='GATEWAY_DOWN' AND opened_at BETWEEN ? AND ?",
                          (a, b + 600)).fetchone()
        probes = [p for p in r.probes if a <= p.t <= b + 1800]
        bf_err = []
        for row in conn.execute("SELECT r.t, r.boot_count, r.seq FROM readings r WHERE time_source='backfilled' "
                                "AND rx_at BETWEEN ? AND ?", (b, b + 60)):
            tx = [x for x in r.tx_log if x[1] == row[1] and x[2] == row[2]]
            if tx:
                bf_err.append((row[0] - tx[0][0]) / 60.0)
        out["gateway_disconnect"] = {
            "window": [iso(a), iso(b)], "minutes": (b - a) / 60, "frames_queued": r.radio.stats.queued,
            "backfilled_readings": bf, "backfill_time_error_min": [round(x, 1) for x in bf_err],
            "GATEWAY_DOWN": [iso(gd[0]), iso(gd[1])] if gd else None,
            "probe_codes": sorted({p.code for p in probes}),
            "level_served_during_gap": sum(1 for p in probes if p.code == 200 and a + 900 < p.t < b),
        }
    return out


def link(r: SimResult, conn: sqlite3.Connection) -> dict:
    st = r.radio.stats
    statuses = dict(conn.execute("SELECT parse_status, COUNT(*) FROM packets_raw GROUP BY 1").fetchall())
    dup_keys = conn.execute("SELECT COUNT(*) FROM (SELECT node_id, boot_count, seq, COUNT(*) c FROM readings "
                            "GROUP BY 1,2,3 HAVING c > 1)").fetchone()[0]
    n_read = conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
    keys = {(a, b) for a, b in conn.execute("SELECT boot_count, seq FROM readings")}
    lost_by_queue = st.queue_dropped
    return {"transmitted": st.tx, "delivered_unique_by_radio": st.delivered_unique,
            "copies_delivered": st.copies_delivered, "duplicate_copies_by_radio": st.duplicates,
            "corrupted_copies": st.corrupted, "foreign_frames": st.foreign,
            "packets_raw_by_status": statuses, "readings_stored": n_read, "duplicate_reading_keys": dup_keys,
            "intact_unique_keys_delivered": len(st.intact_keys),
            "readings_match_intact_keys": keys == st.intact_keys, "queue_dropped": lost_by_queue,
            "delivery_pct": 100.0 * n_read / st.tx if st.tx else None,
            "lost": st.lost, "lost_in_outage": st.lost_in_outage}


def energy_check(r: SimResult, conn: sqlite3.Connection) -> dict:
    cfg = r.cfg
    v = energymod.verdict(conn, cfg, r.t1)
    first, last = v["window"]
    days = [d for d in r.power.truth if first <= d.isoformat() <= last]
    th = sum(r.power.truth[d]["harvest_mah"] for d in days)
    ta = sum(r.power.truth[d]["available_mah"] for d in days)
    tc = sum(r.power.truth[d]["consumption_mah"] for d in days)
    true_ratio = th / tc if tc else None
    avail_ratio = ta / tc if tc else None
    rows = conn.execute("SELECT * FROM energy_daily WHERE date BETWEEN ? AND ? ORDER BY date", (first, last)).fetchall()
    # naive ARCHITECTURE 6.6 harvest (raw ipanel integral) for comparison
    naive = 0.0
    for d in days:
        s, e = local_day_bounds(d)
        rs = conn.execute("SELECT t, ipanel_ma FROM readings WHERE t>=? AND t<? AND ipanel_ma IS NOT NULL ORDER BY t",
                          (s, e)).fetchall()
        for a, b in zip(rs, rs[1:]):
            if b[0] - a[0] <= 900:
                naive += (a[1] + b[1]) / 2 * (b[0] - a[0]) / 3600
    svc_h = sum(x["harvest_mah"] for x in rows)
    svc_c = sum(x["consumption_est_mah"] for x in rows)
    per_day = []
    for x in rows:
        d = _dt.date.fromisoformat(x["date"])
        tr = r.power.truth.get(d, {})
        per_day.append({"date": x["date"], "svc_harvest": round(x["harvest_mah"], 1),
                        "true_harvest": round(tr.get("harvest_mah", float("nan")), 1),
                        "true_available": round(tr.get("available_mah", float("nan")), 1),
                        "svc_cons": round(x["consumption_est_mah"], 2),
                        "true_cons": round(tr.get("consumption_mah", float("nan")), 2),
                        "svc_cold_h": round(x["charge_inhibit_cold_h"], 2),
                        "true_cold_h": round(tr.get("cold_inhibit_h", float("nan")), 2),
                        "full": bool(x["reached_full"]), "coverage": round(x["coverage_pct"], 1),
                        "psh": round(tr.get("psh", float("nan")), 2)})
    return {"verdict": v, "true_accepted_ratio": true_ratio, "true_available_ratio": avail_ratio,
            "true_assessment": energymod.assessment_for_ratio(avail_ratio) if avail_ratio else None,
            "true_available_mah": ta,
            "service_harvest_mah": svc_h, "true_harvest_mah": th, "service_consumption_mah": svc_c,
            "true_consumption_mah": tc, "naive_raw_ipanel_harvest_mah": naive,
            "naive_ratio": naive / svc_c if svc_c else None,
            "min_true_soc_pct": min(r.power.truth[d]["min_soc_pct"] for d in r.power.truth),
            "per_day": per_day}


def refit(r: SimResult, conn: sqlite3.Connection) -> dict:
    cals = [dict(x) for x in conn.execute("SELECT id, valid_from, method, status, datum, theta0_deg, h0_m, l_eff_m, "
                                          "fit_stats_json FROM calibrations ORDER BY id")]
    for c in cals:
        fs = json.loads(c.pop("fit_stats_json") or "{}")
        fs.pop("pairs", None)
        c["fit_stats"] = fs
        c["valid_from"] = iso(c["valid_from"])
    true_theta0 = r.node.sensor.mount_offset_deg
    return {"calibrations": cals, "refit_runs": r.core.refit_log, "true_theta0_deg": true_theta0,
            "true_l_m": r.node.ramp.length_m,
            "true_h0_mllw_float_m": r.node.ramp.hinge_m - r.node.ramp.freeboard_m}


def alerts_summary(conn: sqlite3.Connection) -> list[dict]:
    return [{"kind": a["kind"], "severity": a["severity"], "opened_at": iso(a["opened_at"]),
             "cleared_at": iso(a["cleared_at"]), "value": a["value"], "notified": a["notified_at"] is not None}
            for a in conn.execute("SELECT * FROM alerts ORDER BY opened_at")]


def all_metrics(r: SimResult) -> dict:
    conn = sqlite3.connect(r.db_path)
    conn.row_factory = sqlite3.Row
    acc = accuracy(r, conn)
    m = {"accuracy": {k: v for k, v in acc.items() if k != "_series"}, "hilo": hilo_timing(r, acc),
         "surge": surge(r, conn), "outage": outage(r, conn), "link": link(r, conn), "energy": energy_check(r, conn),
         "calibration": refit(r, conn), "alerts": alerts_summary(conn), "emails": len(r.notifier.sent)}
    m["_series"] = acc["_series"]
    conn.close()
    return m


_ = math
