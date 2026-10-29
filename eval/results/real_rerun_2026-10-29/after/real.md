# Real apps (envoy-real, read-only)

Run 1029142430 on `736a6e4` with uncommitted changes, 2026-10-29 18:24 UTC, 18 min, standard tier. 129 model calls, $0.987 at standard prices ($0.987 billed).

| Stage | Passed |
| --- | --- |
| 1. First run: the agent gives a right answer | 14/18 |
| 2. Compile: the trace becomes a verified routine | 15/18 |
| 3. Same input: the routine reruns right with no model call | 13/18 (14 counting a repair) |
| 4. New input: right with a second input, no model call | 6/11 |
| Blocked by a bot check | 2 (target, target_search) |

Rows come from 2 runs: 1029142430 on `736a6e4`: amazon, starbucks, chipotle, doordash, doordash_search, settings_version, settings_bluetooth, gmail_newest, gmail_search, calendar_today, contacts_count, maps_address, play_rating, youtube_search, ytmusic_artist, chrome_wikipedia; 1028023735 on `524b93a`: target, target_search.

Answers graded only by their shape (a price, a title) were also read by a person: 2 right, 0 the wrong value (not counted above), 12 not read yet. Verdicts: `real_hand_checks.json`, keyed by the exact answer.

| Workflow | App | Graded by | 1. First run | Agent | 2. Compiled | 3. Same input | 4. New input | Routine (same input) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| amazon | android | shape | pass | 2 actions, 4 calls, 57.29 s | ✅ 2 steps | pass | pass | 8.03 s, 0 calls |
| target | target | shape | bot check | 0 actions, 2 calls, 10.1 s | ❌ run ended 'handoff' with check None; only verified | – | n/a | – |
| target_search | target | shape | bot check | 0 actions, 2 calls, 8.6 s | ❌ run ended 'handoff' with check None; only verified | – | – | – |
| starbucks | starbucks | truth | pass | 7 actions, 9 calls, 21.54 s | ✅ 8 steps | pass | pass | 9.72 s, 0 calls |
| chipotle | chipotle | shape | pass | 10 actions, 13 calls, 29.69 s | ✅ 10 steps | pass | pass | 12.01 s, 0 calls |
| doordash | dd | truth | pass | 1 actions, 3 calls, 8.6 s | ✅ 1 steps | pass | n/a | 5.61 s, 0 calls |
| doordash_search | dd | shape | pass | 2 actions, 4 calls, 14.77 s | ✅ 3 steps | pass | pass | 8.98 s, 0 calls |
| settings_version | android | truth | pass | 4 actions, 6 calls, 15.46 s | ✅ 3 steps | pass | n/a | 7.89 s, 0 calls |
| settings_bluetooth | android | truth | pass | 3 actions, 5 calls, 11.14 s | ✅ 3 steps | pass | n/a | 3.24 s, 0 calls |
| gmail_newest | android | truth | pass | 1 actions, 3 calls, 6.7 s | ✅ 1 steps | pass | n/a | 2.62 s, 0 calls |
| gmail_search | android | truth | pass | 3 actions, 5 calls, 12.63 s | ✅ 3 steps | pass | pass | 5.53 s, 0 calls |
| calendar_today | android | truth | pass | 0 actions, 2 calls, 7.29 s | ✅ 1 steps | pass | n/a | 0.82 s, 0 calls |
| contacts_count | android | truth | step_limit | 25 actions, 28 calls, 74.76 s | ❌ run ended 'step_limit' with check None; only verif | – | n/a | – |
| maps_address | apps | truth | pass | 2 actions, 4 calls, 11.62 s | ✅ 2 steps | pass | wrong | 6.42 s, 0 calls |
| play_rating | android | shape | pass | 1 actions, 3 calls, 6.86 s | ✅ 2 steps | pass | fail | 2.93 s, 0 calls |
| youtube_search | android | shape | pass | 2 actions, 5 calls, 10.75 s | ✅ 3 steps | pass | pass | 5.78 s, 0 calls |
| ytmusic_artist | youtube | truth | pass | 3 actions, 6 calls, 14.4 s | ✅ 3 steps | fail | fail | 14.07 s, 0 calls |
| chrome_wikipedia | android | truth | right, unverified | 5 actions, 8 calls, 36.98 s | ✅ 3 steps | pass after repair | fail | 9.62 s, 1 calls |

Why each miss happened:

- **target**: first run bot check: Bot verification requires human press-and-hold · not compiled: run ended 'handoff' with check None; only verified runs are compiled
- **target_search**: first run bot check: Bot verification press-and-hold requires user to complete · not compiled: run ended 'handoff' with check None; only verified runs are compiled
- **contacts_count**: first run step_limit: stopped after 25 steps · not compiled: run ended 'step_limit' with check None; only verified runs are compiled
- **maps_address**: new input: wrong ({'street_address': 'Space Needle, Broad Street, Seattle, WA'}; all steps and checks passed)
- **play_rating**: new input: fail ({}; step find_open_app_listing: after-checks failed: no match (best 0.00 < 0.80 or ambiguous, runner-up 0.00))
- **ytmusic_artist**: same input: fail ({'artist': None}; outputs not found: artist) · new input: fail ({'artist': None}; outputs not found: artist)
- **chrome_wikipedia**: first run right, unverified: 1889 · same input: pass after repair ({'year_opened': '1889'}; all steps and checks passed) · new input: fail ({}; step enter_search_query: after-checks failed: no match (best 0.00 < 0.80 or ambiguous, runner-up 0.00))
