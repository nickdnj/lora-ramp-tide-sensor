#include "payload.h"

#include <math.h>

namespace tide {

uint16_t crc16_ccitt_false(const uint8_t* data, size_t len) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < len; ++i) {
    crc ^= static_cast<uint16_t>(data[i]) << 8;
    for (int b = 0; b < 8; ++b) {
      crc = (crc & 0x8000) ? static_cast<uint16_t>((crc << 1) ^ 0x1021) : static_cast<uint16_t>(crc << 1);
    }
  }
  return crc;
}

namespace {
inline void put_u16(uint8_t* p, uint16_t v) {
  p[0] = static_cast<uint8_t>(v & 0xFF);
  p[1] = static_cast<uint8_t>(v >> 8);
}
inline uint16_t get_u16(const uint8_t* p) { return static_cast<uint16_t>(p[0] | (p[1] << 8)); }

double clamp_round(double x, double lo, double hi) {
  if (isnan(x)) return 0.0;
  double r = floor(fabs(x) + 0.5);
  if (x < 0) r = -r;
  if (r < lo) return lo;
  if (r > hi) return hi;
  return r;
}
}  // namespace

void encode(const PayloadV1& p, uint8_t out[kPayloadLen]) {
  out[0] = p.ver;
  out[1] = p.node_id;
  put_u16(out + 2, p.seq);
  out[4] = p.boot_count;
  put_u16(out + 5, static_cast<uint16_t>(p.pitch_med));
  put_u16(out + 7, p.pitch_sd);
  put_u16(out + 9, static_cast<uint16_t>(p.roll_mean));
  put_u16(out + 11, static_cast<uint16_t>(p.temp));
  put_u16(out + 13, p.vbat);
  put_u16(out + 15, p.vpanel);
  put_u16(out + 17, p.ipanel);
  out[19] = p.chg;
  put_u16(out + 20, p.awake_ms_prev);
  put_u16(out + 22, p.flags);
  put_u16(out + 24, crc16_ccitt_false(out, 24));
}

DecodeStatus decode(const uint8_t* buf, size_t len, PayloadV1* out) {
  if (len != kPayloadLen) return DecodeStatus::BadLength;
  if (crc16_ccitt_false(buf, 24) != get_u16(buf + 24)) return DecodeStatus::BadCrc;
  if (buf[0] != kPayloadVersion) return DecodeStatus::BadVersion;
  PayloadV1 p;
  p.ver = buf[0];
  p.node_id = buf[1];
  p.seq = get_u16(buf + 2);
  p.boot_count = buf[4];
  p.pitch_med = static_cast<int16_t>(get_u16(buf + 5));
  p.pitch_sd = get_u16(buf + 7);
  p.roll_mean = static_cast<int16_t>(get_u16(buf + 9));
  p.temp = static_cast<int16_t>(get_u16(buf + 11));
  p.vbat = get_u16(buf + 13);
  p.vpanel = get_u16(buf + 15);
  p.ipanel = get_u16(buf + 17);
  p.chg = buf[19];
  p.awake_ms_prev = get_u16(buf + 20);
  p.flags = get_u16(buf + 22);
  *out = p;
  return DecodeStatus::Ok;
}

const char* decode_status_name(DecodeStatus s) {
  switch (s) {
    case DecodeStatus::Ok: return "ok";
    case DecodeStatus::BadLength: return "bad_length";
    case DecodeStatus::BadCrc: return "bad_crc";
    case DecodeStatus::BadVersion: return "bad_version";
  }
  return "unknown";
}

int16_t q_pitch(double deg) { return static_cast<int16_t>(clamp_round(deg * 1000.0, -32767, 32767)); }
uint16_t q_pitch_sd(double deg) { return static_cast<uint16_t>(clamp_round(deg * 1000.0, 0, 65535)); }
int16_t q_roll(double deg) { return static_cast<int16_t>(clamp_round(deg * 100.0, -32767, 32767)); }
int16_t q_temp(double c) { return static_cast<int16_t>(clamp_round(c * 10.0, -32767, 32767)); }
uint16_t q_ipanel(double ma) { return static_cast<uint16_t>(clamp_round(ma * 10.0, 0, 65535)); }
uint16_t q_u16(double v) { return static_cast<uint16_t>(clamp_round(v, 0, 65535)); }

}  // namespace tide
