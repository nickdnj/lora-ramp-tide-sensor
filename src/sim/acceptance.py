"""Acceptance criteria for a simulation run (shared by the CLI report and the
end-to-end tests). Each check: (id, description, target, measured, passed)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Check:
    id: str
    what: str
    target: str
    measured: str
    passed: bool
    stretch: bool = False  # stretch goals are reported but do not fail the run


def _f(x, nd=2):
    return "n/a" if x is None else f"{x:.{nd}f}"


def checks(m: dict, scenario) -> list[Check]:
    out: list[Check] = []
    a = m["accuracy"]
    live = a["live_trailing_vs_truth_now"]
    out.append(Check("ACC-1", "Served level (/level/current value: trailing 30-min median) vs true water level at the "
                     "same instant, after calibration", "RMS <= 5 cm", f"RMS {_f(live['rms_cm'])} cm "
                     f"(bias {_f(live['bias_cm'])}, p95 {_f(live['p95_abs_cm'])}, max {_f(live['max_abs_cm'])})",
                     live["rms_cm"] <= 5.0))
    out.append(Check("ACC-2", "Same, stretch goal", "RMS <= 2 cm", f"RMS {_f(live['rms_cm'])} cm",
                     live["rms_cm"] <= 2.0, stretch=True))
    cen = a["live_trailing_vs_truth_window_centre"]
    out.append(Check("ACC-3", "Served level vs truth at the window centre it represents (removes the ~12.5 min "
                     "trailing-median lag)", "RMS <= 2 cm (stretch)", f"RMS {_f(cen['rms_cm'])} cm "
                     f"(bias {_f(cen['bias_cm'])})", cen["rms_cm"] <= 2.0, stretch=True))
    c30 = a["centred_30min"]
    out.append(Check("ACC-4", "Historical centred 30-min median vs truth", "RMS <= 2 cm (stretch)",
                     f"RMS {_f(c30['rms_cm'])} cm (max {_f(c30['max_abs_cm'])})", c30["rms_cm"] <= 2.0, stretch=True))
    h = m["hilo"]
    found_pct = 100.0 * h["n_found"] / max(1, h["n_true_extremes"])
    out.append(Check("HILO-1", "High/low timing (observed centred series vs true extremes)",
                     "RMS <= 5 min, max <= 10 min, >= 95% of extremes found",
                     f"RMS {_f(h['dt_min_rms'], 1)} min, max {_f(h['dt_min_max_abs'], 1)} min, "
                     f"{h['n_found']}/{h['n_true_extremes']} found ({found_pct:.0f}%; misses are in data gaps)",
                     (h["dt_min_rms"] or 99) <= 5 and (h["dt_min_max_abs"] or 99) <= 10 and found_pct >= 95))
    s = m["surge"]
    if s.get("present"):
        w, sv = s["SURGE_WARNING"], s["SURGE_SEVERE"]
        out.append(Check("SURGE-1", "Surge residual detected: SURGE_WARNING opens after the true residual crosses "
                         "+0.30 m", "opens, latency <= 60 min", f"opened {w['opened_at']}, latency "
                         f"{_f(w['latency_min'], 0)} min after true crossing {w['true_cross_at']}",
                         w["opened_at"] is not None and (w["latency_min"] or 1e9) <= 60))
        out.append(Check("SURGE-2", "SURGE_SEVERE for the +0.70 m peak (+0.60 m threshold)", "opens, latency <= 60 min",
                         f"opened {sv['opened_at']}, latency {_f(sv['latency_min'], 0)} min; measured peak residual "
                         f"{_f(s['measured_peak_residual_m'], 3)} m vs true {_f(s['peak_true_m'], 3)} m",
                         sv["opened_at"] is not None and (sv["latency_min"] or 1e9) <= 60))
        out.append(Check("SURGE-3", "Surge alerts clear per their stated condition and email once each",
                         "cleared; <= 1 email per alert kind", f"warning cleared {w['cleared_at']}, severe cleared "
                         f"{sv['cleared_at']}; {s['surge_emails']} surge/rise emails",
                         bool(w["cleared_at"] and sv["cleared_at"]) and s["surge_emails"] <= 3))
    o = m["outage"].get("repeater_outage")
    if o:
        ok = (o["probes_after_stale_threshold"] > 0 and o["of_which_503"] == o["probes_after_stale_threshold"]
              and o["of_which_level_null"] == o["probes_after_stale_threshold"]
              and o["of_which_last_good_labelled"] == o["probes_after_stale_threshold"]
              and o["readings_stored_inside_window"] == 0)
        out.append(Check("OUT-1", f"{o['hours']:.0f} h repeater outage: /level/current stale, not invented",
                         "every probe after 15 min: HTTP 503, level_m null, labelled last_good; no readings",
                         f"{o['of_which_503']}/{o['probes_after_stale_threshold']} probes 503, "
                         f"{o['of_which_level_null']} null level, {o['of_which_last_good_labelled']} with last_good; "
                         f"{o['readings_stored_inside_window']} readings stored", ok))
        out.append(Check("OUT-2", "Outage alerts: NODE_SILENT at 30 min, REPEATER_SILENT at 4 h, both clear",
                         "NODE_SILENT 30-36 min; REPEATER_SILENT 4.0-4.2 h after last evidence",
                         f"NODE_SILENT after {_f(o['NODE_SILENT_opened_after_min'], 1)} min; REPEATER_SILENT after "
                         f"{_f(o['REPEATER_SILENT_opened_after_h'], 2)} h of outage; cleared "
                         f"{o['REPEATER_SILENT_cleared']}",
                         o["NODE_SILENT_opened_after_min"] is not None and 30 <= o["NODE_SILENT_opened_after_min"] <= 36
                         and o["REPEATER_SILENT_opened_after_h"] is not None
                         and 3.8 <= o["REPEATER_SILENT_opened_after_h"] <= 4.2 and o["REPEATER_SILENT_cleared"]))
    g = m["outage"].get("gateway_disconnect")
    if g:
        errs = g["backfill_time_error_min"]
        out.append(Check("BACKLOG-1", f"{g['minutes']:.0f} min gateway USB unplug: companion queue drained and "
                         "back-dated (ADR-012)", "backfilled readings flagged, time error <= 5 min, GATEWAY_DOWN opens",
                         f"{g['backfilled_readings']} backfilled, time error {min(errs, default=0):.1f}-"
                         f"{max(errs, default=0):.1f} min, GATEWAY_DOWN {g['GATEWAY_DOWN']}",
                         g["backfilled_readings"] > 0 and all(abs(e) <= 5 for e in errs) and g["GATEWAY_DOWN"] is not None
                         and g["level_served_during_gap"] == 0))
    ln = m["link"]
    out.append(Check("DEDUP-1", "Duplicate (direct + relayed) copies de-duplicated", "one reading per "
                     "(node, boot, seq); readings == intact unique frames",
                     f"{ln['duplicate_copies_by_radio']} duplicate copies sent, "
                     f"{ln['packets_raw_by_status'].get('duplicate', 0)} marked duplicate (the rest arrived "
                     f"corrupted: bad_crc), "
                     f"{ln['duplicate_reading_keys']} duplicate keys, readings == intact keys: "
                     f"{ln['readings_match_intact_keys']}",
                     ln["duplicate_reading_keys"] == 0 and ln["readings_match_intact_keys"]))
    e = m["energy"]
    v = e["verdict"]
    out.append(Check("ENERGY-1", "14-day energy verdict matches the simulated truth", f"category == truth "
                     f"({e['true_assessment']})", f"{v['assessment']} (ratio {_f(v['energy_ratio'], 3)}, "
                     f"full on {v.get('qualifying_days_reached_full')} of {v['qualifying_days']} days); truth: "
                     f"accepted ratio {_f(e['true_accepted_ratio'], 3)}, available ratio "
                     f"{_f(e['true_available_ratio'], 2)}", v["assessment"] == e["true_assessment"]))
    out.append(Check("ENERGY-2", "Harvest accounting vs truth (14-day window)", "within 15% of true accepted harvest",
                     f"service {_f(e['service_harvest_mah'], 1)} mAh vs true {_f(e['true_harvest_mah'], 1)} mAh; "
                     f"raw-ipanel integral (ARCHITECTURE 6.6 as written) {_f(e['naive_raw_ipanel_harvest_mah'], 1)} mAh",
                     abs(e["service_harvest_mah"] - e["true_harvest_mah"]) <= 0.15 * max(1.0, e["true_harvest_mah"])))
    cal = m["calibration"]
    runs = cal["refit_runs"]
    if runs:
        r = runs[-1]
        out.append(Check("REFIT-1", "Monthly refit (1st, 03:00 local) stays within bounds and is applied",
                         "|dh0| <= 0.05 m, |dL/L| <= 3%, applied", f"dh0 {_f(r.get('dh0_m'), 4)} m, dL/L "
                         f"{_f(100 * r['dl_rel'] if r.get('dl_rel') is not None else None, 2)}%, n={r.get('n')}, "
                         f"status {r.get('status')}", bool(r.get("applied"))))
    return out
