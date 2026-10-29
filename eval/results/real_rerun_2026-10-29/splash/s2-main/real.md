# Real apps (envoy-real, read-only)

Run 1029165841 on `059bb7f` with uncommitted changes, 2026-10-29 20:58 UTC, 23 min, standard tier. 108 model calls, $0.990 at standard prices ($0.990 billed).

| Stage | Passed |
| --- | --- |
| 1. First run: the agent gives a right answer | 15/18 |
| 2. Compile: the trace becomes a verified routine | 16/18 |
| 3. Same input: the routine reruns right with no model call | 12/18 (14 counting a repair) |
| 4. New input: right with a second input, no model call | 6/11 |
| Blocked by a bot check | 2 (target, target_search) |

Rows come from 2 runs: 1029165841 on `059bb7f`: amazon, starbucks, chipotle, doordash, doordash_search, settings_version, settings_bluetooth, gmail_newest, gmail_search, calendar_today, contacts_count, maps_address, play_rating, youtube_search, ytmusic_artist, chrome_wikipedia; 1028023735 on `524b93a`: target, target_search.

Answers graded only by their shape (a price, a title) were also read by a person: 2 right, 0 the wrong value (not counted above), 10 not read yet. Verdicts: `real_hand_checks.json`, keyed by the exact answer.

| Workflow | App | Graded by | 1. First run | Agent | 2. Compiled | 3. Same input | 4. New input | Routine (same input) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| amazon | android | shape | pass | 2 actions, 4 calls, 26.9 s | ✅ 2 steps | fail | fail | 37.09 s, 0 calls |
| target | target | shape | bot check | 0 actions, 2 calls, 10.1 s | ❌ run ended 'handoff' with check None; only verified | – | n/a | – |
| target_search | target | shape | bot check | 0 actions, 2 calls, 8.6 s | ❌ run ended 'handoff' with check None; only verified | – | – | – |
| starbucks | starbucks | truth | pass | 7 actions, 9 calls, 23.42 s | ✅ 8 steps | pass | pass | 10.01 s, 0 calls |
| chipotle | chipotle | shape | pass | 9 actions, 12 calls, 32.94 s | ✅ 9 steps | pass | pass | 12.89 s, 0 calls |
| doordash | dd | truth | pass | 1 actions, 3 calls, 8.74 s | ✅ 1 steps | pass | n/a | 4.74 s, 0 calls |
| doordash_search | dd | shape | pass | 2 actions, 4 calls, 12.82 s | ✅ 3 steps | pass after repair | pass after repair | 7.57 s, 0 calls |
| settings_version | android | truth | pass | 4 actions, 6 calls, 17.75 s | ✅ 3 steps | pass | n/a | 7.25 s, 0 calls |
| settings_bluetooth | android | truth | pass | 3 actions, 6 calls, 14.09 s | ✅ 3 steps | pass | n/a | 2.55 s, 0 calls |
| gmail_newest | android | truth | pass | 2 actions, 4 calls, 11.01 s | ✅ 1 steps | pass | n/a | 0.72 s, 0 calls |
| gmail_search | android | truth | pass | 3 actions, 5 calls, 14.3 s | ✅ 3 steps | pass | pass | 5.21 s, 0 calls |
| calendar_today | android | truth | pass | 0 actions, 2 calls, 7.68 s | ✅ 1 steps | pass | n/a | 0.73 s, 0 calls |
| contacts_count | android | truth | pass | 0 actions, 2 calls, 5.63 s | ✅ 1 steps | pass | n/a | 0.71 s, 0 calls |
| maps_address | apps | truth | pass | 2 actions, 4 calls, 10.93 s | ✅ 2 steps | pass | pass | 4.51 s, 0 calls |
| play_rating | android | shape | pass | 1 actions, 3 calls, 8.36 s | ✅ 2 steps | pass after repair | fail | 3.92 s, 0 calls |
| youtube_search | android | shape | pass | 2 actions, 5 calls, 16.33 s | ✅ 2 steps | pass | pass | 4.7 s, 0 calls |
| ytmusic_artist | youtube | truth | pass | 3 actions, 6 calls, 19.92 s | ✅ 3 steps | pass | pass | 4.95 s, 0 calls |
| chrome_wikipedia | android | truth | right, unverified | 7 actions, 10 calls, 43.07 s | ✅ 5 steps | fail | fail | 34.5 s, 2 calls |

Why each miss happened:

- **amazon**: same input: fail ({'first_result_price': None}; outputs not found: first_result_price) · new input: fail ({'first_result_price': None}; outputs not found: first_result_price)
- **target**: first run bot check: Bot verification requires human press-and-hold · not compiled: run ended 'handoff' with check None; only verified runs are compiled
- **target_search**: first run bot check: Bot verification press-and-hold requires user to complete · not compiled: run ended 'handoff' with check None; only verified runs are compiled
- **doordash_search**: same input: pass after repair ({'first_restaurant_name': 'Pizza Zombie'}; all steps and checks passed) · new input: pass after repair ({'first_restaurant_name': 'Sushi Roku'}; all steps and checks passed)
- **play_rating**: same input: pass after repair ({'star_rating': '4.7 stars in 48 million reviews'}; all steps and checks passed) · new input: fail ({}; step find_open_app_listing: after-checks failed: no match (best 0.00 < 0.80 or ambiguous, runner-up 0.00))
- **chrome_wikipedia**: first run right, unverified: 1889 - Opening 15 May 1889 · same input: fail ({}; step type_search_query: after-checks failed: no match (best 0.25 < 0.80 or ambiguous, runner-up 0.00); no matc) · new input: fail ({}; step type_search_query: after-checks failed: no match (best 0.25 < 0.80 or ambiguous, runner-up 0.00); no matc)
