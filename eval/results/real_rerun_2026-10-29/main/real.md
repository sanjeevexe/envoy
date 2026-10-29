# Real apps (envoy-real, read-only)

Run 1029135934 on `53ab459` with uncommitted changes, 2026-10-29 17:59 UTC, 21 min, standard tier. 180 model calls, $1.062 at standard prices ($1.062 billed).

| Stage | Passed |
| --- | --- |
| 1. First run: the agent gives a right answer | 14/18 |
| 2. Compile: the trace becomes a verified routine | 14/18 |
| 3. Same input: the routine reruns right with no model call | 9/18 (11 counting a repair) |
| 4. New input: right with a second input, no model call | 5/11 |
| Blocked by a bot check | 2 (target, target_search) |

Rows come from 2 runs: 1029135934 on `53ab459`: amazon, starbucks, chipotle, doordash, doordash_search, settings_version, settings_bluetooth, gmail_newest, gmail_search, calendar_today, contacts_count, maps_address, play_rating, youtube_search, ytmusic_artist, chrome_wikipedia; 1028023735 on `524b93a`: target, target_search.

Answers graded only by their shape (a price, a title) were also read by a person: 1 right, 0 the wrong value (not counted above), 10 not read yet. Verdicts: `real_hand_checks.json`, keyed by the exact answer.

| Workflow | App | Graded by | 1. First run | Agent | 2. Compiled | 3. Same input | 4. New input | Routine (same input) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| amazon | android | shape | pass | 2 actions, 4 calls, 18.17 s | ✅ 2 steps | pass | pass | 8.9 s, 0 calls |
| target | target | shape | bot check | 0 actions, 2 calls, 10.1 s | ❌ run ended 'handoff' with check None; only verified | – | n/a | – |
| target_search | target | shape | bot check | 0 actions, 2 calls, 8.6 s | ❌ run ended 'handoff' with check None; only verified | – | – | – |
| starbucks | starbucks | truth | pass | 21 actions, 24 calls, 57.3 s | ✅ 11 steps | pass | pass | 12.64 s, 0 calls |
| chipotle | chipotle | shape | step_limit | 21 actions, 28 calls, 68.44 s | ❌ run ended 'step_limit' with check None; only verif | – | – | – |
| doordash | dd | truth | pass | 13 actions, 17 calls, 47.48 s | ✅ 3 steps | pass | n/a | 5.6 s, 0 calls |
| doordash_search | dd | shape | pass | 2 actions, 4 calls, 12.3 s | ✅ 3 steps | pass | pass | 7.81 s, 0 calls |
| settings_version | android | truth | pass | 4 actions, 6 calls, 15.55 s | ✅ 3 steps | pass | n/a | 7.76 s, 0 calls |
| settings_bluetooth | android | truth | pass | 13 actions, 17 calls, 43.37 s | ✅ 4 steps | fail | n/a | 22.44 s, 2 calls |
| gmail_newest | android | truth | pass | 3 actions, 5 calls, 14.75 s | ✅ 3 steps | pass | n/a | 4.25 s, 0 calls |
| gmail_search | android | truth | pass | 3 actions, 5 calls, 13.48 s | ✅ 4 steps | wrong | pass | 4.95 s, 0 calls |
| calendar_today | android | truth | pass | 0 actions, 2 calls, 6.9 s | ✅ 1 steps | pass | n/a | 1.93 s, 0 calls |
| contacts_count | android | truth | pass | 0 actions, 2 calls, 5.36 s | ✅ 1 steps | pass | n/a | 1.6 s, 0 calls |
| maps_address | apps | truth | pass | 4 actions, 7 calls, 25.19 s | ✅ 3 steps | fail | fail | 24.32 s, 2 calls |
| play_rating | android | shape | pass | 2 actions, 4 calls, 10.03 s | ✅ 3 steps | pass after repair | fail | 51.24 s, 1 calls |
| youtube_search | android | shape | pass | 4 actions, 9 calls, 23.18 s | ✅ 5 steps | pass | pass | 4.91 s, 0 calls |
| ytmusic_artist | youtube | truth | pass | 6 actions, 12 calls, 27.12 s | ✅ 6 steps | pass after repair | fail | 5.93 s, 0 calls |
| chrome_wikipedia | android | truth | error | 8 actions, 11 calls, 47.35 s | ❌ run ended 'error' with check None; only verified r | – | – | – |

Why each miss happened:

- **target**: first run bot check: Bot verification requires human press-and-hold · not compiled: run ended 'handoff' with check None; only verified runs are compiled
- **target_search**: first run bot check: Bot verification press-and-hold requires user to complete · not compiled: run ended 'handoff' with check None; only verified runs are compiled
- **chipotle**: first run step_limit: stopped after 25 steps · not compiled: run ended 'step_limit' with check None; only verified runs are compiled
- **settings_bluetooth**: same input: fail ({}; step tap_search_settings: before-checks failed: app in front is com.google.android.settings.intelligence; no m)
- **gmail_search**: same input: wrong ({'first_result_subject': 'You shared some Google Account data with Doo; all steps and checks passed)
- **maps_address**: same input: fail ({}; step scroll_place_details: after-checks failed: no match (best 0.00 < 0.80 or ambiguous, runner-up 0.00)) · new input: fail ({}; step type_place_search: after-checks failed: element not found: no match (best 0.55 < 0.80 or ambiguous, runne)
- **play_rating**: same input: pass after repair ({'star_rating': '4.7 stars in 48 million reviews'}; all steps and checks passed) · new input: fail ({}; step find_open_app_listing: after-checks failed: no match (best 0.00 < 0.80 or ambiguous, runner-up 0.00))
- **ytmusic_artist**: same input: pass after repair ({'artist': 'Queen'}; all steps and checks passed) · new input: fail ({'artist': None}; outputs not found: artist)
- **chrome_wikipedia**: first run error: CostCapExceeded: daily cap $10.00 reached (spent $10.0021 today) · not compiled: run ended 'error' with check None; only verified runs are compiled
