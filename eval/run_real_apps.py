"""Phase 2 real-app checkpoint on envoy-real: read-only workflows, compiled into routines and rerun.

  uv run --project backend python eval/run_real_apps.py [--only target,amazon] [--skip-agent]

For each workflow: the full agent runs it once from a fresh app launch (standard tier: real apps never
use the Contributor tier), the trace is compiled into a routine (Muse Wonder), and the routine is
rerun from a fresh launch with the same inputs and, where the workflow has one, a second input.
envoy-real is never restored to a snapshot; "reset" is only force-stopping and relaunching the app.

Safety: every approval is declined by the script (nothing irreversible may run), sign-in screens stop
the run (hand-off), nothing is typed into a password field. Outputs that hold personal data (a saved
address) are redacted before they are written to eval/results.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from agent.loop import AgentRunner, RunConfig
from agent.trace import RUNS
from devices.emulator import EmulatorDevice
from models.adapter import ModelAdapter
from policy.approvals import ScriptedApprover
from models.schemas import CompiledRoutine
from routines.compiler import NotCompilable, compile_trace
from routines.executor import ExecConfig, RoutineExecutor
from routines.model import dump_yaml
from routines.screens import norm

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "eval" / "results" / "phase2"


@dataclass
class Workflow:
    id: str
    app: str
    goal: str
    memory: str = ""
    second: dict[str, str] = field(default_factory=dict)  # example value → second value (e.g. a search term)
    private: bool = False  # outputs hold personal data: redact before writing results


WORKFLOWS = [
    Workflow("target", "com.target.ui", "In the Target app, what are today's hours for my Target store?"),
    Workflow("chipotle", "com.chipotle.ordering", "In the Chipotle app, find the price of Chips & Guacamole.",
             memory="Preferred Chipotle location: near zip code 10001 (Chelsea, New York)", second={"Chips & Guacamole": "Chips & Queso Blanco"}),
    Workflow("amazon", "com.amazon.mShop.android.shopping", "In the Amazon app, search for AA batteries and tell me the price of the first result.",
             second={"AA batteries": "USB-C cable"}),
    Workflow("doordash", "com.dd.doordash", "In the DoorDash app, what is my saved delivery address?", private=True),
    Workflow("starbucks", "com.starbucks.mobilecard", "In the Starbucks app, how many calories are in a Grande Caffè Latte?",
             second={"Caffè Latte": "Caramel Macchiato", "Caffe Latte": "Caramel Macchiato"}),
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def redact(wf: Workflow, value: object) -> object:
    if not wf.private:
        return value
    if isinstance(value, dict):
        return {k: "[redacted]" if v else v for k, v in value.items()}
    if isinstance(value, str) and value:
        return "[redacted]"
    return value


def step_rows(outcome) -> list[dict]:
    return [{"id": s.id, "status": s.status, "rung": s.rung, "rungs": s.rungs, "score": s.score, "detail": s.detail[:200],
             "ms": round(s.wait_ms + s.act_ms + s.post_ms)} for s in outcome.steps]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--skip-agent", action="store_true", help="reuse the existing agent trace")
    ap.add_argument("--reuse-spec", action="store_true", help="reuse the cached compile answer (no model cost)")
    args = ap.parse_args()
    device = EmulatorDevice("envoy-real").connect()
    adapter = ModelAdapter()
    approver = ScriptedApprover(approve=False)  # real apps: every approval is declined; nothing irreversible runs
    path = OUT / "real_apps.json"
    results = json.loads(path.read_text())["workflows"] if path.exists() else {}
    for wf in WORKFLOWS:
        if args.only and wf.id not in args.only.split(","):
            continue
        row: dict = {"app": wf.app, "goal": wf.goal, "time": now()}
        task_id = f"p2-real-{wf.id}"
        if not args.skip_agent:
            await device.launch(wf.app, fresh=True)
            await asyncio.sleep(2.0)
            agent = AgentRunner(device, adapter=adapter, approver=approver, config=RunConfig(data_scope="real", max_steps=25, max_cost_usd=0.25))
            res = await agent.run(wf.goal, task_id=task_id, memory=wf.memory)
            row["agent"] = {"status": res.status, "result": redact(wf, res.result), "steps": res.steps, "model_calls": res.model_calls,
                            "cost_usd": round(res.cost_at_standard_usd, 4), "duration_s": res.duration_s, "popups": res.popups,
                            "approvals": len(res.approvals), "check": res.check}
            print(f"agent    {wf.id:9s} {res.status:15s} {res.steps} steps {res.model_calls} calls ${res.cost_usd:.4f} {res.duration_s}s "
                  f"{redact(wf, res.result)!s:.90}", flush=True)
        else:
            row["agent"] = results.get(wf.id, {}).get("agent")
        spec_dir = (REPO / "data" / "real_routines") if wf.private else (OUT / "compiled-real")
        spec_dir.mkdir(parents=True, exist_ok=True)
        spec_file = spec_dir / f"{wf.id}.spec.json"
        cached = CompiledRoutine.model_validate_json(spec_file.read_text()) if args.reuse_spec and spec_file.exists() else None
        try:
            routine, report = await compile_trace(RUNS / task_id, adapter=adapter, memory=wf.memory, spec=cached)
            if cached is None and report.wonder:
                spec_file.write_text(json.dumps(report.wonder, indent=1, ensure_ascii=False))
        except NotCompilable as e:
            row["compile"] = {"compiled": False, "reason": str(e)}
            print(f"compile  {wf.id:9s} not compiled: {e}", flush=True)
            results[wf.id] = row
            path.write_text(json.dumps({"time": now(), "workflows": results}, indent=1, ensure_ascii=False, default=str))
            continue
        # A routine over personal data (a saved address) stays out of the repo: data/ is not committed.
        ydir = (REPO / "data" / "real_routines") if wf.private else (OUT / "compiled-real")
        ydir.mkdir(parents=True, exist_ok=True)
        (ydir / f"{wf.id}.yaml").write_text(dump_yaml(routine))
        row["compile"] = {"compiled": True, "routine": routine.routine, "steps": len(routine.steps), "inputs": {k: v.example for k, v in routine.inputs.items()},
                          "outputs": routine.outputs, "dropped": report.dropped, "warnings": report.warnings, "cost_usd": round(report.cost_at_standard_usd, 4)}
        print(f"compile  {wf.id:9s} {routine.routine}: {len(routine.steps)} steps, inputs {list(routine.inputs)}, outputs {routine.outputs}", flush=True)
        ex = RoutineExecutor(device, adapter=adapter, approver=approver, config=ExecConfig(data_scope="real"))
        runs = []
        cases = [("same-inputs", {k: v.example or "" for k, v in routine.inputs.items()})]
        if wf.second:
            alt = {}
            for k, v in routine.inputs.items():  # replace the part of the example that the second input changes
                example = v.example or ""
                alt[k] = next((new if norm(old) == norm(example) else example.replace(old, new)
                               for old, new in wf.second.items() if norm(old) in norm(example)), example)
            if alt != cases[0][1]:
                cases.append(("second-input", alt))
        for name, inputs in cases:
            for allow_repair in (False, True):
                out = await ex.run(routine, inputs, task_id=f"{task_id}-{name}-{'repair' if allow_repair else 'strict'}", launch="fresh",
                                   allow_repair=allow_repair, allow_agent=False, memory=wf.memory)
                runs.append({"case": name, "inputs": inputs, "repair_allowed": allow_repair, "status": out.status, "detail": out.detail[:300],
                             "outputs": redact(wf, out.outputs), "rung": out.rung, "model_calls": out.model_calls,
                             "cost_usd": round(out.cost_at_standard_usd, 4), "duration_s": out.duration_s, "steps": step_rows(out),
                             "patches": [p.description for p in out.patches], "popups": out.popups})
                print(f"routine  {wf.id:9s} {name:12s} {'repair' if allow_repair else 'strict'}: {out.status} rung={out.rung} calls={out.model_calls} "
                      f"{out.duration_s}s {redact(wf, out.outputs)} {out.detail[:100]}", flush=True)
                if out.status == "done" and not allow_repair:
                    break  # it worked without repair; no need to try with it
        row["routine_runs"] = runs
        results[wf.id] = row
        path.write_text(json.dumps({"time": now(), "workflows": results}, indent=1, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
