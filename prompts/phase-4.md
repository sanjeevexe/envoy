# Phase 4: web app, live view, safety (plan)

Written by Claude from the design doc on Oct 27, 2026, when you asked to start Phase 4 ("same rules as before"). The build-phases diagram defines this phase as: chat app, live view and takeover, graph view, full approvals, MCP server, schedules, triggers. **Gate:** a full check-in where you sign in through the live view, approve, and memory updates.

## Rules (unchanged from Phase 2)

- Never type passwords or sign in to accounts; sign-ins are yours. Never use payment methods.
- Ask before anything visible outside this Mac (making the repo public, posting, submitting forms).
- Contributor tier only for SkyLark; real apps and real data use the standard tier. Budget: spend where it helps.
- `envoy-real` is never snapshot-restored and is always stopped with `scripts/stop_emulator.sh`; at most two emulators run at once.
- The demo shows only work built during the hackathon; keep `THIRD_PARTY.md` current; open source is plumbing.
- Live design doc: find-and-replace edits through the Claude Docs connector, check `sinceRev` first, never overwrite someone else's edit.
- Commit and push after each meaningful step. When something needs you mid-task, ask right away and send a notification.

## What gets built

All of it runs from one FastAPI process, `backend/api/` (`uv run --project backend python -m api`), on `127.0.0.1:8700`.

| Part | What it does |
| --- | --- |
| Tasks | Every request from any interface becomes a task (goal, source, status, steps, approvals) in SQLite. A runner leases a phone, picks a routine (matcher plus memory) or the agent, and runs it. |
| Event stream | `WS /api/events`: task steps (from the trace writer), approvals, takeovers and memory changes, as they happen. |
| Approvals | A web approver: the request (screenshot, description, reasons) goes to the approvals inbox. Only your browser session can decide, by POST; opening a link never approves, because link previews fetch it. No answer means the task waits and is never auto-approved. The approval is bound to the screen it was shown for. |
| Live view and takeover | On emulators, the emulator's own gRPC screen stream as JPEG frames over a WebSocket, with taps, swipes, typing and keys sent back over gRPC. Unlike scrcpy, this shows secure sign-in screens (Phase 0). **Take over** pauses the agent: its next look at the screen waits, and nothing you do is logged or shown to a model. **Hand back** resumes it with a fresh look. The scrcpy relay for real phones moves to Phase 6. |
| Chat | Envoy's own assistant on Muse Spark: answers from memory when it can (with sources), otherwise starts a task. |
| Memory graph | Entities and links (Cytoscape.js), each entity's facts with their sources and history; edit a fact (your edit outranks extracted ones) or delete a source. |
| Routines | The library: steps, inputs, versions, runs, success rate. |
| MCP server | The real tools at `/mcp` (Streamable HTTP, bearer token): `run_task`, `get_task`, `list_routines`, `run_routine`, `memory_search`, `memory_get`, `memory_note`. There is no approve tool; `get_task` returns the approval link for a person to open. |
| Schedules and triggers | A small scheduler inside the API: time triggers, memory-derived ones ("24 hours before any flight, check in", moving when the fact changes), and watchers (rerun a read-only routine every N minutes). Event triggers start only routines or templates you created, with typed inputs. |
| Web app | `web/`: Next.js (static export, served by the API). Chat, tasks with steps and screenshots, live phone panel, approvals inbox, memory graph, routines, triggers. |

## Gate test

1. SkyLark is signed out. "Check me in for my flight" goes in through the API (and once through MCP).
2. The run stops at the sign-in screen and asks you to take over. You sign in through the live view, then hand back.
3. The check-in reaches the irreversible step; the approval appears in the inbox; you approve.
4. The check-in completes, and memory updates (checked in, seat, gate, boarding time), visible in the graph and in the event stream.

An automated version (`eval/run_phase4.py`) exercises the same path on envoy-test: a scripted person takes over, completes sign-in through SkyLark's test hook (no password typed), hands back, and approves through the same endpoint the web app uses. The human run of the gate is done by you, in the web app.

## Done means

- The gate passes, scripted and by you.
- Tests for the API, approvals, takeover, MCP tools and scheduler pass offline.
- `docs/phase-4-results.md`, both copies of the design doc, `THIRD_PARTY.md` and `docs/meta-feedback.md` are updated; everything is committed and pushed.
