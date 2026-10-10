"""Fake NOAA provider derived from the simulated world (implements
tidesvc.noaa.PredictionProvider).

- 8531942 hilo predictions = extremes of the astronomical tide only (no surge,
  no weather), rounded like NOAA (minute, millimetre).
- 8531680 "Sandy Hook" observed = astronomical + 0.9 x the local weather/surge
  residual + 1 cm independent noise; its 6-min predictions = astronomical.
- Optional outage windows make every fetch fail (for SV-N5 behaviour).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from tidesvc.noaa import Extreme, NoaaError, ObsPoint

from .world import TideWorld


@dataclass
class SimNoaaProvider:
    world: TideWorld
    outages: list[tuple[float, float]] = field(default_factory=list)
    now_fn: object = None  # callable returning virtual now (to apply outages)
    seed: int = 21
    calls: int = 0
    failures: int = 0

    def _check(self) -> None:
        self.calls += 1
        if self.now_fn is not None:
            now = self.now_fn()
            if any(a <= now < b for a, b in self.outages):
                self.failures += 1
                raise NoaaError("simulated NOAA outage (timeout)")

    def fetch_hilo(self, station: str, begin: float, end: float) -> list[Extreme]:
        self._check()
        out = []
        for t, v, typ in self.world.astro_extremes(begin, end):
            out.append(Extreme(round(t / 60.0) * 60.0, round(v, 3), typ))
        if not out:
            raise NoaaError("No Predictions data was found")
        return out

    def fetch_observed(self, station: str, begin: float, end: float) -> list[ObsPoint]:
        self._check()
        start = np.ceil(begin / 360.0) * 360.0
        ts = np.arange(start, end + 1, 360.0)
        if len(ts) == 0:
            return []
        rng = np.random.default_rng(int(start) % (2**31) + self.seed)
        pred = self.world.astro(ts)
        obs = pred + 0.9 * self.world.residual(ts) + rng.normal(0, 0.01, len(ts))
        return [ObsPoint(float(t), round(float(o), 3), round(float(p), 3)) for t, o, p in zip(ts, obs, pred)]
