# Development Plan: LoRa Ramp Tide Sensor

**Version:** 0.3 (draft)
**Last Updated:** 2026-11-04
**Author:** Nick DeMarco, with AI assistance (dev-planning agent)
**Status:** Draft, for Nick's review. **No GitHub repo or issues exist yet.** Section 6 holds the issue list in a form that can be created once Nick approves a repo.
**Inputs:** `docs/PRD.md` v0.4, `docs/ARCHITECTURE.md` v0.3 plus Nick's answers log, `docs/BATTERY.md` v0.3, `docs/BOM.md` v0.3, `workspace/research/SPEC.md`
**Not duplicated here:** battery chemistry, cell, and charger research lives in `docs/BATTERY.md` (v0.3, decisions recorded). Stories in the power system epic *consume* its output; they do not redo it.

**Changes in v0.3 (2026-11-04):** applied Nick's 2026-11-04 decisions. The repeater is taken down, and the node sends LoRa point-to-point to a Wi-Fi gateway that posts to `tidesvc` on :8120. MeshCore is dropped (ARCHITECTURE 2.1, pending Nick's confirmation). Rewritten: E1.1 (spike S1 on RadioLib), E4.1 (gateway firmware, now size 5), E4.2, E4.3 (gateway placement and direct-link check, replacing the repeater story), E4.4, E5.3 (HTTP ingest), E5.4 (fake gateway), E5.8. **E5.9 (repeater health) dropped.** E3.3/E3.4/E3.5 updated for the battery thermistor, payload v2 with `ibat`/`tbat`, and the frame/AEAD key. E5.7/E13.2: backup to a Google Drive folder. E8.3: `NODE_SILENT` at 30 min decided, `REPEATER_SILENT` removed. Section 7 items 1, 2, 3, 8, 9 and 11 closed; new items added. **The GitHub issues created on 2026-10-10 still carry the v0.2 text for the stories above and need editing (E5.9 closing); that was not done in this pass.**

**Changes in v0.2 (2026-10-10):** applied Nick's decisions. E0.2 and E2.1 charger/cell items resolved (BQ25185, 26650). E0.3 doc updates done (repeater is Nick's existing PVC-tube design). E1.6, E3.3 and E2.2 corrected for BQ25185 /CE polarity (HIGH = disabled, pull-up), 130 kΩ NTC shift, firmware 0 °C rule and the 4 h CE pulse. E4.3 and E4.4 restated for flood routing, matched private settings and per-hop margin; the repeater's own power budget dropped from scope. New story E5.9 (repeater health). E8.3: energy alert decided (14-day verdict official, 7-day early warning) and `REPEATER_SILENT` added. Section 7 is now the single list of open items, including the TEST-PLAN spec gaps.

---

## 1. Shape of the project

One node, one Wi-Fi gateway (no repeater), one Python service, one owner (Nick). Hobby pace: evenings and weekends, no sprints. Work is organized as **epics in phases**; stories inside a phase are ordered, and the phase exit is a testable gate. Milestones in the issue list map one-to-one to phases.

**Sizing.** Points use the dev-planning scale: 1 trivial, 2 small, 3 medium, 5 large, 8 should be split. Rough hobby conversion: **1 point is about one focused evening**. Total is about **175 points**, which is a rough estimate: Phase 1 numbers are the most solid, the winter phases are checkpoints that depend on the calendar rather than effort.

**Calendar pressure.** The pilot's headline question (PRD section 7, metric 1) is answered by December-February data. To have a December in the log, the node should be **installed and reporting by about the end of November**. The critical path is therefore parts, bench (S1 and power), node firmware, link test, install. The server only needs the *raw-capture slice* (stories 5.1-5.3) before install, because raw packets are stored first and everything else can be reprocessed from them later.

### Critical path

```
0.1 site (gateway spot) + 0.2 decisions -> 0.4 order parts -> 1.1 S1 spike -> 1.2/1.3/1.6 bench power
  -> 2.2 power path -> 3.x firmware -> 4.1 gateway firmware -> 4.3 gateway placement -> 4.4 link test -> 10.2 install
parallel: 5.1-5.3 raw capture on the mini PC (must be live at install)
```

---

## 2. Phases and exit gates

| Phase | PRD phase | Epics | Exit gate (testable) |
|---|---|---|---|
| **P0 Site and decisions** | 0 | E0 | L, hinge, stringer, shading recorded; radio settings, cell size, and parts list decided; Nick has approved the order |
| **P1 Bench** | 1 | E1, E2 | S1 passes; sleep and awake current measured and inside the 25 mAh/day design budget; LiFePO4 brownout point known; tilt noise at or below 0.01 deg; charger cold cutoff observed |
| **P2 Build** | 1-2 | E3, E4 (4.1-4.3), E5, E6, E7, E8, E9 | Firmware soaks 72 h on the bench; service ingests from the real gateway and serves the API; alerts replay green; Tempest optional path passes with it on and off |
| **P3 Link test and install** | 2-3 | E4 (4.4), E10 | 48 h direct link test to the gateway meets PRD >=95% and >= 10 dB margin over the chosen SF floor before anything is bonded; node installed and calibrated |
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
| E3 | Node firmware | Wake, measure, send one encrypted LoRa frame, deep sleep | P2 |
| E4 | Gateway and link | Frames get from the ramp to the mini PC reliably over one hop and Wi-Fi | P2-P3 |
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
E0 -> E4.1/4.2/4.3 (gateway firmware, radio settings, gateway placement) -> E4.4
E3.4 (golden vectors) -> E5.2 (codec), E4.1 (gateway frame filter)
E4.1 (gateway) <-> E5.3 (ingest endpoint) 
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
  - [ ] Gateway spot chosen and recorded (feeds E4.3): distance to the ramp, height above water, line of sight, window glazing (plain or coated), and whether its Wi-Fi reaches the mini PC's port 8120. **No repeater any more, so this spot decides the link** (ARCHITECTURE 2.4)

#### E0.2 Resolve blocking choices before ordering
- **Labels:** `epic:E0-site`, `phase:P0`, `type:chore`, `area:docs`
- **Size:** 2 · **Depends on:** `docs/BATTERY.md` complete (input), E0.1
- **Body:** Close the items that block the order. Take battery, cell, and charger conclusions from BATTERY.md as given.
  - [x] Q7 closed: 26650 LiFePO4 (Nick, 2026-10-10; fits the Fibox PCB 65T by outside dimensions)
  - [ ] 26650 physically test-fitted in the chosen enclosure, against the space measured in E0.1. **Nick's bench to-do, still open (2026-11-04)**
  - [ ] Bioenno cell label read on arrival: capacity recorded (planning value 3200 mAh; update `energy.capacity_mah` if different)
  - [x] Charger part chosen per BATTERY.md: TI BQ25185 on Adafruit 6091 (architecture v0.2 and BOM v0.2 agree)
  - [ ] Panel open-circuit voltage measured on the 1 W flexible amorphous panel (or its datasheet value recorded) and checked against the BQ25185 input (3.6-18 V operating; BATTERY.md expects about 7.7 V for a 6 V panel). **Nick's bench to-do, still open (2026-11-04)**
  - [ ] SMA vs RP-SMA confirmed for the Heltec V3 and the antenna
  - [ ] US enclosure source with gland options chosen
  - [ ] Private radio settings requested from E4.2 (so node and gateway can be flashed the same way)

#### E0.3 Update BOM and architecture for the transport (repeater, then direct link)
- **Labels:** `epic:E0-site`, `phase:P0`, `type:chore`, `area:docs`
- **Size:** 1 · **Depends on:** E0.2
- **Body:** v0.2: Nick's PVC-tube repeater bridged the ramp to the gateway (done in BOM/ARCHITECTURE v0.2). **2026-11-04: the repeater is taken down;** the node sends point-to-point to a Wi-Fi gateway.
  - [x] v0.2 repeater changes (BOM v0.2, ARCHITECTURE v0.2, PRD v0.3), now superseded
  - [x] Docs updated for the direct link: PRD v0.4 (D20), ARCHITECTURE v0.3 (sections 2, 5, ADR-001 to 004), BOM v0.3 (repeater section removed, gateway G1-G5), TEST-PLAN v0.3
  - [ ] Nick confirms dropping MeshCore entirely (ARCHITECTURE Q12); if not, ARCHITECTURE 2.1's alternative (MeshCore framing with a MeshCore-library gateway) replaces sections 2.2 and 5.2
  - [ ] GitHub issues E0.3, E1.1, E3.3-E3.6, E4.1-E4.4, E5.3, E5.4, E5.7-E5.9, E8.3, E13.1, E13.2 edited to this text; E5.9 closed as dropped

#### E0.4 Order parts (needs Nick's approval to spend)
- **Labels:** `epic:E0-site`, `phase:P0`, `type:chore`, `area:hardware`
- **Size:** 1 · **Depends on:** E0.2, E0.3
- **Body:** Node, gateway Heltec V3 with its antenna and USB wall adapter, node antenna, enclosure, cell, charger, two B3435 NTCs, the 130 kΩ and 10 kΩ 0.1% resistors, LM66100, INA3221 breakout, fuse, breather vent, panel, bonding and isolation hardware, current-measurement gear (PPK2/Otii/uCurrent).
  - [ ] Parts list agrees with the updated BOM
  - [ ] Nick has approved the spend
  - [ ] Order placed; delivery dates noted against the end-of-November install target

### P1 - Bench

#### E1.1 Spike S1: minimal LoRa sender that never listens
- **Labels:** `epic:E1-bench`, `phase:P1`, `type:spike`, `area:firmware`, `risk:high`
- **Size:** 5 (time box: 2 days) · **Depends on:** E0.4
- **Body:** Rewritten 2026-11-04 (MeshCore dropped, ARCHITECTURE 2.1). Prove the node's radio path before building on it: RadioLib on the Heltec V3, the 54-byte encrypted frame, deep sleep with no RX, and end-to-end opening on the server.
  - [ ] PlatformIO env builds with RadioLib and rweather/Crypto pinned by version in `platformio.ini`
  - [ ] Sender does a channel-activity scan, transmits one 54-byte frame (ARCHITECTURE 2.2) on the private settings, then enters deep sleep without ever enabling receive
  - [ ] A bench gateway (E4.1 prototype, or a second Heltec logging to serial) receives the frame; `tidesvc`'s codec opens it with the link key and the payload bytes match exactly
  - [ ] ChaCha20-Poly1305 output from the C++ side matches Python `cryptography` on the shared vectors (header as AAD, nonce rule from ARCHITECTURE 2.2)
  - [ ] Link key and radio settings come from NVS via provisioning, not from source or git; `epoch` persists and increments on cold boot
  - [ ] 100 consecutive cycles with zero loss at bench distance; airtime measured at SF7 and SF9 against ARCHITECTURE 2.3
  - [ ] Findings and a go/no-go written to `docs/bench/S1.md`. **If no-go,** stop and bring the options to Nick

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
  - [ ] Battery thermistor (the MCU's NTC on the cell, BATTERY.md 3.4) read through the ADC against a reference thermocouple: error near 0 °C recorded (expected about ±0.5 °C); open and shorted thermistor detected as `tbat_error`
  - [ ] STAT1/STAT2 readable as GPIOs (no more than 3.3 V at the pin); /CE: **HIGH disables charging**; the 1 MΩ pull-up keeps charging off with the MCU unpowered; firmware drives /CE LOW to enable, held through deep sleep (T3)
  - [ ] Safety timer: without the firmware CE pulse charging latches off at 6 h; with a pulse about every 4 h it does not (T7)
  - [ ] Both NTCs (charger TS and MCU) placed on the cell (not the board) in the chosen enclosure confirmed

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
- **Body:** Panel input, charger, INA3221 (ch1 panel, ch2 cell side), fuse, cell, charger NTC ∥ 130 kΩ, battery thermistor divider to an ADC1 pin, /CE GPIO with 1 MΩ pull-up, SYS → LM66100 → Heltec JP1, battery disconnect jumper (BATTERY.md 3.4).
  - [ ] Wiring matches BATTERY.md 3.4 and the architecture block diagram; INA3221 reads both channels
  - [ ] Charge cycle observed end to end: STAT charging then done, with logged vbat, vpanel, ipanel, ibat, tbat
  - [ ] Battery disconnect or jumper present for programming; "no USB with cell attached" label on the unit
  - [ ] Sleep current with this path matches E1.2

#### E2.3 Enclosure fit, sealing, and thermal sanity
- **Labels:** `epic:E2-power`, `phase:P1`, `type:story`, `area:hardware`
- **Size:** 2 · **Depends on:** E2.2, E0.4
- **Body:**
  - [ ] Boards, cell, and wiring fit with drip loops and strain relief
  - [ ] Conformal coat applied to boards; desiccant placed; glands sealed
  - [ ] Both NTCs on the cell, not the board
  - [ ] Pressure/leak test (water spray or submersion of the closed empty box)

### P2 - Node firmware (E3)

#### E3.1 Cycle state machine and battery-state intervals
- **Labels:** `epic:E3-firmware`, `phase:P2`, `type:story`, `area:firmware`
- **Size:** 5 · **Depends on:** E1.1, E1.3
- **Body:** Wake, power read, sample or skip, build, encrypt, transmit, sleep. Interval by battery state: normal 5 min, low 15 min, critical 60 min with a health-only payload.
  - [ ] Thresholds are the measured values from E1.3
  - [ ] RTC memory carries `seq`, `boot_count`; NVS carries `epoch` (incremented on cold boot and on `seq` wrap, ARCHITECTURE 2.2); `reboot` flag set on cold boot; reset reason mapped to `brownout_reset` and `wdt_reset`
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
  - [ ] INA3221 one-shot read of vbat, vpanel, ipanel and **ibat** (ch2 shunt, signed; Nick 2026-11-04), then power-down; Vext switched off in sleep
  - [ ] Battery thermistor read through the ADC1 pin and converted (B3435 beta); `tbat` sent; open/short sets `tbat_error`
  - [ ] STAT1/STAT2 mapped into the `chg` byte per ARCHITECTURE 4.7 (CHRG, DONE, cold_charge_inhibit, CE override, latch fault, CE pulse)
  - [ ] Firmware owns the 0 °C rule **on the battery thermistor** (Nick, 2026-11-04; not the SCL3300 die): drives /CE **HIGH (disable)** below +1 C or when `tbat` is unknown, **LOW (enable)** above +2 C, holds state in between, and reports it (ARCHITECTURE 4.3)
  - [ ] Safety-timer pulse: after about 4 h of continuous charging (counted in RTC memory), /CE pulsed HIGH briefly then LOW
  - [ ] /CE state held through deep sleep (`gpio_hold_en`)
  - [ ] "No sun" and "too cold to charge" are distinguishable in the payload (PRD FR6)
  - [ ] `ina_error` flag set on read failure instead of reporting zeros

#### E3.4 Payload v2 codec, frame, and shared golden vectors
- **Labels:** `epic:E3-firmware`, `phase:P2`, `type:story`, `area:firmware`
- **Size:** 3 · **Depends on:** none (spec in ARCHITECTURE 2.2 and 4.7)
- **Body:** 30-byte little-endian payload v2 (v1 + `ibat` + `tbat`), CRC-16/CCITT-FALSE over bytes 0-27, inside the 54-byte frame (8-byte header as AAD, ChaCha20-Poly1305, 16-byte tag).
  - [ ] Encoder per the field table; frame seal per the nonce rule
  - [ ] Golden vectors in `tests/vectors/` (v2 payloads and sealed frames, with a fixed test key) incl. edge values (negative pitch and `ibat`, saturated SD, all flags, `tbat_error`); v1 vectors kept for the decoder
  - [ ] PlatformIO native test passes on the vectors; the same files are consumed by E5.2 and the gateway's frame filter (E4.1)

#### E3.5 Provisioning command and routing options
- **Labels:** `epic:E3-firmware`, `phase:P2`, `type:story`, `area:firmware`
- **Size:** 3 · **Depends on:** E1.1, E4.2
- **Body:** One-time USB serial `provision` command writing NVS.
  - [ ] Stores the 32-byte link key, node id, TX power, frequency, bandwidth, SF, CR, sync word, `tx_repeats` (no routing options any more)
  - [ ] Key never appears in source, build artifacts, or logs
  - [ ] Settings can be read back (secret masked) to verify what a deployed node carries
  - [ ] Procedure documented for the runbook (changing settings needs USB because the node never listens)

#### E3.6 72-hour bench soak
- **Labels:** `epic:E3-firmware`, `phase:P2`, `type:story`, `area:firmware`
- **Size:** 3 · **Depends on:** E3.1-E3.5, E4.1, E5.3
- **Body:** Node on a bench supply and the real gateway posting to `tidesvc`, sending every 5 min.
  - [ ] 72 h with no stuck cycle; sequence continuity from gateway log (loss measured, not assumed)
  - [ ] Measured daily consumption within 25 mAh/day budget
  - [ ] A deliberate brownout and a deliberate reboot show the right flags
  - [ ] Result recorded in `docs/bench/`

### P2 - Gateway and link (E4)

#### E4.1 Gateway firmware: receive, queue, forward, heartbeat
- **Labels:** `epic:E4-link`, `phase:P2`, `type:story`, `area:gateway`
- **Size:** 5 · **Depends on:** E0.4, E4.2, E3.4, E5.3
- **Body:** Rewritten 2026-11-04. Custom firmware (PlatformIO env `heltec_v3_gateway`) on the second Heltec V3, on the home/marina Wi-Fi (ARCHITECTURE 5.1-5.3).
  - [ ] Continuous RX on the private settings; frames filtered on LoRa CRC, length 54 and `fmt = 0x54`; RSSI, SNR and frequency error recorded; no decryption and no link key on the gateway
  - [ ] RAM queue of 288 frames; `POST /api/v1/ingest/frames` with bearer token and per-frame `age_ms`; frames removed only after a 200; retry with backoff
  - [ ] `POST /api/v1/ingest/heartbeat` every 60 s with uptime, firmware, Wi-Fi RSSI, queue depth, RX/CRC-error/wrong-format counters, noise floor
  - [ ] Watchdog; Wi-Fi reconnect; reboot after 30 min without a successful POST while Wi-Fi is up
  - [ ] USB provisioning into NVS: Wi-Fi SSID/password, server URL, ingest token, gateway id, radio settings; none in git; settings readable back with secrets masked
  - [ ] Powered from a USB wall adapter at the spot chosen in E0.1

#### E4.2 Choose the private radio settings
- **Labels:** `epic:E4-link`, `phase:P0`, `type:spike`, `area:gateway`
- **Size:** 2 · **Depends on:** none
- **Body:** Nick chose a private frequency and encrypted frames (Q2). Frequency, bandwidth, SF and CR are still to choose within 902-928 MHz, for one direct hop (no repeater).
  - [ ] A scan with a spare radio (RadioLib RSSI sweep) shows which sub-bands are quiet at the ramp and at the gateway spot
  - [ ] Frequency, BW, SF, CR and sync word chosen and written to ARCHITECTURE ADR-003; planning start SF9/BW125, SF10 the upper limit (ARCHITECTURE 2.3-2.4)
  - [ ] Airtime and mAh/day recomputed for the chosen settings (ARCHITECTURE 2.3, 4.4)
  - [ ] Same settings applied to node and gateway from one config note
  - [ ] Acceptance threshold written down for the chosen SF: median SNR at least 10 dB above that SF's floor (ARCHITECTURE 5.4)
  - [ ] FCC Part 15 basis for a single fixed channel at the chosen power and airtime checked and noted (ARCHITECTURE 13 item 8; unverified)

#### E4.3 Gateway placement and direct-link check
- **Labels:** `epic:E4-link`, `phase:P2`, `type:story`, `area:gateway`
- **Size:** 3 · **Depends on:** E4.1, E4.2, E1.1, E0.1
- **Body:** Replaces the v0.2 repeater story (repeater taken down 2026-11-04). The direct link is the main RF risk now (ARCHITECTURE 2.4).
  - [ ] Gateway at the E0.1 spot posts heartbeats to the mini PC over the Wi-Fi (network path to port 8120 confirmed)
  - [ ] Walk test: node held at the ramp in its planned antenna position, frames received with RSSI/SNR recorded at high and low tide
  - [ ] Measured margin compared with the link budget in ARCHITECTURE 2.4, and the assumed losses replaced with measured ones
  - [ ] If margin is short, the ladder in ARCHITECTURE 2.4 is tried and recorded (SF, outside antenna, closer spot, `tx_repeats`); if none works, bring the relay question to Nick
  - [ ] Gateway placement documented in the runbook draft

#### E4.4 48-hour link test from the final node position
- **Labels:** `epic:E4-link`, `phase:P3`, `type:story`, `area:gateway`, `gate`
- **Size:** 3 · **Depends on:** E3.6, E4.3, E5.3, E0.1
- **Body:** Before anything is bonded to the ramp (PRD).
  - [ ] Node in its planned spot and antenna position (temporary hold, no adhesive), with the gateway in its planned place
  - [ ] 48 h or more: delivery >= 95%, and >= 10 dB margin over the chosen SF's floor (gateway SNR per frame; 10 dB attenuator test, TEST-PLAN RF-3)
  - [ ] Repeated or extended across a high and a low tide (geometry changes with float height)
  - [ ] If short: the ladder is tried in order, each with a recorded result: lower TX power not helpful, higher SF on both radios, gateway antenna outside or higher, gateway moved closer, `tx_repeats = 1`
  - [ ] Result and settings written up; **install (E10.2) is blocked until this passes**

### P2 - tidesvc core (E5)

#### E5.1 Project skeleton, schema, and deploy scaffolding
- **Labels:** `epic:E5-service`, `phase:P2`, `type:story`, `area:service`
- **Size:** 3 · **Depends on:** none
- **Body:**
  - [ ] Python 3.12 project at `src/tidesvc/` with pytest, ruff, and config loader (`config.toml`, secrets from `.env`)
  - [ ] SQLite WAL schema with migrations: `packets_raw`, `readings`, `derived`, `calibrations`, `cal_observations`, plus the other tables from ARCHITECTURE 6.9; `meta(schema_version)`
  - [ ] Single writer behind an asyncio queue, read-only connections for the API
  - [ ] Dockerfile and compose file that builds and starts with no gateway posting
  - [ ] Timestamps UTC in storage; local-day helper for America/New_York

#### E5.2 Codec: decode v1, CRC, de-dup, sequence gaps
- **Labels:** `epic:E5-service`, `phase:P2`, `type:story`, `area:service`
- **Size:** 3 · **Depends on:** E3.4, E5.1
- **Body:**
  - [ ] Opens and decodes every golden vector (v2 frames, v1 payloads) identically to the C++ encoder
  - [ ] Bad tag, bad CRC, wrong `ver`, header/payload mismatch, or wrong length stored in `packets_raw` with `parse_status`, never dropped
  - [ ] De-dup on `(node_id, epoch, seq)`; frames from an older epoch rejected as replays; duplicates counted, not stored twice
  - [ ] Sequence gaps (and wraps and reboots) counted so delivery % is computable per day

#### E5.3 Ingest endpoint: gateway HTTP POST and gateway health
- **Labels:** `epic:E5-service`, `phase:P2`, `type:story`, `area:service`
- **Size:** 5 · **Depends on:** E5.1, E5.2
- **Body:** Rewritten 2026-11-04 (replaces the meshcore_py radio module). The raw-capture slice that must be live before install (ARCHITECTURE 5.3, 5.5).
  - [ ] `POST /api/v1/ingest/frames` and `/heartbeat` with bearer-token check (`TIDE_INGEST_TOKEN`); 401 stores nothing; 200 only after every frame is stored raw
  - [ ] Every frame inserted raw first (with gateway id, `age_ms`, RSSI, SNR), then opened, decoded and handed to derive
  - [ ] Reading time `t = rx_at - age_ms`; `time_source = "queued"` above 2 intervals; seq back-dating only as a fallback
  - [ ] Gateway status `ok|error|unknown` from heartbeats; `gateway_events` written; the API keeps serving with no gateway
  - [ ] Gateway `ok` with no frames is reported differently from gateway `error` (node or link vs gateway/network)

#### E5.9 Repeater health (dropped 2026-11-04)
- **Labels:** `epic:E5-service`, `phase:P2`, `type:story`, `area:service`
- **Size:** 0 (was 3) · **Depends on:** none
- **Body:** **Dropped:** the repeater is taken down (Nick, 2026-11-04). Gateway health (E5.3) covers the remaining "which box is dead" question. Close the GitHub issue. If code for repeater health already exists (BUILD.md), remove it with the MeshCore adapter.

#### E5.4 Fake gateway and ingest integration tests
- **Labels:** `epic:E5-service`, `phase:P2`, `type:story`, `area:service`
- **Size:** 3 · **Depends on:** E5.3
- **Body:**
  - [ ] Fake gateway (HTTP client) posting frame batches and heartbeats to the real app
  - [ ] Tests: normal flow, queued frames with large `age_ms`, retried batch (duplicates), bad token, bad tag, corrupt frame, wrong format byte, heartbeat loss and recovery
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
  - [ ] Off-box copy to **a Google Drive folder** (Nick, 2026-11-04) via `rclone`; upload failure visible as `backup` status (ARCHITECTURE 6.9). Nick names the folder and authorises the rclone remote

#### E5.8 Deploy to the mini PC
- **Labels:** `epic:E5-service`, `phase:P2`, `type:story`, `area:service`
- **Size:** 3 · **Depends on:** E5.1, E5.6
- **Body:** Separate compose project under `/opt/tidesvc/`, same pattern as SignBoard.
  - [ ] Port 8120 confirmed free on the mini PC (or another port chosen; configurable)
  - [ ] `deploy.sh` (rsync + `docker compose up -d --build` over Tailscale), run by Nick
  - [ ] Port 8120 reachable from the gateway's Wi-Fi; container starts with no gateway and picks up its first heartbeat without a restart
  - [ ] Container runs non-root; `.env` (link key, ingest token, SMTP, Tempest) and the rclone config hold secrets and are not committed
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
- **Body:** `NODE_SILENT`, `GATEWAY_DOWN`, `LOW_BATTERY`, `ENERGY_DEFICIT`, `ENERGY_NEGATIVE_STREAK`, `SENSOR_QUALITY`, `OUT_OF_RANGE`, `PREDICTION_UNAVAILABLE`, `CALIBRATION_DRIFT`.
  - [ ] Each rule from ARCHITECTURE 6.8 implemented with its open and clear conditions
  - [ ] `NODE_SILENT` and `GATEWAY_DOWN` (no heartbeat for 5 min) are distinct and the email says which side to look at
  - [x] Decided (Nick, 2026-11-04): `NODE_SILENT` at **30 min**; displays still go stale at 15 min. `REPEATER_SILENT` removed (no repeater)
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
  - [ ] Final firmware flashed; node provisioned (E3.5); gateway provisioned (E4.1); label on the box: no USB with cell attached
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
  - [ ] Restart the gateway and the service; re-provision the gateway's Wi-Fi; "node silent and gateway down: check the gateway, its power and Wi-Fi first"
  - [ ] Recalibrate and approve a proposed calibration; reprocess
  - [ ] Where secrets live; how to rotate the link key (node over USB, plus `tidesvc` `.env`) and the ingest token (gateway over USB, plus `.env`); restoring from the Google Drive backup
  - [ ] Nick has done at least one routine task (for example, a desiccant or battery check) from the runbook

#### E13.2 Off-box backup
- **Labels:** `epic:E13-ops`, `phase:P4`, `type:chore`, `area:service`
- **Size:** 1 · **Depends on:** E5.7, Nick naming the Drive folder
- **Body:** Location decided (Nick, 2026-11-04): a Google Drive folder.
  - [ ] Nightly copy of the SQLite backup to the Google Drive folder (rclone remote authorised by Nick on the mini PC; token not in git)
  - [ ] A restore from the Drive copy tested once

---

## 6. GitHub issues, ready to create later

**Created 2026-10-10:** all 59 stories exist as issues in the public repo (issue titles start with the plan ID, e.g. "E0.1 ..."; milestones M0-M6; labels as below). This document stays the source of the story text; the issues are the working tracker. Original note: When he does, the list below is complete enough to script. Everything in section 5 is one issue each; the **Body** text in section 5 is the issue body (user story line optional for a solo project). E12.1 goes to the SignBoard repo.

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
| E0.3 | Update BOM and architecture for the transport (repeater, then direct link) | chore, docs | M0 | 1 | E0.2 |
| E0.4 | Order parts (needs Nick's approval to spend) | chore, hardware | M0 | 1 | E0.2, E0.3 |
| E4.2 | Choose the private radio settings | spike, gateway | M0 | 2 | none |
| E1.1 | Spike S1: minimal LoRa sender that never listens | spike, firmware, risk:high | M1 | 5 | E0.4 |
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
| E3.4 | Payload v2 codec, frame, and shared golden vectors | story, firmware | M2 | 3 | none |
| E3.5 | Provisioning command and routing options | story, firmware | M2 | 3 | E1.1, E4.2 |
| E3.6 | 72-hour bench soak | story, firmware | M2 | 3 | E3.1-E3.5, E4.1 |
| E4.1 | Gateway firmware: receive, queue, forward, heartbeat | story, gateway | M2 | 5 | E0.4, E4.2, E3.4, E5.3 |
| E4.3 | Gateway placement and direct-link check | story, gateway | M2 | 3 | E4.1, E4.2, E1.1, E0.1 |
| E4.4 | 48-hour link test from the final node position | story, gateway, gate | M3 | 3 | E3.6, E4.3, E5.3 |
| E5.1 | Project skeleton, schema, and deploy scaffolding | story, service | M2 | 3 | none |
| E5.2 | Codec: decode v1, CRC, de-dup, sequence gaps | story, service | M2 | 3 | E3.4, E5.1 |
| E5.3 | Ingest endpoint: gateway HTTP POST and gateway health | story, service | M2 | 5 | E5.1, E5.2 |
| E5.4 | Fake gateway and ingest integration tests | story, service | M2 | 3 | E5.3 |
| E5.5 | Derive: level conversion, validity, and smoothing | story, service | M2 | 5 | E5.2 |
| E5.6 | API: status, level, health, history (no demo data) | story, service | M2 | 5 | E5.5 |
| E5.7 | Daily CSV export and nightly backup | story, service | M2 | 2 | E5.5 |
| E5.8 | Deploy to the mini PC | story, service | M2 | 3 | E5.1, E5.6 |
| E5.9 | Repeater health (**dropped 2026-11-04**; close the issue) | story, service | M2 | 0 | none |
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

**This is the single list of open items across the planning docs** (PRD v0.4, ARCHITECTURE v0.3, BATTERY.md v0.3, BOM v0.3 and TEST-PLAN v0.3 point here). None block starting P0. Item numbers are kept stable so existing references still work; closed items are struck through, and items added on 2026-11-04 are numbered 14-19.

**Still open, needs Nick:**
1. ~~Node-silent alert timing.~~ **Closed 2026-11-04:** 30 min (displays stale at 15).
2. ~~Off-box backup location.~~ **Closed 2026-11-04:** a Google Drive folder. Nick still names the folder and authorises the rclone remote on the mini PC (E5.7, E13.2).
3. ~~Repeater on the private frequency.~~ **Closed 2026-11-04:** the repeater is taken down.
4. **Panel type and Voc** (Nick's bench to-do, still open). The 1 W flexible amorphous panel is lower efficiency than the mono Adafruit 3809, and the architecture's eta = 0.5 was not derived for it. Its Voc is still to be measured (BATTERY.md expects about 7.7 V for a 6 V panel, well inside the BQ25185's 18 V). If it underperforms, the headline question becomes "is this particular panel enough", which E11.3 should say.
5. **26650 physical fit** in the Fibox PCB 65T (accepted on outside dimensions only; Nick's bench to-do, still open) (E0.2).
14. **Confirm dropping MeshCore entirely** (ARCHITECTURE 2.1, Q12). Architecture's call: plain RadioLib point-to-point with its own 54-byte encrypted frame. The alternative is MeshCore `GRP_DATA` framing with a MeshCore-library gateway. This is a real fork, because it reverses the 2026-10-10 MeshCore choice and the existing `tidesvc.radio` / sim code assumes MeshCore (E0.3).
15. **Gateway spot** (ARCHITECTURE Q13): distance to the ramp, height, glazing, and whether that Wi-Fi reaches the mini PC's port 8120. Without the repeater, this decides the link (E0.1, E4.3). If the direct link fails after the fallback ladder, a relay comes back as a new decision.
16. **Bioenno cell label:** planning uses 3200 mAh; read the capacity on arrival and update `energy.capacity_mah` if it differs (E0.2).

**Spec gaps (from TEST-PLAN section 11, not settled by Nick's decisions):**
6. **Minimum number of matched extremes** for a monthly calibration fit (TEST-PLAN SV-C7). Proposal needed in E6.5. (BUILD.md deviation 9 proposes 12, including both H and L.)
7. **Median rule for an even sample count** (300 samples) in firmware and server (TEST-PLAN FW-U4). Fix in one place in E3.2 / E5.5. (BUILD.md deviation 9 proposes the mean of the two middle values.)
8. ~~Cell current is not in the payload.~~ **Closed 2026-11-04:** `ibat` added (payload v2, ARCHITECTURE 4.7).
9. ~~Which temperature the firmware 0 °C rule uses.~~ **Closed 2026-11-04:** a thermistor on the battery, read by the MCU (ARCHITECTURE 4.2, BATTERY.md 3.4). `tbat` is also logged; that field is an architecture addition beyond Nick's decision (2 bytes; drop it if unwanted).
10. **Hardware unknowns to check on the bench** (BATTERY.md section 10): the Adafruit 6091's existing pull on /CE and the LED pull-up rail; Heltec V3 board revision; whether SYS stays up from the panel during a TS fault; battery-thermistor accuracy near 0 °C.
11. ~~Repeater visibility from `tidesvc`.~~ **Closed 2026-11-04:** no repeater; gateway health comes from its heartbeat (ARCHITECTURE 5.5).
17. **Link budget values are assumptions** (ARCHITECTURE 2.4): Heltec V3 delivered TX power and sensitivity, node antenna pattern next to aluminium, ramp shadowing, window loss, distance. RF-3/RF-4 replace them with measurements.
18. **FCC Part 15 basis** for a single fixed 915 MHz channel at +22 dBm (carried over from the MeshCore design, unverified); it matters most for frames over 400 ms (SF10+) (E4.2).
19. **Code is behind the docs.** `src/tidesvc`, `src/sim`, `firmware/lib/tidecore` and `tests/vectors` still implement the v0.2 design: MeshCore adapter, 26-byte payload v1, repeater health, and the die-temperature cold rule. They need the v0.3 changes (BUILD.md, "Design changes not yet in the code").

**Resolved on 2026-10-10, kept for the record:** energy alert form (14-day verdict official, 7-day early warning); PRD v0.3 written (FR1 ±5%, no ack, Q1b closed); repeater as the bridge (since superseded); Q7 cell size (26650) and charger (BQ25185) settled, CN3058E dropped; INA3221 added to the BOM.

**Resolved on 2026-11-04 (Nick):** node-silent 30 min; Google Drive backup; repeater taken down and direct LoRa point-to-point to a Wi-Fi gateway posting to :8120; cell current in the payload; battery thermistor for the 0 °C rule; plan with 3200 mAh; board mounting permission granted (per Nick, 2026-11-04); Tempest hub radio link rejected as a transport (ARCHITECTURE ADR-001).

**Notes:**
12. **The RAK WisBlock option in the BOM** is kept as a prototype path only. It would need an nRF52 port of the custom firmware (unverified) and is not planned here; the Heltec V3 + SCL3300 build is primary.
13. **Schedule risk.** As of 2026-10-10 no parts were ordered; check the current status. Today is 2026-11-04, so about four weeks remain to the end-of-November install target, and the gateway firmware (E4.1) is new work. If the install slips past about December 1, the winter test loses its worst-case weeks; E11.1 and E11.2 should note the actual install date in the report.
