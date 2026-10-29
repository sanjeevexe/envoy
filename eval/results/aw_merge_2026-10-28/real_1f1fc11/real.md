# Real apps (envoy-real, read-only)

Run 1029020238 on `1f1fc11` with uncommitted changes, 2026-10-29 06:02 UTC, 14 min, standard tier. 113 model calls, $0.691 at standard prices ($0.691 billed).

| Stage | Passed |
| --- | --- |
| 1. First run: the agent gives a right answer | 10/18 |
| 2. Compile: the trace becomes a verified routine | 10/18 |
| 3. Same input: the routine reruns right with no model call | 6/18 (8 counting a repair) |
| 4. New input: right with a second input, no model call | 4/10 |
| Blocked by a bot check | 2 (target, target_search) |

Rows come from 2 runs: 1029020238 on `1f1fc11`: amazon, starbucks, chipotle, doordash, doordash_search, settings_version, settings_bluetooth, gmail_newest, gmail_search, calendar_today, contacts_count, maps_address, play_rating, youtube_search, ytmusic_artist, chrome_wikipedia; 1028023735 on `524b93a`: target, target_search.

Answers graded only by their shape (a price, a title) were also read by a person: 2 right, 0 the wrong value (not counted above), 7 not read yet. Verdicts: `real_hand_checks.json`, keyed by the exact answer.

| Workflow | App | Graded by | 1. First run | Agent | 2. Compiled | 3. Same input | 4. New input | Routine (same input) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| amazon | android | shape | pass | 3 actions, 5 calls, 52.76 s | ✅ 3 steps | wrong | fail | 10.3 s, 0 calls |
| target | target | shape | bot check | 0 actions, 2 calls, 10.1 s | ❌ run ended 'handoff' with check None; only verified | – | n/a | – |
| target_search | target | shape | bot check | 0 actions, 2 calls, 8.6 s | ❌ run ended 'handoff' with check None; only verified | – | – | – |
| starbucks | starbucks | truth | pass | 7 actions, 9 calls, 19.55 s | ✅ 8 steps | pass | pass | 12.98 s, 0 calls |
| chipotle | chipotle | shape | pass | 9 actions, 11 calls, 26.1 s | ✅ 9 steps | pass | pass | 13.29 s, 0 calls |
| doordash | dd | truth | pass | 9 actions, 12 calls, 34.12 s | ✅ 1 steps | wrong | n/a | 7.06 s, 0 calls |
| doordash_search | dd | shape | pass | 2 actions, 4 calls, 12.76 s | ✅ 3 steps | pass | pass | 8.98 s, 0 calls |
| settings_version | android | truth | pass | 6 actions, 8 calls, 21.45 s | ✅ 4 steps | pass | n/a | 11.43 s, 0 calls |
| settings_bluetooth | android | truth | pass | 7 actions, 11 calls, 22.03 s | ✅ 3 steps | pass | n/a | 3.61 s, 0 calls |
| gmail_newest | android | truth | error | – actions, – calls, – s | – | – | n/a | – |
| gmail_search | android | truth | error | – actions, – calls, – s | – | – | n/a | – |
| calendar_today | android | truth | pass | 0 actions, 2 calls, 5.01 s | ✅ 1 steps | pass after repair | n/a | 0.88 s, 0 calls |
| contacts_count | android | truth | step_limit | 25 actions, 28 calls, 72.5 s | ❌ run ended 'step_limit' with check None; only verif | – | n/a | – |
| maps_address | apps | truth | pass | 4 actions, 6 calls, 19.18 s | ✅ 3 steps | pass | pass | 13.87 s, 0 calls |
| play_rating | android | shape | pass | 1 actions, 3 calls, 6.9 s | ✅ 2 steps | pass after repair | fail | 3.0 s, 0 calls |
| youtube_search | android | shape | error | 0 actions, 0 calls, 0.73 s | ❌ run ended 'error' with check None; only verified r | – | – | – |
| ytmusic_artist | youtube | truth | error | 0 actions, 0 calls, 0.63 s | ❌ run ended 'error' with check None; only verified r | – | – | – |
| chrome_wikipedia | android | truth | error | 0 actions, 0 calls, 0.97 s | ❌ run ended 'error' with check None; only verified r | – | – | – |

Why each miss happened:

- **amazon**: same input: wrong ({}; all steps and checks passed) · new input: fail ({}; the user declined the approval)
- **target**: first run bot check: Bot verification requires human press-and-hold · not compiled: run ended 'handoff' with check None; only verified runs are compiled
- **target_search**: first run bot check: Bot verification press-and-hold requires user to complete · not compiled: run ended 'handoff' with check None; only verified runs are compiled
- **doordash**: same input: wrong ({'saved_delivery_address': '[redacted]'}; all steps and checks passed)
- **gmail_newest**: first run error: None
- **gmail_search**: first run error: None
- **calendar_today**: same input: pass after repair ({'todays_events_status': 'Nothing planned. Tap to create.'}; all steps and checks passed)
- **contacts_count**: first run step_limit: stopped after 25 steps · not compiled: run ended 'step_limit' with check None; only verified runs are compiled
- **play_rating**: same input: pass after repair ({'star_rating': '4.7 stars in 48 million reviews'}; all steps and checks passed) · new input: fail ({}; APIStatusError: Error code: 402 - Billing verification failed. Billing Issue. To use this API key, your team n)
- **youtube_search**: first run error: APIStatusError: Error code: 402 - Billing verification failed. Billing Issue. To use this API key, your team needs to resolve a billing issue first. T · not compiled: run ended 'error' with check None; only verified runs are compiled
- **ytmusic_artist**: first run error: APIStatusError: Error code: 402 - Billing verification failed. Billing Issue. To use this API key, your team needs to resolve a billing issue first. T · not compiled: run ended 'error' with check None; only verified runs are compiled
- **chrome_wikipedia**: first run error: APIStatusError: Error code: 402 - Billing verification failed. Billing Issue. To use this API key, your team needs to resolve a billing issue first. T · not compiled: run ended 'error' with check None; only verified runs are compiled
