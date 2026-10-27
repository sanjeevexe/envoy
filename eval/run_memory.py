"""Phase 3 evaluation: the shared memory graph on SkyLark Air and its test inbox.

  uv run --project backend python eval/run_memory.py emails     # extraction + matching from the inbox alone (no phone)
  uv run --project backend python eval/run_memory.py gate       # the gate on the phone: email + app → one trip; gate from memory; a gate change
  uv run --project backend python eval/run_memory.py report     # eval/results/phase3/report.md

Ground truth comes from the bookings that seed both SkyLark and the inbox, so scores are exact. Model calls use the
standard tier; the data is our own test app's.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import statistics
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from integrations.mail import LocalMailbox
from memory.bridge import fill_inputs, notes_for, remember_run
from memory.retrieval import Retriever
from memory.service import MemoryService
from memory.store import MemoryStore
from memory.types import normalize_key_value
from models.adapter import ModelAdapter
from skylark_mail import build_inbox, write_inbox
from skylark_routines import Booking, chicago_booking, compile_booking, fixtures, generate

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "eval" / "results" / "phase3"
WORK = REPO / "data" / "phase3"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save(name: str, payload: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(payload, indent=1, default=str, ensure_ascii=False))


def bookings_for_eval() -> list[Booking]:
    """Chicago (the next trip), Denver, four new bookings, and a second Denver trip on another date (a hard case)."""
    extra = generate(2024, 5)
    second_denver = copy.deepcopy(extra[-1])
    second_denver.city, second_denver.airport, second_denver.code = "Denver", "DEN", "DN7Q4X"
    second_denver.date, second_denver.number = "Fri, Dec 4, 2026", "SL 1192"
    return [chicago_booking(), compile_booking()] + extra[:4] + [second_denver]


class Clock:
    """Real time plus an offset, so staleness can be tested without waiting."""

    def __init__(self) -> None:
        self.offset = 0.0

    def __call__(self) -> float:
        return time.time() + self.offset


# ---- scoring --------------------------------------------------------------------------------------


def score_extraction(extracted: list[Any], truth: list[dict]) -> dict[str, int]:
    """Per attribute in the truth: found with the right value (normalized), wrong value, or missing. Extracted
    values for those attributes that match no truth entity count as wrong."""
    found = wrong = missing = 0
    for t in truth:
        typ = t["type"]
        cands = [e for e in extracted if e.type == typ]
        for attr, val in t.items():
            if attr == "type":
                continue
            vals = [o.value for e in cands for o in e.observations if o.attribute == attr]
            if any(normalize_key_value(attr, v) == normalize_key_value(attr, val) for v in vals):
                found += 1
            elif vals:
                wrong += 1
            else:
                missing += 1
    return {"found": found, "wrong": wrong, "missing": missing}


def entities_by_booking(store: MemoryStore, b: Booking) -> dict[str, list[str]]:
    trips = [e["id"] for e in store.entities("Trip") if normalize_key_value("confirmation_code", (store.current(e["id"], "confirmation_code") or {}).get("value", "")) == b.code]
    flights = [e["id"] for e in store.entities("Flight")
               if normalize_key_value("number", (store.current(e["id"], "number") or {}).get("value", "")) == normalize_key_value("number", b.number)
               and normalize_key_value("date", (store.current(e["id"], "date") or {}).get("value", "")) == normalize_key_value("date", b.date)]
    return {"trips": trips, "flights": flights}


def source_kinds(store: MemoryStore, eid: str) -> set[str]:
    kinds = set()
    for f in store.history(eid):
        s = store.source(f["source"]) if f["source"] else None
        if s:
            kinds.add(s["kind"])
    return kinds


# ---- 1. emails only ---------------------------------------------------------------------------------


async def cmd_emails(args: argparse.Namespace) -> dict:
    bookings = bookings_for_eval()
    mails = build_inbox(bookings, seed=args.seed)
    inbox = WORK / "inbox"
    write_inbox(mails, inbox)
    db = WORK / "emails.db"
    db.unlink(missing_ok=True)
    store = MemoryStore(db)
    svc = MemoryService(store, ModelAdapter(), data_scope="test_app")
    by_name = {m.name: m for m in mails}
    rows, cost, calls = [], 0.0, 0
    emails, _ = LocalMailbox(inbox).fetch(None)
    for mail in emails:
        tm = by_name[mail.id]
        rep = await svc.ingest_email(mail, task_id="p3-emails")
        ext = rep.extracted  # score what the extractor read, before matching and de-duplication
        sc = score_extraction(ext, tm.truth)
        cost += rep.cost_usd
        calls += rep.model_calls
        rows.append({"email": mail.id, "kind": tm.kind, "method": rep.method, "resolved": [(r.type, r.how) for r in rep.resolved],
                     "facts": rep.facts, "merged": rep.merged, "dropped": rep.dropped, **sc})
        print(f"{mail.id:28s} {tm.kind:12s} {rep.method:7s} found={sc['found']:2d} wrong={sc['wrong']} missing={sc['missing']} "
              f"{[(r.type, r.how) for r in rep.resolved]}", flush=True)
    # Matching: one Trip and one Flight per booking; promos created nothing; the two Denver trips stay apart; the cancelled one is cancelled.
    match_rows = []
    for b in bookings:
        eb = entities_by_booking(store, b)
        match_rows.append({"booking": b.code, "city": b.city, "trips": len(eb["trips"]), "flights": len(eb["flights"]),
                           "ok": len(eb["trips"]) == 1 and len(eb["flights"]) == 1})
    promo_trips = [e["name"] for e in store.entities("Trip") if not any(normalize_key_value("confirmation_code", (store.current(e["id"], "confirmation_code") or {}).get("value", "")) == b.code for b in bookings)]
    cancelled = bookings[-1]
    cancelled_trip = entities_by_booking(store, cancelled)["trips"]
    cancelled_ok = bool(cancelled_trip) and (store.current(cancelled_trip[0], "status") or {}).get("value", "").casefold() == "cancelled"
    denvers = [e for e in store.entities("Trip") if (store.current(e["id"], "destination") or {}).get("value", "").casefold() == "denver"]
    traceable = all(f["source"] and store.source(f["source"]) for e in store.entities() for f in store.history(e["id"]))
    tot = {k: sum(r[k] for r in rows) for k in ("found", "wrong", "missing")}
    summary = {
        "emails": len(rows), "model_calls": calls, "cost_usd": round(cost, 4),
        "attributes": tot, "recall": round(tot["found"] / max(1, sum(tot.values())), 3),
        "precision": round(tot["found"] / max(1, tot["found"] + tot["wrong"]), 3),
        "by_method": {m: {k: sum(r[k] for r in rows if r["method"] == m) for k in ("found", "wrong", "missing")} for m in ("markup", "model")},
        "bookings_one_trip_one_flight": f"{sum(r['ok'] for r in match_rows)}/{len(match_rows)}",
        "trips_without_a_booking": promo_trips, "cancelled_marked": cancelled_ok, "denver_trips_kept_apart": len(denvers) == 2,
        "traceable": traceable, "entities": {t: len(store.entities(t)) for t in ("Trip", "Flight", "Person", "Order", "Item")},
    }
    print(json.dumps(summary, indent=1))
    save("emails", {"time": now(), "summary": summary, "rows": rows, "matching": match_rows})
    return summary


# ---- 2. the gate on the phone -----------------------------------------------------------------------


async def cmd_gate(args: argparse.Namespace) -> dict:
    from devices.emulator import EmulatorDevice
    from policy.approvals import ScriptedApprover
    from routines.executor import ExecConfig, RoutineExecutor
    from routines.matcher import RoutineMatcher
    from routines.store import RoutineStore
    from testapps.skylark import SkyLark

    bookings = bookings_for_eval()
    mails = build_inbox(bookings, seed=args.seed)
    inbox = WORK / "inbox"
    write_inbox(mails, inbox)
    db = WORK / "gate.db"
    db.unlink(missing_ok=True)
    clock = Clock()
    store = MemoryStore(db, clock=clock)
    adapter = ModelAdapter()
    svc = MemoryService(store, adapter, data_scope="test_app")
    routines = RoutineStore(REPO / "data" / "routines")
    device = EmulatorDevice("envoy-test").connect()
    app = SkyLark(device.serial)
    ex = RoutineExecutor(device, adapter=adapter, approver=ScriptedApprover(True), config=ExecConfig(data_scope="test_app"))
    steps: list[dict] = []
    t0 = time.time()

    def log(name: str, ok: bool, **kw: Any) -> None:
        steps.append({"step": name, "ok": ok, **kw})
        print(f"{'OK ' if ok else 'BAD'} {name}: " + ", ".join(f"{k}={v}" for k, v in kw.items() if k not in ("notes",))[:300], flush=True)

    # 1. The inbox: confirmation emails become trips and flights.
    emails, _ = LocalMailbox(inbox).fetch(None)
    for m in emails:
        await svc.ingest_email(m, task_id="p3-gate-inbox")
    log("inbox ingested", True, emails=len(emails), trips=len(store.entities("Trip")), flights=len(store.entities("Flight")))

    # 2. The app: SkyLark seeded with the same bookings (the cancelled one too); each trip's details screen is read into memory,
    #    and the gate routine runs with its input filled from memory.
    fx = fixtures([b for b in bookings[2:]])
    for t in fx["trips"]:
        if t["code"] == bookings[-1].code:
            t["cancelled"] = True
    gate_routine = routines.get(next(n for n in routines.names() if "gate" in n and "flight_status" not in n))
    for b in bookings[:-1]:
        app.prepare(fixtures=fx, variant=0)
        request = f"What gate does my {b.city} flight leave from?" if b.city != "Denver" or b.code == bookings[1].code else f"What gate does my {b.date} Denver flight leave from?"
        filled = fill_inputs(store, gate_routine, request)
        out = await ex.run(gate_routine, filled.inputs, task_id=f"p3-gate-{b.code}", launch="never")
        rrep, srep = await remember_run(svc, gate_routine, filled.inputs, out.outputs, task_id=out.task_id, final_screen=await device.observe())
        log(f"app read for {b.city} {b.code}", out.status == "done", inputs=filled.inputs, input_sources=filled.sources, outputs=out.outputs,
            screen_resolved=[(r.type, r.how) for r in srep.resolved] if srep else None, routine_resolved=[(r.type, r.how) for r in rrep.resolved],
            dropped=srep.dropped if srep else None)

    # 3. One trip per booking, holding facts from both the email and the app.
    merged = []
    for b in bookings[:-1]:
        eb = entities_by_booking(store, b)
        kinds = set().union(*(source_kinds(store, e) for e in eb["trips"] + eb["flights"])) if eb["trips"] or eb["flights"] else set()
        ok = len(eb["trips"]) == 1 and len(eb["flights"]) == 1 and bool(kinds & {"email", "email_markup"}) and bool(kinds & {"app_screen", "routine_run"})
        merged.append(ok)
        log(f"one trip for {b.city} {b.code}", ok, trips=len(eb["trips"]), flights=len(eb["flights"]), sources=sorted(kinds))

    # 4. "What's my gate?" from memory alone: the device is not touched.
    r = Retriever(store)
    actions_before = device_actions(device)
    ans = await r.answer("What's my gate?", adapter, data_scope="test_app", task_id="p3-gate-answer")
    chicago = bookings[0]
    ok = ans.found and chicago.gate.casefold() in ans.answer.casefold() and device_actions(device) == actions_before
    log("What's my gate? (from memory)", ok, answer=ans.answer, stale=ans.stale, supported=ans.supported, notes=ans.notes.markdown[:1200])

    # 5. The gate changes in the app; a routine refresh replaces it and the answer shows both.
    app.set_gate(chicago.code, "C14")
    app.stop()
    app.launch()
    filled = fill_inputs(store, gate_routine, "What gate does my Chicago flight leave from?")
    out = await ex.run(gate_routine, filled.inputs, task_id="p3-gate-refresh", launch="never")
    await remember_run(svc, gate_routine, filled.inputs, out.outputs, task_id=out.task_id, final_screen=await device.observe())
    ans2 = await r.answer("What's my gate?", adapter, data_scope="test_app", task_id="p3-gate-answer2")
    flight = entities_by_booking(store, chicago)["flights"]
    hist = [h["value"] for h in store.history(flight[0], "gate")] if flight else []
    ok = "C14" in ans2.answer and hist[-2:] == [chicago.gate, "C14"] and "was " + chicago.gate in ans2.notes.markdown
    log("gate change replaces the old value", ok, answer=ans2.answer, history=hist)

    # 6. Freshness: 45 minutes later the gate is marked possibly out of date.
    clock.offset = 45 * 60
    ans3 = await r.answer("What's my gate?", adapter, data_scope="test_app", task_id="p3-gate-answer3")
    log("a 45-minute-old gate is marked stale", ans3.stale and ans3.notes.stale >= 1, answer=ans3.answer, stale_lines=ans3.notes.stale)
    clock.offset = 0

    # 7. "Check me in": the matcher fills the trip from memory's notes, the routine runs, its outputs become facts.
    matcher = RoutineMatcher(routines, adapter, data_scope="test_app")
    request = "Check me in for my flight"
    m = await matcher.match(request, notes_for(store, request), task_id="p3-checkin-match")
    filled = fill_inputs(store, m.routine, request, m.inputs) if m.routine else None
    if m.routine and filled and not filled.missing:
        app.prepare(fixtures=fx, variant=0)
        out = await ex.run(m.routine, filled.inputs, task_id="p3-checkin", launch="never")
        rep, _ = await remember_run(svc, m.routine, filled.inputs, out.outputs, task_id=out.task_id, final_screen=await device.observe())
        checked = app.trip(chicago.code)["checked_in"]
        seat = (store.current(entities_by_booking(store, chicago)["flights"][0], "seat") or {}).get("value")
        log("check me in, filled from memory", out.status == "done" and checked, routine=m.routine.routine, inputs=filled.inputs,
            sources=filled.sources, outputs=out.outputs, memory_seat=seat, model_calls=m.model_calls + out.model_calls)
    else:
        log("check me in, filled from memory", False, routine=m.routine.routine if m.routine else None, missing=filled.missing if filled else None)

    # 8. Traceability and stale facts served.
    facts = [f for e in store.entities() for f in store.history(e["id"])]
    traceable = sum(1 for f in facts if f["source"] and store.source(f["source"]))
    notes = Retriever(store).notes("my trips and flights")
    log("every fact has a source", traceable == len(facts), facts=len(facts), traceable=traceable)
    passed = all(s["ok"] for s in steps)
    summary = {"passed": passed, "steps_ok": f"{sum(s['ok'] for s in steps)}/{len(steps)}", "duration_s": round(time.time() - t0, 1),
               "entities": {t: len(store.entities(t)) for t in ("Trip", "Flight", "Person", "Order")}, "facts": len(facts),
               "events": len(store.events())}
    print(json.dumps(summary, indent=1))
    save("gate", {"time": now(), "summary": summary, "steps": steps})
    app.prepare()
    return summary


def device_actions(device: Any) -> int:
    """How many actions the device has run (taps, typing); the memory answer must not add any."""
    return getattr(device, "_actions", 0)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["emails", "gate"])
    ap.add_argument("--seed", type=int, default=3)
    args = ap.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    await {"emails": cmd_emails, "gate": cmd_gate}[args.cmd](args)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
