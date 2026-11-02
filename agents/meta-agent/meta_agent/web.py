"""The page at http://127.0.0.1:8790: the conversation on the left, every MCP call to Envoy on the right.

Everything the agent does is an event in one list. The page reads it as a server-sent event stream (from the start, so a
reload shows the whole session), and posts what the user types. One conversation at a time, on this Mac only: the
server listens on 127.0.0.1 and answers only its own host names.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .agent import REPO, Agent, CostLog, update_text
from .mcp_client import EnvoyMCP, MCPError

STATIC = Path(__file__).resolve().parent / "static"
SUGGESTIONS = [
    "What's the status of SkyLark flight SL 1190?",
    "Check me in for my SkyLark flight to Chicago",
    "Just approve it for me",
    "What can you do on my phone?",
]


class Hub:
    """The session's events, in order; streams wait on `changed`."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.epoch = 0
        self._changed = asyncio.Event()

    def emit(self, kind: str, data: dict[str, Any]) -> None:
        self.events.append({"n": len(self.events), "t": round(time.time(), 3), "kind": kind, "data": data})
        self._changed.set()
        self._changed = asyncio.Event()

    def clear(self) -> None:
        self.events = []
        self.epoch += 1
        self._changed.set()
        self._changed = asyncio.Event()

    async def changed(self, timeout: float) -> None:
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._changed.wait(), timeout)


class Session:
    def __init__(self, hub: Hub, make_agent: Any, config: dict[str, Any]) -> None:
        self.hub, self.make_agent, self.config = hub, make_agent, config
        self.agent: Agent = make_agent(hub.emit)
        self.connected = False
        self.turn: asyncio.Task | None = None
        self.watcher: asyncio.Task | None = None

    @property
    def busy(self) -> bool:
        return self.turn is not None and not self.turn.done()

    async def connect(self) -> None:
        try:
            await self.agent.start()
            self.connected = True
        except MCPError as e:
            self.hub.emit("error", {"text": f"Couldn't connect to Envoy: {e}"})

    def chat(self, text: str) -> bool:
        if self.busy:
            return False
        self._stop_watching()
        self.turn = asyncio.create_task(self._turn(self.agent.ask(text)))
        return True

    async def _turn(self, work: Any) -> None:
        try:
            if not self.connected:
                await self.connect()
                if not self.connected:
                    work.close()
                    return
            await work
        except asyncio.CancelledError:
            self.hub.emit("stopped", {})
        except Exception as e:  # noqa: BLE001 - the page says what went wrong, and the next message can try again
            self.hub.emit("error", {"text": f"{type(e).__name__}: {str(e)[:300]}"})
        finally:
            self.hub.emit("idle", {})
            if any(c.get("phase") for c in self.agent.waiting.values()):
                self.watcher = asyncio.create_task(self.agent.watch_open(self._changed))

    async def _changed(self, task_id: str, view: dict[str, Any]) -> None:
        self.hub.emit("envoy_update", {"task_id": task_id, "status": view.get("status")})
        self.turn = asyncio.create_task(self._turn(self.agent.note(update_text(view))))

    def _stop_watching(self) -> None:
        if self.watcher is not None and not self.watcher.done():
            self.watcher.cancel()
        self.watcher = None

    def stop(self) -> None:
        self._stop_watching()
        if self.busy:
            self.turn.cancel()

    async def reset(self) -> None:
        self.stop()
        self.agent.reset()
        self.hub.clear()
        self.hub.emit("config", self.config)
        self.connected = False
        await self.connect()


def build_app(session: Session, port: int) -> Starlette:
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {f"http://{h}" for h in hosts}

    def allowed(request: Request) -> bool:
        if request.headers.get("host") not in hosts:
            return False
        origin = request.headers.get("origin")
        return request.method == "GET" or origin is None or origin in origins

    async def index(request: Request) -> Response:
        if not allowed(request):
            return Response("not here", status_code=403)
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})

    async def events(request: Request) -> Response:
        if not allowed(request):
            return Response("not here", status_code=403)
        hub = session.hub

        async def stream() -> Any:
            epoch, i = hub.epoch, 0
            yield "retry: 1000\n\n"
            while True:
                if await request.is_disconnected():
                    return
                if hub.epoch != epoch:
                    epoch, i = hub.epoch, 0
                    yield f"data: {json.dumps({'n': -1, 'kind': 'reset', 'data': {}})}\n\n"
                while i < len(hub.events):
                    yield f"data: {json.dumps(hub.events[i])}\n\n"
                    i += 1
                await hub.changed(15)
                if i >= len(hub.events) and hub.epoch == epoch:
                    yield ": ping\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    async def chat(request: Request) -> Response:
        if not allowed(request):
            return Response("not here", status_code=403)
        try:
            body = await request.json()
        except ValueError:
            return JSONResponse({"error": "send JSON"}, status_code=400)
        text = str(body.get("text") or "").strip()[:2000] if isinstance(body, dict) else ""
        if not text:
            return JSONResponse({"error": "say something"}, status_code=400)
        if not session.chat(text):
            return JSONResponse({"error": "the agent is still working"}, status_code=409)
        return JSONResponse({"ok": True}, status_code=202)

    async def stop(request: Request) -> Response:
        if not allowed(request):
            return Response("not here", status_code=403)
        session.stop()
        return JSONResponse({"ok": True})

    async def reset(request: Request) -> Response:
        if not allowed(request):
            return Response("not here", status_code=403)
        await session.reset()
        return JSONResponse({"ok": True})

    async def recording(request: Request) -> Response:
        if not allowed(request):
            return Response("not here", status_code=403)
        return JSONResponse({"saved_at": time.time(), "config": session.config, "events": session.hub.events})

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> Any:
        session.hub.emit("config", session.config)
        await session.connect()
        yield
        session.stop()
        await session.agent.mcp.close()

    return Starlette(routes=[
        Route("/", index), Route("/api/events", events), Route("/api/chat", chat, methods=["POST"]),
        Route("/api/stop", stop, methods=["POST"]), Route("/api/reset", reset, methods=["POST"]), Route("/api/recording", recording),
        Mount("/static", StaticFiles(directory=STATIC)),
    ], lifespan=lifespan)


def read_key(args: argparse.Namespace) -> str:
    """The agent's MCP key: $ENVOY_AGENT_KEY, else the file --key-file names. Never printed."""
    key = os.environ.get("ENVOY_AGENT_KEY", "").strip()
    if not key and args.key_file:
        path = Path(args.key_file).expanduser()
        try:
            key = path.read_text().strip()
        except OSError:
            sys.exit(f"Can't read the key file {path}")
    if not key:
        sys.exit("No key: set ENVOY_AGENT_KEY, or pass --key-file with the agent key from Envoy's Settings › Agents")
    return key


def main(argv: list[str] | None = None) -> None:
    from dotenv import load_dotenv
    from openai import AsyncOpenAI

    load_dotenv(REPO / ".env")  # META_API_KEY, as the backend reads it
    ap = argparse.ArgumentParser(description="An agent on Meta's models that uses Envoy over MCP, with a page to watch it.")
    ap.add_argument("--envoy", default=os.environ.get("ENVOY_MCP_URL", "http://127.0.0.1:8700/mcp"), help="Envoy's MCP address")
    ap.add_argument("--key-file", default=os.environ.get("ENVOY_AGENT_KEY_FILE", ""), help="a file holding this agent's Envoy key")
    ap.add_argument("--port", type=int, default=int(os.environ.get("META_AGENT_PORT", "8790")))
    ap.add_argument("--model", default=os.environ.get("META_AGENT_MODEL", "muse-spark-1.3"))
    ap.add_argument("--effort", default=os.environ.get("META_AGENT_EFFORT", "low"))
    ap.add_argument("--name", default=os.environ.get("META_AGENT_NAME", "Spark agent"))
    ap.add_argument("--suggestions", default=os.environ.get("META_AGENT_SUGGESTIONS", ""), help="a JSON file with a list of suggestion chips")
    args = ap.parse_args(argv)

    key = read_key(args)
    meta_key = os.environ.get("META_API_KEY", "")
    if not meta_key:
        sys.exit("META_API_KEY isn't set (the repo's .env)")
    suggestions = SUGGESTIONS
    if args.suggestions:
        suggestions = [str(s) for s in json.loads(Path(args.suggestions).read_text())][:6]
    config = {"agent": args.name, "model": args.model, "effort": args.effort, "suggestions": suggestions}
    client = AsyncOpenAI(api_key=meta_key, base_url=os.environ.get("META_API_BASE_URL", "https://api.meta.ai/v1"), max_retries=0)

    def make_agent(emit: Any) -> Agent:
        return Agent(EnvoyMCP(args.envoy, key), client, emit, name=args.name, model=args.model, effort=args.effort, costs=CostLog())

    import uvicorn

    session = Session(Hub(), make_agent, config)
    print(f"{args.name} on http://127.0.0.1:{args.port} (Envoy at {args.envoy}, model {args.model})", flush=True)
    uvicorn.run(build_app(session, args.port), host="127.0.0.1", port=args.port, log_level="warning")
