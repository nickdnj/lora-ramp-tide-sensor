"""SV-C4..C8: install fit, identifiability, bounds, matched extremes, versioning/reprocess."""

import math
import random

import pytest

from conftest import HINGE, L_TRUE, T0, THETA0, frame, payload, pitch_for_level, tide
from test_derive_noaa import insert_cal
from tidesvc import calibration as cal
from tidesvc.core import Core
from tidesvc.derive import load_calibrations
from tidesvc.noaa import ObsPoint
from tidesvc.notify import RecordingNotifier

MARK = 2.5  # bulkhead mark, metres above MLLW


def two_harmonic(t):
    return 0.48 + 0.42 * math.cos(2 * math.pi * (t - T0) / (12.42 * 3600)) + \
        0.08 * math.cos(2 * math.pi * (t - T0) / (23.93 * 3600) + 1.0)


def feed(core, start, n, step, level_fn, rng, noise_deg=0.005, jitter_m=0.01, h_offset=0.0):
    for i in range(n):
        t = start + i * step
        core.tick(t)
        lvl = level_fn(t) + rng.gauss(0, jitter_m) + h_offset
        p = pitch_for_level(lvl) + rng.gauss(0, noise_deg)
        core.handle(frame(t, payload(i, p)))


def test_install_fit_recovers_known_parameters(conn, cfg, provider):
    rng = random.Random(4)
    core = Core(conn, cfg, provider, RecordingNotifier())
    feed(core, T0, 300, 300, two_harmonic, rng)
    # level check at the start (reference digital level, +/-0.05 deg)
    t_lc = T0 + 1800
    true_angle = math.degrees(math.asin((two_harmonic(t_lc) - HINGE) / L_TRUE))
    cal.add_observation(conn, t_lc, "level_check", angle_deg=true_angle + 0.03)
    # tape at high, low and mid tide (+/-2 mm)
    for t in (T0 + 0 * 3600 + 900, T0 + 6.2 * 3600, T0 + 9.3 * 3600):
        cal.add_observation(conn, t, "tape", freeboard_m=MARK - two_harmonic(t) + rng.gauss(0, 0.002))
    cid = cal.fit_install(conn, cfg, T0 + 86400)
    c = next(x for x in load_calibrations(conn) if x.id == cid)
    assert c.datum == "bulkhead_mark"
    assert c.theta0_deg == pytest.approx(THETA0 - 0.03, abs=0.02)
    # theta0 error is absorbed into h0 (SV-C5): compare levels, not h0 directly
    for lvl in (0.0, 0.5, 1.0):
        assert c.level(pitch_for_level(lvl)) + MARK == pytest.approx(lvl, abs=0.01)
    assert c.l_eff_m == pytest.approx(L_TRUE, rel=0.01)


def test_theta0_perturbation_absorbed_into_h0(conn, cfg, provider):
    """SV-C5: theta0 fixed; a 0.1 deg error shifts h0 by ~L*cos*0.1deg and levels barely change."""
    pitches = [pitch_for_level(x) for x in (0.0, 1.0)]
    ys = [x - MARK for x in (0.0, 1.0)]
    fits = []
    for th in (THETA0, THETA0 + 0.1):
        s = [math.sin(math.radians(p - th)) for p in pitches]
        L = (ys[1] - ys[0]) / (s[1] - s[0])
        fits.append((ys[0] - L * s[0], L, th))
    (h_a, l_a, th_a), (h_b, l_b, th_b) = fits
    assert h_b - h_a == pytest.approx(L_TRUE * math.radians(0.1) * math.cos(math.radians(-6)), abs=0.002)
    assert abs(l_b - l_a) / l_a < 0.002
    mid = pitch_for_level(0.5)
    la = h_a + l_a * math.sin(math.radians(mid - th_a))
    lb = h_b + l_b * math.sin(math.radians(mid - th_b))
    assert abs(la - lb) < 0.001


def test_install_needs_two_states_half_metre_apart(conn, cfg):
    conn.execute("INSERT INTO cal_observations(t, kind, angle_deg, pitch_deg) VALUES (?, 'level_check', -5, -4.2)",
                 (T0,))
    for t, fb in ((T0, 2.0), (T0 + 3600, 1.7)):
        conn.execute("INSERT INTO cal_observations(t, kind, freeboard_m, pitch_deg) VALUES (?, 'tape', ?, -4)", (t, fb))
    with pytest.raises(cal.CalibrationError, match="span"):
        cal.fit_install(conn, cfg, T0)


@pytest.mark.parametrize("dh,dl,ok", [(0.049, 0.0, True), (0.051, 0.0, False), (0.0, 0.029, True),
                                      (0.0, 0.031, False), (-0.05, -0.03, True), (-0.0501, 0.0, False)])
def test_refit_bounds(cfg, dh, dl, ok):
    assert cal.within_bounds(dh, dl, cfg.calibration) is ok


def _refit_world(conn, cfg, provider, offset):
    """Ten days of data whose truth differs from the active calibration by ``offset`` metres."""
    cfg.calibration.refit_days = 10
    rng = random.Random(7)
    core = Core(conn, cfg, provider, RecordingNotifier())
    insert_cal(conn, valid_from=T0 - 86400)
    core.deriver.invalidate()
    feed(core, T0, 10 * 288, 300, lambda t: tide(t), rng, noise_deg=0.003, jitter_m=0.005, h_offset=offset)
    return core


def test_monthly_refit_within_bounds_is_applied(conn, cfg, provider):
    core = _refit_world(conn, cfg, provider, offset=0.04)
    now = T0 + 10 * 86400
    res = cal.monthly_refit(conn, cfg, core.deriver, now)
    assert res["status"] == "active" and res["applied"]
    assert res["dh0_m"] == pytest.approx(-0.04, abs=0.01)  # observed is 4 cm high -> h0 moves down
    assert abs(res["dl_rel"]) < 0.01
    core.alerts.evaluate(now)
    assert core.alerts.open_alert("CALIBRATION_DRIFT") is None


def test_monthly_refit_outside_bounds_is_proposed_and_alerts(conn, cfg, provider):
    core = _refit_world(conn, cfg, provider, offset=0.08)
    now = T0 + 10 * 86400
    res = cal.monthly_refit(conn, cfg, core.deriver, now)
    assert res["status"] == "proposed" and not res["applied"]
    active = [c.id for c in load_calibrations(conn)]
    assert res["calibration_id"] not in active  # nothing applied silently
    core.alerts.evaluate(now)
    assert core.alerts.open_alert("CALIBRATION_DRIFT") is not None
    cal.reject(conn, res["calibration_id"])
    core.alerts.evaluate(now + 60)
    assert core.alerts.open_alert("CALIBRATION_DRIFT") is None


def test_matched_extremes_calm_gating_and_too_few(conn, cfg, provider):
    core = _refit_world(conn, cfg, provider, offset=0.0)
    c = load_calibrations(conn)[-1]
    pairs = cal.matched_extremes(conn, cfg, c, T0, T0 + 10 * 86400)
    assert len(pairs) >= 15
    assert all(abs(p.dt_min) <= 90 for p in pairs)
    assert max(abs(p.dt_min) for p in pairs) < 10
    # make every day stormy at Sandy Hook: nothing qualifies, nothing is fitted
    conn.execute("UPDATE noaa_observations SET v = pred_v + 0.2")
    assert cal.matched_extremes(conn, cfg, c, T0, T0 + 10 * 86400) == []
    res = cal.monthly_refit(conn, cfg, core.deriver, T0 + 10 * 86400)
    assert res["status"] == "skipped"
    assert conn.execute("SELECT COUNT(*) FROM calibrations").fetchone()[0] == 1


def test_versioning_and_reprocess_idempotent(conn, cfg, provider):
    core = _refit_world(conn, cfg, provider, offset=0.0)
    raw_before = conn.execute("SELECT COUNT(*), SUM(pitch_deg) FROM readings").fetchone()
    first = conn.execute("SELECT reading_id, calibration_id, level_raw_m FROM derived ORDER BY reading_id").fetchall()
    insert_cal(conn, h0=HINGE + 0.03, valid_from=T0 + 5 * 86400, method="manual")
    n = core.deriver.reprocess(T0)
    assert n == raw_before[0]
    again = conn.execute("SELECT reading_id, calibration_id, level_raw_m FROM derived ORDER BY reading_id").fetchall()
    late = [(a, b) for a, b in zip(first, again) if b["calibration_id"] != a["calibration_id"]]
    assert late and all(b["level_raw_m"] - a["level_raw_m"] == pytest.approx(0.03) for a, b in late)
    core.deriver.reprocess(T0)
    third = conn.execute("SELECT reading_id, calibration_id, level_raw_m FROM derived ORDER BY reading_id").fetchall()
    assert [tuple(r) for r in third] == [tuple(r) for r in again]
    assert tuple(conn.execute("SELECT COUNT(*), SUM(pitch_deg) FROM readings").fetchone()) == tuple(raw_before)


def test_refit_schedule_first_of_month_0300_local():
    from tidesvc.timeutil import parse_iso
    sched = parse_iso("2027-01-01T08:00:00Z")  # 03:00 EST
    assert not cal.is_refit_due(sched - 60, parse_iso("2026-12-01T08:00:00Z"))
    assert cal.is_refit_due(sched + 1, parse_iso("2026-12-01T08:00:00Z"))
    assert not cal.is_refit_due(sched + 3600, sched + 1)
    # November 1st 2026 is a DST day; 03:00 EST = 08:00Z
    assert cal.is_refit_due(parse_iso("2026-11-01T08:00:30Z"), parse_iso("2026-10-01T07:00:00Z"))


_ = ObsPoint
