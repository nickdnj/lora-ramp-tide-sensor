#include "power_logic.h"

#include "payload.h"

namespace tide {

BattState next_batt_state(BattState prev, int32_t mv, bool valid) {
  if (!valid) return prev;  // INA error: keep the previous state
  if (mv < kCritEnterMv) return kBattCritical;
  if (prev == kBattCritical && mv < kCritExitMv) return kBattCritical;
  if (mv < kLowEnterMv) return kBattLow;
  if ((prev == kBattLow || prev == kBattCritical) && mv < kLowExitMv) return kBattLow;
  return kBattNormal;
}

uint32_t interval_s(BattState s) {
  switch (s) {
    case kBattLow: return 900;
    case kBattCritical: return 3600;
    default: return 300;
  }
}

uint16_t batt_flags(BattState s) {
  if (s == kBattLow) return kFlagLowBatt | kFlagReducedInterval;
  if (s == kBattCritical) return kFlagLowBatt | kFlagCriticalBatt | kFlagReducedInterval | kFlagSensorSkipped;
  return 0;
}

ChargerOut charger_step(const ChargerState& prev, const ChargerInputs& in) {
  bool cold;
  if (!in.temp_valid || in.temp_c < kColdDisableBelowC) {
    cold = true;  // fail-safe: unknown temperature disables charging
  } else if (in.temp_c > kColdEnableAboveC) {
    cold = false;
  } else {
    cold = prev.ce_disabled;  // hysteresis band: hold
  }
  const bool charging = in.stat1 == 1 && in.stat2 == 0;
  const bool latched = in.stat1 == 0 && in.stat2 == 0;
  uint32_t elapsed = prev.charging_elapsed_s;
  bool pulse = false;
  if (cold) {
    elapsed = 0;
  } else if (charging) {
    elapsed += in.dt_s;
    if (elapsed >= kCePulseAfterS) {
      pulse = true;
      elapsed = 0;
    }
  } else {
    elapsed = 0;
    if (latched) pulse = true;  // recover a latched safety timer
  }
  uint8_t chg = 0;
  if (charging) chg |= kChgCharging;
  if (in.stat1 == 1 && in.stat2 == 1 && !prev.ce_disabled && in.vin_present) chg |= kChgDone;
  const bool hw_cold = in.stat1 == 0 && in.stat2 == 1 && in.temp_valid && in.temp_c < kHwColdFaultBelowC;
  if (cold || hw_cold) chg |= kChgColdInhibit;
  if (cold) chg |= kChgCeOverride;
  if (latched) chg |= kChgLatchFault;
  if (pulse) chg |= kChgCePulse;
  ChargerOut out;
  out.state.ce_disabled = cold;
  out.state.charging_elapsed_s = elapsed;
  out.ce_disabled = cold;
  out.pulse = pulse;
  out.chg = chg;
  return out;
}

}  // namespace tide
