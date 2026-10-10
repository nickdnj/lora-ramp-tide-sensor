#include "cycle.h"

namespace tide {

void on_cold_boot(RtcState* rtc, uint8_t boot_count_from_nvs, bool brownout, bool watchdog) {
  *rtc = RtcState();
  rtc->boot_count = static_cast<uint8_t>(boot_count_from_nvs + 1);  // caller writes it back to NVS
  rtc->reboot_pending = true;
  rtc->reset_flags = static_cast<uint16_t>((brownout ? kFlagBrownoutReset : 0) | (watchdog ? kFlagWdtReset : 0));
}

CycleResult run_cycle(RtcState* rtc, uint8_t node_id, uint32_t now_s, IInclinometer& sensor,
                      IPowerMonitor& power, IUplink& uplink) {
  CycleResult res;
  const uint32_t dt = rtc->have_last_wake ? now_s - rtc->last_wake_s : 0;
  rtc->last_wake_s = now_s;
  rtc->have_last_wake = true;

  // power read
  int32_t vbat = 0, vpanel = 0;
  double ipanel = 0;
  const bool ina_ok = power.read(&vbat, &vpanel, &ipanel);
  uint8_t s1 = 1, s2 = 1;
  power.read_stat(&s1, &s2);
  double temp_c = 0;
  const bool temp_ok = sensor.read_temperature(&temp_c);

  // charger control: 0 C rule, safety-timer pulse
  ChargerInputs ci;
  ci.temp_valid = temp_ok;
  ci.temp_c = temp_c;
  ci.stat1 = s1;
  ci.stat2 = s2;
  ci.dt_s = dt;
  ci.vin_present = ina_ok && vpanel >= kVinPresentMv;
  const ChargerOut co = charger_step(rtc->charger, ci);
  rtc->charger = co.state;
  power.set_ce_disabled(co.ce_disabled);
  if (co.pulse) power.pulse_ce();
  res.ce_disabled = co.ce_disabled;
  res.ce_pulsed = co.pulse;

  // battery state
  rtc->batt = next_batt_state(rtc->batt, vbat, ina_ok);
  uint16_t flags = batt_flags(rtc->batt);
  if (!ina_ok) flags |= kFlagInaError;
  if (rtc->reboot_pending) flags |= static_cast<uint16_t>(kFlagReboot | rtc->reset_flags);

  PayloadV1 p;
  p.node_id = node_id;
  p.seq = rtc->seq;
  p.boot_count = rtc->boot_count;
  p.temp = temp_ok ? q_temp(temp_c) : 0;
  p.vbat = ina_ok ? q_u16(vbat) : 0;
  p.vpanel = ina_ok ? q_u16(vpanel) : 0;
  p.ipanel = ina_ok ? q_ipanel(ipanel) : 0;
  p.chg = co.chg;
  p.awake_ms_prev = rtc->awake_ms_prev;

  // burst sample unless critical (health-only payload)
  if (rtc->batt != kBattCritical) {
    static double pitch[kBurstSamples], roll[kBurstSamples], scratch[kBurstSamples];
    size_t n_valid = 0;
    const bool ok = sensor.burst(pitch, roll, kBurstSamples, &n_valid);
    BurstStats st;
    const bool have = ok && n_valid > 0 && burst_stats(pitch, roll, n_valid, scratch, &st);
    flags |= sample_flags(have ? &st : nullptr, ok ? n_valid : 0);
    if (have && !(flags & kFlagSensorError)) {
      p.pitch_med = q_pitch(st.pitch_median);
      p.pitch_sd = q_pitch_sd(st.pitch_sd);
      p.roll_mean = q_roll(st.roll_mean);
    }
  }
  if (!temp_ok) flags |= kFlagSensorError;
  p.flags = flags;
  res.payload = p;
  encode(p, res.bytes);
  res.sent = uplink.send_group_data(kDataType, res.bytes, kPayloadLen);

  rtc->seq = static_cast<uint16_t>(rtc->seq + 1);  // wraps at 65535 -> 0
  rtc->reboot_pending = false;
  rtc->reset_flags = 0;
  res.sleep_s = interval_s(rtc->batt);
  return res;
}

void finish_cycle(RtcState* rtc, uint16_t awake_ms_this_cycle) { rtc->awake_ms_prev = awake_ms_this_cycle; }

}  // namespace tide
