"""Read one AndroidWorld episode the way the failure analysis does: goal, score, Envoy's plan and every step.

  python3 eval/androidworld/show.py baseline SimpleCalendarEventsOnDate            # steps, with the screen heads
  python3 eval/androidworld/show.py baseline SimpleCalendarEventsOnDate --screens  # plus each screen as the model saw it
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[2] / "eval" / "results" / "androidworld"


def main() -> None:
    stage, task = sys.argv[1], sys.argv[2]
    screens = "--screens" in sys.argv
    for ep_path in sorted((RESULTS / stage / "episodes").glob(f"{task}__s*.json")):
        ep = json.loads(ep_path.read_text())
        e = ep.get("envoy") or {}
        print(f"# {ep['task']} (seed {ep['seed']}) score {ep['score']}\nGOAL: {ep['goal']}")
        print(f"envoy: {e.get('status')} · {e.get('result')!r} · {e.get('iterations')}/{e.get('max_steps')} steps · "
              f"{e.get('model_calls')} calls · ${e.get('cost_usd')} · {e.get('duration_s')} s · approvals {len(e.get('approvals') or [])}"
              f" · pop-ups {e.get('popups')} · check {e.get('check')}")
        if ep.get("harness_exception"):
            print("HARNESS EXCEPTION:", ep["harness_exception"][-600:])
        dig = Path(RESULTS.parents[2] / e["trace_digest"]) if e.get("trace_digest") else None
        if not dig or not dig.exists():
            continue
        for line in gzip.open(dig, "rt"):
            r = json.loads(line)
            k = r.get("kind")
            if k in ("plan", "replan"):
                p = r.get("plan") or {}
                print(f"\n[{r.get('step')}] {k.upper()}: app={p.get('app')} subgoals={p.get('subgoals')} check={p.get('success_check')}"
                      + (f"\n    tried: {r.get('tried')}" if r.get("tried") else ""))
                continue
            d = r.get("decision") or {}
            a = d.get("action") or {}
            extra = {kk: vv for kk, vv in a.items() if kk != "type"}
            tgt = r.get("target") or {}
            print(f"\n[{r.get('step')}] {k}: {a.get('type') or r.get('handler') or r.get('action') or ''} {json.dumps(extra, ensure_ascii=False) if extra else ''}"
                  + (f" → {tgt.get('kind')} {tgt.get('label')!r}" if tgt else "")
                  + (f"\n    why: {d.get('reason')}" if d.get("reason") else "")
                  + (f"\n    expect: {d.get('expected_result')}" if d.get("expected_result") else "")
                  + (f"\n    ERROR: {r['error']}" if r.get("error") else "")
                  + (f"\n    approval: {r['approval']}" if r.get("approval") else "")
                  + (f"\n    vision: {r['vision'].get('method')} {r['vision'].get('target')!r} {r['vision'].get('detail')}" if r.get("vision") else "")
                  + (f"\n    changed={r.get('changed')} → {r.get('screen_after_head')}" if "changed" in r else ""))
            if screens and r.get("screen"):
                print("    | " + r["screen"].replace("\n", "\n    | "))
            elif r.get("screen"):
                print("    @ " + r["screen"].split("\n", 1)[0])


if __name__ == "__main__":
    main()
