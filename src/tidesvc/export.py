"""Daily CSV export (raw + derived, including power telemetry; E5.7) and
nightly SQLite backup. Gaps are empty cells with a reason, never filled."""

from __future__ import annotations

import csv
import datetime as _dt
import io
import sqlite3
from pathlib import Path

from .timeutil import iso, local_day_bounds

COLUMNS = ["t", "time_source", "node_id", "boot_count", "seq", "pitch_deg", "pitch_sd_deg", "roll_deg", "temp_c",
           "vbat_mv", "vpanel_mv", "ipanel_ma", "chg_bits", "awake_ms_prev", "flags", "path_len", "snr_db",
           "calibration_id", "level_raw_m", "level_smooth_m", "predicted_m", "residual_m", "excess_rise_mph",
           "valid", "reason"]


def daily_csv(conn: sqlite3.Connection, day: _dt.date, interval_s: int = 300) -> str:
    start, end = local_day_bounds(day)
    rows = conn.execute(
        "SELECT r.*, d.calibration_id, d.level_raw_m, d.level_smooth_m, d.predicted_m, d.residual_m, "
        "d.excess_rise_mph, d.valid, d.invalid_reason FROM readings r LEFT JOIN derived d ON d.reading_id=r.id "
        "WHERE r.t >= ? AND r.t < ? ORDER BY r.t", (start, end)).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(COLUMNS)
    prev_t = start
    for r in rows:
        # mark gaps explicitly (one row per gap, no values)
        if r["t"] - prev_t > 1.5 * interval_s:
            w.writerow([iso(prev_t + interval_s)] + [""] * (len(COLUMNS) - 3) + ["0", "missing_packet"])
        prev_t = r["t"]
        valid = r["valid"] == 1
        w.writerow([
            iso(r["t"]), r["time_source"], r["node_id"], r["boot_count"], r["seq"], r["pitch_deg"],
            r["pitch_sd_deg"], r["roll_deg"], r["temp_c"], r["vbat_mv"], r["vpanel_mv"], r["ipanel_ma"],
            r["chg_bits"], r["awake_ms_prev"], r["flags"], r["path_len"], r["snr_db"], r["calibration_id"],
            _f(r["level_raw_m"]) if valid else "", _f(r["level_smooth_m"]) if valid else "",
            _f(r["predicted_m"]), _f(r["residual_m"]) if valid else "", _f(r["excess_rise_mph"]) if valid else "",
            int(valid), r["invalid_reason"] or "",
        ])
    if end - prev_t > 1.5 * interval_s and rows:
        w.writerow([iso(prev_t + interval_s)] + [""] * (len(COLUMNS) - 3) + ["0", "missing_packet"])
    return buf.getvalue()


def _f(v):
    return "" if v is None else f"{v:.4f}"


def write_daily_csv(conn: sqlite3.Connection, day: _dt.date, export_dir: str) -> Path:
    p = Path(export_dir)
    p.mkdir(parents=True, exist_ok=True)
    out = p / f"{day.isoformat()}.csv"
    out.write_text(daily_csv(conn, day))
    return out


def backup(conn: sqlite3.Connection, backup_dir: str, stamp: str, keep: int = 14) -> Path:
    p = Path(backup_dir)
    p.mkdir(parents=True, exist_ok=True)
    out = p / f"tide-{stamp}.db"
    dst = sqlite3.connect(str(out))
    with dst:
        conn.backup(dst)
    dst.close()
    olds = sorted(p.glob("tide-*.db"))
    for old in olds[:-keep]:
        old.unlink()
    return out
