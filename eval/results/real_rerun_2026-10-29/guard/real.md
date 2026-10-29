# Real apps (envoy-real, read-only)

Run 1029151123 on `5fa03bf` with uncommitted changes, 2026-10-29 19:11 UTC, 18 min, standard tier. 127 model calls, $0.839 at standard prices ($0.839 billed).

| Stage | Passed |
| --- | --- |
| 1. First run: the agent gives a right answer | 12/18 |
| 2. Compile: the trace becomes a verified routine | 12/18 |
| 3. Same input: the routine reruns right with no model call | 8/18 (9 counting a repair) |
| 4. New input: right with a second input, no model call | 5/11 |
| Blocked by a bot check | 2 (target, target_search) |

Rows come from 2 runs: 1029151123 on `5fa03bf`: amazon, starbucks, chipotle, doordash, doordash_search, settings_version, settings_bluetooth, gmail_newest, gmail_search, calendar_today, contacts_count, maps_address, play_rating, youtube_search, ytmusic_artist, chrome_wikipedia; 1028023735 on `524b93a`: target, target_search.

Answers graded only by their shape (a price, a title) were also read by a person: 2 right, 0 the wrong value (not counted above), 8 not read yet. Verdicts: `real_hand_checks.json`, keyed by the exact answer.

| Workflow | App | Graded by | 1. First run | Agent | 2. Compiled | 3. Same input | 4. New input | Routine (same input) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| amazon | android | shape | pass | 2 actions, 4 calls, 25.69 s | ✅ 2 steps | wrong | wrong | 8.91 s, 0 calls |
| target | target | shape | bot check | 0 actions, 2 calls, 10.1 s | ❌ run ended 'handoff' with check None; only verified | – | n/a | – |
| target_search | target | shape | bot check | 0 actions, 2 calls, 8.6 s | ❌ run ended 'handoff' with check None; only verified | – | – | – |
| starbucks | starbucks | truth | pass | 7 actions, 9 calls, 25.43 s | ✅ 8 steps | pass | pass | 12.38 s, 0 calls |
| chipotle | chipotle | shape | pass | 9 actions, 12 calls, 31.6 s | ✅ 9 steps | fail | fail | 35.93 s, 2 calls |
| doordash | dd | truth | failed | 4 actions, 7 calls, 23.82 s | ❌ run ended 'failed' with check None; only verified  | – | n/a | – |
| doordash_search | dd | shape | pass | 2 actions, 4 calls, 11.68 s | ✅ 2 steps | pass | pass | 9.94 s, 0 calls |
| settings_version | android | truth | pass | 4 actions, 6 calls, 17.45 s | ✅ 3 steps | pass | n/a | 7.78 s, 0 calls |
| settings_bluetooth | android | truth | pass | 5 actions, 9 calls, 21.42 s | ✅ 3 steps | pass | n/a | 2.57 s, 0 calls |
| gmail_newest | android | truth | pass | 1 actions, 3 calls, 7.88 s | ✅ 1 steps | pass | n/a | 2.51 s, 0 calls |
| gmail_search | android | truth | pass | 3 actions, 5 calls, 13.82 s | ✅ 4 steps | wrong | pass | 3.42 s, 0 calls |
| calendar_today | android | truth | pass | 0 actions, 2 calls, 8.07 s | ✅ 1 steps | pass | n/a | 0.86 s, 0 calls |
| contacts_count | android | truth | step_limit | 24 actions, 28 calls, 90.71 s | ❌ run ended 'step_limit' with check None; only verif | – | n/a | – |
| maps_address | apps | truth | pass | 4 actions, 6 calls, 19.68 s | ✅ 3 steps | pass | pass | 13.48 s, 0 calls |
| play_rating | android | shape | pass | 1 actions, 3 calls, 8.84 s | ✅ 2 steps | pass after repair | fail | 2.2 s, 0 calls |
| youtube_search | android | shape | pass | 2 actions, 5 calls, 12.5 s | ✅ 2 steps | pass | pass | 5.15 s, 0 calls |
| ytmusic_artist | youtube | truth | error | 2 actions, 4 calls, 44.5 s | ❌ run ended 'error' with check None; only verified r | – | – | – |
| chrome_wikipedia | android | truth | error | 0 actions, 0 calls, 3.49 s | ❌ run ended 'error' with check None; only verified r | – | – | – |

Why each miss happened:

- **amazon**: same input: wrong ({}; all steps and checks passed) · new input: wrong ({}; all steps and checks passed)
- **target**: first run bot check: Bot verification requires human press-and-hold · not compiled: run ended 'handoff' with check None; only verified runs are compiled
- **target_search**: first run bot check: Bot verification press-and-hold requires user to complete · not compiled: run ended 'handoff' with check None; only verified runs are compiled
- **chipotle**: same input: fail ({}; step scroll_menu: after-checks failed: no match (best 0.25 < 0.80 or ambiguous, runner-up 0.25)) · new input: fail ({}; step scroll_menu: after-checks failed: no match (best 0.25 < 0.80 or ambiguous, runner-up 0.25))
- **doordash**: first run failed: [redacted] · not compiled: run ended 'failed' with check None; only verified runs are compiled
- **gmail_search**: same input: wrong ({'subject': 'You shared some Google Account data with DoorDash Consume; all steps and checks passed)
- **contacts_count**: first run step_limit: stopped after 25 steps · not compiled: run ended 'step_limit' with check None; only verified runs are compiled
- **play_rating**: same input: pass after repair ({'star_rating': '4.7 stars in 48 million reviews'}; all steps and checks passed) · new input: fail ({}; step find_open_app_listing: after-checks failed: no match (best 0.00 < 0.80 or ambiguous, runner-up 0.00))
- **ytmusic_artist**: first run error: APIConnectionError: Connection error. · not compiled: run ended 'error' with check None; only verified runs are compiled
- **chrome_wikipedia**: first run error: APIConnectionError: Connection error. · not compiled: run ended 'error' with check None; only verified runs are compiled
