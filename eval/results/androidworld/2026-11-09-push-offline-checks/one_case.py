"""One safety case, N calls, natural goal only: what the step model picks and how it labels it.
  python one_case.py <checkout> <case id> <N> [step line on/off]"""
import collections, gzip, inspect, json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
root, cid, n = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
use_step = (sys.argv[4] if len(sys.argv) > 4 else "on") == "on"
sys.path[:0] = [str(root / "backend"), str(root / "eval"), str(Path(__file__).parent)]
from dotenv import load_dotenv
load_dotenv("/Users/sanjeevvarma/Desktop/Envoy/.claude/worktrees/aw-push-853c98/.env")
import final_safety as fs
from models.adapter import ModelAdapter
from models.prompts import STEP_INSTRUCTIONS, step_input
from rebuild import rebuild
has_step = "max_steps" in inspect.signature(step_input).parameters and use_step
c = next(c for c in fs.IRREVERSIBLE + fs.REVERSIBLE if c.id == cid)
s = rebuild(json.load(gzip.open(fs.SCREENS / f"{c.screen}.json.gz", "rt")))
el = fs.find_target(s, c)
ad = ModelAdapter()
def one(i):
    kw = {"step": 1, "max_steps": 25} if has_step else {}
    res = ad.call("step", [{"type": "input_text", "text": step_input(c.goal, s.compact, **kw)}], instructions=STEP_INSTRUCTIONS,
                  data_scope="real", contributor=False, task_id=f"awpush-case-{cid}-{i}", effort="low")
    d = res.parsed
    e = getattr(d.action, "element", None)
    lab = s.numbered[e - 1].label[:40] if e and 1 <= e <= len(s.numbered) else ""
    return (d.action.type, e == el.number, lab, d.risk, res.cost_usd)
with ThreadPoolExecutor(6) as ex:
    out = list(ex.map(one, range(n)))
print(root.name, "STEP line" if has_step else "no STEP line", f"${sum(x[-1] for x in out):.3f}")
print(collections.Counter((t, hit, lab, risk) for t, hit, lab, risk, _ in out).most_common())
print("target chosen and labelled irreversible:", sum(1 for t, hit, lab, risk, _ in out if hit and risk == "irreversible"), "/", n)
