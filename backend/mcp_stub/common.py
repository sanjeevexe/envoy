"""Settings and pages shared by the MCP stub and the REST fallback."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = REPO_ROOT / "logs" / "mcp_stub.jsonl"

load_dotenv(REPO_ROOT / ".env")


def bearer_token() -> str:
    return os.environ.get("MCP_BEARER_TOKEN", "")


def allowed_hosts(port: int) -> list[str]:
    """Hosts accepted by the MCP SDK's DNS-rebinding check: localhost plus the tunnel host, if known."""
    hosts = [f"127.0.0.1:{port}", f"localhost:{port}", "127.0.0.1:*", "localhost:*"]
    public = os.environ.get("MCP_PUBLIC_URL", "")
    if public:
        host = public.split("://", 1)[-1].split("/", 1)[0]
        hosts += [host, f"{host}:443"]
    return hosts


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "stub": True})


async def approve_page(request: Request) -> HTMLResponse:
    """Fake approval page. It has no buttons: it only proves the link reached the user."""
    task_id = request.path_params["task_id"]
    return HTMLResponse(
        "<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>Envoy approval (stub)</title>"
        "<body style='font-family:system-ui;max-width:32rem;margin:2rem auto;padding:0 1rem'>"
        f"<h1>Approval needed</h1><p>Task <code>{task_id}</code>: confirm check-in for SkyLark SL 482 "
        "(ATL to ORD, Oct 30).</p><p>This is the Phase 0 stub. In Envoy, this page shows the screenshot "
        "and an Approve button that only you can press.</p></body>"
    )
