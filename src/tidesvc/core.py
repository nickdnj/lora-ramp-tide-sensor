"""The service core: wires ingest, derive, NOAA, energy, alerts, Tempest and the
schedule (ARCHITECTURE 6.2) behind two calls, ``handle(event)`` and
``tick(now)``. The asyncio service (tidesvc.service) and any offline driver
(tests, the simulator) use the same object, so the simulated world exercises
the real pipeline.
"""

from __future__ import annotations

import datetime as _dt
import logging
import sqlite3

from . import calibration as calmod
from . import energy as energymod
from . import export as exportmod
from .alerts import AlertEngine
from .derive import Deriver
from .ingest import Ingestor
from .noaa import NoaaService, PredictionProvider
from .notify import Notifier
from .tempest import TempestPoller, TempestSource
from .timeutil import LOCAL_TZ, local_date

log = logging.getLogger("tidesvc.core")


def _local(now: float) -> _dt.datetime:
    return _dt.datetime.fromtimestamp(now, LOCAL_TZ)


class Core:
    def __init__(self, conn: sqlite3.Connection, cfg, provider: PredictionProvider, notifier: Notifier | None,
                 tempest_source: TempestSource | None = None, write_exports: bool = False) -> None:
        self.conn = conn
        self.cfg = cfg
        self.deriver = Deriver(conn, cfg)
        self.ingestor = Ingestor(conn, cfg, self.deriver)
        self.noaa = NoaaService(conn, provider, cfg.noaa)
        self.alerts = AlertEngine(conn, cfg, notifier)
        self.tempest = TempestPoller(conn, cfg, tempest_source)
        self.write_exports = write_exports
        self._last_alert = None
        self._last_ref = None
        self._last_tempest = None
        self._noaa_day = None
        self._noaa_ok = False
        self._noaa_retry_at = 0.0
        self._rollup_day = None
        self._export_day = None
        self.refit_log: list[dict] = []

    # ------------------------------------------------------------------ events
    def handle(self, ev):
        return self.ingestor.handle(ev)

    # ------------------------------------------------------------------ schedule
    def tick(self, now: float) -> None:
        loc = _local(now)
        today = loc.date()
        # NOAA predictions: on start, daily at 00:30 local, hourly retry after a failure
        due_daily = (self._noaa_day != today and (loc.hour, loc.minute) >= (0, 30)) or self._noaa_day is None
        if due_daily or (not self._noaa_ok and now >= self._noaa_retry_at):
            self._noaa_ok = self.noaa.refresh_predictions(now)
            self._noaa_day = today
            self._noaa_retry_at = now + 3600
            self.deriver.invalidate()
        # Sandy Hook observed + 6-min predictions every 6 min
        if self._last_ref is None or now - self._last_ref >= 360:
            self.noaa.refresh_reference(now, hours=6.0 if self._last_ref is not None else 72.0)
            self._last_ref = now
        # Tempest (optional)
        if self._last_tempest is None or now - self._last_tempest >= self.cfg.tempest.poll_s:
            self.tempest.poll(now)
            self._last_tempest = now
        # energy rollup 00:05 local (previous days, idempotent)
        if self._rollup_day != today and (loc.hour, loc.minute) >= (0, 5):
            energymod.rollup_through(self.conn, self.cfg, now, days_back=3)
            self._rollup_day = today
            self.alerts.refresh_energy(now)
        # daily CSV export 00:15 local
        if self.write_exports and self._export_day != today and (loc.hour, loc.minute) >= (0, 15):
            exportmod.write_daily_csv(self.conn, today - _dt.timedelta(days=1), self.cfg.storage.export_dir)
            self._export_day = today
        # monthly refit, the 1st at 03:00 local
        row = self.conn.execute("SELECT value FROM meta WHERE key='last_refit_at'").fetchone()
        if row is None:  # first start: the first refit is the next 1st-of-month 03:00
            self.conn.execute("INSERT INTO meta(key, value) VALUES ('last_refit_at', ?)", (str(now),))
        elif calmod.is_refit_due(now, float(row[0])):
            res = calmod.monthly_refit(self.conn, self.cfg, self.deriver, now)
            res["at"] = now
            self.refit_log.append(res)
            log.info("monthly refit: %s", res)
            self.conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('last_refit_at', ?)", (str(now),))
        # alerts every 60 s
        if self._last_alert is None or now - self._last_alert >= self.cfg.alerts.eval_interval_s:
            self.alerts.evaluate(now)
            self._last_alert = now

    def local_date(self, now: float):
        return local_date(now)
