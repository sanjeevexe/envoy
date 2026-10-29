"""Phase 7's real-app pass on 1f1fc11: read-only answers turned into verifying (contacts_count, doordash) or answers with
words the screen doesn't show (calendar_today). Offline: for each code/prompt variant, plan on the run's first screen with
that variant's planner, then that variant's step on the recorded screen (step 1, and DoorDash's step 2 on both paths).

  python realapp_ab.py dry  cur,no742,nof93,open N out.json     # 1f1fc11's backend and prompt variants of it
  python realapp_ab.py main main N out.json                     # main 8b5e9c2's backend, as is
"""
import json, re, sys, os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
S = Path("/private/tmp/claude-501/-Users-sanjeevvarma-Desktop-Envoy/ac29808f-24a8-4c21-a4dc-a5afb3cedcad/scratchpad")
which, variants, N, out_path = sys.argv[1], sys.argv[2].split(","), int(sys.argv[3]), sys.argv[4]
sys.path.insert(0, str(S / ("next" if which == "next" else "main8b5") / "backend"))
from models.adapter import ModelAdapter
from models import prompts as P
from models.schemas import Plan, StepOutput, StepOutputListed
src = open(S / "fix5/done_ab.py").read()
exec(src[src.index("def line_for"):src.index("def rebuild")])  # line_for, where
irr = open(S / "fix5/irrev_ab.py").read()
exec(irr[irr.index("def rebuild_at"):irr.index("cases = []")])  # rebuild_at (1f1fc11's history format)

NEW = Path("/Users/sanjeevvarma/Desktop/Envoy-awfix/data/runs")
OLD = Path("/Users/sanjeevvarma/Desktop/Envoy/data/runs")
labels = json.loads(Path("/Users/sanjeevvarma/Desktop/Envoy-awfix/data/apps/labels.json").read_text())
APPS = ", ".join(labels.values())

def recs(d): return [json.loads(l) for l in (d / "steps.jsonl").read_text().splitlines() if l.strip()]
def phone_time(t): return datetime.fromtimestamp(t).strftime("%A, %B %d %Y, %H:%M")

CASES = []  # (id, goal, plan screen, step screen run dir, step no, today)
for t, steps in (("contacts_count", [1]), ("doordash", [1, 2]), ("calendar_today", [1])):
    d = NEW / f"f7-1029020238-real-{t}"
    rr = recs(d)
    goal = json.loads((d / "run.json").read_text())["goal"]
    first = next(r for r in rr if r.get("kind") == "action")["screen_before"]["compact"]
    for k in steps:
        CASES.append((f"{t} s{k}" + (" (1f1fc11 path: Account)" if t == "doordash" and k == 2 else ""), goal, first, d, k, phone_time(rr[0]["time"])))
d = OLD / "f7-1028023735-real-doordash"
CASES.append(("doordash s2 (main path: saved addresses)", CASES[1][1], CASES[1][2], d, 2, CASES[1][5]))

RISK_OLD = "When unsure between reversible and irreversible, choose irreversible: the user will be asked to approve."
CHECK = (" Before an irreversible action, check that SCREEN, or REMEMBERED copied from an earlier screen, names the goal's own "
         "item (the flight, person, item or amount the goal names), not only a number or code for it. If it names a different one, "
         "or doesn't say, find out on the phone first: go back to the item, or the list it came from. Don't ask the user.")
REM_OLD, REM_NEW = "Copy it word for word.", "Copy it word for word from the screen; never add what the goal says."
PLAN_F93 = (" A button shown with one item (on the card for the next trip, the last order, an open message) acts on that item only; "
            "if the goal names a different item, go through the list that holds it.")
OPEN = ('A button that only opens a flow or its next screen, where a later step confirms (Checkout, Continue, Start), is "read"; '
        'the irreversible step is the one that commits (Confirm, Pay, Place order, Send), or a button that commits in one tap (Buy now, Delete).')
STEP, PLAN = P.STEP_INSTRUCTIONS, P.PLAN_INSTRUCTIONS
V = {"main": (STEP, PLAN)}
if which == "next":
    assert RISK_OLD + CHECK in STEP and REM_NEW in STEP and PLAN_F93 in PLAN
    V = {"cur": (STEP, PLAN),
         "no742": (STEP.replace(RISK_OLD + CHECK, RISK_OLD).replace(REM_NEW, REM_OLD), PLAN),
         "nof93": (STEP, PLAN.replace(PLAN_F93, "")),
         "open": (STEP.replace(RISK_OLD + CHECK, OPEN + " " + RISK_OLD + CHECK), PLAN)}
    extra = os.environ.get("EXTRA")  # a JSON file {name: [[old, new, "step"|"plan"], ...]} for fix candidates
    if extra:
        for name, edits in json.loads(Path(extra).read_text()).items():
            st, pl = STEP, PLAN
            for old, new, where_ in edits:
                if where_ == "append": st = st + new
                elif where_ == "step": assert old in st, (name, old); st = st.replace(old, new)
                else: assert old in pl, (name, old); pl = pl.replace(old, new)
            V[name] = (st, pl)

ad = ModelAdapter()
def plan_text_for(p): return "\n".join(f"{i}. {s}" for i, s in enumerate(p.subgoals, 1)) if p else ""
def one(args):
    case, v, i = args
    cid, goal, first, d, k, today = case
    step_instr, plan_instr = V[v]
    pin = P.plan_input(goal, first, "", "", APPS, today) if which == "next" else P.plan_input(goal, first, "")
    for attempt in range(3):
        try:
            if os.environ.get("RECORDED_PLAN"):  # the plan the live run made (on its own first screen), not a fresh one
                rec = next(json.loads(l) for l in (d / "steps.jsonl").read_text().splitlines() if '"kind": "plan"' in l)
                plan = Plan.model_validate(rec["plan"]) if which == "next" else type("P", (), {"subgoals": rec["plan"]["subgoals"]})()
                pr = type("R", (), {"cost_usd": 0.0, "usage": {}})()
            else:
                pr = ad.call("plan", [{"type": "input_text", "text": pin}], instructions=plan_instr, data_scope="real", contributor=False,
                             task_id=f"realab-plan-{v}-{i}", effort="low", schema=Plan)
                plan = pr.parsed
            b = rebuild_at(d, goal, k, today)
            kw = dict(plan=plan_text_for(plan), history=b["history"], visited=b["visited"])
            if which == "next": kw.update(today=today, remembered=b["remembered"])
            sin = P.step_input(goal, b["screen"], **kw)
            n_el = sum(1 for l in b["screen"].split("\n") if l.startswith("["))
            sr = ad.call("step", [{"type": "input_text", "text": sin}], instructions=step_instr, data_scope="real", contributor=False,
                         task_id=f"realab-step-{v}-{i}", effort="low", schema=StepOutput if n_el < 3 else StepOutputListed)
            break
        except Exception as e:
            if attempt == 2: return {"case": cid, "variant": v, "error": str(e)[:200]}
    a = sr.parsed.action
    el = getattr(a, "element", None)
    return {"case": cid, "variant": v, "plan": plan.subgoals if plan else None, "plan_tokens": pr.usage.get("input_tokens") if isinstance(pr.usage, dict) else None,
            "action": a.type, "element": el, "element_line": line_for(b["screen"], el) if el else "", "result": getattr(a, "result", None),
            "remember": getattr(sr.parsed, "remember", ""), "step_tokens": (sr.usage or {}).get("input_tokens") if isinstance(sr.usage, dict) else None, "reason": sr.parsed.reason, "risk": sr.parsed.risk,
            "screen_text": b["screen"], "cost": pr.cost_usd + sr.cost_usd}
jobs = [(c, v, i) for c in CASES for v in variants for i in range(N)]
with ThreadPoolExecutor(6) as ex:
    out = list(ex.map(one, jobs))
Path(out_path).write_text(json.dumps(out, indent=1))
print(f"cost ${sum(o.get('cost', 0) for o in out):.3f}; errors {sum(1 for o in out if 'error' in o)}")
