"""Replay recorded agent runs step by step on one checkout's prompts, screen code and history format.
  python replay_steps.py <checkout> <N per step> <out.json> <run dir>...
For each recorded decision, the step input is rebuilt as that checkout's loop would build it (its screen code on the saved
tree, its history lines from the recorded actions and screens, the run's plan, remembered text and screenshot), the step
model is called N times, and each answer is compared with the recorded decision: same kind of action on the same element
(or, for done, the same answer). Prints agreement per run and in total."""
import collections, gzip, inspect, json, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
root, N, out_path = Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
import os
specs = [p for a in sys.argv[4:] for p in (Path(a[1:]).read_text().split() if a.startswith("@") else [a])]
runs = [Path(p.split(":")[0]) for p in specs]
MAXS = {Path(p.split(":")[0]).name: int(p.split(":")[1]) for p in specs if ":" in p}
LAST_ONLY = os.environ.get("LAST_ONLY") == "1"
sys.path[:0] = [str(root / "backend"), str(Path(__file__).parent)]
from dotenv import load_dotenv
load_dotenv("/Users/sanjeevvarma/Desktop/Envoy/.claude/worktrees/aw-push-853c98/.env")
from agent import loop as L
from devices.types import Action
from models.adapter import ModelAdapter, image_part
from models.prompts import STEP_INSTRUCTIONS, step_input
from models.schemas import StepOutput, StepOutputListed
from rebuild import rebuild, load
has_step = "max_steps" in inspect.signature(step_input).parameters
scroll_note = getattr(L, "_scroll_note", None)
ad = ModelAdapter()

def norm(s): return re.sub(r"[^a-z0-9$.%]+", " ", (s or "").lower()).strip()

def same(rec, got, screen):
    a, b = rec["action"], got.action.model_dump()
    if a["type"] != b["type"]:
        return False
    if a["type"] == "done":
        return norm(a.get("result")) == norm(b.get("result"))
    if a["type"] in ("tap", "long_press", "type", "scroll") and a.get("element") is not None:
        if a.get("element") != b.get("element"):
            return False
        if a["type"] == "type":
            return norm(a.get("text")) == norm(b.get("text"))
        if a["type"] == "scroll":
            return a.get("direction") == b.get("direction")
    if a["type"] == "launch":
        return norm(a.get("app")) == norm(b.get("app"))
    return True

jobs = []
for d in runs:
    meta = json.load(open(d / "run.json"))
    recs = [json.loads(l) for l in open(d / "steps.jsonl")]
    plan = next((r.get("plan") for r in recs if r.get("kind") == "plan"), None) or {}
    plan_text = "\n".join(f"{i}. {s}" for i, s in enumerate(plan.get("subgoals") or [], 1))
    today = os.environ.get("TODAY") or (datetime.fromtimestamp(recs[0]["time"]).strftime("%A, %B %d %Y, %H:%M") if recs and recs[0].get("time") else "")
    history, remembered, visits, names, prev = [], [], {}, {}, None
    for r in recs:
        if r.get("kind") != "action" or not r.get("tree_before"):
            continue
        before = rebuild(load(d / r["tree_before"]))
        before.signature = load(d / r["tree_before"]).get("signature", "")
        sig = before.signature
        names.setdefault(sig, L._where(before).split(" · ", 1)[-1].strip("'\"") or before.activity.rsplit(".", 1)[-1])
        visits[sig] = visits.get(sig, 0) + 1
        visited = " · ".join(f"{names[k]} ×{n}" for k, n in visits.items())
        kw = dict(plan=plan_text, history="\n".join(history[-L.HISTORY_STEPS:]), memory="", feedback="", visited=visited, today=today,
                  remembered="\n".join(f"- {x}" for x in remembered))
        if has_step:
            kw.update(step=r["step"], max_steps=MAXS.get(d.name, 25))
        text = step_input(meta["goal"], before.compact, **kw)
        png = (d / r["screenshot_before"]).read_bytes() if r.get("screenshot_before") and (d / r["screenshot_before"]).exists() else None
        schema = StepOutput if (png is not None or len(before.numbered) < 3) else StepOutputListed
        scope = "test_app" if "-age-" in d.name or "-src-" in d.name else "real"
        if not LAST_ONLY or r["step"] == max(x["step"] for x in recs if x.get("kind") == "action"):
            jobs.append((d.name, r["step"], text, png, schema, r["decision"], before, scope))
        # the history line this checkout's loop would write after the recorded action
        dec = StepOutput.model_validate(r["decision"])
        desc = L._describe(dec, before)
        keep = (r["decision"].get("remember") or "").strip()
        if keep and keep not in remembered:
            remembered.append(keep)
        t = r["decision"]["action"]["type"]
        if t == "look":
            history.append(f"step {r['step']}: look → a screenshot comes with the next step"); continue
        if not r.get("tree_after"):
            continue
        after = rebuild(load(d / r["tree_after"]))
        after.signature = load(d / r["tree_after"]).get("signature", "")
        changed = r.get("changed", True)
        note = scroll_note(before, after, Action(**r["device_action"]), changed) if scroll_note and r.get("device_action") else None
        if not (r.get("result") or {}).get("ok", True):
            history.append(f"step {r['step']}: {desc} → FAILED: {(r.get('result') or {}).get('error')}")
        elif note is not None:
            history.append(f"step {r['step']}: {desc} → {note}")
        elif changed:
            history.append(f"step {r['step']}: {desc} → screen changed, now {L._where(after)}")
        else:
            history.append(f"step {r['step']}: {desc} → NO VISIBLE CHANGE")

def call(job_i):
    (run, step, text, png, schema, rec, before, scope), i = job_i
    content = [{"type": "input_text", "text": text}] + ([image_part(png)] if png else [])
    for attempt in range(3):
        try:
            res = ad.call("step", content, instructions=L.STEP_INSTRUCTIONS if hasattr(L, "STEP_INSTRUCTIONS") else STEP_INSTRUCTIONS,
                          data_scope=scope, contributor=False, task_id=f"awpush-replay-{run[-30:]}-{step}-{i}", effort="low", schema=schema)
            return run, step, rec["action"]["type"], res.parsed.action.model_dump(), same(rec, res.parsed, before), res.parsed.risk, rec.get("risk"), res.cost_usd
        except Exception as e:
            err = f"{type(e).__name__}: {e}"[:200]
            time.sleep(2)
    return run, step, rec["action"]["type"], {"error": err}, None, None, rec.get("risk"), 0.0

with ThreadPoolExecutor(6) as ex:
    out = list(ex.map(call, [(j, i) for j in jobs for i in range(N)]))
Path(out_path).write_text(json.dumps(out, indent=1, default=str))
per = collections.defaultdict(lambda: [0, 0])
for run, step, t, got, ok, risk, rrisk, c in out:
    per[run][0] += bool(ok); per[run][1] += 1
for run, (a, n) in sorted(per.items()):
    print(f"{run[-40:]:40} {a}/{n}")
ok = sum(1 for x in out if x[4]); errs = sum(1 for x in out if x[4] is None)
print(f"{root.name}: STEP line support {has_step}, steps {len(jobs)}, calls {len(out)}, agree {ok}/{len(out)}, errors {errs}, cost ${sum(x[-1] for x in out):.3f}")
