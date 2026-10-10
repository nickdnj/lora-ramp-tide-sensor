# Bill of Materials: one ramp node + gateway (draft, 2026-10-10)

**Version:** 0.2, 2026-10-10

**Changes in v0.2 (2026-10-10):** power rows (3-5) taken from `docs/BATTERY.md` (26650 LiFePO4, BQ25185 on Adafruit 6091, B3435 NTC with 130 kΩ in parallel); added the INA3221, LM66100 ideal diode and the BATTERY.md small parts; panel row notes the Voc check; enclosure row records the 26650 fit (still to be physically verified); WisBlock path marked as needing an nRF52 firmware port (unverified), Heltec V3 + SCL3300 recommended as the primary build; new Repeater section for Nick's solar PVC-tube repeater; gateway antenna no longer depends on Q1b; open items updated.

Status: working draft for Nick's review. Nothing ordered. Prices are from search results, not quotes; confirm on the seller page. Source of truth for design intent is `docs/PRD.md` v0.3 and `docs/ARCHITECTURE.md` v0.2; the power subsystem source is `docs/BATTERY.md`.

## Node (on the ramp)

**Primary build: Heltec V3 + SCL3300** (per ARCHITECTURE, ADR-001 and ADR-005).

| # | Part | Pick | Where | ~$ | Status |
|---|---|---|---|---|---|
| 1 | MCU + LoRa radio | Heltec WiFi LoRa 32 V3, US915 (ESP32-S3 + SX1262), runs custom firmware with MeshCore as a library | [Rokland](https://store.rokland.com/products/heltec-wifi-lora-32v3), [Hackster](https://hackster.io/products/buy/116383) | 27-30 | Chosen. Note the board revision (BATTERY.md 3.1 used the V3.2 schematic). |
| 2 | Inclinometer | Murata SCL3300 breakout (SPI) | [LogicalEdges on Tindie](https://www.tindie.com/products/led/scl3300-0001-inclinometer-tilt-sensor-breakout/) | 40-60 | Accepted default. Third-party board; verify specs against Murata datasheet. Murata's own eval board needs an extra interface board. Alternative: ADXL355. |
| 3 | Battery cell | **26650 LiFePO4, 3.2 V, about 3300 mAh, unprotected** (Bioenno Power 4-pack), plus a 26650 holder or a tabbed cell with a soldered pigtail | [bioennopower.com](https://www.bioennopower.com/products/26650-3-2v-3200-mah-2c-lifepo4-cells-4-pcs) (BATTERY.md B1, B7) | 30 (4-pack) + 3-6 | Chosen (BATTERY.md). Unprotected: protection is the charger, a 1 A fuse (row 15) and an optional PCM. Stock not confirmed. |
| 4 | Charger | **TI BQ25185 on Adafruit 6091**: cut VS jumper and close the 3.65 V (LiFePO4) jumper; 250 mA ISET; cut the TH trace; 1 MΩ pull-up from /CE to SYS (charging off unless the MCU enables it). Buy 2. | [Adafruit 6091](https://www.adafruit.com/product/6091), [TI](https://www.ti.com/product/BQ25185) | 14 (2) | Chosen (BATTERY.md section 4). TH pad access confirmed from the Adafruit guide. Cold thresholds are calculated, not measured (BATTERY T2). |
| 5 | Cell NTC + parallel resistor | 10 kΩ NTC, **B25/85 = 3435 K** (Semitec 103AT-2 class), bonded to the cell can; **130 kΩ 1% in parallel** (hardware stop about -3 °C, resume about +2.4 °C; firmware enforces 0 °C) | Digi-Key / Mouser | 3-6 | Chosen (Nick, 2026-10-10). Do not use a B3950 part (shifts the window about 3 °C warmer). |
| 6 | Solar panel | **Decided 2026-10-10: same 1 W flexible amorphous type Nick bought for the repeater (second unit of the same model).** Adafruit 3809 below is the fallback (out of stock per BATTERY.md). 6 V, 1 W, IP67 | [Adafruit 3809](https://adafruit.com/product/3809); silicone alt [Soldered 108763](https://www.mouser.com/catalog/specsheets/Soldered_108763%20solar%20panel%201w%206v.pdf) | 10-15 | Accepted default (1 W). Nick buys. **Open-circuit voltage to be measured.** BATTERY.md: a 6 V panel at about 7.7 V Voc is well inside the BQ25185 input (3.6-18 V operating, 25 V abs max). The pilot's main question is whether this is enough. |
| 7 | Antenna | Doodle Labs ANT-915-3-O, 3 dBi, IP67, SMA male pigtail | [datasheet](https://mouser.com/datasheet/2/895/Doodle_432024_ANT_915_3_O_Datasheet-3436791.pdf) | 15-25 | Best match found; not a bulkhead mount, so bracket it 2-3 cm off the south face. Check SMA vs RP-SMA against the Heltec board. |
| 8 | Enclosure | IP67 polycarbonate, small, with glands | [Fibox Piccolo PCB 65T](https://cpcireland.farnell.com/fibox/pcb-65t/fibox-piccolo-transp-110x80x65mm/dp/EN81977), [RND 455-01069](https://www.distrelec.ch/en/plastic-enclosure-65x115x40mm-light-grey-polycarbonate-ip67-rnd-rnd-455-01069/p/30129921) | 15-25 | **Fibox PCB 65T** takes the 26650 by outside dimensions (BATTERY.md 2.3); physical test-fit still required. RND is tight in height. Both European listings; need a US source and gland options confirmed. |
| 9 | Bracket and hardware | 316 SS or aluminum angle, nylon isolating washers, dielectric paste | hardware store | 10 | Reversible install, no drilling (dock warranty precaution). |
| 10 | Bonding | VHB-type tape for the panel on the south face | hardware store | 8 | |
| 11 | Cable glands, desiccant, conformal coat, wire | misc | any | 10-15 | |
| 12 | Power telemetry | **TI INA3221 3-channel V/I breakout (I2C)**: ch1 panel input, ch2 cell side (ARCHITECTURE 4.2, BATTERY.md 3.4) | Adafruit / SparkFun / other breakout (part number to confirm) | 8-12 | Needed for FR6. Was missing from v0.1. Check the shunt value suits about 0-250 mA. |
| 13 | Ideal diode | TI LM66100DCKR + SC-70-6 adapter board, or LM66100EVM: charger SYS → LM66100 → Heltec JP1 | [TI](https://www.ti.com/product/LM66100), Digi-Key (BATTERY.md B5) | 2-15 | Chosen. Blocks the Heltec's 4.2 V onboard charger from the cell. Still: no USB with the cell attached until bench test T6 passes. |
| 14 | Pigtails | JST-PH 2-pin (charger battery) and **1.25 mm 2-pin** (Heltec JP1); meter-check polarity | Adafruit / any (BATTERY.md B8) | 5 | |
| 15 | Fuse | 1 A fast inline, or 0.5-0.75 A-hold PTC, within 2 cm of the cell + | any (BATTERY.md B6) | 3 | |
| 16 | Breather vent | ePTFE screw-in vent sized to the enclosure | Digi-Key (BATTERY.md B9) | 5-10 | |
| 17 | Optional LFP PCM | 1S LiFePO4 protection board with stated thresholds | BATTERY.md section 7, B10 | 3-30 | Optional; no US source confirmed. |

Node subtotal: about $190-270 (rough; adds the INA3221, LM66100 and BATTERY.md small parts to the v0.1 estimate of $150-210; the cell and charger lines buy spares).

## Prototype option: RAK WisBlock (plug-together, no wiring)

Added 2026-10-10 at Nick's request. **Kept as an option only; the recommended primary build is the Heltec V3 + SCL3300 node above, per ARCHITECTURE.** The project's custom push-and-deep-sleep firmware is written for the ESP32-S3 (Heltec V3). Using the RAK4631 (nRF52840) **would need an nRF52 port of that firmware; this is unverified** and not in the dev plan.

Same node role as the table above, built from snap-together modules. Consumer-grade accelerometer, so expect temperature drift of a few cm of apparent level per day-night swing (typical datasheet behavior, not measured on this build). Handle by logging sensor temperature, compensating in the server, and monthly NOAA recalibration. The tide cycle itself (about 1 m swing) is far larger than the drift.

| # | Part | Pick | Where | ~$ | Status |
|---|---|---|---|---|---|
| W1 | Core | RAK4631 (nRF52840 + SX1262) | [RAK store](https://store.rakwireless.com/) | 25-30 | MeshCore README lists RAK4631 as supported; verify against the official repo. Custom firmware needs an nRF52 port (unverified). |
| W2 | Base board | RAK5005-O (or current WisBlock base) | RAK store | 10-15 | **Cannot charge LiFePO4 and has no cold cutoff; solar input abs max 5.5 V** (BATTERY.md section 5). Leave its solar connector empty. |
| W3 | Accelerometer module | RAK1904 (ST LIS3DH, I2C) | [RAK1904](https://store.rakwireless.com/products/rak1904-lis3dh-3-axis-acceleration-sensor) | 5-10 | Prototype grade. Check RAK's range for a better tilt module before ordering. |
| W4 | Enclosure | RAK Unify IP65, 100x75x38 mm (solar variant has a built-in 80x45 mm lid panel) | [datasheet](https://docs.rakwireless.com/product-categories/wisblock/rakbox-uo100x75x38-solar/overview/) | 25-35 | Verify board, module and battery fit. Its small panel is weaker than the planned 1 W south-face panel. |
| W5 | Battery, panel, antenna, charger | as in the node table (LiFePO4 cell, 1 W panel, Doodle antenna) **plus the same external BQ25185 charger** | see above | | Per BATTERY.md section 5: the WisBlock base cannot charge LiFePO4. Use the BQ25185, feed the RAK battery input from the **cell side through an LM66100** (not from SYS, which reaches 4.5 V vs the RAK's 4.3 V max). RAK operation at 3.2-3.3 V LFP is unverified. |

Unverified: whether MeshCore on the RAK4631 can read an I2C sensor and send it as telemetry, and the nRF52 port of the custom firmware.

## Gateway (mini PC where SignBoard runs)

| # | Part | Pick | Status |
|---|---|---|---|
| G1 | MeshCore-capable LoRa radio on USB-serial | a second Heltec V3 (or similar) running MeshCore companion firmware | Chosen (ARCHITECTURE ADR-002). Set to the project's private frequency and channel. |
| G2 | Antenna for the gateway | 915 MHz, placed within range of the repeater | Placement is no longer a blocker: the repeater bridges the ramp to the gateway (Q1 / PRD Q1b resolved). |
| G3 | Software | ingest service, SQLite, HTTP JSON API | Per `docs/ARCHITECTURE.md`. |

## Repeater (bridge between the ramp node and the gateway)

Nick's own solar PVC-tube MeshCore repeater, designed 2026-09-29 (designed 2026-09-29). **Already owned/planned by Nick, listed here for completeness, not a cost of this project.** As of 2026-09-29 the parts were listed but not purchased; confirm build status.

| # | Part | Pick | Status |
|---|---|---|---|
| R1 | Repeater core and base | RAK4631 (nRF52840 + SX1262) on RAK19007 | Planned (Nick). Runs stock MeshCore repeater firmware, set to the project's private frequency, SF, BW and CR. |
| R2 | Repeater power | 2x Nitecore NL1835 protected 18650 Li-ion in parallel; Adafruit 4755 (bq24074) charger with 10K NTC cold cutoff; RAK fed straight from the cells | Planned (Nick). **Its power budget is a separate concern, outside this project's solar test.** |
| R3 | Repeater panel | 1 W flexible amorphous panel wrapped on 1-1/2" PVC (same type as node row 6) | Planned (Nick). |
| R4 | Repeater antenna and housing | ALFA 915 MHz omni, N-male, on the PVC tube cap | Planned (Nick). About $208 for the whole repeater per the 2026-09-29 manual. |

## Optional

| Part | Why |
|---|---|
| MS5837 / Blue Robotics Bar30 pressure sensor on a pile | one-week validation of the tilt-derived level |
| WeatherFlow Tempest (already installed) | optional software-only input: pressure, wind, rain via REST (station 183092, SignBoard's token) |
| Bench gear: USB power meter / current logger | measure real duty-cycle energy against the 25 mAh/day design budget (ARCHITECTURE 4.4) |

## Open items before ordering

1. ~~Verify BQ25185 breakout temperature pin and thresholds.~~ TH pad confirmed (BATTERY.md 4.1). Thresholds are calculated; measure on the bench (BATTERY T2).
2. Confirm SMA vs RP-SMA on the Heltec V3 and the antenna.
3. Confirm MeshCore firmware supports the V3 in a sensor/telemetry role and what the node reads over I2C/SPI. (ARCHITECTURE answered: custom firmware with MeshCore as a library; spike S1 verifies.)
4. Pick a US enclosure source with gland options, and physically test-fit the 26650 in the Fibox PCB 65T.
5. ~~Source the LiFePO4 cell and holder.~~ Bioenno 26650 chosen (BATTERY.md); confirm stock.
6. Measure the node panel's open-circuit voltage in sun.
7. Pick the INA3221 breakout and confirm its shunt value.
