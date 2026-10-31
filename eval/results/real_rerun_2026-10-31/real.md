# Real apps (envoy-real, read-only)

Run 1031152557 on `a594136` with uncommitted changes, 2026-10-31 19:25 UTC, 1 min, standard tier, the `hybrid` profile (Muse Wonder for compile, plan, repair, step; Muse Spark for the rest). 9 model calls, $0.149 at standard prices ($0.149 billed).

| Stage | Passed |
| --- | --- |
| 1. First run: the agent gives a right answer | 12/18 |
| 2. Compile: the trace becomes a verified routine | 12/18 |
| 3. Same input: the routine reruns right with no model call | 9/18 (9 counting a repair) |
| 4. New input: right with a second input, no model call | 6/11 |
| Blocked by a bot check | 2 (target, target_search) |

Rows come from 2 runs: 1031150937 on `a594136`: amazon, target, target_search, starbucks, chipotle, doordash, doordash_search, settings_version, settings_bluetooth, calendar_today, contacts_count, maps_address, play_rating, youtube_search, ytmusic_artist, chrome_wikipedia; 1031152557 on `a594136`: gmail_newest, gmail_search.

Answers graded only by their shape (a price, a title) were also read by a person: 1 right, 0 the wrong value (not counted above), 11 not read yet. Verdicts: `real_hand_checks.json`, keyed by the exact answer.

| Workflow | App | Graded by | 1. First run | Agent | 2. Compiled | 3. Same input | 4. New input | Routine (same input) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| amazon | android | shape | pass | 2 actions, 4 calls, 28.73 s | ✅ 2 steps | pass | pass | 5.98 s, 0 calls |
| target | target | shape | bot check | 0 actions, 2 calls, 11.93 s | ❌ run ended 'handoff' with check None; only verified | – | n/a | – |
| target_search | target | shape | bot check | 0 actions, 2 calls, 15.29 s | ❌ run ended 'handoff' with check None; only verified | – | – | – |
| starbucks | starbucks | truth | pass | 7 actions, 9 calls, 26.42 s | ✅ 8 steps | pass | pass | 11.79 s, 0 calls |
| chipotle | chipotle | shape | pass | 12 actions, 14 calls, 46.15 s | ✅ 11 steps | fail | input not learned | 44.9 s, 2 calls |
| doordash | dd | truth | pass | 8 actions, 11 calls, 39.93 s | ❌ the run answered a question ('1 Hacker Way'), but  | – | n/a | – |
| doordash_search | dd | shape | pass | 2 actions, 4 calls, 25.98 s | ✅ 2 steps | pass | pass | 10.1 s, 0 calls |
| settings_version | android | truth | pass | 5 actions, 7 calls, 26.02 s | ✅ 3 steps | pass | n/a | 9.62 s, 0 calls |
| settings_bluetooth | android | truth | right, unverified | 3 actions, 6 calls, 16.68 s | ❌ run ended 'done_unverified' with check "'Bluetooth | – | n/a | – |
| gmail_newest | android | truth | wrong | 0 actions, 2 calls, 7.14 s | ✅ 1 steps | wrong | n/a | 0.78 s, 0 calls |
| gmail_search | android | truth | pass | 3 actions, 5 calls, 17.71 s | ✅ 4 steps | pass | pass | 6.08 s, 0 calls |
| calendar_today | android | truth | failed | 13 actions, 14 calls, 56.38 s | ❌ run ended 'failed' with check None; only verified  | – | n/a | – |
| contacts_count | android | truth | pass | 0 actions, 3 calls, 7.84 s | ✅ 1 steps | pass | n/a | 0.72 s, 0 calls |
| maps_address | apps | truth | pass | 2 actions, 4 calls, 12.51 s | ✅ 2 steps | pass | pass | 5.0 s, 0 calls |
| play_rating | android | shape | pass | 0 actions, 2 calls, 5.95 s | ✅ 1 steps | pass | fail | 27.43 s, 0 calls |
| youtube_search | android | shape | pass | 2 actions, 4 calls, 17.87 s | ✅ 2 steps | pass | pass | 4.56 s, 0 calls |
| ytmusic_artist | youtube | truth | pass | 2 actions, 4 calls, 17.23 s | ✅ 2 steps | wrong | wrong | 6.12 s, 0 calls |
| chrome_wikipedia | android | truth | right, unverified | 12 actions, 15 calls, 68.39 s | ❌ run ended 'done_unverified' with check "none of [' | – | – | – |

Why each miss happened:

- **target**: first run bot check: Target app shows 'Quick verification - Press & hold to confirm you're a human (and not a bot)' - this CAPTCHA/bot check must be done by you. · not compiled: run ended 'handoff' with check None; only verified runs are compiled
- **target_search**: first run bot check: Target is showing a 'Quick verification - Press & hold to confirm you're a human (and not a bot)' CAPTCHA/bot check. Please complete the press & hold  · not compiled: run ended 'handoff' with check None; only verified runs are compiled
- **chipotle**: same input: fail ({}; step select_nearby_location: target not found: no match (best 0.26 < 0.80 or ambiguous, runner-up 0.22)) · new input: input not learned (; the compiled routine has no input the second value fits)
- **doordash**: not compiled: the run answered a question ('1 Hacker Way'), but no output can be read back from its own final screen: output 'saved_delivery_address': '1 Hacker Way
- **settings_bluetooth**: first run right, unverified: Bluetooth is turned on · not compiled: run ended 'done_unverified' with check "'Bluetooth on/off status' is not visible"; only verified runs are compiled
- **gmail_newest**: first run wrong: [code] - Your Spotify login code · same input: wrong ({'newest_email_subject': '[code] - Your Spotify login code, button Cop; all steps and checks passed)
- **calendar_today**: first run failed: stuck on the same screen after two recoveries · not compiled: run ended 'failed' with check None; only verified runs are compiled
- **play_rating**: new input: fail ({'star_rating': None}; outputs not found: star_rating)
- **ytmusic_artist**: same input: wrong ({}; all steps and checks passed) · new input: wrong ({}; all steps and checks passed)
- **chrome_wikipedia**: first run right, unverified: 1889 · not compiled: run ended 'done_unverified' with check "none of ['1889'] is visible on the current screen"; only verified runs are compiled
