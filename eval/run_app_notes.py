"""Do self-written app notes help? The same tasks before and after Envoy has learned notes from other tasks in the app.

  scripts/start_emulator.sh envoy-test
  META_DAILY_COST_CAP_USD=6 uv run --project backend python eval/run_app_notes.py --phase skylark
  uv run --project backend python eval/run_app_notes.py --phase real      # envoy-real, read-only (every approval declined)

Per phase, with the agent alone (no routines, no memory notes about the user) so the app notes are the only difference:
1. cold: the eval tasks with app notes off and an empty notes store;
2. warm-up: different tasks in the same app, notes on, and after each run one Spark call writes what it learned;
3. warm: the eval tasks again, reading those notes (no learning during this pass, so eval tasks can't teach each other).
Notes live in a scratch memory database (never data/memory.db); the standard tier throughout, so timings compare.
Results: eval/results/app-notes/<date>/<phase>.json and README.md (with each run's notes used, from its trace).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT_ROOT = REPO / "eval" / "results" / "app-notes"
SKYLARK, STARBUCKS, DOORDASH = "com.skylark.air", "com.starbucks.mobilecard", "com.dd.doordash"

CAL = r"\b\d{2,3}\s*(cal|calories)\b"
# (id, app, goal, check: a regex the answer must match, case-insensitive)
PHASES: dict[str, dict[str, list[tuple[str, str, str, str]]]] = {
    "skylark": {
        "eval": [
            ("boarding_denver", SKYLARK, "What time does boarding start for my Denver flight?", r"2:05"),
            ("group_chicago", SKYLARK, "Which boarding group am I in on my Chicago flight?", r"\b3\b"),
            ("bags_boston", SKYLARK, "How many checked bags were on my Boston trip?", r"\b(1|one)\b"),
            ("rewards_number", SKYLARK, "What's my SkyLark rewards number?", r"SR\s*4471\s*0923"),
            ("miami_date", SKYLARK, "When did I fly to Miami?", r"jul(y)?\s*19"),
            ("denver_lands", SKYLARK, "What time does my Denver flight land?", r"4:05"),
        ],
        "warmup": [
            ("seat_denver", SKYLARK, "What seat do I have on my Denver flight?", r"22F"),
            ("miles", SKYLARK, "How many SkyLark miles do I have?", r"38,?240"),
            ("tier", SKYLARK, "What's my SkyLark status tier?", r"silver"),
            ("austin_date", SKYLARK, "When did I fly to Austin?", r"aug(ust)?\s*21"),
            ("chicago_departs", SKYLARK, "What time does my Chicago flight depart?", r"6:10"),
            ("gate_denver", SKYLARK, "What gate does my Denver flight leave from?", r"\bA7\b"),
        ],
    },
    "real": {
        "eval": [
            ("sb_mocha", STARBUCKS, "How many calories are in a Caffè Mocha at Starbucks?", CAL),
            ("dd_pizza", DOORDASH, "What's the first restaurant DoorDash shows when you search for pizza?", r"\w{3,}"),
            ("sb_flat_white", STARBUCKS, "How many calories are in a Flat White at Starbucks?", CAL),
        ],
        "warmup": [
            ("sb_americano", STARBUCKS, "How many calories are in a Caffè Americano at Starbucks?", CAL),
            ("dd_sushi", DOORDASH, "What's the first restaurant DoorDash shows when you search for sushi?", r"\w{3,}"),
            ("sb_latte", STARBUCKS, "How many calories are in a Caffè Latte at Starbucks?", CAL),
        ],
    },
}
SERIAL = {"skylark": "emulator-5554", "real": "emulator-5556"}
AVD = {"skylark": "envoy-test", "real": "envoy-real"}


def notes_used(trace_dir: str) -> list[str]:
    ids: list[str] = []
    p = Path(trace_dir) / "steps.jsonl"
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                for n in json.loads(line).get("app_notes") or []:
                    if n not in ids:
                        ids.append(n)
            except ValueError:
                continue
    return ids


async def run_task(device: Any, sky: Any, notes: Any, phase: str, pas: str, task: tuple[str, str, str, str], learn: bool) -> dict[str, Any]:
    from agent.loop import AgentRunner, RunConfig
    from devices.types import Action
    from policy.approvals import ScriptedApprover
    from testapps.skylark import default_fixtures
    tid, app, goal, check = task
    scope = "test_app" if app == SKYLARK else "real"
    if sky is not None:
        await asyncio.to_thread(sky.prepare, default_fixtures(), 0)  # reset, variant 0, cold launch
    else:
        await device.launch(app, fresh=True)
    runner = AgentRunner(device, approver=ScriptedApprover(approve=False), config=RunConfig(data_scope=scope, contributor=False, max_cost_usd=0.25),
                         app_notes=notes)
    run_id = f"notes-{phase}-{pas}-{tid}-{datetime.now().strftime('%H%M%S')}"
    res = await runner.run(goal, task_id=run_id, memory="")
    ok = res.status in ("done", "done_unverified") and bool(re.search(check, res.result or "", re.I))
    row = {"pass": pas, "task": tid, "app": app, "goal": goal, "status": res.status, "result": res.result, "ok": ok, "steps": res.steps,
           "model_calls": res.model_calls, "cost_usd": round(res.cost_usd, 5), "duration_s": res.duration_s, "trace_dir": res.trace_dir,
           "notes_used": notes_used(res.trace_dir), "approvals": res.approvals}
    if learn:
        try:
            rep = await notes.learn(res.trace_dir, app=app, goal=goal, status=res.status, result=res.result, task_id=run_id, data_scope=scope,
                                    contributor=False)
            row["learned"] = {"proposed": rep.proposed, "applied": rep.applied, "dropped": rep.dropped, "cost_usd": rep.cost_usd}
        except Exception as e:  # noqa: BLE001 - recorded; the measurement goes on
            row["learned"] = {"error": f"{type(e).__name__}: {e}"[:300], "applied": [], "dropped": [], "cost_usd": 0.0}
    await device.act(Action(kind="home"))
    print(f"{pas:7s} {tid:16s} {'OK ' if ok else 'BAD'} {res.status:15s} steps {res.steps:2d} calls {res.model_calls:2d} "
          f"notes {len(row['notes_used'])} ${res.cost_usd:.3f}: {(res.result or '')[:70]}", flush=True)
    return row


def summary(rows: list[dict[str, Any]], pas: str) -> dict[str, Any]:
    rs = [r for r in rows if r["pass"] == pas]
    n = len(rs) or 1
    return {"runs": len(rs), "ok": sum(r["ok"] for r in rs), "steps_mean": round(sum(r["steps"] for r in rs) / n, 2),
            "calls_mean": round(sum(r["model_calls"] for r in rs) / n, 2), "cost_usd": round(sum(r["cost_usd"] for r in rs), 4),
            "note_writing_usd": round(sum((r.get("learned") or {}).get("cost_usd", 0.0) for r in rs), 4),
            "seconds_mean": round(sum(r["duration_s"] for r in rs) / n, 1)}


def markdown(phase: str, doc: dict[str, Any]) -> str:
    s = doc["summary"]
    out = [f"## {phase}", "", f"Profile `{doc['profile']}`, standard tier, agent only (no routines, no memory notes about the user).", "",
           "| Pass | Success | Mean steps | Mean model calls | Mean seconds | Cost |", "| --- | --- | --- | --- | --- | --- |"]
    for p in ("cold", "warmup", "warm"):
        x = s[p]
        out.append(f"| {p} | {x['ok']}/{x['runs']} | {x['steps_mean']} | {x['calls_mean']} | {x['seconds_mean']} | ${x['cost_usd']:.3f} |")
    out += ["", "| Task | Cold | Warm | Steps cold → warm | Notes used (warm) |", "| --- | --- | --- | --- | --- |"]
    by = {(r["pass"], r["task"]): r for r in doc["rows"]}
    for t in [r["task"] for r in doc["rows"] if r["pass"] == "cold"]:
        c, w = by[("cold", t)], by.get(("warm", t))
        out.append(f"| {t} | {'ok' if c['ok'] else 'fail'} ({c['status']}) | {('ok' if w['ok'] else 'fail') + ' (' + w['status'] + ')' if w else '—'} | "
                   f"{c['steps']} → {w['steps'] if w else '—'} | {len(w['notes_used']) if w else 0} |")
    out += ["", "Notes Envoy wrote in the warm-up (its own words, after its filter):", ""]
    out += [f"- {n['text']} (seen {n['confirmations']}×)" for n in doc["notes"]] or ["- (none)"]
    dropped = [d for r in doc["rows"] for d in (r.get("learned") or {}).get("dropped", [])]
    if dropped:
        out += ["", "Proposed and dropped by the filter:", ""] + [f"- {d.get('text', d.get('note_id'))!r}: {d['why']}" for d in dropped]
    return "\n".join(out) + "\n"


async def main_async(args: argparse.Namespace) -> int:
    from devices.emulator import EmulatorDevice
    from memory.app_notes import AppNotes
    from memory.store import MemoryStore
    from models.adapter import ModelAdapter, active_profile
    from testapps.skylark import SkyLark

    out = OUT_ROOT / ((args.date or datetime.now().strftime("%Y-%m-%d")) + (f"-{args.label}" if args.label else ""))
    out.mkdir(parents=True, exist_ok=True)
    db = Path(args.scratch) / f"notes-{args.phase}.db"
    if db.exists():
        db.unlink()
    store = MemoryStore(db)
    notes = AppNotes(store, ModelAdapter())
    device = EmulatorDevice(AVD[args.phase]).connect()
    sky = SkyLark(SERIAL["skylark"]) if args.phase == "skylark" else None
    tasks = {k: v[: args.limit or None] for k, v in PHASES[args.phase].items()}
    rows: list[dict[str, Any]] = []
    t0 = time.time()
    os.environ["ENVOY_APP_NOTES"] = "off"
    for t in tasks["eval"]:
        rows.append(await run_task(device, sky, notes, args.phase, "cold", t, learn=False))
    os.environ["ENVOY_APP_NOTES"] = "on"
    for t in tasks["warmup"]:
        rows.append(await run_task(device, sky, notes, args.phase, "warmup", t, learn=True))
    for t in tasks["eval"]:
        rows.append(await run_task(device, sky, notes, args.phase, "warm", t, learn=False))
    if sky is not None:
        await asyncio.to_thread(sky.reset)
    doc = {"phase": args.phase, "date": datetime.now(timezone.utc).isoformat(timespec="seconds"), "profile": active_profile(),
           "commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=REPO).stdout.strip(),
           "wall_s": round(time.time() - t0, 1), "rows": rows, "summary": {p: summary(rows, p) for p in ("cold", "warmup", "warm")},
           "notes": [n.to_json() for n in notes.list(include_retired=False)]}
    (out / f"{args.phase}.json").write_text(json.dumps(doc, indent=1, default=str, ensure_ascii=False))
    parts = [markdown(p, json.loads((out / f"{p}.json").read_text())) for p in ("skylark", "real") if (out / f"{p}.json").exists()]
    (out / "README.md").write_text("# App notes: before and after\n\nSame tasks, same agent and profile; the only difference is the notes Envoy "
                                   "wrote itself during a warm-up on other tasks in the same app. Small samples (6 and 3 tasks), one run each: "
                                   "read the per-task rows, not just the totals.\n\n" + "\n".join(parts))
    print(json.dumps(doc["summary"]), flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", choices=list(PHASES), default="skylark")
    ap.add_argument("--scratch", default=os.environ.get("TMPDIR", "/tmp"))
    ap.add_argument("--limit", type=int, default=0, help="only the first N tasks of each pass (a smoke test)")
    ap.add_argument("--label", default="", help="a suffix for the results folder")
    ap.add_argument("--date", default="", help="the results folder's date (default today), so both phases share one folder")
    args = ap.parse_args()
    sys.path.insert(0, str(REPO / "backend"))
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
