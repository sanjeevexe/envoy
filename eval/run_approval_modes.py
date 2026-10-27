"""Approval modes on SkyLark, through the API (the API must be running with the demo profile; envoy-test up).

  uv run --project backend python eval/run_approval_modes.py

1. Default ("ask unless I asked for it"): "Check me in for my flight" from the web app checks in without asking,
   and the approval is on record as given by "your request".
2. The same request from an AI client over MCP asks (not the user's own words).
3. A standing approval on the check-in routine: the MCP request runs without asking.
4. "Always ask": the web request asks.
Each case reseeds SkyLark (signed in, not checked in). Results: eval/results/phase4/approval_modes.json.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "eval"))
from demo_setup import demo_fixtures  # noqa: E402
from run_phase4 import BASE, H, mcp_call  # noqa: E402
from testapps.skylark import SkyLark  # noqa: E402

ROUTINE = "skylark_check_in_flight"


async def run_case(c: httpx.AsyncClient, name: str, rules: dict[str, Any], via: str, expect_ask: bool) -> dict[str, Any]:
    app = SkyLark("emulator-5554")
    await asyncio.to_thread(app.prepare, demo_fixtures(signed_in=True), 0)
    await c.post(f"{BASE}/api/settings/approvals", json=rules, headers=H)
    if via == "web":
        tid = (await c.post(f"{BASE}/api/tasks", json={"goal": "Check me in for my flight"}, headers=H)).json()["id"]
    else:
        res = await mcp_call(c, "tools/call", {"name": "run_task", "arguments": {"goal": "Check me in for my flight"}}, 7)
        tid = json.loads(res["result"]["content"][0]["text"])["task_id"]
    asked = False
    t0 = time.time()
    while time.time() - t0 < 240:
        d = (await c.get(f"{BASE}/api/tasks/{tid}", headers=H)).json()
        pend = [a for a in d["approvals"] if a["status"] == "pending"]
        if pend:
            asked = True
            full = (await c.get(f"{BASE}/api/approvals/{pend[0]['id']}", headers=H)).json()
            await c.post(f"{BASE}/api/approvals/{pend[0]['id']}", json={"decision": "approve", "nonce": full["nonce"]}, headers=H)
        if d["task"]["status"] in ("done", "failed", "declined", "stopped"):
            break
        await asyncio.sleep(1)
    d = (await c.get(f"{BASE}/api/tasks/{tid}", headers=H)).json()
    checked = (await asyncio.to_thread(app.trip, "KX7Q2M"))["checked_in"]
    recs = [(a["status"], a["decided_by"]) for a in d["approvals"]]
    ok = d["task"]["status"] == "done" and checked and asked == expect_ask
    row = {"case": name, "via": via, "rules": rules, "asked": asked, "expected_ask": expect_ask, "status": d["task"]["status"],
           "checked_in": checked, "approvals": recs, "ok": ok}
    print(f"{'OK ' if ok else 'BAD'} {name}: asked={asked} (expected {expect_ask}), {d['task']['status']}, approvals {recs}", flush=True)
    return row


async def main() -> int:
    async with httpx.AsyncClient(timeout=60) as c:
        before = (await c.get(f"{BASE}/api/settings/approvals", headers=H)).json()["rules"]
        default = {"default": "unless_requested", "apps": {}, "routines": {}}
        rows = [
            await run_case(c, "your own request, default mode", default, "web", expect_ask=False),
            await run_case(c, "the same request from MCP", default, "mcp", expect_ask=True),
            await run_case(c, "MCP with a standing approval on the routine", {**default, "routines": {ROUTINE: "never"}}, "mcp", expect_ask=False),
            await run_case(c, "your own request, always ask", {**default, "default": "always"}, "web", expect_ask=True),
        ]
        await c.post(f"{BASE}/api/settings/approvals", json=before, headers=H)
    out = REPO / "eval" / "results" / "phase4" / "approval_modes.json"
    out.write_text(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "cases": rows}, indent=1))
    passed = all(r["ok"] for r in rows)
    print(json.dumps({"passed": passed, "ok": f"{sum(r['ok'] for r in rows)}/{len(rows)}"}))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
