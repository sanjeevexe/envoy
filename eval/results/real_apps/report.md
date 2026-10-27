# Real-app test set (envoy-real, read-only)

Last run 2026-10-27T17:00:30+00:00. 18 workflows in 8 categories; 11 graded against ground truth, the rest by the answer's shape. Built by `eval/run_real_apps.py`; `--regression` reruns it after a routines change with no agent runs and cached compile answers.

| Stage | Passed |
| --- | --- |
| 1. First run: the agent gives a right answer | 13/18 |
| 2. Compile: the trace becomes a routine | 13/18 |
| 3. Same input: the routine reruns right with no model call | 5/18 (5 counting a repair) |
| 4. New input: right with a second input, no model call | 5/11 |
| Stopped by a bot check | 2 (target, target_search) |

First runs: 214 model calls in all.

| Workflow | Category | Graded by | 1. First run | 2. Compiled | 3. Same input | 4. New input | Agent | Routine (same input) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| amazon | shopping | shape | pass | ✅ 2 steps | pass | pass | 2 steps, 4 calls, 23.01 s | 8.51 s, 0 calls |
| target | shopping | shape | pass | ✅ 4 steps | bot check | n/a | 4 steps, 7 calls, 22.24 s | 7.72 s, 0 calls |
| target_search | shopping | shape | bot check | ❌ run ended 'handoff' with check None; only verified runs are  | – | – | 0 steps, 2 calls, 11.85 s | – |
| starbucks | food | truth | pass | ✅ 8 steps | pass | pass | 7 steps, 9 calls, 25.72 s | 9.94 s, 0 calls |
| chipotle | food | shape | pass | ✅ 11 steps | fail | input not learned | 14 steps, 18 calls, 47.44 s | 44.97 s, 3 calls |
| doordash | food | truth | pass | ✅ 1 steps | pass | n/a | 1 steps, 3 calls, 7.81 s | 6.89 s, 0 calls |
| doordash_search | food | shape | pass | ✅ 3 steps | pass | pass | 3 steps, 5 calls, 13.24 s | 8.51 s, 0 calls |
| settings_version | system | truth | failed | ❌ run ended 'failed' with check None; only verified runs are c | – | n/a | 8 steps, 12 calls, 29.06 s | – |
| settings_bluetooth | system | truth | pass | ✅ 3 steps | pass | n/a | 3 steps, 7 calls, 13.97 s | 2.68 s, 0 calls |
| gmail_newest | google | truth | step_limit | ❌ run ended 'step_limit' with check None; only verified runs a | – | n/a | 16 steps, 27 calls, 63.03 s | – |
| gmail_search | google | truth | pass | ✅ 3 steps | wrong | pass | 3 steps, 8 calls, 15.28 s | 3.8 s, 0 calls |
| calendar_today | google | truth | pass | ✅ 2 steps | fail | n/a | 3 steps, 15 calls, 21.1 s | 30.52 s, 2 calls |
| contacts_count | google | truth | pass | ✅ 0 steps | wrong | n/a | 13 steps, 21 calls, 49.69 s | 0.39 s, 0 calls |
| maps_address | maps | truth | pass | ✅ 6 steps | fail | pass | 5 steps, 11 calls, 46.38 s | 54.07 s, 2 calls |
| play_rating | store | shape | pass | ✅ 7 steps | fail | fail | 7 steps, 12 calls, 27.0 s | 43.43 s, 4 calls |
| youtube_search | media | shape | step_limit | ❌ run ended 'step_limit' with check None; only verified runs a | – | – | 15 steps, 26 calls, 46.54 s | – |
| ytmusic_artist | media | truth | pass | ✅ 2 steps | wrong | wrong | 3 steps, 4 calls, 9.45 s | 7.76 s, 0 calls |
| chrome_wikipedia | web | truth | right, unverified | ❌ run ended 'done_unverified' with check "none of ['Eiffel', ' | – | – | 13 steps, 23 calls, 94.27 s | – |

## Why each miss happened

- **target**: same input: bot check ({}; step open_my_target: after-checks failed: no match (best 0.00 < 0.80 or ambiguous, runner-up 0.00); no match (best 0.00 )
- **target_search**: first run bot check: Human verification press-and-hold check must be completed by user · not compiled: run ended 'handoff' with check None; only verified runs are compiled
- **chipotle**: same input: fail ({}; step scroll_to_chips_and_sides: after-checks failed: no match (best 0.00 < 0.80 or ambiguous, runner-up 0.00)) · new input: input not learned (; the compiled routine has no input the second value fits)
- **settings_version**: first run failed: stuck on the same screen after two recoveries · not compiled: run ended 'failed' with check None; only verified runs are compiled
- **gmail_newest**: first run step_limit: stopped after 25 steps · not compiled: run ended 'step_limit' with check None; only verified runs are compiled
- **gmail_search**: same input: wrong ({'first_result_subject': ', , , Google, , You shared some Google Account data wi; all steps and checks passed)
- **calendar_today**: same input: fail ({}; step tap_next_page: repair gave up: fail)
- **contacts_count**: same input: wrong ({}; all steps and checks passed)
- **maps_address**: same input: fail ({}; step scroll_to_street_address: after-checks failed: no match (best 0.00 < 0.80 or ambiguous, runner-up 0.00))
- **play_rating**: same input: fail ({}; step continue_onboarding: target not found: no match (best 0.42 < 0.80 or ambiguous, runner-up 0.41)) · new input: fail ({}; step continue_onboarding: target not found: no match (best 0.42 < 0.80 or ambiguous, runner-up 0.41))
- **youtube_search**: first run step_limit: stopped after 25 steps · not compiled: run ended 'step_limit' with check None; only verified runs are compiled
- **ytmusic_artist**: same input: wrong ({'artist': 'Queen • 5:55 • 2.7B plays'}; all steps and checks passed) · new input: wrong ({'artist': 'Ed Sheeran • 3:54 • 9.5B plays'}; all steps and checks passed)
- **chrome_wikipedia**: first run right, unverified: The Eiffel Tower opened in 1889 - Opening: 15 May 1889; 137 years ago as shown in the Wikipedia infobox · not compiled: run ended 'done_unverified' with check "none of ['Eiffel', 'Tower', '1889', 'Opening', '15'] is visible on the current screen"; only verified runs are compiled
