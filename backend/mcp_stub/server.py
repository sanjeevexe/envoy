"""Phase 0 stub MCP server (Streamable HTTP, bearer token) for the Muse custom-connector test.

Run: uv run python -m mcp_stub.server   (from backend/)
Endpoint: http://127.0.0.1:$MCP_PORT/mcp
"""

from __future__ import annotations

import os

import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import ToolAnnotations
from starlette.routing import Route

from mcp_stub import fake_data
from mcp_stub.common import LOG_PATH, allowed_hosts, approve_page, bearer_token, health
from mcp_stub.middleware import BearerAuthLogMiddleware

PORT = int(os.environ.get("MCP_PORT", "8765"))

server = MCPServer(
    name="envoy",
    title="Envoy",
    description="Envoy operates Android apps on the user's behalf and remembers what it sees.",
    instructions=(
        "Envoy gives you the user's phone: use memory_search for facts from their apps "
        "(trips, bookings, orders) and run_task to have Envoy do something in a phone app. "
        "Irreversible steps need the user's approval: share the approve_url from run_task "
        "with the user. You cannot approve on their behalf."
    ),
    version="0.0.1-stub",
)


@server.tool(
    annotations=ToolAnnotations(title="Search Envoy memory", readOnlyHint=True, openWorldHint=False),
)
def memory_search(query: str) -> dict:
    """Search the user's Envoy memory (facts seen in their phone apps, email and photos).

    Returns matching entities with each fact's value and source. Use it for questions like
    "what's my gate?" or "when is my flight?".
    """
    return fake_data.memory_search(query)


@server.tool(
    annotations=ToolAnnotations(
        title="Run a task on the user's phone", readOnlyHint=False, destructiveHint=False, openWorldHint=True
    ),
)
def run_task(goal: str) -> dict:
    """Ask Envoy to do something in one of the user's phone apps, such as "check me in for my flight".

    Returns a task ID. Irreversible steps wait for the user's approval: give the user the
    approve_url from the result. You cannot approve on the user's behalf.
    """
    return fake_data.run_task(goal)


def build_app():
    server.custom_route("/healthz", methods=["GET"])(health)
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=os.environ.get("MCP_STATELESS", "1") == "1",
        json_response=os.environ.get("MCP_JSON_RESPONSE", "1") == "1",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True, allowed_hosts=allowed_hosts(PORT), allowed_origins=[]
        ),
    )
    app.router.routes.append(Route("/approve/{task_id}", approve_page, methods=["GET"]))
    return BearerAuthLogMiddleware(app, token=bearer_token(), log_path=LOG_PATH, server="mcp")


if __name__ == "__main__":
    uvicorn.run(build_app(), host="127.0.0.1", port=PORT, log_level="warning")
