"""Energy log (ARCHITECTURE 6.6; E7.1). The pilot's headline question.

Harvest definition (deviation from ARCHITECTURE 6.6, found in simulation):
ARCHITECTURE integrates the raw ``ipanel`` sample. The sample is taken while the
node is awake (~25-40 mA from SYS). With a weak panel the BQ25185 sits in VINDPM
and ``ipanel`` is the panel's available current regardless of load, so the raw
sample is right while charging. But when charging is *off* (DONE, cold inhibit,
CE override, latch fault) the panel supplies only the load, and the sample then
measures the node's *awake* current, not its average (~0.5 mA). Integrating it
would credit ~25 mA x daylight hours of harvest that never existed, which can
turn a cold-inhibited deficit week into a "surplus". So, per sample:

- CHRG set, panel pulled down (VINDPM, vpanel < vbat + 1.0 V): panel-limited,
  harvest current = ipanel
- CHRG set, panel not pulled down (charger-limited, e.g. CV taper near full):
  ipanel = awake load at the INA read + charge, so
  harvest current = ipanel - i_read_ma + modelled average load
- panel present, no CHRG -> harvest current = min(ipanel, modelled average load)
- otherwise              -> 0
The VINDPM test (vpanel vs vbat) relies on BQ25185 behaviour to confirm on the
bench (TEST-PLAN B10).

Consumption is the bench model: cycles x awake_ms x I_awake + sleep x I_sleep,
with the constants recorded per day. Gaps > 15 min are not integrated and
``coverage_pct`` is reported.

Verdict (deviation from the letter of ARCHITECTURE 6.6, following its stated
intent): accepted harvest is capped once the cell is full, so harvest /
consumption tends to ~1.0 for any node that keeps reaching full, however big the
panel. A cell that reached full on at least half of the qualifying days is
therefore "surplus"; otherwise the 2.0 / 1.0 ratio thresholds apply.
"""

from __future__ import annotations

import datetime as _dt
import sqlite3
from dataclasses import dataclass

from . import codec
from .timeutil import LOCAL_TZ, local_date, local_day_bounds


VIN_PRESENT_MV = 3000


def is_done(r) -> bool:
    """DONE bit with panel input present. Without input the BQ25185 STAT pins float
    high (1/1); firmware built to the letter of ARCHITECTURE 4.7 would then report
    DONE every night, so the server ignores DONE without panel voltage."""
    return bool((r["chg_bits"] or 0) & codec.CHG_DONE) and (r["vpanel_mv"] or 0) >= VIN_PRESENT_MV


def _interval_for_flags(flags: int) -> int:
    if flags & codec.F_CRITICAL_BATT:
        return 3600
    if flags & codec.F_REDUCED_INTERVAL:
        return 900
    return 300


def avg_load_ma(cfg, interval_s: int = 300) -> float:
    e = cfg.energy
    awake_s = e.nominal_awake_ms / 1000.0
    return (e.awake_mas_per_cycle + max(0.0, interval_s - awake_s) * e.i_sleep_ua / 1000.0) / interval_s


def harvest_current_ma(cfg, r) -> float | None:
    """Per-sample harvest current (mA) per the definition in the module docstring."""
    ip = r["ipanel_ma"]
    if ip is None:
        return None
    chg = r["chg_bits"] or 0
    vp, vb = r["vpanel_mv"], r["vbat_mv"]
    e = cfg.energy
    if chg & codec.CHG_CHRG:
        if vp is not None and vb is not None and vp > vb + e.vindpm_margin_mv:
            return max(0.0, float(ip) - e.i_read_ma) + avg_load_ma(cfg, _interval_for_flags(r["flags"] or 0))
        return float(ip)
    # panel input judged by voltage: an INA3221 current offset (~1 mA on a 0.1 ohm shunt) must not count at night
    panel_present = (vp >= VIN_PRESENT_MV) if vp is not None else ip > 1.0
    if not panel_present:
        return 0.0
    return min(float(ip), avg_load_ma(cfg, _interval_for_flags(r["flags"] or 0)))


@dataclass
class DayRollup:
    date: str
    harvest_mah: float
    harvest_mwh: float
    consumption_est_mah: float
    net_mah: float
    coverage_pct: float
    reached_full: bool
    charge_inhibit_cold_h: float
    charging_h: float
    vbat_rest_v: float | None
    vbat_min_v: float | None
    vbat_max_v: float | None
    vbat_end_v: float | None
    panel_peak_ma: float | None
    temp_min_c: float | None
    i_sleep_ua: float
    i_awake_ma: float
    n_readings: int


def rollup_day(conn: sqlite3.Connection, cfg, day: _dt.date) -> DayRollup:
    e = cfg.energy
    start, end = local_day_bounds(day)
    rows = conn.execute(
        "SELECT t, vbat_mv, vpanel_mv, ipanel_ma, chg_bits, awake_ms_prev, flags, temp_c FROM readings "
        "WHERE t >= ? AND t < ? ORDER BY t", (start - e.max_gap_s, end + e.max_gap_s)).fetchall()
    in_day = [r for r in rows if start <= r["t"] < end]
    harvest = mwh = covered = cold_s = chg_s = 0.0
    for a, b in zip(rows, rows[1:]):
        dt = b["t"] - a["t"]
        if dt <= 0 or dt > e.max_gap_s:
            continue
        lo, hi = max(a["t"], start), min(b["t"], end)
        if hi <= lo:
            continue
        ha, hb = harvest_current_ma(cfg, a), harvest_current_ma(cfg, b)
        if ha is None or hb is None:
            continue
        frac = (hi - lo) / 3600.0
        harvest += (ha + hb) / 2.0 * frac
        va = (a["vbat_mv"] or 0) / 1000.0
        vb = (b["vbat_mv"] or 0) / 1000.0
        mwh += (ha * va + hb * vb) / 2.0 * frac
        covered += hi - lo
        if (a["chg_bits"] or 0) & codec.CHG_COLD_INHIBIT:
            cold_s += hi - lo
        if (a["chg_bits"] or 0) & codec.CHG_CHRG:
            chg_s += hi - lo
    day_s = end - start
    # consumption: whole day, from the bench model and reported awake times
    awake = [r["awake_ms_prev"] for r in in_day if (r["awake_ms_prev"] or 0) > 0]
    awake_s = (sum(awake) / len(awake) / 1000.0) if awake else e.nominal_awake_ms / 1000.0
    if in_day:
        intervals = sorted(_interval_for_flags(r["flags"] or 0) for r in in_day)
        interval = intervals[len(intervals) // 2]
    else:
        interval = cfg.node.interval_s
    cycles = day_s / interval
    i_awake = e.i_awake_ma
    cons = cycles * awake_s * i_awake / 3600.0 + max(0.0, day_s - cycles * awake_s) * e.i_sleep_ua / 1000.0 / 3600.0
    vb = [r["vbat_mv"] / 1000.0 for r in in_day if r["vbat_mv"] is not None]
    rest = []
    for r in in_day:
        lt = _dt.datetime.fromtimestamp(r["t"], LOCAL_TZ)
        if 2 <= lt.hour < 5 and r["vbat_mv"] is not None:
            rest.append(r["vbat_mv"] / 1000.0)
    ip = [r["ipanel_ma"] for r in in_day if r["ipanel_ma"] is not None]
    temps = [r["temp_c"] for r in in_day if r["temp_c"] is not None]
    return DayRollup(
        date=day.isoformat(), harvest_mah=harvest, harvest_mwh=mwh, consumption_est_mah=cons,
        net_mah=harvest - cons, coverage_pct=100.0 * covered / day_s,
        reached_full=any(is_done(r) for r in in_day),
        charge_inhibit_cold_h=cold_s / 3600.0, charging_h=chg_s / 3600.0,
        vbat_rest_v=min(rest) if rest else None, vbat_min_v=min(vb) if vb else None,
        vbat_max_v=max(vb) if vb else None, vbat_end_v=vb[-1] if vb else None,
        panel_peak_ma=max(ip) if ip else None, temp_min_c=min(temps) if temps else None,
        i_sleep_ua=e.i_sleep_ua, i_awake_ma=i_awake, n_readings=len(in_day))


def store_rollup(conn: sqlite3.Connection, r: DayRollup, now: float) -> None:
    d = dict(r.__dict__)
    d["reached_full"] = int(d["reached_full"])
    d["computed_at"] = now
    cols = list(d)
    conn.execute(f"INSERT OR REPLACE INTO energy_daily({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                 [d[c] for c in cols])


def rollup_through(conn: sqlite3.Connection, cfg, now: float, days_back: int = 3) -> list[DayRollup]:
    """Recompute rollups for the last ``days_back`` complete local days (idempotent;
    late/backfilled data is picked up)."""
    today = local_date(now)
    out = []
    for k in range(days_back, 0, -1):
        d = today - _dt.timedelta(days=k)
        r = rollup_day(conn, cfg, d)
        if r.n_readings == 0 and conn.execute("SELECT 1 FROM readings WHERE t < ? LIMIT 1",
                                              (local_day_bounds(d)[0],)).fetchone() is None:
            continue  # before the first reading ever: nothing to log
        store_rollup(conn, r, now)
        out.append(r)
    return out


# --------------------------------------------------------------------------- verdict
def daily_rows(conn: sqlite3.Connection, first: _dt.date, last: _dt.date) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM energy_daily WHERE date >= ? AND date <= ? ORDER BY date",
                        (first.isoformat(), last.isoformat())).fetchall()


def soc_estimate(conn: sqlite3.Connection, cfg, now: float) -> dict:
    """Coulomb count from the last DONE anchor (100%), clamped to [0, capacity]."""
    e = cfg.energy
    anc = conn.execute("SELECT t FROM readings WHERE (chg_bits & ?) != 0 AND vpanel_mv >= ? AND t <= ? "
                       "ORDER BY t DESC LIMIT 1", (codec.CHG_DONE, VIN_PRESENT_MV, now)).fetchone()
    if anc is None:
        return {"soc_est_pct": None, "soc_mah": None, "soc_anchor": None, "reason": "no_done_anchor_yet"}
    t_anchor = anc[0]
    rows = conn.execute("SELECT t, vbat_mv, vpanel_mv, ipanel_ma, chg_bits, flags FROM readings WHERE t >= ? "
                        "AND t <= ? ORDER BY t", (t_anchor, now)).fetchall()
    soc = e.capacity_mah
    load = avg_load_ma(cfg)
    for a, b in zip(rows, rows[1:]):
        dt_h = (b["t"] - a["t"]) / 3600.0
        if dt_h <= 0:
            continue
        ha = harvest_current_ma(cfg, a) if (b["t"] - a["t"]) <= e.max_gap_s else 0.0
        soc = min(e.capacity_mah, max(0.0, soc + ((ha or 0.0) - load) * dt_h))
        if is_done(b):
            soc = e.capacity_mah
    if rows:
        soc = max(0.0, soc - load * max(0.0, now - rows[-1]["t"]) / 3600.0)
    return {"soc_est_pct": round(100.0 * soc / e.capacity_mah, 1), "soc_mah": soc,
            "soc_anchor": {"event": "DONE", "at": t_anchor}}


def negative_streak(conn: sqlite3.Connection, cfg, now: float) -> int:
    e = cfg.energy
    yesterday = local_date(now) - _dt.timedelta(days=1)
    rows = {r["date"]: r for r in conn.execute("SELECT * FROM energy_daily WHERE date <= ? ORDER BY date DESC",
                                                (yesterday.isoformat(),)).fetchall()}
    streak = 0
    d = yesterday
    for _ in range(400):
        r = rows.get(d.isoformat())
        if r is None:
            if not rows or d.isoformat() < min(rows):
                break
        elif r["coverage_pct"] >= e.min_coverage_pct:
            if r["net_mah"] < 0:
                streak += 1
            else:
                break
        d -= _dt.timedelta(days=1)
    return streak


def verdict(conn: sqlite3.Connection, cfg, now: float) -> dict:
    e = cfg.energy
    last = local_date(now) - _dt.timedelta(days=1)
    first = last - _dt.timedelta(days=e.verdict_window_days - 1)
    rows = daily_rows(conn, first, last)
    q = [r for r in rows if r["coverage_pct"] >= e.min_coverage_pct]
    out = {"window_days": e.verdict_window_days, "window": [first.isoformat(), last.isoformat()],
           "qualifying_days": len(q), "energy_ratio": None, "assessment": "insufficient_data",
           "days_reached_full": sum(1 for r in rows if r["reached_full"]),
           "charge_inhibit_cold_h": round(sum(r["charge_inhibit_cold_h"] or 0 for r in rows), 2),
           "projected_days_to_empty": None,
           "negative_streak_days": negative_streak(conn, cfg, now),
           "basis": (f"harvest = integrated panel current while charging, panel-covered load otherwise; "
                     f"consumption = bench model, i_sleep {e.i_sleep_ua:g} uA, "
                     f"{e.awake_mas_per_cycle:g} mAs/cycle")}
    if len(q) >= e.min_verdict_days:
        h = sum(r["harvest_mah"] for r in q)
        c = sum(r["consumption_est_mah"] for r in q)
        ratio = h / c if c > 0 else None
        full = [r for r in q if r["reached_full"]]
        out["energy_ratio"] = round(ratio, 3) if ratio is not None else None
        out["qualifying_days_reached_full"] = len(full)
        out["energy_ratio_is_lower_bound"] = bool(full)
        if ratio is not None:
            out["assessment"] = assessment_for_ratio(ratio)
            out["assessment_basis"] = "energy_ratio"
        # Accepted harvest is capped once the cell is full (the charger stops taking
        # current), so by conservation the ratio tends to ~1.0 for any node whose
        # cell keeps reaching full, however large the panel. ARCHITECTURE 6.6 says
        # reaching full is itself the "panel is large enough" signal; this applies it:
        # full on at least half the qualifying days -> surplus.
        if len(full) * 2 >= len(q) and out["assessment"] != "surplus":
            out["assessment"] = "surplus"
            out["assessment_basis"] = (f"cell reached full on {len(full)} of {len(q)} qualifying days "
                                       f"(accepted harvest is capped by a full cell)")
    last7 = [r for r in q if r["date"] >= (last - _dt.timedelta(days=6)).isoformat()]
    if last7:
        net7 = sum(r["net_mah"] for r in last7) / len(last7)
        if net7 < 0:
            soc = soc_estimate(conn, cfg, now)
            have = soc["soc_mah"] if soc["soc_mah"] is not None else None
            if have is not None:
                out["projected_days_to_empty"] = round(have / -net7, 1)
    return out


def assessment_for_ratio(ratio: float) -> str:
    return "surplus" if ratio >= 2.0 else "marginal" if ratio >= 1.0 else "deficit"
