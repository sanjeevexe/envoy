"""Offers, end to end on envoy-test, with no model calls: an ask-mode trigger fires, its offer ("Check in for SL 482?")
pushes to a fake push service, the user's yes comes from this copy's own session, and skylark_check_in_flight runs
from its routine, with "Confirm check-in" going through as "your request".

  scripts/start_emulator.sh envoy-test        # and claim it: ~/Desktop/Envoy/coord/devices.sh claim envoy-test <owner> 30 offers
  uv run --project backend python eval/run_offers.py --scratch <your scratch dir>

Everything runs on a copy of the API, in this process, on 127.0.0.1:8741: its own data dir and session token (in the
scratch folder), a copy of the demo memory (data/demo/memory.db) and of data/routines. Its only push subscription is the
fake service (it checks VAPID and decrypts, the way Apple's service would), so nothing reaches a real phone. The API on
:8700, data/api/ and the demo memory itself are never touched.

1. SkyLark on envoy-test is signed in, and the trip to check in (the soonest upcoming one, SL 482 to Chicago in the demo)
   isn't checked in yet. It is read, not changed: pass --reseed to seed the demo bookings first (only when the device's
   owner agrees; it resets SkyLark's data).
2. The trigger is the Triggers page's preset "Ask me to check in when check-in opens" (web/lib/trigger-presets.json):
   before_fact on Flight, 24 h before, ask mode, routine skylark_check_in_flight with trip_city from the trip. When the
   flight is more than 24 h away, the window is widened to reach it, so the run can be repeated on another day.
3. The offer: its title, goal and request (the template with its slots empty), and its push.
4. Your yes: POST /api/offers/{id} with this copy's session (the scripted person, as in run_phase4.py). The task's source
   is web, its goal is the card's, and it runs the routine on envoy-test.
5. Confirm check-in: auto-approved as "your request" (no person asked), and the trigger keeps its credit.
6. Model calls and spend from the cost log (expected: none).

Results: eval/results/offers/offers.json and offers.md. SkyLark is left with that trip checked in.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "eval" / "results" / "offers"
PORT = 8741
SERIAL, AVD = "emulator-5554", "envoy-test"
PRESET = "Ask me to check in when check-in opens"

steps: list[dict[str, Any]] = []
T0 = time.time()


def configure(scratch: Path) -> None:
    """Before any api import: this copy's own data dir, port and address."""
    os.environ["ENVOY_API_DIR"] = str(scratch / "api")
    os.environ["ENVOY_PORT"] = str(PORT)
    os.environ["ENVOY_PUBLIC_URL"] = f"http://127.0.0.1:{PORT}"
    os.environ.setdefault("META_DAILY_COST_CAP_USD", "0.30")
    for p in (REPO / "backend", REPO / "backend" / "tests", REPO / "scripts", REPO / "eval"):
        sys.path.insert(0, str(p))


def log(name: str, ok: bool, **kw: Any) -> bool:
    steps.append({"step": name, "ok": ok, "t": round(time.time() - T0, 2), **kw})
    print(f"{'OK ' if ok else 'BAD'} {name}: " + ", ".join(f"{k}={v}" for k, v in kw.items())[:600], flush=True)
    return ok


def spent(since: float) -> dict[str, Any]:
    from models.adapter import COST_LOG
    calls, usd = 0, 0.0
    if COST_LOG.exists():
        for line in COST_LOG.read_text().splitlines():
            try:
                r = json.loads(line)
                at = datetime.fromisoformat(str(r.get("time"))).timestamp()
            except ValueError:
                continue
            if at >= since:
                calls += 1
                usd += float(r.get("cost_usd") or 0)
    return {"model_calls": calls, "cost_usd": round(usd, 4)}


def adb(*args: str, timeout: float = 30) -> str:
    return subprocess.run(["adb", "-s", SERIAL, *args], capture_output=True, text=True, timeout=timeout).stdout.strip()


def upcoming_trip(state: dict[str, Any], now: float) -> dict[str, Any] | None:
    """SkyLark's soonest trip that hasn't left: the one its home screen offers to check in."""
    from memory.types import parse_date
    from api.scheduler import parse_clock
    best = None
    for t in state.get("trips", []):
        f = t.get("flight") or {}
        d, hm = parse_date(f.get("date")), parse_clock(f.get("depart") or "") or (0, 0)
        if d is None or t.get("cancelled") or not t.get("upcoming", True):
            continue
        when = datetime(d.year, d.month, d.day, *hm).timestamp()
        if when > now and (best is None or when < best[0]):
            best = (when, t)
    return best[1] if best else None


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True, help="a folder of your own (the API copy's data, memory and routines)")
    ap.add_argument("--reseed", action="store_true", help="seed SkyLark with the demo bookings first (resets its data)")
    ap.add_argument("--timeout", type=float, default=240, help="seconds to wait for the check-in to finish")
    args = ap.parse_args()
    scratch = Path(args.scratch).resolve()
    if scratch == (REPO / "data").resolve() or (REPO / "data" / "api").resolve() in (scratch, *scratch.parents):
        print("use a scratch folder, not data/", file=sys.stderr)
        return 2
    if (scratch / "api").exists():
        shutil.rmtree(scratch / "api")  # a fresh copy each run: no triggers or offers left from the last one
    scratch.mkdir(parents=True, exist_ok=True)
    configure(scratch)

    import logging

    import httpx
    import uvicorn
    logging.getLogger("httpx").setLevel(logging.WARNING)
    from api.app import build, session_token
    from api.store import TaskStore
    from memory.store import MemoryStore
    from routines.store import RoutineStore
    from test_phase5 import FakePushService
    from testapps.skylark import SkyLark

    started_at = time.time()
    report: dict[str, Any] = {"started": datetime.fromtimestamp(started_at).isoformat(timespec="seconds"), "avd": AVD, "serial": SERIAL,
                              "commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()}
    if not log("envoy-test is running", adb("get-state") == "device", serial=SERIAL):
        return 1
    sky = SkyLark(SERIAL)
    if args.reseed:
        from demo_setup import demo_fixtures
        await asyncio.to_thread(sky.prepare, demo_fixtures(signed_in=True), 0)
        log("SkyLark seeded with the demo bookings, signed in", True)
    state = await asyncio.to_thread(sky.state)
    trip = upcoming_trip(state, time.time())
    ready = bool(state.get("signed_in")) and trip is not None and not trip.get("checked_in")
    log("SkyLark signed in, the next trip not checked in yet", ready, signed_in=state.get("signed_in"),
        trip=(trip or {}).get("code"), flight=((trip or {}).get("flight") or {}).get("number"), checked_in=(trip or {}).get("checked_in"))
    if not ready:
        print("SkyLark isn't ready (signed out, or that trip is already checked in). With the device owner's OK: --reseed", file=sys.stderr)
        return 1

    db = scratch / "memory.db"
    shutil.copy(REPO / "data" / "demo" / "memory.db", db)  # a copy: the demo memory itself is never written
    routines_dir = scratch / "routines"
    if routines_dir.exists():
        shutil.rmtree(routines_dir)
    shutil.copytree(REPO / "data" / "routines", routines_dir)  # run bookkeeping stays out of the tracked files
    memory = MemoryStore(db)
    tasks = TaskStore(scratch / "api" / "envoy.db")
    _, ctx = build("demo", memory=memory, tasks=tasks, routines=RoutineStore(routines_dir), scheduler_every_s=2)
    token = session_token()
    H = {"Authorization": f"Bearer {token}"}
    server = uvicorn.Server(uvicorn.Config(ctx.asgi, host="127.0.0.1", port=PORT, log_level="warning"))
    serving = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)
    base = f"http://127.0.0.1:{PORT}"
    log("API copy up", True, base=base, data_dir=os.environ["ENVOY_API_DIR"], memory=str(db), scheduler_every_s=ctx.scheduler.every_s)

    svc = FakePushService()
    orig = svc.server.RequestHandlerClass.do_POST

    def stamped(handler: Any) -> None:  # when each push arrives
        n = len(svc.received)
        orig(handler)
        if len(svc.received) > n:
            svc.received[-1]["at"] = time.time()
    svc.server.RequestHandlerClass.do_POST = stamped

    flight_no = (trip.get("flight") or {}).get("number")
    flight = next((e["id"] for e in memory.entities("Flight") if (memory.current(e["id"], "number") or {}).get("value") == flight_no), None)
    ok = True
    try:
        async with httpx.AsyncClient(base_url=base, headers=H, timeout=30) as c:
            r = await c.post("/api/push/subscribe", json={"subscription": svc.subscription("/push/offers-eval")})
            subs = ctx.pusher.subscriptions()
            if not log("the fake push service is the only subscription", r.status_code == 200 and len(subs) == 1, subscriptions=[s["service"] for s in subs]):
                return 1
            level = (await c.get("/api/settings/proactivity")).json()["level"]
            log("proactivity", level == "important", level=level)

            # ---- the trigger: the Triggers page's preset, as it sends it ----
            preset = next(p for p in json.loads((REPO / "web" / "lib" / "trigger-presets.json").read_text()) if p["label"] == PRESET)
            body = json.loads(json.dumps(preset["body"]))
            when = next((w for w, eid, _ in ctx.scheduler.occasions(body["spec"]) if eid == flight), None)
            if when is None:
                log("the flight is in memory", False, flight=flight_no)
                return 1
            need = math.ceil((when - time.time()) / 60) + 5
            if need > body["spec"]["minutes_before"]:
                body["spec"]["minutes_before"] = need  # the flight is further away than 24 h: widen the window to reach it
            report["trigger_body"] = body
            t_trigger = time.time()
            trig = (await c.post("/api/triggers", json=body)).json()
            log("ask-mode trigger created", "id" in trig and trig["action"].get("ask") is True, trigger=trig.get("name"),
                minutes_before=body["spec"]["minutes_before"], departs=datetime.fromtimestamp(when).isoformat(timespec="minutes"))

            # ---- the offer, not a task ----
            offer = None
            while time.time() - t_trigger < 30 and offer is None:
                got = (await c.get("/api/offers")).json()
                offer = got[0] if got else None
                await asyncio.sleep(0.2)
            t_offer = time.time()
            if not log("the trigger fired an offer", offer is not None, seconds=round(t_offer - t_trigger, 2)):
                return 1
            a = offer["action"]
            report["offer"] = {k: offer[k] for k in ("id", "kind", "title", "body", "key", "expires_at", "preflight", "origin")} | {"goal": a["goal"], "request": a["request"],
                                                                                                                                 "inputs": a.get("inputs"), "routine": a.get("routine")}
            ok &= log("the offer", offer["title"] == f"Check in for {flight_no}?" and a["request"] == "Check me in for my flight to" and a["routine"] == "skylark_check_in_flight",
                      title=offer["title"], goal=a["goal"], request=a["request"], inputs=a.get("inputs"), expires=offer.get("expires_at"))
            ok &= log("nothing started before the yes", (await c.get("/api/tasks")).json() == [])
            while time.time() - t_offer < 10 and not svc.received:
                await asyncio.sleep(0.05)
            push = svc.received[0] if svc.received else None
            p = (push or {}).get("payload") or {}
            report["push"] = {"payload": p, "seconds_after_trigger": round(push["at"] - t_trigger, 2) if push else None,
                              "seconds_after_offer": round(push["at"] - offer["created_at"], 3) if push else None}
            ok &= log("the offer pushed (fake service, decrypted)", p.get("kind") == "offer" and p.get("url") == f"/?offer={offer['id']}",
                      title=p.get("title"), url=p.get("url"), after_offer_s=report["push"]["seconds_after_offer"])

            # ---- your yes ----
            t_yes = time.time()
            r = await c.post(f"/api/offers/{offer['id']}", json={"decision": "accept"})
            decided = r.json()
            tid = decided.get("task_id")
            ok &= log("you said yes (this copy's session)", r.status_code == 200 and decided.get("status") == "accepted" and bool(tid),
                      decided_by=decided.get("decided_by"), task=tid, ms=round((time.time() - t_yes) * 1000))
            if not tid:
                return 1
            task: dict[str, Any] = {}
            while time.time() - t_yes < args.timeout:
                task = (await c.get(f"/api/tasks/{tid}")).json()
                if task["task"]["status"] in ("done", "failed", "declined", "stopped", "needs_you"):
                    break
                await asyncio.sleep(0.5)
            t_done = time.time()
            t, run_steps, approvals = task["task"], task["steps"], task["approvals"]
            report["task"] = {k: t.get(k) for k in ("id", "goal", "request", "source", "status", "result", "detail", "routine", "inputs", "device",
                                                    "model_calls", "cost_usd")}
            report["task"]["seconds"] = round(t_done - t_yes, 1)
            report["steps"] = [{k: s.get(k) for k in ("seq", "kind", "text", "status", "rung", "reason") if s.get(k) is not None} for s in run_steps]
            report["approvals"] = [{k: x.get(k) for k in ("description", "status", "decided_by", "note")} for x in approvals]
            ok &= log("the task", t["source"] == "web" and t["goal"] == a["goal"] and t["request"] == a["request"] and t["status"] == "done",
                      status=t["status"], source=t["source"], device=t.get("device"), result=t.get("result"), detail=t.get("detail"),
                      seconds=report["task"]["seconds"], model_calls=t.get("model_calls"))
            confirm = [x for x in approvals if "confirm" in (x.get("description") or "").lower() or "check" in (x.get("description") or "").lower()]
            ok &= log("Confirm check-in went through as your request", any(x["status"] == "approved" and x["decided_by"] == "your request" for x in confirm),
                      approvals=[(x["description"], x["status"], x["decided_by"]) for x in approvals])
            ok &= log("no approval waited for a person", not any(x["decided_by"] in ("user", "timeout") for x in approvals))
            ok &= log("the trigger keeps its credit", ctx.alerts.started_by.get(tid) == trig["id"] and ctx.offers.trigger_of(tid) == trig["id"])
            after = await asyncio.to_thread(sky.trip, trip["code"])
            ok &= log("SkyLark: the trip is checked in", bool(after.get("checked_in")), trip=trip["code"], checked_in=after.get("checked_in"))
            cost = spent(started_at)
            report["spend"] = cost
            ok &= log("model calls", cost["model_calls"] == 0 and (t.get("model_calls") or 0) == 0, **cost, task_model_calls=t.get("model_calls"))
            report["timings_s"] = {"trigger_to_offer": round(t_offer - t_trigger, 2), "offer_to_push": report["push"]["seconds_after_offer"],
                                   "yes_to_done": report["task"]["seconds"], "total": round(t_done - t_trigger, 1)}
            await c.post(f"/api/triggers/{trig['id']}", json={"enabled": False})
    finally:
        server.should_exit = True
        await serving
    report["ok"] = bool(ok)
    report["steps_log"] = steps
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "offers.json").write_text(json.dumps(report, indent=2, default=str))
    (OUT / "offers.md").write_text(markdown(report))
    print(f"\n{'PASS' if ok else 'FAIL'}: {OUT / 'offers.md'}", flush=True)
    return 0 if ok else 1


def markdown(r: dict[str, Any]) -> str:
    o, t, tm = r.get("offer", {}), r.get("task", {}), r.get("timings_s", {})
    lines = [f"# Offers on envoy-test ({r['started']}, {r['commit']})", "", f"**{'PASS' if r['ok'] else 'FAIL'}**, model calls: "
             f"{r.get('spend', {}).get('model_calls')}, spend: ${r.get('spend', {}).get('cost_usd')}", "",
             "| | |", "| --- | --- |",
             f"| Offer | {o.get('title')} |", f"| What I'll do (goal) | {o.get('goal')} |", f"| Request (what approvals read) | {o.get('request')} |",
             f"| Push | `{(r.get('push') or {}).get('payload', {}).get('url')}`, {tm.get('offer_to_push')} s after the offer |",
             f"| Task | {t.get('status')} on {t.get('device')}, source {t.get('source')}, routine {t.get('routine')} |",
             f"| Result | {t.get('result') or t.get('detail')} |",
             f"| Trigger → offer | {tm.get('trigger_to_offer')} s |", f"| Yes → done | {tm.get('yes_to_done')} s |", "",
             "## Approvals", "", *[f"- {a['description']}: {a['status']} by {a['decided_by']}" for a in r.get("approvals", [])], "",
             "## Steps", "", *[f"- {s['step']}: {'ok' if s['ok'] else 'BAD'}" for s in r.get("steps_log", [])], ""]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
