"""AndroidWorld's question tasks under the answer-rule fix (b630d3f): replay, from final-standard's traces, the final done
step (is the answer the same?) and the step before it (does the fix answer too early, and with what?), N calls each.

  python aw_answer_ab.py N out.json [variants]      # variants from answer_fix_variants.json, plus "cur"
"""
import collections, json, re, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
S = Path("/private/tmp/claude-501/-Users-sanjeevvarma-Desktop-Envoy/ac29808f-24a8-4c21-a4dc-a5afb3cedcad/scratchpad")
BR = Path("/Users/sanjeevvarma/Desktop/Envoy-androidworld")
sys.path.insert(0, str(S / "next" / "backend"))
from models.adapter import ModelAdapter
from models.prompts import STEP_INSTRUCTIONS, step_input
from models.schemas import StepOutput, StepOutputListed
src = open(S / "fix5/done_ab.py").read()
exec(src[src.index("def line_for"):src.index("def rebuild")])
irr = open(S / "fix5/irrev_ab.py").read()
exec(irr[irr.index("def rebuild_at"):irr.index("cases = []")])
N = int(sys.argv[1]); out_path = sys.argv[2]
spec = json.loads((S / "fix5/answer_fix_variants.json").read_text())
want = (sys.argv[3] if len(sys.argv) > 3 else "cur,fix").split(",")
V = {"cur": STEP_INSTRUCTIONS}
for name, edits in spec.items():
    st = STEP_INSTRUCTIONS
    for old, new, where_ in edits:
        if where_ == "append": st = st + new
        elif where_ == "step": assert old in st; st = st.replace(old, new)
    V[name] = st
V = {k: V[k] for k in want}
TODAY = "Sunday, October 15 2023, 15:34"
norm = lambda s: re.sub(r"[^a-z0-9/]+", " ", (s or "").casefold()).strip()
cases = []  # (task, which, trace, goal, step, recorded answer, score)
for f in sorted((BR / "eval/results/androidworld/final-standard/episodes").glob("*.json")):
    ep = json.loads(f.read_text()); e = ep["envoy"]
    if "?" not in ep["goal"]: continue  # a question, by the request's own words
    t = BR / (e.get("trace_dir") or "x")
    if not (t / "steps.jsonl").exists(): continue
    acts = [json.loads(l) for l in (t / "steps.jsonl").read_text().splitlines() if l.strip()]
    acts = [r for r in acts if r.get("kind") == "action"]
    if not acts or (acts[-1]["decision"].get("action") or {}).get("type") != "done": continue
    ans = acts[-1]["decision"]["action"].get("result")
    cases.append((ep["task"], "final", t, ep["goal"], acts[-1]["step"], ans, ep.get("score")))
    if len(acts) > 1 and (acts[-2]["decision"].get("action") or {}).get("type") != "done":
        cases.append((ep["task"], "before", t, ep["goal"], acts[-2]["step"], ans, ep.get("score")))
# Phase 7's real-app rows on 1f1fc11 that ended in an answer (rule 7: our own cases beside the benchmark's)
from datetime import datetime
for d in sorted(Path("/Users/sanjeevvarma/Desktop/Envoy-awfix/data/runs").glob("f7-1029020238-real-*")):
    if "-input-" in d.name or not (d / "run.json").exists(): continue
    run = json.loads((d / "run.json").read_text())
    if run.get("status") != "done": continue
    recs = [json.loads(l) for l in (d / "steps.jsonl").read_text().splitlines() if l.strip()]
    acts = [r for r in recs if r.get("kind") == "action"]
    if not acts or (acts[-1]["decision"].get("action") or {}).get("type") != "done": continue
    today = datetime.fromtimestamp(recs[0]["time"]).strftime("%A, %B %d %Y, %H:%M")
    task = "real " + d.name.split("-real-", 1)[1]
    ans = acts[-1]["decision"]["action"].get("result")
    cases.append((task, "final", d, run["goal"], acts[-1]["step"], ans, 1.0, today))
    if len(acts) > 1 and (acts[-2]["decision"].get("action") or {}).get("type") != "done":
        cases.append((task, "before", d, run["goal"], acts[-2]["step"], ans, 1.0, today))
ad = ModelAdapter()
built = [(c, rebuild_at(c[2], c[3], c[4], c[7] if len(c) > 7 else TODAY)) for c in cases]
built = [(c, b) for c, b in built if b]
print(len(built), "cases:", collections.Counter(c[1] for c, _ in built), flush=True)
def one(args):
    c, b, v, i = args
    text = step_input(b["goal"], b["screen"], plan=b["plan"], history=b["history"], visited=b["visited"], today=b["today"], remembered=b["remembered"])
    n_el = sum(1 for l in b["screen"].split("\n") if l.startswith("["))
    for attempt in range(3):
        try:
            r = ad.call("step", [{"type": "input_text", "text": text}], instructions=V[v], data_scope="real", contributor=False,
                        task_id=f"awans-{v}-{i}", effort="low", schema=StepOutput if n_el < 3 else StepOutputListed)
            break
        except Exception as e:
            if attempt == 2: return {"task": c[0], "which": c[1], "variant": v, "error": str(e)[:120]}
    a = r.parsed.action
    res = getattr(a, "result", None) if a.type == "done" else None
    return {"task": c[0], "which": c[1], "variant": v, "score": c[6], "recorded": c[5], "action": a.type, "result": res,
            "same_answer": a.type == "done" and norm(res) == norm(c[5]), "cost": r.cost_usd}
jobs = [(c, b, v, i) for c, b in built for v in V for i in range(N)]
with ThreadPoolExecutor(6) as ex:
    out = list(ex.map(one, jobs))
Path(out_path).write_text(json.dumps(out, indent=1))
print(f"cost ${sum(o.get('cost', 0) for o in out):.3f}; errors {sum(1 for o in out if 'error' in o)}")
tab = collections.defaultdict(collections.Counter)
for o in out:
    if "error" in o: continue
    k = "same answer" if o["same_answer"] else ("done, other answer" if o["action"] == "done" else o["action"])
    tab[(o["which"], o["variant"], o["score"] == 1)][k] += 1
for (which, v, ok), c in sorted(tab.items()):
    print(f"{which:6} {'scored 1' if ok else 'scored 0':8} {v:10} {dict(c.most_common())}")
