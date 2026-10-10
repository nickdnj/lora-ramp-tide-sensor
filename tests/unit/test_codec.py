"""SV-D1, FW-U1..U3, FW-U5: payload v1 codec against the shared golden vectors."""

import json

import pytest

from conftest import VECTORS
from tidesvc import codec

V = json.loads((VECTORS / "packets_v1.json").read_text())


def test_crc_check_values():
    for c in V["crc_checks"]:
        assert codec.crc16_ccitt_false(c["ascii"].encode()) == c["crc"]
    assert codec.crc16_ccitt_false(b"123456789") == 0x29B1


@pytest.mark.parametrize("vec", V["valid"], ids=lambda v: v["name"])
def test_encode_matches_vector(vec):
    p = codec.PayloadV1(**vec["fields"])
    assert codec.encode(p).hex() == vec["hex"]
    assert len(bytes.fromhex(vec["hex"])) == 26


@pytest.mark.parametrize("vec", V["valid"], ids=lambda v: v["name"])
def test_decode_matches_vector(vec):
    p = codec.decode(bytes.fromhex(vec["hex"]))
    assert p.to_dict() == {**vec["fields"]}


@pytest.mark.parametrize("vec", V["invalid"], ids=lambda v: v["name"])
def test_invalid_vectors(vec):
    with pytest.raises(codec.DecodeError) as e:
        codec.decode(bytes.fromhex(vec["hex"]))
    assert e.value.status == vec["expect"]


def test_any_single_bit_flip_detected():
    good = bytes.fromhex(V["valid"][0]["hex"])
    for i in range(24 * 8):
        b = bytearray(good)
        b[i // 8] ^= 1 << (i % 8)
        with pytest.raises(codec.DecodeError):
            codec.decode(bytes(b))


def test_little_endian_offsets():
    p = codec.decode(bytes.fromhex(V["valid"][0]["hex"]))
    raw = codec.encode(p)
    assert int.from_bytes(raw[2:4], "little") == p.seq
    assert int.from_bytes(raw[5:7], "little", signed=True) == p.pitch_med
    assert int.from_bytes(raw[7:9], "little") == p.pitch_sd
    assert int.from_bytes(raw[13:15], "little") == p.vbat
    assert raw[19] == p.chg
    assert int.from_bytes(raw[22:24], "little") == p.flags


QFN = {"pitch": codec.q_pitch, "pitch_sd": codec.q_pitch_sd, "roll": codec.q_roll, "temp": codec.q_temp,
       "ipanel": codec.q_ipanel}


@pytest.mark.parametrize("q", V["quantize"], ids=lambda q: f"{q['kind']}:{q['in']}")
def test_quantize_clamps_never_wraps(q):
    assert QFN[q["kind"]](q["in"]) == q["out"]


def test_encode_rejects_out_of_range():
    p = codec.PayloadV1(**{**V["valid"][0]["fields"], "seq": 70000})
    with pytest.raises(ValueError):
        codec.encode(p)


def test_flag_and_chg_names():
    p = codec.decode(bytes.fromhex(next(v for v in V["valid"] if v["name"] == "cold_inhibit")["hex"]))
    assert "cold_charge_inhibit" in p.chg_names() and "ce_override" in p.chg_names()
    p2 = codec.decode(bytes.fromhex(next(v for v in V["valid"] if v["name"] == "reboot_first_frame")["hex"]))
    assert p2.flag_names() == ["reboot", "brownout_reset"]
