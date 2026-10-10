# Test Plan: LoRa Ramp Tide Sensor (one-node pilot)

**Version:** 0.2 (draft)
**Last Updated:** 2026-10-10
**Author:** Nick DeMarco, with AI assistance (qa-strategy agent)
**Status:** Draft, for Nick's review
**Inputs:** `docs/PRD.md` v0.3, `docs/ARCHITECTURE.md` v0.2 plus Nick's answers log, `docs/BATTERY.md` v0.2, `docs/BOM.md` v0.2

**Changes in v0.2 (2026-10-10):** charger is the BQ25185, so FW-U7 is rewritten for the correct /CE polarity (HIGH = disabled) and the +1/+2 °C firmware rule, FW-U10 (safety-timer CE pulse) and B13 are added, B9 pass criteria reflect the 130 kΩ hardware backstop at about -3 °C (firmware alone owns 0 °C), and B10's harvest check accounts for the power path. RF section restated for flood routing through Nick's repeater with per-hop margin. RF-7 now expects repeater health (`REPEATER_SILENT`) instead of a known gap. Alert tests cover `ENERGY_NEGATIVE_STREAK` (early warning) and `REPEATER_SILENT`. Section 11 updated; remaining open items moved to DEV-PLAN section 7.

This is a hobby build with one node, one gateway and one repeater. The plan is deliberately small: automate what is cheap and deterministic (codec, math, server behavior), bench-measure what the whole project depends on (energy, cold charging, link margin), and treat the field phases as the real acceptance test. Bench results go in `docs/bench/` (per ARCHITECTURE section 10). Nothing here is a coverage target; the gate is the pass criteria below.

---

## 1. Objectives, scope, and where the risk actually is

**Objectives (in PRD order of importance):**
1. Answer the solar question with logged evidence (G1, FR6).
2. Show a credible water level (+/-5 cm vs reference, stretch +/-2 cm).
3. Never present invented data as an observation (FR5, no demo fallback).
4. Run unattended, with failures that are visible and distinguishable.

**Out of scope:** certification as a tide gauge, load/stress testing of the API (one node, a few consumers), browser/device matrix and accessibility (there is no UI in this repo; the SignBoard tide panel is a separate SignBoard change), penetration testing beyond "API is read-only and LAN/Tailscale only".

**Where the error budget sits (so test effort goes to the right place).** Level sensitivity is `L * cos(theta) * dtheta`, about 1.3 mm per 0.01 degree at L = 7.62 m. The +/-5 cm target is therefore about +/-0.38 degree of tilt, and +/-2 cm is about 0.15 degree. Sensor noise is far inside that. The dominant errors are scale (L_eff, 1% = about 9 mm over a 0.9 m swing), float freeboard changes with load and wakes, datum tie, and the half-cosine prediction error at mid-tide. So: do the sensor characterization once and cheaply, and spend the effort on calibration procedure, install, and the end-to-end soak.

Likewise on energy: break-even harvest at the 25 mAh/day design budget is roughly 0.16 peak-sun-hours on a 1 W panel (using the architecture's eta = 0.5), against 2.75-3.45 in December. Panel size is not the binding risk on paper. The real failure modes are cold-charge inhibition, heavy shading, a sleep current several times the estimate, and a hardware fault. The tests below are aimed at those.

---

## 2. Test levels and tooling

| Level | What | Where | Automated |
|---|---|---|---|
| Host unit (firmware logic) | Codec, stats, battery state machine, CE-override rule | PlatformIO `native` env | Yes |
| Host unit (server) | Codec, conversion, calibration fit, residual, energy, alerts, API | pytest (frozen clock, respx fixtures) | Yes |
| Bench (hardware) | Noise, temperature drift, scale, sleep/awake current, brownout, cold charge | Bench + freezer, results in `docs/bench/` | Manual |
| RF | Bench link, fade margin, range test, repeater hop | Field | Semi (logs from tidesvc) |
| End-to-end soak | Whole chain incl. NOAA, email, restart/outage injection | Bench then installed | Semi |
| Install acceptance | Calibration and tape-measure checks | On the ramp | Manual |
| Solar sufficiency | Winter energy log analysis | Field, Dec-Feb | Computed by `tidesvc` energy module plus a one-off analysis script |

**Equipment:** current meter with microamp resolution and logging (Nordic PPK2, Otii, or uCurrent plus a logging DMM); freezer plus a thermocouple or a second NTC for ground-truth temperature; a tilt rig with a sine bar or gauge blocks (or a digital level of known accuracy as the reference); bench supply with current limit; a 10 dB SMA attenuator (and a 20 dB if available); a spare Heltec V3 for spectrum sniffing and as a stand-in gateway; tape measure (mm), digital level, camera.

**Shared fixtures:** `tests/fixtures/packets_v1.json` (golden vectors, consumed by both C++ native tests and pytest), recorded NOAA responses (8531942 hilo, 8531680 observed and 6-min predicted, plus an outage and a malformed response), recorded Tempest responses.

---

## 3. Firmware

### 3.1 Host unit tests (native, no hardware)

| ID | Area | Cases | Pass |
|---|---|---|---|
| FW-U1 | Payload v1 encode | All fields at min, max, zero; negative pitch, roll, temp; `pitch_sd` above 0.255 degree (the u16 widening); every flag bit set singly and all together | Bytes equal golden vectors; length 26; little-endian offsets per ARCHITECTURE 4.7 |
| FW-U2 | CRC-16 | CRC-16/CCITT-FALSE check value for ASCII `123456789` is `0x29B1`; CRC covers bytes 0-23 | Matches; one flipped bit anywhere changes CRC |
| FW-U3 | Decode/round trip | encode then decode, C++ output decoded by the Python codec and the reverse | Identical field values, via the shared vectors |
| FW-U4 | Stats | Median and SD of 300 samples: constant, ramp, single outlier, all identical. **Even-count median rule** (300 is even) must be fixed in one place and the server test must agree | SD 0 for constant; outlier does not move median; rule documented |
| FW-U5 | Quantization | pitch 0.001 degree LSB, saturation at +/-32.767 degree, temp 0.1 C | Clamp, never wrap |
| FW-U6 | Battery state machine | Thresholds (3.15 / 3.05 V placeholders): intervals 5/15/60 min, flags `low_batt`, `critical_batt`, `reduced_interval`, `sensor_skipped`; hysteresis at the boundaries | Correct state and interval for each vbat step, both directions |
| FW-U7 | Cold-charge CE rule (BQ25185: /CE HIGH = charging disabled) | Pure function: /CE HIGH (disable) when die temp < +1 C; /CE LOW (enable) when > +2 C; previous state held between +1 and +2 C; `cold_charge_inhibit` and CE-override bits; behavior at -40, 0.9, 1.0, 1.1, 1.9, 2.0, 2.1, 85 C, approached from both directions; sensor error with unknown temp | Fail-safe: unknown temperature means /CE HIGH (charging disabled) |
| FW-U10 | Safety-timer CE pulse | Pure function of STAT history: continuous "charging" counted across wakes; at about 4 h a pulse (HIGH then LOW) is issued and the counter resets; counter resets on "not charging", done, or panel loss; no pulse while the cold rule holds /CE HIGH | Pulse at the configured time, never during cold inhibit; `chg` bit5 set on the cycle that pulses |
| FW-U8 | Seq/boot counters | seq increments per frame, u16 wrap 65535 to 0; boot_count wrap; reboot flag only on first frame after reset | Matches vectors |
| FW-U9 | Range flags | `out_of_range` at \|pitch\| > 15 or \|roll\| > 10 degree; `high_sd`; `short_sample`; `sensor_error` zeroing | As specified |

### 3.2 Bench tests

Run in this order. Each has its own pass criterion; a fail stops the line until understood. All results recorded with date, firmware commit, board and cell ID.

| ID | Test | Method | Pass / action |
|---|---|---|---|
| **B1** | **Spike S1: minimal MeshCore sender** | Node sends one GRP_DATA frame on a private channel and deep-sleeps; companion v1.17.1 gateway reports frame `0x1B` with the right bytes | Payload decodes with a good CRC; node returns to sleep without listening. If this fails, the architecture's premise fails; stop and re-plan. |
| **B2** | **Sleep current** | Whole node as it will be installed (charger, INA3221 power-down, battery divider, Vext off), panel disconnected, dark, cell or 3.2 V supply, settle at least 60 s. Repeat at about +20 C and about 0 C | Target at most 50 uA (the `config.toml` default). Acceptable at most 100 uA. Above 100 uA: find the leaker (divider, charger quiescent, INA3221, Vext FET) before continuing. |
| **B3** | **Awake charge per cycle and airtime** | Capture a full wake: init, sample, TX at the chosen SF/BW/power. Integrate mAs. Re-run with the final private-frequency settings and TX power | Target about 125 mAs (model). Acceptable at most 200 mAs. Hard limit about 280 mAs: at 288 cycles plus 100 uA sleep that exhausts the 25 mAh/day budget. Record `awake_ms` against `awake_ms_prev` reported in the packet (should agree within 5%). |
| **B4** | **24 h energy run** | Node cycling normally on the bench with the current logger for 24 h (at least 288 cycles) | mAh/day within 10% of B2 + B3 prediction; at most 25 mAh/day. This is the value that goes into `config.toml` (`i_sleep_ua`, `awake_mas_per_cycle`) and the solar report. |
| **B5** | **Noise** | Node fixed on the tilt rig at 0, about 3 and about 7 degree, 2 h each, normal 5-min cycling, cell-powered, no vibration. Then one run with a table tap or a fan nearby | SD of the per-cycle **median pitch** across cycles at most 0.01 degree (PRD NFR, about 1.3 mm). Per-burst `pitch_sd` reported separately. Disturbance run should raise `pitch_sd` and trip `high_sd` at the intended level without crashing. |
| **B6** | **Scale, linearity, sign** | Tilt rig at 6 or more angles across 0-8 degree against a sine bar or reference digital level | Error at most 0.02 degree (reference limited). Sign convention and axis (pitch vs roll) confirmed so the install cannot be mounted swapped. |
| **B7** | **Temperature drift** | Node (sensor and enclosure) on the rig at fixed angle in the freezer, then ambient, then +40 C, slow ramp (at most 1 C/min so die temp tracks air temp), at least 30 min soak at each of -15, 0, +20, +40 C, with a reference thermocouple. Fit `k_T` in degree per C | Residual drift after `k_T` correction at most 0.05 degree (about 6.6 mm) across -10 to +40 C. If raw drift is already within that, leave `k_T = 0`. Record the lag between die temp and air temp; the die temp is also used as the battery-temperature proxy. |
| **B8** | **Brownout** | Bench supply with a series resistance matching the cell (cell internal resistance, cold value if measured), sweep 3.6 to 2.9 V while the node cycles, plus a TX-under-load check at each step. Repeat with the real cell at about 0 C if possible | Record the voltage where it first resets or fails to TX. Node must (a) enter `critical` / 60 min behavior above that voltage with at least 0.1 V margin, (b) never boot-loop, (c) set `brownout_reset` on the first frame after recovery. Adjust the 3.15 / 3.05 V thresholds to the measured knee. |
| **B9** | **Cold charge inhibit (freezer)** | See below | See below |
| **B10** | **Charger and telemetry accuracy** | Reference meter in series with panel input and cell. Panel emulation with a current-limited bench supply (6 V open circuit; limits 5, 10, 20, 50, 100 mA). Compare `ipanel`, `vpanel`, `vbat` against the reference. Integrate `ipanel` over a controlled charge of a part-discharged cell, with the node load running, and compare with the Ah actually accepted by the cell | `ipanel` within +/-5% or +/-1 mA (whichever is larger); `vbat` within +/-20 mV. **Harvest definition check:** the BQ25185 is linear with a power path (load served from SYS), so in sun `ipanel` ≈ load + charge. Pass if integrated `ipanel` minus the measured load charge is within +/-10% of cell-accepted charge (ARCHITECTURE 6.6). Also: panel Voc (measure in full sun) is below the BQ25185 input maximum (18 V operating) with margin. |
| B11 | Weak-light charging | Same emulation at 2, 5, 10 mA and at the lowest panel voltage the real panel gives in overcast | Charger starts and accepts current. Record the minimum input voltage/current at which charging starts. Feeds the inferred 0.5 W case in section 8. |
| B12 | Enclosure | Assembled node, desiccant in, humidity indicator card inside; 30 min under 10 cm of water or a hose test; gland and drip-loop check; thermal cycle (freezer to warm room) twice | Card unchanged, no moisture. Re-check at the first desiccant swap. |
| B13 | Safety timer and /CE fail-safe (BATTERY.md T3, T7) | Emulate 7 h of continuous weak sun (VINDPM) on a nearly full cell, with and without the firmware pulse. Then remove MCU power with the panel supply on | Without the pulse, charging latches off (STAT 0/0) at about 6 h; with the pulse about every 4 h, no latch. With the MCU unpowered, the 1 MΩ pull-up keeps charging disabled until the MCU boots from SYS and drives /CE LOW. |

**B9 detail: cold charge inhibit.** This is both a safety item (charging LiFePO4 below 0 C damages the cell) and the largest unknown for the winter test. The cell is unprotected (no protected LiFePO4 cell was found, BATTERY.md 2.2), so use the 1 A fuse and a current-limited supply on the panel input. Design (Nick, 2026-10-10): **firmware owns the 0 C rule** (disable below +1 C, enable above +2 C); the charger NTC (B3435 with 130 kΩ in parallel) is a **hardware backstop at about -3 C** (resume about +2.4 C).
1. Cell at about 20 C: confirm charging starts with the supply connected (`chg` bit0, battery current positive). This is the control.
2. Put the node, cell and NTC in the freezer (about -18 C) until the NTC and the die temp read below -5 C. Apply the supply. Expect no charge current, `cold_charge_inhibit` set, and `vpanel` present. Confirm the node keeps running from the panel through SYS.
3. Test the **firmware** rule alone (NTC replaced by a fixed 10 kΩ, so the charger always sees 25 C): charging stops when die temp falls below +1 C and restarts above +2 C. Test the **hardware** backstop alone (firmware CE rule disabled in a test build): charging stops at about -3 C falling (record the value) and restarts at about +2.4 C rising (record the value).
4. Warm slowly with both layers active. Record the cell temperature at which charging resumes. Confirm no oscillation (rapid on/off) near either threshold.
5. Verify the NTC is physically on the cell, not just in the box (cell temperature lags and is colder than air in a shaded ramp). Record the offset between die temperature and cell (NTC/thermocouple) temperature during cool-down, since the firmware rule uses die temperature.
Pass: with both layers active, zero charge current at cell temperature below 0 C; the firmware rule alone stops charging above 0 C cell temperature (the +1 C threshold minus the measured die-to-cell offset must stay above 0 C); the hardware backstop alone stops charging at or above about -4 C; inhibit logged distinctly from "no sun" in the packet. Fail on any measurable charge current at cell temperature below 0 C with both layers active.
**Safety:** never connect USB to the Heltec while the LiFePO4 cell is attached (the onboard charger is a 4.2 V Li-ion charger). Test builds are programmed with the cell disconnected, and the enclosure label is part of acceptance.

**Note on the charger:** B9, B10 and B13 are charger-specific. The charger is settled as the TI BQ25185 on Adafruit 6091 (BATTERY.md; BOM and ARCHITECTURE v0.2 agree). Its TH pad is broken out. BATTERY.md section 9 (T1-T10) holds the detailed bench procedures; this plan's B-tests are the acceptance view of them.

---

## 4. Server (`tidesvc`)

All of this runs in CI-less pytest on the dev machine, with a frozen clock and recorded NOAA/Tempest fixtures (no live network in unit tests). Test IDs map to ARCHITECTURE section 10.

### 4.1 Decode and ingest

| ID | Case | Pass |
|---|---|---|
| SV-D1 | Golden vectors (shared with FW-U1) | Fields exact |
| SV-D2 | Bad CRC; wrong `ver`; wrong channel; wrong data type; length 25 and 27 | Raw frame stored with `parse_status` set; no `readings` row; not counted as a valid reading |
| SV-D3 | De-dup on `(node_id, boot_count, seq)`, including the same frame arriving direct and via the repeater | One reading; duplicate counted in link stats |
| SV-D4 | Seq wrap (65535 to 0), boot_count increment with seq reset, gap of N frames | Loss counted correctly; no negative or huge gap on a reboot |
| SV-D5 | Backlog drain (several frames in seconds, as the companion's 16-frame queue does) | Timestamps back-filled per ADR-012, `time_source = backfilled`, excluded from live "current" but kept |
| SV-D6 | Raw first | A frame that fails to parse is still in `packets_raw` |
| SV-D7 | Fake companion over a pty: unplug and replug, reconnect backoff | API stays up, gateway status `error` then `ok`; no crash |

### 4.2 Conversion and calibration math

| ID | Case | Pass |
|---|---|---|
| SV-C1 | Conversion formula `h = h0 + L*sin(radians(pitch - theta0))`. Hand vectors (re-verify in code): with L = 7.62, h0 = 0, theta0 = 0: 0 degree gives 0; 3.0 degree gives 0.3988 m; 6.5 degree gives 0.8626 m. With `k_T` set, `pitch_corr = pitch - k_T*(temp-25)` | Exact to 1e-6 m |
| SV-C2 | Validity rules: `sensor_error`, `out_of_range`, outside envelope +/-0.5 degree, `pitch_sd > 0.25` | Excluded from level and alerts, kept raw, `invalid_reason` set |
| SV-C3 | Smoothing: trailing 30-min median (needs at least 4 valid points, else null with `insufficient_points`); centred median for history | Matches hand-computed series; lag about 15 min on a ramp input |
| SV-C4 | Install fit: synthetic tide (two harmonics) plus 0.005 degree noise plus 1 cm freeboard jitter, known (h0, L_eff) | Recovers h0 within 1 cm and L_eff within 1% |
| SV-C5 | Identifiability: perturb theta0 by 0.1 degree | Absorbed into h0 as documented (theta0 stays fixed); test pins this behavior |
| SV-C6 | Bound logic: |dh0| 0.049 vs 0.051 m; |dL/L| 2.9% vs 3.1% | Applied vs `proposed` plus `CALIBRATION_DRIFT`; nothing applied silently |
| SV-C7 | Matched-extremes pairing (+/-90 min), calm-day gating (|residual_SH| < 0.10), too few matches in a month | Fit uses only qualifying pairs; with too few it does not fit or apply (**spec gap: minimum number of matched extremes is not defined**) |
| SV-C8 | Versioning and reprocess | Derived rows carry calibration version; `reprocess` leaves raw untouched and is idempotent |

### 4.3 NOAA prediction and residual

| ID | Case | Pass |
|---|---|---|
| SV-N1 | Half-cosine interpolation: value equals the extreme at each extreme; midpoint equals the average; monotonic between extremes; hi-to-lo and lo-to-hi | Exact |
| SV-N2 | Request parameters: `station=8531942`, `product=predictions`, `interval=hilo`, `datum=MLLW`, `units=metric`, GMT time zone, `application=lora_ramp_tide_sensor` | Matches; local-time handling checked around DST |
| SV-N3 | Residual = smoothed level minus prediction; rate of rise = slope(level) - slope(pred) over 60 min | Matches hand series; sign convention (positive = above predicted) |
| SV-N4 | Injected surge: add +0.35 m ramp over 3 h to synthetic observed | `SURGE_WARNING` opens after 2 consecutive evaluations; `RAPID_RISE` fires on the slope; clears per the stated condition; one email, de-duplicated |
| SV-N5 | NOAA down, cache covers now: status `degraded`, residual still computed from published predictions | 200, residual present, `noaa` component `error` |
| SV-N6 | NOAA down, cache does not cover now: `PREDICTION_UNAVAILABLE`, residual error state | `residual_m` null; never extrapolated; no stand-in value |
| SV-N7 | Malformed or empty NOAA response; 8531942 `interval=6` "no data" response | Treated as fetch failure; cache untouched |
| SV-N8 | **Interpolation error quantification** (ARCHITECTURE section 10): hi/lo from Sandy Hook interpolated by half-cosine vs its 6-min harmonic predictions over a year | Publish RMS and 95th-percentile error in `docs/bench/`. Proposed gate: RMS at most 0.10 m (a third of the 0.30 m warning). If worse, quote ">0.30 m surge" confidence accordingly and judge +/-5 cm accuracy at the extremes only (where interpolation is exact by construction). |

### 4.4 Energy module

| ID | Case | Pass |
|---|---|---|
| SV-E1 | Trapezoidal integration of `ipanel`; gaps over 15 min not integrated; `coverage_pct` | Matches hand-computed day |
| SV-E2 | SoC coulomb count re-anchored at DONE, clamped to [0, capacity] | Matches |
| SV-E3 | Verdict thresholds: ratio 2.0 surplus, 1.0-2.0 marginal, under 1.0 deficit; `insufficient_data` under 7 days at 80% coverage | Boundaries exact |
| SV-E4 | Local-day rollup on DST days (Sun 2026-11-01 is 25 h; Sun 2027-03-14 is 23 h) and the monthly refit at 03:00 local on the 1st | Correct day totals, no skipped or doubled rollup. **This lands inside the first shakedown.** |
| SV-E5 | Consumption model uses `awake_ms_prev` and config constants, and records which constants were used | Constants recorded per day |

### 4.5 Alerts

One table-driven test per row of ARCHITECTURE 6.8: open condition, clear condition and hysteresis, de-duplication while open, clear-condition text present in the email, and (for `SURGE_WATCH`) evaluated only when Tempest is `ok`. `TEMPEST_UNAVAILABLE` never emails. Add: two alerts open at once; process restart while an alert is open (does not re-send on startup).

Specific cases for the v0.2 rules:
- `ENERGY_NEGATIVE_STREAK` (early warning): 6 vs 7 consecutive negative-net days; a low-coverage day inside the streak (skipped, neither extends nor breaks it); clears on the first qualifying non-negative day; the email is marked early warning; it never changes the 14-day verdict or opens `ENERGY_DEFICIT` by itself.
- `REPEATER_SILENT`: relayed frames (`path_len >= 1`) keep the repeater `ok` without adverts; adverts alone keep it `ok`; silence for `silent_after_s` opens it; it is suppressed while `GATEWAY_DOWN` is open; the email says "check the repeater first" when the node is also silent.

### 4.6 API: stale, errors, and no demo fallback

This is the hard requirement from FR5 and CLAUDE.md. Test it as a property, not just by example.

| ID | Case | Pass |
|---|---|---|
| SV-A1 | `/level/current` at 14:59 and 15:01 since the last valid reading (stale after 900 s) | 200 `ok` then 503 `stale` |
| SV-A2 | 503 body: `level_m`, `residual_m` null; `last_good` present, labelled, with its own timestamp; `predicted_m` present but labelled as prediction | Exactly as ARCHITECTURE 7.3 |
| SV-A3 | **Fresh database** (no readings, no calibration, no predictions) | 503 with null observed fields and no `last_good`; no zeros, no placeholder |
| SV-A4 | **Property test:** for every combination of component states (gateway ok/error, node ok/stale/silent, NOAA ok/error/uncovered, calibration present/absent, Tempest ok/disabled/error), no observed field ever equals a predicted value, a default, or a value from an invalid reading | Holds for all combinations |
| SV-A5 | Invalid readings (`out_of_range`, high SD, sensor error, backfilled) | Excluded from `/level/current`; shown as `valid: false` with a reason in history |
| SV-A6 | Gateway link lost while node healthy | `GATEWAY_DOWN`, component status distinct from node `stale` |
| SV-A11 | Repeater silent while gateway ok (fake companion stops relayed frames and adverts) | `/api/v1/status` shows repeater `silent` and overall `degraded`; `/node/health` repeater block present; distinct from node `stale` and gateway `error` |
| SV-A7 | Tempest disabled, 401, timeout, missing fields, stale obs | Core endpoints byte-identical (excluding the weather block); fields null with a reason, never defaults |
| SV-A8 | Composite and history endpoints during the same faults | 200 with per-component `status`; `/healthz` 200 while the process is up |
| SV-A9 | CSV export during an outage day | Gaps are empty cells with a reason, not filled |
| SV-A10 | Read-only | No write verbs routed; unknown paths 404 |

---

## 5. RF link tests

Prerequisite: Q1 is answered with **Nick's solar PVC-tube repeater bridging the ramp to the gateway** (node in **flood** mode, ADR-003 v0.2), and Q2 with a **private frequency and encrypted channel**, set identically on node, repeater and gateway. **Acceptance is stated as margin over the demodulation floor of the chosen SF, per hop** (approx. -7.5, -10, -12.5, -15 dB for SF7, 8, 9, 10 at the usual bandwidths; ARCHITECTURE 5.4): median SNR at least 10 dB above the floor, or at least 10 dB fade margin by the attenuator test. The gateway's reported SNR covers only the repeater → gateway hop; the node → repeater hop is proved by RF-3. The repeater's own power budget is not tested here (outside this project).

**Counting delivery.** Two independent measures, and both must be reported.
- Seq-based: `received_unique / (seq_max - seq_min + 1)` within a boot, handling wrap and boot_count. This misses loss across a reboot and at the ends.
- Time-based: unique frames per local day versus 288 (+/-5% for oscillator drift). This catches what seq cannot.
Reduce the expected count in periods when the node was legitimately in 15-min or 60-min mode (flag `reduced_interval`).

| ID | Test | Method | Pass |
|---|---|---|---|
| RF-1 | Spectrum check | Spare radio logs RSSI on candidate frequencies for 24 h at the gateway and at the ramp | Choose the quietest slot inside 902-928 MHz; record the noise floor |
| RF-2 | Bench link | Node 1-3 m from gateway, final settings, 1 h | 100% delivery; SNR/RSSI baseline recorded |
| RF-3 | **Fade margin** | Final antennas and geometry; insert a 10 dB attenuator in the node antenna feed (20 dB for a stretch test); 24 h | At least 95% delivery with 10 dB inserted. This directly proves 10 dB of margin without needing SNR statistics. |
| RF-4 | **Range test, node leg** | Node temporarily clamped (not bonded) at the final position and antenna height, final TX power; 48 h or longer, spanning at least one high and one low tide | At least 95% delivery overall and at least 85% in the worst rolling 6-hour window (tide-correlated fades, boats, people). Per PRD this is done before anything is bonded. |
| RF-5 | **Repeater hop** | Node, repeater, gateway in final positions; node in flood mode (ADR-003 default; zero-hop is not relayed; confirm the exact MeshCore behavior in S1). 48 h | End-to-end at least 95% delivery; `path_len` 1 where expected; repeater → gateway median SNR at least 10 dB above the chosen SF floor; duplicates from direct and relayed copies de-duplicated (SV-D3) |
| RF-6 | Repeater power-saving | Repeat RF-5 with the repeater's `powersaving` mode on and off | No significant drop with it on. Light-sleep can miss a short preamble; if it does, record it for Nick (the repeater's power budget is his separate concern) |
| RF-7 | Repeater/gateway fault visibility | Power the repeater off for longer than `silent_after_s` (default 4 h); then unplug the gateway for 30 min; then reboot the mini PC | `/level/current` goes 503 at 15 min; `NODE_SILENT` at 30 min; repeater status `silent` and `REPEATER_SILENT` open once `silent_after_s` passes (ARCHITECTURE 5.5); gateway `ok` vs `error` as documented. If the advert/status path in E5.9 turned out unworkable, record that the repeater is visible only through relayed frames, and keep the runbook line "node silent and repeater silent: check the repeater first". |
| RF-8 | Repeat at final settings after any change of SF, TX power, antenna, or repeater position | As RF-4 | Same criteria |

---

## 6. End-to-end soak

| Stage | Duration | Setup | Pass |
|---|---|---|---|
| **Soak A: bench** | 72 h minimum | Real node, real gateway, real `tidesvc` on the mini PC (or a staging copy), node on a tilt rig that is moved by hand twice daily through a tide-like sequence, NOAA live, SMTP live, repeater in the path | No unplanned `tidesvc` restart; no memory growth beyond the 256 MB limit; DB and CSV rows consistent with packets received; delivery at least 95% |
| **Soak B: installed shakedown** | 14 days (the PRD shakedown) | Installed and calibrated per section 7 | PRD section 7 metrics 2 and 3 (calm-day hi/lo within +/-15 min and +/-5 cm; at least 95% delivery) |

**Fault injection during Soak A or B** (one at a time, each with the expected visible behavior and recovery):
1. Block NOAA at the firewall for 1 h, then for longer than cache coverage.
2. Unplug the gateway USB, replug (udev symlink, hot-plug).
3. Power-cycle the node (expect `reboot` flag, `boot_count` increment, no phantom level).
4. Reboot the mini PC (service autostarts, backlog drained from the companion's queue, time back-filled).
5. Force a real email: temporarily set `surge_warning_m` low in config, confirm one email with its clear condition and the context lines, restore the config.
6. Leave the node covered for 3 days to see the battery-state ladder and recovery (bench only).
7. Cross DST (2026-11-01) with the service running.
8. Restart `tidesvc` while an alert is open (no duplicate email).

Review the logs for: duplicate readings, level values during staleness, and any API response where an observed field is non-null while a component is in error.

---

## 7. Install acceptance and calibration procedure

### 7.1 Pre-install gate (bench, before anything is bonded)

- B1-B13 recorded and passed; `config.toml` constants updated from B4.
- RF-3 to RF-5 passed at the final positions with the node clamped, not bonded.
- Enclosure leak test passed (B12); desiccant fitted; USB warning label fitted; cell fully charged at room temperature before it goes outdoors in cold weather.
- Site shading check on the south face done (phase 0); the Voc of the actual panel measured and confirmed within the charger input rating.
- Reversible, no-drill mounting method confirmed.

### 7.2 Install

1. Fit the enclosure and bond or clamp the panel (allow the adhesive cure time before loading it).
2. Check the stub antenna stands 2-3 cm off the metal and matches the RF-4 geometry (re-run a short RF-4 if it differs).
3. Confirm packets arrive and decode, `cold_charge_inhibit` and `chg` bits are sane, `roll_mean` is stable (detects bracket creep or twist).
4. Mark a **permanent reference point** on the bulkhead (paint pen or tag) and photograph it. All freeboard readings are taken from this mark.

### 7.3 Two-state calibration (FR3, ADR-009)

Needs two tide states at least 0.5 m apart; with a 0.8-1.0 m range, that is one near high and one near low, about 6 hours apart. A third mid-tide reading is taken as a consistency check, and a fourth state on another day is the validation set.

| Step | Do | Record |
|---|---|---|
| 1 | Pick a calm moment: no one on the ramp, no wake from a passing boat. Note time to the minute | UTC time, weather, wind, who was on the ramp |
| 2 | Measure freeboard (bulkhead mark to the float reference or the water, one chosen reference only) **three times** with a tape, to the nearest mm | The three values and their mean; spread must be 3 mm or less, otherwise repeat |
| 3 | Take the node pitch: at least 3 consecutive packets spanning the measurement time (median); also a digital level on the ramp rail as a cross-check (+/-0.1 degree is about +/-13 mm, so a sanity check, not the reference) | Packet seq numbers and pitches |
| 4 | Enter with `tidesvc cal add-obs` | |
| 5 | After at least two states: fit L_eff from the change in level over the change in sin(pitch); theta0 fixed from the install level reading; h0 relative to the bulkhead mark | Fit stats |
| 6 | Mid-tide point and later states: check them against the fit | Residuals |

**Calibration acceptance:**
- Fit residual on the third reading at most 1 cm.
- L_eff within 3% of the geometry value (about 7.62 m, to be confirmed from Meeco Sullivan drawings); a larger difference is a flag to re-check the geometry or the hinge, not necessarily a failure.
- On a **fourth, independent** tide state (not used in the fit): level within 5 cm of the tape-measured value to pass, within 2 cm to meet the stretch goal.

**Datum caveat (important for how results are read).** The datum tie to MLLW is derived from NOAA 8531942 predicted extremes, not from a survey. Once tied, agreement with NOAA hi/lo is partly circular; the tape measurement is the independent check. 8531942 is also a subordinate station, so its own predictions are approximate in time and height; judge hi/lo timing and height against that, and prefer calm, high-pressure days.

### 7.4 Shakedown acceptance (14 days)

| Check | Pass |
|---|---|
| Delivery | At least 95% overall, and no unexplained 24 h below 90% |
| Level vs NOAA on calm days (centred smoothing) | Hi/lo times within +/-15 min; heights within +/-5 cm |
| Level vs tape on at least two further dates and tide states | Within 5 cm |
| Noise in service | Median `pitch_sd` consistent with bench; `high_sd` flag rate under 5% of cycles |
| Health | No `sensor_error`, no unexplained reboot, no `brownout_reset`; `out_of_range` flags only when expected |
| Alerts | At least one forced email test received; no spurious open alerts |
| Stability | Re-take tape check at day 14: no creep in `roll_mean` or in the offset |

The first automatic monthly refit (1st of the month, 03:00 local) must be observed once: it should log a fit, apply it or hold it as `proposed`, and not move the level by more than the bounds without an alert.

---

## 8. Solar-sufficiency measurement protocol (PRD FR6, D12)

**Question being answered:** does the 1 W vertical south-face panel keep the node energy-neutral through a New Jersey winter, and would 0.5 W?

**Window:** 1 December to 28 February (90 local days). Start logging as soon as the node is installed (autumn data is a useful baseline and tests the pipeline); the verdict uses the winter window only.

### 8.1 What to log

**Already in the v1 payload and the energy module (per 5-min cycle):** `vbat`, `vpanel`, `ipanel`, `chg` bits (CHRG, DONE, cold inhibit, CE override), die `temp`, `awake_ms_prev`, `flags`, `seq`, `boot_count`. Server computes `energy_daily` (harvest mAh/mWh, consumption estimate, net, coverage, reached full, cold-inhibit hours, resting voltage, minimum temperature).

**Additional records (small, mostly manual, recommended):**
- The B4 measured sleep/awake constants and the capacity actually fitted (26650, about 3300 mAh rated; Q7 resolved), recorded in the dated config.
- Site shading survey and a **reference reading**: panel short-circuit current and open-circuit voltage by multimeter at noon on a clear day, monthly, with the panel unshaded, plus the same on an unshaded vertical south surface elsewhere (for example, a house wall). This separates "low sun" from "local shading".
- Optional, and not currently in the architecture: Tempest solar radiation / illuminance to weight clear versus overcast days. **[unverified]** that the REST observation exposes it as used by `tempest.py`.
- A human event log: battery swaps, enclosure opened, panel cleaned, bird fouling, snow or ice cover, anything that interrupts or biases the data.
- Raw data is never deleted (PRD); keep the daily CSVs.

### 8.2 Computing margin

For each local day *d* with `coverage_pct` of at least 80%:

| Quantity | Formula |
|---|---|
| Harvest H_d | Integrated `ipanel` (mAh), charger-accepted (B10 confirms this equals cell charge within 10%) |
| Consumption C_d | Measured constants from B4 (not the 125 mAs / 50 uA placeholders) times the logged awake time |
| Net N_d | H_d - C_d |
| Energy ratio R_14 | Sum(H)/Sum(C) over a rolling 14-day window (matches the architecture verdict: at least 2 surplus, 1-2 marginal, under 1 deficit) |
| Worst-week net W_7 | Minimum over all 7-day windows of Sum(N) |
| Replay SoC | Start at 100%; each day add N_d, clamp to [0, capacity]; re-anchor to 100% on every DONE day. Report the minimum and its date |
| Dark autonomy | 0.8 x capacity / mean C_d. Must be at least 14 days (PRD) |
| Cold-inhibit exposure | Longest run of consecutive days with at least 12 h inhibited; times mean C_d, as a share of usable capacity |
| Derate factor | H_d (mWh) / (1000 x P_w x PSH_month x 0.5) using the PVGIS vertical-south PSH table (Dec 3.45, Jan 3.88, Feb 4.14 mean; 2.75-2.98 worst year). About 1 is as modelled; below about 0.3 means heavy shading or a fault |

**Days that reached full are a lower bound on harvest** (the charger stopped accepting). They show the panel is large enough that day, but they understate what a smaller panel would receive. Exclude them from the derate factor and from the 0.5 W worst-case analysis; keep them in the 1 W ratio.

**Reduce uncertainty in the constant that dominates:** a 2x error in `i_sleep_ua` moves C_d by about 1-2 mAh/day. Cross-check in the field: on a dark, cold, panel-covered week on the bench the battery should lose about C_d x 7 (LiFePO4's flat voltage makes voltage a poor gauge, so use B4's coulomb measurement rather than voltage).

### 8.3 Pass/fail: 1 W panel (measured)

| Outcome | Criteria (all must hold for PASS) |
|---|---|
| **PASS** | (1) zero `brownout_reset`, zero `critical_batt` or `sensor_skipped` cycles, and no reboot not explained by human action in the window; (2) worst rolling R_14 at least 2.0; (3) replay minimum SoC at least 50%; (4) at least one DONE (reached full) in every 14-day window; (5) no `LOW_BATTERY` or `ENERGY_DEFICIT` alert opened (an `ENERGY_NEGATIVE_STREAK` early warning does not by itself fail PASS; record it); (6) at least 80 of 90 days at 80% or better coverage |
| **MARGINAL** | No energy-caused outage, but any of: worst R_14 in [1.0, 2.0); a 14-day window with no DONE; minimum SoC 20-50%; `LOW_BATTERY` opened and self-cleared. Interpretation: it works, with the winter-worst case thin; size up or fix the cause |
| **FAIL** | Any energy-caused outage (brownout, critical state, node stops reporting for lack of energy); or worst R_14 below 1.0; or minimum SoC below 20% |
| **INCONCLUSIVE** | Fewer than 7 qualifying days in the window, or the energy telemetry itself failed its B10 check. State why; do not report a verdict |

A FAIL backed by telemetry is a valid result (PRD section 7). The report must say *why*: shading (low derate factor), cold inhibit (inhibit hours), or load (consumption above model).

### 8.4 Pass/fail: 0.5 W panel (inferred)

The 0.5 W case is **inferred from the 1 W log, not measured**: H_d x 0.5 on non-full days; harvest below the charger's start-up threshold counted as zero.

| Outcome | Criteria |
|---|---|
| **PASS (inferred)** | Worst-14-day inferred ratio at least 1.5 (that is, R_1W of at least 3.0 on those days), replay minimum SoC at least 50% using the pessimistic rule below, and B11 shows the charger still starts and accepts current at the lowest halved panel current seen in the winter |
| **MARGINAL** | Inferred ratio 1.0-1.5, or minimum SoC 20-50% |
| **FAIL** | Inferred ratio below 1.0, or minimum SoC below 20%, or B11 shows no charging at the halved current |

**Pessimistic replay rule:** on days that reached full, count the inferred 0.5 W harvest as 0.5 x (accepted charge), which understates it. If the pessimistic replay passes, the pass is solid. If it fails but the non-full-day test passes, report INCONCLUSIVE, not FAIL.

**Limits of the inference (state them in the report):** it scales linearly. Low-light behavior is not linear (an amorphous panel's start-up voltage under overcast may be below the charger's minimum, and a different 0.5 W panel could behave differently); the higher 1.5 bar and the B11 check are there to cover that. If the answer matters (for example, to order a smaller panel for a second ramp), measure it: cover the panel or swap in a 0.5 W unit for a month and re-run.

---

## 9. Risk-based priority order

| # | Item | Why first | Gate it unlocks |
|---|---|---|---|
| 1 | **B1** S1 spike (MeshCore sender plus deep sleep) | If it fails the whole design is wrong, and it costs a day | Everything |
| 2 | **B9** cold charge inhibit; **B10** telemetry/harvest accounting | Can damage the cell; and the headline measurement is meaningless if `ipanel` is not what the model assumes | Cell goes outdoors; winter test is valid |
| 3 | **B2, B3, B4** sleep, awake, 24 h energy | The 25 mAh/day budget and every solar number rest on these | Constants in config |
| 4 | **RF-3, RF-4, RF-5** fade margin, range, repeater | No link, no data; checked before bonding | Install may proceed |
| 5 | **FW-U1 to U3, SV-D, SV-A** codec and no-demo/stale behavior | Cheap, deterministic, and the explicit non-negotiable | Server goes live |
| 6 | **B8** brownout, **B5-B7** noise, scale, drift | Prevents silent bad data and boot loops; sensor effects are small vs the +/-5 cm budget | Firmware freeze |
| 7 | **SV-C, SV-N, SV-E, alerts** | Correctness of calibration and residual | Calibration at install |
| 8 | **Install acceptance (section 7)** and **Soak A/B** | Where accuracy is actually won or lost | Shakedown pass |
| 9 | **Solar protocol (section 8)** | Long-running; run in parallel from install, verdict in March | PRD metric 1 |
| 10 | Everything else (enclosure thermal cycling, extras) | Lower likelihood or consequence | |

**Phase gates (mapped to PRD section 9):**
- Phase 1 exit: B1-B13 pass; FW-U and SV-D/SV-A pass.
- Phase 2 exit: RF-3 to RF-6 pass at final positions.
- Phase 3 exit: section 7.3 calibration acceptance and section 7.4 shakedown acceptance.
- Phase 4 exit: section 8 verdict recorded (PASS, MARGINAL, FAIL or INCONCLUSIVE with reasons) and the runbook used once.

---

## 10. Bench checklist

Copy into `docs/bench/` per run. Record date, firmware commit, board ID, cell ID, panel ID.

**Safety and setup**
- [ ] USB-with-LiFePO4 warning label on the enclosure; cell disconnected for flashing
- [ ] Fused cell (1 A, within 2 cm of +); current-limited supply used for charge tests
- [ ] Panel Voc measured in sun, below the charger input rating with margin

**Firmware (host)**
- [ ] FW-U1 to FW-U10 pass; golden vectors identical in C++ and Python
- [ ] Even-count median rule fixed and documented

**Hardware**
- [ ] B1 S1 spike: frame decodes, node sleeps, no listening
- [ ] B2 sleep current: ___ uA (target 50, max 100)
- [ ] B3 awake charge: ___ mAs/cycle (target 125, max 200); TX power ___ dBm; SF/BW ___
- [ ] B4 24 h run: ___ mAh/day (max 25); constants written to `config.toml`
- [ ] B5 noise: SD of median ___ degree (max 0.01) at 0, 3 and 7 degree
- [ ] B6 scale: max error ___ degree (max 0.02); sign and axis confirmed
- [ ] B7 drift: ___ degree over -10 to +40 C after correction (max 0.05); `k_T` ___
- [ ] B8 brownout: first reset at ___ V; `critical` threshold margin at least 0.1 V; recovery clean
- [ ] B9 cold inhibit: zero charge below 0 C with both layers; firmware alone stops at +1 C die (die-to-cell offset ___ C); hardware alone stops at ___ C (expect about -3) and resumes at ___ C (expect about +2.4); no chatter
- [ ] B10 `ipanel` within +/-5% or 1 mA; `ipanel` minus load within 10% of cell-accepted charge
- [ ] B13 safety timer: latch at 6 h without pulse, none with pulse; /CE fail-safe holds charging off with MCU unpowered
- [ ] B11 charger starts at 2/5/10 mA; min input ___ V
- [ ] B12 enclosure leak test and humidity card clean

**RF**
- [ ] RF-1 frequency chosen from the noise survey; SF/BW chosen
- [ ] RF-3 delivery with 10 dB pad: ___ % (min 95)
- [ ] RF-4 48 h range test: ___ % overall, worst 6 h ___ % (min 95 / 85)
- [ ] RF-5 repeater hop: ___ %; duplicates de-duplicated
- [ ] RF-6 repeater power-saving on vs off: ___
- [ ] RF-7 outage visibility: `REPEATER_SILENT` distinct from `NODE_SILENT` and `GATEWAY_DOWN`; runbook line

**Server and soak**
- [ ] SV-A4 property test passes; fresh-DB 503 test passes
- [ ] SV-N8 interpolation error recorded
- [ ] Soak A 72 h clean; fault injection items 1-8 run
- [ ] DST test (SV-E4) passes before 2026-11-01

**Install**
- [ ] Reference mark made and photographed
- [ ] Two tide-state calibration plus mid-tide and an independent fourth check within 5 cm
- [ ] Shakedown acceptance table completed
- [ ] Solar log running; event log started

---

## 11. Gaps and flags for Nick

Open items are now tracked in one place: `docs/DEV-PLAN.md` section 7. Status of the v0.1 flags:

1. **Alert rule mismatch:** resolved (Nick, 2026-10-10). `ENERGY_DEFICIT` on the 14-day verdict is the official answer; 7 consecutive negative days is the `ENERGY_NEGATIVE_STREAK` early warning. Both are tested (section 4.5).
2. **BOM missing parts:** resolved. BOM v0.2 has the INA3221 and Nick's repeater (as an already-owned/planned item).
3. **Charger not settled:** resolved. BQ25185 on Adafruit 6091 (TH pad broken out). It is linear with a power path; B10's harvest check is restated accordingly.
4. **Zero-hop vs repeater:** resolved. Flood is the ADR-003 default; the margin criterion is restated per hop for the private SF/BW (section 5).
5. **Repeater with no telemetry:** resolved for liveness (ARCHITECTURE 5.5, `REPEATER_SILENT`, RF-7, SV-A11). Its power budget is out of scope (Nick). Whether the advert/status path works in `meshcore_py` is open (DEV-PLAN 7, item 11).
6. **Flexible amorphous panel (Q6):** still open: measure Voc, expect a lower derate factor than modelled (DEV-PLAN 7, item 4).
7. **Cell size (Q7):** resolved: 26650, about 3300 mAh rated; physical fit still to verify.
8. **Spec gaps:** matched-extremes minimum (SV-C7) and even-count median rule (FW-U4) are still open (DEV-PLAN 7, items 6-7). The harvest definition (B10) is settled for the BQ25185; whether to add a cell-current field to the payload is open (DEV-PLAN 7, item 8).
9. **WisBlock prototype option** (BOM): kept as a prototype path only; it would need an nRF52 port of the firmware (unverified). If used, B7 temperature drift becomes mandatory and likely large; the rest of the plan carries over.
10. **Not verified by this plan:** NOAA's own accuracy at 8531942 (subordinate station) bounds how well hi/lo comparison can ever look. Tempest station 183092's exposure relative to the ramp is unstated.

---

## 12. Revision history

| Version | Date | Author | Changes |
|---|---|---|---|
| 0.1 | 2026-10-10 | qa-strategy agent | Initial draft from PRD v0.2, ARCHITECTURE v0.1 plus answers log, and BOM |
| 0.2 | 2026-10-10 | software-architecture agent (doc reconciliation) | Aligned with Nick's decisions: BQ25185 /CE polarity and cold layering (FW-U7, B9), safety-timer pulse (FW-U10, B13), power-path harvest check (B10), flood/per-hop RF criteria, repeater health (RF-7, SV-A11), new alert cases; section 11 statuses. |
