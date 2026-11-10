# Phase 4 results: web app, live view, safety

Oct 27, 2026. **Gate passed.** The gate was "full check-in: the user signs in through the live view, approves, and memory updates".

You ran it yourself in the web app: you asked in chat, Envoy stopped at SkyLark's sign-in and asked you to take over, you signed in through the live view and handed back, the check-in ran up to its irreversible step, you approved, and the check-in completed and updated memory. A scripted version of the same path passes 10/10 (`eval/run_phase4.py`, 83 s from a clean demo state), and also checks the live view, the MCP server and chat. Your first attempt found a bug the scripted run could not (below); it was fixed, and your second attempt passed.

Results: `eval/results/phase4/gate.json`. To run it: `scripts/demo_setup.py`, then `python -m api`, then open the sign-in link it prints.

## What was built

All of it is Envoy's own code: about 1,700 lines of Python (`backend/api/`, `backend/mcp_server/`) and 850 of TypeScript (`web/`). FastAPI, the MCP SDK, Next.js, React, Tailwind and Cytoscape.js are plumbing.

| Part | Where | What it does |
| --- | --- | --- |
| Tasks and runner | `api/store.py`, `api/runner.py` | Every request (chat, web, MCP, trigger) becomes a task in SQLite. The runner picks a routine (matcher, inputs from memory) or the agent, leases the phone, hands sign-ins to you, asks for approvals through the web, and writes the results into memory. A task is done as soon as the phone work is; memory is written right after. |
| Event stream | `api/events.py` | One WebSocket stream: task status, every step (from the trace writer, with a thumbnail unless the screen is secure), approvals, takeovers, memory changes. Reconnects catch up. |
| Approvals | `api/approvals.py`, `api/app.py` | The request carries a screenshot, the action and why it was flagged. Only your session decides, by POST with a per-approval nonce and an `X-Envoy` header; opening the link decides nothing; the MCP token is refused; no answer means the action doesn't happen. An approval is bound to the app's own screen: if that changed while you decided, the routine finds the same control and asks again. |
| Takeover | `api/devices.py` | A lease per phone. **Take over** makes the agent's next look at the phone wait; your taps and typing go straight to the phone, never logged or shown to a model; **Hand back** resumes with a fresh look. A sign-in screen at the start of a run, or a hand-off mid-run, asks you to take over. |
| Live view | `api/live.py`, `web/components/LivePhone.tsx` | On emulators, the emulator's own gRPC frames, scaled by the emulator, as JPEG over a WebSocket; unchanged frames are skipped. Unlike scrcpy, this shows secure sign-in screens. Click to tap, drag to swipe, type or paste with the screen focused, plus Back, Home and Enter keys. |
| Chat | `api/chat.py` | Envoy's assistant on Muse Spark: one call decides between a memory question (answered from memory's notes, with sources and ages), a task, or a plain reply. It cannot approve. |
| Memory, routines, triggers | `api/app.py`, `api/scheduler.py` | The memory graph (entities, links, each fact's sources and history, your edits, deleting a source), the routine library (versions, runs), and triggers: time, before a remembered event (24 hours before each flight, moving if it's delayed), watchers (read-only routines only) and new email. Memory and email only fill typed values into a goal or routine you set up. |
| MCP server | `mcp_server/server.py` | `run_task`, `get_task`, `list_routines`, `run_routine`, `memory_search`, `memory_get`, `memory_note` at `/mcp` (Streamable HTTP, stateless, its own bearer token). No approve tool: `get_task` returns an approval link for you. |
| Web app | `web/` | Next.js static export served by the API (one origin, session cookie from the printed sign-in link): Chat, Tasks (live steps, thumbnails, risk, approvals), Approvals, Memory (Cytoscape graph), Routines, Triggers, and the live phone beside them. |
| Demo state | `scripts/demo_setup.py` | SkyLark seeded and signed out, and a demo memory built from the matching test inbox (`data/demo/`), so the demo starts the same way every time. |

## Results

| Check | Result |
| --- | --- |
| Gate, by you in the web app | Passed on the second attempt (sign-in through the live view, approval in 3.8 s, check-in done, memory 5 new and 4 replaced facts). The first attempt found the stale-approval bug below. |
| Gate, scripted (`eval/run_phase4.py`) | 10/10 in 83 s from a clean demo state: sign-in hand-off, takeover, hand back, approval with a screenshot, check-in done in SkyLark, memory updated (4 new, 3 replaced), MCP task, chat from memory |
| Model calls for the check-in | 1 (the routine matcher); the routine itself ran with none |
| Approval rules | Opening an approval decided nothing; the MCP token was refused (401); a stale nonce was refused (403); a browser POST without `X-Envoy` was refused (403); no answer expired the approval |
| Live view (this Mac, emulator) | Capture 12 ms at 540 px wide (scaled by the emulator), JPEG 13 ms, about 90 KB a frame, 18 to 60 ms from capture to the browser; input refused unless you have taken over |
| MCP | 7 tools, none can approve; `run_task` then `get_task` returned "gate: B12" |
| Chat | "What's my gate?" → "Gate B12, from the SkyLark app just now" (2 model calls) |
| Offline tests | 75 pass (8 new: approvals, takeover, scheduler, email triggers, MCP and API auth, the keyboard case) |
| Cost | 142 model calls, $0.80 at standard prices ($0.65 billed), most of it reading screens into memory during the many gate runs |

## What the gate runs found, and what changed

1. **A closing keyboard made your approval look stale.** You approved after 24 seconds; by then, most likely, the on-screen keyboard (from typing the SMS code) had closed, its keys left the screen's element list (we confirmed on the phone that the keyboard's keys were part of the comparison), and the approval was treated as shown for a different screen, so the check-in stopped and the task wrongly said you had declined. Approvals are now bound only to the app's own elements (not the keyboard or status bar), a stale approval in a routine re-finds the same control and asks again, the approval's note says what changed, and a regression test covers it. The scripted gate couldn't find this: it signs in through a test hook, so no keyboard ever opens.
2. **"Done" came 11 seconds after the work was done.** After you approved, the task stayed "running" while the boarding pass was read into memory, which looked stuck. A task is now done (and the phone free) as soon as the phone work is, and memory is written as a follow-up step. Checked in the browser: Done about 4 seconds after approving.
3. **The memory store was used from several threads** (the API's worker threads, MCP tools) and refused; it now allows that, with SQLite serializing the calls.
4. **MCP tools run in worker threads** with no event loop, so `run_task` failed; tasks can now start from any thread.
5. **An approval made in the same instant it was created could be missed**; the approver now registers before anything can decide.

## Configurable approvals (added after the gate, at your request)

Asking "check me in" is already your OK to check in, so by default Envoy no longer asks again. Three modes, for everything, per app or per routine (`policy/approval_rules.py`, Settings tab):

| Mode | When Envoy asks before an irreversible step |
| --- | --- |
| Ask unless I asked for it (default) | Only when it isn't what you asked for |
| Always ask | Every time |
| Never ask (routines only) | Never for that routine's own steps, even when a trigger starts it: a standing approval |

Whatever the mode, Envoy asks when money is involved, when the button's own words aren't in your request ("Cancel trip" during a check-in), when your request's details aren't on the screen or in the task's inputs (another flight, another seat), and when the request came from a trigger, an email or an AI client over MCP, unless a standing approval covers the routine. These are rules, not model judgments, matched against your own words (chat keeps them, not the assistant's rephrasing). An approval given this way is on record with who gave it ("your request", "standing approval") and shows in the task.

On SkyLark (`eval/run_approval_modes.py`, 4/4): your own "check me in" checked in without asking; the same request from MCP asked; with a standing approval on the routine, the MCP request didn't ask; with "always ask", your request asked. 4 new offline tests (79 in all). The scripted gate sets "always ask" for its run, since the gate is "the user approves", and still passes 10/10.

## Honest limits

- **The live view is local.** It is a JPEG stream over WebSocket, fine on this Mac and on the local network; over a tunnel it will need a lower frame rate or real video. HTTPS (needed by the iPhone, Phase 5) is not set up yet.
- **Emulators only.** Real phones show secure screens as black, so the scrcpy relay (Phase 6) will show them black too; you sign in on the phone itself there.
- **The scripted gate signs in through a test hook**, never by typing a password. Only your run exercised typing through the live view.
- **One person.** The web app has one session; there are no accounts, by design for a personal assistant on your own Mac.
- **Schedules and triggers are tested offline**, not yet on a live trip over days. Voice and the iPhone are Phase 5.

## Changes to the design

For the design doc (applied in both copies):

1. **On emulators the live view is the emulator's own gRPC frames** (JPEG over WebSocket), not the scrcpy relay: it shows secure sign-in screens, which is what lets you sign in from the web app, at 18 to 60 ms locally. The scrcpy relay is for real phones (Phase 6).
2. **One process serves the API, the MCP server (`/mcp`) and the web app** (a static export). You sign in once with a printed link (a cookie); AI clients use their own token, which can never approve.
3. **Takeover is a lease with a gated device:** the agent waits at its next call to the phone, so no agent code had to change; a sign-in at the start of a run is detected before the run begins.
4. **An approval is bound to the app's own elements**, not the whole screen (the keyboard and status bar come and go); a stale approval is asked again, never treated as a decline.
5. **A task is done when the phone work is**; memory is written right after.
6. **The scheduler is Envoy's own small one** (about 200 lines) instead of APScheduler: times derived from memory are recomputed on every check, so a delayed flight moves its trigger, and each occasion fires once.
7. **Approvals are configurable** (always ask; ask unless I asked for it, the default; standing approvals per routine), with money, other actions, other details and requests not from you always asking.

## Next

- **You:** nothing required. To try it again: `uv run --project backend python scripts/demo_setup.py` (with the API stopped), start the API, and run the check-in.
- **Phase 5** (iPhone companion and voice): the web app on the iPhone's Home Screen with push approvals, which needs HTTPS (Tailscale Serve), and voice input. **Phase 6** (real Android phone) when it arrives.
