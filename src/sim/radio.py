"""Lossy MeshCore link and a fake companion radio source.

Each node frame may reach the gateway relayed by the repeater (path_len 1),
directly (path_len 0), both (a duplicate), or not at all. Outage windows take
the repeater down (no relays, no adverts, no direct copies at this geometry).
While the host link is down, the companion queues up to 16 frames (oldest
dropped) and drains them on reconnect: that is the ADR-012 backlog case.
Events come out as tidesvc.ingest events, so the real pipeline consumes them.
"""

from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass, field

import numpy as np

from tidesvc.ingest import AdvertEvent, ChannelFrame, LinkEvent

from .node import TxPacket

OFFLINE_QUEUE = 16


@dataclass
class LinkStats:
    tx: int = 0
    delivered_unique: int = 0
    copies_delivered: int = 0
    duplicates: int = 0
    lost: int = 0
    lost_in_outage: int = 0
    queued: int = 0
    queue_dropped: int = 0
    corrupted: int = 0
    foreign: int = 0
    intact_keys: set = field(default_factory=set)  # (boot_count, seq) delivered with a good CRC


@dataclass
class SimRadio:
    rng: np.random.Generator = field(default_factory=lambda: np.random.default_rng(9))
    p_relay: float = 0.975
    p_direct: float = 0.25
    p_corrupt: float = 0.002
    repeater_outages: list[tuple[float, float]] = field(default_factory=list)
    host_disconnects: list[tuple[float, float]] = field(default_factory=list)
    advert_every_s: float = 7200.0
    heartbeat_s: float = 60.0
    channel_idx: int = 1
    data_type: int = 0xFF54
    stats: LinkStats = field(default_factory=LinkStats)
    _heap: list = field(default_factory=list)
    _ctr: itertools.count = field(default_factory=itertools.count)
    _queue: list = field(default_factory=list)
    _host_up: bool = True

    def _push(self, t: float, ev) -> None:
        heapq.heappush(self._heap, (t, next(self._ctr), ev))

    def repeater_up(self, t: float) -> bool:
        return not any(a <= t < b for a, b in self.repeater_outages)

    def host_up(self, t: float) -> bool:
        return not any(a <= t < b for a, b in self.host_disconnects)

    def schedule_background(self, t0: float, t1: float) -> None:
        """Adverts, heartbeats and host link transitions for the whole run."""
        t = t0 + 600
        while t < t1:
            if self.repeater_up(t):
                self._push(t, ("advert", t))
            t += self.advert_every_s
        t = t0
        while t < t1:
            if self.host_up(t):
                self._push(t, ("heartbeat", t))
            t += self.heartbeat_s
        for a, b in self.host_disconnects:
            self._push(a, ("host_down", a))
            self._push(b, ("host_up", b))
        # occasional public-channel traffic that the filter must ignore
        t = t0 + 3000
        while t < t1:
            self._push(t, ("foreign", t))
            t += float(self.rng.uniform(4, 12)) * 3600

    def transmit(self, pkt: TxPacket) -> None:
        self.stats.tx += 1
        copies = []
        up = self.repeater_up(pkt.t_tx)
        if up and self.rng.uniform() < self.p_relay:
            copies.append((pkt.t_tx + float(self.rng.uniform(0.4, 1.2)), 1, float(self.rng.normal(6.5, 1.5))))
        if up and self.rng.uniform() < self.p_direct:
            copies.append((pkt.t_tx + 0.25, 0, float(self.rng.normal(-6.0, 1.5))))
        if not copies:
            self.stats.lost += 1
            if not up:
                self.stats.lost_in_outage += 1
            return
        self.stats.delivered_unique += 1
        self.stats.copies_delivered += len(copies)
        self.stats.duplicates += len(copies) - 1
        for t, path_len, snr in copies:
            data = pkt.payload
            if self.rng.uniform() < self.p_corrupt:
                b = bytearray(data)
                b[int(self.rng.integers(0, 24))] ^= 1 << int(self.rng.integers(0, 8))
                data = bytes(b)
                self.stats.corrupted += 1
            else:
                self.stats.intact_keys.add((pkt.boot_count, pkt.seq))
            self._push(t, ("frame", ChannelFrame(t, self.channel_idx, self.data_type, data, round(snr * 4) / 4,
                                                 path_len)))

    def pop_until(self, t_now: float):
        """Yield ingest events with time <= t_now, applying the host-link queue."""
        while self._heap and self._heap[0][0] <= t_now:
            t, _, (kind, ev) = heapq.heappop(self._heap)
            if kind == "frame":
                if self._host_up:
                    yield ev
                else:
                    self.stats.queued += 1
                    self._queue.append(ev)
                    if len(self._queue) > OFFLINE_QUEUE:
                        self._queue.pop(0)
                        self.stats.queue_dropped += 1
            elif kind == "advert":
                if self._host_up:
                    yield AdvertEvent(t, "a1b2c3", "nick-pvc-repeater", 5.0)
            elif kind == "heartbeat":
                if self._host_up:
                    yield LinkEvent(t, "ok", "heartbeat")
            elif kind == "host_down":
                self._host_up = False
                yield LinkEvent(t, "error", "serial link lost (simulated USB unplug)")
            elif kind == "host_up":
                self._host_up = True
                yield LinkEvent(t, "ok", "reconnected")
                for k, q in enumerate(self._queue):
                    # the host stamps arrival time as the queue drains
                    yield ChannelFrame(t + 0.15 * (k + 1), q.channel_idx, q.data_type, q.payload, q.snr_db,
                                       q.path_len)
                self._queue.clear()
            elif kind == "foreign":
                if self._host_up:
                    self.stats.foreign += 1
                    yield ChannelFrame(t, 0, 0x0001, b"public channel chatter", 3.0, 2)
