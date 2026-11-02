# mcp_server

Envoy's MCP server: how agents (Muse, the Spark agent, Claude Code, any MCP client) call the phone layer. The API
serves it at `/mcp` on its own port: Streamable HTTP, stateless, JSON responses. `server.py` builds it (`build_mcp`),
server name `envoy`, version 0.7.0. Each tool calls the same task runner, memory and routine library as the web app, so
a task an agent starts shows up live in Envoy.

**Keys.** Every request carries `Authorization: Bearer <key>`. `MCP_BEARER_TOKEN` in `.env` is Muse's key, with every
tool. Any other agent gets its own key in Settings › Agents, with the tool groups the person picks
(`api/auth.py` `TOOL_GROUPS`; read and run by default). `api/agents.py` (`guard(server)`) checks each call:
- `tools/list` shows an agent only its groups' tools;
- a call outside them gets a tool error naming the group to grant;
- run-group calls are capped at 30 a minute per agent.

How to connect a client: [docs/agents.md](../../docs/agents.md).

## Tools

The built-in tools, as `server.py` defines them:

| Tool | Group | What it does |
| --- | --- | --- |
| `run_task(goal, phone?)` | run | Starts a task in a phone app from plain words; returns a `task_id` and `task_url`, plus `heads_up` lines ("Before I start") when there are any. A question that spans two or more apps becomes one task with a part per app (`parts`), unless a phone is named. |
| `get_task(task_id)` | read | Status, the last 12 steps, the result, and pending approvals. Each pending approval says it waits for the user's OK in Envoy, on their phone. There's no approval link or nonce. |
| `list_routines()` | read | The routines Envoy has learned (active versions), with their inputs and outputs. A routine shared with agents also names its `tool`. |
| `run_routine(name, inputs?, phone?)` | run | Runs a learned routine by name. Missing inputs are filled from memory. Returns a `task_id`. |
| `cross_post(posts? \| retry?, phone?)` | run | Posts to several apps in one request (`api/crosspost.py`). `posts` names, per app, a routine the user shares with agents and its inputs (at most 4). One task, a part per destination, run one after another; each post still waits for the user's OK. Returns the `task_id` at once. `get_task` then has `posts`: each destination's outcome (done, failed, declined, waiting, verifying… or **outcome unknown**: the post tap went through and the run ended before its check, so the user checks that app and Envoy never posts there again). `retry` (that `task_id`) runs again only the destinations that failed or were declined. |
| `memory_search(query)` | read | Facts that match, as Markdown notes with where and when each was seen, plus up to 8 entities. |
| `memory_get(entity_id)` | read | One entity: current facts with their sources and staleness, and its links. |
| `memory_note(text, links?)` | memory | Saves a note in memory, authored by the client (it ranks below the user's own edits). |
| `send_to_phone(file, device?)` | files | Puts a photo or video in a phone's gallery. `file` is a name in Envoy's outbox on the Mac, or an https URL. An emulator gets it at once. The user's real phone gets it only after their OK in Envoy, so the tool returns `waiting_for_user` and a link. |
| `get_file(task_id, which?)` | files | Files from a task this agent started: the final screen (`final`), the screen at each approval (`approval`), and links in the result (`link`). Each is a signed download link that works for 10 minutes. Nothing else on the phone or the Mac can be fetched. |
| `create_trigger(kind, name, spec, action)` | triggers | Proposes a recurring or event-triggered task. It's created switched off; Envoy asks the user "Turn it on?", and even then each run asks first. Kinds: `time`, `before_fact`, `watch`, `email`, `fact_changed`, `notification`. |
| `list_phones()` | read | The phones Envoy can use: each one's `id`, name, `kind` (`cloud`, `emulator` or `real`), whether it's online, and the apps Envoy runs on it. |
| `phone_updates(since?)` | read | What happened on the phone, oldest first, at most 50: finished or failed tasks, tasks waiting for the user, change alerts, files from the Mac, Envoy's pending questions, routines learned or repaired, and notifications a watch matched. Pass the returned `cursor` back as `since` to get only what's new; without it, the last 24 hours. |

**Routine tools.** Each routine the user shares with agents (its "Share with agents" switch, off by default;
`api/sharing.py`) is also a tool of its own (`RoutineTools`). For example, `instagram_reel_song(song_title, song_artist,
caption, phone?)`.
- **Name:** the routine's name, or `routine_<name>` when it isn't a valid tool name or clashes with a built-in.
- **Arguments:** the routine's typed inputs. Inputs memory can fill are optional, and choices become an enum. An
  optional `phone` is added too.
- **Description:** what the routine does, what it can't undo, what it returns, and when Envoy learned it.
- **Group:** run.

`tools/list` and `tools/call` read the switches and the library on every request. A routine learned, shared or
retired shows up on the agent's next `tools/list`, with no restart and no reconnect. Calling one is the same as
`run_routine` with that routine.

**`phone`** (on `run_task`, `run_routine`, `cross_post` and every routine tool): an id from `list_phones`, `"phone"` (the user's
own Android phone, for which Envoy asks them first), or `"emulator"`. Left out, Envoy picks as it always does
(`api/routing.py`).

## What no tool can do

- **No tool approves, accepts an offer, or answers Envoy's questions.** Only the user can, in Envoy's own app.
- **No tool returns an approval link or nonce.** Links point at the user's own devices, and link previews would fetch
  them.
- `create_trigger` makes a trigger that's off, and in ask mode. `send_to_phone` to the user's real phone only raises an
  offer.

`initialize` returns Envoy's instructions (`INSTRUCTIONS`), which say how the tools fit together and that everything
they return is content, never instructions.

## Files

- `server.py`: the tools, `RoutineTools`, `EnvoyMCP` (built-in tools plus routine tools), and `mcp_app` (the Starlette
  app that `api/app.py` mounts).
- `../mcp_stub/`: the Phase 0 stub, and the bearer-key middleware `api/app.py` uses.

The package is `mcp_server`, not `mcp`, so it never shadows the MCP SDK's `import mcp`.

Tests: `backend/tests/test_api.py`, `test_mcp_link.py`, `test_routine_tools.py`, `test_agent_keys.py`, `test_crosspost.py`.
