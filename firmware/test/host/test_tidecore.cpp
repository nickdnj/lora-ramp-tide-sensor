// Host unit tests for the portable firmware core (TEST-PLAN FW-U1..U10).
// Reads the same golden vectors as pytest from tests/vectors/ (path from VECTORS_DIR or argv[1]).
#include <cmath>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#include "cycle.h"
#include "minijson.h"
#include "payload.h"
#include "power_logic.h"
#include "stats.h"

using namespace tide;
using minijson::Value;

static int g_fail = 0, g_pass = 0;
#define CHECK(cond, ...)                                              \
  do {                                                                \
    if (cond) {                                                       \
      ++g_pass;                                                       \
    } else {                                                          \
      ++g_fail;                                                       \
      std::fprintf(stderr, "FAIL %s:%d: %s | ", __FILE__, __LINE__, #cond); \
      std::fprintf(stderr, __VA_ARGS__);                              \
      std::fprintf(stderr, "\n");                                     \
    }                                                                 \
  } while (0)

static std::string g_dir;

static Value load(const char* name) {
  std::ifstream f(g_dir + "/" + name);
  if (!f) {
    std::fprintf(stderr, "cannot open %s/%s\n", g_dir.c_str(), name);
    std::exit(2);
  }
  std::stringstream ss;
  ss << f.rdbuf();
  return minijson::Parser(ss.str()).parse();
}

static std::vector<uint8_t> unhex(const std::string& h) {
  std::vector<uint8_t> out;
  for (size_t i = 0; i + 1 < h.size(); i += 2) out.push_back(static_cast<uint8_t>(std::stoul(h.substr(i, 2), nullptr, 16)));
  return out;
}

static std::string hex(const uint8_t* b, size_t n) {
  static const char* d = "0123456789abcdef";
  std::string s;
  for (size_t i = 0; i < n; ++i) {
    s += d[b[i] >> 4];
    s += d[b[i] & 15];
  }
  return s;
}

static PayloadV1 from_fields(const Value& f) {
  PayloadV1 p;
  p.ver = static_cast<uint8_t>(f["ver"].i());
  p.node_id = static_cast<uint8_t>(f["node_id"].i());
  p.seq = static_cast<uint16_t>(f["seq"].i());
  p.boot_count = static_cast<uint8_t>(f["boot_count"].i());
  p.pitch_med = static_cast<int16_t>(f["pitch_med"].i());
  p.pitch_sd = static_cast<uint16_t>(f["pitch_sd"].i());
  p.roll_mean = static_cast<int16_t>(f["roll_mean"].i());
  p.temp = static_cast<int16_t>(f["temp"].i());
  p.vbat = static_cast<uint16_t>(f["vbat"].i());
  p.vpanel = static_cast<uint16_t>(f["vpanel"].i());
  p.ipanel = static_cast<uint16_t>(f["ipanel"].i());
  p.chg = static_cast<uint8_t>(f["chg"].i());
  p.awake_ms_prev = static_cast<uint16_t>(f["awake_ms_prev"].i());
  p.flags = static_cast<uint16_t>(f["flags"].i());
  return p;
}

static bool same(const PayloadV1& a, const PayloadV1& b) {
  return a.ver == b.ver && a.node_id == b.node_id && a.seq == b.seq && a.boot_count == b.boot_count &&
         a.pitch_med == b.pitch_med && a.pitch_sd == b.pitch_sd && a.roll_mean == b.roll_mean && a.temp == b.temp &&
         a.vbat == b.vbat && a.vpanel == b.vpanel && a.ipanel == b.ipanel && a.chg == b.chg &&
         a.awake_ms_prev == b.awake_ms_prev && a.flags == b.flags;
}

// ---- FW-U1..U3, FW-U5, FW-U8 -------------------------------------------------------
static void test_packets() {
  const Value v = load("packets_v1.json");
  for (const auto& c : v["crc_checks"].arr) {
    const std::string& s = c["ascii"].str;
    CHECK(crc16_ccitt_false(reinterpret_cast<const uint8_t*>(s.data()), s.size()) == c["crc"].i(), "crc '%s'",
          s.c_str());
  }
  for (const auto& vec : v["valid"].arr) {
    const PayloadV1 p = from_fields(vec["fields"]);
    uint8_t buf[kPayloadLen];
    encode(p, buf);
    CHECK(hex(buf, kPayloadLen) == vec["hex"].str, "encode %s", vec["name"].str.c_str());
    const std::vector<uint8_t> b = unhex(vec["hex"].str);
    PayloadV1 d;
    CHECK(decode(b.data(), b.size(), &d) == DecodeStatus::Ok, "decode %s", vec["name"].str.c_str());
    CHECK(same(d, p), "roundtrip %s", vec["name"].str.c_str());
  }
  for (const auto& vec : v["invalid"].arr) {
    const std::vector<uint8_t> b = unhex(vec["hex"].str);
    PayloadV1 d;
    const DecodeStatus st = decode(b.data(), b.size(), &d);
    CHECK(vec["expect"].str == decode_status_name(st), "invalid %s -> %s", vec["name"].str.c_str(),
          decode_status_name(st));
  }
  for (const auto& q : v["quantize"].arr) {
    const std::string& k = q["kind"].str;
    const double in = q["in"].num;
    long long got = -999999;
    if (k == "pitch") got = q_pitch(in);
    else if (k == "pitch_sd") got = q_pitch_sd(in);
    else if (k == "roll") got = q_roll(in);
    else if (k == "temp") got = q_temp(in);
    else if (k == "ipanel") got = q_ipanel(in);
    CHECK(got == q["out"].i(), "quantize %s(%.6f) = %lld, want %lld", k.c_str(), in, got, q["out"].i());
  }
  // a single flipped bit anywhere in the body is caught
  const std::vector<uint8_t> good = unhex(v["valid"][0]["hex"].str);
  int caught = 0;
  for (int bit = 0; bit < 24 * 8; ++bit) {
    std::vector<uint8_t> b = good;
    b[bit / 8] ^= static_cast<uint8_t>(1u << (bit % 8));
    PayloadV1 d;
    if (decode(b.data(), b.size(), &d) != DecodeStatus::Ok) ++caught;
  }
  CHECK(caught == 24 * 8, "bit flips caught %d", caught);
}

// ---- FW-U4 ------------------------------------------------------------------------
static void test_stats() {
  const Value v = load("stats_v1.json");
  for (const auto& c : v["cases"].arr) {
    std::vector<double> xs;
    for (const auto& x : c["samples"].arr) xs.push_back(x.num);
    std::vector<double> roll(xs.size(), 0.0), scratch(xs.size());
    BurstStats st;
    CHECK(burst_stats(xs.data(), roll.data(), xs.size(), scratch.data(), &st), "stats %s", c["name"].str.c_str());
    CHECK(std::fabs(st.pitch_median - c["median"].num) < 1e-12, "median %s %.12f vs %.12f", c["name"].str.c_str(),
          st.pitch_median, c["median"].num);
    CHECK(std::fabs(st.pitch_sd - c["sd_pop"].num) < 1e-9, "sd %s %.12f vs %.12f", c["name"].str.c_str(), st.pitch_sd,
          c["sd_pop"].num);
  }
}

// ---- FW-U6, FW-U7, FW-U9, FW-U10 ---------------------------------------------------
static void test_logic() {
  const Value v = load("fw_logic_v1.json");
  BattState s = static_cast<BattState>(v["battery"]["start_state"].i());
  for (const auto& st : v["battery"]["steps"].arr) {
    const bool valid = !st["vbat_mv"].is_null();
    s = next_batt_state(s, valid ? static_cast<int32_t>(st["vbat_mv"].i()) : 0, valid);
    CHECK(s == st["state"].i(), "battery state at %lld", valid ? st["vbat_mv"].i() : -1);
    CHECK(interval_s(s) == st["interval_s"].i(), "interval");
    CHECK(batt_flags(s) == st["flags"].i(), "batt flags");
  }
  const Value& seqs = v["charger"]["sequences"];
  for (const auto& kv : seqs.obj) {
    const Value& start = v["charger"]["starts"][kv.first];
    ChargerState cs;
    cs.ce_disabled = start["ce_disabled"].b;
    cs.charging_elapsed_s = static_cast<uint32_t>(start["charging_elapsed_s"].i());
    int k = 0;
    for (const auto& st : kv.second.arr) {
      ChargerInputs in;
      in.temp_valid = !st["temp_c"].is_null();
      in.temp_c = in.temp_valid ? st["temp_c"].num : 0;
      in.stat1 = static_cast<uint8_t>(st["stat1"].i());
      in.stat2 = static_cast<uint8_t>(st["stat2"].i());
      in.dt_s = static_cast<uint32_t>(st["dt_s"].i());
      in.vin_present = st["vin_present"].b;
      const ChargerOut o = charger_step(cs, in);
      CHECK(o.ce_disabled == st["ce_disabled"].b && o.pulse == st["pulse"].b && o.chg == st["chg"].i() &&
                o.state.charging_elapsed_s == st["charging_elapsed_s"].i(),
            "charger %s step %d: ce=%d pulse=%d chg=%d elapsed=%u", kv.first.c_str(), k, o.ce_disabled, o.pulse, o.chg,
            o.state.charging_elapsed_s);
      cs = o.state;
      ++k;
    }
  }
  for (const auto& c : v["sample_flags"].arr) {
    BurstStats st;
    st.n = static_cast<size_t>(c["n_valid"].i());
    st.pitch_median = c["pitch_median"].num;
    st.pitch_sd = c["pitch_sd"].num;
    st.roll_mean = c["roll_mean"].num;
    CHECK(sample_flags(&st, st.n) == c["flags"].i(), "sample flags %s", c["name"].str.c_str());
  }
}

// ---- cycle with fakes ---------------------------------------------------------------
struct FakeSensor : IInclinometer {
  double temp = 12.0, pitch = -4.321, sd = 0.0;
  bool fail = false;
  int bursts = 0;
  bool read_temperature(double* t) override {
    *t = temp;
    return !fail;
  }
  bool burst(double* p, double* r, size_t max_n, size_t* n) override {
    ++bursts;
    if (fail) { *n = 0; return false; }
    for (size_t i = 0; i < max_n; ++i) {
      p[i] = pitch + ((i % 2) ? sd : -sd);
      r[i] = 0.41;
    }
    *n = max_n;
    return true;
  }
};

struct FakePower : IPowerMonitor {
  int32_t vbat = 3320, vpanel = 3700;
  double ipanel = 42.0;
  uint8_t s1 = 1, s2 = 0;
  bool ce_disabled = true;
  int pulses = 0;
  bool read(int32_t* vb, int32_t* vp, double* ip) override {
    *vb = vbat;
    *vp = vpanel;
    *ip = ipanel;
    return true;
  }
  void read_stat(uint8_t* a, uint8_t* b) override { *a = s1; *b = s2; }
  void set_ce_disabled(bool d) override { ce_disabled = d; }
  void pulse_ce() override { ++pulses; }
};

struct FakeUplink : IUplink {
  std::vector<std::vector<uint8_t>> sent;
  uint16_t last_type = 0;
  bool send_group_data(uint16_t t, const uint8_t* b, size_t n) override {
    last_type = t;
    sent.emplace_back(b, b + n);
    return true;
  }
};

static void test_cycle() {
  RtcState rtc;
  on_cold_boot(&rtc, 6, /*brownout=*/true, /*watchdog=*/false);
  FakeSensor sens;
  FakePower pwr;
  FakeUplink up;
  uint32_t now = 1000;
  CycleResult r = run_cycle(&rtc, 1, now, sens, pwr, up);
  finish_cycle(&rtc, 3900);
  CHECK(up.sent.size() == 1 && up.last_type == kDataType && up.sent[0].size() == kPayloadLen, "one datagram sent");
  PayloadV1 d;
  CHECK(decode(up.sent[0].data(), up.sent[0].size(), &d) == DecodeStatus::Ok, "decodes");
  CHECK(d.boot_count == 7 && d.seq == 0, "boot %d seq %d", d.boot_count, d.seq);
  CHECK((d.flags & kFlagReboot) && (d.flags & kFlagBrownoutReset), "reboot+brownout flags 0x%x", d.flags);
  CHECK(d.pitch_med == -4321 && d.roll_mean == 41 && d.temp == 120, "measurement fields");
  CHECK(!r.ce_disabled && !pwr.ce_disabled && (d.chg & kChgCharging), "charging enabled at 12 C");
  CHECK(r.sleep_s == 300, "normal interval");
  // second cycle: no reboot flag, seq 1, awake_ms_prev reported
  now += 300;
  r = run_cycle(&rtc, 1, now, sens, pwr, up);
  finish_cycle(&rtc, 3950);
  decode(up.sent[1].data(), kPayloadLen, &d);
  CHECK(d.seq == 1 && !(d.flags & kFlagReboot) && d.awake_ms_prev == 3900, "second frame seq %d flags 0x%x", d.seq,
        d.flags);
  // 4 h of charging -> one CE pulse
  for (int i = 0; i < 48; ++i) {
    now += 300;
    run_cycle(&rtc, 1, now, sens, pwr, up);
  }
  CHECK(pwr.pulses == 1, "pulses %d", pwr.pulses);
  // cold: /CE HIGH, override + cold bits, no pulses while cold
  sens.temp = 0.5;
  for (int i = 0; i < 60; ++i) {
    now += 300;
    run_cycle(&rtc, 1, now, sens, pwr, up);
  }
  decode(up.sent.back().data(), kPayloadLen, &d);
  CHECK(pwr.ce_disabled && (d.chg & kChgCeOverride) && (d.chg & kChgColdInhibit) && pwr.pulses == 1, "cold rule");
  // sensor failure: temperature unknown -> charging disabled, sensor_error, pitch zeroed
  sens.temp = 20.0;
  sens.fail = true;
  now += 300;
  run_cycle(&rtc, 1, now, sens, pwr, up);
  decode(up.sent.back().data(), kPayloadLen, &d);
  CHECK((d.flags & kFlagSensorError) && pwr.ce_disabled && d.pitch_med == 0, "sensor error fail-safe 0x%x", d.flags);
  // critical battery: health-only payload, 60 min interval, no burst
  sens.fail = false;
  pwr.vbat = 3000;
  const int bursts_before = sens.bursts;
  now += 300;
  r = run_cycle(&rtc, 1, now, sens, pwr, up);
  decode(up.sent.back().data(), kPayloadLen, &d);
  CHECK(sens.bursts == bursts_before && (d.flags & kFlagSensorSkipped) && (d.flags & kFlagCriticalBatt) &&
            r.sleep_s == 3600 && d.pitch_med == 0,
        "critical: flags 0x%x sleep %u", d.flags, r.sleep_s);
  // seq wrap
  rtc.seq = 65535;
  pwr.vbat = 3320;
  now += 3600;
  run_cycle(&rtc, 1, now, sens, pwr, up);
  CHECK(rtc.seq == 0, "seq wraps to 0");
  // night: STAT floats to 1/1 with no panel input -> never DONE
  pwr.s1 = 1;
  pwr.s2 = 1;
  pwr.vpanel = 0;
  now += 300;
  run_cycle(&rtc, 1, now, sens, pwr, up);
  now += 300;
  run_cycle(&rtc, 1, now, sens, pwr, up);
  decode(up.sent.back().data(), kPayloadLen, &d);
  CHECK(!(d.chg & kChgDone), "no DONE at night chg=0x%x", d.chg);
  pwr.vpanel = 7200;
  now += 300;
  run_cycle(&rtc, 1, now, sens, pwr, up);
  decode(up.sent.back().data(), kPayloadLen, &d);
  CHECK(d.chg & kChgDone, "DONE with panel input chg=0x%x", d.chg);
  // high SD burst sets high_sd
  sens.sd = 0.3;
  now += 300;
  run_cycle(&rtc, 1, now, sens, pwr, up);
  decode(up.sent.back().data(), kPayloadLen, &d);
  CHECK((d.flags & kFlagHighSd) && d.pitch_sd == 300, "high_sd flags 0x%x sd %u", d.flags, d.pitch_sd);
}

int main(int argc, char** argv) {
#ifdef VECTORS_DIR
  g_dir = VECTORS_DIR;
#endif
  if (argc > 1) g_dir = argv[1];
  if (g_dir.empty()) g_dir = "../../../tests/vectors";
  test_packets();
  test_stats();
  test_logic();
  test_cycle();
  std::printf("tidecore host tests: %d passed, %d failed\n", g_pass, g_fail);
  return g_fail ? 1 : 0;
}
