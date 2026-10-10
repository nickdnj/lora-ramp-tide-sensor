"""Time helpers. Storage is UTC epoch seconds (float); the API renders ISO-8601 Z.

Daily rollups use America/New_York local days (ARCHITECTURE 6.3).
"""

from __future__ import annotations

import datetime as _dt
import time
from typing import Callable, Protocol
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("America/New_York")
UTC = _dt.timezone.utc


class Clock(Protocol):
    def now(self) -> float: ...


class SystemClock:
    """Wall clock (UTC epoch seconds)."""

    def now(self) -> float:
        return time.time()


class FixedClock:
    """A settable clock for tests and the simulator's virtual time."""

    def __init__(self, t: float = 0.0) -> None:
        self.t = float(t)

    def now(self) -> float:
        return self.t

    def set(self, t: float) -> None:
        self.t = float(t)

    def advance(self, seconds: float) -> None:
        self.t += seconds


def iso(t: float | None) -> str | None:
    """UTC epoch seconds to ISO-8601 with a Z suffix (second resolution)."""
    if t is None:
        return None
    return _dt.datetime.fromtimestamp(round(t), UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str) -> float:
    """Parse ISO-8601 (Z, offset or naive=UTC) or YYYY-MM-DD to epoch seconds."""
    s = s.strip()
    if len(s) == 10:
        d = _dt.datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC)
        return d.timestamp()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    d = _dt.datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=UTC)
    return d.timestamp()


def utc_dt(t: float) -> _dt.datetime:
    return _dt.datetime.fromtimestamp(t, UTC)


def local_date(t: float) -> _dt.date:
    return _dt.datetime.fromtimestamp(t, LOCAL_TZ).date()


def local_day_bounds(day: _dt.date) -> tuple[float, float]:
    """UTC epoch bounds [start, end) of a local (America/New_York) day.

    Handles DST: 2026-11-01 is 25 h long, 2027-03-14 is 23 h long.
    """
    start = _dt.datetime(day.year, day.month, day.day, tzinfo=LOCAL_TZ)
    nxt = day + _dt.timedelta(days=1)
    end = _dt.datetime(nxt.year, nxt.month, nxt.day, tzinfo=LOCAL_TZ)
    return start.timestamp(), end.timestamp()


def local_time_hours(t: float) -> float:
    d = _dt.datetime.fromtimestamp(t, LOCAL_TZ)
    return d.hour + d.minute / 60.0 + d.second / 3600.0


ClockFn = Callable[[], float]
