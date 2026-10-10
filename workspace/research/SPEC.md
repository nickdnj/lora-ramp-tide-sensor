# Ramp-Angle Tide Sensor: Build Spec (v0.1, 2026-10-10)

Goal: a LoRa node on the underside of a bulkhead-to-float ramp at the pilot marina that reports ramp tilt, converted server-side into actual water level and residual vs NOAA 8531942 predictions.

## 1. Physics

- Ramp hinged at bulkhead, free end rides on the float. `h = h0 + L·sin(θ − θ0)`, L ≈ 7.62 m (25 ft, to be confirmed from Meeco Sullivan drawings).
- Local range ≈ 0.8–1.0 m → ≈ 6–7.5° total swing. 1 cm = 0.075°. Linear within ~1%.
- Target: 0.01° noise after averaging (≈ 1.3 mm), real-world accuracy ±2–5 cm (freeboard, wakes, load).

## 2. Bill of materials (≈ $120–150 for one node)

| Part | Pick | Notes | ~$ |
|---|---|---|---|
| MCU + LoRa | Heltec WiFi LoRa 32 V3 (915 MHz) | ESP32-S3 + SX1262, ~20 µA deep sleep | 20 |
| Inclinometer | Murata SCL3300 or ADXL355 breakout | low-noise, low temp drift; avoid MPU6050/LIS3DH | 40–60 |
| Antenna | 915 MHz 3–5 dBi, SMA bulkhead + pigtail | mount **outside** the metal frame | 15 |
| Power | 18650 (protected) + solar charge board | or LiFePO4 for cold weather | 15 |
| Solar | 2 W / 6 V panel | on top of ramp or railing, not the underside | 10 |
| Enclosure | IP67 polycarbonate box, cable glands, desiccant | conformal-coat the boards | 15 |
| Bracket | SS or aluminum angle, 316 SS fasteners, isolating washers | rigid, mounted to a stringer at midspan | 10 |

Optional validation unit: MS5837 / Blue Robotics Bar30 pressure sensor on a pile for one week.

## 3. Mounting

1. Midspan of the ramp, bolted to a stringer. Slope at midspan equals chord angle under symmetric loading.
2. Sensor axis aligned along the ramp's long axis (pitch). Mark and photograph orientation.
3. Concealed install (Nick's preference, 2026-10-10): ramp runs east-west, so the thick aluminum **south-facing side face** carries a small (0.5-1 W) solar panel, bonded flat (VHB-type tape plus isolated fasteners). Vertical south face suits NJ: strong winter sun, sheds rain and droppings. Load is only ~17 mAh/day. Box tucked under the ramp beside it; antenna as a short stub standing 2-3 cm off the metal on the same face. Metal frame will detune and shield an antenna tucked underneath.
   - Isolate stainless hardware from aluminum (nylon washers, dielectric paste) to prevent galvanic corrosion.
   - Dock shore power was considered and set aside: needs an electrician and GFCI circuit, solar is simpler.
4. Strain relief and drip loops on every cable.

## 4. Firmware (PlatformIO, Arduino framework, RadioLib)

Cycle every 5 min:
1. Wake from deep sleep, power sensor.
2. Sample 300 readings at 100 Hz (3 s). Compute median pitch and standard deviation; read sensor temperature.
3. Read battery voltage.
4. Transmit one packet (SX1262, US915, SF8 / 125 kHz, 14 dBm), optional ack and retry once.
5. Deep sleep.

Packet (≈ 12 bytes): node id (1), seq (2), pitch median int16 in 0.001° (2), pitch stddev uint8 in 0.001° (1), temp int8 in 0.5 °C (1), battery mV uint16 (2), flags (1: low batt, high stddev, out-of-range, reboot), CRC (2).

Energy: ~4 s awake at ~50 mA ≈ 0.06 mAh per cycle ≈ 17 mAh/day. A 2600 mAh cell lasts ~5 months with no sun; the panel makes it indefinite.

## 5. Server side (Python, runs wherever the gateway lands)

1. Decode packet, store raw (SQLite or HA sensor).
2. Convert: `level = h0 + L·sin(radians(pitch − θ0))`.
3. Smooth: rolling median over 30–60 min to kill wakes and foot traffic; keep raw for storm analysis.
4. NOAA prediction: fetch hi/lo for station 8531942 (datagetter, `interval=hilo`, datum MLLW, metric), half-cosine interpolate between extremes.
5. Residual = level − predicted. Alert thresholds on residual (surge) and on rate of rise.
6. Publish: Home Assistant sensor, signboard tide panel, daily CSV.

## 6. Calibration

1. At install: read pitch with the ramp level (θ0 candidate); tape-measure float freeboard vs a fixed bulkhead mark at two different tide states.
2. Fit offset and scale (θ0, L-effective) from those points.
3. Ongoing: NOAA predicted highs and lows repeat to a few cm. Fit offset/scale monthly against them; use ocean gauge 8531991 and Sandy Hook 8531680 (lag ~2 h 18 m) as sanity checks on weather residuals.

## 7. Risks

- Float freeboard shifts with load: few cm, filtered statistically.
- Ramp end lifts off or float grounds: flag out-of-range tilt.
- Salt corrosion, bird fouling, vandalism: IP67, conformal coat, hide the box.
- RF: metal frame and bulkhead; test link margin before gluing anything down.
- Marina/association approval to attach hardware to the new ramps (dock manufacturer warranty).

## 8. Plan

| Step | What | Time |
|---|---|---|
| 1 | Confirm ramp length, hinge, roller, and stringer details from drawings and a site visit | 1 day |
| 2 | Bench build: MCU + inclinometer, tilt rig, verify noise and temp drift | 1 weekend |
| 3 | Range test: node at the ramp, gateway at its planned spot | 1 day |
| 4 | Install and calibrate | 1 day |
| 5 | Two-week shakedown vs NOAA hi/lo, then dashboards and alerts | 2 weeks |
| 6 | Optional: pressure-sensor validation, second ramp | later |

## 9. Open decisions

1. Gateway and transport: raw LoRa/LoRaWAN to a gateway vs MeshCore telemetry node. What LoRa gear is already in place at or near the marina?
2. Where the data lands: Home Assistant, signboard backend, both.
3. Permission to mount on the ramp.
