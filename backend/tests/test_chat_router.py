"""Chat's router (api/chat.py): a request to do something in an app is a task even when no learned routine covers it.

In the personal benchmark (run 1's P2), "Add a checked bag to my Chicago trip." got "I don't have a routine for that in
the SkyLark app": SkyLark had routines, none for bags. Replayed on Spark, 6 of 40 as is, 0 of 40 with the line below
(eval/results/personal/2026-10-28-run1/p2-router/ on claude/wonder-appnotes).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from api.chat import chat
from memory.store import MemoryStore
from models.prompts import CHAT_INSTRUCTIONS
from models.schemas import ChatRoute

LINE = "A task needs no learned routine: APPS lists only what Envoy has already learned"


class Recorder:
    def __init__(self) -> None:
        self.calls = []

    def call(self, job, content, **kw):
        self.calls.append({"job": job, "content": content, **kw})
        return SimpleNamespace(parsed=ChatRoute(kind="task", goal="Add a checked bag to my Chicago trip in SkyLark", reply=""),
                               cost_at_standard_usd=0.001)


class Runner:
    def __init__(self) -> None:
        self.started = []

    def start(self, goal, source, **kw):
        self.started.append(goal)
        return {"id": "t1", "goal": goal}


class Routines:
    def active(self):
        return [SimpleNamespace(app="com.skylark.air", intent="Check in for a SkyLark flight"),
                SimpleNamespace(app="com.skylark.air", intent="Change a seat on a SkyLark flight")]


def test_the_router_is_told_a_task_needs_no_learned_routine():
    assert CHAT_INSTRUCTIONS.count(LINE) == 1
    adapter, runner = Recorder(), Runner()
    out = asyncio.run(chat("Add a checked bag to my Chicago trip.", adapter=adapter, memory=MemoryStore(":memory:"), runner=runner,
                           routines=Routines()))
    call = adapter.calls[0]
    assert call["job"] == "chat" and LINE in call["instructions"] and "Change a seat on a SkyLark flight" in call["content"]
    assert out["kind"] == "task" and runner.started == ["Add a checked bag to my Chicago trip in SkyLark"]
