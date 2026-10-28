"""Routines across AndroidWorld seeds: compile solved runs, keep the ones a replay verifies, report.

  uv run --project backend python eval/androidworld/routines_aw.py compile --source baseline-standard   # solved seed-30 runs → candidates
  eval/androidworld/aw.sh run_aw.py --stage routines-verify --tasks … --config '{"mode": "routine", "library": "candidates", "allow_repair": false, "tier": "standard"}'
  uv run --project backend python eval/androidworld/routines_aw.py promote --verify routines-verify   # replays that scored 1 → verified
  eval/androidworld/aw.sh run_aw.py --stage routines-seeds --instances 1,2,3 --tasks … --config '{"mode": "routine", "library": "verified", "tier": "standard"}'
  eval/androidworld/aw.sh run_aw.py --stage agent-seeds --instances 1,2,3 --tasks … --config '{"tier": "standard"}'
  uv run --project backend python eval/androidworld/routines_aw.py report

Compiling is Envoy's own (`routines.compiler.compile_trace`, Muse Wonder), from the trace of a run AndroidWorld scored 1
(that score is the confirmation the compiler needs). Libraries live under eval/results/androidworld/routines/, never in
data/routines/. Verification is a replay on the same seed through AndroidWorld's runner, scored by AndroidWorld, with
no repair and no agent: only a routine that does the task on its own is kept. Routine names are made unique with a
number when two compiles pick the same name (never with the task's name: the matcher sees routine names).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RESULTS = REPO / "eval" / "results" / "androidworld"
LIBS = RESULTS / "routines"


def episodes(stage: str) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted((RESULTS / stage / "episodes").glob("*.json"))]


async def cmd_compile(args: argparse.Namespace) -> None:
    from models.adapter import ModelAdapter
    from routines.compiler import compile_trace
    from routines.model import dump_yaml
    from routines.store import RoutineStore

    store = RoutineStore(LIBS / "candidates")
    adapter = ModelAdapter()
    only = {t for t in args.tasks.split(",") if t}
    rows = []
    for ep in episodes(args.source):
        e = ep.get("envoy") or {}
        if (ep.get("score") or 0) < 1.0 or (only and ep["task"] not in only) or not e.get("trace_dir"):
            continue
        trace = REPO / e["trace_dir"]
        try:
            routine, report = await compile_trace(trace, adapter=adapter, memory="", confirmed=True)
        except Exception as exc:  # noqa: BLE001 - a run that can't be compiled is a finding, not a crash
            rows.append({"task": ep["task"], "compiled": False, "error": f"{type(exc).__name__}: {exc}"[:400]})
            print(f"NOT COMPILED {ep['task']}: {exc}", flush=True)
            continue
        base, n = routine.routine, 2
        while routine.routine in store.names():
            routine.routine, n = f"{base}_{n}", n + 1
        routine = store.add(routine, {"source": args.source, "source_seed": ep["seed"]})
        rows.append({"task": ep["task"], "compiled": True, "routine": routine.routine, "steps": len(routine.steps),
                     "inputs": {k: s.model_dump() for k, s in routine.inputs.items()}, "outputs": routine.outputs,
                     "kept": report.kept, "dropped": report.dropped, "warnings": report.warnings, "compiler": report.model,
                     "cost_usd": report.cost_usd, "cost_at_standard_usd": report.cost_at_standard_usd, "latency_s": report.latency_s})
        print(f"COMPILED {ep['task']} → {routine.routine}: {len(routine.steps)} steps, inputs {list(routine.inputs)}, "
              f"outputs {routine.outputs}, ${report.cost_at_standard_usd:.3f}", flush=True)
        (LIBS / "candidates" / routine.routine / "source.txt").write_text(f"{args.source} {ep['task']} seed {ep['seed']}\n")
    out = LIBS / "compile.json"
    prev = json.loads(out.read_text())["rows"] if out.exists() and only else []
    keep = [r for r in prev if r["task"] not in {x["task"] for x in rows}]
    out.write_text(json.dumps({"source": args.source, "rows": keep + rows}, indent=1, ensure_ascii=False, default=str))


def cmd_promote(args: argparse.Namespace) -> None:
    """Routines whose same-seed replay AndroidWorld scored 1 (no repair, no agent) go to the verified library."""
    verified = LIBS / "verified"
    rows = []
    for ep in episodes(args.verify):
        e = ep.get("envoy") or {}
        name = (e.get("match") or {}).get("routine")
        ok = (ep.get("score") or 0) >= 1.0 and e.get("status") == "done" and not e.get("repaired_steps")
        rows.append({"task": ep["task"], "routine": name, "verified": ok, "status": e.get("status"), "score": ep.get("score"),
                     "detail": e.get("result")})
        if ok and name:
            shutil.copytree(LIBS / "candidates" / name, verified / name, dirs_exist_ok=True)
        print(f"{'VERIFIED' if ok else 'REJECTED'} {ep['task']}: {name} ({e.get('status')}, score {ep.get('score')})")
    (LIBS / "verify.json").write_text(json.dumps({"stage": args.verify, "rows": rows}, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compile")
    c.add_argument("--source", required=True)
    c.add_argument("--tasks", default="")
    p = sub.add_parser("promote")
    p.add_argument("--verify", required=True)
    args = ap.parse_args()
    if args.cmd == "compile":
        asyncio.run(cmd_compile(args))
    elif args.cmd == "promote":
        cmd_promote(args)


if __name__ == "__main__":
    sys.exit(main())
