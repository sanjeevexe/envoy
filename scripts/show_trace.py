"""Print an agent run's trace step by step:  python3 scripts/show_trace.py <task_id> [--screens]"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RUNS = Path(__file__).resolve().parents[1] / "data" / "runs"


def main() -> int:
    if len(sys.argv) < 2:
        runs = sorted(RUNS.iterdir(), key=lambda p: p.stat().st_mtime)[-15:]
        print("recent runs:\n" + "\n".join(f"  {p.name}" for p in runs))
        return 0
    run = RUNS / sys.argv[1]
    show_screens = "--screens" in sys.argv
    summary = json.loads((run / "run.json").read_text()) if (run / "run.json").exists() else {}
    print(f"{summary.get('goal')}\n→ {summary.get('status')}: {summary.get('result')}")
    print(f"  {summary.get('steps')} steps, {summary.get('model_calls')} model calls, ${summary.get('cost_usd', 0):.4f}, {summary.get('duration_s')} s\n")
    for line in (run / "steps.jsonl").read_text().splitlines():
        r = json.loads(line)
        k = r["kind"]
        if k == "plan":
            p = r["plan"] or {}
            print(f"[plan] {p.get('subgoals')}  check={p.get('success_check')}")
        elif k == "popup":
            print(f"[{r['step']}] popup: {r['handler']}")
        elif k == "handoff":
            print(f"[{r['step']}] HANDOFF: {r['reason']}")
        elif k == "replan":
            p = r["plan"] or {}
            print(f"[{r['step']}] REPLAN ({r.get('tried')}) → {p.get('subgoals')}")
        elif k == "model_error":
            print(f"[{r['step']}] model reply unparseable, asked again: {r['error'][:100]}")
        elif "decision" not in r:
            print(f"[{r.get('step')}] {k}")
        else:
            d = r["decision"]
            t = r.get("timings_ms", {})
            extra = []
            if r.get("risk", {}).get("level") == "irreversible":
                extra.append(f"APPROVAL {'yes' if r.get('approval', {}).get('approved') else 'NO'}")
            if r.get("changed") is False:
                extra.append("no change")
            if r.get("error"):
                extra.append(r["error"])
            print(f"[{r['step']}] {json.dumps(d['action'])}  ({d['reason']})  model {t.get('model')} ms  {' · '.join(extra)}")
            if show_screens:
                print("    " + r["screen_before"]["compact"].replace("\n", "\n    "))
    return 0


if __name__ == "__main__":
    sys.exit(main())
