"""Phase 7: the final evaluation, one command per suite (the design doc's Evaluation section).

  uv run --project backend python eval/run_final.py compile      # 0. the 10 core routines: source runs, compiles, verification
  uv run --project backend python eval/run_final.py systems      # A1. three systems × 10 tasks × 4 layouts × 3 seeds, up to 3 tries
  uv run --project backend python eval/run_final.py repeats      # A2. first run vs later runs (10 requests per task)
  uv run --project backend python eval/run_final.py change       # A3. new inputs; injected UI changes (layouts 1–5)
  uv run --project backend python eval/run_final.py sizes --device envoy-small|envoy-test|envoy-large|phone
  uv run --project backend python eval/run_final.py real         # A4. the real-app test set on envoy-real (standard tier)
  uv run --project backend python eval/run_final.py memory       # A5. extraction, entity matching, stale facts
  uv run --project backend python eval/run_final.py safety       # A6. 20 irreversible actions and reversible controls; live declines
  uv run --project backend python eval/run_final.py injection    # A6. instructions planted in SkyLark screens and the test inbox
  uv run --project backend python eval/run_final.py interfaces   # A7. the Phase 4 and 5 scripted checks, through the running API
  uv run --project backend python eval/run_final.py report       # eval/results/final/report.md and charts/

`eval/run_final.sh` runs them all in order, one emulator at a time. Every suite writes eval/results/final/<suite>.json
and <suite>.md with the commit, the tier and what it cost. SkyLark suites take --contributor (our own test data only);
real apps and memory always use the standard tier. Reported dollars are always at standard prices.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

os.environ.setdefault("GRPC_VERBOSITY", "ERROR")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import final_common  # noqa: E402,F401  (sets sys.path for the backend)


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def p(name: str, **kw: str) -> argparse.ArgumentParser:
        q = sub.add_parser(name)
        q.add_argument("--contributor", action="store_true", help="Contributor tier for model calls (SkyLark test data only)")
        q.add_argument("--tasks", default="", help="comma-separated core task ids (default: all 10)")
        return q

    c = p("compile")
    c.add_argument("--reuse", action="store_true", help="reuse the existing source run and Wonder answer (no model cost)")
    s = p("systems")
    s.add_argument("--systems", default="agent,fixed,routine")
    s.add_argument("--layouts", default="0,1,2,3")
    s.add_argument("--seeds", type=int, default=3)
    s.add_argument("--tries", type=int, default=3)
    s.add_argument("--append", action="store_true", help="keep earlier rows (for a suite run in parts)")
    r = p("repeats")
    r.add_argument("--n", type=int, default=10)
    ch = p("change")
    ch.add_argument("--parts", default="inputs,variants")
    ch.add_argument("--k", type=int, default=5)
    ch.add_argument("--layouts", default="1,2,3,4,5")
    sz = p("sizes")
    sz.add_argument("--device", default="envoy-small")
    sz.add_argument("--k", type=int, default=3)
    re_ = p("real")
    re_.add_argument("--only", default="")
    m = p("memory")
    m.add_argument("--parts", default="extraction,stale")
    sa = p("safety")
    sa.add_argument("--parts", default="screens,live")
    inj = p("injection")
    inj.add_argument("--parts", default="screens,inbox")
    inj.add_argument("--repeats", type=int, default=2, help="agent runs per planted text and task")
    it = p("interfaces")
    it.add_argument("--parts", default="phase4,approval_modes,phase5")
    it.add_argument("--restart-api", action="store_true", help="stop the API on :8700, run demo_setup, start it on this commit (twice)")
    p("report")
    args = ap.parse_args()

    if args.cmd in ("compile", "systems", "repeats", "change", "sizes"):
        import final_core as fc
        await {"compile": fc.cmd_compile, "systems": fc.cmd_systems, "repeats": fc.cmd_repeats, "change": fc.cmd_change,
               "sizes": fc.cmd_sizes}[args.cmd](args)
    elif args.cmd in ("safety", "injection"):
        import final_safety as fs
        await {"safety": fs.cmd_safety, "injection": fs.cmd_injection}[args.cmd](args)
    elif args.cmd == "memory":
        import final_memory as fm
        await fm.cmd_memory(args)
    elif args.cmd == "real":
        import final_real as fr
        await fr.cmd_real(args)
    elif args.cmd == "interfaces":
        import final_interfaces as fi
        await fi.cmd_interfaces(args)
    elif args.cmd == "report":
        import final_report as rp
        rp.build()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
