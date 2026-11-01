"""The page's server: it answers only its own host names, takes posts only from its own page, runs one turn at a time,
and its recording is the whole session's events."""

from __future__ import annotations

import time

from starlette.testclient import TestClient

from fakes import SECRET, FakeEnvoy, FakeModel, call, say, view
from meta_agent.agent import Agent, CostLog
from meta_agent.web import Hub, Session, build_app

BASE = "http://127.0.0.1:8790"


def client(tmp_path, script, views=None):
    envoy = FakeEnvoy(task_views=views or [view("done", result="Delayed 25 min")])
    envoy._key = SECRET
    model = FakeModel(script)
    hub = Hub()
    session = Session(hub, lambda emit: Agent(envoy, model, emit, costs=CostLog(tmp_path / "c.jsonl"), poll_s=0),
                      {"agent": "Spark agent", "model": "muse-spark-1.3", "effort": "low", "suggestions": ["hi"]})
    return TestClient(build_app(session, 8790), base_url=BASE), session, envoy


def wait_idle(session, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if any(e["kind"] == "idle" for e in session.hub.events):
            return
        time.sleep(0.02)
    raise AssertionError("the turn didn't finish")


def test_the_page_and_a_turn_end_to_end(tmp_path):
    script = [[call("run_routine", {"name": "skylark_check_flight_status", "inputs": {"flight_number": "SL 1190"}}, 1)],
              [call("wait_for_task", {"task_id": "t1"}, 2)], [say("SL 1190 is delayed 25 minutes.")]]
    c, session, envoy = client(tmp_path, script)
    with c:
        page = c.get("/")
        assert page.status_code == 200 and "Every call to Envoy" in page.text
        assert c.get("/static/style.css").status_code == 200 and c.get("/static/fonts/manrope-latin-wght-normal.woff2").status_code == 200
        assert c.post("/api/chat", json={"text": "status of SL 1190?"}, headers={"Origin": BASE}).status_code == 202
        wait_idle(session)
        rec = c.get("/api/recording").json()
    kinds = [e["kind"] for e in rec["events"]]
    assert kinds[:2] == ["config", "hello"] and "reply" in kinds
    assert [e["data"]["tool"] for e in rec["events"] if e["kind"] == "call_start"] == ["tools/list", "tools/list", "run_routine", "get_task"]
    assert SECRET not in str(rec)


def test_only_its_own_host_and_page_get_in(tmp_path):
    c, session, envoy = client(tmp_path, [[say("hi")]])
    with c:
        assert c.get("/", headers={"Host": "evil.example:8790"}).status_code == 403  # a rebound name
        assert c.post("/api/chat", json={"text": "hi"}, headers={"Origin": "https://evil.example"}).status_code == 403
        assert c.post("/api/chat", json={"text": ""}).status_code == 400
        assert c.post("/api/reset", headers={"Origin": "https://evil.example"}).status_code == 403
    assert envoy.calls == []


def test_one_turn_at_a_time(tmp_path):
    script = [[call("wait_for_task", {"task_id": "t1", "timeout_s": 30}, 1)], [say("done")]]
    c, session, envoy = client(tmp_path, script, views=[view("running")])
    session.agent.poll_s = 0.05
    with c:
        assert c.post("/api/chat", json={"text": "wait"}).status_code == 202
        time.sleep(0.2)
        assert c.post("/api/chat", json={"text": "again"}).status_code == 409
        assert c.post("/api/stop").status_code == 200
        wait_idle(session)
    assert [e["kind"] for e in session.hub.events if e["kind"] in ("stopped", "idle")] == ["stopped", "idle"]
