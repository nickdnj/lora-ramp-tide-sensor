"""Sensor-node model: wake, read power, charger control, battery state, burst
sample, build a v1 payload, transmit, sleep. Uses sim.fwlogic, the Python
mirror of the C++ portable core, so the firmware rules are the same ones the
host tests check.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from tidesvc import codec

from . import fwlogic as fw
from .power import PowerSystem
from .ramp import Inclinometer, Ramp
from .world import TideWorld

AWAKE_SAMPLING_MA = 25.0  # instantaneous load while the INA3221 is read


@dataclass
class TxPacket:
    t_tx: float
    payload: bytes
    seq: int
    boot_count: int
    truth_water_m: float  # water level at the burst midpoint (for analysis only)


@dataclass
class NodeModel:
    world: TideWorld
    ramp: Ramp
    sensor: Inclinometer
    power: PowerSystem
    node_id: int = 1
    i_sleep_ma: float = 0.055  # true sleep current (config assumes 50 uA)
    awake_mas: float = 128.0  # true charge per normal cycle (config assumes 125)
    clock_drift: float = 0.012  # RC oscillator: +1.2% slow (within +/-5%)
    rng: np.random.Generator = field(default_factory=lambda: np.random.default_rng(5))
    seq: int = 0
    boot_count: int = 7
    batt_state: int = fw.NORMAL
    charger: fw.ChargerState = field(default_factory=fw.ChargerState)
    awake_ms_prev: int = 0
    reboot_pending: bool = True  # first frame after power-up carries the reboot flag
    reset_flags: int = 0
    next_wake: float = 0.0
    last_wake: float | None = None

    def reboot(self, t: float, reason_flag: int = codec.F_WDT_RESET) -> None:
        """Reset: RTC memory lost (seq, charger state), boot_count from NVS + 1."""
        self.boot_count = (self.boot_count + 1) & 0xFF
        self.seq = 0
        self.charger = fw.ChargerState()
        self.power.ce_disabled = True  # pull-up holds charging off until firmware runs
        self.awake_ms_prev = 0
        self.reboot_pending = True
        self.reset_flags = reason_flag
        self.next_wake = t + 2.0
        self.last_wake = None

    def cycle(self, t: float) -> TxPacket:
        """Run one wake cycle starting at t; returns the transmitted packet."""
        dt_since = int(round(t - self.last_wake)) if self.last_wake is not None else 0
        self.last_wake = t
        p = self.power
        vbat, vpanel, ipanel = p.measure(t, AWAKE_SAMPLING_MA, self.rng)
        s1, s2 = p.stat_pins(t)
        die_c = p.cell_temp() + 0.3
        r = fw.charger_step(self.charger, round(die_c, 1), s1, s2, dt_since, vpanel >= fw.VIN_PRESENT_MV)
        self.charger = r.state
        p.ce_disabled = r.ce_disabled
        if r.pulse:
            p.ce_pulse()
        self.batt_state = fw.next_batt_state(self.batt_state, vbat)
        flags = fw.batt_flags(self.batt_state)
        if self.reboot_pending:
            flags |= codec.F_REBOOT | self.reset_flags
        pitch_q = sd_q = roll_q = 0
        t_mid = t + 1.9
        if self.batt_state != fw.CRITICAL:
            ts = t + 0.45 + np.arange(fw.BURST_SAMPLES) / 100.0
            water = self.world.water(ts)
            ang = self.ramp.angle_deg(self.ramp.float_level(water, ts))
            pitch, roll = self.sensor.read(ang, die_c)
            st = fw.burst_stats(pitch.tolist(), roll.tolist())
            flags |= fw.sample_flags(st, len(pitch))
            pitch_q, sd_q, roll_q = codec.q_pitch(st.pitch_median), codec.q_pitch_sd(st.pitch_sd), codec.q_roll(st.roll_mean)
            awake_s = 3.9 + self.rng.normal(0, 0.05)
        else:
            awake_s = 0.9
        pl = codec.PayloadV1(
            node_id=self.node_id, seq=self.seq, boot_count=self.boot_count, pitch_med=pitch_q, pitch_sd=sd_q,
            roll_mean=roll_q, temp=codec.q_temp(die_c), vbat=codec.q_u16(vbat), vpanel=codec.q_u16(vpanel),
            ipanel=codec.q_ipanel(ipanel), chg=r.chg, awake_ms_prev=codec.q_u16(self.awake_ms_prev), flags=flags)
        pkt = TxPacket(t_tx=t + awake_s - 0.2, payload=codec.encode(pl), seq=self.seq, boot_count=self.boot_count,
                       truth_water_m=float(self.world.water(t_mid)))
        self.seq = (self.seq + 1) & 0xFFFF
        self.reboot_pending = False
        self.reset_flags = 0
        self.awake_ms_prev = int(round(awake_s * 1000))
        interval = fw.INTERVAL_S[self.batt_state] * (1 + self.clock_drift)
        self.next_wake = t + interval
        return pkt

    def awake_charge_mas(self) -> float:
        return self.awake_mas if self.batt_state != fw.CRITICAL else 25.0
