// Heltec WiFi LoRa 32 V3 node: wake, measure, send one MeshCore group datagram, deep sleep.
// SKELETON. Not compiled in this repository yet: the Arduino-ESP32 framework and MeshCore
// (git tag companion-v1.17.1) are fetched by PlatformIO on first build, and the drivers
// below are stubs. The cycle logic lives in lib/tidecore and is host-tested
// (firmware/test/host). Spike S1 (ARCHITECTURE 2.5, TEST-PLAN B1) must prove the MeshCore
// sender before the uplink stub is replaced.
#ifdef ARDUINO
#include <Arduino.h>
#include <esp_sleep.h>
#include <esp_system.h>
#include <driver/gpio.h>

#include "cycle.h"
#include "hal_heltec_v3.h"

using namespace tide;

RTC_DATA_ATTR static RtcState g_rtc;
RTC_DATA_ATTR static bool g_rtc_valid = false;

void setup() {
  const uint32_t t_start = millis();
  hal::begin();  // Vext on, SPI/I2C, watchdog (always return to sleep)
  if (!g_rtc_valid) {
    const esp_reset_reason_t why = esp_reset_reason();
    const uint8_t boots = hal::nvs_boot_count();
    on_cold_boot(&g_rtc, boots, why == ESP_RST_BROWNOUT, why == ESP_RST_TASK_WDT || why == ESP_RST_INT_WDT);
    hal::nvs_store_boot_count(g_rtc.boot_count);
    g_rtc_valid = true;
  }
  hal::Scl3300 sensor;
  hal::PowerPins power;
  hal::MeshcoreUplink uplink;  // TODO(S1): minimal MeshCore Mesh subclass, GRP_DATA, flood, wait TX done
  const CycleResult r = run_cycle(&g_rtc, hal::node_id(), hal::rtc_seconds(), sensor, power, uplink);
  hal::end();  // radio sleep, Vext off, INA3221 power-down, gpio_hold_en(/CE)
  finish_cycle(&g_rtc, static_cast<uint16_t>(millis() - t_start));
  esp_sleep_enable_timer_wakeup(static_cast<uint64_t>(r.sleep_s) * 1000000ULL);
  esp_deep_sleep_start();
}

void loop() {}
#endif
