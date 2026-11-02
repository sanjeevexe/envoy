"""A key per AI agent (phone-layer plan, contract 2): Settings › Agents makes keys with tool groups, the MCP check names
the agent for each call, tools/list and tools/call follow its groups, run calls are limited per agent, and a task an
agent starts says which one. Muse's key (MCP_BEARER_TOKEN) keeps every tool."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from api.agents import AgentGuard
from api.auth import TOOL_GROUPS, Agent, allowed, group_of
from test_mcp_link import make, me

BASE = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json", "MCP-Protocol-Version": "2025-11-25"}
MUSE = {**BASE, "Authorization": "Bearer mcp-test-token"}
EVERY_TOOL = {"run_task", "get_task", "list_routines", "run_routine", "memory_search", "memory_get", "memory_note",
              "send_to_phone", "phone_updates", "create_trigger", "list_phones", "get_file"}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    e = make(tmp_path, monkeypatch)
    e.started = []

    def start(goal, source, **kw):  # a task as the runner makes it, without running anything
        e.started.append(goal)
        return e.ctx.tasks.create(goal, source)

    monkeypatch.setattr(e.ctx.runner, "start", start)
    monkeypatch.setattr("mcp_server.server.preflight_check", None)
    return e


def key(key: str) -> dict:
    return {**BASE, "Authorization": f"Bearer {key}"}


def new_agent(c: TestClient, env, name: str, tools: list[str] | None = None) -> tuple[dict, str]:
    r = c.post("/api/agents", json={"name": name, **({"tools": tools} if tools is not None else {})}, headers=me(env.token))
    assert r.status_code == 200, r.text
    return r.json()["agent"], r.json()["key"]


def tools(c: TestClient, hdr: dict) -> set[str]:
    r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}, headers=hdr)
    assert r.status_code == 200, r.text
    return {t["name"] for t in r.json()["result"]["tools"]}


def call(c: TestClient, hdr: dict, tool: str, **args) -> tuple[bool, str]:
    """(isError, the text) of a tool call."""
    r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": args}}, headers=hdr)
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    return bool(res.get("isError")), res["content"][0]["text"]


# ---- the brief's four checks ------------------------------------------------------------------------------------


def test_a_read_only_key_cant_see_or_call_run_task(env):
    with TestClient(env.ctx.asgi) as c:
        agent, k = new_agent(c, env, "Claude", ["read"])
        assert agent["tools"] == ["read"] and agent["name"] == "Claude"
        assert tools(c, key(k)) == set(TOOL_GROUPS["read"])
        err, text = call(c, key(k), "run_task", goal="check me in for my flight")
        assert err and 'run_task: it is in Envoy\'s "run" tool group' in text and "Settings › Agents" in text
        err, text = call(c, key(k), "memory_note", text="the user likes aisle seats")
        assert err and '"memory" tool group' in text
        err, text = call(c, key(k), "get_task", task_id="task-nope")
        assert not err and json.loads(text) == {"error": "no task task-nope"}  # its own tools work
        err, text = call(c, key(k), "no_such_tool")
        assert err and "run" not in text  # an unknown tool is the MCP server's own answer, not a grant to ask for
    assert env.started == []


def test_revoking_one_key_leaves_muse_and_the_other_agents_working(env):
    with TestClient(env.ctx.asgi) as c:
        claude, k1 = new_agent(c, env, "Claude")
        _, k2 = new_agent(c, env, "Meta agent")
        assert c.delete(f"/api/agents/{claude['id']}", headers=me(env.token)).json() == {"revoked": claude["id"]}
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        assert c.post("/mcp", json=body, headers=key(k1)).status_code == 401
        assert tools(c, key(k2)) == TOOL_GROUPS["read"] | {"run_task", "run_routine"}  # read and run, the default
        assert tools(c, MUSE) == EVERY_TOOL
        assert not call(c, MUSE, "run_task", goal="check me in for my flight")[0]
        assert [a["name"] for a in c.get("/api/agents", headers=me(env.token)).json()["agents"]] == ["Meta agent"]
        assert c.delete(f"/api/agents/{claude['id']}", headers=me(env.token)).status_code == 404


def test_a_task_started_with_a_key_says_which_agent_started_it(env):
    with TestClient(env.ctx.asgi) as c:
        _, k = new_agent(c, env, "Claude", ["read", "run", "triggers"])
        mine = json.loads(call(c, key(k), "run_task", goal="check me in for my flight")[1])
        muses = json.loads(call(c, MUSE, "run_task", goal="what's my gate")[1])
        web = env.ctx.tasks.create("order my usual", "web")
        assert env.ctx.tasks.get(mine["task_id"])["agent"] == "Claude"
        assert env.ctx.tasks.get(muses["task_id"])["agent"] == "Muse"
        assert env.ctx.tasks.get(web["id"])["agent"] is None
        listed = {t["id"]: t.get("agent") for t in c.get("/api/state", headers=me(env.token)).json()["tasks"]}
        assert listed[mine["task_id"]] == "Claude" and listed[muses["task_id"]] == "Muse"
        out = json.loads(call(c, key(k), "create_trigger", kind="time", name="Gate check", spec={"daily_at": "08:00"},
                              action={"goal": "check my gate"})[1])
        offer = env.ctx.offers.get(out["offer_id"])
        assert offer["title"].startswith("Claude wants to set this up: every day at 08:00") and "by Claude." in offer["body"]


def test_no_key_value_reaches_a_log(env, caplog, capsys):
    caplog.set_level("DEBUG")
    with TestClient(env.ctx.asgi) as c:
        agent, k = new_agent(c, env, "Claude", ["read"])
        rotated = c.post(f"/api/agents/{agent['id']}/rotate", headers=me(env.token)).json()["key"]
        guard = next(m for m in env.ctx.mcp.middleware if isinstance(m, AgentGuard))
        guard.per_minute = 1
        assert c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}, headers=key(k)).status_code == 401
        tools(c, key(rotated))
        call(c, key(rotated), "run_task", goal="check me in")  # refused: not its group
        call(c, MUSE, "run_task", goal="check me in")
        call(c, MUSE, "run_task", goal="check me in")  # refused: the limit
        c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}, headers=key("envoy_agent_not-a-key"))
    logged = [f.read_text(errors="replace") for f in env.tmp.rglob("*") if f.is_file() and f.suffix in (".jsonl", ".log", ".txt")]
    out = capsys.readouterr()
    everything = "\n".join([*logged, caplog.text, out.out, out.err])
    assert logged and "Claude" in everything  # the log names the agent...
    for secret in (k, rotated, "mcp-test-token"):
        assert secret not in everything  # ...never its key
    lines = [json.loads(x) for x in (env.tmp / "mcp.jsonl").read_text().splitlines()]
    assert {x.get("caller") for x in lines if x["auth"] == "ok"} == {"Claude", "Muse"}
    assert all(x["headers"].get("authorization") == "<redacted>" for x in lines)


def test_a_learned_routines_own_tool_is_in_the_run_group(env):
    """agent-door publishes a tool per shared routine (contract 1). No group names it, so it is a run tool: a read-only key
    neither sees nor calls it, a key with run does, and it counts against the run limit."""
    def skylark_check_in(trip_city: str) -> dict:
        """Check in for the trip to trip_city."""
        return {"task_id": env.ctx.runner.start(f"check in for {trip_city}", "mcp")["id"]}

    env.ctx.mcp.add_tool(skylark_check_in)
    with TestClient(env.ctx.asgi) as c:
        _, reader = new_agent(c, env, "Reader", ["read"])
        _, runner = new_agent(c, env, "Runner", ["run"])
        assert "skylark_check_in" not in tools(c, key(reader)) and "skylark_check_in" in tools(c, key(runner))
        err, text = call(c, key(reader), "skylark_check_in", trip_city="Chicago")
        assert err and '"run" tool group' in text
        out = json.loads(call(c, key(runner), "skylark_check_in", trip_city="Chicago")[1])
        assert env.ctx.tasks.get(out["task_id"])["agent"] == "Runner"
        guard = next(m for m in env.ctx.mcp.middleware if isinstance(m, AgentGuard))
        assert len(guard.runs["Runner"]) == 1
    assert env.started == ["check in for Chicago"]


def test_the_guard_covers_tools_a_server_subclass_merges_in_itself():
    """agent-door's server (contract 1) doesn't register routine tools: its own list_tools() and call_tool() merge them
    in on every call. The guard works on the MCP messages around those two, so it filters and refuses them unchanged."""
    from mcp.server.mcpserver import MCPServer
    from mcp_types import CallToolResult, TextContent, Tool

    from api.agents import guard
    from mcp_server.server import mcp_app

    class Merging(MCPServer):
        async def list_tools(self):
            return [*await super().list_tools(), Tool(name="skylark_check_in", input_schema={"type": "object", "properties": {}})]

        async def call_tool(self, name, arguments, context=None):
            if name == "skylark_check_in":
                return CallToolResult(content=[TextContent(type="text", text="started")])
            return await super().call_tool(name, arguments, context)

    server = Merging(name="t")
    server.add_tool(lambda: {"ok": True}, name="get_task")
    guard(server)
    inner = mcp_app(server, 8799, extra_hosts=set())
    who: list[Agent] = []

    async def app(scope, receive, send):  # what the bearer check does: the agent rides in the request scope
        await inner({**scope, "envoy.caller": who[-1]} if scope["type"] == "http" else scope, receive, send)

    with TestClient(app, base_url="http://127.0.0.1:8799") as c:
        who.append(Agent("Reader", frozenset({"read"})))
        assert tools(c, BASE) == {"get_task"}
        err, text = call(c, BASE, "skylark_check_in")
        assert err and '"run" tool group' in text
        who.append(Agent("Runner", frozenset({"read", "run"})))
        assert tools(c, BASE) == {"get_task", "skylark_check_in"}
        assert call(c, BASE, "skylark_check_in") == (False, "started")


# ---- the rate limit -----------------------------------------------------------------------------------------------


def test_run_calls_are_limited_per_agent_with_an_answer_that_says_when(env):
    now = [1000.0]
    with TestClient(env.ctx.asgi) as c:
        _, k = new_agent(c, env, "Claude")
        guard = next(m for m in env.ctx.mcp.middleware if isinstance(m, AgentGuard))
        guard.per_minute, guard.clock = 3, lambda: now[0]
        for i in range(3):
            assert not call(c, key(k), "run_task", goal=f"task {i}")[0]
            now[0] += 10
        err, text = call(c, key(k), "run_routine", name="skylark_check_in")
        assert err and "at most 3 run calls a minute from Claude" in text and "Nothing was started" in text
        assert "Try run_routine again in 30 s" in text  # the first of the three leaves the window then
        assert not call(c, key(k), "list_routines")[0]  # reading isn't limited
        assert not call(c, MUSE, "run_task", goal="Muse's own")[0]  # each agent has its own count
        now[0] += 31
        assert not call(c, key(k), "run_task", goal="task 3")[0]
    assert env.started == ["task 0", "task 1", "task 2", "Muse's own", "task 3"]


# ---- the keys themselves -----------------------------------------------------------------------------------------


def test_an_agent_key_opens_mcp_and_nothing_else(env):
    with TestClient(env.ctx.asgi) as c:
        _, k = new_agent(c, env, "Claude", list(TOOL_GROUPS))
        assert c.get("/api/state", headers={"Authorization": f"Bearer {k}"}).status_code == 401  # not a session
        assert c.get("/api/agents", headers={"Authorization": f"Bearer {k}"}).status_code == 401
        assert c.post("/api/photos", headers={"Authorization": f"Bearer {k}"}).status_code in (401, 403)  # not a Shortcut's token
        assert c.get("/mcp/outbox", headers={"Authorization": f"Bearer {k}"}).status_code == 401  # the door takes Muse's key only
        assert env.ctx.auth.check(k) is None
        assert c.get("/api/paired", headers=me(env.token)).json()["devices"] == []  # not a paired device either
        assert tools(c, key(k)) == EVERY_TOOL  # every group: every tool, and still no approve tool


def test_rotating_a_key_and_changing_its_groups(env):
    with TestClient(env.ctx.asgi) as c:
        agent, old = new_agent(c, env, "Claude", ["read"])
        r = c.post(f"/api/agents/{agent['id']}/rotate", headers=me(env.token)).json()
        new = r["key"]
        assert new != old and new.startswith("envoy_agent_") and r["agent"]["id"] == agent["id"]
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        assert c.post("/mcp", json=body, headers=key(old)).status_code == 401
        assert "create_trigger" not in tools(c, key(new))
        assert c.post(f"/api/agents/{agent['id']}", json={"tools": ["read", "triggers"]}, headers=me(env.token)).json()["tools"] == ["read", "triggers"]
        assert "create_trigger" in tools(c, key(new))  # the next call follows the change
        seen = c.get("/api/agents", headers=me(env.token)).json()
        assert seen["agents"][0]["last_seen"] and "key" not in json.dumps(seen["agents"])
        assert seen["muse"]["name"] == "Muse" and seen["muse"]["key"] is True and seen["default"] == ["read", "run"]
        assert [g["id"] for g in seen["groups"]] == ["read", "run", "memory", "files", "triggers"] and seen["can_manage"] is True


def test_only_the_mac_makes_or_widens_keys_but_any_session_can_revoke_one(env):
    phone = env.ctx.auth.issue("session", "iPhone")
    with TestClient(env.ctx.asgi) as c:
        agent, _ = new_agent(c, env, "Claude", ["read"])
        assert c.get("/api/agents", headers=me(phone)).json()["can_manage"] is False
        assert c.post("/api/agents", json={"name": "Other"}, headers=me(phone)).status_code == 403
        assert c.post(f"/api/agents/{agent['id']}/rotate", headers=me(phone)).status_code == 403
        assert c.post(f"/api/agents/{agent['id']}", json={"tools": ["run"]}, headers=me(phone)).status_code == 403
        assert c.delete(f"/api/agents/{agent['id']}", headers=me(phone)).status_code == 200
        assert c.get("/api/agents").status_code == 401


def test_agent_names_and_groups_are_checked(env):
    with TestClient(env.ctx.asgi) as c:
        new_agent(c, env, "Claude")
        post = lambda body: c.post("/api/agents", json=body, headers=me(env.token)).status_code  # noqa: E731
        assert post({"name": "claude"}) == 409 and post({"name": "Muse"}) == 409  # one key per agent; Muse's is in .env
        assert post({"name": ""}) == 400 and post({"name": "x" * 41}) == 400 and post({"name": "<script>"}) == 400
        assert post({"name": "Gemini", "tools": ["admin"]}) == 400 and post({"name": "Gemini", "tools": []}) == 400
        assert post({"name": "Gemini", "tools": "read"}) == 400
        assert post({"name": "  Meta   agent "}) == 200
        assert [a["name"] for a in c.get("/api/agents", headers=me(env.token)).json()["agents"]] == ["Claude", "Meta agent"]


def test_the_public_address_rules_hold_for_agent_keys(env, monkeypatch):
    monkeypatch.setenv("MCP_PERMANENT_URL", "https://envoy-mac.example.ts.net:10000/mcp")
    funnel = {"Host": "envoy-mac.example.ts.net:10000", "Tailscale-Funnel-Request": "?1"}
    with TestClient(env.ctx.asgi) as c:
        _, k = new_agent(c, env, "Claude")
        r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}, headers={**key(k), **funnel})
        assert r.status_code == 200 and "run_task" in {t["name"] for t in r.json()["result"]["tools"]}
        assert c.get("/api/agents", headers={**funnel, **me(env.token)}).status_code == 421  # Settings isn't on the public address
        assert c.get("/api/state", headers={**funnel, "Authorization": f"Bearer {k}"}).status_code == 421


# ---- the rules ---------------------------------------------------------------------------------------------------


def test_groups_and_allowed():
    assert group_of("run_task") == "run" and group_of("phone_updates") == "read" and group_of("get_file") == "files"
    assert group_of("skylark_check_in") == "run"  # a learned routine's own tool starts a task, like run_routine
    muse, reader = Agent("Muse"), Agent("Claude", frozenset({"read"}))
    assert all(allowed(muse, t) for t in EVERY_TOOL | {"skylark_check_in"})
    assert allowed(reader, "get_task") and not allowed(reader, "run_task") and not allowed(reader, "skylark_check_in")
    assert allowed(Agent("Claude", frozenset({"read", "run_task"})), "run_task")  # a single tool by name
    assert not allowed(None, "get_task")


# ---- scripts/agent_key.py ----------------------------------------------------------------------------------------


def agent_key_script():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("agent_key", Path(__file__).resolve().parents[2] / "scripts" / "agent_key.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_script_puts_a_key_in_a_file_and_never_prints_it_while_the_api_runs(tmp_path, monkeypatch, capsys):
    """The coordinator makes meta-agent's key on the live API with scripts/agent_key.py: it must not stop the API's running
    tasks (TaskStore's start-up would), and the key must reach only the file."""
    from api.store import TaskStore
    db = tmp_path / "api" / "envoy.db"
    env = make(tmp_path, monkeypatch, tasks=TaskStore(db))
    running = env.ctx.tasks.create("order my usual", "web")
    env.ctx.tasks.update(running["id"], status="running")
    script = agent_key_script()
    out = tmp_path / "keys" / "meta.key"
    with TestClient(env.ctx.asgi) as c:
        assert script.main(["--db", str(db), "issue", "Meta agent", "--tools", "read,run,files,triggers", "--out", str(out)]) == 0
        k = out.read_text().strip()
        assert k.startswith("envoy_agent_") and out.stat().st_mode & 0o777 == 0o600
        assert {"send_to_phone", "create_trigger", "run_task"} <= tools(c, key(k)) and "memory_note" not in tools(c, key(k))
        assert script.main(["--db", str(db), "list"]) == 0
        assert script.main(["--db", str(db), "rotate", "meta AGENT", "--out", str(out)]) == 0
        k2 = out.read_text().strip()
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        assert k2 != k and c.post("/mcp", json=body, headers=key(k)).status_code == 401 and "run_task" in tools(c, key(k2))
        assert [a["name"] for a in c.get("/api/agents", headers=me(env.token)).json()["agents"]] == ["Meta agent"]  # Settings sees it
        assert script.main(["--db", str(db), "revoke", "Meta agent"]) == 0
        assert c.post("/mcp", json=body, headers=key(k2)).status_code == 401
        assert tools(c, MUSE) == EVERY_TOOL
    printed = capsys.readouterr()
    assert k not in printed.out + printed.err and k2 not in printed.out + printed.err
    assert "Made a key for Meta agent (files, read, run, triggers). It is in" in printed.out and str(out) in printed.out
    assert "Meta agent: files, read, run, triggers · key made" in printed.out and "Revoked Meta agent's key" in printed.out
    assert env.ctx.tasks.get(running["id"])["status"] == "running"  # the API's running task carries on


def test_the_script_refuses_a_key_file_git_would_commit_and_bad_input(tmp_path, monkeypatch):
    from pathlib import Path

    from api.store import TaskStore
    db = tmp_path / "envoy.db"
    TaskStore(db).db.close()
    script = agent_key_script()
    repo = Path(script.REPO)
    tracked = repo / "backend" / "meta-agent.key"
    with pytest.raises(SystemExit, match="isn't gitignored"):
        script.main(["--db", str(db), "issue", "Meta agent", "--out", str(tracked)])
    assert not tracked.exists()
    assert script.main(["--db", str(db), "issue", "Meta agent", "--out", str(tmp_path / "k")]) == 0  # read and run, the default
    with pytest.raises(SystemExit, match="already an agent called Meta agent"):
        script.main(["--db", str(db), "issue", "meta agent", "--out", str(tmp_path / "k2")])
    with pytest.raises(SystemExit, match="tool groups"):
        script.main(["--db", str(db), "issue", "Other", "--tools", "read,admin", "--out", str(tmp_path / "k3")])
    with pytest.raises(SystemExit, match="No agent called Nobody"):
        script.main(["--db", str(db), "revoke", "Nobody"])
    with pytest.raises(SystemExit, match="No Envoy database"):
        script.main(["--db", str(tmp_path / "missing.db"), "list"])
    assert not (tmp_path / "missing.db").exists() and not (tmp_path / "k2").exists() and not (tmp_path / "k3").exists()
    monkeypatch.setattr(script, "API_DIR", tmp_path / "api-dir")  # the default file: next to the API's database, gitignored
    assert script.key_file("Meta agent", None) == (tmp_path / "api-dir" / "agent_keys" / "meta-agent.key").resolve()
    assert script.key_file("Meta agent", str(repo / "data" / "api" / "agent_keys" / "x.key")).name == "x.key"


def test_settings_lists_exactly_the_tools_each_agent_sees(env):
    """Settings › Agents shows each agent's tools as tools/list gives them to its key: its groups, and the routines shared
    with agents while it has run (contract 1)."""
    import shutil
    from pathlib import Path
    shutil.copytree(Path(__file__).resolve().parents[2] / "data" / "routines" / "skylark_get_flight_gate",
                    env.ctx.routines.root / "skylark_get_flight_gate")
    with TestClient(env.ctx.asgi) as c:
        _, reader = new_agent(c, env, "Reader", ["read"])
        _, runner = new_agent(c, env, "Runner", ["read", "run"])
        env.ctx.sharing.set("skylark_get_flight_gate", True)
        seen = c.get("/api/agents", headers=me(env.token)).json()
        sees = {a["name"]: a["sees"] for a in seen["agents"]}
        assert seen["learned"] == ["skylark_get_flight_gate"]
        assert set(sees["Reader"]) == tools(c, key(reader)) == set(TOOL_GROUPS["read"])
        assert set(sees["Runner"]) == tools(c, key(runner)) and sees["Runner"][0] == "skylark_get_flight_gate"  # learned first
        assert set(seen["muse"]["sees"]) == tools(c, MUSE) == EVERY_TOOL | {"skylark_get_flight_gate"}
        env.ctx.sharing.set("skylark_get_flight_gate", False)
        assert "skylark_get_flight_gate" not in c.get("/api/agents", headers=me(env.token)).json()["muse"]["sees"]
