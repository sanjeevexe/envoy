"""What get_task tells an agent about a pending approval (backlog #53): that it waits for the user's OK in Envoy, never an
approval link or its nonce. A link is for the user's own devices, and it names the Mac's private address."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from mcp_server.server import WAITING_FOR_OK
from test_mcp_link import HDR, call, env  # noqa: F401 - env is a fixture


def test_get_task_says_a_step_waits_for_the_users_ok_with_no_approval_link(env):
    store = env.ctx.tasks
    task = store.create("Check me in for my flight", "mcp")
    store.update(task["id"], status="waiting_approval")
    appr = store.add_approval(task["id"], "Confirm check-in", ["irreversible"], "com.skylark.air", "", None)
    with TestClient(env.ctx.asgi) as c:
        got = call(c, "get_task", task_id=task["id"])
    assert got["pending_approvals"] == [{"approval_id": appr["id"], "description": "Confirm check-in", "text": WAITING_FOR_OK}]
    text = json.dumps(got)
    assert "approve_url" not in text and "/approve/" not in text and appr["nonce"] not in text
    assert got["task_url"].endswith(f"/?task={task['id']}")  # the task's own page is still named, as phone_updates does


def test_no_tool_text_tells_an_agent_to_pass_on_an_approval_link(env):
    with TestClient(env.ctx.asgi) as c:
        info = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}}, headers=HDR).json()["result"]
        tools = c.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, headers=HDR).json()["result"]["tools"]
    said = info["instructions"] + " ".join(t.get("description", "") for t in tools)
    assert "approve_url" not in said and "approval link" not in said.replace("no approval link", "")
    assert "waiting for their OK there" in info["instructions"]
