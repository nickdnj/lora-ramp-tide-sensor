"""SV-A1..A11: stale/503, no demo data (as a property), read-only, composite endpoints."""

import itertools

import pytest
from fastapi.testclient import TestClient

from conftest import T0, frame, payload, pitch_for_level, tide
from test_derive_noaa import insert_cal
from tidesvc import db as dbmod
from tidesvc.api import create_app
from tidesvc.config import Config
from tidesvc.core import Core
from tidesvc.ingest import AdvertEvent, LinkEvent
from tidesvc.noaa import StaticPredictionProvider
from tidesvc.notify import RecordingNotifier
from tidesvc.tempest import FakeTempestSource, TempestError
from tidesvc.timeutil import FixedClock, parse_iso


def make(db_path, provider, cfg=None, tempest_fn=None):
    cfg = cfg or Config()
    conn = dbmod.connect(db_path)
    core = Core(conn, cfg, provider, RecordingNotifier(), FakeTempestSource(tempest_fn) if tempest_fn else None)
    clock = FixedClock(T0)
    client = TestClient(create_app(cfg, str(db_path), clock))
    return conn, core, clock, client


def feed(core, t0, t1, seq0=0, level_fn=tide, path_len=1):
    t, seq = t0, seq0
    while t < t1:
        core.tick(t)
        core.handle(frame(t, payload(seq, pitch_for_level(level_fn(t))), path_len=path_len))
        t += 300
        seq += 1
    return t, seq


def test_fresh_database_503_no_last_good(db_path, provider):
    conn, core, clock, client = make(db_path, provider)
    r = client.get("/api/v1/level/current")
    assert r.status_code == 503
    b = r.json()
    assert b["status"] == "error" and b["level_m"] is None and b["residual_m"] is None
    assert b["last_good"] is None
    assert client.get("/healthz").json() == {"status": "ok"}


def test_stale_boundary_and_503_body(db_path, provider):
    conn, core, clock, client = make(db_path, provider)
    insert_cal(conn)
    core.deriver.invalidate()
    core.handle(LinkEvent(T0, "ok", "connected"))
    t_end, _ = feed(core, T0, T0 + 3 * 3600)
    last = t_end - 300
    clock.set(last + 14 * 60 + 59)
    r = client.get("/api/v1/level/current")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    ok = r.json()
    assert ok["level_m"] is not None and ok["datum"].startswith("MLLW")
    assert ok["level_m"] == pytest.approx(tide(last - 750), abs=0.01)  # trailing median
    clock.set(last + 15 * 60 + 1)
    r = client.get("/api/v1/level/current")
    assert r.status_code == 503
    b = r.json()
    assert b["status"] == "stale" and b["error"]["code"] == "NODE_STALE"
    assert b["level_m"] is None and b["residual_m"] is None and b["level_raw_m"] is None
    assert b["last_good"]["at"] is not None and b["last_good"]["level_m"] == ok["level_m"]
    assert b["predicted_m"] is not None and "not an observation" in b["predicted_note"]
    assert b["predicted_m"] != b["level_m"]


def test_invalid_and_backfilled_excluded_from_current(db_path, provider):
    conn, core, clock, client = make(db_path, provider)
    insert_cal(conn)
    core.deriver.invalidate()
    t_end, seq = feed(core, T0, T0 + 3600)
    # high-SD readings after the good ones: current must not use them
    for k in range(3):
        core.handle(frame(t_end + 300 * k, payload(seq + k, pitch_for_level(2.0), sd=0.5)))
    clock.set(t_end + 600)
    b = client.get("/api/v1/level/current").json()
    assert b["as_of"] < "2026-12-03T06:00:00Z" or b["level_m"] < 1.2
    h = client.get("/api/v1/level/history", params={"from": "2026-12-03T05:00:00Z",
                                                    "to": "2026-12-03T07:00:00Z"}).json()
    bad = [s for s in h["series"] if not s["valid"]]
    assert len(bad) == 3 and all(s["reason"] == "high_sd" and s["level_m"] is None for s in bad)


def _state_combos():
    return list(itertools.product(["ok", "error"], ["ok", "stale", "silent"], ["ok", "error", "uncovered"],
                                  [True, False], ["ok", "disabled", "error"]))


@pytest.mark.parametrize("gw,node,noaa_st,has_cal,tmp", _state_combos())
def test_property_no_observed_field_is_invented(tmp_path, provider, gw, node, noaa_st, has_cal, tmp):
    """SV-A4: for every combination, observed fields are null or come from a valid reading."""
    cfg = Config()
    cfg.tempest.enabled = tmp != "disabled"

    def tsrc():
        if tmp == "error":
            raise TempestError("HTTP 401")
        return {"obs": [{"timestamp": clock.now(), "sea_level_pressure": 1000.0, "wind_avg": 3.0,
                         "wind_direction": 200}]}
    prov = StaticPredictionProvider([], fail=True) if noaa_st == "uncovered" else provider
    conn, core, clock, client = make(tmp_path / "t.db", prov, cfg, tsrc)
    if has_cal:
        insert_cal(conn)
        core.deriver.invalidate()
    core.handle(LinkEvent(T0, "ok", "c"))
    t_end, _ = feed(core, T0, T0 + 2 * 3600)
    if noaa_st == "error":
        prov.fail = True
        core.noaa.refresh_predictions(t_end)
    if gw == "error":
        core.handle(LinkEvent(t_end, "error", "gone"))
    clock.set(t_end - 300 + {"ok": 60, "stale": 20 * 60, "silent": 45 * 60}[node])
    core.tempest.poll(clock.now())
    valid_levels = {round(r[0], 3) for r in conn.execute("SELECT level_smooth_m FROM derived WHERE valid=1 AND "
                                                         "level_smooth_m IS NOT NULL")}
    preds = {round(r[0], 3) for r in conn.execute("SELECT predicted_m FROM derived WHERE predicted_m IS NOT NULL")}
    r = client.get("/api/v1/level/current")
    b = r.json()
    if node != "ok" or not has_cal:
        assert r.status_code == 503
        assert b["level_m"] is None and b["residual_m"] is None and b["level_raw_m"] is None
    else:
        assert r.status_code == 200
        assert b["level_m"] in valid_levels
    if b["level_m"] is not None:
        assert b["level_m"] not in (0, 0.0) or 0.0 in valid_levels
    if noaa_st == "uncovered":
        assert b["predicted_m"] is None and b["residual_m"] is None
    if b.get("last_good"):
        assert b["last_good"]["level_m"] in valid_levels
    # composite endpoints stay 200 with per-component status
    for path in ("/api/v1/status", "/api/v1/node/health", "/api/v1/residual", "/api/v1/predictions",
                 "/api/v1/node/energy", "/api/v1/weather/current", "/api/v1/alerts", "/api/v1/calibration",
                 "/api/v1/level/history"):
        rr = client.get(path)
        assert rr.status_code == 200, path
        assert "status" in rr.json()
    st = client.get("/api/v1/status").json()
    assert st["components"]["tempest"]["status"] == ("disabled" if tmp == "disabled" else
                                                    "error" if tmp == "error" else "ok")
    if gw == "ok" and node == "ok" and noaa_st == "ok" and has_cal:
        assert st["status"] == "ok"  # optional Tempest never degrades overall status
    w = client.get("/api/v1/weather/current").json()
    if tmp != "ok":
        assert w["pressure"] is None and w["wind"] is None
    _ = preds


def test_core_endpoint_identical_with_tempest_on_off(tmp_path, provider):
    bodies = []
    for enabled in (False, True):
        cfg = Config()
        cfg.tempest.enabled = enabled
        conn, core, clock, client = make(tmp_path / f"{enabled}.db", provider, cfg,
                                         lambda: (_ for _ in ()).throw(TempestError("timeout")))
        insert_cal(conn)
        core.deriver.invalidate()
        t_end, _ = feed(core, T0, T0 + 3600)
        clock.set(t_end)
        b = client.get("/api/v1/level/current").json()
        b.pop("weather_context")
        b["components"].pop("tempest")
        bodies.append(b)
    assert bodies[0] == bodies[1]


def test_repeater_silent_degrades_status(db_path, provider):
    conn, core, clock, client = make(db_path, provider)
    insert_cal(conn)
    core.deriver.invalidate()
    core.handle(LinkEvent(T0, "ok", "c"))
    core.handle(AdvertEvent(T0, "ab"))
    t_end, _ = feed(core, T0, T0 + 6 * 3600, path_len=0)  # gateway hears node directly only
    clock.set(t_end)
    st = client.get("/api/v1/status").json()
    assert st["components"]["repeater"]["status"] == "silent" and st["status"] == "degraded"
    nh = client.get("/api/v1/node/health").json()
    assert nh["repeater"]["status"] == "silent" and nh["status"] == "ok" and nh["gateway"]["status"] == "ok"


def test_read_only_and_unknown_paths(db_path, provider):
    conn, core, clock, client = make(db_path, provider)
    assert client.post("/api/v1/level/current").status_code == 405
    assert client.delete("/api/v1/alerts").status_code == 405
    assert client.get("/api/v1/nope").status_code == 404
    assert client.get("/docs").status_code == 404


def test_csv_export_marks_gaps(db_path, provider):
    conn, core, clock, client = make(db_path, provider)
    insert_cal(conn)
    core.deriver.invalidate()
    feed(core, T0, T0 + 3600)
    feed(core, T0 + 3 * 3600, T0 + 4 * 3600, seq0=36)
    clock.set(T0 + 86400)
    r = client.get("/api/v1/export/2026-12-03.csv")
    assert r.status_code == 200
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("t,time_source")
    gaps = [ln for ln in lines if ln.endswith(",0,missing_packet")]
    assert gaps
    assert all(",," in g for g in gaps)


def test_energy_and_samples_endpoints(db_path, provider):
    conn, core, clock, client = make(db_path, provider)
    feed(core, T0, T0 + 2 * 86400)
    clock.set(T0 + 2 * 86400)
    b = client.get("/api/v1/node/energy", params={"days": 5}).json()
    assert b["status"] == "insufficient_data" and b["verdict"]["energy_ratio"] is None
    assert b["daily"] and all("no_sun" in d for d in b["daily"])
    s = client.get("/api/v1/node/energy/samples", params={"from": "2026-12-03T05:00:00Z",
                                                          "to": "2026-12-03T06:00:00Z"}).json()
    assert len(s["samples"]) == 13  # inclusive range


def test_residual_endpoint_missing_markers(db_path, provider):
    conn, core, clock, client = make(db_path, provider)
    insert_cal(conn)
    core.deriver.invalidate()
    feed(core, T0, T0 + 3600)
    feed(core, T0 + 2 * 3600, T0 + 3 * 3600, seq0=24)
    clock.set(T0 + 3 * 3600 - 200)
    b = client.get("/api/v1/residual", params={"hours": 4}).json()
    assert b["status"] == "ok" and b["current"]["residual_m"] is not None
    assert any(s.get("reason") == "missing_packet" for s in b["series"])
    assert b["prediction_source"]["method"] == "hilo_half_cosine"


_ = parse_iso
