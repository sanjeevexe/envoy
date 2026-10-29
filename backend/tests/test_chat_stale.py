"""Offline tests for answering from old memory (personal benchmark M4): past a fact's freshness window chat checks the
app first; memory answers alone only when no phone can run the check, and says how old the answer is."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

from api.chat import chat
from memory.store import MemoryStore
from models.schemas import ChatRoute
from test_crossapp import FakeAdapter

GOAL = "Check the gate of my flight to Chicago in SkyLark"


class Pool:
    def __init__(self, up: bool) -> None:
        self.up, self.phones = up, {}

    def running(self):
        return {"envoy-test": self.up, "envoy-real": False}

    @staticmethod
    def avd_for(app):
        return "envoy-test"


class Runner:
    def __init__(self, up: bool) -> None:
        self.pool, self.started = Pool(up), []

    def start(self, goal, source, **kw):
        self.started.append(goal)
        return {"id": "t1", "goal": goal}


class Routines:
    def active(self):
        return [SimpleNamespace(app="com.skylark.air", intent="Get the gate of a flight")]


def setup(age_s: float):
    m = MemoryStore(":memory:")
    src = m.add_source("app_screen", {"app": "com.skylark.air", "screen": "TripDetailsActivity"}, captured_at=time.time() - age_s)
    f = m.create_entity("Flight")
    m.observe(f, "number", "SL 482", source=src, observed_at=time.time() - age_s)
    m.observe(f, "gate", "B9", source=src, observed_at=time.time() - age_s)
    adapter = FakeAdapter({"chat": ChatRoute(kind="memory", goal=GOAL, reply=""),
                           "answer": SimpleNamespace(answer="Your gate is B9.", found=True, stale=age_s > 1800)})
    return m, adapter


def ask(age_s: float, up: bool):
    m, adapter = setup(age_s)
    runner = Runner(up)
    out = asyncio.run(chat("What's my gate?", adapter=adapter, memory=m, runner=runner, routines=Routines()))
    return out, runner


def test_an_old_gate_is_checked_in_the_app_first():
    out, runner = ask(3 * 3600, up=True)
    assert out["kind"] == "task" and runner.started == [GOAL]
    assert "may have changed" in out["reply"] and "B9" in out["reply"]


def test_with_no_phone_memory_answers_and_says_how_old():
    out, runner = ask(3 * 3600, up=False)
    assert out["from_memory"] and runner.started == []
    assert out["reply"].startswith("Your gate is B9.") and "no phone is free" in out["reply"]


def test_a_fresh_gate_is_answered_from_memory():
    out, runner = ask(5 * 60, up=True)
    assert out["from_memory"] and runner.started == [] and out["reply"] == "Your gate is B9."
