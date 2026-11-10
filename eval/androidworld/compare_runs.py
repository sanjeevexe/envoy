"""Two AndroidWorld stages side by side, paired by task (standard library only).

  python3 eval/androidworld/compare_runs.py 2026-11-03-hybrid-7ed4aa6 2026-11-09-push-all-3e557d1 [--out file.json]

Overall, by half (held-out is the estimate), by difficulty and by app; the tasks gained and lost with an exact two-sided
sign test; how episodes ended; cost, time, steps, screenshots per step; and, from each stage's trace digests, how often the
Nov 2026 mechanisms fired (scroll reports, list ends, long text in parts, row text, replans, dones in the last 5 steps).
"""

from __future__ import annotations

import collections
import gzip
import json
import statistics as st
import sys
from math import comb
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RESULTS = REPO / "eval" / "results" / "androidworld"


def load(stage: str) -> dict[str, dict]:
    out = {}
    for p in sorted((RESULTS / stage / "episodes").glob("*.json")):
        e = json.loads(p.read_text())
        out[e["task"]] = e
    return out


def sign_p(gained: int, lost: int) -> float:
    n, k = gained + lost, min(gained, lost)
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def digest(e: dict) -> list[dict]:
    path = (e.get("envoy") or {}).get("trace_digest")
    return [json.loads(line) for line in gzip.open(REPO / path, "rt")] if path and (REPO / path).exists() else []


def mechanisms(eps: dict[str, dict], tasks: list[str]) -> dict:
    c = collections.Counter()
    for e in (eps[t] for t in tasks):
        v, rows = e.get("envoy") or {}, digest(e)
        acts = [r for r in rows if r.get("kind") == "action"]
        c["steps"] += len(acts)
        c["screenshots"] += sum(1 for r in acts if r.get("shot"))
        c["scrolls"] += sum(1 for r in acts if (r.get("decision") or {}).get("action", {}).get("type") == "scroll")
        notes = [r["scroll"] for r in acts if r.get("scroll")]
        c["scroll reports"] += len(notes)
        c["scroll reports: list end"] += sum(1 for n in notes if "end of the list" in n or "top of the list" in n)
        c["scroll reports: nothing new (all seen before)"] += sum(1 for n in notes if n.startswith("0 new items came into view ("))
        c["scroll reports: next part of a long text"] += sum(1 for n in notes if n.startswith("the long text"))
        c["screens with row text"] += sum(1 for r in acts if "(in row " in (r.get("screen") or ""))
        c["screens with long text in parts"] += sum(1 for r in acts if "[characters " in (r.get("screen") or ""))
        c["replans"] += sum(1 for r in rows if r.get("kind") == "replan")
        mx = v.get("max_steps") or 0
        dones = [r for r in acts if (r.get("decision") or {}).get("action", {}).get("type") == "done"]
        late = [r for r in dones if mx and mx - r["step"] + 1 <= 5]
        if late and v.get("status") in ("done", "done_unverified"):
            c["ended with a done in the last 5 steps"] += 1
            c["ended with a done in the last 5 steps, scored 1"] += e.get("score", 0) >= 1
        if dones and dones[-1]["step"] == mx and v.get("status") in ("done", "done_unverified"):
            c["ended with a done on the very last step"] += 1
            c["ended with a done on the very last step, scored 1"] += e.get("score", 0) >= 1
        c["failed (the agent's own fail)"] += v.get("status") == "failed"
    return dict(c)


def summary(eps: dict[str, dict], tasks: list[str]) -> dict:
    es = [eps[t] for t in tasks if t in eps]
    v = [e.get("envoy") or {} for e in es]
    cost = [x.get("cost_usd") or 0 for x in v]
    solved = sum(e.get("score", 0) for e in es)
    return {
        "n": len(es), "solved": solved, "rate": round(solved / len(es), 4) if es else None,
        "cost_total": round(sum(cost), 2), "cost_mean": round(st.mean(cost), 4) if cost else None,
        "cost_median": round(st.median(cost), 4) if cost else None,
        "cost_per_solved": round(sum(cost) / solved, 4) if solved else None,
        "envoy_s_median": round(st.median([x.get("duration_s") or 0 for x in v]), 1) if v else None,
        "model_s_median": round(st.median([x.get("model_s") or 0 for x in v]), 1) if v else None,
        "device_s_median": round(st.median([x.get("device_s") or 0 for x in v]), 1) if v else None,
        "aw_s_median": round(st.median([e.get("aw_run_time_s") or 0 for e in es]), 1) if es else None,
        "steps": sum(x.get("iterations") or 0 for x in v), "model_calls": sum(x.get("model_calls") or 0 for x in v),
        "ended": dict(collections.Counter(x.get("status") for x in v)),
        "dones_scored_0": sum(1 for e, x in zip(es, v) if x.get("status") in ("done", "done_unverified") and e.get("score", 0) < 1),
        "harness_exceptions": sum(1 for e in es if e.get("harness_exception")),
    }


def main() -> None:
    a_name, b_name = sys.argv[1], sys.argv[2]
    out_path = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    sp = json.loads((RESULTS / "split.json").read_text())
    a, b = load(a_name), load(b_name)
    common = sorted(set(a) & set(b))
    groups = {"all": common, "held_out": [t for t in common if t in sp["held_out"]], "dev": [t for t in common if t in sp["dev"]]}
    for d in ("easy", "medium", "hard"):
        groups[d] = [t for t in common if sp["tasks"][t]["difficulty"] == d]
    for half in ("held_out", "dev"):
        for d in ("easy", "medium", "hard"):
            groups[f"{half}:{d}"] = [t for t in groups[half] if sp["tasks"][t]["difficulty"] == d]
    report: dict = {"a": a_name, "b": b_name, "groups": {}}
    for g, ts in groups.items():
        gained = [t for t in ts if b[t]["score"] > a[t]["score"]]
        lost = [t for t in ts if b[t]["score"] < a[t]["score"]]
        report["groups"][g] = {"a": summary(a, ts), "b": summary(b, ts), "gained": gained, "lost": lost,
                               "sign_test_p": round(sign_p(len(gained), len(lost)), 4)}
    apps = collections.defaultdict(list)
    for t in common:
        apps[sp["tasks"][t]["app"]].append(t)
    report["by_app"] = {app: {"n": len(ts), "a": sum(a[t]["score"] for t in ts), "b": sum(b[t]["score"] for t in ts)}
                        for app, ts in sorted(apps.items(), key=lambda kv: -len(kv[1]))}
    report["mechanisms"] = {g: {"a": mechanisms(a, groups[g]), "b": mechanisms(b, groups[g])} for g in ("all", "held_out", "dev")}
    for g in ("all", "held_out", "dev"):
        r = report["groups"][g]
        print(f"{g:9} {a_name}: {r['a']['solved']:g}/{r['a']['n']}  {b_name}: {r['b']['solved']:g}/{r['b']['n']}  "
              f"+{len(r['gained'])} -{len(r['lost'])}  p={r['sign_test_p']}")
        print(f"          gained {r['gained']}\n          lost {r['lost']}")
    for k in ("cost_total", "cost_mean", "cost_median", "cost_per_solved", "envoy_s_median", "model_s_median", "aw_s_median",
              "steps", "model_calls", "ended", "dones_scored_0", "harness_exceptions"):
        print(f"  {k}: {report['groups']['all']['a'][k]} -> {report['groups']['all']['b'][k]}")
    m = report["mechanisms"]["all"]
    for k in sorted(set(m["a"]) | set(m["b"])):
        print(f"  {k}: {m['a'].get(k, 0)} -> {m['b'].get(k, 0)}")
    if out_path:
        Path(out_path).write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
