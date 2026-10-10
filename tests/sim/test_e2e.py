"""End-to-end: the simulated world feeding the real tidesvc pipeline.

`quick` (8 days) always runs; the full 30-day December scenario and the shaded
deficit scenario are marked slow (about 30 s together) but still run offline by
default. Every required acceptance check must pass; stretch goals are reported.
"""

import sqlite3

import pytest

from sim import fwlogic as fw
from sim.acceptance import checks
from sim.engine import run
from sim.metrics import all_metrics
from sim.scenario import deficit, default, quick
from tidesvc import codec


@pytest.fixture(scope="module")
def quick_run(tmp_path_factory):
    r = run(quick(), workdir=str(tmp_path_factory.mktemp("quick")))
    return r, all_metrics(r)


def _required_failures(m, sc):
    return [c for c in checks(m, sc) if not c.passed and not c.stretch]


def test_quick_all_required_checks_pass(quick_run):
    r, m = quick_run
    assert _required_failures(m, r.scenario) == []


def test_quick_no_invented_level_in_any_probe(quick_run):
    r, m = quick_run
    conn = sqlite3.connect(r.db_path)
    served = {round(x[0], 3) for x in conn.execute("SELECT level_smooth_m FROM derived WHERE valid=1 AND live=1 "
                                                   "AND level_smooth_m IS NOT NULL")}
    preds = {round(x[0], 3) for x in conn.execute("SELECT predicted_m FROM derived WHERE predicted_m IS NOT NULL")}
    assert r.probes
    tie = r.events["install"]["datum_tie_t"]  # earlier probes were served before the datum-tie reprocess
    for p in r.probes:
        if p.code == 200:
            assert p.level_m is not None and p.status == "ok"
            if p.t > tie + 60:
                assert p.level_m in served
        else:
            assert p.code == 503 and p.level_m is None and p.residual_m is None
    # a served level never equals the prediction at the same time by construction of the world noise
    assert sum(1 for p in r.probes if p.code == 200 and p.level_m == p.predicted_m) <= 1
    _ = preds


def test_quick_reboot_and_flags(quick_run):
    r, m = quick_run
    conn = sqlite3.connect(r.db_path)
    rows = conn.execute("SELECT boot_count, seq, flags FROM readings ORDER BY t").fetchall()
    boots = sorted({b for b, _, _ in rows})
    assert len(boots) == 2 and boots[1] == boots[0] + 1
    first_after = next(x for x in rows if x[0] == boots[1])
    assert first_after[1] == 0 and first_after[2] & codec.F_REBOOT and first_after[2] & codec.F_WDT_RESET
    # the power-up frame of the first boot also carries the reboot flag
    assert rows[0][2] & codec.F_REBOOT
    # no phantom backfill around the reboot
    assert conn.execute("SELECT COUNT(*) FROM readings WHERE boot_count=? AND time_source='backfilled'",
                        (boots[1],)).fetchone()[0] == 0


def test_quick_wake_burst_flags_high_sd(quick_run):
    r, m = quick_run
    conn = sqlite3.connect(r.db_path)
    tb = r.events["wake_burst"]
    n = conn.execute("SELECT COUNT(*) FROM readings WHERE t BETWEEN ? AND ? AND (flags & ?) != 0",
                     (tb, tb + 2400, codec.F_HIGH_SD)).fetchone()[0]
    assert n >= 2
    bad = conn.execute("SELECT COUNT(*) FROM derived WHERE t BETWEEN ? AND ? AND invalid_reason='high_sd'",
                       (tb, tb + 2400)).fetchone()[0]
    assert bad == n  # excluded from level and alerts, kept raw
    assert not any(a["kind"] == "SENSOR_QUALITY" for a in m["alerts"])  # a short burst is not a sensor fault


def test_quick_firmware_mirror_used_by_node(quick_run):
    r, _ = quick_run
    assert r.node.batt_state == fw.NORMAL
    assert r.radio.stats.tx > 2000


@pytest.mark.slow
def test_default_30_day_december(tmp_path):
    r = run(default(), workdir=str(tmp_path))
    m = all_metrics(r)
    assert _required_failures(m, r.scenario) == []
    assert m["accuracy"]["live_trailing_vs_truth_now"]["rms_cm"] <= 5.0
    assert m["hilo"]["dt_min_max_abs"] <= 10
    assert m["energy"]["verdict"]["assessment"] == "surplus"
    assert m["calibration"]["refit_runs"] and m["calibration"]["refit_runs"][-1]["applied"]
    kinds = [a["kind"] for a in m["alerts"]]
    for k in ("SURGE_WARNING", "SURGE_SEVERE", "NODE_SILENT", "REPEATER_SILENT", "GATEWAY_DOWN"):
        assert k in kinds
    for k in ("ENERGY_DEFICIT", "LOW_BATTERY", "SENSOR_QUALITY", "OUT_OF_RANGE", "CALIBRATION_DRIFT",
              "PREDICTION_UNAVAILABLE"):
        assert k not in kinds  # no spurious alerts (the NOAA outage is covered by the cache)


@pytest.mark.slow
def test_shaded_deficit(tmp_path):
    r = run(deficit(), workdir=str(tmp_path))
    m = all_metrics(r)
    assert _required_failures(m, r.scenario) == []
    assert m["energy"]["verdict"]["assessment"] == "deficit"
    assert "ENERGY_DEFICIT" in [a["kind"] for a in m["alerts"]]
