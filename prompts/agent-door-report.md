# agent-door: learned routines as agents' tools, the phone parameter, richer phone_updates (Nov 1)

Branch `claude/agent-door-117797`, rebased on main `17af085` (agent-keys). Stage 1 (T1a + web): `a28a568`, `6947d70`.
Stage 2 (T2e + T2b): `b483c33`, `94438c7`, `4228335`, `608b295`.
Plan: `prompts/phone-layer-plan.md` §5 "agent-door", contracts 1, 3 (reader), 4 and 5.

## What is true now

**T1a: a shared routine is a tool of its own** (`backend/api/sharing.py`, `backend/mcp_server/server.py`).
- Each routine has a "Share with agents" switch: table `routine_sharing` in the API's database, off by default, no lock.
  `GET /api/routines/sharing` and `POST /api/routines/{name}/share {"on": bool}`, session only (the MCP key and a
  missing X-Envoy are refused). The router is included before `/api/routines/{name}`, which would take "sharing".
- While a routine is shared and has an active version, `tools/list` has it as a tool:
  - **name:** the routine's own when it matches `^[a-z][a-z0-9_]{0,63}$` and isn't a built-in tool's name, else
    `routine_<sanitized>`; two routines can't collide (`_2`, `_3`). The showcase names (`instagram_reel_song`,
    `tiktok_post_sound`, `youtube_short_sound`, `instagram_story_poll`) are tested to stay as they are.
  - **schema** from the `InputSpec`s: strings; a date with `format: date`; a choice with known choices as an enum; an
    input with `from_memory` optional ("Envoy fills it from memory (…) if left out"), the rest required. Checked before
    anything starts (a missing input or a value outside the choices is an error; a number becomes its digits).
  - **description:** intent and app, the compiler's description, outputs, and "Learned by Envoy from a run on <date>;
    replays without model calls while the app looks as it did; anything irreversible waits for the user's OK on their
    phone." (a taught routine says "from the user doing it once"). No input examples: they come from real runs.
  - **annotations:** `readOnlyHint` only when every step only reads; `_meta` has `envoy/routine`, `envoy/version`, `envoy/app`.
- A call goes where `run_routine` goes (`start_routine`: preflight's heads_up, then `runner.start(intent, "mcp",
  routine=…, inputs=…)`) and returns the same shape. `run_routine` and `list_routines` stay; `list_routines` names a
  shared routine's `tool`.
- **Freshness:** `EnvoyMCP.list_tools` and `call_tool` read the switch and the library on every call (off the event
  loop), so learning, switching a routine off or on, retiring it or flipping the switch shows on the next `tools/list`
  with no restart. A tool is rebuilt only when its active version (or that file) changes. `tools/list` took 4 ms on the
  test copy.
- **Web:** the switch on each routine's page (it names the tool when on), a "Shared with agents" badge in the routine
  list, and Settings › **Agents** › "Agent tools": each tool as an agent calls it (`skylark_check_in_flight(trip_city,
  phone?)`), its inputs, outputs, whether it asks before an irreversible step, when it was learned, and Envoy's own
  tools; it refreshes every 4 s and marks a tool that appears while you watch as New, first. The Settings section row now
  scrolls sideways on a phone (five sections don't fit 375 px).

**T2e: the phone parameter** (contract 5). `run_task`, `run_routine` and every routine tool take an optional `phone`:
an id from `list_phones`, `"phone"` or `"emulator"` (`"auto"` or empty = left out). It is checked against
`list_phones` and handed to `runner.start(phone=…)`, so routing's existing choice decides and the user's own phone still
waits for their yes. Left out, the runner is called exactly as before. An unknown id starts nothing and says to use
`list_phones`. With a phone named, a cross-app question runs as one task there (CrossApp takes no phone). A routine with
an input called `phone` keeps it as its input and has no selector.

**T2b: phone_updates** (contracts 3 and 4).
- `routine_learned`: a version compiled from a run or a demonstration that became the routine ("Envoy learned …",
  "relearned" for a later one); when the routine is shared, the line ends "agents can call it as the tool <name>" and
  the item has `tool`.
- `routine_repaired`: a repair's trial that passed, with its changes in one line. A trial still running or rolled back
  isn't listed. Both are read from `RoutineStore.index()` (read only), dated by the version's `created`.
- `notification`: read from phone-watch's `notification_events` when the table exists, worded by its
  `api.notifications.update_line(row, phone_name)`: `<App> on Envoy's phone: "<title>: <text>"`, the phone named as in
  Settings › Phones, with `app`, `phone`, `trigger_id`. Title and text go through its `redact` once more on the way out.
  Until its module is in main, the same line and a fallback redaction come from server.py (checked against phone-watch's
  real `update_line` and `redact` from its worktree).

## Tests

- `backend/tests/test_routine_tools.py` (18, one of them with agent-keys' keys: a read-only key neither sees nor calls a
  routine's tool, a key with run does) and `test_sharing.py` (6).
- Full suite on the branch tip (rebased on 17af085): **826 passed** on `ENVOY_MODEL_PROFILE=spark`; on the default
  profile 825 passed and 1 failed: `test_preflight.py::test_check_is_fast_on_a_long_history`, which asserts that
  preflight takes under 50 ms of wall time. It failed while the Mac's load average was 55–74 (other sessions) and
  passes 4/4 on this branch at load 18; `preflight.py` and its test are the same as main's.
- `npm run build` in `web/`: clean.

## Device check (stage 1)

On a `:8761` test copy in its own worktree (`.claude/worktrees/agent-door-check`: `d44bcb4` for the lists, the rebased
tip `608b295` for the calls), with `ENVOY_API_DIR` a fresh scratch folder (0 push subscriptions) and its own session and
MCP keys; envoy-test claimed 18:27–18:31 (`coord/devices.sh`), released:
- `eval/results/agent-door/tools-before.json`: 11 tools, no routine tools.
- Shared `skylark_get_flight_gate` from its page in the web app.
- `eval/results/agent-door/tools-after.json`: 12 tools; the routine tool in full.
- `eval/results/agent-door/call.json`: `skylark_get_flight_gate(trip_city="Denver")` over MCP → a task; followed with
  `get_task`: done, "gate: A7", the routine's replay with all steps and checks passed, 0 model calls, $0. The task is
  recorded as from Muse (the test copy's key is its MCP_BEARER_TOKEN).
- `eval/results/agent-door/call-phone.json` (T2e): the same tool with `trip_city="Chicago", phone="envoy-test"`: the task
  notes "phone: Test phone (you picked it)", done, "gate: B12", 0 model calls.
- Timing, honestly: each task took 41–63 s end to end, ~32 s of it connecting to the emulator and launching SkyLark and
  ~8 s for the three steps (usually 1.7 s), while the Mac's load average was 50–74 (other sessions and a test suite).
  That is the runner's usual path for any task; nothing here adds to it.
- `eval/results/agent-door/phone-updates.json`: phone_updates after the calls (the two finished tasks).
- Screenshots: `eval/results/agent-door/settings-agent-tools.png` (and `-phone`), `routine-share-switch.png`,
  `routines-shared-badges.png`.

The client is `eval/mcp_tool_check.py` (initialize, tools/list, one tools/call, get_task until the task ends).

## Not done / open

- **P1** (whether Muse sees a new tool without reconnecting) is the coordinator's check. If Muse caches its list,
  Settings › Agents is the on-screen proof, and `list_routines` and `run_routine` still reach every routine.
- `run_routine` still runs any active routine by name, shared or not (the plan keeps it). The switch decides which
  routines are tools of their own, not which can run; approvals are unchanged either way.
- agent-keys' `allowed(agent, tool)` hook goes in `EnvoyMCP.list_tools` and `call_tool` (told them); their keys UI goes
  in the same Settings › Agents section.
- The cloud phone check of `phone` (optional in the plan) wasn't run.

## What the video can honestly claim

- "Share a learned routine and it shows up as its own tool, by name, with typed inputs": true, on the next `tools/list`,
  no restart (measured on the test copy). Whether Muse's own list refreshes without reconnecting is P1.
- "Calling it runs the learned routine, replaying without model calls while the app looks as it did; anything
  irreversible still waits for your OK": true, the same path as `run_routine`.
- "An agent can pick the phone": true for a `list_phones` id, "phone" or "emulator"; the user's phone still asks first.
- "Muse hears when Envoy learns or repairs a routine, and when a watched notification lands": true through
  `phone_updates`, which Muse has to poll (P4).
