"""Node power models: December insolation on a vertical south face, enclosure
temperature, a 1 W panel, the BQ25185 linear charger (VINDPM, /CE, NTC backstop,
6 h safety timer, DONE) and a LiFePO4 26650 cell. Ground truth for the energy
verdict (true harvest and consumption) is accumulated here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

LAT, LON = 40.333, -73.981


def sun_vertical_south(t: float) -> tuple[float, float]:
    """(elevation_deg, cos_incidence on a vertical south-facing plane)."""
    import datetime as _dt

    d = _dt.datetime.fromtimestamp(t, _dt.timezone.utc)
    n = d.timetuple().tm_yday
    b = 2 * math.pi * (n - 81) / 364
    eot_min = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)
    decl = math.radians(23.44) * math.sin(2 * math.pi * (284 + n) / 365)
    solar_h = d.hour + d.minute / 60 + d.second / 3600 + LON / 15 + eot_min / 60
    ha = math.radians(15 * (solar_h - 12))
    phi = math.radians(LAT)
    sin_el = math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(decl) * math.cos(ha)
    north = math.sin(decl) * math.cos(phi) - math.cos(decl) * math.sin(phi) * math.cos(ha)
    return math.degrees(math.asin(max(-1, min(1, sin_el)))), -north


def clear_sky_poa(t: float) -> float:
    el, cos_i = sun_vertical_south(t)
    if el <= 0.5:
        return 0.0
    am = 1 / math.sin(math.radians(el))
    dni = 1353 * 0.7 ** (am ** 0.678)
    dhi = 0.12 * dni * math.sin(math.radians(el)) + 20
    ghi = dni * math.sin(math.radians(el)) + dhi
    return max(0.0, dni * max(0.0, cos_i)) + dhi / 2 + 0.10 * ghi / 2


@dataclass
class Weather:
    """Daily cloud class and air temperature (December, NJ shore)."""

    t0: float
    days: int
    local_offset_s: float
    target_psh: float = 3.45  # PVGIS Dec mean, vertical south (ARCHITECTURE 4.5)
    shading: float = 1.0
    mean_air_c: float = 3.5
    cold_snaps: list[tuple[float, float, float]] = field(default_factory=list)  # (start, end, delta_c)
    seed: int = 11
    clouds: list[float] = field(init=False)
    _scale: float = field(init=False)
    _air_mean: list[float] = field(init=False)

    def __post_init__(self) -> None:
        rng = np.random.default_rng(self.seed)
        self.clouds = []
        for _ in range(self.days + 3):
            u = rng.uniform()
            self.clouds.append(0.95 if u < 0.38 else float(rng.uniform(0.45, 0.75)) if u < 0.72 else
                               float(rng.uniform(0.08, 0.2)))
        x, self._air_mean = 0.0, []
        for _ in range(self.days + 3):
            x = 0.7 * x + rng.normal(0, 2.2)
            self._air_mean.append(self.mean_air_c + x)
        self._scale = 1.0
        psh = [self.day_psh(k) for k in range(self.days)]
        self._scale = self.target_psh / (sum(psh) / len(psh))

    def _day(self, t: float) -> int:
        return int(math.floor((t - self.t0) / 86400.0)) if t >= self.t0 else 0

    def poa(self, t: float) -> float:
        k = min(max(self._day(t), 0), len(self.clouds) - 1)
        c = self.clouds[k]
        if 0.3 < c < 0.9:  # broken cloud: 30-min variability
            c *= 0.6 + 0.4 * (0.5 + 0.5 * math.sin(t / 1800.0 * 2.1 + k))
        return clear_sky_poa(t) * c * self._scale

    def day_psh(self, k: int) -> float:
        t = self.t0 + k * 86400
        return sum(self.poa(t + 600 * i) for i in range(144)) * 600 / 3600 / 1000

    def air_c(self, t: float) -> float:
        k = min(max(self._day(t), 0), len(self._air_mean) - 1)
        loc_h = ((t + self.local_offset_s) % 86400) / 3600
        cloudy = self.clouds[k] < 0.3
        amp = 1.5 if cloudy else 4.0
        v = self._air_mean[k] + amp * math.cos(2 * math.pi * (loc_h - 14.5) / 24)
        for s, e, dlt in self.cold_snaps:
            if s - 6 * 3600 <= t <= e + 6 * 3600:
                ramp = min(1.0, (t - (s - 6 * 3600)) / (6 * 3600), ((e + 6 * 3600) - t) / (6 * 3600))
                v += dlt * max(0.0, ramp)
        return v


@dataclass
class Enclosure:
    """Box (cell and die) temperature: lagged air temperature plus solar gain."""

    temp_c: float = 5.0
    tau_s: float = 5400.0
    gain_c_per_wm2: float = 0.010

    def step(self, air_c: float, poa: float, dt: float) -> float:
        target = air_c + self.gain_c_per_wm2 * poa
        self.temp_c += (target - self.temp_c) * (1 - math.exp(-dt / self.tau_s))
        return self.temp_c


OCV = [(0, 2.50), (5, 3.00), (10, 3.20), (20, 3.25), (40, 3.28), (60, 3.30), (80, 3.32), (90, 3.33), (95, 3.34),
       (98, 3.36), (100, 3.40)]


def ocv(soc_pct: float) -> float:
    xs, ys = zip(*OCV)
    return float(np.interp(soc_pct, xs, ys))


@dataclass
class PowerSystem:
    weather: Weather
    capacity_mah: float = 3200.0  # true (rated 3300, a little aged)
    soc_mah: float = 2600.0
    isc_ma: float = 185.0  # 1 W 6 V panel
    panel_derate: float = 0.85
    ichg_ma: float = 250.0
    r_int_ohm: float = 0.06
    enclosure: Enclosure = field(default_factory=Enclosure)
    # charger state
    ce_disabled: bool = True  # pull-up default
    done: bool = False
    latched: bool = False
    hw_cold: bool = False
    timer_s: float = 0.0
    last_charge_ma: float = 0.0
    last_supply_ma: float = 0.0
    # ground truth accumulators per local day: date -> dict
    truth: dict = field(default_factory=dict)

    def panel_avail_ma(self, t: float) -> float:
        return self.isc_ma * self.weather.poa(t) / 1000.0 * self.panel_derate * self.weather.shading

    def cell_temp(self) -> float:
        return self.enclosure.temp_c

    def _charge_enabled(self) -> bool:
        return not (self.ce_disabled or self.hw_cold or self.latched or self.done)

    def ce_pulse(self) -> None:
        self.timer_s = 0.0
        self.latched = False

    def step(self, t: float, dt: float, load_ma: float, day_key) -> None:
        w = self.weather
        self.enclosure.step(w.air_c(t), w.poa(t), dt)
        tc = self.cell_temp()
        if tc < -3.0:
            self.hw_cold = True
        elif tc > 2.4:
            self.hw_cold = False
        avail = self.panel_avail_ma(t)
        supply = charge = 0.0
        if avail > 0.5:
            supply = min(avail, load_ma)
            if self._charge_enabled():
                soc_pct = 100 * self.soc_mah / self.capacity_mah
                accept = self.ichg_ma if soc_pct < 95 else self.ichg_ma * max(0.0, 100 - soc_pct) / 5
                charge = max(0.0, min(self.ichg_ma, avail - supply, accept))
                self.timer_s += dt
                if self.timer_s >= 6 * 3600:
                    self.latched = True
                if soc_pct >= 99.5:
                    self.done = True
            if self.done and 100 * self.soc_mah / self.capacity_mah < 97.0:
                self.done = False
        else:
            self.timer_s = 0.0  # VIN loss clears the safety timer
            self.latched = False
            if self.done and 100 * self.soc_mah / self.capacity_mah < 99.0:
                self.done = False
        batt_ma = charge - (load_ma - supply)
        self.soc_mah = min(self.capacity_mah, max(0.0, self.soc_mah + batt_ma * dt / 3600))
        self.last_charge_ma, self.last_supply_ma = charge, supply
        d = self.truth.setdefault(day_key, {"harvest_mah": 0.0, "available_mah": 0.0, "consumption_mah": 0.0,
                                            "cold_inhibit_h": 0.0,
                                            "charge_mah": 0.0, "psh": 0.0, "reached_full": False,
                                            "min_soc_pct": 100.0, "min_cell_c": 99.0})
        d["harvest_mah"] += (supply + charge) * dt / 3600
        # what the panel could have delivered through this charger: capped at ICHG + load, and at the
        # load alone while charging is blocked by cold (a full cell does not reduce it)
        cold_blocked = self.ce_disabled or self.hw_cold
        cap = load_ma if cold_blocked else self.ichg_ma + load_ma
        d["available_mah"] += (min(avail, cap) if avail > 0.5 else 0.0) * dt / 3600
        d["charge_mah"] += charge * dt / 3600
        d["consumption_mah"] += load_ma * dt / 3600
        d["psh"] += w.poa(t) * dt / 3600 / 1000
        if avail > 0.5 and (self.ce_disabled or self.hw_cold):
            d["cold_inhibit_h"] += dt / 3600
        d["reached_full"] = d["reached_full"] or self.done
        d["min_soc_pct"] = min(d["min_soc_pct"], 100 * self.soc_mah / self.capacity_mah)
        d["min_cell_c"] = min(d["min_cell_c"], tc)

    def stat_pins(self, t: float) -> tuple[int, int]:
        """BQ25185 STAT1/STAT2 as the firmware reads them (open drain + pull-ups)."""
        if self.panel_avail_ma(t) <= 0.5:
            return 1, 1  # no input: high-Z, reads 'done/disabled'
        if self.latched:
            return 0, 0
        if self.hw_cold:
            return 0, 1
        if self.ce_disabled or self.done:
            return 1, 1
        return 1, 0

    def measure(self, t: float, awake_load_ma: float, rng: np.random.Generator) -> tuple[int, int, float]:
        """INA3221 read while the node is awake: (vbat_mv, vpanel_mv, ipanel_ma)."""
        avail = self.panel_avail_ma(t)
        soc_pct = 100 * self.soc_mah / self.capacity_mah
        if avail > 0.5:
            supply = min(avail, awake_load_ma)
            charge = 0.0
            if self._charge_enabled():
                accept = self.ichg_ma if soc_pct < 95 else self.ichg_ma * max(0.0, 100 - soc_pct) / 5
                charge = max(0.0, min(self.ichg_ma, avail - supply, accept))
            ipanel = supply + charge
            batt = charge - (awake_load_ma - supply)
            vindpm = supply + charge >= avail - 1e-6
            vb = ocv(soc_pct) + batt / 1000 * self.r_int_ohm + (0.25 if charge > 0 and soc_pct > 97 else 0)
            vb = min(vb, 3.65)
            voc = 7.7 + 0.05 * math.log(max(avail, 1.0) / self.isc_ma)
            vp = max(3.6, vb + 0.33) if vindpm else voc * 0.97
        else:
            ipanel, vp = 0.0, 0.0
            vb = ocv(soc_pct) - awake_load_ma / 1000 * self.r_int_ohm
        ipanel = max(0.0, ipanel * (1 + rng.normal(0, 0.01)) + rng.normal(0, 0.05))
        return int(round(vb * 1000 + rng.normal(0, 3))), int(round(vp * 1000)), float(ipanel)
