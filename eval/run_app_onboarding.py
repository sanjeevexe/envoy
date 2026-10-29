"""Apps the emulator doesn't have yet, measured on envoy-real (docs/app-routing-onboarding.md).

  uv run --project backend python eval/run_app_onboarding.py --label today --goal "In the Wikipedia app, ..."
  uv run --project backend python eval/run_app_onboarding.py --label install --goal "..." --goal "..."
  uv run --project backend python eval/run_app_onboarding.py --uninstall org.wikipedia     # put envoy-real back as it was

Each goal runs as a task through the task runner, the same code path as a request from the web app, on envoy-real, with:
- its own data: tasks, memory and routines in a fresh folder under --data (never data/api, data/memory.db or the library);
- no phone: phone discovery is off, so your Android phone is never touched;
- nobody there: every approval and every "use your phone?" ask is declined by this script, and a take-over request
  waits --takeover-s seconds and ends the task (a sign-in is recorded, never done).
Standard tier only (real apps). Results: eval/results/app_onboarding/<label>.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "eval" / "results" / "app_onboarding"
SERIAL = "emulator-5556"  # envoy-real


def adb(*args: str) -> str:
    return subprocess.run(["adb", "-s", SERIAL, *args], capture_output=True, text=True, timeout=60).stdout


def installed(pkg: str) -> bool:
    return f"package:{pkg}" in adb("shell", "pm", "list", "packages", pkg).split()


async def run(goals: list[str], label: str, data: Path, takeover_s: float, install: bool, device: str | None = None) -> list[dict]:
    data.mkdir(parents=True, exist_ok=True)
    os.environ["ENVOY_API_DIR"] = str(data / "api")  # read when api.store is imported
    sys.path.insert(0, str(REPO / "backend"))
    import api.devices as devices_mod
    from api.devices import DevicePool
    from api.events import EventBus
    from api.runner import TaskRunner
    from api.store import TaskStore
    from memory.store import MemoryStore
    from models.adapter import ModelAdapter
    from routines.store import RoutineStore

    devices_mod.discover = lambda: []  # no phone: the person's own phone is never looked at
    loop = asyncio.get_running_loop()
    bus = EventBus()
    bus.bind(loop)
    (data / "api").mkdir(parents=True, exist_ok=True)
    store = TaskStore(data / "api" / "envoy.db")
    pool = DevicePool(bus)
    runner = TaskRunner(store, bus, pool, MemoryStore(data / "memory.db"), RoutineStore(data / "routines"), ModelAdapter(),
                        takeover_timeout_s=takeover_s, approval_timeout_s=120)
    runner.loop = loop
    if hasattr(runner, "install_apps"):
        runner.install_apps = install
    events: list[dict] = []

    def on_event(ev: dict) -> None:
        kind, tid = ev.get("type"), ev.get("task_id")
        if kind in ("approval_requested", "phone_requested", "takeover_requested", "settings"):
            events.append({"t": time.time(), "type": kind, "task_id": tid, "reason": ev.get("reason"),
                           "approval": (ev.get("approval") or {}).get("description")})
        if kind == "approval_requested":  # nobody there: declined, never approved
            aid = (ev.get("approval") or {}).get("id")
            appr = runner.approvers.get(tid or "")
            if appr is not None and aid:
                loop.call_later(1.0, lambda: appr.decide(aid, False, "measurement script"))
        elif kind == "phone_requested":
            loop.call_later(1.0, lambda: runner.answer_phone(tid, False, "measurement script"))

    bus.listeners.append(on_event)
    rows = []
    for goal in goals:
        t0 = time.time()
        task = runner.start(goal, "eval", phone=device)
        tid = task["id"]
        job = runner.jobs[tid]
        await job
        final = store.get(tid) or {}
        steps = store.steps(tid)
        row = {"goal": goal, "task_id": tid, "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "status": final.get("status"), "result": final.get("result"), "detail": final.get("detail"), "app": final.get("app"),
               "kind": final.get("kind"), "device": final.get("device"), "model_calls": final.get("model_calls"),
               "cost_usd": final.get("cost_usd"), "duration_s": round(time.time() - t0, 1),
               "steps": [{"t": round(s.get("time", t0) - t0, 1) if isinstance(s.get("time"), (int, float)) else None,
                          **{k: s.get(k) for k in ("kind", "text", "status", "reason", "error") if s.get(k)}} for s in steps],
               "events": [{**e, "t": round(e["t"] - t0, 1)} for e in events if e["task_id"] == tid],
               "installed_after": installed(final["app"]) if final.get("app") else None}
        rows.append(row)
        print(f"{row['status']:10s} {row['duration_s']:6.1f}s calls={row['model_calls']} ${row['cost_usd']} app={row['app']} "
              f"{(row['result'] or row['detail'] or '')[:120]}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{label}.json"
    path.write_text(json.dumps({"label": label, "serial": SERIAL, "install_on_demand": install, "device": device, "runs": rows}, indent=1,
                               ensure_ascii=False))
    print(f"wrote {path.relative_to(REPO)}")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--goal", action="append", default=[])
    ap.add_argument("--label", default="run")
    ap.add_argument("--data", type=Path, default=None, help="a fresh folder for this run's tasks, memory and routines")
    ap.add_argument("--takeover-s", type=float, default=30.0)
    ap.add_argument("--no-install", action="store_true", help="install on demand off (today's behavior)")
    ap.add_argument("--device", default=None, help="run on this device instead of the one routing picks (e.g. envoy-real)")
    ap.add_argument("--uninstall", action="append", default=[], help="uninstall a package this measurement installed")
    args = ap.parse_args()
    for pkg in args.uninstall:
        print(pkg, adb("uninstall", pkg).strip() or "not installed")
    if not args.goal:
        return 0
    data = args.data or Path(os.environ.get("TMPDIR", "/tmp")) / f"envoy-onboarding-{args.label}-{int(time.time())}"
    asyncio.run(run(args.goal, args.label, data, args.takeover_s, not args.no_install, args.device))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
