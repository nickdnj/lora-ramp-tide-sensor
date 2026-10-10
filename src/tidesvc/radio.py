"""Gateway radio adapter: MeshCore companion (USB serial or TCP) via meshcore_py
(ARCHITECTURE 5.1-5.2; ADR-002; E5.3).

UNVERIFIED: this adapter has not been run against meshcore_py 2.3.15 or a real
companion. The library calls follow ARCHITECTURE 2.2/5.2 (create_serial /
create_tcp, start_auto_message_fetching, EventType.CHANNEL_DATA_RECV), but the
event payload key names below are assumptions to confirm in spike S1 / story
E5.3. Everything downstream of ``ChannelFrame`` is tested offline.

The adapter converts library events into tidesvc.ingest events and pushes them
onto an asyncio queue; it never touches the database itself (single writer).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

from .ingest import AdvertEvent, ChannelFrame, LinkEvent

log = logging.getLogger("tidesvc.radio")


def _get(d, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and k in d:
            return d[k]
        if hasattr(d, k):
            return getattr(d, k)
    return default


def frame_from_event_payload(payload, rx_at: float) -> ChannelFrame:
    """Map a CHANNEL_DATA_RECV payload to a ChannelFrame. Key names UNVERIFIED."""
    raw = _get(payload, "payload", "data", default=b"")
    data = bytes.fromhex(raw) if isinstance(raw, str) else bytes(raw)
    snr = _get(payload, "SNR", "snr")
    return ChannelFrame(
        rx_at=rx_at,
        channel_idx=int(_get(payload, "channel_idx", "chan", default=-1)),
        data_type=int(_get(payload, "data_type", "type", default=-1)),
        payload=data,
        snr_db=float(snr) if snr is not None else None,
        path_len=int(_get(payload, "path_len", default=0) or 0),
    )


class MeshcoreRadio:
    def __init__(self, cfg, queue: asyncio.Queue, now: Callable[[], float]) -> None:
        self.cfg = cfg
        self.queue = queue
        self.now = now
        self._mc = None

    async def run(self) -> None:
        """Connect, subscribe, heartbeat; reconnect with 1 s -> 60 s backoff. Never raises."""
        backoff = 1.0
        while True:
            try:
                await self._connect_and_serve()
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - any link failure means 'error' and retry
                await self.queue.put(LinkEvent(self.now(), "error", f"{e.__class__.__name__}: {e}"))
                log.warning("gateway link error: %s (retry in %.0f s)", e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(60.0, backoff * 2)

    async def _connect_and_serve(self) -> None:
        try:
            from meshcore import EventType, MeshCore  # type: ignore
        except ImportError as e:
            raise RuntimeError("meshcore library not installed (pip install '.[radio]')") from e
        rc = self.cfg.radio
        if rc.transport == "tcp":
            mc = await MeshCore.create_tcp(rc.host, rc.tcp_port)
        else:
            mc = await MeshCore.create_serial(rc.port, 115200)
        self._mc = mc
        await self.queue.put(LinkEvent(self.now(), "ok", "connected"))

        async def on_channel_data(event):
            await self.queue.put(frame_from_event_payload(event.payload, self.now()))

        mc.subscribe(EventType.CHANNEL_DATA_RECV, on_channel_data)
        advert_type = getattr(EventType, "ADVERTISEMENT", None)  # UNVERIFIED event name
        if advert_type is not None:
            async def on_advert(event):
                p = event.payload
                await self.queue.put(AdvertEvent(self.now(), str(_get(p, "public_key", "pubkey", default="")),
                                                 str(_get(p, "adv_name", "name", default=""))))
            mc.subscribe(advert_type, on_advert)
        await mc.start_auto_message_fetching()
        while True:  # heartbeat: a cheap companion command every heartbeat_s
            await asyncio.sleep(rc.heartbeat_s)
            res = await mc.commands.get_bat()  # UNVERIFIED command name
            if getattr(res, "type", None) == getattr(EventType, "ERROR", object()):
                raise RuntimeError("companion did not answer heartbeat")
            await self.queue.put(LinkEvent(self.now(), "ok", "heartbeat"))
