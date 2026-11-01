"""A key per AI agent, each with its own tools (phone-layer plan, contract 2).

Muse calls Envoy with `MCP_BEARER_TOKEN` from .env and keeps every tool. Any other agent (Claude, the Meta agent) gets a
key of its own in Settings › Agents, with the tool groups the user picks (api/auth.py `TOOL_GROUPS`; read and run by
default). The key is shown once and stored hashed. It can be rotated (the old key stops at once) or revoked, and
Settings shows when each agent was last seen.

For each MCP request the bearer check (mcp_stub/middleware.py, `verify=Auth.agent_for`) names the agent, and
`AgentGuard`, the MCP server's middleware, then:
- sets `api.auth.current_agent` for the call, so a task it starts records `agent` and Envoy's questions to the user say
  who asked;
- leaves out of `tools/list` every tool outside the agent's groups, and answers a call to one with a tool error that
  names the group to grant;
- limits each agent to RUN_PER_MINUTE calls a minute to the `run` group's tools, with an error that says when to try again.

A refusal is an ordinary tool result (isError), so the agent can read it and tell the user; its connection is fine.
Approvals don't change: no agent can approve, whatever its groups. A key opens /mcp and nothing else (Auth.check never
accepts one).
"""

from __future__ import annotations

import os
import re
import time
from collections import deque
from typing import Any, Callable

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from api.auth import DEFAULT_GROUPS, MUSE, TOOL_GROUPS, Agent, allowed, current_agent, group_of

RUN_PER_MINUTE = 30
NAME = re.compile(r"^[^\W_][\w .'-]{0,39}$")  # "Claude", "Meta agent", "o'Brien's bot"
GROUP_TEXT = {  # Settings › Agents: each group's name and what it lets an agent do
    "read": ("Read", "follow tasks, see routines, search memory, read the phone's updates and its list of phones"),
    "run": ("Run", "start tasks and routines; every irreversible step still waits for your OK"),
    "memory": ("Memory", "add notes to your memory"),
    "files": ("Files", "put photos and videos on a phone, and get files back"),
    "triggers": ("Triggers", "propose recurring tasks; each stays off until you turn it on"),
}


def _refusal(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": True}


class AgentGuard:
    """The MCP server's middleware for agent keys: see the module docstring. `clock` is for tests."""

    def __init__(self, server: Any, *, per_minute: int = RUN_PER_MINUTE, clock: Callable[[], float] = time.monotonic) -> None:
        self.server, self.per_minute, self.clock = server, per_minute, clock
        self.runs: dict[str, deque[float]] = {}

    async def __call__(self, ctx: Any, call_next: Any) -> Any:
        request = getattr(ctx, "request", None)
        agent = request.scope.get("envoy.caller") if request is not None else None
        agent = agent if isinstance(agent, Agent) else None
        token = current_agent.set(agent)
        try:
            if ctx.method == "tools/call":
                why = await self.refuse(agent, str((ctx.params or {}).get("name") or ""))
                if why:
                    return _refusal(why)
            out = await call_next(ctx)
            if ctx.method == "tools/list" and isinstance(out, dict) and isinstance(out.get("tools"), list):
                out = {**out, "tools": [t for t in out["tools"] if allowed(agent, str(t.get("name") or ""))]}
            return out
        finally:
            current_agent.reset(token)

    async def refuse(self, agent: Agent | None, tool: str) -> str | None:
        if agent is None:
            return "Envoy doesn't know which agent this is, so it can't run tools for it. Connect with an agent key from Envoy › Settings › Agents."
        if not allowed(agent, tool):
            if tool not in {t.name for t in await self.server.list_tools()}:
                return None  # no such tool: the MCP server's own "unknown tool" answer
            group = group_of(tool)
            return (f"{agent.name}'s key can't use {tool}: it is in Envoy's \"{group}\" tool group, which this key wasn't given. "
                    f"The user can add \"{group}\" to {agent.name} in Envoy › Settings › Agents.")
        if group_of(tool) == "run":
            now = self.clock()
            times = self.runs.setdefault(agent.name, deque())
            while times and times[0] <= now - 60:
                times.popleft()
            if len(times) >= self.per_minute:
                wait = max(1, round(times[0] + 60 - now))
                return (f"Envoy takes at most {self.per_minute} run calls a minute from {agent.name}, and that many came in the last minute. "
                        f"Nothing was started. Try {tool} again in {wait} s.")
            times.append(now)
        return None


def guard(server: Any) -> AgentGuard:
    """Put the agent check on an MCP server (mcp_server/server.py calls this as it builds it)."""
    g = AgentGuard(server)
    server.middleware.append(g)
    return g


def agents_router(ctx: Any, session: Callable[..., None], owner: Callable[..., None], caller: Callable[..., Any]) -> APIRouter:
    """Settings › Agents. Seeing the agents and revoking a key are for any of your sessions (cut an agent off from your
    iPhone); creating a key, rotating one and changing what one may do happen on the Mac, like pairing a device. The
    checks are the app's own (closures inside `build()`)."""
    r = APIRouter()
    auth = ctx.auth

    def groups(body: dict[str, Any], default: tuple[str, ...] | None = None) -> list[str]:
        got = body.get("tools", default)
        if not isinstance(got, (list, tuple)) or not got or not all(isinstance(g, str) and g in TOOL_GROUPS for g in got):
            raise HTTPException(400, f"tools is a list of tool groups: {', '.join(TOOL_GROUPS)}")
        return sorted(set(got))

    @r.get("/api/agents", dependencies=[Depends(session)])
    def list_agents(request: Request) -> dict[str, Any]:
        me = caller(request)
        return {"agents": auth.agents(), "muse": {"name": MUSE, "key": bool(auth.mcp_token), "last_seen": auth.muse_last_seen()},
                "groups": [{"id": g, "label": GROUP_TEXT[g][0], "detail": GROUP_TEXT[g][1], "tools": sorted(TOOL_GROUPS[g])} for g in TOOL_GROUPS],
                "default": list(DEFAULT_GROUPS), "per_minute": RUN_PER_MINUTE, "mcp_url": mcp_url(ctx),
                "can_manage": me is not None and me.kind == "owner"}

    @r.post("/api/agents", dependencies=[Depends(owner)])
    def new_agent(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        """A new agent and its key. The key is in this answer only: Envoy keeps its hash."""
        name = re.sub(r"\s+", " ", str(body.get("name") or "")).strip()
        if not NAME.match(name):
            raise HTTPException(400, "Give the agent a name of up to 40 letters, digits, spaces or - . '")
        if name.casefold() == MUSE.casefold() or any(a["name"].casefold() == name.casefold() for a in auth.agents()):
            raise HTTPException(409, f"There is already an agent called {name}. Rotate its key instead, or pick another name.")
        agent, key = auth.issue_agent(name, groups(body, DEFAULT_GROUPS))
        return {"agent": agent, "key": key}

    @r.post("/api/agents/{aid}/rotate", dependencies=[Depends(owner)])
    def rotate(aid: str) -> dict[str, Any]:
        key = auth.rotate_agent(aid)
        if key is None:
            raise HTTPException(404, "no such agent")
        return {"agent": next(a for a in auth.agents() if a["id"] == aid), "key": key}

    @r.post("/api/agents/{aid}", dependencies=[Depends(owner)])
    def set_tools(aid: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        agent = auth.set_agent_tools(aid, groups(body))
        if agent is None:
            raise HTTPException(404, "no such agent")
        return agent

    @r.delete("/api/agents/{aid}", dependencies=[Depends(session)])
    def revoke(aid: str) -> dict[str, Any]:
        if not auth.revoke_agent(aid):
            raise HTTPException(404, "no such agent")
        return {"revoked": aid}

    return r


def mcp_url(ctx: Any) -> str:
    """Where an agent connects: the permanent public address when there is one (MCP_PERMANENT_URL), else this API's /mcp."""
    return (os.environ.get("MCP_PERMANENT_URL") or "").strip() or f"{ctx.public.rstrip('/')}/mcp"
