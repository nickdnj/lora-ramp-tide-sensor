"""Run simulated scenarios and write the report.

  python -m sim.run                        # default 30-day + shaded deficit, report to docs/SIM-REPORT.md
  python -m sim.run --scenario quick --report /tmp/r.md
  python -m sim.run --days 45 --seed 3 --no-plots
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .acceptance import checks
from .engine import run
from .metrics import all_metrics
from .report import plots, write_report
from .scenario import SCENARIOS


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m sim.run")
    ap.add_argument("--scenario", action="append", choices=sorted(SCENARIOS),
                    help="scenario(s) to run (default: default and deficit)")
    ap.add_argument("--days", type=float, help="override days for the scenario(s)")
    ap.add_argument("--seed", type=int, help="override the random seed")
    ap.add_argument("--report", default="docs/SIM-REPORT.md")
    ap.add_argument("--workdir", default="sim-out", help="databases and plots (git-ignored)")
    ap.add_argument("--no-plots", action="store_true")
    ap.add_argument("--sweep", type=int, default=0,
                    help="also run the default scenario with seeds 2..N and add a robustness table")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    names = args.scenario or ["default", "deficit"]
    Path(args.workdir).mkdir(parents=True, exist_ok=True)
    results = []
    plot_files: list[str] = []
    ok_all = True
    for name in names:
        sc = SCENARIOS[name]()
        if args.days:
            sc.days = args.days
        if args.seed is not None:
            sc.seed = args.seed
        print(f"running {sc.name}: {sc.days:g} days, seed {sc.seed} ...", flush=True)
        r = run(sc, workdir=args.workdir, verbose=args.verbose)
        m = all_metrics(r)
        for c in checks(m, sc):
            tag = "PASS" if c.passed else ("stretch not met" if c.stretch else "FAIL")
            print(f"  [{tag:>15}] {c.id:<9} {c.measured}")
            if not c.passed and not c.stretch:
                ok_all = False
        if not args.no_plots:
            plot_files += plots(r, m, Path(args.workdir))
        results.append((r, m))
        print(f"  wall {r.wall_s:.1f} s, db {r.db_path}")
    sweep = []
    for seed in range(2, args.sweep + 1):
        sc = SCENARIOS["default"]()
        sc.seed = seed
        print(f"sweep: default seed {seed} ...", flush=True)
        r = run(sc, workdir=args.workdir)
        m = all_metrics(r)
        cs = checks(m, sc)
        fails = [c.id for c in cs if not c.passed and not c.stretch]
        if fails:
            ok_all = False
        print(f"  required failures: {fails or 'none'}")
        sweep.append((seed, m, cs))
    write_report(results, Path(args.report), plot_files, sweep)
    print(f"report written to {args.report}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
