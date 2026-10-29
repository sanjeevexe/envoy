"""Chat setting up recurring jobs, live on Muse Spark (standard tier): a few phrasings through `chat()`, each one's draft,
the trigger it made (switched off, asking each time), its offer, and the spend.

  uv run --project backend python eval/run_recurring.py --scratch <your scratch dir> [--phrasing "..."]

Nothing touches a phone: the runner here only records what chat would start, and the triggers and offers live in a
scratch tasks database. The real model is called once per phrasing that passes the pre-filter (twice when the draft
says it isn't recurring and chat goes on as before). Results: eval/results/recurring/recurring.json and recurring.md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "eval" / "results" / "recurring"
PHRASINGS = [
    "Every Friday at 6 PM, order my usual from Thai Basil",
    "check my flight status every weekday morning at 7:30",
    "Whenever SkyLark emails me that check-in is open, check me in for my flight",
    "When my flight's gate changes, look up my boarding time",
    "Check me in 24 hours before every flight",
    "Check me in before my flight to Chicago tomorrow",  # schedule words, but once: chat goes on as before
]


class Recorder:
    """A runner that records what chat would start, and starts nothing."""

    def __init__(self) -> None:
        self.started: list = []

    def start(self, goal: str, source: str, **kw: Any) -> dict[str, Any]:
        self.started.append({"goal": goal, "source": source, **{k: v for k, v in kw.items() if v}})
        return {"id": f"not-started-{len(self.started)}", "goal": goal, "status": "queued"}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--phrasing", action="append", help="instead of the built-in phrasings (repeatable)")
    ap.add_argument("--max-usd", type=float, default=0.30, help="stop once this run has spent this much (standard prices)")
    args = ap.parse_args()
    scratch = Path(args.scratch).resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(REPO / "backend"))
    from api.chat import chat
    from api.events import EventBus
    from api.offers import Offers
    from api.recurring import Recurring, may_schedule
    from api.scheduler import Scheduler
    from api.store import TaskStore
    from memory.store import MemoryStore
    from models.adapter import ModelAdapter
    from routines.store import RoutineStore

    db = scratch / "recurring.db"
    db.unlink(missing_ok=True)
    tasks, memory, bus, adapter = TaskStore(db), MemoryStore(":memory:"), EventBus(), ModelAdapter()
    runner = Recorder()
    sched = Scheduler(tasks, memory, runner.start, bus)
    offers = Offers(tasks, bus, runner, sched)
    sched.offers = offers
    runner.recurring = Recurring(offers, sched, adapter)
    routines = RoutineStore(REPO / "data" / "routines")
    rows, spent, calls = [], 0.0, 0
    for message in args.phrasing or PHRASINGS:
        if spent >= args.max_usd:
            print(f"stopping: this run spent ${spent:.4f} (cap ${args.max_usd})", flush=True)
            break
        n0 = len(runner.started)
        t0 = time.perf_counter()
        out = await chat(message, adapter=adapter, memory=memory, runner=runner, routines=routines, source="chat")
        ms = round((time.perf_counter() - t0) * 1000)
        trig = (out.get("trigger") or {})
        row = {"message": message, "pre_filter": may_schedule(message), "kind": out.get("kind"), "reply": out.get("reply"), "ms": ms,
               "model_calls": out.get("model_calls"), "cost_usd": out.get("cost_usd"),
               "trigger": {k: trig.get(k) for k in ("kind", "name", "spec", "action", "enabled")} if trig else None,
               "offer": (out.get("offer") or {}).get("title"), "started": runner.started[n0:], "rejected": out.get("draft_rejected")}
        rows.append(row)
        spent += float(out.get("cost_usd") or 0)
        calls += int(out.get("model_calls") or 0)
        print(json.dumps(row, default=str)[:700], flush=True)
    report = {"time": datetime.now().isoformat(timespec="seconds"), "model": "muse-spark-1.3 (standard tier)", "rows": rows,
              "model_calls": calls, "cost_usd": round(spent, 5)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "recurring.json").write_text(json.dumps(report, indent=2, default=str))
    lines = [f"# Chat sets up recurring jobs, live ({report['time']})", "", f"{report['model']}: {calls} model calls, ${report['cost_usd']}.", "",
             "| You said | What happened | Trigger (off, asks each time) | Calls | ms |", "| --- | --- | --- | --- | --- |"]
    for r in rows:
        t = r["trigger"]
        what = r["offer"] or (f"refused: {r['rejected']}" if r["rejected"] else f"chat as before ({r['kind']}): {', '.join(s['goal'] for s in r['started'])}")
        lines.append(f"| {r['message']} | {what} | {json.dumps(t['spec']) + ' · ' + t['action']['goal'] if t else ''} | {r['model_calls']} | {r['ms']} |")
    (OUT / "recurring.md").write_text("\n".join(lines) + "\n")
    print(f"\n{calls} calls, ${report['cost_usd']}: {OUT / 'recurring.md'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
