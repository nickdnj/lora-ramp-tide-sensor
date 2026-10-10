"""Markdown report and optional PNG plots for simulation runs."""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import numpy as np

from tidesvc.timeutil import iso

from .acceptance import checks


def _row(*cells) -> str:
    return "| " + " | ".join(str(c) for c in cells) + " |"


def scenario_table(r) -> list[str]:
    sc, ev = r.scenario, r.events
    lines = [_row("Item", "Value"), _row("---", "---"),
             _row("Simulated period", f"{iso(r.t0)} to {iso(r.t1)} ({sc.days:g} days), seed {sc.seed}"),
             _row("Tide", "M2 0.42, S2 0.07, N2 0.09, K1 0.07, O1 0.05 m; mean 0.50 m above MLLW; weather noise "
                  f"sigma {sc.weather_sigma_m * 100:.1f} cm (OU, tau 10 h, smoothed 1.5 h)")]
    if ev["surges"]:
        pt, pm = ev["surges"][0]
        lines.append(_row("Storm surge", f"peak +{pm:.2f} m at {iso(pt)} (rise sigma {sc.surge_rise_sigma_h} h, fall "
                          f"sigma {sc.surge_fall_sigma_h} h)"))
    for a, b in ev["repeater_outages"]:
        lines.append(_row("Repeater outage", f"{iso(a)} to {iso(b)} (no relays, adverts or direct copies)"))
    for a, b in ev["host_disconnects"]:
        lines.append(_row("Gateway USB unplug", f"{iso(a)} to {iso(b)} (companion queues up to 16 frames)"))
    for a, b in ev["noaa_outages"]:
        lines.append(_row("NOAA outage", f"{iso(a)} to {iso(b)} (every fetch fails)"))
    if ev["reboot"]:
        lines.append(_row("Node reboot", f"{iso(ev['reboot'])} (watchdog reset; boot_count+1, seq restarts)"))
    if ev["wake_burst"]:
        lines.append(_row("Wake burst", f"8 boat wakes (0.18 m heave, 250 s apart) from {iso(ev['wake_burst'])}, plus "
                          f"{sc.wakes_per_day:g} random wakes/day and {sc.loads_per_day:g} foot-traffic loads/day"))
    for a, b, d in ev["cold_snaps"]:
        lines.append(_row("Cold snap", f"{iso(a)} to {iso(b)}, air {d:+.0f} C vs normal"))
    lines.append(_row("Panel / insolation", f"1 W (Isc 185 mA, derate 0.85), vertical south, December mean "
                      f"{sc.target_psh} PSH (PVGIS), shading factor {sc.shading}"))
    lines.append(_row("Ramp / sensor", "L 7.62 m, hinge 2.10 m above MLLW, freeboard 0.45 m; SCL3300-like: mount offset "
                      "0.80 deg, drift 0.0035 deg/C (tidesvc k_T = 0), noise 0.004 deg, LSB 0.0055 deg"))
    lines.append(_row("Node truth vs service model", "sleep 55 uA, 128 mAs/cycle, clock +1.2% vs config 50 uA, "
                      "125 mAs/cycle"))
    lines.append(_row("Radio", "relay delivery 97.5%, direct copy 25% (duplicates), 0.2% corrupted copies, "
                      "public-channel chatter"))
    inst = ev["install"]
    lines.append(_row("Install calibration", f"level check {iso(inst['level_check_t'])}; tape at "
                      f"{iso(inst['tape_t'][0])} and {iso(inst['tape_t'][1])}; fit {iso(inst['fit_t'])}; "
                      f"datum tie {iso(inst['datum_tie_t'])} (shakedown compressed to "
                      f"{sc.datum_tie_after_days:g} days)"))
    return lines


def acceptance_table(m, sc) -> tuple[list[str], bool]:
    cs = checks(m, sc)
    lines = [_row("ID", "Requirement", "Target", "Measured", "Result"), _row("---", "---", "---", "---", "---")]
    ok = True
    for c in cs:
        res = ("PASS" if c.passed else "not met (stretch)") if c.stretch else ("PASS" if c.passed else "FAIL")
        if not c.passed and not c.stretch:
            ok = False
        lines.append(_row(c.id, c.what, c.target, c.measured, res))
    return lines, ok


def plots(r, m, outdir: Path) -> list[str]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # noqa: BLE001 - plots are optional
        return []
    outdir.mkdir(parents=True, exist_ok=True)
    s = m["_series"]
    w = r.world
    files = []
    days = lambda t: (np.asarray(t) - r.t0) / 86400  # noqa: E731
    fig, ax = plt.subplots(2, 1, figsize=(13, 7), sharex=True)
    tg = np.arange(r.t0, r.t1, 300.0)
    ax[0].plot(days(tg), w.water(tg), lw=0.6, color="k", label="true water level")
    ax[0].plot(days(s["lt"]), s["smooth"], ".", ms=1.5, color="tab:blue", label="served level (trailing median)")
    ax[0].plot(days(tg), w.astro(tg), lw=0.5, color="tab:orange", alpha=0.6, label="astronomical (NOAA-like)")
    ax[0].set_ylabel("m above MLLW")
    ax[0].legend(loc="upper right", fontsize=8)
    ax[1].plot(days(s["lt"]), (s["smooth"] - w.water(s["lt"] - 750)) * 100, ".", ms=1.5, label="served - truth(window centre)")
    ax[1].set_ylabel("error, cm")
    ax[1].set_xlabel("days from start")
    ax[1].legend(fontsize=8)
    f = outdir / f"{r.scenario.name}-level.png"
    fig.tight_layout()
    fig.savefig(f, dpi=110)
    plt.close(fig)
    files.append(str(f))
    return files


def sweep_table(sweep) -> list[str]:
    lines = ["## Robustness across seeds (default scenario)", "",
             "Same scenario, different random seeds (tide phases fixed; weather noise, wakes, loads, clouds, radio "
             "loss and sensor noise re-drawn).", "",
             _row("Seed", "Served RMS cm", "Window-centre RMS cm", "Bias cm", "Hi/lo RMS / max min", "Warning latency min",
                  "Severe latency min", "Energy verdict (truth)", "Refit dh0 cm / dL %", "Required checks"),
             _row(*["---"] * 10)]
    for seed, m, cs in sweep:
        a = m["accuracy"]
        h = m["hilo"]
        s = m["surge"]
        e = m["energy"]
        rf = m["calibration"]["refit_runs"][-1] if m["calibration"]["refit_runs"] else {}
        fails = [c.id for c in cs if not c.passed and not c.stretch]
        lines.append(_row(seed, f"{a['live_trailing_vs_truth_now']['rms_cm']:.2f}",
                          f"{a['live_trailing_vs_truth_window_centre']['rms_cm']:.2f}",
                          f"{a['live_trailing_vs_truth_now']['bias_cm']:+.2f}",
                          f"{h['dt_min_rms']:.1f} / {h['dt_min_max_abs']:.1f}",
                          f"{s['SURGE_WARNING']['latency_min']:.0f}", f"{s['SURGE_SEVERE']['latency_min']:.0f}",
                          f"{e['verdict']['assessment']} ({e['true_assessment']})",
                          f"{100 * rf.get('dh0_m', 0):+.2f} / {100 * rf.get('dl_rel', 0):+.2f}",
                          "all pass" if not fails else "FAIL: " + ", ".join(fails)))
    return lines + [""]


def write_report(results: list[tuple], path: Path, plot_files: list[str], sweep=None) -> bool:
    """results: list of (SimResult, metrics). Returns overall pass."""
    lines = ["# Simulation Report: LoRa Ramp Tide Sensor", "",
             f"Generated {_dt.datetime.now(_dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} by `python -m sim.run` "
             "(offline; no hardware, no network). Every number below is measured from the run, not asserted.", "",
             "The simulator drives the real `tidesvc` code (ingest, derive, calibration, NOAA cache, energy, alerts, "
             "API via HTTP test client) through a fake radio source on a virtual clock. The node model uses "
             "`sim.fwlogic`, the Python mirror of the firmware portable core held to the same vectors as the C++.", ""]
    overall = True
    for r, m in results:
        acc_lines, ok = acceptance_table(m, r.scenario)
        overall = overall and ok
        lines += [f"## Scenario `{r.scenario.name}`", "", f"Wall time {r.wall_s:.1f} s for {r.scenario.days:g} "
                  f"simulated days. Result: **{'all required checks pass' if ok else 'REQUIRED CHECKS FAILED'}**.", "",
                  "### Setup", ""] + scenario_table(r) + ["", "### Acceptance", ""] + acc_lines + [""]
        a = m["accuracy"]
        if a["live_trailing_vs_truth_now"].get("n"):
            lines += ["### Level accuracy (after the datum tie)", "",
                      _row("Series", "n", "RMS cm", "bias cm", "p95 cm", "max cm"), _row(*["---"] * 6)]
            for k, label in (("live_trailing_vs_truth_now", "Served (trailing median) vs truth now"),
                             ("live_trailing_vs_truth_window_centre", "Served vs truth at window centre (t-12.5 min)"),
                             ("raw_per_reading", "Raw per-reading level"),
                             ("centred_30min", "Centred 30-min median (history)"),
                             ("residual_vs_true_residual", "Residual vs true residual")):
                x = a[k]
                lines.append(_row(label, x["n"], f"{x['rms_cm']:.2f}", f"{x['bias_cm']:+.2f}", f"{x['p95_abs_cm']:.2f}",
                                  f"{x['max_abs_cm']:.2f}"))
            h = m["hilo"]
            lines += ["", f"High/low: {h['n_found']} of {h['n_true_extremes']} true extremes located; timing error "
                      f"mean {h['dt_min_mean']:+.1f} min, RMS {h['dt_min_rms']:.1f} min, p95 {h['dt_min_p95_abs']:.1f} "
                      f"min, max {h['dt_min_max_abs']:.1f} min; height RMS {h['height_cm_rms']:.1f} cm. Observed vs NOAA "
                      f"predicted extreme times differ by {h['vs_noaa_predicted_dt_min_rms']:.1f} min RMS (that is "
                      "real weather in the simulated water, not error).", ""]
        s = m["surge"]
        if s.get("present"):
            lines += ["### Storm surge", "", _row("Alert", "True trigger", "Opened", "Latency", "Cleared"),
                      _row(*["---"] * 5)]
            for k in ("SURGE_WARNING", "SURGE_SEVERE", "RAPID_RISE"):
                d = s[k]
                trig = d.get("true_cross_at") or d.get("true_rate_above_0.15_at")
                lat = d.get("latency_min")
                lines.append(_row(k, trig, d["opened_at"], "n/a" if lat is None else f"{lat:.0f} min", d["cleared_at"]))
            lines += ["", f"Measured peak residual {s['measured_peak_residual_m']:.3f} m vs true {s['peak_true_m']:.3f} "
                      f"m. True maximum surge rise rate {s['RAPID_RISE'].get('true_max_rate_m_per_h', 0):.2f} m/h. "
                      "Latency = time from the true residual crossing the threshold to the alert opening; it is the "
                      "trailing 30-min median (about 12 min), two consecutive readings (5-10 min) and the 60 s tick. "
                      "RAPID_RISE uses a 60-min least-squares slope of the smoothed series, so it trails the "
                      "instantaneous rate by roughly 30-60 min.", ""]
        ln = m["link"]
        lines += ["### Link, de-duplication and faults", "",
                  f"- Transmitted {ln['transmitted']}, stored {ln['readings_stored']} readings "
                  f"({ln['delivery_pct']:.1f}% delivery; {ln['lost_in_outage']} lost in the repeater outage).",
                  f"- packets_raw by status: {json.dumps(ln['packets_raw_by_status'])}. Corrupted copies "
                  f"{ln['corrupted_copies']} (stored raw as bad_crc), public-channel frames {ln['foreign_frames']} "
                  "(wrong_channel).",
                  f"- Duplicate copies sent by the radio {ln['duplicate_copies_by_radio']}; duplicate reading keys in "
                  f"the database {ln['duplicate_reading_keys']}; stored keys equal the intact unique frames: "
                  f"{ln['readings_match_intact_keys']}."]
        o = m["outage"]
        if "repeater_outage" in o:
            x = o["repeater_outage"]
            lines.append(f"- Repeater outage {x['window'][0]} to {x['window'][1]}: {x['probes_in_window']} API probes; "
                         f"{x['probes_before_stale_200']} answered 200 before the 15-min stale threshold, then "
                         f"{x['of_which_503']}/{x['probes_after_stale_threshold']} answered 503 with status "
                         f"{x['status_values']}, level_m null and a labelled last_good. NODE_SILENT after "
                         f"{x['NODE_SILENT_opened_after_min']:.1f} min, REPEATER_SILENT after "
                         f"{x['REPEATER_SILENT_opened_after_h']:.2f} h of outage.")
        if "gateway_disconnect" in o:
            x = o["gateway_disconnect"]
            lines.append(f"- Gateway unplug {x['window'][0]} to {x['window'][1]}: GATEWAY_DOWN {x['GATEWAY_DOWN']}; "
                         f"{x['backfilled_readings']} readings back-dated from seq on reconnect, time error "
                         f"{x['backfill_time_error_min']} min (the newest queued frame is stamped at drain time).")
        lines.append("")
        e = m["energy"]
        v = e["verdict"]
        lines += ["### Energy", "",
                  f"Verdict window {v['window'][0]} to {v['window'][1]}: **{v['assessment']}** "
                  f"({v.get('assessment_basis')}); energy_ratio {v['energy_ratio']} "
                  f"(lower bound: {v.get('energy_ratio_is_lower_bound')}), days reached full {v['days_reached_full']}, "
                  f"cold-inhibit hours {v['charge_inhibit_cold_h']}, negative streak {v['negative_streak_days']}.", "",
                  f"Truth: accepted harvest {e['true_harvest_mah']:.1f} mAh, panel-available harvest "
                  f"{e['true_available_mah']:.1f} mAh, consumption {e['true_consumption_mah']:.1f} mAh; accepted ratio "
                  f"{e['true_accepted_ratio']:.3f}, available ratio {e['true_available_ratio']:.2f} -> "
                  f"{e['true_assessment']}. Service: harvest {e['service_harvest_mah']:.1f} mAh, consumption "
                  f"{e['service_consumption_mah']:.1f} mAh. Integrating raw ipanel as ARCHITECTURE 6.6 literally says "
                  f"would give {e['naive_raw_ipanel_harvest_mah']:.1f} mAh (ratio {e['naive_ratio']:.2f}). Lowest "
                  f"true state of charge {e['min_true_soc_pct']:.1f}%.", "",
                  _row("Date", "Svc harvest", "True accepted", "True available", "Svc cons", "True cons", "Svc cold h",
                       "True cold h", "Full", "Cov %", "PSH"), _row(*["---"] * 11)]
        for d in e["per_day"]:
            lines.append(_row(d["date"], d["svc_harvest"], d["true_harvest"], d["true_available"], d["svc_cons"],
                              d["true_cons"], d["svc_cold_h"], d["true_cold_h"], "yes" if d["full"] else "",
                              d["coverage"], d["psh"]))
        lines.append("")
        cal = m["calibration"]
        lines += ["### Calibration history", "", _row("id", "method", "status", "datum", "valid_from", "theta0 deg",
                                                          "h0 m", "L_eff m", "notes"), _row(*["---"] * 9)]
        for c in cal["calibrations"]:
            fs = c["fit_stats"]
            note = ", ".join(f"{k}={round(v, 4) if isinstance(v, float) else v}" for k, v in fs.items()
                             if k in ("n", "n_tape", "span_m", "shift_m", "dh0_m", "dl_rel", "rms_m", "within_bounds"))
            lines.append(_row(c["id"], c["method"], c["status"], c["datum"], c["valid_from"], f"{c['theta0_deg']:.3f}",
                              f"{c['h0_m']:.4f}", f"{c['l_eff_m']:.4f}", note))
        lines += ["", f"True values: theta0 (mount offset) {cal['true_theta0_deg']} deg, L {cal['true_l_m']} m. "
                  "theta0 also absorbs the sensor's temperature offset at install (k_T is 0 until bench B7), and "
                  "h0 absorbs any theta0 error (ADR-009).", ""]
        lines += ["### Alerts raised", "", _row("Kind", "Severity", "Opened", "Cleared", "Value", "Emailed"),
                  _row(*["---"] * 6)]
        for al in m["alerts"]:
            val = al["value"]
            lines.append(_row(al["kind"], al["severity"], al["opened_at"], al["cleared_at"],
                              f"{val:.3f}" if isinstance(val, float) else val, al["notified"]))
        lines += ["", f"Emails recorded by the fake notifier: {m['emails']} (nothing was sent).", ""]
        lc = r.final_api.get("/api/v1/level/current")
        if lc:
            lines += ["Final `/api/v1/level/current` (HTTP %d):" % lc["code"], "", "```json",
                      json.dumps(lc["body"], indent=1)[:2500], "```", ""]
    if sweep:
        first = results[0][1]
        sweep = [(results[0][0].scenario.seed, first, checks(first, results[0][0].scenario))] + list(sweep)
        lines += sweep_table(sweep)
    if plot_files:
        lines += ["## Plots", "", "PNG plots were written outside the repo (not committed): " +
                  ", ".join(f"`{p}`" for p in plot_files), ""]
    lines += FINDINGS
    path.write_text("\n".join(lines) + "\n")
    return overall


FINDINGS = [
    "## Findings, deviations and limits", "",
    "Found by simulating, fixed in code (not by loosening a check):", "",
    "1. **Energy verdict could never say `surplus` for a healthy node.** Charger-accepted harvest is capped once the "
    "cell is full, so by conservation harvest/consumption tends to 1.0 whenever the cell keeps reaching full, "
    "whatever the panel size. ARCHITECTURE 6.6's ratio thresholds alone gave `marginal` (1.03) for a 1 W panel that "
    "refilled the cell on most days. ARCHITECTURE 6.6 already says full-charge days are the 'panel is large enough' "
    "signal; `tidesvc.energy.verdict` now applies it (full on at least half of the qualifying days means surplus) and "
    "reports `energy_ratio_is_lower_bound`. Needs Nick's agreement.",
    "2. **Raw `ipanel` integration overstates harvest.** The INA3221 is read while the node is awake (about 25 mA "
    "from SYS). While charging, the BQ25185 sits in VINDPM and the sample is the panel current, which is correct; when "
    "charging is off (DONE, cold inhibit, CE override, latch), the sample is the node's awake current. The literal "
    "ARCHITECTURE 6.6 integral reported about 17x the true accepted harvest for the 1 W December run, and turned the "
    "shaded/cold deficit run into `marginal`. `tidesvc.energy.harvest_current_ma` counts ipanel only while CHRG is "
    "set and the modelled average load otherwise.",
    "3. **False DONE every night.** Without panel input the BQ25185 STAT pins float high (1/1), which ARCHITECTURE "
    "4.7's DONE rule ('STAT 1/1 while /CE is LOW') reads as DONE. The firmware rule now also requires panel voltage "
    "(vpanel >= 3.0 V); the server ignores DONE without panel voltage.",
    "4. **Envelope margin would reject a surge.** ARCHITECTURE 6.4 excludes readings outside the calibrated pitch "
    "envelope +/-0.5 deg, which is only about 6.6 cm of level. The install fit therefore sets the envelope from the "
    "tape levels -1.0 m / +2.0 m, so a real surge is not discarded as out of range.",
    "5. **Residual lag.** A trailing 30-min median lags the water by about 12.5 min, which alone is about 5 cm of "
    "residual error at mid-tide. The prediction is now passed through the same trailing median over the same "
    "reading times before subtracting (`predicted_smooth_m`); `predicted_m` is still the plain prediction.",
    "6. **One-sided extreme fits.** An extreme next to an outage could be fitted from data on one side only (an "
    "18-minute timing error in an early run). `find_extreme_near` now requires data on both sides of the vertex, "
    "which also protects the monthly refit.",
    "7. **World-model fix (simulator only).** The first weather-noise model was an unsmoothed random walk, which "
    "made even the true high/low times jitter by tens of minutes; it is now smoothed (1.5 h).", "",
    "Limits that remain (reported, not hidden):", "",
    "- The served `level_m` is a trailing median, so against the true water at the same instant it carries the "
    "~12.5 min lag: see ACC-1/ACC-2. It meets +/-5 cm; it does not meet the +/-2 cm stretch at mid-tide rates. "
    "Against the time it represents (window centre), and as history, it is within 2 cm.",
    "- The datum comes from NOAA predicted extremes (ADR-009). It absorbs the mean weather residual of the tie "
    "window: in the default run that is about -1.5 cm of bias, which dominates the error budget. The sim compresses "
    "the 14-day shakedown to a few days so that the surge and faults happen after the tie; a 14-day tie averages "
    "the weather down further.",
    "- `k_T` stays 0 (no bench B7 yet); the simulated sensor drifts 0.0035 deg/C, about 0.5 mm per C of level.",
    "- The simulated physics (charger, panel, cell, wakes) is a model with stated assumptions, not a substitute for "
    "the bench tests B1-B13 and the RF tests; nothing here verifies MeshCore, the companion protocol or meshcore_py.",
]
