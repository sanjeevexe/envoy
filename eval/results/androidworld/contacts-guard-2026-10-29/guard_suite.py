"""The contacts guard (guard_variants.json) beside what it could break, on 736a6e4's prompts (BACKEND=next2):
  skylark  the planner on SkyLark's home screen, check-in for another trip: plans whose first subgoal offers Home's
           "Check in" (f93ce08's case: must stay 0), and for the next trip itself (the button stays the route)
  aw       AndroidWorld's question tasks (final-standard, "?" in the goal): plan on the first screen, then step 1;
           a done at step 1 is premature (these all need opening something first)
  python guard_suite.py N out.json cur,guard
"""
import collections, json, os, re, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
S = Path("/private/tmp/claude-501/-Users-sanjeevvarma-Desktop-Envoy/ac29808f-24a8-4c21-a4dc-a5afb3cedcad/scratchpad")
BR = Path("/Users/sanjeevvarma/Desktop/Envoy-androidworld")
sys.path.insert(0, str(S / os.environ.get("BACKEND", "next2") / "backend"))
from models.adapter import ModelAdapter
from models import prompts as P
from models.schemas import Plan, StepOutput, StepOutputListed
src = open(S / "fix5/done_ab.py").read(); exec(src[src.index("def line_for"):src.index("def rebuild")])
irr = open(S / "fix5/irrev_ab.py").read(); exec(irr[irr.index("def rebuild_at"):irr.index("cases = []")])
N, out_path, want = int(sys.argv[1]), sys.argv[2], sys.argv[3].split(",")
spec = json.loads((S / "fix5/guard_variants.json").read_text())
V = {"cur": (P.STEP_INSTRUCTIONS, P.PLAN_INSTRUCTIONS)}
for name, edits in spec.items():
    st, pl = P.STEP_INSTRUCTIONS, P.PLAN_INSTRUCTIONS
    for old, new, w in edits:
        if w == "step": assert old in st; st = st.replace(old, new)
        else: assert old in pl; pl = pl.replace(old, new)
    V[name] = (st, pl)
V = {k: V[k] for k in want}
ad = ModelAdapter()
# SkyLark (plan_ab.py's case)
run = Path("/Users/sanjeevvarma/Desktop/Envoy-phase6/data/runs/f7-1028205457-age-check_in-L0-s101-t1")
sk_screen = [json.loads(l) for l in run.joinpath("steps.jsonl").read_text().splitlines()][1]["screen_before"]["compact"]
sk_apps = ", ".join(json.loads(Path("/Users/sanjeevvarma/Desktop/Envoy-phase6/data/apps/labels.json").read_text()).values())
sk_today = "Wednesday, October 28 2026, 20:54"
SK_GOALS = {"other": ["Check me in for my flight to Denver.", "Check me in for my flight to Pittsburgh."], "next": ["Check me in for my flight to Chicago."]}
offers = lambda s: bool(re.search(r"check[- ]?in\b", s, re.I)) and not re.search(r"^(open|go to|tap) (my )?trips\b[^,]*$", s, re.I)
# AndroidWorld question tasks
aw = []
for f in sorted((BR / "eval/results/androidworld/final-standard/episodes").glob("*.json")):
    ep = json.loads(f.read_text()); e = ep["envoy"]
    if "?" not in ep["goal"]: continue
    t = BR / (e.get("trace_dir") or "x")
    if not (t / "steps.jsonl").exists(): continue
    recs = [json.loads(l) for l in (t / "steps.jsonl").read_text().splitlines() if l.strip()]
    a1 = next((r for r in recs if r.get("kind") == "action"), None)
    if a1: aw.append((ep["task"], ep["goal"], t, a1["screen_before"]["compact"]))
AW_TODAY = "Sunday, October 15 2023, 15:34"
AW_APPS = ", ".join(json.loads((BR / "data/apps/labels.json").read_text()).values())
FILTERS = re.compile(r"\bfilter|\bsettings?\b|\bsort", re.I)

def one(args):
    kind, item, v, i = args
    step_instr, plan_instr = V[v]
    for attempt in range(3):
        try:
            if kind == "skylark":
                which, goal = item
                r = ad.call("plan", [{"type": "input_text", "text": P.plan_input(goal, sk_screen, "", "", sk_apps, sk_today)}], instructions=plan_instr,
                            data_scope="test_app", contributor=False, task_id=f"gs-sk-{v}-{i}", effort="low", schema=Plan)
                return {"kind": kind, "which": which, "variant": v, "first": r.parsed.subgoals[0], "offers": offers(r.parsed.subgoals[0]), "cost": r.cost_usd}
            task, goal, t, screen = item
            pr = ad.call("plan", [{"type": "input_text", "text": P.plan_input(goal, screen, "", "", AW_APPS, AW_TODAY)}], instructions=plan_instr,
                         data_scope="real", contributor=False, task_id=f"gs-aw-plan-{v}-{i}", effort="low", schema=Plan)
            b = rebuild_at(t, goal, 1, AW_TODAY)
            text = P.step_input(goal, b["screen"], plan="\n".join(f"{k}. {s}" for k, s in enumerate(pr.parsed.subgoals, 1)), history="",
                                visited=b["visited"], today=AW_TODAY, remembered="")
            n_el = sum(1 for l in b["screen"].split("\n") if l.startswith("["))
            sr = ad.call("step", [{"type": "input_text", "text": text}], instructions=step_instr, data_scope="real", contributor=False,
                         task_id=f"gs-aw-step-{v}-{i}", effort="low", schema=StepOutput if n_el < 3 else StepOutputListed)
            return {"kind": kind, "task": task, "variant": v, "plan": pr.parsed.subgoals, "filters": bool(FILTERS.search(" ".join(pr.parsed.subgoals))),
                    "step1": sr.parsed.action.type, "cost": pr.cost_usd + sr.cost_usd}
        except Exception as e:
            err = str(e)[:120]
    return {"kind": kind, "variant": v, "error": err}

jobs = [("skylark", (w, g), v, i) for w, gs in SK_GOALS.items() for g in gs for v in V for i in range(N)]
jobs += [] if os.environ.get("ONLY_SK") else [("aw", a, v, i) for a in aw for v in V for i in range(max(2, N // 4))]
with ThreadPoolExecutor(6) as ex:
    out = list(ex.map(one, jobs))
Path(out_path).write_text(json.dumps(out, indent=1, default=str))
print(f"cost ${sum(o.get('cost', 0) for o in out):.3f}; errors {sum(1 for o in out if 'error' in o)}; AW question tasks {len(aw)}")
for v in V:
    sk = [o for o in out if o["kind"] == "skylark" and o["variant"] == v and "error" not in o]
    for w in SK_GOALS:
        rows = [o for o in sk if o["which"] == w]
        print(f"skylark {v:7} {w:5} first subgoal offers Home's Check in: {sum(o['offers'] for o in rows)}/{len(rows)}")
    a = [o for o in out if o["kind"] == "aw" and o["variant"] == v and "error" not in o]
    print(f"aw      {v:7} plans with a filter/settings/sort step {sum(o['filters'] for o in a)}/{len(a)}; step 1 done (premature) "
          f"{sum(o['step1'] == 'done' for o in a)}/{len(a)}; step 1 actions {dict(collections.Counter(o['step1'] for o in a))}")
