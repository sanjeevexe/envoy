"""Test the Phase 0 MCP stub and REST fallback: the right token works, no token or a wrong token is rejected.

Usage (servers must be running):
  uv run --project backend python scripts/test_mcp_stub.py [--mcp-url URL] [--rest-url URL]
Defaults to the local servers; pass the tunnel URL to test through Cloudflare.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
import httpx2
from dotenv import load_dotenv
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

REPO = Path(__file__).resolve().parents[1]
load_dotenv(REPO / ".env")
TOKEN = os.environ["MCP_BEARER_TOKEN"]

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


async def mcp_with_sdk(url: str) -> None:
    """Full MCP handshake with the official client: list tools, call both."""
    async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {TOKEN}"}, timeout=30) as http:
        async with Client(streamable_http_client(url, http_client=http)) as client:
            tools = await client.list_tools()
            names = sorted(t.name for t in tools.tools)
            check("mcp: list_tools with token", names == ["memory_search", "run_task"], str(names))

            res = await client.call_tool("memory_search", {"query": "what's my gate?"})
            text = json.dumps(res.structured_content or [c.model_dump() for c in res.content])
            check("mcp: memory_search returns the fake trip", "B12" in text and "KX7Q2M" in text)

            res = await client.call_tool("run_task", {"goal": "check me in for my flight"})
            text = json.dumps(res.structured_content or [c.model_dump() for c in res.content])
            check("mcp: run_task returns task id + approve_url", "task_" in text and "/approve/" in text)


def mcp_raw(url: str, token: str | None) -> int:
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "envoy-test", "version": "0"},
        },
    }
    return httpx.post(url, json=body, headers=headers, timeout=30).status_code


def rest(base: str, token: str | None) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return httpx.post(f"{base}/memory_search", json={"query": "gate"}, headers=headers, timeout=30)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mcp-url", default=f"http://127.0.0.1:{os.environ.get('MCP_PORT', '8765')}/mcp")
    ap.add_argument("--rest-url", default=f"http://127.0.0.1:{os.environ.get('REST_PORT', '8766')}")
    ap.add_argument("--skip-rest", action="store_true")
    args = ap.parse_args()

    await mcp_with_sdk(args.mcp_url)
    check("mcp: no token rejected", (s := mcp_raw(args.mcp_url, None)) == 401, f"status {s}")
    check("mcp: wrong token rejected", (s := mcp_raw(args.mcp_url, "wrong-" + TOKEN[:8])) == 401, f"status {s}")
    check("mcp: right token accepted (raw initialize)", (s := mcp_raw(args.mcp_url, TOKEN)) == 200, f"status {s}")

    if not args.skip_rest:
        r = rest(args.rest_url, TOKEN)
        check("rest: memory_search with token", r.status_code == 200 and "B12" in r.text, f"status {r.status_code}")
        r = httpx.post(f"{args.rest_url}/run_task", json={"goal": "check me in"},
                       headers={"Authorization": f"Bearer {TOKEN}"}, timeout=30)
        check("rest: run_task with token", r.status_code == 200 and "/approve/" in r.text, f"status {r.status_code}")
        check("rest: no token rejected", (s := rest(args.rest_url, None).status_code) == 401, f"status {s}")
        check("rest: wrong token rejected", (s := rest(args.rest_url, "nope").status_code) == 401, f"status {s}")
        spec = httpx.get(f"{args.rest_url}/openapi.json", timeout=30).json()
        check("rest: OpenAPI lists both operations",
              {"memory_search", "run_task"} <= {op.get("operationId") for p in spec["paths"].values() for op in p.values()})

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
