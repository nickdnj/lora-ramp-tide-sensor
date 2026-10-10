// Battery state machine and BQ25185 charger control (ARCHITECTURE 4.2, 4.3; BATTERY.md 4.4).
// Pure functions of their inputs so they run natively. Python mirror: src/sim/fwlogic.py.
// Vectors: tests/vectors/fw_logic_v1.json.
#pragma once

#include <stdint.h>

namespace tide {

// ---- battery state (thresholds are placeholders until bench B8) ----------------
enum BattState : uint8_t { kBattNormal = 0, kBattLow = 1, kBattCritical = 2 };

constexpr int32_t kLowEnterMv = 3150;   // NORMAL -> LOW below
constexpr int32_t kLowExitMv = 3200;    // LOW -> NORMAL at or above
constexpr int32_t kCritEnterMv = 3050;  // -> CRITICAL below
constexpr int32_t kCritExitMv = 3100;   // CRITICAL -> LOW at or above

BattState next_batt_state(BattState prev, int32_t vbat_mv, bool vbat_valid);
uint32_t interval_s(BattState s);  // 300 / 900 / 3600
uint16_t batt_flags(BattState s);  // low_batt, critical_batt, reduced_interval, sensor_skipped

// ---- charger control (/CE HIGH = charging disabled) ------------------------------
constexpr double kColdDisableBelowC = 1.0;
constexpr double kColdEnableAboveC = 2.0;
constexpr double kHwColdFaultBelowC = 5.0;  // to attribute STAT 0/1 to the NTC cold fault
constexpr uint32_t kCePulseAfterS = 4u * 3600u;
constexpr int32_t kVinPresentMv = 3000;

struct ChargerState {
  bool ce_disabled = true;  // 1 Mohm pull-up: charging off until firmware enables it
  uint32_t charging_elapsed_s = 0;
};

struct ChargerInputs {
  bool temp_valid = false;
  double temp_c = 0;   // SCL3300 die temperature (in-box proxy for the cell)
  uint8_t stat1 = 1;   // BQ25185 STAT1 level
  uint8_t stat2 = 1;   // BQ25185 STAT2 level
  uint32_t dt_s = 0;   // time since the previous wake
  bool vin_present = true;  // vpanel >= 3.0 V (STAT floats to 1/1 without input)
};

struct ChargerOut {
  ChargerState state;
  bool ce_disabled = true;  // drive /CE HIGH when true
  bool pulse = false;       // pulse /CE HIGH briefly then LOW (safety timer / latch recovery)
  uint8_t chg = 0;          // payload chg byte
};

ChargerOut charger_step(const ChargerState& prev, const ChargerInputs& in);

}  // namespace tide
