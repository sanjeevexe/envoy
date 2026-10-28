# Change alerts: end to end on envoy-test

Oct 28, 2026, 04:42–05:09 EDT, by the `alerts` worker on branch `claude/change-alerts-6f322a`. Reproduce with
`eval/run_alerts.py` (its docstring has the commands).

## Setup

- envoy-test (`emulator-5554`), with SkyLark seeded from the demo bookings and signed in. Trip KX7Q2M is flight SL 482
  to Chicago, gate B12.
- A copy of the API runs in the script's own process on 127.0.0.1:8712. It has its own data dir and a session token
  that the script generates, and it uses the production scheduler tick of 10 s. Its memory is built from the demo
  inbox at a scratch path: 14 emails giving 7 trips and 7 flights, with no gate known for SL 482. Its routines are a
  scratch copy of `data/routines`.
- Its only push subscription is a local fake push service, which checks the VAPID JWT and decrypts each push
  (aes128gcm) with the subscriber's key. Nothing could reach a real phone. The API on :8700 and `data/api/` were not
  touched.
- Triggers were created through `POST /api/triggers`:
  - **Watch my gate**: `watch`, every minute, alerts on (on is the default for watchers, so `alert_on` defaults to
    `gate`, the routine's output). It runs routine `skylark_get_flight_gate`, which makes 0 model calls, with
    `trip_city = Chicago`.
  - **When my gate changes**: `fact_changed` on Flight.gate. It runs routine `skylark_check_flight_status` with the
    goal "My gate moved to {change.new} (was {change.old}): check flight {flight.number}", and takes the flight number
    as a typed value from the changed Flight.
- Gate changes go through SkyLark's `SET_GATE` debug broadcast at t₀. Latency is the time the fake service decrypted
  the push minus t₀.

## Final run (`alerts.json`, `run.log`; code at 174f919, `main` merged in): every check passed

| Gate | Changed at (s after a watcher run started) | First seen by | Push | Latency | Wait for that task | Routine | Memory write | Alert → push received |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B12 → C14 | 10 | watcher run | "Gate changed: B12 → C14" | **56.7 s** | 47.1 s | 4.0 s | 5.5 s | 0.05 s |
| C14 → D3 | 50 | watcher run | "Gate changed: C14 → D3" | **18.0 s** | 9.1 s | 3.8 s | 5.1 s | 0.01 s |
| D3 → E7 | 30 | watcher run | "Gate changed: D3 → E7" | **41.2 s** | 29.1 s | 3.7 s | 8.3 s | 0.02 s |
| E7 → B12 | 20 | the fact-changed follow-up (already running) | "Gate changed: E7 → B12", sent for "Watch my gate" | **5.4 s** | −1.2 s | 4.6 s | 2.1 s | 0.01 s |

- **Latency** was 5.4 to 56.7 s, mean 30.3 s. With a one-minute watcher, the wait for the next run dominates: it is
  between 0 and 60 s plus the 10 s scheduler tick. After that, the routine takes about 4 s and memory's write takes
  about 5 s (one extraction call on the final screen). The alert and the push together take under 0.06 s.
- **Push contents**: body "Flight SL 482 · SkyLark app, just now", url `/?task=<the task that saw it>`, urgency
  high, TTL 1800, tag `change-<flight>-gate`, so a later change replaces the earlier notification.
- **No push when nothing changed.**
  - Baseline run 1 was a first sighting of B12.
  - Baseline run 2 saw B12 again.
  - The run after the last change saw B12 again.
  - None of them pushed or added a change step for the gate.
- **No push for noise.**
  - Memory's extraction of the gate screen read the boarding group as "Group 3" on one run and "3" on another. Each
    flip is a memory change and appears as a change step: "not pushed: this trigger alerts on gate only".
  - This is why `alert_on` defaults to what the watcher's routine reads (see Findings).
- **Memory**:
  - The flight's gate history is B12 → C14 → D3 → E7 → B12, and each value has its source.
  - The current B12 was written by the follow-up task's app screen, and the watcher's next routine run saw it again.
  - `GET /api/memory/entity/<flight>` shows it (`gate_history` in `alerts.json`).
- **The fact-changed trigger**:
  - It started one status check for each change the watcher found: C14, D3 and E7.
  - Each check got typed values only (`flight_number = SL 482`, from the changed Flight) and each finished `done`.
  - It started none for E7 → B12, which its own follow-up had made. That is the loop guard.
  - It started none before the first change.
- **Teardown**:
  - Both triggers were paused, not deleted, so the web app can show them.
  - SkyLark was left the way `scripts/demo_setup.py` leaves it: demo bookings, signed out, variant 0, gate B12.

## Run 2 (`alerts-run2.json`, `run2.log`): found a missed alert, which was fixed and then passed in the final run

The setup was the same, at merge commit 17dc69d. B12 → C14, C14 → D3 and D3 → E7 pushed with latencies of 54.3, 19.5
and 40.2 s. E7 → B12 did not push:
- The gate changed 20 s after a watcher run. The fact-changed trigger's follow-up for D3 → E7 started a few seconds
  later and read B12 from the app before the watcher's next run did.
- Memory's change was credited to the follow-up task. Its trigger doesn't alert by default, so the change was recorded
  with "alerts are off for this trigger".
- The watcher's next run then found nothing new.

The fix (174f919): a change seen by any trigger-started task now pushes when the task's own trigger watches the
attribute, or when another enabled trigger has alerts on for it and its runs have read that entity. The step names the
trigger it was sent for. An offline test reproduces the case:
`test_a_change_another_background_task_saw_first_still_alerts_for_the_watcher`.

## Run 1 (`alerts-run1.json`, `run1.log`)

The first pass, at 7002237 and before `main` was merged, used three changes. All checks passed. Latencies were 53.5,
23.1 and 37.6 s, with the same split.

## Screenshots (the API copy serving the final run's data, no phone involved)

- `triggers.jpg`: the new presets; the watcher with "🔔 alerts on: gate" and its Alerts off button; the fact-changed
  trigger ("runs when Flight.gate changes"); and Recent changes, both pushed and not pushed.
- `task-watcher-change.jpg`: a watcher run's activity. "Gate changed: D3 → E7 · Flight SL 482 · seen in SkyLark app,
  just now · 🔔 pushed to your devices", and the boarding-group re-read, "not pushed: this trigger alerts on gate only".
- `task-followup-alerts-for-watcher.jpg`: the follow-up that saw E7 → B12 first, "pushed to your devices (for 'Watch my
  gate')".

## Cost

These are model calls through Envoy's adapter, with `META_DAILY_COST_CAP_USD=1`. The routines made 0 calls.

| | Calls | Cost |
| --- | --- | --- |
| Building the scratch memory from the demo inbox (×3) | 33 | $0.161 |
| End-to-end runs 1–3 (one extraction call per run's final screen) | 29 | $0.149 |
| **Total** | **62** | **$0.31** |

## Findings for other owners

- **Memory (Phase 7 owns it; not changed here):** `normalize_key_value` doesn't treat "Group 3" and "3" as the same
  boarding group, so a re-read from the same screen can flip it back and forth as a change. Alerts already filter it.
  The fix belongs in `memory/types.py`.
- **iOS Simulator (optional; not done):** `xcrun simctl` started `xcodebuild -runFirstLaunch`. This Mac's CoreSimulator
  (1171.7) is older than Xcode expects (1174.9.2), and the install needs an admin password. Until someone runs
  `sudo xcodebuild -runFirstLaunch`, no simulator can boot here, so showing the push on a Home Screen web app in the
  Simulator wasn't attempted.
