"""Which step-level change makes the merged agent second-guess a read-only answer? Replays recorded steps of Phase 7's
real-app runs (memory NOTES as the harness gives them) under 5fa03bf's step prompt and ablations of it, N calls each.
  python step_ablate.py <backend dir: abl0 | abl10b | main53> <variants> N out.json
"""
import collections, json, os, re, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
S = Path("/private/tmp/claude-501/-Users-sanjeevvarma-Desktop-Envoy/ac29808f-24a8-4c21-a4dc-a5afb3cedcad/scratchpad")
which, want, N, out_path = sys.argv[1], sys.argv[2].split(","), int(sys.argv[3]), sys.argv[4]
sys.path.insert(0, str(S / which / "backend"))
from models.adapter import ModelAdapter
from models import prompts as P
from models.schemas import StepOutput, StepOutputListed
src = open(S / "fix5/done_ab.py").read(); exec(src[src.index("def line_for"):src.index("def rebuild")])
irr = open(S / "fix5/irrev_ab.py").read(); exec(irr[irr.index("def rebuild_at"):irr.index("cases = []")])
NO_ACCOUNT = "Don't sign in, create an account or turn on sync; if asked, choose to continue without an account. Don't install anything."
R = Path("/Users/sanjeevvarma/Desktop/Envoy-realrun/data/runs")
CASES = [("contacts s1, clean plan (5fa03bf run)", "f7-1029151123-real-contacts_count", 1),
         ("contacts s1, full-list plan (736a6e4 run)", "f7-1029142430-real-contacts_count", 1),
         ("contacts s1, main's plan (main run)", "f7-1029135934-real-contacts_count", 1),
         ("doordash s5, Addresses (5fa03bf run)", "f7-1029151123-real-doordash", 5)]
STEP = P.STEP_INSTRUCTIONS
V = {}
if which in ("abl0", "abl10b"):
    CHECK = (" Before an irreversible action, check that SCREEN, or REMEMBERED copied from an earlier screen, names the goal's own "
             "item (the flight, person, item or amount the goal names), not only a number or code for it. If it names a different one, "
             "or doesn't say, find out on the phone first: go back to the item, or the list it came from. Don't ask the user.")
    REM_NEW, REM_OLD = "Copy it word for word from the screen; never add what the goal says.", "Copy it word for word."
    DONE_NEW = next(l for l in STEP.splitlines() if l.startswith("- done(result)"))
    DONE_MAIN = ("- done(result): the goal is reached. If the goal asks a question, result must state the answer exactly as the screen "
                 "shows it (for example \"Gate B12\"), and that answer must be visible on the current screen. Otherwise say briefly what you did.")
    TODAY_LINE = "- TODAY: the phone's own date and time when the task started. Words like today, tomorrow or this Thursday mean dates from it.\n"
    LOOK_LINE = "- Every action you return is carried out on the phone; there is no placeholder action. If you are unsure what to do, use look.\n"
    assert CHECK in STEP and REM_NEW in STEP and TODAY_LINE in STEP and LOOK_LINE in STEP
    base = "" if which == "abl0" else "no10b"
    def name(n): return (base + ("+" if base and n else "") + n) or "cur"
    V[name("")] = (STEP, True, True)
    V[name("notes_off")] = (STEP, False, True)
    V[name("no742")] = (STEP.replace(CHECK, "").replace(REM_NEW, REM_OLD), True, True)
    V[name("no_done")] = (STEP.replace(DONE_NEW, DONE_MAIN), True, True)
    V[name("no_today")] = (STEP.replace(TODAY_LINE, ""), True, False)
    V[name("no_look")] = (STEP.replace(LOOK_LINE, ""), True, True)
    V[name("no742+no_done")] = (STEP.replace(CHECK, "").replace(REM_NEW, REM_OLD).replace(DONE_NEW, DONE_MAIN), True, True)
    if os.environ.get("EXTRA"):
        for _n, _edits in json.loads(open(os.environ["EXTRA"]).read()).items():
            _st = STEP
            for _o, _new, _w in _edits:
                if _w == "append": _st = _st + _new
                else: assert _o in _st; _st = _st.replace(_o, _new)
            V[_n] = (_st, True, True)
else:
    V["main"] = (STEP, True, False)
V = {k: V[k] for k in want if k in V}
assert V, f"no variants {want} for {which}"
ad = ModelAdapter()
built = []
for cid, run, k in CASES:
    d = R / run
    recs = [json.loads(l) for l in (d / "steps.jsonl").read_text().splitlines() if l.strip()]
    goal = json.loads((d / "run.json").read_text())["goal"]
    today = datetime.fromtimestamp(recs[0]["time"]).strftime("%A, %B %d %Y, %H:%M")
    b = rebuild_at(d, goal, k, today)
    live = next(r for r in recs if r.get("kind") == "action" and r["step"] == k)
    built.append((cid, goal, today, b, live))

def classify(cid, b, a, risk):
    el = getattr(a, "element", None); line = line_for(b["screen"], el) if el else ""
    if cid.startswith("contacts"):
        return "answers" if a.type == "done" else ("opens filters" if "filter" in line.lower() else f"{a.type} {line[:28]}")
    return ("taps Addresses" if "Addresses" in line else f"{a.type} {line[:28]}") + (" [irreversible]" if risk == "irreversible" else "")

def one(args):
    (cid, goal, today, b, live), v, i = args
    instr, with_notes, with_today = V[v]
    kw = dict(plan=b["plan"], history=b["history"], visited=b["visited"], memory=NO_ACCOUNT if with_notes else "")
    if which != "main53":
        kw.update(today=today if with_today else "", remembered=b["remembered"])
    text = P.step_input(goal, b["screen"], **kw)
    n_el = sum(1 for l in b["screen"].split("\n") if l.startswith("["))
    for attempt in range(3):
        try:
            r = ad.call("step", [{"type": "input_text", "text": text}], instructions=instr, data_scope="real", contributor=False,
                        task_id=f"abl-{v}-{i}", effort="low", schema=StepOutput if n_el < 3 else StepOutputListed)
            return {"case": cid, "variant": v, "kind": classify(cid, b, r.parsed.action, r.parsed.risk), "reason": r.parsed.reason,
                    "tokens": r.usage.get("input_tokens"), "live_tokens": live["usage"].get("input_tokens"), "cost": r.cost_usd}
        except Exception as e:
            err = str(e)[:120]
    return {"case": cid, "variant": v, "error": err}

jobs = [(c, v, i) for c in built for v in V for i in range(N)]
with ThreadPoolExecutor(6) as ex:
    out = list(ex.map(one, jobs))
Path(out_path).write_text(json.dumps(out, indent=1))
print(f"[{which}] cost ${sum(o.get('cost', 0) for o in out):.3f}; errors {sum(1 for o in out if 'error' in o)}")
for c in built:
    rows = [o for o in out if o["case"] == c[0] and "error" not in o]
    print(f"== {c[0]} (live input {c[4]['usage'].get('input_tokens')} tokens)")
    for v in V:
        rr = [o for o in rows if o["variant"] == v]
        print(f"   {v:22} {dict(collections.Counter(o['kind'] for o in rr).most_common())}  tokens {sorted({o['tokens'] for o in rr})}")
