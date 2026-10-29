"""Offline tests for "Ask Envoy" from Siri (api/siri.py): the `siri` token reaches /api/siri and nothing else; Siri's
requests get the non-direct source `siri`, so a step the request names still asks; the one `say` line (plain, short,
with the right Before I start line); recurring jobs drafted switched off; the per-token caps; every error still says
something; and the Shortcut's actions (scripts/make_shortcut.py)."""

from __future__ import annotations

import importlib.util
import json
import logging
import re
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api.siri as siri
from api.events import EventBus
from api.store import TaskStore
from memory.store import MemoryStore
from models.adapter import CostMeter
from policy.approval_rules import ApprovalRules, decide
from test_approval_rules import CONFIRM
from test_crossapp import FakeAdapter
from test_phase5 import me
from test_preflight import CHECK_IN, lib, make_runner, texts  # noqa: F401 - lib is a fixture
from test_recurring import Recorded, chat_route, draft

ASK = "/api/siri"


def make_env(tmp_path, monkeypatch, adapter=None):
    monkeypatch.setenv("MCP_BEARER_TOKEN", "mcp-test-token")
    monkeypatch.setenv("ENVOY_PUBLIC_URL", "https://envoy-mac.example.ts.net:8443")
    monkeypatch.setenv("ENVOY_ALLOWED_HOSTS", "testserver")
    monkeypatch.setattr("api.app.API_DIR", tmp_path)
    monkeypatch.setattr("api.push.LOG", tmp_path / "push.jsonl")
    monkeypatch.setattr("api.app.LOGS", tmp_path)
    from api.app import build, session_token
    from routines.store import RoutineStore
    adapter = adapter or SimpleNamespace(api_key="meta-test-key", meter=CostMeter(tmp_path / "costs.jsonl", daily_cap_usd=5), calls=[])
    app, ctx = build("demo", memory=MemoryStore(":memory:"), tasks=TaskStore(":memory:"), routines=RoutineStore(tmp_path / "routines"), adapter=adapter)
    events: list = []
    ctx.bus.listeners.append(events.append)
    return SimpleNamespace(app=app, ctx=ctx, token=session_token(), events=events, tmp=tmp_path)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    return make_env(tmp_path, monkeypatch)


def siri_token(env) -> str:
    return env.ctx.auth.issue("siri", "Ask Envoy (Siri)")


def stub_chat(monkeypatch, out=None, seen=None):
    """chat() replaced: records each message and returns `out` (a dict, or a function of the message)."""
    async def fake(message, **kw):
        if seen is not None:
            seen.append((message, kw["source"]))
        got = out(message) if callable(out) else out
        if isinstance(got, Exception):
            raise got
        return got or {"kind": "reply", "reply": "Hi.", "spoken": "Hi."}
    monkeypatch.setattr("api.siri.chat", fake)


# ---- the token: it asks, and does nothing else ----------------------------------------------------------


def test_a_session_issues_the_siri_token_and_the_token_asks(env, monkeypatch):
    stub_chat(monkeypatch, {"kind": "memory", "reply": "Your gate is B12.", "spoken": "Your gate is B12.", "from_memory": True})
    with TestClient(env.ctx.asgi) as c:
        got = c.post("/api/siri/token", headers=me(env.token)).json()
        assert got["scope"] == "siri" and got["ask_url"] == "https://envoy-mac.example.ts.net:8443/api/siri"
        [dev] = [d for d in c.get("/api/paired", headers=me(env.token)).json()["devices"] if d["scope"] == "siri"]
        assert dev["name"] == "Ask Envoy (Siri)"
        r = c.post(ASK, json={"message": "What gate is my flight?"}, headers=me(got["token"]))
        assert r.status_code == 200 and r.json() == {"say": "Your gate is B12.", "kind": "memory"}
        assert c.post(ASK, json={"message": "What gate is my flight?"}, headers=me(env.token)).json()["say"] == "Your gate is B12."  # your session
        assert c.post("/api/siri/token", headers=me(got["token"])).status_code == 401  # it can't make more tokens
        assert c.delete(f"/api/paired/{dev['id']}", headers=me(env.token)).json()["revoked"]
        r = c.post(ASK, json={"message": "What gate is my flight?"}, headers=me(got["token"]))
        assert r.status_code == 401 and r.json()["say"]  # revoked: refused, and still something to say
    [ev] = [e for e in env.events if e["type"] == "chat"][:1]
    assert ev["source"] == "siri" and ev["message"] == "What gate is my flight?"


PUBLIC = {"/login", "/api/pair", "/healthz", ASK}  # pairing needs a code from the Mac; /api/siri is the token's one route


def all_routes(routes):
    """Every route, including the ones in included routers (FastAPI wraps those)."""
    for r in routes:
        inner = getattr(r, "original_router", None)
        yield from all_routes(inner.routes) if inner is not None else [r]


def test_the_siri_token_reaches_no_other_route(env):
    tok = siri_token(env)
    routes = [(m, r.path) for r in all_routes(env.app.routes) if getattr(r, "methods", None) and r.path.startswith("/api") and r.path not in PUBLIC
              for m in sorted(r.methods - {"HEAD", "OPTIONS"})]
    assert len(routes) > 50
    named = {("POST", "/api/chat"), ("GET", "/api/approvals"), ("POST", "/api/approvals/{aid}"), ("POST", "/api/offers/{oid}"),
             ("GET", "/api/state"), ("POST", "/api/tasks"), ("POST", "/api/tokens"), ("POST", "/api/photos"), ("POST", "/api/codes/test"),
             ("POST", "/api/siri/token"), ("GET", "/api/memory/graph")}
    assert named <= set(routes)
    with TestClient(env.ctx.asgi) as c:
        for method, path in routes:
            url = re.sub(r"\{[^}]+\}", "x", path)
            r = c.request(method, url, json={}, headers=me(tok))
            assert r.status_code in (401, 403), (method, path, r.status_code)
        for path in ("/api/events", "/api/live/envoy-test", "/api/voice"):
            with pytest.raises(Exception):
                with c.websocket_connect(path, headers=me(tok)) as ws:
                    ws.receive_json()
        assert c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=me(tok)).status_code == 401


def test_a_session_can_ask_and_a_page_elsewhere_cant(env, monkeypatch):
    stub_chat(monkeypatch)
    with TestClient(env.ctx.asgi) as c:
        c.cookies.set("envoy_session", env.token)
        r = c.post(ASK, json={"message": "hi"})  # a browser POST without X-Envoy (another site making your browser ask)
        assert r.status_code == 403 and r.json()["say"]
        assert c.post(ASK, json={"message": "hi"}, headers={"X-Envoy": "1"}).json()["say"] == "Hi."


# ---- the source: Siri's requests aren't your own words for approvals -------------------------------------


def test_a_siri_task_gets_the_siri_source_and_your_words_as_its_request(env, monkeypatch):
    started = []

    def start(goal, source, **kw):
        started.append((goal, source, kw))
        return env.ctx.tasks.create(goal, source, request=kw.get("request") or goal)
    monkeypatch.setattr(env.ctx.runner, "start", start)
    env.ctx.adapter = FakeAdapter({"chat": chat_route})
    monkeypatch.setattr(siri, "PREFLIGHT_WAIT_S", 0.05)
    with TestClient(env.ctx.asgi) as c:
        out = c.post(ASK, json={"message": "Check me in for my flight"}, headers=me(siri_token(env))).json()
    [(goal, source, kw)] = started
    assert source == "siri" and kw["request"] == "Check me in for my flight"
    task = env.ctx.tasks.get(out["task_id"])
    assert task["source"] == "siri" and out["kind"] == "task"
    assert out["say"] == "On it: Check me in for my flight. Anything that can't be undone will wait for your OK."


def test_the_step_the_request_names_asks_for_siri_and_not_for_chat():
    base = dict(goal="Check me in for my flight", app="com.skylark.air", routine="skylark_check_in_flight", origin="routine_step",
                target="Confirm check-in", screen_text=CONFIRM, inputs={"trip_city": "Chicago"})
    rules = ApprovalRules()
    assert decide(rules, source="siri", **base) is None  # asks
    assert decide(rules, source="chat", **base).by == "your request"  # typed in Envoy: you asked for it
    for source in ("siri", "chat"):  # money always asks
        assert decide(rules, source=source, **{**base, "screen_text": CONFIRM + "\nTotal due $35.00"}) is None
    standing = ApprovalRules(routines={"skylark_check_in_flight": "never"})
    assert decide(standing, source="siri", **base).by == "standing approval"  # a routine you set to run without asking, as for every source


def test_the_approver_waits_for_you_on_a_siri_task():
    from api.approvals import WebApprover
    from policy.approvals import ApprovalRequest
    from test_api import FakeDevice, background_loop

    store = TaskStore(":memory:")
    bus = SimpleNamespace(publish=lambda t, **kw: None)
    got = {}
    for source in ("siri", "chat"):
        task = store.create("Check me in for my flight", source, request="Check me in for my flight", routine="skylark_check_in_flight")
        approver = WebApprover(store, bus, background_loop(), task["id"], phone=FakeDevice, on_wait=lambda _: None, timeout_s=1)
        req = ApprovalRequest(task["id"], "check in", "com.skylark.air", 'tap "Confirm check-in"', ["rule"], CONFIRM, origin="routine_step",
                              target="Confirm check-in")
        t = threading.Thread(target=lambda a=approver, r=req, s=source: got.update({s: a.request(r)}))
        t.start()
        t.join(3)
    assert not got["siri"].approved and got["siri"].by == "timeout"  # nobody said yes: nothing happens
    assert got["chat"].approved and got["chat"].by == "your request"


def test_before_i_start_says_the_named_step_will_wait_for_siri(lib):  # noqa: F811
    r = make_runner(lib)
    line = lambda source: texts(siri.preflight_check(r, "Check me in for my flight", routine=CHECK_IN, source=source), "approval")  # noqa: E731
    assert line("siri") == ["Confirming check-in will wait for your OK."]
    assert line("chat") == ["Confirming check-in will go ahead: you asked for it."]
    assert texts(siri.preflight_check(r, "Check me in for my flight", source="siri"), "approval") == [
        "Anything that can't be undone will wait for your OK."]  # no routine yet: the general line


# ---- what Siri says ----------------------------------------------------------------------------------------


def task_out(env, goal, spoken, **kw):
    """chat's result for a task, with the task really in the store."""
    def make(message):
        t = env.ctx.tasks.create(goal, "siri", request=message)
        return {"kind": "task", "reply": f"On it: {goal}. You can follow it here.", "spoken": spoken, "task": t, **kw}
    return make


def add_preflight_later(env, lines, after_s=0.2):
    """The runner's own `preflight` step, a moment after chat returns (it comes once the routine is picked)."""
    def later():
        time.sleep(after_s)
        for t in env.ctx.tasks.list(5):
            env.ctx.tasks.add_step(t["id"], {"kind": "preflight", "text": "before I start", "lines": lines})
    threading.Thread(target=later, daemon=True).start()


def ask(env, message, token=None):
    with TestClient(env.ctx.asgi) as c:
        r = c.post(ASK, json={"message": message}, headers=me(token or siri_token(env)))
    return r.status_code, r.json()


ROUTINE = {"kind": "routine", "text": "Using routine skylark_check_in_flight v1: usually 9 s, no model calls.", "level": "info"}
CHECKIN_WAITS = {"kind": "approval", "text": "Confirming check-in will wait for your OK.", "level": "info"}


def test_a_fresh_memory_answer_is_said_as_is(env, monkeypatch):
    stub_chat(monkeypatch, {"kind": "memory", "reply": "Your gate is B12.", "spoken": "Your gate is B12.", "from_memory": True})
    assert ask(env, "What gate is my flight?") == (200, {"say": "Your gate is B12.", "kind": "memory"})


def test_an_old_answer_without_a_phone_says_when_once(env, monkeypatch):
    ans = "Gate B12, from the SkyLark app yesterday at 5:50 PM, but it may have changed. (from yesterday 5:50 PM; no phone is free to check it now)"
    stub_chat(monkeypatch, {"kind": "memory", "reply": ans, "spoken": ans, "from_memory": True})
    assert ask(env, "What gate is my flight?")[1]["say"] == "Gate B12, from the SkyLark app yesterday at 5:50 PM, but it may have changed."


def test_a_stale_answer_that_became_a_task_says_so_without_waiting(env, monkeypatch):
    stub_chat(monkeypatch, task_out(env, "Get the gate of my flight", "That may have changed. I'm checking the app.", stale=True))
    monkeypatch.setattr(siri, "PREFLIGHT_WAIT_S", 5)
    t0 = time.monotonic()
    code, out = ask(env, "What gate is my flight?")
    assert time.monotonic() - t0 < 2  # two sentences already: no wait for the step
    assert code == 200 and out["say"] == "That may have changed. I'm checking the app." and out["kind"] == "task" and out["task_id"]


def test_a_task_says_its_own_preflight_line_when_it_comes_in_time(env, monkeypatch):
    stub_chat(monkeypatch, task_out(env, "check me in for my flight", "On it: check me in for my flight."))
    monkeypatch.setattr(siri, "PREFLIGHT_WAIT_S", 3)
    monkeypatch.setattr(siri, "preflight_check", lambda *a, **kw: pytest.fail("the task's own step came in time"))
    add_preflight_later(env, [ROUTINE, CHECKIN_WAITS], after_s=0.3)
    assert ask(env, "Check me in for my flight")[1]["say"] == "On it: check me in for my flight. Confirming check-in will wait for your OK."


def test_a_task_falls_back_to_the_general_line_when_the_step_is_late(env, monkeypatch):
    stub_chat(monkeypatch, task_out(env, "check me in for my flight", "On it: check me in for my flight."))
    monkeypatch.setattr(siri, "PREFLIGHT_WAIT_S", 0.2)
    calls = []

    def check(runner, goal, **kw):
        calls.append((goal, kw))
        return [{"kind": "approval", "text": "Anything that can't be undone will wait for your OK.", "level": "info"}]
    monkeypatch.setattr(siri, "preflight_check", check)
    assert ask(env, "Check me in for my flight")[1]["say"] == "On it: check me in for my flight. Anything that can't be undone will wait for your OK."
    [(goal, kw)] = calls
    assert goal == "check me in for my flight" and kw == {"request": "Check me in for my flight", "source": "siri"}


@pytest.mark.parametrize("goal,lines,said", [
    ("order my usual from DoorDash", [ROUTINE, {"kind": "approval", "text": "The payment step will need your OK.", "level": "info"}],
     "On it: order my usual from DoorDash. The payment step will need your OK."),
    ("check the price of AirPods Pro at Target", [{"kind": "device", "text": "Target blocks emulators: I'll ask to use your Pixel 5.", "level": "warn"}],
     "On it: check the price of AirPods Pro at Target. Target blocks emulators: I'll ask to use your Pixel 5."),
    ("check my Chase balance", [{"kind": "signin", "text": "Chase asked you to sign in on your Pixel 5 last time (Oct 24).", "level": "warn"},
                                {"kind": "blocked", "text": "Chase needs your Android phone, and it isn't connected.", "level": "stop"}],
     "On it: check my Chase balance. Chase needs your Android phone, and it isn't connected."),  # a stop line first
    ("check me in for my flight", [ROUTINE, {"kind": "approval", "text": "Confirming check-in will go ahead: you set this routine to run "
                                             "without asking.", "level": "info"}],
     "On it: check me in for my flight."),  # nothing worth saying
])
def test_which_line_a_task_says(env, monkeypatch, goal, lines, said):
    stub_chat(monkeypatch, task_out(env, goal, f"On it: {goal}."))
    add_preflight_later(env, lines, after_s=0.05)
    assert ask(env, goal)[1]["say"] == said


def test_a_stop_line_replaces_chats_second_sentence(env, monkeypatch):
    stub_chat(monkeypatch, task_out(env, "Get the gate of my flight", "That may have changed. I'm checking the app."))
    monkeypatch.setattr(siri, "preflight_check", lambda *a, **kw: [
        {"kind": "blocked", "text": "SkyLark needs envoy-test, and it isn't running.", "level": "stop"}])
    assert ask(env, "What gate is my flight?")[1]["say"] == "That may have changed. SkyLark needs envoy-test, and it isn't running."


def test_a_drafted_recurring_job_says_to_say_yes_in_envoy_and_a_rejected_one_says_why(env, monkeypatch):
    drafted = {"kind": "trigger_request", "reply": "I can do that…", "spoken": "I've drafted it. Say yes on the card to turn it on.",
               "offer": {"id": "offer-1"}, "trigger": {"id": "trig-1"}}
    rejected = {"kind": "trigger_request", "reply": "I couldn't tell exactly what to do each time. Try it like this: …",
                "spoken": "I couldn't tell exactly what to do each time.", "draft_rejected": "goal"}
    stub_chat(monkeypatch, lambda m: drafted if "6 PM" in m else rejected)
    tok = siri_token(env)
    with TestClient(env.ctx.asgi) as c:
        assert c.post(ASK, json={"message": "Every Friday at 6 PM, order my usual"}, headers=me(tok)).json() == {
            "say": "I've drafted it. Say yes in Envoy to turn it on.", "kind": "trigger_request"}
        assert c.post(ASK, json={"message": "Every Friday do the thing"}, headers=me(tok)).json()["say"] == \
            "I couldn't tell exactly what to do each time."


def test_say_is_plain_and_short():
    out = {"kind": "reply", "reply": "**Your gate** is [B12](https://envoy.example/tasks/task-1029-151818-0e2b) 🛫 (task-1029-151818-0e2b). "
                                     "It took a while. Then something else happened. And more after that, which goes on and on " + "and on " * 30}
    assert siri.say_for(out) == "Your gate is B12. It took a while."  # two sentences at most
    cut = siri.say_for({"kind": "reply", "reply": "It goes on and on " + "and on " * 40})
    assert len(cut) <= siri.SAY_MAX and cut.endswith("…") and cut[:-1].split()[-1] in ("and", "on")  # cut at a word
    long = siri.say_for({"kind": "reply", "spoken": "On it: " + "order a very long list of things " * 10 + "."},
                        {"kind": "approval", "text": "The payment step will need your OK.", "level": "info"})
    assert len(long) <= siri.SAY_MAX and long.endswith("… The payment step will need your OK.")
    assert siri.plain("Gate changed: B14 → B22, 72°F ✈️") == "Gate changed: B14 to B22, 72°F"
    assert siri.say_for({"kind": "task", "spoken": "On it: check me in. Confirming check-in will wait for your OK."}, CHECKIN_WAITS) == \
        "On it: check me in. Confirming check-in will wait for your OK."  # not said twice
    for text in ("", "   "):
        assert siri.say_for({"kind": "reply", "reply": text, "spoken": text})  # always something


# ---- recurring jobs through Siri ----------------------------------------------------------------------------


def test_a_recurring_job_from_siri_is_drafted_off_and_only_your_session_turns_it_on(tmp_path, monkeypatch):
    adapter = Recorded({"recurring": draft(days=["fri"], time_of_day="18:00", goal="Order my usual from Thai Basil"), "chat": chat_route})
    env = make_env(tmp_path, monkeypatch, adapter)
    tok = siri_token(env)
    with TestClient(env.ctx.asgi) as c:
        r = c.post(ASK, json={"message": "Every Friday at 6 PM, order my usual from Thai Basil"}, headers=me(tok))
        assert r.json() == {"say": "I've drafted it. Say yes in Envoy to turn it on.", "kind": "trigger_request"}
        [trig] = c.get("/api/triggers", headers=me(env.token)).json()
        assert not trig["enabled"] and trig["action"]["ask"] is True
        [offer] = c.get("/api/offers", headers=me(env.token)).json()
        assert offer["source"] == "siri" and offer["kind"] == "trigger_request" and offer["status"] == "pending"
        assert c.post(f"/api/offers/{offer['id']}", json={"decision": "accept"}, headers=me(tok)).status_code == 401  # Siri never turns it on
        assert c.post(f"/api/offers/{offer['id']}", json={"decision": "accept"}, headers=me(env.token)).json()["status"] == "accepted"
        assert c.get("/api/triggers", headers=me(env.token)).json()[0]["enabled"]
    assert adapter.jobs == ["recurring"] and env.ctx.tasks.list(5) == []  # one call; nothing started


# ---- limits ------------------------------------------------------------------------------------------------


def test_six_a_minute_and_a_hundred_a_day_per_token(env, monkeypatch):
    now = [1_000_000.0]
    monkeypatch.setattr(siri, "now", lambda: now[0])
    seen: list = []
    stub_chat(monkeypatch, seen=seen)
    a, b = siri_token(env), siri_token(env)
    with TestClient(env.ctx.asgi) as c:
        post = lambda tok: c.post(ASK, json={"message": "hi"}, headers=me(tok))  # noqa: E731
        assert [post(a).status_code for _ in range(6)] == [200] * 6
        r = post(a)
        assert r.status_code == 429 and r.json() == {"say": siri.SAY_TOO_MANY, "kind": "error"}
        assert post(b).status_code == 200  # each token counts on its own
        assert post(env.token).status_code == 200  # and so does your session
        now[0] += 61
        assert post(a).status_code == 200
        for _ in range(93):  # 7 so far; 100 in the day, a few seconds apart
            now[0] += 11
            assert post(a).status_code == 200
        now[0] += 11
        r = post(a)
        assert r.status_code == 429 and r.json()["say"] == siri.SAY_TOO_MANY_TODAY
        now[0] += 86400
        assert post(a).status_code == 200
    assert len(seen) == 103 and all(src == "siri" for _, src in seen)


def test_the_message_is_trimmed_and_capped(env, monkeypatch):
    seen: list = []
    stub_chat(monkeypatch, seen=seen)
    tok = siri_token(env)
    with TestClient(env.ctx.asgi) as c:
        assert c.post(ASK, json={"message": "  check   me\nin  "}, headers=me(tok)).status_code == 200
        assert c.post(ASK, json={"message": "x " * 1000}, headers=me(tok)).status_code == 200
        for bad in ({"message": "   "}, {"message": 42}, {}, ["hi"]):
            r = c.post(ASK, json=bad, headers=me(tok))
            assert r.status_code == 400 and r.json() == {"say": "I didn't catch that.", "kind": "error"}
        r = c.post(ASK, content=b"not json", headers={**me(tok), "content-type": "application/json"})
        assert r.status_code == 400 and r.json()["say"]
    assert seen[0][0] == "check me in" and len(seen[1][0]) <= siri.MESSAGE_MAX and len(seen) == 2


# ---- errors -------------------------------------------------------------------------------------------------


def test_a_model_failure_still_says_something_and_logs_no_words(env, monkeypatch, caplog):
    stub_chat(monkeypatch, RuntimeError("Meta API 402: billing for 'my secret plan'"))
    with caplog.at_level(logging.INFO, logger="api.siri"):
        code, out = ask(env, "my secret plan")
    assert code == 200 and out == {"say": "I couldn't do that just now. Try again in a minute.", "kind": "error"}
    assert "RuntimeError" in caplog.text and "secret" not in caplog.text


def test_every_error_carries_a_say(env, monkeypatch):
    stub_chat(monkeypatch)
    with TestClient(env.ctx.asgi) as c:
        for headers, code in (({}, 401), (me("not-a-token"), 401), (me(env.ctx.auth.issue("photos", "Send to Envoy")), 401)):
            r = c.post(ASK, json={"message": "hi"}, headers=headers)
            assert r.status_code == code and r.json()["say"] and "detail" not in r.json()


# ---- the Shortcut --------------------------------------------------------------------------------------------


def shortcut_builder():
    spec = importlib.util.spec_from_file_location("make_shortcut", siri.__file__.rsplit("/backend/", 1)[0] + "/scripts/make_shortcut.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_shortcut_listens_posts_and_says_the_answer():
    ms = shortcut_builder()
    flow = ms.siri_workflow("https://envoy-mac.example.ts.net:8443/api/siri", "TOKEN-123")
    acts = flow["WFWorkflowActions"]
    ids = [a["WFWorkflowActionIdentifier"].removeprefix("is.workflow.actions.") for a in acts]
    assert ids == ["conditional", "setvariable", "conditional", "dictatetext", "setvariable", "conditional", "downloadurl", "getvalueforkey",
                   "speaktext", "notification"]
    p = [a["WFWorkflowActionParameters"] for a in acts]
    assert [x.get("WFControlFlowMode") for x in p[:6:]] == [0, None, 1, None, None, 2] and p[0]["WFCondition"] == 100  # has any value
    assert p[0]["WFInput"]["Variable"]["Value"]["Type"] == "ExtensionInput"  # text it was given, else listen
    assert p[1]["WFVariableName"] == p[4]["WFVariableName"] == "Request"
    assert p[4]["WFInput"]["Value"]["OutputUUID"] == p[3]["UUID"]
    post = p[6]
    assert post["WFURL"].endswith("/api/siri") and post["WFHTTPMethod"] == "POST" and post["WFHTTPBodyType"] == "JSON"
    [field] = post["WFJSONValues"]["Value"]["WFDictionaryFieldValueItems"]
    assert field["WFKey"]["Value"]["string"] == "message" and field["WFValue"]["Value"]["attachmentsByRange"]["{0, 1}"]["VariableName"] == "Request"
    [header] = post["WFHTTPHeaders"]["Value"]["WFDictionaryFieldValueItems"]
    assert header["WFKey"]["Value"]["string"] == "Authorization" and header["WFValue"]["Value"]["string"] == "Bearer TOKEN-123"
    assert p[7]["WFDictionaryKey"] == "say" and p[7]["WFInput"]["Value"]["OutputUUID"] == post["UUID"]
    for x in (p[8]["WFText"], p[9]["WFNotificationActionBody"]):
        assert x["Value"]["attachmentsByRange"]["{0, 1}"]["OutputUUID"] == p[7]["UUID"]
    holding = [i for i, a in enumerate(acts) if "TOKEN-123" in json.dumps(a)]
    assert holding == [6] and json.dumps(post).count("TOKEN-123") == 1  # the token is in the header only
    assert "TOKEN-123" not in json.dumps({k: v for k, v in flow.items() if k != "WFWorkflowActions"})
    last = lambda reply: [a["WFWorkflowActionIdentifier"].removeprefix("is.workflow.actions.")  # noqa: E731
                          for a in ms.siri_workflow("https://x/api/siri", "t", reply)["WFWorkflowActions"][8:]]
    assert last("show") == ["showresult"] and last("speak+show") == ["speaktext", "showresult"] and last("output") == ["output"]
    with pytest.raises(ValueError):
        ms.siri_workflow("https://x/api/siri", "t", "shout")


def test_only_this_mac_is_allowed_without_https():
    ms = shortcut_builder()
    assert ms.local_only("http://127.0.0.1:8746/api/siri") and ms.local_only("http://localhost:8746/api/siri")
    for url in ("http://127.0.0.1.evil.example/api/siri", "http://192.168.1.4:8746/api/siri", "http://envoy-mac.example.ts.net/api/siri"):
        assert not ms.local_only(url)
