"""Scenario definitions (all times are offsets in days from the start)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Scenario:
    name: str = "december-30d"
    start_iso: str = "2026-12-03T05:00:00Z"  # 00:00 EST, Thursday 3 Dec 2026
    days: float = 30.0
    seed: int = 1
    # tide world
    surge_peak_day: float | None = 12.6
    surge_peak_m: float = 0.70
    surge_rise_sigma_h: float = 2.0
    surge_fall_sigma_h: float = 4.0
    weather_sigma_m: float = 0.025
    # faults and events
    repeater_outage: tuple[float, float] | None = (17.40, 6.0)  # (start day, hours)
    host_disconnect: tuple[float, float] | None = (7.30, 45.0)  # (start day, minutes)
    reboot_day: float | None = 20.55
    wake_burst_day: float | None = 9.60  # several boats in 30 min (14:24 local)
    noaa_outage: tuple[float, float] | None = (14.05, 18.0)  # (start day, hours) cache must cover
    cold_snap: tuple[float, float, float] | None = (21.0, 24.5, -9.0)  # (start day, end day, delta C)
    wakes_per_day: float = 4.0
    loads_per_day: float = 8.0
    # power
    target_psh: float = 3.45
    shading: float = 1.0
    initial_soc_pct: float = 80.0
    # calibration procedure
    mark_m: float = 2.60  # bulkhead reference mark above MLLW (unknown to the service)
    tape_sigma_m: float = 0.002
    level_check_sigma_deg: float = 0.05
    datum_tie_after_days: float = 4.0  # shakedown compressed (ARCHITECTURE: end of the 14-day shakedown)
    # API probing
    api_probe_s: int = 600
    extra: dict = field(default_factory=dict)


def default() -> Scenario:
    return Scenario()


def deficit() -> Scenario:
    """Heavily shaded panel plus a long cold spell: the verdict must say deficit."""
    return Scenario(name="shaded-deficit-21d", days=21.0, surge_peak_day=None, repeater_outage=None,
                    host_disconnect=None, reboot_day=None, wake_burst_day=None, noaa_outage=None,
                    cold_snap=(3.0, 19.0, -7.0), shading=0.02, initial_soc_pct=60.0, api_probe_s=3600)


def quick() -> Scenario:
    """Short smoke scenario for the test suite."""
    return Scenario(name="quick-8d", days=8.0, surge_peak_day=6.3, repeater_outage=(5.2, 6.0),
                    host_disconnect=(4.3, 45.0), reboot_day=5.9, wake_burst_day=4.6, noaa_outage=(6.8, 6.0),
                    cold_snap=None, datum_tie_after_days=3.0, api_probe_s=900)


SCENARIOS = {"default": default, "deficit": deficit, "quick": quick}
