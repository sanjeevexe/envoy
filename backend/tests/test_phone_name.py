"""A real phone's name (Settings › Phones), and a routine switched off.

The demo films the Pixel 5 as "Envoy's phone": the offer, its "Before I start" lines and the task's notes say the name
the user gave the phone, word for word, instead of "your Pixel 5". Unnamed phones read as before. A routine switched off
(its first take is the agent's) leaves an offer that names it to the agent instead of failing the task.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from types import SimpleNamespace

import pytest

from api.devices import DevicePool, phone_ref
from api.handoff import HANDOFF_TEMPLATES, Handoff
from api.preflight import check
from api.store import TaskStore
from memory.store import MemoryStore
from routines.store import LIBRARY, RoutineStore
from test_handoff import MP4, PIXEL, Clock, FakeAdb, pool, settle, with_offers
from test_preflight import make_runner

PID = "phone-0A1B"
NAMED = {PID: {**PIXEL[PID], "name": "Envoy's phone"}}
IG = HANDOFF_TEMPLATES["instagram"]


def test_a_phone_is_called_by_its_name_word_for_word_else_by_its_model():
    assert phone_ref(NAMED[PID]) == phone_ref(NAMED[PID], "their") == "Envoy's phone"
    assert phone_ref(PIXEL[PID]) == "your Pixel 5" and phone_ref(PIXEL[PID], "the") == "the Pixel 5"
    assert phone_ref({**PIXEL[PID], "name": "  "}) == "your Pixel 5" and phone_ref(None) == "your Android phone"


def offer_for(phones: dict, tmp_path) -> dict:
    store = TaskStore(":memory:")
    store.set_setting("handoff", {"outbox": str(tmp_path / "outbox")})
    hand = SimpleNamespace(store=store, adb=FakeAdb(), clock=Clock(), box=tmp_path / "outbox")
    hand.h = Handoff(store, pool(phones), SimpleNamespace(publish=lambda t, **d: None), adb=hand.adb, clock=hand.clock)
    env = with_offers(hand)
    env.h.scan()
    (env.box / "pier.mp4").write_bytes(MP4)
    (env.box / "pier.json").write_text(json.dumps({"app": "Instagram", "caption": "Golden hour at the pier."}))
    [item] = settle(env)
    return env.offers.get(env.h.item(item["id"])["offer_id"])


def test_the_offer_names_the_phone_as_the_user_named_it(tmp_path):
    assert offer_for(NAMED, tmp_path / "a")["title"] == "Put pier.mp4 on Envoy's phone and post it to Instagram?"
    assert offer_for(PIXEL, tmp_path / "b")["title"] == "Put pier.mp4 on your Pixel 5 and post it to Instagram?"


def test_before_i_start_names_the_phone_too():
    lines = check(make_runner(None, NAMED[PID]), 'Post the newest video in my phone\'s gallery to Instagram as a reel with this caption: "x"',
                  request=IG["request"], source="web", app=IG["package"], phone=PID, phone_ok=PID)
    assert {"kind": "device", "text": "I'll use Envoy's phone (you said yes).", "level": "info"} in lines
    target = check(make_runner(None, NAMED[PID]), "check the price of AirPods at Target")
    assert {"kind": "device", "text": "Target blocks emulators: I'll ask to use Envoy's phone.", "level": "warn"} in target
    assert not any("Pixel" in ln["text"] for ln in lines + target)


def test_the_pool_gives_discovered_phones_their_names(monkeypatch):
    monkeypatch.setattr("api.devices.discover", lambda: [dict(PIXEL[PID])])
    monkeypatch.setattr(DevicePool, "running", lambda self: {})
    p = DevicePool(SimpleNamespace(publish=lambda *a, **k: None))
    p.refresh_phones()
    assert "name" not in p.phones[PID] and next(r for r in p.status() if r["avd"] == PID)["name"] == "Pixel 5"
    p.names = lambda: {PID: "Envoy's phone"}
    p.refresh_phones()
    row = next(r for r in p.status() if r["avd"] == PID)
    assert p.phones[PID]["name"] == row["name"] == "Envoy's phone" and row["model"] == "Pixel 5"


def test_settings_phones_sets_and_clears_a_name(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("MCP_BEARER_TOKEN", "mcp-test-token")
    monkeypatch.setenv("ENVOY_ALLOWED_HOSTS", "testserver")
    monkeypatch.setattr("api.app.API_DIR", tmp_path)
    monkeypatch.setattr("api.push.LOG", tmp_path / "push.jsonl")
    monkeypatch.setattr("api.app.LOGS", tmp_path)
    monkeypatch.setattr("api.devices.discover", lambda: [dict(PIXEL[PID])])
    monkeypatch.setattr(DevicePool, "running", lambda self: {})
    from api.app import build, session_token
    tasks = TaskStore(":memory:")
    app, ctx = build("demo", memory=MemoryStore(":memory:"), tasks=tasks, routines=RoutineStore(tmp_path / "routines"),
                     adapter=SimpleNamespace(api_key="k", calls=[]))
    me = {"Authorization": f"Bearer {session_token()}"}
    with TestClient(ctx.asgi) as c:
        ctx.pool.refresh_phones()
        got = c.post("/api/settings/phones/name", json={"id": PID, "name": " Envoy's phone‮ "}, headers=me).json()
        assert got["name"] == "Envoy's phone" and tasks.setting("phone_names") == {PID: "Envoy's phone"}
        assert ctx.pool.phones[PID]["name"] == "Envoy's phone"  # at once, before the next discovery
        [phone] = c.get("/api/settings/phones", headers=me).json()["phones"]
        assert (phone["name"], phone["model"]) == ("Envoy's phone", "Pixel 5")
        assert c.post("/api/settings/phones/name", json={"id": PID, "name": ""}, headers=me).json()["names"] == {}
        assert "name" not in ctx.pool.phones[PID] and phone_ref(ctx.pool.phones[PID]) == "your Pixel 5"
        assert c.post("/api/settings/phones/name", json={"id": "envoy-test", "name": "x"}, headers=me).status_code == 400
        assert c.post("/api/settings/phones/name", json={"id": PID, "name": "x"},
                      headers={"Authorization": "Bearer mcp-test-token"}).status_code == 401


def test_muse_hears_the_phones_name_in_phone_updates():
    from mcp_server.server import _handoff_text
    h = Handoff(TaskStore(":memory:"), pool(NAMED), SimpleNamespace(publish=lambda *a, **k: None))
    row = {"name": "pier.mp4", "device": PID, "status": "posted", "remote_path": None, "error": None}
    assert _handoff_text(SimpleNamespace(handoff=h), row) == '"pier.mp4" was posted from Envoy\'s phone'
    assert _handoff_text(SimpleNamespace(handoff=h), {**row, "status": "offered"}) == 'Envoy asked the user whether to put "pier.mp4" on Envoy\'s phone'
    plain = Handoff(TaskStore(":memory:"), pool(PIXEL), SimpleNamespace(publish=lambda *a, **k: None))
    assert _handoff_text(SimpleNamespace(handoff=plain), row) == '"pier.mp4" was posted from the Pixel 5'
    assert _handoff_text(SimpleNamespace(handoff=plain), {**row, "status": "waiting"}).endswith("before it goes to their Pixel 5")


# ---- a routine switched off ------------------------------------------------------------------------


@pytest.fixture
def lib(tmp_path) -> RoutineStore:
    shutil.copytree(LIBRARY / "instagram_post_reel", tmp_path / "routines" / "instagram_post_reel")
    store = RoutineStore(tmp_path / "routines")
    store.switch("instagram_post_reel", on=True)  # the live library has it switched off since Nov 1
    return store


def test_a_routine_switched_off_keeps_its_versions_and_comes_back_on(lib):
    v = lib.index("instagram_post_reel")["active"]
    assert lib.switch("instagram_post_reel", on=False) is None
    assert "instagram_post_reel" not in [r.routine for r in lib.active()]
    with pytest.raises(KeyError):
        lib.get("instagram_post_reel")
    assert lib.get("instagram_post_reel", v).version == v and lib.index("instagram_post_reel")["off"]["version"] == v
    assert lib.switch("instagram_post_reel", on=False) is None  # already off: stays off, remembers the version
    assert lib.switch("instagram_post_reel", on=True) == v and "off" not in lib.index("instagram_post_reel")
    assert lib.switch("instagram_post_reel", on=True) == v
    with pytest.raises(KeyError):
        lib.switch("no_such_routine", on=False)


def test_an_offer_naming_a_switched_off_routine_runs_the_agent(lib):
    lib.switch("instagram_post_reel", on=False)
    r = make_runner(lib, NAMED[PID])
    t = r.store.create("post it", "web")
    routine, inputs, app, sources, calls = asyncio.run(r._plan(t["id"], "post it", "instagram_post_reel", {"caption": "x"}, IG["package"]))
    assert routine is None and inputs == {"caption": "x"} and app == IG["package"] and calls == 0
    assert any(s.get("text") == "routine instagram_post_reel isn't active: the agent does it instead" for s in r.store.steps(t["id"]))
    lib.switch("instagram_post_reel", on=True)
    routine, *_ = asyncio.run(r._plan(t["id"], "post it", "instagram_post_reel", {"caption": "x"}, IG["package"]))
    assert routine is not None and routine.routine == "instagram_post_reel"
