"""An overview of one half's failures, for the failure analysis (read each in full with show.py before labeling it).

  python3 eval/androidworld/failures.py baseline dev            # every dev failure: goal, outcome, plan, last steps
  python3 eval/androidworld/failures.py baseline dev --all      # successes too
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[2] / "eval" / "results" / "androidworld"


def main() -> None:
    stage, half = sys.argv[1], sys.argv[2]
    show_all = "--all" in sys.argv
    sp = json.loads((RESULTS / "split.json").read_text())
    names = set(sp[half])
    for p in sorted((RESULTS / stage / "episodes").glob("*.json")):
        ep = json.loads(p.read_text())
        if ep["task"] not in names or (ep.get("score", 0) > 0.5 and not show_all):
            continue
        e = ep.get("envoy") or {}
        t = sp["tasks"][ep["task"]]
        print(f"\n=== {ep['task']} ({t['app']}, {t['difficulty']}) score {ep['score']} · {e.get('status')} {e.get('result')!r}"
              f" · {e.get('iterations')}/{t['step_budget']} steps · actions {e.get('actions')} · looks {e.get('looks')}"
              f" · stuck {e.get('stuck_recoveries')} · replans {e.get('replans')} · approvals {len(e.get('approvals') or [])}"
              f" · popups {e.get('popups')}")
        print(f"GOAL: {ep['goal']}")
        if ep.get("harness_exception"):
            print("HARNESS:", ep["harness_exception"][-300:])
        if (e.get("harness") or {}).get("crash_dialog_after_episode"):
            print("CRASH DIALOG:", e["harness"]["crash_dialog_after_episode"])
        if not e.get("trace_digest"):
            continue
        rows = [json.loads(l) for l in gzip.open(RESULTS.parents[2] / e["trace_digest"], "rt")]
        plan = next((r.get("plan") for r in rows if r.get("kind") == "plan"), None) or {}
        print(f"PLAN: app={plan.get('app')} {plan.get('subgoals')} check={plan.get('success_check')}")
        acts = [r for r in rows if r.get("kind") in ("action", "popup", "stuck", "replan")]
        for r in acts[-8:]:
            d = r.get("decision") or {}
            a = d.get("action") or {}
            tgt = (r.get("target") or {}).get("label")
            print(f"  [{r.get('step')}] {r['kind']} {a.get('type', r.get('handler') or r.get('action') or '')}"
                  f"{' ' + json.dumps({k: v for k, v in a.items() if k != 'type'}, ensure_ascii=False)[:90] if a else ''}"
                  f"{' → ' + repr(tgt)[:50] if tgt else ''} | {(d.get('reason') or '')[:90]}{' | ERR ' + r['error'][:80] if r.get('error') else ''}")
        last = next((r.get("screen") for r in reversed(rows) if r.get("screen")), "")
        print("LAST SCREEN: " + " / ".join(last.split("\n")[:14])[:900])


if __name__ == "__main__":
    main()
