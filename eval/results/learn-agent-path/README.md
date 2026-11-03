# The agent path and "Make it a routine": results

Run under [PROTOCOL.md](PROTOCOL.md) on `eval-final` = `cf78fa04f` (copy HEAD `cf78fa04f`, harness `75b2c0579`; resumed 2026-11-03T09:22:02+00:00 with harness `d259f3b98` after starbucks; resumed 2026-11-03T09:28:19+00:00 with harness `d259f3b98` after settings_bluetooth), 2026-11-03T09:05:08+00:00 → 2026-11-03T09:39:36+00:00.

- **Agent path:** right 14/18.
- **Learn rate:** saved 8/18.
- **New input:** right 3/3 saved routines with a second input; 2 of them with 0 model calls.

Starting state: Google Calendar's "Holidays" calendar on envoy-real is unchecked in the app, as it was for the eval (Nov 3 is Election Day, which made calendar_today ambiguous); the coordinator re-enables it after this pass.

| Row | a. Agent path | b. Make it a routine | c. Share | d. Call | Calls (a / compile / replay / d) |
| --- | --- | --- | --- | --- | --- |
| amazon | no answer (library routine amazon_search_price) | not learnable (ran library routine amazon_search_price, which ended failed) | – | – | 1 / – / – / – |
| target | blocked | blocked (the task ended needs_you) | – | – | 0 / – / – / – |
| target_search | no answer | not learnable (the task ended timed out) | – | – | 0 / – / – / – |
| starbucks | no answer (library routine starbucks_drink_calories) | not learnable (ran library routine starbucks_drink_calories, which ended timed out) | – | – | 0 / – / – / – |
| chipotle | right (library routine chipotle_item_price) | not learnable (ran library routine chipotle_item_price: this task ran the routine chipotle_item_price) | – | – | 1 / – / – / – |
| doordash | right | saved | listed | same input: right, 0 calls | 4 / 1 / 0 / 0 |
| doordash_search | right | saved | listed | new input: right, 0 calls | 5 / 1 / 0 / 0 |
| settings_version | right | saved | listed | same input: right, 0 calls | 8 / 1 / 0 / 0 |
| settings_bluetooth | right | saved | listed | same input: right, 0 calls | 6 / 1 / 0 / 0 |
| gmail_newest | right | saved | listed | same input: right, 0 calls | 4 / 1 / 0 / 0 |
| gmail_search | right (library routine gmail_search_subject) | not learnable (ran library routine gmail_search_subject: this task ran the routine gmail_search_subject) | – | – | 1 / – / – / – |
| calendar_today | right | not compilable (can't become a routine: the run answered a question ("No — Tuesday, November 3, 2026 shows 'Nothing ) | – | – | 16 / 1 / None / – |
| contacts_count | right | saved | listed | same input: right, 0 calls | 3 / 1 / 0 / 0 |
| maps_address | right | saved | listed | new input: right, 0 calls | 7 / 1 / 0 / 0 |
| play_rating | right (library routine play_app_rating) | not learnable (ran library routine play_app_rating: this task ran the routine play_app_rating) | – | – | 7 / – / – / – |
| youtube_search | right (library routine youtube_search_first_video) | not learnable (ran library routine youtube_search_first_video: this task ran the routine youtube_search_first_video) | – | – | 1 / – / – / – |
| ytmusic_artist | right | saved | listed | new input: right with model calls | 7 / 1 / 0 / 1 |
| chrome_wikipedia | right | replay failed (the replay stopped at scroll_to_opening_information: step scroll_to_opening_information: after-check) | – | – | 11 / 1 / 0 / – |
| target_search-retry | blocked | blocked (the task ended needs_you) | – | – | 0 / – / – / – |
| starbucks-retry | right (library routine starbucks_drink_calories) | not learnable (ran library routine starbucks_drink_calories: this task ran the routine starbucks_drink_calories) | – | – | 1 / – / – / – |

## Shape-graded answers to read by hand

- amazon: first-run answer 'outputs not found: first_result_price'
- chipotle: first-run answer 'menu item price: $4.90'
- doordash_search: first-run answer "Mountain Mike's Pizza"
- doordash_search: tool-call answer 'SH HAWAIIAN BBQ &DONUTS'
- play_rating: first-run answer 'star rating: 4.7 stars in 48 million reviews'
- youtube_search: first-run answer 'first video title: lofi hip hop radio .. beats to relax/study to'

## Supplementary pass: an empty routine library (a deviation, outside the headline)

Over MCP, run_task matches the tag's routine library first: in the pass above, 6 workflows (amazon, starbucks, chipotle, gmail_search, play_rating, youtube_search) ran a library routine instead of the agent, and "Make it a routine" can't take a routine's task, so the learn rate couldn't be measured for them. This pass runs just those 6, in the protocol's order, on a second fresh copy at the tag whose only change is its routine library deleted (`git rm -r data/routines`), under the same rules otherwise (the coordinator's call, Nov 3). Its rows stay out of the headline.

Run on `eval-final` = `cf78fa04f` (copy HEAD `cf78fa04f`, harness `2f918da4b`), 2026-11-03T09:41:51+00:00 → 2026-11-03T09:50:35+00:00.

- **Agent path:** right 5/6.
- **Learn rate:** saved 5/6.
- **New input:** right 3/5 saved routines with a second input; 3 of them with 0 model calls.

| Row | a. Agent path | b. Make it a routine | c. Share | d. Call | Calls (a / compile / replay / d) |
| --- | --- | --- | --- | --- | --- |
| amazon | right | saved | listed | new input: no answer | 4 / 1 / 0 / 0 |
| starbucks | right | saved | listed | new input: right, 0 calls | 10 / 1 / 0 / 0 |
| chipotle | no answer | not learnable (the task ended failed) | – | – | 29 / – / – / – |
| gmail_search | right | saved | listed | new input: right, 0 calls | 6 / 1 / 0 / 0 |
| play_rating | right | saved | listed | new input: no answer | 3 / 1 / 0 / 0 |
| youtube_search | right | saved | listed | new input: right, 0 calls | 5 / 1 / 0 / 0 |

Shape-graded answers to read by hand:

- amazon: first-run answer '$19.99'
- amazon: tool-call answer 'outputs not found: first_result_price'
- chipotle: first-run answer 'stopped after 25 steps'
- play_rating: first-run answer '4.7'
- play_rating: tool-call answer "Couldn't install 404.: the Play Store isn't in front (com.android.chrome)"
- youtube_search: first-run answer 'lofi hip hop radio .. beats to relax/study to'
- youtube_search: tool-call answer 'Carbonara | Basics with Babish'

## Deviations

- **The phone held by Target's hand-off (a harness fault).** Target's task ended needs_you: the tag lists Target as blocking emulators (`backend/api/emulator_blocked.json`), so it asked to use the Pixel 5 (declined), then waited for a takeover. The harness at `75b2c05` moved on without ending it, and it held envoy-real: the next three tasks waited for the phone and never reached it. target_search and starbucks hit the 6-minute cap (their rows are kept as recorded); chipotle's task was stopped while still waiting, before any row was written, so its row is its first attempt on the phone. The harness was stopped, the open tasks ended as the person would, the copy restarted on the same api-dir, and the pass resumed from chipotle with `d259f3b`, which ends any task left waiting for the person. target_search and starbucks ran once more at the end as `-retry` rows under the protocol's infrastructure-fault rule; the headline counts their originals (counted by their retries, the agent path would be 15/18: target_search-retry is blocked, starbucks-retry right).
- **A second stop, before gmail_newest started.** The suite's Gmail truth grader found no Gmail connection in the harness's checkout (`data/gmail/` is gitignored). No task had started. `data/gmail` was linked to the main checkout's read-only connection, as the eval's checkout had it, and the pass resumed from gmail_newest.
- **Classes amended after the pass** (`--report --amend`, harness `2f918da`, from the stopped copy's own task records, read-only; listed in results.json's `amended`). Target was recorded live as "no answer" and is "blocked" (the coordinator's call, the protocol's bot-check class): the harness's block pattern didn't know "blocks emulators", and stopping the task replaced its detail. The same rule makes target_search-retry blocked. The amend also names the library routine amazon and starbucks ran.
- **Library routines pre-empt the agent.** Over MCP, run_task first matches the tag's routine library: 6 workflows (amazon, starbucks, chipotle, gmail_search, play_rating, youtube_search) ran a library routine, not the agent. Their rows are kept as they happened (amazon's `amazon_search_price` failed with "outputs not found"), and "Make it a routine" refuses a routine's task, so the learn rate couldn't be measured for them. The supplementary pass above measures those 6 on a second copy with an empty library (the coordinator's call).
- **Harness commits** (eval/ only; both copies stayed at the tag): `75b2c05` started the pass, `d259f3b` resumed it twice, `2f918da` amended the classes and ran the supplementary pass.
