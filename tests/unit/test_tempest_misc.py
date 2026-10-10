"""Tempest parser and statuses (E9.1/E9.2), config/secrets, and package isolation."""

import ast
import pathlib

import pytest

from conftest import ROOT, T0
from tidesvc import tempest
from tidesvc.config import Config, load_config
from tidesvc.tempest import FakeTempestSource, TempestError, TempestPoller


def test_parser_missing_fields_null_with_reason():
    ts, vals, reasons = tempest.parse_obs({"obs": [{"timestamp": 1000, "sea_level_pressure": 1005.2,
                                                     "wind_avg": "x"}]})
    assert ts == 1000 and vals["slp_hpa"] == 1005.2
    assert vals["wind_avg"] is None and reasons["wind_avg"] == "not_numeric"
    assert vals["air_c"] is None and reasons["air_c"] == "missing"
    for bad in ({}, {"obs": []}, {"obs": [{"wind_avg": 3}]}, []):
        with pytest.raises(TempestError):
            tempest.parse_obs(bad)


def test_disabled_error_stale_ok(conn):
    cfg = Config()
    p = TempestPoller(conn, cfg, None)
    assert p.poll(T0) == "disabled"
    assert tempest.tempest_status(conn, cfg, T0)["status"] == "disabled"
    cfg.tempest.enabled = True
    now = {"t": T0}
    p = TempestPoller(conn, cfg, FakeTempestSource(lambda: {"obs": [{"timestamp": now["t"], "sea_level_pressure": 1000,
                                                                       "wind_avg": 9, "wind_direction": 60}]}))
    for k in range(0, 7 * 3600, 300):
        now["t"] = T0 + k
        assert p.poll(T0 + k) == "ok"
    ctx = tempest.context(conn, cfg, T0 + 7 * 3600 - 300)
    assert ctx["status"] == "ok" and ctx["onshore_wind_sustained"] is True
    assert ctx["pressure_change_3h_hpa"] == 0 and ctx["inverse_barometer_m"] == pytest.approx(0.133)
    assert tempest.tempest_status(conn, cfg, T0 + 8 * 3600)["status"] == "stale"
    p2 = TempestPoller(conn, cfg, FakeTempestSource(lambda: (_ for _ in ()).throw(TempestError("HTTP 401"))))
    assert p2.poll(T0 + 8 * 3600) == "error"
    st = tempest.tempest_status(conn, cfg, T0 + 8 * 3600)
    assert st["status"] == "error" and "401" in st["error"]["message"]
    assert tempest.context(conn, cfg, T0 + 8 * 3600)["pressure_change_3h_hpa"] is None


def test_secrets_only_from_env(tmp_path):
    t = tmp_path / "c.toml"
    t.write_text("[secrets]\nsmtp_password='x'\n")
    with pytest.raises(ValueError):
        load_config(t, env={})
    env = tmp_path / ".env"
    env.write_text("SMTP_HOST=mail.example\nALERT_EMAIL_TO=me@example.com\n")
    c = load_config(None, env={}, dotenv=env)
    assert c.secrets.smtp_host == "mail.example"
    assert "mail.example" not in repr(c)
    with pytest.raises(ValueError):
        t.write_text("[node]\nbogus=1\n")
        load_config(t, env={})


def test_example_config_loads():
    c = load_config(ROOT / "src" / "tidesvc" / "config.example.toml", env={})
    assert c.api.port == 8120 and c.tempest.enabled is False and c.radio.data_type == 0xFF54


def test_tidesvc_never_imports_simulator():
    for path in (ROOT / "src" / "tidesvc").rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not any(a.name.split(".")[0] == "sim" for a in node.names), path
            if isinstance(node, ast.ImportFrom) and node.level == 0:
                assert (node.module or "").split(".")[0] != "sim", path


_ = pathlib
