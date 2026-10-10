# Product Requirements Document: LoRa Ramp Tide Sensor

**Version:** 0.3 (draft)
**Last Updated:** 2026-10-10
**Author:** Nick DeMarco, with AI assistance (product-requirements agent)
**Status:** Draft. v0.3 records Nick's later 2026-10-10 decisions (D14-D19, section 11). No PRD question remains open; remaining open items are tracked in `docs/DEV-PLAN.md` section 7.
**Sources:** `workspace/research/SPEC.md` (build spec v0.1), `workspace/research/README-seed.md` (both 2026-10-10); Nick's decisions in chat, 2026-10-10; `docs/ARCHITECTURE.md` v0.2 answers log; `docs/BATTERY.md` v0.2

**Changes in v0.3 (2026-10-10):** Q1b closed (Nick's solar PVC-tube repeater bridges the ramp to the gateway; flood routing; private frequency and encrypted channel). FR1 timing relaxed to 5 min ±5%, no ack/retry. FR4: email only, repeater-silent health alert, optional Tempest surge-watch (station 183092, SignBoard's token, accepted defaults). FR5: port 8120, nightly SQLite backup to a second location (TBD). FR6: the 14-day deficit verdict is the official answer; 7 consecutive negative days is an early-warning email. Energy and cold-weather NFRs aligned with ARCHITECTURE v0.2 and BATTERY.md (BQ25185, 26650, 130k ∥ B3435 NTC with firmware 0 °C rule). Scope, risks, phasing and dependencies updated for the repeater.

---

## 1. Overview

### 1.1 Problem
The pilot marina in Monmouth Beach, NJ has no observed water-level data. The nearest NOAA station, 8531942 Long Branch Reach, is a subordinate station: it publishes predicted highs and lows only. Nobody at the marina can see the actual water level right now, how far it differs from the prediction (storm surge or wind setup), or how quickly it is rising.

### 1.2 Product
A battery- and solar-powered LoRa sensor node mounted under a bulkhead-to-float gangway ramp. The node measures the ramp's tilt angle and sends it over **MeshCore**. Because the ramp is hinged at the bulkhead and its free end rides on a float that moves with the water, a server can convert the angle into water level using `h = h0 + L·sin(θ − θ0)`. The server runs on the mini PC that hosts SignBoard. It compares the level with NOAA predictions, raises alerts on surge or rapid rise, and exposes everything through an HTTP JSON API that SignBoard, Home Assistant, and any other client can read.

### 1.3 Nature of the pilot
This is **Nick's hobby project and a test**, not a commercial product. The main question the pilot has to answer is: **is the small vertical south-face solar panel big enough to keep the node running, especially through winter?** Water-level accuracy and surge alerting matter, but they come second to that answer.

### 1.4 Goals
- G1 (headline): Find out, with logged evidence, whether the south-face panel keeps the node energy-neutral through a NJ winter.
- G2: Show the actual water level at the marina, continuously, with credible accuracy.
- G3: Show the residual (actual minus predicted) so surge is visible as it builds.
- G4: Alert when the residual or the rate of rise crosses a threshold.
- G5: Run unattended, with a short runbook so Nick can maintain it without re-deriving how it works.

---

## 2. Decisions already made (not open for re-litigation in this PRD)

| # | Decision | Source |
|---|---|---|
| D1 | **Measurement method: ramp tilt** (inclinometer), chosen as the most robust option. A pressure sensor is an optional, temporary validation unit only. | README-seed, SPEC §1, §2 |
| D2 | **Concealed install.** The enclosure is tucked under the ramp. A small solar panel is bonded flat to the **south-facing aluminum side face** (the ramp runs east-west). The antenna is a short stub standing 2-3 cm off the metal on the same face. | SPEC §3 (Nick, 2026-10-10) |
| D3 | **Power: battery plus solar.** No dock shore power, which was considered and rejected because it needs an electrician and a GFCI circuit. | SPEC §3, README-seed |
| D4 | **A LoRa receiver is required.** There is no LoRa equipment at the marina today. | README-seed |
| D5 | **The Tempest weather hub cannot be used as the LoRa receiver.** | README-seed |
| D6 | **Reference data: NOAA 8531942** predicted hi/lo (MLLW datum, metric). Ocean gauge 8531991 and Sandy Hook 8531680 (about 2 h 18 m lag) are used for sanity checks. | SPEC §5, §6 |
| D7 | **Pilot site:** a single 25 ft Meeco Sullivan ramp at the pilot marina, mounted at midspan on a stringer, with the sensor axis along the ramp. | SPEC §3, README-seed |
| D8 | **Transport: MeshCore.** Not raw LoRa point-to-point and not LoRaWAN. Receiving side resolved by D14. | Nick, chat 2026-10-10 |
| D9 | **Owner and sponsor: Nick.** Hobby project and test, not commercial. Nick is the user and owner, which satisfies the CLAUDE.md "transfer ownership to the actual user" condition. There is no dockmaster or association handover. | Nick, chat 2026-10-10 |
| D10 | **Mounting permission: granted.** Nick has permission to mount on the ramp. | Nick, chat 2026-10-10 |
| D11 | **Data sink: the mini PC that runs SignBoard**, exposing an **HTTP API (JSON)**. Home Assistant, SignBoard, and anything else are consumers of that API. Home Assistant is not in the required path. | Nick, chat 2026-10-10 |
| D12 | **Pilot purpose: a solar-sufficiency test.** The headline success metric is whether the small south-face panel is enough (especially in winter, mounted vertically). The node's battery and charge telemetry is logged to answer it. | Nick, chat 2026-10-10 |
| D13 | **Non-commercial; patent is not a gate.** Prior patent US11371841B2 (ramp-tilt tide gauge) reportedly lapsed for unpaid maintenance fees on 2026-08-03. This is non-commercial hobby use. | Nick, chat 2026-10-10 |
| D14 | **Relay: Nick's existing solar PVC-tube MeshCore repeater** (RAK4631 + RAK19007) bridges the ramp node to the gateway radio on the mini PC. The node uses **flood** routing. The repeater's own power budget is outside this pilot's solar test; the pilot tracks only whether it is alive. | Nick, 2026-10-10 (ARCHITECTURE Q1) |
| D15 | **Radio: private frequency and encrypted private channel**, the same settings on node, repeater and gateway. No use of the public US MeshCore preset. | Nick, 2026-10-10 (ARCHITECTURE Q2) |
| D16 | **Reporting: every 5 min, timing ±5%, no ack or retry.** Loss is measured from sequence numbers. The node never listens, so changing the interval means reflashing. | Nick, 2026-10-10 (ARCHITECTURE Q8) |
| D17 | **Server: HTTP API on port 8120** (configurable); **nightly SQLite backup** to a second location (location TBD by Nick); **alerts by email only** (push deferred). | Nick, 2026-10-10 (ARCHITECTURE Q5, Q9, Q10) |
| D18 | **Tempest (optional input): station 183092 with SignBoard's token.** Surge-watch defaults accepted: onshore wind 20-140°, ≥ 8 m/s for 6 h; pressure falling 3 hPa in 3 h. Tune after the first storm season. | Nick, 2026-10-10 (ARCHITECTURE Q3, Q4) |
| D19 | **Power hardware:** 26650 LiFePO4; TI BQ25185 charger (Adafruit 6091); Heltec fed through an LM66100 ideal diode; 10k B3435 NTC with 130 kΩ in parallel (hardware stop about -3 °C, resume about +2.4 °C) and **firmware enforces the 0 °C charge rule**; a second 1 W flexible amorphous panel of the repeater's type. Details in `docs/BATTERY.md`. | Nick, 2026-10-10 |

---

## 3. Users and ownership

### 3.1 Users
| User | Need | Touchpoint |
|---|---|---|
| Nick (owner, sponsor, operator) | Answer the solar question; check health (battery, charge, link, staleness, calibration drift); receive alerts | HTTP API, health view, alerts, runbook |
| Boat owners and residents | Current level and trend: can I get out or back in, is the ramp steep? | SignBoard tide panel (an API consumer) |
| Other consumers (Home Assistant, scripts) | Read current and historical data | HTTP JSON API |

### 3.2 Ownership
Nick owns, sponsors, and operates the system (D9). No handover to the dockmaster or the association is required. To keep the system maintainable without re-learning it each time, the project delivers:

1. **A short runbook** covering: reading the health view; what each flag means (low battery, high stddev, out of range, reboot, stale, charge inhibited); swapping the battery or desiccant; restarting the receiver and server; and recalibrating.
2. **Automatic recalibration** (monthly fit against NOAA hi/lo, per SPEC §6), so routine operation needs no manual work.
3. **Health alerts to Nick**, including a node-silent / stale-data alert.

---

## 4. Scope

### 4.1 In scope (pilot)
- One sensor node on one ramp (hardware per SPEC §2, firmware per SPEC §4), sending over MeshCore (D8).
- One MeshCore gateway radio connected to the mini PC, reached through Nick's solar repeater (D14). The repeater itself is Nick's existing design; this project configures it and monitors its liveness.
- A server pipeline on the SignBoard mini PC: decode, store raw, convert to level, smooth, fetch NOAA predictions, compute residual, alert, serve the HTTP JSON API.
- **Power telemetry logging and a solar-sufficiency report** (FR6).
- Install-time calibration and automatic monthly recalibration.
- A daily CSV export.
- Health monitoring, explicit error and stale states, and a short runbook.

### 4.2 Non-goals
- Not an official or navigational tide gauge. It carries no NOAA/NWS certification and no safety-of-life use.
- No dock shore power (D3).
- No public-internet exposure of the API or third-party data sharing in the pilot.
- No commercial product, kit, or sale. This is non-commercial hobby use; the prior patent reportedly lapsed (D13).
- No pressure sensor as the primary sensor (D1).
- No Home Assistant dependency (D11). HA may consume the API, but nothing requires it.
- No second ramp until the pilot exit criteria are met (section 9).
- No solar-sufficiency measurement of the repeater. Its power budget is a separate concern (D14).

---

## 5. Functional requirements

### FR1. Tilt measurement and transmission (node)
As the system, I need a tilt reading every 5 minutes so that level can be computed at a useful resolution.
- [ ] Wakes every 5 min (±5%; D16), samples 300 readings at 100 Hz, and reports median pitch, pitch stddev, sensor temperature, and the power telemetry in FR6.
- [ ] Sends over MeshCore (D8) on the private frequency and encrypted channel (D15), flood-routed through the repeater (D14). The payload carries node id, sequence number, the fields above, flags (low battery, high stddev, out of range, reboot, charge inhibited), and an integrity check. SPEC §4 sized a raw-LoRa packet at ~12 bytes; architecture sets a 26-byte versioned payload (ARCHITECTURE 4.7).
- [ ] No ack and no retry (D16). Sequence numbers let the server detect and count lost packets.
- [ ] Sets the out-of-range flag when tilt falls outside the calibrated envelope (ramp lifted off, or float grounded).

### FR2. Level conversion and residual (server)
- [ ] Stores every decoded packet raw, and never discards raw data. It is needed for storm analysis and the solar report.
- [ ] Converts pitch to level (MLLW, metres) with the current calibration (θ0, effective L, h0).
- [ ] Produces a smoothed level (30-min rolling median by default, configurable) alongside the raw level.
- [ ] Fetches NOAA 8531942 hi/lo predictions and interpolates between extremes with a half-cosine curve.
- [ ] Computes residual = smoothed level minus predicted level, and computes rate of rise.

### FR3. Calibration
- [ ] Install procedure: a level-ramp pitch reading plus tape-measured freeboard at a fixed bulkhead mark, at two different tide states. Fit θ0 and effective L.
- [ ] Automatic monthly refit of offset and scale against NOAA predicted highs and lows. The run is logged, and a change beyond a set bound alerts Nick instead of being applied silently.
- [ ] Calibration history is versioned, so raw data can be reprocessed.

### FR4. Alerting
- [ ] Residual (surge) alert: warning at **≥ +0.3 m**, severe at **≥ +0.6 m** (configurable).
- [ ] Rate-of-rise alert at **≥ 0.15 m/h above predicted** (configurable).
- [ ] Health alerts: node silent longer than 15 min, repeater silent (so a dead repeater is distinguishable from a dead node), low battery, repeated high stddev, out of range, NOAA fetch failure, the 14-day energy-deficit verdict, and the 7-day negative-balance early warning (FR6).
- [ ] Optional advisory surge-watch from the Tempest (D18): residual ≥ +0.15 m and either pressure falling ≥ 3 hPa in 3 h or onshore wind (20-140°) ≥ 8 m/s for 6 h. Evaluated only when Tempest data is available; Tempest is never in the required path.
- [ ] Alerts go to Nick by email only (D17).
- [ ] Alerts are de-duplicated, and each one states its own clearance condition.
- Thresholds are accepted defaults (Q4), to be tuned after one storm season.

### FR5. Publishing (HTTP JSON API)
- [ ] The mini PC serves an HTTP API on port 8120 (configurable; D17) returning JSON: current level (raw and smoothed), trend / rate of rise, predicted level, residual, data age, node health, and power telemetry. Historical queries over a time range are supported.
- [ ] SignBoard, Home Assistant, and any other client read from this API. No consumer is in the required path for the system to run.
- [ ] Writes a daily CSV of raw and smoothed data, including power telemetry.
- [ ] Backs up the SQLite database nightly, locally and to a second location (location TBD by Nick; D17).
- [ ] **No demo fallback.** If data is stale, the node is silent, or the NOAA fetch fails, the API reports an explicit error or stale state with the time of the last good reading. It never returns predicted-only values or placeholder numbers presented as observations.

### FR6. Power telemetry and solar-sufficiency report (headline)
As Nick, I want the node's energy behavior logged every cycle so that I can tell whether the south-face panel is big enough, especially in winter.
- [ ] Each packet carries battery voltage plus charge telemetry sufficient to tell whether, and roughly how much, the panel is charging: at minimum charger status (charging / not charging / charge inhibited by low temperature) and a solar-input measure (panel voltage and current). Fields are set in ARCHITECTURE 4.7 against the BQ25185 status pins and the INA3221.
- [ ] The low-temperature charge cutoff (Q5, D19) is logged as a distinct state, so "no sun" and "too cold to charge" can be told apart.
- [ ] The server stores all power telemetry raw and computes daily figures: minimum and end-of-day battery voltage, hours of charging, hours charge-inhibited, and an estimated daily net energy balance.
- [ ] The API exposes a solar-sufficiency view: daily figures over any date range, the trend through winter, and estimated days of autonomy remaining at current state of charge.
- [ ] **Official answer:** a rolling 14-day energy verdict (harvest / consumption: surplus ≥ 2, marginal 1-2, deficit < 1). A deficit verdict raises a health alert to Nick.
- [ ] **Early warning:** 7 consecutive days of negative net energy balance sends an early-warning email. It does not change the verdict.

---

## 6. Non-functional requirements

| Area | Requirement | Basis |
|---|---|---|
| Resolution | ≤0.01° pitch noise after per-cycle averaging (≈1.3 mm) | SPEC §1 |
| Accuracy | Smoothed level within **±5 cm** of reference (tape-measured freeboard and NOAA hi/lo). Stretch goal **±2 cm**. Accepted default. | SPEC §1 (±2-5 cm real-world) |
| Freshness | Reading every 5 min. The API marks data stale after 15 min (3 missed packets). Accepted default (Q8). | SPEC §4 |
| Link reliability | ≥95% end-to-end packet delivery over MeshCore through the repeater, measured over the shakedown. Link margin (≥ 10 dB over the chosen spreading factor's floor, on each hop) is verified **before** anything is bonded. | SPEC §7, ARCHITECTURE 5.4 |
| Energy | Average load ≈11-12.5 mAh/day nominal, 25 mAh/day design budget (ARCHITECTURE 4.4; SPEC's ≈17 mAh/day superseded), to be measured on the bench. Target: energy-neutral year-round on a **1 W** south-face panel (flexible amorphous, D19), surviving **≥14 days with no solar input**. Accepted default (Q6). Whether this holds is the pilot's headline question (section 7). | SPEC §3, §4 |
| Cold weather | **LiFePO4** battery (26650) with a **BQ25185** charger. The cell never charges below 0 °C: firmware enforces the rule, and the charger's NTC (B3435 with 130 kΩ in parallel) is a hardware backstop at about -3 °C (D19). Accepted default (Q5). | SPEC §2, BATTERY.md |
| Environment | IP67 enclosure, conformal-coated boards, desiccant, cable glands, drip loops. Galvanic isolation between stainless and aluminum. | SPEC §2, §3 |
| Install integrity | Reversible, no-drill install (bonded or clamped), to stay clear of the new ramps' manufacturer warranty. | SPEC §7 |
| Concealment | Not visible from the deck surface. Panel and antenna are low-profile on the south side face. | D2 |
| Data retention | Raw data, including power telemetry, kept indefinitely (small volume: ~105k packets per year). | SPEC §5 |

---

## 7. Success metrics (pilot)

**Headline: solar sufficiency (D12).**
1. **Through the first winter (December-February), the node never browns out or stops reporting for lack of energy, and the logged daily energy balance shows the panel covers the load**, with battery voltage recovering after cloudy spells. The pilot passes on the solar question if this holds; a clear "no" backed by the telemetry is also a valid outcome of the test, because it answers the question and sizes the fix.

Supporting:
2. Two-week shakedown: smoothed level tracks NOAA predicted hi/lo times within ±15 min and heights within ±5 cm on calm-weather days.
3. ≥95% of expected packets received across the shakedown and the first 90 days.
4. At least one weather event where the residual shows a surge consistent with 8531991 / Sandy Hook, after accounting for the lag.
5. The runbook exists and Nick has used it for at least one routine task (for example, a desiccant or battery check).

---

## 8. Risks and constraints

| Risk / constraint | Impact | Mitigation / status |
|---|---|---|
| **Vertical south panel in winter** (low sun, short days), shading by piles or boats | Energy deficit; this is the pilot's main question | Log power telemetry every cycle (FR6); 14-day autonomy target; site shading check; bench energy measurement. |
| **Low-temperature charge cutoff** stops charging on cold sunny mornings | Less winter charging than sun hours suggest | Log charge-inhibit as its own state (FR6) so its effect is measurable. The 130 kΩ NTC shift plus a firmware +1/+2 °C rule avoids the stock charger's +6 °C restart (BATTERY.md 4.4). |
| **Repeater failure** (its own solar power, outside this pilot's test) | Node looks dead though it is fine | Repeater liveness tracked from the gateway (relayed frames, adverts); a repeater-silent alert is distinct from node-silent (FR4). |
| MeshCore radio duty and airtime differ from the raw-LoRa assumptions in SPEC §4 | Energy budget and packet design may change | Re-measure awake current and airtime on the bench with MeshCore firmware (Phase 1). |
| Dock manufacturer warranty (Meeco Sullivan; ramps are new) | Attaching hardware could void it | Reversible, no-drill install (section 6). Mounting permission itself is granted (D10). |
| RF shielding by the aluminum frame and bulkhead | Packet loss | Antenna stub on the outer face. Range test before bonding. The repeater bridges the ramp to the gateway (D14). |
| Float freeboard changes with load, wakes, and foot traffic | Noise, few-cm error | Rolling median, stddev flag, monthly refit. |
| Ramp lifts off or float grounds | Invalid reading | Out-of-range flag. Reading is excluded from level and alerts. |
| Salt corrosion, bird fouling, vandalism | Hardware failure | IP67, conformal coat, concealment, galvanic isolation. |
| Ramp geometry assumed (L ≈ 7.62 m) | Scale error | Confirm from Meeco Sullivan drawings and a site visit. Calibration fits effective L regardless. |
| Mini PC outage | No data served, alerts stop | Node keeps transmitting; the API and consumers show an explicit stale/error state on recovery gap. Runbook covers restart. |

**Patent note:** US11371841B2 reportedly lapsed for unpaid maintenance fees on 2026-08-03; this is non-commercial hobby use (D13).

**Seed inconsistencies, resolved:** the BOM listed a 2 W / 6 V panel "on top of ramp or railing"; this PRD follows D2 (south side face) with a 1 W panel (Q6 default). The BOM's open choices resolve to SCL3300 (Q9) and LiFePO4 (Q5).

---

## 9. Phasing

| Phase | Content | Exit criteria |
|---|---|---|
| **0. Site** | Ramp drawings and site visit; shading check on the south face; repeater and gateway antenna spots noted; private radio settings chosen | L, hinge, and stringer confirmed; repeater location chosen |
| **1. Bench** | MCU, SCL3300, LiFePO4 charger, and MeshCore firmware on a tilt rig: noise, temperature drift, energy, telemetry fields | ≤0.01° noise; measured awake current/airtime within budget; FR6 telemetry reporting correctly |
| **2. Repeater, gateway and range test** | Repeater and gateway radio at their planned locations, gateway connected to the mini PC; node at the ramp in its final antenna position | Link margin verified on each hop; ≥95% end-to-end delivery over 48 h |
| **3. Single-node pilot** | Install, calibrate, 2-week shakedown, then API, SignBoard panel, and alerts live | Section 7 metrics 2-3 |
| **4. Winter test** | Run through December-February with power telemetry logged; runbook written | Section 7 metric 1 answered (yes or no, with data); metric 5 |
| **5. Expansion (later)** | Optional pressure-sensor validation week; second ramp. A second ramp adds redundancy and cross-checks on freeboard/load error. | Pilot through one winter (metric 1) |

---

## 10. Dependencies and assumptions
- **Dependencies:** NOAA CO-OPS datagetter API (prediction source; if it is unavailable, residual shows an error state, not stale or invented predictions); the SignBoard mini PC (host for the server and API); Nick's solar MeshCore repeater (D14) and a USB MeshCore gateway radio on the mini PC.
- **Assumptions:** the ramp is hinged at the bulkhead with its free end on the float, and the relationship between tilt and level is linear to within ~1% across the 6-7.5° swing; the local tide range is ≈0.8-1.0 m; MeshCore on US915 is license-free at the chosen power; SignBoard (live at the pool and office kiosks) can consume the API for a tide panel; the BQ25185 status pins plus the INA3221 report charge status and panel input (BATTERY.md, to be bench-verified).

---

## 11. Open questions

### 11.1 Still open

None owned by the PRD. Remaining open items (for example the node-silent alert timing, the off-box backup location, and spec gaps found by the test plan) are tracked in one place: `docs/DEV-PLAN.md` section 7.

Handled in architecture as design work: MeshCore payload encoding (FR1), the exact power-telemetry fields (FR6), and the HTTP API schema (FR5); see ARCHITECTURE v0.2.

### 11.2 Resolved

| # | Question | Resolution | How |
|---|---|---|---|
| Q1a | Transport: raw LoRa, LoRaWAN, or MeshCore? | **MeshCore** (D8) | Nick, 2026-10-10 |
| Q1b | Receiver placement | **Nick's solar PVC-tube repeater bridges the ramp to a USB gateway radio on the mini PC**; flood routing; private frequency and channel (D14, D15) | Nick, 2026-10-10 |
| Q2 | Who is the operational owner? | **Nick** owns and sponsors it; hobby project and test. No dockmaster/association handover. Short runbook kept (D9, section 3.2). | Nick, 2026-10-10 |
| Q3 | Data sink: Home Assistant, SignBoard, or both? | **HTTP JSON API on the SignBoard mini PC.** SignBoard, HA, and others are consumers; HA not in the required path (D11). | Nick, 2026-10-10 |
| Q4 | Alert thresholds, recipients, channel | Residual ≥ +0.3 m warning / ≥ +0.6 m severe; rate of rise ≥ 0.15 m/h above predicted; email only to the owner (Nick; D17). Tempest surge-watch defaults accepted (D18). Tune after one storm season. | Accepted default; Nick 2026-10-10 |
| Q5 | Battery chemistry | **LiFePO4** (26650) with low-temperature charge cutoff: firmware 0 °C rule plus BQ25185 NTC backstop (D19). | Accepted default; Nick 2026-10-10 |
| Q6 | Energy target and panel size | ≥14 days of autonomy; **1 W** panel (flexible amorphous, same type as the repeater's; Voc to be measured); verified by site shading check and bench measurement. Whether it is enough in winter is the pilot's headline test (D12). | Accepted default; Nick 2026-10-10 |
| Q7 | Mounting permission and warranty | **Permission granted** (D10). Install stays reversible and no-drill. | Nick, 2026-10-10 |
| Q8 | Display behavior | 30-min rolling median shown; raw kept. Stale after 15 min (3 missed packets). | Accepted default |
| Q9 | Sensor part | **SCL3300**; revisit only if the bench test with both parts on hand says otherwise. | Accepted default |
| Q10 | Commercial intent | **Non-commercial hobby use.** Patent reportedly lapsed; not a gate (D13). | Nick, 2026-10-10 |
| Q11 | Pressure-sensor validation unit | Deferred to Phase 5. Pilot accuracy uses tape-measured freeboard and NOAA hi/lo. | Accepted default |
| — | Accuracy targets | ±5 cm smoothed vs reference; stretch ±2 cm (section 6). | Accepted default |
| — | Report timing, ack, port, backup, Tempest | 5 min ±5%, no ack/retry (D16); port 8120, nightly backup, email only (D17); Tempest 183092 with SignBoard's token (D18) | Nick, 2026-10-10 |
| — | Energy alert form | 14-day deficit verdict is official; 7 consecutive negative days is an early warning (FR6) | Nick, 2026-10-10 |

---

## 12. Revision history

| Version | Date | Author | Changes |
|---|---|---|---|
| 0.1 | 2026-10-10 | product-requirements agent | Initial draft from seed SPEC v0.1 and README-seed |
| 0.2 | 2026-10-10 | product-requirements agent | Recorded Nick's chat decisions: MeshCore transport; Nick as owner/sponsor (hobby, non-commercial; handover requirements dropped, runbook kept); mounting permission granted; HTTP JSON API on the SignBoard mini PC as the data sink; solar sufficiency as headline metric with new FR6 power telemetry; patent no longer a gate. Accepted PRD defaults for Q4-Q6, Q8, Q9, Q11 and accuracy. Split open questions into still-open (Q1b receiver placement) and resolved. |
| 0.3 | 2026-10-10 | software-architecture agent (doc reconciliation) | Recorded D14-D19 (repeater bridge, private radio, 5 min ±5% no ack, port/backup/email, Tempest, power hardware); Q1b closed; FR1, FR4, FR5, FR6 and NFRs updated; open items moved to DEV-PLAN section 7. |
