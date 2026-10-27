"""Compile one agent trace into an app routine and print it (no replay, nothing saved unless --out).

  uv run --project backend python scripts/compile_routine.py p1-final-code-check-checkin-v0-r0
  uv run --project backend python scripts/compile_routine.py <task_id> --memory "Known traveler number: 98765432" --out data/drafts
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from agent.trace import RUNS
from routines.compiler import compile_trace
from routines.model import dump_yaml


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("task_id")
    ap.add_argument("--memory", default="")
    ap.add_argument("--effort", default=None)
    ap.add_argument("--out", default=None, help="directory to write <name>.yaml and the report into")
    args = ap.parse_args()
    routine, report = await compile_trace(RUNS / args.task_id, memory=args.memory, effort=args.effort)
    text = dump_yaml(routine)
    print(text)
    print("# dropped:", *[f"#   step {n}: {why}" for n, why in report.dropped], sep="\n")
    print(f"# compiler {report.model}: {report.latency_s} s, ${report.cost_at_standard_usd:.4f}")
    for w in report.warnings:
        print(f"# warning: {w}")
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{routine.routine}.yaml").write_text(text)
        (out / f"{routine.routine}.report.json").write_text(json.dumps(report.__dict__, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
