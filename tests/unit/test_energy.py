"""SV-E1..E5, verdict, early-warning streak, and the harvest-definition fix."""

import datetime as dt

import pytest

from tidesvc import codec, energy
from tidesvc.timeutil import local_day_bounds

DAY = dt.date(2026, 12, 5)


def add(conn, t, *, ipanel=0.0, vbat=3300, vpanel=0, chg=0, awake=3900, flags=0, seq=[0]):
    seq[0] += 1
    conn.execute("INSERT INTO readings(node_id, boot_count, seq, t, rx_at, time_source, pitch_deg, vbat_mv, "
                 "vpanel_mv, ipanel_ma, chg_bits, awake_ms_prev, flags, temp_c) VALUES (1,1,?,?,?,'rx',-3,?,?,?,?,?,?,5)",
                 (seq[0] & 0xFFFF, t, t, vbat, vpanel, ipanel, chg, awake, flags))


def fill_day(conn, day, fn, step=300, skip=lambda t: False):
    start, end = local_day_bounds(day)
    t = start
    while t <= end:  # include the next midnight sample so the last segment is covered
        if not skip(t):
            add(conn, t, **fn(t - start))
        t += step


def test_trapezoid_integration_gaps_and_coverage(conn, cfg):
    # 10 mA while charging from 08:00 to 18:00 local, otherwise dark
    fill_day(conn, DAY, lambda s: {"ipanel": 10.0, "chg": codec.CHG_CHRG, "vpanel": 3600}
             if 8 * 3600 <= s < 18 * 3600 else {})
    r = energy.rollup_day(conn, cfg, DAY)
    assert r.harvest_mah == pytest.approx(100.0, abs=1.0)
    assert r.coverage_pct == pytest.approx(100.0, abs=0.01)
    assert r.charging_h == pytest.approx(10.0, abs=0.1)
    # a 30-minute hole (> 15 min) at noon is not integrated
    conn.execute("DELETE FROM readings")
    start, _ = local_day_bounds(DAY)
    fill_day(conn, DAY, lambda s: {"ipanel": 10.0, "chg": codec.CHG_CHRG}, skip=lambda t: start + 43200 < t < start + 45000)
    r2 = energy.rollup_day(conn, cfg, DAY)
    gap_h = (45000 - 43200) / 3600  # the one 30-min segment spanning the hole is dropped
    assert r2.harvest_mah == pytest.approx(240.0 - 10.0 * gap_h, abs=1.0)
    assert r2.coverage_pct == pytest.approx(100 * (1 - gap_h / 24), abs=0.2)


def test_harvest_not_credited_from_awake_load_when_not_charging(conn, cfg):
    """Cold-inhibited sunny day: the INA sample sees ~25 mA of awake load, not harvest."""
    fill_day(conn, DAY, lambda s: {"ipanel": 25.0, "vpanel": 6500, "chg": codec.CHG_COLD_INHIBIT | codec.CHG_CE_OVERRIDE}
             if 8 * 3600 <= s < 16 * 3600 else {})
    r = energy.rollup_day(conn, cfg, DAY)
    load = energy.avg_load_ma(cfg)
    assert r.harvest_mah == pytest.approx(load * 8, rel=0.05)  # panel only covers the load
    assert r.harvest_mah < 10  # naive integration would claim ~200 mAh
    assert r.charge_inhibit_cold_h == pytest.approx(8.0, abs=0.1)
    assert r.net_mah < 0


@pytest.mark.parametrize("day,hours", [(dt.date(2026, 11, 1), 25), (dt.date(2027, 3, 14), 23),
                                       (dt.date(2026, 12, 5), 24)])
def test_dst_days(conn, cfg, day, hours):
    s, e = local_day_bounds(day)
    assert (e - s) / 3600 == hours
    fill_day(conn, day, lambda s: {})
    r = energy.rollup_day(conn, cfg, day)
    assert r.coverage_pct == pytest.approx(100.0, abs=0.01)
    assert r.n_readings == hours * 12
    assert r.consumption_est_mah == pytest.approx(energy.avg_load_ma(cfg) * hours, rel=0.01)


def test_constants_recorded_and_model(conn, cfg):
    cfg.energy.i_sleep_ua = 80
    fill_day(conn, DAY, lambda s: {"awake": 7800})
    r = energy.rollup_day(conn, cfg, DAY)
    assert r.i_sleep_ua == 80 and r.i_awake_ma == pytest.approx(125 / 3.9)
    expected = 288 * 7.8 * (125 / 3.9) / 3600 + (86400 - 288 * 7.8) * 0.08 / 3600
    assert r.consumption_est_mah == pytest.approx(expected, rel=1e-6)


def _days(conn, rows, end=dt.date(2026, 12, 31)):
    for k, (h, c, cov) in enumerate(reversed(rows)):
        d = end - dt.timedelta(days=k)
        conn.execute("INSERT INTO energy_daily(date, harvest_mah, consumption_est_mah, net_mah, coverage_pct, "
                     "reached_full, charge_inhibit_cold_h) VALUES (?,?,?,?,?,0,0)", (d.isoformat(), h, c, h - c, cov))


NOW = local_day_bounds(dt.date(2027, 1, 1))[0] + 3600


@pytest.mark.parametrize("h,expect", [(24.0, "surplus"), (23.99, "marginal"), (12.0, "marginal"),
                                      (11.99, "deficit")])
def test_verdict_boundaries(conn, cfg, h, expect):
    _days(conn, [(h, 12.0, 99.0)] * 14)
    v = energy.verdict(conn, cfg, NOW)
    assert v["assessment"] == expect


def test_verdict_insufficient_data(conn, cfg):
    _days(conn, [(50.0, 12.0, 99.0)] * 6 + [(50.0, 12.0, 70.0)] * 8)
    assert energy.verdict(conn, cfg, NOW)["assessment"] == "insufficient_data"
    conn.execute("DELETE FROM energy_daily")
    _days(conn, [(50.0, 12.0, 80.0)] * 7)
    assert energy.verdict(conn, cfg, NOW)["assessment"] == "surplus"


def test_negative_streak_six_vs_seven_and_low_coverage_skip(conn, cfg):
    _days(conn, [(20.0, 12.0, 99.0)] + [(5.0, 12.0, 99.0)] * 6)
    assert energy.negative_streak(conn, cfg, NOW) == 6
    conn.execute("DELETE FROM energy_daily")
    _days(conn, [(20.0, 12.0, 99.0)] + [(5.0, 12.0, 99.0)] * 3 + [(50.0, 12.0, 40.0)] + [(5.0, 12.0, 99.0)] * 4)
    assert energy.negative_streak(conn, cfg, NOW) == 7  # low-coverage day neither extends nor breaks
    conn.execute("DELETE FROM energy_daily")
    _days(conn, [(5.0, 12.0, 99.0)] * 7 + [(12.0, 12.0, 99.0)])
    assert energy.negative_streak(conn, cfg, NOW) == 0  # net == 0 is non-negative


def test_soc_anchor_and_clamp(conn, cfg):
    start, _ = local_day_bounds(DAY)
    add(conn, start, chg=codec.CHG_DONE)
    for k in range(1, 289):
        add(conn, start + 300 * k)
    s = energy.soc_estimate(conn, cfg, start + 86400)
    load = energy.avg_load_ma(cfg)
    assert s["soc_anchor"]["at"] == start
    assert s["soc_mah"] == pytest.approx(cfg.energy.capacity_mah - 24 * load, abs=0.5)
    # big harvest cannot exceed capacity
    conn.execute("UPDATE readings SET ipanel_ma=200, chg_bits=1")
    conn.execute("UPDATE readings SET chg_bits=2 WHERE t=?", (start,))
    assert energy.soc_estimate(conn, cfg, start + 86400)["soc_mah"] <= cfg.energy.capacity_mah
    conn.execute("DELETE FROM readings")
    add(conn, start)
    assert energy.soc_estimate(conn, cfg, start)["soc_est_pct"] is None


def test_projected_days_to_empty_when_negative(conn, cfg):
    start, _ = local_day_bounds(dt.date(2026, 12, 31))
    add(conn, start, chg=codec.CHG_DONE)
    _days(conn, [(2.0, 12.0, 99.0)] * 14)
    v = energy.verdict(conn, cfg, NOW)
    assert v["assessment"] == "deficit" and v["projected_days_to_empty"] is not None
    assert 200 < v["projected_days_to_empty"] < 400
