"""NOAA CO-OPS predictions (ARCHITECTURE 6.4, E6.1/E6.2).

- ``PredictionProvider`` is the interface. ``NoaaHttpProvider`` talks to the live
  datagetter; ``StaticPredictionProvider`` is a deterministic offline provider
  (a fixed list of extremes / observations, e.g. a recorded fixture). The
  simulator supplies its own provider implementing the same interface.
- Hi/lo extremes are cached in ``noaa_predictions``. A cached, published
  prediction covering t stays valid after a failed fetch.
- ``HiloPredictor`` interpolates with a half-cosine between consecutive
  extremes. No bracketing pair -> None (PREDICTION_UNAVAILABLE). Predictions are
  never stored or served as observations.
"""

from __future__ import annotations

import bisect
import datetime as _dt
import json
import math
import sqlite3
from dataclasses import dataclass
from typing import Protocol, Sequence

from . import db as dbmod
from .timeutil import UTC


@dataclass(frozen=True)
class Extreme:
    t: float  # UTC epoch s
    v: float  # metres, MLLW
    type: str  # 'H' | 'L'


@dataclass(frozen=True)
class ObsPoint:
    t: float
    v: float | None  # observed (None if missing)
    pred_v: float | None  # 6-min harmonic prediction at the same station


class NoaaError(RuntimeError):
    """Fetch failed, timed out, or returned malformed / no data."""


class PredictionProvider(Protocol):
    def fetch_hilo(self, station: str, begin: float, end: float) -> list[Extreme]: ...

    def fetch_observed(self, station: str, begin: float, end: float) -> list[ObsPoint]: ...


# --------------------------------------------------------------------------- HTTP
def _fmt_date(t: float) -> str:
    return _dt.datetime.fromtimestamp(t, UTC).strftime("%Y%m%d %H:%M")


def _parse_gmt(s: str) -> float:
    return _dt.datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=UTC).timestamp()


def hilo_params(station: str, begin: float, end: float, application: str) -> dict[str, str]:
    return {
        "product": "predictions",
        "application": application,
        "begin_date": _fmt_date(begin),
        "end_date": _fmt_date(end),
        "datum": "MLLW",
        "station": station,
        "time_zone": "gmt",
        "units": "metric",
        "interval": "hilo",
        "format": "json",
    }


def parse_hilo_response(payload: dict) -> list[Extreme]:
    if not isinstance(payload, dict):
        raise NoaaError("malformed response (not an object)")
    if "error" in payload:
        msg = payload["error"].get("message", "unknown error") if isinstance(payload["error"], dict) else str(payload["error"])
        raise NoaaError(f"NOAA error: {msg}")
    preds = payload.get("predictions")
    if not isinstance(preds, list) or not preds:
        raise NoaaError("malformed or empty predictions list")
    out = []
    try:
        for p in preds:
            typ = p["type"]
            if typ not in ("H", "L"):
                raise NoaaError(f"unexpected type {typ!r}")
            out.append(Extreme(t=_parse_gmt(p["t"]), v=float(p["v"]), type=typ))
    except (KeyError, ValueError, TypeError) as e:
        raise NoaaError(f"malformed prediction entry: {e}") from e
    out.sort(key=lambda e: e.t)
    return out


class NoaaHttpProvider:
    """Live datagetter client. Network only; never used by tests or the simulator."""

    def __init__(self, base_url: str, application: str, timeout_s: float = 20.0, client=None) -> None:
        self.base_url = base_url
        self.application = application
        self.timeout_s = timeout_s
        self._client = client

    def _get(self, params: dict) -> dict:
        import httpx

        try:
            if self._client is not None:
                r = self._client.get(self.base_url, params=params, timeout=self.timeout_s)
            else:
                r = httpx.get(self.base_url, params=params, timeout=self.timeout_s)
        except httpx.HTTPError as e:
            raise NoaaError(f"fetch failed: {e.__class__.__name__}: {e}") from e
        if r.status_code != 200:
            raise NoaaError(f"HTTP {r.status_code}")
        try:
            return r.json()
        except ValueError as e:
            raise NoaaError("response is not JSON") from e

    def fetch_hilo(self, station: str, begin: float, end: float) -> list[Extreme]:
        return parse_hilo_response(self._get(hilo_params(station, begin, end, self.application)))

    def fetch_observed(self, station: str, begin: float, end: float) -> list[ObsPoint]:
        base = {"application": self.application, "begin_date": _fmt_date(begin), "end_date": _fmt_date(end),
                "datum": "MLLW", "station": station, "time_zone": "gmt", "units": "metric", "format": "json"}
        obs = self._get({**base, "product": "water_level"})
        pred = self._get({**base, "product": "predictions", "interval": "6"})
        if "error" in obs or "error" in pred:
            raise NoaaError("NOAA error in observed/6-min response")
        try:
            pv = {_parse_gmt(p["t"]): float(p["v"]) for p in pred.get("predictions", [])}
            out = []
            for o in obs.get("data", []):
                t = _parse_gmt(o["t"])
                v = float(o["v"]) if o.get("v") not in (None, "") else None
                out.append(ObsPoint(t=t, v=v, pred_v=pv.get(t)))
        except (KeyError, ValueError, TypeError) as e:
            raise NoaaError(f"malformed observation entry: {e}") from e
        if not out:
            raise NoaaError("no observations returned")
        return out


class StaticPredictionProvider:
    """Deterministic offline provider (fixture data). Fails on demand for tests."""

    def __init__(self, extremes: Sequence[Extreme] = (), observed: Sequence[ObsPoint] = (),
                 fail: bool = False) -> None:
        self.extremes = sorted(extremes, key=lambda e: e.t)
        self.observed = sorted(observed, key=lambda o: o.t)
        self.fail = fail

    @classmethod
    def from_noaa_json(cls, path: str) -> "StaticPredictionProvider":
        with open(path) as fh:
            return cls(parse_hilo_response(json.load(fh)))

    def fetch_hilo(self, station: str, begin: float, end: float) -> list[Extreme]:
        if self.fail:
            raise NoaaError("offline provider configured to fail")
        out = [e for e in self.extremes if begin <= e.t <= end]
        if not out:
            raise NoaaError("No Predictions data was found")
        return out

    def fetch_observed(self, station: str, begin: float, end: float) -> list[ObsPoint]:
        if self.fail:
            raise NoaaError("offline provider configured to fail")
        return [o for o in self.observed if begin <= o.t <= end]


# --------------------------------------------------------------------------- math
def half_cosine(t: float, e1: Extreme, e2: Extreme) -> float:
    """pred(t) = h2 + (h1 - h2) * (1 + cos(pi*(t - t1)/(t2 - t1))) / 2."""
    frac = (t - e1.t) / (e2.t - e1.t)
    return e2.v + (e1.v - e2.v) * (1.0 + math.cos(math.pi * frac)) / 2.0


class HiloPredictor:
    """Half-cosine interpolation over a sorted list of extremes."""

    def __init__(self, extremes: Sequence[Extreme]) -> None:
        self.ext = sorted(extremes, key=lambda e: e.t)
        self._ts = [e.t for e in self.ext]

    def __bool__(self) -> bool:
        return len(self.ext) >= 2

    @property
    def covers_from(self) -> float | None:
        return self._ts[0] if self.ext else None

    @property
    def covers_until(self) -> float | None:
        return self._ts[-1] if self.ext else None

    def covers(self, t: float) -> bool:
        return len(self.ext) >= 2 and self._ts[0] <= t <= self._ts[-1]

    def predict(self, t: float) -> float | None:
        if not self.covers(t):
            return None
        i = bisect.bisect_right(self._ts, t)
        if i >= len(self._ts):
            return self.ext[-1].v
        e1, e2 = self.ext[i - 1], self.ext[i]
        return half_cosine(t, e1, e2)

    def extremes_between(self, t0: float, t1: float) -> list[Extreme]:
        lo = bisect.bisect_left(self._ts, t0)
        hi = bisect.bisect_right(self._ts, t1)
        return self.ext[lo:hi]


# --------------------------------------------------------------------------- cache
def store_extremes(conn: sqlite3.Connection, station: str, ext: Sequence[Extreme], now: float) -> int:
    conn.executemany(
        "INSERT INTO noaa_predictions(station, t, v, type, fetched_at) VALUES (?,?,?,?,?) "
        "ON CONFLICT(station, t) DO UPDATE SET v=excluded.v, type=excluded.type, fetched_at=excluded.fetched_at",
        [(station, e.t, e.v, e.type, now) for e in ext],
    )
    return len(ext)


def load_predictor(conn: sqlite3.Connection, station: str, t0: float | None = None,
                   t1: float | None = None) -> HiloPredictor:
    q = "SELECT t, v, type FROM noaa_predictions WHERE station=?"
    args: list = [station]
    if t0 is not None:
        q += " AND t >= ?"
        args.append(t0)
    if t1 is not None:
        q += " AND t <= ?"
        args.append(t1)
    rows = conn.execute(q + " ORDER BY t", args).fetchall()
    return HiloPredictor([Extreme(r["t"], r["v"], r["type"]) for r in rows])


def store_observed(conn: sqlite3.Connection, station: str, pts: Sequence[ObsPoint]) -> None:
    conn.executemany(
        "INSERT INTO noaa_observations(station, t, v, pred_v) VALUES (?,?,?,?) "
        "ON CONFLICT(station, t) DO UPDATE SET v=excluded.v, pred_v=excluded.pred_v",
        [(station, p.t, p.v, p.pred_v) for p in pts],
    )


def reference_residual(conn: sqlite3.Connection, station: str, t: float, max_age_s: float = 1800) -> float | None:
    """Sandy Hook residual (observed - 6-min predicted) nearest at or before t."""
    row = conn.execute(
        "SELECT t, v, pred_v FROM noaa_observations WHERE station=? AND t<=? AND t>=? AND v IS NOT NULL "
        "AND pred_v IS NOT NULL ORDER BY t DESC LIMIT 1", (station, t, t - max_age_s)).fetchone()
    if row is None:
        return None
    return row["v"] - row["pred_v"]


class NoaaService:
    """Fetch-and-cache orchestration; records component status for the API."""

    def __init__(self, conn: sqlite3.Connection, provider: PredictionProvider, cfg) -> None:
        self.conn = conn
        self.provider = provider
        self.cfg = cfg  # NoaaCfg

    def refresh_predictions(self, now: float) -> bool:
        begin = now - self.cfg.past_days * 86400
        end = now + self.cfg.future_days * 86400
        ok = True
        for station in (self.cfg.prediction_station,):
            try:
                ext = self.provider.fetch_hilo(station, begin, end)
                store_extremes(self.conn, station, ext, now)
            except NoaaError as e:
                ok = False
                self._status("error", now, {"code": "NOAA_FETCH_FAILED", "message": str(e)})
        if ok:
            self._status("ok", now, {"last_success_at": now})
        return ok

    def refresh_reference(self, now: float, hours: float = 6.0) -> bool:
        station = self.cfg.observed_reference
        try:
            pts = self.provider.fetch_observed(station, now - hours * 3600, now)
            store_observed(self.conn, station, pts)
            dbmod.set_component(self.conn, "noaa_reference", "ok", now, {"last_success_at": now})
            return True
        except NoaaError as e:
            dbmod.set_component(self.conn, "noaa_reference", "error", now,
                                {"code": "NOAA_REFERENCE_FAILED", "message": str(e)})
            return False

    def _status(self, status: str, now: float, detail: dict) -> None:
        prev = dbmod.get_component(self.conn, "noaa")
        if status == "error" and prev is not None:
            last = prev["detail"].get("last_success_at")
            if last is not None:
                detail = {**detail, "last_success_at": last}
        dbmod.set_component(self.conn, "noaa", status, now, detail)
