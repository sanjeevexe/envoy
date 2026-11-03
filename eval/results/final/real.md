# real

Run 1103034419 on `eval-final`, 2026-11-03 08:44 UTC, 18 min, standard tier, the `hybrid` profile (Muse Wonder for compile, plan, repair, step; Muse Spark for the rest). 120 model calls, $1.449 at standard prices ($1.449 billed).

| Stage | Passed |
| --- | --- |
| 1. First run: the agent gives a right answer | 13/18 |
| 2. Compile: the trace becomes a verified routine | 14/18 |
| 3. Same input: the routine reruns right with no model call | 13/18 (14 counting a repair) |
| 4. New input: right with a second input, no model call | 7/11 |
| Blocked by a bot check | 2 (target, target_search) |

Answers graded only by their shape (a price, a title) were also read by a person: 3 right, 0 the wrong value (not counted above), 8 not read yet. Verdicts: `real_hand_checks.json`, keyed by the exact answer.

| Workflow | App | Graded by | 1. First run | Agent | 2. Compiled | 3. Same input | 4. New input | Routine (same input) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| amazon | android | shape | pass | 3 actions, 5 calls, 43.8 s | ✅ 2 steps | pass | fail | 6.95 s, 0 calls |
| target | target | shape | bot check | 0 actions, 2 calls, 17.74 s | ❌ run ended 'handoff' with check None; only verified | – | n/a | – |
| target_search | target | shape | bot check | 0 actions, 2 calls, 17.81 s | ❌ run ended 'handoff' with check None; only verified | – | – | – |
| starbucks | starbucks | truth | pass | 7 actions, 9 calls, 30.8 s | ✅ 8 steps | pass | pass | 10.58 s, 0 calls |
| chipotle | chipotle | shape | pass | 10 actions, 13 calls, 52.82 s | ✅ 9 steps | pass | pass | 12.26 s, 0 calls |
| doordash | dd | truth | failed | 5 actions, 8 calls, 32.3 s | ❌ run ended 'failed' with check None; only verified  | – | n/a | – |
| doordash_search | dd | shape | pass | 2 actions, 4 calls, 17.96 s | ✅ 2 steps | pass | pass | 6.85 s, 0 calls |
| settings_version | android | truth | pass | 4 actions, 6 calls, 24.89 s | ✅ 3 steps | pass | n/a | 7.74 s, 0 calls |
| settings_bluetooth | android | truth | pass | 3 actions, 5 calls, 17.74 s | ✅ 3 steps | pass | n/a | 2.66 s, 0 calls |
| gmail_newest | android | truth | pass | 1 actions, 3 calls, 16.77 s | ✅ 1 steps | pass | n/a | 2.32 s, 0 calls |
| gmail_search | android | truth | pass | 3 actions, 5 calls, 20.85 s | ✅ 3 steps | pass | pass | 4.27 s, 0 calls |
| calendar_today | android | truth | pass | 0 actions, 2 calls, 8.49 s | ✅ 1 steps | pass | n/a | 0.8 s, 0 calls |
| contacts_count | android | truth | pass | 0 actions, 2 calls, 9.47 s | ✅ 1 steps | pass | n/a | 0.75 s, 0 calls |
| maps_address | apps | truth | pass | 3 actions, 5 calls, 26.44 s | ✅ 2 steps | pass | pass | 11.17 s, 0 calls |
| play_rating | android | shape | pass | 3 actions, 5 calls, 17.99 s | ✅ 3 steps | pass | pass | 4.17 s, 0 calls |
| youtube_search | android | shape | right, unverified | 3 actions, 6 calls, 27.14 s | ❌ run ended 'done_unverified' with check "['radio',  | – | – | – |
| ytmusic_artist | youtube | truth | pass | 3 actions, 5 calls, 19.59 s | ✅ 3 steps | pass | pass | 4.88 s, 0 calls |
| chrome_wikipedia | android | truth | right, unverified | 5 actions, 8 calls, 56.25 s | ✅ 3 steps | pass after repair | pass after repair | 21.77 s, 3 calls |

Why each miss happened:

- **amazon**: new input: fail ({'first_result_price': None}; outputs not found: first_result_price)
- **target**: first run bot check: Target app shows 'Quick verification - Press & hold to confirm you're a human (and not a bot)' which is a bot check that must be completed by the user · not compiled: run ended 'handoff' with check None; only verified runs are compiled
- **target_search**: first run bot check: Target is showing a bot check: 'Quick verification - Press & hold to confirm you're a human (and not a bot).' Please press and hold the button to veri · not compiled: run ended 'handoff' with check None; only verified runs are compiled
- **doordash**: first run failed: [redacted] · not compiled: run ended 'failed' with check None; only verified runs are compiled
- **youtube_search**: first run right, unverified: lofi hip hop radio 📚 beats to relax/study to · not compiled: run ended 'done_unverified' with check "['radio', 'beats', 'relax', 'study'] from the answer are not on the current screen"; only verified runs are co
- **chrome_wikipedia**: first run right, unverified: The Eiffel Tower opened in 1889 (Opening: 15 May 1889). · same input: pass after repair ({'opening_year': '1889'}; all steps and checks passed) · new input: pass after repair ({'opening_year': '1886'}; all steps and checks passed)
