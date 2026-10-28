"""A short device check of the cross-app follow-ups on envoy-real (one run each, not a timing study):

  META_DAILY_COST_CAP_USD=2 uv run --project backend python eval/smoke_crossapp.py --data /tmp/crossapp-smoke

1. a plain single-app task (Starbucks calories, the way the web app starts one);
2. R1 through chat (Starbucks calories + DoorDash's first latte place);
3. the same question through MCP `run_task` over HTTP, with the API copy's own bearer token;
4. a plain single-app task on DoorDash (its first latte place).

For each task it checks that every step shown in the task view has its picture (taken in a thread now) and that the
steps are in the order of the run's trace, and it counts the "Done" pushes Envoy decides to send (the API copy has no
push subscription, so nothing leaves this Mac; the pushes are recorded where Pusher sends them). The API copy, its
data and every rule are those of eval/run_crossapp.py: every approval declined, apps closed after each task.

Results: eval/results/crossapp/smoke.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import run_crossapp as rc  # puts backend/ on the path

SINGLE = "How many calories are in a Caffè Latte at Starbucks?"
SINGLE_DD = "What's the first place DoorDash shows for a latte?"
REAL = rc.SERIALS["envoy-real"]
SHOWN = ("action", "routine_step")  # the steps that carry a picture


def check_steps(ctx: Any, tid: str) -> dict[str, Any]:
    """Pictures on the steps that should have one, and the steps in the order the run traced them."""
    from agent.trace import RUNS
    from api.runner import SHOTS, describe
    stored = [s for s in ctx.tasks.steps(tid) if s["kind"] in SHOWN]
    traced = []
    for d in sorted(RUNS.glob(f"{tid}-r*")):
        f = d / "steps.jsonl"
        for line in (f.read_text().splitlines() if f.exists() else []):
            got = describe(json.loads(line))
            if got and got["kind"] in SHOWN:
                traced.append([got["kind"], got["text"]])
    wanted = [s for s in stored if not s.get("secure")]
    pictured = [s for s in wanted if s.get("shot") and (SHOTS / s["shot"]).exists()]
    return {"steps": len(stored), "traced": len(traced), "with_picture": len(pictured), "secure": len(stored) - len(wanted),
            "in_trace_order": [[s["kind"], s["text"]] for s in stored] == traced,
            "seq_increasing": all(a["seq"] < b["seq"] for a, b in zip(stored, stored[1:])),
            "texts": [s["text"] for s in stored]}


def done_pushes(pushes: list[dict[str, Any]], ids: set[str]) -> list[dict[str, Any]]:
    return [p for p in pushes if p["kind"] == "task" and p["path"].split("task=")[-1] in ids]


def cross_summary(ctx: Any, pid: str, pushes: list[dict[str, Any]]) -> dict[str, Any]:
    kids = sorted((t for t in ctx.tasks.list(200) if t.get("parent") == pid), key=lambda t: t["created_at"])
    parent = ctx.tasks.get(pid)
    return {"parent_id": pid, "status": parent["status"], "answer": parent.get("result"),
            "parts": [{"task_id": k["id"], "app": k["app"], "routine": k.get("routine"), "status": k["status"], "result": k.get("result"),
                       "steps": check_steps(ctx, k["id"])} for k in kids],
            "task_pushes": done_pushes(pushes, {pid, *(k["id"] for k in kids)}),
            "approvals_requested": sum(len(ctx.tasks.approvals(task_id=k["id"])) for k in kids)}


async def wait_ended(ctx: Any, tid: str, limit: float = 600) -> None:
    t0 = time.time()
    while ctx.tasks.get(tid)["status"] not in rc.ENDED and time.time() - t0 < limit:
        await asyncio.sleep(0.2)
    try:
        await asyncio.wait_for(asyncio.shield(ctx.runner.jobs[tid]), 300)  # memory writes
    except Exception:  # noqa: BLE001
        pass


def home(*apps: str) -> None:
    for a in apps:
        if a:
            rc.adb(REAL, "am", "force-stop", a)
    rc.adb(REAL, "input", "keyevent", "KEYCODE_HOME")


async def single(ctx: Any, pushes: list[dict[str, Any]], goal: str = SINGLE) -> dict[str, Any]:
    t0 = time.time()
    task = ctx.runner.start(goal, "web")
    await wait_ended(ctx, task["id"])
    t = ctx.tasks.get(task["id"])
    home(t.get("app"))
    return {"task_id": t["id"], "goal": goal, "app": t.get("app"), "routine": t.get("routine"), "status": t["status"], "result": t.get("result"),
            "wall_s": round(time.time() - t0, 1), "steps": check_steps(ctx, t["id"]), "task_pushes": done_pushes(pushes, {t["id"]}),
            "approvals_requested": len(ctx.tasks.approvals(task_id=t["id"]))}


async def through_chat(ctx: Any, watch: Any, pushes: list[dict[str, Any]]) -> dict[str, Any]:
    run = await rc.run_one(ctx, watch, "R1", "parallel")
    if not run.get("parent_id"):
        return {"error": run.get("error"), "chat": run.get("chat")}
    return {"question": run["message"], "wall_s": run["wall_s"], **cross_summary(ctx, run["parent_id"], pushes)}


async def through_mcp(ctx: Any, port: int, pushes: list[dict[str, Any]]) -> dict[str, Any]:
    import httpx
    message = rc.QUESTIONS["R1"][0]
    t0 = time.time()
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"http://127.0.0.1:{port}/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                                                "params": {"name": "run_task", "arguments": {"goal": message}}},
                         headers={"Authorization": f"Bearer {os.environ['MCP_BEARER_TOKEN']}", "Accept": "application/json, text/event-stream",
                                  "MCP-Protocol-Version": "2025-11-25"})
    body = r.json()
    try:
        reply = json.loads(body["result"]["content"][0]["text"])
    except Exception:  # noqa: BLE001
        return {"http_status": r.status_code, "error": str(body)[:500]}
    out: dict[str, Any] = {"question": message, "http_status": r.status_code, "reply": reply}
    tid = reply.get("task_id")
    if tid:
        await wait_ended(ctx, tid)
        kids = [t for t in ctx.tasks.list(200) if t.get("parent") == tid]
        home(*(k.get("app") for k in kids))
        out.update({"wall_s": round(time.time() - t0, 1), **cross_summary(ctx, tid, pushes)})
    return out


async def main_async(args: argparse.Namespace) -> None:
    import uvicorn
    from api.app import build
    from api.store import TaskStore
    from memory.store import MemoryStore

    data = Path(args.data).resolve()
    shutil.rmtree(data, ignore_errors=True)
    (data / "api").mkdir(parents=True)
    token = data / "api" / "session_token"
    token.write_text(secrets.token_urlsafe(32))
    token.chmod(0o600)
    app, ctx = build("demo", memory=MemoryStore(data / "memory.db"), routines=rc.library(data / "routines"),
                     tasks=TaskStore(data / "api" / "envoy.db"), scheduler_every_s=3600)
    pushes: list[dict[str, Any]] = []
    send = ctx.pusher.notify

    def recorded(kind: str, title: str, body: str, path: str, **kw: Any) -> Any:
        pushes.append({"time": time.time(), "kind": kind, "title": title, "path": path})
        return send(kind, title, body, path, **kw)
    ctx.pusher.notify = recorded  # on_event calls self.notify: every push Envoy decides to send goes through here
    # The API's own entry point: it sends /mcp to the MCP server (with its bearer token) and the rest to the app.
    server = uvicorn.Server(uvicorn.Config(getattr(ctx, "asgi", app), host="127.0.0.1", port=args.port, log_level="warning"))
    serving = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.1)
    print(f"API copy on http://127.0.0.1:{args.port}", flush=True)
    watch = rc.Watch(ctx)
    decliner = asyncio.create_task(watch.decline_forever())
    await ctx.pool.device("envoy-real")
    home()
    t_all = time.time()
    earlier = json.loads((rc.OUT / "smoke.json").read_text()) if args.skip and (rc.OUT / "smoke.json").exists() else {}
    out: dict[str, Any] = {k: v for k, v in earlier.items() if k not in ("meta", "earlier_meta")}  # --skip: keep the checks already run
    for name, step in (("single_app", lambda: single(ctx, pushes)), ("r1_chat", lambda: through_chat(ctx, watch, pushes)),
                       ("r1_mcp", lambda: through_mcp(ctx, args.port, pushes)),
                       ("single_app_doordash", lambda: single(ctx, pushes, SINGLE_DD))):
        if name in args.skip:
            continue
        out[name] = await step()
        print(name, json.dumps(out[name], default=str, ensure_ascii=False)[:900], flush=True)
        spent = rc.costs_between(t_all - 1, time.time() + 1)
        meta = {"date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "phone": "envoy-real", "calls": spent["calls"], "usd": spent["usd"],
                "commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=rc.REPO).stdout.strip(),
                "declined": watch.declined, "pushes": pushes}
        rc.OUT.mkdir(parents=True, exist_ok=True)
        extra = {"earlier_meta": [*earlier.get("earlier_meta", []), earlier["meta"]]} if earlier.get("meta") else {}
        (rc.OUT / "smoke.json").write_text(json.dumps({"meta": meta, **extra, **out}, indent=1, default=str, ensure_ascii=False))
    decliner.cancel()
    server.should_exit = True
    await serving


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="a folder for the API copy's tasks, memory and routines (wiped first)")
    ap.add_argument("--port", type=int, default=8713)
    ap.add_argument("--skip", default="", help="comma-separated: single_app, r1_chat, r1_mcp, single_app_doordash")
    args = ap.parse_args()
    args.skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    os.environ["ENVOY_API_DIR"] = str(Path(args.data).resolve() / "api")
    os.environ["ENVOY_PORT"] = str(args.port)
    os.environ["ENVOY_PUBLIC_URL"] = f"http://127.0.0.1:{args.port}"
    os.environ.setdefault("MCP_BEARER_TOKEN", secrets.token_urlsafe(24))
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
