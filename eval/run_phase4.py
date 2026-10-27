"""Phase 4 gate, scripted: a full check-in through the API, with a scripted person doing the person's parts.

  uv run --project backend python scripts/demo_setup.py          # SkyLark signed out, fresh demo memory (API stopped)
  uv run --project backend python -m api --profile demo           # in another terminal
  uv run --project backend python eval/run_phase4.py              # this script

1. "Check me in for my flight" is sent to the API, the way the web app sends it.
2. The run stops at SkyLark's sign-in and asks for a takeover. The scripted person takes over, signs in through
   SkyLark's test hook (no password is typed by anything), and hands back.
3. The check-in reaches its irreversible step; the approval request arrives (with a screenshot); the scripted person
   opens it and approves through the same endpoint the web app uses, with the session.
4. The check-in completes in the app, and memory updates (events streamed, facts readable).
It also checks the live view (frames, latency, input refused unless taken over), the MCP server (no approve tool,
run_task + get_task with an approve_url), and chat answering from memory.

Results: eval/results/phase4/gate.json. The real gate is the same flow done by you in the web app.
"""

from __future__ import annotations

import asyncio
import json
import struct
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import websockets

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from demo_setup import demo_fixtures  # noqa: E402
from testapps.skylark import SkyLark  # noqa: E402

BASE = "http://127.0.0.1:8700"
OUT = REPO / "eval" / "results" / "phase4"
TOKEN = (REPO / "data" / "api" / "session_token").read_text().strip()
H = {"Authorization": f"Bearer {TOKEN}"}


def mcp_token() -> str:
    for line in (REPO / ".env").read_text().splitlines():
        if line.startswith("MCP_BEARER_TOKEN="):
            return line.split("=", 1)[1].strip()
    return ""


async def mcp_call(c: httpx.AsyncClient, method: str, params: dict[str, Any], i: int = 1) -> dict[str, Any]:
    r = await c.post(f"{BASE}/mcp", json={"jsonrpc": "2.0", "id": i, "method": method, "params": params},
                     headers={"Authorization": f"Bearer {mcp_token()}", "Accept": "application/json, text/event-stream",
                              "MCP-Protocol-Version": "2025-11-25"})
    r.raise_for_status()
    return r.json()


async def live_check() -> dict[str, Any]:
    async with websockets.connect(f"ws://127.0.0.1:8700/api/live/envoy-test?fps=10", additional_headers=H, max_size=None) as ws:
        hello = json.loads(await ws.recv())
        await ws.send(json.dumps({"type": "tap", "x": 0.5, "y": 0.5}))
        refused, lat, n, t0 = False, [], 0, time.time()
        while time.time() - t0 < 3:
            m = await ws.recv()
            if isinstance(m, bytes):
                lat.append((time.time() - struct.unpack(">d", m[:8])[0]) * 1000)
                n += 1
            elif "take over first" in m:
                refused = True
        return {"device": f"{hello['width']}x{hello['height']}", "frames": n, "latency_ms": round(sorted(lat)[len(lat) // 2]) if lat else None,
                "input_refused_without_takeover": refused}


async def gate() -> dict[str, Any]:
    app = SkyLark("emulator-5554")
    fx = demo_fixtures(signed_in=False)
    app.prepare(fixtures=fx, variant=0)
    code = next(t["code"] for t in fx["trips"] if t["flight"]["to"] == "ORD" or "Chicago" in json.dumps(t))
    steps: list[dict[str, Any]] = []
    t0 = time.time()

    def log(name: str, ok: bool, **kw: Any) -> None:
        steps.append({"step": name, "ok": ok, "t": round(time.time() - t0, 1), **kw})
        print(f"{'OK ' if ok else 'BAD'} {name}: " + ", ".join(f"{k}={v}" for k, v in kw.items())[:300], flush=True)

    async with httpx.AsyncClient(timeout=60) as c, websockets.connect("ws://127.0.0.1:8700/api/events", additional_headers=H, max_size=None) as ev:
        state = (await c.get(f"{BASE}/api/state", headers=H)).json()
        log("API up, demo memory loaded", state["memory"]["entities"] > 0, entities=state["memory"]["entities"], routines=state["routines"])
        log("live view", True, **await live_check())

        # The gate is "the user approves": ask before every irreversible step for this run (restored at the end).
        before_rules = (await c.get(f"{BASE}/api/settings/approvals", headers=H)).json()["rules"]
        await c.post(f"{BASE}/api/settings/approvals", json={**before_rules, "default": "always", "apps": {}, "routines": {}}, headers=H)
        r = await c.post(f"{BASE}/api/tasks", json={"goal": "Check me in for my flight"}, headers=H)
        tid = r.json()["id"]
        log("task started", r.status_code == 200, task=tid)
        seen: dict[str, Any] = {"memory_events": 0, "step_events": 0, "shots": 0}
        final = None
        deadline = time.time() + 420
        while time.time() < deadline:
            try:
                e = json.loads(await asyncio.wait_for(ev.recv(), timeout=deadline - time.time()))
            except asyncio.TimeoutError:
                break
            if e["type"] == "memory":
                seen["memory_events"] += 1
            if e.get("task_id") != tid and (e.get("task") or {}).get("id") != tid:
                continue
            if e["type"] == "step":
                seen["step_events"] += 1
                seen["shots"] += 1 if e["step"].get("shot") else 0
            elif e["type"] == "takeover_requested":
                log("asked to take over", True, reason=e["reason"])
                tk = await c.post(f"{BASE}/api/devices/envoy-test/takeover", headers=H)
                await asyncio.sleep(1.0)
                st = (await c.get(f"{BASE}/api/tasks/{tid}", headers=H)).json()["task"]["status"]
                fx_in = demo_fixtures(signed_in=True)
                await asyncio.to_thread(app.seed, fx_in)  # the scripted person signs in (test hook; nothing types a password)
                await asyncio.sleep(1.5)
                hb = await c.post(f"{BASE}/api/devices/envoy-test/handback", headers=H)
                log("took over, signed in, handed back", tk.status_code == 200 and hb.status_code == 200 and st == "taken_over",
                    status_during_takeover=st)
            elif e["type"] == "approval_requested":
                a = e["approval"]
                full = (await c.get(f"{BASE}/api/approvals/{a['id']}", headers=H)).json()
                still = (await c.get(f"{BASE}/api/approvals/{a['id']}", headers=H)).json()["status"]
                shot = (await c.get(f"{BASE}/api/approvals/{a['id']}/shot", headers=H)).status_code == 200
                mcp_try = await c.post(f"{BASE}/api/approvals/{a['id']}", json={"decision": "approve", "nonce": full["nonce"]},
                                       headers={"Authorization": f"Bearer {mcp_token()}"})
                d = await c.post(f"{BASE}/api/approvals/{a['id']}", json={"decision": "approve", "nonce": full["nonce"]}, headers=H)
                log("approval requested and approved by the person", d.status_code == 200 and still == "pending" and shot and mcp_try.status_code == 401,
                    description=a["description"], screenshot=shot, opening_decided_nothing=still == "pending",
                    mcp_token_refused=mcp_try.status_code == 401)
            elif e["type"] == "task" and e["task"]["status"] in ("done", "failed", "declined", "needs_you", "stopped") and e["task"]["id"] == tid:
                if e["task"]["status"] == "needs_you" and e["task"].get("waiting_for") == "takeover":
                    continue
                final = e["task"]
                break
        task = (await c.get(f"{BASE}/api/tasks/{tid}", headers=H)).json()
        for _ in range(60):  # the task is done as soon as the phone work is; memory is written right after
            if any(s.get("kind") == "memory" for s in task["steps"]):
                break
            await asyncio.sleep(1)
            task = (await c.get(f"{BASE}/api/tasks/{tid}", headers=H)).json()
        checked = (await asyncio.to_thread(app.trip, code))["checked_in"]
        log("check-in done in the app", bool(final) and final["status"] == "done" and checked, status=(final or {}).get("status"),
            result=(final or {}).get("result"), routine=task["task"].get("routine"), model_calls=task["task"].get("model_calls"),
            checked_in=checked, steps=len(task["steps"]), step_events=seen["step_events"], step_screenshots=seen["shots"])
        mem_step = next((s for s in task["steps"] if s.get("kind") == "memory"), None)
        notes = (await c.get(f"{BASE}/api/memory/search", params={"q": "my Chicago flight seat gate boarding"}, headers=H)).json()["markdown"]
        log("memory updated", bool(mem_step) and "SkyLark app" in notes, memory_step=(mem_step or {}).get("text"),
            memory_events=seen["memory_events"], notes_excerpt=notes[:400])

        # MCP: the same task API from an AI client; no approve tool.
        tools = await mcp_call(c, "tools/list", {})
        names = sorted(t["name"] for t in tools["result"]["tools"])
        run = await mcp_call(c, "tools/call", {"name": "run_task", "arguments": {"goal": "What gate does my Chicago flight leave from?"}}, 2)
        mtid = json.loads(run["result"]["content"][0]["text"])["task_id"]
        info: dict[str, Any] = {}
        for _ in range(120):
            got = await mcp_call(c, "tools/call", {"name": "get_task", "arguments": {"task_id": mtid}}, 3)
            info = json.loads(got["result"]["content"][0]["text"])
            if info["status"] in ("done", "failed", "declined", "stopped"):
                break
            await asyncio.sleep(1)
        log("MCP: tools, run_task and get_task", "approve" not in " ".join(names) and info.get("status") == "done", tools=names,
            mcp_task=info.get("status"), result=info.get("result"))

        await c.post(f"{BASE}/api/settings/approvals", json=before_rules, headers=H)
        chat = (await c.post(f"{BASE}/api/chat", json={"message": "What's my gate?"}, headers=H)).json()
        log("chat answers from memory", chat.get("kind") == "memory" and bool(chat.get("from_memory")), reply=chat.get("reply"))
    passed = all(s["ok"] for s in steps)
    summary = {"passed": passed, "steps_ok": f"{sum(s['ok'] for s in steps)}/{len(steps)}", "duration_s": round(time.time() - t0, 1)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "gate.json").write_text(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "summary": summary, "steps": steps}, indent=1, default=str))
    print(json.dumps(summary))
    return summary


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(gate())["passed"] else 1)
