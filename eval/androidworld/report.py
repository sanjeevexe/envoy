"""Tables and JSON for AndroidWorld stages (standard library only).

  python3 eval/androidworld/report.py pilot                    # one stage → eval/results/androidworld/<stage>/summary.json
  python3 eval/androidworld/report.py baseline improved        # two stages side by side, by half (dev / held-out)

Scores are AndroidWorld's (`is_successful`, gated by the agent's done). A harness exception (AndroidWorld failing to set up,
score or tear down a task) counts as a failure in every rate here and is listed, never dropped.
"""

from __future__ import annotations

import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[2] / "eval" / "results" / "androidworld"


def load(stage: str) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted((RESULTS / stage / "episodes").glob("*.json"))]


def split() -> dict:
    return json.loads((RESULTS / "split.json").read_text())


def _med(xs):
    xs = [x for x in xs if x is not None]
    return round(st.median(xs), 4) if xs else None


def _sum(xs):
    return round(sum(x for x in xs if x is not None), 4)


def rate(eps: list[dict]) -> dict:
    n = len(eps)
    s = sum(e.get("score", 0.0) for e in eps)
    return {"n": n, "success": round(s, 2), "rate": round(100 * s / n, 1) if n else None}


def summarize(stage: str) -> dict:
    eps = load(stage)
    sp = split()
    tasks = sp["tasks"]
    half = {t: "dev" for t in sp["dev"]} | {t: "held_out" for t in sp["held_out"]}
    env = [e.get("envoy") or {} for e in eps]
    by = lambda key: {k: rate(v) for k, v in sorted(_group(eps, key).items())}  # noqa: E731
    out = {
        "stage": stage,
        "overall": rate(eps),
        "by_half": by(lambda e: half.get(e["task"], "?")),
        "by_difficulty": by(lambda e: tasks.get(e["task"], {}).get("difficulty", "?")),
        "by_app": by(lambda e: tasks.get(e["task"], {}).get("app", "?")),
        "harness_exceptions": [e["task"] for e in eps if e.get("harness_exception")],
        "envoy_status": _count(x.get("status", "none") for x in env),
        "success_by_envoy_status": _count(x.get("status") for x, e in zip(env, eps) if e.get("score", 0) > 0.5),
        "cost_billed_usd": {"total": _sum(x.get("cost_usd") for x in env), "median_task": _med([x.get("cost_usd") for x in env])},
        "cost_standard_usd": {"total": _sum(x.get("cost_at_standard_usd") for x in env),
                              "median_task": _med([x.get("cost_at_standard_usd") for x in env])},
        "time_s": {"envoy_median": _med([x.get("duration_s") for x in env]), "envoy_total": _sum(x.get("duration_s") for x in env),
                   "model_median": _med([x.get("model_s") for x in env]), "device_median": _med([x.get("device_s") for x in env]),
                   "androidworld_task_median": _med([e.get("aw_run_time_s") for e in eps])},
        "steps": {"median": _med([x.get("iterations") for x in env]), "total": _sum(x.get("iterations") for x in env),
                  "budget_total": sum(tasks.get(e["task"], {}).get("step_budget", 0) for e in eps)},
        "model_calls": {"median": _med([x.get("model_calls") for x in env]), "total": _sum(x.get("model_calls") for x in env)},
        "approvals": {"total": sum(len(x.get("approvals") or []) for x in env),
                      "tasks": sum(1 for x in env if x.get("approvals"))},
        "popups_handled": sum(len(x.get("popups") or []) for x in env),
        "screenshots_sent": _sum(x.get("screenshots_sent") for x in env),
        "looks": _sum(x.get("looks") for x in env),
        "vision_calls": _sum(x.get("vision_calls") for x in env),
        "stuck_recoveries": _sum(x.get("stuck_recoveries") for x in env),
        "replans": _sum(x.get("replans") for x in env),
        "crash_dialogs": sum(1 for x in env if (x.get("harness") or {}).get("crash_dialog_after_episode")),
        "tasks": [{"task": e["task"], "half": half.get(e["task"]), "difficulty": tasks.get(e["task"], {}).get("difficulty"),
                   "app": tasks.get(e["task"], {}).get("app"), "score": e.get("score"), "status": (e.get("envoy") or {}).get("status"),
                   "answer": (e.get("envoy") or {}).get("answer"), "steps": (e.get("envoy") or {}).get("iterations"),
                   "budget": tasks.get(e["task"], {}).get("step_budget"), "calls": (e.get("envoy") or {}).get("model_calls"),
                   "cost_usd": (e.get("envoy") or {}).get("cost_usd"), "duration_s": (e.get("envoy") or {}).get("duration_s"),
                   "approvals": len((e.get("envoy") or {}).get("approvals") or []), "harness_exception": bool(e.get("harness_exception")),
                   "trace": (e.get("envoy") or {}).get("trace_digest")} for e in eps],
    }
    return out


def _group(eps, key):
    g = defaultdict(list)
    for e in eps:
        g[key(e)].append(e)
    return g


def _count(xs):
    c: dict = defaultdict(int)
    for x in xs:
        c[x] += 1
    return dict(sorted(c.items(), key=lambda kv: -kv[1]))


def print_stage(s: dict) -> None:
    o = s["overall"]
    print(f"## {s['stage']}: {o['success']:g}/{o['n']} = {o['rate']}%")
    for k in ("by_half", "by_difficulty", "by_app"):
        print(f"\n{k}: " + "; ".join(f"{name} {r['success']:g}/{r['n']}" for name, r in s[k].items()))
    print(f"\nenvoy status: {s['envoy_status']}; successes by status: {s['success_by_envoy_status']}")
    print(f"cost billed ${s['cost_billed_usd']['total']} (median ${s['cost_billed_usd']['median_task']}/task); "
          f"standard ${s['cost_standard_usd']['total']} (median ${s['cost_standard_usd']['median_task']}/task)")
    print(f"time: envoy median {s['time_s']['envoy_median']} s (model {s['time_s']['model_median']} s, device {s['time_s']['device_median']} s), "
          f"AndroidWorld task median {s['time_s']['androidworld_task_median']} s, envoy total {s['time_s']['envoy_total']} s")
    print(f"steps median {s['steps']['median']} (total {s['steps']['total']} of {s['steps']['budget_total']} budget); "
          f"model calls median {s['model_calls']['median']} (total {s['model_calls']['total']})")
    print(f"approvals {s['approvals']['total']} in {s['approvals']['tasks']} tasks; pop-ups {s['popups_handled']}; screenshots {s['screenshots_sent']}; "
          f"looks {s['looks']}; vision {s['vision_calls']}; stuck {s['stuck_recoveries']}; replans {s['replans']}; "
          f"crash dialogs {s['crash_dialogs']}; harness exceptions {s['harness_exceptions']}")
    print("\n| task | half | diff | score | status | steps/budget | calls | $ billed | s | answer |\n|---|---|---|---|---|---|---|---|---|---|")
    for t in sorted(s["tasks"], key=lambda t: t["task"]):
        print(f"| {t['task']} | {t['half']} | {t['difficulty']} | {t['score']} | {t['status']} | {t['steps']}/{t['budget']} | {t['calls']} | "
              f"{t['cost_usd']} | {t['duration_s']} | {(t['answer'] or '')[:40]} |")


def compare(a: str, b: str) -> dict:
    sa, sb = summarize(a), summarize(b)
    ta = {t["task"]: t for t in sa["tasks"]}
    tb = {t["task"]: t for t in sb["tasks"]}
    common = sorted(set(ta) & set(tb))
    out = {"before": a, "after": b, "by_half": {}, "gained": [], "lost": []}
    for h in ("dev", "held_out", None):
        names = [t for t in common if h is None or ta[t]["half"] == h]
        g = [t for t in names if (tb[t]["score"] or 0) > (ta[t]["score"] or 0)]
        lo = [t for t in names if (tb[t]["score"] or 0) < (ta[t]["score"] or 0)]
        out["by_half"][h or "all"] = {"n": len(names), "before": sum(ta[t]["score"] or 0 for t in names),
                                      "after": sum(tb[t]["score"] or 0 for t in names), "gained": len(g), "lost": len(lo),
                                      "p_paired": sign_test(len(g), len(lo))}
    out["gained"] = [t for t in common if (tb[t]["score"] or 0) > (ta[t]["score"] or 0)]
    out["lost"] = [t for t in common if (tb[t]["score"] or 0) < (ta[t]["score"] or 0)]
    return out


def sign_test(gained: int, lost: int) -> float:
    """Exact two-sided McNemar (sign) test on the tasks that changed: how likely a split this uneven is if the change
    did nothing and each changed task was a coin flip. Two runs of the same agent differ on ~20% of tasks."""
    from math import comb

    n, k = gained + lost, min(gained, lost)
    if n == 0:
        return 1.0
    return round(min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n), 4)


def main() -> None:
    stages = sys.argv[1:]
    if len(stages) == 1:
        s = summarize(stages[0])
        (RESULTS / stages[0] / "summary.json").write_text(json.dumps(s, indent=1, ensure_ascii=False))
        print_stage(s)
    elif len(stages) == 2:
        c = compare(*stages)
        (RESULTS / f"compare_{stages[0]}_{stages[1]}.json").write_text(json.dumps(c, indent=1))
        print(json.dumps(c, indent=1))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
