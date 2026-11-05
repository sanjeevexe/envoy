"""The client against Envoy's real MCP server, over HTTP: an Envoy built in process (as backend/tests/test_mcp_link.py
builds it, with in-memory stores and no phone) served by uvicorn on a free port. This test imports Envoy; the agent never does."""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from types import SimpleNamespace

import pytest

from meta_agent.agent import Agent, CostLog, approval_rule, function_tools
from meta_agent.mcp_client import EnvoyMCP, MCPError

KEY = "meta-agent-test-key"


@pytest.fixture()
def envoy(tmp_path, monkeypatch):
    uvicorn = pytest.importorskip("uvicorn")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    monkeypatch.setenv("MCP_BEARER_TOKEN", KEY)
    monkeypatch.setenv("ENVOY_ALLOWED_HOSTS", f"127.0.0.1:{port}")
    monkeypatch.setattr("api.app.API_DIR", tmp_path)
    monkeypatch.setattr("api.app.LOGS", tmp_path)
    from api.app import build
    from api.store import TaskStore
    from memory.store import MemoryStore
    from models.adapter import CostMeter
    from routines.store import RoutineStore

    adapter = SimpleNamespace(api_key="meta-test-key", meter=CostMeter(tmp_path / "costs.jsonl", daily_cap_usd=5), calls=[])
    _, ctx = build("demo", memory=MemoryStore(":memory:"), tasks=TaskStore(":memory:"), routines=RoutineStore(tmp_path / "routines"), adapter=adapter)
    ctx.pool.refresh_phones = lambda: []  # no adb in tests
    task = ctx.tasks.create("Check in for a SkyLark flight", "mcp")
    ctx.tasks.update(task["id"], status="waiting_approval")
    approval = ctx.tasks.add_approval(task["id"], "Confirm check-in for SL 482", ["irreversible"], "com.skylark.air", "", None)
    server = uvicorn.Server(uvicorn.Config(ctx.asgi, host="127.0.0.1", port=port, log_level="warning", lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started, "Envoy didn't start"
    yield SimpleNamespace(url=f"http://127.0.0.1:{port}/mcp", ctx=ctx, task=task, approval=approval)
    server.should_exit = True
    thread.join(timeout=10)


def test_the_client_speaks_to_envoys_mcp_server(envoy):
    async def go():
        mcp = EnvoyMCP(envoy.url, KEY)
        try:
            await mcp.connect()
            tools = await mcp.list_tools()
            routines = await mcp.call_tool("list_routines", {})
            task = await mcp.call_tool("get_task", {"task_id": envoy.task["id"]})
            approve = await mcp.call_tool("approve", {"approval_id": envoy.approval["id"]})
            return mcp, tools, routines, task, approve
        finally:
            await mcp.close()

    mcp, tools, routines, task, approve = asyncio.run(go())
    assert mcp.server_info["name"] == "envoy" and "only the user can, in Envoy" in mcp.instructions
    names = {t.name for t in tools}
    assert {"run_task", "get_task", "list_routines", "run_routine", "phone_updates"} <= names
    assert not any(w in n for n in names for w in ("approve", "accept", "decline"))
    defs, _ = function_tools(tools)  # every one of Envoy's schemas converts
    assert len(defs) == len(tools)  # the local wait helper stands in for Envoy's wait_for_task
    assert routines.data == {"routines": []} and not routines.is_error
    assert task.data["status"] == "waiting_approval"
    assert [a["approval_id"] for a in task.data["pending_approvals"]] == [envoy.approval["id"]]
    # Envoy has no approve tool: the call is refused, and the approval is still the user's.
    assert approve.is_error and "approve" in approve.text.lower()
    assert envoy.ctx.tasks.approval(envoy.approval["id"])["status"] == "pending"
    assert approval_rule(mcp.instructions).startswith("You cannot approve anything")


def test_a_wrong_key_is_refused_and_the_error_doesnt_repeat_it(envoy):
    async def go():
        mcp = EnvoyMCP(envoy.url, "not-the-key-zzzz")
        try:
            await mcp.connect()
        finally:
            await mcp.close()

    with pytest.raises(MCPError) as e:
        asyncio.run(go())
    assert "401" in str(e.value) and "zzzz" not in str(e.value)


def test_the_wait_helper_sees_envoys_approval_and_opens_the_card(envoy, tmp_path):
    from fakes import FakeModel, call, say

    events = []
    model = FakeModel([[call("wait_for_task", {"task_id": envoy.task["id"], "timeout_s": 5}, 1)], [say("Approve it on your phone.")]])

    async def go():
        agent = Agent(EnvoyMCP(envoy.url, KEY), model, lambda k, d: events.append((k, d)), costs=CostLog(tmp_path / "c.jsonl"), poll_s=0.05)
        await agent.start()
        await agent.ask("check me in")
        await agent.mcp.close()

    asyncio.run(go())
    waiting = [d for k, d in events if k == "waiting"]
    assert waiting and waiting[0]["kind"] == "approval" and waiting[0]["title"] == "Confirm check-in for SL 482"
    assert envoy.ctx.tasks.approval(envoy.approval["id"])["status"] == "pending"
