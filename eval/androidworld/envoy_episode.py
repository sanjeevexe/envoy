"""One AndroidWorld episode, done by Envoy (the Envoy half of the adapter; Python 3.13, Envoy's backend).

  uv run --project backend python eval/androidworld/envoy_episode.py --payload p.json --out record.json

AndroidWorld's own runner (`run_aw.py`, in AndroidWorld's venv) sets the task up, then calls this once per task with
a payload of exactly four things: the goal text, the step budget AndroidWorld allotted, a run id (no task name in it)
and the run's configuration. Envoy then works the phone with its own device layer, as for any request:

- the agent exactly as in this checkout (main's, unless a stage says otherwise), memory off (no notes), no routines;
- Contributor tier (AndroidWorld's apps hold only synthetic data), `low` effort as Envoy uses it;
- irreversible steps go through Envoy's policy gate; a scripted person approves them (AndroidWorld's synthetic apps
  only) and every approval is logged;
- the step budget is Envoy's `max_steps`: one loop iteration (one decision, or one pop-up handled in code) is one step.

The record says whether Envoy ended the episode itself (AndroidWorld counts a task only then) and gives its answer,
which AndroidWorld's runner puts in its answer channel. AndroidWorld alone scores the task.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
SERIAL, GRPC_PORT = "emulator-5560", 8560  # eval/androidworld/emulator.sh; never Envoy's own emulators

PAYLOAD_KEYS = {"goal", "max_steps", "run_id", "config"}
# Statuses where the agent itself ended the episode (AndroidWorld's "done"); the rest are limits or crashes.
AGENT_ENDED = {"done", "done_unverified", "failed", "handoff", "needs_user"}
ANSWERED = {"done", "done_unverified"}
RUNCONFIG_KEYS = {"plan", "screenshots", "vision", "step_effort", "plan_effort", "max_done_rejections"}  # agent overrides
ROUTINE_KEYS = {"mode", "library", "allow_repair"}  # the routines experiment (envoy_routine.py)
CONFIG_KEYS = RUNCONFIG_KEYS | ROUTINE_KEYS


def make_payload(goal: str, max_steps: int, run_id: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Everything Envoy is told about a task. Nothing else from AndroidWorld may be added (tests assert the keys)."""
    config = dict(config or {})
    unknown = set(config) - CONFIG_KEYS
    if unknown:
        raise ValueError(f"unknown config keys: {sorted(unknown)}")
    if not isinstance(goal, str) or not goal.strip():
        raise ValueError("goal must be non-empty text")
    if not isinstance(max_steps, int) or max_steps < 1:
        raise ValueError("max_steps must be a positive integer")
    return {"goal": goal, "max_steps": max_steps, "run_id": run_id, "config": config}


def to_androidworld(status: str, result: str) -> dict[str, Any]:
    """Envoy's outcome → AndroidWorld's episode: done (the agent ended it) and the answer for the answer channel.

    Like AndroidWorld's M3A, which returns done on `status: infeasible`, an episode the agent ended itself (done, its own
    fail, a hand-off) is done; a step limit or a crash is not. Only a `done` carries an answer: a failure reason must
    never be scored as one.
    """
    return {"done": status in AGENT_ENDED, "answer": result if status in ANSWERED and result else None}


def git_commit(path: Path = REPO) -> str:
    sha = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(path), "status", "--porcelain", "--", "backend"], capture_output=True, text=True).stdout.strip()
    return sha + ("+dirty-backend" if dirty else "")


def summarize_trace(trace_dir: Path) -> dict[str, Any]:
    """Counts from Envoy's trace that RunResult doesn't carry: iterations, looks, screenshots, replans, stuck recoveries,
    vision calls, invalid elements, rejected dones, model time."""
    steps_file = trace_dir / "steps.jsonl"
    recs = [json.loads(l) for l in steps_file.read_text().splitlines() if l.strip()] if steps_file.exists() else []
    c = {"iterations": 0, "looks": 0, "screenshots_sent": 0, "replans": 0, "stuck_recoveries": 0, "vision_calls": 0,
         "invalid_elements": 0, "done_rejected": 0, "tap_point_rejected": 0, "model_errors": 0, "model_ms": 0, "actions": {}}
    for r in recs:
        c["iterations"] = max(c["iterations"], r.get("step", 0) or 0)
        kind = r.get("kind")
        if kind in ("plan", "replan"):
            c["model_ms"] += r.get("model_ms", 0) or 0
            c["replans"] += kind == "replan"
        elif kind == "stuck":
            c["stuck_recoveries"] += 1
        elif kind == "model_error":
            c["model_errors"] += 1
        elif kind == "action":
            c["model_ms"] += (r.get("timings_ms") or {}).get("model", 0) or 0
            t = ((r.get("decision") or {}).get("action") or {}).get("type", "?")
            c["actions"][t] = c["actions"].get(t, 0) + 1
            c["looks"] += t == "look"
            c["screenshots_sent"] += bool(r.get("screenshot_before"))
            c["vision_calls"] += bool(r.get("vision"))
            err = r.get("error") or ""
            c["invalid_elements"] += "not on the current screen" in err
            c["tap_point_rejected"] += err.startswith("tap_point rejected")
    return c


def write_digest(trace_dir: Path, dest: Path) -> None:
    """A compact copy of the trace (no trees or images): what the model saw and did at every step, gzipped."""
    steps_file = trace_dir / "steps.jsonl"
    if not steps_file.exists():
        return
    keep = ("step", "kind", "decision", "error", "risk", "approval", "result", "changed", "handler", "reason", "plan",
            "tried", "vision", "recovery", "action", "timings_ms", "cost_usd")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(dest, "wt") as f:
        for line in steps_file.read_text().splitlines():
            r = json.loads(line)
            d = {k: r[k] for k in keep if k in r}
            seen = r.get("screen_before") or (r["screen"] if isinstance(r.get("screen"), dict) else None)
            if seen:
                d["screen"] = seen.get("compact")
            if r.get("screen_after"):
                d["screen_after_head"] = (r["screen_after"].get("compact") or "").split("\n", 1)[0]
            if r.get("target"):
                d["target"] = {k: r["target"].get(k) for k in ("label", "kind", "resource_id", "bounds")}
            f.write(json.dumps(d, ensure_ascii=False) + "\n")


async def run_episode(payload: dict[str, Any]) -> dict[str, Any]:
    from agent.loop import AgentRunner, RunConfig
    from devices import emulator
    from models.adapter import JOBS, ModelAdapter
    from policy.approvals import ScriptedApprover

    emulator.AVDS.setdefault("AndroidWorldAvd", {"serial": SERIAL, "grpc_port": GRPC_PORT, "can_snapshot": False})
    t0 = time.time()
    device = emulator.EmulatorDevice("AndroidWorldAvd").connect()
    connect_s = time.time() - t0
    approver = ScriptedApprover(approve=True)  # AndroidWorld's synthetic test apps only (user's permission for this benchmark)
    cfg = RunConfig(max_steps=payload["max_steps"], data_scope="test_app", contributor=True,
                    **{k: v for k, v in payload["config"].items() if k in RUNCONFIG_KEYS})
    adapter = ModelAdapter()
    runner = AgentRunner(device, adapter, approver, cfg)
    try:
        res = await runner.run(payload["goal"], task_id=payload["run_id"], memory="")
    finally:
        # uiautomator2's UiAutomation session can suppress AndroidWorld's accessibility forwarder, which some of its
        # checks read the screen through: stop it so AndroidWorld scores and resets on a normal phone.
        try:
            device.u2.stop_uiautomator()
        except Exception as e:  # noqa: BLE001
            print(f"stop_uiautomator failed: {e}", file=sys.stderr)
    trace_dir = Path(res.trace_dir)
    counts = summarize_trace(trace_dir)
    model_s = counts.pop("model_ms") / 1000
    return {
        "run_id": payload["run_id"],
        "goal": payload["goal"],
        "max_steps": payload["max_steps"],
        "config": payload["config"],
        "status": res.status,
        "result": res.result,
        **to_androidworld(res.status, res.result),
        "steps_device": res.steps,
        **counts,
        "model_calls": res.model_calls,
        "input_tokens": res.input_tokens,
        "cached_tokens": res.cached_tokens,
        "output_tokens": res.output_tokens,
        "reasoning_tokens": res.reasoning_tokens,
        "cost_usd": round(res.cost_usd, 6),
        "cost_at_standard_usd": round(res.cost_at_standard_usd, 6),
        "duration_s": res.duration_s,
        "model_s": round(model_s, 2),
        "device_s": round(max(0.0, res.duration_s - model_s), 2),
        "connect_s": round(connect_s, 2),
        "approvals": res.approvals,
        "popups": res.popups,
        "plan": res.plan,
        "check": res.check,
        "trace_dir": str(trace_dir.relative_to(REPO)) if trace_dir.is_relative_to(REPO) else str(trace_dir),
        "envoy_commit": git_commit(),
        "model": adapter.resolve_model(JOBS["step"], "test_app", True),
        "effort": {"step": cfg.step_effort, "plan": cfg.plan_effort},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--payload", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--digest", help="where to write the compact trace digest (.jsonl.gz)")
    args = ap.parse_args()
    payload = json.loads(Path(args.payload).read_text())
    if set(payload) != PAYLOAD_KEYS:
        raise SystemExit(f"payload must have exactly {sorted(PAYLOAD_KEYS)}, got {sorted(payload)}")
    record = asyncio.run(run_episode(payload))
    if args.digest:
        write_digest(REPO / record["trace_dir"], Path(args.digest))
        record["trace_digest"] = str(Path(args.digest).resolve().relative_to(REPO))
    Path(args.out).write_text(json.dumps(record, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
