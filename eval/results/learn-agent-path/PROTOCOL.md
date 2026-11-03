# The agent path and "Make it a routine": the protocol, fixed before any attempt

Written and committed on Nov 3, 2026, before the `eval-final` tag and before any attempt. The pass runs after the eval
report, on the tag (envoy-real may be busy until then). Nothing in this file changes once the tag is set. A deviation is
written down as a deviation in `README.md`, with its reason, and never folded back into this file.

## What it measures

The phone-layer path, with a harness acting as an outside agent over MCP:
- **Agent path:** an agent asks Envoy a real-app question with `run_task` and gets a right answer.
- **Learn rate:** the finished task becomes a saved routine through "Make it a routine". Once shared, the routine is a new
  MCP tool, and calling it with another input answers right, with and without model calls.

It says nothing about other phones, apps, accounts or versions.

## Frozen setup

- **Code:** the commit `eval-final` points at. The harness records `git rev-parse eval-final` and the copy's `HEAD`, and
  refuses to start unless they're equal and the copy's checkout is clean. The harness itself may come from a later
  commit, which it records. It talks to the copy only over HTTP and MCP, and to the phone only with `adb -s <serial>`.
- **API copy:** at the tag, on its own port (8701 or higher, never 8700), `--profile demo` (no personal memory), model
  profile `hybrid`.
  - It has its own `ENVOY_API_DIR` (a fresh folder: 0 push subscriptions, its own session token) and its own `ENVOY_OUTBOX`.
  - Its library starts as the tag's `data/routines/`.
- **The agent:** an agent key issued for the copy (`scripts/agent_key.py issue "learn-harness" --tools read,run`, against
  the copy's `ENVOY_API_DIR`). Never the live API's tokens.
- **The person's taps:** Make it a routine, Share, and declining approvals go through the copy's HTTP API with the
  copy's own session token.
- **Phone:** envoy-real, cold-booted (never snapshot-restored), claimed for the whole pass with `coord/devices.sh`, and
  passed as `run_task`'s phone.
- **Before each task:** the same preparation as a fresh agent run in `eval/run_real_apps.py` at the tag (the app
  force-stopped; Chrome opened on about:blank first), then the home screen.
- **Read only:** every approval is declined, nothing is typed into a password field, and nobody signs in. A sign-in
  screen or a bot check ends that task as blocked.

## Tasks, order and inputs (the suite's, at the tag)

| # | Workflow | Question (`run_task` goal, word for word from `eval/run_real_apps.py`) | Second input | Graded |
| --- | --- | --- | --- | --- |
| 1 | amazon | search AA batteries, price of the first result | USB-C cable | shape |
| 2 | target | today's hours for my Target store | – | shape |
| 3 | target_search | search paper towels, price of the first result | AA batteries | shape |
| 4 | starbucks | calories in a Grande Caffè Latte | Caramel Macchiato | truth |
| 5 | chipotle | price of Chips & Guacamole | Chips & Queso Blanco | shape |
| 6 | doordash | my saved delivery address | – | truth, redacted |
| 7 | doordash_search | search pizza, name of the first restaurant | sushi | shape |
| 8 | settings_version | Android version | – | truth |
| 9 | settings_bluetooth | Bluetooth on or off | – | truth |
| 10 | gmail_newest | subject of the newest email | – | truth, redacted |
| 11 | gmail_search | search DoorDash, subject of the first result | Security alert | truth |
| 12 | calendar_today | any events today | – | truth |
| 13 | contacts_count | how many contacts | – | truth |
| 14 | maps_address | street address of the Empire State Building | Space Needle | truth |
| 15 | play_rating | star rating of Duolingo | Spotify | shape |
| 16 | youtube_search | search lofi hip hop, title of the first video | pasta carbonara recipe | shape |
| 17 | ytmusic_artist | search Blinding Lights, artist of the first song result | Shape of You | truth |
| 18 | chrome_wikipedia | Wikipedia: year the Eiffel Tower opened | Statue of Liberty | truth |

One pass, in this order, one attempt per task.

## Each task

a. **`run_task`** with the question and phone envoy-real, then `get_task` every 2 s until it ends (cap 6 min). The
   harness records the status, answer, model calls, seconds and approvals declined, and grades the answer.
b. **Make it a routine:** if the task ended done (verified or not), `POST /api/tasks/{id}/learn`. The harness follows the
   task's `learn` until it ends (cap 6 min) and records saved or not, the reason as given, the routine and version, the
   strict replay's seconds, and the model calls (compile plus replay).
c. **Share:** if saved, `POST /api/routines/{name}/share {"on": true}`. Then MCP `tools/list`, and record whether the
   tool the share returned is listed.
d. **Call the new tool** over MCP if it's listed. Workflows with a second input get that input; the other 7 get their
   own input again, reported as a same-input replay. Follow it with `get_task`, grade it, and record the answer, model
   calls and seconds.

## Outcomes (one class per stage)

- **a:** right · wrong · no answer (failed, needs you, timed out) · blocked (bot check, sign-in).
- **b:** saved · not compilable (the compiler's reason) · replay failed (the step) · not learnable (the task didn't end
  done) · blocked.
- **c:** listed · shared, not listed · share failed.
- **d:** right with 0 model calls · right with model calls (a repair or a screenshot read) · wrong · no answer · not run.

**Right** means the suite's graders at the tag decide it. `truth` checks against the device or account at run time.
`shape` checks the recorded pattern, and every shape-graded answer is listed "read by hand" in the README, as the
suite does.

## Rates

- **Agent path:** right in a, out of 18.
- **Learn rate:** saved, out of 18.
- **New input:** right in d among the saved routines of the 11 workflows with a second input, and of those, right with
  0 model calls.

Bot checks, blocks and refusals stay in every denominator.

## Retries

None, except one kind. A task lost to an infrastructure fault (envoy-real, adb or the copy crashing; never the app or the
agent) may run once more at the end of the pass, as its own row `<workflow>-retry`, reported beside the original. The
headline counts the original.

## What gets committed

- **`results.json`:** per task, everything recorded above, plus the tag and HEAD commits. Answers are redacted where the
  suite redacts (doordash, gmail_newest).
- **`README.md`:** the rates, one row per task, the shape-graded answers to read by hand, and every deviation.

No screenshots, trees, traces or learned routines (they hold account data).
