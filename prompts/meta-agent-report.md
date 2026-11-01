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
    on your phone" or "You said no on your phone";
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
- **Tests:** `uv run --project backend pytest -q agents/meta-agent/tests` gives 23 passed. They cover:
  - the loop and the wait helper;
  - waiting cards and refusals;
  - stopping mid-wait;
  - costs and the cap;
  - that no key reaches an event or a log;
  - the page server's host and origin checks;
  - the client against Envoy's real MCP server over HTTP, with Envoy built in process.
- **Claude doc:** `docs/agents.md` covers making a key in Settings › Agents, adding Envoy to Claude Code with
  `claude mcp add --transport http … --header "Authorization: Bearer $(pbpaste)"`, and running the Spark agent.

## Not done yet

- **Stage 2:**
  - the agent on the live :8700 with the key the coordinator makes;
  - the Claude Code test, where the user adds Envoy and pastes the key.
- **Learned routines as their own tools** (agent-door's T1a) aren't in main yet, so the agent uses `list_routines` and
  `run_routine`. Once they land, they appear in the tool list as "learned" chips with no change here (tested with a fake
  Envoy).
- **The approve card on the page has only been seen with a scripted model.** In real runs Spark never tried to call an
  approve tool: it refused in words.
- **Speed on camera:** the recorded status run took 150 s because the emulator had just cold-booted (empty screen dumps
  for ~100 s, then slow steps). Warm the phone before filming. A replay normally takes a few seconds.
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

About $0.10 of Meta credit in all:
- $0.068: the agent's 19 Spark calls;
- $0.025: the copy Envoy's own 4 calls (memory and app notes after the runs);
- $0.001: one probe of the function-call shape.
