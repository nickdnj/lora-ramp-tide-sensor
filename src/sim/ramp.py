"""Ramp, float and inclinometer models.

Ramp: rigid, hinged at the bulkhead, free end on a float. The float deck sits
``freeboard`` above the water; foot traffic pushes it down (load); boat wakes
make it heave. The ramp angle is asin((float - hinge) / L).

Inclinometer (SCL3300-like, ADR-005): mount offset (this is the theta0 the
install level check measures), temperature-dependent offset drift, white noise
after the on-chip ~10 Hz filter, 90/2^14 deg angle quantization.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


@dataclass
class WakeEvent:
    t: float
    amp_m: float  # initial heave amplitude
    period_s: float = 4.0
    decay_s: float = 50.0
    duration_s: float = 150.0


@dataclass
class LoadEvent:
    t: float
    duration_s: float
    sink_m: float  # float sinks by this much while loaded


@dataclass
class Ramp:
    length_m: float = 7.62
    hinge_m: float = 2.10  # hinge height above MLLW
    freeboard_m: float = 0.45  # float reference above water, unloaded
    wakes: list[WakeEvent] = field(default_factory=list)
    loads: list[LoadEvent] = field(default_factory=list)

    def heave(self, t: np.ndarray) -> np.ndarray:
        out = np.zeros_like(t)
        for w in self.wakes:
            if t[-1] < w.t or t[0] > w.t + w.duration_s:
                continue
            dt = t - w.t
            m = (dt >= 0) & (dt <= w.duration_s)
            out[m] += w.amp_m * np.exp(-dt[m] / w.decay_s) * np.sin(2 * math.pi * dt[m] / w.period_s)
        return out

    def load_sink(self, t: np.ndarray) -> np.ndarray:
        out = np.zeros_like(t)
        for ld in self.loads:
            if t[-1] < ld.t or t[0] > ld.t + ld.duration_s:
                continue
            out[(t >= ld.t) & (t <= ld.t + ld.duration_s)] += ld.sink_m
        return out

    def float_level(self, water: np.ndarray, t: np.ndarray) -> np.ndarray:
        return water + self.freeboard_m - self.load_sink(t) + self.heave(t)

    def angle_deg(self, float_level: np.ndarray) -> np.ndarray:
        x = np.clip((float_level - self.hinge_m) / self.length_m, -1.0, 1.0)
        return np.degrees(np.arcsin(x))


@dataclass
class Inclinometer:
    mount_offset_deg: float = 0.80
    temp_coeff_deg_per_c: float = 0.0035  # true drift; tidesvc k_T stays 0 (not bench-measured)
    noise_deg: float = 0.004
    lsb_deg: float = 90.0 / 16384.0
    roll_deg: float = 0.40
    rng: np.random.Generator = field(default_factory=lambda: np.random.default_rng(3))

    def read(self, angle_deg: np.ndarray, die_temp_c: float) -> tuple[np.ndarray, np.ndarray]:
        n = len(angle_deg)
        drift = self.temp_coeff_deg_per_c * (die_temp_c - 25.0)
        p = angle_deg + self.mount_offset_deg + drift + self.rng.normal(0, self.noise_deg, n)
        r = self.roll_deg + 0.02 * self.rng.standard_normal(n)
        return np.round(p / self.lsb_deg) * self.lsb_deg, np.round(r / self.lsb_deg) * self.lsb_deg


def random_wakes(rng: np.random.Generator, t0: float, t1: float, per_day: float, local_offset_s: float,
                 amp=(0.02, 0.10)) -> list[WakeEvent]:
    """Daytime (08-17 local) boat wakes, Poisson."""
    out = []
    day = 86400.0
    d = math.floor((t0 + local_offset_s) / day) * day - local_offset_s
    while d < t1:
        n = rng.poisson(per_day)
        for _ in range(n):
            t = d + rng.uniform(8 * 3600, 17 * 3600)
            if t0 <= t <= t1:
                out.append(WakeEvent(t, float(rng.uniform(*amp)), float(rng.uniform(3, 6))))
        d += day
    return out


def random_loads(rng: np.random.Generator, t0: float, t1: float, per_day: float, local_offset_s: float) -> list[LoadEvent]:
    """People and carts on the ramp/float during the day: 1-4 cm for 1-10 min."""
    out = []
    day = 86400.0
    d = math.floor((t0 + local_offset_s) / day) * day - local_offset_s
    while d < t1:
        for _ in range(rng.poisson(per_day)):
            t = d + rng.uniform(7 * 3600, 19 * 3600)
            if t0 <= t <= t1:
                out.append(LoadEvent(t, float(rng.uniform(60, 600)), float(rng.uniform(0.01, 0.04))))
        d += day
    return out
