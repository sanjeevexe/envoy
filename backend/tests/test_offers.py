"""Offline tests for offers ("Should I check you in for SL 482?", api/offers.py) and ask mode on triggers: the store and
its no-nagging keys, who can say yes (only your session, never a token or MCP), what an accepted task may do under the
real approval rules (values never grant permission), the trigger keeping its credit, the proactivity setting's pushes,
the briefing, the presets' templates against demo values, and triggers created switched off."""

from __future__ import annotations

import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.auth import Caller
from api.briefing import build_briefing
from api.events import EventBus
from api.offers import Offers, OfferError, pushes
from api.push import Pusher, VapidKeys
from api.scheduler import Scheduler, _fill
from api.store import TaskStore
from memory.store import MemoryStore
from policy.approval_rules import ApprovalRules, decide
from policy.approvals import ApprovalRequest
from test_phase5 import me
from test_phase5 import env as phase5_env  # noqa: F401 - the fixture, built the same way

REPO = Path(__file__).resolve().parents[2]
PRESETS = json.loads((REPO / "web" / "lib" / "trigger-presets.json").read_text())
OWNER, IPHONE = Caller("owner", "session", name="this Mac"), Caller("device", "session", "dev-1", "Maya's iPhone")
CONFIRM = "Step 3 of 3\nConfirm check-in\nPassenger · Maya Patel\nFlight · SL 482 · Fri, Oct 30, 2026\nSeat · 14C"
CHECK_IN = {"type": "task", "goal": "Check me in for my flight SL 482 to Chicago", "request": "Check me in for my flight to",
            "routine": "skylark_check_in_flight", "inputs": {"trip_city": "Chicago"}}


def starter(store: TaskStore, started: list):
    """runner.start without the run: the task as the runner records it (its request is what approvals read)."""
    def start(goal, source, **kw):
        task = store.create(goal, source, routine=kw.get("routine"), inputs=kw.get("inputs") or {}, app=kw.get("app"),
                            request=kw.get("request") or goal)
        started.append((goal, source, kw))
        return task
    return start


def unit(clock=None):
    """Offers on their own stores, with a recording runner and a scheduler."""
    store, mem, bus = TaskStore(":memory:"), MemoryStore(":memory:"), EventBus()
    started: list = []
    runner = SimpleNamespace(start=starter(store, started))
    now = clock or [time.time()]
    sched = Scheduler(store, mem, runner.start, bus, clock=lambda: now[0])
    offers = Offers(store, bus, runner, sched, clock=lambda: now[0])
    sched.offers = offers
    return SimpleNamespace(store=store, memory=mem, bus=bus, started=started, runner=runner, sched=sched, offers=offers, now=now)


def demo_flight(mem: MemoryStore, number="SL 482", date="Fri, Oct 30, 2026", depart="6:10 AM", city="Chicago"):
    """A flight and its trip as the demo memory has them (data/demo/memory.db)."""
    src = mem.add_source("email", {"subject": f"Booking confirmation: Atlanta to {city}", "sender": "SkyLark Air <reservations@skylark.example>"})
    trip, flight = mem.create_entity("Trip"), mem.create_entity("Flight")
    mem.observe(trip, "destination", city, source=src)
    mem.observe(flight, "number", number, source=src)
    mem.observe(flight, "date", date, source=src)
    mem.observe(flight, "depart_time", depart, source=src)
    mem.link(trip, "includes", flight, src)
    return flight


# ---- the store: making one, no nagging ----------------------------------------------------------------


def test_a_key_never_nags_twice_and_offers_share_nothing_between_builds():
    u = unit()
    o = u.offers.make(kind="trigger", title="Check in for SL 482?", body="b", action=CHECK_IN, source="trigger:x", key="k1",
                      origin={"trigger_id": "trig-1"})
    assert o["status"] == "pending" and o["origin"] == {"trigger_id": "trig-1"} and o["action"]["request"] == "Check me in for my flight to"
    assert u.offers.make(kind="trigger", title="again", body="", action=CHECK_IN, source="trigger:x", key="k1") is None  # pending
    u.offers.decide(o["id"], "decline", OWNER)
    assert u.offers.make(kind="trigger", title="again", body="", action=CHECK_IN, source="trigger:x", key="k1") is None  # declined
    assert u.offers.make(kind="trigger", title="other", body="", action=CHECK_IN, source="trigger:x", key="k2") is not None
    with pytest.raises(ValueError):
        u.offers.make(kind="spam", title="x", body="", action=CHECK_IN, source="x", key="k3")
    with pytest.raises(ValueError):  # no fixed words: values would become the request
        u.offers.make(kind="trigger", title="x", body="", action={**CHECK_IN, "request": " {caption} "}, source="x", key="k4")
    with pytest.raises(ValueError):
        u.offers.make(kind="trigger", title="x", body="", action={"type": "run_shell"}, source="x", key="k5")
    other = unit()  # a second build: its own table, its own handlers
    assert other.offers.list("all") == [] and other.offers.handlers is not u.offers.handlers
    u.offers.register("handoff", lambda offer, source: {})
    assert "handoff" not in other.offers.handlers


def test_preflight_lines_come_from_the_check_and_a_broken_check_is_skipped(monkeypatch):
    u = unit()
    seen = {}

    def check(runner, goal, **kw):
        seen.update(goal=goal, **kw)
        return [{"kind": "approval", "text": "Confirming check-in will go ahead: you asked for it", "level": "info"}]
    monkeypatch.setattr("api.offers.preflight_check", check)
    o = u.offers.make(kind="trigger", title="t", body="", action=CHECK_IN, source="trigger:x", key="p1")
    assert o["preflight"][0]["kind"] == "approval" and seen["source"] == "web" and seen["request"] == "Check me in for my flight to"
    assert seen["goal"] == CHECK_IN["goal"] and seen["routine"] == "skylark_check_in_flight"
    monkeypatch.setattr("api.offers.preflight_check", lambda *a, **k: 1 / 0)
    assert u.offers.make(kind="trigger", title="t", body="", action=CHECK_IN, source="trigger:x", key="p2")["preflight"] == []
    given = [{"kind": "device", "text": "On your Pixel 5", "level": "info"}]
    assert u.offers.make(kind="handoff", title="t", body="", action=CHECK_IN, source="x", key="p3", preflight=given)["preflight"] == given


# ---- deciding: who, twice, when it counts -----------------------------------------------------------------


def test_only_your_session_decides_and_the_source_is_where_you_tapped():
    u = unit()
    o = u.offers.make(kind="trigger", title="t", body="", action=CHECK_IN, source="trigger:x", key="d1")
    for nobody in (None, Caller("token", "photos", "dev-2", "Shortcut"), Caller("token", "code_test"), SimpleNamespace(kind="mcp", scope="mcp")):
        with pytest.raises(OfferError) as e:
            u.offers.decide(o["id"], "accept", nobody)
        assert e.value.status == 403
    assert u.started == [] and u.offers.get(o["id"])["status"] == "pending"
    done = u.offers.decide(o["id"], "accept", IPHONE)
    goal, source, kw = u.started[0]
    assert source == "iphone" and goal == CHECK_IN["goal"] and kw["request"] == "Check me in for my flight to"  # the card's goal verbatim
    assert done["status"] == "accepted" and done["decided_by"] == "you on Maya's iPhone" and u.store.get(done["task_id"])["source"] == "iphone"
    assert u.offers.decide(o["id"], "accept", OWNER)["task_id"] == done["task_id"] and len(u.started) == 1  # twice: the same task
    with pytest.raises(OfferError) as e:
        u.offers.decide(o["id"], "decline", OWNER)
    assert e.value.status == 409
    o2 = u.offers.make(kind="trigger", title="t", body="", action=CHECK_IN, source="trigger:x", key="d2")
    u.offers.decide(o2["id"], "accept", OWNER)
    assert u.started[-1][1] == "web"


def test_declined_and_expired_are_final_and_a_failed_start_stays_pending():
    u = unit()
    o = u.offers.make(kind="trigger", title="t", body="", action=CHECK_IN, source="x", key="e1", expires_at=u.now[0] + 60)
    events = []
    u.bus.listeners.append(events.append)
    u.now[0] += 61
    with pytest.raises(OfferError) as e:
        u.offers.decide(o["id"], "accept", OWNER)
    assert e.value.status == 409 and u.offers.get(o["id"])["status"] == "expired" and u.started == []
    assert any(ev["type"] == "offer" and ev["change"] == "expired" for ev in events)
    assert u.offers.make(kind="trigger", title="t", body="", action=CHECK_IN, source="x", key="late", expires_at=u.now[0] - 1) is None
    d = u.offers.make(kind="trigger", title="t", body="", action=CHECK_IN, source="x", key="e2")
    u.offers.decide(d["id"], "decline", OWNER)
    with pytest.raises(OfferError) as e:
        u.offers.decide(d["id"], "accept", OWNER)
    assert e.value.status == 409
    f = u.offers.make(kind="trigger", title="t", body="", action=CHECK_IN, source="x", key="e3")
    u.runner.start = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("the task runner has no event loop yet"))
    with pytest.raises(OfferError) as e:
        u.offers.decide(f["id"], "accept", OWNER)
    got = u.offers.get(f["id"])
    assert e.value.status == 409 and got["status"] == "pending" and "no event loop" in got["note"]  # pending, and says why


def test_enable_and_create_trigger_actions():
    u = unit()
    off = u.sched.add("time", "Sunday coupons", {"daily_at": "9:00"}, {"goal": "Clip my coupons", "ask": True}, enabled=False)
    o = u.offers.make(kind="trigger_request", title="Muse wants to set this up. Turn it on?", body="", source="mcp", key=f"enable:{off['id']}",
                      action={"type": "enable_trigger", "trigger_id": off["id"]})
    assert u.offers.decide(o["id"], "accept", OWNER)["result"] == {"trigger_id": off["id"]} and u.store.trigger(off["id"])["enabled"]
    c = u.offers.make(kind="repeat", title="Make this a habit?", body="", source="repeats", key="r1",
                      action={"type": "create_trigger", "kind": "time", "name": "Gate on Mondays", "spec": {"daily_at": "8:00"},
                              "action": {"routine": "skylark_get_flight_gate", "ask": True}})
    made = u.store.trigger(u.offers.decide(c["id"], "accept", OWNER)["result"]["trigger_id"])
    assert made["enabled"] and made["action"]["ask"] is True  # the yes is the switch: it's created on
    bad = u.offers.make(kind="repeat", title="x", body="", source="repeats", key="r2",
                        action={"type": "create_trigger", "kind": "nope", "name": "x", "spec": {}, "action": {"goal": "x"}})
    with pytest.raises(OfferError):
        u.offers.decide(bad["id"], "accept", OWNER)
    assert u.offers.get(bad["id"])["status"] == "pending"


# ---- values never grant permission (the real approval rules) -------------------------------------------------


def asks(store: TaskStore, task: dict, target: str, screen: str = CONFIRM) -> bool:
    """What WebApprover asks decide() for this task's step (api/approvals.py): True when it would ask you."""
    t = store.get(task["id"])
    return decide(ApprovalRules(), goal=t["request"] or t["goal"], source=t["source"], app="com.skylark.air", routine=t["routine"],
                  origin="routine_step", target=target, screen_text=screen, inputs=t["inputs"] or {}) is None


def test_an_accepted_check_in_offer_covers_confirm_check_in_and_nothing_else():
    u = unit()
    o = u.offers.make(kind="trigger", title="Check in for SL 482?", body="", action=CHECK_IN, source="trigger:x", key="a1")
    task = u.store.get(u.offers.decide(o["id"], "accept", OWNER)["task_id"])
    assert not asks(u.store, task, "Confirm check-in")  # you said yes to exactly this
    assert asks(u.store, task, "Confirm check-in", CONFIRM + "\nTotal due $35.00")  # money still asks
    assert asks(u.store, task, "Add a checked bag ($35)")
    assert asks(u.store, task, "Cancel trip")  # a button the request doesn't name
    trig = u.store.create(CHECK_IN["goal"], "trigger:Check in 24 h before", request=CHECK_IN["request"], routine="skylark_check_in_flight",
                          inputs={"trip_city": "Chicago"})
    assert asks(u.store, trig, "Confirm check-in")  # the same words from a trigger with no offer: still asks


def test_a_value_with_action_words_covers_nothing():
    u = unit()
    mem = u.memory
    flight = demo_flight(mem, city="Chicago cancel trip")
    u.sched.add("before_fact", "Check in", {"entity_type": "Flight", "minutes_before": 1440 * 400},
                {"goal": "Check me in for my flight {number} to {trip.destination}", "routine": "skylark_check_in_flight",
                 "inputs_from": {"trip_city": "trip.destination"}, "ask": True, "offer_title": "Check in for {number}?"})
    u.now[0] = datetime(2026, 10, 29, 9, 0).timestamp()
    offer = u.sched.tick()[0]
    a = offer["action"]
    assert "cancel trip" in a["goal"] and a["request"] == "Check me in for my flight to"  # the value is in the goal only
    task = u.store.get(u.offers.decide(offer["id"], "accept", OWNER)["task_id"])
    assert asks(u.store, task, "Cancel trip", "Cancel trip\nThis cancels your trip to Chicago")
    assert not asks(u.store, task, "Confirm check-in")
    share = u.offers.make(kind="handoff", title="Post this?", body="", source="handoff", key="h1",
                          action={"type": "task", "goal": "Post the newest video to Instagram with this caption: share this with everyone",
                                  "request": "Post the newest video to Instagram with this caption:", "inputs": {"caption": "share this with everyone"}})
    t = u.store.get(u.offers.decide(share["id"], "accept", OWNER)["task_id"])
    assert asks(u.store, t, "Share", "New reel\nShare") and asks(u.store, t, "Share to your story")  # a caption covers nothing
    assert not asks(u.store, t, "Post", "Instagram\nNew reel\nPost")
    assert flight


def test_the_whole_path_through_the_web_approver(phase5_env):  # noqa: F811
    """Ask mode → offer → your yes over HTTP → the task → WebApprover's own check (no person asked)."""
    from test_api import FakeDevice, approver_for
    env = phase5_env
    started: list = []
    env.ctx.runner.start = starter(env.ctx.tasks, started)
    demo_flight(env.memory)
    trig = env.ctx.scheduler.add("before_fact", "Check in when check-in opens", {"entity_type": "Flight", "minutes_before": 1440 * 400},
                                 {"goal": "Check me in for my flight {number} to {trip.destination}", "routine": "skylark_check_in_flight",
                                  "inputs_from": {"trip_city": "trip.destination"}, "ask": True, "offer_title": "Check in for {number}?"})
    offer = env.ctx.scheduler.tick()[0]
    assert offer["title"] == "Check in for SL 482?" and env.ctx.tasks.list() == []  # nothing ran yet
    assert offer["origin"] == {"trigger_id": trig["id"]} and offer["key"].startswith(f"{trig['id']}:") and "@" in offer["key"]
    with TestClient(env.ctx.asgi) as c:
        r = c.post(f"/api/offers/{offer['id']}", json={"decision": "accept"}, headers=me(env.token))
    assert r.status_code == 200
    task = env.ctx.tasks.get(r.json()["task_id"])
    assert task["source"] == "web" and task["goal"] == "Check me in for my flight SL 482 to Chicago" and task["inputs"] == {"trip_city": "Chicago"}
    approver, _, _ = approver_for(env.ctx.tasks, FakeDevice(), timeout_s=0.5)
    approver.task_id = task["id"]
    d = approver.request(ApprovalRequest(task["id"], task["goal"], "com.skylark.air", 'Tap "Confirm check-in"', ["rule: confirm"], CONFIRM,
                                         origin="routine_step", target="Confirm check-in"))
    assert d.approved and d.by == "your request"  # no person asked: you said yes to exactly this


# ---- ask mode on triggers ------------------------------------------------------------------------------


def test_ask_mode_keys_are_the_occasion_and_a_check_in_expires_at_departure():
    u = unit([datetime(2026, 10, 29, 9, 0).timestamp()])
    demo_flight(u.memory)
    demo_flight(u.memory, "SL 1190", "Sat, Oct 31, 2026", "2:45 PM", "Denver")
    trig = u.sched.add("before_fact", "Check in", {"entity_type": "Flight", "minutes_before": 1440},
                       {"goal": "Check me in for my flight {number} to {trip.destination}", "ask": True, "offer_title": "Check in for {number}?"})
    first = u.sched.tick()
    assert [o["title"] for o in first] == ["Check in for SL 482?"] and u.started == []
    assert first[0]["expires_at"] == datetime(2026, 10, 30, 6, 10).timestamp()  # departure
    u.offers.decide(first[0]["id"], "decline", OWNER)
    u.now[0] = datetime(2026, 10, 30, 15, 0).timestamp()  # the next flight's day opens: its own occasion
    second = u.sched.tick()
    assert [o["title"] for o in second] == ["Check in for SL 1190?"]
    assert u.sched.tick() == []  # each occasion once
    daily = u.sched.add("time", "Morning gate", {"daily_at": "16:00"}, {"goal": "What's my gate?", "ask": True})
    u.now[0] = datetime(2026, 10, 30, 16, 1).timestamp()
    d1 = [o for o in u.sched.tick() if o["origin"]["trigger_id"] == daily["id"]]
    assert d1 and d1[0]["key"] == f"{daily['id']}:2026-10-30" and d1[0]["title"] == "Should I look this up: what's your gate?"
    u.offers.decide(d1[0]["id"], "decline", OWNER)
    u.now[0] = datetime(2026, 10, 31, 16, 1).timestamp()
    d2 = [o for o in u.sched.tick() if o["origin"]["trigger_id"] == daily["id"]]
    assert d2 and d2[0]["key"] == f"{daily['id']}:2026-10-31"  # one "Not now" never blocks the next day
    assert trig


def test_the_default_title_says_it_back_to_you():
    u = unit([datetime(2026, 10, 29, 9, 0).timestamp()])
    demo_flight(u.memory)
    u.sched.add("before_fact", "Check in", {"entity_type": "Flight", "minutes_before": 1440},
                {"goal": "Check me in for my flight to {trip.destination}", "ask": True})
    o = u.sched.tick()[0]
    assert o["title"] == "Should I check you in for your flight to Chicago?" and o["action"]["goal"] == "Check me in for my flight to Chicago"


def test_ask_mode_is_validated(phase5_env):  # noqa: F811
    env = phase5_env
    with pytest.raises(ValueError):
        env.ctx.scheduler.add("time", "x", {"daily_at": "9:00"}, {"goal": "x", "ask": "yes"})
    with pytest.raises(ValueError):
        env.ctx.scheduler.add("time", "x", {"daily_at": "9:00"}, {"goal": "x", "ask": True, "offer_title": "two\nlines"})
    with TestClient(env.ctx.asgi) as c:
        h = me(env.token)
        assert c.post("/api/triggers", json={"kind": "time", "name": "x", "spec": {"daily_at": "9:00"}, "action": {"goal": "x", "ask": 1}}, headers=h).status_code == 400
        t = c.post("/api/triggers", json={"kind": "time", "name": "x", "spec": {"daily_at": "9:00"}, "action": {"goal": "Order my coffee"}}, headers=h).json()
        assert c.post(f"/api/triggers/{t['id']}", json={"ask": "maybe"}, headers=h).status_code == 400
        r = c.post(f"/api/triggers/{t['id']}", json={"ask": True, "offer_title": "Order your coffee?"}, headers=h).json()
        assert r["action"] == {"goal": "Order my coffee", "ask": True, "offer_title": "Order your coffee?"} and r["enabled"]
        r = c.post(f"/api/triggers/{t['id']}", json={"ask": False, "offer_title": ""}, headers=h).json()
        assert r["action"] == {"goal": "Order my coffee", "ask": False}


def test_ask_mode_without_offers_never_starts_the_task_silently():
    store, mem, bus = TaskStore(":memory:"), MemoryStore(":memory:"), EventBus()
    started: list = []
    sched = Scheduler(store, mem, lambda *a, **k: started.append(a) or {"id": "t"}, bus)
    sched.add("time", "x", {"at": time.time() - 5}, {"goal": "Pay my bill", "ask": True})
    assert sched.tick() == [] and started == [] and any(e["type"] == "trigger_error" for e in bus.recent)


def test_a_trigger_created_switched_off_never_fires():
    u = unit()
    t = u.sched.add("time", "Once", {"at": u.now[0] - 5}, {"goal": "Check my gate"}, enabled=False)
    assert not t["enabled"] and u.sched.tick() == [] and u.started == []
    u.store.update_trigger(t["id"], enabled=1)
    assert len(u.sched.tick()) == 1 and u.started[0][0] == "Check my gate"


# ---- the trigger keeps its credit -------------------------------------------------------------------------


def test_a_watchers_offer_keeps_its_credit_for_change_alerts(phase5_env):  # noqa: F811
    env = phase5_env
    shutil.copytree(REPO / "data" / "routines" / "skylark_get_flight_gate", env.tmp / "routines" / "skylark_get_flight_gate")
    started: list = []
    env.ctx.runner.start = starter(env.ctx.tasks, started)
    w = env.ctx.scheduler.add("watch", "Watch my gate", {"every_minutes": 10, "alert": True}, {"routine": "skylark_get_flight_gate", "ask": True})
    offer = env.ctx.scheduler.tick()[0]
    assert offer["kind"] == "trigger" and offer["action"]["routine"] == "skylark_get_flight_gate" and started == []
    events = []
    env.ctx.bus.listeners.append(events.append)
    done = env.ctx.offers.decide(offer["id"], "accept", OWNER)
    fired = [e for e in events if e["type"] == "trigger_fired"]
    assert fired and {k: fired[-1][k] for k in ("trigger", "name", "task_id", "offer_id")} == {
        "trigger": w["id"], "name": "Watch my gate", "task_id": done["task_id"], "offer_id": offer["id"]}
    task = env.ctx.tasks.get(done["task_id"])
    assert task["source"] == "web" and env.ctx.alerts.trigger_of(task)["id"] == w["id"]  # credited to the watcher, as before
    flight = env.memory.create_entity("Flight")
    env.memory.observe(flight, "number", "SL 482", source=env.memory.add_source("email", {"subject": "x"}))
    change = {"entity": flight, "attribute": "gate", "old": "B12", "new": "C14"}
    assert env.ctx.alerts.why_not(task, env.ctx.alerts.trigger_of(task), change) is None  # so its change pushes


def test_a_change_made_by_a_task_from_the_triggers_offer_doesnt_feed_it():
    u = unit()
    mem = u.memory
    flight = demo_flight(mem)
    trig = u.sched.add("fact_changed", "Departure changed", {"entity_type": "Flight", "attribute": "depart_time"},
                       {"goal": "My flight now leaves at {change.new}: what's its gate?", "ask": True})
    mem.observe(flight, "depart_time", "8:30 AM", source=mem.add_source("email", {"subject": "Delay"}))
    offer = u.sched.tick()[0]
    assert offer["action"]["goal"] == "My flight now leaves at 8:30 AM: what's its gate?"
    assert offer["action"]["request"] == "My flight now leaves at : what's its gate?"
    task = u.store.get(u.offers.decide(offer["id"], "accept", OWNER)["task_id"])
    screen = mem.add_source("app_screen", {"app": "com.skylark.air", "task_id": task["id"]})
    mem.observe(flight, "depart_time", "9:00 AM", source=screen)  # the task it started saw another change
    assert u.sched.tick() == []  # not fed back to itself
    assert u.offers.trigger_of(task["id"]) == trig["id"]


# ---- push and the proactivity setting -----------------------------------------------------------------


def test_proactivity_decides_which_offers_push_and_approvals_always_push(tmp_path, monkeypatch):
    monkeypatch.setattr("api.push.LOG", tmp_path / "push.jsonl")
    store, sent = TaskStore(":memory:"), []
    pusher = Pusher(store, VapidKeys(tmp_path), "http://127.0.0.1:8741", send=lambda info, data, **kw: sent.append(json.loads(data)) or SimpleNamespace(status_code=201))
    pusher.subscribe({"endpoint": "http://127.0.0.1:9/push", "keys": {"p256dh": "x", "auth": "y"}}, None)

    def push(kind: str) -> list:
        n = len(sent)
        offer = {"id": f"offer-{kind}", "kind": kind, "status": "pending", "title": f"Should I {kind}?", "body": "b", "expires_at": None, "action": {}}
        for f in pusher.on_event({"type": "offer", "change": "created", "offer": offer}) or []:
            f.result()
        pusher.pool.shutdown(wait=True)
        pusher.pool = __import__("concurrent.futures").futures.ThreadPoolExecutor(max_workers=4)
        return sent[n:]

    for level, want in (("off", set()), ("important", {"trigger", "handoff", "trigger_request"}), ("all", {"trigger", "handoff", "trigger_request", "repeat"})):
        store.set_setting("proactivity", level)
        got = {k for k in ("trigger", "repeat", "handoff", "trigger_request") if push(k)}
        assert got == want, level
    store.set_setting("proactivity", "important")
    p = push("trigger")[0]
    assert p["kind"] == "offer" and p["url"] == "/?offer=offer-trigger" and p["title"] == "Should I trigger?"
    assert not pushes("repeat", None) and pushes("trigger", "bogus")  # the default is important
    store.set_setting("proactivity", "off")
    n = len(sent)
    pusher.on_event({"type": "approval_requested", "approval": {"id": "appr-1", "description": "Pay $18.42"}, "task_id": "t"})
    pusher.pool.shutdown(wait=True)
    assert len(sent) == n + 1 and sent[-1]["kind"] == "approval"  # approvals aren't proactivity


def test_the_proactivity_setting_over_http(phase5_env):  # noqa: F811
    env = phase5_env
    with TestClient(env.ctx.asgi) as c:
        h = me(env.token)
        assert c.get("/api/settings/proactivity", headers=h).json() == {"level": "important", "levels": ["off", "important", "all"]}
        assert c.post("/api/settings/proactivity", json={"level": "loud"}, headers=h).status_code == 400
        assert c.post("/api/settings/proactivity", json={"level": "all"}, headers=h).json()["level"] == "all"
        assert env.ctx.offers.level() == "all"
        assert c.post("/api/settings/proactivity", json={"level": "off"}).status_code == 401


# ---- no token, no MCP --------------------------------------------------------------------------------


def test_no_token_and_no_mcp_call_path_decides(phase5_env):  # noqa: F811
    env = phase5_env
    env.ctx.runner.start = starter(env.ctx.tasks, [])
    o = env.ctx.offers.make(kind="trigger", title="t", body="", action=CHECK_IN, source="mcp", key="m1")  # MCP may create one
    with TestClient(env.ctx.asgi) as c:
        shortcut = c.post("/api/tokens", json={"scope": "photos"}, headers=me(env.token)).json()["token"]
        for h in ({}, {"Authorization": "Bearer mcp-test-token"}, me(shortcut), me("nope")):
            assert c.post(f"/api/offers/{o['id']}", json={"decision": "accept"}, headers=h).status_code == 401
            assert c.get("/api/offers", headers=h).status_code == 401
        c.cookies.set("envoy_session", env.token)
        assert c.post(f"/api/offers/{o['id']}", json={"decision": "accept"}).status_code == 403  # no X-Envoy: another site can't
        c.cookies.clear()
        mc = TestClient(env.ctx.asgi, base_url="http://127.0.0.1:8700")
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        hdr = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json", "MCP-Protocol-Version": "2025-11-25",
               "Authorization": "Bearer mcp-test-token"}
        tools = mc.post("/mcp", json=body, headers=hdr).json()["result"]["tools"]
        assert not any(w in t["name"] for t in tools for w in ("accept", "decide", "answer", "approv"))
    assert env.ctx.offers.get(o["id"])["status"] == "pending"
    for path in (REPO / "backend" / "mcp_server").rglob("*.py"):  # the MCP server never calls decide (it can't make a session)
        assert "offers.decide" not in path.read_text() and "decide_offer" not in path.read_text(), path
    with pytest.raises(OfferError):
        env.ctx.offers.decide(o["id"], "accept", None)


def test_offers_over_http(phase5_env):  # noqa: F811
    env = phase5_env
    started: list = []
    env.ctx.runner.start = starter(env.ctx.tasks, started)
    o = env.ctx.offers.make(kind="trigger", title="Check in for SL 482?", body="b", action=CHECK_IN, source="trigger:x", key="w1")
    with TestClient(env.ctx.asgi) as c:
        h = me(env.token)
        assert [x["id"] for x in c.get("/api/offers", headers=h).json()] == [o["id"]]
        assert c.get("/api/offers?status=bogus", headers=h).status_code == 400
        assert c.get(f"/api/offers/{o['id']}", headers=h).json()["title"] == "Check in for SL 482?"
        assert c.post(f"/api/offers/{o['id']}", json={"decision": "maybe"}, headers=h).status_code == 400
        assert c.post("/api/offers/offer-nope", json={"decision": "accept"}, headers=h).status_code == 404
        r = c.post(f"/api/offers/{o['id']}", json={"decision": "accept"}, headers=h).json()
        assert r["status"] == "accepted" and r["task_id"] and c.get("/api/offers", headers=h).json() == []
        assert [x["status"] for x in c.get("/api/offers?status=all", headers=h).json()] == ["accepted"]
        assert c.post(f"/api/offers/{o['id']}", json={"decision": "accept"}, headers=h).json()["task_id"] == r["task_id"]


# ---- the briefing ------------------------------------------------------------------------------------


def test_pending_offers_are_in_the_briefing_and_ask_mode_is_marked(phase5_env):  # noqa: F811
    env = phase5_env
    ctx = env.ctx
    noon = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0).timestamp()
    o = ctx.offers.make(kind="trigger", title="Check in for SL 482?", body="From your trigger", action=CHECK_IN, source="trigger:x", key="b1",
                        preflight=[{"kind": "approval", "text": "Confirming check-in will go ahead: you asked for it", "level": "info"}])
    ctx.scheduler.add("time", "Check in for SL 482", {"at": noon + 3 * 3600}, {"goal": "Check me in for my flight", "ask": True})
    b = build_briefing(ctx.tasks, ctx.memory, ctx.routines, ctx.scheduler, ctx.alerts, now=noon, offers=ctx.offers)
    need = next(n for n in b["needs"] if n["kind"] == "offer")
    assert need["id"] == o["id"] and need["goal"] == CHECK_IN["goal"] and need["preflight"][0]["kind"] == "approval" and need["action"] == "task"
    assert b["upcoming"][0]["ask"] is True and "I'll ask you first" in b["text"] and "I have a question for you: Check in for SL 482?" in b["text"]
    ctx.offers.decide(o["id"], "decline", OWNER)
    b = build_briefing(ctx.tasks, ctx.memory, ctx.routines, ctx.scheduler, ctx.alerts, now=noon, offers=ctx.offers)
    assert not any(n["kind"] == "offer" for n in b["needs"])
    with TestClient(ctx.asgi) as c:
        assert c.get("/api/briefing", headers=me(env.token)).status_code == 200


# ---- the presets' templates ---------------------------------------------------------------------------


def preset_values(sched: Scheduler, mem: MemoryStore, preset: dict) -> list[dict[str, str]]:
    """The values each preset's firing would bring, from the demo's flights and inbox."""
    kind, spec = preset["body"]["kind"], preset["body"]["spec"]
    if kind == "before_fact":
        return [v for _, _, v in sched.occasions(spec)]
    if kind == "email":
        return [v for _, v in sched._new_emails({**spec, "after_rowid": 0}, set())]
    if kind == "fact_changed":
        return [{**sched.values(e["id"]), **{f"flight.{k}": v for k, v in sched.values(e["id"]).items()},
                 "change.attribute": "depart_time", "change.old": "6:10 AM", "change.new": "8:30 AM"} for e in mem.entities("Flight")]
    return [{}]


def demo_memory(tmp_path: Path) -> MemoryStore:
    """The demo memory when this checkout has it (data/demo/memory.db, copied), else the same facts built here."""
    db = REPO / "data" / "demo" / "memory.db"
    if db.exists():
        shutil.copy(db, tmp_path / "memory.db")
        mem = MemoryStore(tmp_path / "memory.db")
    else:
        mem = MemoryStore(":memory:")
        demo_flight(mem)
        demo_flight(mem, "SL 1190", "Sat, Nov 14, 2026", "2:45 PM", "Denver")
    src = mem.add_source("email", {"subject": "Check-in is open for your flight to Chicago", "sender": "SkyLark Air <reservations@skylark.example>"})
    for f in mem.entities("Flight"):
        if (mem.current(f["id"], "number") or {}).get("value") == "SL 482":
            mem.observe(f["id"], "number", "SL 482", source=src)  # the check-in email names the flight and its city
            for n in mem.neighbors(f["id"]):
                if (mem.entity(n) or {}).get("type") == "Trip":
                    mem.observe(n, "destination", "Chicago", source=src)
    return mem


def test_every_preset_renders_with_demo_values_and_no_empty_slot(tmp_path):
    mem = demo_memory(tmp_path)
    sched = Scheduler(TaskStore(":memory:"), mem, lambda *a, **k: {"id": "t"}, EventBus())
    asked = [p for p in PRESETS if p["body"]["action"].get("ask")]
    assert {p["body"]["kind"] for p in asked} >= {"before_fact", "email"}  # the two ask-mode presets
    for p in PRESETS:
        a = p["body"]["action"]
        templates = [t for t in (a.get("goal"), a.get("offer_title")) if t]
        values = preset_values(sched, mem, p)
        assert values, p["label"]
        for v in values[:3]:
            lower = {k.lower(): str(x) for k, x in v.items()}
            for t in templates:
                filled = _fill(t, lower)
                for slot in __import__("re").findall(r"\{([\w.]+)\}", t):
                    assert lower.get(slot.lower()), f"{p['label']}: {{{slot}}} is empty in {t!r}"
                assert "{" not in filled and "  " not in filled
            for name, path in (a.get("inputs_from") or {}).items():
                assert lower.get(path.lower()), f"{p['label']}: input {name} from {path} is empty"
        sched.add(p["body"]["kind"], p["body"]["name"], json.loads(json.dumps(p["body"]["spec"])), json.loads(json.dumps(a)))  # valid as given
