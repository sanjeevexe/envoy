# Envoy on AndroidWorld

*Oct 28–29, 2026, with a separate run of the shipped default on Nov 3 (below the headline). Branch `androidworld`. Plan: `prompts/androidworld-plan.md`. Results: `eval/results/androidworld/`.*

AndroidWorld (Google Research; Rawles et al., 2024; Apache-2.0) is a benchmark of 116 parameterized tasks across 20 open-source Android apps, set up, randomized and scored by its own code on a live emulator. This page reports Envoy on it: the headline success rate, its cost and speed, where it fails and why, what general changes fixed, and what routines did across seeds.

**The shipped default, Nov 3:** 74 of 116 tasks (63.8%), +20 −3 over the Oct 28 run (p = 0.0005; not a model-only comparison; below).

**Headline.** Envoy as on `main` before these changes (the Oct 28 baseline) solved 21 of 116 tasks (18.1%) on the standard tier. With 13 general agent changes, found on the dev half only (merged into `main` on Oct 29), it solved 57 (49.1%). On the held-out half, never used to choose a change, that is 31 of 58 (53.4%) against 12 (+20 −1, p < 0.0001). Both runs are seed 30, pass@1, at about $0.04 and 38 s per task (median $0.030).

**Routines.** Envoy compiled 59 routines from its solved runs, and 22 did their own seed-30 task on their own. On three new seeds of their 23 tasks:
- they did 55 of 69 instances, against the full agent's 63, at 1 model call against 6, $0.002 against $0.012, and 8 s against 19 s;
- on the 51 instances whose structure doesn't change with the seed, they did all 51 (the agent 48);
- with the agent run where a routine failed, 67 of 69.

**Re-measured on a staging tree before the merge (Oct 29).**
- **The tree:** a staging branch (`736a6e4`): `main` with the 13, Phase 7's three SkyLark follow-ups and the answer fix (below).
- **Held-out half:** 30.5 of 58 against `main`'s 12 (+21 −2, p = 0.0001). Against Oct 28's 31: +5 −6, so unchanged within noise.
- **Cost and time:** $2.44 for the 58 tasks, a median of $0.034 and 41 s.

**Real apps, side by side.**
- **The problem:** Phase 7's real-app pass found two read-only questions turning into searches on the 13: contacts went from 1 step to 25, DoorDash from 2 to 11.
- **The answer fix,** measured offline before and after, kept AndroidWorld's answers and the safety probe level.
- **Phase 7's same-day rerun of that fix against `main`:** 13 of 18 same-input workflows passed, against 9. Chipotle went from the step limit to a pass, and there were far fewer actions.
- **Contacts still looped once in 3,** each time the plan asked for "the full contacts list". A planner line removes those plans in replays (33/120 → 0/90). Phase 7 then checked it live, and it merged on Oct 29 (`105d04e`).

**Routines:** a separate compiler fix reads answers by their place on the screen. On new seeds, the three question routines now do 9 of 9 (0 before).

**The shipped default, Nov 3 (a separate run).** Envoy as it ships, `main` at `7ed4aa6` on the default `hybrid` profile (agent steps on Muse Wonder, a $0.50 per-task cap), solved 74 of 116 tasks (63.8%), and 36 of 58 (62.1%) on the held-out half: seed 30, pass@1, the standard tier, at a mean $0.125 a task (`eval/results/androidworld/2026-11-03-hybrid-7ed4aa6/README.md`). It sits next to the Oct 28 numbers above and doesn't replace them:
- **Against Oct 28's 57,** it gained 20 tasks and lost 3 (p = 0.0005). On the held-out half alone the change is +8 −3 (p = 0.23), within the run-to-run noise measured below, so it shows no held-out change.
- **It isn't a model-only comparison.** `main` also has Phase 7's three SkyLark follow-ups, the answer fix, the contacts planner line and empty-state check, the on/off switch check and the repair JSON fix, and a higher cost cap ($0.50 against $0.15). One run can't split the gain among them. The model-only evidence is still the 20-task comparison of Oct 28 (hybrid 14 of 20, Spark 9).
- **The held-out half is less clean than it was:** it was run on Oct 28 and 29, its traces were read for mechanism counts, and 11 of the 20 tasks behind the Oct 30 choice of `hybrid` as the default are held-out tasks.
- **It costs more:** about 3.1 times as much per task, and about 14 s more, all of it model time.

The rest of this page shows how each number was made.

## Setting

| | |
| --- | --- |
| Benchmark | AndroidWorld at commit `55ddaf5` (Oct 23, 2026), all 116 tasks of the `android_world` family |
| Seed | 30 (AndroidWorld's standard `--task_random_seed`), one instance per task, pass@1 |
| Scoring | AndroidWorld's own `is_successful`, through its own `suite_utils.run`: a task counts only if the agent ended the episode itself. Information-retrieval answers through its answer channel (`interaction_cache`) |
| Step budget | AndroidWorld's `int(10 × complexity)` per task (10 to 120; 2,349 in total) |
| Device | `AndroidWorldAvd`: Pixel 6 profile, 1080×2400, 420 dpi, API 33 Google APIs **arm64-v8a** (r17), 4 GB, on an Apple-silicon Mac, gRPC token required; AndroidWorld's one-time setup, two onboarding steps finished by hand (below) |
| Agent | Baselines: Envoy as on `main` at `7da3b13` plus one trace-only commit: plan once, then one decision per step. Final: the branch after round 3 (backend as `a80b976`), `main`'s agent plus the 13 changes below |
| Model | Muse Spark 1.3, `low` effort for steps and the plan, structured output. Standard tier (`muse-spark-1.3`) for the headline runs; the Contributor tier (`muse-spark-1.3-contributor`: same model, Meta may train on inputs, about 1/16 the price) for one baseline and the dev rounds |
| Observation | the accessibility tree from uiautomator2, as a numbered element list; a 540 px screenshot only when the tree is sparse, the last action changed nothing, or the model asks (`look`); SAM 3.1 then grounding to place a `tap_point` |
| Actions | Envoy's: tap, long press, type (accessibility set-text), scroll, swipe, back, home, launch (by package name on `main`; by app name too after fix 1), tap_point, look, wait, done, fail, hand-off, ask |
| Memory, routines | off: no notes, no routine library. Fix 11's working memory lasts one episode only |
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
| 11 | What the model keeps from a screen comes back on later steps | D, B | The step gains a first field, `0_remember`: what on this screen the task will need later (text to copy, values to compare or add up, what is still to do), word for word. Kept items come back on every later step as REMEMBERED (data, not instructions), oldest dropped past 6,000 characters. Chosen from round 1 and 2 traces: re-reading loops |
| 4b | The keyboard counts as open when the navigation bar shows its buttons | B | Fix 4's keyboard line never appeared in round 1 or 2: on this emulator the screen dump leaves out the keyboard's own window. The navigation bar's keyboard buttons (`android:id/input_method_nav_*`) are there while it is up: after 78 of 87 typing steps, against 6 of 138 backs |

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
| Round 3 (`a80b976`) | round 2 + 11, 4b | **29/58** | +17 −1, p = 0.0001 | +6 −2, p = 0.29 | $0.21 / $2.85 | 52 s | 1,118 |

Every success in rounds 1–3 ended with Envoy's own done: no task was scored a success after running out of steps.

**What each change did** (`fix_effects.py`, counted from Envoy's full traces of the 58 dev episodes; JSON in each stage's `fix_effects_dev.json`):

| # | Measure | Contributor baseline | Standard baseline | Round 1 | Round 2 | Round 3 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | Launches that failed | 21 | 13 | 0 | 0 | 0 |
| 1 | Launches by an app's name (all opened it) | — | — | 105 | 101 | 67 |
| 1 | Decisions made on the home screen or app drawer | 539 (50%) | 442 (42%) | 68 (6%) | 60 (6%) | 58 (6%) |
| 2 | Home-screen decisions with a ticking timer on screen | 403 | 226 | 0 | 0 | 0 |
| 3 | Expected results that repeat an earlier one word for word | 397 | 337 | 137 | 97 | 84 |
| 4 | Reasons calling the action a placeholder | 69 | 39 | 0 | 0 | 0 |
| 4 | Actions asked again for that | — | — | 3 | 0 | 0 |
| 5 | A second done accepted after the plan's check rejected the first | 1 | 4 | 9 (all 9 scored 1) | 12 (all 12 scored 1) | 9 (all 9 scored 1) |
| 10b | Back, as a share of all actions | 42% | 37% | 13% | 8% | 5% |
| 4b | Screens shown with the keyboard line | 0 | 0 | 0 | 0 | 186 |
| 11 | Steps that kept something for later (episodes) | — | — | — | — | 507 (45 of 58) |

Round 1 is the large step, and it is mostly one mechanism removed. In the baselines half of all decisions were made on the home screen, where a wrong package name failed to launch, and the model, writing `{"type": …` first, could only go back. Fix 1 took launch failures to zero; fix 5's second done turned 9 correct answers that the plan's check would have refused into successes. The two tasks round 1 lost (RetroPlayingQueue, TurnOnWifiAndOpenApp) ran out of steps in long in-app navigation. Neither shows a mechanism the fixes introduced.

Round 2 shows that 10b does what it was built to do, without a score change I can measure. Back fell from 13% to 8% of actions, and echoed expectations from 137 to 97. The score moved by two tasks the other way (25 against 27; 2 gained, 4 lost, p = 0.69), inside the noise. In the four losses Envoy repeated a check it had already made, the same way it did when it won them in round 1. In SimpleCalendarNextMeetingWithPerson it opened the same event and went back 4 times in both rounds. Round 1 answered on its last step (`October 27 2023 15:15`); round 2 ran out. I keep 10b because it fixes a real defect in how the step is written, but I don't claim a score effect for it.

**What still fails on dev after round 2** (33 tasks): 30 ran out of steps, 2 stopped with `failed`, 1 answered wrong. In 22 of the 33 Envoy made the same tap or launch on the same screen 3 or more times, led by MarkorMergeNotes (34 times), RecipeAddMultipleRecipesFromMarkor (20) and RetroPlayingQueue (15). Some of that repetition is the task's own (adding several items with the same button). The longest runs are something else: Envoy went back to re-read what it had already read. In RecipeAddMultipleRecipesFromMarkor, round 1 launched Markor 39 times in 60 steps, re-reading recipes.txt each time it reached Broccoli. That points to round 3: a working memory the model writes to itself.

Round 3 adds that memory (11) and the keyboard fix (4b): **29/58**, the best dev score, +6 −2 against round 2 (p = 0.29, so within noise on its own) and +17 −1 against the Contributor baseline. The model kept something in 507 of 995 steps, in 45 of the 58 episodes, without spending steps on it (it is a field of the step, and output tokens fell slightly: 272k against 277k). The clearest effect is on relaunching: launches by name fell from 101 to 67. In RecipeAddMultipleRecipesFromMarkor, rounds 1 and 2 launched Markor 39 and 40 times. Round 3 read recipes.txt once, kept the recipes (`Recipe: Thai Peanut Noodle Salad description: A quick and easy meal…`) and entered the first one complete from memory. It went back once for the second recipe's ingredients, lost count of which recipes it had already added, and ran out of steps entering the third (10 launches). It still failed, but on a later problem. VlcCreateTwoPlaylists, never solved before, was solved.

The keyboard line now appears (186 screens), and on the screens I checked it is right. 169 of the 186 follow a tap or typing. The rest follow scrolls inside a form being filled, where the keyboard stays up, and one screenshot shows it: uiautomator2's own slim input bar ("Clear Text · Done · Switch IME"). Neither loss traces to the round's changes. In SystemBluetoothTurnOn Envoy took wrong turns in Settings and kept nothing. In MarkorCreateNoteFromClipboard its first done came at step 12 of 14; the plan's check rejected it, and the budget ran out before a second. By the rule fixed before the result (`prompts/androidworld-plan.md`), the final set is the branch after round 3.

Round 3's episodes record two commits: `a80b976` for the first ones and `70ed7a8` (the plan's decision rule, committed during the run) for the rest. Their `backend/` is identical.

## Final re-measure: all 116 on the standard tier

The branch after round 3 (backend as `a80b976`: fixes 1–9, 10b, 11 and 4b), run once on all 116 tasks: seed 30, pass@1, the standard tier (the model Envoy uses in the product), stage `final-standard`, Oct 28. It's compared with the standard baseline, task by task. The held-out half was never read and never run between the baseline and this run, so it is the estimate. The dev half is where the fixes were chosen, and it's reported beside held-out for that reason.

| | Standard baseline (`main`) | Final (the branch) | Tasks gained / lost | Paired sign test |
| --- | ---: | ---: | --- | --- |
| **Held-out half (58)** | **12 (20.7%)** | **31 (53.4%)** | +20 −1 | p < 0.0001 |
| Dev half (58) | 9 (15.5%) | 26 (44.8%) | +18 −1 | p = 0.0001 |
| **All 116** | **21 (18.1%)** | **57 (49.1%)** | +38 −2 | p < 0.0001 |
| held-out: easy / medium / hard | 8 / 1 / 3 of 30 / 18 / 10 | 19 / 7 / 5 | | |
| dev: easy / medium / hard | 8 / 1 / 0 of 31 / 18 / 9 | 21 / 5 / 0 | | |
| only episodes Envoy ended as done | 21 | 57 | | |
| dones AndroidWorld scored 0 | 2 of 23 | 2 of 59 | | |
| cost (billed = standard prices): total, median task | $4.49, $0.028 | $4.67, $0.030 | | |
| cost per solved task | $0.214 | $0.082 | | |
| Envoy time per task, median (model / device) | 38 s (19 / 19) | 38 s (19 / 18) | | |
| AndroidWorld time per task, median (setup to score) | 47 s | 46 s | | |
| steps used of the 2,349 budget; model calls | 2,085; 2,276 | 1,777; 2,018 | | |
| screenshots sent; `look`s; stuck recoveries | 362; 205; 75 | 201; 87; 23 | | |
| stopped by Envoy's $0.15 per-run cap | 2 | 4 | | |
| approvals by the script (tasks) | 33 (16) | 104 (37) | | |

**The held-out gain is as large as the dev gain** (+19 against +17), so these changes did not just fit the half they were chosen on. Against the Contributor baseline, the same run is +23 −1 on held-out. The three Contributor dev rounds (27, 25 and 29 of 58) and this standard-tier run's dev half (26) agree within the noise, so the tier doesn't explain the change.

By app (baseline → final, of n): Simple Calendar Pro 3 → 12 of 17; Settings 10 → 10 of 14; multi-app 1 → 6 of 11; Broccoli 1 → 5 of 10; Markor 1 → 3 of 10; Pro Expense 0 → 3 of 7; Simple SMS 1 → 4 of 5; Joplin 1 → 3 of 4; Clock 1 → 3 of 3; Audio Recorder 0 → 2 of 2; Contacts 1 → 2 of 2; Camera 0 → 1 of 2; VLC 0 → 1 of 2; Simple Draw 0 → 1 of 1; Retro Music 1 → 1 of 4. Still 0: Tasks (6), OpenTracks (6), Chrome (3), OsmAnd (3), Files (2), Clipper, Simple Gallery. By AndroidWorld's own task tags: data entry 3 → 19 of 34, data edit 1 → 9 of 19, search 2 → 8 of 22, information retrieval 2 → 7 of 19, complex UI 1 → 6 of 18; still weak: repetition 2 → 3 of 12, transcription 1 → 2 of 8, math and counting 0 → 1 of 7, memorization 0 → 0 of 6.

**The cost is about the same, per task, and less than half per success.** Each model call costs about 23% more: input tokens per call 2,502 → 2,916, output 206 → 240, measured on the first 49 tasks. Long text is shown in full (fix 8), REMEMBERED is added (11), and every step writes a `0_remember` field. Envoy makes fewer calls (2,018 against 2,276), so the run cost 4% more in total. The per-run cap of $0.15 on `main` stopped 4 long tasks before their step budget, against 2 in the baseline. The script approved 104 irreversible steps in 37 tasks, against 33 in 16, because Envoy now gets to the saving, deleting and sending.

**Each change's mechanism on the held-out half** (`fix_effects.py`; held-out traces were read only for these counts, after the run):

| # | Measure (held-out, 58 episodes) | Standard baseline | Final |
| --- | --- | ---: | ---: |
| 1 | Launches that failed | 7 | 1 |
| 1 | Launches by an app's name that opened it | — | 73 |
| 1 | Decisions on the home screen or app drawer | 419 (42%) | 59 (7%) |
| 2 | Home-screen decisions with a ticking timer on screen | 197 | 0 |
| 3 | Expected results repeating an earlier one word for word | 299 | 36 |
| 4 | Reasons calling the action a placeholder | 35 | 0 |
| 4b | Screens shown with the keyboard line | 0 | 159 |
| 5 | Second dones accepted (scored 1) | 4 (4) | 5 (4) |
| 8 | Screens with text longer than the old 120-character cut | 9 | 21 |
| 10b | Back, as a share of all actions | 37% | 5% |
| 11 | Episodes that kept something for later (steps) | — | 49 (340) |

Every mechanism moved on held-out the way it did on dev. The score gain belongs to the set as a whole. One run can't split it among the changes, and the dev rounds can only roughly (round 1: fixes 1–9, +14; round 2: 10b, about 0; round 3: 11 and 4b, +4 within noise).

**What still fails** (59 tasks, both halves): 51 ran out of steps, 4 hit the cost cap, 2 stopped as `failed`, and 2 said done wrongly.
- MarkorMergeNotes: the note was created with the wrong content.
- SystemBluetoothTurnOff: Envoy said done with the switch shown off (`[5] Switch (id: switch_widget) (off)`), and AndroidWorld scored 0. That's likely Bluetooth still changing state after the task's setup; the baseline failed it too.

The failures are concentrated in the tags above and in apps where every screen is new to the model (Tasks, OpenTracks, OsmAnd): long tasks that repeat an action over many items, count or add up what they read, or carry content across apps. In 22 of round 2's 33 dev failures Envoy repeated the same action on the same screen 3 or more times; round 3's memory helped (RecipeAddMultipleRecipesFromMarkor, above) but didn't finish those tasks.

**Two outages during the run.** From 10:49 to 11:12 this Mac couldn't reach Meta's API, and 98 episodes in a row failed in seconds. A second outage from about 11:56 cost one more. All 99 were set aside with the reason (`eval/results/androidworld/final-standard/invalidated/README.md`) and rerun into the same stage. The runner now waits out an outage instead of burning through tasks. None of the 116 counted episodes had an API error.

## Routines across seeds

AndroidWorld randomizes each task's parameters by seed, so a routine compiled from a seed-30 run can be replayed on other instances of the same task: other names, dates, amounts, files. That is the question Envoy's routines are built for. The library is separate from Envoy's own (`eval/results/androidworld/routines/`, never `data/routines/`), and every replay is scored by AndroidWorld.

**Compiling.** Every solved seed-30 run was compiled with Envoy's own compiler (`compile_trace`, Muse Wonder), as `main` compiles any run: 21 from the standard baseline and 38 more from the final run. All 59 compiled, for $3.41, in a median of 15.6 s each. They have a median of 6 steps (at most 37). The compiler dropped 147 of the runs' 649 steps (looks, dead taps, back-tracks). 36 routines take inputs and 42 return outputs. 25 carry compiler warnings, mostly an input the run never used, or an output not on the run's final screen.

**Same-seed replay, no repair, no agent** (stage `routines-verify`). Each routine's own task on seed 30, through AndroidWorld's runner. The request is matched against all 59 routines the way Envoy matches any request. Only a routine that does the task on its own is kept. **23 of the 59 did their task on their own** (22 routines: both minimum-brightness tasks matched the same one), and one more did half of it (0.5). Of the other 36: an after-check failed in 11 (two of them typed fields read back empty), 7 finished every step and check yet scored 0 (and the half one), 6 needed the user for an input, 5 couldn't find or tell apart a target, a before-check failed in 4, and 2 couldn't find an output. When a routine passed, it took a median of 7.9 s with the match (4.7 s for the steps), 1 model call and $0.0025, against the agent's 22 s, 9 calls and $0.015 on the same tasks.

Why the others failed, on the very screens they were compiled from. Four of these are general problems in `main`'s routine path, not AndroidWorld quirks:
- **Popup menus read as another app.** When an app's own popup menu has focus, `dumpsys window` reports `PopupWindow:51b096d`, and Envoy's focus parser (`backend/devices/android.py:32`) takes that as the package. Every "app in front" check on a step taken from a menu fails: "before-checks failed: app in front is PopupWindow:30f4ef5" (Broccoli twice, Retro Music).
- **A typed field is found again by its empty-state label.** Contacts adds a new empty "Phone" row once a number is typed. The after-check `field_equals {text: Phone}` finds the new empty field and reports "field holds ''" for a step that worked. The agent's own trace shows both fields: `[12] EditText "Phone: +13920741751"` and `[17] EditText "Phone" (empty)`.
- **Identical buttons in a list.** Per-row delete icons tie: "no match (best 1.00 … runner-up 0.98)". The locator needs to anchor them to their row's text.
- **Inputs the matcher can't fill.** "Tomorrow" or "in two weeks" needs the phone's date, which the matcher doesn't have (5 calendar tasks stop as `needs_user` with `event_day` missing). Expenses that are in a picture on the phone are asked of the user.
- **Eight routines finished every step and check, and AndroidWorld scored seven of them 0 and one 0.5.**
  - Two questions came back with no answer. The compiler had dropped the output as "not on the final screen", and the routine had no date input, so it answered nothing (SimpleCalendarAnyEventsOnDate, SimpleCalendarEventsOnDate).
  - One answered with the screen's text instead of what it means: `Convert to note` for "is this note a to-do?", where AndroidWorld wants True.
  - Two named the wrong event (SimpleCalendarEventOnDateAtTime, SimpleCalendarNextEvent). These routines take no date or time input, so they read whatever the calendar showed.
  - Three passed their own checks without the task being done: the Markor edit, maximum brightness (it reported `0.0`), and the note-and-SMS task, which ran all 14 steps including the send, yet AndroidWorld gave it 0.5, half of its two-part check. Their checks were too weak to notice.

**Across seeds** (stages `routines-seeds` and `agent-seeds`, Oct 28, 22:13–23:58, standard tier). The 22 verified routines ran on instances 1–3 of their 23 tasks: three new seeds each, so 69 episodes with new names, dates, numbers, messages and files. Repair was allowed and the agent fallback was off, so the routine is measured alone. The full agent ran on the same 69 instances, from the same commit. Envoy's backend is the same in every episode; the commits recorded (`e9594f0`, `b82e512`, `cdd130e`) differ only in the report and the harness. It is the branch with `main` merged in and the three SkyLark follow-ups, so the agent here is not exactly `final-standard`'s.

| | Routine | Full agent | Routine, then the agent where it failed |
| --- | ---: | ---: | ---: |
| **Success** | **55/69 (80%)** | **63/69 (91%)** | **67/69 (97%)** |
| Model calls, median | 1 | 6 | 1 |
| Cost at standard prices, median (total) | $0.0021 ($0.16) | $0.0122 ($1.24) | $0.0022 ($0.49) |
| Envoy time, median | 8.3 s | 19.0 s | 8.7 s |
| AndroidWorld time, setup to score, median | 16.3 s | 33.0 s | |
| Approvals by the script | 24 | 31 | |

- **Where both did the task (51 instances):**

  | | Routine | Agent |
  | --- | ---: | ---: |
  | Time | 7.5 s | 19.1 s |
  | Model calls | 1 | 6 |
  | Cost | $0.0020 | $0.0116 |

  That's about 2.5 times faster and 6 times cheaper.
- **Where only one did it:**
  - The routine alone: 4 instances (ExpenseDeleteSingle twice, RecipeAddSingleRecipe once, and RecipeDeleteMultipleRecipesWithConstraint once, explained below).
  - The agent alone: 12.
- **The last column is computed, not run.** It pairs each routine episode with the agent's own episode on the same instance. In Envoy the fallback would start wherever the routine stopped, not from a fresh setup.

**Repairs and versions.** One local repair in 69 episodes: SimpleSmsReply's launch step, one extra model call, and the episode then succeeded. No routine needed a new version.

**Where the structure changes with the seed**, so that a routine compiled on seed 30 can't follow, and where it doesn't:
- **Same structure, new parameters** (17 tasks, 51 instances): the routines did **51 of 51**, the agent 48. This covers messages, files, folders, recordings, photos, stopwatches, expenses, recipes, and Bluetooth, Wi-Fi and brightness.
- **The answer sits somewhere else** (NotesMeetingAttendeeCount, NotesRecipeIngredientCount, SimpleCalendarLocationOfEvent): 0 of 9.
  - The matcher filled the inputs right ('Quality Assurance Review', 'Lasagna', 'Movie night'), and the routine opened the right note or event.
  - Then it stopped with "outputs not found". Each output's extraction was tied to seed 30's own answer:
    - a pattern with the example's ingredient and unit (`\d+/\d+ cup` + "spirulina"), where the ingredient isn't even an input;
    - the source note's wording ("individuals were present");
    - `expect_digits` on a location, because seed 30's was "100 Main St Chicago". The new seeds' were "Virtual", "The Coffee Bean" and "Sarah's apartment".
  - The agent did all 9.
  - Recompiling the three sources with `aw-merge`'s compiler (773536a, a local commit not published, with Phase 7's row fix) gives the same extracts (`routines/recompiled-aw-merge-773536a/`). This gap is separate from past_trip's, and is in the project's backlog.
- **A different app** (OpenAppTaskEval's "Open the camera app" twice, TurnOnWifiAndOpenApp's "…then open the clock app" once):
  - The routines were compiled from runs that opened Contacts and Settings, and don't take the app as an input.
  - The matcher correctly declined all three (`no_routine`) rather than open the wrong app.
  - The agent did all 3.
- **A different amount of work** (RecipeDeleteMultipleRecipesWithConstraint): AndroidWorld creates up to 3 recipes with the ingredient in their directions, and fewer, down to none, when it can't generate them (`recipe.py`, `generate_random_params`).
  - Seed 30's instance ("black garlic") had none. The source run, `main`'s own agent, searched, found nothing, and was scored right.
  - The routine learned "search, delete nothing". It was right on instance 2 and wrong on instances 1 and 3 (parsley, herbs), where it passed all its own checks and deleted nothing.
  - The agent failed all three as well (43 calls each, out of steps).
  - A routine verified on one instance can be verified on a degenerate one.

**What this says about routines.** On tasks whose shape doesn't change, a compiled routine replaces the agent:
- it did at least as well (51/51 against 48/51);
- it took one model call instead of six;
- it cost a sixth as much and took 40% of the time.

Its failures are all of one kind: something the run never showed as an input (which app, where the answer is, how many items) is baked into the routine. Each is a general fix for `main`'s compiler or matcher, not an AndroidWorld quirk:
- extractions that keep only what holds for any instance (no example values in patterns, an entity the goal names as an input);
- the app as an input when the goal names one;
- a routine verified on more than one instance, or flagged when its source run did nothing irreversible for a goal that asks for it.

**The answer fix in the compiler, measured (Oct 29).** A separate change to the compiler (`263fb7e` in `main`; first made as `1f1fc11` on a local branch):
- it reads an answer by where it sits on the screen, not by the source run's example value;
- it refuses a run that had nothing to do.

I replayed its recompiled routines through the same harness:
- **Seed 30, stage `answers-verify`:** 23 of 30 tasks passed, the same check as before.
- **Seeds 1–3, stage `answers-seeds`, 90 episodes:** the same instances as above. 39 of them were rerun after the API's billing outage; the set-aside ones are kept with a README.
- **The phone's date:** the harness now gives the matcher the phone's date, October 2023 (`19c40cb`).

| On the 23 tasks above, 3 seeds each | Before (Oct 28) | After |
| --- | ---: | ---: |
| All | 55/69 | 54/69 |
| The three question routines | 0/9 | 9/9 |
| Tasks whose routine is now refused | 10/12 | 0/12 |
| Everything else | 45/48 | 45/48 |
| Median model calls, cost, Envoy time | 1, $0.0021, 8.3 s | 1, $0.0021, 6.4 s |

- **The refused routines passed by doing nothing.** They are Bluetooth on and off Verify, brightness max Verify, and the black-garlic delete. AndroidWorld's `*Verify` tasks start in the asked state on every seed.
- **Without them, the matcher declined all 12 episodes** rather than pick another routine.
- **Of the 7 newly compiled tasks, 4 verified on seed 30.** On new seeds:
  - MarkorCreateNoteAndSms and NotesIsTodo did 3/3.
  - MarkorEditNote did 0/3: the kind of edit changes with the seed.
  - SimpleCalendarEventOnDateAtTime did 0/3: the matcher filled the time but left the date empty.
  - That same date-and-time routine was also chosen for two date-only questions, and then needed a time. Both are matcher issues, in the project's backlog.

**An incident during this stage.** At 22:32 the emulator stalled (AndroidWorld couldn't read the screen, and `dumpsys` timed out). android_env, AndroidWorld's emulator library, then restarted the adb server that every run on this Mac shares (`adb kill-server`). That crashed Phase 7's SkyLark runs on envoy-test.
- The next 26 routine episodes failed at once on adb. They're set aside with a README (`routines-seeds/invalidated/`) and were rerun after the fix.
- The agent stage hadn't started.
- The fix (`3631542`) replaces android_env's restart with a wait, refuses any adb command that would kill or restart the server, and the runner won't start without it (`cdd130e`).
- The logs show the same restart had fired, unseen, on every AndroidWorld setup since Oct 27 (its VLC APK always fails to install on arm64), and on two failed commands in `final-standard`.

## Against the leaderboard

The leaderboard (fetched Oct 27, `eval/results/androidworld/leaderboard-2026-10-27.csv`) is self-reported pass@1 on the same 116 tasks, and it labels each entry's screen representation. Two things make most of it a different contest from this one. First, the top of the board (90–100%) comes from agent systems built on frontier models with screenshots, often several models and many calls per step. Second, AndroidWorld's step budgets were changed on Nov 18, 2024, so entries from before that date ran under different budgets. The fairest comparisons are agents that read the accessibility tree, with one general model, as published:

| Agent | Model | Screen | Seed / runs | Success |
| --- | --- | --- | --- | ---: |
| Human (AndroidWorld paper) | — | — | 3 runs | 80.0 |
| V-Droid (Mar 2025) | Llama 8B, trained verifier | A11y tree | 1 | 59.5 |
| AndroidGen (Apr 2025) | GPT-4o | A11y tree | 1 | 46.8 |
| ScaleTrack (Apr 2025) | ScaleTrack-7B, trained | A11y tree | 1 | 44.0 |
| M3A, paper (May 2024) | GPT-4 Turbo | A11y tree | seed 30 (27.6–33.2 over 3 seeds) | 30.6 |
| M3A, paper | GPT-4 Turbo | SoM (screenshot + a11y tree) | seed 30 | 25.4 |
| M3A, paper | Gemini 1.5 Pro | SoM (screenshot + a11y tree) | seed 30 | 22.8 |
| M3A-Simple, paper (minimal prompt, no guidelines or reflection) | GPT-4 Turbo | A11y tree | seed 30 | 19.8 |
| M3A, paper | Gemini 1.5 Pro | A11y tree | seed 30 | 19.4 |
| SeeAct, paper | GPT-4 Turbo | SoM (screenshot + a11y tree) | seed 30 | 15.5 |
| M3A-Simple, paper | Gemini 1.5 Pro | A11y tree | seed 30 | 14.7 |
| M3A, paper | Gemma 2 | A11y tree | seed 30 | 9.5 |
| **Envoy, baseline (`main`)** | Muse Spark 1.3, low effort | A11y tree (+ screenshot on request, 17% of steps) | seed 30 | **18.1** (standard) / 18.5 (Contributor) |
| **Envoy, with the changes (this branch)** | Muse Spark 1.3, low effort | A11y tree (+ screenshot on request, 11% of steps) | seed 30 | **49.1** (held-out half: 53.4) |

What this says, with the caveats attached:
- **Envoy before the changes sits with the paper's 2024 agents on weaker setups** (M3A-Simple with GPT-4 Turbo, 19.8; M3A with Gemini 1.5 Pro on the tree, 19.4): 18%.
- **With the changes it is at 49%** (53% on the held-out half), above the paper's best agent (M3A with GPT-4 Turbo, 30.6) and between AndroidGen (46.8) and V-Droid (59.5) among tree-only entries. It does that with one general model at low effort, no task-specific training, and about $0.04 and 38 s per task. The held-out 53% is the number to quote. The all-116 figure includes the dev half the fixes were chosen on, though the two halves came out close (45% and 53%).
- **It is far from the top of the board** (90–100%, frontier models with screenshots, often several models per step) and from people (80%).
- **Not like for like.** The paper's numbers (its Table 3, seed 30, temperature 0) ran on x86_64 under the budgets of the time, about twice the steps human annotators needed; Envoy's ran on arm64 under the current budgets. Envoy is one model call per step at `low` effort plus one plan call, and answers in one step where M3A takes two. The leaderboard's label for Envoy would be "Screenshot + A11y tree", because screenshots are available, but 89% of the final run's steps carried no screenshot (201 screenshots in 1,777 steps).
- **Run-to-run noise is about ±4 tasks per half** (two identical baseline runs differed on 23 of 116 tasks), so differences of a few points against neighbours mean nothing.

## Real apps beside the benchmark (Oct 29)

The project's rule since Oct 29: AndroidWorld exists to make Envoy better on real apps.
- Every change to the core agent is measured on Envoy's own cases, Phase 7's real-app runs and SkyLark, before it's proposed. A real-app drop blocks it, whatever the benchmark gain.
- Behavior only the benchmark needs lives in its adapter (`eval/androidworld/`), not in Envoy's instructions.

**What the 13 changes did on real apps.** Phase 7 ran its real-app workflows on `main` (Oct 28) and on `main` plus the 13 and the three follow-ups (`1f1fc11`, Oct 29), on the same phone (envoy-real), read-only.

| Workflow | `main` | + the 13 |
| --- | ---: | ---: |
| contacts_count | 1 step | 25 (step limit) |
| doordash (saved address) | 2 | 11 |
| chipotle | 24 | 10 |
| maps_address | 7 | 5 |
| play_rating | 4 | 2 |
| amazon | 3 | 4 |
| settings_bluetooth | 7 | 9 |
| settings_version | 6 | 7 |
| starbucks | 9 | 8 |
| calendar_today | 1 | 1 |
| doordash_search | 3 | 3 |

On the 9 workflows besides contacts and DoorDash, the 13 took 49 steps against 64, and answered more tersely ("15", "4.7 stars"). Three more rows (Chrome, YouTube, YouTube Music) hit the API's billing failure on Oct 29 and have no second run.

**The two regressions, replayed** (`eval/results/androidworld/answer-fix-2026-10-29/`).

Each case is replayed from its recorded screen, with the plan the live run made or with a fresh one. The rebuilt inputs match the live calls (DoorDash's step to the token, contacts within 23 of 2,692).
- **DoorDash's detour came from its plan, not the step prompt.**
  - The live plan was made on an 816-token screen before the app had loaded ("Wait for DoorDash to finish loading…", "Open Account or Profile section").
  - Under that plan, `main`'s own prompts also go to Account (9 of 10). On the loaded screen, every version taps the address.
  - The fix belongs at planning time: plan, or plan again, once the app has loaded. It's in the project's backlog.
- **Contacts' 25 steps were a rare draw.**
  - Under the live plan, `main` and the merged agent both answer at once (10 of 10).
  - On fresh plans, the merged agent switched filters once in 8, `main` never.
- **Calendar's date was on the screen** ("Thursday 29 October 2026, Open Day View"), not taken from TODAY, but the merged agent often opened the day first.

**The answer fix** (`b630d3f`, then `9a573f8`): only the done rule in the step prompt changes.
- The question rule had said "taken from what you read on the phone" (fix 5). It now says:
  - answer in the words the phone shows (SCREEN or REMEMBERED), adding nothing they don't show;
  - a screen that says there is none answers the question;
  - don't switch filters or settings to look for another answer.
- "In the format the goal asks for" served only AndroidWorld's checker, so it moves to the adapter (`4c714b2`). It wasn't doing anything: the answers are the same with or without it.

Replayed on `fdce597`, the branch that merges (5–10 calls per case):

| | `main` | `fdce597` | + the fix |
| --- | ---: | ---: | ---: |
| Calendar, live plan: answers at once | 5/10 | 4/10 | 9/10 |
| Contacts, fresh plan: answers at once | 8/8 | 7/8 | 8/8 |
| Real-app final steps, same answer (10 workflows) | | 35/50 | 40/50 |
| AndroidWorld question steps, same answer (8 tasks) | | 29/40 | 31/40 |
| Safety probe: irreversible controls labelled irreversible | | 80/100 | 82/100 |
| Round 1's wrong-flight confirms taken (lower is better) | | 21/30 | 20/30 |

No answer changed on AndroidWorld, and none came early with a different value. The safety probe gave the unchanged prompt 80, 82 and 84 across rounds, so 82 is within its noise.

**An earlier wording, kept out.** Phase 7 asked whether the risk wording could stop labelling SkyLark's "Check in" (which only opens the flow) irreversible. The wording that did so also made the model call Amazon's Buy Now and Play's "Buy for $…" "read". The safety probe fell to 73–75 of 100. The current wording stays (`wording-2026-10-29/`).

**Phase 7's same-day real-app rerun of the fix** (Oct 29 afternoon, envoy-real, `main` `53ab459` against the staging branch `736a6e4`, Phase 7's numbers):
- **Same-input workflows passed:** 9 of 18 on `main`, 13 of 18 with the fix.
- **Better with the fix:** chipotle went from the step limit to a pass; settings_bluetooth, gmail_search, maps_address and play_rating also improved. There were far fewer actions: DoorDash took 1 against 13, and the plan-before-load detour didn't recur.
- **contacts_count still looped once:** on `736a6e4` its 3 runs were a 25-step filter loop, a right answer left unverified, and a pass. `main` answered all 3 with no action.
- **The loop's plan** said "View the full contacts list" every time. Every quick answer's plan, and all of `main`'s, read the list or its empty state.

**A planner line for it** (`edfab2b`, `contacts-guard-2026-10-29/`): "For a question, read the answer where the app shows it, an empty state ("none yet") included; plan no step that changes filters or settings, and no "full" or "complete" list unless the goal asks for one."

Replayed on the loop run's own first screen, `736a6e4`'s prompts, 30 per cell:

| | Current | With the line |
| --- | ---: | ---: |
| Plans asking for a full list or filters | 33/120 | 0/90 |
| Plan, then step 1: opens the filters | 3/90 | 0/30 |
| Real apps, fresh plans: contacts answers at once | 13/16 | 8/8 |
| SkyLark: another trip's check-in planned through Home's button | 5/120 | 4/120 |
| AndroidWorld question plans with a filter or settings step | 5/125 | 1/125 |
| AndroidWorld question tasks answered prematurely at step 1 | 0/125 | 0/125 |

- The step prompt is untouched, so the safety probe and the answer steps don't move.
- Step-side clauses were tried too. One added scrolls before answers; the other didn't help. Neither is used.
- Phase 7 then ran contacts on it live, with a SkyLark check; it merged on Oct 29 with an empty-state answer check (`83a9702`, in `105d04e`; `eval/results/real_rerun_2026-10-29/`).

**AndroidWorld and real apps, side by side:**

| | `main` | `main` + the 13 (Oct 28) | staging `736a6e4`: + 3 follow-ups + the answer fix (Oct 29) |
| --- | ---: | ---: | ---: |
| AndroidWorld held-out half (58 tasks, seed 30, pass@1) | 12 | 31 | 30.5 |
| Real-app same-input workflows (Phase 7, Oct 29 afternoon) | 9/18 | | 13/18 |
| Real-app steps on the 9 workflows besides contacts and DoorDash (Phase 7, Oct 28–29) | 64 | 49 | |
| contacts_count | answers at once (3/3) | 25-step loop | 1 loop in 3 (the planner line is next) |

- **The held-out re-run** paired with Oct 28's: +5 −6.
  - Gained: ExpenseAddSingle, SimpleCalendarDeleteOneEvent, SystemBluetoothTurnOff, TasksDueOnDate, TurnOffWifiAndTurnOnBluetooth.
  - Lost: ExpenseDeleteMultiple, MarkorCreateNoteAndSms, RecipeAddMultipleRecipesFromImage, RecipeDeleteMultipleRecipes, RetroSavePlaylist, SimpleCalendarEventOnDateAtTime.
  - Both lists are what a rerun of the same agent moves by (Baseline: about four tasks per half).
- **Which commit each episode ran on:** 23 on `fdce597` + `b630d3f` + `9a573f8`, after which the run was paused for Phase 7's rerun. The other 35 ran on `736a6e4`. The only agent-side difference between them is `main`'s password mask and its Share/Post/Publish rule, and none of the 23 episodes touched either.
- **The answer-format note** was in the adapter for all 58.
- **Stuck recoveries weren't recorded in this run.** The merged loop these 58 episodes ran on didn't write the trace record for a stuck recovery: it was a two-line, trace-only change on this branch (`73c6fab`) that wasn't among the commits taken to `main`. So their `stuck_recoveries` read 0, meaning "not recorded", not "none".
  - Iterations are unaffected: all 24 step-limit episodes reached their full budget.
  - The step budget is the loop's own `max_steps`, so scores are unaffected too.
  - The record is back in `main`'s loop with the harness commit, and `test_androidworlds_step_budget_is_envoys_max_steps` checks it.


## What Envoy should change on `main`, ranked

**Approved for `main` (Oct 28, the author: "All 13").** The 13, Phase 7's three SkyLark follow-ups, the answer fix, the contacts planner line and an empty-state check merged on Oct 29 (`105d04e`). The first real-app rerun on the staging tree (`736a6e4`) still found contacts_count worse than `main`; after the planner line and the empty-state check, Phase 7's decisive check came within a bar of at most one more failure than `main` (`eval/results/real_rerun_2026-10-29/`).

**Proposed on Oct 29, after the 13:**
- **The answer fix,** `b630d3f` + `9a573f8`: answers in the phone's words, and AndroidWorld's answer form moves to its adapter. It's on the same staging branch (`736a6e4`), and the real-app rerun and held-out half above were run on it.
- **The contacts planner line,** `edfab2b`: replayed offline above. Phase 7's live contacts runs and a SkyLark check came before the merge (Oct 29, `105d04e`).

The 13 agent commits below cherry-pick cleanly onto `main` as it is on Oct 28 (`e0789e1`: Phases 6 and 7, cross-app answers and app routing). On that result `main`'s whole suite passes (251 tests). Main's commits since the branch was measured touch routine repair, the phone, the task history and the API's routing, and none of the agent, model or device code, so the agent is still the one measured here. The only differences are the AndroidWorld tests and a two-line trace change (`73c6fab`). Against branches still waiting to merge:
- `claude/repair-fixes` and `claude/overnight-integration`: already in `main`.
- `claude/wonder-appnotes` (model profiles, app notes): 4 small conflicts, in `plan_input`/`step_input` (`backend/models/prompts.py`) and their two calls (`backend/agent/loop.py`). Both sides add keyword arguments (`apps`, `today`, `remembered` here, `app_notes` there), so each is resolved by keeping both. Held-out effects are of the set as a whole (31 against 12 of 58, +20 −1). Each change's own evidence is its mechanism, counted on held-out and on dev. None names an app, a task or AndroidWorld.

| Rank | Change (branch commit) | Why first | Held-out evidence (baseline → final) | Risk on `main` |
| --- | --- | --- | --- | --- |
| 1 | **Routines: a swipe compiles as a swipe, a launch as a launch** (`8bbed6b`) | A bug on `main` since `ca50dab`: every swipe in a trace compiles as a launch of the app on screen, and every launch is dropped | (A compiler fix: found compiling AndroidWorld runs; offline test.) None of `main`'s 279 committed routines has a swipe or launch, so no committed result changes | None |
| 2 | **The step's fields are named in the order the model writes them** (10b, `598a6cd`) | Meta's decoder writes keys alphabetically, so on `main` the model writes the action before its reason, and an action begun `{"type"` can only be back, home or look. This affects every step Envoy takes, on every app, on both tiers | Back 37% → 5% of actions; placeholder reasons 35 → 0 | Field names change in the prompt only; code, traces and routines keep theirs |
| 3 | **Apps open by the names people use; the plan sees the phone's apps** (fix 1, `0c6c830`; 1b, `821d713`) | The largest failure cause on dev (15 of 45): a guessed package that isn't installed, then no way to open the app | Failed launches 7 → 1; decisions on the home screen 42% → 7%; 73 launches by name, all opened the app | Labels come from `aapt2` in the Android SDK's build-tools, cached per app version; without it, names fall back to the package's last word |
| 4 | **Done as soon as the screen shows it; answers in the goal's format; a second done is accepted** (fix 5, `876d5db`) | The plan's check is written before seeing the app and rejected correct dones; the agent then "verified" until it ran out | Second dones accepted 4 → 5. Across the four runs with the fix, 42 of the 43 accepted second dones were right. Wrong dones overall 2 of 23 → 2 of 59 | A wrong done can get through when the check can't judge it. It's recorded as `done_unverified` |
| 5 | **The history says what happened, not what the model expected** (fix 3, `7dd3153`) | The model copied its own earlier expectations and acted on them, not on the screen | Echoed expectations 299 → 36 | None found |
| 6 | **Working memory: what the model keeps from a screen comes back later** (fix 11, `23a845d`) | Read-and-forget loops: tasks re-read the same file or item dozens of times | Used in 49 of 58 held-out episodes (340 steps). On dev, relaunches 101 → 67 and +6 −2 against round 2 (within noise on its own) | About 17% more input and output tokens per call (with fix 8). The kept text is screen content and stays in the run's trace like the screens themselves; secure screens are still never read |
| 7 | **A screen line that changes by itself is not progress** (fix 2, `11057a0`) | A ticking timer made every back "change the screen", so stuck detection never fired. Real apps have countdowns and clocks too | Timer-chip decisions 197 → 0 (mostly because fix 5 stopped Envoy starting the timer); stuck recoveries 75 → 23 in all | One extra look before acting; a masked line can hide a real one-character change |
| 8 | **The keyboard line, back explained, placeholders asked again** (fix 4, `cce463b`; 4b, `a80b976`) | Back pressed "to dismiss the keyboard" when none was up closed forms | Keyboard line on 159 held-out screens (0 before 4b); placeholders asked again 0 (the cause is gone after 10b) | 4b reads the navigation bar's keyboard buttons; on a phone with gesture navigation they may not exist, and then the line is simply absent |
| 9 | **The model knows the phone's date** (fix 7, `e926caa`) | "This Thursday" and "this Monday" went to wrong days | Simple Calendar Pro 3 → 12 of 17 (with the rest) | None |
| 10 | **Long text is shown at length** (fix 8, `11cbdb9`) | A 12,101-character file was shown as its first 120 characters | Screens with long text 9 → 21 | Tokens: up to 4,000 characters per field and 8,000 per screen. Watch cost on real apps with long pages |
| 11 | **Stuck recoveries start afresh once the agent moves again** (fix 6, `ba50eb5`) | An early stall ended runs that had recovered | Not separable | None |

**What the merge test on SkyLark found, and three follow-ups (Oct 28).** Before merging, Phase 7 ran `main`'s SkyLark suites on `main` plus the 13 (`aw-merge`), against `main` (`e0789e1`) the same evening.

The SkyLark round 1 results below are Phase 7's (the 13 against `main`):

| | `main` + the 13 | `main` |
| --- | ---: | ---: |
| Full agent, first try | 120/120 | 119/119 |
| Side effects | 0 | 0 |
| Median steps | 2 | 4 |
| Median calls | 4 | 6 |
| Median cost | $0.0074 | $0.0090 |
| Median time | 8.8 s | 12.6 s |
| Compile | 8/10 | |

- The extra tokens per call are more than paid back by fewer steps.
- Injection: no irreversible step without approval, and the planted texts were ignored. Safety gate: 20/20.

It found two regressions:
- **A wrong-flight check-in.** SkyLark's home shows "Next trip · Chicago" with a "Check in" button that acts on that trip. Asked to check in for another trip, 4 of 11 merged plans offered that button as the route. Each time the agent confirmed the Chicago check-in before noticing, then checked in the right trip too. Round 1 put the count at 1 of 3 compile source runs and 3 of 15 runs where a routine fell back to the agent, against 0 on `main`. In the agent arm's 120 runs there were none.
- **check_in no longer compiled.** Correct dones were rejected and ended `done_unverified`, and compile learns only from verified runs. The other routine that stopped compiling, past_trip, read its answer off a list row without opening the trip; Phase 7 fixed it in the compiler (`183cc60`).

Measured offline, from the runs' own inputs, each fix in its own commit on this branch:
- **`f93ce08`, a planner line:** "A button shown with one item (on the card for the next trip, the last order, an open message) acts on that item only; if the goal names a different item, go through the list that holds it."
  - Measured on the planner alone, 40 plans per condition, input rebuilt to the token from the run. Plans offering the wrong route: `main` 3/40, the 13 13/40, with the line 0/40.
  - No single new input explains the rise: TODAY alone 9, the app list alone 4, neither 8.
  - For the next trip itself, the button stays the route (20/20).
- **`5decf4a`, the check fix.** The plan's check was element_present "View boarding pass", the planner prompt's own example (on `main` too), but check-in ends on the boarding pass itself, where that button isn't. A check named for the button that opens a screen ("View/Open/See/Show/Go to X") now also passes when X is a label on screen.
  - It touches 1 of 28 AndroidWorld element checks, on a task that failed anyway.
  - Fix 5 itself is unchanged. Replaying the step after a rejection with `main`'s wording ("get to the screen that shows it"), the agent left 4 of AndroidWorld's 6 correct answers and still didn't satisfy SkyLark's check.
- **`742ede6`, a second guard.** In 4 of the 5 wrong runs, `0_remember` had fused the goal's city with the flight number ("Flight SL 482 to Pittsburgh"), and the confirm screen showed only the number. Two sentences in the step prompt:
  - memory is copied from the screen and never adds what the goal says;
  - before an irreversible action, SCREEN or REMEMBERED must name the goal's own item, or the agent goes back on the phone to find out.

  Single-step replays of `742ede6` (before → after):

  | What | Before | After |
  | --- | ---: | ---: |
  | Goal's city written into memory | 27/40 | 14/40 |
  | Wrong-flight confirms, with what the agent really saw kept: went ahead | 50/50 | 7/50 |
  | Correct irreversible steps (22 SkyLark, 20 AndroidWorld): went ahead | 210/210 | 210/210 |
  | AndroidWorld steps that keep text: still keep something | 85/120 | 88/120 |

  A stricter wording cut fusion to 10/40, but also cut AndroidWorld's kept text to 57/120, so it wasn't used.

**Phase 7's second SkyLark round passed** (Oct 29, `773536a`: `main` with the 13, the three follow-ups and the row fix). Compile was 10 of 10 on the first try; agent 120/120 and routines 120/120, with 0 side effects. All 21 check-in runs went through My Trips: no plan offered Home's "Check in", and no flight was wrong. Injection: no irreversible step without approval. One new behaviour: in 4 of 21 check-in runs the agent also labelled the trip page's "Check in" (which only opens the flow) irreversible, so the person is asked once more. A wording that stops this also stopped flagging one-tap purchases, so it wasn't used ("Real apps beside the benchmark", below the leaderboard).

**Also for `main`, not code:**
- **The $0.15 per-run cap** stopped 4 of 116 long tasks (OsmAndTrack, ExpenseAddMultiple, two recipe tasks) before their step budget, at standard prices. It is a product decision; for AndroidWorld-length tasks (up to 120 steps) about $0.30 would let them finish.
- **Two problems to report to AndroidWorld's maintainers** (a public issue, so only with the author's OK): app snapshots are deleted when the emulator reboots on API 33, and then each app keeps its state from task to task without an error; a Clock timer started by one task keeps ticking on the home screen in every later one. Also two setup strings that don't match on this image (Contacts' "Don't allow" has a curly apostrophe; OpenTracks shows no "Allow").

## What is left, or uncertain

- **One run per configuration.** Every number is pass@1 on one seed. Two identical baseline runs differed on 23 of 116 tasks, so the final's 57 could plausibly be anywhere from about 50 to 64 in a rerun. The held-out gain (+20 −1) is far outside that; the rank of individual changes is not.
- **Per-change attribution is by mechanism, not score.** The dev rounds add changes in groups. I didn't run a held-out ablation per change (each would cost a full run), so the ranked list says what each change did to the agent's behaviour, not how many tasks each one is worth.
- **The dev half was used four times** (three rounds and the final); its 26 is not an estimate. The held-out half was used once.
- **The setting differs from the official one** in ways that could move the number either way: arm64 instead of x86_64, Envoy's own device layer instead of AndroidWorld's, the forwarder parked during episodes, the one-step answer. All of it is listed under Setting.
- **The Contributor tier is not the product's tier.** The dev rounds ran on it; the headline doesn't.
- **Real apps are not AndroidWorld.** They weren't, either: Phase 7's real-app pass on the 13 found two read-only questions that turned into searches ("Real apps beside the benchmark"). One came from the agent's answer rule, now fixed and replayed. The other, DoorDash, came from a plan made before the app had loaded, which `main`'s prompts follow too; it's in the project's backlog. The replays are single steps from recorded screens. Phase 7's same-day real-app rerun of the fix, against `main`, is the live test.
- **The two failed Bluetooth dones** (SystemBluetoothTurnOff in the final run, and earlier ones) suggest that the emulator's Bluetooth state can lag behind its Settings screen. I didn't chase that further.
- **The answer fix and the planner line were measured offline from recorded screens**, from one or two steps of each run. The first live real-app rerun covered the answer fix only; the planner line was then checked live on real apps before the merge (`eval/results/real_rerun_2026-10-29/`), but the held-out half ran without it. Its AndroidWorld effect is estimated only from plan replays: question plans with a filter or settings step 5/125 → 1/125.
- **The three SkyLark follow-ups** passed Phase 7's second SkyLark round live (above). On AndroidWorld they're in the held-out re-run on the staging branch (`736a6e4`).
- **Routines across seeds are one pass on three seeds, from routines verified on a single instance.** RecipeDeleteMultipleRecipesWithConstraint shows how a degenerate instance can pass verification. The routine-bug fixes waiting on another branch (popup focus, twin fields, row-anchored icons, dates for the matcher) weren't in this run. The 5 PopupWindow routines and the 2 Pro Expense routines they'd recompile weren't among the verified 22 anyway.
- **Not done:** pass@k or other seeds for the full agent beyond the routines comparison. The AndroidWorld issues are drafted here, not filed. Neither is the android_env behaviour of restarting the adb server on failure, which is worth raising with its maintainers (with the author's OK).

## Proposed text for other documents

These were drafts for other documents; they have since been applied (`docs/technical-design.md`, `docs/meta-feedback.md`, `THIRD_PARTY.md`).

### Proposed for the design doc's Evaluation section

In "Task sets", the AndroidWorld part of the **Stretch** bullet becomes a measured set:

> - **AndroidWorld (measured Oct 27–28, branch `androidworld`):** Google's 116 tasks over 20 apps, run unmodified through AndroidWorld's own runner and scoring on an API 33 emulator, seed 30, pass@1, with Envoy's whole agent as the agent (one subprocess per task; the answer goes to AndroidWorld's answer channel). The tasks were split 58/58 into a dev half for finding and fixing failures and a held-out half that measures the result; the split was committed before any run. Envoy as on `main` scored 21 of 116 (18%). With 13 general agent changes found on the dev half, it scored 57 (49%), and 31 of 58 (53%) on the held-out half against 12, at about $0.04 and 38 s per task (`docs/androidworld-results.md`). Routines compiled from seed-30 runs were replayed on three other seeds; see that report.

And in "How results are reported", one sentence:

> AndroidWorld results are reported by half (dev and held-out) with a paired test per change set, and failures are explained from step-level trace evidence, not from the score alone.

### Proposed for `docs/meta-feedback.md`

A new entry:

> ## Muse Spark as the agent on Google's AndroidWorld benchmark (Oct 27–28; 116 tasks, both tiers, about 8,000 step calls)
>
> **What worked well**
> - **The Contributor tier is a real saving, with the same quality.** The same agent scored 21.5 of 116 on Contributor and 21 of 116 on standard. Contributor billed $0.30 for the whole run against $4.49. That made it practical to develop fixes in repeated runs (three runs of 58 tasks for $0.63 billed).
> - **Structured output never failed.** Not one of about 8,000 step calls across five runs ended in a model error or unusable output, sometimes after a sentence of prose (below).
> - **The model follows a self-written memory well.** Given a field for "what on this screen you will need later", it kept text word for word (recipes, IDs, values to add up) in 45 of 58 episodes and used it on later screens. In the task that re-read a file most, the agent opened the file's app 10 times instead of 40.
>
> **What could be better**
> - **Strict JSON-schema output writes keys in alphabetical order, not the schema's order.** A schema listing `zebra_first, middle, apple_last` came back `apple_last, middle, zebra_first`, 6 times of 6 on both tiers, even when the descriptions said "write this field first". So a model can't be made to reason before it answers by ordering fields, the usual technique. In a discriminated union, a discriminator named `type` sorts after most fields, so an object begun `{"type": …` can only become a variant with no other field. In Envoy's agent that variant was `back`: 42% of all actions in one run, often with reasons like "placeholder" or "schema requires back?". Renaming fields so the alphabet gives the intended order (`1_reason`, `2_expected_result`, `3_action`; `act` for the discriminator) took back from 13% to 8% of actions. Please document the ordering, or keep the schema's property order.
> - **Prose before structured output, much more often on the standard tier.** 32% of standard-tier step answers (665 of 2,049) came as two message items, against 13% on Contributor (283 of 2,212). The first item was a sentence ("I'll open the app drawer to find the Audio Recorder."), the second the JSON. `output_text` joins them, so a plain `json.loads` fails; we parse the last message item. The sentence often disagreed with the JSON: it said "open the app drawer" while the JSON said back. That is how we found the key-order problem.
> - **Contributor answered more slowly.** Median model time per task was 37 s on Contributor against 19 s on standard (same agent and tasks, different hours of the same day).

### Proposed for `THIRD_PARTY.md`

A new section after "In use", since none of this ships in Envoy or is imported by it:

> ## Evaluation only: AndroidWorld (Oct 27–29, branch `androidworld`)
>
> Used to measure Envoy on Google's public benchmark. These tools run in their own Python 3.11 environment (`third_party/aw-venv`, gitignored). Envoy's backend doesn't import them, and they are not distributed with Envoy.
>
> | Component | Version | License | What we use it for |
> | --- | --- | --- | --- |
> | [AndroidWorld](https://github.com/google-research/android_world) | commit `55ddaf5` (Oct 23, 2026) | Apache-2.0 | The benchmark: 116 tasks, their setup, step budgets and scoring, run unmodified through its own `suite_utils.run` |
> | [AndroidEnv](https://github.com/google-deepmind/android_env) | 1.2.3 | Apache-2.0 | AndroidWorld's emulator controller (adb and gRPC) |
> | AndroidWorld's dependencies: absl-py, dm_env, grpcio-tools, protobuf, immutabledict, jsonschema, NumPy, pandas, OpenCV, pydub, tenacity, termcolor, requests, matplotlib, google-generativeai | as pinned by AndroidWorld | Apache-2.0, BSD-3-Clause, MIT, PSF | Required by AndroidWorld's code; Envoy uses none of them directly |
> | [thefuzz](https://github.com/seatgeek/thefuzz), [python-Levenshtein](https://github.com/rapidfuzz/python-Levenshtein) | 0.19.0 / 0.27.5 | GPL-2.0 / GPL-2.0-or-later | AndroidWorld's fuzzy matching of answers when scoring. Run as part of the benchmark only; not linked into or shipped with Envoy |
> | The apps AndroidWorld installs on its test emulator (Markor, Broccoli, Simple Calendar Pro, OsmAnd, VLC, Retro Music, Joplin, OpenTracks, Pro Expense, and others) | as AndroidWorld pins them | each app's own license (several GPL-3.0) | The benchmark's apps, installed by AndroidWorld's setup on the evaluation emulator only |
>
> **Android SDK Build-Tools' `aapt2`** (37.0.0; Android SDK License, a tool) is new for Envoy itself, not only the evaluation: `backend/devices/apps.py` runs `aapt2 dump badging` on an app's APK to read the name people know it by, cached per app version. Its last line under "Development tools (not shipped)" would read: "Android SDK command-line tools, platform-tools, build-tools (`aapt2`, which reads app names from APKs) and emulator (Android Software Development Kit License; not open source, used as tools only)".

"What Envoy builds itself" gains a line:

> - **AndroidWorld evaluation** (Oct 27–29; `eval/androidworld/`): the adapter that runs Envoy's whole agent as an AndroidWorld agent through AndroidWorld's own runner and scoring (a subprocess per task, the answer channel, step budgets), the gRPC token interceptor that lets AndroidWorld use a token-protected emulator, the stratified dev/held-out split, the failure taxonomy and its trace digests, per-change effect counts, and the routines-across-seeds experiment. AndroidWorld and AndroidEnv are the benchmark, unmodified.
