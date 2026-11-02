"""A small MCP client for checking Envoy's tools from outside, the way an agent sees them (phone-layer plan, agent-door's
check): initialize, tools/list, and optionally one tools/call, then get_task until the task ends.

  uv run --project backend python eval/mcp_tool_check.py --url http://127.0.0.1:8761/mcp --token-file <file> \\
      --out eval/results/agent-door/tools-before.json
  ... --call skylark_get_flight_gate --args '{"trip_city": "Chicago"}' --wait 240 --out eval/results/agent-door/call.json

The key is read from a file and never printed. The output has the tool names, each routine tool in full, and the call's
result and task; nothing else from the server.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx

HDR = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json", "MCP-Protocol-Version": "2025-11-25"}
DONE = {"done", "failed", "declined", "stopped"}


class Client:
    def __init__(self, url: str, token: str) -> None:
        self.url, self.http, self.n = url, httpx.Client(timeout=60, headers={**HDR, "Authorization": f"Bearer {token}"}), 0

    def rpc(self, method: str, params: dict | None = None) -> dict:
        self.n += 1
        r = self.http.post(self.url, json={"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}})
        r.raise_for_status()
        body = r.json()
        if "error" in body:
            raise RuntimeError(f"{method}: {body['error']}")
        return body["result"]

    def call(self, name: str, args: dict) -> tuple[bool, dict | str]:
        res = self.rpc("tools/call", {"name": name, "arguments": args})
        text = (res.get("content") or [{}])[0].get("text", "")
        try:
            return bool(res.get("isError")), json.loads(text)
        except ValueError:
            return bool(res.get("isError")), text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--call")
    ap.add_argument("--args", default="{}")
    ap.add_argument("--wait", type=float, default=0, help="seconds to follow the call's task with get_task")
    a = ap.parse_args()
    c = Client(a.url, Path(a.token_file).read_text().strip())
    info = c.rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "agent-door-check", "version": "1"}})
    t0 = time.time()
    tools = c.rpc("tools/list")["tools"]
    out: dict = {"at": time.strftime("%Y-%m-%d %H:%M:%S %Z"), "server": info.get("serverInfo", {}).get("name"),
                 "list_ms": round((time.time() - t0) * 1000), "tools": sorted(t["name"] for t in tools),
                 "routine_tools": [t for t in tools if (t.get("_meta") or {}).get("envoy/routine")]}
    if a.call:
        args = json.loads(a.args)
        t0 = time.time()
        err, res = c.call(a.call, args)
        out["call"] = {"tool": a.call, "arguments": args, "is_error": err, "result": res, "seconds": round(time.time() - t0, 2)}
        tid = res.get("task_id") if isinstance(res, dict) else None
        polls, task = 0, None
        while tid and time.time() - t0 < a.wait:
            _, task = c.call("get_task", {"task_id": tid})
            polls += 1
            if isinstance(task, dict) and task.get("status") in DONE:
                break
            time.sleep(3)
        if task is not None:
            out["task"] = {**task, "followed_s": round(time.time() - t0, 1), "polls": polls}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"{len(out['tools'])} tools ({len(out['routine_tools'])} routine tools: {', '.join(t['name'] for t in out['routine_tools']) or 'none'})"
          + (f"; called {a.call}: {'error' if out['call']['is_error'] else 'ok'}" if a.call else "")
          + (f"; task {out['task'].get('status')} after {out['task']['followed_s']} s" if out.get("task") else ""))


if __name__ == "__main__":
    main()
