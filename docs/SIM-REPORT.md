# Simulation Report: LoRa Ramp Tide Sensor

Generated 2026-10-10 15:22 UTC by `python -m sim.run` (offline; no hardware, no network). Every number below is measured from the run, not asserted.

The simulator drives the real `tidesvc` code (ingest, derive, calibration, NOAA cache, energy, alerts, API via HTTP test client) through a fake radio source on a virtual clock. The node model uses `sim.fwlogic`, the Python mirror of the firmware portable core held to the same vectors as the C++.

## Scenario `december-30d`

Wall time 17.0 s for 30 simulated days. Result: **all required checks pass**.

### Setup

| Item | Value |
| --- | --- |
| Simulated period | 2026-12-03T05:00:00Z to 2027-01-02T05:00:00Z (30 days), seed 1 |
| Tide | M2 0.42, S2 0.07, N2 0.09, K1 0.07, O1 0.05 m; mean 0.50 m above MLLW; weather noise sigma 2.5 cm (OU, tau 10 h, smoothed 1.5 h) |
| Storm surge | peak +0.70 m at 2026-12-15T19:24:00Z (rise sigma 2.0 h, fall sigma 4.0 h) |
| Repeater outage | 2026-12-20T14:36:00Z to 2026-12-20T20:36:00Z (no relays, adverts or direct copies) |
| Gateway USB unplug | 2026-12-10T12:12:00Z to 2026-12-10T12:57:00Z (companion queues up to 16 frames) |
| NOAA outage | 2026-12-17T06:12:00Z to 2026-12-18T00:12:00Z (every fetch fails) |
| Node reboot | 2026-12-23T18:12:00Z (watchdog reset; boot_count+1, seq restarts) |
| Wake burst | 8 boat wakes (0.18 m heave, 250 s apart) from 2026-12-12T19:24:00Z, plus 4 random wakes/day and 8 foot-traffic loads/day |
| Cold snap | 2026-12-24T05:00:00Z to 2026-12-27T17:00:00Z, air -9 C vs normal |
| Panel / insolation | 1 W (Isc 185 mA, derate 0.85), vertical south, December mean 3.45 PSH (PVGIS), shading factor 1.0 |
| Ramp / sensor | L 7.62 m, hinge 2.10 m above MLLW, freeboard 0.45 m; SCL3300-like: mount offset 0.80 deg, drift 0.0035 deg/C (tidesvc k_T = 0), noise 0.004 deg, LSB 0.0055 deg |
| Node truth vs service model | sleep 55 uA, 128 mAs/cycle, clock +1.2% vs config 50 uA, 125 mAs/cycle |
| Radio | relay delivery 97.5%, direct copy 25% (duplicates), 0.2% corrupted copies, public-channel chatter |
| Install calibration | level check 2026-12-05T12:47:27Z; tape at 2026-12-05T13:17:27Z and 2026-12-05T19:30:59Z; fit 2026-12-05T20:30:59Z; datum tie 2026-12-09T20:30:59Z (shakedown compressed to 4 days) |

### Acceptance

| ID | Requirement | Target | Measured | Result |
| --- | --- | --- | --- | --- |
| ACC-1 | Served level (/level/current value: trailing 30-min median) vs true water level at the same instant, after calibration | RMS <= 5 cm | RMS 3.57 cm (bias -1.61, p95 6.20, max 9.79) | PASS |
| ACC-2 | Same, stretch goal | RMS <= 2 cm | RMS 3.57 cm | not met (stretch) |
| ACC-3 | Served level vs truth at the window centre it represents (removes the ~12.5 min trailing-median lag) | RMS <= 2 cm (stretch) | RMS 1.70 cm (bias -1.63) | PASS |
| ACC-4 | Historical centred 30-min median vs truth | RMS <= 2 cm (stretch) | RMS 1.70 cm (max 5.00) | PASS |
| HILO-1 | High/low timing (observed centred series vs true extremes) | RMS <= 5 min, max <= 10 min, >= 95% of extremes found | RMS 1.1 min, max 4.0 min, 88/89 found (99%; misses are in data gaps) | PASS |
| SURGE-1 | Surge residual detected: SURGE_WARNING opens after the true residual crosses +0.30 m | opens, latency <= 60 min | opened 2026-12-15T17:09:00Z, latency 25 min after true crossing 2026-12-15T16:44:00Z | PASS |
| SURGE-2 | SURGE_SEVERE for the +0.70 m peak (+0.60 m threshold) | opens, latency <= 60 min | opened 2026-12-15T18:35:00Z, latency 22 min; measured peak residual 0.698 m vs true 0.710 m | PASS |
| SURGE-3 | Surge alerts clear per their stated condition and email once each | cleared; <= 1 email per alert kind | warning cleared 2026-12-16T02:41:00Z, severe cleared 2026-12-15T23:24:00Z; 3 surge/rise emails | PASS |
| OUT-1 | 6 h repeater outage: /level/current stale, not invented | every probe after 15 min: HTTP 503, level_m null, labelled last_good; no readings | 70/70 probes 503, 70 null level, 70 with last_good; 0 readings stored | PASS |
| OUT-2 | Outage alerts: NODE_SILENT at 30 min, REPEATER_SILENT at 4 h, both clear | NODE_SILENT 30-36 min; REPEATER_SILENT 4.0-4.2 h after last evidence | NODE_SILENT after 30.7 min; REPEATER_SILENT after 3.95 h of outage; cleared True | PASS |
| BACKLOG-1 | 45 min gateway USB unplug: companion queue drained and back-dated (ADR-012) | backfilled readings flagged, time error <= 5 min, GATEWAY_DOWN opens | 8 backfilled, time error 1.7-2.2 min, GATEWAY_DOWN ['2026-12-10T12:18:00Z', '2026-12-10T12:57:00Z'] | PASS |
| DEDUP-1 | Duplicate (direct + relayed) copies de-duplicated | one reading per (node, boot, seq); readings == intact unique frames | 2108 duplicate copies sent, 2095 marked duplicate (the rest arrived corrupted: bad_crc), 0 duplicate keys, readings == intact keys: True | PASS |
| ENERGY-1 | 14-day energy verdict matches the simulated truth | category == truth (surplus) | surplus (ratio 0.943, full on 10 of 13 days); truth: accepted ratio 1.001, available ratio 39.27 | PASS |
| ENERGY-2 | Harvest accounting vs truth (14-day window) | within 15% of true accepted harvest | service 161.0 mAh vs true 160.3 mAh; raw-ipanel integral (ARCHITECTURE 6.6 as written) 2696.4 mAh | PASS |
| REFIT-1 | Monthly refit (1st, 03:00 local) stays within bounds and is applied | |dh0| <= 0.05 m, |dL/L| <= 3%, applied | dh0 0.0019 m, dL/L -0.04%, n=94, status active | PASS |

### Level accuracy (after the datum tie)

| Series | n | RMS cm | bias cm | p95 cm | max cm |
| --- | --- | --- | --- | --- | --- |
| Served (trailing median) vs truth now | 6425 | 3.57 | -1.61 | 6.20 | 9.79 |
| Served vs truth at window centre (t-12.5 min) | 6425 | 1.70 | -1.63 | 2.47 | 5.75 |
| Raw per-reading level | 6439 | 1.73 | -1.64 | 2.42 | 8.64 |
| Centred 30-min median (history) | 6420 | 1.70 | -1.63 | 2.47 | 5.00 |
| Residual vs true residual | 6425 | 1.71 | -1.63 | 2.59 | 5.38 |

High/low: 88 of 89 true extremes located; timing error mean -0.0 min, RMS 1.1 min, p95 2.4 min, max 4.0 min; height RMS 1.6 cm. Observed vs NOAA predicted extreme times differ by 13.5 min RMS (that is real weather in the simulated water, not error).

### Storm surge

| Alert | True trigger | Opened | Latency | Cleared |
| --- | --- | --- | --- | --- |
| SURGE_WARNING | 2026-12-15T16:44:00Z | 2026-12-15T17:09:00Z | 25 min | 2026-12-16T02:41:00Z |
| SURGE_SEVERE | 2026-12-15T18:13:00Z | 2026-12-15T18:35:00Z | 22 min | 2026-12-15T23:24:00Z |
| RAPID_RISE | 2026-12-15T16:06:00Z | 2026-12-15T16:54:00Z | 48 min | 2026-12-15T20:11:00Z |

Measured peak residual 0.698 m vs true 0.710 m. True maximum surge rise rate 0.21 m/h. Latency = time from the true residual crossing the threshold to the alert opening; it is the trailing 30-min median (about 12 min), two consecutive readings (5-10 min) and the 60 s tick. RAPID_RISE uses a 60-min least-squares slope of the smoothed series, so it trails the instantaneous rate by roughly 30-60 min.

### Link, de-duplication and faults

- Transmitted 8539, stored 8301 readings (97.2% delivery; 71 lost in the repeater outage).
- packets_raw by status: {"bad_crc": 31, "duplicate": 2095, "ok": 8301, "wrong_channel": 86}. Corrupted copies 31 (stored raw as bad_crc), public-channel frames 86 (wrong_channel).
- Duplicate copies sent by the radio 2108; duplicate reading keys in the database 0; stored keys equal the intact unique frames: True.
- Repeater outage 2026-12-20T14:36:00Z to 2026-12-20T20:36:00Z: 72 API probes; 2 answered 200 before the 15-min stale threshold, then 70/70 answered 503 with status ['stale'], level_m null and a labelled last_good. NODE_SILENT after 30.7 min, REPEATER_SILENT after 3.95 h of outage.
- Gateway unplug 2026-12-10T12:12:00Z to 2026-12-10T12:57:00Z: GATEWAY_DOWN ['2026-12-10T12:18:00Z', '2026-12-10T12:57:00Z']; 8 readings back-dated from seq on reconnect, time error [2.2, 2.1, 2.0, 2.0, 1.9, 1.9, 1.8, 1.7] min (the newest queued frame is stamped at drain time).

### Energy

Verdict window 2026-12-19 to 2027-01-01: **surplus** (cell reached full on 10 of 13 qualifying days (accepted harvest is capped by a full cell)); energy_ratio 0.943 (lower bound: True), days reached full 11, cold-inhibit hours 38.54, negative streak 1.

Truth: accepted harvest 160.3 mAh, panel-available harvest 6289.9 mAh, consumption 160.2 mAh; accepted ratio 1.001, available ratio 39.27 -> surplus. Service: harvest 161.0 mAh, consumption 156.6 mAh. Integrating raw ipanel as ARCHITECTURE 6.6 literally says would give 2696.4 mAh (ratio 17.22). Lowest true state of charge 79.9%.

| Date | Svc harvest | True accepted | True available | Svc cons | True cons | Svc cold h | True cold h | Full | Cov % | PSH |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-12-19 | 4.2 | 4.3 | 966.1 | 11.18 | 11.42 | 1.1 | 1.08 | yes | 100.0 | 6.39 |
| 2026-12-20 | 23.9 | 25.8 | 544.4 | 11.17 | 11.45 | 0.0 | 0.0 | yes | 74.7 | 3.46 |
| 2026-12-21 | 4.2 | 4.2 | 158.5 | 11.2 | 11.45 | 0.0 | 0.0 | yes | 100.0 | 1.01 |
| 2026-12-22 | 4.2 | 4.3 | 1005.5 | 11.19 | 11.42 | 0.0 | 0.0 | yes | 100.0 | 6.39 |
| 2026-12-23 | 26.6 | 25.8 | 147.1 | 11.18 | 11.49 | 0.0 | 0.0 | yes | 100.0 | 0.94 |
| 2026-12-24 | 4.2 | 4.3 | 4.3 | 11.18 | 11.42 | 9.02 | 9.02 |  | 100.0 | 3.2 |
| 2026-12-25 | 4.2 | 4.3 | 386.6 | 11.18 | 11.45 | 5.73 | 5.7 | yes | 100.0 | 6.4 |
| 2026-12-26 | 4.2 | 4.3 | 4.3 | 11.2 | 11.42 | 9.11 | 9.03 |  | 100.0 | 3.67 |
| 2026-12-27 | 4.2 | 4.3 | 4.3 | 11.2 | 11.45 | 9.02 | 9.03 |  | 100.0 | 6.41 |
| 2026-12-28 | 41.7 | 40.0 | 329.4 | 11.2 | 11.42 | 3.37 | 3.37 | yes | 100.0 | 3.02 |
| 2026-12-29 | 4.2 | 4.3 | 955.2 | 11.18 | 11.45 | 1.18 | 1.28 | yes | 100.0 | 6.43 |
| 2026-12-30 | 4.2 | 4.3 | 1011.9 | 11.19 | 11.45 | 0.0 | 0.0 | yes | 100.0 | 6.44 |
| 2026-12-31 | 26.9 | 25.8 | 198.5 | 11.18 | 11.42 | 0.0 | 0.0 | yes | 100.0 | 1.26 |
| 2027-01-01 | 4.2 | 4.3 | 573.6 | 11.18 | 11.45 | 0.0 | 0.0 | yes | 99.9 | 3.65 |

### Calibration history

| id | method | status | datum | valid_from | theta0 deg | h0 m | L_eff m | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | install | active | bulkhead_mark | 2026-12-05T12:47:27Z | 0.722 | -0.5040 | 7.6035 | n_tape=2, span_m=1.1606 |
| 2 | datum_tie | active | MLLW | 2026-12-05T12:47:27Z | 0.722 | 1.6312 | 7.6035 | n=16, shift_m=2.1352 |
| 3 | monthly_refit | active | MLLW | 2027-01-01T08:00:00Z | 0.722 | 1.6331 | 7.6005 | n=94, dh0_m=0.0019, dl_rel=-0.0004, rms_m=0.0229, within_bounds=True |

True values: theta0 (mount offset) 0.8 deg, L 7.62 m. theta0 also absorbs the sensor's temperature offset at install (k_T is 0 until bench B7), and h0 absorbs any theta0 error (ADR-009).

### Alerts raised

| Kind | Severity | Opened | Cleared | Value | Emailed |
| --- | --- | --- | --- | --- | --- |
| GATEWAY_DOWN | health | 2026-12-10T12:18:00Z | 2026-12-10T12:57:00Z | 360.000 | True |
| NODE_SILENT | health | 2026-12-10T12:40:00Z | 2026-12-10T12:58:00Z | 1811.000 | True |
| RAPID_RISE | warning | 2026-12-15T16:54:00Z | 2026-12-15T20:11:00Z | 0.160 | True |
| SURGE_WARNING | warning | 2026-12-15T17:09:00Z | 2026-12-16T02:41:00Z | 0.326 | True |
| SURGE_SEVERE | severe | 2026-12-15T18:35:00Z | 2026-12-15T23:24:00Z | 0.612 | True |
| NODE_SILENT | health | 2026-12-20T15:03:00Z | 2026-12-20T20:37:00Z | 1845.000 | True |
| REPEATER_SILENT | health | 2026-12-20T18:33:00Z | 2026-12-20T20:37:00Z | 14444.594 | True |

Emails recorded by the fake notifier: 7 (nothing was sent).

Final `/api/v1/level/current` (HTTP 200):

```json
{
 "status": "ok",
 "as_of": "2027-01-02T04:58:27Z",
 "age_s": 93,
 "level_m": 0.818,
 "level_raw_m": 0.857,
 "datum": "MLLW (tied to NOAA 8531942 predicted extremes; not surveyed)",
 "smoothing": {
  "method": "trailing_median",
  "window_min": 30,
  "n_points": 6
 },
 "trend": {
  "rate_m_per_h": 0.236,
  "direction": "rising",
  "excess_over_predicted_m_per_h": -0.007
 },
 "predicted_m": 0.879,
 "predicted_note": "prediction at as_of (NOAA 8531942 hi/lo, half-cosine); not an observation",
 "residual_m": -0.021,
 "residual_status": "ok",
 "calibration": {
  "version": 3,
  "valid_from": "2027-01-01T08:00:00Z"
 },
 "quality": {
  "pitch_sd_deg": 0.004,
  "flags": []
 },
 "weather_context": {
  "status": "disabled",
  "pressure_change_3h_hpa": null,
  "inverse_barometer_m": null,
  "onshore_wind_sustained": null,
  "wind_6h_mean_mps": null,
  "wind_6h_mean_dir_deg": null,
  "error": {
   "code": "TEMPEST_NOT_CONFIGURED",
   "message": "tempest.enabled is false"
  }
 },
 "components": {
  "gateway": "ok",
  "repeater": "ok",
  "node": "ok",
  "noaa": "ok",
  "tempest": "disabled"
 }
}
```

## Scenario `shaded-deficit-21d`

Wall time 8.8 s for 21 simulated days. Result: **all required checks pass**.

### Setup

| Item | Value |
| --- | --- |
| Simulated period | 2026-12-03T05:00:00Z to 2026-12-24T05:00:00Z (21 days), seed 1 |
| Tide | M2 0.42, S2 0.07, N2 0.09, K1 0.07, O1 0.05 m; mean 0.50 m above MLLW; weather noise sigma 2.5 cm (OU, tau 10 h, smoothed 1.5 h) |
| Cold snap | 2026-12-06T05:00:00Z to 2026-12-22T05:00:00Z, air -7 C vs normal |
| Panel / insolation | 1 W (Isc 185 mA, derate 0.85), vertical south, December mean 3.45 PSH (PVGIS), shading factor 0.02 |
| Ramp / sensor | L 7.62 m, hinge 2.10 m above MLLW, freeboard 0.45 m; SCL3300-like: mount offset 0.80 deg, drift 0.0035 deg/C (tidesvc k_T = 0), noise 0.004 deg, LSB 0.0055 deg |
| Node truth vs service model | sleep 55 uA, 128 mAs/cycle, clock +1.2% vs config 50 uA, 125 mAs/cycle |
| Radio | relay delivery 97.5%, direct copy 25% (duplicates), 0.2% corrupted copies, public-channel chatter |
| Install calibration | level check 2026-12-05T12:47:27Z; tape at 2026-12-05T13:17:27Z and 2026-12-05T19:30:59Z; fit 2026-12-05T20:30:59Z; datum tie 2026-12-09T20:30:59Z (shakedown compressed to 4 days) |

### Acceptance

| ID | Requirement | Target | Measured | Result |
| --- | --- | --- | --- | --- |
| ACC-1 | Served level (/level/current value: trailing 30-min median) vs true water level at the same instant, after calibration | RMS <= 5 cm | RMS 3.37 cm (bias -1.41, p95 5.78, max 7.71) | PASS |
| ACC-2 | Same, stretch goal | RMS <= 2 cm | RMS 3.37 cm | not met (stretch) |
| ACC-3 | Served level vs truth at the window centre it represents (removes the ~12.5 min trailing-median lag) | RMS <= 2 cm (stretch) | RMS 1.50 cm (bias -1.44) | PASS |
| ACC-4 | Historical centred 30-min median vs truth | RMS <= 2 cm (stretch) | RMS 1.51 cm (max 5.02) | PASS |
| HILO-1 | High/low timing (observed centred series vs true extremes) | RMS <= 5 min, max <= 10 min, >= 95% of extremes found | RMS 0.9 min, max 2.7 min, 55/55 found (100%; misses are in data gaps) | PASS |
| DEDUP-1 | Duplicate (direct + relayed) copies de-duplicated | one reading per (node, boot, seq); readings == intact unique frames | 1505 duplicate copies sent, 1496 marked duplicate (the rest arrived corrupted: bad_crc), 0 duplicate keys, readings == intact keys: True | PASS |
| ENERGY-1 | 14-day energy verdict matches the simulated truth | category == truth (deficit) | deficit (ratio 0.871, full on 0 of 14 days); truth: accepted ratio 0.816, available ratio 0.82 | PASS |
| ENERGY-2 | Harvest accounting vs truth (14-day window) | within 15% of true accepted harvest | service 136.4 mAh vs true 130.6 mAh; raw-ipanel integral (ARCHITECTURE 6.6 as written) 170.7 mAh | PASS |

### Level accuracy (after the datum tie)

| Series | n | RMS cm | bias cm | p95 cm | max cm |
| --- | --- | --- | --- | --- | --- |
| Served (trailing median) vs truth now | 4006 | 3.37 | -1.41 | 5.78 | 7.71 |
| Served vs truth at window centre (t-12.5 min) | 4006 | 1.50 | -1.44 | 2.17 | 4.10 |
| Raw per-reading level | 4006 | 1.56 | -1.46 | 1.76 | 8.58 |
| Centred 30-min median (history) | 4001 | 1.51 | -1.44 | 2.20 | 5.02 |
| Residual vs true residual | 4006 | 1.51 | -1.44 | 2.22 | 4.28 |

High/low: 55 of 55 true extremes located; timing error mean +0.0 min, RMS 0.9 min, p95 1.9 min, max 2.7 min; height RMS 1.5 cm. Observed vs NOAA predicted extreme times differ by 3.5 min RMS (that is real weather in the simulated water, not error).

### Link, de-duplication and faults

- Transmitted 5977, stored 5862 readings (98.1% delivery; 0 lost in the repeater outage).
- packets_raw by status: {"bad_crc": 25, "duplicate": 1496, "ok": 5862, "wrong_channel": 63}. Corrupted copies 25 (stored raw as bad_crc), public-channel frames 63 (wrong_channel).
- Duplicate copies sent by the radio 1505; duplicate reading keys in the database 0; stored keys equal the intact unique frames: True.

### Energy

Verdict window 2026-12-10 to 2026-12-23: **deficit** (energy_ratio); energy_ratio 0.871 (lower bound: False), days reached full 0, cold-inhibit hours 36.18, negative streak 1.

Truth: accepted harvest 130.6 mAh, panel-available harvest 130.6 mAh, consumption 160.1 mAh; accepted ratio 0.816, available ratio 0.82 -> deficit. Service: harvest 136.4 mAh, consumption 156.6 mAh. Integrating raw ipanel as ARCHITECTURE 6.6 literally says would give 170.7 mAh (ratio 1.09). Lowest true state of charge 57.1%.

| Date | Svc harvest | True accepted | True available | Svc cons | True cons | Svc cold h | True cold h | Full | Cov % | PSH |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-12-10 | 0.0 | 0.0 | 0.0 | 11.18 | 11.42 | 0.0 | 0.0 |  | 100.0 | 0.93 |
| 2026-12-11 | 2.5 | 0.9 | 0.9 | 11.2 | 11.45 | 5.31 | 5.27 |  | 100.0 | 1.43 |
| 2026-12-12 | 17.5 | 17.3 | 17.3 | 11.18 | 11.42 | 2.7 | 2.7 |  | 100.0 | 7.08 |
| 2026-12-13 | 7.3 | 6.9 | 6.9 | 11.19 | 11.45 | 4.22 | 4.13 |  | 100.0 | 3.94 |
| 2026-12-14 | 1.8 | 0.6 | 0.6 | 11.19 | 11.42 | 3.96 | 4.0 |  | 100.0 | 1.19 |
| 2026-12-15 | 19.0 | 19.0 | 19.0 | 11.18 | 11.45 | 2.11 | 2.07 |  | 100.0 | 7.06 |
| 2026-12-16 | 5.1 | 4.5 | 4.5 | 11.17 | 11.45 | 5.4 | 5.4 |  | 100.0 | 3.55 |
| 2026-12-17 | 11.1 | 10.9 | 10.9 | 11.19 | 11.42 | 2.28 | 2.23 |  | 100.0 | 4.37 |
| 2026-12-18 | 18.6 | 18.5 | 18.5 | 11.18 | 11.45 | 2.28 | 2.25 |  | 100.0 | 7.04 |
| 2026-12-19 | 18.8 | 18.7 | 18.7 | 11.18 | 11.42 | 2.11 | 2.15 |  | 100.0 | 7.04 |
| 2026-12-20 | 10.0 | 9.6 | 9.6 | 11.18 | 11.45 | 2.45 | 2.4 |  | 100.0 | 3.81 |
| 2026-12-21 | 1.6 | 0.5 | 0.5 | 11.19 | 11.45 | 3.37 | 3.35 |  | 100.0 | 1.11 |
| 2026-12-22 | 21.9 | 22.0 | 22.0 | 11.18 | 11.42 | 0.0 | 0.0 |  | 100.0 | 7.04 |
| 2026-12-23 | 1.2 | 1.2 | 1.2 | 11.18 | 11.45 | 0.0 | 0.0 |  | 99.9 | 1.03 |

### Calibration history

| id | method | status | datum | valid_from | theta0 deg | h0 m | L_eff m | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | install | active | bulkhead_mark | 2026-12-05T12:47:27Z | 0.711 | -0.5040 | 7.6062 | n_tape=2, span_m=1.1607 |
| 2 | datum_tie | active | MLLW | 2026-12-05T12:47:27Z | 0.711 | 1.6339 | 7.6062 | n=17, shift_m=2.1379 |

True values: theta0 (mount offset) 0.8 deg, L 7.62 m. theta0 also absorbs the sensor's temperature offset at install (k_T is 0 until bench B7), and h0 absorbs any theta0 error (ADR-009).

### Alerts raised

| Kind | Severity | Opened | Cleared | Value | Emailed |
| --- | --- | --- | --- | --- | --- |
| ENERGY_DEFICIT | health | 2026-12-10T05:05:00Z | None | 0.300 | True |
| ENERGY_NEGATIVE_STREAK | early_warning | 2026-12-10T05:05:00Z | 2026-12-13T05:05:00Z | 7.000 | True |

Emails recorded by the fake notifier: 2 (nothing was sent).

Final `/api/v1/level/current` (HTTP 200):

```json
{
 "status": "ok",
 "as_of": "2026-12-24T04:58:45Z",
 "age_s": 75,
 "level_m": 0.132,
 "level_raw_m": 0.149,
 "datum": "MLLW (tied to NOAA 8531942 predicted extremes; not surveyed)",
 "smoothing": {
  "method": "trailing_median",
  "window_min": 30,
  "n_points": 6
 },
 "trend": {
  "rate_m_per_h": 0.028,
  "direction": "rising",
  "excess_over_predicted_m_per_h": -0.004
 },
 "predicted_m": 0.165,
 "predicted_note": "prediction at as_of (NOAA 8531942 hi/lo, half-cosine); not an observation",
 "residual_m": -0.015,
 "residual_status": "ok",
 "calibration": {
  "version": 2,
  "valid_from": "2026-12-05T12:47:27Z"
 },
 "quality": {
  "pitch_sd_deg": 0.004,
  "flags": []
 },
 "weather_context": {
  "status": "disabled",
  "pressure_change_3h_hpa": null,
  "inverse_barometer_m": null,
  "onshore_wind_sustained": null,
  "wind_6h_mean_mps": null,
  "wind_6h_mean_dir_deg": null,
  "error": {
   "code": "TEMPEST_NOT_CONFIGURED",
   "message": "tempest.enabled is false"
  }
 },
 "components": {
  "gateway": "ok",
  "repeater": "ok",
  "node": "ok",
  "noaa": "ok",
  "tempest": "disabled"
 }
}
```

## Robustness across seeds (default scenario)

Same scenario, different random seeds (tide phases fixed; weather noise, wakes, loads, clouds, radio loss and sensor noise re-drawn).

| Seed | Served RMS cm | Window-centre RMS cm | Bias cm | Hi/lo RMS / max min | Warning latency min | Severe latency min | Energy verdict (truth) | Refit dh0 cm / dL % | Required checks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 3.57 | 1.70 | -1.61 | 1.1 / 4.0 | 25 | 22 | surplus (surplus) | +0.19 / -0.04 | all pass |
| 2 | 3.18 | 0.50 | +0.22 | 1.1 / 4.6 | 20 | 19 | surplus (surplus) | -0.13 / +0.04 | all pass |
| 3 | 3.19 | 0.47 | -0.09 | 1.1 / 4.8 | 17 | 17 | surplus (surplus) | -1.91 / -0.63 | all pass |
| 4 | 4.10 | 2.62 | -2.57 | 1.1 / 4.5 | 26 | 29 | surplus (surplus) | +0.68 / -0.50 | all pass |
| 5 | 3.74 | 2.02 | -1.92 | 0.9 / 3.5 | 23 | 28 | surplus (surplus) | +1.76 / -0.28 | all pass |
| 1 (tie 14 d) | 3.66 | 1.80 | -1.66 | 1.0 / 2.8 | n/a | n/a | surplus (surplus) | +0.21 / -0.04 | accuracy sensitivity only (surge precedes the tie) |
| 2 (tie 14 d) | 3.27 | 0.56 | -0.27 | 1.1 / 3.8 | n/a | n/a | surplus (surplus) | +0.27 / +0.04 | accuracy sensitivity only (surge precedes the tie) |
| 3 (tie 14 d) | 3.55 | 1.52 | -1.39 | 1.0 / 3.4 | n/a | n/a | surplus (surplus) | -0.59 / -0.63 | accuracy sensitivity only (surge precedes the tie) |
| 4 (tie 14 d) | 3.56 | 1.50 | -1.40 | 1.1 / 4.4 | n/a | n/a | surplus (surplus) | -0.50 / -0.50 | accuracy sensitivity only (surge precedes the tie) |
| 5 (tie 14 d) | 3.35 | 0.88 | -0.70 | 0.8 / 2.6 | n/a | n/a | surplus (surplus) | +0.49 / -0.28 | accuracy sensitivity only (surge precedes the tie) |

Rows marked 'tie 14 d' follow ARCHITECTURE 6.5 literally (datum tie at the end of a 14-day shakedown); accuracy is then measured over the remaining ~15 days only.

## Plots

PNG plots were written outside the repo (not committed): `sim-out/december-30d-level.png`, `sim-out/shaded-deficit-21d-level.png`

## Findings, deviations and limits

Found by simulating, fixed in code (not by loosening a check):

1. **Energy verdict could never say `surplus` for a healthy node.** Charger-accepted harvest is capped once the cell is full, so by conservation harvest/consumption tends to 1.0 whenever the cell keeps reaching full, whatever the panel size. ARCHITECTURE 6.6's ratio thresholds alone gave `marginal` (1.03) for a 1 W panel that refilled the cell on most days. ARCHITECTURE 6.6 already says full-charge days are the 'panel is large enough' signal; `tidesvc.energy.verdict` now applies it (full on at least half of the qualifying days means surplus) and reports `energy_ratio_is_lower_bound`. Needs Nick's agreement.
2. **Raw `ipanel` integration overstates harvest.** The INA3221 is read while the node is awake (about 25 mA from SYS). While charging, the BQ25185 sits in VINDPM and the sample is the panel current, which is correct; when charging is off (DONE, cold inhibit, CE override, latch), the sample is the node's awake current. The literal ARCHITECTURE 6.6 integral reported about 17x the true accepted harvest for the 1 W December run, and turned the shaded/cold deficit run into `marginal`. The same happens while charging in the CV taper near full, when the panel is no longer the limit (seeds 2-5 overstated harvest by 17-32% until fixed). `tidesvc.energy.harvest_current_ma` now counts ipanel as is only when the panel is pulled down to VINDPM (vpanel < vbat + 1.0 V), subtracts the awake read current otherwise, and counts only the modelled average load when not charging. Panel presence is judged by voltage, not by a near-zero current. Bench B10 must confirm the VINDPM signature.
3. **False DONE every night.** Without panel input the BQ25185 STAT pins float high (1/1), which ARCHITECTURE 4.7's DONE rule ('STAT 1/1 while /CE is LOW') reads as DONE. The firmware rule now also requires panel voltage (vpanel >= 3.0 V); the server ignores DONE without panel voltage.
4. **Envelope margin would reject a surge.** ARCHITECTURE 6.4 excludes readings outside the calibrated pitch envelope +/-0.5 deg, which is only about 6.6 cm of level. The install fit therefore sets the envelope from the tape levels -1.0 m / +2.0 m, so a real surge is not discarded as out of range.
5. **Residual lag.** A trailing 30-min median lags the water by about 12.5 min, which alone is about 5 cm of residual error at mid-tide. The prediction is now passed through the same trailing median over the same reading times before subtracting (`predicted_smooth_m`); `predicted_m` is still the plain prediction.
6. **One-sided extreme fits.** An extreme next to an outage could be fitted from data on one side only (an 18-minute timing error in an early run). `find_extreme_near` now requires data on both sides of the vertex, which also protects the monthly refit.
7. **Cold-inhibit hours counted the night.** The firmware cold bit is set whenever the box is below +1 C, so 'time with cold_charge_inhibit set' (ARCHITECTURE 6.6) counted every cold night and blurred 'no sun' with 'too cold to charge' (PRD FR6). `charge_inhibit_cold_h` now counts cold-bit time with panel input present.
8. **World-model fix (simulator only).** The first weather-noise model was an unsmoothed random walk, which made even the true high/low times jitter by tens of minutes; it is now smoothed (1.5 h).

Limits that remain (reported, not hidden):

- The served `level_m` is a trailing median, so against the true water at the same instant it carries the ~12.5 min lag: see ACC-1/ACC-2. It meets +/-5 cm; it does not meet the +/-2 cm stretch at mid-tide rates. Against the time it represents (window centre), and as history, it is within 2 cm.
- The datum comes from NOAA predicted extremes (ADR-009). It absorbs the mean weather residual of the tie window: -1.6 cm of bias in the default run (-2.6 to +0.2 cm across seeds), which dominates the error budget. The sim compresses the 14-day shakedown to 4 days so that the surge and faults happen after the tie; the 'tie 14 d' rows show a 14-day tie gives a similar bias (-1.7 to -0.3 cm), because the level error is the difference between the mean weather residual over the tie window and over the evaluation window, each of order 0.5-1 cm for a 2.5 cm residual correlated over ~10 h. The Sandy Hook residual could be used to correct the tie; that is not in the architecture and was not done.
- `k_T` stays 0 (no bench B7 yet); the simulated sensor drifts 0.0035 deg/C, about 0.5 mm per C of level.
- The simulated physics (charger, panel, cell, wakes) is a model with stated assumptions, not a substitute for the bench tests B1-B13 and the RF tests; nothing here verifies MeshCore, the companion protocol or meshcore_py.
