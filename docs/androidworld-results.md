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
- **Offline tests:** 13 for the Envoy side (the payload holds only the goal, budget, run id and configuration; the status → done mapping; the real loop honors the budget; trace digests), 5 for the AndroidWorld side (the agent shim with a fake environment). Envoy's 111 existing tests still pass.

<!-- Results, failure analysis, improvements, routines, leaderboard comparison and proposals follow once measured. -->
