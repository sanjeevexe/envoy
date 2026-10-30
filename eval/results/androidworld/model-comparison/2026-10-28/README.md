# AndroidWorld: model profiles compared (2026-10-28)

Same 20 tasks (6 that Envoy passed and 14 it failed in the final standard-tier run), AndroidWorld seed 30, the same harness and step budgets, standard tier, one run per task per profile, per-episode cost cap $0.60 for all.

| Profile | Success | Mean steps | Mean wall s | Model calls (by model) | Cost | Per task | 116-task estimate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| spark | 9/20 | 10.8 | 39.0 | 272 (spark-1.3 268, sam-3.1 4) | $0.60 | $0.030 | $3.50 |
| hybrid | 14/20 | 9.7 | 51.3 | 259 (spark-1.3 4, wonder-1.0 249, sam-3.1 6) | $2.09 | $0.104 | $12.09 |
| wonder | 13/20 | 9.4 | 56.6 | 251 (wonder-1.0 247, sam-3.1 4) | $2.07 | $0.104 | $12.02 |

| Task | spark | hybrid | wonder |
| --- | --- | --- | --- |
| ContactsAddContact | **pass** (done, 7 steps, $0.019) | **pass** (done, 8 steps, $0.059) | **pass** (done, 6 steps, $0.042) |
| ExpenseAddSingle | **pass** (done, 9 steps, $0.023) | **pass** (done, 10 steps, $0.088) | **pass** (done, 10 steps, $0.092) |
| ExpenseDeleteDuplicates2 | fail (step_limit, 17 steps, $0.066) | fail (step_limit, 17 steps, $0.282) | fail (step_limit, 18 steps, $0.260) |
| ExpenseDeleteSingle | **pass** (done, 4 steps, $0.011) | **pass** (done, 7 steps, $0.079) | **pass** (done, 4 steps, $0.040) |
| FilesDeleteFile | fail (step_limit, 22 steps, $0.053) | **pass** (done_unverified, 11 steps, $0.120) | **pass** (done, 10 steps, $0.116) |
| MarkorAddNoteHeader | fail (step_limit, 11 steps, $0.030) | fail (step_limit, 11 steps, $0.106) | fail (step_limit, 11 steps, $0.127) |
| MarkorCreateNote | **pass** (done, 11 steps, $0.025) | **pass** (done, 15 steps, $0.154) | fail (step_limit, 16 steps, $0.139) |
| MarkorDeleteNewestNote | **pass** (done, 8 steps, $0.033) | fail (step_limit, 9 steps, $0.125) | **pass** (done, 7 steps, $0.125) |
| MarkorMoveNote | fail (step_limit, 13 steps, $0.037) | **pass** (done, 12 steps, $0.141) | fail (step_limit, 14 steps, $0.134) |
| NotesMeetingAttendeeCount | **pass** (done, 5 steps, $0.013) | **pass** (done, 6 steps, $0.058) | **pass** (done, 5 steps, $0.048) |
| NotesTodoItemCount | fail (step_limit, 9 steps, $0.022) | fail (step_limit, 9 steps, $0.084) | fail (step_limit, 8 steps, $0.089) |
| OsmAndFavorite | **pass** (done, 7 steps, $0.018) | **pass** (done, 7 steps, $0.068) | **pass** (done, 7 steps, $0.069) |
| RecipeDeleteDuplicateRecipes | fail (step_limit, 10 steps, $0.025) | fail (step_limit, 10 steps, $0.099) | fail (step_limit, 10 steps, $0.102) |
| RetroCreatePlaylist | fail (step_limit, 23 steps, $0.044) | **pass** (done, 18 steps, $0.132) | **pass** (done, 18 steps, $0.141) |
| SimpleCalendarDeleteEvents | **pass** (done, 11 steps, $0.052) | **pass** (done, 12 steps, $0.157) | **pass** (done, 12 steps, $0.181) |
| SimpleCalendarEventsInNextWeek | fail (step_limit, 8 steps, $0.032) | fail (step_limit, 7 steps, $0.111) | fail (step_limit, 8 steps, $0.125) |
| SimpleSmsResend | fail (step_limit, 10 steps, $0.030) | **pass** (done, 4 steps, $0.046) | **pass** (done, 4 steps, $0.056) |
| SimpleSmsSendReceivedAddress | **pass** (done, 10 steps, $0.024) | **pass** (done, 9 steps, $0.071) | **pass** (done, 9 steps, $0.072) |
| SportsTrackerActivityDuration | fail (step_limit, 10 steps, $0.025) | **pass** (done_unverified, 5 steps, $0.061) | **pass** (done_unverified, 7 steps, $0.079) |
| SystemBluetoothTurnOn | fail (step_limit, 10 steps, $0.021) | **pass** (done_unverified, 6 steps, $0.044) | **pass** (done_unverified, 5 steps, $0.035) |

Files: `comparison.json` (every number above), `traces/<profile>.md` (each episode's plan and actions with the agent's reasons), `raw/<profile>/` (AndroidWorld's episode records and Envoy's traces, copied from the comparison checkout).

## Verdict

**Update, Oct 30:** the user made `hybrid` the default (branch `coord/hybrid-default`): they judged the 3× rule too strict for real use, since saved routines replay mostly on Spark jobs and the extra cost lands on first runs and repairs, where hybrid helps.

**Spark stays the default; `hybrid` stays available.** Hybrid passed 14 of 20 against Spark's 9 (+5, which meets the rule's
"≥ 5 of 20"), but cost $0.104 per task against $0.030, **3.46×**, and the rule asks for under 3× per task. (Per *passed*
task the ratio is 2.2×, $0.149 against $0.067; the rule is written per task, so that is the one applied.) Wonder on every
job (`wonder`) was no better than hybrid: 13 of 20 at the same cost. So Wonder's gain is in the plan and step jobs, and
putting matching, extraction and grounding on Wonder as well buys nothing here.

**How sure:** one run per task per profile, and these tasks vary from run to run. On the same seed, Spark passed 3 tasks
here that it failed in the final standard run (ExpenseAddSingle, MarkorDeleteNewestNote, OsmAndFavorite; each cost under
$0.04, so the cost cap wasn't why), and it kept all 6 of its earlier passes. A margin of 5 is at the edge of that noise.

**Where Wonder helps (read from the traces of the 7 tasks that changed between spark and hybrid).** Hybrid gained 6, and
in 5 of them Spark spent its steps on a wrong strategy and ran out:
- SimpleSmsResend: Spark looked for a "Resend" item in the message's menus (there is none) until it ran out of steps; hybrid
  retyped the message and sent it in 4.
- SystemBluetoothTurnOn: Spark followed a "See all · Bluetooth will turn on" label into empty device lists; hybrid went to
  Connection preferences › Bluetooth and flipped the switch in 6.
- RetroCreatePlaylist: Spark looked for "add songs" inside the empty playlist for 6 steps, then added songs from the library
  and ran out on the third; hybrid finished with 6 steps to spare.
- MarkorMoveNote: Spark lost 2 steps to a stray search and made the move on its last step; hybrid moved the note in 9 and
  checked the folder.
- SportsTrackerActivityDuration: Spark browsed and searched the track list; hybrid opened the Oct 12 track and read
  2:15:00 = 135 minutes.
- FilesDeleteFile: Spark pressed Delete and OK by step 9, then spent 13 steps trying to confirm and never finished (scored
  0); hybrid deleted it and finished in 11.

**Where it hurt.** Hybrid's one loss and both of `wonder`'s losses have the same shape: the work was done (or nearly), and
then a replan sent the agent somewhere else instead of finishing. MarkorDeleteNewestNote (hybrid): deleted the right note by
step 7, then the replan re-sorted the list and opened another note, out of steps. MarkorMoveNote (`wonder`): reached
"SELECT THIS FOLDER" at step 9 like hybrid, then searched instead of looking in the folder, out of steps. MarkorCreateNote
(`wonder`): Markor's extension field dropped the dot, it renamed the file, and ran out of steps verifying.

**Time:** hybrid's episodes averaged 51 s and `wonder`'s 57 s against Spark's 39 s, mostly model latency; with AndroidWorld's
setup and scoring, each profile's 20 tasks took 20, 20 and 22 minutes.

**What a full 116-task rerun would cost.** The final standard run (Spark) cost $4.67 for all 116 ($0.040 per task: its tasks
are longer than these 20). At the ratios measured here: `spark` about $4.70, `hybrid` about **$16**, `wonder` about $16. (The
table's estimate, cost per task here × 116, is lower because these 20 tasks have small step budgets.) Not run: that's the
user's call. Under hybrid, the harness's default per-run cap of $0.15 scales with the step price to $0.48.

**Next, if Wonder is wanted where it pays:** escalation (Spark first, Wonder after a step that made no progress or a
replan) would keep Spark's cost on the easy tasks (7 of the 9 Spark passes cost under $0.025) and give Wonder the stuck
ones. And all three of Wonder's losses suggest one small agent fix: once the last irreversible step succeeds and the
screen shows the result, finish instead of replanning.

**Fairness and infrastructure.** Same 20 tasks, seed 30, the same harness (the AndroidWorld branch at 1c2a680 with only the
profile code added: `claude/aw-model-compare`, eafd184), standard tier, the same step budgets, one run each, a $0.60
per-episode cap for all (the agent's own cap scales with the step price; the costliest episode was $0.28). No episode
errored and none was rerun. AndroidWorld's setup after the emulator's boot logged VLC's `INSTALL_FAILED_NO_MATCHING_ABIS` (VLC is installed)
and skipped dialogs it had dismissed before; an adb SIGTRAP on Markor's `mkdir` came once in the spark and once in the
hybrid stage, and its retry handled it. Both appear in AndroidWorld's own logs too. **Found afterwards:** each of those three first-try failures made android_env's `AdbController` restart the adb server that every session on the Mac shares (`kill-server`, then `start-server`), around 20:38, 20:45 and 21:01; the last overlapped Phase 7's SkyLark suites. AndroidWorld fixed its harness in androidworld 3631542 (cherry-picked onto `claude/aw-model-compare` as f4f943f); our own episodes weren't affected.
Three hybrid passes and two `wonder` passes are `done_unverified`: Envoy's own success check couldn't confirm them, and
AndroidWorld's scorer did. `sam-3.1` is the segmentation model the agent uses on drawn screens (OsmAnd); it isn't part of a
profile. Spend: $4.76 of the $8 share (this checkout's cost log matches the episode records to the cent).
