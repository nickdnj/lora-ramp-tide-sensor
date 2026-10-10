"""Uplink payload v1 codec (ARCHITECTURE 4.7, ADR-004).

26 bytes, little-endian, carried as a MeshCore channel datagram with
data_type 0xFF54. CRC-16/CCITT-FALSE over bytes 0-23, stored little-endian at 24.

The C++ firmware codec (firmware/lib/tidecore) must agree with this module on
every vector in tests/vectors/packets_v1.json.
"""

from __future__ import annotations

import math
import struct
from dataclasses import asdict, dataclass

PAYLOAD_VERSION = 1
PAYLOAD_LEN = 26
DATA_TYPE = 0xFF54

# ver, node_id, seq, boot_count, pitch_med, pitch_sd, roll_mean, temp, vbat,
# vpanel, ipanel, chg, awake_ms_prev, flags  (crc appended separately)
_BODY = struct.Struct("<BBHBhHhhHHHBHH")
assert _BODY.size == 24

# chg bits
CHG_CHRG = 1 << 0
CHG_DONE = 1 << 1
CHG_COLD_INHIBIT = 1 << 2
CHG_CE_OVERRIDE = 1 << 3
CHG_LATCH_FAULT = 1 << 4
CHG_CE_PULSE = 1 << 5

CHG_NAMES = {
    CHG_CHRG: "charging",
    CHG_DONE: "done",
    CHG_COLD_INHIBIT: "cold_charge_inhibit",
    CHG_CE_OVERRIDE: "ce_override",
    CHG_LATCH_FAULT: "charger_latch_fault",
    CHG_CE_PULSE: "ce_pulse",
}

# flags bits
F_LOW_BATT = 1 << 0
F_CRITICAL_BATT = 1 << 1
F_HIGH_SD = 1 << 2
F_OUT_OF_RANGE = 1 << 3
F_REBOOT = 1 << 4
F_BROWNOUT_RESET = 1 << 5
F_WDT_RESET = 1 << 6
F_SENSOR_ERROR = 1 << 7
F_INA_ERROR = 1 << 8
F_REDUCED_INTERVAL = 1 << 9
F_SENSOR_SKIPPED = 1 << 10
F_SHORT_SAMPLE = 1 << 11

FLAG_NAMES = {
    F_LOW_BATT: "low_batt",
    F_CRITICAL_BATT: "critical_batt",
    F_HIGH_SD: "high_sd",
    F_OUT_OF_RANGE: "out_of_range",
    F_REBOOT: "reboot",
    F_BROWNOUT_RESET: "brownout_reset",
    F_WDT_RESET: "wdt_reset",
    F_SENSOR_ERROR: "sensor_error",
    F_INA_ERROR: "ina_error",
    F_REDUCED_INTERVAL: "reduced_interval",
    F_SENSOR_SKIPPED: "sensor_skipped",
    F_SHORT_SAMPLE: "short_sample",
}


class DecodeError(ValueError):
    """Raised with a parse_status code: bad_length, bad_crc, bad_version."""

    def __init__(self, status: str, message: str) -> None:
        super().__init__(message)
        self.status = status


def crc16_ccitt_false(data: bytes) -> int:
    """CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection, xorout 0."""
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


@dataclass(frozen=True)
class PayloadV1:
    """Raw (integer, on-the-wire) field values."""

    node_id: int
    seq: int
    boot_count: int
    pitch_med: int  # 0.001 deg
    pitch_sd: int  # 0.001 deg
    roll_mean: int  # 0.01 deg
    temp: int  # 0.1 C
    vbat: int  # mV
    vpanel: int  # mV
    ipanel: int  # 0.1 mA
    chg: int
    awake_ms_prev: int
    flags: int
    ver: int = PAYLOAD_VERSION

    # ---- engineering-unit views -------------------------------------------
    @property
    def pitch_deg(self) -> float:
        return self.pitch_med / 1000.0

    @property
    def pitch_sd_deg(self) -> float:
        return self.pitch_sd / 1000.0

    @property
    def roll_deg(self) -> float:
        return self.roll_mean / 100.0

    @property
    def temp_c(self) -> float:
        return self.temp / 10.0

    @property
    def ipanel_ma(self) -> float:
        return self.ipanel / 10.0

    def flag_names(self) -> list[str]:
        return [n for bit, n in FLAG_NAMES.items() if self.flags & bit]

    def chg_names(self) -> list[str]:
        return [n for bit, n in CHG_NAMES.items() if self.chg & bit]

    def to_dict(self) -> dict:
        return asdict(self)


_RANGES = {
    "ver": (0, 0xFF),
    "node_id": (0, 0xFF),
    "seq": (0, 0xFFFF),
    "boot_count": (0, 0xFF),
    "pitch_med": (-32768, 32767),
    "pitch_sd": (0, 0xFFFF),
    "roll_mean": (-32768, 32767),
    "temp": (-32768, 32767),
    "vbat": (0, 0xFFFF),
    "vpanel": (0, 0xFFFF),
    "ipanel": (0, 0xFFFF),
    "chg": (0, 0xFF),
    "awake_ms_prev": (0, 0xFFFF),
    "flags": (0, 0xFFFF),
}


def encode(p: PayloadV1) -> bytes:
    for name, (lo, hi) in _RANGES.items():
        v = getattr(p, name)
        if not isinstance(v, int) or v < lo or v > hi:
            raise ValueError(f"{name}={v!r} outside [{lo}, {hi}]")
    body = _BODY.pack(
        p.ver, p.node_id, p.seq, p.boot_count, p.pitch_med, p.pitch_sd, p.roll_mean,
        p.temp, p.vbat, p.vpanel, p.ipanel, p.chg, p.awake_ms_prev, p.flags,
    )
    return body + crc16_ccitt_false(body).to_bytes(2, "little")


def decode(data: bytes) -> PayloadV1:
    """Decode and validate. Raises DecodeError(status) on any problem."""
    if len(data) != PAYLOAD_LEN:
        raise DecodeError("bad_length", f"payload length {len(data)} != {PAYLOAD_LEN}")
    body, crc_rx = data[:24], int.from_bytes(data[24:26], "little")
    crc = crc16_ccitt_false(body)
    if crc != crc_rx:
        raise DecodeError("bad_crc", f"crc 0x{crc_rx:04X} != computed 0x{crc:04X}")
    f = _BODY.unpack(body)
    if f[0] != PAYLOAD_VERSION:
        raise DecodeError("bad_version", f"payload version {f[0]} not supported")
    return PayloadV1(
        ver=f[0], node_id=f[1], seq=f[2], boot_count=f[3], pitch_med=f[4], pitch_sd=f[5],
        roll_mean=f[6], temp=f[7], vbat=f[8], vpanel=f[9], ipanel=f[10], chg=f[11],
        awake_ms_prev=f[12], flags=f[13],
    )


# ---- quantization (engineering units -> wire integers) ----------------------
# Rule shared with firmware: round half away from zero, then clamp (never wrap).
# Signed fields clamp to +/-32767 (the documented +/-32.767 deg range).

def round_half_away(x: float) -> int:
    if math.isnan(x):
        raise ValueError("NaN cannot be quantized")
    return int(math.floor(abs(x) + 0.5)) * (1 if x >= 0 else -1)


def _clamp(v: int, lo: int, hi: int) -> int:
    return lo if v < lo else hi if v > hi else v


def q_pitch(deg: float) -> int:
    return _clamp(round_half_away(deg * 1000.0), -32767, 32767)


def q_pitch_sd(deg: float) -> int:
    return _clamp(round_half_away(deg * 1000.0), 0, 65535)


def q_roll(deg: float) -> int:
    return _clamp(round_half_away(deg * 100.0), -32767, 32767)


def q_temp(c: float) -> int:
    return _clamp(round_half_away(c * 10.0), -32767, 32767)


def q_mv(v: float) -> int:
    """Volts to mV."""
    return _clamp(round_half_away(v * 1000.0), 0, 65535)


def q_ipanel(ma: float) -> int:
    return _clamp(round_half_away(ma * 10.0), 0, 65535)


def q_u16(v: float) -> int:
    return _clamp(round_half_away(v), 0, 65535)
