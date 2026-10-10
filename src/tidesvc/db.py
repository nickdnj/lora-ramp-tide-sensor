"""SQLite storage (WAL). One writer connection; the API opens read-only ones.

Schema follows ARCHITECTURE 6.9. Differences, all additive:
- timestamps are stored as UTC epoch seconds (REAL); the API renders ISO-8601 Z;
- readings also keep rx_at, path_len and snr_db; derived keeps t and the reasons;
- calibrations add pitch envelope, datum ('bulkhead_mark' until tied, then 'MLLW');
- component_state holds the latest gateway/noaa/tempest status for the API.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS packets_raw (
    id INTEGER PRIMARY KEY,
    rx_at REAL NOT NULL,
    time_source TEXT NOT NULL DEFAULT 'rx',
    channel_idx INTEGER,
    data_type INTEGER,
    snr_db REAL,
    path_len INTEGER,
    payload BLOB,
    parse_status TEXT NOT NULL,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS ix_packets_rx ON packets_raw(rx_at);

CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY,
    packet_id INTEGER REFERENCES packets_raw(id),
    node_id INTEGER NOT NULL,
    boot_count INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    t REAL NOT NULL,
    rx_at REAL NOT NULL,
    time_source TEXT NOT NULL,
    pitch_deg REAL,
    pitch_sd_deg REAL,
    roll_deg REAL,
    temp_c REAL,
    vbat_mv INTEGER,
    vpanel_mv INTEGER,
    ipanel_ma REAL,
    chg_bits INTEGER,
    awake_ms_prev INTEGER,
    flags INTEGER,
    path_len INTEGER,
    snr_db REAL
);
CREATE INDEX IF NOT EXISTS ix_readings_t ON readings(t);
CREATE INDEX IF NOT EXISTS ix_readings_key ON readings(node_id, boot_count, seq);

CREATE TABLE IF NOT EXISTS calibrations (
    id INTEGER PRIMARY KEY,
    created_at REAL NOT NULL,
    valid_from REAL NOT NULL,
    theta0_deg REAL NOT NULL,
    h0_m REAL NOT NULL,
    l_eff_m REAL NOT NULL,
    k_t REAL NOT NULL DEFAULT 0,
    pitch_min_deg REAL,
    pitch_max_deg REAL,
    method TEXT NOT NULL,
    status TEXT NOT NULL,
    datum TEXT NOT NULL,
    fit_stats_json TEXT
);

CREATE TABLE IF NOT EXISTS derived (
    reading_id INTEGER PRIMARY KEY REFERENCES readings(id),
    t REAL NOT NULL,
    live INTEGER NOT NULL,
    calibration_id INTEGER REFERENCES calibrations(id),
    level_raw_m REAL,
    level_smooth_m REAL,
    predicted_m REAL,
    predicted_smooth_m REAL,
    residual_m REAL,
    excess_rise_mph REAL,
    valid INTEGER NOT NULL,
    invalid_reason TEXT,
    smooth_reason TEXT,
    residual_reason TEXT
);
CREATE INDEX IF NOT EXISTS ix_derived_t ON derived(t);

CREATE TABLE IF NOT EXISTS cal_observations (
    id INTEGER PRIMARY KEY,
    t REAL NOT NULL,
    kind TEXT NOT NULL,             -- 'tape' | 'level_check'
    freeboard_m REAL,
    angle_deg REAL,                 -- reference digital-level angle for kind=level_check
    pitch_deg REAL,                 -- node pitch (median of packets around t)
    note TEXT
);

CREATE TABLE IF NOT EXISTS noaa_predictions (
    station TEXT NOT NULL, t REAL NOT NULL, v REAL NOT NULL, type TEXT NOT NULL,
    fetched_at REAL NOT NULL, PRIMARY KEY (station, t)
);
CREATE TABLE IF NOT EXISTS noaa_observations (
    station TEXT NOT NULL, t REAL NOT NULL, v REAL, pred_v REAL, PRIMARY KEY (station, t)
);

CREATE TABLE IF NOT EXISTS tempest_obs (
    obs_at REAL PRIMARY KEY, fetched_at REAL, slp_hpa REAL, station_hpa REAL, wind_avg REAL,
    wind_gust REAL, wind_dir REAL, rain_1h_mm REAL, rain_day_mm REAL, air_c REAL, raw_json TEXT
);

CREATE TABLE IF NOT EXISTS energy_daily (
    date TEXT PRIMARY KEY, harvest_mah REAL, harvest_mwh REAL, consumption_est_mah REAL,
    net_mah REAL, coverage_pct REAL, reached_full INTEGER, charge_inhibit_cold_h REAL,
    charging_h REAL, vbat_rest_v REAL, vbat_min_v REAL, vbat_max_v REAL, vbat_end_v REAL,
    panel_peak_ma REAL, temp_min_c REAL, i_sleep_ua REAL, i_awake_ma REAL, n_readings INTEGER,
    computed_at REAL
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, severity TEXT NOT NULL, opened_at REAL NOT NULL,
    cleared_at REAL, clear_condition TEXT NOT NULL, value REAL, threshold REAL,
    context_json TEXT, notified_at REAL, notify INTEGER NOT NULL DEFAULT 1,
    notify_attempts INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_alerts_open ON alerts(kind, cleared_at);

CREATE TABLE IF NOT EXISTS gateway_events (t REAL NOT NULL, event TEXT NOT NULL, detail TEXT);
CREATE TABLE IF NOT EXISTS repeater_events (
    t REAL NOT NULL, source TEXT NOT NULL, detail TEXT, snr_db REAL, batt_mv INTEGER
);
CREATE TABLE IF NOT EXISTS component_state (
    name TEXT PRIMARY KEY, status TEXT NOT NULL, since REAL, updated_at REAL, detail_json TEXT
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    """Writer connection. Creates the schema if needed."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    if row is None:
        conn.execute("INSERT INTO meta(key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
    return conn


def connect_ro(path: str | Path) -> sqlite3.Connection:
    """Read-only connection for the API (WAL allows concurrent readers)."""
    uri = f"file:{Path(path).resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def set_component(conn: sqlite3.Connection, name: str, status: str, now: float,
                  detail: dict | None = None) -> None:
    row = conn.execute("SELECT status, since FROM component_state WHERE name=?", (name,)).fetchone()
    since = row["since"] if row is not None and row["status"] == status else now
    conn.execute(
        "INSERT INTO component_state(name, status, since, updated_at, detail_json) VALUES (?,?,?,?,?) "
        "ON CONFLICT(name) DO UPDATE SET status=excluded.status, since=excluded.since, "
        "updated_at=excluded.updated_at, detail_json=excluded.detail_json",
        (name, status, since, now, json.dumps(detail or {})),
    )


def get_component(conn: sqlite3.Connection, name: str) -> dict | None:
    row = conn.execute("SELECT * FROM component_state WHERE name=?", (name,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["detail"] = json.loads(d.pop("detail_json") or "{}")
    return d
