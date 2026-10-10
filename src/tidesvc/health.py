"""Component health shared by the API and the alert engine (ARCHITECTURE 5.2, 5.5, 7.3)."""

from __future__ import annotations

import sqlite3

from . import db as dbmod


def last_valid_live(conn: sqlite3.Connection, now: float) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM derived WHERE valid=1 AND live=1 AND t <= ? ORDER BY t DESC LIMIT 1", (now,)).fetchone()


def last_reading(conn: sqlite3.Connection, now: float) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM readings WHERE t <= ? ORDER BY t DESC LIMIT 1", (now,)).fetchone()


def node_status(conn: sqlite3.Connection, cfg, now: float) -> dict:
    row = last_valid_live(conn, now)
    if row is None:
        return {"status": "error", "age_s": None, "last_valid_at": None,
                "error": {"code": "NO_DATA", "message": "No valid reading received yet."}}
    age = now - row["t"]
    if age > cfg.node.silent_alert_after_s:
        st = "silent"
    elif age > cfg.node.stale_after_s:
        st = "stale"
    else:
        st = "ok"
    return {"status": st, "age_s": round(age), "last_valid_at": row["t"]}


def gateway_status(conn: sqlite3.Connection, now: float) -> dict:
    g = dbmod.get_component(conn, "gateway")
    if g is None:
        return {"status": "unknown", "since": None, "detail": {}}
    return {"status": g["status"], "since": g["since"], "detail": g["detail"]}


def repeater_status(conn: sqlite3.Connection, cfg, now: float) -> dict:
    ev = dbmod.get_component(conn, "repeater_evidence")
    d = ev["detail"] if ev else {}
    times = [d.get(k) for k in ("last_relayed_frame_at", "last_advert_at", "last_status_at") if d.get(k)]
    times = [t for t in times if t <= now]
    if not times:
        st = "unknown"
    elif now - max(times) <= cfg.repeater.silent_after_s:
        st = "ok"
    else:
        st = "silent"
    return {"status": st, "last_relayed_frame_at": d.get("last_relayed_frame_at"),
            "last_advert_at": d.get("last_advert_at"), "last_status_at": d.get("last_status_at"),
            "batt_mv": d.get("batt_mv"), "last_evidence_at": max(times) if times else None}
