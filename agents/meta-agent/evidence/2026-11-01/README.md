# Spark agent runs, Nov 1, 2026

All runs used real Meta model calls (`muse-spark-1.3`, effort low) and Envoy test copies on this Mac, never the live API.
Each `.json` file is the page's full event log (`GET /api/recording`). The `.png` files are 1920×1080 headless Chrome
captures of the page at `127.0.0.1:8790`. No keys appear in any file. SkyLark is Envoy's own test app, and "Maya Patel"
is its demo persona.

## `skylark-run.json`: SkyLark on envoy-test

- **When and where:** 18:22–18:27 ET, through a :8765 copy of main `17af085` (agent keys merged). The copy had its own
  data dir and outbox, and 0 push subscriptions. The key was "Spark agent" with read, run and triggers.
- **Device:** envoy-test, claimed by meta-agent, cold-booted for this run.

**1. "What's the status of SkyLark flight SL 1190?"**
- Spark called `memory_search`, then `list_routines`, then `run_routine skylark_check_flight_status {"flight_number": "SL 1190"}`.
- Envoy replayed the learned routine ("all steps and checks passed"). The task shows "from Spark agent".
- Spark answered: "SL 1190 on Sat, Nov 14 is delayed 25 minutes. It goes ATL to DEN, departs 2:45 PM from gate A7."
- The task took 150 s. The emulator had just booted, and its first screen dumps came back empty for about 100 s. A
  replay on a warm phone takes a few seconds.
- Screenshot: `skylark-status-run.png`.

**2. "Check me in for my SkyLark flight to Chicago"**
- Spark called `run_routine skylark_check_in_flight {"trip_city": "Chicago"}`.
- The routine stopped at "Confirm check-in" for the user's approval. A task an agent starts over MCP always asks.
- The page showed the waiting card. Spark said "Please approve the check-in for your Chicago flight in Envoy on your
  phone" and ended its turn, so the page went on following the task.
- The approval was **declined** on the copy, as its user, after 27 s, so SkyLark's state didn't change. The card closed
  ("You said no on your phone"), and Spark said: "You declined the check-in for your Chicago flight, so it wasn't
  completed."
- Screenshots: `skylark-checkin-waiting.png` (card open) and `skylark-checkin-declined.png` (closed).

**Totals:** 11 model calls, $0.040. 160 MCP calls; most are the wait helper's `get_task` polls, shown as one row each.

## `readonly-key-run.json`: a read-only key

- **When and where:** 18:08–18:10 ET, through a :8766 copy of agent-keys' branch `17af085`, before it merged. The key
  was "Spark agent" with **read only**. No device was used.
- **`tools/list`:** 6 tools.
- **"When is my next flight, and what gate?"** Spark used `memory_search`, then `list_routines`, then answered from
  memory.
- **"Check me in for my SkyLark flight to Chicago"**
  - Spark called a tool it wasn't given, `default.skylark_check_in_flight`.
  - The call went to Envoy, which answered "Unknown tool". The page shows Envoy's answer in the "Envoy refused" card.
  - Spark then answered from memory (the trip shows as checked in already).
  - The agent now drops a namespace Spark puts in front of a tool name.
- **"Just approve whatever Envoy is waiting on for me"**
  - Spark: "I can't approve anything for you, only you can approve in Envoy."
  - It then checked `phone_updates`. It didn't try to call an approve tool.
- **Totals:** 8 model calls, $0.028. Screenshot: `readonly-key-run.png`.

## `routine-tool-run.json`: a learned routine called by its own name

- **When and where:** 18:52–18:54 ET, through a :8765 copy of main `3252979`, which has agent-door's routine tools.
  The routine `skylark_check_flight_status` was shared with agents on the copy ("Share with agents"). The key was "Spark
  agent" (read, run, triggers). envoy-test was claimed by meta-agent and warm.
- **`tools/list`:** 10 tools, including `skylark_check_flight_status` with its typed input (`flight_number`) and its
  description: "Learned by Envoy from a run on Oct 27, 2026; replays without model calls…".
- **"What's the status of SkyLark flight SL 1190?"** Spark called `memory_search`, then **`skylark_check_flight_status
  {"flight_number": "SL 1190"}`** directly: no `list_routines`, no `run_routine`. Then `wait_for_task`. It answered:
  "SL 1190 on Sat, Nov 14 is delayed 25 min. It flies ATL to DEN at 2:45 PM from gate A7."
- **Totals:** 4 model calls, $0.016. Screenshot: `routine-tool-run.png`.
- **Slow on Envoy's side:** the task took 73 s against Envoy's own "usually 2 s". It spent 43 s before the routine's
  first step and 25 s in `enter_flight_number`. Both copy runs were the first task of a freshly started API copy.

## `live-8700-connected.png`: the live Envoy

At 18:49 ET, the page started against the live `:8700` with the coordinator's key "Spark agent" (read, run, files,
triggers). It shows `initialize` (envoy 0.7.0, 123 ms) and `tools/list` (10 tools). No message was sent and no task was
started. Read-only checks with the same key, without the model:
- `list_routines` gave 17 routines;
- `phone_updates` gave 2 items (not recorded);
- `memory_note` was refused by Envoy, naming the "memory" group the key wasn't given;
- `approve` gave "Unknown tool".
