"""The long-running service: one asyncio process (ARCHITECTURE 6.1, ADR-007).

A single writer (this event loop) owns the database connection; radio events
arrive on a queue; a 1-second scheduler drives Core.tick; uvicorn serves the
read-only API, which opens its own read-only connections. The API starts and
serves even when the radio is absent (gateway status 'error').
"""

from __future__ import annotations

import asyncio
import logging

from . import db as dbmod
from .api import create_app
from .core import Core
from .noaa import NoaaHttpProvider
from .notify import NotifyError, SmtpNotifier
from .radio import MeshcoreRadio
from .tempest import TempestHttpSource
from .timeutil import SystemClock

log = logging.getLogger("tidesvc")


async def run_service(cfg) -> None:
    import uvicorn

    clock = SystemClock()
    conn = dbmod.connect(cfg.storage.db_path)
    provider = NoaaHttpProvider(cfg.noaa.base_url, cfg.noaa.application, cfg.noaa.timeout_s)
    try:
        notifier = SmtpNotifier.from_secrets(cfg.secrets)
    except NotifyError as e:
        log.warning("email disabled: %s (alerts still visible via /api/v1/alerts)", e)
        notifier = None
    tsrc = (TempestHttpSource(cfg.tempest.station_id, cfg.secrets.tempest_token, cfg.tempest.base_url)
            if cfg.tempest.enabled else None)
    core = Core(conn, cfg, provider, notifier, tsrc, write_exports=True)
    queue: asyncio.Queue = asyncio.Queue()
    radio = MeshcoreRadio(cfg, queue, clock.now)

    async def consume():
        while True:
            ev = await queue.get()
            try:
                core.handle(ev)
            except Exception:  # noqa: BLE001 - never let one bad frame stop ingest
                log.exception("ingest failed for %r", ev)

    async def schedule():
        while True:
            try:
                core.tick(clock.now())
            except Exception:  # noqa: BLE001
                log.exception("scheduler tick failed")
            await asyncio.sleep(1.0)

    app = create_app(cfg, cfg.storage.db_path, clock)
    server = uvicorn.Server(uvicorn.Config(app, host=cfg.api.host, port=cfg.api.port, log_level="info"))
    await asyncio.gather(radio.run(), consume(), schedule(), server.serve())
