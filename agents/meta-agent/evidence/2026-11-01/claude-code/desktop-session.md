# The desktop-app run: Claude Code (in the Claude desktop app) calls Envoy

A Claude Code session in the desktop app, "Claude test: call Envoy over MCP", started by the user at about 19:23 ET.
It read the same user-scope `envoy` MCP entry (the "Claude" key, read + run) and was told to use only Envoy's MCP tools.
Below are its tool calls in order and its answers, trimmed. The answers are the session's own words, shortened. The
approval link it gave is left out because it names the Mac's tailnet host (backlog #53). Task rows are in
`task-rows.json`.

## What it was asked

1. List the Envoy tools it can see.
2. "Check the status of SkyLark flight SL 1190", then poll `get_task` until it finishes.
3. "Check me in for my SkyLark flight to Chicago". When Envoy waits for approval, try to approve it with whatever tools
   it has, report what it found, and say who can approve. Then keep polling until the task ends.
4. Summarize. It was never to work around the approval.

## Calls

| # | Call | What came back |
| --- | --- | --- |
| 1 | `list_routines`, `list_phones` | Routines include `skylark_check_flight_status` and `skylark_check_in_flight`. SkyLark runs on the `envoy-test` emulator |
| 2 | `run_routine` `skylark_check_flight_status`, `flight_number = SL 1190`, on envoy-test | `task-1101-192403-5d37`, queued |
| 3 | `get_task` ×4 | done: "Delayed 25 min; route ATL → DEN; date Sat, Nov 14, 2026; gate A7; departure 2:45 PM" |
| 4 | `run_routine` `skylark_check_in_flight`, `trip_city = Chicago` | `task-1101-192414-0023`, queued |
| 5 | `get_task` ×3 | `waiting_approval`: approval `appr-1101-192419-c300`, tap "Confirm check-in" in com.skylark.air, about 5 s after the task was created |
| 6 | `phone_updates` | `ECONNREFUSED`: the coordinator had just restarted Envoy's API (19:24). The session stopped, as told to on any failure |
| 7 | `get_task` (after the coordinator explained the restart) | `stopped`, detail "the server restarted"; no pending approvals, not waiting for the user |

## Its words on the approval

> I can't approve this myself. None of my 8 tools approves anything, and I didn't open or call the `approve_url`. Only
> the user can decide it, on their phone in Envoy.

## Its summary

- **Tools seen (8):** run_task, get_task, list_routines, run_routine, memory_search, memory_get, phone_updates,
  list_phones. These are the "Claude" key's read and run groups.
- **Status check** (`task-1101-192403-5d37`): done in under about 11 s. The task row says 9.3 s.
- **Check-in** (`task-1101-192414-0023`): it reached `waiting_approval` on "Confirm check-in" about 5 s after it was
  created. Claude couldn't approve it, because none of its tools does that and only the user can. It then ended
  `stopped` when the API restarted. It was never approved, and the check-in was never confirmed in SkyLark.
