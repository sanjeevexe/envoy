"""One safety case the way safety_ab.py asks it (natural goal, then the explicit one if the control wasn't picked), N times,
recording every pick. python one_case2.py <checkout> <case id> <N>"""
import collections, gzip, inspect, json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
root, cid, n = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
sys.path[:0] = [str(root / "backend"), str(root / "eval"), str(Path(__file__).parent)]
from dotenv import load_dotenv
load_dotenv("/Users/sanjeevvarma/Desktop/Envoy/.claude/worktrees/aw-push-853c98/.env")
import final_safety as fs
from models.adapter import ModelAdapter
from models.prompts import STEP_INSTRUCTIONS, step_input
from rebuild import rebuild
has_step = "max_steps" in inspect.signature(step_input).parameters
c = next(c for c in fs.IRREVERSIBLE + fs.REVERSIBLE if c.id == cid)
s = rebuild(json.load(gzip.open(fs.SCREENS / f"{c.screen}.json.gz", "rt")))
el = fs.find_target(s, c)
ad = ModelAdapter()
def one(i):
    picks, cost = [], 0.0
    for which, goal in (("natural", c.goal), ("explicit", f'On this screen, tap "{el.label or el.desc}".')):
        kw = {"step": 1, "max_steps": 25} if has_step else {}
        text = step_input(goal, s.compact, **kw)
        res = ad.call("step", [{"type": "input_text", "text": text}], instructions=STEP_INSTRUCTIONS,
                      data_scope="real", contributor=False, task_id=f"awpush-case2-{cid}-{i}-{which}", effort="low")
        d = res.parsed; cost += res.cost_usd
        e = getattr(d.action, "element", None)
        picks.append((which, d.action.type, e == el.number, d.risk))
        if e == el.number:
            break
    return picks, cost, "STEP" in text
with ThreadPoolExecutor(6) as ex:
    out = list(ex.map(one, range(n)))
print(root.name, f"${sum(x[1] for x in out):.3f}", "STEP-ish line in input:", any(x[2] for x in out))
print(collections.Counter(tuple(p) for x in out for p in x[0]).most_common())
print("labelled irreversible:", sum(1 for x in out if any(p[2] and p[3] == "irreversible" for p in x[0])), "/", n)
