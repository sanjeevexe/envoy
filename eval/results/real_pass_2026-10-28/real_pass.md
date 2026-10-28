# Real-app routine pass, 2026-10-28 17:22 EDT

On `265177e` (main with the repair fixes), envoy-real, standard tier, 6.5 min, 7 model calls, $0.0304 at standard prices. Method: Phase 7's routine reruns (`run_real_apps.run_one --regression`): each Phase 7 agent trace compiled again on this commit with Wonder's cached answer, then rerun on the same input and a second input. Target was left out (off limits). Frozen Phase 7 results: `eval/results/final/real.md`.

| Workflow | Same input: Phase 7 | Same input: now | New input: Phase 7 | New input: now |
| --- | --- | --- | --- | --- |
| amazon | pass | pass | fail | wrong value (by hand) |
| target | – | – | – | – |
| target_search | – | – | – | – |
| starbucks | pass | pass after repair | pass | pass |
| chipotle | pass after repair | pass after repair | pass after repair | pass after repair |
| doordash | pass | pass | – | – |
| doordash_search | pass | pass | pass after repair | pass |
| settings_version | pass | pass | – | – |
| settings_bluetooth | pass | pass | – | – |
| gmail_newest | pass | pass | – | – |
| gmail_search | pass | pass | pass | pass |
| calendar_today | pass | pass | – | – |
| contacts_count | pass | pass | – | – |
| maps_address | pass | pass | pass | pass |
| play_rating | pass | pass | fail | wrong value (by hand) |
| youtube_search | – | – | – | – |
| ytmusic_artist | pass | pass | pass | pass |
| chrome_wikipedia | – | – | – | – |
| starbucks (repaired v2) | – | pass | – | pass |

## The full table (Phase 7's format)

| Stage | Passed |
| --- | --- |
| 1. First run: the agent gives a right answer | 14/18 |
| 2. Compile: the trace becomes a verified routine | 14/18 |
| 3. Same input: the routine reruns right with no model call | 12/18 (14 counting a repair) |
| 4. New input: right with a second input, no model call | 5/10 |
| Blocked by a bot check | 0 (none) |

Answers graded only by their shape (a price, a title) were also read by a person: 10 right, 2 the wrong value (not counted above), 0 not read yet. Verdicts: `real_hand_checks.json`, keyed by the exact answer.

| Workflow | App | Graded by | 1. First run | Agent | 2. Compiled | 3. Same input | 4. New input | Routine (same input) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| amazon | android | shape | pass | 2 actions, 4 calls, 25.59 s | ✅ 2 steps | pass | wrong value (by hand) | 6.81 s, 0 calls |
| target | target | shape | skipped | – actions, – calls, – s | – | – | n/a | – |
| target_search | target | shape | skipped | – actions, – calls, – s | – | – | n/a | – |
| starbucks | starbucks | truth | pass | 8 actions, 10 calls, 32.41 s | ✅ 8 steps | pass after repair | pass | 20.25 s, 1 calls |
| chipotle | chipotle | shape | pass | 21 actions, 25 calls, 73.46 s | ✅ 22 steps | pass after repair | pass after repair | 44.46 s, 2 calls |
| doordash | dd | truth | pass | 1 actions, 3 calls, 12.47 s | ✅ 1 steps | pass | n/a | 6.95 s, 0 calls |
| doordash_search | dd | shape | pass | 2 actions, 4 calls, 18.35 s | ✅ 2 steps | pass | pass | 8.79 s, 0 calls |
| settings_version | android | truth | pass | 4 actions, 6 calls, 15.33 s | ✅ 3 steps | pass | n/a | 8.86 s, 0 calls |
| settings_bluetooth | android | truth | pass | 6 actions, 8 calls, 22.08 s | ✅ 3 steps | pass | n/a | 3.23 s, 0 calls |
| gmail_newest | android | truth | pass | 14 actions, 19 calls, 47.89 s | ✅ 1 steps | pass | n/a | 3.05 s, 0 calls |
| gmail_search | android | truth | pass | 3 actions, 5 calls, 21.96 s | ✅ 3 steps | pass | pass | 6.07 s, 0 calls |
| calendar_today | android | truth | pass | 0 actions, 2 calls, 4.39 s | ✅ 1 steps | pass | n/a | 2.11 s, 0 calls |
| contacts_count | android | truth | pass | 0 actions, 2 calls, 6.05 s | ✅ 1 steps | pass | n/a | 1.38 s, 0 calls |
| maps_address | apps | truth | pass | 4 actions, 6 calls, 19.3 s | ✅ 3 steps | pass | pass | 13.44 s, 0 calls |
| play_rating | android | shape | pass | 6 actions, 8 calls, 19.56 s | ✅ 3 steps | pass | wrong value (by hand) | 5.88 s, 0 calls |
| youtube_search | android | shape | error | 4 actions, 5 calls, 511.67 s | ❌ run ended 'error' with check None; only verified r | – | – | – |
| ytmusic_artist | youtube | truth | pass | 6 actions, 8 calls, 17.85 s | ✅ 5 steps | pass | pass | 5.45 s, 0 calls |
| chrome_wikipedia | android | truth | right, unverified | 10 actions, 15 calls, 70.56 s | ❌ run ended 'done_unverified' with check "none of [' | – | – | – |

Why each miss happened:

- **amazon**: new input: the right shape but the wrong value, by hand: the product (XIAWAO 6-pack) and the price ($9.99 ( $5.00 /count), a 2-pack in the row above) come from different rows; XIAWAO shows $8.49
- **target**: first run skipped: None
- **target_search**: first run skipped: None
- **starbucks**: same input: pass after repair ({'calories': '190 calories'}; all steps and checks passed)
- **chipotle**: same input: pass after repair ({'price': '$4.90'}; all steps and checks passed) · new input: pass after repair ({'price': '$4.90'}; all steps and checks passed)
- **play_rating**: new input: pass after repair ({'star_rating': '4.7 stars in 48 million reviews'}; all steps and checks passed) · new input: the right shape but the wrong value, by hand: the second input is 'Spotify: Learn Languages' (the test set swaps Duolingo for Spotify in the learned example), no such app; Play showed Duolingo and the repair read Duolingo's 4.7
- **youtube_search**: first run error: TimeoutExpired: Command '['/Users/sanjeevvarma/Library/Android/sdk/platform-tools/adb', '-s', 'emulator-5556', 'exec-out', 'screencap', '-p']' timed o · not compiled: run ended 'error' with check None; only verified runs are compiled
- **chrome_wikipedia**: first run right, unverified: Eiffel Tower opened 15 May 1889 · not compiled: run ended 'done_unverified' with check "none of ['Eiffel', 'Tower', '15', 'May', '1889'] is visible on the current screen"; only verified runs are com
