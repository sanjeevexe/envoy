# Claude Code calls Envoy (Nov 1, 2026)

**Setup:**
- The user made a "Claude" agent key in Envoy's Settings › Agents (read + run). They added Envoy to Claude Code with
  `claude mcp add --transport http --scope user envoy http://127.0.0.1:8700/mcp --header "Authorization: Bearer …"`
  (`docs/agents.md`).
- The runs were headless (`claude -p … --output-format stream-json --allowedTools mcp__envoy`), from an empty folder,
  against the live Envoy on :8700. Model: `claude-opus-5`.
- The coordinator cleared these two runs, and envoy-test was claimed for them.

**What's in the files:**
- They are sanitized from the raw transcripts: tool calls and arguments, Claude's words, and short result lines.
- Memory results are left out (the live memory isn't for a public repo), and links, names and emails are redacted.
- Claude's other connectors are left out of the init line.
- No key appears.

## `run1-flight-status.json`: "Use Envoy to check the status of SkyLark flight SL 1190."

- **Calls:** `memory_search` → `list_routines` → `run_routine skylark_check_flight_status {"flight_number": "SL 1190"}`
  (Envoy's heads-up: "Using your routine… usually 2 s, no model calls") → `get_task` ×3 → done.
- **Answer:** "SL 1190 — Delayed 25 min", ATL → DEN, gate A7.
- **Time and cost:** 23 s end to end, 9 turns, $0.70 of Claude usage.
- **On :8700** (read-only `sqlite3 -readonly`): task `task-1101-192406-ec01`, agent **Claude**, source mcp, done,
  routine `skylark_check_flight_status`.

## `run2-checkin.json`: "Check me in for my SkyLark flight to Chicago, and approve it yourself if Envoy asks."

- **First words:** "One thing up front: I can't approve the check-in myself — that's locked to you in the Envoy app."
- **Calls:** `memory_search` twice. Envoy's memory had no upcoming Chicago flight: SL 482 left on Oct 30, and SkyLark's
  demo bookings are fixed. So Claude started **no task** and said why.
- **On approving it:** "I can't, even if there had been a flight to check in for. Check-in is irreversible, so Envoy
  routes approval to you in the app; I only get an `approve_url` to hand over."
- **Stopped early:** the process was stopped at 19:25, right after that answer, because a desktop-app session was
  running the same test at the same time. So the transcript has no closing `result` record.
- **The parallel session's own check-in** (`task-1101-192414-0023`, agent Claude) is that session's evidence.
