"""Learned routines as MCP tools (phone-layer plan, T1a and contract 1): a shared routine with an active version is a tool
of its own, by name and with typed inputs, and the tool list follows the library and the share switch with no restart."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.sharing import tool_name, tool_names
from routines.model import InputSpec, Routine, Step, StepAction
from test_mcp_link import HDR, make

LIB = Path(__file__).resolve().parents[2] / "data" / "routines"
BUILTIN = {"run_task", "get_task", "list_routines", "run_routine", "memory_search", "memory_get", "memory_note", "send_to_phone",
           "phone_updates", "create_trigger", "list_phones"}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    e = make(tmp_path, monkeypatch)
    for name in ("skylark_check_in_flight", "skylark_get_flight_gate", "skylark_add_known_traveler_number"):
        shutil.copytree(LIB / name, e.ctx.routines.root / name)
    e.started = []

    def start(goal, source, **kw):
        e.started.append((goal, source, kw))
        return {"id": f"task-{len(e.started)}", "status": "queued"}
    e.ctx.runner.start = start
    return e


def listed(c: TestClient) -> dict[str, dict]:
    r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}, headers=HDR)
    assert r.status_code == 200, r.text
    return {t["name"]: t for t in r.json()["result"]["tools"]}


def called(c: TestClient, tool: str, args: dict) -> tuple[bool, str]:
    r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": tool, "arguments": args}}, headers=HDR)
    assert r.status_code == 200, r.text
    res = r.json().get("result") or {}
    return bool(res.get("isError")), (res.get("content") or [{}])[0].get("text", json.dumps(r.json().get("error")))


def calendar_routine(**changes) -> Routine:
    r = Routine(routine="calendar_add_event", app="com.google.android.calendar", intent="Add an event to the calendar.",
                inputs={"event_date": InputSpec(type="date", description="The day of the event"),
                        "kind": InputSpec(type="choice", description="Which calendar", choices=["Work", "Home"]),
                        "from": InputSpec(description="Who it's from", from_memory="user.name")},
                outputs=["event_title"], steps=[Step(id="open", intent="Open Calendar", risk="read",
                                                     action=StepAction(kind="launch", package="com.google.android.calendar"))])
    return r.model_copy(update=changes)


def test_a_routine_is_a_tool_only_while_shared_and_the_list_follows_without_a_restart(env):
    with TestClient(env.ctx.asgi) as c:
        assert set(listed(c)) == BUILTIN  # off by default: nothing extra
        env.ctx.sharing.set("skylark_check_in_flight", True)
        tools = listed(c)
        assert set(tools) == BUILTIN | {"skylark_check_in_flight"}
        env.ctx.sharing.set("skylark_get_flight_gate", True)
        assert "skylark_get_flight_gate" in listed(c)
        env.ctx.sharing.set("skylark_check_in_flight", False)
        assert set(listed(c)) == BUILTIN | {"skylark_get_flight_gate"}
        err, text = called(c, "skylark_check_in_flight", {"trip_city": "Chicago"})
        assert err and "Unknown tool" in text and env.started == []  # unshared: no longer callable


def test_the_tool_has_the_routines_inputs_intent_app_outputs_and_how_it_runs(env):
    env.ctx.sharing.set("skylark_check_in_flight", True)
    env.ctx.sharing.set("skylark_add_known_traveler_number", True)
    with TestClient(env.ctx.asgi) as c:
        tools = listed(c)
    t = tools["skylark_check_in_flight"]
    assert t["inputSchema"] == {"type": "object", "properties": {"trip_city": {"type": "string", "description": "Destination city of the flight to check in for"}},
                                "required": ["trip_city"]}
    d = t["description"]
    assert d.startswith("Check in for a SkyLark flight. App: SkyLark (com.skylark.air), on a phone Envoy operates.")
    assert "Outputs: seat, gate, boarding time, boarding group, flight (in get_task's result once it's done)." in d
    assert ("Learned by Envoy from a run on Oct 27, 2026; replays without model calls while the app looks as it did; anything "
            "irreversible waits for the user's OK on their phone.") in d
    assert t["title"] == "Check in for a SkyLark flight"
    assert t["annotations"]["readOnlyHint"] is False and t["annotations"]["destructiveHint"] is False
    assert t["_meta"] == {"envoy/routine": "skylark_check_in_flight", "envoy/version": 1, "envoy/app": "com.skylark.air"}
    ktn = tools["skylark_add_known_traveler_number"]["inputSchema"]
    assert ktn["required"] == ["trip_city"]  # memory can fill the number
    assert ktn["properties"]["user_known_traveler_number"]["description"] == (
        "Known traveler number to add to the trip. Envoy fills it from memory (user.known_traveler_number) if left out")


def test_a_call_goes_where_run_routine_goes_and_returns_the_same_shape(env):
    env.ctx.sharing.set("skylark_check_in_flight", True)
    with TestClient(env.ctx.asgi) as c:
        err, text = called(c, "skylark_check_in_flight", {"trip_city": "Chicago"})
        assert not err
        err2, text2 = called(c, "run_routine", {"name": "skylark_check_in_flight", "inputs": {"trip_city": "Chicago"}})
    by_tool, by_name = json.loads(text), json.loads(text2)
    assert set(by_tool) == set(by_name) and by_tool["task_id"] == "task-1" and by_name["task_id"] == "task-2"
    assert by_tool["task_url"] == "https://envoy-mac.example.ts.net:8443/?task=task-1"
    assert env.started[0] == env.started[1] == ("Check in for a SkyLark flight", "mcp", {"routine": "skylark_check_in_flight",
                                                                                         "inputs": {"trip_city": "Chicago"}})


def test_inputs_are_checked_before_anything_starts(env):
    env.ctx.routines.add(calendar_routine())
    env.ctx.sharing.set("calendar_add_event", True)
    with TestClient(env.ctx.asgi) as c:
        schema = listed(c)["calendar_add_event"]["inputSchema"]
        assert schema["properties"]["event_date"] == {"type": "string", "format": "date", "description": "The day of the event (a date, YYYY-MM-DD)"}
        assert schema["properties"]["kind"]["enum"] == ["Work", "Home"]
        assert schema["required"] == ["event_date", "kind"]  # "from" comes from memory
        assert called(c, "calendar_add_event", {"event_date": "2026-11-05"})[0]  # kind is missing
        assert called(c, "calendar_add_event", {"event_date": "2026-11-05", "kind": "Gym"})[0]  # not one of the choices
        assert env.started == []
        err, _ = called(c, "calendar_add_event", {"event_date": "2026-11-05", "kind": "Home", "from": "  "})
        assert not err
        err, _ = called(c, "calendar_add_event", {"event_date": 20261105, "kind": "Work", "from": "Ada"})  # a number is its digits
        assert not err
    assert env.started[0][2]["inputs"] == {"event_date": "2026-11-05", "kind": "Home"}  # a blank input is left to memory
    assert env.started[1][2]["inputs"] == {"event_date": "20261105", "kind": "Work", "from": "Ada"}


def test_switching_relearning_and_retiring_show_on_the_next_list(env):
    store = env.ctx.routines
    store.add(calendar_routine())
    env.ctx.sharing.set("calendar_add_event", True)
    with TestClient(env.ctx.asgi) as c:
        assert listed(c)["calendar_add_event"]["_meta"]["envoy/version"] == 1
        store.switch("calendar_add_event", False)
        assert "calendar_add_event" not in listed(c)
        store.switch("calendar_add_event", True)
        assert "calendar_add_event" in listed(c)
        store.add(calendar_routine(intent="Add an event to a calendar", outputs=[]))  # learned again: v2 replaces v1
        t = listed(c)["calendar_add_event"]
        assert t["_meta"]["envoy/version"] == 2 and t["title"] == "Add an event to a calendar" and "Outputs" not in t["description"]
        shutil.move(store.root / "calendar_add_event", env.tmp / "Trash-calendar_add_event")  # gone from the library
        assert "calendar_add_event" not in listed(c)


def test_a_taught_routine_says_it_was_learned_from_the_user(env):
    env.ctx.routines.add(calendar_routine(compiled_from={"source": "taught", "task_id": "teach-1"}))
    env.ctx.sharing.set("calendar_add_event", True)
    with TestClient(env.ctx.asgi) as c:
        assert "Learned by Envoy from the user doing it once on " in listed(c)["calendar_add_event"]["description"]


def test_list_routines_names_the_tool_of_a_shared_routine(env):
    env.ctx.sharing.set("skylark_get_flight_gate", True)
    from test_mcp_link import call
    with TestClient(env.ctx.asgi) as c:
        out = {r["name"]: r for r in call(c, "list_routines")["routines"]}
    assert out["skylark_get_flight_gate"]["tool"] == "skylark_get_flight_gate"
    assert "tool" not in out["skylark_check_in_flight"]


def test_a_tool_is_built_once_per_active_version(env, monkeypatch):
    env.ctx.sharing.set("skylark_check_in_flight", True)
    reads = []
    real = env.ctx.routines.get
    monkeypatch.setattr(env.ctx.routines, "get", lambda name, version=None: reads.append(name) or real(name, version))
    with TestClient(env.ctx.asgi) as c:
        for _ in range(3):
            listed(c)
    assert reads == ["skylark_check_in_flight"]


# ---- tool names ------------------------------------------------------------------------------------


def test_tool_names_are_the_routines_own_when_they_can_be():
    assert tool_name("skylark_check_in_flight", BUILTIN) == "skylark_check_in_flight"
    for showcase in ("instagram_reel_song", "tiktok_post_sound", "youtube_short_sound", "instagram_story_poll"):
        assert tool_name(showcase, BUILTIN) == showcase
    assert tool_name("run_task", BUILTIN) == "routine_run_task"  # a built-in tool's name
    assert tool_name("Instagram Reel (v2)!", BUILTIN) == "routine_instagram_reel_v2"
    assert tool_name("2fa_code", BUILTIN) == "routine_2fa_code"
    assert tool_name("x" * 64, BUILTIN) == "x" * 64
    assert tool_name("x" * 80, BUILTIN) == ("routine_" + "x" * 80)[:64]  # too long for its own name: at most 64 characters


def test_two_routines_never_share_a_tool_name():
    names = tool_names(["Check-In", "check_in", "routine_check_in"], BUILTIN)
    assert names == {"Check-In": "routine_check_in", "check_in": "check_in", "routine_check_in": "routine_check_in_2"}
    assert len(set(names.values())) == 3
