"""A small MCP client for Envoy: Streamable HTTP, JSON-RPC over POST, one bearer key.

Envoy's server is stateless (each request stands alone), so this client is too: `initialize` once to learn the
server's name and instructions, then `tools/list` and `tools/call` as plain POSTs. A response may come back as JSON or
as a short SSE stream; both are read. The key goes only in the Authorization header, never in a log or an error.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from typing import Any

import httpx

PROTOCOL = "2025-11-25"
CLIENT_INFO = {"name": "envoy-meta-agent", "version": "0.1.0"}


class MCPError(RuntimeError):
    """The server couldn't be reached, refused the key, or answered something that isn't MCP."""


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    title: str | None = None
    annotations: dict[str, Any] = field(default_factory=dict)


@dataclass
class CallResult:
    """A tools/call answer: Envoy's structured result when it sent one, else its text; `is_error` for tool errors and
    JSON-RPC errors alike (an unknown tool, a refused tool group)."""
    data: Any
    text: str
    is_error: bool


class EnvoyMCP:
    def __init__(self, url: str, key: str, *, timeout_s: float = 60, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.url = url
        self._key = key
        self._ids = itertools.count(1)
        self._session: str | None = None
        self.protocol = PROTOCOL
        self.server_info: dict[str, Any] = {}
        self.instructions = ""
        self._http = httpx.AsyncClient(timeout=timeout_s, transport=transport)

    async def close(self) -> None:
        await self._http.aclose()

    def _headers(self) -> dict[str, str]:
        h = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json",
             "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": self.protocol}
        if self._session:
            h["Mcp-Session-Id"] = self._session
        return h

    async def _post(self, body: dict[str, Any]) -> dict[str, Any] | None:
        try:
            r = await self._http.post(self.url, json=body, headers=self._headers())
        except httpx.HTTPError as e:
            raise MCPError(f"can't reach Envoy at {self.url}: {type(e).__name__}") from None
        if r.status_code == 401:
            raise MCPError("Envoy refused this agent's key (401)")
        if r.status_code == 202 or "id" not in body:
            return None
        if r.status_code >= 400:
            raise MCPError(f"Envoy answered HTTP {r.status_code}: {r.text[:200]}")
        if sid := r.headers.get("mcp-session-id"):
            self._session = sid
        kind = r.headers.get("content-type", "")
        if kind.startswith("text/event-stream"):
            return _from_sse(r.text, body["id"])
        try:
            return r.json()
        except ValueError:
            raise MCPError(f"Envoy's answer isn't JSON ({kind or 'no content type'})") from None

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        msg = await self._post({"jsonrpc": "2.0", "id": next(self._ids), "method": method, **({"params": params} if params else {})})
        if msg is None:
            raise MCPError(f"no answer to {method}")
        return msg

    async def connect(self) -> None:
        msg = await self.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": CLIENT_INFO})
        if "error" in msg:
            raise MCPError(f"initialize failed: {msg['error'].get('message')}")
        res = msg.get("result") or {}
        self.protocol = res.get("protocolVersion") or PROTOCOL
        self.server_info = res.get("serverInfo") or {}
        self.instructions = res.get("instructions") or ""
        await self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    async def list_tools(self) -> list[Tool]:
        tools, cursor = [], None
        while True:
            msg = await self.request("tools/list", {"cursor": cursor} if cursor else None)
            if "error" in msg:
                raise MCPError(f"tools/list failed: {msg['error'].get('message')}")
            res = msg.get("result") or {}
            for t in res.get("tools") or []:
                tools.append(Tool(t["name"], t.get("description") or "", t.get("inputSchema") or {"type": "object"},
                                  t.get("title"), t.get("annotations") or {}))
            cursor = res.get("nextCursor")
            if not cursor:
                return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> CallResult:
        msg = await self.request("tools/call", {"name": name, "arguments": arguments})
        if "error" in msg:
            text = str(msg["error"].get("message") or msg["error"])
            return CallResult({"error": text}, text, True)
        res = msg.get("result") or {}
        text = "\n".join(c.get("text", "") for c in res.get("content") or [] if c.get("type") == "text")
        data = res.get("structuredContent")
        if data is None:
            try:
                data = json.loads(text) if text.strip().startswith(("{", "[")) else None
            except ValueError:
                data = None
        if isinstance(data, dict) and set(data) == {"result"}:  # a tool whose return type isn't an object gets wrapped
            data = data["result"]
        return CallResult(data if data is not None else text, text, bool(res.get("isError")))


def _from_sse(body: str, want_id: Any) -> dict[str, Any]:
    """The JSON-RPC answer with our id from an SSE body (`data:` lines, events split by blank lines)."""
    for event in body.replace("\r\n", "\n").split("\n\n"):
        data = "\n".join(line[5:].lstrip() for line in event.split("\n") if line.startswith("data:"))
        if not data:
            continue
        try:
            msg = json.loads(data)
        except ValueError:
            continue
        if isinstance(msg, dict) and msg.get("id") == want_id:
            return msg
    raise MCPError("Envoy's event stream ended without an answer")
