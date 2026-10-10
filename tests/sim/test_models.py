"""Sanity checks on the simulator's world models (so the e2e results rest on
models that behave as described)."""

import numpy as np
import pytest

from conftest import T0
from sim.noaa_fake import SimNoaaProvider
from sim.power import PowerSystem, Weather, clear_sky_poa
from sim.radio import OFFLINE_QUEUE, SimRadio
from sim.node import TxPacket
from sim.world import SurgeEvent, TideWorld
from tidesvc.ingest import ChannelFrame, LinkEvent
from tidesvc.noaa import NoaaError


def test_tide_range_and_extremes():
    w = TideWorld(T0, T0 + 30 * 86400)
    ext = w.astro_extremes(T0, T0 + 30 * 86400)
    assert all(a[2] != b[2] for a, b in zip(ext, ext[1:]))  # alternate H/L
    ranges = [abs(a[1] - b[1]) for a, b in zip(ext, ext[1:])]
    assert 0.6 < np.median(ranges) < 1.1 and max(ranges) < 1.5
    gaps_h = [(b[0] - a[0]) / 3600 for a, b in zip(ext, ext[1:])]
    assert 5 < min(gaps_h) and max(gaps_h) < 8
    for t, v, typ in ext[:6]:
        around = w.astro(np.array([t - 600, t + 600]))
        assert (v >= around).all() if typ == "H" else (v <= around).all()


def test_surge_and_noaa_fake_excludes_surge():
    w = TideWorld(T0, T0 + 5 * 86400, surges=[SurgeEvent(T0 + 2 * 86400, 0.7)])
    assert float(w.surge(T0 + 2 * 86400)) == pytest.approx(0.7)
    now = {"t": T0}
    prov = SimNoaaProvider(w, outages=[(T0 + 3600, T0 + 7200)], now_fn=lambda: now["t"])
    ext = prov.fetch_hilo("8531942", T0 + 86400, T0 + 3 * 86400)
    for e in ext:
        assert e.v == pytest.approx(float(w.astro(e.t)), abs=0.002)  # predictions = astronomical only
    obs = prov.fetch_observed("8531680", T0 + 2 * 86400 - 3600, T0 + 2 * 86400)
    assert all(o.v - o.pred_v > 0.5 for o in obs)  # Sandy Hook sees the surge in its residual
    now["t"] = T0 + 5000
    with pytest.raises(NoaaError):
        prov.fetch_hilo("8531942", T0, T0 + 86400)


def test_december_insolation_scaled_and_night_dark():
    w = Weather(T0, 30, -5 * 3600)
    psh = [w.day_psh(k) for k in range(30)]
    assert np.mean(psh) == pytest.approx(3.45, rel=0.01)
    assert clear_sky_poa(T0) == 0.0  # local midnight
    noon = T0 + 12 * 3600
    assert clear_sky_poa(noon) > 400  # low December sun on a vertical south face


def test_charger_physics():
    w = Weather(T0, 5, -5 * 3600)
    p = PowerSystem(w, soc_mah=1500)
    p.ce_disabled = False
    noon = T0 + 12 * 3600
    p.enclosure.temp_c = 10.0
    for k in range(60):
        p.step(noon + 60 * k, 60, 0.5, "d")
    assert p.truth["d"]["charge_mah"] > 1.0  # charging in sun
    # cold: hardware backstop below -3 C blocks charge, the panel still covers the load
    p2 = PowerSystem(w, soc_mah=1500)
    p2.ce_disabled = False
    p2.enclosure.temp_c = -6.0
    p2.weather.mean_air_c = -20
    for k in range(10):
        p2.step(noon + 60 * k, 60, 0.5, "d")
    assert p2.hw_cold and p2.truth["d"]["charge_mah"] == 0.0 and p2.truth["d"]["harvest_mah"] > 0
    # safety timer: 6 h of continuous charging latches unless CE is pulsed
    p3 = PowerSystem(w, soc_mah=500, isc_ma=5000)
    p3.ce_disabled = False
    p3.enclosure.temp_c = 15.0
    p3.weather.mean_air_c = 15
    p3.timer_s = 5.9 * 3600
    for k in range(10):
        p3.step(noon + 60 * k, 60, 0.5, "d")
    assert p3.latched and p3.stat_pins(noon) == (0, 0)
    p3.ce_pulse()
    assert not p3.latched


def test_radio_duplicates_and_queue():
    r = SimRadio(p_relay=1.0, p_direct=1.0, p_corrupt=0.0, host_disconnects=[(T0 + 100, T0 + 100 + 20 * 400)])
    r.schedule_background(T0, T0 + 86400)
    for k in range(30):
        r.transmit(TxPacket(T0 + 300 * k, b"x" * 26, k, 1, 0.0))
    evs = list(r.pop_until(T0 + 86400))
    frames = [e for e in evs if isinstance(e, ChannelFrame) and e.channel_idx == 1]
    assert r.stats.duplicates == 30
    assert r.stats.queue_dropped > 0
    links = [e.status for e in evs if isinstance(e, LinkEvent) and e.detail != "heartbeat"]
    assert links == ["error", "ok"]
    assert len(frames) == 60 - r.stats.queue_dropped
    assert OFFLINE_QUEUE == 16
