"""Run the SkyLark Air task set and write a report.

  uv run --project backend python eval/run_skylark.py                     # 10 core + 3 safety tasks, variant 0
  uv run --project backend python eval/run_skylark.py --tasks gate,checkin --variant 2 --repeat 3
  uv run --project backend python eval/run_skylark.py --suite core

Each run: SkyLark reset to its fixtures (plus task overrides), layout variant set, cold launch, agent
run, then the task's code check against the app's state. Results: eval/results/phase1/<name>.json + .md
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from agent.loop import AgentRunner, RunConfig
from devices.emulator import EmulatorDevice
from policy.approvals import ScriptedApprover
from skylark_tasks import BY_ID, TASKS, Task
from testapps.skylark import SkyLark, default_fixtures

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "eval" / "results" / "phase1"


async def run_one(device: EmulatorDevice, app: SkyLark, task: Task, variant: int, rep: int, tag: str) -> dict:
    fixtures = copy.deepcopy(default_fixtures())
    fixtures.update(task.fixtures)
    app.prepare(fixtures=fixtures, variant=variant)
    approver = ScriptedApprover(approve=task.approve)
    runner = AgentRunner(device, approver=approver, config=RunConfig(data_scope="test_app"))
    task_id = f"{tag}-{task.id}-v{variant}-r{rep}"
    result = await runner.run(task.goal, task_id=task_id, memory=task.memory)
    state = app.state()
    passed = bool(task.check(state, result))
    gate_ok = None
    if task.expect_approval is not None:
        gate_ok = (len(result.approvals) > 0) == task.expect_approval
    row = {
        "task": task.id, "suite": task.suite, "variant": variant, "rep": rep, "goal": task.goal,
        "passed": passed, "status": result.status, "result": result.result,
        "steps": result.steps, "model_calls": result.model_calls, "cost_usd": round(result.cost_usd, 5),
        "input_tokens": result.input_tokens, "cached_tokens": result.cached_tokens,
        "output_tokens": result.output_tokens, "reasoning_tokens": result.reasoning_tokens,
        "duration_s": result.duration_s, "approvals": result.approvals, "approval_gate_ok": gate_ok,
        "popups": result.popups, "plan": result.plan, "check": result.check, "trace": result.trace_dir,
    }
    mark = "PASS" if passed else "FAIL"
    print(f"{mark}  {task.id:16s} v{variant} r{rep}  {result.status:15s} {result.steps:2d} steps  {result.model_calls:2d} calls  "
          f"${result.cost_usd:.4f}  {result.duration_s:5.1f}s  approvals={len(result.approvals)}  {result.result[:70]!r}", flush=True)
    return row


def summarize(rows: list[dict]) -> dict:
    def agg(rs: list[dict]) -> dict:
        if not rs:
            return {}
        return {
            "runs": len(rs),
            "success_rate": round(sum(r["passed"] for r in rs) / len(rs), 3),
            "median_steps": statistics.median(r["steps"] for r in rs),
            "median_model_calls": statistics.median(r["model_calls"] for r in rs),
            "median_duration_s": statistics.median(r["duration_s"] for r in rs),
            "median_cost_usd": round(statistics.median(r["cost_usd"] for r in rs), 5),
            "total_cost_usd": round(sum(r["cost_usd"] for r in rs), 4),
            "cache_hit_share": round(sum(r["cached_tokens"] for r in rs) / max(1, sum(r["input_tokens"] for r in rs)), 3),
            "approval_gate_correct": f'{sum(1 for r in rs if r["approval_gate_ok"])}/{sum(1 for r in rs if r["approval_gate_ok"] is not None)}',
        }
    out = {"all": agg(rows)}
    for suite in sorted({r["suite"] for r in rows}):
        out[suite] = agg([r for r in rows if r["suite"] == suite])
    for v in sorted({r["variant"] for r in rows}):
        out[f"core_variant_{v}"] = agg([r for r in rows if r["suite"] == "core" and r["variant"] == v])
    return out


def markdown(name: str, rows: list[dict], summary: dict) -> str:
    lines = [f"# SkyLark eval: {name}", "", f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}", ""]
    lines += ["| Suite | Runs | Success | Median steps | Median model calls | Median time | Median cost | Total cost | Approval gate correct |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for k, s in summary.items():
        if s:
            lines.append(f"| {k} | {s['runs']} | {s['success_rate']:.0%} | {s['median_steps']} | {s['median_model_calls']} | "
                         f"{s['median_duration_s']} s | ${s['median_cost_usd']} | ${s['total_cost_usd']} | {s['approval_gate_correct']} |")
    lines += ["", "| Task | Variant | Pass | Status | Steps | Calls | Time | Cost | Result |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        res = r["result"].replace("|", "/").replace("\n", " ")[:90]
        lines.append(f"| {r['task']} | {r['variant']} | {'✅' if r['passed'] else '❌'} | {r['status']} | {r['steps']} | {r['model_calls']} | "
                     f"{r['duration_s']} s | ${r['cost_usd']} | {res} |")
    return "\n".join(lines) + "\n"


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", help="comma-separated task ids (default: all)")
    ap.add_argument("--suite", choices=["core", "safety", "robustness"])
    ap.add_argument("--variant", default="0", help="layout variant(s), e.g. 0 or 0,1,2,3")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--name", default=None, help="report name (default: timestamp)")
    args = ap.parse_args()

    tasks = [BY_ID[t] for t in args.tasks.split(",")] if args.tasks else [t for t in TASKS if not args.suite or t.suite == args.suite]
    variants = [int(v) for v in args.variant.split(",")]
    name = args.name or datetime.now().strftime("%Y%m%d-%H%M%S")
    device = EmulatorDevice("envoy-test").connect()
    app = SkyLark(device.serial)
    if not app.installed():
        app.install()

    rows: list[dict] = []
    t0 = time.time()
    for v in variants:
        for task in tasks:
            for rep in range(args.repeat):
                rows.append(await run_one(device, app, task, v, rep, name))
    app.prepare()

    summary = summarize(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps({"name": name, "summary": summary, "rows": rows}, indent=1, default=str))
    (OUT / f"{name}.md").write_text(markdown(name, rows, summary))
    print("\n" + "\n".join(f"{k}: {v}" for k, v in summary.items()))
    print(f"\n{time.time() - t0:.0f} s · report: eval/results/phase1/{name}.md")
    core = summary.get("core", {})
    return 0 if not core or core.get("success_rate", 0) >= 0.6 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
