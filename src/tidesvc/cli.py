"""tidesvc command line. All writes (calibration, approvals, reprocess) are
CLI-only (ARCHITECTURE 7).

  python -m tidesvc serve --config config.toml [--env .env]
  python -m tidesvc cal add-obs --kind tape --freeboard 1.234 --at 2026-12-03T14:05Z [--pitch -3.21]
  python -m tidesvc cal add-obs --kind level_check --angle -2.10 --at ...
  python -m tidesvc cal fit-install
  python -m tidesvc cal datum-tie --from 2026-12-03 --to 2026-12-17
  python -m tidesvc cal refit | approve <id> | reject <id> | show
  python -m tidesvc reprocess --from 2026-12-03T00:00Z
  python -m tidesvc export --date 2026-12-05
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import json
import logging
import sys
import time

from . import calibration as calmod
from . import db as dbmod
from . import export as exportmod
from .config import load_config
from .derive import Deriver
from .timeutil import iso, parse_iso


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tidesvc")
    ap.add_argument("--config", default=None)
    ap.add_argument("--env", default=None, help=".env file with secrets")
    ap.add_argument("--db", default=None, help="override storage.db_path")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve")
    cal = sub.add_parser("cal")
    csub = cal.add_subparsers(dest="cal_cmd", required=True)
    ao = csub.add_parser("add-obs")
    ao.add_argument("--kind", choices=["tape", "level_check"], required=True)
    ao.add_argument("--at", required=True)
    ao.add_argument("--freeboard", type=float)
    ao.add_argument("--angle", type=float)
    ao.add_argument("--pitch", type=float, help="node pitch; default: median of packets around --at")
    ao.add_argument("--note", default="")
    csub.add_parser("fit-install")
    dt = csub.add_parser("datum-tie")
    dt.add_argument("--from", dest="t0", required=True)
    dt.add_argument("--to", dest="t1", required=True)
    csub.add_parser("refit")
    for name in ("approve", "reject"):
        p = csub.add_parser(name)
        p.add_argument("id", type=int)
    csub.add_parser("show")
    rp = sub.add_parser("reprocess")
    rp.add_argument("--from", dest="t0", required=True)
    ex = sub.add_parser("export")
    ex.add_argument("--date", required=True)
    args = ap.parse_args(argv)

    cfg = load_config(args.config, dotenv=args.env)
    if args.db:
        cfg.storage.db_path = args.db
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    if args.cmd == "serve":
        from .service import run_service
        asyncio.run(run_service(cfg))
        return 0
    conn = dbmod.connect(cfg.storage.db_path)
    now = time.time()
    deriver = Deriver(conn, cfg)
    if args.cmd == "cal":
        c = args.cal_cmd
        if c == "add-obs":
            oid = calmod.add_observation(conn, parse_iso(args.at), args.kind, freeboard_m=args.freeboard,
                                         angle_deg=args.angle, pitch_deg=args.pitch, note=args.note)
            print(f"observation {oid} stored")
        elif c == "fit-install":
            cid = calmod.fit_install(conn, cfg, now)
            row = conn.execute("SELECT * FROM calibrations WHERE id=?", (cid,)).fetchone()
            print(json.dumps(dict(row), indent=1))
            deriver.reprocess(row["valid_from"])
        elif c == "datum-tie":
            print(json.dumps(calmod.datum_tie(conn, cfg, deriver, now, parse_iso(args.t0), parse_iso(args.t1)),
                             indent=1, default=str))
        elif c == "refit":
            print(json.dumps(calmod.monthly_refit(conn, cfg, deriver, now), indent=1))
        elif c == "approve":
            calmod.approve(conn, args.id, deriver)
            print(f"calibration {args.id} approved; run reprocess if needed")
        elif c == "reject":
            calmod.reject(conn, args.id)
            print(f"calibration {args.id} rejected")
        elif c == "show":
            for r in conn.execute("SELECT id, valid_from, method, status, datum, theta0_deg, h0_m, l_eff_m "
                                  "FROM calibrations ORDER BY id"):
                d = dict(r)
                d["valid_from"] = iso(d["valid_from"])
                print(json.dumps(d))
    elif args.cmd == "reprocess":
        n = deriver.reprocess(parse_iso(args.t0))
        print(f"reprocessed {n} readings")
    elif args.cmd == "export":
        p = exportmod.write_daily_csv(conn, _dt.date.fromisoformat(args.date), cfg.storage.export_dir)
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
