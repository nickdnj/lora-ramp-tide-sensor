# Development Plan: LoRa Ramp Tide Sensor

**Version:** 0.2 (draft)
**Last Updated:** 2026-10-10
**Author:** Nick DeMarco, with AI assistance (dev-planning agent)
**Status:** Draft, for Nick's review. **No GitHub repo or issues exist yet.** Section 6 holds the issue list in a form that can be created once Nick approves a repo.
**Inputs:** `docs/PRD.md` v0.3, `docs/ARCHITECTURE.md` v0.2 plus Nick's answers log, `docs/BATTERY.md` v0.2, `docs/BOM.md` v0.2, `workspace/research/SPEC.md`
**Not duplicated here:** battery chemistry, cell, and charger research lives in `docs/BATTERY.md` (v0.2, decisions recorded). Stories in the power system epic *consume* its output; they do not redo it.

**Changes in v0.2 (2026-10-10):** applied Nick's decisions. E0.2 and E2.1 charger/cell items resolved (BQ25185, 26650). E0.3 doc updates done (repeater is Nick's existing PVC-tube design). E1.6, E3.3 and E2.2 corrected for BQ25185 /CE polarity (HIGH = disabled, pull-up), 130 kΩ NTC shift, firmware 0 °C rule and the 4 h CE pulse. E4.3 and E4.4 restated for flood routing, matched private settings and per-hop margin; the repeater's own power budget dropped from scope. New story E5.9 (repeater health). E8.3: energy alert decided (14-day verdict official, 7-day early warning) and `REPEATER_SILENT` added. Section 7 is now the single list of open items, including the TEST-PLAN spec gaps.

---

## 1. Shape of the project

One node, one gateway, one repeater, one Python service, one owner (Nick). Hobby pace: evenings and weekends, no sprints. Work is organized as **epics in phases**; stories inside a phase are ordered, and the phase exit is a testable gate. Milestones in the issue list map one-to-one to phases.

**Sizing.** Points use the dev-planning scale: 1 trivial, 2 small, 3 medium, 5 large, 8 should be split. Rough hobby conversion: **1 point is about one focused evening**. Total is about **175 points**, which is a rough estimate: Phase 1 numbers are the most solid, the winter phases are checkpoints that depend on the calendar rather than effort.

**Calendar pressure.** The pilot's headline question (PRD section 7, metric 1) is answered by December-February data. To have a December in the log, the node should be **installed and reporting by about the end of November**. The critical path is therefore parts, bench (S1 and power), node firmware, link test, install. The server only needs the *raw-capture slice* (stories 5.1-5.3) before install, because raw packets are stored first and everything else can be reprocessed from them later.

### Critical path

```
0.2 decisions -> 0.3 order parts -> 1.1 S1 spike -> 1.2/1.3/1.6 bench power
  -> 2.2 power path -> 3.x firmware -> 4.3 repeater -> 4.4 link test -> 10.2 install
parallel: 5.1-5.3 raw capture on the mini PC (must be live at install)
```

---

## 2. Phases and exit gates

| Phase | PRD phase | Epics | Exit gate (testable) |
|---|---|---|---|
| **P0 Site and decisions** | 0 | E0 | L, hinge, stringer, shading recorded; radio settings, cell size, and parts list decided; Nick has approved the order |
| **P1 Bench** | 1 | E1, E2 | S1 passes; sleep and awake current measured and inside the 25 mAh/day design budget; LiFePO4 brownout point known; tilt noise at or below 0.01 deg; charger cold cutoff observed |
| **P2 Build** | 1-2 | E3, E4 (4.1-4.3), E5, E6, E7, E8, E9 | Firmware soaks 72 h on the bench; service ingests from the real gateway and serves the API; alerts replay green; Tempest optional path passes with it on and off |
| **P3 Link test and install** | 2-3 | E4 (4.4), E10 | 48 h link test through the repeater meets PRD >=95% and >= 10 dB margin over the chosen SF floor on each hop before anything is bonded; node installed and calibrated |
| **P4 Shakedown** | 3 | E10 (10.4), E13 | 2-week shakedown meets PRD section 7 metrics 2 and 3; runbook exists |
| **P5 Winter test and analysis** | 4 | E11 | December-February report with a yes/no solar verdict backed by telemetry |
| **P6 SignBoard panel (later, separate repo)** | 3-4 | E12 | Panel shows level, trend, residual, and the stale state; tracked in the SignBoard repo |

---

## 3. Epics

| Epic | Name | Outcome | Phase |
|---|---|---|---|
| E0 | Site and decisions | Facts and choices that block ordering and building | P0 |
| E1 | Bench and spikes | Measured numbers replace the architecture's estimates | P1 |
| E2 | Power system | A built, tested power path, using BATTERY.md decisions | P1 |
| E3 | Node firmware | Wake, measure, send one group datagram, deep sleep | P2 |
| E4 | Gateway, repeater, and link | Frames get from the ramp to the mini PC reliably | P2-P3 |
| E5 | `tidesvc` core | Ingest, store raw, convert, serve the API, deploy | P2 |
| E6 | NOAA and calibration | Predictions, residual, install fit, bounded monthly refit | P2 |
| E7 | Energy log | Daily harvest, state of charge, verdict | P2 |
| E8 | Alerts by email | Surge and health alerts to Nick | P2 |
| E9 | Tempest input (optional) | Pressure and wind context, never in the required path | P2 |
| E10 | Install and calibration | Node on the ramp, calibrated, shaken down | P3-P4 |
| E11 | Solar-sufficiency analysis | The headline answer, with data | P5 |
| E12 | SignBoard tide panel | Residents see the level (separate repo) | P6 |
| E13 | Operations and ownership | Runbook, backups, routine tasks Nick can do without re-learning | P4 |

---

## 4. Dependency map (epic level)

```
E0 -> E1 -> E2 -> E3 -> E4.4 -> E10 -> E11
E0 -> E4.1/4.2/4.3 (radio settings, repeater) -> E4.4
E3.4 (golden vectors) -> E5.2 (codec)
E4.1 (gateway) -> E5.3 (radio) 
E5 -> E6, E7, E8 (all read the readings table)
E5 + E6 + E7 -> E8 (alert rules need level, residual, energy)
E5 -> E9 (optional, additive)
E5.6 API stable + E10.4 shakedown -> E12
E1.2 / E1.3 constants -> E3.1 thresholds, E7.1 config, E11.1 expectation
BATTERY.md (external) -> E0.2, E1.3, E1.6, E2.1
```

---

## 5. Stories (ordered by phase, then by epic)

Each story is written as an issue: **Title**, **Labels**, **Size**, **Depends on**, **Body** with acceptance criteria. Section 6 turns this list into a creation checklist. Story IDs (`E.n`) are plan IDs; real issue numbers come later.

### P0 - Site and decisions

#### E0.1 Site visit: ramp geometry, stringer, and south-face shading
- **Labels:** `epic:E0-site`, `phase:P0`, `type:chore`, `area:hardware`
- **Size:** 2 · **Depends on:** none
- **Body:** Confirm the physical facts the model and the install depend on, using Meeco Sullivan drawings and a visit.
  - [ ] Ramp length L (assumed 7.62 m), hinge location, and float end details recorded
  - [ ] Stringer position at midspan and room for a no-drill, reversible mount confirmed
  - [ ] Orientation of the sensor axis marked and photographed
  - [ ] South-face shading assessed for a December noon sun (~26 deg elevation): piles, boats, structure; photo and a rough percent estimate
  - [ ] Free space under the ramp measured against the candidate enclosure and cell size
  - [ ] Physical spot for the repeater and the gateway antenna noted (feeds E4)

#### E0.2 Resolve blocking choices before ordering
- **Labels:** `epic:E0-site`, `phase:P0`, `type:chore`, `area:docs`
- **Size:** 2 · **Depends on:** `docs/BATTERY.md` complete (input), E0.1
- **Body:** Close the items that block the order. Take battery, cell, and charger conclusions from BATTERY.md as given.
  - [x] Q7 closed: 26650 LiFePO4 (Nick, 2026-10-10; fits the Fibox PCB 65T by outside dimensions)
  - [ ] 26650 physically test-fitted in the chosen enclosure, against the space measured in E0.1
  - [x] Charger part chosen per BATTERY.md: TI BQ25185 on Adafruit 6091 (architecture v0.2 and BOM v0.2 agree)
  - [ ] Panel open-circuit voltage measured on the 1 W flexible amorphous panel (or its datasheet value recorded) and checked against the BQ25185 input (3.6-18 V operating; BATTERY.md expects about 7.7 V for a 6 V panel)
  - [ ] SMA vs RP-SMA confirmed for the Heltec V3 and the antenna
  - [ ] US enclosure source with gland options chosen
  - [ ] Private radio settings requested from E4.2 (so both radios can be ordered and flashed the same way)

#### E0.3 Update BOM and architecture for the repeater
- **Labels:** `epic:E0-site`, `phase:P0`, `type:chore`, `area:docs`
- **Size:** 1 · **Depends on:** E0.2
- **Body:** Nick's answer to Q1: a repeater bridges the ramp to the gateway. It is **Nick's existing designed solar PVC-tube repeater** (RAK4631 + RAK19007).
  - [x] BOM gains the repeater hardware as an already-owned/planned item (BOM v0.2)
  - [x] ARCHITECTURE ADR-003 updated from "zero-hop default" to "flood via the repeater"; de-dup on `(node_id, boot_count, seq)` covers direct plus relayed copies (ARCHITECTURE v0.2, 5.4)
  - [x] ARCHITECTURE section 5.3 fallback text updated; repeater health added (5.5); PRD Q1b marked resolved (PRD v0.3)
  - [ ] Repeater build status confirmed with Nick (as of 2026-09-29 its parts were listed but not bought)

#### E0.4 Order parts (needs Nick's approval to spend)
- **Labels:** `epic:E0-site`, `phase:P0`, `type:chore`, `area:hardware`
- **Size:** 1 · **Depends on:** E0.2, E0.3
- **Body:** Node, gateway Heltec V3, antenna, enclosure, cell, charger, B3435 NTC and 130 kΩ resistor, LM66100, INA3221 breakout, fuse, breather vent, panel, bonding and isolation hardware, current-measurement gear (PPK2/Otii/uCurrent). Repeater parts are Nick's own project, not part of this order.
  - [ ] Parts list agrees with the updated BOM
  - [ ] Nick has approved the spend
  - [ ] Order placed; delivery dates noted against the end-of-November install target

### P1 - Bench

#### E1.1 Spike S1: minimal MeshCore sender that never listens
- **Labels:** `epic:E1-bench`, `phase:P1`, `type:spike`, `area:firmware`, `risk:high`
- **Size:** 5 (time box: 2 days) · **Depends on:** E0.4
- **Body:** The architecture's central claim is unverified: a library `Mesh` subclass with no identity, no RX, and deep sleep straight after TX works on MeshCore v1.17.1. Prove or disprove it before building on it.
  - [ ] PlatformIO env builds with MeshCore pinned by git tag `companion-v1.17.1` (not by library version)
  - [ ] Sender transmits one `GRP_DATA` on a private channel with data type `0xFF54`, then enters deep sleep without ever enabling receive
  - [ ] A stock `companion_radio_usb` v1.17.1 gateway emits `CHANNEL_DATA_RECV` (`0x1B`) and the payload bytes match the sent bytes exactly (read via `meshcore_py`/`meshcore-cli`)
  - [ ] Channel secret and radio settings come from NVS or a provisioning step, not from source or git
  - [ ] 100 consecutive cycles with zero loss at bench distance
  - [ ] Behaviour through the repeater (flood) captured if the repeater is on hand; otherwise recorded as pending for E4.3
  - [ ] Findings and a go/no-go written to `docs/bench/S1.md`. **If no-go,** stop and bring the options to Nick; do not silently fall back to the stock sensor firmware, which costs ~20x the energy budget

#### E1.2 Measure sleep current and awake profile
- **Labels:** `epic:E1-bench`, `phase:P1`, `type:spike`, `area:hardware`
- **Size:** 3 · **Depends on:** E1.1, E2.2 prototype power path (can use a bench supply at 3.2 V first)
- **Body:** Replace the estimates in architecture section 4.4 with measurements, including real leakage from the charger, INA3221, and battery divider.
  - [ ] Deep-sleep current measured with the full board stack attached (target 30-100 uA; the SPEC's ~20 uA is flagged as optimistic)
  - [ ] Per-cycle charge (mAs) measured for wake, sample, radio init, and TX at 22 dBm and 14 dBm
  - [ ] Result computed as mAh/day at 5 min and compared with the 25 mAh/day design budget; PRD's 17 mAh/day also restated
  - [ ] `i_sleep_ua` and `awake_mas_per_cycle` recorded in `docs/bench/` and in `config.example.toml`
  - [ ] RC-oscillator wake drift measured over at least 24 h (arch assumes 1-5%)

#### E1.3 LiFePO4 brownout sweep on the Heltec V3 battery input
- **Labels:** `epic:E1-bench`, `phase:P1`, `type:spike`, `area:hardware`
- **Size:** 2 · **Depends on:** E1.1, BATTERY.md (cell choice)
- **Body:** Find where the node actually dies, so the low and critical thresholds are measured.
  - [ ] Bench supply swept 3.6 V to 2.9 V while the firmware cycles; the brownout and reset-reason voltage recorded
  - [ ] Low (3.15 V) and critical (3.05 V) placeholders replaced by measured values with margin
  - [ ] Swept through the real feed path (BQ25185 BAT → SYS → LM66100 → JP1), per BATTERY.md T4
  - [ ] **Safety check recorded:** USB must not be connected while the LiFePO4 cell is attached (Heltec onboard charger is Li-ion 4.2 V) until BATTERY.md T6 shows the LM66100 blocks it; the procedure uses a bench supply or a disconnect jumper
  - [ ] Result feeds E3.1 thresholds

#### E1.4 SCL3300 bring-up and tilt-rig noise test
- **Labels:** `epic:E1-bench`, `phase:P1`, `type:spike`, `area:firmware`
- **Size:** 5 · **Depends on:** E0.4
- **Body:** SPI driver with frame CRC and status checking, burst sampling, and a tilt rig (a hinged board and a micrometer or a known shim).
  - [ ] Driver reads angle output with CRC check; bad frame sets `sensor_error`
  - [ ] Mode and filter choice recorded with datasheet figures (arch figures are from product pages, unverified)
  - [ ] Settling time and active current recorded
  - [ ] Per-cycle median pitch noise at fixed angles is at or below 0.01 deg (PRD NFR)
  - [ ] A 1 cm-equivalent (0.075 deg) shim step is visible in the data
  - [ ] Orientation convention (pitch vs roll axis) fixed in code and documented

#### E1.5 Temperature characterisation (k_T)
- **Labels:** `epic:E1-bench`, `phase:P1`, `type:spike`, `area:hardware`
- **Size:** 3 · **Depends on:** E1.4
- **Body:** Freezer to about +40 C sweep with the sensor at a fixed angle.
  - [ ] Pitch vs sensor temperature curve captured
  - [ ] `k_T` (deg per C) fitted, or recorded as negligible with the residual drift bound in cm of apparent level
  - [ ] Value written into the default calibration; if the part is worse than the prediction, the ADXL355 swap question goes to Nick (driver interface was kept swappable)

#### E1.6 Charger, panel, and cold-cutoff verification
- **Labels:** `epic:E1-bench`, `phase:P1`, `type:spike`, `area:hardware`, `risk:high`
- **Size:** 3 · **Depends on:** E0.4, BATTERY.md
- **Body:** Confirm the charger actually does what the winter test relies on: BQ25185 on Adafruit 6091, 3.65 V, 250 mA, B3435 NTC with 130 kΩ in parallel (BATTERY.md tests T1, T2, T3, T7, T9).
  - [ ] Panel plus charger work together: charger input limit versus measured panel Voc and short-circuit current (flexible amorphous panel)
  - [ ] Hardware cold window measured with the 130 kΩ in place (expected about -3 °C stop / +2.4 °C resume; T2); SYS stays up from the panel during the inhibit
  - [ ] STAT1/STAT2 readable as GPIOs (no more than 3.3 V at the pin); /CE: **HIGH disables charging**; the 1 MΩ pull-up keeps charging off with the MCU unpowered; firmware drives /CE LOW to enable, held through deep sleep (T3)
  - [ ] Safety timer: without the firmware CE pulse charging latches off at 6 h; with a pulse about every 4 h it does not (T7)
  - [ ] Whether the NTC can be placed on the cell (not the board) in the chosen enclosure confirmed

#### E1.7 Phase 1 exit review
- **Labels:** `epic:E1-bench`, `phase:P1`, `type:chore`, `area:docs`
- **Size:** 1 · **Depends on:** E1.1-E1.6
- **Body:**
  - [ ] `docs/bench/` has one page per spike with raw numbers
  - [ ] Energy constants updated; if nominal load exceeds the 25 mAh/day budget, the radio-setting or panel question goes to Nick before more build
  - [ ] Go/no-go recorded for: 1 W panel, 26650 vs 18650, SCL3300

### P1 - Power system (E2)

#### E2.1 Power design intake from BATTERY.md
- **Labels:** `epic:E2-power`, `phase:P1`, `type:chore`, `area:docs`
- **Size:** 1 · **Depends on:** BATTERY.md complete
- **Body:** Copy decisions, do not re-research. Resolve any conflict between BATTERY.md and ARCHITECTURE section 4.2.
  - [x] Cell, protection, charger, and NTC placement referenced from BATTERY.md in the BOM and architecture (BOM v0.2, ARCHITECTURE v0.2)
  - [x] Disagreements with ARCHITECTURE resolved in writing: charger part (BQ25185, CN3058E dropped) and /CE polarity (ARCHITECTURE v0.2, 4.2-4.3)

#### E2.2 Assemble and test the power path
- **Labels:** `epic:E2-power`, `phase:P1`, `type:story`, `area:hardware`
- **Size:** 5 · **Depends on:** E2.1, E1.3, E1.6
- **Body:** Panel input, charger, INA3221 (ch1 panel, ch2 cell side), fuse, cell, NTC ∥ 130 kΩ, /CE GPIO with 1 MΩ pull-up, SYS → LM66100 → Heltec JP1, battery disconnect jumper (BATTERY.md 3.4).
  - [ ] Wiring matches BATTERY.md 3.4 and the architecture block diagram; INA3221 reads both channels
  - [ ] Charge cycle observed end to end: STAT charging then done, with logged vbat, vpanel, ipanel
  - [ ] Battery disconnect or jumper present for programming; "no USB with cell attached" label on the unit
  - [ ] Sleep current with this path matches E1.2

#### E2.3 Enclosure fit, sealing, and thermal sanity
- **Labels:** `epic:E2-power`, `phase:P1`, `type:story`, `area:hardware`
- **Size:** 2 · **Depends on:** E2.2, E0.4
- **Body:**
  - [ ] Boards, cell, and wiring fit with drip loops and strain relief
  - [ ] Conformal coat applied to boards; desiccant placed; glands sealed
  - [ ] NTC on the cell, not the board
  - [ ] Pressure/leak test (water spray or submersion of the closed empty box)

### P2 - Node firmware (E3)

#### E3.1 Cycle state machine and battery-state intervals
- **Labels:** `epic:E3-firmware`, `phase:P2`, `type:story`, `area:firmware`
- **Size:** 5 · **Depends on:** E1.1, E1.3
- **Body:** Wake, power read, sample or skip, build, transmit, sleep. Interval by battery state: normal 5 min, low 15 min, critical 60 min with a health-only payload.
  - [ ] Thresholds are the measured values from E1.3
  - [ ] RTC memory carries `seq`, `boot_count`; `reboot` flag set on cold boot; reset reason mapped to `brownout_reset` and `wdt_reset`
  - [ ] A watchdog ensures the node always returns to sleep (a hung radio must not drain the cell)
  - [ ] Native tests cover state selection and interval selection
  - [ ] Never enters receive mode (asserted in a test or by code review checklist)

#### E3.2 Burst sampling and statistics
- **Labels:** `epic:E3-firmware`, `phase:P2`, `type:story`, `area:firmware`
- **Size:** 3 · **Depends on:** E1.4
- **Body:** 300 samples at 100 Hz, median and standard deviation of pitch, mean roll, sensor temperature, error handling.
  - [ ] Median and SD in `stats.{h,cpp}`, covered by native tests with known vectors
  - [ ] Bad SPI frame or status marks `sensor_error`; short sample marks `short_sample`
  - [ ] Coarse out-of-range flag set at |pitch| > 15 deg or |roll| > 10 deg

#### E3.3 Power telemetry and charger control
- **Labels:** `epic:E3-firmware`, `phase:P2`, `type:story`, `area:firmware`
- **Size:** 5 · **Depends on:** E2.2, E1.6
- **Body:** FR6 on the node side.
  - [ ] INA3221 one-shot read of vbat, vpanel, ipanel, then power-down; Vext switched off in sleep
  - [ ] STAT1/STAT2 mapped into the `chg` byte per ARCHITECTURE 4.7 (CHRG, DONE, cold_charge_inhibit, CE override, latch fault, CE pulse)
  - [ ] Firmware owns the 0 °C rule: drives /CE **HIGH (disable)** below +1 C or when temperature is unknown, **LOW (enable)** above +2 C, holds state in between, and reports it (ARCHITECTURE 4.3)
  - [ ] Safety-timer pulse: after about 4 h of continuous charging (counted in RTC memory), /CE pulsed HIGH briefly then LOW
  - [ ] /CE state held through deep sleep (`gpio_hold_en`)
  - [ ] "No sun" and "too cold to charge" are distinguishable in the payload (PRD FR6)
  - [ ] `ina_error` flag set on read failure instead of reporting zeros

#### E3.4 Payload v1 codec and shared golden vectors
- **Labels:** `epic:E3-firmware`, `phase:P2`, `type:story`, `area:firmware`
- **Size:** 3 · **Depends on:** none (spec in ARCHITECTURE 4.7)
- **Body:** 26-byte little-endian payload, CRC-16/CCITT-FALSE over bytes 0-23.
  - [ ] `uplink.{h,cpp}` encoder per the field table
  - [ ] `tests/fixtures/packets_v1.json` holds golden vectors incl. edge values (negative pitch, saturated SD, all flags)
  - [ ] PlatformIO native test passes on the vectors; the same file is consumed by E5.2

#### E3.5 Provisioning command and routing options
- **Labels:** `epic:E3-firmware`, `phase:P2`, `type:story`, `area:firmware`
- **Size:** 3 · **Depends on:** E1.1, E4.2
- **Body:** One-time USB serial `provision` command writing NVS.
  - [ ] Stores 16-byte channel secret, node id, TX power, frequency, bandwidth, SF, CR, routing (flood default; zero-hop for bench only), `tx_repeats`
  - [ ] Secret never appears in source, build artifacts, or logs
  - [ ] Settings can be read back (secret masked) to verify what a deployed node carries
  - [ ] Procedure documented for the runbook (changing settings needs USB because the node never listens)

#### E3.6 72-hour bench soak
- **Labels:** `epic:E3-firmware`, `phase:P2`, `type:story`, `area:firmware`
- **Size:** 3 · **Depends on:** E3.1-E3.5, E4.1, E5.3 (or `meshcore-cli` logging)
- **Body:** Node on a bench supply and the real gateway, sending every 5 min.
  - [ ] 72 h with no stuck cycle; sequence continuity from gateway log (loss measured, not assumed)
  - [ ] Measured daily consumption within 25 mAh/day budget
  - [ ] A deliberate brownout and a deliberate reboot show the right flags
  - [ ] Result recorded in `docs/bench/`

### P2 - Gateway, repeater, and link (E4)

#### E4.1 Gateway radio: flash, configure, and attach
- **Labels:** `epic:E4-link`, `phase:P2`, `type:story`, `area:gateway`
- **Size:** 2 · **Depends on:** E0.4, E4.2
- **Body:** Stock `Heltec_v3_companion_radio_usb` v1.17.1 on the second Heltec V3.
  - [ ] Flashed from the official flasher; version confirmed with `meshcore-cli`
  - [ ] Radio parameters set to the private settings; name `tide-gw`; channel slot 1 = private channel "tide" with the node's secret; public channel slot not used by our filter
  - [ ] udev rule creates `/dev/meshcore-gw` matched on the board's serial
  - [ ] Antenna placement chosen (E0.1) and connected; USB plugged into the mini PC

#### E4.2 Choose the private radio settings
- **Labels:** `epic:E4-link`, `phase:P0`, `type:spike`, `area:gateway`
- **Size:** 2 · **Depends on:** none
- **Body:** Nick chose a private frequency and encrypted private channel (Q2). Frequency, bandwidth, and SF are still to choose within 902-928 MHz.
  - [ ] A scan with a spare radio (or `meshcore-cli`/RadioLib RSSI sweep) shows which sub-bands are quiet at the marina and at the mini PC
  - [ ] Frequency, BW, SF, CR chosen and written to ARCHITECTURE ADR-003 update; starting point is SF7-SF9 and BW62.5-125 with the ~10 dB margin rule
  - [ ] Airtime and mAh/day recomputed for the chosen settings (arch: SF10/BW125 adds ~4.4 mAh/day)
  - [ ] Same settings applied to node, repeater, and gateway from one config note (the node's settings must match the repeater's)
  - [ ] Nick confirms that moving his repeater to the private frequency is acceptable (it then no longer serves the public US mesh)
  - [ ] Per-hop acceptance threshold written down for the chosen SF: median SNR at least 10 dB above that SF's floor (ARCHITECTURE 5.4)

#### E4.3 Repeater: configure and verify the bridge
- **Labels:** `epic:E4-link`, `phase:P2`, `type:story`, `area:gateway`
- **Size:** 3 · **Depends on:** E4.1, E4.2, E1.1, E0.3
- **Body:** Node to Nick's solar PVC-tube repeater to gateway, with the node sending in flood mode. The repeater's own power budget is outside this project (Nick, 2026-10-10); only its liveness is in scope (E5.9).
  - [ ] Repeater firmware (`repeater-v1.17.1` or matching) set to the private settings; periodic advert interval set so `tidesvc` can see it is alive
  - [ ] Frame sent flood from the node reaches the gateway with `path_len >= 1` when the gateway cannot hear the node directly
  - [ ] No public-mesh traffic is forwarded because of the private frequency; nothing hears the channel without the secret
  - [ ] `tidesvc` de-dup behaves if the gateway hears both the direct and relayed copy
  - [ ] Repeater `powersaving` mode tested; delivery rate with and without it recorded (the choice is Nick's, for his repeater's budget)
  - [ ] Repeater placement documented in the runbook draft

#### E4.4 48-hour link test from the final node position
- **Labels:** `epic:E4-link`, `phase:P3`, `type:story`, `area:gateway`, `gate`
- **Size:** 3 · **Depends on:** E3.6, E4.3, E5.3, E0.1
- **Body:** Before anything is bonded to the ramp (PRD).
  - [ ] Node in its planned spot and antenna position (temporary hold, no adhesive), with the repeater and gateway in their planned places
  - [ ] 48 h or more: end-to-end delivery >= 95%, and each hop has >= 10 dB margin over the chosen SF's floor (gateway SNR for repeater → gateway; 10 dB attenuator test, TEST-PLAN RF-3, for node → repeater)
  - [ ] Repeated or extended across a high and a low tide (geometry changes with float height)
  - [ ] If short: the ladder is tried in order, each with a recorded result: lower TX power not helpful, higher SF on all three radios, antenna reposition, `tx_repeats = 1`
  - [ ] Result and settings written up; **install (E10.2) is blocked until this passes**

### P2 - tidesvc core (E5)

#### E5.1 Project skeleton, schema, and deploy scaffolding
- **Labels:** `epic:E5-service`, `phase:P2`, `type:story`, `area:service`
- **Size:** 3 · **Depends on:** none
- **Body:**
  - [ ] Python 3.12 project at `src/tidesvc/` with pytest, ruff, and config loader (`config.toml`, secrets from `.env`)
  - [ ] SQLite WAL schema with migrations: `packets_raw`, `readings`, `derived`, `calibrations`, `cal_observations`, plus the other tables from ARCHITECTURE 6.9; `meta(schema_version)`
  - [ ] Single writer behind an asyncio queue, read-only connections for the API
  - [ ] Dockerfile and compose file that builds and starts with the radio absent
  - [ ] Timestamps UTC in storage; local-day helper for America/New_York

#### E5.2 Codec: decode v1, CRC, de-dup, sequence gaps
- **Labels:** `epic:E5-service`, `phase:P2`, `type:story`, `area:service`
- **Size:** 3 · **Depends on:** E3.4, E5.1
- **Body:**
  - [ ] Decodes every golden vector from `packets_v1.json` identically to the C++ encoder
  - [ ] Bad CRC, wrong `ver`, or wrong length stored in `packets_raw` with `parse_status`, never dropped
  - [ ] De-dup on `(node_id, boot_count, seq)`; duplicates counted, not stored twice
  - [ ] Sequence gaps (and wraps and reboots) counted so delivery % is computable per day

#### E5.3 Radio module: meshcore_py ingest and gateway health
- **Labels:** `epic:E5-service`, `phase:P2`, `type:story`, `area:service`
- **Size:** 5 · **Depends on:** E4.1, E5.1, E5.2
- **Body:** The raw-capture slice that must be live before install.
  - [ ] Connects with `create_serial`, verifies channel slot 1 and sets it from `.env` secret if missing, subscribes to `CHANNEL_DATA_RECV`
  - [ ] Every frame inserted raw first, then filtered on channel and data type, decoded, and handed to derive
  - [ ] 60 s heartbeat; link failure sets gateway `error`, reconnects with 1 s to 60 s backoff, writes `gateway_events`; the API keeps serving
  - [ ] Host stamps arrival time; backlog drain detected and back-dated from `seq` with `time_source = "backfilled"`
  - [ ] Gateway `ok` with no frames is reported differently from gateway `error` (node silent vs mini PC problem)

#### E5.9 Repeater health
- **Labels:** `epic:E5-service`, `phase:P2`, `type:story`, `area:service`
- **Size:** 3 · **Depends on:** E5.3, E4.3
- **Body:** ARCHITECTURE 5.5. A dead repeater must be distinguishable from a dead node.
  - [ ] Repeater evidence recorded: relayed node frames (`path_len >= 1`), the repeater's periodic advert (matched on its public-key prefix), and optionally a status request (off by default)
  - [ ] The unverified `meshcore_py` advert event and status-request calls confirmed, or the feature trimmed to relayed frames only, with the result written down
  - [ ] Repeater status `ok|silent|unknown` in `/api/v1/status` and `/api/v1/node/health`; `repeater_events` table
  - [ ] Tests with the fake companion: relayed frames, advert only, silence; status changes as specified
  - [ ] No energy verdict for the repeater (its power budget is out of scope)

#### E5.4 Fake companion and ingest integration tests
- **Labels:** `epic:E5-service`, `phase:P2`, `type:story`, `area:service`
- **Size:** 3 · **Depends on:** E5.3
- **Body:**
  - [ ] pty-based fake companion speaking `0x83` and `0x1B` frames
  - [ ] Tests: normal flow, backlog drain with backfilled timestamps, unplug and replug, corrupt frame, wrong channel, wrong data type
  - [ ] Runs in CI-less local `pytest` in under a minute

#### E5.5 Derive: level conversion, validity, and smoothing
- **Labels:** `epic:E5-service`, `phase:P2`, `type:story`, `area:service`
- **Size:** 5 · **Depends on:** E5.2
- **Body:** `level = h0 + L_eff * sin(radians(pitch_corr - theta0))`, with `k_T` correction.
  - [ ] Validity rules: `sensor_error`, `out_of_range` (node flag or outside calibrated envelope +/- 0.5 deg), `pitch_sd > 0.25 deg`, backfilled time for the live view
  - [ ] Trailing 30 min median (needs >= 4 valid points, otherwise null with `insufficient_points`) for live; centred median for analysis and calibration
  - [ ] Invalid readings kept raw, excluded from level and alerts, with `invalid_reason`
  - [ ] Works with a default calibration before E6 lands, labelled uncalibrated in the API

#### E5.6 API: status, level, health, history (no demo data)
- **Labels:** `epic:E5-service`, `phase:P2`, `type:story`, `area:service`
- **Size:** 5 · **Depends on:** E5.5
- **Body:** FastAPI on :8120 (configurable), read-only, LAN and Tailscale only.
  - [ ] `/healthz`, `/api/v1/status`, `/api/v1/level/current`, `/api/v1/level/history`, `/api/v1/node/health`
  - [ ] Every response has `status` in `ok|stale|error|disabled|insufficient_data`; non-ok has `error {code, message}`
  - [ ] `/level/current` returns 503 with `last_good` when stale (15 min) or unavailable; values are null, never predicted or placeholder numbers in observed fields
  - [ ] API tests for every stale and error path assert `level_m` is null and `last_good` is labelled
  - [ ] No writes are exposed over HTTP

#### E5.7 Daily CSV export and nightly backup
- **Labels:** `epic:E5-service`, `phase:P2`, `type:story`, `area:service`
- **Size:** 2 · **Depends on:** E5.5
- **Body:**
  - [ ] Daily CSV of raw and derived data including power telemetry at 00:15 local; `GET /api/v1/export/{date}.csv`
  - [ ] Nightly `sqlite3 .backup` to the local backups folder with 14 copies (off-box copy is E13.2)
  - [ ] Second-location backup implemented per Nick's answer to Q10 (location TBD by Nick; story stays open until he names it)

#### E5.8 Deploy to the mini PC
- **Labels:** `epic:E5-service`, `phase:P2`, `type:story`, `area:service`
- **Size:** 3 · **Depends on:** E5.1, E5.6
- **Body:** Separate compose project under `/opt/tidesvc/`, same pattern as SignBoard.
  - [ ] Port 8120 confirmed free on the mini PC (or another port chosen; configurable)
  - [ ] `deploy.sh` (rsync + `docker compose up -d --build` over Tailscale), run by Nick
  - [ ] udev rule installed; container starts with the radio unplugged and recovers on replug without a restart
  - [ ] Container runs non-root in `dialout`; `.env` holds secrets and is not committed
  - [ ] systemd + venv fallback written down but not built

### P2 - NOAA and calibration (E6)

#### E6.1 NOAA module
- **Labels:** `epic:E6-calibration`, `phase:P2`, `type:story`, `area:service`
- **Size:** 3 · **Depends on:** E5.1
- **Body:**
  - [ ] Fetches `interval=hilo` predictions for 8531942 and 8531991 (MLLW, metric); cache covers -3 d to +7 d; refresh daily at 00:30
  - [ ] Sandy Hook 8531680 observations and 6-minute predictions every 6 min
  - [ ] A cached, published prediction stays valid after a failed fetch until it runs out; after that, an explicit `PREDICTION_UNAVAILABLE`
  - [ ] Recorded fixtures cover success, timeout, and "no data" responses
  - [ ] Notes that 8531991 has no observed data are reflected in the config names (prediction reference only)

#### E6.2 Prediction interpolation, residual, and rate of rise
- **Labels:** `epic:E6-calibration`, `phase:P2`, `type:story`, `area:service`
- **Size:** 3 · **Depends on:** E6.1, E5.5
- **Body:**
  - [ ] Half-cosine interpolation between consecutive extremes
  - [ ] `residual = level_smooth - pred`; `excess_rise` from a 60 min least-squares slope of level minus slope of prediction
  - [ ] No bracketing extreme pair gives `PREDICTION_UNAVAILABLE`; predicted values never fill observed fields
  - [ ] Unit tests with synthetic tides and known surge

#### E6.3 Quantify half-cosine error
- **Labels:** `epic:E6-calibration`, `phase:P2`, `type:spike`, `area:service`
- **Size:** 2 · **Depends on:** E6.1
- **Body:**
  - [ ] Interpolate Sandy Hook hi/lo and compare with its 6-minute harmonic predictions over a year
  - [ ] Error (mean, 95th percentile, in cm and minutes) documented in `docs/bench/` and linked from the API's `prediction_source`
  - [ ] If the error is more than half the +/-5 cm accuracy budget, the issue goes to Nick before alert thresholds are tuned

#### E6.4 Calibration module and install fit
- **Labels:** `epic:E6-calibration`, `phase:P2`, `type:story`, `area:service`
- **Size:** 5 · **Depends on:** E5.5
- **Body:** theta0 fixed from the level-ramp reading; fit h0 and L_eff only (ADR-009).
  - [ ] `tidesvc cal add-obs` stores tape freeboard and pitch pairs; `cal fit-install` needs >= 2 observations at tide states >= 0.5 m apart
  - [ ] Calibrations are versioned with `valid_from`; each derived row stores its calibration id
  - [ ] `tidesvc reprocess --from ...` recomputes derived data; raw is never modified
  - [ ] Fit recovers known (h0, L_eff) from synthetic tides with noise and freeboard jitter (tolerance stated in the test)
  - [ ] `datum` field in the API says MLLW is tied to NOAA predicted extremes, not surveyed

#### E6.5 Monthly refit with bounds and approval
- **Labels:** `epic:E6-calibration`, `phase:P2`, `type:story`, `area:service`
- **Size:** 5 · **Depends on:** E6.4, E6.2, E6.1
- **Body:**
  - [ ] Runs on the 1st at 03:00 local; matches observed extremes (centred smoothing, within +/-90 min) to predicted extremes
  - [ ] Only calm days included: Sandy Hook residual below 0.10 m in magnitude
  - [ ] Applied automatically only if |dh0| <= 0.05 m and |dL/L| <= 3%; otherwise stored `proposed` and raises `CALIBRATION_DRIFT`
  - [ ] `tidesvc cal approve|reject <id>`
  - [ ] Run is logged with its fit statistics

#### E6.6 Residual, predictions, and calibration endpoints
- **Labels:** `epic:E6-calibration`, `phase:P2`, `type:story`, `area:service`
- **Size:** 2 · **Depends on:** E6.2, E6.4, E5.6
- **Body:**
  - [ ] `/api/v1/residual`, `/api/v1/predictions`, `/api/v1/calibration`
  - [ ] Residual response carries `prediction_source`, Sandy Hook reference, and optional weather context
  - [ ] Error states follow the E5.6 conventions

### P2 - Energy log (E7)

#### E7.1 Energy accounting and verdict
- **Labels:** `epic:E7-energy`, `phase:P2`, `type:story`, `area:service`, `headline`
- **Size:** 5 · **Depends on:** E5.2, E1.2
- **Body:** The headline-metric logic (PRD FR6).
  - [ ] Harvest as the trapezoidal integral of `ipanel`; gaps over 15 min not integrated; daily `coverage_pct`
  - [ ] Consumption from the bench model; constants in config and stored per day
  - [ ] State of charge by coulomb count, re-anchored to 100% at each DONE; shown with anchor time
  - [ ] Daily rollup at 00:05 local: harvest, consumption, net, min and rest voltage, charge-inhibited hours, reached-full
  - [ ] 14-day verdict: surplus (>= 2), marginal (1-2), deficit (< 1), `insufficient_data` (fewer than 7 days at >= 80% coverage); `projected_days_to_empty` when the 7-day net is negative
  - [ ] Tests with gaps, DONE re-anchoring, and each verdict boundary

#### E7.2 Energy endpoints
- **Labels:** `epic:E7-energy`, `phase:P2`, `type:story`, `area:service`
- **Size:** 2 · **Depends on:** E7.1, E5.6
- **Body:**
  - [ ] `/api/v1/node/energy?days=` and `/api/v1/node/energy/samples?from&to`
  - [ ] Daily figures over any date range (PRD FR6), the verdict, and autonomy estimate
  - [ ] "No sun" vs "cold-inhibited" visible per day

### P2 - Alerts by email (E8)

#### E8.1 Alert engine and email notifier
- **Labels:** `epic:E8-alerts`, `phase:P2`, `type:story`, `area:service`
- **Size:** 5 · **Depends on:** E5.5
- **Body:**
  - [ ] Rules evaluate every 60 s; open/clear with hysteresis; de-duplicated by `kind` while open
  - [ ] Each alert records and prints its own clear condition
  - [ ] SMTP notifier sends only to the address in `.env` (Nick); no other recipients are configurable in v1
  - [ ] Failed email send is logged and retried; alert stays visible via `/api/v1/alerts`
  - [ ] `/api/v1/alerts?state=open|all&since`

#### E8.2 Surge and rapid-rise rules
- **Labels:** `epic:E8-alerts`, `phase:P2`, `type:story`, `area:service`
- **Size:** 2 · **Depends on:** E8.1, E6.2
- **Body:**
  - [ ] `SURGE_WARNING` at +0.30 m and `SURGE_SEVERE` at +0.60 m on 2 consecutive evaluations; clear at +0.20 / +0.50 for 30 min
  - [ ] `RAPID_RISE` at 0.15 m/h excess; clear below 0.08 m/h for 30 min
  - [ ] Thresholds configurable; emails include the Sandy Hook residual
  - [ ] Frozen-clock tests for open, hold, clear, and flapping input

#### E8.3 Health rules
- **Labels:** `epic:E8-alerts`, `phase:P2`, `type:story`, `area:service`
- **Size:** 3 · **Depends on:** E8.1, E7.1, E6.5
- **Body:** `NODE_SILENT`, `GATEWAY_DOWN`, `REPEATER_SILENT`, `LOW_BATTERY`, `ENERGY_DEFICIT`, `ENERGY_NEGATIVE_STREAK`, `SENSOR_QUALITY`, `OUT_OF_RANGE`, `PREDICTION_UNAVAILABLE`, `CALIBRATION_DRIFT`.
  - [ ] Each rule from ARCHITECTURE 6.8 implemented with its open and clear conditions
  - [ ] `NODE_SILENT`, `REPEATER_SILENT` and `GATEWAY_DOWN` are distinct and the email says which side to look at
  - [ ] Open decision recorded: PRD says node silent after 15 min, architecture says alert at 30 min while displays go stale at 15 (section 7 item 1); Nick picks
  - [x] Decided (Nick, 2026-10-10): `ENERGY_DEFICIT` on the 14-day verdict is the official answer; `ENERGY_NEGATIVE_STREAK` sends an early-warning email after 7 consecutive negative-net days (low-coverage days skipped) and clears on the first non-negative day (PRD v0.3 FR6, ARCHITECTURE 6.6/6.8)

#### E8.4 Alert replay and test email
- **Labels:** `epic:E8-alerts`, `phase:P2`, `type:story`, `area:service`
- **Size:** 2 · **Depends on:** E8.2, E8.3
- **Body:**
  - [ ] A synthetic surge (injected residual ramp) opens warning then severe, and clears, in a replay test
  - [ ] A real test email of each severity arrives at Nick's address and reads clearly on a phone
  - [ ] A silent-node replay opens `NODE_SILENT` and clears on the next valid reading

### P2 - Tempest, optional (E9)

#### E9.1 Tempest poller (disabled by default)
- **Labels:** `epic:E9-tempest`, `phase:P2`, `type:story`, `area:service`, `optional`
- **Size:** 3 · **Depends on:** E5.1
- **Body:** REST poll of station 183092, every 5 min, personal token (may share SignBoard's token per Nick's Q3 answer).
  - [ ] `tempest.enabled = false` by default; token only in `.env`
  - [ ] Defensive parser: missing fields become null with a field-level reason, never a default
  - [ ] Statuses `ok|disabled|error|stale` (stale after 15 min); stored in `tempest_obs`
  - [ ] Verified once against the live response; the unverified fields from ARCHITECTURE 13 item 5 are confirmed or dropped
  - [ ] No UDP listener is opened (port 50222 stays with the TempestWeather sidecar)

#### E9.2 Derived context and weather endpoint
- **Labels:** `epic:E9-tempest`, `phase:P2`, `type:story`, `area:service`, `optional`
- **Size:** 3 · **Depends on:** E9.1, E6.6
- **Body:**
  - [ ] `pressure_change_3h_hpa` (needs >= 2.5 h history), `inverse_barometer_m`, `onshore_wind_sustained` (20-140 deg, >= 8 m/s over 6 h)
  - [ ] `/api/v1/weather/current`; weather block also in `/residual`
  - [ ] **Core endpoints byte-identical in structure with Tempest on, off, or failing** (test); overall `status` never degraded by Tempest

#### E9.3 SURGE_WATCH rule and email context
- **Labels:** `epic:E9-tempest`, `phase:P2`, `type:story`, `area:service`, `optional`
- **Size:** 2 · **Depends on:** E9.2, E8.1
- **Body:**
  - [ ] Opens at residual >= +0.15 m and (pressure drop <= -3 hPa/3 h or onshore wind sustained); only when Tempest is `ok`
  - [ ] Marked advisory in the email; surge emails say "Tempest context unavailable" when it is
  - [ ] `TEMPEST_UNAVAILABLE` is status only, with no email

#### E9.4 Backfill and station-exposure check
- **Labels:** `epic:E9-tempest`, `phase:P4`, `type:chore`, `area:service`, `optional`
- **Size:** 1 · **Depends on:** E9.2, E10.4
- **Body:**
  - [ ] Optional start-up backfill from the device history endpoint works, or is dropped
  - [ ] Station 183092's distance and wind exposure relative to the ramp noted; if it is unrepresentative, the onshore sector and thresholds flagged for Nick after the first storm season

### P3 - Install and calibration (E10)

#### E10.1 Install kit and enclosure final assembly
- **Labels:** `epic:E10-install`, `phase:P3`, `type:story`, `area:hardware`
- **Size:** 3 · **Depends on:** E2.3, E3.6
- **Body:**
  - [ ] Final firmware flashed; node provisioned (E3.5); label on the box: no USB with cell attached
  - [ ] Bracket, 316 SS fasteners, nylon washers, dielectric paste, VHB tape, antenna stub assembled and test-fit
  - [ ] Photos of the assembled unit and orientation reference
  - [ ] Spare parts: one cell, desiccant, fuses/jumper

#### E10.2 Install on the ramp
- **Labels:** `epic:E10-install`, `phase:P3`, `type:story`, `area:hardware`, `gate`
- **Size:** 3 · **Depends on:** E4.4, E10.1, E5.3 live
- **Body:** Reversible, no drilling (warranty precaution); concealed from the deck.
  - [ ] Panel bonded flat to the south face; enclosure tucked beside it; antenna stub 2-3 cm off the metal
  - [ ] Sensor axis along the ramp; isolation between stainless and aluminum
  - [ ] Drip loops and strain relief on every cable
  - [ ] First 12 packets seen in `packets_raw` and the API `node/health` shows `ok`
  - [ ] Nothing visible from the deck (photo check)

#### E10.3 Install calibration
- **Labels:** `epic:E10-install`, `phase:P3`, `type:story`, `area:hardware`
- **Size:** 3 · **Depends on:** E10.2, E6.4
- **Body:**
  - [ ] Level-ramp pitch reading taken for theta0 (or taken from the bench-and-geometry method if the ramp cannot be levelled; method recorded)
  - [ ] Tape freeboard against the fixed bulkhead mark at two tide states >= 0.5 m apart (spans a tide cycle)
  - [ ] Observations entered with `cal add-obs`; `cal fit-install` run; calibration v1 active
  - [ ] Resulting level compared with the tape values and NOAA hi/lo timing; difference recorded

#### E10.4 Two-week shakedown and datum tie
- **Labels:** `epic:E10-install`, `phase:P4`, `type:story`, `area:service`, `gate`
- **Size:** 3 · **Depends on:** E10.3, E6.5, E8.4
- **Body:** PRD section 7, metrics 2 and 3.
  - [ ] Smoothed level tracks NOAA predicted hi/lo times within +/-15 min and heights within +/-5 cm on calm days
  - [ ] >= 95% of expected packets received, measured from sequence numbers
  - [ ] Datum tie performed on calm days; monthly refit runs once cleanly or is simulated on shakedown data
  - [ ] Alerts armed after the shakedown; a list of any surprises written to `docs/`
  - [ ] Result recorded: pass, or the specific failing metric and the fix plan

### P5 - Solar-sufficiency analysis (E11)

#### E11.1 Write the expectation before the data arrives
- **Labels:** `epic:E11-solar`, `phase:P3`, `type:chore`, `area:docs`, `headline`
- **Size:** 2 · **Depends on:** E0.1, E1.2, E1.6
- **Body:** A falsifiable prediction so the winter result means something.
  - [ ] Expected daily harvest for Nov, Dec, Jan, Feb from measured panel output, charger efficiency, the PVGIS table (ARCHITECTURE 4.5), and the site shading estimate
  - [ ] Expected number of cold-inhibited hours per month for a shaded box under a ramp (stated as an assumption)
  - [ ] Failure definition stated up front: what energy ratio, autonomy, or brownout counts as "panel too small"
  - [ ] Committed to `docs/` before the winter data accumulates

#### E11.2 Monthly energy checkpoints (Nov, Dec, Jan, Feb)
- **Labels:** `epic:E11-solar`, `phase:P5`, `type:chore`, `area:docs`, `headline`
- **Size:** 1 each (4 total) · **Depends on:** E7.2, E10.4
- **Body:** Short review at the end of each month.
  - [ ] Harvest vs the E11.1 expectation; shortfall attributed to shading, cold inhibit, or load (the three suspects in ARCHITECTURE 4.5)
  - [ ] Lowest battery voltage and any days not reaching full
  - [ ] A line in the doc or an issue comment; flag early if the verdict is trending to deficit, so a fix (bigger panel, relocated panel) can be tried before February

#### E11.3 Winter report and recommendation
- **Labels:** `epic:E11-solar`, `phase:P5`, `type:story`, `area:docs`, `headline`
- **Size:** 3 · **Depends on:** E11.2 through February
- **Body:** The pilot's headline deliverable (PRD G1 and metric 1).
  - [ ] Yes or no on "the south-face panel keeps the node energy-neutral through winter", with the daily figures, worst week, and any brownout
  - [ ] Cold-inhibit effect separated from the cloud effect
  - [ ] If no: the size of the shortfall and a specific fix (panel area, tilt, relocation, cell, interval)
  - [ ] If yes: the margin, and what would break it (shading change, snow, bird fouling)
  - [ ] Recommendation on a second ramp (PRD phase 5)

### P6 - SignBoard tide panel (E12, separate repo, later)

#### E12.1 SignBoard tide panel consuming the tidesvc API
- **Labels:** `epic:E12-signboard`, `phase:P6`, `type:story`, `area:signboard`, `later`
- **Repo:** the SignBoard repo, **not** this one. Create there when approved.
- **Size:** 5 · **Depends on:** E5.6, E6.6, E10.4 (Q11: build after the sensor is reporting)
- **Body:** SignBoard's backend polls `http://host.docker.internal:8120/api/v1/level/current` every 60 s, the same pattern as TempestWeather.
  - [ ] Panel shows current level, trend arrow, predicted level, and residual
  - [ ] On 503 or stale, the panel shows "offline since ..." with `last_good`, and never shows predicted values as the water level
  - [ ] Works with tidesvc down (SignBoard stays up; panel shows an error state)
  - [ ] Existing tide service (currently Sandy Hook 8531680) is left alone or its replacement is a separate decision for Nick
  - [ ] No changes to this repo are needed beyond API fixes

### P4 - Operations and ownership (E13)

#### E13.1 Runbook
- **Labels:** `epic:E13-ops`, `phase:P4`, `type:story`, `area:docs`
- **Size:** 3 · **Depends on:** E10.4
- **Body:** PRD section 3.2 and metric 5.
  - [ ] How to read health and energy views; what each flag and alert kind means and what to do
  - [ ] Swap a battery; swap desiccant; re-flash or re-provision the node over USB (and the "no USB with cell" warning)
  - [ ] Restart the gateway, the repeater, and the service; recover from a replugged radio; "node silent and repeater silent: check the repeater first"
  - [ ] Recalibrate and approve a proposed calibration; reprocess
  - [ ] Where secrets live and how to rotate the channel secret on all three radios
  - [ ] Nick has done at least one routine task (for example, a desiccant or battery check) from the runbook

#### E13.2 Off-box backup
- **Labels:** `epic:E13-ops`, `phase:P4`, `type:chore`, `area:service`
- **Size:** 1 · **Depends on:** E5.7, Nick naming a location
- **Body:**
  - [ ] Nightly copy of the SQLite backup to the second location Nick names (for example his Mac over Tailscale)
  - [ ] A restore from that copy tested once

---

## 6. GitHub issues, ready to create later

**Do not create yet.** Nick has not approved a repo or issues. When he does, the list below is complete enough to script. Everything in section 5 is one issue each; the **Body** text in section 5 is the issue body (user story line optional for a solo project). E12.1 goes to the SignBoard repo.

### 6.1 Labels

| Group | Labels |
|---|---|
| Epic | `epic:E0-site`, `epic:E1-bench`, `epic:E2-power`, `epic:E3-firmware`, `epic:E4-link`, `epic:E5-service`, `epic:E6-calibration`, `epic:E7-energy`, `epic:E8-alerts`, `epic:E9-tempest`, `epic:E10-install`, `epic:E11-solar`, `epic:E12-signboard`, `epic:E13-ops` |
| Phase | `phase:P0` ... `phase:P6` |
| Type | `type:story`, `type:spike`, `type:chore`, `type:bug` |
| Area | `area:firmware`, `area:hardware`, `area:gateway`, `area:service`, `area:docs`, `area:signboard` |
| Flags | `gate` (phase exit or blocks later work), `risk:high`, `headline` (answers the solar question), `optional`, `later`, `blocked` |
| Size | `size:1`, `size:2`, `size:3`, `size:5` |

### 6.2 Milestones

| Milestone | Phase | Closes when |
|---|---|---|
| M0 Site and decisions | P0 | E0.1-E0.4, E4.2 done |
| M1 Bench | P1 | E1.7 review done and E2.1-E2.3 done |
| M2 Build | P2 | E3.6 soak, E5.8 deployed, E8.4 replay, E9 pass |
| M3 Link and install | P3 | E4.4 and E10.3 done |
| M4 Shakedown | P4 | E10.4 and E13.1 done |
| M5 Winter | P5 | E11.3 done |
| M6 SignBoard panel | P6 | E12.1 in the SignBoard repo |

### 6.3 Issue index (title, labels, milestone, size)

| ID | Title | Key labels | Milestone | Size | Depends on |
|---|---|---|---|---|---|
| E0.1 | Site visit: ramp geometry, stringer, and south-face shading | chore, hardware | M0 | 2 | none |
| E0.2 | Resolve blocking choices before ordering | chore, docs | M0 | 2 | BATTERY.md, E0.1 |
| E0.3 | Update BOM and architecture for the repeater | chore, docs | M0 | 1 | E0.2 |
| E0.4 | Order parts (needs Nick's approval to spend) | chore, hardware | M0 | 1 | E0.2, E0.3 |
| E4.2 | Choose the private radio settings | spike, gateway | M0 | 2 | none |
| E1.1 | Spike S1: minimal MeshCore sender that never listens | spike, firmware, risk:high | M1 | 5 | E0.4 |
| E1.2 | Measure sleep current and awake profile | spike, hardware | M1 | 3 | E1.1 |
| E1.3 | LiFePO4 brownout sweep on the Heltec V3 battery input | spike, hardware | M1 | 2 | E1.1, BATTERY.md |
| E1.4 | SCL3300 bring-up and tilt-rig noise test | spike, firmware | M1 | 5 | E0.4 |
| E1.5 | Temperature characterisation (k_T) | spike, hardware | M1 | 3 | E1.4 |
| E1.6 | Charger, panel, and cold-cutoff verification | spike, hardware, risk:high | M1 | 3 | E0.4, BATTERY.md |
| E1.7 | Phase 1 exit review | chore, docs | M1 | 1 | E1.1-E1.6 |
| E2.1 | Power design intake from BATTERY.md | chore, docs | M1 | 1 | BATTERY.md |
| E2.2 | Assemble and test the power path | story, hardware | M1 | 5 | E2.1, E1.3, E1.6 |
| E2.3 | Enclosure fit, sealing, and thermal sanity | story, hardware | M1 | 2 | E2.2 |
| E3.1 | Cycle state machine and battery-state intervals | story, firmware | M2 | 5 | E1.1, E1.3 |
| E3.2 | Burst sampling and statistics | story, firmware | M2 | 3 | E1.4 |
| E3.3 | Power telemetry and charger control | story, firmware | M2 | 5 | E2.2, E1.6 |
| E3.4 | Payload v1 codec and shared golden vectors | story, firmware | M2 | 3 | none |
| E3.5 | Provisioning command and routing options | story, firmware | M2 | 3 | E1.1, E4.2 |
| E3.6 | 72-hour bench soak | story, firmware | M2 | 3 | E3.1-E3.5, E4.1 |
| E4.1 | Gateway radio: flash, configure, and attach | story, gateway | M2 | 2 | E0.4, E4.2 |
| E4.3 | Repeater: configure and verify the bridge | story, gateway | M2 | 3 | E4.1, E4.2, E1.1 |
| E4.4 | 48-hour link test from the final node position | story, gateway, gate | M3 | 3 | E3.6, E4.3, E5.3 |
| E5.1 | Project skeleton, schema, and deploy scaffolding | story, service | M2 | 3 | none |
| E5.2 | Codec: decode v1, CRC, de-dup, sequence gaps | story, service | M2 | 3 | E3.4, E5.1 |
| E5.3 | Radio module: meshcore_py ingest and gateway health | story, service | M2 | 5 | E4.1, E5.2 |
| E5.4 | Fake companion and ingest integration tests | story, service | M2 | 3 | E5.3 |
| E5.5 | Derive: level conversion, validity, and smoothing | story, service | M2 | 5 | E5.2 |
| E5.6 | API: status, level, health, history (no demo data) | story, service | M2 | 5 | E5.5 |
| E5.7 | Daily CSV export and nightly backup | story, service | M2 | 2 | E5.5 |
| E5.8 | Deploy to the mini PC | story, service | M2 | 3 | E5.1, E5.6 |
| E5.9 | Repeater health | story, service | M2 | 3 | E5.3, E4.3 |
| E6.1 | NOAA module | story, service | M2 | 3 | E5.1 |
| E6.2 | Prediction interpolation, residual, and rate of rise | story, service | M2 | 3 | E6.1, E5.5 |
| E6.3 | Quantify half-cosine error | spike, service | M2 | 2 | E6.1 |
| E6.4 | Calibration module and install fit | story, service | M2 | 5 | E5.5 |
| E6.5 | Monthly refit with bounds and approval | story, service | M2 | 5 | E6.4, E6.2 |
| E6.6 | Residual, predictions, and calibration endpoints | story, service | M2 | 2 | E6.2, E6.4, E5.6 |
| E7.1 | Energy accounting and verdict | story, service, headline | M2 | 5 | E5.2, E1.2 |
| E7.2 | Energy endpoints | story, service | M2 | 2 | E7.1, E5.6 |
| E8.1 | Alert engine and email notifier | story, service | M2 | 5 | E5.5 |
| E8.2 | Surge and rapid-rise rules | story, service | M2 | 2 | E8.1, E6.2 |
| E8.3 | Health rules | story, service | M2 | 3 | E8.1, E7.1, E6.5 |
| E8.4 | Alert replay and test email | story, service | M2 | 2 | E8.2, E8.3 |
| E9.1 | Tempest poller (disabled by default) | story, service, optional | M2 | 3 | E5.1 |
| E9.2 | Derived context and weather endpoint | story, service, optional | M2 | 3 | E9.1, E6.6 |
| E9.3 | SURGE_WATCH rule and email context | story, service, optional | M2 | 2 | E9.2, E8.1 |
| E9.4 | Backfill and station-exposure check | chore, service, optional | M4 | 1 | E9.2, E10.4 |
| E10.1 | Install kit and enclosure final assembly | story, hardware | M3 | 3 | E2.3, E3.6 |
| E10.2 | Install on the ramp | story, hardware, gate | M3 | 3 | E4.4, E10.1, E5.3 |
| E10.3 | Install calibration | story, hardware | M3 | 3 | E10.2, E6.4 |
| E10.4 | Two-week shakedown and datum tie | story, service, gate | M4 | 3 | E10.3, E6.5, E8.4 |
| E11.1 | Write the expectation before the data arrives | chore, docs, headline | M3 | 2 | E0.1, E1.2, E1.6 |
| E11.2 | Monthly energy checkpoints (Nov-Feb), 4 issues or one recurring | chore, docs, headline | M5 | 1 each | E7.2, E10.4 |
| E11.3 | Winter report and recommendation | story, docs, headline | M5 | 3 | E11.2 |
| E12.1 | SignBoard tide panel consuming the tidesvc API (SignBoard repo) | story, signboard, later | M6 | 5 | E5.6, E6.6, E10.4 |
| E13.1 | Runbook | story, docs | M4 | 3 | E10.4 |
| E13.2 | Off-box backup | chore, service | M4 | 1 | E5.7 |

### 6.4 Creating them later

When approved, the issues can be created with one `gh issue create --title ... --label ... --milestone ... --body-file ...` per row, with the story body from section 5 as the body file, after `gh label create` and `gh api` calls for the labels and milestones above. That is a script to write at that time, not now. Only Nick approves creating the repo.

---

## 7. Open items for Nick

**This is the single list of open items across the planning docs** (PRD v0.3, ARCHITECTURE v0.2, BATTERY.md v0.2, BOM v0.2 and TEST-PLAN v0.2 point here). None block starting P0.

**Still open, needs Nick:**
1. **Node-silent alert timing:** PRD FR4 says node silent after 15 min; ARCHITECTURE 6.8 alerts at 30 min while displays go stale at 15. Pick one (E8.3).
2. **Off-box backup location (Q10):** nightly backup to a second location is decided, the location is not. E5.7 and E13.2 wait on it.
3. **Repeater on the private frequency:** a repeater listens on one frequency, so moving Nick's repeater to the project's private settings means it no longer serves the public US MeshCore mesh. Confirm (E4.2). Also confirm the repeater's build status (parts were listed, not bought, as of 2026-09-29).
4. **Panel type.** The 1 W flexible amorphous panel is lower efficiency than the mono Adafruit 3809, and the architecture's eta = 0.5 was not derived for it. Its Voc is still to be measured (BATTERY.md expects about 7.7 V for a 6 V panel, well inside the BQ25185's 18 V). If it underperforms, the headline question becomes "is this particular panel enough", which E11.3 should say.
5. **26650 physical fit** in the Fibox PCB 65T (accepted on outside dimensions only) (E0.2).

**Spec gaps (from TEST-PLAN section 11, not settled by Nick's decisions):**
6. **Minimum number of matched extremes** for a monthly calibration fit (TEST-PLAN SV-C7). Proposal needed in E6.5.
7. **Median rule for an even sample count** (300 samples) in firmware and server (TEST-PLAN FW-U4). Fix in one place in E3.2 / E5.5.
8. **Cell current is not in the payload.** The BQ25185 is a linear charger with a power path, so `ipanel` = load + charge in sun. Harvest = ∫`ipanel` remains a valid measure for the energy ratio (ARCHITECTURE 6.6), and TEST-PLAN B10 now checks it that way. But INA3221 ch2 measures cell current, and payload v1 does not carry it. Decide before the payload freezes (E3.4) whether to add an `ibat` field, which would give a direct check on net charge.
9. **Which temperature the firmware 0 °C rule uses.** ARCHITECTURE 4.3 uses the SCL3300 die temperature as an in-box proxy. The cell-bonded NTC sits on the charger's TS pin and is not read by the MCU. Decide whether the proxy plus the +1 °C threshold is enough, or add an ADC tap or a second cell sensor (E1.6, E3.3).
10. **Hardware unknowns to check on the bench** (BATTERY.md section 10): the Adafruit 6091's existing pull on /CE and the LED pull-up rail; Heltec V3 board revision; whether SYS stays up from the panel during a TS fault.
11. **Repeater visibility from `tidesvc`:** the advert event and status request in `meshcore_py` are unverified (ARCHITECTURE 5.5, E5.9). If neither works, repeater health falls back to relayed-frame evidence only, which cannot tell a dead repeater from a dead node once the node is also silent.

**Resolved in this pass (2026-10-10), kept for the record:** energy alert form (14-day verdict official, 7-day early warning); PRD v0.3 written (FR1 ±5%, no ack, Q1b closed); repeater is Nick's existing PVC-tube design, flood routing, repeater power out of scope; Q7 cell size (26650) and charger (BQ25185) settled, CN3058E dropped; INA3221 and repeater added to the BOM; per-hop link-margin criterion restated.

**Notes:**
12. **The RAK WisBlock option in the BOM** is kept as a prototype path only. It would need an nRF52 port of the custom firmware (unverified) and is not planned here; the Heltec V3 + SCL3300 build is primary.
13. **Schedule risk.** Parts have not been ordered and today is 2026-10-10. If the install slips past about December 1, the winter test loses its worst-case weeks; E11.1 and E11.2 should note the actual install date in the report.
