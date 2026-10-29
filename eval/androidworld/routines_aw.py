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
    prev = json.loads(out.read_text()) if out.exists() and only else {"rows": []}
    for r in prev["rows"]:  # rows from an earlier compile keep the stage they came from
        r.setdefault("source", prev.get("source"))
    for r in rows:
        r["source"] = args.source
    keep = [r for r in prev["rows"] if r["task"] not in {x["task"] for x in rows}]
    out.write_text(json.dumps({"rows": keep + rows}, indent=1, ensure_ascii=False, default=str))


def cmd_promote(args: argparse.Namespace) -> None:
    """Routines whose same-seed replay AndroidWorld scored 1 (no repair, no agent) go to the verified library."""
    verified = LIBS / args.into
    rows = []
    for ep in episodes(args.verify):
        e = ep.get("envoy") or {}
        name = (e.get("match") or {}).get("routine")
        ok = (ep.get("score") or 0) >= 1.0 and e.get("status") == "done" and not e.get("repaired_steps")
        rows.append({"task": ep["task"], "routine": name, "verified": ok, "status": e.get("status"), "score": ep.get("score"),
                     "detail": e.get("result")})
        if ok and name:
            shutil.copytree(LIBS / args.library / name, verified / name, dirs_exist_ok=True)
        print(f"{'VERIFIED' if ok else 'REJECTED'} {ep['task']}: {name} ({e.get('status')}, score {ep.get('score')})")
    out = LIBS / ("verify.json" if args.into == "verified" else f"verify-{args.into}.json")
    out.write_text(json.dumps({"stage": args.verify, "library": args.library, "rows": rows}, indent=1))


def cmd_report(args: argparse.Namespace) -> None:
    """Routines vs the agent on the same unseen seeds: success, model calls, cost, time (model vs device), repairs."""
    import statistics as st

    def rows(stage: str) -> dict[tuple[str, int], dict]:
        return {(ep["task"], ep["seed"]): ep for ep in episodes(stage)} if (RESULTS / stage).exists() else {}

    r, a = rows(args.routines), rows(args.agent)
    tasks = sorted({t for t, _ in r})
    table, totals = [], {"routine": [], "agent": []}
    for t in tasks:
        seeds = sorted(s for (tt, s) in r if tt == t)
        rr = [r[(t, s)] for s in seeds]
        aa = [a[(t, s)] for s in seeds if (t, s) in a]
        def agg(eps, key):
            vals = [(e.get("envoy") or {}).get(key) for e in eps]
            return [v for v in vals if v is not None]
        row = {"task": t, "seeds": seeds,
               "routine_success": sum(e.get("score", 0) for e in rr), "agent_success": sum(e.get("score", 0) for e in aa),
               "routine_calls": agg(rr, "model_calls"), "agent_calls": agg(aa, "model_calls"),
               "routine_cost_std": agg(rr, "cost_at_standard_usd"), "agent_cost_std": agg(aa, "cost_at_standard_usd"),
               "routine_s": agg(rr, "duration_s"), "agent_s": agg(aa, "duration_s"),
               "routine_status": [(e.get("envoy") or {}).get("status") for e in rr],
               "repaired_steps": sorted({x for e in rr for x in (e.get("envoy") or {}).get("repaired_steps") or []}),
               "match": [((e.get("envoy") or {}).get("match") or {}).get("routine") for e in rr]}
        table.append(row)
        totals["routine"] += rr
        totals["agent"] += aa
    summary = {k: {"episodes": len(v), "success": sum(e.get("score", 0) for e in v),
                   "median_calls": st.median([(e.get("envoy") or {}).get("model_calls") or 0 for e in v]) if v else None,
                   "median_cost_std": st.median([(e.get("envoy") or {}).get("cost_at_standard_usd") or 0 for e in v]) if v else None,
                   "median_s": st.median([(e.get("envoy") or {}).get("duration_s") or 0 for e in v]) if v else None}
               for k, v in totals.items()}
    (LIBS / args.out).write_text(json.dumps({"routines": args.routines, "agent": args.agent, "summary": summary, "tasks": table},
                                            indent=1, default=str))
    print(json.dumps(summary, indent=1))
    for row in table:
        print(f"{row['task']:42} routine {row['routine_success']:g}/{len(row['seeds'])} {row['routine_status']} calls {row['routine_calls']}"
              f" | agent {row['agent_success']:g}/{len(row['seeds'])} calls {row['agent_calls']} | repaired {row['repaired_steps']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compile")
    c.add_argument("--source", required=True)
    c.add_argument("--tasks", default="")
    p = sub.add_parser("promote")
    p.add_argument("--verify", required=True)
    p.add_argument("--library", default="candidates", help="the library the verify stage replayed")
    p.add_argument("--into", default="verified")
    r = sub.add_parser("report")
    r.add_argument("--routines", default="routines-seeds")
    r.add_argument("--agent", default="agent-seeds")
    r.add_argument("--out", default="report.json")
    args = ap.parse_args()
    if args.cmd == "report":
        cmd_report(args)
    elif args.cmd == "compile":
        asyncio.run(cmd_compile(args))
    elif args.cmd == "promote":
        cmd_promote(args)


if __name__ == "__main__":
    sys.exit(main())
