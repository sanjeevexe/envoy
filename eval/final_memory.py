"""A5 memory: extraction accuracy on labeled emails, app screens and screenshots; entity matching; stale facts served.

  extraction  Phase 3's large test inbox (28 emails, 18 bookings), a fresh inbox from new bookings, 12 SkyLark trip screens and
              Phase 5's 7 screenshots: every attribute scored against the bookings that seed both SkyLark and the inbox, so the
              ground truth is exact. Entity matching: each booking becomes exactly one trip and one flight; promotions make no
              trips; the cancellation applies to its trip; two trips to one city stay apart; screenshots merge into known entities.
  stale       Questions answered from memory with facts at known ages, inside and past their freshness windows, and values
              that were replaced: a stale fact must come with "may have changed", a fresh one need not, and a replaced value
              is never served as current. Scored in code on the answer and its stale flag.

Standard tier (extraction is the product reading your data; the data here is our own test app's).
"""

from __future__ import annotations

import re
import shutil
import time
from typing import Any

from final_common import REPO, Suite, load, pct

from integrations.mail import LocalMailbox  # noqa: E402
from memory.service import MemoryService  # noqa: E402
from memory.store import MemoryStore  # noqa: E402
from memory.types import normalize_key_value  # noqa: E402
from models.adapter import ModelAdapter  # noqa: E402

WORK = REPO / "data" / "final" / "memory"


async def inbox_suite(s: Suite, name: str, bookings: list[Any], seed: int) -> dict[str, Any]:
    from run_memory import entities_by_booking, score_extraction
    from skylark_mail import build_inbox, write_inbox
    mails = build_inbox(bookings, seed=seed)
    folder = WORK / name
    if folder.exists():
        shutil.rmtree(folder)
    write_inbox(mails, folder / "inbox")
    store = MemoryStore(folder / "memory.db")
    svc = MemoryService(store, ModelAdapter(), data_scope="test_app")
    by_name = {m.name: m for m in mails}
    rows = []
    emails, _ = LocalMailbox(folder / "inbox").fetch(None)
    for mail in emails:
        tm = by_name[mail.id]
        rep = await svc.ingest_email(mail, task_id=s.tid("mem", name, mail.id[:16]))
        sc = score_extraction(rep.extracted, tm.truth)
        got = {(e.type, o.attribute) for e in rep.extracted for o in e.observations}
        sc["missing_attrs"] = [f"{t['type']}.{a}" for t in tm.truth for a in t if a != "type" and (t["type"], a) not in got]
        rows.append({"email": mail.id, "kind": tm.kind, "method": rep.method, **sc, "dropped": rep.dropped[:5]})
        print(f"{name:12s} {mail.id:28s} {tm.kind:12s} {rep.method:7s} found={sc['found']:2d} wrong={sc['wrong']} missing={sc['missing']}", flush=True)
    matching = []
    for b in bookings:
        eb = entities_by_booking(store, b)
        matching.append({"booking": b.code, "city": b.city, "trips": len(eb["trips"]), "flights": len(eb["flights"]),
                         "ok": len(eb["trips"]) == 1 and len(eb["flights"]) == 1})
    codes = {b.code for b in bookings}
    promo_trips = [e["name"] for e in store.entities("Trip")
                   if normalize_key_value("confirmation_code", (store.current(e["id"], "confirmation_code") or {}).get("value", "")) not in codes]
    cancelled = entities_by_booking(store, bookings[-1])["trips"]
    cancelled_ok = bool(cancelled) and (store.current(cancelled[0], "status") or {}).get("value", "").casefold() == "cancelled"
    cities = [b.city for b in bookings]
    dup = next((c for c in set(cities) if cities.count(c) > 1), None)
    apart = None
    if dup:
        apart = len([e for e in store.entities("Trip") if (store.current(e["id"], "destination") or {}).get("value", "").casefold() == dup.casefold()]) == cities.count(dup)
    traceable = all(f["source"] and store.source(f["source"]) for e in store.entities() for f in store.history(e["id"]))
    tot = {k: sum(r[k] for r in rows) for k in ("found", "wrong", "missing")}
    return {"items": len(rows), "kind": "emails", "attributes": tot, "by_method": {m: {k: sum(r[k] for r in rows if r["method"] == m) for k in tot}
                                                                                  for m in ("markup", "model")},
            "matching": {"bookings": len(bookings), "one_trip_one_flight": sum(m["ok"] for m in matching), "trips_without_a_booking": promo_trips,
                         "cancellation_applied": cancelled_ok, "same_city_kept_apart": apart, "traceable": traceable},
            "rows": rows, "matching_rows": matching}


async def screens_suite(s: Suite) -> dict[str, Any]:
    """Each booking's trip page in SkyLark (reached by the compiled gate routine, no model), read by Muse Spark."""
    import final_core as fc
    from memory import extract as ex_mod
    from routines.store import RoutineStore
    from run_memory import score_extraction
    from skylark_routines import chicago_booking, compile_booking, generate
    env = fc.Env()
    gate = fc.routine_of(RoutineStore(fc.LIB_COMPILED), fc.BY_ID["gate"])
    bookings = [chicago_booking(), compile_booking()] + generate(5150, 10)
    w = fc.World(seed=5150, upcoming=bookings[2:])
    rows = []
    adapter = ModelAdapter()
    for b in bookings:
        await env.reset(w)
        await env.executor().run(gate, fc.inputs_for(gate, fc.BY_ID["gate"].source(), b), task_id=s.tid("mem", "nav", b.code), launch="never")
        screen = await env.device.observe()
        extraction = await ex_mod.from_screen(screen, adapter, data_scope="test_app", task_id=s.tid("mem", "screen", b.code))
        truth = [{"type": "Trip", "confirmation_code": b.code, "destination": b.city},
                 {"type": "Flight", "number": b.number, "date": b.date, "gate": b.gate, "seat": b.seat, "depart_time": b.depart}]
        sc = score_extraction(extraction.entities, truth)
        got = {(e.type, o.attribute) for e in extraction.entities for o in e.observations}
        sc["missing_attrs"] = [f"{t['type']}.{a}" for t in truth for a in t if a != "type" and (t["type"], a) not in got]
        ev = sum(1 for e in extraction.entities for o in e.observations if o.evidence)
        n = sum(len(e.observations) for e in extraction.entities)
        rows.append({"booking": b.code, "city": b.city, **sc, "evidence": f"{ev}/{n}", "dropped": extraction.dropped[:5]})
        print(f"screen {b.code} {b.city:12s} found={sc['found']} wrong={sc['wrong']} missing={sc['missing']}", flush=True)
    await env.reset(fc.compile_world())
    tot = {k: sum(r[k] for r in rows) for k in ("found", "wrong", "missing")}
    return {"items": len(rows), "kind": "app screens", "attributes": tot, "rows": rows}


async def photos_suite(s: Suite) -> dict[str, Any]:
    """Phase 5's 7 screenshots (home card, trip pages, boarding passes, a status lookup), through the photo pipeline into a
    copy of the demo memory: values right, wrong, missed, and whether each merged into the trip and flight memory knew."""
    import sys
    sys.path.insert(0, str(REPO / "scripts"))
    import run_photos as rp
    from demo_setup import demo_fixtures
    from memory.photos import ingest_photo
    from testapps.skylark import SkyLark
    rp.WORK.mkdir(parents=True, exist_ok=True)
    app = SkyLark("emulator-5554")
    fx = demo_fixtures(signed_in=True)
    for t in fx["trips"]:
        if t["code"] in rp.CHECKED_IN:
            t["checked_in"] = True
    app.prepare(fixtures=fx, variant=0)
    shots = await rp.capture(app, fx)
    db = rp.WORK / "memory.db"
    shutil.copy(REPO / "data" / "demo" / "memory.db", db)
    store = MemoryStore(db)
    svc = MemoryService(store, ModelAdapter(), data_scope="real")
    rows = []
    for code, kind, path in shots:
        t = next(x for x in fx["trips"] if x["code"] == code)
        exp = rp.truth(t, kind, fx["profile"])
        flights, trips = len(store.entities("Flight")), len(store.entities("Trip"))
        up = rp.WORK / f"upload_{path.name}"
        shutil.copy(path, up)
        res = await ingest_photo(svc, up, photo_id=f"final-{path.stem}", origin="eval", task_id=s.tid("mem", "photo", path.stem))
        got: dict[str, list[str]] = {}
        for e in res.report.extracted if res.report else []:
            for o in e.observations:
                got.setdefault(o.attribute, []).append(o.value)
        right = [a for a, v in exp.items() if any(rp.same(a, v, g) for g in got.get(a, []))]
        wrong = [a for a in exp if a in got and a not in right]
        if kind == "status":
            # Another flight's status, looked up: not evidence of a booking of yours. Right is storing nothing about it.
            rows.append({"screen": path.stem, "kind": kind, "negative": True, "stored": sum(len(e.observations) for e in (res.report.extracted if res.report else [])),
                         "new_flights": len(store.entities("Flight")) - flights, "new_trips": len(store.entities("Trip")) - trips, "deleted": res.deleted})
            print(f"photo {path.stem:20s} (another flight) new F/T={rows[-1]['new_flights']}/{rows[-1]['new_trips']}", flush=True)
            continue
        rows.append({"screen": path.stem, "kind": kind, "found": len(right), "wrong": len(wrong), "missing": len([a for a in exp if a not in got]),
                     "wrong_detail": [f"{a}: {got[a]} (expected {exp[a]})" for a in wrong], "new_flights": len(store.entities("Flight")) - flights,
                     "new_trips": len(store.entities("Trip")) - trips, "deleted": res.deleted})
        print(f"photo {path.stem:20s} {len(right)}/{len(exp)} wrong={wrong} new F/T={rows[-1]['new_flights']}/{rows[-1]['new_trips']}", flush=True)
    shutil.rmtree(rp.WORK, ignore_errors=True)
    app.prepare(fixtures=demo_fixtures(signed_in=True), variant=0)
    scored = [r for r in rows if not r.get("negative")]
    neg = [r for r in rows if r.get("negative")]
    tot = {k: sum(r[k] for r in scored) for k in ("found", "wrong", "missing")}
    return {"items": len(scored), "kind": "screenshots", "attributes": tot,
            "merged_into_known": sum(r["new_flights"] == 0 and r["new_trips"] == 0 for r in scored),
            "other_flight_created_nothing": all(r["new_flights"] == 0 and r["new_trips"] == 0 for r in neg) if neg else None,
            "all_deleted": all(r["deleted"] for r in rows), "rows": rows}


# ---- stale facts -------------------------------------------------------------------------------------------------------

class Clock:
    def __init__(self) -> None:
        self.t = time.time()

    def __call__(self) -> float:
        return self.t


WARN = re.compile(r"may (have )?changed|might (have )?changed|may be out of date|could have changed|may no longer|re-?check|not be current|"
                  r"might be outdated|may be outdated|could be out of date", re.I)


def stale_world(clock: Clock) -> tuple[MemoryStore, dict[str, str]]:
    """A memory with known ages: a flight whose gate changed (B12 → C14), a points balance, a delivery, a trip's seat."""
    db = WORK / "stale.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.unlink(missing_ok=True)
    st = MemoryStore(db, clock=clock)
    t0 = clock()
    app = st.add_source("app_screen", {"app": "com.skylark.air", "screen": "TripDetails"}, captured_at=t0)
    trip = st.create_entity("Trip", "Chicago")
    flight = st.create_entity("Flight", "SL 482")
    st.observe(trip, "destination", "Chicago", source=app, observed_at=t0)
    st.observe(trip, "confirmation_code", "KX7Q2M", source=app, observed_at=t0)
    st.observe(trip, "start_date", "Fri, Oct 30, 2026", source=app, observed_at=t0)
    for a, v in (("number", "SL 482"), ("date", "Fri, Oct 30, 2026"), ("from", "ATL"), ("to", "ORD"), ("depart_time", "6:10 AM"), ("seat", "14C"),
                 ("status", "On time"), ("boarding_time", "5:30 AM")):
        st.observe(flight, a, v, source=app, observed_at=t0)
    st.observe(flight, "gate", "B12", source=app, observed_at=t0 - 3600)
    st.observe(flight, "gate", "C14", source=app, observed_at=t0)
    st.link(trip, "has_flight", flight, source=app)
    loyalty = st.create_entity("Loyalty program", "SkyLark Rewards")
    st.observe(loyalty, "program", "SkyLark Rewards", source=app, observed_at=t0)
    st.observe(loyalty, "miles", "38,240", source=app, observed_at=t0)
    dd = st.add_source("app_screen", {"app": "com.dd.doordash", "screen": "OrderStatus"}, captured_at=t0)
    order = st.create_entity("Order", "DoorDash order")
    st.observe(order, "merchant", "DoorDash", source=dd, observed_at=t0)
    st.observe(order, "order_number", "4471", source=dd, observed_at=t0)
    st.observe(order, "delivery_eta", "7:45 PM", source=dd, observed_at=t0)
    st.observe(order, "status", "On the way", source=dd, observed_at=t0)
    st.commit()
    return st, {"trip": trip, "flight": flight, "loyalty": loyalty, "order": order}


# (question, expected current value, attribute's freshness window in seconds or None, a replaced value that must not be served)
QUESTIONS = [
    ("What's my gate for my Chicago flight?", "C14", 30 * 60, "B12"),
    ("What seat do I have on my Chicago flight?", "14C", None, None),
    ("Is my Chicago flight on time?", "On time", 30 * 60, None),
    ("When does boarding start for my Chicago flight?", "5:30", 6 * 3600, None),
    ("How many SkyLark miles do I have?", "38,240", 7 * 86400, None),
    ("When will my DoorDash order arrive?", "7:45", 10 * 60, None),
]
AGES = [("just now", 60), ("45 minutes later", 45 * 60), ("8 hours later", 8 * 3600), ("10 days later", 10 * 86400)]


async def stale_suite(s: Suite) -> dict[str, Any]:
    from memory.retrieval import Retriever
    clock = Clock()
    store, _ = stale_world(clock)
    base = clock.t
    adapter = ModelAdapter()
    rows = []
    for age_name, age in AGES:
        clock.t = base + age
        for q, value, ttl, replaced in QUESTIONS:
            stale = ttl is not None and age > ttl
            a = await Retriever(store).answer(q, adapter, data_scope="test_app", task_id=s.tid("stale", age_name.split()[0], q[:20].replace(" ", "_")))
            text = a.answer
            served = value.casefold() in text.casefold().replace(" ", "") or value.casefold() in text.casefold()
            warned = bool(a.stale) or bool(WARN.search(text))
            old_as_current = bool(replaced) and re.search(rf"\b{replaced}\b", text) is not None and not re.search(
                rf"(was|previously|earlier|changed from|before)\W+(gate\s+)?{replaced}\b", text, re.I)
            rows.append({"age": age_name, "question": q, "stale": stale, "served_value": served, "warned": warned,
                         "stale_without_warning": stale and not warned, "warned_when_fresh": warned and not stale,
                         "replaced_served_as_current": old_as_current, "answer": text, "notes_stale_lines": a.notes.stale})
            print(f"{'ok ' if served and warned == stale and not old_as_current else 'NOTE'} {age_name:17s} stale={stale!s:5s} warned={warned!s:5s} "
                  f"{q[:40]:40s} {text[:80]!r}", flush=True)
    return {"rows": rows, "questions": len(rows)}


def memory_md(out: dict[str, Any]) -> str:
    md = []
    parts = [k for k in ("emails_large", "emails_new", "screens", "photos") if k in out]
    if parts:
        tf = sum(out[k]["attributes"]["found"] for k in parts)
        tw = sum(out[k]["attributes"]["wrong"] for k in parts)
        tm = sum(out[k]["attributes"]["missing"] for k in parts)
        items = sum(out[k]["items"] for k in parts)
        md += ["## Extraction", "", f"**{items} labeled items: {pct(tf, tf + tw + tm)} of attributes right, {tw} wrong values.**", "",
               "| Set | Items | Right | Wrong | Missing |", "| --- | --- | --- | --- | --- |"]
        names = {"emails_large": "Phase 3's large test inbox", "emails_new": "A fresh inbox (new bookings)", "screens": "SkyLark trip screens",
                 "photos": "Screenshots (Phase 5's set)"}
        for k in parts:
            a = out[k]["attributes"]
            md.append(f"| {names[k]} | {out[k]['items']} {out[k]['kind']} | {pct(a['found'], sum(a.values()))} | {a['wrong']} | {a['missing']} |")
        md += ["", "## Entity matching", "", "| Set | Bookings → one trip and one flight | Trips from promotions | Cancellation applied | Same city kept apart | Traceable |",
               "| --- | --- | --- | --- | --- | --- |"]
        for k in ("emails_large", "emails_new"):
            if k in out:
                m = out[k]["matching"]
                md.append(f"| {names[k]} | {m['one_trip_one_flight']}/{m['bookings']} | {len(m['trips_without_a_booking'])} | {m['cancellation_applied']} | "
                          f"{'n/a' if m['same_city_kept_apart'] is None else m['same_city_kept_apart']} | {m['traceable']} |")
        if "photos" in out:
            md.append(f"\nScreenshots merged into the trip and flight memory already knew: {out['photos']['merged_into_known']} of {out['photos']['items']}; "
                      f"a status lookup of another flight created no trip or flight: {out['photos'].get('other_flight_created_nothing')}; "
                      f"every image deleted: {out['photos']['all_deleted']}.")
        misses: dict[str, int] = {}
        for k in parts:
            for r in out[k].get("rows", []):
                for a in r.get("missing_attrs", []):
                    misses[a] = misses.get(a, 0) + 1
        if misses:
            md.append("Missing attributes: " + ", ".join(f"{a} ×{n}" for a, n in sorted(misses.items(), key=lambda kv: -kv[1])) + ".")
    if "stale" in out:
        rs = out["stale"]["rows"]
        st = [r for r in rs if r["stale"]]
        fr = [r for r in rs if not r["stale"]]
        md += ["", "## Stale facts", "",
               f"{len(rs)} answers from memory at four ages. **Stale facts served without a warning: {sum(r['stale_without_warning'] for r in st)} of {len(st)}.** "
               f"Replaced values served as current: {sum(r['replaced_served_as_current'] for r in rs)}. The right value given: "
               f"{sum(r['served_value'] for r in rs)} of {len(rs)}. Fresh facts given a warning anyway: {sum(r['warned_when_fresh'] for r in fr)} of {len(fr)}.", "",
               "| Age | Question | Stale | Warned | Answer |", "| --- | --- | --- | --- | --- |"]
        for r in rs:
            md.append(f"| {r['age']} | {r['question']} | {'yes' if r['stale'] else ''} | {'yes' if r['warned'] else ''} | {r['answer'][:110].replace('|', '/')} |")
    return "\n".join(md) + "\n"


async def cmd_memory(args: Any) -> None:
    from run_memory import bookings_for_eval
    from skylark_routines import generate
    s = Suite("memory", label="Memory: extraction, entity matching and stale facts")
    out: dict[str, Any] = {k: v for k, v in (load("memory") or {}).items() if k != "meta"}  # parts not run keep their earlier result
    parts = set(args.parts.split(","))
    if "extraction" in parts:
        parts |= {"emails", "screens", "photos"}
    if "emails" in parts:
        out["emails_large"] = await inbox_suite(s, "emails_large", bookings_for_eval(15), seed=3)
        out["emails_new"] = await inbox_suite(s, "emails_new", generate(4242, 8), seed=9)
    if "screens" in parts:
        out["screens"] = await screens_suite(s)
    if "photos" in parts:
        out["photos"] = await photos_suite(s)
    if "stale" in args.parts:
        out["stale"] = await stale_suite(s)
    ran = (["emails_large", "emails_new"] if "emails" in parts else []) + [k for k in ("screens", "photos", "stale") if k in parts]
    for k in ran:
        out[k]["run"] = s.stamp()
    s.save(out, memory_md(out))
