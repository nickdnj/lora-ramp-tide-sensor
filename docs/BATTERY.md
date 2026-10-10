# Battery and Charging: LoRa Ramp Tide Sensor Node

Version 0.2, 2026-10-10. Research note for the power subsystem (ADR-006).

**Changes in v0.2 (2026-10-10):** records Nick's decisions. NTC option 2 chosen (130 kΩ in parallel with a B3435 NTC; firmware owns the 0 °C rule). BQ25185 / Adafruit 6091, the 26650 cell and the LM66100 feed confirmed. Q7 (enclosure fit) accepted on outside dimensions, still to be physically verified. The CE-polarity fix is now in ARCHITECTURE v0.2. No analysis changed. Inputs: `docs/PRD.md` v0.2, `docs/ARCHITECTURE.md` v0.1 (sections 4.4, 4.5, ADR-006), `docs/BOM.md`. It also cross-checks Nick's 2026-09-29 solar MeshCore PVC-tube repeater design.

Evidence tags used throughout:

- **[V]** Verified. Read directly from the cited datasheet, schematic or vendor page during this research.
- **[C]** Calculated from [V] numbers. The method is shown so it can be rechecked.
- **[I]** Inferred, typical behavior or engineering judgment. Not checked against a primary source for this exact part.
- **[U]** Unverified or not found. Needs a bench test or a vendor answer.

---

## 0. Decision summary

| Item | Decision | Confidence |
|---|---|---|
| Chemistry | **LiFePO4, 1S.** Keeps the PRD Q5 default. | High |
| Cell | **26650 LiFePO4, about 3300 mAh, unprotected**, e.g. Bioenno Power 4-pack (US seller). An 18650 LiFePO4 (1400-1800 mAh) is the fallback if the enclosure is too small. Do **not** use a 14500 (too small). | Medium (stock and brand-specific cold data still to confirm) |
| Charger | **TI BQ25185 on Adafruit 6091.** Use the 3.65 V jumper (LiFePO4) and the 250 mA ISET jumper, and connect a 10k B3435 NTC **with 130 kΩ in parallel** to the TH pad, bonded to the cell (section 4.4 option 2, **chosen by Nick 2026-10-10**). Firmware owns the 0 °C rule through /CE, with a pull-up so charging is off unless the MCU enables it, and a CE pulse about every 4 h for the safety timer. | High for the part. Medium for the exact cold thresholds (calculated, not measured). |
| Heltec feed | Charger **SYS/LOAD → LM66100 ideal diode → Heltec JP1 (battery JST)**. Do not feed the Heltec 3V3 or 5V pins. | Medium. Needs the bench brownout test. |
| USB hazard | The ideal diode blocks the Heltec's onboard 4.2 V charger from reaching the LiFePO4 cell. Also label the box and, as procedure, unplug the cell before USB work. | High in principle. Bench-verify. |
| Protection | 1 A fuse at the cell + terminal. The charger provides CV limit, BUVLO 3.0 V and reverse OCP. Optional LiFePO4 PCM. | Medium |
| Panel | 0.5 W is enough on paper (about 3.7x the load in the worst-year December with 50% shading). **1 W stays the default**, because the real limit is cold-charge inhibit, not panel size. | Medium |
| RAK WisBlock path | **The base boards cannot charge LiFePO4.** They are Li-ion 4.2 V, have no NTC, and the solar input absolute maximum is 5.5 V, below the 6 V panel's 7.7 V open-circuit voltage. Use the same external BQ25185 and leave the RAK solar and USB ports unused in the field. | High |

**Biggest finding:** the BQ25185 cold window has wide hysteresis. Charging stops at about **+2 °C** but resumes only at about **+6 °C** (calculated, section 4.3). In a NJ January, with typical air highs of about 3-5 °C, a shaded cell may often not get back above 6 °C. That limit, not panel size, is the likely winter constraint. Section 4.4 gives two mitigations. **Nick chose option 2 (2026-10-10):** 130 kΩ in parallel moves the hardware window to about -3 °C stop / +2.4 °C resume, and firmware enforces the 0 °C rule.

---

## 1. Chemistry choice

| Chemistry | Cold charge | Cold discharge | Fit to this node | Verdict |
|---|---|---|---|---|
| **LiFePO4 (LFP)** | Not below 0 °C. Example cells: Bioenno 26650 rated 0-45 °C [V]; Tenergy 30085 18650 rated 0-45 °C [V] | Bioenno -20 to 60 °C [V]; Tenergy -20 to 60 °C [V], keeping ≥40% capacity at -20 °C and ≥60% at 0 °C, both at 0.5C [V] | Most thermally stable lithium chemistry [I]. Flat 3.2-3.3 V plateau. Long cycle life [I]. A 3.6 V class charger exists with an NTC input (BQ25185) [V]. **Downsides:** low headroom for the Heltec's 3.3 V LDO, and the Heltec onboard charger is Li-ion. | **Chosen** |
| Li-ion (NMC/NCA, 4.2 V) | Not below 0 °C, the same as LFP for typical cells [I] | Fine to about -20 °C [I] | More headroom above the LDO, matches the Heltec onboard charger (no USB overcharge hazard), more Wh per cell. Nick's PVC repeater uses this route (bq24074 plus Nitecore NL1835 protected Li-ion cells). Higher thermal-runaway energy [I]. Holding 4.2 V on hot summer days speeds aging [I]. | **Fallback**, if the bench brownout test fails on LFP (section 3.4) |
| LTO (lithium titanate) | Charges well below 0 °C [I] | Excellent [I] | 2.4 V nominal. The BQ25185 cannot regulate it (its VREG range is 3.6-4.4 V [V]). It would need a boost converter plus a special charger. No small cylindrical LTO cell was sourced. | Rejected |
| Primary Li-SOCl2 (e.g. a D-size bobbin cell) | n/a | Very good [I] | About 17 Ah would last years at 12 mAh/day [C], but **it defeats the pilot's purpose**, which is the solar test. It also needs a pulse capacitor for 145 mA TX bursts [I]. | Rejected for the pilot. Keep as the "solar failed" fallback. |
| Supercap / LIC hybrid | Charges cold [I] | Good [I] | 14 days at 25 mAh/day is about 1.2 Wh at 3.3 V [C]. That needs a large ultracap bank plus a buck-boost converter, and leakage eats into the budget [I]. It would not fit the concealed box. | Rejected |

**Why the decision stays LFP.** Both lithium chemistries need the same 0 °C charge cutoff, so neither avoids the cold problem. LFP is the safer chemistry for an unattended cell in a sealed box under a public dock. Its weakness, a low voltage on a 3.3 V LDO board, is measurable and fixable (section 3). Li-ion remains a known-good fallback because the repeater design already uses it.

**Cross-check with the repeater design.** The bq24074 on Adafruit 4755 is a **Li-ion/LiPo charger only**: 3.7 V nominal / 4.2 V charge, and the product page says "For use with Adafruit Lipoly/LiIon batteries only" [V, [Adafruit 4755](https://www.adafruit.com/product/4755)]. It is **not** LiFePO4-compatible. The repeater is consistent, because it uses Li-ion Nitecore NL1835 cells. Do not reuse the bq24074 for this node.

## 2. Cell selection and capacity

### 2.1 Capacity needed for 14 days without sun

| Term | Value | Basis |
|---|---|---|
| Load, design budget | 25 mAh/day | ARCHITECTURE 4.4 (nominal 11-12.5) |
| LFP self-discharge | 1-3 %/month of capacity, so about 1-3.3 mAh/day for a 3300 mAh cell | [I] typical LFP. The vendor did not state a figure [U]. |
| BQ25185 battery quiescent current | ≤5 µA, about 0.12 mAh/day | [V] IQ_BAT 4 µA typ / 5 µA max, 0-85 °C. Not specified below 0 °C. |
| LM66100 ideal diode quiescent current | ≤0.3 µA, negligible | [V] TI product page |
| **Planning drain** | **about 28.5 mAh/day** | [C] |
| 14 days | about 400 mAh | [C] |
| Cold derating at -15 °C | 0.6 | [I] The Tenergy spec gives ≥40% at -20 °C at a 0.5C rate [V]. Our average current is about C/3000 with short 0.05C pulses, so the real derating is much milder. 0.6 is a conservative planning value. |
| Aging (end of pilot plus 2 years) | 0.8 | [I] |
| Usable above BUVLO (3.0 V) | 0.95 | [I] LFP has very little capacity below 3.0 V |
| **Minimum rated capacity** | **about 880 mAh** | [C] 400 / (0.6 × 0.8 × 0.95) |

Result: a 14500 LFP (about 550-600 mAh, e.g. [Silicognition on Tindie](https://www.tindie.com/products/silicognition/550-600-mah-lifepo4-aa-14500-cell-32v/)) **fails** the requirement. An 18650 LFP (1400-1800 mAh) passes with 1.6-2x margin. A **26650 LFP (about 3300 mAh) gives about 3.8x margin**, about 55 days at the full cold and aged planning drain [C]. That covers a multi-week cold spell in which charging is inhibited (section 4.3). **Choose the 26650.**

### 2.2 Candidate cells (US sources first)

| Cell | Capacity | Charge / discharge temperature | Protected | Source | ~$ | Status |
|---|---|---|---|---|---|---|
| **Bioenno Power 26650 LFP, 3.2 V** (4-pack) | 3300 mAh rated | 0-45 °C / -20-60 °C [V] | No (vendor says it must be used with a PCM/BMS) | [bioennopower.com](https://www.bioennopower.com/products/26650-3-2v-3200-mah-2c-lifepo4-cells-4-pcs) (Santa Ana, CA) | 29.99 per 4 [V] | **Recommended.** Stock not shown on the page [U]. The listing gives only an MSDS, no full spec sheet [U]. |
| JGNE 26650 LFP | 3000 mAh, 3.65 V max | not listed on the page | No | [18650batterystore](https://www.18650batterystore.com/products/jgne-26650-3000mah-battery) (GA) | 6.99 | Sold out when checked [V]. A [spec PDF](https://cdn.shopify.com/s/files/1/0481/9678/0183/files/HTPFR26650-3000-3.2V_Specification.pdf?v=1612938206) is linked but was not read [U]. |
| JGNE 18650 LFP | 1800 mAh | not listed | No | [18650batterystore](https://18650batterystore.com/products/jgne-18650-1800) | 4.99 | Sold out when checked [V]. 18650 fallback. |
| Tenergy 30085-0 18650 LFP | 1450 mAh | 0-45 / -20-60 °C, -20 °C ≥40% [V, [datasheet](https://files.batteryjunction.com/frontend/files/Tenergy-30085-0-datasheet.pdf)] | No | [Battery Junction](https://www.batteryjunction.com/products/tenergy-30085-18650) | 4.49 | **Discontinued / sold out** [V]. Its datasheet is the best cold-capacity reference found. |
| Lithium Werks (ex-A123) ANR26650M1B | 2500-2600 mAh | Operating -30 to 55 °C. The charge-temperature limit was not found [U]. | No | EU sellers only were found ([nkon.nl](https://www.nkon.nl/en/a123-systems-anr26650m1b-a-grade-3-3v-a-grade.html)) | n/a | Not a US source |

**Protected vs unprotected.** No protected LiFePO4 18650 or 26650 cell with an in-can PCB was found at a US seller [V, search]. The plan uses an unprotected cell. Protection comes from the BQ25185 (CV, BUVLO, reverse OCP), a fuse, and optionally a 1S LiFePO4 PCM (section 7).

**Repeater cross-check.** The repeater's Nitecore NL1835 (3500 mAh, protected, 18.2 × 69.2 mm) is a **Li-ion** cell. Do not mix it into this node. Its sourcing note still applies: avoid no-name cells from Amazon and buy from specialty battery sellers.

### 2.3 Enclosure fit [I, from external dimensions; internal dimensions not verified]

| Enclosure | External size | 26650 + holder (cell 26 × 65 mm [V]; holder about 30 × 75 mm [U]) | 18650 + holder (about 21 × 77 mm) |
|---|---|---|---|
| Fibox Piccolo PCB 65 T | 110 × 80 × 65 mm | Fits along the length, beside a Heltec V3 (about 50 × 25 mm), the Adafruit charger and the INA3221 | Fits |
| RND 455-01069 | 115 × 65 × 40 mm | Tight in height (about 35 mm inside). Test-fit first. | Fits |
| RAK Unify 100 × 75 × 38 | 100 × 75 × 38 mm | Probably too tight with WisBlock modules | Likely fits. Test-fit. |

Answer to ARCHITECTURE Q7: yes for the Fibox PCB 65 T. Confirm the internal height before ordering the RND box. **Accepted by Nick 2026-10-10** on outside dimensions; a physical test-fit is still required.

## 3. Powering the Heltec V3 from a 1S LiFePO4

### 3.1 What is on the board (V3.2 schematic) [V]

Source: [Heltec WiFi LoRa 32 V3.2 schematic](https://resource.heltec.cn/download/WiFi_LoRa_32_V3/WiFi_LoRa_32_V3.2_Schematic_Diagram.pdf), linked from the [Heltec wiki](https://wiki.heltec.org/docs/devices/open-source-hardware/esp32-series/lora-32/wifi-lora-32-v3/).

- **USB path:** VUSB → F1 (6 V 2 A fuse) → VDD_5V → D2 1N5817WS Schottky → LDO input bus.
- **Battery path:** JP1 "1.25X2P-LiPo" (1.25 mm 2-pin) → VBAT → Q2 AO3401 P-MOSFET → the same LDO input bus. Q2's gate is pulled toward VDD_5V, so Q2 turns off when USB is present.
- **Battery reverse polarity:** an AO3400 N-MOSFET (Q4) in the JP1 negative lead, gated from VBAT. This looks like reverse-polarity protection [I].
- **Charger:** U3 **LGS4056HDA**, a TP4056-class linear Li-ion charger. VCC comes from VDD_5V, BAT goes to VBAT, PROG is 2 kΩ (so about 500 mA [I, LGS4056H family: I = 1000/R_PROG]), **TEMP is tied to GND (no NTC)**, and CE is tied to VDD_5V (always enabled). It charges to 4.2 V [I, 4056 family].
- **Regulators:** two **CE6260B33M** 3.3 V LDOs. U2 supplies VDD_3V3; U5 supplies Vext, switched by Vext_Ctrl.
- **Battery ADC:** a 390k/100k divider switched by ADC_Ctrl.

**Revision caveat:** this is the V3.2 drawing. V3.0 and V3.1 boards may differ; for example, the ADC_Ctrl polarity is reported to differ [U]. Check the board silkscreen.

### 3.2 Voltage headroom on battery

| Link | Value | Source |
|---|---|---|
| ESP32-S3 VDD3P3 / VDDA / RTC / CPU, recommended | 3.0-3.6 V | [V] [ESP32-S3 datasheet v2.2](https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf), Table 5-2 |
| ESP32-S3 input power pins, **absolute maximum** | **3.6 V** | [V] Table 5-1 |
| CE6260B33M dropout | about 120 mV typ at 100 mA. VIN 2-6 V. | [U] Third-party [flux.ai](https://www.flux.ai/silicon-yard/ce6260b33m~kv.md) only. No Chipower datasheet was found. |
| Q2 AO3401 + LM66100 (91 mΩ at 3.6 V [V]) + BQ25185 BATFET (115 mΩ typ [V]) | about 0.3 Ω in total, so about 45 mV at a 145 mA TX peak | [C], AO3401 resistance [I] |
| LFP cell, rested, 20-90% SOC | about 3.2-3.3 V; under a cold 145 mA pulse about 3.1-3.2 V | [I] |

[C] On battery during TX: 3.15 V − 0.045 V − about 0.18 V of LDO dropout at 145 mA gives about **2.9-2.95 V on the 3.3 V rail**. That is **slightly below the ESP32-S3's 3.0 V recommended minimum** during the 180 ms TX burst, worst case cold. During sleep and sampling (about 25 mA) the rail is about 3.05-3.1 V. With sun on the panel, the BQ25185 SYS rail sits at ≥3.8 V (VMINSYS [V]), so the LDO has full headroom.

Brownout behavior in this range is **[U]** and must be measured (section 8). Heltec support has said it can run from LFP but "we don't recommend it" ([Meshtastic forum](https://meshtastic.discourse.group/t/can-heltec-v3-be-powered-by-lifepo4-battery/12150), [U] second-hand). SX1262 22 dBm output may also drop slightly at a reduced supply [I].

### 3.3 Feed options compared

| Option | Verdict | Why |
|---|---|---|
| A. Cell straight to JP1 | Workable, not preferred | Simplest. But no over-discharge cutoff, and **USB plug-in charges the LFP cell to 4.2 V** through the LGS4056. |
| **B. BQ25185 SYS → LM66100 ideal diode → JP1** | **Recommended** | SYS is battery-backed, panel-powered when there is sun (the load runs from the panel even when charging is cold-inhibited [I, power-path behavior; bench-verify]), and cut off below BUVLO 3.0 V (hysteresis 150 mV [V]). The diode blocks the onboard charger from back-charging the cell if USB is plugged in. SYS reaches up to 4.5 V [V], which is within what the Heltec VBAT net already sees: the LDO bus runs at about 4.7 V on USB, and the LGS4056 BAT pin is rated 6 V abs max [I, from a family datasheet found by search]. |
| C. External supply into the 3V3 pin | **Rejected** | A raw LFP cell at 3.6-3.65 V charge reaches the ESP32-S3 **3.6 V absolute maximum** [V]. It also back-feeds the CE6260 output (reverse leakage [U]) and fights the LDO when USB is plugged in. |
| D. External supply into the 5V / VDD_5V pin | **Rejected** | VDD_5V powers the LGS4056 charger (VCC). Anything fed there would start charging whatever is on JP1 to 4.2 V [V, schematic]. |
| E. Buck-boost (fixed about 3.6-3.8 V out) → JP1 | Fallback if the brownout test fails | Gives the LDO full headroom at any cell voltage. It adds converter quiescent current; candidate parts were not verified [U]. |

The repeater found the same kind of trap: the bq24074 LOAD output reaches 4.4 V while the RAK19007 battery input maximum is 4.3 V, so the RAK was wired straight to the cells. For the Heltec, the equivalent check passes: 4.5 V from SYS is acceptable on the VBAT net [I]. For the RAK path it fails (section 5).

### 3.4 Safest wiring (recommended)

```
 6 V panel (+) ──[INA3221 ch1 shunt]──► Adafruit 6091 DC/solar IN (+)
 6 V panel (−) ───────────────────────► GND (single star ground at the charger)

 Adafruit 6091 BATT JST-PH (+) ──[INA3221 ch2 shunt]──[1 A fuse]──► 26650 LFP (+)
 Adafruit 6091 BATT (−) ───────────────────────────────────────────► 26650 LFP (−)
 Adafruit 6091 TH pad (TH trace CUT) ── 10k B3435 NTC ∥ 130k 1% ── GND   (NTC bonded to the cell can, under Kapton + foam; 130k per section 4.4 option 2)
 Adafruit /CE pad ──[1 MΩ]──► SYS   (fail-safe pull-up: charging OFF unless the MCU drives /CE LOW)

 Adafruit 6091 LOAD/SYS (+) ──► LM66100 VIN ; LM66100 VOUT ──► Heltec JP1 (+)   (CE pin of LM66100 to GND = enabled)
 Adafruit 6091 GND ────────────────────────────────────────► Heltec JP1 (−)

 Heltec GPIO (RTC-capable, held in deep sleep) ──[1k]──► Adafruit /CE pad   (HIGH = charge disabled)
 Adafruit S1 / S2 (STAT1/STAT2, open drain) ──► Heltec GPIOs with 100k pull-ups to 3V3   (read only, see the LED note)
```

Notes:

- **INA3221 channel 2 sits on the cell side.** It measures net cell current, charge minus load. The Heltec's own battery ADC now reads SYS, not the cell, so use the INA3221 for `vbat`.
- **JP1 is a 1.25 mm 2-pin connector** [V, schematic], not JST-PH. Use a 1.25 mm pigtail and **check its polarity with a meter.** Pigtail polarity varies between vendors [I].
- **STAT pins drive the onboard LEDs** (S1 = red FAULT, S2 = orange CHRG [V, Adafruit guide]). In daytime cold inhibit, the red FAULT LED may be lit off the panel supply, wasting a little harvest. Where the LED pull-up returns is [U]: check the Adafruit schematic and measure so a GPIO never sees more than 3.3 V. Remove or cut the LEDs if the board allows it.
- **CE polarity: the BQ25185 /CE is active-low.** HIGH disables charging [V]. ARCHITECTURE v0.1 (section 4.2 notes) said "drives the charger's CE pin low when … below +2 °C", which is the wrong polarity for this part. Fixed in ARCHITECTURE v0.2 (sections 4.2 and 4.3).
- **USB procedure:** label the enclosure "LiFePO4: do not plug USB with the cell connected." With the LM66100 in place, plugging USB is safe in principle: the onboard charger drives only the JP1 side, the diode is reverse-biased, and VOUT > VIN triggers reverse blocking [V, TI states reverse-current blocking; no threshold is given]. Still unplug the cell for USB sessions until section 8 test T6 passes.
- **LM66100 package:** SC-70-6 only [V]. No Adafruit or Pololu breakout was found [V, search]. Use an SC-70-to-DIP adapter or TI's LM66100EVM. The SparkFun Ideal Diode Breakout (COM-27925) is listed with 20 V test conditions, so it is probably a different IC [U].

## 4. Charger selection

### 4.1 TI BQ25185 (recommended) [V unless noted]

Source: [TI BQ25185 datasheet SLUSF65B, rev. Aug 2026](https://www.ti.com/lit/ds/symlink/bq25185.pdf).

| Parameter | Value | Relevance |
|---|---|---|
| Chemistries | Li-ion, Li-poly, **LiFePO4** | |
| VBATREG options (ILIM/VSET resistor) | 3.6 V (3.6k / 2.4k), **3.65 V (5.1k)**, 4.05, 4.2, 4.35, 4.4 V; ±0.5% | 3.65 V matches the cells' charge voltage (3.65 ± 0.05 V, Tenergy [V]). 3.6 V is gentler for long float at CV (see the safety timer row). |
| VIN operating range | 3.6-18 V; OVP 18.5 V; **abs max 25 V** | A 6 V panel (Voc 7.7 V [V, [Adafruit 3809](https://www.adafruit.com/product/3809)]) is well inside |
| VINDPM | VBAT + 330 mV when VBAT > 3.5 V, otherwise VIN regulated to 3.6 V | Solar-friendly. **This is not MPPT:** the panel is pulled down near 3.6-4 V and delivers about its short-circuit current [I]. |
| Charge current | 5-1000 mA, ICHG = 300/RISET | Adafruit jumpers: 1 A / 500 mA / 250 mA [V]. The product page and the guide disagree on the default (1 A vs 500 mA), so check the board [U]. **Use 250 mA.** |
| Battery quiescent current (no VIN) | 4 µA typ, 5 µA max (0-85 °C) | |
| BUVLO | 3.0 V falling, 150 mV hysteresis | Over-discharge cutoff of SYS |
| VLOWV (precharge → fast) | 3.0 V | |
| SYS | 4.5 V regulated with input present; VMINSYS 3.8 V when VBAT < 3.6 V | Section 3 |
| Safety timer | **6 h fast charge, 90 min precharge. Expiry latches charging off until a CE toggle or VIN removal.** Termination does not occur while VINDPM is active. | **Gotcha:** on a long sunny day the panel keeps the charger in VINDPM, so charging may never terminate and the 6 h timer can expire and latch off. Firmware should pulse CE high briefly every about 4 h of continuous charging (STAT = charging). The Adafruit guide confirms the 6 h timer and the CE-pulse reset [V]. Nightly VIN loss also clears it. |
| TS cold/hot | See 4.3. Charging and timers are suspended outside the window. A TS fault also disables trickle charging. | |
| STAT1/STAT2 | 1/1 = done or disabled; 1/0 = charging; **0/1 = recoverable fault (VIN_OVP, TS HOT, TS COLD, TSHUT, SYS short)**; 0/0 = latch-off fault (timer, BATOCP, pin short) | Cold inhibit shows as 0/1. It shares that code with OVP and TSHUT, so firmware should confirm with its own temperature reading. |
| TS/MR factory mode | Holding TS/MR below about 90 mV for 10 s with VIN present enters factory mode (battery disconnected) | With an NTC, that means about 67 °C at the cell [C]. Unlikely under the ramp, but on a summer day with the panel connected the node would turn off [I]. |

Adafruit 6091 board specifics [V, [product page](https://www.adafruit.com/product/6091) and [learn guide](https://learn.adafruit.com/adafruit-bq25185-usb-dc-solar-lithium-ion-polymer-charger.md?view=all)]:

- $6.95.
- DC/solar input pads rated 5-18 V.
- **LiFePO4: cut the VS jumper and close the 3.65 V back jumper.**
- **TH pad is broken out: cut the TH trace, then connect a 10k thermistor.** This answers BOM open item 1. The TS pin is accessible.
- /CE pad, S1/S2 pads, LOAD output (≤4.5 V), JST-PH battery connectors.
- The back silkscreen was corrected on 2025-02-05, so boards from before then may be mislabeled [V].

Not to be confused with Adafruit's "bq25185 … with 5V Boost" board, which is a different product.

### 4.2 Alternatives considered

| Part / board | LFP? | Cold cutoff | 6 V panel? | Verdict |
|---|---|---|---|---|
| TI BQ25570 / BQ25504 (boost harvesters) | Programmable OV, so possible | **No NTC input** listed [V for BQ25570, [TI](https://www.ti.com/product/BQ25570)] | **No:** VIN max 5.1 V, abs max 5.5 V [V] | Rejected. Built for sub-1 V sources. A 6 V panel exceeds its input rating. |
| Consonance CN3058E | Yes, fixed 3.6 V [V, datasheet copy on [hobbielektronika.hu](https://hobbielektronika.hu/forum/getfile.php?id=374185)] | TEMP pin, window about 45-80% of VIN [U, community wiki] | Input 3.8-6 V, abs max 6.5 V [U]. **The 7.7 V Voc exceeds it.** | Rejected. It would need an input clamp. |
| Microchip MCP73123 | Yes, 3.6 V [V, search summary of DS22191] | **No battery-temperature input** [U, LCSC listing] | OVP 6.5 V, abs max 18 V | Rejected (no NTC) |
| ADI LTC4071 | Float options are Li-ion (4.0-4.2 V) [I] | Has NTC [I] | Shunt charger, not a solar front end | Rejected |
| MCP73871 | Li-ion voltage options only [I] | Has THERM | Yes | Rejected (no LFP) |
| Adafruit 4755 (bq24074) | **No.** Li-ion/LiPo 4.2 V only [V] | 10k NTC, about 0 °C / 50 °C per Adafruit [V, page]. TI thresholds not checked [U]. | Yes (5-10 V, 28 V protected) [V] | Correct for the Li-ion repeater, wrong for this node |
| DFRobot / Seeed solar boards (CN3065-class, "LiPo Rider") | Li-ion [I] | Not checked [U] | | Not evaluated further |

### 4.3 NTC thresholds [C from V]

The datasheet specifies a 10 kΩ at 25 °C, β(25/85) = 3435 K NTC [V]. The thresholds are VCOLD_ENTRY 1.0075 V (0.9575-1.0575), VCOLD_EXIT 0.82 V, and VHOT_ENTRY 0.115 V [V]. The TS bias is listed as ITSMR = 38 µA (36.5-39.5), "adapter present" [V]. That it is the NTC bias current is an inference [I].

R = V / 38 µA and the beta equation give:

| Threshold | Voltage | NTC resistance | Temperature (β 3435 NTC) | With a β 3950 NTC (wrong type) |
|---|---|---|---|---|
| Cold, charging stops | 1.0075 V | 26.5 kΩ | **about +1.7 °C** (roughly +0.5 to +3 °C over tolerances) | about +4.6 °C |
| Cold, charging resumes | 0.82 V | 21.6 kΩ | **about +6.3 °C** | about +8.6 °C |
| Hot, charging stops | 0.115 V | 3.0 kΩ | about +59 °C | about +55 °C |

- **NTC type matters.** The repeater bought a B3950 NTC on Amazon (DIKAVS B074JBZ63Z). On the BQ25185 that type shifts the cold window about 3 °C warmer, costing winter charge hours. Buy a **B25/85 = 3435 K** part (Semitec 103AT-2 class) [I, that series is commonly specified as 3435 K; confirm on the distributor page].
- **Placement:** bond the NTC to the middle of the cell can with Kapton tape, under a closed-cell foam sleeve over the cell. Then it reads cell temperature, not air temperature or the charger IC's self-heating. The charger dissipates almost nothing at VINDPM: (3.6 V − 3.3 V) × 0.18 A ≈ 50 mW [C].

### 4.4 The hysteresis problem and mitigations

The about 4.6 °C hysteresis is fixed by the 1.0075 V / 0.82 V ratio and by the slope of a 10k NTC near 0 °C. Series or parallel resistors cannot narrow it. A parallel resistor only shifts the window colder and flattens the slope [C].

January air at nearby Long Branch averages highs of about 38-41 °F (3-5 °C) and lows of about 21-24 °F (-6 to -4 °C) ([Rutgers NJ climate office weekly normals, 1965-1995](https://climate.rutgers.edu/stateclim_v1/norms/weekly/longbranch.html); older period, [V] for that table). A shaded cell under the ramp may therefore often stay **between +2 and +6 °C: never inhibited from below, but once inhibited, unable to restart.** [I]

Options:

1. **Pilot default:** use the stock thresholds and log `charge_inhibit_cold_h`. The pilot exists to measure this. The 26650's about 55-day cold reserve (section 2.1) covers the risk.
2. **Window shifted down, firmware owns the 0 °C rule:** put about **130 kΩ in parallel with the NTC**. Then the hardware stops at about -3 °C and resumes at about +2.4 °C [C]. Firmware drives /CE HIGH (disable) below +1 °C and LOW above +2 °C, using the INA3221-side or SCL3300 temperature. The hardware layer becomes a backstop at -3 °C. That is slightly beyond the cell's 0 °C rating, but only reached if the firmware fails, and the charge rate is ≤0.06C [C, 0.18 A / 3.3 Ah]. **Chosen by Nick, 2026-10-10.**
3. **Thermal coupling (evaluate, do not assume):** bond the enclosure to the inner face of the south side member, behind the panel. The sun-heated aluminum then warms the cell exactly when charge is available. The cost is higher summer cell temperatures, with the hot cutoff at about 59 °C [I]. Log cell temperature to decide.

**Fail-safe /CE design (any option):** add a 1 MΩ pull-up from /CE to SYS, so charging is **disabled** unless the MCU actively holds /CE low. Use `gpio_hold_en` / RTC hold so the state survives deep sleep. If the battery is flat and the MCU is dead, SYS is still powered from the panel in sun, so the MCU boots and can re-enable charging [I, power-path behavior; bench-verify]. The Adafruit board's existing pull on /CE is [U].

## 5. RAK WisBlock base boards

| Board | Charge chemistry | Cold cutoff | Solar input | Battery input | Source |
|---|---|---|---|---|---|
| RAK19007 | Li-ion only: "3.7 V standard, 4.2 V charging" | **None mentioned** | **Abs max 5.5 V** ("must not exceed 5.5 V") | 3.3 V min / 3.7 typ / 4.3 V max | [V] [RAK19007 datasheet](https://docs.rakwireless.com/product-categories/wisblock/rak19007/datasheet/). Charger IC believed to be TP4054 [U, RAK forum]. |
| RAK5005-O | Li-ion only, 4.2 V, 500 mA | **None mentioned** | **Abs max 5.5 V** | Same limits | [V] [RAK5005-O datasheet](https://docs.rakwireless.com/product-categories/wisblock/rak5005-o/datasheet/) |

**Neither board charges LiFePO4 correctly or has a cold cutoff.** A 6 V panel at 7.7 V Voc would exceed the solar input's absolute maximum. The repeater found the same 5.5 V limit and noted the RAK19007 has no reverse-polarity protection.

What to do on the RAK path:

1. Leave the RAK solar connector **empty**. Use the same BQ25185 board, with the panel on its DC input.
2. **Do not feed the RAK battery JST from SYS**, because SYS reaches 4.5 V and the RAK battery input maximum is 4.3 V (the same trap as the repeater's bq24074 at 4.4 V). Wire the RAK battery input to the **cell side (BAT)** through an LM66100. The diode blocks the RAK's own Li-ion charger from back-charging the cell if USB is plugged in.
3. RAK states a 3.3 V minimum battery voltage. LFP sits at 3.2-3.3 V, so this is **[U]** and needs its own brownout sweep. On this path LFP is marginal, and a Li-ion cell plus a Li-ion NTC charger (the repeater pattern) may fit better.
4. The 6 V panel is fine for the BQ25185. The RAK Unify solar lid panel is weaker than the planned 1 W panel (BOM W4).

## 6. Panel sizing and winter energy check

For a linear charger, harvest is best counted in **mAh into the cell = panel current near Isc × PSH × k**. In VINDPM the panel is pulled down to about 3.6-4 V, where a crystalline panel delivers about its short-circuit current [I]. k = 0.85 covers soiling, salt film, angle-of-incidence losses on a vertical panel, and wiring [I].

Panel currents: 1 W, about 0.18 A (Adafruit 3809 Imp 180 mA [V]; Isc not listed). 0.5 W, about 0.09 A [I, scaled]. Load is 28.5 mAh/day (section 2.1, budget + self-discharge + quiescent).

| Case (PSH from ARCHITECTURE 4.5, PVGIS) | PSH | 0.5 W (mAh/day, ratio) | 1 W (mAh/day, ratio) |
|---|---|---|---|
| Dec mean | 3.45 | 264 (9.3x) | 528 (18.5x) |
| Dec worst year | 2.75 | 210 (7.4x) | 421 (14.8x) |
| Dec worst year, 50% shading | 1.38 | 106 (**3.7x**) | 211 (7.4x) |
| One heavy-overcast day (assumed) | 0.4 | 31 (1.07x) | 61 (2.1x) |

[C] These are consistent with ARCHITECTURE's η = 0.5 Wh method: for example, 1 W × 2.75 × 0.5 / 3.2 V ≈ 430 mAh.

**The "0.5 W gives about 4x budget" claim holds:** it reproduces as 3.7x for the worst-year December with 50% shading, even after adding self-discharge. Two caveats:

1. **Cold inhibit multiplies everything.** If f is the fraction of sun hours with the cell inside the charge window, the 0.5 W shaded case breaks even at f ≈ 27%, and the 1 W case at f ≈ 14% [C]. Nothing in PVGIS predicts f. This is why **1 W stays the default**: it buys margin against cold, not against darkness.
2. **PVGIS ERA5 is an upper bound** (ARCHITECTURE 4.5). Small PET/ETFE panels also lose disproportionately in diffuse low light [I]. A vertical panel sheds snow but collects salt film; clean it monthly when checking the desiccant [I].

At night, 0 mAh is harvested. The cell carries about 12 h × 1-1.2 mAh/h, about 13 mAh, which is trivial [C].

## 7. Safety and robustness

| Hazard | Mitigation | Tag |
|---|---|---|
| Overcharge | BQ25185 CV at 3.65 V ±0.5%. The LM66100 blocks the Heltec 4.2 V charger. Never feed the Heltec 5V pin. Optional 1S LFP PCM (HY2112-class boards list about 3.75 V over-charge / about 2.1 V over-discharge, e.g. [Gogo:Tronics](https://sparks.gogo.co.nz/catalog/DC-Power-260/1S-Single-Cell-LiFePO4-Protection-Board-3A-Peak-1054.html), an NZ seller). No US source was confirmed [U]. If used, measure its thresholds on the bench. | V / U |
| Over-discharge | BQ25185 BUVLO cuts SYS at 3.0 V [V]. Firmware lengthens the reporting interval earlier (ARCHITECTURE 4.3). Leakage below BUVLO (charger about 5 µA, INA3221 off) takes months to matter [C]. | V / C |
| Short circuit / wiring fault | **1 A fast fuse or a 0.5-0.75 A-hold PTC within 2 cm of the cell (+)**, ahead of everything, including the INA3221 shunt. BQ25185 reverse OCP at 3.13 A is a second layer [V]. The 5 A blade fuse from the repeater list is too large; that list already flags it. | I / V |
| Reverse polarity | Heltec JP1 has an N-MOSFET in the negative lead [V, schematic; function I]. **The BQ25185 board has none [I].** Use keyed JST-PH, meter-check every pigtail, and color-code the leads. The RAK19007 has none either (repeater finding). | I |
| Fire risk (unattended cell in a box) | LFP has much higher thermal-runaway onset and lower energy release than NMC [I]. A single cell is about 10.5 Wh [C]. Use a fused, strain-relieved, fully enclosed holder. Keep the box away from wood decking if possible; the mount is on aluminum. Charge rate is ≤0.08C [C]. | I |
| Venting / pressure | IP67 boxes pump moist air through glands during day-night cycling [I]. Fit an **ePTFE membrane breather vent**. It also gives a vent path if a cell ever vents. Add desiccant, and inspect it monthly (PRD runbook). | I |
| Salt and humidity | Conformal coat the Heltec, the charger and the INA3221. Keep connectors, the antenna SMA and the USB-C port uncoated. Put dielectric grease on the JST and fuse contacts. Use tinned copper wire. Make drip loops below the glands. | I |
| Corrosion and galvanic coupling | The cell holder's nickel-plated springs corrode in salt air [I]. A spot-welded tab cell with a soldered pigtail is better than spring holders for a multi-year install [I]. Isolate stainless hardware from the aluminum (nylon washers, BOM item 9). | I |
| Thermal cycling | Strain-relieve every wire (cable ties to the holder). Use a foam sleeve on the cell, which also slows temperature swings and helps the NTC read the cell. Do not let VHB tape be the only retention of the battery inside the box. | I |
| Cold-weather discharge | The Bioenno discharge rating goes to -20 °C [V]. The site's design minimum is about -15 °C. | V |

## 8. Shopping list (battery subsystem only, one node plus a bench spare)

| # | Item | Pick | Source | ~$ | Tag |
|---|---|---|---|---|---|
| B1 | LFP cells | Bioenno 26650 3.2 V 3300 mAh, 4-pack | [bioennopower.com](https://www.bioennopower.com/products/26650-3-2v-3200-mah-2c-lifepo4-cells-4-pcs) | 30 | V (stock U) |
| B2 | Charger | Adafruit 6091 bq25185 USB/DC/Solar (buy 2) | [adafruit.com/product/6091](https://www.adafruit.com/product/6091) | 14 | V |
| B3 | NTC | 10 kΩ, B25/85 = 3435 K, epoxy bead with leads (Semitec 103AT-2 class) | Digi-Key / Mouser | 2-5 | U (search the part at the distributor) |
| B4 | Parallel resistor (option 2, chosen) | 130 kΩ 1% | any | <1 | C |
| B5 | Ideal diode | TI LM66100DCKR + SC-70-6 adapter board, or LM66100EVM | [TI](https://www.ti.com/product/LM66100), Digi-Key | 2-15 | V (part) / U (adapter) |
| B6 | Fuse | 1 A fast inline or 0.5-0.75 A-hold PTC | any | 3 | I |
| B7 | 26650 holder, or a tabbed cell plus solder pigtail | Digi-Key "26650 battery holder" | Digi-Key | 3-6 | U (no part number checked) |
| B8 | Pigtails | JST-PH 2-pin (charger) and 1.25 mm 2-pin (Heltec JP1) | Adafruit / any | 5 | V (connector types) |
| B9 | Breather vent | ePTFE screw-in vent sized to the enclosure | Digi-Key | 5-10 | U |
| B10 | Optional LFP PCM | 1S LiFePO4 protection board with stated thresholds | see section 7 | 3-30 | U |
| B11 | Panel | 6 V 1 W IP67. Adafruit 3809 is **out of stock** [V], so use the BOM's silicone alternative or an equivalent with Voc ≤ 18 V. | BOM item 6 | 15-20 | V |

Battery subsystem total, excluding the panel: about **$70-90** for one node plus spares.

Replaces BOM rows 3-5: row 3 is resolved to the 26650 LFP, row 4's TS-pin question is resolved, and row 5 gets the NTC type.

## 9. Bench test plan

Record results in `docs/bench/`. Equipment: PPK2 or Otii, bench supply, DMM, oscilloscope, a kitchen freezer (about -18 °C), an ice bath, and thermocouples taped beside the NTC.

| ID | Test | Pass criteria |
|---|---|---|
| T1 | Charger configuration. With the cell at about 50% SOC and a bench supply at 6 V through 33 Ω (panel emulator), measure CV voltage at the end of charge, and ICHG. | VBAT holds at 3.65 V ±20 mV; ICHG ≈ 250 mA, or limited by the emulator |
| T2 | **Cold inhibit.** Cell plus NTC in the freezer to -10 °C, then warm slowly in still air with VIN applied. Log NTC/thermocouple temperature, STAT1/2 and the INA3221 cell current every 30 s. Repeat cooling from +10 °C. | Charging stops at ≤ +3 °C falling and restarts at a logged temperature (expect about +6 °C stock, about +2.4 °C with 130k). STAT = 0/1 while inhibited. **SYS stays up and the load runs from VIN during inhibit.** |
| T3 | Firmware /CE override and fail-safe pull-up. Force temperature below the firmware threshold and confirm CE goes HIGH and holds through deep sleep. Remove MCU power and confirm charging stays disabled until the MCU boots from SYS on VIN. | As described |
| T4 | **Brownout sweep.** Feed the full path (bench supply → BQ25185 BAT, VIN off → LM66100 → JP1). Step 3.6 → 2.9 V in 50 mV steps. Each step runs one full cycle including 22 dBm TX. Scope the 3V3 rail during TX and record the reset reason. Repeat at 14 dBm, and with the cell itself at -15 °C. | No brownout reset at ≥3.05 V supply. Record the minimum rail during TX and the lowest working supply voltage. If resets occur above 3.15 V, apply option E (buck-boost) or the Li-ion fallback. |
| T5 | **Sleep current** of the whole node at the cell (PPK2 in series with the cell), VIN off, at 25 °C and -15 °C | ≤100 µA (budget). Record `i_sleep_ua` for the server config. |
| T6 | **USB hazard.** With the cell replaced by a bench supply at 3.3 V that can show reverse current (or a 3.3 V supply through a 1 Ω shunt), plug Heltec USB in. | Current into the "cell" node ≤ 1 µA. The JP1 side may rise to about 4.2 V while the cell side stays at 3.3 V. |
| T7 | **Safety timer.** Emulate 7 h of continuous weak sun (VINDPM active) on a nearly full cell. | Without the firmware pulse, charging latches off (STAT 0/0) at 6 h. With the firmware CE pulse every 4 h, no latch. |
| T8 | BUVLO and recovery. Discharge the cell to below 3.0 V under node load; then apply VIN. | SYS drops at about 3.0 V; precharge, then fast charge; the node reboots from SYS and reports a reboot flag |
| T9 | Real panel in winter sun. Measure VIN (expect about 3.6-4 V in VINDPM) and charge current against panel Isc, at the actual vertical south orientation. | Charge current ≥ 80% of measured Isc. This calibrates k in section 6. |
| T10 | Cold capacity spot check. Discharge a full cell at -15 °C with a node-like pulse load (25 mA plus 150 mA pulses) to 3.0 V. | ≥ 60% of 25 °C capacity (planning assumption) |

## 10. Remaining unknowns

1. **Actual TS bias and cold temperatures** of the BQ25185. They are calculated from the datasheet voltages and an inferred 38 µA bias, so T2 must measure them.
2. **Heltec V3 brownout on LFP** and the CE6260 dropout (no primary datasheet found). T4 measures both.
3. **Fraction of winter sun hours with the cell at or above the restart temperature.** Unknown until pilot telemetry. (Option 2 is chosen; the telemetry now measures how much the firmware's +1/+2 °C rule costs.)
4. Bioenno stock, full spec sheet and self-discharge figure. Ask the vendor or measure.
5. LED pull-up rail and default /CE pull on the Adafruit 6091 (check the schematic).
6. Whether SYS stays powered from VIN during a TS fault (expected from the power-path design). T2 confirms it.
7. RAK path: RAK19007 operation at 3.2-3.3 V LFP voltages (below the stated 3.3 V minimum).
8. Heltec board revision (V3.0/3.1 vs the V3.2 schematic used here).

## Sources

- TI BQ25185 datasheet SLUSF65B: https://www.ti.com/lit/ds/symlink/bq25185.pdf
- Adafruit 6091 product: https://www.adafruit.com/product/6091 ; guide: https://learn.adafruit.com/adafruit-bq25185-usb-dc-solar-lithium-ion-polymer-charger.md?view=all
- Heltec V3.2 schematic: https://resource.heltec.cn/download/WiFi_LoRa_32_V3/WiFi_LoRa_32_V3.2_Schematic_Diagram.pdf ; wiki: https://wiki.heltec.org/docs/devices/open-source-hardware/esp32-series/lora-32/wifi-lora-32-v3/
- ESP32-S3 datasheet v2.2: https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf
- CE6260B33M (third-party summary only): https://www.flux.ai/silicon-yard/ce6260b33m~kv.md
- Meshtastic forum, Heltec V3 on LiFePO4: https://meshtastic.discourse.group/t/can-heltec-v3-be-powered-by-lifepo4-battery/12150
- TI LM66100: https://www.ti.com/product/LM66100
- TI BQ25570: https://www.ti.com/product/BQ25570
- CN3058E datasheet copy: https://hobbielektronika.hu/forum/getfile.php?id=374185 ; community wiki: https://wiki.adom.inc/ray/cn3058e
- Microchip MCP73123/223 (DS22191) via eval board page: https://www.microchip.com/en-us/development-tool/mcp73x23ev-lfp
- Adafruit 4755 (bq24074): https://www.adafruit.com/product/4755
- Adafruit 3809 panel: https://www.adafruit.com/product/3809
- RAK19007 datasheet: https://docs.rakwireless.com/product-categories/wisblock/rak19007/datasheet/ ; RAK5005-O: https://docs.rakwireless.com/product-categories/wisblock/rak5005-o/datasheet/
- Bioenno 26650: https://www.bioennopower.com/products/26650-3-2v-3200-mah-2c-lifepo4-cells-4-pcs
- Tenergy 30085-0 datasheet: https://files.batteryjunction.com/frontend/files/Tenergy-30085-0-datasheet.pdf ; listing: https://www.batteryjunction.com/products/tenergy-30085-18650
- 18650batterystore JGNE 26650: https://www.18650batterystore.com/products/jgne-26650-3000mah-battery ; JGNE 18650: https://18650batterystore.com/products/jgne-18650-1800
- Rutgers NJ climate weekly normals, Long Branch: https://climate.rutgers.edu/stateclim_v1/norms/weekly/longbranch.html
- PVGIS figures: as cited in `docs/ARCHITECTURE.md` section 4.5

## Revision history

| Version | Date | Author | Change |
|---|---|---|---|
| 0.1 | 2026-10-10 | research agent | First version: chemistry, cell, Heltec feed, charger, RAK, energy, safety, shopping list, bench plan. Cross-checked against the 2026-09-29 PVC repeater design. |
| 0.2 | 2026-10-10 | software-architecture agent (doc reconciliation) | Recorded Nick's decisions: NTC option 2 (130k ∥ B3435), /CE fail-safe pull-up in the wiring, Q7 accepted pending a physical fit, CE-polarity note points to ARCHITECTURE v0.2. |
