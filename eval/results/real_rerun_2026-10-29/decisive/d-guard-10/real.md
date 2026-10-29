# Real apps (envoy-real, read-only)

Run 1029161442 on `5fa03bf` with uncommitted changes, 2026-10-29 20:14 UTC, 0 min, standard tier. 4 model calls, $0.037 at standard prices ($0.037 billed).

| Stage | Passed |
| --- | --- |
| 1. First run: the agent gives a right answer | 14/18 |
| 2. Compile: the trace becomes a verified routine | 14/18 |
| 3. Same input: the routine reruns right with no model call | 13/18 (14 counting a repair) |
| 4. New input: right with a second input, no model call | 4/11 |
| Blocked by a bot check | 2 (target, target_search) |

Rows come from 5 runs: 1028030222 on `401e994`: amazon, settings_version, maps_address, play_rating; 1028023735 on `524b93a`: target, target_search, starbucks, chipotle, doordash, doordash_search, settings_bluetooth, gmail_search, calendar_today, ytmusic_artist, chrome_wikipedia; 1028031054 on `cddf1b2`: gmail_newest; 1029161442 on `5fa03bf`: contacts_count; 1028032143 on `00ec5d9`: youtube_search.

Answers graded only by their shape (a price, a title) were also read by a person: 10 right, 0 the wrong value (not counted above), 0 not read yet. Verdicts: `real_hand_checks.json`, keyed by the exact answer.

| Workflow | App | Graded by | 1. First run | Agent | 2. Compiled | 3. Same input | 4. New input | Routine (same input) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| amazon | android | shape | pass | 2 actions, 4 calls, 25.59 s | ✅ 2 steps | pass | fail | 21.24 s, 0 calls |
| target | target | shape | bot check | 0 actions, 2 calls, 10.1 s | ❌ run ended 'handoff' with check None; only verified | – | n/a | – |
| target_search | target | shape | bot check | 0 actions, 2 calls, 8.6 s | ❌ run ended 'handoff' with check None; only verified | – | – | – |
| starbucks | starbucks | truth | pass | 8 actions, 10 calls, 32.41 s | ✅ 8 steps | pass | pass | 21.41 s, 0 calls |
| chipotle | chipotle | shape | pass | 21 actions, 25 calls, 73.46 s | ✅ 22 steps | pass after repair | pass after repair | 53.09 s, 2 calls |
| doordash | dd | truth | pass | 1 actions, 3 calls, 12.47 s | ✅ 1 steps | pass | n/a | 9.64 s, 0 calls |
| doordash_search | dd | shape | pass | 2 actions, 4 calls, 18.35 s | ✅ 2 steps | pass | pass after repair | 16.3 s, 0 calls |
| settings_version | android | truth | pass | 4 actions, 6 calls, 15.33 s | ✅ 3 steps | pass | n/a | 7.88 s, 0 calls |
| settings_bluetooth | android | truth | pass | 6 actions, 8 calls, 22.08 s | ✅ 3 steps | pass | n/a | 3.21 s, 0 calls |
| gmail_newest | android | truth | pass | 14 actions, 19 calls, 47.89 s | ✅ 1 steps | pass | n/a | 2.29 s, 0 calls |
| gmail_search | android | truth | pass | 3 actions, 5 calls, 21.96 s | ✅ 3 steps | pass | pass | 8.28 s, 0 calls |
| calendar_today | android | truth | pass | 0 actions, 2 calls, 4.39 s | ✅ 1 steps | pass | n/a | 1.47 s, 0 calls |
| contacts_count | android | truth | pass | 0 actions, 3 calls, 7.46 s | ✅ 1 steps | pass | n/a | 0.66 s, 0 calls |
| maps_address | apps | truth | pass | 4 actions, 6 calls, 19.3 s | ✅ 3 steps | pass | pass | 11.8 s, 0 calls |
| play_rating | android | shape | pass | 6 actions, 8 calls, 19.56 s | ✅ 3 steps | pass | fail | 4.96 s, 0 calls |
| youtube_search | android | shape | error | 4 actions, 5 calls, 511.67 s | ❌ run ended 'error' with check None; only verified r | – | – | – |
| ytmusic_artist | youtube | truth | pass | 6 actions, 8 calls, 17.85 s | ✅ 5 steps | pass | pass | 7.78 s, 0 calls |
| chrome_wikipedia | android | truth | right, unverified | 10 actions, 15 calls, 70.56 s | ❌ run ended 'done_unverified' with check "none of [' | – | – | – |

Why each miss happened:

- **amazon**: new input: fail ({'first_result_product': 'Amazon Official USB- C to USB- C Cable for F; outputs not found: first_result_price)
- **target**: first run bot check: Bot verification requires human press-and-hold · not compiled: run ended 'handoff' with check None; only verified runs are compiled
- **target_search**: first run bot check: Bot verification press-and-hold requires user to complete · not compiled: run ended 'handoff' with check None; only verified runs are compiled
- **chipotle**: same input: pass after repair ({'price': '$4.90'}; all steps and checks passed) · new input: pass after repair ({'price': '$4.90'}; all steps and checks passed)
- **doordash_search**: new input: pass after repair ({'first_restaurant_name': 'SH HAWAIIAN BBQ &DONUTS'}; all steps and checks passed)
- **play_rating**: new input: fail ({'star_rating': None}; outputs not found: star_rating)
- **youtube_search**: first run error: TimeoutExpired: Command '['/Users/sanjeevvarma/Library/Android/sdk/platform-tools/adb', '-s', 'emulator-5556', 'exec-out', 'screencap', '-p']' timed o · not compiled: run ended 'error' with check None; only verified runs are compiled
- **chrome_wikipedia**: first run right, unverified: Eiffel Tower opened 15 May 1889 · not compiled: run ended 'done_unverified' with check "none of ['Eiffel', 'Tower', '15', 'May', '1889'] is visible on the current screen"; only verified runs are com
