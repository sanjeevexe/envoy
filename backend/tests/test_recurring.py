"""Offline tests for chat setting up recurring jobs (api/recurring.py), with a recorded adapter: the code pre-filter, every
other message taking chat's path byte for byte, each kind of draft becoming a trigger that is switched off and asks
each time, the checks that refuse a draft (words you didn't type, a sender you didn't name, too often), and the offer
that turns it on."""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.chat import chat
from api.recurring import Draft, Recurring, may_schedule, own_words, when
from models.schemas import ChatRoute
from test_crossapp import Routines, SpyCross, SpyRunner
from test_offers import OWNER, unit
from test_phase5 import me

NOW = datetime(2026, 10, 29, 12, 0)


class Recorded:
    """Replies by job name; records each call's job, content and instructions."""

    def __init__(self, replies: dict) -> None:
        self.replies, self.calls = replies, []

    def call(self, job, content, **kw):
        name = job if isinstance(job, str) else job.name
        self.calls.append((name, content, kw.get("instructions")))
        r = self.replies[name]
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(parsed=r(content) if callable(r) else r, cost_at_standard_usd=0.0012)

    @property
    def jobs(self) -> list[str]:
        return [c[0] for c in self.calls]


def draft(**kw) -> Draft:
    base = dict(recurring=True, kind="time", name="", days=[], time_of_day="", every_minutes=0, minutes_before=0, sender_contains="",
                subject_contains="", attribute="", goal="")
    return Draft(**{**base, **kw})


def chat_route(c: str) -> ChatRoute:
    return ChatRoute(kind="task", goal=c.split("\n")[0].removeprefix("REQUEST: "), reply="")


def setup(d: Draft | Exception, chat_reply=chat_route):
    u = unit([NOW.timestamp()])
    adapter = Recorded({"recurring": d, "chat": chat_reply})
    runner = SpyRunner()
    runner.recurring = Recurring(u.offers, u.sched, adapter, clock=lambda: NOW)
    return u, adapter, runner


def say(message: str, adapter, runner, source="chat") -> dict:
    return asyncio.run(chat(message, adapter=adapter, memory=None, runner=runner, routines=Routines(), source=source))


# ---- the pre-filter, and everything else untouched ---------------------------------------------------------


SCHEDULED = ["Every Friday at 6 PM, order my usual from Thai Basil", "check my flight status each morning at 7", "Order coffee daily at 8am",
             "Weekly on Mondays, check my gate", "Whenever SkyLark emails me about check-in, check me in", "When my gate changes, tell me the new one",
             "Remind me to check in", "Check me in before every flight", "Before my flights, look up the gate", "on Fridays get my usual from Thai Basil"]
PLAIN = ["What's my gate?", "Check me in for my flight to Chicago", "Order my usual from Thai Basil on DoorDash", "What's a Caffè Latte at Starbucks vs on DoorDash?",
         "How many calories are in a Caffè Latte at Starbucks?", "When does my Amazon package arrive?", "Change my seat to 21C", "hi", "What changed?"]


def test_only_schedule_words_go_further():
    for m in SCHEDULED:
        assert may_schedule(m), m
    for m in PLAIN:
        assert not may_schedule(m), m


@pytest.mark.parametrize("message", PLAIN)
def test_every_other_message_takes_chats_path_byte_for_byte(message):
    """The same model calls (job, content, instructions), the same task, the same reply as chat with no recurring jobs."""
    def run(with_recurring: bool):
        from api.crossapp import LeadSplit
        adapter = Recorded({"chat": chat_route, "lead": LeadSplit(multi_app=False, parts=[], relation="separate"),
                            "recurring": AssertionError("the draft must not be called")})
        runner = SpyRunner(SpyCross())
        if with_recurring:
            runner.recurring = SimpleNamespace(propose=lambda *a, **k: (_ for _ in ()).throw(AssertionError("never called")))
        out = asyncio.run(chat(message, adapter=adapter, memory=None, runner=runner, routines=Routines()))
        return out, adapter.calls, runner.started
    a, b = run(True), run(False)
    assert a[1] == b[1] and a[2] == b[2] and a[0] == b[0]
    assert "recurring" not in [c[0] for c in a[1]]


def test_not_recurring_after_all_goes_on_as_before_and_counts_the_call():
    u, adapter, runner = setup(draft(recurring=False))
    out = say("Check me in before every flight? No, just this one to Chicago", adapter, runner)
    assert adapter.jobs == ["recurring", "chat"] and out["kind"] == "task" and out["model_calls"] == 2 and out["cost_usd"] == pytest.approx(0.0024)
    assert u.store.triggers() == [] and u.offers.list("all") == []
    u2, broken, runner2 = setup(RuntimeError("402 billing"))
    assert say("Every Friday at 6 PM, order my usual from Thai Basil", broken, runner2)["kind"] == "task"  # a failing draft: chat as before


# ---- drafts that become a trigger, switched off, asking each time ------------------------------------------------


CASES = [
    ("Every Friday at 6 PM, order my usual from Thai Basil", draft(name="Friday Thai", days=["fri"], time_of_day="18:00", goal="Order my usual from Thai Basil"),
     "time", {"weekly_on": {"days": ["fri"], "at": "18:00"}}, "Set this up? Every Friday at 6:00 PM: order your usual from Thai Basil"),
    ("Check my flight status every weekday morning at 7:30", draft(days=["mon", "tue", "wed", "thu", "fri"], time_of_day="07:30", goal="Check my flight status"),
     "time", {"weekly_on": {"days": ["mon", "tue", "wed", "thu", "fri"], "at": "07:30"}}, "Set this up? Every weekday at 7:30 AM: check your flight status"),
    ("Order my morning coffee daily at 8", draft(time_of_day="08:00", goal="Order my morning coffee"),
     "time", {"daily_at": "08:00"}, "Set this up? Every day at 8:00 AM: order your morning coffee"),
    ("Every 2 hours, check my flight status", draft(every_minutes=120, goal="check my flight status"),
     "time", {"every_minutes": 120}, "Set this up? Every 2 hours: check your flight status"),
    ("Check me in 24 hours before every flight", draft(kind="before_fact", minutes_before=1440, goal="Check me in"),
     "before_fact", {"entity_type": "Flight", "date_attr": "date", "time_attr": "depart_time", "minutes_before": 1440},
     "Set this up? 24 h before every flight: check you in"),
    ("Whenever SkyLark emails me about check-in, check me in for my flight", draft(kind="email", sender_contains="SkyLark", subject_contains="check-in",
                                                                                   goal="Check me in for my flight"),
     "email", {"sender_contains": "SkyLark", "subject_contains": "check-in"},
     "Set this up? Whenever an email from “SkyLark” about “check-in” arrives: check you in for your flight"),
    ("When my flight's gate changes, look up my boarding time", draft(kind="fact_changed", attribute="gate", goal="look up my boarding time"),
     "fact_changed", {"entity_type": "Flight", "attributes": ["gate"]}, "Set this up? Whenever your flight's gate changes: look up your boarding time"),
]


@pytest.mark.parametrize("message,d,kind,spec,title", CASES)
def test_a_recurring_request_becomes_a_switched_off_trigger_and_an_offer(message, d, kind, spec, title):
    u, adapter, runner = setup(d)
    out = say(message, adapter, runner)
    assert adapter.jobs == ["recurring"] and runner.started == []  # one call, nothing started
    trig = u.store.trigger(out["trigger"]["id"])
    assert trig["kind"] == kind and {k: v for k, v in trig["spec"].items() if k not in ("after_rowid", "after_seq", "memory_db")} == spec
    assert not trig["enabled"] and trig["action"] == {"goal": d.goal.rstrip("."), "ask": True}  # off, and asks each time once on
    o = out["offer"]
    assert out["kind"] == "trigger_request" and o["kind"] == "trigger_request" and o["source"] == "chat" and o["title"] == title
    assert o["action"]["type"] == "enable_trigger" and o["action"]["trigger_id"] == trig["id"]
    assert "off until you say yes" in out["reply"] and out["model_calls"] == 1


def test_off_until_your_yes_then_it_asks_each_time():
    u, adapter, runner = setup(draft(days=["fri"], time_of_day="18:00", goal="Order my usual from Thai Basil"))
    out = say("Every Friday at 6 PM, order my usual from Thai Basil", adapter, runner, source="voice")
    assert out["offer"]["source"] == "voice"
    u.now[0] = datetime(2026, 10, 30, 18, 1).timestamp()  # Friday, 6:01 PM
    assert u.sched.tick() == []  # off: nothing fires
    u.offers.decide(out["offer"]["id"], "accept", OWNER)
    assert u.store.trigger(out["trigger"]["id"])["enabled"]
    [asked] = u.sched.tick()  # on, in ask mode: it asks, it doesn't order
    assert asked["kind"] == "trigger" and asked["title"] == "Should I order your usual from Thai Basil?" and u.started == []
    assert asked["action"]["request"] == "Order my usual from Thai Basil"  # your own words, the whole request


# ---- drafts that are refused ----------------------------------------------------------------------------


@pytest.mark.parametrize("message,d,why", [
    ("Every Friday at 6 PM, order my usual from Thai Basil", draft(days=["fri"], time_of_day="18:00", goal="Order my usual from Thai Basil and tip $20"), "goal"),
    ("Every Friday at 6 PM, order my usual", draft(days=["fri"], time_of_day="18:00", goal="Order your usual from Thai Basil on DoorDash"), "goal"),
    ("Whenever I get an email about check-in, check me in", draft(kind="email", sender_contains="skylark", goal="check me in"), "isn't in what you wrote"),
    ("Every 5 minutes check my gate", draft(every_minutes=5, goal="check my gate"), "more often"),
    ("Every day check my gate", draft(goal="check my gate"), "time of day"),
    ("When my flight changes, check my gate", draft(kind="fact_changed", attribute="price", goal="check my gate"), "flight detail"),
])
def test_drafts_that_add_words_or_break_the_rules_set_up_nothing(message, d, why):
    u, adapter, runner = setup(d)
    out = say(message, adapter, runner)
    assert u.store.triggers() == [] and u.offers.list("all") == [] and runner.started == []
    assert out["kind"] == "trigger_request" and "offer" not in out and why in (out.get("draft_rejected") or "") + out["reply"]


def test_own_words_and_when():
    assert own_words("Check me in for my flight", "check me in before every flight")
    assert not own_words("Check you in", "check me in before every flight")
    assert not own_words("", "every day")
    assert when("time", {"every_minutes": 60}) == "every hour" and when("time", {"every_minutes": 45}) == "every 45 minutes"
    assert when("before_fact", {"minutes_before": 90}) == "90 minutes before every flight"
    assert when("time", {"weekly_on": {"days": ["mon", "fri"], "at": "9:00"}}) == "every Monday and Friday at 9:00 AM"


# ---- over HTTP --------------------------------------------------------------------------------------


def test_chat_over_http_sets_it_up_and_only_your_session_turns_it_on(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_BEARER_TOKEN", "mcp-test-token")
    monkeypatch.setenv("ENVOY_ALLOWED_HOSTS", "testserver")
    monkeypatch.setattr("api.app.API_DIR", tmp_path)
    monkeypatch.setattr("api.push.LOG", tmp_path / "push.jsonl")
    from api.app import build, session_token
    from api.store import TaskStore
    from memory.store import MemoryStore
    from routines.store import RoutineStore
    adapter = Recorded({"recurring": draft(days=["fri"], time_of_day="18:00", goal="Order my usual from Thai Basil"), "chat": chat_route})
    _, ctx = build("demo", memory=MemoryStore(":memory:"), tasks=TaskStore(":memory:"), routines=RoutineStore(tmp_path / "routines"), adapter=adapter)
    token = session_token()
    with TestClient(ctx.asgi) as c:
        out = c.post("/api/chat", json={"message": "Every Friday at 6 PM, order my usual from Thai Basil"}, headers=me(token)).json()
        assert out["kind"] == "trigger_request" and out["offer"]["title"].startswith("Set this up? Every Friday at 6:00 PM")
        [trig] = c.get("/api/triggers", headers=me(token)).json()
        assert not trig["enabled"] and trig["action"]["ask"] is True
        oid = out["offer"]["id"]
        assert c.post(f"/api/offers/{oid}", json={"decision": "accept"}, headers={"Authorization": "Bearer mcp-test-token"}).status_code == 401
        assert c.post(f"/api/offers/{oid}", json={"decision": "accept"}, headers=me(token)).json()["status"] == "accepted"
        assert c.get("/api/triggers", headers=me(token)).json()[0]["enabled"]
