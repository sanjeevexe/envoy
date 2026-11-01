# meta-agent (T2d): report

Branch `claude/meta-agent-bddeda`, on main `17af085`. It adds `agents/meta-agent/` and `docs/agents.md`, and touches
no other file.

## What is true now (stage 1, Nov 1)

- **The Spark agent works.** `agents/meta-agent/` is a standalone agent on Meta's `muse-spark-1.3`, called through the
  Responses API with the backend's key. It reaches Envoy only over MCP and imports none of Envoy's code.
  - **Tools:** it lists Envoy's tools and hands them to Spark as function tools, refreshed before every message.
  - **The loop:** stateless (`store: false`), with the encrypted reasoning replayed each call.
  - **Waiting:** a local `wait_for_task` helper polls `get_task`, so the model doesn't spend a call per poll.
  - **Costs:** priced and capped like `backend/models/adapter.py` (`logs/meta_agent_costs.jsonl`, $3/day by default).
- **The page films well.** `http://127.0.0.1:8790`, in the Sage look, laid out for 1920×1080:
  - the conversation on the left;
  - every MCP call on the right (tool, arguments, one-line result, time), with each Spark model call between them
    (time, tokens, cost);
  - a waiting card while Envoy waits for the user's OK on their phone, with a live timer, which turns into "Approved
    on your phone" or "You said no on your phone". It sits in a dock above the feed, so it stays in view, and stacks
    when several tasks wait (the cross-post: three routine tools, then one `wait_for_task` on all three);
  - learned routines first in the tool strip, with Envoy's built-in tools folded into one chip;
  - an "Envoy refused" card with Envoy's own answer when the model calls a tool it wasn't given.
- **Recorded on a real device** (envoy-test, a :8765 copy of main `17af085`, its own agent key "Spark agent"):
  - **Flight status:** SL 1190 through `run_routine skylark_check_flight_status`, done ("Delayed 25 min… gate A7").
  - **Check-in:** through `run_routine skylark_check_in_flight`. It stopped at "Confirm check-in" with the waiting card
    up. It was declined on the copy, the card closed, and Spark reported it.
  - **Tasks** show "from Spark agent".
  - **Evidence:** `agents/meta-agent/evidence/2026-11-01/` (event logs and screenshots).
- **With a read-only key** (agent keys), the agent saw 6 tools.
  - Spark once called a tool it wasn't given. Envoy's "Unknown tool" answer shows in the refusal card.
  - Asked to approve, Spark said only the user can, in Envoy.
- **Tests:** `uv run --project backend pytest -q agents/meta-agent/tests` gives 24 passed. They cover:
  - the loop and the wait helper;
  - waiting cards and refusals;
  - stopping mid-wait;
  - costs and the cap;
  - that no key reaches an event or a log;
  - the page server's host and origin checks;
  - the client against Envoy's real MCP server over HTTP, with Envoy built in process.
- **Claude doc:** `docs/agents.md` covers making a key in Settings › Agents, adding Envoy to Claude Code with
  `claude mcp add --transport http … --header "Authorization: Bearer $(pbpaste)"`, and running the Spark agent.

## Stage 2 so far (Nov 1, evening)

- **On the live :8700** with the coordinator's key ("Spark agent": read, run, files, triggers), read-only checks only:
  - `initialize` answered, and `tools/list` gave 10 tools.
  - `list_routines` and `phone_updates` answered.
  - `memory_note` got Envoy's refusal naming the "memory" group.
  - `approve` got "Unknown tool".
  - The page connected (`evidence/2026-11-01/live-8700-connected.png`).
  - No task was started there: that waits for the coordinator's OK.
- **A learned routine called by name** (agent-door's routine tools, on a :8765 copy of main `3252979`):
  - `skylark_check_flight_status` was shared, so it was in the tool list with its typed input.
  - Spark called it directly with `{"flight_number": "SL 1190"}` and answered with the status.
  - The page marks it "learned" (`evidence/2026-11-01/routine-tool-run.png`).

## Not done yet

- **The Claude Code test:** the user adds Envoy and pastes the key.
- **A task on the live :8700:** only with the coordinator's OK.
- **The approve card on the page has only been seen with a scripted model.** In real runs Spark never tried to call an
  approve tool: it refused in words.
- **Speed on camera:** both status runs on the copy were slow on Envoy's side:
  - 150 s right after a cold boot (empty screen dumps for ~100 s);
  - 73 s on a warm emulator, with 43 s before the first step and 25 s typing the flight number.

  Envoy's own estimate is "usually 2 s". Both were the first task of a freshly started API copy, so do one warm-up run
  on :8700 before a take.
- **The copy's library:** after that slow run, Envoy put a v2 trial of `skylark_check_flight_status` in the copy's own
  library. Nothing in this branch or in main changed.

## What the video can claim

- "An agent built on Meta's Muse Spark, not Muse itself, uses Envoy over MCP with its own key, and Envoy's tasks say
  which agent asked." True, recorded.
- **"Any agent":** two clients are tested (Muse and the Spark agent). With the Claude Code test, three.
- "Anything irreversible waits for your OK on your phone; the agent has no way to approve." True. Envoy has no approve
  tool, and an agent's task always asks.
- **Avoid** "the agent learned the app". Envoy learned the routine; the agent calls it.

## Spend

About $0.16 of Meta credit in all:
- $0.083: the agent's 23 Spark calls;
- $0.073: the copy Envoy's own 9 calls (memory, app notes and a patch after the runs);
- $0.001: one probe of the function-call shape.
