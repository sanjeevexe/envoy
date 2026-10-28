"""Baselines for the three-system comparison (design doc, Evaluation › Three systems compared).

Fixed replay mirrors Mobilerun-style macros: replay the recorded actions at their recorded screen
coordinates with the recorded text, each after a screen-similarity check against the recorded
screen; on a mismatch the full agent takes over the rest of the task. It has no inputs, no
element locators and no after-checks, which is exactly what Envoy routines add.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from agent.loop import AgentRunner
from devices.types import Action
from routines.screens import jaccard, load_tree, signature_keys

SIMILARITY = 0.7  # Jaccard of screen-signature keys required before each replayed action


async def fixed_replay(device: Any, trace_dir: Path, agent: AgentRunner, goal: str, memory: str, task_id: str) -> dict[str, Any]:
    t0 = time.time()
    records = [json.loads(line) for line in (trace_dir / "steps.jsonl").read_text().splitlines() if line.strip()]
    actions = [r for r in records if r.get("kind") == "action" and r.get("device_action") and (r.get("result") or {}).get("ok")]
    replayed = 0
    for r in actions:
        screen = await device.wait_until_settled()
        recorded = load_tree(trace_dir / r["tree_before"])
        sim = jaccard(signature_keys(screen), signature_keys(recorded))
        if sim < SIMILARITY:
            res = await agent.run(goal, task_id=task_id, memory=memory)
            return {"status": res.status, "model_calls": res.model_calls, "cost_usd": round(res.cost_at_standard_usd, 5),
                    "duration_s": round(time.time() - t0, 2), "handoff_at": replayed + 1, "similarity": round(sim, 2),
                    "replayed": replayed, "result": res.result, "agent_steps": res.steps, "approvals": len(res.approvals)}
        a = r["device_action"]
        tgt = r.get("target") or {}
        x1, y1, x2, y2 = tgt.get("bounds", (0, 0, 0, 0))
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        if a["kind"] in ("tap", "long_press"):
            await device.act(Action(kind="tap_point", x=cx, y=cy))
        elif a["kind"] == "type":
            await device.act(Action(kind="tap_point", x=cx, y=cy))
            s = await device.wait_until_settled()
            field = next((e for e in s.numbered if e.editable and e.bounds[0] <= cx <= e.bounds[2] and e.bounds[1] <= cy <= e.bounds[3]), None)
            if field is not None:
                await device.act(Action(kind="type", element=field.number, text=a.get("text") or "", submit=a.get("submit", False)))
        elif a["kind"] == "scroll":
            await device.act(Action(kind="scroll", direction=a.get("direction") or "down"))
        elif a["kind"] == "back":
            await device.act(Action(kind="back"))
        replayed += 1
    await device.wait_until_settled()
    return {"status": "replayed", "model_calls": 0, "cost_usd": 0.0, "duration_s": round(time.time() - t0, 2), "handoff_at": None,
            "similarity": None, "replayed": replayed, "result": "", "agent_steps": 0, "approvals": 0}
