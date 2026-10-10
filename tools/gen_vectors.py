#!/usr/bin/env python3
"""Generate the shared golden vectors in tests/vectors/.

The byte packing and CRC here are deliberately an *independent* implementation
(manual int.to_bytes, table-free CRC written separately) so the vectors are not
just the Python codec checking itself. Both pytest (tidesvc.codec) and the C++
host tests (firmware/test/host) consume the generated JSON.

Usage: python tools/gen_vectors.py            # writes tests/vectors/*.json
       python tools/gen_vectors.py --check    # exit 1 if files would change
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "vectors"

FIELDS = [
    # name, size, signed
    ("ver", 1, False), ("node_id", 1, False), ("seq", 2, False), ("boot_count", 1, False),
    ("pitch_med", 2, True), ("pitch_sd", 2, False), ("roll_mean", 2, True), ("temp", 2, True),
    ("vbat", 2, False), ("vpanel", 2, False), ("ipanel", 2, False), ("chg", 1, False),
    ("awake_ms_prev", 2, False), ("flags", 2, False),
]


def crc_ccitt_false(data: bytes) -> int:
    reg = 0xFFFF
    for byte in data:
        for i in range(7, -1, -1):
            bit = (byte >> i) & 1
            top = (reg >> 15) & 1
            reg = (reg << 1) & 0xFFFF
            if top ^ bit:
                reg ^= 0x1021
    return reg


def pack(fields: dict) -> bytes:
    out = b""
    for name, size, signed in FIELDS:
        out += int(fields[name]).to_bytes(size, "little", signed=signed)
    assert len(out) == 24
    return out + crc_ccitt_false(out).to_bytes(2, "little")


def base(**kw) -> dict:
    f = dict(ver=1, node_id=1, seq=1234, boot_count=3, pitch_med=-4321, pitch_sd=21,
             roll_mean=41, temp=75, vbat=3318, vpanel=5120, ipanel=1215, chg=0b000001,
             awake_ms_prev=3912, flags=0)
    f.update(kw)
    return f


def packet_vectors() -> dict:
    valid = []

    def add(name, desc, fields):
        valid.append({"name": name, "description": desc, "fields": fields,
                      "hex": pack(fields).hex()})

    add("typical", "Typical mid-tide reading, charging", base())
    add("all_zero", "Every field zero except ver", base(node_id=0, seq=0, boot_count=0, pitch_med=0,
        pitch_sd=0, roll_mean=0, temp=0, vbat=0, vpanel=0, ipanel=0, chg=0, awake_ms_prev=0, flags=0))
    add("all_max", "Every unsigned field at max, signed at +max",
        base(node_id=255, seq=65535, boot_count=255, pitch_med=32767, pitch_sd=65535, roll_mean=32767,
             temp=32767, vbat=65535, vpanel=65535, ipanel=65535, chg=255, awake_ms_prev=65535, flags=65535))
    add("signed_min", "Signed fields at -32768 (wire minimum)",
        base(pitch_med=-32768, roll_mean=-32768, temp=-32768))
    add("negative_values", "Negative pitch, roll and temperature",
        base(pitch_med=-8123, roll_mean=-152, temp=-123))
    add("wide_sd", "pitch_sd above 0.255 deg (the u16 widening)", base(pitch_sd=1234, flags=1 << 2))
    add("seq_wrap_last", "seq 65535 just before wrap", base(seq=65535))
    add("seq_wrap_first", "seq 0 just after wrap", base(seq=0))
    add("reboot_first_frame", "First frame after a reset: seq 0, reboot+brownout flags",
        base(seq=0, boot_count=4, flags=(1 << 4) | (1 << 5), awake_ms_prev=0))
    add("cold_inhibit", "Cold charge inhibit by firmware rule (CE override)",
        base(temp=-35, chg=(1 << 2) | (1 << 3), ipanel=0))
    add("health_only", "Critical battery, sensor skipped (health-only payload)",
        base(pitch_med=0, pitch_sd=0, roll_mean=0, vbat=3010,
             flags=(1 << 1) | (1 << 0) | (1 << 9) | (1 << 10)))
    for bit in range(16):
        add(f"flag_bit_{bit}", f"flags bit {bit} set alone", base(flags=1 << bit))
    add("flags_all", "Every flag bit set", base(flags=0xFFFF))
    for bit in range(8):
        add(f"chg_bit_{bit}", f"chg bit {bit} set alone", base(chg=1 << bit))
    add("chg_all", "Every chg bit set", base(chg=0xFF))

    invalid = []
    good = bytes.fromhex(valid[0]["hex"])
    flipped = bytearray(good)
    flipped[5] ^= 0x01
    invalid.append({"name": "bad_crc_bitflip", "hex": bytes(flipped).hex(), "expect": "bad_crc"})
    badcrc = bytearray(good)
    badcrc[24] ^= 0xFF
    invalid.append({"name": "bad_crc_field", "hex": bytes(badcrc).hex(), "expect": "bad_crc"})
    v2 = base(ver=2)
    invalid.append({"name": "wrong_version", "hex": pack(v2).hex(), "expect": "bad_version"})
    invalid.append({"name": "length_25", "hex": good[:25].hex(), "expect": "bad_length"})
    invalid.append({"name": "length_27", "hex": (good + b"\x00").hex(), "expect": "bad_length"})
    invalid.append({"name": "length_0", "hex": "", "expect": "bad_length"})

    crc_checks = [
        {"ascii": "123456789", "crc": 0x29B1},
        {"ascii": "", "crc": 0xFFFF},
        {"ascii": "A", "crc": crc_ccitt_false(b"A")},
    ]

    def q(x, scale, lo, hi):
        v = int(math.floor(abs(x * scale) + 0.5)) * (1 if x * scale >= 0 else -1)
        return max(lo, min(hi, v))

    quant = []
    for deg in [0.0, 1.2344, 1.2345, -1.2345, -0.0004, -0.0005, 0.0005, 32.767, 32.7675, 40.0, -40.0, -32.768]:
        quant.append({"kind": "pitch", "in": deg, "out": q(deg, 1000.0, -32767, 32767)})
    for deg in [0.0, 0.2555, 0.256, 65.535, 70.0, -0.001]:
        quant.append({"kind": "pitch_sd", "in": deg, "out": q(deg, 1000.0, 0, 65535)})
    for deg in [0.0, 0.415, -0.415, 0.004, -0.005, 400.0]:
        quant.append({"kind": "roll", "in": deg, "out": q(deg, 100.0, -32767, 32767)})
    for c in [25.0, -40.0, 85.0, 7.45, -7.45, 0.04, -0.05, 4000.0]:
        quant.append({"kind": "temp", "in": c, "out": q(c, 10.0, -32767, 32767)})
    for ma in [0.0, 121.5, 0.04, 0.05, 7000.0, -1.0]:
        quant.append({"kind": "ipanel", "in": ma, "out": q(ma, 10.0, 0, 65535)})

    return {
        "format": "tide-sensor payload v1 golden vectors",
        "spec": "docs/ARCHITECTURE.md section 4.7; CRC-16/CCITT-FALSE over bytes 0-23, little-endian",
        "length": 26,
        "data_type": 0xFF54,
        "rounding_rule": "round half away from zero, then clamp to the field range (never wrap); signed fields clamp to +/-32767",
        "crc_checks": crc_checks,
        "valid": valid,
        "invalid": invalid,
        "quantize": quant,
    }


def stats_vectors() -> dict:
    """Median/SD rule shared by firmware (stats.cpp) and server (derive.median).

    Median of an even count = mean of the two middle values (after sorting).
    SD = population standard deviation (divide by N).
    """
    cases = []

    def add(name, xs):
        xs = [float(x) for x in xs]
        n = len(xs)
        s = sorted(xs)
        med = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0
        mean = math.fsum(xs) / n
        sd = math.sqrt(math.fsum((x - mean) ** 2 for x in xs) / n)
        cases.append({"name": name, "samples": xs, "median": med, "mean": mean, "sd_pop": sd})

    add("constant_300", [-4.321] * 300)
    add("ramp_300", [i * 0.001 for i in range(300)])
    add("outlier_300", [1.0] * 299 + [25.0])
    add("two_values_even", [1.0, 2.0])
    add("odd_5", [5.0, 1.0, 4.0, 2.0, 3.0])
    add("even_unsorted_6", [0.3, -0.1, 0.2, 0.25, -0.05, 0.1])
    add("single", [3.14159])
    # deterministic pseudo-noise around -3.5 deg (LCG so C++ needs no RNG)
    x, xs = 12345, []
    for _ in range(300):
        x = (1103515245 * x + 12345) % (1 << 31)
        xs.append(round(-3.5 + ((x / (1 << 31)) - 0.5) * 0.02, 6))
    add("noise_300", xs)
    assert statistics.median(cases[2]["samples"]) == cases[2]["median"]
    return {
        "format": "burst statistics vectors",
        "median_rule": "even count: mean of the two middle values after sorting",
        "sd_rule": "population standard deviation (divide by N)",
        "cases": cases,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    files = {
        "packets_v1.json": packet_vectors(),
        "stats_v1.json": stats_vectors(),
    }
    # fw_logic vectors come from the Python firmware mirror (sim.fwlogic).
    sys.path.insert(0, str(ROOT / "src"))
    from sim.fwlogic import generate_logic_vectors  # noqa: E402

    files["fw_logic_v1.json"] = generate_logic_vectors()
    OUT.mkdir(parents=True, exist_ok=True)
    changed = False
    for name, obj in files.items():
        text = json.dumps(obj, indent=1, sort_keys=False) + "\n"
        path = OUT / name
        old = path.read_text() if path.exists() else None
        if old != text:
            changed = True
            if not args.check:
                path.write_text(text)
                print(f"wrote {path.relative_to(ROOT)}")
    if args.check and changed:
        print("vectors out of date; run tools/gen_vectors.py")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
