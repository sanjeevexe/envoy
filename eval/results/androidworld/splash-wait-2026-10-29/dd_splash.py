"""DoorDash's plan is made on its loading screen (plan input 680 tokens on main, 864 on 5fa03bf with NOTES). Rebuild that
screen as empty, check the token count against the live plan calls, then: plan N times (main 53ab459's planner, and
5fa03bf's), and run step 1 on the loaded home screen (the 5fa03bf run's own) under each plan: tap the address, or Account.
  python dd_splash.py <main53|abl0> N out.json
"""
import collections, json, re, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
S = Path("/private/tmp/claude-501/-Users-sanjeevvarma-Desktop-Envoy/ac29808f-24a8-4c21-a4dc-a5afb3cedcad/scratchpad")
which, N, out_path = sys.argv[1], int(sys.argv[2]), sys.argv[3]
sys.path.insert(0, str(S / which / "backend"))
from models.adapter import ModelAdapter
from models import prompts as P
from models.schemas import Plan, StepOutput, StepOutputListed
src = open(S / "fix5/done_ab.py").read(); exec(src[src.index("def line_for"):src.index("def rebuild")])
irr = open(S / "fix5/irrev_ab.py").read(); exec(irr[irr.index("def rebuild_at"):irr.index("cases = []")])
NO_ACCOUNT = "Don't sign in, create an account or turn on sync; if asked, choose to continue without an account. Don't install anything."
D = Path("/Users/sanjeevvarma/Desktop/Envoy-realrun/data/runs/f7-1029151123-real-doordash")
recs = [json.loads(l) for l in (D / "steps.jsonl").read_text().splitlines() if l.strip()]
goal = json.loads((D / "run.json").read_text())["goal"]
today = datetime.fromtimestamp(recs[0]["time"]).strftime("%A, %B %d %Y, %H:%M")
APPS = ", ".join(json.loads(Path("/Users/sanjeevvarma/Desktop/Envoy-awfix/data/apps/labels.json").read_text()).values())
SPLASH = "App: com.dd.doordash · Screen: SplashActivity · settled 1500 ms"
b = rebuild_at(D, goal, 1, today)   # the loaded home screen at step 1
ad = ModelAdapter()
import os
PLAN_SCREEN = b["screen"] if os.environ.get("LOADED") else SPLASH
PLAN_INSTR = P.PLAN_INSTRUCTIONS
if os.environ.get("GUARD"):
    _o, _n, _ = json.load(open(S / "fix5/guard_variants.json"))["p_only"][0]; assert _o in PLAN_INSTR; PLAN_INSTR = PLAN_INSTR.replace(_o, _n)
def one(i):
    pin = P.plan_input(goal, PLAN_SCREEN, NO_ACCOUNT, "", APPS, today) if which != "main53" else P.plan_input(goal, PLAN_SCREEN, NO_ACCOUNT)
    for attempt in range(3):
        try:
            pr = ad.call("plan", [{"type": "input_text", "text": pin}], instructions=PLAN_INSTR, data_scope="real", contributor=False,
                         task_id=f"dds-plan-{i}", effort="low", schema=Plan)
            plan_text = "\n".join(f"{k}. {s}" for k, s in enumerate(pr.parsed.subgoals, 1))
            kw = dict(plan=plan_text, history="", visited=b["visited"], memory=NO_ACCOUNT)
            if which != "main53": kw.update(today=today, remembered="")
            text = P.step_input(goal, b["screen"], **kw)
            sr = ad.call("step", [{"type": "input_text", "text": text}], instructions=P.STEP_INSTRUCTIONS, data_scope="real", contributor=False,
                         task_id=f"dds-step-{i}", effort="low", schema=StepOutputListed)
            el = getattr(sr.parsed.action, "element", None); line = line_for(b["screen"], el) if el else ""
            kind = "address" if "Hacker Way" in line else ("Account" if "Account" in line else f"{sr.parsed.action.type} {line[:25]}")
            return {"plan": pr.parsed.subgoals, "plan_tokens": pr.usage.get("input_tokens"), "step1": kind, "cost": pr.cost_usd + sr.cost_usd}
        except Exception as e:
            err = str(e)[:100]
    return {"error": err}
with ThreadPoolExecutor(6) as ex:
    out = list(ex.map(one, range(N)))
Path(out_path).write_text(json.dumps(out, indent=1))
ok = [o for o in out if "error" not in o]
route = lambda p: "account/profile" if re.search(r"account|profile", " ".join(p), re.I) and not re.search(r"address", p[1] if len(p) > 1 else "", re.I) else "address"
print(f"[{which}] cost ${sum(o.get('cost', 0) for o in out):.3f}; errors {len(out) - len(ok)}; plan tokens {sorted({o['plan_tokens'] for o in ok})} (live: main 680, 5fa03bf 864)")
print("step 1 on the loaded home:", dict(collections.Counter(o["step1"] for o in ok)))
print("plans' second subgoal:", collections.Counter(re.sub(r"\s+", " ", o["plan"][1].lower())[:40] if len(o["plan"]) > 1 else "" for o in ok).most_common(5))
