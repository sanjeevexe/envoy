"""Change alerts, end to end on envoy-test: SkyLark's gate changes, a watcher reruns the gate routine every minute, and a
fake push service (it checks VAPID and decrypts, the way Apple's service and the iPhone would) receives "Gate changed: …".

  scripts/start_emulator.sh envoy-test
  META_DAILY_COST_CAP_USD=1 uv run --project backend python eval/run_alerts.py [--changes C14 D3 B12] [--scratch DIR]

Everything runs on a copy of the API, in this process, on 127.0.0.1:8712: its own data dir and session token (in the
scratch folder), memory built from the demo inbox at a scratch path, and a scratch copy of data/routines. Its only push
subscription is the fake service, so nothing reaches a real phone. The API on :8700 and data/api/ are never touched.

1. SkyLark is seeded with the demo bookings, signed in: SL 482 to Chicago (KX7Q2M), gate B12.
2. Triggers, created through POST /api/triggers with the bodies the Triggers page sends:
   - "Watch my gate": `watch`, every minute, alerts on, routine `skylark_get_flight_gate` (0 model calls);
   - "When my gate changes": `fact_changed` Flight.gate → routine `skylark_check_flight_status`, with the flight number
     as a typed value from the changed Flight.
3. Baseline runs: memory already knows the gate (or sees it first): no push.
4. For each new gate: SkyLark's SET_GATE debug broadcast at t0, then wait for the push. Latency = push received − t0,
   split into waiting for the next watcher run, the routine run, the memory write (one extraction call on the final
   screen) and the push. The changes are made at different points in the watcher's minute.
5. One more run after the last change: no repeat push.
6. Memory: the flight's current gate, its gate history and each value's source. The fact-changed trigger started one
   task per change, with typed values only.
7. Teardown: triggers paused (kept, so the web app can show them), SkyLark left the way scripts/demo_setup.py leaves it
   (demo bookings, signed out, variant 0).

Results: eval/results/alerts/alerts.json and alerts.md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "eval" / "results" / "alerts"
PORT = 8712
SERIAL, AVD = "emulator-5554", "envoy-test"
CODE = "KX7Q2M"  # the demo's Chicago trip: SL 482, gate B12


def configure(scratch: Path) -> None:
    """Before any api import: this copy's own data dir, port and address."""
    os.environ["ENVOY_API_DIR"] = str(scratch / "api")
    os.environ["ENVOY_PORT"] = str(PORT)
    os.environ["ENVOY_PUBLIC_URL"] = f"http://127.0.0.1:{PORT}"
    os.environ.setdefault("META_DAILY_COST_CAP_USD", "1")
    for p in (REPO / "backend", REPO / "backend" / "tests", REPO / "scripts", REPO / "eval"):
        sys.path.insert(0, str(p))


steps: list[dict[str, Any]] = []
T0 = time.time()


def log(name: str, ok: bool, **kw: Any) -> None:
    steps.append({"step": name, "ok": ok, "t": round(time.time() - T0, 1), **kw})
    print(f"{'OK ' if ok else 'BAD'} {name}: " + ", ".join(f"{k}={v}" for k, v in kw.items())[:500], flush=True)


async def build_memory(db: Path) -> dict[str, Any]:
    """The demo memory, built from the demo inbox the way scripts/demo_setup.py builds it, at a scratch path."""
    from integrations.mail import LocalMailbox
    from memory.service import MemoryService
    from memory.store import MemoryStore
    from models.adapter import ModelAdapter
    from run_memory import bookings_for_eval
    from skylark_mail import build_inbox, write_inbox
    inbox = db.parent / "inbox"
    write_inbox(build_inbox(bookings_for_eval(), seed=3), inbox)
    store = MemoryStore(db)
    adapter = ModelAdapter()
    svc = MemoryService(store, adapter, data_scope="test_app")
    mails, _ = LocalMailbox(inbox).fetch(None)
    for m in mails:
        await svc.ingest_email(m, task_id="demo-inbox")
    store.commit()
    return {"emails": len(mails), "trips": len(store.entities("Trip")), "flights": len(store.entities("Flight"))}


def spent(since: float) -> dict[str, Any]:
    from models.adapter import COST_LOG
    calls, usd = 0, 0.0
    if COST_LOG.exists():
        for line in COST_LOG.read_text().splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            try:
                at = datetime.fromisoformat(str(r.get("time"))).timestamp()
            except ValueError:
                continue
            if at >= since:
                calls += 1
                usd += float(r.get("cost_usd") or 0)
    return {"model_calls": calls, "cost_usd": round(usd, 4), "log": str(COST_LOG.relative_to(REPO))}


def adb(*args: str, timeout: float = 30) -> str:
    return subprocess.run(["adb", "-s", SERIAL, *args], capture_output=True, text=True, timeout=timeout).stdout.strip()


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--changes", nargs="+", default=["C14", "D3", "B12"])
    ap.add_argument("--offsets", nargs="+", type=float, default=[15, 45, 30],
                    help="seconds after a watcher run starts to change the gate, one per change (cycled)")
    ap.add_argument("--scratch", default=os.environ.get("ENVOY_ALERTS_SCRATCH") or str(Path(os.environ.get("TMPDIR", "/tmp")) / "envoy-alerts"))
    ap.add_argument("--hold", type=float, default=0, help="keep the API copy up this many seconds at the end")
    ap.add_argument("--memory-only", action="store_true", help="only build the scratch memory (no phone needed)")
    args = ap.parse_args()
    scratch = Path(args.scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    configure(scratch)
    db = scratch / "memory.db"
    if args.memory_only:
        t = time.time()
        built = await build_memory(db) if not db.exists() else {"exists": True}
        print(json.dumps({**built, "path": str(db), "cost": spent(t)}), flush=True)
        (scratch / "memory_build.json").write_text(json.dumps({**built, "cost": spent(t)}))
        return 0

    import httpx
    import uvicorn
    from api.app import build, session_token
    from api.store import TaskStore
    from demo_setup import demo_fixtures
    from memory.retrieval import Retriever
    from memory.store import MemoryStore
    from routines.store import RoutineStore
    from test_phase5 import FakePushService
    from testapps.skylark import SkyLark

    started_at = time.time()
    if adb("get-state") != "device":
        log("envoy-test is running", False, serial=SERIAL)
        return 1
    if not db.exists():
        built = await build_memory(db)
        log("demo memory built from the inbox (scratch copy)", built["flights"] > 0, **built, path=str(db))
    routines_dir = scratch / "routines"
    if not routines_dir.exists():
        shutil.copytree(REPO / "data" / "routines", routines_dir)  # run bookkeeping stays out of the tracked files
    memory = MemoryStore(db)
    tasks = TaskStore(scratch / "api" / "envoy.db")
    app_, ctx = build("demo", memory=memory, tasks=tasks, routines=RoutineStore(routines_dir))
    token = session_token()
    H = {"Authorization": f"Bearer {token}"}
    server = uvicorn.Server(uvicorn.Config(ctx.asgi, host="127.0.0.1", port=PORT, log_level="warning"))
    serving = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)
    base = f"http://127.0.0.1:{PORT}"
    log("API copy up", True, base=base, data_dir=os.environ["ENVOY_API_DIR"], memory=str(db), scheduler_every_s=ctx.scheduler.every_s)

    sky = SkyLark(SERIAL)
    await asyncio.to_thread(sky.prepare, demo_fixtures(signed_in=True), 0)
    gate0 = (await asyncio.to_thread(sky.trip, CODE))["flight"]["gate"]
    log("SkyLark seeded, signed in", gate0 == "B12", trip=CODE, gate=gate0)

    svc = FakePushService()
    orig = svc.server.RequestHandlerClass.do_POST

    def stamped(handler: Any) -> None:  # when each push arrives
        n = len(svc.received)
        orig(handler)
        if len(svc.received) > n:
            svc.received[-1]["at"] = time.time()
    svc.server.RequestHandlerClass.do_POST = stamped

    flight = next(e["id"] for e in memory.entities("Flight") if (memory.current(e["id"], "number") or {}).get("value") == "SL 482")
    report: dict[str, Any] = {"started": started_at, "avd": AVD, "serial": SERIAL, "flight": flight,
                              "commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()}
    report["gate_in_memory_before"] = (memory.current(flight, "gate") or {}).get("value")
    samples: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(base_url=base, headers=H, timeout=30) as c:
            r = await c.post("/api/push/subscribe", json={"subscription": svc.subscription("/push/alerts-eval")})
            subs = ctx.pusher.subscriptions()
            log("fake push service is the only subscription", r.status_code == 200 and len(subs) == 1, subscriptions=[s["service"] for s in subs])
            if len(subs) != 1:
                return 1
            watch = (await c.post("/api/triggers", json={
                "kind": "watch", "name": "Watch my gate", "spec": {"every_minutes": 1, "alert": True},
                "action": {"routine": "skylark_get_flight_gate", "inputs": {"trip_city": "Chicago"}, "goal": "What's my gate for Chicago?"}})).json()
            changed = (await c.post("/api/triggers", json={
                "kind": "fact_changed", "name": "When my gate changes", "spec": {"entity_type": "Flight", "attribute": "gate"},
                "action": {"routine": "skylark_check_flight_status", "inputs_from": {"flight_number": "flight.number"},
                           "goal": "My gate moved to {change.new} (was {change.old}): check flight {flight.number}"}})).json()
            log("triggers created", "id" in watch and "id" in changed, watcher=watch.get("spec"), fact_changed=changed.get("spec"))

            async def watcher_runs() -> list[dict[str, Any]]:
                return [t for t in (await c.get("/api/tasks", params={"limit": 200})).json() if t["source"] == "trigger:Watch my gate"]

            async def finished_run(after: float, timeout: float = 150) -> dict[str, Any] | None:
                """The first watcher run started after `after`, once its memory is written (or it failed)."""
                t = time.time()
                while time.time() - t < timeout:
                    for task in sorted(await watcher_runs(), key=lambda x: x["created_at"]):
                        if task["created_at"] < after:
                            continue
                        if task["status"] in ("failed", "stopped", "declined", "needs_you"):
                            return task
                        if task["status"] == "done" and task.get("memory") is not None:
                            await asyncio.sleep(0.5)  # the change step and push follow the memory step on the loop
                            return task
                        break
                    await asyncio.sleep(0.5)
                return None

            async def detail(tid: str) -> dict[str, Any]:
                return (await c.get(f"/api/tasks/{tid}")).json()

            # Baseline: memory already has the gate (or sees it now for the first time), and the app shows the same gate.
            for i in range(2):
                n = len(svc.received)
                run = await finished_run(T0 if i == 0 else run["created_at"] + 1)  # type: ignore[has-type]
                d = await detail(run["id"]) if run else {"steps": []}
                ch = [s for s in d["steps"] if s["kind"] == "change"]
                await asyncio.sleep(1)
                log(f"baseline run {i + 1}: gate {gate0}, nothing changed → no push", bool(run) and run["status"] == "done" and not ch and len(svc.received) == n,
                    task=run and run["id"], result=run and run["result"], change_steps=ch, pushes=len(svc.received) - n,
                    memory_gate=(memory.current(flight, "gate") or {}).get("value"))
            last_run = run

            for i, gate in enumerate(args.changes):
                offset = args.offsets[i % len(args.offsets)]
                wait = last_run["created_at"] + offset - time.time()
                if wait > 0:
                    await asyncio.sleep(wait)
                old = (await asyncio.to_thread(sky.trip, CODE))["flight"]["gate"]
                n = len(svc.received)
                t_set = time.time()
                await asyncio.to_thread(sky.set_gate, CODE, gate)
                t_set_done = time.time()
                now_gate = (await asyncio.to_thread(sky.trip, CODE))["flight"]["gate"]
                got = None
                deadline = time.time() + 180
                while time.time() < deadline and got is None:
                    got = next((g for g in svc.received[n:] if g["payload"]["kind"] == "change"), None)
                    await asyncio.sleep(0.05)
                if got:  # the run that saw it: the push opens it
                    await asyncio.sleep(1)
                    d = await detail(got["payload"]["url"].split("task=", 1)[-1])
                    run = d["task"] if d.get("task", {}).get("source") == "trigger:Watch my gate" else None
                else:
                    run = await finished_run(t_set)
                    d = await detail(run["id"]) if run else {"task": {}, "steps": []}
                saving = next((s["time"] for s in d["steps"] if s["kind"] == "note" and s["text"].startswith("saving what it saw")), None)
                mem_step = next((s["time"] for s in d["steps"] if s["kind"] == "memory"), None)
                ch = [s for s in d["steps"] if s["kind"] == "change"]
                sample = {"from": old, "to": gate, "offset_in_minute_s": offset, "set_at": t_set, "app_gate_after_set": now_gate,
                          "task": run and run["id"], "push": got and got["payload"], "push_received_at": got and got.get("at")}
                if got and run:
                    sample["latency_s"] = round(got["at"] - t_set, 2)
                    sample["split_s"] = {
                        "wait_for_next_watcher_run": round(run["created_at"] - t_set, 2),
                        "routine_run": round((saving or run["created_at"]) - run["created_at"], 2),
                        "memory_write": round((mem_step or 0) - (saving or 0), 2) if mem_step and saving else None,
                        "alert_and_push": round(got["at"] - mem_step, 3) if mem_step else None,
                        "push_send_to_receive": round(got["at"] - got["payload"]["sent_at"], 3)}
                samples.append(sample)
                p = (got or {}).get("payload") or {}
                log(f"gate {old} → {gate}: one push", bool(got) and p.get("title") == f"Gate changed: {old} → {gate}" and p.get("url") == f"/?task={run and run['id']}"
                    and "Flight SL 482" in p.get("body", "") and len([g for g in svc.received[n:] if g['payload']['kind'] == 'change']) == 1,
                    title=p.get("title"), body=p.get("body"), url=p.get("url"), latency_s=sample.get("latency_s"), split=sample.get("split_s"),
                    change_steps=[(s["text"], s["pushed"], s.get("why_not")) for s in ch], set_broadcast_s=round(t_set_done - t_set, 2))
                last_run = run or last_run
                memory_gate = (memory.current(flight, "gate") or {}).get("value")
                log(f"memory's gate is now {gate}", memory_gate == gate, memory_gate=memory_gate)

            n = len(svc.received)
            run = await finished_run(last_run["created_at"] + 1)
            await asyncio.sleep(2)
            d = await detail(run["id"]) if run else {"steps": []}
            log("the next run sees the same gate: no repeat push", bool(run) and run["status"] == "done" and len(svc.received) == n
                and not [s for s in d["steps"] if s["kind"] == "change"], task=run and run["id"], result=run and run["result"], pushes=len(svc.received) - n)

            # The fact-changed trigger: one status check per change, with typed values only.
            await asyncio.sleep(12)  # its last task may still be running
            fc = sorted([t for t in (await c.get("/api/tasks", params={"limit": 200})).json() if t["source"] == "trigger:When my gate changes"],
                        key=lambda t: t["created_at"])
            first_change = samples[0]["set_at"] if samples else time.time()
            expect = [f"My gate moved to {s['to']} (was {s['from']}): check flight SL 482" for s in samples]
            log("fact-changed trigger: one task per change, typed values only", [t["goal"] for t in fc] == expect and all(t["created_at"] > first_change for t in fc),
                tasks=[{"goal": t["goal"], "routine": t.get("routine"), "inputs": t.get("inputs"), "status": t["status"], "result": t.get("result"),
                        "after_change_s": round(t["created_at"] - s["set_at"], 1) if (s := next((x for x in samples if x["to"] in t["goal"]), None)) else None}
                       for t in fc])
            report["fact_changed_tasks"] = [{k: t.get(k) for k in ("id", "goal", "routine", "inputs", "status", "result", "created_at")} for t in fc]

            ent = (await c.get(f"/api/memory/entity/{flight}")).json()
            hist = [{"value": f["value"], "current": f["current"], "valid_from": f["valid_from"], "sources": [s["where"] for s in f["sources"]]}
                    for f in ent["facts"] if f["attribute"] == "gate"]
            cur = next((f for f in ent["facts"] if f["attribute"] == "gate" and f["current"]), None)
            writer = memory.db.execute("select source from facts where id = ?", (cur["id"],)).fetchone() if cur else None
            src = memory.source(writer[0]) if writer and writer[0] else None  # the source that wrote the value (later runs only saw it again)
            ref = (src or {}).get("reference") or {}
            log("memory shows the new gate with its source", bool(cur) and cur["value"] == args.changes[-1] and ref.get("task_id") == last_run["id"],
                current=cur and cur["value"], source=cur and cur["sources"][0]["where"], source_kind=(src or {}).get("kind"), source_task=ref.get("task_id"),
                history=[h["value"] for h in hist])
            report["gate_history"] = hist
            report["alerts"] = (await c.get("/api/alerts")).json()
            report["other_changes_not_pushed"] = [a for a in report["alerts"] if not a["pushed"]]
            for t in (await c.get("/api/triggers")).json():
                await c.post(f"/api/triggers/{t['id']}", json={"enabled": False})
            report["triggers"] = (await c.get("/api/triggers")).json()
            log("triggers paused (kept for the web app)", all(not t["enabled"] for t in report["triggers"]), n=len(report["triggers"]))
            if args.hold:
                print(f"holding the API copy for {args.hold:.0f} s: {base}/login?k=<token in {os.environ['ENVOY_API_DIR']}/session_token>", flush=True)
                await asyncio.sleep(args.hold)
    finally:
        try:
            await asyncio.to_thread(sky.prepare, demo_fixtures(signed_in=False), 0)  # as scripts/demo_setup.py leaves it
            st = await asyncio.to_thread(sky.state)
            log("SkyLark left as demo_setup leaves it (demo bookings, signed out, variant 0)",
                not st.get("signed_in") and next(t for t in st["trips"] if t["code"] == CODE)["flight"]["gate"] == "B12", signed_in=st.get("signed_in"))
        except Exception as e:  # noqa: BLE001 - the phone may be gone (revoked); say so
            log("SkyLark reset", False, error=f"{type(e).__name__}: {e}"[:200])
        server.should_exit = True
        await serving

    lat = [s["latency_s"] for s in samples if s.get("latency_s") is not None]
    report.update({"finished": time.time(), "steps": steps, "samples": samples, "pushes": [g["payload"] for g in svc.received],
                   "latency_s": {"samples": lat, "min": min(lat, default=None), "max": max(lat, default=None),
                                 "mean": round(sum(lat) / len(lat), 2) if lat else None},
                   "cost": spent(started_at), "ok": all(s["ok"] for s in steps)})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "alerts.json").write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps({"ok": report["ok"], "latency_s": report["latency_s"], "cost": report["cost"]}), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
