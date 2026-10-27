"""Envoy's API: tasks, the event stream, approvals, takeover and the live view, chat, memory, routines, triggers, the MCP
server and the web app, all in one process (`python -m api`, port 8700).

Two kinds of caller:
- **You**, through the web app: a session (cookie, or the same token as a bearer header for scripts). Only a session can
  approve, take over or edit memory. The login link with the session token is printed when the server starts.
- **AI clients**, through `/mcp` with the MCP bearer token. They can start and follow tasks and use memory, never approve.

Browser POSTs must carry an `X-Envoy` header, which another site can't add without a CORS preflight (refused), so a
page elsewhere can't make your browser approve something.
"""

from __future__ import annotations

import asyncio
import hmac
import os
import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from memory.retrieval import Retriever
from memory.store import MemoryStore
from models.adapter import ModelAdapter
from routines.model import dump_yaml
from routines.store import RoutineStore

from api.chat import chat
from api.devices import DevicePool
from api.events import EventBus
from api.live import live_view
from api.runner import SHOTS, TaskRunner
from api.scheduler import Scheduler
from api.store import API_DIR, REPO, TaskStore

PORT = int(os.environ.get("ENVOY_PORT", "8700"))
PROFILES = {"demo": REPO / "data" / "demo" / "memory.db", "real": REPO / "data" / "memory.db"}
WEB_OUT = REPO / "web" / "out"
COOKIE = "envoy_session"


def session_token() -> str:
    path = API_DIR / "session_token"
    if not path.exists():
        API_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_urlsafe(32))
        path.chmod(0o600)
    return path.read_text().strip()


@dataclass
class Ctx:
    tasks: TaskStore
    bus: EventBus
    pool: DevicePool
    memory: MemoryStore
    routines: RoutineStore
    adapter: ModelAdapter
    runner: TaskRunner
    scheduler: Scheduler
    profile: str


def build(profile: str | None = None, *, adapter: ModelAdapter | None = None, memory: MemoryStore | None = None,
          tasks: TaskStore | None = None, routines: RoutineStore | None = None, scheduler_every_s: float = 10) -> tuple[FastAPI, Ctx]:
    profile = profile or os.environ.get("ENVOY_PROFILE", "demo")
    bus = EventBus()
    tasks = tasks or TaskStore()
    if memory is None:
        PROFILES[profile].parent.mkdir(parents=True, exist_ok=True)
        memory = MemoryStore(PROFILES[profile])
    routines = routines or RoutineStore()
    adapter = adapter or ModelAdapter()
    pool = DevicePool(bus)
    runner = TaskRunner(tasks, bus, pool, memory, routines, adapter)
    scheduler = Scheduler(tasks, memory, runner.start, bus, routines, every_s=scheduler_every_s)
    ctx = Ctx(tasks, bus, pool, memory, routines, adapter, runner, scheduler, profile)
    memory.subscribe(lambda ev: bus.publish("memory", event=ev))
    token = session_token()

    from mcp_server.server import build_mcp, mcp_app
    from mcp_stub.common import bearer_token
    from mcp_stub.middleware import BearerAuthLogMiddleware
    mcp_inner = mcp_app(build_mcp(ctx, PORT), PORT)
    mcp = BearerAuthLogMiddleware(mcp_inner, token=bearer_token(), log_path=REPO / "logs" / "mcp.jsonl", server="mcp")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        bus.bind(asyncio.get_running_loop())
        runner.loop = asyncio.get_running_loop()
        scheduler.run_in_background()
        async with mcp_inner.router.lifespan_context(mcp_inner):
            yield

    app = FastAPI(title="Envoy", lifespan=lifespan)
    app.state.ctx = ctx

    # ---- auth ------------------------------------------------------------------------------------

    def is_session(request: Request | WebSocket) -> bool:
        got = request.cookies.get(COOKIE) or ""
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            got = got or auth[7:]
        return bool(got) and hmac.compare_digest(got, token)

    def session(request: Request) -> None:
        if not is_session(request):
            raise HTTPException(401, "sign in to Envoy with the link the server printed")
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.cookies.get(COOKIE) and request.headers.get("x-envoy") != "1":
            raise HTTPException(403, "missing X-Envoy header")

    @app.get("/login")
    def login(k: str = "") -> Response:
        if not k or not hmac.compare_digest(k, token):
            return HTMLResponse("<p>That link is not valid. Use the one the Envoy server printed.</p>", status_code=401)
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie(COOKIE, token, httponly=True, samesite="strict", max_age=30 * 86400)
        return resp

    # ---- state and tasks -----------------------------------------------------------------------

    @app.get("/api/state", dependencies=[Depends(session)])
    def state() -> dict[str, Any]:
        return {"profile": ctx.profile, "devices": pool.status(), "tasks": tasks.list(20), "approvals": tasks.approvals("pending"),
                "routines": len(routines.active()), "memory": {"entities": len(memory.entities())}}

    @app.post("/api/tasks", dependencies=[Depends(session)])
    async def create_task(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        goal = (body.get("goal") or "").strip()
        if not goal and not body.get("routine"):
            raise HTTPException(400, "goal or routine needed")
        if body.get("routine"):
            goal = goal or routines.get(body["routine"]).intent
        return runner.start(goal, body.get("source", "web"), routine=body.get("routine"), inputs=body.get("inputs") or {})

    @app.get("/api/tasks", dependencies=[Depends(session)])
    def list_tasks(limit: int = 50) -> list[dict[str, Any]]:
        return tasks.list(limit)

    @app.get("/api/tasks/{tid}", dependencies=[Depends(session)])
    def get_task(tid: str) -> dict[str, Any]:
        task = tasks.get(tid)
        if task is None:
            raise HTTPException(404)
        return {"task": task, "steps": tasks.steps(tid), "approvals": [_public(a) for a in tasks.approvals(task_id=tid)]}

    @app.post("/api/tasks/{tid}/stop", dependencies=[Depends(session)])
    def stop_task(tid: str) -> dict[str, Any]:
        return {"stopped": runner.stop(tid)}

    @app.get("/api/shots/{tid}/{name}", dependencies=[Depends(session)])
    def shot(tid: str, name: str) -> FileResponse:
        path = (SHOTS / tid / name).resolve()
        if SHOTS.resolve() not in path.parents or not path.exists():
            raise HTTPException(404)
        return FileResponse(path, media_type="image/jpeg")

    # ---- approvals (only your session decides; GET never decides) -------------------------------

    def _public(a: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in a.items() if k != "nonce"}

    @app.get("/api/approvals", dependencies=[Depends(session)])
    def list_approvals(status: str | None = None) -> list[dict[str, Any]]:
        return [_public(a) for a in tasks.approvals(status)]

    @app.get("/api/approvals/{aid}", dependencies=[Depends(session)])
    def get_approval(aid: str) -> dict[str, Any]:
        a = tasks.approval(aid)
        if a is None:
            raise HTTPException(404)
        task = tasks.get(a["task_id"]) or {}
        return {**a, "goal": task.get("goal"), "task_status": task.get("status")}  # the nonce goes to your session's page only

    @app.get("/api/approvals/{aid}/shot", dependencies=[Depends(session)])
    def approval_shot(aid: str) -> FileResponse:
        a = tasks.approval(aid)
        if not a or not a.get("screenshot"):
            raise HTTPException(404)
        return FileResponse(API_DIR / "approvals" / a["screenshot"], media_type="image/jpeg")

    @app.post("/api/approvals/{aid}", dependencies=[Depends(session)])
    def decide(aid: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        a = tasks.approval(aid)
        if a is None:
            raise HTTPException(404)
        if not hmac.compare_digest(str(body.get("nonce", "")), a["nonce"] or ""):
            raise HTTPException(403, "this approval page is out of date: reload it")
        if a["status"] != "pending":
            raise HTTPException(409, f"already {a['status']}")
        approver = runner.approvers.get(a["task_id"])
        if approver is None:
            raise HTTPException(409, "the task is no longer waiting")
        rec = approver.decide(aid, body.get("decision") == "approve", by="user")
        if rec is None:
            raise HTTPException(409, "already decided")
        return _public(rec)

    # ---- phones: takeover, hand back, live view -------------------------------------------------

    @app.get("/api/devices", dependencies=[Depends(session)])
    def devices() -> list[dict[str, Any]]:
        return pool.status()

    @app.post("/api/devices/{avd}/takeover", dependencies=[Depends(session)])
    def take_over(avd: str) -> dict[str, Any]:
        if avd not in pool.leases:
            raise HTTPException(404)
        lease = pool.take_over(avd)
        if lease.task_id:
            runner._set(lease.task_id, status="taken_over")
        return lease.state()

    @app.post("/api/devices/{avd}/handback", dependencies=[Depends(session)])
    def hand_back(avd: str) -> dict[str, Any]:
        if avd not in pool.leases:
            raise HTTPException(404)
        lease = pool.hand_back(avd)
        if lease.task_id:
            runner._set(lease.task_id, status="running", waiting_for=None)
        return lease.state()

    @app.websocket("/api/live/{avd}")
    async def live(ws: WebSocket, avd: str, fps: float = 10, width: int = 540) -> None:
        if not is_session(ws):
            await ws.close(code=4401)
            return
        await live_view(ws, avd, pool, fps=min(fps, 20), width=max(240, min(width, 1080)))

    @app.websocket("/api/events")
    async def events(ws: WebSocket, after: int = 0) -> None:
        if not is_session(ws):
            await ws.close(code=4401)
            return
        await ws.accept()
        try:
            async for ev in bus.subscribe(after):
                await ws.send_json(ev)
        except (WebSocketDisconnect, RuntimeError):
            pass

    # ---- chat ----------------------------------------------------------------------------------

    @app.post("/api/chat", dependencies=[Depends(session)])
    async def chat_route(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        msg = (body.get("message") or "").strip()
        if not msg:
            raise HTTPException(400, "message needed")
        out = await chat(msg, adapter=adapter, memory=memory, runner=runner, routines=routines)
        bus.publish("chat", message=msg, reply=out.get("reply"), kind=out.get("kind"), task_id=(out.get("task") or {}).get("id"))
        return out

    # ---- memory --------------------------------------------------------------------------------

    @app.get("/api/memory/graph", dependencies=[Depends(session)])
    def graph() -> dict[str, Any]:
        nodes, edges, seen = [], [], set()
        for e in memory.entities():
            facts = memory.current_facts(e["id"])
            nodes.append({"id": e["id"], "type": e["type"], "name": e["name"] or e["type"], "facts": len(facts),
                          "stale": any(memory.is_stale(f, e["type"]) for f in facts), "user_edited": bool(e.get("user_edited"))})
            for x in memory.edges_of(e["id"]):
                if x["id"] not in seen and not x.get("retired_at"):
                    seen.add(x["id"])
                    edges.append({"id": x["id"], "source": memory.resolve(x["from_entity"]), "target": memory.resolve(x["to_entity"]), "relation": x["relation"]})
        ids = {n["id"] for n in nodes}
        return {"nodes": nodes, "edges": [x for x in edges if x["source"] in ids and x["target"] in ids]}

    @app.get("/api/memory/entity/{eid}", dependencies=[Depends(session)])
    def entity(eid: str) -> dict[str, Any]:
        e = memory.entity(eid)
        if e is None:
            raise HTTPException(404)
        r = Retriever(memory)
        hist = []
        for f in memory.history(eid):
            hist.append({**{k: f[k] for k in ("id", "attribute", "value", "valid_from", "valid_to", "recorded_at", "retired_at", "conflict", "author")},
                         "current": f["valid_to"] is None and not f["retired_at"] and not f["conflict"],
                         "stale": memory.is_stale(f, e["type"]),
                         "sources": [{"id": s["source"], "where": r.where(s["source"])} for s in memory.sources_of(f["id"])]
                         or ([{"id": f["source"], "where": r.where(f["source"])}] if f["source"] else [])})
        links = []
        for x in memory.edges_of(eid):
            other = x["to_entity"] if memory.resolve(x["from_entity"]) == eid else x["from_entity"]
            o = memory.entity(other) or {}
            links.append({"relation": x["relation"], "id": other, "type": o.get("type"), "name": o.get("name")})
        return {"entity": e, "facts": hist, "links": links}

    @app.post("/api/memory/entity/{eid}/fact", dependencies=[Depends(session)])
    def edit_fact(eid: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        if memory.entity(eid) is None or not body.get("attribute"):
            raise HTTPException(400)
        res = memory.user_edit(eid, body["attribute"], str(body.get("value", "")))
        memory.commit()
        return {"result": getattr(res, "kind", str(res))}

    @app.delete("/api/memory/source/{sid}", dependencies=[Depends(session)])
    def delete_source(sid: str) -> dict[str, Any]:
        out = memory.delete_source(sid)
        memory.commit()
        return out

    @app.get("/api/memory/search", dependencies=[Depends(session)])
    def search(q: str = Query(...)) -> dict[str, Any]:
        n = Retriever(memory).notes(q)
        return {"markdown": n.markdown, "entities": n.entities, "stale": n.stale}

    @app.get("/api/memory/events", dependencies=[Depends(session)])
    def memory_events(after: int = 0) -> list[dict[str, Any]]:
        return memory.events(after)[-300:]

    # ---- routines and triggers -----------------------------------------------------------------

    @app.get("/api/routines", dependencies=[Depends(session)])
    def list_routines() -> list[dict[str, Any]]:
        out = []
        for name in routines.names():
            idx = routines.index(name)
            try:
                r = routines.get(name)
            except Exception:  # noqa: BLE001
                continue
            runs = idx.get("runs", [])
            ok = sum(1 for x in runs if x.get("status") in ("done", "agent_done"))
            out.append({"name": name, "app": r.app, "intent": r.intent, "active": idx.get("active"), "versions": idx.get("versions", []),
                        "inputs": {k: v.description for k, v in r.inputs.items()}, "outputs": r.outputs, "steps": len(r.steps),
                        "runs": len(runs), "success": round(ok / len(runs), 2) if runs else None,
                        "recompile": idx.get("recompile", False)})
        return out

    @app.get("/api/routines/{name}", dependencies=[Depends(session)])
    def get_routine(name: str, version: int | None = None) -> dict[str, Any]:
        r = routines.get(name, version)
        return {"index": routines.index(name), "yaml": dump_yaml(r)}

    @app.get("/api/triggers", dependencies=[Depends(session)])
    def list_triggers() -> list[dict[str, Any]]:
        return [{**t, "next": scheduler.next_runs(t)} for t in tasks.triggers()]

    @app.post("/api/triggers", dependencies=[Depends(session)])
    def add_trigger(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            return scheduler.add(body.get("kind", ""), body.get("name", "trigger"), body.get("spec") or {}, body.get("action") or {})
        except (ValueError, KeyError) as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/api/triggers/{tid}", dependencies=[Depends(session)])
    def toggle_trigger(tid: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        tasks.update_trigger(tid, enabled=1 if body.get("enabled") else 0)
        return tasks.trigger(tid) or {}

    @app.delete("/api/triggers/{tid}", dependencies=[Depends(session)])
    def delete_trigger(tid: str) -> dict[str, Any]:
        tasks.delete_trigger(tid)
        return {"deleted": tid}

    # ---- the web app ---------------------------------------------------------------------------

    @app.get("/healthz")
    def health() -> dict[str, Any]:
        return {"ok": True, "profile": ctx.profile}

    if WEB_OUT.exists():
        app.mount("/", StaticFiles(directory=WEB_OUT, html=True), name="web")
    else:
        @app.get("/")
        def no_web() -> HTMLResponse:
            return HTMLResponse("<p>Envoy API is running. Build the web app: <code>cd web && npm run build</code></p>")

    async def dispatch(scope: dict, receive: Any, send: Any) -> None:
        """/mcp goes to the MCP server (its own bearer token); everything else to the API and web app."""
        if scope["type"] == "http" and (scope["path"] == "/mcp" or scope["path"].startswith("/mcp/")):
            await mcp(scope, receive, send)
        else:
            await app(scope, receive, send)

    ctx.asgi = dispatch  # type: ignore[attr-defined]
    return app, ctx


def login_url() -> str:
    return f"http://127.0.0.1:{PORT}/login?k={session_token()}"


__all__ = ["build", "login_url", "PORT"]
