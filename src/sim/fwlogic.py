"""Python mirror of the portable firmware core (firmware/lib/tidecore).

The simulator's node model uses this so its behaviour matches the C++ firmware.
Both implementations are held to tests/vectors/fw_logic_v1.json and
tests/vectors/stats_v1.json.

Rules (ARCHITECTURE 4.3, 4.6, 4.7; thresholds are placeholders until bench B8):
- Battery state with hysteresis: NORMAL -> LOW below 3150 mV, LOW -> NORMAL at
  >= 3200 mV; -> CRITICAL below 3050 mV, CRITICAL -> LOW at >= 3100 mV.
  Intervals 300 / 900 / 3600 s. CRITICAL skips sampling (health-only payload).
- Cold rule (BQ25185 /CE HIGH = charging disabled): temperature unknown or
  < +1.0 C -> disable; > +2.0 C -> enable; otherwise hold the previous state.
- Safety-timer pulse: continuous "charging" (STAT 1/0) is accumulated across
  wakes; at >= 4 h a CE pulse is issued and the counter resets. The counter
  resets on any non-charging STAT and while the cold rule holds /CE HIGH. A
  latched charger (STAT 0/0) also gets a recovery pulse unless cold-held.
- DONE is reported only when STAT is 1/1 while /CE was LOW (enabled) at the
  time STAT was read (i.e. the previous cycle's CE state).
- A hardware cold fault is inferred from STAT 0/1 with temperature < +5.0 C.
- Burst statistics: median (even count: mean of the two middle values),
  population SD, mean roll. high_sd above 0.25 deg; out_of_range when
  |pitch| > 15 deg or |roll| > 10 deg; short_sample below 300 samples;
  sensor_error below 30 valid samples.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

NORMAL, LOW, CRITICAL = 0, 1, 2
STATE_NAMES = {NORMAL: "normal", LOW: "low", CRITICAL: "critical"}

LOW_ENTER_MV = 3150
LOW_EXIT_MV = 3200
CRIT_ENTER_MV = 3050
CRIT_EXIT_MV = 3100
INTERVAL_S = {NORMAL: 300, LOW: 900, CRITICAL: 3600}

COLD_DISABLE_BELOW_C = 1.0
COLD_ENABLE_ABOVE_C = 2.0
HW_COLD_FAULT_BELOW_C = 5.0
CE_PULSE_AFTER_S = 4 * 3600

HIGH_SD_DEG = 0.25
OOR_PITCH_DEG = 15.0
OOR_ROLL_DEG = 10.0
BURST_SAMPLES = 300
MIN_VALID_SAMPLES = 30

# chg bits / flags (same as tidesvc.codec; duplicated so this mirror stands alone)
CHG_CHRG, CHG_DONE, CHG_COLD, CHG_CE_OVR, CHG_LATCH, CHG_PULSE = (1 << i for i in range(6))
F_LOW_BATT, F_CRIT, F_HIGH_SD, F_OOR, F_REBOOT, F_BROWNOUT, F_WDT, F_SENSOR_ERR, \
    F_INA_ERR, F_REDUCED, F_SKIPPED, F_SHORT = (1 << i for i in range(12))


def next_batt_state(prev: int, vbat_mv: int | None) -> int:
    if vbat_mv is None:  # INA error: keep the previous state
        return prev
    if vbat_mv < CRIT_ENTER_MV:
        return CRITICAL
    if prev == CRITICAL and vbat_mv < CRIT_EXIT_MV:
        return CRITICAL
    if vbat_mv < LOW_ENTER_MV:
        return LOW
    if prev in (LOW, CRITICAL) and vbat_mv < LOW_EXIT_MV:
        return LOW
    return NORMAL


def batt_flags(state: int) -> int:
    if state == LOW:
        return F_LOW_BATT | F_REDUCED
    if state == CRITICAL:
        return F_LOW_BATT | F_CRIT | F_REDUCED | F_SKIPPED
    return 0


@dataclass(frozen=True)
class ChargerState:
    ce_disabled: bool = True  # pull-up default: charging off until firmware enables
    charging_elapsed_s: int = 0


@dataclass(frozen=True)
class ChargerOut:
    state: ChargerState
    ce_disabled: bool
    pulse: bool
    chg: int


def charger_step(prev: ChargerState, temp_c: float | None, stat1: int, stat2: int,
                 dt_s: int) -> ChargerOut:
    if temp_c is None or temp_c < COLD_DISABLE_BELOW_C:
        cold = True
    elif temp_c > COLD_ENABLE_ABOVE_C:
        cold = False
    else:
        cold = prev.ce_disabled
    charging = stat1 == 1 and stat2 == 0
    latched = stat1 == 0 and stat2 == 0
    elapsed = prev.charging_elapsed_s
    pulse = False
    if cold:
        elapsed = 0
    elif charging:
        elapsed += dt_s
        if elapsed >= CE_PULSE_AFTER_S:
            pulse = True
            elapsed = 0
    else:
        elapsed = 0
        if latched:
            pulse = True
    chg = 0
    if charging:
        chg |= CHG_CHRG
    if stat1 == 1 and stat2 == 1 and not prev.ce_disabled:
        chg |= CHG_DONE
    hw_cold = stat1 == 0 and stat2 == 1 and temp_c is not None and temp_c < HW_COLD_FAULT_BELOW_C
    if cold or hw_cold:
        chg |= CHG_COLD
    if cold:
        chg |= CHG_CE_OVR
    if latched:
        chg |= CHG_LATCH
    if pulse:
        chg |= CHG_PULSE
    st = ChargerState(ce_disabled=cold, charging_elapsed_s=elapsed)
    return ChargerOut(state=st, ce_disabled=cold, pulse=pulse, chg=chg)


@dataclass(frozen=True)
class BurstStats:
    n: int
    pitch_median: float
    pitch_sd: float
    roll_mean: float


def median(xs) -> float:
    s = sorted(xs)
    n = len(s)
    if n == 0:
        raise ValueError("median of empty sequence")
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def burst_stats(pitch, roll) -> BurstStats:
    n = len(pitch)
    mean = math.fsum(pitch) / n
    sd = math.sqrt(math.fsum((x - mean) ** 2 for x in pitch) / n)
    return BurstStats(n=n, pitch_median=median(pitch), pitch_sd=sd,
                      roll_mean=math.fsum(roll) / len(roll))


def sample_flags(stats: BurstStats | None, n_valid: int) -> int:
    f = 0
    if stats is None or n_valid < MIN_VALID_SAMPLES:
        return F_SENSOR_ERR | (F_SHORT if n_valid < BURST_SAMPLES else 0)
    if n_valid < BURST_SAMPLES:
        f |= F_SHORT
    if stats.pitch_sd > HIGH_SD_DEG:
        f |= F_HIGH_SD
    if abs(stats.pitch_median) > OOR_PITCH_DEG or abs(stats.roll_mean) > OOR_ROLL_DEG:
        f |= F_OOR
    return f


# --------------------------------------------------------------------------
def generate_logic_vectors() -> dict:
    """Vectors for the C++ host tests and for tests/unit/test_fwlogic.py."""
    batt_seq = [3400, 3200, 3151, 3149, 3160, 3199, 3200, 3100, 3049, 3060, 3099, 3100,
                3150, 3199, 3200, 3000, 3300]
    b_steps = []
    st = NORMAL
    for mv in batt_seq:
        st = next_batt_state(st, mv)
        b_steps.append({"vbat_mv": mv, "state": st, "interval_s": INTERVAL_S[st], "flags": batt_flags(st)})
    b_steps.append({"vbat_mv": None, "state": st, "interval_s": INTERVAL_S[st], "flags": batt_flags(st)})

    def run(seq, start=ChargerState()):
        out, s = [], start
        for temp, s1, s2, dt in seq:
            r = charger_step(s, temp, s1, s2, dt)
            out.append({"temp_c": temp, "stat1": s1, "stat2": s2, "dt_s": dt,
                        "ce_disabled": r.ce_disabled, "pulse": r.pulse, "chg": r.chg,
                        "charging_elapsed_s": r.state.charging_elapsed_s})
            s = r.state
        return out

    # cold rule boundaries approached from both directions (STAT 1/1 = disabled/idle)
    falling = [(t, 1, 1, 300) for t in (85.0, 2.1, 2.0, 1.9, 1.1, 1.0, 0.9, -40.0)]
    rising = [(t, 1, 1, 300) for t in (-40.0, 0.9, 1.0, 1.1, 1.9, 2.0, 2.1, 85.0)]
    unknown = [(10.0, 1, 0, 300), (None, 1, 0, 300), (10.0, 1, 1, 300)]
    # 5 h of continuous sun-charging at 20 C: pulse at 4 h, counter resets
    pulse_seq = [(20.0, 1, 0, 300)] * 60
    # charging, then cold for a while (no pulse during cold hold), then warm again
    cold_mid = [(20.0, 1, 0, 300)] * 30 + [(0.5, 1, 1, 300)] * 6 + [(3.0, 1, 0, 300)] * 50
    # charging interrupted (STAT 1/1 done) resets the counter; latch gets a recovery pulse
    misc = [(20.0, 1, 0, 300)] * 10 + [(20.0, 1, 1, 300)] + [(20.0, 1, 0, 300)] * 5 + \
           [(20.0, 0, 0, 300)] + [(3.0, 0, 1, 300), (12.0, 0, 1, 300)]
    start_enabled = ChargerState(ce_disabled=False, charging_elapsed_s=0)
    charger = {
        "cold_falling": run(falling, start_enabled),
        "cold_rising": run(rising, ChargerState(ce_disabled=True)),
        "unknown_temp": run(unknown, start_enabled),
        "safety_pulse": run(pulse_seq, start_enabled),
        "cold_interrupts_pulse": run(cold_mid, start_enabled),
        "misc_done_latch_hwcold": run(misc, start_enabled),
    }
    charger_starts = {
        "cold_falling": {"ce_disabled": False, "charging_elapsed_s": 0},
        "cold_rising": {"ce_disabled": True, "charging_elapsed_s": 0},
        "unknown_temp": {"ce_disabled": False, "charging_elapsed_s": 0},
        "safety_pulse": {"ce_disabled": False, "charging_elapsed_s": 0},
        "cold_interrupts_pulse": {"ce_disabled": False, "charging_elapsed_s": 0},
        "misc_done_latch_hwcold": {"ce_disabled": False, "charging_elapsed_s": 0},
    }

    flag_cases = []
    for name, med, sd, roll, n in [
        ("nominal", -3.2, 0.02, 0.4, 300), ("high_sd", -3.2, 0.26, 0.4, 300),
        ("sd_at_threshold", -3.2, 0.25, 0.4, 300), ("oor_pitch", 15.001, 0.02, 0.0, 300),
        ("oor_pitch_neg", -15.5, 0.02, 0.0, 300), ("pitch_at_15", 15.0, 0.02, 0.0, 300),
        ("oor_roll", 1.0, 0.02, -10.01, 300), ("short", 1.0, 0.02, 0.0, 299),
        ("sensor_error", 1.0, 0.02, 0.0, 29),
    ]:
        stt = BurstStats(n=n, pitch_median=med, pitch_sd=sd, roll_mean=roll)
        flag_cases.append({"name": name, "pitch_median": med, "pitch_sd": sd, "roll_mean": roll,
                           "n_valid": n, "flags": sample_flags(stt, n)})
    return {
        "format": "firmware portable-core logic vectors",
        "battery": {"thresholds_mv": {"low_enter": LOW_ENTER_MV, "low_exit": LOW_EXIT_MV,
                                      "crit_enter": CRIT_ENTER_MV, "crit_exit": CRIT_EXIT_MV},
                    "start_state": NORMAL, "steps": b_steps},
        "charger": {"pulse_after_s": CE_PULSE_AFTER_S, "starts": charger_starts, "sequences": charger},
        "sample_flags": flag_cases,
    }


__all__ = [
    "NORMAL", "LOW", "CRITICAL", "INTERVAL_S", "next_batt_state", "batt_flags", "ChargerState",
    "charger_step", "burst_stats", "sample_flags", "median", "generate_logic_vectors", "replace",
]
