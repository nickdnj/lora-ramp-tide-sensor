"""Shared test helpers. Everything here is offline and deterministic."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tidesvc import codec  # noqa: E402
from tidesvc import db as dbmod  # noqa: E402
from tidesvc.config import Config  # noqa: E402
from tidesvc.ingest import ChannelFrame  # noqa: E402
from tidesvc.noaa import Extreme, ObsPoint, StaticPredictionProvider  # noqa: E402
from tidesvc.timeutil import parse_iso  # noqa: E402

VECTORS = ROOT / "tests" / "vectors"
FIXTURES = ROOT / "tests" / "fixtures"

T0 = parse_iso("2026-12-03T05:00:00Z")  # midnight local (EST)
M2_S = 12.42 * 3600
MEAN = 0.48
AMP = 0.45
L_TRUE = 7.62
THETA0 = 0.8


def tide(t: float) -> float:
    """Single-constituent synthetic tide (MLLW metres) for unit tests."""
    return MEAN + AMP * math.cos(2 * math.pi * (t - T0) / M2_S)


def tide_extremes(t_start: float, t_end: float) -> list[Extreme]:
    out = []
    k = math.floor((t_start - T0) / (M2_S / 2)) - 1
    while True:
        t = T0 + k * M2_S / 2
        if t > t_end:
            break
        if t >= t_start:
            out.append(Extreme(t, tide(t), "H" if k % 2 == 0 else "L"))
        k += 1
    return out


HINGE = 1.6  # ramp hinge (level-ramp float height), metres above MLLW


def pitch_for_level(level: float, l_eff: float = L_TRUE, theta0: float = THETA0, hinge: float = HINGE) -> float:
    """Pitch a node would report for a water level (MLLW), ramp hinge at +1.6 m."""
    return theta0 + math.degrees(math.asin((level - hinge) / l_eff))


@pytest.fixture
def cfg() -> Config:
    c = Config()
    c.storage.db_path = ":unused:"
    return c


@pytest.fixture
def conn(tmp_path):
    c = dbmod.connect(tmp_path / "tide.db")
    yield c
    c.close()


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "tide.db"


@pytest.fixture
def provider() -> StaticPredictionProvider:
    ext = tide_extremes(T0 - 5 * 86400, T0 + 40 * 86400)
    obs = [ObsPoint(t, tide(t) + 0.01 * math.sin(t / 5000.0), tide(t))
           for t in [T0 - 4 * 86400 + 360 * i for i in range(int(44 * 86400 / 360))]]
    return StaticPredictionProvider(ext, obs)


def payload(seq: int, pitch: float, *, boot: int = 1, sd: float = 0.02, roll: float = 0.4, temp: float = 7.5,
            vbat: int = 3300, vpanel: int = 0, ipanel: float = 0.0, chg: int = 0, awake: int = 3900,
            flags: int = 0, node: int = 1) -> bytes:
    return codec.encode(codec.PayloadV1(
        node_id=node, seq=seq & 0xFFFF, boot_count=boot & 0xFF, pitch_med=codec.q_pitch(pitch),
        pitch_sd=codec.q_pitch_sd(sd), roll_mean=codec.q_roll(roll), temp=codec.q_temp(temp), vbat=vbat,
        vpanel=vpanel, ipanel=codec.q_ipanel(ipanel), chg=chg, awake_ms_prev=awake, flags=flags))


def frame(t: float, data: bytes, *, path_len: int = 1, channel: int = 1, data_type: int = 0xFF54,
          snr: float = 7.0) -> ChannelFrame:
    return ChannelFrame(rx_at=t, channel_idx=channel, data_type=data_type, payload=data, snr_db=snr,
                        path_len=path_len)
