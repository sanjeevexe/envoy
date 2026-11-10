"""Replay a recorded replan on one checkout's planner: the same goal, screen, visited screens and apps, plus (where the
checkout has them) what was done and kept. python replan_ab.py <checkout> <N> <out.json> <trace dir>:<replan step> ..."""
import inspect, json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
root, N, out_path = Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
sys.path[:0] = [str(root / "backend"), str(Path(__file__).parent)]
from dotenv import load_dotenv
load_dotenv("/Users/sanjeevvarma/Desktop/Envoy/.claude/worktrees/aw-push-853c98/.env")
from agent import loop as L
from devices.types import Action
from models.adapter import ModelAdapter
from models.prompts import PLAN_INSTRUCTIONS, plan_input
from models.schemas import StepOutput
from rebuild import rebuild, load
has_done = "done_so_far" in inspect.signature(plan_input).parameters
APPS = ", ".join(json.load(open("/Users/sanjeevvarma/Desktop/Envoy-aw-compare/data/apps/labels.json")).values()) if False else ""
labels = json.load(open("/Users/sanjeevvarma/Desktop/Envoy-aw-compare/data/apps/labels.json"))
APPS = ", ".join(sorted({v if isinstance(v, str) else v.get("label", "") for v in labels.values()}))
TODAY = "Sunday, October 15 2023, 15:34"
ad = ModelAdapter()
jobs = []
for spec in sys.argv[4:]:
    d, k = spec.rsplit(":", 1); d, k = Path(d), int(k)
    goal = json.load(open(d / "run.json"))["goal"]
    recs = [json.loads(l) for l in open(d / "steps.jsonl")]
    rp = next(r for r in recs if r.get("kind") == "replan" and r["step"] == k)
    history, remembered, screen = [], [], None
    for r in recs:
        if r.get("kind") == "popup":
            history.append(f"(runtime) dismissed a pop-up: {r.get('handler')}"); continue
        if r.get("kind") == "replan" and r["step"] < k:
            history.append(f"(runtime) going in circles: replanned"); continue
        if r.get("kind") != "action" or r["step"] >= k:
            if r.get("kind") == "action" and r["step"] == k:
                screen = rebuild(load(d / r["tree_before"]))
            continue
        before = rebuild(load(d / r["tree_before"]))
        dec = StepOutput.model_validate(r["decision"])
        keep = (r["decision"].get("remember") or "").strip()
        if keep and keep not in remembered:
            remembered.append(keep)
        desc = L._describe(dec, before)
        t = r["decision"]["action"]["type"]
        if t == "look":
            history.append(f"step {r['step']}: look → a screenshot comes with the next step"); continue
        if t == "done":
            history.append(f"step {r['step']}: done rejected by the success check"); continue
        if not r.get("tree_after"):
            continue
        after = rebuild(load(d / r["tree_after"]))
        history.append(f"step {r['step']}: {desc} → " + ("screen changed, now " + L._where(after) if r.get("changed", True) else "NO VISIBLE CHANGE")
                       + (" (approved)" if r.get("approval") else ""))
    kw = {"done_so_far": "\n".join(history[-20:]), "remembered": "\n".join(f"- {x}" for x in remembered)} if has_done else {}
    text = plan_input(goal, screen.compact, "", rp["tried"], APPS, TODAY, **kw)
    jobs += [(d.name, k, text, i) for i in range(N)]

def call(j):
    name, k, text, i = j
    res = ad.call("plan", [{"type": "input_text", "text": text}], instructions=PLAN_INSTRUCTIONS, data_scope="test_app",
                  contributor=False, task_id=f"awpush-replan-{name[-12:]}-{k}-{i}", effort="low")
    return name, k, res.parsed.model_dump() if res.parsed else None, res.cost_usd
with ThreadPoolExecutor(6) as ex:
    out = list(ex.map(call, jobs))
Path(out_path).write_text(json.dumps(out, indent=1))
print(root.name, "DONE SO FAR:", has_done, f"${sum(x[-1] for x in out):.3f}")
for name, k, plan, c in out:
    print(f"--- {name[-28:]} replan@{k}: " + " | ".join((plan or {}).get("subgoals") or []))
