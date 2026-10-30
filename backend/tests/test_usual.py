"""Your usual (memory/usual.py): what you tell Envoy you always get from a place, in chat or on the Memory page, stored
with you as its source; "order my usual from <place>" then spells it out in the task's goal (with the app you order it
on), and Before I start says what it will order. All code, no model call."""

from __future__ import annotations

import asyncio
import typing
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_crossapp import Routines, SpyRunner
from test_phase5 import me
from test_phase6 import AppPhone, RoutePool, route_runner

import api.runner as runner_mod
from api.chat import chat
from api.preflight import check
from api.runner import APP_NAMES
from api.store import TaskStore
from memory.retrieval import Retriever
from memory.store import MemoryStore
from memory.usual import Usual, names_place, remember, resolve, said, with_usual
from models.schemas import EntityTypeName

AMAZON = APP_NAMES["amazon"]
APPS = ["amazon", "food runner"]


# ---- what you say ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("text, place, order, app", [
    ("My usual from Thai Basil is a pad see ew and a Thai iced tea.", "Thai Basil", "a pad see ew and a Thai iced tea", None),
    ("my usual from thai basil is a pad see ew and a thai iced tea", "thai basil", "a pad see ew and a thai iced tea", None),  # dictation
    ("Hey Envoy, remember that my usual at Pho 24 is a large pho tai!", "Pho 24", "a large pho tai", None),
    ("My usual order from Whole Foods is a dozen eggs and oat milk, on Amazon.", "Whole Foods", "a dozen eggs and oat milk", "Amazon"),
    ("hey envoy my usual from whole foods is a dozen eggs and oat milk on amazon", "whole foods", "a dozen eggs and oat milk", "amazon"),
    ("On Food Runner, my usual from Thai Basil is a pad see ew", "Thai Basil", "a pad see ew", "Food Runner"),
    ("My usual Food Runner order from Thai Basil is a pad see ew", "Thai Basil", "a pad see ew", "Food Runner"),
    ("My usual Thai Basil order is a pad see ew via the Food Runner app", "Thai Basil", "a pad see ew", "Food Runner"),
])
def test_a_stated_usual_is_read_typed_or_dictated(text, place, order, app):
    u = said(text, APPS)
    assert (u.place, u.order, u.app) == (place, order, app)


@pytest.mark.parametrize("text", [
    "Order my usual from Thai Basil", "Hey Envoy, I've had such a long day. Order me my usual from Thai Basil.",
    "What's my usual from Thai Basil?", "Is my usual from Thai Basil still a pad see ew?", "Every Friday at 6 PM, order my usual from Thai Basil",
    "My usual is late again", "Check me in for my flight",
])
def test_requests_and_questions_are_not_statements(text):
    assert said(text, APPS) is None


def test_a_place_that_is_an_app_stays_the_place():
    u = said("My usual from Amazon is paper towels", APPS)
    assert (u.place, u.order, u.app) == ("Amazon", "paper towels", None)


def test_the_extractor_can_never_write_a_usual():
    """Only you state one: extraction's schema doesn't offer the type, so no app screen, email or photo can."""
    assert "Usual" not in typing.get_args(EntityTypeName)


# ---- stored with you as its source, found when you ask for it -------------------------------------------------


def test_it_is_stored_as_your_fact_and_found_in_a_request():
    m = MemoryStore(":memory:")
    eid, known = remember(m, Usual("Thai Basil", "a pad see ew and a Thai iced tea", "Food Runner"), via="chat")
    assert not known and m.entity(eid)["type"] == "Usual" and m.entity(eid)["name"] == "Thai Basil"
    facts = {f["attribute"]: f for f in m.current_facts(eid)}
    assert {a: f["value"] for a, f in facts.items()} == {"place": "Thai Basil", "order": "a pad see ew and a Thai iced tea", "app": "Food Runner"}
    assert {f["author"] for f in facts.values()} == {"user"} and len({f["source"] for f in facts.values()}) == 1  # one statement, one source
    assert Retriever(m).where(facts["order"]["source"]) == "what you told me"
    for request in ("Order me my usual from Thai Basil.", "order me my usual from thai basil", "get the usual from THAI-BASIL"):
        u = resolve(m, request)
        assert (u.place, u.order, u.app, u.entity) == ("Thai Basil", "a pad see ew and a Thai iced tea", "Food Runner", eid), request


def test_saying_it_again_replaces_the_order_and_keeps_the_app_and_the_history():
    m = MemoryStore(":memory:")
    eid, _ = remember(m, Usual("Thai Basil", "a pad see ew", "Food Runner"))
    again, known = remember(m, Usual("thai basil", "a drunken noodle"), via="memory page")  # spelled another way: the same place
    assert again == eid and known and len(m.entities("Usual")) == 1
    assert {f["attribute"]: f["value"] for f in m.current_facts(eid)} == {"place": "Thai Basil", "order": "a drunken noodle", "app": "Food Runner"}
    assert [f["value"] for f in m.history(eid, "order")] == ["a pad see ew", "a drunken noodle"]
    assert Retriever(m).where(m.current(eid, "order")["source"]) == "your edit"


def test_a_request_needs_my_usual_and_a_place_you_have_one_from():
    m = MemoryStore(":memory:")
    remember(m, Usual("Blue Bottle", "a New Orleans iced coffee"))
    remember(m, Usual("Blue Bottle Coffee Oakland", "a cortado"))
    remember(m, Usual("Pho", "a pho tai"))
    assert resolve(m, "Order a New Orleans iced coffee from Blue Bottle") is None  # no "my usual"
    assert resolve(m, "Order my usual from Thai Basil") is None  # no usual from there
    assert resolve(m, "Order my usual from Blue Bottle").order == "a New Orleans iced coffee"
    assert resolve(m, "Order my usual from blue bottle coffee oakland").order == "a cortado"  # the longer name wins
    assert resolve(m, "Call my usual phone number") is None and names_place("pho-24 near me", "Pho") and not names_place("my phone", "Pho")


def test_the_goal_spells_out_the_order_once():
    u = Usual("Thai Basil", "a pad see ew", "Food Runner")
    assert with_usual("Order my usual from Thai Basil.", u, add_app=True) == "Order my usual from Thai Basil on Food Runner: a pad see ew"
    assert with_usual("Order my usual from Thai Basil", u) == "Order my usual from Thai Basil: a pad see ew"
    done = with_usual("Order my usual from Thai Basil", u, add_app=True)
    assert with_usual(done, u, add_app=True) == done


# ---- chat ------------------------------------------------------------------------------------------------


class NoModel:
    def call(self, *a, **k):
        raise AssertionError("no model call")


class Routed:
    def __init__(self) -> None:
        self.calls = 0

    def call(self, job, content, **kw):
        self.calls += 1
        from models.schemas import ChatRoute
        return SimpleNamespace(parsed=ChatRoute(kind="reply", goal="", reply="Noted."), cost_at_standard_usd=0.001)


def say(message, memory, adapter, runner=None, source="chat"):
    return asyncio.run(chat(message, adapter=adapter, memory=memory, runner=runner or SpyRunner(), routines=Routines(), source=source))


def test_telling_envoy_in_chat_stores_it_with_no_model_call():
    m = MemoryStore(":memory:")
    runner = SpyRunner()
    runner.app_names = lambda: APPS
    out = say("My usual from Whole Foods is a dozen eggs and oat milk, on Amazon.", m, NoModel(), runner)
    assert out["kind"] == "reply" and out["model_calls"] == 0 and runner.started == []
    assert out["reply"] == ('Got it: your usual from Whole Foods is a dozen eggs and oat milk, on Amazon. '
                            'Ask for "my usual from Whole Foods" any time.')
    assert out["spoken"] == "Got it: your usual from Whole Foods is a dozen eggs and oat milk, on Amazon."
    assert resolve(m, "order my usual from whole foods").app == "Amazon"
    out = say("my usual from whole foods is a dozen eggs", m, NoModel(), runner, source="voice")
    assert "It replaces the one I had." in out["reply"] and out["remembered"]["app"] == "Amazon"


def test_without_an_app_chat_asks_which_one():
    out = say("My usual from Thai Basil is a pad see ew", MemoryStore(":memory:"), NoModel())
    assert out["reply"].endswith('Which app do you order it on? Say it again with the app, like "… on <app>", and I\'ll order it there.')


def test_only_your_own_words_in_envoys_app_can_state_one():
    """Siri's token (and anything else that isn't chat or voice) takes chat's usual path; nothing is stored."""
    m, adapter = MemoryStore(":memory:"), Routed()
    out = say("My usual from Thai Basil is a pad see ew", m, adapter, source="siri")
    assert adapter.calls == 1 and out["reply"] == "Noted." and m.entities("Usual") == []


# ---- the task: goal, app, Before I start --------------------------------------------------------------------


class SeesGoal:
    goals: list[str] = []

    def __init__(self, device, **kw):
        pass

    async def run(self, goal, *, task_id, memory=""):
        SeesGoal.goals.append(goal)
        return SimpleNamespace(status="done", result="at checkout", model_calls=1, cost_at_standard_usd=0.001)


async def _finish(r, goal, **kw):
    r.loop = asyncio.get_running_loop()
    task = r.start(goal, "chat", **kw)
    await r.jobs[task["id"]]
    return task, r.store.get(task["id"]), r.store.steps(task["id"])


def test_order_my_usual_spells_it_out_runs_in_its_app_and_says_so_before_starting(monkeypatch):
    r = route_runner(monkeypatch, RoutePool(AppPhone({}, {AMAZON})))
    monkeypatch.setattr(runner_mod, "AgentRunner", SeesGoal)
    SeesGoal.goals = []
    remember(r.memory, Usual("Whole Foods", "a dozen eggs and oat milk", "Amazon"))
    said_ = "Hey Envoy, I've had such a long day. Order me my usual from Whole Foods."
    started, done, steps = asyncio.run(_finish(r, "Order my usual from Whole Foods", request=said_))
    goal = "Order my usual from Whole Foods on Amazon: a dozen eggs and oat milk"
    assert started["usual"] == {"place": "Whole Foods", "order": "a dozen eggs and oat milk", "app": "Amazon"}
    assert done["goal"] == goal and done["request"] == said_ and done["app"] == AMAZON and done["device"] == "envoy-real"
    assert SeesGoal.goals == [goal]
    lines = next(s["lines"] for s in steps if s["kind"] == "preflight")
    assert lines[0] == {"kind": "memory", "text": "Your usual from Whole Foods: a dozen eggs and oat milk, on Amazon.", "level": "info"}
    assert {"kind": "approval", "text": "Any payment will need your OK.", "level": "info"} in lines


def test_without_a_usual_the_goal_is_as_you_said_it(monkeypatch):
    r = route_runner(monkeypatch, RoutePool(AppPhone({}, {AMAZON})))
    task = r.store.create("x", "web")  # the store works; nothing about a usual is in memory
    assert r._usual("Order my usual from Whole Foods on Amazon", "Order my usual from Whole Foods on Amazon") is None
    started, done, _ = asyncio.run(_finish(r, "Order my usual from Whole Foods on Amazon"))
    assert "usual" not in started and done["goal"] == "Order my usual from Whole Foods on Amazon" and task


def test_chat_says_what_it_will_order(monkeypatch):
    r = route_runner(monkeypatch, RoutePool(AppPhone({}, {AMAZON})))
    monkeypatch.setattr(runner_mod, "AgentRunner", SeesGoal)
    remember(r.memory, Usual("Whole Foods", "a dozen eggs and oat milk", "Amazon"))
    from models.schemas import ChatRoute
    adapter = SimpleNamespace(call=lambda *a, **k: SimpleNamespace(parsed=ChatRoute(kind="task", goal="Order my usual from Whole Foods", reply=""),
                                                                    cost_at_standard_usd=0.001))

    async def scenario():
        r.loop = asyncio.get_running_loop()
        out = await chat("order me my usual from whole foods", adapter=adapter, memory=r.memory, runner=r, routines=Routines(), source="voice")
        await r.jobs[out["task"]["id"]]
        return out
    out = asyncio.run(scenario())
    assert out["reply"].startswith("On it: Order my usual from Whole Foods on Amazon: a dozen eggs and oat milk. You can follow it here")
    assert out["spoken"] == "On it: your usual from Whole Foods, a dozen eggs and oat milk."


def test_an_offers_card_shows_the_usual_too():
    m = MemoryStore(":memory:")
    remember(m, Usual("Thai Basil", "a pad see ew"))
    r = SimpleNamespace(store=TaskStore(":memory:"), pool=SimpleNamespace(phones={}), memory=m, routines=SimpleNamespace())
    lines = check(r, "Order my usual from Thai Basil")
    assert {"kind": "memory", "text": "Your usual from Thai Basil: a pad see ew.", "level": "info"} in lines


# ---- the Memory page -------------------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_BEARER_TOKEN", "mcp-test-token")  # as the other app tests: no .env needed
    monkeypatch.setenv("ENVOY_ALLOWED_HOSTS", "testserver")
    monkeypatch.setattr("api.app.API_DIR", tmp_path)
    from api.app import build, session_token
    from routines.store import RoutineStore
    memory = MemoryStore(":memory:")
    app, _ = build("demo", memory=memory, tasks=TaskStore(":memory:"), routines=RoutineStore(tmp_path / "routines"), adapter=SimpleNamespace())
    return app, memory, session_token()


def test_the_memory_page_adds_a_usual(client):
    app, memory, token = client
    with TestClient(app) as c:
        assert c.post("/api/memory/usual", json={"place": "Thai Basil", "order": "a pad see ew"}).status_code == 401
        assert c.post("/api/memory/usual", json={"place": "Thai Basil", "order": " "}, headers=me(token)).status_code == 400
        r = c.post("/api/memory/usual", json={"place": " Thai  Basil ", "order": "a pad see ew", "app": "Food Runner"}, headers=me(token))
        assert r.status_code == 200 and r.json()["replaced"] is False
        node = next(n for n in c.get("/api/memory/graph", headers=me(token)).json()["nodes"] if n["type"] == "Usual")
        assert node["name"] == "Thai Basil" and node["user_edited"]
        facts = c.get(f"/api/memory/entity/{node['id']}", headers=me(token)).json()["facts"]
        assert {f["attribute"]: f["sources"][0]["where"] for f in facts} == {"place": "your edit", "order": "your edit", "app": "your edit"}
    assert resolve(memory, "order my usual from thai basil").app == "Food Runner"


# ---- the order itself always waits for your OK -------------------------------------------------------------


def _checkout(*rows: tuple[str, str]) -> SimpleNamespace:
    els = [SimpleNamespace(label=t, text=t, desc="", resource_id="", kind=k, editable=False) for k, t in rows]
    return SimpleNamespace(numbered=els, text=" ".join(t for _, t in rows))


@pytest.mark.parametrize("rows, button", [
    ([("Text", "Your cart from Thai Basil"), ("Text", "Subtotal $20.40"), ("Button", "Place Order")], 3),  # the label alone
    ([("Text", "Checkout"), ("Text", "Order total $23.46"), ("Button", "Schedule Order")], 3),  # a closed store's: the screen
])
def test_placing_the_usual_always_waits_for_your_ok(rows, button):
    """However the usual was asked for (your own words, a routine set to never ask), the order's last button asks: risk.py
    calls it irreversible whatever the model said, and approval_rules never skips a step that involves money."""
    from devices.types import Action
    from policy.approval_rules import ApprovalRules, decide
    from policy.risk import classify
    screen = _checkout(*rows)
    assert classify(Action(kind="tap", element=button), screen, "reversible").irreversible
    standing = ApprovalRules(default="unless_requested", routines={"food_order_meal": "never"})
    for source in ("voice", "chat"):
        assert decide(standing, goal="hey envoy order me my usual from thai basil", source=source, app="com.example.food",
                      routine="food_order_meal", origin="routine_step", target=rows[button - 1][1], screen_text=screen.text) is None
