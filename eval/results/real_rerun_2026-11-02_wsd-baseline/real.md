# Real apps (envoy-real, read-only)

Run 1102175459 on `192cd29`, 2026-11-02 22:54 UTC, 17 min, standard tier, the `hybrid` profile (Muse Wonder for compile, plan, repair, step; Muse Spark for the rest). 118 model calls, $1.452 at standard prices ($1.452 billed).

| Stage | Passed |
| --- | --- |
| 1. First run: the agent gives a right answer | 14/18 |
| 2. Compile: the trace becomes a verified routine | 15/18 |
| 3. Same input: the routine reruns right with no model call | 12/18 (14 counting a repair) |
| 4. New input: right with a second input, no model call | 8/11 |
| Blocked by a bot check | 2 (target, target_search) |

Rows come from 2 runs: 1102175459 on `192cd29`: amazon, starbucks, chipotle, doordash, doordash_search, settings_version, settings_bluetooth, gmail_newest, gmail_search, calendar_today, contacts_count, maps_address, play_rating, youtube_search, ytmusic_artist, chrome_wikipedia; 1028023735 on `524b93a`: target, target_search.

Answers graded only by their shape (a price, a title) were also read by a person: 1 right, 0 the wrong value (not counted above), 13 not read yet. Verdicts: `real_hand_checks.json`, keyed by the exact answer.

| Workflow | App | Graded by | 1. First run | Agent | 2. Compiled | 3. Same input | 4. New input | Routine (same input) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| amazon | android | shape | pass | 2 actions, 4 calls, 33.37 s | ✅ 2 steps | pass after repair | fail | 39.53 s, 1 calls |
| target | target | shape | bot check | 0 actions, 2 calls, 10.1 s | ❌ run ended 'handoff' with check None; only verified | – | n/a | – |
| target_search | target | shape | bot check | 0 actions, 2 calls, 8.6 s | ❌ run ended 'handoff' with check None; only verified | – | – | – |
| starbucks | starbucks | truth | pass | 7 actions, 9 calls, 29.9 s | ✅ 8 steps | pass | pass | 9.37 s, 0 calls |
| chipotle | chipotle | shape | pass | 11 actions, 13 calls, 43.82 s | ✅ 12 steps | pass | pass | 15.18 s, 0 calls |
| doordash | dd | truth | failed | 7 actions, 12 calls, 50.0 s | ❌ run ended 'failed' with check None; only verified  | – | n/a | – |
| doordash_search | dd | shape | pass | 2 actions, 4 calls, 14.8 s | ✅ 2 steps | pass | pass | 7.72 s, 0 calls |
| settings_version | android | truth | pass | 5 actions, 7 calls, 26.7 s | ✅ 3 steps | pass | n/a | 10.07 s, 0 calls |
| settings_bluetooth | android | truth | pass | 3 actions, 5 calls, 15.35 s | ✅ 3 steps | pass | n/a | 3.28 s, 0 calls |
| gmail_newest | android | truth | pass | 1 actions, 3 calls, 11.78 s | ✅ 1 steps | pass | n/a | 3.18 s, 0 calls |
| gmail_search | android | truth | pass | 3 actions, 5 calls, 21.51 s | ✅ 3 steps | pass | pass | 5.48 s, 0 calls |
| calendar_today | android | truth | pass | 0 actions, 2 calls, 9.5 s | ✅ 1 steps | pass | n/a | 0.85 s, 0 calls |
| contacts_count | android | truth | pass | 0 actions, 2 calls, 6.62 s | ✅ 1 steps | pass | n/a | 0.74 s, 0 calls |
| maps_address | apps | truth | pass | 4 actions, 6 calls, 28.62 s | ✅ 3 steps | pass | pass | 11.63 s, 0 calls |
| play_rating | android | shape | pass | 3 actions, 5 calls, 17.21 s | ✅ 3 steps | pass | pass | 4.66 s, 0 calls |
| youtube_search | android | shape | pass | 3 actions, 6 calls, 24.97 s | ✅ 2 steps | pass | pass | 5.31 s, 0 calls |
| ytmusic_artist | youtube | truth | pass | 4 actions, 6 calls, 21.7 s | ✅ 4 steps | wrong | pass | 4.79 s, 0 calls |
| chrome_wikipedia | android | truth | right, unverified | 4 actions, 7 calls, 44.66 s | ✅ 1 steps | pass after repair | input not learned | 17.67 s, 3 calls |

Why each miss happened:

- **amazon**: same input: pass after repair ({'first_result_price': '$19.99'}; all steps and checks passed) · new input: fail ({'first_result_price': None}; outputs not found: first_result_price)
- **target**: first run bot check: Bot verification requires human press-and-hold · not compiled: run ended 'handoff' with check None; only verified runs are compiled
- **target_search**: first run bot check: Bot verification press-and-hold requires user to complete · not compiled: run ended 'handoff' with check None; only verified runs are compiled
- **doordash**: first run failed: [redacted] · not compiled: run ended 'failed' with check None; only verified runs are compiled
- **ytmusic_artist**: same input: wrong ({'artist': 'Royal Philharmonic Orchestra & Matthew Freeman'}; all steps and checks passed)
- **chrome_wikipedia**: first run right, unverified: 1889 · same input: pass after repair ({'year_opened': '1889'}; all steps and checks passed) · new input: input not learned (; the compiled routine has no input the second value fits)
