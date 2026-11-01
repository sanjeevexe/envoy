"""Which learned routines other agents can call as tools of their own (phone-layer plan, contract 1).

Each routine has a "Share with agents" switch, off by default. While it's on and the routine has an active version, the
MCP server lists the routine as its own tool, by name and with typed inputs (mcp_server/server.py, `RoutineTools`). There
is no lock: the user decided that off by default plus approvals is enough, since anything irreversible still waits for
their OK on their phone.

The switch is kept in the API's database (`routine_sharing`), so nothing under `backend/routines/` changes. Routes are
session only, like the other settings writes:

  GET  /api/routines/sharing         {"shared": [names], "tools": [{"routine", "tool", "app", "inputs", ...}], "builtin": [...]}
  POST /api/routines/{name}/share    {"on": bool} → the same, plus {"routine", "on", "tool": its tool's name or null}

A tool's name is the routine's own when it reads like a tool name and isn't one of the built-in tools' names; otherwise
`routine_<name, sanitized>`.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

SCHEMA = "CREATE TABLE IF NOT EXISTS routine_sharing (routine TEXT PRIMARY KEY, shared INTEGER NOT NULL, updated_at REAL)"

TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
PREFIX = "routine_"


class Sharing:
    def __init__(self, tasks: Any) -> None:
        self.db, self.lock = tasks.db, tasks.lock
        with self.lock:
            self.db.execute(SCHEMA)
            self.db.commit()

    def shared(self, name: str) -> bool:
        with self.lock:
            row = self.db.execute("SELECT shared FROM routine_sharing WHERE routine=?", (name,)).fetchone()
        return bool(row and row["shared"])

    def names(self) -> set[str]:
        with self.lock:
            return {r["routine"] for r in self.db.execute("SELECT routine FROM routine_sharing WHERE shared=1")}

    def set(self, name: str, on: bool) -> bool:
        with self.lock:
            self.db.execute("INSERT INTO routine_sharing (routine, shared, updated_at) VALUES (?,?,?) "
                            "ON CONFLICT(routine) DO UPDATE SET shared=excluded.shared, updated_at=excluded.updated_at",
                            (name, int(bool(on)), time.time()))
            self.db.commit()
        return bool(on)


def tool_name(routine: str, reserved: Iterable[str] = ()) -> str:
    """The routine's own name when it reads like a tool name and isn't a built-in tool's; else `routine_<sanitized>`
    (lower case, anything but letters, digits and underscores made an underscore, at most 64 characters)."""
    if TOOL_NAME.match(routine) and routine not in set(reserved):
        return routine
    clean = re.sub(r"_+", "_", re.sub(r"[^a-z0-9_]", "_", routine.lower())).strip("_") or "unnamed"
    return (PREFIX + clean)[:64].rstrip("_")


def tool_names(routines: Iterable[str], reserved: Iterable[str] = ()) -> dict[str, str]:
    """routine → tool name for several routines at once, so two can't end up with the same tool: a later one (in name
    order) that would take a name already given gets `_2`, `_3`, …"""
    reserved = set(reserved)
    taken, out = set(reserved), {}
    for name in sorted(routines):
        tool = base = tool_name(name, reserved)
        n = 2
        while tool in taken:
            tool = f"{base[:64 - len(str(n)) - 1]}_{n}"
            n += 1
        taken.add(tool)
        out[name] = tool
    return out


def sharing_router(ctx: Any, session: Callable[..., None], agent_tools: Callable[[], dict[str, Any]]) -> APIRouter:
    """The share switch's routes. `agent_tools` is the MCP server's own account of what agents see now
    (`EnvoyMCP.agent_tools`), so Settings › Agents shows exactly that. Include this router before
    `/api/routines/{name}`, which would otherwise take "sharing" for a routine's name."""
    r = APIRouter()
    sharing: Sharing = ctx.sharing

    def state() -> dict[str, Any]:
        return {"shared": sorted(sharing.names()), **agent_tools()}

    @r.get("/api/routines/sharing", dependencies=[Depends(session)])
    def get_sharing() -> dict[str, Any]:
        return state()

    @r.post("/api/routines/{name}/share", dependencies=[Depends(session)])
    def share(name: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        if name not in ctx.routines.names():
            raise HTTPException(404, "no such routine")
        if not isinstance(body.get("on"), bool):
            raise HTTPException(400, 'send {"on": true} or {"on": false}')
        sharing.set(name, body["on"])
        out = state()
        tool = next((t for t in out["tools"] if t["routine"] == name), None)
        return {**out, "routine": name, "on": body["on"], "tool": tool["tool"] if tool else None}

    return r
