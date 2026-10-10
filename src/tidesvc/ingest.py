"""Ingest: radio events -> packets_raw -> readings -> derived (ARCHITECTURE 5.2,
6.2, 6.3; E5.2, E5.3, E5.9).

Every frame is stored raw first, even if it fails to parse. Then: filter on
channel and data type, decode v1 + CRC, de-duplicate on
(node_id, boot_count, seq), stamp time (host receive time; backlog drains are
back-dated from seq and marked ``backfilled``, ADR-012), store the reading, and
derive. Relayed frames (path_len >= 1) and repeater adverts are recorded as
repeater evidence (ARCHITECTURE 5.5).

The radio side is abstracted as events so the real meshcore adapter
(tidesvc.radio) and any fake source (tests, simulator) feed the same code.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from . import codec
from . import db as dbmod
from .derive import BACKFILLED, LIVE, Deriver


@dataclass(frozen=True)
class ChannelFrame:
    """A 0x1B CHANNEL_DATA_RECV frame as delivered by the companion."""

    rx_at: float
    channel_idx: int
    data_type: int
    payload: bytes
    snr_db: float | None = None
    path_len: int = 0


@dataclass(frozen=True)
class AdvertEvent:
    rx_at: float
    pubkey_prefix: str
    name: str = ""
    snr_db: float | None = None


@dataclass(frozen=True)
class RepeaterStatusEvent:
    rx_at: float
    batt_mv: int | None
    detail: str = ""


@dataclass(frozen=True)
class LinkEvent:
    """Gateway (companion) link state: 'ok' on connect/heartbeat, 'error' on failure."""

    t: float
    status: str
    detail: str = ""


@dataclass
class IngestResult:
    packet_id: int
    status: str
    reading_id: int | None = None
    backfilled_ids: list[int] = field(default_factory=list)


def _seq_diff(new: int, old: int) -> int:
    """Forward distance new - old modulo 2^16 (0..65535)."""
    return (new - old) & 0xFFFF


class Ingestor:
    def __init__(self, conn: sqlite3.Connection, cfg, deriver: Deriver) -> None:
        self.conn = conn
        self.cfg = cfg
        self.deriver = deriver
        # backlog group: node_id -> list of (reading_id, seq, rx_at)
        self._group: dict[int, list[tuple[int, int, float]]] = {}

    # ------------------------------------------------------------------ dispatch
    def handle(self, ev) -> IngestResult | None:
        if isinstance(ev, ChannelFrame):
            return self.handle_frame(ev)
        if isinstance(ev, AdvertEvent):
            self.handle_advert(ev)
        elif isinstance(ev, RepeaterStatusEvent):
            self.handle_repeater_status(ev)
        elif isinstance(ev, LinkEvent):
            self.handle_link(ev)
        else:
            raise TypeError(f"unknown event {ev!r}")
        return None

    # ------------------------------------------------------------------ frames
    def handle_frame(self, fr: ChannelFrame) -> IngestResult:
        rc = self.cfg.radio
        cur = self.conn.execute(
            "INSERT INTO packets_raw(rx_at, time_source, channel_idx, data_type, snr_db, path_len, payload, "
            "parse_status) VALUES (?,?,?,?,?,?,?,?)",
            (fr.rx_at, LIVE, fr.channel_idx, fr.data_type, fr.snr_db, fr.path_len, bytes(fr.payload), "pending"))
        pid = int(cur.lastrowid)

        def done(status: str, detail: str | None = None, rid: int | None = None) -> IngestResult:
            self.conn.execute("UPDATE packets_raw SET parse_status=?, detail=? WHERE id=?", (status, detail, pid))
            return IngestResult(packet_id=pid, status=status, reading_id=rid)

        if fr.channel_idx != rc.channel_idx:
            return done("wrong_channel")
        if fr.data_type != rc.data_type:
            return done("wrong_data_type")
        try:
            p = codec.decode(fr.payload)
        except codec.DecodeError as e:
            return done(e.status, str(e))

        if fr.path_len >= 1:
            self._repeater_evidence(fr.rx_at, "relayed_frame", fr.snr_db)

        dup = self.conn.execute(
            "SELECT id FROM readings WHERE node_id=? AND boot_count=? AND seq=? AND rx_at >= ? LIMIT 1",
            (p.node_id, p.boot_count, p.seq, fr.rx_at - self.cfg.node.dedup_window_s)).fetchone()
        if dup is not None:
            return done("duplicate", f"duplicate of reading {dup[0]}")

        sensor_ok = not (p.flags & (codec.F_SENSOR_SKIPPED | codec.F_SENSOR_ERROR))
        ina_ok = not (p.flags & codec.F_INA_ERROR)
        cur = self.conn.execute(
            "INSERT INTO readings(packet_id, node_id, boot_count, seq, t, rx_at, time_source, pitch_deg, "
            "pitch_sd_deg, roll_deg, temp_c, vbat_mv, vpanel_mv, ipanel_ma, chg_bits, awake_ms_prev, flags, "
            "path_len, snr_db) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, p.node_id, p.boot_count, p.seq, fr.rx_at, fr.rx_at, LIVE,
             p.pitch_deg if sensor_ok else None, p.pitch_sd_deg if sensor_ok else None,
             p.roll_deg if sensor_ok else None, p.temp_c if not (p.flags & codec.F_SENSOR_ERROR) else None,
             p.vbat if ina_ok else None, p.vpanel if ina_ok else None, p.ipanel_ma if ina_ok else None,
             p.chg, p.awake_ms_prev, p.flags, fr.path_len, fr.snr_db))
        rid = int(cur.lastrowid)
        res = done("ok", None, rid)
        res.backfilled_ids = self._backlog(p, rid, fr.rx_at)
        for b in res.backfilled_ids:
            self.deriver.process(b)
        self.deriver.process(rid)
        return res

    def _backlog(self, p: codec.PayloadV1, rid: int, rx_at: float) -> list[int]:
        """Detect a companion queue drain and back-date the older frames (ADR-012)."""
        win = self.cfg.radio.backlog_window_s
        grp = self._group.get(p.node_id, [])
        if grp:
            last_rid, last_seq, last_rx = grp[-1]
            last_boot = self.conn.execute("SELECT boot_count FROM readings WHERE id=?", (last_rid,)).fetchone()
            same_boot = last_boot is not None and last_boot[0] == p.boot_count
            d = _seq_diff(p.seq, last_seq)
            if rx_at - last_rx <= win and same_boot and 0 < d < 0x8000:
                grp.append((rid, p.seq, rx_at))
            else:
                grp = [(rid, p.seq, rx_at)]
        else:
            grp = [(rid, p.seq, rx_at)]
        self._group[p.node_id] = grp
        if len(grp) < 2:
            return []
        newest_rid, newest_seq, newest_rx = grp[-1]
        interval = self.cfg.node.interval_s
        out = []
        for g_rid, g_seq, _ in grp[:-1]:
            t = newest_rx - _seq_diff(newest_seq, g_seq) * interval
            self.conn.execute("UPDATE readings SET t=?, time_source=? WHERE id=?", (t, BACKFILLED, g_rid))
            self.conn.execute(
                "UPDATE packets_raw SET time_source=? WHERE id=(SELECT packet_id FROM readings WHERE id=?)",
                (BACKFILLED, g_rid))
            out.append(g_rid)
        return out

    # ------------------------------------------------------------------ repeater / gateway
    def _repeater_evidence(self, t: float, source: str, snr_db: float | None = None,
                           batt_mv: int | None = None, detail: str = "") -> None:
        st = dbmod.get_component(self.conn, "repeater_evidence")
        d = st["detail"] if st else {}
        key = {"relayed_frame": "last_relayed_frame_at", "advert": "last_advert_at", "status": "last_status_at"}[source]
        d[key] = max(t, d.get(key) or 0)
        if batt_mv is not None:
            d["batt_mv"] = batt_mv
        dbmod.set_component(self.conn, "repeater_evidence", "seen", t, d)
        if source != "relayed_frame":
            self.conn.execute("INSERT INTO repeater_events(t, source, detail, snr_db, batt_mv) VALUES (?,?,?,?,?)",
                              (t, source, detail, snr_db, batt_mv))

    def handle_advert(self, ev: AdvertEvent) -> None:
        prefix = self.cfg.repeater.pubkey_prefix
        if prefix and not ev.pubkey_prefix.lower().startswith(prefix.lower()):
            return
        self._repeater_evidence(ev.rx_at, "advert", ev.snr_db, detail=json.dumps({"name": ev.name}))

    def handle_repeater_status(self, ev: RepeaterStatusEvent) -> None:
        self._repeater_evidence(ev.rx_at, "status", None, ev.batt_mv, ev.detail)

    def handle_link(self, ev: LinkEvent) -> None:
        prev = dbmod.get_component(self.conn, "gateway")
        if prev is None or prev["status"] != ev.status:
            self.conn.execute("INSERT INTO gateway_events(t, event, detail) VALUES (?,?,?)",
                              (ev.t, ev.status, ev.detail))
        detail = {"message": ev.detail}
        if ev.status == "ok":
            detail["connected_since"] = (prev["since"] if prev and prev["status"] == "ok" else ev.t)
        dbmod.set_component(self.conn, "gateway", ev.status, ev.t, detail)
