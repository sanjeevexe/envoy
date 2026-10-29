"""Phase 7's contacts_count loop on 736a6e4: plans that say "View the full contacts list" send the step into the list's
filters. Offline, on the loop run's own first screen (Envoy-realrun f7-1029142430), on 736a6e4's prompts:
  plan   the planner alone, N plans per variant: how many ask for a "full"/"complete"/"all" list, or for filters
  step   step 1 under the loop run's recorded plan, N per variant: answers at once, or opens filters
  chain  each variant's own plan, then its step 1, N per variant
  python contacts_guard_ab.py N out.json cur,s_guard,p_guard,both
"""
import collections, json, re, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
S = Path("/private/tmp/claude-501/-Users-sanjeevvarma-Desktop-Envoy/ac29808f-24a8-4c21-a4dc-a5afb3cedcad/scratchpad")
sys.path.insert(0, str(S / "next2" / "backend"))
from models.adapter import ModelAdapter
from models import prompts as P
from models.schemas import Plan, StepOutput, StepOutputListed
src = open(S / "fix5/done_ab.py").read()
exec(src[src.index("def line_for"):src.index("def rebuild")])
irr = open(S / "fix5/irrev_ab.py").read()
exec(irr[irr.index("def rebuild_at"):irr.index("cases = []")])
N, out_path, want = int(sys.argv[1]), sys.argv[2], sys.argv[3].split(",")
D = Path("/Users/sanjeevvarma/Desktop/Envoy-realrun/data/runs/f7-1029142430-real-contacts_count")
recs = [json.loads(l) for l in (D / "steps.jsonl").read_text().splitlines() if l.strip()]
goal = json.loads((D / "run.json").read_text())["goal"]
today = datetime.fromtimestamp(recs[0]["time"]).strftime("%A, %B %d %Y, %H:%M")
first = next(r for r in recs if r.get("kind") == "action")["screen_before"]["compact"]
live_plan = next(r["plan"] for r in recs if r.get("kind") == "plan")
labels = json.loads(Path("/Users/sanjeevvarma/Desktop/Envoy-awfix/data/apps/labels.json").read_text())
APPS = ", ".join(labels.values())

STEP_OLD = "don't switch filters or settings to look for a different answer."
STEP_NEW = "don't switch filters or settings to look for a different answer. A list answers as the app shows it (scroll it if it goes on), even when the plan says the full or complete list: don't open its filters, sorting or settings to check it."
PLAN_OLD = 'phrased as screens or outcomes ("Open the trip to Chicago", "Confirm check-in").'
PLAN_NEW = 'phrased as screens or outcomes ("Open the trip to Chicago", "Confirm check-in"). For a question, read the answer where the app shows it, an empty state ("none yet") included; plan no step that changes filters or settings, and no "full" or "complete" list unless the goal asks for one.'
assert STEP_OLD in P.STEP_INSTRUCTIONS and PLAN_OLD in P.PLAN_INSTRUCTIONS
V = {"cur": (P.STEP_INSTRUCTIONS, P.PLAN_INSTRUCTIONS),
     "s_guard": (P.STEP_INSTRUCTIONS.replace(STEP_OLD, STEP_NEW), P.PLAN_INSTRUCTIONS),
     "p_guard": (P.STEP_INSTRUCTIONS, P.PLAN_INSTRUCTIONS.replace(PLAN_OLD, PLAN_NEW)),
     "both": (P.STEP_INSTRUCTIONS.replace(STEP_OLD, STEP_NEW), P.PLAN_INSTRUCTIONS.replace(PLAN_OLD, PLAN_NEW))}
import os
for _name, _edits in (json.loads(open(os.environ["EXTRA"]).read()).items() if os.environ.get("EXTRA") else []):
    _st, _pl = P.STEP_INSTRUCTIONS, P.PLAN_INSTRUCTIONS
    for _o, _n, _w in _edits:
        if _w == "step": assert _o in _st; _st = _st.replace(_o, _n)
        else: assert _o in _pl; _pl = _pl.replace(_o, _n)
    V[_name] = (_st, _pl)
V = {k: V[k] for k in want}
FULL = re.compile(r"\b(full|complete|entire|all (of )?(the |my )?contacts)\b|filter", re.I)
ad = ModelAdapter()
b = rebuild_at(D, goal, 1, today)

def plan_call(v, i):
    r = ad.call("plan", [{"type": "input_text", "text": P.plan_input(goal, first, "", "", APPS, today)}], instructions=V[v][1],
                data_scope="real", contributor=False, task_id=f"cg-plan-{v}-{i}", effort="low", schema=Plan)
    return r

def step_call(v, i, plan_subgoals):
    text = P.step_input(goal, b["screen"], plan="\n".join(f"{k}. {s}" for k, s in enumerate(plan_subgoals, 1)), history=b["history"],
                        visited=b["visited"], today=today, remembered=b["remembered"])
    n_el = sum(1 for l in b["screen"].split("\n") if l.startswith("["))
    return ad.call("step", [{"type": "input_text", "text": text}], instructions=V[v][0], data_scope="real", contributor=False,
                   task_id=f"cg-step-{v}-{i}", effort="low", schema=StepOutput if n_el < 3 else StepOutputListed)

def kind(a):
    line = line_for(b["screen"], getattr(a, "element", None)) if getattr(a, "element", None) else ""
    if a.type == "done": return "answers"
    if "filter" in line.lower(): return "opens filters"
    return f"{a.type} {line[:30]}"

def one(args):
    mode, v, i = args
    for attempt in range(3):
        try:
            if mode == "plan":
                r = plan_call(v, i); p = r.parsed
                return {"mode": mode, "variant": v, "plan": p.subgoals, "full": bool(FULL.search(" ".join(p.subgoals))),
                        "tokens": r.usage.get("input_tokens"), "cost": r.cost_usd}
            if mode == "step":
                r = step_call(v, i, live_plan["subgoals"])
                return {"mode": mode, "variant": v, "kind": kind(r.parsed.action), "reason": r.parsed.reason,
                        "tokens": r.usage.get("input_tokens"), "cost": r.cost_usd}
            pr = plan_call(v, i); sr = step_call(v, i, pr.parsed.subgoals)
            return {"mode": mode, "variant": v, "plan": pr.parsed.subgoals, "full": bool(FULL.search(" ".join(pr.parsed.subgoals))),
                    "kind": kind(sr.parsed.action), "reason": sr.parsed.reason, "cost": pr.cost_usd + sr.cost_usd}
        except Exception as e:
            err = str(e)[:120]
    return {"mode": mode, "variant": v, "error": err}

jobs = [(m, v, i) for m in ("plan", "step", "chain") for v in V for i in range(N)]
with ThreadPoolExecutor(6) as ex:
    out = list(ex.map(one, jobs))
Path(out_path).write_text(json.dumps(out, indent=1))
print(f"cost ${sum(o.get('cost', 0) for o in out):.3f}; errors {sum(1 for o in out if 'error' in o)}; live plan tokens "
      f"{recs[0]['usage']['input_tokens']}, live step tokens {next(r for r in recs if r.get('kind') == 'action')['usage']['input_tokens']}")
for m in ("plan", "step", "chain"):
    for v in V:
        rows = [o for o in out if o["mode"] == m and o["variant"] == v and "error" not in o]
        toks = sorted({o.get("tokens") for o in rows if o.get("tokens")})
        if m == "plan":
            print(f"plan  {v:8} 'full'/filter plans {sum(o['full'] for o in rows)}/{len(rows)}  tokens {toks}")
        elif m == "step":
            print(f"step  {v:8} {dict(collections.Counter(o['kind'] for o in rows))}  tokens {toks}")
        else:
            print(f"chain {v:8} {dict(collections.Counter(o['kind'] for o in rows))}  'full' plans {sum(o['full'] for o in rows)}/{len(rows)}")
