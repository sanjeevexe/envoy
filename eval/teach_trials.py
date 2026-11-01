"""Teach-mode trials on real apps (Nov 1): strict replays of a taught routine, straight on the phone with no API copy
running. Each replay launches the app fresh and runs the routine with no repair and no agent, like teach mode's own
verification replay (api/teach.py); any irreversible step is declined. Prints and saves each replay's status, outputs,
model calls, cost and seconds.

  uv run --project backend python eval/teach_trials.py wikipedia_find_opening_year --runs 3 --expect 1937 \
      --out eval/results/teach_trials_2026-11-01/wikipedia/replays.json
  ... --inputs '{"subject": "Brooklyn Bridge"}' --expect 1883 --runs 1 --out .../wikipedia/new_input.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from devices.emulator import EmulatorDevice  # noqa: E402
from models.adapter import ModelAdapter  # noqa: E402
from policy.approvals import ScriptedApprover  # noqa: E402
from routines.executor import ExecConfig, RoutineExecutor  # noqa: E402
from routines.model import load  # noqa: E402
from routines.store import RoutineStore  # noqa: E402


def bare(s: str) -> str:
    """Digits and words only: "7,006,652" and "7006652" are the same answer."""
    return re.sub(r"[\s,]", "", s).lower()


async def replays(name: str, inputs: dict[str, str], expect: str, runs: int, avd: str, version: int | None) -> list[dict[str, Any]]:
    # A routine in the library by name, or a routine.yaml (a taught routine whose verification replay failed isn't saved)
    routine = load(Path(name)) if name.endswith(".yaml") else RoutineStore().get(name, version)
    name = routine.routine
    ins = {**{k: v.example or "" for k, v in routine.inputs.items()}, **inputs}
    device = EmulatorDevice(avd).connect()
    ex = RoutineExecutor(device, adapter=ModelAdapter(), approver=ScriptedApprover(approve=False),
                         config=ExecConfig(data_scope="real", patch_screenshots=False))
    rows = []
    for i in range(runs):
        tid = f"teachtrial-{name}-{time.strftime('%m%d-%H%M%S')}-{i + 1}"
        t0 = time.time()
        out = await ex.run(routine, ins, task_id=tid, launch="fresh", allow_repair=False, allow_agent=False)
        answer = " ".join(str(v) for v in out.outputs.values() if v)
        row = {"run": i + 1, "routine": name, "version": routine.version, "inputs": ins, "status": out.status,
               "passed": out.status == "done" and (not expect or bare(expect) in bare(answer)), "expected": expect,
               "outputs": out.outputs, "detail": out.detail, "model_calls": out.model_calls,
               "cost_usd": round(out.cost_at_standard_usd, 4), "seconds": round(out.duration_s, 1),
               "wall_s": round(time.time() - t0, 1), "steps": len(out.steps), "rung": out.rung,
               "declined_approvals": len(out.approvals), "trace": tid}
        print(json.dumps(row), flush=True)
        rows.append(row)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("routine", help="a library routine's name, or a routine.yaml")
    ap.add_argument("--inputs", default="{}", help="JSON; inputs left out use the routine's examples")
    ap.add_argument("--expect", default="", help="the right answer, found in the outputs for a pass")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--avd", default="envoy-real")
    ap.add_argument("--version", type=int)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    rows = asyncio.run(replays(args.routine, json.loads(args.inputs), args.expect, args.runs, args.avd, args.version))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(rows, indent=1) + "\n")
    return 0 if all(r["passed"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
