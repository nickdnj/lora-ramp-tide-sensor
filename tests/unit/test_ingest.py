"""SV-D2..D6, repeater evidence (E5.9), gateway link events."""

import pytest

from conftest import T0, frame, payload
from tidesvc import codec
from tidesvc.core import Core
from tidesvc.health import gateway_status, repeater_status
from tidesvc.ingest import AdvertEvent, ChannelFrame, LinkEvent
from tidesvc.notify import RecordingNotifier
from test_derive_noaa import insert_cal


@pytest.fixture
def core(conn, cfg, provider):
    c = Core(conn, cfg, provider, RecordingNotifier())
    insert_cal(conn)
    c.deriver.invalidate()
    c.tick(T0)
    return c


def raw_status(conn):
    return [r[0] for r in conn.execute("SELECT parse_status FROM packets_raw ORDER BY id")]


def test_bad_frames_stored_raw_never_readings(core, conn):
    good = payload(1, -3.0)
    bad_crc = bytearray(good)
    bad_crc[6] ^= 4
    v2 = bytearray(good)
    v2[0] = 2
    body = bytes(v2[:24])
    v2 = body + codec.crc16_ccitt_false(body).to_bytes(2, "little")
    cases = [frame(T0, bytes(bad_crc)), frame(T0 + 1, v2), frame(T0 + 2, good, channel=0),
             frame(T0 + 3, good, data_type=0xFF55), frame(T0 + 4, good[:25]), frame(T0 + 5, good + b"\0")]
    for f in cases:
        core.handle(f)
    assert raw_status(conn) == ["bad_crc", "bad_version", "wrong_channel", "wrong_data_type", "bad_length",
                                "bad_length"]
    assert conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM packets_raw WHERE payload IS NOT NULL").fetchone()[0] == 6


def test_dedup_direct_and_relayed_copy(core, conn):
    data = payload(42, -3.0)
    a = core.handle(frame(T0, data, path_len=0))
    b = core.handle(frame(T0 + 1.2, data, path_len=1))
    assert a.status == "ok" and b.status == "duplicate"
    assert conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0] == 1
    # the relayed copy still counts as repeater evidence
    assert repeater_status(conn, core.cfg, T0 + 2)["status"] == "ok"


def test_seq_wrap_and_reboot_not_backlog(core, conn):
    t = T0
    for seq in (65534, 65535, 0, 1):
        core.handle(frame(t, payload(seq, -3.0, boot=3)))
        t += 300
    # reboot: boot_count 4, seq restarts at 0, reboot flag
    r = core.handle(frame(t, payload(0, -3.0, boot=4, flags=codec.F_REBOOT)))
    assert r.status == "ok" and not r.backfilled_ids
    rows = conn.execute("SELECT boot_count, seq, time_source FROM readings ORDER BY t").fetchall()
    assert [tuple(x) for x in rows] == [(3, 65534, "rx"), (3, 65535, "rx"), (3, 0, "rx"), (3, 1, "rx"),
                                        (4, 0, "rx")]


def test_backlog_drain_backfilled(core, conn):
    # 40-min gateway outage: 8 frames queued in the companion, drained in < 2 s at reconnect
    t_rc = T0 + 3600
    ids = []
    for k, seq in enumerate(range(100, 108)):
        ids.append(core.handle(frame(t_rc + 0.2 * k, payload(seq, -3.0))).reading_id)
    rows = conn.execute("SELECT seq, t, time_source FROM readings ORDER BY seq").fetchall()
    newest = rows[-1]
    assert newest["time_source"] == "rx" and newest["t"] == pytest.approx(t_rc + 1.4)
    for r in rows[:-1]:
        assert r["time_source"] == "backfilled"
        assert r["t"] == pytest.approx(newest["t"] - (107 - r["seq"]) * 300)
    live = conn.execute("SELECT COUNT(*) FROM derived WHERE live=1").fetchone()[0]
    assert live == 1  # backfilled readings excluded from the live view but kept
    assert conn.execute("SELECT COUNT(*) FROM derived").fetchone()[0] == 8


def test_normal_cadence_is_not_backlog(core, conn):
    for i in range(5):
        core.handle(frame(T0 + 300 * i, payload(i, -3.0)))
    assert {r[0] for r in conn.execute("SELECT time_source FROM readings")} == {"rx"}


def test_repeater_adverts_and_gateway_link(core, conn, cfg):
    cfg.repeater.pubkey_prefix = "ab12"
    core.handle(AdvertEvent(T0, "ffff00", "other"))
    assert repeater_status(conn, cfg, T0)["status"] == "unknown"
    core.handle(AdvertEvent(T0, "AB12cd", "nick-rep"))
    assert repeater_status(conn, cfg, T0 + 100)["status"] == "ok"
    assert repeater_status(conn, cfg, T0 + cfg.repeater.silent_after_s + 1)["status"] == "silent"
    core.handle(LinkEvent(T0, "ok", "connected"))
    core.handle(LinkEvent(T0 + 60, "ok", "heartbeat"))
    core.handle(LinkEvent(T0 + 120, "error", "serial gone"))
    g = gateway_status(conn, T0 + 130)
    assert g["status"] == "error" and g["since"] == T0 + 120
    assert [r[0] for r in conn.execute("SELECT event FROM gateway_events ORDER BY t")] == ["ok", "error"]


def test_unparseable_payload_still_raw_first(core, conn):
    core.handle(ChannelFrame(T0, 1, 0xFF54, b"\x01\x02", None, 0))
    assert raw_status(conn) == ["bad_length"]
