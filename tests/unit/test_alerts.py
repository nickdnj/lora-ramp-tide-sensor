"""Alert engine (ARCHITECTURE 6.8, TEST-PLAN 4.5, SV-N4): frozen clock, fake notifier."""

import datetime as dt

import pytest

from conftest import T0, frame, payload, pitch_for_level, tide
from test_derive_noaa import insert_cal
from tidesvc.alerts import AlertEngine, format_email
from tidesvc.core import Core
from tidesvc.ingest import AdvertEvent, LinkEvent
from tidesvc.notify import RecordingNotifier
from tidesvc.tempest import FakeTempestSource


@pytest.fixture
def world(conn, cfg, provider):
    n = RecordingNotifier()
    core = Core(conn, cfg, provider, n)
    insert_cal(conn)
    core.deriver.invalidate()
    return core, n


def run(core, t_start, t_end, level_fn, *, seq0=0, step=300, path_len=1, gap=None):
    t, seq = t_start, seq0
    while t < t_end:
        if gap is None or not (gap[0] <= t < gap[1]):
            core.handle(frame(t, payload(seq, pitch_for_level(level_fn(t))), path_len=path_len))
        for k in range(0, step, 60):
            core.tick(t + k)
        t += step
        seq += 1
    return seq


def kinds(conn, open_only=False):
    q = "SELECT kind FROM alerts" + (" WHERE cleared_at IS NULL" if open_only else "") + " ORDER BY id"
    return [r[0] for r in conn.execute(q)]


def test_surge_open_hold_clear_and_single_email(world, conn):
    core, n = world
    # +0.35 m over 1 h (0.35 m/h, above the 0.15 m/h rapid-rise threshold), hold 2 h, recede
    def surge(t):
        x = (t - T0) / 3600 - 3
        return 0.0 if x < 0 else 0.35 * min(x, 1) if x < 3 else max(0.0, 0.35 * (1 - (x - 3)))
    run(core, T0, T0 + 12 * 3600, lambda t: tide(t) + surge(t))
    assert kinds(conn).count("SURGE_WARNING") == 1
    assert "RAPID_RISE" in kinds(conn)
    rows = conn.execute("SELECT * FROM alerts WHERE kind='SURGE_WARNING'").fetchone()
    assert rows["cleared_at"] is not None and rows["cleared_at"] > rows["opened_at"]
    assert "for 30 min" in rows["clear_condition"]
    subj = [s for s, _ in n.sent if "SURGE_WARNING" in s]
    assert len(subj) == 1  # de-duplicated
    body = next(b for s, b in n.sent if "SURGE_WARNING" in s)
    assert "Clears when" in body and "Sandy Hook" in body and "Tempest context unavailable" in body
    assert "SURGE_SEVERE" not in kinds(conn)


def test_two_consecutive_readings_required(world, conn):
    core, n = world
    spike_t = T0 + 4 * 3600
    # a single reading 0.5 m high (as a wake would) cannot open a surge alert via the median anyway;
    # drive the residual directly instead: one high reading then normal
    run(core, T0, T0 + 6 * 3600, lambda t: tide(t) + (0.5 if spike_t <= t < spike_t + 300 else 0))
    assert "SURGE_WARNING" not in kinds(conn)


def test_restart_does_not_resend(world, conn, cfg):
    core, n = world
    run(core, T0, T0 + 3 * 3600, lambda t: tide(t) + (0.45 if t > T0 + 3600 else 0))
    assert kinds(conn, True).count("SURGE_WARNING") == 1
    sent = len(n.sent)
    eng2 = AlertEngine(conn, cfg, n)  # process restart
    eng2.evaluate(T0 + 3 * 3600 + 60)
    assert len(n.sent) == sent


def test_email_failure_retried(world, conn):
    core, n = world
    n.fail_next = 2
    run(core, T0, T0 + 3 * 3600, lambda t: tide(t) + (0.45 if t > T0 + 3600 else 0))
    rows = conn.execute("SELECT * FROM alerts WHERE notify=1").fetchall()
    assert rows and all(r["notified_at"] is not None for r in rows)
    assert sum(r["notify_attempts"] for r in rows) == len(rows) + 2
    assert n.attempts == len(n.sent) + 2


def test_node_silent_and_clear(world, conn, cfg):
    core, n = world
    run(core, T0, T0 + 6 * 3600, tide, gap=(T0 + 2 * 3600, T0 + 3 * 3600))
    a = conn.execute("SELECT * FROM alerts WHERE kind='NODE_SILENT'").fetchone()
    assert a is not None
    assert a["opened_at"] - (T0 + 2 * 3600 - 300) == pytest.approx(cfg.node.silent_alert_after_s + 60, abs=60)
    assert a["cleared_at"] == pytest.approx(T0 + 3 * 3600, abs=1)


def test_repeater_vs_gateway_vs_node(world, conn, cfg):
    core, n = world
    core.handle(LinkEvent(T0, "ok", "connected"))
    core.handle(AdvertEvent(T0, "ab", "rep"))
    # relayed frames keep the repeater ok without adverts
    run(core, T0, T0 + 6 * 3600, tide, path_len=1)
    assert "REPEATER_SILENT" not in kinds(conn)
    # direct-only frames for > 4 h: repeater silent while node is fine
    run(core, T0 + 6 * 3600, T0 + 11 * 3600, tide, seq0=72, path_len=0)
    assert "REPEATER_SILENT" in kinds(conn, True)
    body = next(b for s, b in n.sent if "REPEATER_SILENT" in s)
    assert "directly" in body
    # advert alone clears it
    core.handle(AdvertEvent(T0 + 11 * 3600, "ab", "rep"))
    core.tick(T0 + 11 * 3600 + 60)
    assert "REPEATER_SILENT" not in kinds(conn, True)
    # gateway down: GATEWAY_DOWN after 5 min; REPEATER_SILENT suppressed while it is open
    core.handle(LinkEvent(T0 + 12 * 3600, "error", "usb unplugged"))
    for k in range(0, 6 * 3600, 60):
        core.tick(T0 + 12 * 3600 + k)
    assert "GATEWAY_DOWN" in kinds(conn, True)
    assert "REPEATER_SILENT" not in kinds(conn, True)
    assert "NODE_SILENT" in kinds(conn, True)


def test_energy_streak_early_warning(world, conn, cfg):
    core, n = world
    end = dt.date(2026, 12, 31)
    for k in range(14):
        d = end - dt.timedelta(days=k)
        net = -1.0 if k < 7 else 20.0
        conn.execute("INSERT INTO energy_daily(date, harvest_mah, consumption_est_mah, net_mah, coverage_pct, "
                     "reached_full, charge_inhibit_cold_h) VALUES (?,?,?,?,99,0,0)", (d.isoformat(), 12 + net, 12.0, net))
    from tidesvc.timeutil import local_day_bounds
    now = local_day_bounds(dt.date(2027, 1, 1))[0] + 600
    core.alerts.refresh_energy(now)
    core.alerts.evaluate(now)
    assert "ENERGY_NEGATIVE_STREAK" in kinds(conn, True)
    assert "ENERGY_DEFICIT" not in kinds(conn)  # 14-day ratio 1.79 (marginal): the streak never sets the verdict
    body = next(b for s, b in n.sent if "NEGATIVE_STREAK" in s)
    assert "early warning" in next(s for s, _ in n.sent if "NEGATIVE_STREAK" in s)
    assert "official" in body


def test_surge_watch_only_when_tempest_ok_and_tempest_unavailable_silent(conn, cfg, provider):
    cfg.tempest.enabled = True
    state = {"p": 1010.0, "fail": False}

    def src():
        if state["fail"]:
            raise __import__("tidesvc.tempest", fromlist=["TempestError"]).TempestError("HTTP 401")
        return {"obs": [{"timestamp": state["now"], "sea_level_pressure": state["p"], "wind_avg": 9.5,
                         "wind_direction": 60, "air_temperature": 5.0}]}
    n = RecordingNotifier()
    core = Core(conn, cfg, provider, n, FakeTempestSource(src))
    insert_cal(conn)
    core.deriver.invalidate()
    t = T0
    seq = 0
    while t < T0 + 10 * 3600:
        state["now"] = t
        state["p"] = 1010.0 - 1.5 * (t - T0) / 3600
        core.handle(frame(t, payload(seq, pitch_for_level(tide(t) + (0.2 if t > T0 + 7 * 3600 else 0)))))
        for k in range(0, 300, 60):
            state["now"] = t + k
            core.tick(t + k)
        t += 300
        seq += 1
    assert "SURGE_WATCH" in kinds(conn)
    assert any("[advisory]" in s for s, _ in n.sent)
    state["fail"] = True
    for k in range(0, 3 * 3600, 60):
        core.tick(t + k)
    assert "TEMPEST_UNAVAILABLE" in kinds(conn, True)
    assert not any("TEMPEST_UNAVAILABLE" in s for s, _ in n.sent)


def test_format_email_lists_clear_condition(world, conn):
    core, n = world
    core.alerts._open("SENSOR_QUALITY", T0, 7, 6, {})
    row = conn.execute("SELECT * FROM alerts").fetchone()
    s, b = format_email(row, core.cfg)
    assert "SENSOR_QUALITY" in s and "Clears when: fewer than 2" in b
