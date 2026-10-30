"""Loop B: new real apps on envoy-real, first run against replay (prompts/loop-new-apps.md).

  uv run --project backend python eval/run_new_apps.py run  --app <pkg> --kind first  --goal "In the Clock app, ..."
  uv run --project backend python eval/run_new_apps.py run  --app <pkg> --kind replay --goal "..." [--goal "..."]
  uv run --project backend python eval/run_new_apps.py save <task_id> --by loop-b       # compile a run, add it to the library
  uv run --project backend python eval/run_new_apps.py summary [--app <pkg>]             # the table's numbers per app and task

Every run is a task on the API copy (ENVOY_PORT, default 8751; its token in $ENVOY_API_DIR/session_token), on envoy-real by
name, so it takes the same path as a request from the web app. Nobody is there: every approval is declined, a "use your
phone?" ask is declined, and a hand-off (a sign-in screen or a bot check) stops the task and is recorded, never done.
Before a first run the app is force-stopped and the notes Envoy learned about it are retired, so each first run is cold.
Wall-clock time is from the request to the task's end; cost is the real dollars in this checkout's logs/model_costs.jsonl
for the task (its matcher, agent, repairs and notes), read once the task has written its memory.
Results: eval/results/real-apps/loop-b/runs.json (one record per run, appended).
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
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "eval" / "results" / "real-apps" / "loop-b"
RUNS_FILE = OUT / "runs.json"
COST_LOG = REPO / "logs" / "model_costs.jsonl"
SERIAL = "emulator-5556"  # envoy-real
DEVICE = "envoy-real"
PORT = int(os.environ.get("ENVOY_PORT", "8751"))
API_DIR = Path(os.environ.get("ENVOY_API_DIR", REPO / "data" / "api"))
ENDED = {"done", "failed", "declined", "stopped", "needs_you", "taken_over"}


def adb(*args: str) -> str:
    return subprocess.run(["adb", "-s", SERIAL, *args], capture_output=True, text=True, timeout=60).stdout


def api(method: str, path: str, body: dict | None = None) -> dict:
    token = (API_DIR / "session_token").read_text().strip()
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "X-Envoy": "1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"{}")


def logged_cost(tid: str) -> tuple[float, int]:
    """Real dollars and calls the cost log holds for this task (its own id or one it prefixes: matcher, notes)."""
    cost, calls = 0.0, 0
    if COST_LOG.exists():
        for line in COST_LOG.read_text().splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if str(r.get("task_id") or "").startswith(tid):
                cost += r.get("cost_usd") or 0.0
                calls += 1
    return round(cost, 4), calls


def retire_notes(app: str) -> int:
    notes = [n for a in api("GET", f"/api/app-notes?app={app}")["apps"] for n in a["notes"]]
    for n in notes:
        api("POST", f"/api/app-notes/{n['id']}/retire", {})
    return len(notes)


def reset(app: str, clear: bool = False) -> None:
    """Fresh launch: the app force-stopped (or its data cleared, for a task that leaves something behind, like an alarm)
    and the home screen in front (envoy-real is never restored to a snapshot)."""
    adb("shell", "pm", "clear", app) if clear else adb("shell", "am", "force-stop", app)
    adb("shell", "input", "keyevent", "KEYCODE_HOME")
    time.sleep(1.0)


PRICE = re.compile(r"\$\s?\d[\d,]*(?:\.\d{2})?")


def redact(rec: dict) -> dict:
    """A run in an app signed in with the user's own account (Uber, Lyft): numbers only. The answer keeps its prices,
    and the screen's words (addresses, names, approval descriptions, hand-off reasons) are dropped."""
    prices = PRICE.findall(rec.get("result") or "")
    return {**rec, "result": " ".join(prices) or ("(answer redacted)" if rec.get("result") else None), "detail": None,
            "declined": len(rec["declined"]), "handoff": (rec["handoff"] or "").split(":")[0] or None, "private": True}


def run_one(goal: str, app: str, kind: str, timeout_s: float, clear: bool = False, allow_phone: bool = False,
            private: bool = False) -> dict:
    reset(app, clear)
    retired = retire_notes(app) if kind == "first" else 0
    t0 = time.time()
    tid = api("POST", "/api/tasks", {"goal": goal, "phone": DEVICE})["id"]
    rec_device = DEVICE
    declined: list[str] = []
    handoff = None
    end = None
    while True:
        got = api("GET", f"/api/tasks/{tid}")
        task = got["task"]
        status = task.get("status")
        if status == "waiting_approval" and task.get("waiting_for"):
            a = api("GET", f"/api/approvals/{task['waiting_for']}")
            if a.get("status") == "pending":
                api("POST", f"/api/approvals/{a['id']}", {"nonce": a["nonce"], "decision": "decline"})
                declined.append(a.get("description") or "")
        elif status == "needs_you":
            handoff = f"{task.get('waiting_for')}: {task.get('detail')}"
            if task.get("waiting_for") == "phone":
                # "Use your Android phone?": yes only for a run the user asked to measure on their phone (--allow-phone)
                api("POST", f"/api/tasks/{tid}/phone", {"allow": allow_phone})
                if allow_phone:
                    handoff, end = None, None
                    time.sleep(0.5)
                    continue
            else:  # a sign-in screen or a bot check: recorded, never done
                api("POST", f"/api/tasks/{tid}/stop", {})
            end = end or time.time()
        if status in ENDED and status != "needs_you":
            end = end or time.time()
            break
        if end and time.time() - end > 10:
            break
        if time.time() - t0 > timeout_s:
            api("POST", f"/api/tasks/{tid}/stop", {})
            handoff = handoff or f"timed out after {timeout_s:.0f} s"
            end = time.time()
            break
        time.sleep(0.5)
    for _ in range(60):  # the cost of what it wrote to memory and its notes lands after the phone is free
        task = api("GET", f"/api/tasks/{tid}")["task"]
        if task.get("memory") is not None or task.get("status") != "done":
            break
        time.sleep(1)
    time.sleep(3)
    task = api("GET", f"/api/tasks/{tid}")["task"]
    cost, calls_logged = logged_cost(tid)
    rec = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "app": app, "kind": kind, "goal": goal, "task_id": tid,
           "status": task.get("status"), "ran": task.get("kind"), "routine": task.get("routine"), "result": task.get("result"),
           "detail": task.get("detail"), "duration_s": round(end - t0, 1), "model_calls": task.get("model_calls"),
           "cost_usd": cost, "cost_at_standard_usd": task.get("cost_usd"), "calls_logged": calls_logged,
           "declined": declined, "handoff": handoff, "notes_retired": retired, "cleared": clear, "device": rec_device,
           "main": subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()}
    if private:
        rec = redact(rec)
    runs = json.loads(RUNS_FILE.read_text()) if RUNS_FILE.exists() else []
    runs.append(rec)
    OUT.mkdir(parents=True, exist_ok=True)
    RUNS_FILE.write_text(json.dumps(runs, indent=1, ensure_ascii=False))
    print(f"{rec['status']:9s} {rec['ran'] or '-':8s} {rec['duration_s']:6.1f}s calls={rec['model_calls']}/{calls_logged} "
          f"${cost:.4f} {tid} {(rec['result'] or rec['detail'] or '')[:160]}" + (f" | HANDOFF {handoff}" if handoff else "")
          + (f" | declined {len(declined)}" if declined else ""), flush=True) if not private else print(
        f"{rec['status']:9s} {rec['ran'] or '-':8s} {rec['duration_s']:6.1f}s calls={rec['model_calls']}/{calls_logged} ${cost:.4f} {tid} "
        f"{rec['result'] or ''} | handoff {rec['handoff']} | declined {rec['declined']}", flush=True)
    return rec


async def save(task_id: str, by: str, note: str) -> None:
    sys.path.insert(0, str(REPO / "backend"))
    from agent.trace import RUNS
    from routines.compiler import compile_trace
    from routines.model import dump_yaml
    from routines.store import RoutineStore

    trace = sorted(RUNS.glob(f"{task_id}-r*"))[-1]  # the runner's agent trace: <task>-r<attempt>
    routine, report = await compile_trace(trace)
    print(dump_yaml(routine))
    print("# dropped:", *[f"#   step {n}: {why}" for n, why in report.dropped], sep="\n")
    print(f"# compiler {report.model}: {report.latency_s} s, ${report.cost_at_standard_usd:.4f}")
    for w in report.warnings:
        print(f"# warning: {w}")
    saved = RoutineStore().add(routine, {"by": by, "how": f"compiled from {task_id} (envoy-real, first run on hybrid). {note}".strip(),
                                         "checked": time.strftime("%Y-%m-%d %H:%M")})
    print(f"saved {saved.routine} v{saved.version}")


def summary(app: str | None) -> None:
    runs = [r for r in (json.loads(RUNS_FILE.read_text()) if RUNS_FILE.exists() else []) if not app or r["app"] == app]
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in runs:
        groups.setdefault((r["app"], r["kind"]), []).append(r)
    for (a, kind), rs in groups.items():
        ok = [r for r in rs if r["status"] == "done"]
        avg = lambda k, xs: sum(x[k] or 0 for x in xs) / len(xs) if xs else 0  # noqa: E731
        print(f"{a} {kind}: {len(ok)}/{len(rs)} done; mean {avg('duration_s', ok):.1f} s, ${avg('cost_usd', ok):.4f}, "
              f"{avg('model_calls', ok):.1f} calls (done runs)")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--app", required=True, help="the app's package (force-stopped first; its notes retired before a first run)")
    r.add_argument("--kind", choices=["first", "replay"], required=True)
    r.add_argument("--goal", action="append", required=True)
    r.add_argument("--timeout-s", type=float, default=300)
    r.add_argument("--clear", action="store_true", help="clear the app's data before each run (a task that leaves state)")
    r.add_argument("--serial", default=SERIAL, help="adb serial of the device (default envoy-real)")
    r.add_argument("--device", default=DEVICE, help="the API's device id (default envoy-real; a phone is phone-<serial>)")
    r.add_argument("--private", action="store_true", help="an app signed in with the user's own account: keep numbers only")
    r.add_argument("--allow-phone", action="store_true", help="answer yes to \"use your Android phone?\" (the user asked for this phone)")
    s = sub.add_parser("save")
    s.add_argument("task_id")
    s.add_argument("--by", default="loop-b")
    s.add_argument("--note", default="")
    m = sub.add_parser("summary")
    m.add_argument("--app")
    args = ap.parse_args()
    if args.cmd == "run":
        globals().update(SERIAL=args.serial, DEVICE=args.device)  # adb() and run_one() read these
        for goal in args.goal:
            run_one(goal, args.app, args.kind, args.timeout_s, args.clear, args.allow_phone, args.private)
    elif args.cmd == "save":
        asyncio.run(save(args.task_id, args.by, args.note))
    else:
        summary(args.app)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
