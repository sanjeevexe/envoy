# Spark agent: an agent on Meta's models that uses Envoy over MCP

A small, standalone agent that proves Envoy is a phone layer **any** agent can call. It runs on Meta's Muse Spark 1.3
(Responses API, the same key the backend uses) and reaches Envoy **only over MCP**, with its own agent key. It imports
none of Envoy's code. A page at `http://127.0.0.1:8790` shows the conversation and every MCP call, and is laid out
for a 1080p screen recording.

## How it works

1. **Connect.** `initialize` over Streamable HTTP, which gives Envoy's name, version and instructions
   (`meta_agent/mcp_client.py`, about 150 lines, no MCP library).
2. **Tools.** `tools/list` becomes the model's function tools. Each MCP input schema becomes a Meta function's
   parameters (titles dropped, `X | None` as `X`), so Envoy's learned routines appear by name as tools (agent-door's
   T1a). The list is fetched again before every message, so a routine Envoy learns or shares shows up without a restart.
3. **The loop.** `POST /v1/responses` with `store: false` and `include: ["reasoning.encrypted_content"]`. The whole
   conversation goes up each time, with the model's encrypted reasoning, its tool calls and their outputs replayed, as
   Meta's docs describe for stateless multi-turn tool use. It stops when the model answers without a tool call (at
   most 16 model calls per message).
4. **Waiting.** One local helper, `wait_for_task`, calls Envoy's `get_task` every 1.5 s, for one task or several (three
   cross-posts at once). It returns as soon as a task finishes or waits for the user, so the model doesn't spend a call
   per poll. A task the user approved that carries on is waited past. The page shows the polls as one row.
5. **Approvals.** When Envoy waits for the user's OK, a card comes up in a dock above the feed. It stays in view, has a
   timer, and stacks with the others when several tasks wait. It stays until the user answers on their phone. The agent has no way to approve: Envoy has no approve tool. If the model calls one anyway, the call still goes
   to Envoy, and the page shows Envoy's answer together with the rule from Envoy's own instructions ("You cannot approve
   anything… only the user can, in Envoy."). Between messages, a card that is still open keeps being followed. When the
   user answers, the agent gets one short turn to say what happened.
6. **Costs.** Each model call is priced like `backend/models/adapter.py` prices them, and written to
   `logs/meta_agent_costs.jsonl`. There's a daily cap: `META_AGENT_DAILY_CAP_USD`, $3 by default.

## Run it

From the repo root, with `.env` holding `META_API_KEY`:

```bash
ENVOY_AGENT_KEY_FILE=~/.config/envoy/meta-agent.key uv run --project backend python agents/meta-agent/run.py
```

- `--envoy` (or `ENVOY_MCP_URL`): Envoy's MCP address. Default: `http://127.0.0.1:8700/mcp`.
- **The key:** `ENVOY_AGENT_KEY`, or a file named by `--key-file` / `ENVOY_AGENT_KEY_FILE`. Make the key in Envoy's
  Settings › Agents (`docs/agents.md`). It is sent only in the Authorization header, and never printed or shown on the
  page.
- `--model` (`META_AGENT_MODEL`, default `muse-spark-1.3`), `--effort` (`low`), `--name` (`Spark agent`),
  `--port` (`8790`).
- `--suggestions` (`META_AGENT_SUGGESTIONS`): a JSON file with a list of suggestion chips for the page.

The page listens on 127.0.0.1 only. It answers only its own host names, and takes posts only from its own page.
`GET /api/recording` returns the session's events as JSON (evidence for a run).

## Tests

```bash
uv run --project backend pytest -q agents/meta-agent/tests
```

- **The loop,** against a fake Envoy and a scripted model (`tests/fakes.py`).
- **The page's server.**
- **The client against Envoy's real MCP server over HTTP.** An Envoy is built in process with in-memory stores, as
  `backend/tests/test_mcp_link.py` builds it. Only the test imports Envoy.

`tests/preview.py` serves the page with the fake Envoy and the scripted model, for checking the layout. It is never
for the video.

## Files

| File | What it is |
| --- | --- |
| `meta_agent/mcp_client.py` | Streamable HTTP MCP client: initialize, tools/list, tools/call; JSON or SSE answers |
| `meta_agent/agent.py` | Tools to functions, the model loop, the wait helper, waiting cards, refusals, costs |
| `meta_agent/web.py` | The page's server (Starlette): the event stream, chat, stop, reset, recording |
| `meta_agent/static/` | The page (HTML, CSS, JS), Envoy's mark, and Fraunces and Manrope (OFL-1.1, licenses alongside) |
