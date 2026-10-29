"""Replay the agent's first step on SkyLark's home screen (from 2b's traces) N times per condition and count the
template-like `back` (an action the screen doesn't call for, with a reason about tests, templates or the schema).

  uv run --project backend python <this> [N]
"""
import concurrent.futures as cf
import glob
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "backend"))
from models.adapter import ModelAdapter  # noqa: E402
from models.prompts import STEP_INSTRUCTIONS, step_input  # noqa: E402
from models.schemas import StepOutputListed  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
D = REPO / "eval/results/app-notes/2026-10-28/traces/skylark"
GOALS = {"denver_lands": "What time does my Denver flight land?", "bags_boston": "How many checked bags were on my Boston trip?"}
NOTES = Path(__file__).with_name("skylark-notes.txt").read_text()
FIX = ("\n- Every action must move toward the GOAL from the current SCREEN. There is no test of the format: never return a "
       "placeholder, template or trial action, and never leave the app the goal needs on the first step.")
BAD = re.compile(r"(?i)\b(test|testing|template|placeholder|schema|format)\b|why this action|actually tap")


def first_step(name: str) -> tuple[str, str]:
    """(plan text, screen) of that run's first step."""
    f = glob.glob(str(D / f"notes-skylark-{'cold' if name == 'denver_lands' else 'warm'}-{name}-*.jsonl"))[0]
    plan, screen = "", ""
    for line in open(f):
        r = json.loads(line)
        if r.get("kind") == "plan":
            plan = "\n".join(f"{i}. {s}" for i, s in enumerate((r.get("plan") or {}).get("subgoals", []), 1))
        if r.get("kind") == "action":
            screen = (r.get("screen_before") or {}).get("compact") or ""
            break
    return plan, screen


def one(adapter: ModelAdapter, name: str, notes: bool, fix: bool, i: int) -> dict:
    plan, screen = first_step(name)
    text = step_input(GOALS[name], screen, plan=plan, history="", memory="", feedback="", visited="Good morning, Maya ×1",
                      app_notes=NOTES if notes else "")
    res = adapter.call("step", [{"type": "input_text", "text": text}], instructions=STEP_INSTRUCTIONS + (FIX if fix else ""),
                       data_scope="test_app", contributor=False, task_id=f"probe-firststep-{name}-{int(notes)}{int(fix)}-{i}",
                       effort="low", schema=StepOutputListed)
    d = res.parsed
    a = d.action.type
    return {"action": a, "reason": d.reason, "bad": a == "back" or bool(BAD.search(d.reason)), "cost": res.cost_at_standard_usd}


def main() -> None:
    adapter = ModelAdapter()
    conds = [(n, notes, fix) for n in GOALS for notes in (False, True) for fix in (False, True)]
    jobs = [(c, i) for c in conds for i in range(N)]
    out: dict = {}
    with cf.ThreadPoolExecutor(8) as ex:
        futs = {ex.submit(one, adapter, *c, i): c for c, i in jobs}
        for f in cf.as_completed(futs):
            c = futs[f]
            try:
                out.setdefault(c, []).append(f.result())
            except Exception as e:  # noqa: BLE001
                out.setdefault(c, []).append({"action": "error", "reason": str(e)[:80], "bad": False, "cost": 0})
    total = 0.0
    for c in conds:
        rs = out.get(c, [])
        total += sum(r["cost"] for r in rs)
        acts = {}
        for r in rs:
            acts[r["action"]] = acts.get(r["action"], 0) + 1
        print(f"{c[0]:13} notes={'on ' if c[1] else 'off'} fix={'on ' if c[2] else 'off'}: back/template {sum(r['bad'] for r in rs)}/{len(rs)}  {acts}")
        for r in rs:
            if r["bad"]:
                print(f"      {r['action']}: {r['reason'][:100]}")
    print(f"cost ${total:.3f}")


if __name__ == "__main__":
    main()
