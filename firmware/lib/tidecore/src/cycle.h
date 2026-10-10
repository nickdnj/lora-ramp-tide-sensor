// One wake cycle (ARCHITECTURE 4.3): power read -> charger control -> battery state
// -> burst sample (or skip when critical) -> build v1 payload -> send -> choose sleep.
// Hardware sits behind small interfaces so this runs on the host with fakes.
// The radio interface has no receive call on purpose: the node never listens (ADR-001).
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "payload.h"
#include "power_logic.h"
#include "stats.h"

namespace tide {

class IInclinometer {  // SCL3300 over SPI
 public:
  virtual ~IInclinometer() = default;
  // Die temperature; false on SPI/CRC/status error.
  virtual bool read_temperature(double* temp_c) = 0;
  // Burst of up to max_n samples at 100 Hz (degrees); n_valid excludes bad frames.
  virtual bool burst(double* pitch, double* roll, size_t max_n, size_t* n_valid) = 0;
};

class IPowerMonitor {  // INA3221 + BQ25185 STAT/CE pins
 public:
  virtual ~IPowerMonitor() = default;
  virtual bool read(int32_t* vbat_mv, int32_t* vpanel_mv, double* ipanel_ma) = 0;
  virtual void read_stat(uint8_t* stat1, uint8_t* stat2) = 0;
  virtual void set_ce_disabled(bool disabled) = 0;  // /CE HIGH when true; held through deep sleep
  virtual void pulse_ce() = 0;                      // HIGH briefly, then back to the set level
};

class IUplink {  // MeshCore group datagram on the private channel (stubbed until spike S1)
 public:
  virtual ~IUplink() = default;
  virtual bool send_group_data(uint16_t data_type, const uint8_t* payload, size_t len) = 0;
};

// Survives deep sleep (RTC memory). boot_count comes from NVS at cold boot.
struct RtcState {
  uint16_t seq = 0;
  uint8_t boot_count = 0;
  BattState batt = kBattNormal;
  ChargerState charger;
  uint16_t awake_ms_prev = 0;
  bool reboot_pending = true;
  uint16_t reset_flags = 0;  // brownout_reset / wdt_reset from the reset reason
  uint32_t last_wake_s = 0;
  bool have_last_wake = false;
};

// Cold boot: RTC memory was lost. Call once before the first cycle.
void on_cold_boot(RtcState* rtc, uint8_t boot_count_from_nvs, bool brownout, bool watchdog);

struct CycleResult {
  PayloadV1 payload;
  uint8_t bytes[kPayloadLen];
  bool sent = false;
  bool ce_disabled = true;
  bool ce_pulsed = false;
  uint32_t sleep_s = 300;
};

// now_s: monotonic seconds (RTC timer). awake_ms_this_cycle is measured by the caller
// and reported in the *next* payload as awake_ms_prev.
CycleResult run_cycle(RtcState* rtc, uint8_t node_id, uint32_t now_s, IInclinometer& sensor,
                      IPowerMonitor& power, IUplink& uplink);

void finish_cycle(RtcState* rtc, uint16_t awake_ms_this_cycle);

}  // namespace tide
