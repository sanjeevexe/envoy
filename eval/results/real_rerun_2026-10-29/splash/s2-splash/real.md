# Real apps (envoy-real, read-only)

Run 1029172140 on `f11758c` with uncommitted changes, 2026-10-29 21:21 UTC, 21 min, standard tier. 197 model calls, $1.300 at standard prices ($1.300 billed).

| Stage | Passed |
| --- | --- |
| 1. First run: the agent gives a right answer | 15/18 |
| 2. Compile: the trace becomes a verified routine | 16/18 |
| 3. Same input: the routine reruns right with no model call | 10/18 (12 counting a repair) |
| 4. New input: right with a second input, no model call | 6/11 |
| Blocked by a bot check | 2 (target, target_search) |

Rows come from 2 runs: 1029172140 on `f11758c`: amazon, starbucks, chipotle, doordash, doordash_search, settings_version, settings_bluetooth, gmail_newest, gmail_search, calendar_today, contacts_count, maps_address, play_rating, youtube_search, ytmusic_artist, chrome_wikipedia; 1028023735 on `524b93a`: target, target_search.

Answers graded only by their shape (a price, a title) were also read by a person: 2 right, 0 the wrong value (not counted above), 9 not read yet. Verdicts: `real_hand_checks.json`, keyed by the exact answer.

| Workflow | App | Graded by | 1. First run | Agent | 2. Compiled | 3. Same input | 4. New input | Routine (same input) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| amazon | android | shape | pass | 2 actions, 4 calls, 19.23 s | ✅ 2 steps | wrong | wrong | 6.47 s, 0 calls |
| target | target | shape | bot check | 0 actions, 2 calls, 10.1 s | ❌ run ended 'handoff' with check None; only verified | – | n/a | – |
| target_search | target | shape | bot check | 0 actions, 2 calls, 8.6 s | ❌ run ended 'handoff' with check None; only verified | – | – | – |
| starbucks | starbucks | truth | pass | 7 actions, 9 calls, 30.92 s | ✅ 8 steps | pass | pass | 8.45 s, 0 calls |
| chipotle | chipotle | shape | pass | 12 actions, 14 calls, 35.89 s | ✅ 12 steps | fail | fail | 47.69 s, 2 calls |
| doordash | dd | truth | pass | 1 actions, 3 calls, 8.84 s | ✅ 1 steps | pass | n/a | 5.32 s, 0 calls |
| doordash_search | dd | shape | pass | 2 actions, 4 calls, 11.94 s | ✅ 3 steps | pass | pass | 8.35 s, 0 calls |
| settings_version | android | truth | pass | 5 actions, 7 calls, 20.33 s | ✅ 4 steps | pass | n/a | 8.09 s, 0 calls |
| settings_bluetooth | android | truth | pass | 8 actions, 10 calls, 26.48 s | ✅ 3 steps | pass | n/a | 2.85 s, 0 calls |
| gmail_newest | android | truth | pass | 13 actions, 17 calls, 50.01 s | ✅ 1 steps | pass | n/a | 2.26 s, 0 calls |
| gmail_search | android | truth | pass | 3 actions, 5 calls, 13.58 s | ✅ 4 steps | wrong | pass | 3.57 s, 0 calls |
| calendar_today | android | truth | pass | 0 actions, 2 calls, 6.5 s | ✅ 1 steps | pass | n/a | 0.76 s, 0 calls |
| contacts_count | android | truth | pass | 20 actions, 24 calls, 70.47 s | ✅ 20 steps | pass after repair | n/a | 40.56 s, 3 calls |
| maps_address | apps | truth | pass | 4 actions, 6 calls, 28.45 s | ✅ 3 steps | pass | pass | 11.41 s, 0 calls |
| play_rating | android | shape | pass | 2 actions, 4 calls, 9.28 s | ✅ 3 steps | pass | pass | 3.15 s, 0 calls |
| youtube_search | android | shape | pass | 3 actions, 6 calls, 15.37 s | ✅ 3 steps | pass | pass | 4.5 s, 0 calls |
| ytmusic_artist | youtube | truth | pass | 8 actions, 18 calls, 42.82 s | ✅ 7 steps | wrong | pass after repair | 12.83 s, 4 calls |
| chrome_wikipedia | android | truth | right, unverified | 7 actions, 11 calls, 49.35 s | ✅ 5 steps | pass after repair | fail | 14.61 s, 3 calls |

Why each miss happened:

- **amazon**: same input: wrong ({}; all steps and checks passed) · new input: wrong ({}; all steps and checks passed)
- **target**: first run bot check: Bot verification requires human press-and-hold · not compiled: run ended 'handoff' with check None; only verified runs are compiled
- **target_search**: first run bot check: Bot verification press-and-hold requires user to complete · not compiled: run ended 'handoff' with check None; only verified runs are compiled
- **chipotle**: same input: fail ({}; step scroll_to_chips_and_sides: after-checks failed: no match (best 0.00 < 0.80 or ambiguous, runner-up 0.00)) · new input: fail ({}; step scroll_to_chips_and_sides: after-checks failed: no match (best 0.00 < 0.80 or ambiguous, runner-up 0.00))
- **gmail_search**: same input: wrong ({'first_result_subject': 'You shared some Google Account data with Doo; all steps and checks passed)
- **contacts_count**: same input: pass after repair ({'contact_count': 'No contacts yet'}; all steps and checks passed)
- **ytmusic_artist**: same input: wrong ({'artist': 'Royal Philharmonic Orchestra & Matthew Freeman'}; all steps and checks passed) · new input: pass after repair ({'artist': 'Ed Sheeran'}; all steps and checks passed)
- **chrome_wikipedia**: first run right, unverified: 1889 · same input: pass after repair ({'year_opened': '1889'}; all steps and checks passed) · new input: fail ({'year_opened': None}; outputs not found: year_opened)
