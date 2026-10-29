# Real-app routine pass, 2026-10-28 21:57 EDT

On `808bb4f` (main with the repair fixes), envoy-real, standard tier, 0.4 min, 4 model calls, $0.0234 at standard prices. Method: Phase 7's routine reruns (`run_real_apps.run_one --regression`): each Phase 7 agent trace compiled again on this commit with Wonder's cached answer, then rerun on the same input and a second input. Target was left out (off limits). Frozen Phase 7 results: `eval/results/final/real.md`.

| Workflow | Same input: Phase 7 | Same input: now | New input: Phase 7 | New input: now |
| --- | --- | --- | --- | --- |
| amazon | pass | pass | fail | pass |
| target | – | skipped | – | skipped |
| target_search | – | skipped | – | skipped |
| starbucks | pass | skipped | pass | skipped |
| chipotle | pass after repair | skipped | pass after repair | skipped |
| doordash | pass | skipped | – | skipped |
| doordash_search | pass | skipped | pass after repair | skipped |
| settings_version | pass | skipped | – | skipped |
| settings_bluetooth | pass | skipped | – | skipped |
| gmail_newest | pass | skipped | – | skipped |
| gmail_search | pass | skipped | pass | skipped |
| calendar_today | pass | skipped | – | skipped |
| contacts_count | pass | skipped | – | skipped |
| maps_address | pass | skipped | pass | skipped |
| play_rating | pass | pass | fail | pass |
| youtube_search | – | skipped | – | skipped |
| ytmusic_artist | pass | skipped | pass | skipped |
| chrome_wikipedia | – | pass after repair | – | pass after repair |

## The full table (Phase 7's format)

| Stage | Passed |
| --- | --- |
| 1. First run: the agent gives a right answer | 2/3 |
| 2. Compile: the trace becomes a verified routine | 3/3 |
| 3. Same input: the routine reruns right with no model call | 2/3 (3 counting a repair) |
| 4. New input: right with a second input, no model call | 2/3 |
| Blocked by a bot check | 0 (none) |

Answers graded only by their shape (a price, a title) were also read by a person: 3 right, 0 the wrong value (not counted above), 3 not read yet. Verdicts: `real_hand_checks.json`, keyed by the exact answer.

| Workflow | App | Graded by | 1. First run | Agent | 2. Compiled | 3. Same input | 4. New input | Routine (same input) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| amazon | android | shape | pass | 2 actions, 4 calls, 25.59 s | ✅ 2 steps | pass | pass | 7.54 s, 0 calls |
| play_rating | android | shape | pass | 6 actions, 8 calls, 19.56 s | ✅ 3 steps | pass | pass | 3.2 s, 0 calls |
| chrome_wikipedia | android | truth | right, unverified | 10 actions, 15 calls, 70.56 s | ✅ 5 steps | pass after repair | pass after repair | 14.81 s, 3 calls |

Why each miss happened:

- **chrome_wikipedia**: first run right, unverified: Eiffel Tower opened 15 May 1889 · same input: pass after repair ({'opened_date': '15 May 1889'}; all steps and checks passed) · new input: pass after repair ({'opened_date': 'October 28, 1886'}; all steps and checks passed)
