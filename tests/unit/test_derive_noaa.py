"""SV-C1..C3 (conversion, validity, smoothing), SV-N1..N3, N5..N7 (NOAA)."""

import json
import math

import httpx
import pytest
import respx

from conftest import FIXTURES, HINGE, L_TRUE, T0, THETA0, frame, payload, pitch_for_level, tide
from tidesvc import codec, noaa
from tidesvc.core import Core
from tidesvc.derive import Calibration, centred_median, find_extreme_near, invalid_reason, level_from_pitch, ls_slope, median
from tidesvc.notify import RecordingNotifier


def insert_cal(conn, *, h0=HINGE, l_eff=L_TRUE, theta0=THETA0, datum="MLLW", valid_from=T0 - 86400,
               pmin=None, pmax=None, status="active", method="manual"):
    cur = conn.execute(
        "INSERT INTO calibrations(created_at, valid_from, theta0_deg, h0_m, l_eff_m, k_t, pitch_min_deg, "
        "pitch_max_deg, method, status, datum, fit_stats_json) VALUES (?,?,?,?,?,0,?,?,?,?,?, '{}')",
        (valid_from, valid_from, theta0, h0, l_eff, pmin, pmax, method, status, datum))
    return cur.lastrowid


# ------------------------------------------------------------------ SV-C1
def test_conversion_hand_vectors():
    assert level_from_pitch(0.0, 0.0, 0.0, 7.62) == pytest.approx(0.0, abs=1e-6)
    assert level_from_pitch(3.0, 0.0, 0.0, 7.62) == pytest.approx(0.3988, abs=1e-4)
    assert level_from_pitch(6.5, 0.0, 0.0, 7.62) == pytest.approx(0.8626, abs=1e-4)
    assert level_from_pitch(3.0, 0.0, 0.0, 7.62) == pytest.approx(7.62 * math.sin(math.radians(3.0)), abs=1e-6)
    # k_T correction: pitch_corr = pitch - k_T*(temp-25)
    assert level_from_pitch(3.0, 0.0, 0.0, 7.62, k_t=0.01, temp_c=5.0) == pytest.approx(
        7.62 * math.sin(math.radians(3.2)), abs=1e-6)


# ------------------------------------------------------------------ SV-C2
def test_validity_rules():
    cal = Calibration(1, 0, 0.0, 0.0, 7.62, pitch_min_deg=-9.0, pitch_max_deg=1.0)
    assert invalid_reason(codec.F_SENSOR_ERROR, -3.0, 0.02, cal, 0.5, 0.25) == "sensor_error"
    assert invalid_reason(codec.F_OUT_OF_RANGE, -3.0, 0.02, cal, 0.5, 0.25) == "out_of_range"
    assert invalid_reason(0, -9.6, 0.02, cal, 0.5, 0.25) == "out_of_envelope"
    assert invalid_reason(0, -9.4, 0.02, cal, 0.5, 0.25) is None
    assert invalid_reason(0, 1.51, 0.02, cal, 0.5, 0.25) == "out_of_envelope"
    assert invalid_reason(0, -3.0, 0.251, cal, 0.5, 0.25) == "high_sd"
    assert invalid_reason(0, -3.0, 0.25, cal, 0.5, 0.25) is None
    assert invalid_reason(0, -3.0, 0.02, None, 0.5, 0.25) == "no_calibration"


# ------------------------------------------------------------------ SV-C3
def _feed(core, n, *, start=T0, step=300, level_fn=tide, flags_fn=lambda i: 0, sd_fn=lambda i: 0.02):
    out = []
    for i in range(n):
        t = start + i * step
        core.tick(t)
        out.append(core.handle(frame(t, payload(i, pitch_for_level(level_fn(t)), flags=flags_fn(i), sd=sd_fn(i)))))
    return out


def test_trailing_median_needs_four_points_and_lags(conn, cfg, provider):
    core = Core(conn, cfg, provider, RecordingNotifier())
    insert_cal(conn)
    core.deriver.invalidate()
    ramp = lambda t: 0.2 + 0.25 * (t - T0) / 3600.0  # noqa: E731  0.25 m/h ramp
    res = _feed(core, 20, level_fn=ramp)
    rows = conn.execute("SELECT * FROM derived ORDER BY t").fetchall()
    assert [r["smooth_reason"] for r in rows[:3]] == ["insufficient_points"] * 3
    assert rows[3]["level_smooth_m"] is not None
    # 6 points in a 30-min trailing window -> median at t-12.5 min
    r = rows[15]
    lag_h = (ramp(r["t"]) - r["level_smooth_m"]) / 0.25
    assert lag_h * 60 == pytest.approx(12.5, abs=0.2)
    assert all(x.status == "ok" for x in res)


def test_centred_median_has_no_lag():
    ts = [T0 + 300 * i for i in range(30)]
    vs = [0.25 * (t - T0) / 3600 for t in ts]
    out = dict(centred_median(ts, vs, 30, 4))
    assert out[ts[15]] == pytest.approx(vs[15], abs=1e-9)


def test_invalid_readings_excluded_but_kept(conn, cfg, provider):
    core = Core(conn, cfg, provider, RecordingNotifier())
    insert_cal(conn)
    core.deriver.invalidate()
    _feed(core, 12, sd_fn=lambda i: 0.4 if i == 8 else 0.02)
    r = conn.execute("SELECT d.* FROM derived d JOIN readings r ON r.id=d.reading_id WHERE r.seq=8").fetchone()
    assert r["valid"] == 0 and r["invalid_reason"] == "high_sd" and r["level_smooth_m"] is None
    assert conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0] == 12


# ------------------------------------------------------------------ SV-N1
def test_half_cosine_properties():
    e1, e2 = noaa.Extreme(0.0, 1.0, "H"), noaa.Extreme(6 * 3600.0, 0.0, "L")
    assert noaa.half_cosine(0.0, e1, e2) == pytest.approx(1.0)
    assert noaa.half_cosine(6 * 3600.0, e1, e2) == pytest.approx(0.0)
    assert noaa.half_cosine(3 * 3600.0, e1, e2) == pytest.approx(0.5)
    vals = [noaa.half_cosine(t, e1, e2) for t in range(0, 6 * 3600 + 1, 600)]
    assert all(a >= b for a, b in zip(vals, vals[1:]))
    e3 = noaa.Extreme(12 * 3600.0, 0.9, "H")
    vals = [noaa.half_cosine(t, e2, e3) for t in range(6 * 3600, 12 * 3600 + 1, 600)]
    assert all(a <= b for a, b in zip(vals, vals[1:]))
    p = noaa.HiloPredictor([e1, e2, e3])
    assert p.predict(-1) is None and p.predict(12 * 3600 + 1) is None  # never extrapolated


# ------------------------------------------------------------------ SV-N2 / fixture
def test_request_parameters():
    p = noaa.hilo_params("8531942", T0, T0 + 86400, "lora_ramp_tide_sensor")
    assert p == {"product": "predictions", "application": "lora_ramp_tide_sensor", "begin_date": "20261203 05:00",
                 "end_date": "20261204 05:00", "datum": "MLLW", "station": "8531942", "time_zone": "gmt",
                 "units": "metric", "interval": "hilo", "format": "json"}


def test_recorded_live_fixture_parses():
    data = json.loads((FIXTURES / "noaa_8531942_hilo_20261008_20261015.json").read_text())
    ext = noaa.parse_hilo_response(data)
    assert len(ext) > 20
    assert {e.type for e in ext} == {"H", "L"}
    assert all(a.t < b.t for a, b in zip(ext, ext[1:]))
    assert all(-0.5 < e.v < 2.0 for e in ext)


@respx.mock
def test_http_provider_success_and_failures():
    data = json.loads((FIXTURES / "noaa_8531942_hilo_20261008_20261015.json").read_text())
    url = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
    route = respx.get(url).mock(return_value=httpx.Response(200, json=data))
    prov = noaa.NoaaHttpProvider(url, "lora_ramp_tide_sensor")
    ext = prov.fetch_hilo("8531942", T0, T0 + 86400)
    assert len(ext) == len(data["predictions"])
    q = dict(route.calls.last.request.url.params)
    assert q["interval"] == "hilo" and q["datum"] == "MLLW" and q["units"] == "metric"
    route.mock(return_value=httpx.Response(200, json={"error": {"message": "No Predictions data was found."}}))
    with pytest.raises(noaa.NoaaError):
        prov.fetch_hilo("8531942", T0, T0 + 86400)
    route.mock(return_value=httpx.Response(200, json={"predictions": []}))
    with pytest.raises(noaa.NoaaError):
        prov.fetch_hilo("8531942", T0, T0 + 86400)
    route.mock(side_effect=httpx.ConnectTimeout("timeout"))
    with pytest.raises(noaa.NoaaError):
        prov.fetch_hilo("8531942", T0, T0 + 86400)
    route.mock(return_value=httpx.Response(500))
    with pytest.raises(noaa.NoaaError):
        prov.fetch_hilo("8531942", T0, T0 + 86400)


# ------------------------------------------------------------------ SV-N5 / N6 / N7
def test_noaa_down_cache_covers_then_runs_out(conn, cfg, provider):
    core = Core(conn, cfg, provider, RecordingNotifier())
    insert_cal(conn)
    core.tick(T0)
    covers_until = noaa.load_predictor(conn, "8531942").covers_until
    provider.fail = True
    n_before = conn.execute("SELECT COUNT(*) FROM noaa_predictions").fetchone()[0]
    core.noaa.refresh_predictions(T0 + 86400)
    assert conn.execute("SELECT COUNT(*) FROM noaa_predictions").fetchone()[0] == n_before  # cache untouched
    pred = noaa.load_predictor(conn, "8531942")
    assert pred.predict(T0 + 86400) is not None  # SV-N5: published prediction still valid
    assert pred.predict(covers_until + 3600) is None  # SV-N6: never extrapolated


# ------------------------------------------------------------------ SV-N3
def test_residual_and_rate_of_rise_on_synthetic_surge(conn, cfg, provider):
    core = Core(conn, cfg, provider, RecordingNotifier())
    insert_cal(conn)
    core.deriver.invalidate()
    surge = lambda t: 0.0 if t < T0 + 3 * 3600 else min(0.35, 0.35 * (t - T0 - 3 * 3600) / 3600.0)  # noqa: E731
    _feed(core, 80, level_fn=lambda t: tide(t) + surge(t))
    rows = conn.execute("SELECT * FROM derived WHERE residual_m IS NOT NULL ORDER BY t").fetchall()
    calm = [r["residual_m"] for r in rows if r["t"] < T0 + 3 * 3600]
    late = [r["residual_m"] for r in rows if r["t"] > T0 + 5 * 3600]
    assert max(abs(x) for x in calm) < 0.01  # positive = above predicted; lag-free comparison
    assert min(late) == pytest.approx(0.35, abs=0.01)
    ex = [r["excess_rise_mph"] for r in rows if T0 + 3.75 * 3600 < r["t"] < T0 + 4.0 * 3600]
    assert ex and max(ex) > 0.2


def test_ls_slope_and_extreme_finder():
    ts = [i * 300.0 for i in range(120)]
    assert ls_slope(ts, [0.1 * t / 3600 for t in ts]) == pytest.approx(0.1)
    tpk = 5.0 * 3600 + 137
    vs = [1.0 - 0.1 * ((t - tpk) / 3600) ** 2 for t in ts]
    ob = find_extreme_near(ts, vs, 5 * 3600, "H")
    assert ob is not None and ob.t == pytest.approx(tpk, abs=1) and ob.v == pytest.approx(1.0, abs=1e-6)
    assert median([1, 2, 3, 4]) == 2.5
