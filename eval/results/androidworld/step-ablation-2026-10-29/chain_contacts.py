"""contacts_count end to end at step 1, with the harness's NOTES: each version plans on the run's first screen, then takes
step 1 under its own plan, N times. main = 53ab459's own backend; 5fa03bf = 736a6e4 + edfab2b's planner line;
A = 5fa03bf + A3's done rule.  python chain_contacts.py <main53|abl0> <variants> N out.json"""
import collections, json, re, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
S = Path("/private/tmp/claude-501/-Users-sanjeevvarma-Desktop-Envoy/ac29808f-24a8-4c21-a4dc-a5afb3cedcad/scratchpad")
which, want, N, out_path = sys.argv[1], sys.argv[2].split(","), int(sys.argv[3]), sys.argv[4]
sys.path.insert(0, str(S / which / "backend"))
from models.adapter import ModelAdapter
from models import prompts as P
from models.schemas import Plan, StepOutput, StepOutputListed
src = open(S / "fix5/done_ab.py").read(); exec(src[src.index("def line_for"):src.index("def rebuild")])
irr = open(S / "fix5/irrev_ab.py").read(); exec(irr[irr.index("def rebuild_at"):irr.index("cases = []")])
NO_ACCOUNT = "Don't sign in, create an account or turn on sync; if asked, choose to continue without an account. Don't install anything."
D = Path("/Users/sanjeevvarma/Desktop/Envoy-realrun/data/runs/f7-1029151123-real-contacts_count")
recs = [json.loads(l) for l in (D / "steps.jsonl").read_text().splitlines() if l.strip()]
goal = json.loads((D / "run.json").read_text())["goal"]
today = datetime.fromtimestamp(recs[0]["time"]).strftime("%A, %B %d %Y, %H:%M")
APPS = ", ".join(json.loads(Path("/Users/sanjeevvarma/Desktop/Envoy-awfix/data/apps/labels.json").read_text()).values())
b = rebuild_at(D, goal, 1, today)
first = b["screen"]
if which == "main53":
    V = {"main": (P.STEP_INSTRUCTIONS, P.PLAN_INSTRUCTIONS)}
else:
    pl_old, pl_new, _ = json.load(open(S / "fix5/guard_variants.json"))["p_only"][0]
    dn_old, dn_new, _ = json.load(open(S / "fix5/done_variants.json"))["A3"][0]
    PLAN = P.PLAN_INSTRUCTIONS.replace(pl_old, pl_new); assert PLAN != P.PLAN_INSTRUCTIONS
    STEP_A = P.STEP_INSTRUCTIONS.replace(dn_old, dn_new); assert STEP_A != P.STEP_INSTRUCTIONS
    V = {"5fa03bf": (P.STEP_INSTRUCTIONS, PLAN), "A": (STEP_A, PLAN)}
V = {k: V[k] for k in want if k in V}
ad = ModelAdapter()
def one(args):
    v, i = args
    step_instr, plan_instr = V[v]
    pin = P.plan_input(goal, first, NO_ACCOUNT, "", APPS, today) if which != "main53" else P.plan_input(goal, first, NO_ACCOUNT)
    for attempt in range(3):
        try:
            pr = ad.call("plan", [{"type": "input_text", "text": pin}], instructions=plan_instr, data_scope="real", contributor=False,
                         task_id=f"cc-plan-{v}-{i}", effort="low", schema=Plan)
            kw = dict(plan="\n".join(f"{k}. {s}" for k, s in enumerate(pr.parsed.subgoals, 1)), history="", visited=b["visited"], memory=NO_ACCOUNT)
            if which != "main53": kw.update(today=today, remembered="")
            sr = ad.call("step", [{"type": "input_text", "text": P.step_input(goal, first, **kw)}], instructions=step_instr, data_scope="real",
                         contributor=False, task_id=f"cc-step-{v}-{i}", effort="low", schema=StepOutputListed)
            a = sr.parsed.action; el = getattr(a, "element", None); line = line_for(first, el) if el else ""
            kind = "answers" if a.type == "done" else ("opens filters" if "filter" in line.lower() else f"{a.type} {line[:25]}")
            return {"variant": v, "plan": pr.parsed.subgoals, "kind": kind, "plan_tokens": pr.usage.get("input_tokens"),
                    "step_tokens": sr.usage.get("input_tokens"), "cost": pr.cost_usd + sr.cost_usd}
        except Exception as e:
            err = str(e)[:100]
    return {"variant": v, "error": err}
with ThreadPoolExecutor(6) as ex:
    out = list(ex.map(one, [(v, i) for v in V for i in range(N)]))
Path(out_path).write_text(json.dumps(out, indent=1))
print(f"[{which}] cost ${sum(o.get('cost', 0) for o in out):.3f}; errors {sum(1 for o in out if 'error' in o)}; live plan {recs[0]['usage']['input_tokens']}, live step {next(r for r in recs if r.get('kind') == 'action')['usage']['input_tokens']}")
for v in V:
    rows = [o for o in out if o["variant"] == v and "error" not in o]
    print(f"  {v:8} {dict(collections.Counter(o['kind'] for o in rows).most_common())}  plan tokens {sorted({o['plan_tokens'] for o in rows})}  step tokens {sorted({o['step_tokens'] for o in rows})[:3]}")
