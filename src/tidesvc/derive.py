"""Derive: pitch -> level, validity, smoothing, prediction, residual, rate of rise
(ARCHITECTURE 6.4, E5.5, E6.2).

Conversion: level = h0 + L_eff * sin(radians(pitch_corr - theta0)),
            pitch_corr = pitch - k_T * (temp - 25).

Residual. ARCHITECTURE 6.4 defines residual = level_smooth - pred. The live
smoothing is a *trailing* 30-min median, which lags the water by ~12-15 min; at
mid-tide (~0.25 m/h) that alone is a 5-6 cm residual error. To compare like with
like, the prediction is passed through the same trailing median over the same
reading times (``predicted_smooth_m``) and residual = level_smooth -
predicted_smooth. ``predicted_m`` is still the plain prediction at t. Likewise
excess_rise = slope(level_smooth, 60 min) - slope(predicted_smooth, 60 min).
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from typing import Iterable, Sequence

from . import codec
from .noaa import HiloPredictor, load_predictor

LIVE = "rx"
BACKFILLED = "backfilled"


# --------------------------------------------------------------------------- math
def median(xs: Sequence[float]) -> float:
    """Median; even count = mean of the two middle values (same rule as firmware)."""
    s = sorted(xs)
    n = len(s)
    if n == 0:
        raise ValueError("median of empty sequence")
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def ls_slope(ts: Sequence[float], vs: Sequence[float]) -> float:
    """Least-squares slope in units per hour (ts in seconds)."""
    n = len(ts)
    if n < 2:
        raise ValueError("need at least 2 points")
    mt = math.fsum(ts) / n
    mv = math.fsum(vs) / n
    num = math.fsum((t - mt) * (v - mv) for t, v in zip(ts, vs))
    den = math.fsum((t - mt) ** 2 for t in ts)
    if den == 0:
        raise ValueError("degenerate time base")
    return num / den * 3600.0


@dataclass(frozen=True)
class Calibration:
    id: int
    valid_from: float
    theta0_deg: float
    h0_m: float
    l_eff_m: float
    k_t: float = 0.0
    pitch_min_deg: float | None = None
    pitch_max_deg: float | None = None
    method: str = "install"
    status: str = "active"
    datum: str = "bulkhead_mark"

    def pitch_corr(self, pitch_deg: float, temp_c: float | None) -> float:
        if self.k_t and temp_c is not None:
            return pitch_deg - self.k_t * (temp_c - 25.0)
        return pitch_deg

    def s(self, pitch_deg: float, temp_c: float | None = None) -> float:
        return math.sin(math.radians(self.pitch_corr(pitch_deg, temp_c) - self.theta0_deg))

    def level(self, pitch_deg: float, temp_c: float | None = None) -> float:
        return self.h0_m + self.l_eff_m * self.s(pitch_deg, temp_c)

    @property
    def datum_tied(self) -> bool:
        return self.datum == "MLLW"

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "Calibration":
        return cls(id=r["id"], valid_from=r["valid_from"], theta0_deg=r["theta0_deg"], h0_m=r["h0_m"],
                   l_eff_m=r["l_eff_m"], k_t=r["k_t"] or 0.0, pitch_min_deg=r["pitch_min_deg"],
                   pitch_max_deg=r["pitch_max_deg"], method=r["method"], status=r["status"], datum=r["datum"])


def level_from_pitch(pitch_deg: float, theta0_deg: float, h0_m: float, l_eff_m: float,
                     k_t: float = 0.0, temp_c: float | None = None) -> float:
    cal = Calibration(0, 0.0, theta0_deg, h0_m, l_eff_m, k_t)
    return cal.level(pitch_deg, temp_c)


def invalid_reason(flags: int, pitch_deg: float | None, pitch_sd_deg: float | None,
                   cal: Calibration | None, envelope_margin_deg: float, max_sd_deg: float) -> str | None:
    if flags & codec.F_SENSOR_SKIPPED:
        return "sensor_skipped"
    if flags & codec.F_SENSOR_ERROR or pitch_deg is None:
        return "sensor_error"
    if flags & codec.F_OUT_OF_RANGE:
        return "out_of_range"
    if cal is not None and cal.pitch_min_deg is not None and cal.pitch_max_deg is not None:
        if pitch_deg < cal.pitch_min_deg - envelope_margin_deg or pitch_deg > cal.pitch_max_deg + envelope_margin_deg:
            return "out_of_envelope"
    if pitch_sd_deg is not None and pitch_sd_deg > max_sd_deg:
        return "high_sd"
    if cal is None:
        return "no_calibration"
    return None


# --------------------------------------------------------------------------- calibrations
def load_calibrations(conn: sqlite3.Connection, status: str = "active") -> list[Calibration]:
    rows = conn.execute("SELECT * FROM calibrations WHERE status=? ORDER BY valid_from, id", (status,)).fetchall()
    return [Calibration.from_row(r) for r in rows]


def calibration_at(cals: Sequence[Calibration], t: float) -> Calibration | None:
    """Latest active calibration with valid_from <= t (ties: newest id)."""
    best = None
    for c in cals:
        if c.valid_from <= t and (best is None or (c.valid_from, c.id) >= (best.valid_from, best.id)):
            best = c
    return best


# --------------------------------------------------------------------------- deriver
class Deriver:
    """Computes and stores ``derived`` rows. Holds cached calibrations/predictions;
    call ``invalidate()`` after either changes."""

    def __init__(self, conn: sqlite3.Connection, cfg) -> None:
        self.conn = conn
        self.cfg = cfg  # Config
        self._cals: list[Calibration] | None = None
        self._pred: HiloPredictor | None = None

    def invalidate(self) -> None:
        self._cals = None
        self._pred = None

    @property
    def cals(self) -> list[Calibration]:
        if self._cals is None:
            self._cals = load_calibrations(self.conn)
        return self._cals

    @property
    def predictor(self) -> HiloPredictor:
        if self._pred is None:
            self._pred = load_predictor(self.conn, self.cfg.noaa.prediction_station)
        return self._pred

    # -- one reading ------------------------------------------------------------
    def process(self, reading_id: int) -> dict:
        c = self.cfg.calibration
        r = self.conn.execute("SELECT * FROM readings WHERE id=?", (reading_id,)).fetchone()
        t = r["t"]
        live = r["time_source"] != BACKFILLED
        cal = calibration_at(self.cals, t)
        reason = invalid_reason(r["flags"], r["pitch_deg"], r["pitch_sd_deg"], cal,
                                c.envelope_margin_deg, c.max_pitch_sd_deg)
        level_raw = None
        if cal is not None and r["pitch_deg"] is not None and reason not in ("sensor_error", "sensor_skipped"):
            level_raw = cal.level(r["pitch_deg"], r["temp_c"])
        valid = reason is None
        out = dict(reading_id=reading_id, t=t, live=int(live), calibration_id=cal.id if cal else None,
                   level_raw_m=level_raw, level_smooth_m=None, predicted_m=None, predicted_smooth_m=None,
                   residual_m=None, excess_rise_mph=None, valid=int(valid), invalid_reason=reason,
                   smooth_reason=None, residual_reason=None)
        pred = self.predictor
        out["predicted_m"] = pred.predict(t)

        if not valid:
            out["smooth_reason"] = "invalid_reading"
            out["residual_reason"] = "invalid_reading"
        else:
            window_s = c.window_min * 60
            pts = self._window_points(t, window_s, live_only=live)
            pts.append((t, r["pitch_deg"], r["temp_c"]))
            if len(pts) < c.min_points:
                out["smooth_reason"] = "insufficient_points"
                out["residual_reason"] = "insufficient_points"
            else:
                out["level_smooth_m"] = median([cal.level(p, tc) for _, p, tc in pts])
                preds = [pred.predict(tt) for tt, _, _ in pts]
                if all(p is not None for p in preds):
                    out["predicted_smooth_m"] = median(preds)  # type: ignore[arg-type]
                if not cal.datum_tied:
                    out["residual_reason"] = "datum_not_tied"
                elif out["predicted_smooth_m"] is None:
                    out["residual_reason"] = "prediction_unavailable"
                else:
                    out["residual_m"] = out["level_smooth_m"] - out["predicted_smooth_m"]
                out["excess_rise_mph"] = self._excess_rise(t, live, out)
        self._store(out)
        return out

    def _window_points(self, t: float, window_s: float, live_only: bool) -> list[tuple[float, float, float]]:
        q = ("SELECT r.t, r.pitch_deg, r.temp_c FROM readings r JOIN derived d ON d.reading_id=r.id "
             "WHERE r.t > ? AND r.t < ? AND d.valid=1")
        if live_only:
            q += " AND d.live=1"
        rows = self.conn.execute(q, (t - window_s, t)).fetchall()
        return [(row[0], row[1], row[2]) for row in rows]

    def _excess_rise(self, t: float, live: bool, cur: dict) -> float | None:
        if cur["predicted_smooth_m"] is None or cur["level_smooth_m"] is None:
            return None
        q = ("SELECT t, level_smooth_m, predicted_smooth_m FROM derived WHERE t > ? AND t < ? AND valid=1 "
             "AND level_smooth_m IS NOT NULL AND predicted_smooth_m IS NOT NULL")
        if live:
            q += " AND live=1"
        rows = self.conn.execute(q, (t - 3600, t)).fetchall()
        ts = [row[0] for row in rows] + [t]
        if len(ts) < 6 or (ts[-1] - min(ts)) < 1800:
            return None
        lv = [row[1] for row in rows] + [cur["level_smooth_m"]]
        pv = [row[2] for row in rows] + [cur["predicted_smooth_m"]]
        return ls_slope(ts, lv) - ls_slope(ts, pv)

    def _store(self, d: dict) -> None:
        cols = list(d.keys())
        self.conn.execute(
            f"INSERT OR REPLACE INTO derived({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
            [d[k] for k in cols],
        )

    # -- reprocess ----------------------------------------------------------------
    def reprocess(self, from_t: float, to_t: float | None = None) -> int:
        """Recompute derived rows for readings with t >= from_t. Raw is untouched."""
        self.invalidate()
        args: list = [from_t]
        q = "SELECT id FROM readings WHERE t >= ?"
        if to_t is not None:
            q += " AND t <= ?"
            args.append(to_t)
        ids = [r[0] for r in self.conn.execute(q + " ORDER BY t, id", args).fetchall()]
        self.conn.execute("BEGIN")
        try:
            dq = "DELETE FROM derived WHERE t >= ?" + (" AND t <= ?" if to_t is not None else "")
            self.conn.execute(dq, args)
            for rid in ids:
                self.process(rid)
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return len(ids)


# --------------------------------------------------------------------------- analysis
def centred_series(conn: sqlite3.Connection, t0: float, t1: float, window_min: float = 30.0,
                   min_points: int = 4, cal: Calibration | None = None) -> list[tuple[float, float]]:
    """Centred rolling median of valid raw levels (history/calibration; no lag).

    Uses stored level_raw_m, or recomputes from pitch with ``cal`` if given.
    """
    half = window_min * 60 / 2
    rows = conn.execute(
        "SELECT r.t, r.pitch_deg, r.temp_c, d.level_raw_m FROM readings r JOIN derived d ON d.reading_id=r.id "
        "WHERE d.valid=1 AND r.t >= ? AND r.t <= ? ORDER BY r.t", (t0 - half, t1 + half)).fetchall()
    ts = [r[0] for r in rows]
    vs = [cal.level(r[1], r[2]) if cal is not None else r[3] for r in rows]
    return centred_median(ts, vs, window_min, min_points, t0, t1)


def centred_median(ts: Sequence[float], vs: Sequence[float], window_min: float = 30.0, min_points: int = 4,
                   t0: float | None = None, t1: float | None = None) -> list[tuple[float, float]]:
    half = window_min * 60 / 2
    out = []
    lo = 0
    hi = 0
    n = len(ts)
    for i, t in enumerate(ts):
        if (t0 is not None and t < t0) or (t1 is not None and t > t1):
            continue
        while lo < n and ts[lo] < t - half:
            lo += 1
        while hi < n and ts[hi] <= t + half:
            hi += 1
        win = vs[lo:hi]
        if len(win) >= min_points:
            out.append((t, median(win)))
    return out


@dataclass(frozen=True)
class ObservedExtreme:
    t: float
    v: float
    type: str
    anchor_t: float
    n_points: int


def find_extreme_near(series_t: Sequence[float], series_v: Sequence[float], anchor_t: float, typ: str,
                      search_s: float = 150 * 60, fit_half_s: float = 75 * 60,
                      min_points: int = 12) -> ObservedExtreme | None:
    """Locate the observed extreme of type 'H'/'L' near an anchor (e.g. the
    predicted extreme), refined by a least-squares parabola over +/- fit_half_s.
    Returns None if data is too sparse or the vertex is not inside the fit window."""
    idx = [i for i, t in enumerate(series_t) if abs(t - anchor_t) <= search_s]
    if len(idx) < min_points:
        return None
    pick = max if typ == "H" else min
    i_ext = pick(idx, key=lambda i: series_v[i])
    tc = series_t[i_ext]
    fit = [i for i in idx if abs(series_t[i] - tc) <= fit_half_s]
    if len(fit) < min_points:
        return None
    xs = [(series_t[i] - tc) / 3600.0 for i in fit]
    ys = [series_v[i] for i in fit]
    coef = _polyfit2(xs, ys)
    if coef is None:
        return None
    a, b, c0 = coef
    if (typ == "H" and a >= 0) or (typ == "L" and a <= 0):
        return None
    xv = -b / (2 * a)
    if abs(xv) * 3600 > fit_half_s:
        return None
    return ObservedExtreme(t=tc + xv * 3600, v=c0 + b * xv + a * xv * xv, type=typ, anchor_t=anchor_t,
                           n_points=len(fit))


def _polyfit2(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float, float] | None:
    """Least-squares y = a x^2 + b x + c via normal equations (3x3)."""
    s = [math.fsum(x ** k for x in xs) for k in range(5)]
    t = [math.fsum(y * x ** k for x, y in zip(xs, ys)) for k in range(3)]
    m = [[s[4], s[3], s[2], t[2]], [s[3], s[2], s[1], t[1]], [s[2], s[1], s[0], t[0]]]
    for col in range(3):
        piv = max(range(col, 3), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            return None
        m[col], m[piv] = m[piv], m[col]
        for r in range(3):
            if r != col:
                f = m[r][col] / m[col][col]
                for k in range(col, 4):
                    m[r][k] -= f * m[col][k]
    return m[0][3] / m[0][0], m[1][3] / m[1][1], m[2][3] / m[2][2]


def iter_valid_live(conn: sqlite3.Connection, t0: float, t1: float) -> Iterable[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM derived WHERE t >= ? AND t <= ? AND valid=1 AND live=1 ORDER BY t", (t0, t1))
