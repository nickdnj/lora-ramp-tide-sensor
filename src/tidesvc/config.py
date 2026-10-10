"""Configuration: non-secret settings from config.toml, secrets from the
environment / .env (ARCHITECTURE 8). Defaults follow ARCHITECTURE 8 and 6.8.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path


@dataclass
class RadioCfg:
    transport: str = "serial"  # serial | tcp
    port: str = "/dev/meshcore-gw"
    host: str = ""
    tcp_port: int = 5000
    channel_idx: int = 1
    data_type: int = 0xFF54
    heartbeat_s: int = 60
    backlog_window_s: float = 30.0  # frames closer than this (new seq) => backlog drain


@dataclass
class RepeaterCfg:
    name: str = ""
    pubkey_prefix: str = ""
    silent_after_s: int = 14400
    status_poll_s: int = 0


@dataclass
class NodeCfg:
    node_id: int = 1
    interval_s: int = 300
    stale_after_s: int = 900
    silent_alert_after_s: int = 1800
    dedup_window_s: int = 86400


@dataclass
class CalibrationCfg:
    window_min: int = 30
    envelope_margin_deg: float = 0.5
    max_pitch_sd_deg: float = 0.25
    min_points: int = 4
    refit_h0_m: float = 0.05
    refit_l_eff_rel: float = 0.03
    match_window_min: float = 90.0
    calm_residual_m: float = 0.10
    min_install_span_m: float = 0.5
    # Spec gap SV-C7 (DEV-PLAN 7 item 6): proposed minimums for a fit.
    min_matched_extremes_refit: int = 12
    min_matched_extremes_datum: int = 4
    refit_days: int = 30


@dataclass
class NoaaCfg:
    prediction_station: str = "8531942"
    ocean_reference: str = "8531991"
    observed_reference: str = "8531680"
    base_url: str = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
    application: str = "lora_ramp_tide_sensor"
    timeout_s: float = 20.0
    past_days: int = 3
    future_days: int = 7


@dataclass
class EnergyCfg:
    capacity_mah: float = 3000.0
    i_sleep_ua: float = 50.0
    awake_mas_per_cycle: float = 125.0
    nominal_awake_ms: float = 3900.0
    negative_streak_days: int = 7
    min_coverage_pct: float = 80.0
    max_gap_s: int = 900
    verdict_window_days: int = 14
    min_verdict_days: int = 7
    # panel considered present when vpanel exceeds vbat by this much (mV)
    panel_present_margin_mv: int = 300
    # charging but not panel-limited when vpanel exceeds vbat by this much (VINDPM is vbat + ~330 mV)
    vindpm_margin_mv: int = 1000
    # node current while the INA3221 is read (ARCHITECTURE 4.4 power-read phase); bench value replaces it
    i_read_ma: float = 25.0

    @property
    def i_awake_ma(self) -> float:
        return self.awake_mas_per_cycle / (self.nominal_awake_ms / 1000.0)


@dataclass
class AlertsCfg:
    surge_warning_m: float = 0.30
    surge_warning_clear_m: float = 0.20
    surge_severe_m: float = 0.60
    surge_severe_clear_m: float = 0.50
    excess_rise_m_per_h: float = 0.15
    excess_rise_clear_m_per_h: float = 0.08
    clear_hold_s: int = 1800
    surge_watch_m: float = 0.15
    surge_watch_clear_m: float = 0.10
    gateway_down_after_s: int = 300
    low_batt_mv: int = 3150
    low_batt_clear_mv: int = 3250
    sensor_quality_sd_deg: float = 0.2
    prediction_lookahead_s: int = 86400
    eval_interval_s: int = 60


@dataclass
class TempestCfg:
    enabled: bool = False
    station_id: int = 183092
    poll_s: int = 300
    stale_after_s: int = 900
    onshore_sector_deg: tuple[float, float] = (20.0, 140.0)
    onshore_min_mps: float = 8.0
    pressure_drop_3h_hpa: float = 3.0
    base_url: str = "https://swd.weatherflow.com/swd/rest"


@dataclass
class ApiCfg:
    host: str = "0.0.0.0"
    port: int = 8120


@dataclass
class StorageCfg:
    db_path: str = "/data/tide.db"
    export_dir: str = "/data/exports"
    backup_dir: str = "/data/backups"
    backup_keep: int = 14


@dataclass
class Secrets:
    channel_secret_hex: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    alert_email_to: str = ""
    tempest_token: str = ""

    def __repr__(self) -> str:  # never print secrets
        return "Secrets(<redacted>)"


@dataclass
class Config:
    radio: RadioCfg = field(default_factory=RadioCfg)
    repeater: RepeaterCfg = field(default_factory=RepeaterCfg)
    node: NodeCfg = field(default_factory=NodeCfg)
    calibration: CalibrationCfg = field(default_factory=CalibrationCfg)
    noaa: NoaaCfg = field(default_factory=NoaaCfg)
    energy: EnergyCfg = field(default_factory=EnergyCfg)
    alerts: AlertsCfg = field(default_factory=AlertsCfg)
    tempest: TempestCfg = field(default_factory=TempestCfg)
    api: ApiCfg = field(default_factory=ApiCfg)
    storage: StorageCfg = field(default_factory=StorageCfg)
    secrets: Secrets = field(default_factory=Secrets)


def _apply(obj, data: dict, path: str = "") -> None:
    known = {f.name: f for f in fields(obj)}
    for key, value in data.items():
        if key not in known:
            raise ValueError(f"unknown config key {path}{key}")
        cur = getattr(obj, key)
        if is_dataclass(cur):
            if not isinstance(value, dict):
                raise ValueError(f"config section {path}{key} must be a table")
            _apply(cur, value, f"{path}{key}.")
        else:
            if isinstance(cur, tuple):
                value = tuple(value)
            setattr(obj, key, value)


def _read_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def load_config(path: str | os.PathLike | None = None, env: dict[str, str] | None = None,
                dotenv: str | os.PathLike | None = None) -> Config:
    cfg = Config()
    if path is not None:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
        if "secrets" in data:
            raise ValueError("secrets must come from the environment/.env, not config.toml")
        _apply(cfg, data)
    e = dict(_read_dotenv(Path(dotenv))) if dotenv else {}
    e.update(env if env is not None else os.environ)
    s = cfg.secrets
    s.channel_secret_hex = e.get("TIDE_CHANNEL_SECRET", "")
    s.smtp_host = e.get("SMTP_HOST", "")
    s.smtp_port = int(e.get("SMTP_PORT", "587") or 587)
    s.smtp_user = e.get("SMTP_USER", "")
    s.smtp_password = e.get("SMTP_PASSWORD", "")
    s.smtp_from = e.get("SMTP_FROM", "")
    s.alert_email_to = e.get("ALERT_EMAIL_TO", "")
    s.tempest_token = e.get("TEMPEST_TOKEN", "")
    return cfg
