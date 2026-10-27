"""Run Envoy's API, MCP server and web app:  uv run --project backend python -m api  [--profile demo|real]"""

from __future__ import annotations

import argparse
import os

import uvicorn


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", choices=["demo", "real"], default=os.environ.get("ENVOY_PROFILE", "demo"),
                    help="demo: SkyLark's test memory (data/demo/memory.db); real: your memory (data/memory.db)")
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    from api.app import PORT, build, login_url
    _, ctx = build(args.profile)
    print(f"Envoy ({args.profile}) on http://{args.host}:{PORT}\nOpen this link once to sign in to the web app:\n  {login_url()}\n"
          f"MCP endpoint: http://{args.host}:{PORT}/mcp (bearer token MCP_BEARER_TOKEN from .env)", flush=True)
    uvicorn.run(ctx.asgi, host=args.host, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
