"""FW-U4, FW-U6, FW-U7, FW-U9, FW-U10 for the Python firmware mirror (sim.fwlogic),
using the same vectors the C++ host tests use."""

import json
import math

import pytest

from conftest import VECTORS
from sim import fwlogic as fw
from tidesvc.derive import median as server_median

L = json.loads((VECTORS / "fw_logic_v1.json").read_text())
S = json.loads((VECTORS / "stats_v1.json").read_text())


@pytest.mark.parametrize("case", S["cases"], ids=lambda c: c["name"])
def test_stats_vectors_firmware_and_server_agree(case):
    xs = case["samples"]
    st = fw.burst_stats(xs, [0.0] * len(xs))
    assert st.pitch_median == pytest.approx(case["median"], abs=1e-12)
    assert st.pitch_sd == pytest.approx(case["sd_pop"], abs=1e-9)
    assert server_median(xs) == pytest.approx(case["median"], abs=1e-12)  # one rule, both sides


def test_outlier_does_not_move_median():
    c = next(c for c in S["cases"] if c["name"] == "outlier_300")
    assert c["median"] == 1.0


def test_battery_sequence():
    st = L["battery"]["start_state"]
    for step in L["battery"]["steps"]:
        st = fw.next_batt_state(st, step["vbat_mv"])
        assert st == step["state"], step
        assert fw.INTERVAL_S[st] == step["interval_s"]
        assert fw.batt_flags(st) == step["flags"]


def test_battery_hysteresis_both_directions():
    assert fw.next_batt_state(fw.NORMAL, 3150) == fw.NORMAL
    assert fw.next_batt_state(fw.NORMAL, 3149) == fw.LOW
    assert fw.next_batt_state(fw.LOW, 3199) == fw.LOW
    assert fw.next_batt_state(fw.LOW, 3200) == fw.NORMAL
    assert fw.next_batt_state(fw.LOW, 3049) == fw.CRITICAL
    assert fw.next_batt_state(fw.CRITICAL, 3099) == fw.CRITICAL
    assert fw.next_batt_state(fw.CRITICAL, 3100) == fw.LOW


@pytest.mark.parametrize("name", list(L["charger"]["sequences"]))
def test_charger_sequences(name):
    start = L["charger"]["starts"][name]
    s = fw.ChargerState(ce_disabled=start["ce_disabled"], charging_elapsed_s=start["charging_elapsed_s"])
    for step in L["charger"]["sequences"][name]:
        r = fw.charger_step(s, step["temp_c"], step["stat1"], step["stat2"], step["dt_s"])
        assert (r.ce_disabled, r.pulse, r.chg, r.state.charging_elapsed_s) == (
            step["ce_disabled"], step["pulse"], step["chg"], step["charging_elapsed_s"]), step
        s = r.state


def test_cold_rule_boundaries():
    en = fw.ChargerState(ce_disabled=False)
    dis = fw.ChargerState(ce_disabled=True)
    assert fw.charger_step(en, 0.9, 1, 1, 300).ce_disabled is True
    assert fw.charger_step(en, 1.0, 1, 1, 300).ce_disabled is False  # hold
    assert fw.charger_step(dis, 1.0, 1, 1, 300).ce_disabled is True  # hold
    assert fw.charger_step(dis, 2.0, 1, 1, 300).ce_disabled is True  # hold
    assert fw.charger_step(dis, 2.1, 1, 1, 300).ce_disabled is False
    assert fw.charger_step(en, None, 1, 0, 300).ce_disabled is True  # fail-safe on unknown temp
    r = fw.charger_step(en, -40.0, 1, 1, 300)
    assert r.chg & fw.CHG_COLD and r.chg & fw.CHG_CE_OVR


def test_safety_pulse_at_four_hours_never_during_cold():
    s = fw.ChargerState(ce_disabled=False)
    pulses = []
    for i in range(60):
        r = fw.charger_step(s, 20.0, 1, 0, 300)
        pulses.append(r.pulse)
        s = r.state
    assert pulses.index(True) == 47  # 48 x 300 s = 4 h
    assert sum(pulses) == 1
    s = fw.ChargerState(ce_disabled=False)
    for _ in range(100):
        r = fw.charger_step(s, 0.0, 1, 0, 300)
        assert not r.pulse
        s = r.state


@pytest.mark.parametrize("case", L["sample_flags"], ids=lambda c: c["name"])
def test_sample_flags(case):
    st = fw.BurstStats(case["n_valid"], case["pitch_median"], case["pitch_sd"], case["roll_mean"])
    assert fw.sample_flags(st, case["n_valid"]) == case["flags"]


def test_sd_is_population():
    st = fw.burst_stats([1.0, 3.0], [0.0, 0.0])
    assert st.pitch_sd == pytest.approx(1.0) and not math.isclose(st.pitch_sd, math.sqrt(2))
