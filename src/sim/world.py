"""Synthetic water level: harmonic tide (M2, S2, N2, K1, O1) + storm surge +
weather noise. All levels are metres above MLLW of this synthetic world.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

# speeds in degrees per hour (standard constituent speeds)
SPEEDS = {"M2": 28.9841042, "S2": 30.0, "N2": 28.4397295, "K1": 15.0410686, "O1": 13.9430356}


@dataclass
class Constituent:
    name: str
    amp_m: float
    phase_deg: float

    @property
    def omega(self) -> float:  # rad/s
        return math.radians(SPEEDS[self.name]) / 3600.0


def default_constituents() -> list[Constituent]:
    # mean range ~0.85 m, springs ~1.0 m: like 8531942 (Long Branch, ~0.9-1.0 m)
    return [Constituent("M2", 0.42, 20.0), Constituent("S2", 0.07, 55.0), Constituent("N2", 0.09, 340.0),
            Constituent("K1", 0.07, 160.0), Constituent("O1", 0.05, 140.0)]


@dataclass
class SurgeEvent:
    peak_t: float
    peak_m: float = 0.70
    rise_sigma_h: float = 2.0
    fall_sigma_h: float = 4.0

    def at(self, t):
        sig = np.where(np.asarray(t) < self.peak_t, self.rise_sigma_h, self.fall_sigma_h) * 3600.0
        return self.peak_m * np.exp(-0.5 * ((np.asarray(t) - self.peak_t) / sig) ** 2)


@dataclass
class WeatherNoise:
    """Sea-level weather noise (wind setup, pressure) on a 6-min grid.

    An Ornstein-Uhlenbeck process (correlation time tau_h) smoothed with a
    Gaussian kernel (smooth_h) and rescaled to sigma_m. Unsmoothed OU is
    Brownian at short scales (mm jumps every 6 min), which real sea-level
    residuals are not; it also made the *true* hi/lo times jitter by tens of
    minutes on flat tide tops.
    """

    t0: float
    t1: float
    sigma_m: float = 0.025
    tau_h: float = 10.0
    smooth_h: float = 1.5
    seed: int = 1
    _grid: np.ndarray = field(init=False, repr=False)
    _vals: np.ndarray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        rng = np.random.default_rng(self.seed)
        dt = 360.0
        n = int((self.t1 - self.t0) / dt) + 3
        a = math.exp(-dt / (self.tau_h * 3600))
        x = np.empty(n)
        x[0] = rng.normal(0, self.sigma_m)
        eps = rng.normal(0, self.sigma_m * math.sqrt(1 - a * a), n)
        for i in range(1, n):
            x[i] = a * x[i - 1] + eps[i]
        if self.smooth_h > 0:
            k_sig = self.smooth_h * 3600 / dt
            kk = np.arange(-int(4 * k_sig), int(4 * k_sig) + 1)
            ker = np.exp(-0.5 * (kk / k_sig) ** 2)
            ker /= ker.sum()
            x = np.convolve(np.pad(x, len(kk) // 2, mode="reflect"), ker, mode="valid")[:n]
            x *= self.sigma_m / max(1e-9, float(np.std(x)))
        self._grid = self.t0 - dt + dt * np.arange(n)
        self._vals = x

    def at(self, t):
        return np.interp(t, self._grid, self._vals)


class TideWorld:
    def __init__(self, t0: float, t1: float, z0: float = 0.50, constituents=None, surges=(),
                 weather: WeatherNoise | None = None) -> None:
        self.t0, self.t1 = t0, t1
        self.z0 = z0
        self.cons = list(constituents or default_constituents())
        self.surges = list(surges)
        self.weather = weather or WeatherNoise(t0 - 10 * 86400, t1 + 10 * 86400)
        self._epoch = t0

    def astro(self, t):
        t = np.asarray(t, dtype=float)
        x = (t - self._epoch)
        out = np.full_like(t, self.z0, dtype=float)
        for c in self.cons:
            out = out + c.amp_m * np.cos(c.omega * x - math.radians(c.phase_deg))
        return out

    def surge(self, t):
        t = np.asarray(t, dtype=float)
        out = np.zeros_like(t)
        for s in self.surges:
            out = out + s.at(t)
        return out

    def residual(self, t):
        return self.surge(t) + self.weather.at(t)

    def water(self, t):
        """True water level (MLLW metres)."""
        return self.astro(t) + self.residual(t)

    def astro_extremes(self, t0: float, t1: float) -> list[tuple[float, float, str]]:
        """Extremes of the astronomical tide (what NOAA publishes), refined to ~1 s."""
        step = 60.0
        ts = np.arange(t0 - 2 * step, t1 + 2 * step, step)
        v = self.astro(ts)
        d = np.diff(v)
        out = []
        for i in range(1, len(d)):
            if d[i - 1] > 0 >= d[i] or d[i - 1] < 0 <= d[i]:
                typ = "H" if d[i - 1] > 0 else "L"
                # parabola through three points around ts[i]
                y0, y1, y2 = v[i - 1], v[i], v[i + 1]
                den = y0 - 2 * y1 + y2
                off = 0.5 * (y0 - y2) / den if den != 0 else 0.0
                te = ts[i] + off * step
                if t0 <= te <= t1:
                    out.append((float(te), float(self.astro(te)), typ))
        return out
