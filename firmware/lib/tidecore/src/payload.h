// Uplink payload v1 (docs/ARCHITECTURE.md 4.7, ADR-004).
// 26 bytes, little-endian, CRC-16/CCITT-FALSE over bytes 0-23 stored LE at 24.
// Must agree with src/tidesvc/codec.py on every vector in tests/vectors/packets_v1.json.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace tide {

constexpr size_t kPayloadLen = 26;
constexpr uint16_t kDataType = 0xFF54;  // MeshCore dev range, no registration
constexpr uint8_t kPayloadVersion = 1;

// chg bits
constexpr uint8_t kChgCharging = 1u << 0;     // STAT 1/0
constexpr uint8_t kChgDone = 1u << 1;         // STAT 1/1 while /CE LOW and panel input present
constexpr uint8_t kChgColdInhibit = 1u << 2;  // STAT 0/1 with low temp, or firmware cold rule
constexpr uint8_t kChgCeOverride = 1u << 3;   // /CE held HIGH by firmware
constexpr uint8_t kChgLatchFault = 1u << 4;   // STAT 0/0
constexpr uint8_t kChgCePulse = 1u << 5;      // safety-timer CE pulse this cycle

// flags bits
constexpr uint16_t kFlagLowBatt = 1u << 0;
constexpr uint16_t kFlagCriticalBatt = 1u << 1;
constexpr uint16_t kFlagHighSd = 1u << 2;
constexpr uint16_t kFlagOutOfRange = 1u << 3;
constexpr uint16_t kFlagReboot = 1u << 4;
constexpr uint16_t kFlagBrownoutReset = 1u << 5;
constexpr uint16_t kFlagWdtReset = 1u << 6;
constexpr uint16_t kFlagSensorError = 1u << 7;
constexpr uint16_t kFlagInaError = 1u << 8;
constexpr uint16_t kFlagReducedInterval = 1u << 9;
constexpr uint16_t kFlagSensorSkipped = 1u << 10;
constexpr uint16_t kFlagShortSample = 1u << 11;

struct PayloadV1 {
  uint8_t ver = kPayloadVersion;
  uint8_t node_id = 0;
  uint16_t seq = 0;
  uint8_t boot_count = 0;
  int16_t pitch_med = 0;   // 0.001 deg
  uint16_t pitch_sd = 0;   // 0.001 deg
  int16_t roll_mean = 0;   // 0.01 deg
  int16_t temp = 0;        // 0.1 C
  uint16_t vbat = 0;       // mV
  uint16_t vpanel = 0;     // mV
  uint16_t ipanel = 0;     // 0.1 mA
  uint8_t chg = 0;
  uint16_t awake_ms_prev = 0;
  uint16_t flags = 0;
};

enum class DecodeStatus { Ok, BadLength, BadCrc, BadVersion };

uint16_t crc16_ccitt_false(const uint8_t* data, size_t len);
void encode(const PayloadV1& p, uint8_t out[kPayloadLen]);
DecodeStatus decode(const uint8_t* buf, size_t len, PayloadV1* out);
const char* decode_status_name(DecodeStatus s);  // "ok", "bad_length", "bad_crc", "bad_version"

// Quantization: round half away from zero, then clamp to the field range (never wrap).
// Signed fields clamp to +/-32767. NaN maps to 0 (callers flag sensor_error).
int16_t q_pitch(double deg);       // 0.001 deg
uint16_t q_pitch_sd(double deg);   // 0.001 deg
int16_t q_roll(double deg);        // 0.01 deg
int16_t q_temp(double c);          // 0.1 C
uint16_t q_ipanel(double ma);      // 0.1 mA
uint16_t q_u16(double v);

}  // namespace tide
