"""Envoy's API: tasks, the event stream, approvals, takeover and the live view, chat, memory, routines, triggers, the MCP
server and the web app, all in one process (`python -m api`, port 8700).

Kinds of caller (api/auth.py):
- **You**, through the web app: a session (cookie, or the same token as a bearer header for scripts). Only a session can
  approve, take over or edit memory. The login link with the session token is printed when the server starts.
- **Your paired devices** (the iPhone's Home Screen app, Phase 5): their own session, from a pairing code shown on the Mac.
- **Device tokens with a scope** (Shortcuts): "Send to Envoy" can upload images, nothing else; "Ask Envoy" (Siri) can
  only ask what a chat message can, and its irreversible steps wait for your OK (api/siri.py).
- **AI clients**, through `/mcp`: Muse with the MCP bearer token, every other agent with a key of its own (Settings ›
  Agents, api/agents.py) that opens only the tool groups it was given. They can start and follow tasks and use memory,
  never approve.

The API answers only to the names it is served on (127.0.0.1, localhost, its Tailscale Serve name), and WebSockets
check their Origin, so a page on another name can't reach it (DNS rebinding).

Browser POSTs must carry an `X-Envoy` header, which another site can't add without a CORS preflight (refused), so a
page elsewhere can't make your browser approve something.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import re
import secrets
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date
from typing import Any

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from memory.app_notes import AppNotes
from memory.retrieval import Retriever
from memory.store import MemoryStore
from memory.types import NOT_ABOUT_YOU
from memory.usual import MAX_ORDER, MAX_PLACE, Usual, remember as remember_usual
from models.adapter import ModelAdapter
from routines.model import dump_yaml
from routines.store import RoutineStore

from api import routine_view
from api.agents import agents_router
from api.alerts import ChangeAlerts
from api.autofill import signin_router
from api.auth import Auth, Caller, allowed_hosts, public_url, tunnel_hosts
from api.briefing import build_briefing
from api.chat import chat
from api.crossapp import CrossApp
from api.devices import DevicePool
from api.events import EventBus
from api.handoff import DOOR, Handoff, handoff_router
from api.live import live_view
from api.notifications import NotificationWatcher, notifications_router
from api.offers import Offers, offers_router
from api.recurring import Recurring
from api.repeats import Repeats
from api.push import Pusher, VapidKeys
from api.runner import SHOTS, TaskRunner
from api.scheduler import Scheduler, check_alert, check_ask
from api.sharing import Sharing, sharing_router
from api.siri import siri_router
from api.store import API_DIR, REPO, TaskStore, new_id
from api.task_files import FILES, TaskFiles, files_router
from api.teach import Teacher, TeachError
from api.voice import voice_session

PORT = int(os.environ.get("ENVOY_PORT", "8700"))
PROFILES = {"demo": REPO / "data" / "demo" / "memory.db", "real": REPO / "data" / "memory.db"}
# The demo world's date, for "my flight" and "my trip" only. SkyLark has no clock and its bookings are fixed (Chicago SL 482 on
# Oct 30, 2026 6:10 AM, then Denver on Nov 14), so on the real calendar its next trip would move to Denver from Oct 31 while
# the app still shows Chicago first. Fact ages, freshness, the scheduler and every other clock stay real; so does the real profile.
WORLD_DATES = {"demo": date(2026, 10, 29)}
WEB_OUT = REPO / "web" / "out"
LOGS = REPO / "logs"
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
    auth: Any = None
    pusher: Any = None
    public: str = ""
    alerts: Any = None
    offers: Any = None


def build(profile: str | None = None, *, adapter: ModelAdapter | None = None, memory: MemoryStore | None = None,
          tasks: TaskStore | None = None, routines: RoutineStore | None = None, scheduler_every_s: float = 10) -> tuple[FastAPI, Ctx]:
    profile = profile or os.environ.get("ENVOY_PROFILE", "demo")
    bus = EventBus()
    tasks = tasks or TaskStore()
    if memory is None:
        PROFILES[profile].parent.mkdir(parents=True, exist_ok=True)
        memory = MemoryStore(PROFILES[profile], world_date=WORLD_DATES.get(profile))
    routines = routines or RoutineStore()
    adapter = adapter or ModelAdapter()
    pool = DevicePool(bus)
    pool.names = lambda: tasks.setting("phone_names", {}) or {}  # the names you gave your phones (Settings › Phones)
    runner = TaskRunner(tasks, bus, pool, memory, routines, adapter)
    runner.crossapp = CrossApp(runner, routines, memory, adapter)
    scheduler = Scheduler(tasks, memory, runner.start, bus, routines, every_s=scheduler_every_s)
    ctx = Ctx(tasks, bus, pool, memory, routines, adapter, runner, scheduler, profile)
    memory.subscribe(lambda ev: bus.publish("memory", event=ev))
    token = session_token()
    auth = Auth(tasks, token)
    public = public_url(PORT)
    hosts = allowed_hosts(PORT, public)
    pusher = Pusher(tasks, VapidKeys(API_DIR), public)
    bus.listeners.append(pusher.on_event)
    ctx.auth, ctx.pusher, ctx.public = auth, pusher, public
    alerts = ChangeAlerts(tasks, memory, pusher, bus, routines)  # a watcher's run pushes when it changed a remembered fact
    memory.subscribe(alerts.on_memory)
    bus.listeners.append(alerts.on_event)
    ctx.alerts = alerts
    ctx.offers = Offers(tasks, bus, runner, scheduler)  # "Should I…?" with a one-tap yes (api/offers.py)
    scheduler.offers = ctx.offers
    scheduler.repeats = Repeats(tasks, memory, ctx.offers, scheduler, routines)  # "Make this a habit?" (api/repeats.py)
    bus.listeners.append(scheduler.repeats.on_event)
    runner.recurring = Recurring(ctx.offers, scheduler, adapter)  # chat sets up recurring jobs, switched off (api/recurring.py)
    ctx.handoff = Handoff(tasks, pool, bus, offers=ctx.offers, runner=runner)  # type: ignore[attr-defined]  # files from the Mac to the phone (api/handoff.py)
    ctx.files = TaskFiles(tasks, runner, shots=API_DIR / "shots", approvals=API_DIR / "approvals",  # type: ignore[attr-defined]
                          log=LOGS / "files.jsonl")  # files back to the agent: get_file's download links (api/task_files.py)
    teacher = ctx.teacher = Teacher(pool, tasks, bus, routines, adapter, runner)  # type: ignore[attr-defined]  # you show a task once (api/teach.py)
    ctx.notifications = NotificationWatcher(tasks, pool, scheduler, bus)  # type: ignore[attr-defined]  # notifications on Envoy's phone (api/notifications.py)

    from mcp_server.server import build_mcp, mcp_app
    from mcp_stub.common import bearer_token
    from mcp_stub.middleware import BearerAuthLogMiddleware
    ctx.sharing = Sharing(tasks)  # type: ignore[attr-defined]  # which routines agents can call as tools (api/sharing.py)
    ctx.mcp = build_mcp(ctx, PORT, base=public)  # type: ignore[attr-defined]
    mcp_inner = mcp_app(ctx.mcp, PORT, extra_hosts=hosts)  # type: ignore[attr-defined]
    auth.mcp_token = bearer_token()  # Muse's key: every tool. Other agents' keys are in device_tokens (contract 2)
    mcp = BearerAuthLogMiddleware(mcp_inner, token=bearer_token(), log_path=LOGS / "mcp.jsonl", server="mcp", verify=auth.agent_for)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        bus.bind(asyncio.get_running_loop())
        runner.loop = asyncio.get_running_loop()
        scheduler.run_in_background()
        ctx.handoff.run_in_background()  # type: ignore[attr-defined]
        ctx.notifications.run_in_background()  # type: ignore[attr-defined]
        async with mcp_inner.router.lifespan_context(mcp_inner):
            yield

    app = FastAPI(title="Envoy", lifespan=lifespan)
    app.state.ctx = ctx

    # ---- auth ------------------------------------------------------------------------------------

    def caller(request: Request | WebSocket) -> Caller | None:
        got = request.cookies.get(COOKIE) or ""
        bearer = request.headers.get("authorization", "")
        if bearer.lower().startswith("bearer "):
            got = got or bearer[7:]
        return auth.check(got)

    def is_session(request: Request | WebSocket) -> bool:
        c = caller(request)
        return c is not None and c.is_session

    def csrf(request: Request) -> None:
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.cookies.get(COOKIE) and request.headers.get("x-envoy") != "1":
            raise HTTPException(403, "missing X-Envoy header")

    def session(request: Request) -> None:
        if not is_session(request):
            raise HTTPException(401, "sign in to Envoy with the link the server printed, or pair this device")
        csrf(request)

    def owner(request: Request) -> None:
        """This Mac's own session: pairing new devices and revoking them happen here."""
        c = caller(request)
        if c is None or c.kind != "owner":
            raise HTTPException(403, "do this from Envoy on your Mac")
        csrf(request)

    def https(request: Request) -> bool:
        return request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https"

    def set_session_cookie(resp: Response, request: Request, value: str, days: int) -> None:
        resp.set_cookie(COOKIE, value, httponly=True, samesite="strict", secure=https(request), max_age=days * 86400)

    @app.get("/login")
    def login(request: Request, k: str = "") -> Response:
        if not k or not hmac.compare_digest(k, token):
            return HTMLResponse("<p>That link is not valid. Use the one the Envoy server printed.</p>", status_code=401)
        resp = RedirectResponse("/", status_code=303)
        set_session_cookie(resp, request, token, 30)
        return resp

    # ---- pairing your iPhone, and device tokens ------------------------------------------------------

    @app.post("/api/pair/start", dependencies=[Depends(owner)])
    def pair_start() -> dict[str, Any]:
        return {**auth.start_pairing(), "url": public}

    @app.get("/api/pair/qr", dependencies=[Depends(owner)])
    def pair_qr() -> Response:
        """A QR code of Envoy's tailnet address (not a secret), so the iPhone's camera opens it in Safari."""
        import io as _io

        import segno
        buf = _io.BytesIO()
        segno.make(public + "/", error="m").save(buf, kind="svg", scale=6, border=2, dark="#1c1c1a")
        return Response(buf.getvalue(), media_type="image/svg+xml")

    @app.post("/api/pair")
    def pair(request: Request, body: dict[str, Any] = Body(...)) -> Response:
        if request.headers.get("x-envoy") != "1":
            raise HTTPException(403, "missing X-Envoy header")
        name = str(body.get("name") or "iPhone")[:60]
        got = auth.finish_pairing(str(body.get("code") or ""), name, request.headers.get("user-agent", ""))
        if got is None:
            raise HTTPException(403, "That code didn't work. Use the code on your Mac (it lasts 5 minutes).")
        resp = JSONResponse({"paired": True, "name": name})
        set_session_cookie(resp, request, got, 365)
        bus.publish("paired", name=name)
        return resp

    @app.get("/api/paired", dependencies=[Depends(session)])
    def paired(request: Request) -> dict[str, Any]:
        me = caller(request)
        return {"devices": auth.devices(), "push": pusher.subscriptions(), "me": {"kind": me.kind, "device_id": me.device_id, "name": me.name} if me else None}

    @app.delete("/api/paired/{did}", dependencies=[Depends(owner)])
    def unpair(did: str) -> dict[str, Any]:
        pusher.forget_device(did)
        return {"revoked": auth.revoke(did)}

    @app.post("/api/tokens", dependencies=[Depends(session)])
    def new_token(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        """A narrow token for a Shortcut: `photos` (upload images) or `code_test`. Shown once; it is not a session."""
        scope = body.get("scope")
        if scope not in ("photos", "code_test"):
            raise HTTPException(400, "scope must be photos or code_test")
        return {"token": auth.issue(scope, str(body.get("name") or f"Shortcut ({scope})")), "scope": scope, "upload_url": f"{public}/api/photos"}

    # ---- state and tasks -----------------------------------------------------------------------

    @app.get("/api/state", dependencies=[Depends(session)])
    def state(request: Request) -> dict[str, Any]:
        me = caller(request)
        return {"profile": ctx.profile, "devices": pool.status(), "tasks": tasks.list(20), "approvals": tasks.approvals("pending"),
                "routines": len(routines.active()), "memory": {"entities": sum(1 for e in memory.entities() if e["type"] not in NOT_ABOUT_YOU)}, "public_url": public,
                "me": {"kind": me.kind, "name": me.name} if me else None, "push_key": pusher.keys.public_key}

    @app.get("/api/briefing", dependencies=[Depends(session)])
    def briefing() -> dict[str, Any]:
        """Home's briefing: read only, no model call (api/briefing.py)."""
        return build_briefing(tasks, memory, routines, scheduler, alerts, offers=ctx.offers)

    @app.post("/api/tasks", dependencies=[Depends(session)])
    async def create_task(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        goal = (body.get("goal") or "").strip()
        if not goal and not body.get("routine"):
            raise HTTPException(400, "goal or routine needed")
        if body.get("routine"):
            goal = goal or routines.get(body["routine"]).intent
        phone = body.get("phone") if body.get("phone") not in (None, "", "auto") else None
        return runner.start(goal, "web", routine=body.get("routine"), inputs=body.get("inputs") or {}, phone=phone)

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

    @app.post("/api/tasks/{tid}/phone", dependencies=[Depends(session)])
    def answer_phone(tid: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        """Your answer to "Use your Android phone for this task?". Only your session (the Mac or a paired iPhone) answers;
        MCP, chat and Shortcuts can't."""
        me = caller(request)
        by = "you" if me is None or me.kind == "owner" else f"you on {me.name}"
        if not runner.answer_phone(tid, bool(body.get("allow")), by):
            raise HTTPException(409, "this task isn't waiting for your phone")
        return {"ok": True}

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
    def decide(aid: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
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
        me = caller(request)
        by = "user" if me is None or me.kind == "owner" else f"user on {me.name}"  # the audit log says which of your devices
        rec = approver.decide(aid, body.get("decision") == "approve", by=by)
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
        was = pool.leases[avd].user_control
        lease = pool.take_over(avd)
        if lease.task_id:
            if not was:  # kept in the task's history, not only its status
                runner._step(lease.task_id, {"kind": "note", "text": "taken over by you"})
            runner._set(lease.task_id, status="taken_over")
        return lease.state()

    @app.post("/api/devices/{avd}/handback", dependencies=[Depends(session)])
    def hand_back(avd: str) -> dict[str, Any]:
        if avd not in pool.leases:
            raise HTTPException(404)
        if avd in pool.recorders:
            raise HTTPException(409, "you're teaching Envoy on this phone: finish or cancel first")
        held = time.time() - pool.leases[avd].since if pool.leases[avd].user_control else None
        lease = pool.hand_back(avd)
        if lease.task_id:
            if held is not None:
                runner._step(lease.task_id, {"kind": "note", "text": f"handed back by you after {held:.0f} s"})
            runner._set(lease.task_id, status="running", waiting_for=None)
        return lease.state()

    # ---- teach mode: you do a task once through the live view, and it becomes a routine (api/teach.py) ---------

    async def teaching(call: Any) -> dict[str, Any]:
        try:
            return await call
        except TeachError as e:
            raise HTTPException(e.code, e.detail) from e

    def teach_device(body: dict[str, Any]) -> str:
        avd = body.get("device") or body.get("avd")
        if not isinstance(avd, str) or not avd:
            raise HTTPException(400, "which phone? (device)")
        return avd

    @app.post("/api/teach/start", dependencies=[Depends(session)])
    async def teach_start(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        """{device, goal, app?}: the phone goes into a teach-mode takeover and records what you do."""
        return await teaching(teacher.start(teach_device(body), str(body.get("goal") or ""), body.get("app") or None))

    @app.post("/api/teach/finish", dependencies=[Depends(session)])
    async def teach_finish(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        """{device, ok, answer?}: `ok` is your word that it worked (else nothing is kept); `answer` for a question."""
        return await teaching(teacher.finish(teach_device(body), body.get("ok") is True, str(body.get("answer") or "")))

    @app.post("/api/teach/cancel", dependencies=[Depends(session)])
    async def teach_cancel(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return await teaching(teacher.cancel(teach_device(body)))

    @app.get("/api/teach/{avd}", dependencies=[Depends(session)])
    def teach_status(avd: str) -> dict[str, Any]:
        return teacher.status(avd) or {"device": avd, "status": "none"}

    @app.post("/api/tasks/{tid}/learn", dependencies=[Depends(session)])
    async def learn_task(tid: str) -> dict[str, Any]:
        """"Make it a routine": a task the agent finished on a phone is compiled, replayed once strictly on that phone and
        saved, not shared (api/teach.py `learn_task`). The task's `learn` follows it; only your session can ask."""
        return await teaching(teacher.learn_task(tid))

    @app.websocket("/api/live/{avd}")
    async def live(ws: WebSocket, avd: str, fps: float = 10, width: int = 540, quality: int = 70) -> None:
        if not is_session(ws):
            await ws.close(code=4401)
            return
        await live_view(ws, avd, pool, fps=min(fps, 20), width=max(240, min(width, 1080)), quality=max(30, min(quality, 90)))

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
        source = "voice" if body.get("source") == "voice" else "chat"  # spoken or typed, both your own words
        out = await chat(msg, adapter=adapter, memory=memory, runner=runner, routines=routines, source=source)
        bus.publish("chat", message=msg, reply=out.get("reply"), kind=out.get("kind"), task_id=(out.get("task") or {}).get("id"), source=source)
        return out

    # ---- voice: push to talk, relayed to Muse Voice Transcribe (the key stays here) ------------------

    @app.websocket("/api/voice")
    async def voice(ws: WebSocket) -> None:
        if not is_session(ws):
            await ws.close(code=4401)
            return
        from models.adapter import CostMeter
        await voice_session(ws, api_key=getattr(adapter, "api_key", "") or os.environ.get("META_API_KEY", ""),
                            meter=getattr(adapter, "meter", None) or CostMeter())

    # ---- push notifications --------------------------------------------------------------------------

    @app.get("/api/push/key", dependencies=[Depends(session)])
    def push_key() -> dict[str, Any]:
        return {"key": pusher.keys.public_key}

    @app.post("/api/push/subscribe", dependencies=[Depends(session)])
    def push_subscribe(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        me = caller(request)
        try:
            return pusher.subscribe(body.get("subscription") or body, me.device_id if me else None, request.headers.get("user-agent", ""))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/api/push/unsubscribe", dependencies=[Depends(session)])
    def push_unsubscribe(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return {"removed": pusher.unsubscribe(str(body.get("endpoint") or ""))}

    @app.post("/api/push/test", dependencies=[Depends(session)])
    async def push_test() -> dict[str, Any]:
        futures = pusher.notify("test", "Envoy", "Notifications work. Approvals will arrive like this.", "/", urgency="high", ttl=600)
        results = [await asyncio.wrap_future(f) for f in futures]
        return {"sent": len(results), "results": results}

    @app.post("/api/push/receipt", dependencies=[Depends(session)])
    def push_receipt(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        shown = body.get("shown_at")
        return {"receipt": pusher.receipt(str(body.get("id") or ""), float(shown) / 1000 if shown else None)}

    # ---- photos and screenshots → memory -------------------------------------------------------------

    @app.get("/api/settings/photos", dependencies=[Depends(session)])
    def get_photo_settings() -> dict[str, Any]:
        return tasks.setting("photos", {"enabled": False, "scope": "screenshots"})

    @app.post("/api/settings/photos", dependencies=[Depends(session)])
    def set_photo_settings(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        value = {"enabled": bool(body.get("enabled")), "scope": "photos" if body.get("scope") == "photos" else "screenshots"}
        tasks.set_setting("photos", value)
        return value

    @app.post("/api/photos")
    async def photos(request: Request) -> dict[str, Any]:
        """Images you pick in the app (your session) or share with the Shortcut (a `photos` token, which can do nothing else)."""
        from memory.photos import ingest_photo, summary
        from memory.service import MemoryService
        from PIL import Image
        c = caller(request)
        if c is None or c.scope not in ("session", "photos"):
            raise HTTPException(401, "sign in, or use the Shortcut's device token")
        csrf(request)
        prefs = tasks.setting("photos", {"enabled": False, "scope": "screenshots"})
        if not prefs.get("enabled"):
            raise HTTPException(403, "Photos are off. Turn them on in Envoy's Settings.")
        ctype = request.headers.get("content-type", "")
        blobs: list[bytes] = []
        if ctype.startswith("multipart/form-data"):
            form = await request.form(max_part_size=25 * 1024 * 1024)
            for _, v in form.multi_items():
                if hasattr(v, "read"):
                    blobs.append(await v.read())
        else:
            blobs.append(await request.body())
        blobs = [b for b in blobs if b][:10]
        if not blobs:
            raise HTTPException(400, "no image")
        folder = API_DIR / "photos"
        folder.mkdir(parents=True, exist_ok=True)
        origin = "shortcut" if c.scope == "photos" else "picker"
        out = []
        for blob in blobs:
            if len(blob) > 25 * 1024 * 1024:
                raise HTTPException(413, "image too large")
            pid = new_id("photo")
            path = folder / f"{pid}.img"
            path.write_bytes(blob)
            path.chmod(0o600)
            try:
                with Image.open(path) as im:
                    im.verify()
            except Exception as e:  # noqa: BLE001
                path.unlink(missing_ok=True)
                raise HTTPException(400, "that isn't an image") from e
            svc = MemoryService(memory, adapter, data_scope="real")
            try:
                res = await ingest_photo(svc, path, photo_id=pid, origin=origin, device=c.name, allow_camera_photos=prefs.get("scope") == "photos")
            except Exception as e:  # noqa: BLE001 - the image is already deleted (ingest_photo's finally)
                out.append({"photo_id": pid, "error": f"{type(e).__name__}: {e}"[:300], "deleted": not path.exists()})
                continue
            rep = res.report
            item = {"photo_id": pid, "summary": summary(res, memory), "facts": rep.facts if rep else {}, "dropped": rep.dropped if rep else [],
                    "entities": sorted({memory.resolve(r.entity) for r in rep.resolved}) if rep else [], "lines": res.lines,
                    "redacted_lines": res.redacted_lines, "ocr_ms": res.ocr_ms, "model_ms": res.model_ms, "total_ms": res.timings.get("total_ms"),
                    "cost_usd": round(rep.cost_usd, 5) if rep else 0, "deleted": res.deleted, "skipped": res.skipped}
            out.append(item)
            bus.publish("photo", photo_id=pid, summary=item["summary"], origin=origin, entities=item["entities"])
        return {"results": out, "summary": " ".join(x.get("summary") or x.get("error", "") for x in out)}

    # ---- numbers the apps measure (live-view latency, voice turns) ------------------------------------

    @app.post("/api/metrics", dependencies=[Depends(session)])
    def metrics(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        me = caller(request)
        rec = {"time": time.time(), "device": me.name if me else "", **{k: v for k, v in list(body.items())[:40] if isinstance(v, (int, float, str, bool))}}
        path = LOGS / "client_metrics.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps(rec)[:4000] + "\n")
        return {"ok": True}

    # ---- sign-in codes: the Phase 5 test only (does an iOS automation reach us while the phone is locked?) --

    @app.post("/api/codes/test")
    async def code_test(request: Request) -> dict[str, Any]:
        c = caller(request)
        if c is None or c.scope not in ("session", "code_test"):
            raise HTTPException(401)
        raw = (await request.body())[:2000].decode("utf-8", "replace")
        # Only that a message arrived, and when: never the message, never the code.
        rec = {"time": time.time(), "event": "code_message", "device": c.name, "length": len(raw), "has_code_word": "code" in raw.lower(),
               "has_digits": any(ch.isdigit() for ch in raw)}
        path = LOGS / "code_test.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        bus.publish("code_test", **{k: v for k, v in rec.items() if k != "time"})
        return {"received": True}

    # ---- memory --------------------------------------------------------------------------------

    @app.get("/api/memory/graph", dependencies=[Depends(session)])
    def graph() -> dict[str, Any]:
        nodes, edges, seen = [], [], set()
        for e in memory.entities():
            if e["type"] in NOT_ABOUT_YOU:  # app notes have their own section
                continue
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

    @app.post("/api/memory/usual", dependencies=[Depends(session)])
    def add_usual(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        """Your usual order from a place, from the Memory page (memory/usual.py): place and order, and the app if you name it."""
        place, order, app_ = (" ".join(str(body.get(k) or "").split()) for k in ("place", "order", "app"))
        if not place or not order or len(place) > MAX_PLACE or len(order) > MAX_ORDER or len(app_) > MAX_PLACE:
            raise HTTPException(400, "a place and an order are needed")
        eid, known = remember_usual(memory, Usual(place, order, app_ or None), via="memory page")
        return {"entity": eid, "replaced": known}

    @app.delete("/api/memory/source/{sid}", dependencies=[Depends(session)])
    def delete_source(sid: str) -> dict[str, Any]:
        out = memory.delete_source(sid)
        memory.commit()
        return out

    @app.get("/api/memory/search", dependencies=[Depends(session)])
    def search(q: str = Query(...)) -> dict[str, Any]:
        n = Retriever(memory).notes(q)
        return {"markdown": n.markdown, "entities": n.entities, "stale": n.stale}

    @app.get("/api/app-notes", dependencies=[Depends(session)])
    def app_notes(app_: str | None = Query(None, alias="app"), retired: bool = False) -> dict[str, Any]:
        """Envoy's notes about each app (memory/app_notes.py), with where each was learned."""
        notes = AppNotes(memory)
        by_app: dict[str, list[dict[str, Any]]] = {}
        for n in notes.list(app_, include_retired=retired):
            by_app.setdefault(n.app, []).append({**n.to_json(), "sources": [
                {k: s.get(k) for k in ("task_id", "step", "outcome", "kind", "observed_at", "retired_by", "reason") if s.get(k) is not None}
                for s in n.sources]})
        return {"apps": [{"app": a, "notes": v} for a, v in sorted(by_app.items())]}

    @app.post("/api/app-notes/{nid}/retire", dependencies=[Depends(session)])
    def retire_app_note(nid: str) -> dict[str, Any]:
        notes = AppNotes(memory)
        if notes.get(nid) is None:
            raise HTTPException(404)
        return {"retired": notes.retire(nid, "retired by you", by="user")}

    @app.get("/api/memory/events", dependencies=[Depends(session)])
    def memory_events(after: int = 0) -> list[dict[str, Any]]:
        return memory.events(after)[-300:]

    # ---- settings: when Envoy asks before an irreversible step ---------------------------------------

    @app.get("/api/settings/approvals", dependencies=[Depends(session)])
    def get_approval_rules() -> dict[str, Any]:
        from api.preflight import step_label
        from api.runner import APP_NAMES
        from policy.approval_rules import MODES, ApprovalRules, involves_money
        rules = ApprovalRules.from_dict(tasks.setting("approval_rules"))
        apps = sorted({r.app for r in routines.active()} | set(APP_NAMES.values()))
        # money: an irreversible step that spends money always asks, whatever the routine's mode (approval_rules.decide
        # checks money first), so Settings offers no "Never ask" for it
        return {"rules": rules.to_dict(), "modes": list(MODES), "apps": apps,
                "routines": [{"name": r.routine, "app": r.app, "intent": r.intent,
                              "irreversible": any(s.risk == "irreversible" for s in r.steps),
                              "money": any(s.risk == "irreversible" and involves_money(step_label(s), "", r.app) for s in r.steps)}
                             for r in routines.active()]}

    @app.post("/api/settings/approvals", dependencies=[Depends(session)])
    def set_approval_rules(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        from policy.approval_rules import ApprovalRules
        rules = ApprovalRules.from_dict(body)  # unknown modes are dropped; "never" only for routines
        tasks.set_setting("approval_rules", rules.to_dict())
        bus.publish("settings", approvals=rules.to_dict())
        return rules.to_dict()

    # ---- settings: which apps run on your Android phone ----------------------------------------------

    @app.get("/api/settings/phones", dependencies=[Depends(session)])
    def get_phone_settings() -> dict[str, Any]:
        from api.routing import EMULATOR_REFUSED, known_apps
        apps, names = known_apps(tasks, routines)  # list_phones (MCP) reads the same list
        return {"phone_apps": tasks.setting("phone_apps", []) or [], "apps": apps, "emulator_refused": EMULATOR_REFUSED,
                "learned": tasks.setting("phone_apps_learned", {}) or {}, "names": names,
                "phones": [d for d in pool.status() if d["kind"] == "phone"]}

    @app.post("/api/settings/phones", dependencies=[Depends(session)])
    def set_phone_settings(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        apps = [str(a) for a in body.get("phone_apps") or [] if isinstance(a, str)][:50]
        tasks.set_setting("phone_apps", apps)
        # An app Envoy set to your phone (it blocked the emulator) that you untick goes back to the emulator for good.
        learned = {p: a for p, a in (tasks.setting("phone_apps_learned", {}) or {}).items() if p in apps}
        tasks.set_setting("phone_apps_learned", learned)
        return {"phone_apps": apps, "learned": learned}

    @app.post("/api/settings/phones/name", dependencies=[Depends(session)])
    def set_phone_name(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        """What Envoy calls a phone in offers, "Before I start" and its notes, word for word ("Envoy's phone"). An empty
        name goes back to "your <model>"."""
        did = str(body.get("id") or "")
        if not did.startswith("phone-"):
            raise HTTPException(400, "give a real phone's id (Settings › Phones)")
        name = re.sub(r"[\x00-\x1f\x7f\u202a-\u202e\u2066-\u2069]", "", str(body.get("name") or "")).strip()[:40]
        names = {k: v for k, v in (tasks.setting("phone_names", {}) or {}).items() if k != did}
        if name:
            names[did] = name
        tasks.set_setting("phone_names", names)
        if did in pool.phones:  # the next discovery reads the setting; the phone already seen takes the name now
            pool.phones[did].pop("name", None)
            if name:
                pool.phones[did]["name"] = name
        return {"id": did, "name": name or None, "names": names}

    # ---- routines and triggers -----------------------------------------------------------------

    app.include_router(sharing_router(ctx, session, ctx.mcp.agent_tools))  # type: ignore[attr-defined]  # first: /api/routines/{name} would take "sharing"

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
                        "recompile": idx.get("needs_recompile", idx.get("recompile", False)),
                        "taught": r.compiled_from.get("source") == "taught"})  # you showed Envoy once (api/teach.py)
        return out

    @app.get("/api/routines/{name}", dependencies=[Depends(session)])
    def get_routine(name: str, version: int | None = None) -> dict[str, Any]:
        r = routines.get(name, version)
        return {"index": routines.index(name), "yaml": dump_yaml(r)}

    @app.get("/api/routines/{name}/detail", dependencies=[Depends(session)])
    def routine_detail(name: str) -> dict[str, Any]:
        """Read only: steps, versions with what each patch changed, runs and their savings (api/routine_view.py)."""
        if name not in routines.names():
            raise HTTPException(404, "no such routine")
        try:
            return routine_view.detail(routines, name, tasks)
        except KeyError as e:  # no version of it can be read
            raise HTTPException(404, str(e)) from e

    @app.get("/api/routines/{name}/history/{version}/{file}", dependencies=[Depends(session)])
    def routine_evidence(name: str, version: int, file: str) -> FileResponse:
        path = routine_view.evidence_path(routines, name, version, file)
        if path is None:
            raise HTTPException(404, "no such screenshot")
        return FileResponse(path, media_type="image/png")

    @app.get("/api/triggers", dependencies=[Depends(session)])
    def list_triggers() -> list[dict[str, Any]]:
        return [{**t, "next": scheduler.next_runs(t), "alerts": dict(zip(("on", "attributes"), alerts.settings(t)))} for t in tasks.triggers()]

    @app.post("/api/triggers", dependencies=[Depends(session)])
    def add_trigger(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            return scheduler.add(body.get("kind", ""), body.get("name", "trigger"), body.get("spec") or {}, body.get("action") or {})
        except (ValueError, KeyError) as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/api/triggers/{tid}", dependencies=[Depends(session)])
    def toggle_trigger(tid: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        trig = tasks.trigger(tid)
        if trig is None:
            raise HTTPException(404, "no such trigger")
        action = None
        if "ask" in body or "offer_title" in body:  # ask mode: "Ask me first" or "Just do it"
            action = {**trig["action"], **{k: body[k] for k in ("ask", "offer_title") if k in body}}
            if action.get("offer_title") in ("", None):
                action.pop("offer_title", None)
            try:
                check_ask(trig["kind"], action)
            except ValueError as e:
                raise HTTPException(400, str(e)) from e
        spec = None
        if "alert" in body or "alert_on" in body:  # only the fields given: turning alerts off doesn't pause the trigger
            spec = {**trig["spec"], **{k: body[k] for k in ("alert", "alert_on") if k in body}}
            if spec.get("alert_on") == []:
                spec["alert_on"] = None  # back to the default
            try:
                check_alert(spec)
            except ValueError as e:
                raise HTTPException(400, str(e)) from e
        if "enabled" in body:
            tasks.update_trigger(tid, enabled=1 if body.get("enabled") else 0)
        if spec is not None:
            tasks.update_trigger(tid, spec=spec)
        if action is not None:
            tasks.update_trigger(tid, action=action)
        return tasks.trigger(tid) or {}

    @app.get("/api/alerts", dependencies=[Depends(session)])
    def list_alerts(limit: int = 30) -> list[dict[str, Any]]:
        """Recent changes to remembered facts, newest first: what changed, from which task, and whether it pushed."""
        return alerts.recent(min(limit, 200))

    @app.delete("/api/triggers/{tid}", dependencies=[Depends(session)])
    def delete_trigger(tid: str) -> dict[str, Any]:
        tasks.delete_trigger(tid)
        return {"deleted": tid}

    app.include_router(offers_router(ctx, session, caller))
    app.include_router(agents_router(ctx, session, owner, caller))  # a key per AI agent (Settings › Agents)
    app.include_router(handoff_router(ctx, session, caller, door_key=bearer_token(), door_log=LOGS / "door.jsonl"))  # files from another Mac
    app.include_router(files_router(ctx.files))  # type: ignore[attr-defined]  # get_file's downloads, by signed link only
    app.include_router(siri_router(ctx, session, caller, csrf))
    app.include_router(signin_router(tasks, session))  # saved logins, off by default (api/autofill.py)
    app.include_router(notifications_router(ctx, session))  # which apps' notifications Envoy watches, off by default

    # ---- the web app ---------------------------------------------------------------------------

    import subprocess
    started_on = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()

    @app.get("/healthz")
    def health() -> dict[str, Any]:
        return {"ok": True, "profile": ctx.profile, "commit": started_on}  # the commit the API started on (evaluations check it)

    if WEB_OUT.exists():
        import mimetypes
        mimetypes.add_type("application/manifest+json", ".webmanifest")
        app.mount("/", StaticFiles(directory=WEB_OUT, html=True), name="web")
    else:
        @app.get("/")
        def no_web() -> HTMLResponse:
            return HTMLResponse("<p>Envoy API is running. Build the web app: <code>cd web && npm run build</code></p>")

    async def dispatch(scope: dict, receive: Any, send: Any) -> None:
        """Only the names Envoy is served on (DNS rebinding); WebSockets only from those origins. A public address for AI
        clients (Muse) reaches /mcp and nothing else, and so does anything Tailscale says came in from the internet
        (Funnel), whatever its host; under /mcp that includes the outbox's door (/mcp/outbox, the Mac's forwarder, same key)
        and get_file's downloads (/mcp/files/…, a signed link each). /mcp goes to the MCP server, whose bearer check takes
        Muse's key or an agent's (Auth.agent_for, which names the agent for the call: api/agents.py); the door, the
        downloads and everything else to the API and web app."""
        if scope["type"] in ("http", "websocket"):
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
            origin = headers.get("origin", "")
            host = headers.get("host", "")
            is_mcp = scope["type"] == "http" and (scope["path"] == "/mcp" or scope["path"].startswith("/mcp/"))
            from_internet = "tailscale-funnel-request" in headers
            bad_host = (from_internet or host not in hosts) and not (is_mcp and host in tunnel_hosts(API_DIR / "mcp_public_url"))
            bad_origin = scope["type"] == "websocket" and origin and origin.split("://", 1)[-1] not in hosts
            if bad_host or bad_origin:
                if scope["type"] == "http":
                    await Response("unknown host", status_code=421)(scope, receive, send)
                else:
                    await receive()
                    await send({"type": "websocket.close", "code": 4403})
                return
        if scope["type"] == "http" and (scope["path"] == "/mcp" or scope["path"].startswith("/mcp/")) and scope["path"] != DOOR \
                and not scope["path"].startswith(FILES + "/"):
            await mcp(scope, receive, send)
        else:
            await app(scope, receive, send)

    ctx.asgi = dispatch  # type: ignore[attr-defined]
    return app, ctx


def login_url() -> str:
    return f"http://127.0.0.1:{PORT}/login?k={session_token()}"


__all__ = ["build", "login_url", "PORT"]
