"""One AndroidWorld episode done by a compiled Envoy routine instead of the agent (the routines-across-seeds experiment).

  uv run --project backend python eval/androidworld/envoy_routine.py --payload p.json --out record.json

Same contract as envoy_episode.py: the payload is only the goal, the step budget, a run id and the configuration. Here the
configuration names the routine library (a directory under eval/results/androidworld/routines/, never data/routines/).
The request is matched to a routine the way Envoy matches any request (RoutineMatcher: app, patterns, similarity, then
one model call that fills the inputs from the goal text); the executor replays it with its checks, and with local repair
only when the configuration allows it. The full-agent fallback is off, so the result measures the routine itself.
A routine's outputs become the answer (comma-separated when there are several).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from envoy_episode import GRPC_PORT, PAYLOAD_KEYS, REPO, SERIAL, git_commit  # noqa: E402

LIBRARIES = REPO / "eval" / "results" / "androidworld" / "routines"


def answer_from(outputs: dict[str, str | None]) -> str | None:
    vals = [v for v in outputs.values() if v]
    return ", ".join(vals) if vals else None


async def run_routine(payload: dict[str, Any]) -> dict[str, Any]:
    from agent.loop import RunConfig
    from devices import emulator
    from models.adapter import ModelAdapter
    from policy.approvals import ScriptedApprover
    from routines.executor import ExecConfig, RoutineExecutor
    from routines.matcher import RoutineMatcher
    from routines.store import RoutineStore

    cfg = payload["config"]
    emulator.AVDS.setdefault("AndroidWorldAvd", {"serial": SERIAL, "grpc_port": GRPC_PORT, "can_snapshot": False})
    device = emulator.EmulatorDevice("AndroidWorldAvd").connect()
    adapter = ModelAdapter()
    approver = ScriptedApprover(approve=True)  # AndroidWorld's synthetic apps only; every approval is logged
    store = RoutineStore(LIBRARIES / cfg["library"])
    t0 = time.time()
    rec: dict[str, Any] = {"run_id": payload["run_id"], "goal": payload["goal"], "max_steps": payload["max_steps"], "config": cfg,
                           "envoy_commit": git_commit(), "mode": "routine"}
    try:
        m = await RoutineMatcher(store, adapter, data_scope="test_app", contributor=True).match(payload["goal"], task_id=payload["run_id"])
        rec["match"] = {"routine": m.routine.routine if m.routine else None, "stage": m.stage, "inputs": m.inputs, "missing": m.missing,
                        "candidates": m.candidates}
        calls, cost, cost_std = m.model_calls, 0.0, m.cost_usd  # the matcher reports its cost at standard prices
        if m.routine is None or m.missing:
            rec.update(status="no_routine" if m.routine is None else "needs_user", result=m.stage, done=False, answer=None,
                       model_calls=calls, cost_at_standard_usd=round(cost_std, 6), duration_s=round(time.time() - t0, 2))
            return rec
        ex = RoutineExecutor(device, adapter=adapter, approver=approver,
                             config=ExecConfig(data_scope="test_app", contributor=True,
                                               agent=RunConfig(max_steps=payload["max_steps"], data_scope="test_app", contributor=True)))
        out = await ex.run(m.routine, m.inputs, task_id=payload["run_id"], launch="if_needed",
                           allow_repair=bool(cfg.get("allow_repair", True)), allow_agent=False)
        steps_used = sum(1 for s in out.steps if s.status in ("done", "agent")) + sum(len(s.repairs) for s in out.steps)
        within = steps_used <= payload["max_steps"]
        ok = out.status in ("done", "agent_done")
        rec.update(
            status=out.status if within else "step_limit", result=out.detail, routine=out.routine, version=out.version,
            done=ok and within, answer=answer_from(out.outputs) if ok and within else None, outputs=out.outputs,
            steps_used=steps_used, rung=out.rung,
            steps=[{"id": s.id, "status": s.status, "rung": s.rung, "rungs": s.rungs, "repairs": len(s.repairs), "detail": s.detail}
                   for s in out.steps],
            repaired_steps=[s.id for s in out.steps if s.repairs], patches=len(out.patches),
            model_calls=calls + out.model_calls, cost_usd=round(cost + out.cost_usd, 6),
            cost_at_standard_usd=round(cost_std + out.cost_at_standard_usd, 6), approvals=out.approvals, popups=out.popups,
            duration_s=round(time.time() - t0, 2), routine_duration_s=out.duration_s, trace_dir=str(Path(out.trace_dir).relative_to(REPO)))
        return rec
    finally:
        try:
            device.u2.stop_uiautomator()  # hand the screen back to AndroidWorld's forwarder (see envoy_episode.py)
        except Exception as e:  # noqa: BLE001
            print(f"stop_uiautomator failed: {e}", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--payload", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--digest")  # routines keep their own trace in data/runs/<run id>/; no digest
    args = ap.parse_args()
    payload = json.loads(Path(args.payload).read_text())
    if set(payload) != PAYLOAD_KEYS:
        raise SystemExit(f"payload must have exactly {sorted(PAYLOAD_KEYS)}, got {sorted(payload)}")
    rec = asyncio.run(run_routine(payload))
    Path(args.out).write_text(json.dumps(rec, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
