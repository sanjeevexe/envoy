# AndroidWorld on the shipped default (hybrid), `main` 7ed4aa6, Nov 3 2026

*A separate run, kept apart from the Oct 28–29 numbers in `docs/androidworld-results.md`. Approved by the user on Nov 3 at 12:15 ET ("yes, let's run the full suite under those terms").*

**Result: 74 of 116 (63.8%). Held-out half: 36 of 58 (62.1%).** Against Oct 28's `final-standard` (57 of 116, 49.1%; held-out 31 of 58, 53.4%), the change is +20 −3 overall (p = 0.0005). On held-out alone it is +8 −3 (p = 0.23), which is within run-to-run noise. Cost per task is about 3.1 times as high.

## Setting
- **Envoy:** `main` at `7ed4aa6`, pinned detached in a clean checkout. `backend/` and `eval/androidworld/` there are identical to `eval-final` (`cf78fa0`), the code of the Nov 3 final evaluation.
- **Models:** the default profile, hybrid. Plan, step and repair ran on Muse Wonder 1.0, and the other jobs on Muse Spark 1.3. No `ENVOY_MODEL_*` was set.
  - Every episode records `profile: hybrid` and a step model of `muse-wonder-1.0`.
  - The cost log's 1,837 calls split as: step 1,593 and plan 181 on Wonder; choose 17 and grounding 12 on Spark; SAM 34.
- **Per-task cost cap:** $0.50 when steps run on Wonder (`WONDER_TASK_CAP_USD`). That is the shipped cap; `final-standard` ran with $0.15.
- **AndroidWorld:** `55ddaf5`, unchanged. All 116 tasks, seed 30, instance 0, pass@1. AndroidWorld's own step budgets (`int(10 × complexity)`) and the standard tier. The run's only config was `{"tier": "standard"}`, as in `final-standard`.
- **Emulator:** AndroidWorldAvd, a Pixel 6 (1080x2400, 420 dpi) on API 33 Google APIs arm64, 4 GB, cold-booted. AndroidWorld's setup re-ran on boot and restored 24 of 24 app snapshots.
- **When:** 12:22–14:46 ET, 2 h 24 min including setup.
- **No tuning, no code changes, no reruns:** every task ran once. One stop and resume, described below, lost and repeated no episode.

## Against `final-standard` (Oct 28), paired by task
| | `final-standard` | This run | Gained / lost | Sign test |
| --- | ---: | ---: | --- | --- |
| **All 116** | 57 (49.1%) | **74 (63.8%)** | +20 −3 | p = 0.0005 |
| **Held-out half (58)** | 31 (53.4%) | **36 (62.1%)** | +8 −3 | p = 0.23 |
| Dev half (58) | 26 (44.8%) | 38 (65.5%) | +12 −0 | p = 0.0005 |
| Easy (61) | 40 | 50 | +11 −1 | p = 0.006 |
| Medium (36) | 12 | 19 | +8 −1 | p = 0.04 |
| Hard (19) | 5 | 5 | +1 −1 | p = 1 |
| held-out: easy / medium / hard | 19 / 7 / 5 of 30 / 18 / 10 | 23 / 9 / 4 | | |
| dev: easy / medium / hard | 21 / 5 / 0 of 31 / 18 / 9 | 27 / 10 / 1 | | |
| cost: total; mean, median per task | $4.67; $0.040, $0.030 | $14.54; $0.125, $0.090 | | |
| cost per solved task | $0.082 | $0.197 | | |
| Envoy time per task, median (model / device) | 37.9 s (19.5 / 17.6) | 51.8 s (32.7 / 16.1) | | |
| Envoy time per task, mean | 49 s | 64 s | | |
| AndroidWorld time per task, median (setup to score) | 46 s | 60 s | | |
| steps used of the 2,349 budget; model calls | 1,777; 2,018 | 1,600; 1,837 | | |
| ended: done / unverified done / failed / step limit / cost cap | 46 / 13 / 2 / 51 / 4 | 54 / 22 / 3 / 35 / 2 | | |
| dones that AndroidWorld scored 0 | 2 | 2 | | |

- **Gained, dev (12):** ExpenseAddMultiple, ExpenseDeleteMultiple2, MarkorDeleteAllNotes, MarkorDeleteNote, OsmAndFavorite, RecipeAddMultipleRecipes, RetroPlayingQueue, SimpleCalendarNextMeetingWithPerson, SportsTrackerActivityDuration, SystemBluetoothTurnOn, SystemBluetoothTurnOnVerify, VlcCreateTwoPlaylists.
- **Gained, held-out (8):** ExpenseAddSingle, FilesDeleteFile, MarkorDeleteNewestNote, MarkorMoveNote, SimpleCalendarDeleteOneEvent, SimpleCalendarEventsInTimeRange, SystemBluetoothTurnOff, TurnOffWifiAndTurnOnBluetooth.
- **Lost, all held-out (3):**
  - ExpenseDeleteDuplicates hit the step limit at 12 steps; on Oct 28 it was done in 9.
  - RecipeAddMultipleRecipesFromImage said done after 58 steps, but AndroidWorld scored it 0.
  - SimpleDrawProCreateDrawing hit the step limit at 18.

**By app** (Oct 28 → now, of n): Settings 10 → 14 of 14; Simple Calendar Pro 12 → 15 of 17; Markor 3 → 7 of 10; Pro Expense 3 → 5 of 7; Broccoli 5 → 6 of 10; multi-app 6 → 5 of 11; Simple SMS 4 → 4 of 5; Joplin 3 → 3 of 4; Clock 3 of 3; Audio Recorder 2 of 2; Contacts 2 of 2; VLC 1 → 2 of 2; Retro Music 1 → 2 of 4; Files 0 → 1 of 2; OpenTracks 0 → 1 of 6; OsmAnd 0 → 1 of 3; Camera 1 of 2; Simple Draw 1 → 0 of 1. Still 0: Tasks (6), Chrome (3), Clipper, Simple Gallery.

## How to read it
- **Noise:** two runs of the same agent differed on about 23 of 116 tasks (Oct 28), so a half of 58 moves by about four tasks between identical runs.
  - The overall gain (+20 −3) is well outside that.
  - The held-out gain (+8 −3, net +5) is not: on held-out alone this run doesn't show a change.
  - Against Oct 29's held-out re-measure (`held-out-fdce597-fix`, 30.5 of 58, on spark), it is +9 −3 (p = 0.15).
- **This isn't a model-only comparison.** `final-standard` ran the Oct 28 branch: backend `a80b976`, spark, a $0.15 cap. This run is the shipped `main`, which also has:
  - the $0.50 per-task cap on Wonder (`final-standard` hit its $0.15 cap 4 times, this run its $0.50 cap twice);
  - Phase 7's three SkyLark follow-ups;
  - the answer fix, including the answer-format note now in AndroidWorld's adapter;
  - the contacts planner line and the empty-state check (`105d04e`);
  - the on/off switch check (`57d5fc7`, from a real-app pass) and the repair JSON fix (`a594136`).

  One run can't split the gain among these. The model-only evidence is still the Oct 28 20-task comparison on the same code, where hybrid had 14 of 20 against spark's 9.
- **Same tasks, same model, a week apart:** on those 20 tasks this run got 13 of 20, against hybrid's 14 (+1 −2) and spark's 9 (+4 −0) on Oct 28.
- **The held-out half isn't as clean as on Oct 28.**
  - It was run on Oct 28 and Oct 29, and its traces were read for mechanism counts.
  - 11 of the 20 tasks behind the Oct 30 decision to make hybrid the default are held-out tasks.
  - The agent changes since Oct 28 came from real-app passes, not from AndroidWorld's held-out results.
- **Where it gained:** easy and medium tasks, across both halves. Hard tasks didn't move (5 of 19).
  - Episodes that ran out of steps fell from 51 to 35.
  - Envoy ended 76 tasks as done (54 verified, 22 unverified), against 59 (46 and 13). In each run, 2 of those dones scored 0.
- **What it costs:**
  - About 3.1 times as much per task. Wonder's step price is roughly three times Spark's, and the calls per task fell slightly.
  - About 2.4 times as much per solved task.
  - About 14 s more per task, all of it model time; device time is unchanged.

## Harness and safety
- **adb:** android_env ran with the shared-server guard (`never_restart_the_adb_server`). `aw_env.py` at `7ed4aa6` is byte-identical to androidworld `3631542`, and `run_aw.py` checks for the guard at startup.
  - During setup, VLC's APK failed to install on emulator-5560, the known arm64 failure. The guard waited and listed devices instead of restarting the adb server.
  - Every command used `adb -s emulator-5560`. The Pixel 5, running another session's batch, stayed connected throughout.
- **No API errors:** no outage retries, no API loss mid-episode, no harness exceptions, no crash dialogs.
- **One stop and resume:** at 12:25:45 the run was stopped after episode 3 had been scored and checkpointed, and before episode 4 started. It was resumed at 12:26 to raise the process's daily cap from $12 to $16, at the coordinator's request.
  - AndroidWorld skipped the 3 finished tasks.
  - `run.json` records both sessions.
- **Spend:** $14.54 on Muse, all standard-tier billing, by the episodes and the cost log alike. That is over the $12 estimate and under the run's $16 stop.

## Files
- `run.json`: commits, setting, both sessions.
- `episodes/<Task>__s<seed>.json`: AndroidWorld's score joined with Envoy's record, including `models` and `profile`.
- `traces/`: digests of Envoy's traces.
- `summary.json`: `report.py` on this stage.
- `compare_final-standard.json`: `report.py final-standard 2026-11-03-hybrid-7ed4aa6`.
- `comparison-final-standard.json`: the tables above, with difficulty, app, cost and time, the held-out comparison with Oct 29, and the 20-task subset.

## Publishing
This run meets the bar set before it ran: overall at least 49.1% and held-out at least 53.4%. That makes it a candidate for the README and the site. It changes nothing published until the user approves, through the coordinator. If it is used, it should be reported as "the shipped default, hybrid, on `main`", next to the Oct 28 numbers and with the caveats above. It is not a replacement for the held-out estimate of the Oct 28 changes.
