"""Simulation engine: a virtual clock driving the world, the node, the lossy
radio and the *real* tidesvc Core (ingest -> derive -> alerts -> API).
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from tidesvc import calibration as calmod
from tidesvc import db as dbmod
from tidesvc import energy as energymod
from tidesvc.api import create_app
from tidesvc.config import Config
from tidesvc.core import Core
from tidesvc.notify import RecordingNotifier
from tidesvc.timeutil import LOCAL_TZ, FixedClock, local_date, parse_iso

from . import fwlogic as fw
from .noaa_fake import SimNoaaProvider
from .node import NodeModel
from .power import PowerSystem, Weather
from .radio import SimRadio
from .ramp import Inclinometer, Ramp, WakeEvent, random_loads, random_wakes
from .scenario import Scenario
from .world import SurgeEvent, TideWorld, WeatherNoise

DAY = 86400.0


@dataclass
class Probe:
    t: float
    code: int
    status: str
    level_m: float | None
    residual_m: float | None
    last_good_at: str | None
    predicted_m: float | None


@dataclass
class SimResult:
    scenario: Scenario
    db_path: str
    t0: float
    t1: float
    cfg: Config
    world: TideWorld
    node: NodeModel
    power: PowerSystem
    radio: SimRadio
    noaa: SimNoaaProvider
    notifier: RecordingNotifier
    core: Core
    probes: list[Probe] = field(default_factory=list)
    tx_log: list[tuple[float, int, int, float]] = field(default_factory=list)
    events: dict = field(default_factory=dict)
    cal_log: list[dict] = field(default_factory=list)
    wall_s: float = 0.0
    final_api: dict = field(default_factory=dict)


def _local_offset(t: float) -> float:
    return _dt.datetime.fromtimestamp(t, LOCAL_TZ).utcoffset().total_seconds()


def build_config(db_path: str) -> Config:
    cfg = Config()
    cfg.storage.db_path = db_path
    cfg.repeater.pubkey_prefix = "a1b2"
    return cfg


def run(sc: Scenario, workdir: str | None = None, verbose: bool = False) -> SimResult:
    wall0 = time.time()
    t0 = parse_iso(sc.start_iso)
    t1 = t0 + sc.days * DAY
    rng = np.random.default_rng(sc.seed)
    off = _local_offset(t0)
    workdir = workdir or tempfile.mkdtemp(prefix="tidesim-")
    db_path = str(Path(workdir) / f"{sc.name}-s{sc.seed}.db")
    if Path(db_path).exists():
        Path(db_path).unlink()

    # ---------------------------------------------------------------- world
    surges = [SurgeEvent(t0 + sc.surge_peak_day * DAY, sc.surge_peak_m, sc.surge_rise_sigma_h,
                         sc.surge_fall_sigma_h)] if sc.surge_peak_day is not None else []
    world = TideWorld(t0, t1, surges=surges,
                      weather=WeatherNoise(t0 - 10 * DAY, t1 + 10 * DAY, sigma_m=sc.weather_sigma_m, seed=sc.seed + 1))
    wakes = random_wakes(rng, t0, t1, sc.wakes_per_day, off)
    if sc.wake_burst_day is not None:
        tb = t0 + sc.wake_burst_day * DAY
        wakes += [WakeEvent(tb + k * 250, 0.18, 4.5, 70, 200) for k in range(8)]  # 8 boats in ~33 min
    ramp = Ramp(wakes=wakes, loads=random_loads(rng, t0, t1, sc.loads_per_day, off))
    sensor = Inclinometer(rng=np.random.default_rng(sc.seed + 2))
    snaps = []
    if sc.cold_snap is not None:
        snaps.append((t0 + sc.cold_snap[0] * DAY, t0 + sc.cold_snap[1] * DAY, sc.cold_snap[2]))
    weather = Weather(t0, int(math.ceil(sc.days)) + 2, off, target_psh=sc.target_psh, shading=sc.shading,
                      cold_snaps=snaps, seed=sc.seed + 3)
    power = PowerSystem(weather)
    power.soc_mah = power.capacity_mah * sc.initial_soc_pct / 100
    power.enclosure.temp_c = weather.air_c(t0)
    node = NodeModel(world, ramp, sensor, power, rng=np.random.default_rng(sc.seed + 4))
    node.next_wake = t0 + 7.0
    radio = SimRadio(rng=np.random.default_rng(sc.seed + 5))
    if sc.repeater_outage:
        a = t0 + sc.repeater_outage[0] * DAY
        radio.repeater_outages.append((a, a + sc.repeater_outage[1] * 3600))
    if sc.host_disconnect:
        a = t0 + sc.host_disconnect[0] * DAY
        radio.host_disconnects.append((a, a + sc.host_disconnect[1] * 60))
    radio.schedule_background(t0, t1)

    # ---------------------------------------------------------------- service (real code)
    clock = FixedClock(t0)
    noaa = SimNoaaProvider(world, now_fn=clock.now)
    if sc.noaa_outage:
        a = t0 + sc.noaa_outage[0] * DAY
        noaa.outages.append((a, a + sc.noaa_outage[1] * 3600))
    cfg = build_config(db_path)
    conn = dbmod.connect(db_path)
    notifier = RecordingNotifier()
    core = Core(conn, cfg, noaa, notifier)
    client = TestClient(create_app(cfg, db_path, clock))
    res = SimResult(sc, db_path, t0, t1, cfg, world, node, power, radio, noaa, notifier, core)
    res.events = {"surges": [(s.peak_t, s.peak_m) for s in surges], "repeater_outages": radio.repeater_outages,
                  "host_disconnects": radio.host_disconnects, "noaa_outages": noaa.outages, "cold_snaps": snaps,
                  "wake_burst": (t0 + sc.wake_burst_day * DAY) if sc.wake_burst_day is not None else None,
                  "reboot": (t0 + sc.reboot_day * DAY) if sc.reboot_day is not None else None}

    # ---------------------------------------------------------------- calibration plan
    plan = _plan_install(sc, world, t0)
    res.events["install"] = plan
    rng_cal = np.random.default_rng(sc.seed + 6)
    pending = [(plan["level_check_t"], "level_check"), (plan["tape_t"][0], "tape"), (plan["tape_t"][1], "tape"),
               (plan["fit_t"], "fit"), (plan["datum_tie_t"], "datum_tie")]
    pending.sort()

    def float_still(t: float) -> float:
        return float(world.water(t)) + ramp.freeboard_m

    # ---------------------------------------------------------------- loop
    reboot_t = res.events["reboot"]
    next_probe = t0
    t = t0
    day_key = local_date(t0)
    wake_mas_this_min = 0.0
    while t < t1:
        t_next = t + 60.0
        # node cycles in [t, t_next)
        while node.next_wake < t_next:
            tw = node.next_wake
            if reboot_t is not None and tw >= reboot_t:
                node.reboot(reboot_t, reason_flag=1 << 6)  # watchdog reset
                reboot_t = None
                continue
            pkt = node.cycle(tw)
            wake_mas_this_min += node.awake_charge_mas()
            res.tx_log.append((pkt.t_tx, pkt.boot_count, pkt.seq, pkt.truth_water_m))
            radio.transmit(pkt)
        load = node.i_sleep_ma + wake_mas_this_min / 60.0
        wake_mas_this_min = 0.0
        day_key = local_date(t)
        power.step(t, 60.0, load, day_key)
        for ev in radio.pop_until(t_next):
            clock.set(getattr(ev, "rx_at", None) or getattr(ev, "t"))
            core.handle(ev)
        clock.set(t_next)
        # operator actions (CLI equivalents)
        while pending and pending[0][0] + (660 if pending[0][1] in ("level_check", "tape") else 0) <= t_next:
            ta, kind = pending.pop(0)
            res.cal_log.append(_operator(kind, ta, t_next, core, cfg, conn, ramp, world, float_still, sc, rng_cal,
                                         plan, t0))
        core.tick(t_next)
        # API probes: every api_probe_s; every 5 min around outages
        dense = any(a - 3600 <= t_next <= b + 3600 for a, b in radio.repeater_outages + radio.host_disconnects)
        if t_next >= next_probe or (dense and int(t_next) % 300 == 0):
            res.probes.append(_probe(client, t_next))
            next_probe = t_next + sc.api_probe_s
        t = t_next
        if verbose and int(t - t0) % int(DAY) == 0:
            print(f"  day {(t - t0) / DAY:5.1f}  readings={conn.execute('SELECT COUNT(*) FROM readings').fetchone()[0]}"
                  f"  soc={100 * power.soc_mah / power.capacity_mah:5.1f}%  wall={time.time() - wall0:5.1f}s",
                  flush=True)
    # final rollup for complete days and the final API state
    energymod.rollup_through(conn, cfg, t1, days_back=int(sc.days) + 2)
    core.alerts.refresh_energy(t1)
    core.alerts.evaluate(t1)
    for path in ("/api/v1/status", "/api/v1/level/current", "/api/v1/node/health", "/api/v1/node/energy?days=3",
                 "/api/v1/calibration", "/api/v1/alerts?state=all"):
        r = client.get(path)
        res.final_api[path] = {"code": r.status_code, "body": r.json()}
    res.wall_s = time.time() - wall0
    return res


def _plan_install(sc: Scenario, world: TideWorld, t0: float) -> dict:
    """Pick two daylight tide states >= 0.5 m apart (a high and the next low, or vice versa)."""
    ext = world.astro_extremes(t0 + 3600, t0 + 4 * DAY)

    def daylight(t):
        h = _dt.datetime.fromtimestamp(t, LOCAL_TZ)
        return 7.75 <= h.hour + h.minute / 60 <= 16.25

    for a, b in zip(ext, ext[1:]):
        if daylight(a[0]) and daylight(b[0]) and abs(a[1] - b[1]) >= 0.5:
            fit_t = b[0] + 3600
            return {"level_check_t": a[0] - 1800, "tape_t": (a[0], b[0]), "fit_t": fit_t,
                    "datum_tie_t": fit_t + sc.datum_tie_after_days * DAY}
    raise RuntimeError("no daylight pair of tide states found in the first 4 days")


def _operator(kind, ta, now, core, cfg, conn, ramp, world, float_still, sc, rng, plan, t0) -> dict:
    if kind == "level_check":
        ang = float(ramp.angle_deg(np.array([float_still(ta)]))[0])
        meas = ang + float(rng.normal(0, sc.level_check_sigma_deg))
        oid = calmod.add_observation(conn, ta, "level_check", angle_deg=meas, note="sim: digital level on rail")
        return {"kind": kind, "t": ta, "obs_id": oid, "true_angle_deg": ang, "measured_deg": meas}
    if kind == "tape":
        fb = sc.mark_m - float_still(ta) + float(rng.normal(0, sc.tape_sigma_m))
        oid = calmod.add_observation(conn, ta, "tape", freeboard_m=fb, note="sim: tape, mean of 3")
        return {"kind": kind, "t": ta, "obs_id": oid, "freeboard_m": fb, "water_m": float(world.water(ta))}
    if kind == "fit":
        cid = calmod.fit_install(conn, cfg, now)
        row = dict(conn.execute("SELECT * FROM calibrations WHERE id=?", (cid,)).fetchone())
        core.deriver.invalidate()
        core.deriver.reprocess(row["valid_from"])
        return {"kind": kind, "t": now, "calibration": row}
    if kind == "datum_tie":
        r = calmod.datum_tie(conn, cfg, core.deriver, now, plan["tape_t"][0] - 6 * 3600, now)
        return {"kind": kind, "t": now, "result": {k: v for k, v in r.items()}}
    raise ValueError(kind)


def _probe(client: TestClient, t: float) -> Probe:
    r = client.get("/api/v1/level/current")
    b = r.json()
    lg = b.get("last_good") or {}
    return Probe(t, r.status_code, b.get("status"), b.get("level_m"), b.get("residual_m"), lg.get("at"),
                 b.get("predicted_m"))


_ = (json, fw, energymod)
