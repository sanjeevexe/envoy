"""Offline tests for Home's briefing (`GET /api/briefing`): what needs you, what happened today and what's next, built
from the stores alone (no model call, nothing written); your name only when memory has it; suggestions from your
routines."""

from __future__ import annotations

import shutil
import time
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.briefing import build_briefing, user_name
from api.store import TaskStore
from memory.store import MemoryStore
from test_phase5 import me
from test_phase5 import env as phase5_env  # noqa: F401 - the fixture, built the same way

REPO = Path(__file__).resolve().parents[2]
NOON = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0).timestamp()  # "now" in these tests


@pytest.fixture()
def env(phase5_env):  # noqa: F811
    """The Phase 5 app with the gate routine in its store, Maya in memory, and a day's worth of tasks."""
    shutil.copytree(REPO / "data" / "routines" / "skylark_get_flight_gate", phase5_env.tmp / "routines" / "skylark_get_flight_gate")
    mem, tasks = phase5_env.memory, phase5_env.ctx.tasks
    src = mem.add_source("email", {"subject": "Your trip to Chicago", "from": "SkyLark Air <trips@skylark.example>"})
    person, flight = mem.create_entity("Person"), mem.create_entity("Flight")
    mem.observe(person, "name", "Maya Patel", source=src)
    mem.observe(flight, "number", "SL 482", source=src)
    screen = mem.add_source("app_screen", {"app": "com.skylark.air", "screen": "TripDetailsActivity", "task_id": "task-x"})
    phase5_env.screen = screen
    phase5_env.flight = flight
    return phase5_env


def at(tasks: TaskStore, task: dict, created: float, updated: float | None = None) -> None:
    with tasks.lock:
        tasks.db.execute("UPDATE tasks SET created_at=?, updated_at=? WHERE id=?", (created, updated or created, task["id"]))
        tasks.db.commit()


def change(env, attribute: str, old: str, new: str, when: float) -> None:
    tasks = env.ctx.tasks
    with tasks.lock:
        tasks.db.execute("INSERT INTO change_alerts (time, task_id, entity, entity_label, attribute, old, new, source, pushed, title) "
                         "VALUES (?,?,?,?,?,?,?,?,?,?)", (when, "task-x", env.flight, "Flight SL 482", attribute, old, new, env.screen, 1,
                                                          f"{attribute} changed: {old} → {new}"))
        tasks.db.commit()


def seed_day(env) -> dict[str, dict]:
    tasks = env.ctx.tasks
    out = {}
    out["pay"] = tasks.create("Get my usual from Thai Basil on DoorDash", "chat", app="com.dd.doordash", status="waiting_approval")
    tasks.add_approval(out["pay"]["id"], "Pay $18.42 at DoorDash", ["costs money"], "com.dd.doordash", "screen", None)
    out["phone"] = tasks.create("Check the price of AirPods at Target", "chat", app="com.target.ui", status="needs_you", waiting_for="phone",
                                detail="Target blocks emulators: use your Android phone?")
    out["signin"] = tasks.create("Track my Chipotle order", "chat", app="com.chipotle.ordering", status="needs_you", detail="Sign in to Chipotle")
    out["done"] = tasks.create("When does my Amazon package arrive?", "chat", app="com.amazon.mShop.android.shopping", status="done", result="Arrives Thursday")
    at(tasks, out["done"], NOON - 3600, NOON - 3590)
    out["coffee"] = tasks.create("Order my morning coffee", "trigger:Morning coffee", app="com.starbucks.mobilecard", routine="starbucks_order_usual",
                                 status="done", result="Ordered a grande latte")
    at(tasks, out["coffee"], NOON - 7200, NOON - 7191)
    out["old"] = tasks.create("Check me in for SL 482", "chat", status="done")
    at(tasks, out["old"], NOON - 2 * 86400)
    out["part"] = tasks.create("Price at Amazon", "crossapp", status="done", parent=out["done"]["id"])
    at(tasks, out["part"], NOON - 3600)
    change(env, "gate", "B12", "B14", NOON - 7000)
    change(env, "gate", "B14", "B22", NOON - 600)  # the same fact again: only its latest value shows
    change(env, "seat", "12A", "14C", NOON - 3 * 86400)  # too old
    env.ctx.scheduler.add("time", "Check in for SL 482", {"at": NOON + 3 * 3600}, {"goal": "Check me in for my flight"})
    env.ctx.scheduler.add("time", "Next week", {"at": NOON + 5 * 86400}, {"goal": "x"})
    env.ctx.scheduler.add("watch", "Watch my gate", {"every_minutes": 10}, {"routine": "skylark_get_flight_gate"})  # reruns aren't news
    paused = env.ctx.scheduler.add("time", "Paused", {"at": NOON + 600}, {"goal": "x"})
    tasks.update_trigger(paused["id"], enabled=0)
    return out


def brief(env, now: float = NOON) -> dict:
    ctx = env.ctx
    return build_briefing(ctx.tasks, ctx.memory, ctx.routines, ctx.scheduler, ctx.alerts, now=now)


def test_needs_today_next_and_suggestions(env):
    seeded = seed_day(env)
    b = brief(env)
    assert b["name"] == "Maya"
    needs = {n["kind"]: n for n in b["needs"]}
    assert needs["approval"]["title"] == "Pay $18.42 at DoorDash" and needs["approval"]["money"] and needs["approval"]["task_id"] == seeded["pay"]["id"]
    assert needs["phone"]["id"] == seeded["phone"]["id"] and "blocks emulators" in needs["phone"]["title"]
    assert needs["task"]["id"] == seeded["signin"]["id"]
    assert len(b["needs"]) == 3  # the task waiting on its approval shows once, as the approval
    kinds = [(x["kind"], x.get("new") or x.get("result")) for x in b["today"]]
    assert kinds == [("change", "B22"), ("task", "Arrives Thursday"), ("routine", "Ordered a grande latte")]  # newest first
    gate = b["today"][0]
    assert gate["source"] == "SkyLark" and gate["old"] == "B14" and gate["title"] == "Gate changed to B22"
    assert b["today"][2]["seconds"] == 9.0 and b["today"][2]["routine"] == "starbucks_order_usual"
    assert [u["name"] for u in b["upcoming"]] == ["Check in for SL 482"]  # not next week's, the paused one or the watcher
    assert b["suggestions"][0]["routine"] == "skylark_get_flight_gate" and b["suggestions"][0]["label"]
    assert b["text"] == ("Your gate for flight SL 482 changed to B22. Next up at 3:00 PM: Check in for SL 482. "
                         "One payment is waiting for your OK.")


def test_a_quiet_day_says_so(env):
    b = brief(env)
    assert b["needs"] == [] and b["today"] == [] and b["upcoming"] == []
    assert b["text"] == "All quiet. Nothing needs you right now."
    tasks = env.ctx.tasks
    for goal in ("one", "two"):
        at(tasks, tasks.create(goal, "chat", status="done"), NOON - 60)
    assert brief(env)["text"] == "I finished 2 tasks today."


def test_counts_and_kinds_of_waiting(env):
    tasks = env.ctx.tasks
    for i in range(2):
        t = tasks.create(f"check in {i}", "chat", status="waiting_approval")
        tasks.add_approval(t["id"], 'Tap "Confirm check-in" in com.skylark.air', ["irreversible"], "com.skylark.air", "screen", None)
    b = brief(env)
    assert b["text"] == "2 actions are waiting for your OK."  # not payments
    tasks.create("price at Target", "chat", status="needs_you", waiting_for="phone")
    assert "One task asks to use your Android phone." in brief(env)["text"]


def test_your_name_only_when_memory_has_it():
    mem = MemoryStore(":memory:")
    assert user_name(mem) is None
    src = mem.add_source("email", {"from": "x"})
    p = mem.create_entity("Person")
    mem.observe(p, "email", "envoy3955@gmail.com", source=src)
    mem.observe(p, "name", "envoy", source=src)  # an email's user name, not a name
    assert user_name(mem) is None
    mem.observe(p, "first_name", "Sanjeev", source=src)
    assert user_name(mem) == "Sanjeev"
    other = mem.create_entity("Person")
    mem.observe(other, "name", "Maya Patel", source=src)
    assert user_name(mem) is None  # two people: memory can't say which one is you


def test_the_endpoint_is_read_only_and_needs_your_session(env):
    seed_day(env)
    ctx = env.ctx
    with TestClient(ctx.asgi) as c:
        assert c.get("/api/briefing").status_code == 401
        before = (ctx.tasks.db.total_changes, ctx.memory.db.total_changes)
        r = c.get("/api/briefing", headers=me(env.token))
        again = c.get("/api/briefing", headers=me(env.token))
        assert r.status_code == 200 and again.json()["text"] == r.json()["text"]
        assert (ctx.tasks.db.total_changes, ctx.memory.db.total_changes) == before  # nothing written
        assert env.adapter.calls == []  # no model call
        body = r.json()
        assert set(body) == {"time", "name", "text", "needs", "today", "upcoming", "suggestions"}
        assert abs(body["time"] - time.time()) < 60
