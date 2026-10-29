"""Offline tests for learning from repeats (api/repeats.py) and weekly triggers: each pattern (weekly, daily, before a
trip), the near-misses that aren't one, a "Not now" that never comes back, money tasks (only ever a habit that asks),
tasks a trigger started (directly or through its offer) never counting, and the demo seed."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from api.repeats import Repeats, template
from api.scheduler import check_weekly
from api.store import TaskStore
from test_offers import OWNER, demo_flight, unit
from test_phase5 import env as phase5_env  # noqa: F401 - the fixture

REPO = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 29, 12, 0)  # a Thursday; Oct 12, 19 and 26 are Mondays


def ts(*a: int) -> float:
    return datetime(*a).timestamp()


def done(store: TaskStore, goal: str, when: float, source: str = "chat", **kw) -> dict:
    t = store.create(goal, source, status="done", result="ok", **kw)
    with store.lock:
        store.db.execute("UPDATE tasks SET created_at=?, updated_at=? WHERE id=?", (when, when + 20, t["id"]))
        store.db.commit()
    return store.get(t["id"])


def setup():
    u = unit([NOW.timestamp()])
    u.repeats = Repeats(u.store, u.memory, u.offers, u.sched, clock=lambda: u.now[0])
    return u


STATUS = dict(routine="skylark_check_flight_status", inputs={"flight_number": "SL 1190"}, app="com.skylark.air")


def mondays(u, times=((8, 0), (8, 20), (7, 45)), days=(12, 19, 26), source="chat", **kw):
    for d, (h, m) in zip(days, times):
        done(u.store, "Check the status of my flight SL 1190", ts(2026, 10, d, h, m), source=source, **{**STATUS, **kw})


# ---- the patterns --------------------------------------------------------------------------------------


def test_three_mondays_at_8_become_a_weekly_habit_that_asks():
    u = setup()
    mondays(u)
    [o] = u.repeats.scan()
    a = o["action"]
    assert o["kind"] == "repeat" and o["title"] == "Make this a habit?" and o["status"] == "pending"
    assert o["body"] == "You asked me to check the status of your flight SL 1190 on your last 3 Mondays (Oct 12, Oct 19 and Oct 26), around 8:00 AM."
    assert a["type"] == "create_trigger" and a["kind"] == "time" and a["spec"] == {"weekly_on": {"days": ["mon"], "at": "08:00"}}
    assert a["action"] == {"goal": "Check the status of my flight SL 1190", "ask": True, **{k: STATUS[k] for k in ("routine", "inputs")}}
    assert a["setup"] == "asks you every Monday at 8:00 AM" and "Should I check the status of your flight SL 1190?" in a["summary"]
    assert u.repeats.scan() == []  # pending: not twice
    trig = u.store.trigger(u.offers.decide(o["id"], "accept", OWNER)["result"]["trigger_id"])
    assert trig["enabled"] and trig["action"]["ask"] is True and trig["spec"]["weekly_on"] == {"days": ["mon"], "at": "08:00"}
    assert datetime.fromtimestamp(u.sched.next_runs(trig, NOW.timestamp())[0]["at"]) == datetime(2026, 11, 2, 8, 0)
    mondays(u, days=(5, 12, 19))  # more of the same: a trigger covers it now
    assert u.repeats.scan() == []


def test_three_days_in_a_row_become_a_daily_habit():
    u = setup()
    for d, (h, m) in zip((26, 27, 28), ((21, 0), (21, 30), (20, 45))):
        done(u.store, "Read me tomorrow's forecast.", ts(2026, 10, d, h, m))
    [o] = u.repeats.scan()
    assert o["action"]["spec"] == {"daily_at": "21:00"} and "3 days in a row (Oct 26, Oct 27 and Oct 28), around 9:00 PM" in o["body"]
    assert o["action"]["action"] == {"goal": "Read me tomorrow's forecast.", "ask": True}


def test_before_every_trip_reads_each_trips_destination():
    u = setup()
    demo_flight(u.memory, "SL 1190", "Sat, Oct 17, 2026", "2:45 PM", "Denver")
    demo_flight(u.memory, "SL 1585", "Thu, Oct 22, 2026", "7:35 AM", "Savannah")
    demo_flight(u.memory)  # SL 482 to Chicago, Fri Oct 30 6:10 AM
    for city, when in (("Denver", ts(2026, 10, 16, 15, 0)), ("Savannah", ts(2026, 10, 21, 8, 0)), ("Chicago", ts(2026, 10, 29, 9, 0))):
        done(u.store, f"What's my gate for {city}?", when, routine="skylark_get_flight_gate", inputs={"trip_city": city}, app="com.skylark.air")
    [o] = u.repeats.scan()
    a = o["action"]
    assert a["kind"] == "before_fact" and a["spec"]["entity_type"] == "Flight" and a["spec"]["date_attr"] == "date" and a["spec"]["time_attr"] == "depart_time"
    assert 21 * 60 <= a["spec"]["minutes_before"] <= 24 * 60
    assert a["action"] == {"routine": "skylark_get_flight_gate", "inputs_from": {"trip_city": "trip.destination"}, "ask": True,
                           "goal": "What's my gate for {trip.destination}?"}
    assert o["body"].startswith("You asked “what's your gate for your destination?” before your last 3 flights (Oct 16, Oct 21 and Oct 29)")
    trig = u.store.trigger(u.offers.decide(o["id"], "accept", OWNER)["result"]["trigger_id"])
    u.now[0] = ts(2026, 10, 29, 12, 5)
    fired = u.sched.tick()  # the next flight's window is open: it asks, with that trip's own values
    assert [(f["title"], f["action"]["goal"], f["action"]["request"], f["action"]["inputs"]) for f in fired] == [
        ("Should I look this up: what's your gate for Chicago?", "What's my gate for Chicago?", "What's my gate for ?", {"trip_city": "Chicago"})]
    assert trig and u.started == []


def test_template_keeps_your_words_and_slots_the_trips_values():
    t = {"goal": "Watch the gate for SL 482 to chicago", "inputs": {"trip_city": "Chicago"}}
    assert template(t, {"trip_city": "trip.destination"}, {"number": "SL 482"}) == "Watch the gate for {number} to {trip.destination}"
    assert template({"goal": "Find my gate", "inputs": {"trip_city": "Chicago"}}, {"trip_city": "trip.destination"}, {}) is None


# ---- near-misses ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("times,days", [
    (((8, 0), (8, 15)), (19, 26)),  # only twice
    (((8, 0), (13, 0), (19, 0)), (12, 19, 26)),  # Mondays, at different times
    (((8, 0), (8, 0), (8, 0)), (19, 21, 23)),  # the same time, but neither one weekday nor days in a row
    (((8, 0), (8, 30), (10, 1)), (12, 19, 26)),  # more than 90 minutes either way from each other
])
def test_near_misses_are_not_habits(times, days):
    u = setup()
    mondays(u, times=times, days=days)
    assert u.repeats.scan() == []


def test_a_run_of_days_broken_by_a_gap_is_not_daily():
    u = setup()
    for d in (20, 21, 23, 24):
        done(u.store, "Read me tomorrow's forecast", ts(2026, 10, d, 21, 0))
    assert u.repeats.scan() == []


# ---- what never comes back, and what never counts --------------------------------------------------------


def test_a_declined_pattern_never_comes_back():
    u = setup()
    mondays(u)
    [o] = u.repeats.scan()
    u.offers.decide(o["id"], "decline", OWNER)
    mondays(u, days=(5,), times=((8, 5),))  # a fourth Monday
    assert u.repeats.scan() == [] and len(u.offers.list("all")) == 1


def test_money_tasks_only_ever_become_habits_that_ask():
    u = setup()
    for d in (12, 19, 26):
        t = done(u.store, "Get my usual from Thai Basil on DoorDash", ts(2026, 10, d, 18, 30), routine="doordash_reorder_usual",
                 inputs={"restaurant": "Thai Basil"}, app="com.dd.doordash")
        u.store.add_approval(t["id"], "Pay $18.42 at DoorDash", ["costs money"], "com.dd.doordash", "Checkout\nTotal $18.42", None)
    [o] = u.repeats.scan()
    assert o["action"]["action"]["ask"] is True and "It involves money, so it will always ask you first." in o["body"]
    assert all(x["action"]["action"]["ask"] is True for x in u.offers.list("all") if x["kind"] == "repeat")


def test_tasks_a_trigger_started_never_count_even_through_its_offer():
    u = setup()
    mondays(u, source="trigger:Monday status")
    assert u.repeats.scan() == []
    u2 = setup()
    for d, h in ((12, 8), (19, 8), (26, 8)):  # you said yes to a trigger's offer each Monday: still the trigger's
        o = u2.offers.make(kind="trigger", title="Check SL 1190?", body="", source="trigger:Monday status", key=f"trig-1:{d}", origin={"trigger_id": "trig-1"},
                           action={"type": "task", "goal": "Check the status of my flight SL 1190", "request": "Check the status of my flight", **STATUS})
        tid = u2.offers.decide(o["id"], "accept", OWNER)["task_id"]
        with u2.store.lock:
            u2.store.db.execute("UPDATE tasks SET status='done', created_at=?, updated_at=? WHERE id=?", (ts(2026, 10, d, h, 0), ts(2026, 10, d, h, 1), tid))
            u2.store.db.commit()
        assert u2.store.get(tid)["source"] == "web"
    assert u2.repeats.scan() == []
    parts = setup()
    for d in (12, 19, 26):
        done(parts.store, "Price at Amazon", ts(2026, 10, d, 8, 0), parent="task-x")  # parts of a cross-app question
    assert parts.repeats.scan() == []


def test_it_looks_after_each_finished_task_and_once_a_day():
    u = setup()
    mondays(u, days=(12, 19))
    last = done(u.store, "Check the status of my flight SL 1190", ts(2026, 10, 26, 8, 10), **STATUS)
    u.repeats.on_event({"type": "task_finished", "task_id": last["id"]})
    assert len(u.offers.list()) == 1
    v = setup()
    mondays(v)
    v.sched.repeats = v.repeats
    v.sched.tick()
    assert len(v.offers.list()) == 1
    v.repeats.scan = lambda: (_ for _ in ()).throw(AssertionError("once a day"))  # a second tick the same day doesn't look again
    v.sched.tick()
    v.repeats.scan = lambda: 1 / 0
    v.now[0] += 86400
    v.sched.tick()  # a broken look never breaks the tick
    assert v.repeats.errors


def test_wired_into_the_app(phase5_env):  # noqa: F811
    env = phase5_env
    assert env.ctx.scheduler.repeats is not None and env.ctx.scheduler.repeats.on_event in env.ctx.bus.listeners


# ---- weekly triggers ---------------------------------------------------------------------------------


def test_weekly_triggers_fire_on_their_days_only():
    u = unit([ts(2026, 10, 29, 9, 0)])
    with pytest.raises(ValueError):
        u.sched.add("time", "x", {"weekly_on": {"days": ["funday"], "at": "18:00"}}, {"goal": "x"})
    with pytest.raises(ValueError):
        u.sched.add("time", "x", {"weekly_on": {"days": ["fri"]}}, {"goal": "x"})
    with pytest.raises(ValueError):
        u.sched.add("time", "x", {"weekly_on": {"days": [], "at": "18:00"}}, {"goal": "x"})
    t = u.sched.add("time", "Friday Thai", {"weekly_on": {"days": ["Friday", "tue"], "at": "6:00 PM"}}, {"goal": "Order my usual from Thai Basil"})
    assert t["spec"]["weekly_on"] == {"days": ["tue", "fri"], "at": "6:00 PM"}
    assert [datetime.fromtimestamp(r["at"]) for r in u.sched.next_runs(t)] == [datetime(2026, 10, 30, 18, 0), datetime(2026, 11, 3, 18, 0), datetime(2026, 11, 6, 18, 0)]
    u.now[0] = ts(2026, 10, 29, 18, 5)  # a Thursday: not one of its days
    assert u.sched.tick() == []
    u.now[0] = ts(2026, 10, 30, 18, 5)
    assert len(u.sched.tick()) == 1 and u.sched.tick() == []  # once that Friday
    u.now[0] = ts(2026, 11, 3, 18, 1)
    assert len(u.sched.tick()) == 1
    spec = {"weekly_on": {"days": ["sun"], "at": "9:30"}}
    check_weekly(spec)
    assert spec["weekly_on"]["days"] == ["sun"]


def test_a_weekly_ask_trigger_is_keyed_by_its_day():
    u = unit([ts(2026, 10, 30, 18, 1)])
    t = u.sched.add("time", "Friday Thai", {"weekly_on": {"days": ["fri"], "at": "18:00"}}, {"goal": "Order my usual from Thai Basil", "ask": True})
    [o] = u.sched.tick()
    assert o["key"] == f"{t['id']}:2026-10-30" and o["expires_at"] == pytest.approx(ts(2026, 10, 31, 18, 1)) and u.started == []


# ---- the demo seed ---------------------------------------------------------------------------------


def test_the_seed_writes_three_labelled_mondays_and_the_pattern_shows(tmp_path):
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "seed_repeats.py")], capture_output=True, text=True)
    assert r.returncode != 0 and "--api-dir" in r.stderr  # no default folder
    sys.path.insert(0, str(REPO / "scripts"))
    from seed_repeats import seed
    made = seed(tmp_path, NOW)
    assert len(made) == 3 and seed(tmp_path, NOW) == []  # twice adds nothing
    store = TaskStore(tmp_path / "envoy.db")
    tasks = store.list()
    assert all(t["source"] == "seed" and "seeded" in t["detail"] and t["status"] == "done" for t in tasks)
    assert sorted(datetime.fromtimestamp(t["created_at"]).strftime("%a %b %d") for t in tasks) == ["Mon Oct 12", "Mon Oct 19", "Mon Oct 26"]
    assert store.triggers() == []
    u = unit([NOW.timestamp()])
    from api.offers import Offers
    offers = Offers(store, u.bus, u.runner, u.sched, clock=lambda: NOW.timestamp())
    [o] = Repeats(store, u.memory, offers, u.sched, clock=lambda: NOW.timestamp()).scan()
    assert o["action"]["spec"] == {"weekly_on": {"days": ["mon"], "at": "08:00"}}
