"""Where does "View the full contacts list" come from? The planner alone on the contacts loop run's first screen
(Envoy-realrun f7-1029142430), N plans per condition; counts plans asking for a full/complete/all list or for filters.
  python plan_attr.py main53 N out.json      main 53ab459's own planner prompt, schema and plan_input
  python plan_attr.py next2  N out.json      736a6e4's, and ablations of its prompt lines and inputs
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
from models.schemas import Plan
D = Path("/Users/sanjeevvarma/Desktop/Envoy-realrun/data/runs/f7-1029142430-real-contacts_count")
recs = [json.loads(l) for l in (D / "steps.jsonl").read_text().splitlines() if l.strip()]
goal = json.loads((D / "run.json").read_text())["goal"]
today = datetime.fromtimestamp(recs[0]["time"]).strftime("%A, %B %d %Y, %H:%M")
first = next(r for r in recs if r.get("kind") == "action")["screen_before"]["compact"]
APPS = ", ".join(json.loads(Path("/Users/sanjeevvarma/Desktop/Envoy-awfix/data/apps/labels.json").read_text()).values())
FULL = re.compile(r"\b(full|complete|entire|all (of )?(the |my )?contacts)\b|filter", re.I)
if which == "main53":
    C = {"main": (P.PLAN_INSTRUCTIONS, P.plan_input(goal, first, ""))}
else:
    F93 = (" A button shown with one item (on the card for the next trip, the last order, an open message) acts on that item only; "
           "if the goal names a different item, go through the list that holds it.")
    APP_NEW = "- app: the app the task needs, by its name as APPS ON THIS PHONE lists it (or its package), else null."
    APP_OLD = "- app: the Android package the task needs if you can tell (for example com.skylark.air for SkyLark Air), else null."
    assert F93 in P.PLAN_INSTRUCTIONS and APP_NEW in P.PLAN_INSTRUCTIONS
    main_text = P.PLAN_INSTRUCTIONS.replace(F93, "").replace(APP_NEW, APP_OLD)
    C = {"aw (736a6e4)": (P.PLAN_INSTRUCTIONS, P.plan_input(goal, first, "", "", APPS, today)),
         "aw, no APPS input": (P.PLAN_INSTRUCTIONS, P.plan_input(goal, first, "", "", "", today)),
         "aw, no TODAY input": (P.PLAN_INSTRUCTIONS, P.plan_input(goal, first, "", "", APPS, "")),
         "aw, neither input": (P.PLAN_INSTRUCTIONS, P.plan_input(goal, first, "", "", "", "")),
         "aw, no f93ce08 line": (P.PLAN_INSTRUCTIONS.replace(F93, ""), P.plan_input(goal, first, "", "", APPS, today)),
         "main's prompt, aw inputs": (main_text, P.plan_input(goal, first, "", "", APPS, today)),
         "main's prompt and inputs": (main_text, P.plan_input(goal, first, "", "", "", ""))}
ad = ModelAdapter()
def one(args):
    c, i = args
    for attempt in range(3):
        try:
            r = ad.call("plan", [{"type": "input_text", "text": C[c][1]}], instructions=C[c][0], data_scope="real", contributor=False,
                        task_id=f"pattr-{i}", effort="low", schema=Plan)
            return {"cond": c, "plan": r.parsed.subgoals, "full": bool(FULL.search(" ".join(r.parsed.subgoals))),
                    "tokens": r.usage.get("input_tokens"), "cost": r.cost_usd}
        except Exception as e:
            err = str(e)[:100]
    return {"cond": c, "error": err}
with ThreadPoolExecutor(6) as ex:
    out = list(ex.map(one, [(c, i) for c in C for i in range(N)]))
Path(out_path).write_text(json.dumps(out, indent=1))
print(f"cost ${sum(o.get('cost', 0) for o in out):.3f}; errors {sum(1 for o in out if 'error' in o)}; live plan tokens: loop run {recs[0]['usage']['input_tokens']}")
for c in C:
    rows = [o for o in out if o["cond"] == c and "error" not in o]
    print(f"{c:28} full/filter plans {sum(o['full'] for o in rows):>2}/{len(rows)}  tokens {sorted({o['tokens'] for o in rows})}")
