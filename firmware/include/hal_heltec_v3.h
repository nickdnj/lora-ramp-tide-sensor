// Heltec V3 hardware adapters for the tidecore interfaces. STUBS: every method marks the
// spot where the real driver goes; none of this is verified on hardware.
#pragma once
#ifdef ARDUINO
#include <stdint.h>

#include "cycle.h"

namespace hal {

void begin();
void end();
uint8_t node_id();          // from NVS (provisioned over USB; ARCHITECTURE 4.7)
uint8_t nvs_boot_count();
void nvs_store_boot_count(uint8_t v);
uint32_t rtc_seconds();     // RTC slow clock; no 32 kHz crystal on the V3 (+/-5%)

class Scl3300 : public tide::IInclinometer {  // TODO: SPI driver, mode/settle from the datasheet
 public:
  bool read_temperature(double* temp_c) override { (void)temp_c; return false; }
  bool burst(double* pitch, double* roll, size_t max_n, size_t* n_valid) override {
    (void)pitch; (void)roll; (void)max_n; *n_valid = 0; return false;
  }
};

class PowerPins : public tide::IPowerMonitor {  // TODO: INA3221 one-shot, STAT1/2 GPIO, /CE GPIO + hold
 public:
  bool read(int32_t* vbat_mv, int32_t* vpanel_mv, double* ipanel_ma) override {
    *vbat_mv = 0; *vpanel_mv = 0; *ipanel_ma = 0; return false;
  }
  void read_stat(uint8_t* s1, uint8_t* s2) override { *s1 = 1; *s2 = 1; }
  void set_ce_disabled(bool disabled) override { (void)disabled; }
  void pulse_ce() override {}
};

class MeshcoreUplink : public tide::IUplink {  // TODO(S1): MeshCore GRP_DATA sender, never receives
 public:
  bool send_group_data(uint16_t data_type, const uint8_t* payload, size_t len) override {
    (void)data_type; (void)payload; (void)len; return false;
  }
};

}  // namespace hal
#endif
