"""Static bearer-token check and JSONL request log, as one ASGI middleware.

Every HTTP request is logged to logs/mcp_stub.jsonl (method, path, JSON-RPC
method, tool name and arguments, headers with the token removed, auth result,
status). Requests without the right `Authorization: Bearer <token>` get a 401,
except paths in `open_prefixes` (health check, fake approval page).
"""

from __future__ import annotations

import hmac
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

REDACTED_HEADERS = {"authorization", "cookie", "proxy-authorization", "x-api-key"}


def _summarize_body(body: bytes) -> dict[str, Any]:
    """Pull JSON-RPC method, tool name and arguments out of a request body."""
    if not body:
        return {}
    try:
        data = json.loads(body)
    except ValueError:
        return {"body_preview": body[:500].decode("utf-8", "replace")}
    messages = data if isinstance(data, list) else [data]
    out: list[dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, dict) or "jsonrpc" not in msg:
            continue
        entry: dict[str, Any] = {"rpc_method": msg.get("method"), "rpc_id": msg.get("id")}
        params = msg.get("params") or {}
        if msg.get("method") == "tools/call":
            entry["tool"] = params.get("name")
            entry["arguments"] = params.get("arguments")
        elif msg.get("method") == "initialize":
            entry["protocol_version"] = params.get("protocolVersion")
            entry["client_info"] = params.get("clientInfo")
            entry["client_capabilities"] = params.get("capabilities")
        elif "method" not in msg:
            entry["rpc_response"] = True
        elif params:
            entry["params"] = params
        out.append(entry)
    if not out:
        return {"json": data}
    return out[0] if len(out) == 1 else {"batch": out}


class BearerAuthLogMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        token: str,
        log_path: Path,
        server: str,
        open_prefixes: tuple[str, ...] = ("/healthz", "/approve/"),
    ) -> None:
        if not token:
            raise ValueError("MCP_BEARER_TOKEN is empty; refusing to start without auth")
        self.app = app
        self.token = token.encode()
        self.log_path = log_path
        self.server = server
        self.open_prefixes = open_prefixes
        log_path.parent.mkdir(parents=True, exist_ok=True)

    def _check(self, headers: dict[str, str]) -> str:
        value = headers.get("authorization")
        if not value:
            return "missing"
        scheme, _, presented = value.partition(" ")
        if scheme.lower() != "bearer" or not presented:
            return "malformed"
        return "ok" if hmac.compare_digest(presented.strip().encode(), self.token) else "wrong_token"

    def _write(self, record: dict[str, Any]) -> None:
        with self.log_path.open("a") as f:
            f.write(json.dumps(record, default=str) + "\n")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        path = scope.get("path", "")

        # Read the whole body so it can be logged, then replay it to the app.
        chunks: list[bytes] = []
        more = True
        while more:
            message = await receive()
            if message["type"] == "http.disconnect":
                break
            chunks.append(message.get("body", b""))
            more = message.get("more_body", False)
        body = b"".join(chunks)
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        status: dict[str, int] = {}

        async def capture(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        is_open = path.startswith(self.open_prefixes)
        auth = "open_path" if is_open else self._check(headers)
        record: dict[str, Any] = {
            "time": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "server": self.server,
            "http_method": scope["method"],
            "path": path,
            "query": scope.get("query_string", b"").decode("latin-1") or None,
            "client": (scope.get("client") or [None])[0],
            "auth": auth,
            "headers": {k: ("<redacted>" if k in REDACTED_HEADERS else v) for k, v in headers.items()},
            **_summarize_body(body),
        }

        try:
            if auth in ("ok", "open_path"):
                await self.app(scope, replay, capture)
            else:
                await capture(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"www-authenticate", b'Bearer realm="envoy-stub"'),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})
        finally:
            record["status"] = status.get("code")
            record["ms"] = round((time.perf_counter() - started) * 1000, 1)
            self._write(record)
