"""Optional WeatherFlow Tempest input (ARCHITECTURE 6.7, ADR-011; E9.x).

Disabled by default. REST poll only (no UDP listener; port 50222 belongs to
the TempestWeather sidecar). Defensive parsing: a missing field becomes null
with a field-level reason, never a default. Tempest status never degrades the
core status.
"""

from __future__ import annotations

import json
import math
import sqlite3
from typing import Callable, Protocol

from . import db as dbmod

FIELDS = {
    # our name: REST obs key
    "slp_hpa": "sea_level_pressure",
    "station_hpa": "station_pressure",
    "wind_avg": "wind_avg",
    "wind_gust": "wind_gust",
    "wind_dir": "wind_direction",
    "rain_1h_mm": "precip_accum_last_1hr",
    "rain_day_mm": "precip_accum_local_day",
    "air_c": "air_temperature",
}


class TempestError(RuntimeError):
    pass


class TempestSource(Protocol):
    def fetch_latest(self) -> dict: ...


class TempestHttpSource:
    def __init__(self, station_id: int, token: str, base_url: str, timeout_s: float = 15.0) -> None:
        self.url = f"{base_url}/observations/station/{station_id}"
        self.token = token
        self.timeout_s = timeout_s

    def fetch_latest(self) -> dict:
        import httpx

        if not self.token:
            raise TempestError("TEMPEST_TOKEN not set")
        try:
            r = httpx.get(self.url, params={"token": self.token}, timeout=self.timeout_s)
        except httpx.HTTPError as e:
            raise TempestError(f"fetch failed: {e.__class__.__name__}") from e
        if r.status_code != 200:
            raise TempestError(f"HTTP {r.status_code} from swd.weatherflow.com")
        try:
            return r.json()
        except ValueError as e:
            raise TempestError("response is not JSON") from e


class FakeTempestSource:
    """Test/simulator source: returns payloads from a callable or raises."""

    def __init__(self, fn: Callable[[], dict]) -> None:
        self.fn = fn

    def fetch_latest(self) -> dict:
        return self.fn()


def parse_obs(payload: dict) -> tuple[float, dict, dict]:
    """Return (obs_at, values, reasons). Raises TempestError if no usable obs."""
    obs = payload.get("obs") if isinstance(payload, dict) else None
    if not isinstance(obs, list) or not obs or not isinstance(obs[0], dict):
        raise TempestError("no observation in response")
    o = obs[0]
    ts = o.get("timestamp")
    if not isinstance(ts, (int, float)):
        raise TempestError("observation has no timestamp")
    vals, reasons = {}, {}
    for ours, key in FIELDS.items():
        v = o.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
            vals[ours] = float(v)
        else:
            vals[ours] = None
            reasons[ours] = "missing" if v is None else "not_numeric"
    return float(ts), vals, reasons


class TempestPoller:
    def __init__(self, conn: sqlite3.Connection, cfg, source: TempestSource | None) -> None:
        self.conn = conn
        self.cfg = cfg
        self.source = source

    def poll(self, now: float) -> str:
        tc = self.cfg.tempest
        if not tc.enabled:
            dbmod.set_component(self.conn, "tempest", "disabled", now,
                                {"code": "TEMPEST_NOT_CONFIGURED", "message": "tempest.enabled is false"})
            return "disabled"
        prev = dbmod.get_component(self.conn, "tempest")
        last_ok = prev["detail"].get("last_success_at") if prev else None
        try:
            if self.source is None:
                raise TempestError("no Tempest source configured")
            ts, vals, reasons = parse_obs(self.source.fetch_latest())
        except TempestError as e:
            dbmod.set_component(self.conn, "tempest", "error", now,
                                {"code": "TEMPEST_FETCH_FAILED", "message": str(e), "last_success_at": last_ok})
            return "error"
        self.conn.execute(
            "INSERT OR REPLACE INTO tempest_obs(obs_at, fetched_at, slp_hpa, station_hpa, wind_avg, wind_gust, "
            "wind_dir, rain_1h_mm, rain_day_mm, air_c, raw_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (ts, now, vals["slp_hpa"], vals["station_hpa"], vals["wind_avg"], vals["wind_gust"], vals["wind_dir"],
             vals["rain_1h_mm"], vals["rain_day_mm"], vals["air_c"], json.dumps({"reasons": reasons})))
        dbmod.set_component(self.conn, "tempest", "ok", now, {"last_success_at": now, "field_reasons": reasons})
        return "ok"


def tempest_status(conn: sqlite3.Connection, cfg, now: float) -> dict:
    tc = cfg.tempest
    if not tc.enabled:
        return {"status": "disabled", "error": {"code": "TEMPEST_NOT_CONFIGURED", "message": "tempest.enabled is false"}}
    comp = dbmod.get_component(conn, "tempest")
    if comp is None:
        return {"status": "error", "error": {"code": "TEMPEST_NO_DATA", "message": "not polled yet"}}
    if comp["status"] == "error":
        d = comp["detail"]
        return {"status": "error", "since": comp["since"],
                "error": {"code": d.get("code", "TEMPEST_FETCH_FAILED"), "message": d.get("message", ""),
                          "last_success_at": d.get("last_success_at")}}
    row = conn.execute("SELECT obs_at FROM tempest_obs ORDER BY obs_at DESC LIMIT 1").fetchone()
    if row is None or now - row[0] > tc.stale_after_s:
        return {"status": "stale", "since": row[0] if row else None,
                "error": {"code": "TEMPEST_STALE", "message": "observation older than 15 min"}}
    return {"status": "ok", "obs_at": row[0]}


def context(conn: sqlite3.Connection, cfg, now: float) -> dict:
    """Derived weather context; values null unless Tempest is ok."""
    st = tempest_status(conn, cfg, now)
    out = {"status": st["status"], "pressure_change_3h_hpa": None, "inverse_barometer_m": None,
           "onshore_wind_sustained": None, "wind_6h_mean_mps": None, "wind_6h_mean_dir_deg": None}
    if st["status"] != "ok":
        out["error"] = st.get("error")
        return out
    tc = cfg.tempest
    rows = conn.execute("SELECT obs_at, slp_hpa, wind_avg, wind_dir FROM tempest_obs WHERE obs_at >= ? AND "
                        "obs_at <= ? ORDER BY obs_at", (now - 6 * 3600, now)).fetchall()
    p = [(r[0], r[1]) for r in rows if r[1] is not None]
    if p:
        latest_t, latest_p = p[-1]
        out["inverse_barometer_m"] = round((1013.25 - latest_p) * 0.01, 3)
        old = [x for x in p if x[0] <= latest_t - 2.5 * 3600]
        if old:
            ref = min(old, key=lambda x: abs(x[0] - (latest_t - 3 * 3600)))
            out["pressure_change_3h_hpa"] = round(latest_p - ref[1], 2)
    w = [(r[2], r[3]) for r in rows if r[2] is not None and r[3] is not None]
    if w and rows[-1][0] - rows[0][0] >= 5.5 * 3600:
        u = sum(s * math.sin(math.radians(d)) for s, d in w) / len(w)
        v = sum(s * math.cos(math.radians(d)) for s, d in w) / len(w)
        mean_dir = (math.degrees(math.atan2(u, v)) + 360) % 360
        mean_speed = sum(s for s, _ in w) / len(w)
        lo, hi = tc.onshore_sector_deg
        out["wind_6h_mean_mps"] = round(mean_speed, 2)
        out["wind_6h_mean_dir_deg"] = round(mean_dir, 1)
        out["onshore_wind_sustained"] = bool(lo <= mean_dir <= hi and mean_speed >= tc.onshore_min_mps)
    return out
