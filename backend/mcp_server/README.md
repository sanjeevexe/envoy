# mcp_server

Envoy's MCP server (Phase 4), served by the API at `/mcp` (Streamable HTTP, stateless, bearer token `MCP_BEARER_TOKEN` from `.env`).

Tools: `run_task`, `get_task` (each pending approval says it waits for the user's OK on their phone; no approval links), `list_routines`, `run_routine`, `memory_search`, `memory_get`, `memory_note`. There is no approve tool: approvals come only from the user's own session in the web app. Named `mcp_server`, not `mcp`, so it never shadows the MCP SDK's `import mcp`. The Phase 0 stub lives in `../mcp_stub/`.
