# Envoy on AndroidWorld

*Draft, Oct 28, 2026. Branch `androidworld`. Plan: `prompts/androidworld-plan.md`. Results: `eval/results/androidworld/`.*

AndroidWorld (Google Research; Rawles et al., 2024; Apache-2.0) is a benchmark of 116 parameterized tasks across 20 open-source Android apps, set up, randomized and scored by its own code on a live emulator. This page reports Envoy on it: the headline success rate, its cost and speed, where it fails and why, what general changes fixed, and what routines did across seeds.

## Setting

| | |
| --- | --- |
| Benchmark | AndroidWorld at commit `55ddaf5` (Oct 23, 2026), all 116 tasks of the `android_world` family |
| Seed | 30 (AndroidWorld's standard `--task_random_seed`), one instance per task, pass@1 |
| Scoring | AndroidWorld's own `is_successful`, through its own `suite_utils.run`: a task counts only if the agent ended the episode itself. Information-retrieval answers through its answer channel (`interaction_cache`) |
| Step budget | AndroidWorld's `int(10 × complexity)` per task (10 to 120; 2,369 in total) |
| Device | `AndroidWorldAvd`: Pixel 6 profile, 1080×2400, 420 dpi, API 33 Google APIs **arm64-v8a** (r17), 4 GB, on an Apple-silicon Mac, gRPC token required; AndroidWorld's one-time setup, two onboarding steps finished by hand (below) |
| Agent | Envoy as on `main` at `7da3b13` plus one trace-only commit: plan once, then one decision per step |
| Model | Muse Spark 1.3, `low` effort for steps and the plan, structured output; Contributor tier (`muse-spark-1.3-contributor`: same model, Meta may train on inputs) |
| Observation | the accessibility tree from uiautomator2, as a numbered element list; a 540 px screenshot only when the tree is sparse, the last action changed nothing, or the model asks (`look`); SAM 3.1 then grounding to place a `tap_point` |
| Actions | Envoy's: tap, long press, type (accessibility set-text), scroll, swipe, back, home, launch (by **package name**), tap_point, look, wait, done, fail, hand-off, ask |
| Memory, routines | off (no notes, no routine library) |
| Human help | none. Irreversible steps go through Envoy's policy gate and a script approves them (AndroidWorld's apps hold only synthetic data); every approval is counted |
| Leaderboard label | "Screenshot + A11y tree" (screenshots are available on request), though most steps are text only |

**What differs from the official protocol, and why:**
- **Envoy observes and acts with its own device layer**, not AndroidWorld's accessibility forwarder and adb actuation: that is the system under test. AndroidWorld still sets up, resets, and scores every task.
- **Steps:** one Envoy loop iteration is one step (a decision, a `look`, or a pop-up dismissed in code). The plan call is extra and acts on nothing. Answering takes one step (`done(answer)`), where AndroidWorld's reference agents take two (`answer`, then `status`).
- **The forwarder is parked while Envoy works.** uiautomator2's UiAutomation session suppresses accessibility services; AndroidWorld's forwarder then sometimes crashes with a "keeps stopping" dialog (seen once in the harness check). So the adapter disables it during the episode and restores it with android_env's own calls before AndroidWorld scores (about 3–4 s). Official agents never start UiAutomation.
- **arm64 image** on Apple silicon (AndroidWorld's docs use x86_64 on Linux), and AndroidWorld's own arm64 VLC build, which its setup picks automatically.
- **Setup:** Contacts' notification prompt says "Don’t allow" (curly apostrophe) where AndroidWorld's setup looks for "Don't allow", and OpenTracks' setup found no "Allow" to tap (its permissions are granted over adb), so its last two steps never ran. Both were finished with AndroidWorld's own functions (`eval/androidworld/aw_fix_setup.py`) and the two app snapshots re-saved.

## Harness proof

- **A do-nothing agent** (never acts, no model calls, says done at once) scored **0 of 7** (`harness-noop`): Bluetooth on, an expense deleted, a Markor note, the stopwatch, a contact, two information-retrieval questions. All set up and tore down without exceptions.
- **Tasks done by hand over adb** scored **1** each: add a contact, delete an expense, the next calendar event (answered "Board meeting" through the answer channel), Bluetooth on (`harness-hand`), the stopwatch (read through the restored forwarder) and a Markor note (`harness-hand2`). One more hand attempt at the stopwatch scored 0 because I submitted without checking; it's in the record.
- **Three harness problems found and fixed during the pilot and the first baseline hours** (each with evidence; the affected episodes were set aside and rerun, `eval/results/androidworld/baseline/invalidated/`):
  1. *The forwarder restore turned Wi-Fi back on.* android_env's `_configure_grpc` calls `attempt_enable_networking()` (airplane mode off, `svc wifi enable`), which undid the agent's work on SystemWifiTurnOff. The restore now sends only the forwarder's port. Rerun: 1.0.
  2. *The forwarder's first tree after a restart is empty* (0 elements, then 18 a few seconds later), and AndroidWorld's screen-based checks (Clock, Contacts, Browser) scored that empty screen: ClockStopWatchRunning scored 0 though Envoy finished it and its own check passed. The restore now waits for two non-empty reads; a paused and a running stopwatch done by hand score 1 through it.
  3. *AndroidWorld's app snapshots don't survive a reboot on API 33.* Android's boot-time `reconcileAppsData` deletes `/data/data/android_world` (no package owns it; confirmed with a marker file), and AndroidWorld then only logs "Skipping app snapshot loading", so apps keep their state from task to task. Any setup that restarts the emulator after `--perform_emulator_setup` (AndroidWorld's README cold-boots with `-no-snapshot`) would run this way. The runner now checks the snapshots before every stage and runs AndroidWorld's setup again when they are gone. This is worth reporting to AndroidWorld's maintainers.
- **Offline tests:** 13 for the Envoy side (the payload holds only the goal, budget, run id and configuration; the status → done mapping; the real loop honors the budget; trace digests), 5 for the AndroidWorld side (the agent shim with a fake environment). Envoy's 111 existing tests still pass.

## Baseline: Envoy as it is on `main`

All 116 tasks, seed 30, pass@1, run twice with the same agent, once on each tier: Contributor (`baseline`, Oct 27–28) and standard (`baseline-standard`, Oct 28). The dev/held-out split (`eval/results/androidworld/split.json`, 58/58, stratified by app and difficulty, seed 20261027) was committed before either run.

| | Contributor | standard |
| --- | --- | --- |
| **All 116** | **21.5 (18.5%)** | **21 (18.1%)** |
| dev half (58) | 13 (22.4%) | 9 (15.5%) |
| held-out half (58) | 8.5 (14.7%) | 12 (20.7%) |
| easy (61) | 19 (31.1%) | 16 (26.2%) |
| medium (36) | 2.5 (6.9%) | 2 (5.6%) |
| hard (19) | 0 | 3 (15.8%) |
| only episodes Envoy ended as done | 19 (16.4%) | 21 (18.1%) |
| cost at standard prices: total, median task | $4.71, $0.027 | $4.49, $0.028 |
| billed | $0.30 | $4.49 |
| Envoy time per task, median (model / device) | 61 s (37 / 27) | 38 s (19 / 19) |
| AndroidWorld time per task, median (setup to score) | 72 s | 47 s |
| steps used of the 2,349 budget; episodes out of steps | 2,146; 81 | 2,085; 81 |
| model calls, total (median per task) | 2,324 (13) | 2,276 (13) |
| approvals by the script (tasks) | 35 (14) | 33 (16) |

By app (successes, same order): Settings 5.5 / 10 of 14; Simple Calendar Pro 5 / 3 of 17; Broccoli 2 / 1 of 10; multi-app 2 / 1 of 11; Simple SMS 2 / 1 of 5; Markor 1 / 1 of 10; Clock 1 / 1 of 3; Contacts 1 / 1 of 2; Retro Music 1 / 1 of 4; Audio Recorder 1 / 0 of 2; Joplin 0 / 1 of 4; and 0 in both runs for Pro Expense (7), OpenTracks (6), Tasks (6), Chrome (3), OsmAnd (3), Camera (2), Files (2), VLC (2), Clipper, Simple Draw, Simple Gallery. Full tables: `eval/results/androidworld/baseline*/summary.json`.

**What the two runs say about noise.** They are the same agent, model, seed and tasks; the tier only changes who may train on the inputs. The totals agree (21.5 and 21), but the tasks don't: 10 were solved in both runs, 12 only on Contributor and 11 only on standard. So a half of 58 tasks moves by about four tasks between two identical runs (dev 13 → 9, held-out 8.5 → 12), and no before/after difference smaller than that means anything. The AndroidWorld paper saw the same spread across seeds (M3A with GPT-4 Turbo: 27.6%, 26.3% and 33.2%). Every comparison below is paired by task and counts the tasks gained and lost, not just the totals.

**Notes on the numbers.**
- *Scores from "failed" endings.* AndroidWorld scores the phone whenever the agent ends the episode, and the adapter passes Envoy's "failed" (stuck, giving up) as ended. On Contributor that scored 2.5 points: two "Verify" tasks (the setting was already as asked when Envoy gave up) and half of TurnOffWifiAndTurnOnBluetooth. The done-only row excludes them.
- *Cost cap.* Two standard episodes stopped at Envoy's $0.15 per-run cap (MarkorMergeNotes, OsmAndTrack). On Contributor the billed cost is about 1/16 of standard, so the cap never triggered there.
- *Time.* The standard tier answered faster (model time per task 19 s against 37 s). Device time also differed (19 s against 27 s), so part of the gap is the Mac's load during each run, not the tier.

## Why it fails (dev half only)

I read every dev-half failure of the Contributor baseline (45) step by step, with the screens the model saw, and labelled each with one decisive cause, its mechanism, the step where the episode was lost, and quotes from the trace (`eval/results/androidworld/baseline/labels_dev.jsonl`). The held-out half was not read. Ranked by failures:

| | Cause | Failures | Category (the prompt's six) |
| --- | --- | ---: | --- |
| A | **Could not open the app.** The plan named a package that isn't installed (`com.google.android.apps.nbu.files`, `net.osmand.plus`, `com.google.android.apps.tasks`) or none, `launch` took only package names, and the agent then pressed back on the home screen instead of opening the app drawer | 15 | planning & recovery 11, navigation & app knowledge 3, action mechanics 1 |
| B | **An action the model did not mean, inside the app.** It emitted `back` while its own reason said something else ("placeholder", "schema requires back?"), copied an earlier step's reasoning, or pressed back "to dismiss the keyboard" when none was up, which closed editors and threw away forms | 16 | action mechanics 12, perception 2, planning & recovery 2 |
| C | **Finished but never concluded.** Two correct dones were rejected by the plan's own check, written before seeing the app (a Camera thumbnail with no label; "Resume" on an already-paused stopwatch). Six had the work done, or the answer on screen, and kept "verifying" until the step budget ran out | 8 | verification 8 |
| D | **Could not read or keep content.** A 12,101-character file shown as its first 120 characters; notes re-read 29 and 11 times because nothing carried what was read across steps | 3 | planning & recovery 3 |
| E | **Dates.** The model never knew the phone's date (Sunday, October 15, 2023), so "this Thursday" and "this Monday" went to the wrong days | 2 | perception 1, planning & recovery 1 |
| F | **Task ambiguity.** "After 5:20pm" read strictly; AndroidWorld expects the event at 17:20 | 1 | answer format / harness / emulator / app |

Some evidence, quoted from the traces:
- A, RecipeAddSingleRecipe: back on the home screen 24 times in a row, its whole budget. Step 9's reason: "Mistake: should swipe up to open app drawer".
- A, OsmAndFavorite: `launch net.osmand.plus` fails ("has no launcher activity (is it installed?)"; the app is `net.osmand`), then 11 backs on home. Step 12's reason: "Need placeholder to trigger swipe access".
- B, ContactsNewContactDraft, step 1, expected result: "No, need launch contacts, back is wrong. Correction: should launch. But I must return JSON. Let's launch." The action it returned was back.
- B, RecipeAddMultipleRecipes, step 26: "Dismiss keyboard to access SAVE". The screen listed the SAVE button and no keyboard; back closed the filled-in form. This happened four times in the episode.
- C, MarkorDeleteNote: the note was deleted at step 7 (the list refreshed without it); step 8's reason was "Verify note deletion by checking list", and it went on searching until the budget ran out.
- D, MarkorMergeNotes, step 10: "Got first note content m4kMyOGWaENoPj6FqLjd, need second note". Step 11 opened the first note again.

**Two runtime problems under all of them.**
- *A ticking line hid the loops.* A running Clock timer's chip ticked on the home screen in 62 of the Contributor baseline's 116 episodes and 57 of the standard baseline's. AndroidWorld clears the Clock app's data between tasks, but it also resets the phone's clock each task, so the timer never ends and its chip stays. To Envoy every back on the home screen "changed the screen" (255 such false changes in the dev half), so its stuck detection didn't fire. In BrowserMaze it recorded 0 stuck recoveries in 17 backs. In the standard run, Envoy started that timer itself. In ClockTimerEntry ("Do not start the timer") its correct done was rejected by its own plan check, and on the next step it tapped Start. In the Contributor run it was left running by an earlier episode. With fix 5 the second done is accepted; no run with the fixes has had a timer on the home screen, so later runs did not face this handicap. Part of the improvement below is therefore Envoy no longer harming its own later tasks.
- *The model echoed its own history.* Each history line carried the model's own expected result. In 40 of 45 failures the model then repeated earlier expected results word for word (375 times), and its new actions followed the copied text, not the screen. NotesTodoItemCount, step 5, copies step 2: "Accidental back, need to recover", with Joplin open on the screen.

Measured from the digests over the whole run (`signals.py`), not just the labelled half: 1,057 of the Contributor baseline's 2,101 decisions and 861 of the standard baseline's 2,049 were made on the home screen or app drawer. The standard run's dev failures show the same mechanisms (placeholder reasons in 21 of 49, echoed expectations in 46, false "changed" on 31), so this is not a Contributor-tier effect.

## What I changed, and why

Each change is general (no app, task or AndroidWorld knowledge), has its own commit and an offline test, and was chosen from the dev-half analysis above before any re-measurement (`prompts/androidworld-plan.md`, Oct 28). They are written against current `main` (merged into the branch at `29dc9d4`), so each can be proposed as it stands.

| # | Commit | Cause it addresses | What changes |
| --- | --- | --- | --- |
| 1 | Apps open by the names people use; the plan sees the phone's apps | A | `launch` takes an app's name ("Files", "Simple Calendar Pro") as well as a package; labels come from the phone's own APKs (`aapt2 dump badging`, cached per app version); a wrong package guess is matched by its words; the planner gets the phone's app list |
| 1b | App names are read even when `ANDROID_HOME` has a "~" | A | Found in the first dev run (below): inside an episode the label reader never found `aapt2`, so names didn't resolve |
| 2 | A screen line that changes by itself is not progress | A, B (runtime) | Before acting, the loop looks again; lines that changed with no action (a ticking timer, a clock) are masked when deciding whether the action changed the screen, so stuck detection works |
| 3 | The history says what happened, not what the model expected | B (echo) | History lines no longer carry the model's own expected result |
| 4 | SCREEN says when the keyboard is open; back is explained; an action the model calls a placeholder is asked again | B | A keyboard line on SCREEN when (and only when) one is up; the prompt says what back does; an action whose reason calls it a placeholder or a mistake is not carried out and the step is asked again, once |
| 5 | Done as soon as the screen shows it; answers in the goal's format; a second done is accepted | C, F | Prompt; and when the plan's own check (written before seeing the app) rejects a done, the model is told why and a second done is accepted as `done_unverified` |
| 6 | Stuck recoveries start afresh once the agent is moving again | runtime | Three changed screens in a row reset the recovery count, so an early stall doesn't end a run that recovered |
| 7 | The model knows the phone's date | E | `TODAY:` from the phone, for the plan and every step |
| 8 | Long text is shown at length | D | Text fields and plain text up to 4,000 characters (8,000 per screen) instead of 120; list rows stay short |
| 9 | Routines: a swipe compiles as a swipe again, and a launch as a launch | routines | A bug on `main` since `ca50dab`: the compiler turned every swipe into a launch and dropped every launch step |
| 10 | ~~The step says what should happen before it picks the action~~ (reverted) | B | Reordered the schema's fields. It could not work: see 10b |
| 10b | The step's fields are named in the order the model should write them; an action's kind comes first | A, B | See below |

**10b: Meta's decoder writes JSON keys in alphabetical order.** I found this while checking fix 10 in the first dev run: the JSON still began with `"action"`. A two-field probe confirmed it, 6 of 6 on both tiers: a schema listing `zebra_first, middle, apple_last` (with descriptions saying "write this first") always came back as `apple_last, middle, zebra_first`. For Envoy that meant:
- The model wrote `action` before `reason` and `expected_result`, so its reasons were written after the fact. That is where the "placeholder" reasons come from: the action was already out.
- Inside an action, `type` sorted after every other field. An action begun the usual way, `{"type": …`, could only become one of the three kinds with no other field: back, home or look. Back was 44% of all actions in the Contributor baseline (916 of 2,101) and 37% on standard. Some answers came with a sentence before the JSON: a third on the standard tier (665 of 2,049), 13% on Contributor (283 of 2,212). In both baselines together, where that sentence said the model would open or launch something, the JSON said back 79 times and look 70 times, against 51 launches. One live call on the old schema reproduced the trace pattern exactly: `{"action": {"type": "back"}, "expected_result": "This is wrong; should be swipe but schema requires? Actually swipe allowed. Let's do swipe.", "reason": "placeholder", …}`.

The names the model sees are now aliases that sort in the order a person decides: `1_reason`, `2_expected_result`, `3_action`, `4_risk`, and in every action `act` (its kind) before its fields. Envoy's code, traces and routines keep their own names. On a clean single-screen probe both schemas chose the right swipe 25 of 25 times, so the failure needs a real episode's context, and only episodes can measure the fix.

## Dev-half rounds (Contributor tier, seed 30)

Each round runs the 58 dev tasks once, on the Contributor tier, as the dev work was agreed. The held-out half is not run until the final re-measure. The two baselines are on the same tasks; "p" is the exact two-sided sign test on the tasks that changed, paired by task. Two runs of an unchanged agent differed on about 23 of 116 tasks, so a few tasks either way is noise.

| Stage | Agent | Dev score | vs. Contributor baseline | vs. previous round | Cost (billed / at standard prices) | Median time per task | Model calls |
| --- | --- | ---: | --- | --- | --- | ---: | ---: |
| Contributor baseline | `main` | 13/58 | | | $0.17 / $2.41 | 58 s | 1,184 |
| Standard baseline | `main` | 9/58 | | | $2.33 / $2.33 | 36 s | 1,169 |
| Round 1 (`4c3c989`) | fixes 1–9 | **27/58** | +16 −2, p = 0.0013 | | $0.20 / $2.74 | 54 s | 1,188 |
| Round 2 (`598a6cd`) | round 1 + 10b | 25/58 | +15 −3, p = 0.0075 | +2 −4, p = 0.69 | $0.22 / $2.87 | 57 s | 1,149 |

Every success in rounds 1 and 2 ended with Envoy's own done: no task was scored a success after running out of steps.

**What each change did** (`fix_effects.py`, counted from Envoy's full traces of the 58 dev episodes; JSON in each stage's `fix_effects_dev.json`):

| # | Measure | Contributor baseline | Standard baseline | Round 1 | Round 2 |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | Launches that failed | 21 | 13 | 0 | 0 |
| 1 | Launches by an app's name (all opened it) | — | — | 105 | 101 |
| 1 | Decisions made on the home screen or app drawer | 539 (50%) | 442 (42%) | 68 (6%) | 60 (6%) |
| 2 | Home-screen decisions with a ticking timer on screen | 403 | 226 | 0 | 0 |
| 3 | Expected results that repeat an earlier one word for word | 397 | 337 | 137 | 97 |
| 4 | Reasons calling the action a placeholder | 69 | 39 | 0 | 0 |
| 4 | Actions asked again for that | — | — | 3 | 0 |
| 5 | A second done accepted after the plan's check rejected the first | 1 | 4 | 9 (all 9 scored 1) | 12 (all 12 scored 1) |
| 10b | Back, as a share of all actions | 42% | 37% | 13% | 8% |

Round 1 is the large step, and it is mostly one mechanism removed. In the baselines half of all decisions were made on the home screen, where a wrong package name failed to launch, and the model, writing `{"type": …` first, could only go back. Fix 1 took launch failures to zero; fix 5's second done turned 9 correct answers that the plan's check would have refused into successes. The two tasks round 1 lost (RetroPlayingQueue, TurnOnWifiAndOpenApp) ran out of steps in long in-app navigation. Neither shows a mechanism the fixes introduced.

Round 2 shows that 10b does what it was built to do, without a score change I can measure. Back fell from 13% to 8% of actions, and echoed expectations from 137 to 97. The score moved by two tasks the other way (25 against 27; 2 gained, 4 lost, p = 0.69), inside the noise. In the four losses Envoy repeated a check it had already made, the same way it did when it won them in round 1. In SimpleCalendarNextMeetingWithPerson it opened the same event and went back 4 times in both rounds. Round 1 answered on its last step (`October 27 2023 15:15`); round 2 ran out. I keep 10b because it fixes a real defect in how the step is written, but I don't claim a score effect for it.

**What still fails on dev after round 2** (33 tasks): 30 ran out of steps, 2 stopped with `failed`, 1 answered wrong. In 22 of the 33 Envoy made the same tap or launch on the same screen 3 or more times, led by MarkorMergeNotes (34 times), RecipeAddMultipleRecipesFromMarkor (20) and RetroPlayingQueue (15). Some of that repetition is the task's own (adding several items with the same button). The longest runs are something else: Envoy went back to re-read what it had already read. In RecipeAddMultipleRecipesFromMarkor, round 1 launched Markor 39 times in 60 steps, re-reading recipes.txt each time it reached Broccoli. That points to round 3: a working memory the model writes to itself.

<!-- Improvements, routines, leaderboard comparison and proposals follow once measured. -->
