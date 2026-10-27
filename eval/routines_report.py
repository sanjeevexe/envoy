"""Build eval/results/phase2/report.md from the routines suites' JSON results.

  uv run --project backend python eval/routines_report.py
"""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "eval" / "results" / "phase2"
VARIANTS = {0: "original", 1: "moved button", 2: "renamed labels", 3: "extra screen", 4: "hidden IDs", 5: "renamed + hidden IDs"}
RUNGS = {0: "none needed", 1: "wait and retry", 2: "relaxed match", 3: "pop-up handler", 4: "local repair", 5: "full agent", 6: "ask the user"}


def load(name: str) -> dict | None:
    p = OUT / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def med(xs: list[float]) -> float:
    return round(statistics.median(xs), 2) if xs else 0.0


def pct(a: int, b: int) -> str:
    return f"{a}/{b} ({a / b:.0%})" if b else "–"


def compile_table(tag: str, title: str) -> list[str]:
    c = load(f"compile{tag}")
    if not c:
        return []
    lines = [f"### {title}", "", "| Family | Routine | Steps | Inputs | Outputs | Trace steps dropped | Compiler | Compile cost | Verified (same / second inputs) |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in c["rows"]:
        if not r.get("compiled"):
            lines.append(f"| {r['family']} | not compiled: {r.get('error', '')[:60]} | | | | | | | |")
            continue
        ver = " / ".join("✅" if v["passed"] else f"❌ {v['detail'][:40]}" for v in r["verify"])
        lines.append(f"| {r['family']} | `{r['routine']}` | {r['steps']} | {', '.join(r['inputs'])} | {', '.join(r['outputs'])} | {len(r['dropped'])} | "
                     f"{'muse-wonder-1.0 (cached answer)' if r['compiler'] == 'cached' else r['compiler']} | ${r['compile_cost_usd']:.3f} | {ver} |")
    return lines + [""]


def new_inputs_table(tag: str, title: str) -> tuple[list[str], dict]:
    d = load(f"new_inputs{tag}")
    if not d:
        return [], {}
    rows = d["rows"]
    by = defaultdict(list)
    for r in rows:
        by[r["family"]].append(r)
    lines = [f"### {title}", "", "| Family | Runs | Success | Model calls (total) | Median time | Max time |", "| --- | --- | --- | --- | --- | --- |"]
    for fam, rs in by.items():
        lines.append(f"| {fam} | {len(rs)} | {pct(sum(r['passed'] for r in rs), len(rs))} | {sum(r['model_calls'] for r in rs)} | "
                     f"{med([r['duration_s'] for r in rs])} s | {max(r['duration_s'] for r in rs)} s |")
    ok = sum(r["passed"] for r in rows)
    lines.append(f"| **all** | {len(rows)} | **{pct(ok, len(rows))}** | {sum(r['model_calls'] for r in rows)} | {med([r['duration_s'] for r in rows])} s | "
                 f"{max(r['duration_s'] for r in rows)} s |")
    fails = [r for r in rows if not r["passed"]]
    if fails:
        lines += ["", "Failures:"] + [f"- {r['family']} on {r['city']}: {r['status']} — {r['detail'][:120]}" for r in fails]
    return lines + [""], {"runs": len(rows), "ok": ok}


def variants_tables(tag: str, title: str) -> list[str]:
    d = load(f"variants{tag}")
    if not d:
        return []
    exps = d["experiments"]
    lines = [f"### {title}", "",
             "| Change | Experiments | Recovered | Saved by (highest rung) | Model calls | Median time | Cost | Patches | Trial passed | Patched version alone (0 model calls) | Still works on the original layout |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    by_v = defaultdict(list)
    for e in exps:
        by_v[e["variant"]].append(e)
    for v, es in sorted(by_v.items()):
        firsts = [e["first"] for e in es]
        rec = sum(f["passed"] for f in firsts)
        rungs = Counter(RUNGS[f["rung"]] for f in firsts)
        patches = Counter(p["kind"] for f in firsts for p in f["patches"])
        trials = [e["trial"] for e in es if e.get("trial")]
        alone = [e["after"] for e in es if e.get("trial") and e["trial"]["passed"]]
        alone_ok = sum(1 for a in alone if a["passed"] and a["model_calls"] == 0)
        back = [e["backcompat"] for e in es if e.get("backcompat")]
        lines.append(f"| {v}: {VARIANTS.get(v, v)} | {len(es)} | {pct(rec, len(es))} | {', '.join(f'{k} ×{n}' for k, n in rungs.most_common())} | "
                     f"{sum(f['model_calls'] for f in firsts)} | {med([f['duration_s'] for f in firsts])} s | ${sum(f['cost_usd'] for f in firsts):.4f} | "
                     f"{', '.join(f'{k} ×{n}' for k, n in patches.most_common()) or '–'} | {pct(sum(t['passed'] for t in trials), len(trials))} | "
                     f"{pct(alone_ok, len(alone))} | {pct(sum(b['passed'] for b in back), len(back))} |")
    lines += ["", "Per experiment:", "", "| Routine | Change | First run | Rung | Calls | Time | Patches | Trial | Next run | Original layout |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for e in exps:
        f = e["first"]
        t = e.get("trial")
        a = e.get("after")
        b = e.get("backcompat")
        pdesc = "; ".join(p["description"][:90] for p in f["patches"]) or "–"
        lines.append(f"| {e['family']} | {e['variant']} | {'✅' if f['passed'] else '❌'} {f['status']} | {f['rung']} | {f['model_calls']} | {f['duration_s']} s | {pdesc} | "
                     f"{('✅ v' + str(t['version'])) if t and t['passed'] else ('❌' if t else '–')} | "
                     f"{('✅' if a and a['passed'] else '❌') + (f' {a['model_calls']} calls, rung {a['rung']}' if a else '')} | "
                     f"{('✅' if b['passed'] else '❌') if b else '–'} |")
    return lines + [""]


def comparison(tag: str = "") -> list[str]:
    b = load(f"baselines{tag}")
    v = load(f"variants{tag}")
    n = load(f"new_inputs{tag}")
    if not b:
        return []
    cells: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for r in b["rows"]:
        kind = "routine" if r["kind"].startswith("routine") else r["kind"]
        cells[(kind, r["variant"])].append(r)
    if v:
        for e in v["experiments"]:
            cells[("routine", e["variant"])].append(e["first"])
    lines = ["### Three systems on the same requests", "",
             "Each cell is one request per routine family on a booking none of the systems was built from (6 families). Full agent: plan + one model call per step. "
             "Fixed replay: the recorded taps at their coordinates with the recorded text, a screen-similarity check before each, and the full agent on a mismatch "
             "(like Mobilerun macros). Envoy routine: the compiled routine with its checks and fallback ladder (first run on the changed layout, before any patch).", "",
             "| Layout | System | Success | Median model calls | Median time | Median cost (standard prices) | Wrong-booking or wrong-answer runs |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for var in sorted({k[1] for k in cells}):
        for kind, label in (("agent", "Full agent"), ("fixed", "Fixed replay"), ("routine", "Envoy routine")):
            rs = cells.get((kind, var), [])
            if not rs:
                continue
            wrong = sum(1 for r in rs if not r["passed"] and r.get("status") in ("done", "replayed", "agent_done"))
            lines.append(f"| {var}: {VARIANTS.get(var, var)} | {label} | {pct(sum(r['passed'] for r in rs), len(rs))} | {med([r['model_calls'] for r in rs])} | "
                         f"{med([r['duration_s'] for r in rs])} s | ${med([r['cost_usd'] for r in rs]):.4f} | {wrong} |")
    agent_calls = [r["model_calls"] for (k, _), rs in cells.items() if k == "agent" for r in rs]
    routine_calls = [r["model_calls"] for (k, _), rs in cells.items() if k == "routine" for r in rs]
    agent_t = [r["duration_s"] for (k, _), rs in cells.items() if k == "agent" for r in rs]
    routine_t = [r["duration_s"] for (k, _), rs in cells.items() if k == "routine" for r in rs]
    if agent_calls and routine_calls:
        red = 1 - sum(routine_calls) / sum(agent_calls)
        lines += ["", f"Across these cells, routines used **{sum(routine_calls)} model calls against {sum(agent_calls)} for the full agent ({red:.0%} fewer)**, "
                      f"with a median of {med(routine_t)} s against {med(agent_t)} s."]
    return lines + [""]


def real_apps() -> list[str]:
    d = load("real_apps")
    if not d:
        return []
    lines = ["## Real-app checkpoint (envoy-real, read-only)", "",
             "| App | Agent run | Compiled | Rerun (inputs) | Without repair | With repair allowed |", "| --- | --- | --- | --- | --- | --- |"]
    for app, w in d["workflows"].items():
        a = w.get("agent") or {}
        agent = f"{a.get('status')} · {a.get('steps')} steps · {a.get('model_calls')} calls · {a.get('duration_s')} s · ${a.get('cost_usd')}" if a else "–"
        c = w.get("compile") or {}
        comp = (f"{c['steps']} steps, inputs {', '.join(c['inputs']) or 'none'}, outputs {', '.join(c['outputs']) or 'none'}" if c.get("compiled")
                else f"no: {c.get('reason', '')[:60]}")
        runs = w.get("routine_runs") or []
        cases = sorted({r["case"] for r in runs}, key=lambda x: x != "same-inputs")
        if not cases:
            lines.append(f"| {app} | {agent} | {comp} | – | – | – |")
        for case in cases:
            def cell(repair: bool) -> str:
                r = next((x for x in runs if x["case"] == case and x["repair_allowed"] == repair), None)
                if r is None:
                    return "not needed" if repair else "–"
                ok = "✅" if r["status"] == "done" else "❌"
                why = "" if r["status"] == "done" else f": {r['detail'][:70]}"
                return f"{ok} {r['status']}, rung {r['rung']}, {r['model_calls']} calls, {r['duration_s']} s{why}"
            inputs = next(x["inputs"] for x in runs if x["case"] == case)
            lines.append(f"| {app} | {agent if case == cases[0] else ''} | {comp if case == cases[0] else ''} | {case} {inputs} | {cell(False)} | {cell(True)} |")
    return lines + [""]


def main() -> int:
    md = ["# Phase 2 evaluation: app routines on SkyLark Air", ""]
    rec = load("record")
    if rec:
        md += ["## Source runs (the full agent, once per routine family, on the Denver booking)", "",
               "| Family | Passed | Steps | Model calls | Time | Cost |", "| --- | --- | --- | --- | --- | --- |"]
        md += [f"| {r['family']} | {'✅' if r['passed'] else '❌'} | {r['steps']} | {r['model_calls']} | {r['duration_s']} s | ${r['cost_usd']:.4f} |" for r in rec["rows"]]
        md.append("")
    md += ["## Compiling", ""] + compile_table("", "Compiled on the original layout") + compile_table("-v4", "Compiled with IDs hidden (variant 4)") \
        + compile_table("-v3", "Compiled on the extra-screen layout (variant 3)")
    ni, _ = new_inputs_table("", "Original layout")
    ni4, _ = new_inputs_table("-v4", "IDs hidden (routines compiled on variant 4, run on variant 4)")
    md += ["## Routines on bookings they have never seen", ""] + ni + ni4
    md += ["## Injected UI changes", "",
           "Each experiment: (1) the compiled routine meets the changed layout on a new booking, with repair and the agent allowed; (2) any patches become a trial "
           "version, replayed at once from a reset snapshot on another new booking with no repair and no agent allowed; it becomes active if it passes, else it "
           "is rejected (rollback); (3) the active version runs on a third booking (does it now need no model?); (4) a patched version runs on the original layout.", ""]
    md += variants_tables("", "Routines compiled on the original layout") + variants_tables("-v3", "A routine compiled on the extra-screen layout, run on the original")
    md += variants_tables("-v4", "Routines compiled with IDs hidden")
    md += ["## Three systems compared", ""] + comparison()
    md += real_apps()
    m = load("matching")
    if m:
        md += ["## Matching requests to routines", "", f"{m['summary']}", "", "| Request | Expected | Matched | Inputs | Correct |", "| --- | --- | --- | --- | --- |"]
        md += [f"| {r['request']} | {r['expected'] or '(none)'} | {r['matched'] or '(none)'} | {r['inputs']} | {'✅' if r['correct'] else '❌'} |" for r in m["rows"]]
        md.append("")
    (OUT / "report.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
