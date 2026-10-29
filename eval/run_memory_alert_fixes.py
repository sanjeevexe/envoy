"""Device check for two memory/alert fixes, on envoy-test (SkyLark), through a copy of the API on 127.0.0.1:8751.

  META_DAILY_COST_CAP_USD=1 uv run --project backend python eval/run_memory_alert_fixes.py [--scratch DIR]

1. Stale gate (personal benchmark M4): memory holds gate B9 seen 3 h ago; SkyLark shows B12. "What's my gate for my
   Chicago flight?" in chat must check the app (a task), not answer "B9 (may have changed)", and the task reads B12.
2. A change through a merge: a watcher run reads the next gate (C14) onto a second Flight entity (the flight's natural
   key was held back from key lookup for that run, the way an app read lands before memory knows it is the same
   flight); memory then merges the two the way MemoryService does on a shared natural key. One push "Gate changed:
   B12 → C14", none on the next run.

Memory is seeded at a scratch path (no inbox build); the only push subscription is a fake push service. :8700 and
data/api/ are never touched. Results: eval/results/memory_alert_fixes/report.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "eval" / "results" / "memory_alert_fixes"
PORT = 8751
SERIAL = "emulator-5554"
CODE = "KX7Q2M"  # the demo's Chicago trip: SL 482, gate B12
T0 = time.time()
steps: list[dict[str, Any]] = []


def log(name: str, ok: bool, **kw: Any) -> None:
    steps.append({"step": name, "ok": ok, "t": round(time.time() - T0, 1), **kw})
    print(f"{'OK ' if ok else 'BAD'} {name}: " + ", ".join(f"{k}={v}" for k, v in kw.items())[:600], flush=True)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", default=str(Path(os.environ.get("TMPDIR", "/tmp")) / "envoy-memory-alert-fixes"))
    args = ap.parse_args()
    scratch = Path(args.scratch)
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    os.environ["ENVOY_API_DIR"] = str(scratch / "api")
    os.environ["ENVOY_PORT"] = str(PORT)
    os.environ["ENVOY_PUBLIC_URL"] = f"http://127.0.0.1:{PORT}"
    os.environ.setdefault("META_DAILY_COST_CAP_USD", "1")
    for p in (REPO / "backend", REPO / "backend" / "tests", REPO / "scripts", REPO / "eval"):
        sys.path.insert(0, str(p))

    import httpx
    import uvicorn
    from api.app import build, session_token
    from api.store import TaskStore
    from demo_setup import demo_fixtures
    from memory.store import MemoryStore
    from routines.store import RoutineStore
    from run_alerts import spent
    from test_phase5 import FakePushService
    from testapps.skylark import SkyLark

    sky = SkyLark(SERIAL)
    await asyncio.to_thread(sky.prepare, demo_fixtures(signed_in=True), 0)
    trip = await asyncio.to_thread(sky.trip, CODE)
    fl = trip["flight"]
    log("SkyLark seeded, signed in", fl["gate"] == "B12", trip=CODE, flight=fl)

    db = scratch / "memory.db"
    memory = MemoryStore(db)
    three_h = time.time() - 3 * 3600
    src = memory.add_source("app_screen", {"app": "com.skylark.air", "screen": "TripDetailsActivity", "task_id": "earlier"}, captured_at=three_h)
    t, f = memory.create_entity("Trip"), memory.create_entity("Flight")
    memory.observe(t, "destination", "Chicago", source=src, observed_at=three_h)
    memory.observe(t, "confirmation_code", CODE, source=src, observed_at=three_h)
    for a, v in (("number", fl.get("number") or "SL 482"), ("date", fl.get("date") or "Fri, Oct 30, 2026"), ("gate", "B9")):
        memory.observe(f, a, v, source=src, observed_at=three_h)
    memory.link(t, "includes", f, src)
    memory.commit()
    routines_dir = scratch / "routines"
    shutil.copytree(REPO / "data" / "routines", routines_dir)
    tasks = TaskStore(scratch / "api" / "envoy.db")
    _, ctx = build("demo", memory=memory, tasks=tasks, routines=RoutineStore(routines_dir))
    H = {"Authorization": f"Bearer {session_token()}"}
    server = uvicorn.Server(uvicorn.Config(ctx.asgi, host="127.0.0.1", port=PORT, log_level="warning"))
    serving = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)
    svc = FakePushService()
    report: dict[str, Any] = {"started": T0, "flight": f}
    try:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{PORT}", headers=H, timeout=120) as c:
            await c.post("/api/push/subscribe", json={"subscription": svc.subscription("/push/fixes-eval")})
            log("fake push service is the only subscription", len(ctx.pusher.subscriptions()) == 1)

            async def done(tid: str, timeout: float = 180) -> dict[str, Any]:
                end = time.time() + timeout
                while time.time() < end:
                    d = (await c.get(f"/api/tasks/{tid}")).json()
                    if d["task"]["status"] in ("done", "failed", "stopped", "declined") and (d["task"]["status"] != "done" or d["task"].get("memory") is not None):
                        await asyncio.sleep(1)
                        return (await c.get(f"/api/tasks/{tid}")).json()
                    await asyncio.sleep(0.5)
                return (await c.get(f"/api/tasks/{tid}")).json()

            # ---- 1. stale gate: check the app first ----
            out = (await c.post("/api/chat", json={"message": "What's my gate for my Chicago flight?"})).json()
            tid = (out.get("task") or {}).get("id")
            log("stale gate: chat checks the app instead of answering B9", out.get("kind") == "task" and bool(tid), reply=out.get("reply"), kind=out.get("kind"))
            d = await done(tid) if tid else {"task": {}}
            gate = (memory.current(f, "gate") or {}).get("value")
            log("stale gate: the check read B12", "B12" in str(d["task"].get("result")) and gate == "B12",
                status=d["task"].get("status"), result=d["task"].get("result"), routine=d["task"].get("routine"), memory_gate=gate)
            report["stale"] = {"reply": out.get("reply"), "task": d["task"]}
            pushes0 = len(svc.received)

            # ---- 2. a change that arrives through a merge ----
            watch = (await c.post("/api/triggers", json={
                "kind": "watch", "name": "Watch my gate", "spec": {"every_minutes": 1, "alert": True},
                "action": {"routine": "skylark_get_flight_gate", "inputs": {"trip_city": "Chicago"}, "goal": "What's my gate for Chicago?"}})).json()
            log("watcher created", "id" in watch)

            async def next_run(after: float) -> dict[str, Any]:
                end = time.time() + 150
                while time.time() < end:
                    runs = sorted([t for t in (await c.get("/api/tasks", params={"limit": 50})).json()
                                   if t["source"] == "trigger:Watch my gate" and t["created_at"] > after], key=lambda t: t["created_at"])
                    if runs:
                        return await done(runs[0]["id"])
                    await asyncio.sleep(0.5)
                return {"task": {}, "steps": []}

            base = await next_run(0)
            log("baseline watcher run: B12 again, no push", len(svc.received) == pushes0 and not [s for s in base["steps"] if s["kind"] == "change"],
                result=base["task"].get("result"))

            await asyncio.to_thread(sky.set_gate, CODE, "C14")
            keys = [dict(r) for r in memory.db.execute("select * from entity_keys where entity = ?", (f,)).fetchall()]
            memory.db.execute("delete from entity_keys where entity = ?", (f,))  # this run's read lands on a new entity
            memory.db.commit()
            orig_refresh = memory.refresh_keys
            memory.refresh_keys = lambda eid: [] if eid == f else orig_refresh(eid)  # type: ignore[method-assign]
            run = await next_run(base["task"].get("created_at") or 0)
            memory.refresh_keys = orig_refresh  # type: ignore[method-assign]
            new_ents = [e["id"] for e in memory.entities("Flight") if e["id"] != f]
            merged_from = next((e for e in new_ents if (memory.current(e, "gate") or {}).get("value") == "C14"), None)
            log("watcher run read C14 onto a second Flight entity", merged_from is not None and (memory.current(f, "gate") or {}).get("value") == "B12",
                result=run["task"].get("result"), entities=new_ents, pushes_so_far=len(svc.received) - pushes0)
            for k in keys:
                memory.db.execute("insert or ignore into entity_keys values (?,?,?)", (k["entity"], k["type"], k["key"]))
            memory.commit()
            seq = None
            if merged_from:  # MemoryService's rule: a key that belongs to two entities merges them into the older
                for key in memory.refresh_keys(merged_from):
                    owner = memory.find_by_key("Flight", key)
                    if owner and owner != merged_from:
                        seq = memory.merge(owner, merged_from, f"same natural key {key}")
                if seq is None:
                    seq = memory.merge(f, merged_from, "same flight")
            memory.commit()
            end = time.time() + 40
            while time.time() < end and len(svc.received) == pushes0:
                await asyncio.sleep(0.2)
            got = svc.received[pushes0:]
            title = got[0]["payload"]["title"] if got else None
            log("merge: one push Gate changed: B12 → C14", len(got) == 1 and title == "Gate changed: B12 → C14", merge_seq=seq, title=title,
                body=got[0]["payload"]["body"] if got else None, memory_gate=(memory.current(f, "gate") or {}).get("value"))
            after = await next_run(run["task"].get("created_at") or 0)
            await asyncio.sleep(2)
            log("next watcher run: C14 again, no repeat push", len(svc.received) - pushes0 == 1, result=after["task"].get("result"))
            await c.post(f"/api/triggers/{watch['id']}", json={"enabled": False})
            report["alerts"] = (await c.get("/api/alerts")).json()
    finally:
        try:
            for trig in ctx.tasks.triggers():
                ctx.scheduler.set_enabled(trig["id"], False) if hasattr(ctx.scheduler, "set_enabled") else None
        except Exception:  # noqa: BLE001
            pass
        await asyncio.to_thread(sky.prepare, demo_fixtures(signed_in=False), 0)
        server.should_exit = True
        await serving
        svc.close() if hasattr(svc, "close") else None
    report["cost"] = spent(T0)
    report["steps"] = steps
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(report, indent=1, default=str))
    ok = all(s["ok"] for s in steps)
    print(f"{'ALL OK' if ok else 'SOME FAILED'} · cost {report['cost']}", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
