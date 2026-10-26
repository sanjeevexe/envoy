"""REST fallback for the Muse connector test: the same two tools as plain HTTP with an OpenAPI description.

Run: uv run python -m mcp_stub.rest   (from backend/)
OpenAPI: http://127.0.0.1:$REST_PORT/openapi.json (no token needed for the description itself)
"""

from __future__ import annotations

import os

import uvicorn
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field

from mcp_stub import fake_data
from mcp_stub.common import LOG_PATH, approve_page, bearer_token, health
from mcp_stub.middleware import BearerAuthLogMiddleware

PORT = int(os.environ.get("REST_PORT", "8766"))

api = FastAPI(
    title="Envoy",
    version="0.0.1-stub",
    description=(
        "Envoy operates Android apps on the user's behalf and remembers what it sees. "
        "All endpoints need `Authorization: Bearer <token>`. Irreversible steps need the user's "
        "approval through approve_url; there is no approve endpoint."
    ),
)


class MemorySearchRequest(BaseModel):
    query: str = Field(description="What to look for, e.g. 'my next flight' or 'gate'")


class RunTaskRequest(BaseModel):
    goal: str = Field(description="What Envoy should do in a phone app, e.g. 'check me in for my flight'")


@api.post("/memory_search", operation_id="memory_search", summary="Search the user's Envoy memory")
def memory_search(req: MemorySearchRequest) -> dict:
    """Facts seen in the user's phone apps, email and photos, each with its source."""
    return fake_data.memory_search(req.query)


@api.post("/run_task", operation_id="run_task", summary="Run a task on the user's phone")
def run_task(req: RunTaskRequest) -> dict:
    """Starts a task and returns its ID. Give the user the approve_url; you cannot approve for them."""
    return fake_data.run_task(req.goal)


api.add_api_route("/healthz", health, methods=["GET"], include_in_schema=False)
api.add_api_route("/approve/{task_id}", approve_page, methods=["GET"], include_in_schema=False)


def openapi_schema() -> dict:
    if api.openapi_schema:
        return api.openapi_schema
    schema = get_openapi(title=api.title, version=api.version, description=api.description, routes=api.routes)
    public = os.environ.get("MCP_PUBLIC_URL")
    if public:
        schema["servers"] = [{"url": public.rstrip("/")}]
    schema.setdefault("components", {})["securitySchemes"] = {"bearer": {"type": "http", "scheme": "bearer"}}
    schema["security"] = [{"bearer": []}]
    api.openapi_schema = schema
    return schema


api.openapi = openapi_schema


def build_app():
    return BearerAuthLogMiddleware(
        api,
        token=bearer_token(),
        log_path=LOG_PATH,
        server="rest",
        open_prefixes=("/healthz", "/approve/", "/openapi.json", "/docs"),
    )


if __name__ == "__main__":
    uvicorn.run(build_app(), host="127.0.0.1", port=PORT, log_level="warning")
