# Bill of Materials: one ramp node + gateway (draft, 2026-11-04)

**Version:** 0.3, 2026-11-04

**Changes in v0.3 (2026-11-04):** the repeater is taken down (Repeater section removed). The gateway is now a Heltec V3 with custom receive-and-forward firmware on the home/marina Wi-Fi, USB wall power (G1-G4). MeshCore dropped from the node and gateway rows (ARCHITECTURE 2.1). Cell planned at **3200 mAh**; verify the label (row 3). New row 18: a second thermistor on the battery for the firmware 0 °C rule, plus its reference resistor; row 5 notes the charger NTC stays as the hardware backstop. Row 12: INA3221 ch2 cell current is now sent. Open items updated.

**Changes in v0.2 (2026-10-10):** power rows (3-5) taken from `docs/BATTERY.md` (26650 LiFePO4, BQ25185 on Adafruit 6091, B3435 NTC with 130 kΩ in parallel); added the INA3221, LM66100 ideal diode and the BATTERY.md small parts; panel row notes the Voc check; enclosure row records the 26650 fit (still to be physically verified); WisBlock path marked as needing an nRF52 firmware port (unverified), Heltec V3 + SCL3300 recommended as the primary build; new Repeater section for Nick's solar PVC-tube repeater; gateway antenna no longer depends on Q1b; open items updated.

Status: working draft for Nick's review. Nothing ordered. Prices are from search results, not quotes; confirm on the seller page. Source of truth for design intent is `docs/PRD.md` v0.4 and `docs/ARCHITECTURE.md` v0.3; the power subsystem source is `docs/BATTERY.md` v0.3.

## Node (on the ramp)

**Primary build: Heltec V3 + SCL3300** (per ARCHITECTURE, ADR-001 and ADR-005).

| # | Part | Pick | Where | ~$ | Status |
|---|---|---|---|---|---|
| 1 | MCU + LoRa radio | Heltec WiFi LoRa 32 V3, US915 (ESP32-S3 + SX1262), runs custom push-and-sleep firmware on RadioLib (no MeshCore) | [Rokland](https://store.rokland.com/products/heltec-wifi-lora-32v3), [Hackster](https://hackster.io/products/buy/116383) | 27-30 | Chosen. Note the board revision (BATTERY.md 3.1 used the V3.2 schematic). |
| 2 | Inclinometer | Murata SCL3300 breakout (SPI) | [LogicalEdges on Tindie](https://www.tindie.com/products/led/scl3300-0001-inclinometer-tilt-sensor-breakout/) | 40-60 | Accepted default. Third-party board; verify specs against Murata datasheet. Murata's own eval board needs an extra interface board. Alternative: ADXL355. |
| 3 | Battery cell | **26650 LiFePO4, 3.2 V, 3200 mAh planning value, unprotected** (Bioenno Power 4-pack), plus a 26650 holder or a tabbed cell with a soldered pigtail | [bioennopower.com](https://www.bioennopower.com/products/26650-3-2v-3200-mah-2c-lifepo4-cells-4-pcs) (BATTERY.md B1, B7) | 30 (4-pack) + 3-6 | Chosen (BATTERY.md). **Plan with 3200 mAh (Nick, 2026-11-04); the listing has shown both 3200 and 3300, so read the capacity on the cell label on arrival.** Unprotected: protection is the charger, a 1 A fuse (row 15) and an optional PCM. Stock not confirmed. |
| 4 | Charger | **TI BQ25185 on Adafruit 6091**: cut VS jumper and close the 3.65 V (LiFePO4) jumper; 250 mA ISET; cut the TH trace; 1 MΩ pull-up from /CE to SYS (charging off unless the MCU enables it). Buy 2. | [Adafruit 6091](https://www.adafruit.com/product/6091), [TI](https://www.ti.com/product/BQ25185) | 14 (2) | Chosen (BATTERY.md section 4). TH pad access confirmed from the Adafruit guide. Cold thresholds are calculated, not measured (BATTERY T2). |
| 5 | Charger NTC + parallel resistor (hardware backstop) | 10 kΩ NTC, **B25/85 = 3435 K** (Semitec 103AT-2 class), bonded to the cell can, on the charger TH pad; **130 kΩ 1% in parallel** (hardware stop about -3 °C, resume about +2.4 °C) | Digi-Key / Mouser | 3-6 | Chosen (Nick, 2026-10-10). Do not use a B3950 part (shifts the window about 3 °C warmer). The firmware 0 °C rule no longer uses the SCL3300 die temperature; it reads its own battery thermistor (row 18). |
| 6 | Solar panel | **Decided 2026-10-10: same 1 W flexible amorphous type Nick bought for the (now taken-down) repeater.** Adafruit 3809 below is the fallback (out of stock per BATTERY.md). 6 V, 1 W, IP67 | [Adafruit 3809](https://adafruit.com/product/3809); silicone alt [Soldered 108763](https://www.mouser.com/catalog/specsheets/Soldered_108763%20solar%20panel%201w%206v.pdf) | 10-15 | Accepted default (1 W). Nick buys. **Open-circuit voltage still to be measured on the bench (Nick's to-do).** BATTERY.md: a 6 V panel at about 7.7 V Voc is well inside the BQ25185 input (3.6-18 V operating, 25 V abs max). The pilot's main question is whether this is enough. |
| 7 | Antenna | Doodle Labs ANT-915-3-O, 3 dBi, IP67, SMA male pigtail | [datasheet](https://mouser.com/datasheet/2/895/Doodle_432024_ANT_915_3_O_Datasheet-3436791.pdf) | 15-25 | Best match found; not a bulkhead mount, so bracket it 2-3 cm off the south face. Check SMA vs RP-SMA against the Heltec board. |
| 8 | Enclosure | IP67 polycarbonate, small, with glands | [Fibox Piccolo PCB 65T](https://cpcireland.farnell.com/fibox/pcb-65t/fibox-piccolo-transp-110x80x65mm/dp/EN81977), [RND 455-01069](https://www.distrelec.ch/en/plastic-enclosure-65x115x40mm-light-grey-polycarbonate-ip67-rnd-rnd-455-01069/p/30129921) | 15-25 | **Fibox PCB 65T** takes the 26650 by outside dimensions (BATTERY.md 2.3); **physical test-fit still required (Nick's bench to-do).** RND is tight in height. Both European listings; need a US source and gland options confirmed. |
| 9 | Bracket and hardware | 316 SS or aluminum angle, nylon isolating washers, dielectric paste | hardware store | 10 | Reversible install, no drilling (dock warranty precaution). |
| 10 | Bonding | VHB-type tape for the panel on the south face | hardware store | 8 | |
| 11 | Cable glands, desiccant, conformal coat, wire | misc | any | 10-15 | |
| 12 | Power telemetry | **TI INA3221 3-channel V/I breakout (I2C)**: ch1 panel input, ch2 cell side; ch2 current is sent as `ibat` (payload v2; ARCHITECTURE 4.2, 4.7; BATTERY.md 3.4) | Adafruit / SparkFun / other breakout (part number to confirm) | 8-12 | Needed for FR6. Was missing from v0.1. Check the shunt value suits about 0-250 mA and that ch2 reads both directions (charge and discharge). |
| 13 | Ideal diode | TI LM66100DCKR + SC-70-6 adapter board, or LM66100EVM: charger SYS → LM66100 → Heltec JP1 | [TI](https://www.ti.com/product/LM66100), Digi-Key (BATTERY.md B5) | 2-15 | Chosen. Blocks the Heltec's 4.2 V onboard charger from the cell. Still: no USB with the cell attached until bench test T6 passes. |
| 14 | Pigtails | JST-PH 2-pin (charger battery) and **1.25 mm 2-pin** (Heltec JP1); meter-check polarity | Adafruit / any (BATTERY.md B8) | 5 | |
| 15 | Fuse | 1 A fast inline, or 0.5-0.75 A-hold PTC, within 2 cm of the cell + | any (BATTERY.md B6) | 3 | |
| 16 | Breather vent | ePTFE screw-in vent sized to the enclosure | Digi-Key (BATTERY.md B9) | 5-10 | |
| 17 | Optional LFP PCM | 1S LiFePO4 protection board with stated thresholds | BATTERY.md section 7, B10 | 3-30 | Optional; no US source confirmed. |
| 18 | **Battery thermistor (firmware 0 °C rule)** | A second 10 kΩ **B3435** NTC (same type as row 5), bonded to the cell can beside the charger's NTC, under the foam sleeve; **10 kΩ 0.1% reference resistor** from switched Vext to an ESP32-S3 ADC1 pin, NTC from that pin to GND (BATTERY.md 3.4) | Digi-Key / Mouser (BATTERY.md B3, B12) | 3-5 | Added 2026-11-04 (Nick: the 0 °C rule uses a thermistor on the battery). Separate from the charger's TS circuit, so the two cold layers stay independent. ADC pin to be chosen in E3.3. |

Node subtotal: about $190-275 (rough; adds the INA3221, LM66100, battery thermistor and BATTERY.md small parts to the v0.1 estimate of $150-210; the cell and charger lines buy spares).

## Prototype option: RAK WisBlock (plug-together, no wiring)

Added 2026-10-10 at Nick's request. **Kept as an option only; the recommended primary build is the Heltec V3 + SCL3300 node above, per ARCHITECTURE.** The project's custom push-and-deep-sleep firmware is written for the ESP32-S3 (Heltec V3). Using the RAK4631 (nRF52840) **would need an nRF52 port of that firmware; this is unverified** and not in the dev plan. (RadioLib supports the SX1262 on nRF52 targets [I], which helps a port.)

Same node role as the table above, built from snap-together modules. Consumer-grade accelerometer, so expect temperature drift of a few cm of apparent level per day-night swing (typical datasheet behavior, not measured on this build). Handle by logging sensor temperature, compensating in the server, and monthly NOAA recalibration. The tide cycle itself (about 1 m swing) is far larger than the drift.

| # | Part | Pick | Where | ~$ | Status |
|---|---|---|---|---|---|
| W1 | Core | RAK4631 (nRF52840 + SX1262) | [RAK store](https://store.rakwireless.com/) | 25-30 | Custom firmware needs an nRF52 port (unverified). |
| W2 | Base board | RAK5005-O (or current WisBlock base) | RAK store | 10-15 | **Cannot charge LiFePO4 and has no cold cutoff; solar input abs max 5.5 V** (BATTERY.md section 5). Leave its solar connector empty. |
| W3 | Accelerometer module | RAK1904 (ST LIS3DH, I2C) | [RAK1904](https://store.rakwireless.com/products/rak1904-lis3dh-3-axis-acceleration-sensor) | 5-10 | Prototype grade. Check RAK's range for a better tilt module before ordering. |
| W4 | Enclosure | RAK Unify IP65, 100x75x38 mm (solar variant has a built-in 80x45 mm lid panel) | [datasheet](https://docs.rakwireless.com/product-categories/wisblock/rakbox-uo100x75x38-solar/overview/) | 25-35 | Verify board, module and battery fit. Its small panel is weaker than the planned 1 W south-face panel. |
| W5 | Battery, panel, antenna, charger | as in the node table (LiFePO4 cell, 1 W panel, Doodle antenna) **plus the same external BQ25185 charger** | see above | | Per BATTERY.md section 5: the WisBlock base cannot charge LiFePO4. Use the BQ25185, feed the RAK battery input from the **cell side through an LM66100** (not from SYS, which reaches 4.5 V vs the RAK's 4.3 V max). RAK operation at 3.2-3.3 V LFP is unverified. |

Unverified: the nRF52 port of the custom firmware (radio, sensor drivers, deep sleep).

## Gateway (receiver on the home/marina Wi-Fi)

| # | Part | Pick | ~$ | Status |
|---|---|---|---|---|
| G1 | LoRa receiver + Wi-Fi | A second **Heltec WiFi LoRa 32 V3**, US915, with custom receive-and-forward firmware (RadioLib RX, Wi-Fi, HTTP POST to `tidesvc` :8120; ARCHITECTURE ADR-002, section 5) | 20-30 | Chosen (Nick, 2026-11-04: direct link to a Wi-Fi gateway). Same private radio settings as the node. |
| G2 | Antenna for the gateway | 915 MHz, 3 dBi or better; an indoor stub at a window facing the ramp, or an outside omni on a short low-loss coax run | 15-40 | **Placement is a real decision again** without the repeater: chosen at the site visit (E0.1) and proved by the link test (ARCHITECTURE 2.4). |
| G3 | Power | USB 5 V wall adapter (1 A or more) and USB-C cable; no battery | 10 | Mains-powered indoors. No LiFePO4 on this board, so the node's USB warning does not apply. |
| G4 | Enclosure | Small indoor case or a window mount | 0-10 | Optional. |
| G5 | Software | `tidesvc` ingest endpoint, SQLite, HTTP JSON API on the mini PC | | Per `docs/ARCHITECTURE.md`. No radio is attached to the mini PC any more. |

## Optional

| Part | Why |
|---|---|
| MS5837 / Blue Robotics Bar30 pressure sensor on a pile | one-week validation of the tilt-derived level |
| WeatherFlow Tempest (already installed) | optional software-only input: pressure, wind, rain via REST (station 183092, SignBoard's token) |
| Bench gear: USB power meter / current logger | measure real duty-cycle energy against the 25 mAh/day design budget (ARCHITECTURE 4.4) |

## Open items before ordering

1. ~~Verify BQ25185 breakout temperature pin and thresholds.~~ TH pad confirmed (BATTERY.md 4.1). Thresholds are calculated; measure on the bench (BATTERY T2).
2. Confirm SMA vs RP-SMA on the Heltec V3 and the antenna.
3. ~~Confirm MeshCore firmware supports the V3 in a sensor/telemetry role.~~ Superseded 2026-11-04: MeshCore dropped; custom RadioLib firmware on node and gateway (ARCHITECTURE 2.1; spike S1 verifies).
4. Pick a US enclosure source with gland options, and **physically test-fit the 26650 in the Fibox PCB 65T** (Nick, bench to-do; still open).
5. ~~Source the LiFePO4 cell and holder.~~ Bioenno 26650 chosen (BATTERY.md); confirm stock, and read the capacity on the cell label on arrival (planning value 3200 mAh).
6. **Measure the node panel's open-circuit voltage in sun** (Nick, bench to-do; still open).
7. Pick the INA3221 breakout and confirm its shunt value.
8. Choose the gateway spot (distance to the ramp, height, glazing, Wi-Fi reach to the mini PC) at the site visit; it sets the gateway antenna choice (G2).
