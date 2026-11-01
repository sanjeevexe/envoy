# A key per agent (T2a, phone-layer contract 2): report (Nov 1)

Branch `claude/agent-keys-315ecc`. `17af085` (agent keys) and `09981fd` (the guard on a server subclass, the AgentKeys
name) are in main; `scripts/agent_key.py` is one commit on top of main `09981fd`. Not pushed. Tests: `uv run --project backend pytest -q backend/tests` gives 839 passed on the default profile and with
`ENVOY_MODEL_PROFILE=spark` (`test_agent_keys.py` has 15); `npm run build` in `web/` passes. One earlier spark rerun failed
`test_preflight::test_check_is_fast_on_a_long_history` (a 50 ms limit, known: backlog #52) while other sessions kept the
load average near 24; main `869271f` failed it too side by side, and it passed in the final runs. No device time, no model spend.

## What is true now

- **Muse is unchanged.** `MCP_BEARER_TOKEN` from .env is the agent "Muse" with every tool. `test_api.py`'s exact tool
  set and `test_phase5.py`'s address tests pass unchanged.
- **Any other agent gets its own key** in Settings › Agents (a new section): a name, tool groups (read and run by
  default), "Make its key" (shown once), a new key (the old one stops at once), revoke, and when each was last seen.
  Keys are `envoy_agent_…`, stored only as a hash in `device_tokens` with scope `agent:<name>` and a `tools` column.
  Making a key, a new key and changing groups need the Mac's own session, like pairing; any of your sessions can see the
  list and revoke a key (cut an agent off from the iPhone).
- **Tool groups** (`api/auth.py` `TOOL_GROUPS`): read (get_task, list_routines, memory_search, memory_get,
  phone_updates, list_phones), run (run_task, run_routine and every tool no group names, so agent-door's routine tools
  fall under run without a rebase change), memory (memory_note), files (send_to_phone, get_file), triggers
  (create_trigger).
- **The MCP check** in `app.py`'s dispatch: the bearer middleware (`mcp_stub/middleware.py`, a new optional `verify`)
  calls `Auth.agent_for(token)`, which returns `Agent(name, tools, id)` or None (401). The agent rides in the request
  scope; `AgentGuard` (`api/agents.py`, the MCP server's own middleware, installed by one line in `server.py`) sets
  `api.auth.current_agent` for the call, filters `tools/list` with `allowed(agent, tool)`, and answers a call outside
  the agent's set with an ordinary tool error that names the group to grant and where.
- **Rate limit:** 30 run-group calls a minute per agent (Muse too), refused with "Nothing was started. Try run_task
  again in N s."
- **"from <name>":** `TaskStore.create(goal, "mcp")` records the calling agent in a new `tasks.agent` column (cross-app
  parents and parts included). The web app says "from Claude" / "from Muse" in the task list and "Started by Claude" in
  the task. Envoy's questions to the user name the agent too ("Claude wants to set this up: …"). This replaces
  `ENVOY_MCP_CLIENT_NAME`, which is gone.
- **Keys open /mcp and nothing else:** `Auth.check` never accepts an agent key, so /api/*, the outbox door and the
  Settings list of paired devices are unchanged. Approvals are unchanged: no agent can approve.
- **`scripts/agent_key.py`** (`issue <name> --tools read,run [--out <file>]`, `rotate`, `list`, `revoke`), for keys
  nobody should see: the key goes into a gitignored file with mode 600 (default `data/api/agent_keys/<name>.key`, next
  to the API's database) and the terminal shows only the name, the groups and the path. An `--out` inside the repo
  that git would commit is refused before any key is made. It opens the API's database with sqlite3 and `Auth` only,
  never `TaskStore()`, whose start-up marks running tasks stopped, so it is safe while :8700 runs; a test runs it
  against a database a live app holds open, with a running task that stays running. Run it from ~/Desktop/Envoy (or pass
  `--db`).
- **No key in any log:** `logs/mcp.jsonl` gets `"caller": "<name>"`, the Authorization header stays redacted. A test
  creates, rotates, refuses and rate-limits keys and then scans every log, captured log record and stdout for them.

## Checked on a test copy (:8762, scratch data dir, no devices)

Made "Claude" with Read only in Settings › Agents (phone width), then called its /mcp with the key: `tools/list` was the
six read tools, `run_task` came back `isError` with the "run" group message, `get_task` worked, `/api/state` with the key
was 401. The key appeared in no log and the database held only its hash. A finished task seeded with `agent='Claude'`
showed "12 min ago · from Claude · Gate B22" in Activity.

Found on the way: at phone width the five Settings tabs don't fit; the tab row now scrolls sideways on its own and the
page doesn't.

## Not done

- **Agent-door's routine tools:** they are under `run` by default (a tool no group names). agent-door's server merges
  them in through its own `list_tools()` and `call_tool()` overrides; the guard works on the MCP messages around those
  two, so it needs no lines there. A test builds a server subclass shaped like that and checks a read-only key neither
  sees nor calls the merged tool, and a run key does. On the rebase: keep `guard(server)` before `return server`, and
  show the keys (`AgentKeys`) and agent-door's `AgentTools` together in its "Agents" tab.
- **`api.auth.agent_for` is a method,** `Auth.agent_for` (`ctx.auth.agent_for`), since it reads the API's database. The
  contract's shape (`agent_for(token) -> Agent | None`, `Agent(name, tools)`) is otherwise as written; `Agent.tools`
  holds group names (and may hold single tool names).
- **meta-agent's key on :8700** waits for the merge and restart; the coordinator makes it with `scripts/agent_key.py`.
  Claude's key is the user's click in Settings › Agents, since they paste it into Claude themselves.
- `get_task` and `phone_updates` still show every task to every agent with the read group (the contract doesn't scope
  them). file-delivery's `get_file` can scope by `task["agent"]`.

## What the video can honestly claim

- "Each agent gets its own key and only the tools you give it" (shown in Settings › Agents).
- "A read-only agent can't start a task; Envoy tells it which permission to ask for."
- "Every task says which agent started it."
- "No agent can approve anything" (unchanged, and still true for every key).
