"""The "Share with agents" switch (phone-layer plan, contract 1): off by default, the user's session only, kept in the
API's database, and Settings › Agents reads exactly the tools agents see."""

from __future__ import annotations

import shutil

from fastapi.testclient import TestClient

from api.sharing import Sharing
from api.store import TaskStore
from test_mcp_link import HDR, me
from test_routine_tools import SKYLARK_LIB, env, listed  # noqa: F401 - env is a fixture

X = {"X-Envoy": "1"}


def test_off_by_default_and_kept_across_a_restart(tmp_path):
    db = tmp_path / "envoy.db"
    s = Sharing(TaskStore(db))
    assert not s.shared("skylark_check_in_flight") and s.names() == set()
    assert s.set("skylark_check_in_flight", True) is True
    s.set("skylark_get_flight_gate", True)
    s.set("skylark_get_flight_gate", False)
    again = Sharing(TaskStore(db))
    assert again.shared("skylark_check_in_flight") and again.names() == {"skylark_check_in_flight"}


def test_only_the_users_session_reads_or_flips_the_switch(env):
    with TestClient(env.ctx.asgi) as c:
        assert c.get("/api/routines/sharing").status_code == 401
        assert c.get("/api/routines/sharing", headers={"Authorization": HDR["Authorization"]}).status_code == 401  # the MCP key
        assert c.post("/api/routines/skylark_check_in_flight/share", json={"on": True}, headers={**HDR, **X}).status_code == 401
        c.cookies.set("envoy_session", env.token)
        assert c.post("/api/routines/skylark_check_in_flight/share", json={"on": True}).status_code == 403  # no X-Envoy
    assert env.ctx.sharing.names() == set()


def test_flipping_it_adds_the_tool_and_settings_shows_what_agents_see(env):
    with TestClient(env.ctx.asgi) as c:
        h = {**me(env.token), **X}
        first = c.get("/api/routines/sharing", headers=h).json()
        assert first["shared"] == [] and first["tools"] == []
        assert {b["name"] for b in first["builtin"]} >= {"run_task", "run_routine", "list_phones"}
        assert next(b for b in first["builtin"] if b["name"] == "run_task")["title"] == "Run a task on the user's phone"
        before = set(listed(c))
        r = c.post("/api/routines/skylark_check_in_flight/share", json={"on": True}, headers=h).json()
        assert r["routine"] == "skylark_check_in_flight" and r["on"] is True and r["tool"] == "skylark_check_in_flight"
        after = listed(c)
        assert set(after) == before | {"skylark_check_in_flight"}
        row, = r["tools"]
        assert {k: row[k] for k in ("routine", "tool", "app", "app_name", "version", "learned")} == {
            "routine": "skylark_check_in_flight", "tool": "skylark_check_in_flight", "app": "com.skylark.air", "app_name": "SkyLark",
            "version": 1, "learned": "Oct 27, 2026"}
        assert row["inputs"] == [{"name": "trip_city", "type": "text", "required": True, "description": "Destination city of the flight to check in for"}]
        assert row["description"] == after["skylark_check_in_flight"]["description"] and row["irreversible"] is True
        assert c.get("/api/routines/sharing", headers=h).json()["shared"] == ["skylark_check_in_flight"]
        off = c.post("/api/routines/skylark_check_in_flight/share", json={"on": False}, headers=h).json()
        assert off["on"] is False and off["shared"] == [] and off["tool"] is None and off["tools"] == []
        assert set(listed(c)) == before


def test_a_shared_routine_switched_off_stays_shared_but_isnt_a_tool(env):
    with TestClient(env.ctx.asgi) as c:
        h = {**me(env.token), **X}
        c.post("/api/routines/skylark_get_flight_gate/share", json={"on": True}, headers=h)
        env.ctx.routines.switch("skylark_get_flight_gate", False)
        got = c.get("/api/routines/sharing", headers=h).json()
        assert got["shared"] == ["skylark_get_flight_gate"] and got["tools"] == []
        env.ctx.routines.switch("skylark_get_flight_gate", True)
        assert [t["tool"] for t in c.get("/api/routines/sharing", headers=h).json()["tools"]] == ["skylark_get_flight_gate"]


def test_unknown_routines_and_bad_bodies_are_refused(env):
    with TestClient(env.ctx.asgi) as c:
        h = {**me(env.token), **X}
        assert c.post("/api/routines/no_such_routine/share", json={"on": True}, headers=h).status_code == 404
        assert c.post("/api/routines/..%2F..%2Fapi/share", json={"on": True}, headers=h).status_code in (404, 405)  # never the route
        assert c.post("/api/routines/skylark_get_flight_gate/share", json={"on": "yes"}, headers=h).status_code == 400
        assert c.post("/api/routines/skylark_get_flight_gate/share", json={}, headers=h).status_code == 400
        # A routine's own page still works, and "sharing" isn't taken for a routine's name.
        assert c.get("/api/routines/skylark_get_flight_gate", headers=h).status_code == 200
    assert env.ctx.sharing.names() == set()


def test_a_routine_named_like_a_built_in_tool_gets_a_prefixed_tool(env):
    shutil.copytree(SKYLARK_LIB / "skylark_get_flight_gate", env.ctx.routines.root / "list_phones")
    for f in ("index.json", "v1.yaml"):
        p = env.ctx.routines.root / "list_phones" / f
        p.write_text(p.read_text().replace("skylark_get_flight_gate", "list_phones"))
    with TestClient(env.ctx.asgi) as c:
        h = {**me(env.token), **X}
        r = c.post("/api/routines/list_phones/share", json={"on": True}, headers=h).json()
        assert r["tool"] == "routine_list_phones"
        tools = listed(c)
    assert "routine_list_phones" in tools and tools["list_phones"]["annotations"]["title"] == "List the phones Envoy can use"  # the built-in is untouched
