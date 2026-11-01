"""Backlog #49: the creator workflow on the cloud phone, by the link path (runs ON the VM, in ~/envoy). Nothing is posted.

  From the Mac, once push.sh has put a commit with this file on the VM:
  scripts/cloud/bg.sh ig uv run --project backend python scripts/cloud/instagram_link.py --url https://…/clip.mp4 --caption "…"
  scripts/cloud/wait.sh ig

What Muse would do with a cloud copy, through the copy's own /mcp (its MCP token, read here, never printed):
1. `send_to_phone(<url>, device="envoy-real")`: Envoy downloads the clip and puts it in the Real-app phone's gallery.
   An emulator takes a file at once (mcp_server/server.py), so no offer is made and nothing starts by itself: the
   offer, and the task its Yes starts, exist only for a real phone (`phone-…`).
2. `run_task(<the Instagram template's goal, with the caption>)`: the task the offer's Yes would start. It comes from
   an AI client (source "mcp"), so every irreversible step asks the user, whatever the approval mode
   (policy/approval_rules.py); the run refuses to start if a "never" mode covers Instagram.
3. The task is followed through the copy's session API (its session token, read here, never printed). When Share is
   asked, the phone's screen (adb) and the approval's own picture are saved, and Share is declined through that API.
   Any other approval is left to the user in the app. A task that ends done is reported as a failure at once.
Then Instagram's composer is left without posting or saving (scripts/instagram_take.py's `leave_composer`).

Results: logs/ig/<time>/ (run.json, new-reel.png, share-approval.jpg), fetched to eval/results/cloud/instagram/.

The clip's host must list an IPv4 address first: the VM has no IPv6 route, and Envoy's download connects to the first
of the host's addresses sorted as text (Nov 1: MDN's sample failed that way; test-videos.co.uk worked).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "backend"), str(REPO / "eval"), str(REPO / "scripts")]

import httpx  # noqa: E402
from api.handoff import HANDOFF_TEMPLATES, fill  # noqa: E402
from devices.emulator import AVDS  # noqa: E402
from run_creator import IG, PAUSED, Copy, ended, is_share, spent  # noqa: E402

DEVICE = "envoy-real"
API = "http://127.0.0.1:8700"


def mcp(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    token = next((line.split("=", 1)[1].strip() for line in (REPO / ".env").read_text().splitlines() if line.startswith("MCP_BEARER_TOKEN=")), "")
    r = httpx.post(f"{API}/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}},
                   headers={"Authorization": f"Bearer {token}", "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-11-25"},
                   timeout=300)
    r.raise_for_status()
    return json.loads(r.json()["result"]["content"][0]["text"])


def screencap(path: Path) -> None:
    path.write_bytes(subprocess.run(["adb", "-s", AVDS[DEVICE]["serial"], "exec-out", "screencap", "-p"], capture_output=True, timeout=30, check=False).stdout)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--caption", required=True)
    args = ap.parse_args()
    api = Copy(API, REPO / "data" / "api")
    t0 = time.time()
    out = REPO / "logs" / "ig" / f"{datetime.fromtimestamp(t0):%Y%m%d-%H%M%S}"
    out.mkdir(parents=True, exist_ok=True)
    marks: dict[str, float] = {}
    mark = lambda k: marks.setdefault(k, round(time.time() - t0, 1))  # noqa: E731
    say = lambda s: print(f"[{time.time() - t0:6.1f}s] {s}", flush=True)  # noqa: E731

    rules = api.get("/api/settings/approvals")["rules"]
    if "never" in (rules.get("routines") or {}).values() or (rules.get("apps") or {}).get(IG) == "never":
        say(f"STOP: a standing approval could let Share through: {rules}")
        return 1

    # 1. The link to the cloud phone.
    sent = mcp("send_to_phone", {"file": args.url, "device": DEVICE})
    mark("sent")
    say(f"send_to_phone: {sent}")
    if sent.get("status") != "sent":
        return 1

    # 2. The task the offer's Yes would start.
    goal = fill(HANDOFF_TEMPLATES["instagram"]["goal"], {"caption": args.caption})
    started = mcp("run_task", {"goal": goal})
    tid = started["task_id"]
    t_start = time.time()
    mark("task_started")
    say(f"run_task: {tid} {started.get('status')}; heads_up={started.get('heads_up')}")

    # 3. Follow it; decline Share.
    seen: dict[str, dict[str, Any]] = {}
    status, pauses, share = None, [], None
    while time.time() - t0 < 1800:
        got = api.get(f"/api/tasks/{tid}")
        task = got["task"]
        if task["status"] != status:
            status = task["status"]
            mark(status)
            say(f"task {status}{': ' + str(task.get('detail'))[:160] if task.get('detail') else ''}")
            if status in PAUSED and not ended(task):
                pauses.append({"at_s": round(time.time() - t0, 1), "status": status, "detail": task.get("detail")})
                say("PAUSED: the user takes over in the live view (Real-app phone), then hands back")
        for a in got["approvals"]:
            if a["id"] in seen:
                continue
            seen[a["id"]] = a
            if is_share(a) and a["status"] == "pending":
                share = a
                mark("share_asked")
                screencap(out / "new-reel.png")
                shot = api.http.get(f"/api/approvals/{a['id']}/shot")
                if shot.status_code == 200:
                    (out / "share-approval.jpg").write_bytes(shot.content)
                api.decline(a["id"])
                mark("share_declined")
                say(f"Share asked ({a.get('description')!r}, reasons {a.get('reasons')}): screen saved, declined. Nothing is posted.")
            elif is_share(a):
                say(f"STOP: Share was {a['status']} by {a.get('decided_by')} before this script saw it: check envoy3955's profile")
            else:
                mark(f"asked_{len(seen)}")
                say(f"NOT Share, left to the user in the app: {a.get('description')!r} {a.get('status')} reasons={a.get('reasons')}")
        if ended(task):
            break
        time.sleep(1)
    got = api.get(f"/api/tasks/{tid}")
    task, steps, approvals = got["task"], got["steps"], got["approvals"]
    mark("end")

    failures = []
    if task["status"] == "done":
        failures.append("THE TASK ENDED DONE: check envoy3955's profile now")
    if share is None:
        failures.append("Share was never asked")
    auto = [s.get("text") for s in steps if s.get("kind") == "approval" and "without asking" in (s.get("text") or "")]
    if auto:
        failures.append(f"approved without asking: {auto}")

    from devices.android import AndroidDevice
    from instagram_take import leave_composer
    try:
        cleanup = leave_composer(AndroidDevice(AVDS[DEVICE]["serial"]).connect())
    except Exception as e:  # noqa: BLE001 - the run's result stands without it
        cleanup = [f"not cleaned up: {type(e).__name__}: {e}"[:200]]

    yes_to_share = round(marks["share_asked"] - marks["task_started"], 1) if "share_asked" in marks else None
    result = {"time": datetime.fromtimestamp(t0).isoformat(timespec="seconds"), "url": args.url, "caption": args.caption, "goal": goal,
              "device": DEVICE, "send_to_phone": sent, "heads_up": started.get("heads_up"),
              "task": {k: task.get(k) for k in ("id", "status", "routine", "model_calls", "cost_usd", "traces", "detail", "source", "device", "result")},
              "steps": [{k: s.get(k) for k in ("seq", "kind", "text", "reason")} for s in steps],
              "approvals": [{k: a.get(k) for k in ("description", "reasons", "status", "decided_by")} for a in approvals],
              "pauses": pauses, "marks_s": marks, "start_to_share_s": yes_to_share,
              "spent": spent(tid, t_start - 5), "cleanup": cleanup, "ok": not failures, "failures": failures}
    (out / "run.json").write_text(json.dumps(result, indent=1, default=str))
    say(f"saved {out.relative_to(REPO)}: start→Share {yes_to_share} s, {result['spent']['model_calls']} model calls, ${result['spent']['cost_usd']}")
    if failures:
        print("\n" + "\n".join(f"FAIL: {x}" for x in failures), flush=True)
        return 2
    say("OK: declined at Share")
    return 0


if __name__ == "__main__":
    sys.exit(main())
