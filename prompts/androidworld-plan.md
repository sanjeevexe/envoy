# Envoy on AndroidWorld (plan)

Written by Claude from `prompts/androidworld.md` on Oct 27, 2026 (evening), after reading AndroidWorld's code at commit `55ddaf5` (Oct 23, 2026), its paper and leaderboard, and Envoy's design doc, Phase 1/2/6 results and code. Branch `androidworld`, worktree `~/Desktop/Envoy-androidworld`. Where this plan and the prompt's "what I know" differ, the code was checked and the code wins (noted inline).

## Decision after the pilot (Oct 27, with the user): both tiers

The Phase 7 chat measured that the Contributor-tier model takes about twice the steps of the standard tier on SkyLark's core tasks (75 vs 37 actions, same code and cells), with "placeholder" actions such as backing out of an enabled button. The pilot traces here show the same thing: 116 of 231 actions were `back`, 37 with a reason naming another action, 7 saying "placeholder". AndroidWorld's budgets are tight (48 tasks get 10 steps) and a task counts only if the agent says done within them, so the tier can move the headline for reasons unrelated to Envoy's design. The user chose:

- **Baseline on both tiers:** all 116 on Contributor (as planned) and all 116 on the standard tier (`muse-spark-1.3`), same code, seed and adapter (`--config '{"tier": "standard"}'`). The standard tier is the model Envoy uses in the product, so its number is the headline; the gap between the two is a finding.
- **Development of fixes on the dev half on Contributor** (cheap), then the **re-measure on the standard tier** (both halves).
- **Budget:** the $10 guards against needless spending, not justified runs; no need to ask before exceeding it. Spend is still reported at each checkpoint. The daily cap in this checkout is $15 so a run can't stop halfway.

## Rules (from the prompt)

- No passwords, no sign-ins, no payment methods; ask before anything visible outside this Mac; never touch the real phone, the iPhone, the main chat's emulators, its API or `main`.
- My emulator only: `AndroidWorldAvd` on console **5560**, gRPC **8560** (`emulator-5560`), `-s emulator-5560` on every adb call, never `adb kill-server`, at most two emulators on the Mac counting the main chat's, stopped cleanly when I pause.
- Budget **$10 billed** on the Contributor tier (`muse-spark-1.3-contributor`, `low` effort as Envoy uses it); costs reported billed and at standard prices; ask before going over.
- Integrity: no hints, prompts or code keyed to tasks, apps or answers; nothing reads AndroidWorld's task internals during a run; scored only by AndroidWorld's own checks; every number with its setting.
- Commit each step on `androidworld` and push only that branch. Merges into `main` only with the user's OK, by Nov 1.

## What I found before planning (verified in code)

**AndroidWorld** (`third_party/android_world`, gitignored, Apache-2.0):
- 116 tasks (`registry.TaskRegistry().get_registry('android_world')`), 61 easy / 36 medium / 19 hard (`task_metadata.json`), across 20 apps plus 11 multi-app tasks.
- **Seed:** `run.py --task_random_seed` defaults to **30**; each instance's seed is `sha256(f"{seed}_{task}_{i}") % 2**32`, so instance `i` of a task always gets the same parameters. Instances 1..3 are the "other seeds" for routines.
- **Step budget:** `suite_utils._allocate_step_budget` = `int(10 * task.complexity)`: 48 tasks get 10 steps, the largest 120; 2,369 steps in total at seed 30.
- **Score:** `suite_utils._run_task`: `initialize_task` → `run_episode` (`agent.reset(go_home=start_on_home_screen)`, then up to budget `agent.step(goal)` calls) → `is_successful(env)` → `tear_down`. **A task counts only if the agent said it was done:** `agent_successful = task_successful if interaction_results.done else 0.0`. Composite tasks can score fractions.
- **Answers:** information-retrieval tasks read `env.interaction_cache`, set by an `answer` action (`env.execute_action(JSONAction(action_type="answer", text=...))`). `proto_utils.check_agent_answer` splits the answer on commas, casts each part to the expected type (number, date, time, string), and compares (fuzzy for strings, tolerance for some numbers). Only IR tasks read the cache (grep of `task_evals/`), so sending Envoy's `done` text for every task is harmless.
- **Screen reading in scoring:** Clock, Contacts, Browser, Phone and SMS validators call `env.get_state()` and read the screen through AndroidWorld's **accessibility forwarder** (an AccessibilityService that streams the tree to a gRPC server on the host). uiautomator2 runs a UiAutomation session that may suppress accessibility services, so the two can conflict (checked in step 1).
- **Ports:** `env_launcher.load_and_setup_env(console_port, …, grpc_port)` takes both; `run.py` and `server/android_server.py` hard-code 5554 / default 8554, so I drive AndroidWorld from my own runner. android_env opens the gRPC channel with local credentials and **no token**; it works with `-grpc-use-token` if the token is added as call metadata (done in `eval/androidworld/aw_env.py` with a channel interceptor; nothing in AndroidWorld is modified). Verified: AndroidWorld connects, its forwarder reads 18 elements, gRPC listens on 127.0.0.1:8560 only. The forwarder's own host server listens on `[::]:<random>` with gRPC *local* server credentials, which refuse non-loopback peers.
- **Python:** its requirements pin numpy 1.26, pandas 2.1, matplotlib 3.6 (no 3.13 wheels) and need ≥3.11, so it has its own venv (`third_party/aw-venv`, Python 3.11.17). It is not pip-installed (its `setup.py` only generates two protobuf modules, which I generated with `grpc_tools.protoc`); `eval/androidworld/aw.sh` puts it on `PYTHONPATH`. Envoy's backend stays on 3.13.
- **Emulator:** `AndroidWorldAvd`, Pixel 6 (1080×2400, 420 dpi), `system-images;android-33;google_apis;arm64-v8a` r17 (Google APIs, not Play: AndroidWorld's setup and scoring need `adb root`), 4 GB guest RAM like Envoy's AVDs, cold boot every time (`-no-snapshot`, as AndroidWorld's README launches it). Boots in 14 s.
- **The leaderboard** (fetched Oct 27, saved as `eval/results/androidworld/leaderboard-2026-10-27.csv`) labels each entry's *screen representation*: Screenshot, Screenshot + A11y tree, or A11y tree. Results are self-reported pass@1. The top is at 100%; the best A11y-tree-only entries are V-Droid 59.5 and AndroidGen (GPT-4o) 46.8; the paper's M3A with GPT-4 Turbo on the a11y tree is 30.6. Envoy is tree first with screenshots on request, so it is "Screenshot + A11y tree" by the rules, and mostly text in practice; I'll report both comparisons with that label.

**Envoy:**
- `AgentRunner.run(goal)` is one whole episode: plan (one call), then observe → pop-ups/sign-in in code → stuck and cycle checks → decide (one call) → policy → act → verify. `max_steps` counts every loop iteration (each decision, each pop-up handled in code); the plan is not a step.
- `launch` takes a **package name**. AndroidWorld's goals name apps as people do ("Simple Calendar Pro", "Broccoli"); the baseline keeps Envoy's behavior (the model guesses a package or uses the launcher).
- `done(result)` is checked by Envoy's own success check (an `info` answer must be visible on screen); rejected twice more, it finishes `done_unverified`.
- The pop-up handler **denies permission prompts** unless the goal is about permissions; the policy asks before irreversible steps (a scripted approver approves on AndroidWorld's synthetic apps and every approval is logged).
- Costs from the main checkout's log: a Contributor step costs $0.00017 billed ($0.0031 at standard) with a 3.4 s median latency (0.88 s on the standard tier); a Wonder compile $0.05.

## The adapter

```
AndroidWorld venv (Python 3.11)                         Envoy backend (Python 3.13, uv)
eval/androidworld/run_aw.py                              eval/androidworld/envoy_episode.py
  suite_utils.create_suite(seed=30, tasks=…)               EmulatorDevice("AndroidWorldAvd") → emulator-5560, gRPC 8560
  suite_utils.run(suite, EnvoyAgent, checkpointer)          AgentRunner(RunConfig(max_steps=budget, contributor=True,
    _run_task: initialize_task → run_episode                                     data_scope="test_app"), ScriptedApprover)
               → is_successful → tear_down                  .run(goal)   (memory "", no routines)
  EnvoyAgent.step(goal)  ── goal, budget, run id ──►        stops uiautomator2 before exiting
                          ◄── status, answer, totals ──     writes run JSON + trace (data/runs/<run id>/)
    answer → env.execute_action(answer)
    done = Envoy ended the episode itself
```

- **AndroidWorld's own runner.** `run_aw.py` is `run.py` with my ports, the gRPC token, Envoy as the agent and an output directory under `eval/results/androidworld/<stage>/`: `create_suite`, `suite_utils.run` with its `IncrementalCheckpointer` (resumable after a crash), its `_run_task` (so the done-gating and scoring are AndroidWorld's, line for line), its episode runner (start on the home screen, step budget). Nothing in AndroidWorld is changed.
- **`EnvoyAgent`** (`base_agent.EnvironmentInteractingAgent`): the first `step(goal)` of an episode runs one whole Envoy episode in a subprocess with only the goal, the budget AndroidWorld gave it (`set_max_steps`) and a run id. Then:
  - Envoy's `done` text (when it has one) goes to AndroidWorld's answer channel through `env.execute_action(answer)`, verbatim in the baseline.
  - `done=True` when Envoy ended the episode itself (`done`, `done_unverified`, its own `fail`, `handoff`, `ask_user`), as AndroidWorld's M3A returns done on `status: infeasible`; `done=False` when it hit the step limit or crashed. Later `step` calls in that episode do nothing and return `done=False`, so AndroidWorld's loop runs out its budget without acting.
- **Why a subprocess per task:** Envoy can't be imported into a 3.11 process (its pins), and its loop is a whole episode, not a step function. A fresh process per task also means no state carries over between tasks (uiautomator2 sessions, caches). It costs about 2–4 s per task (uv start, uiautomator2 connect), against a few minutes per task.
- **Step accounting:** one Envoy loop iteration = one AndroidWorld step. The plan call is not a step (it acts on nothing). `look` costs a step. Answering is one step (`done(result)`), where M3A spends two (`answer`, then `status`). Stated in the setting.
- **Observation and actions are Envoy's own** (uiautomator2 tree, gRPC taps and screenshots, set-text typing), not AndroidWorld's forwarder and adb actuation, because that is the system under test. AndroidWorld still sets up, resets and scores.
- **The uiautomator2 conflict:** step 1 checks whether AndroidWorld's forwarder still reads the screen while uiautomator2's server runs. If not, `envoy_episode.py` stops uiautomator2's server before it exits (the next episode starts it again), so AndroidWorld's reset and screen-reading checks always see a working forwarder. Verified with the hand-solved Clock/Contacts tasks, which are scored through the screen.
- **Integrity in code:** `EnvoyAgent` never receives a task object (AndroidWorld's `step` only passes the goal); the payload to Envoy is exactly `{goal, max_steps, run_id, config}` and a test asserts it. Memory is off (`memory=""`), the routine library is not loaded, and the prompts are main's.
- **One run, one record:** per task, AndroidWorld's checkpoint (goal, score, run time, its step data) and Envoy's run JSON (status, answer, steps, model calls, tokens, cost billed and at standard prices, time split into model and device, approvals, pop-ups, stuck recoveries, replans, screenshots sent, vision calls). Envoy's full trace stays in `data/runs/<run id>/` (gitignored, large); a compact digest of every step (decision, action, target, the screen as the model saw it) is committed as `traces/<task>.jsonl.gz` beside the results, so every quoted failure can be checked on the branch.
- **Rejected designs:** (a) AndroidWorld's FastAPI server: hard-coded ports, and I'd re-implement `_run_task` on the Envoy side, which is where scoring errors would creep in. (b) An Envoy step function called per AndroidWorld step: rewrites Envoy's loop (plan, stuck and cycle state) for the benchmark, so it would no longer be the agent main has. (c) Envoy acting through AndroidWorld's `execute_action`: tests AndroidWorld's actuation, not Envoy's.

## Setting (what differs from the official protocol)

| | Official | Here |
| --- | --- | --- |
| Device | Pixel 6 AVD, API 33 (x86_64 on Linux usually) | Pixel 6 AVD, API 33 Google APIs **arm64** on Apple silicon, 4 GB RAM, gRPC with token |
| Observation | the agent's choice (leaderboard labels it) | Envoy's: uiautomator2 tree as a numbered list; a 540 px screenshot when the tree is sparse, the last action did nothing, or the model asks (`look`); SAM 3.1 then grounding for `tap_point` targets |
| Actions | `json_action` through adb | Envoy's action space through uiautomator2 and gRPC; launch by package name (baseline) |
| Steps | `int(10 × complexity)` | the same budget; one Envoy iteration = one step; the plan call is extra |
| Answer | `answer` action → `interaction_cache` | Envoy's `done` text → the same channel |
| Score | `is_successful` gated by the agent's done | the same code |
| Seed | 30, pass@1 | 30, pass@1 (other seeds only for routines, labelled) |
| Model | any | Muse Spark 1.3, `low` effort steps and plan, Contributor tier (same model, Meta may train on inputs; slower) |
| Human-like help | none | none; irreversible steps approved by a script (counted) |

## Protocol

**0. Split (done before any run):** `eval/androidworld/split.py` → `eval/results/androidworld/split.json`: tasks grouped by (app, difficulty), shuffled with seed 20261027, alternated between halves. Dev 58 (31 easy, 18 medium, 9 hard, 20 apps), held-out 58 (30 / 18 / 10, 21 apps). Committed with this plan.

**1. Harness proof** (`run_aw.py --agent noop` and `handsolve.py`):
- AndroidWorld's one-time setup on 5560/8560 (`aw_setup.py`); any app whose automatic onboarding fails is finished by hand over adb and noted.
- A trivial agent that never acts and never calls a model (AndroidWorld's random agent is fine too; I'll use a do-nothing one so the result is deterministic) on ~6 tasks across apps, including IR: each initializes, scores 0, tears down.
- 4–6 tasks done correctly by hand through adb (setting, Clock or Contacts scored through the screen, a data-entry task, an IR question answered through the channel): each scores 1. Plus the uiautomator2 check above.

**2. Adapter and offline tests:** goal in → answer out; step budget passed; status → done mapping; payload holds nothing but the goal and budget; trace linked; the answer reaches `interaction_cache`. Envoy's 111 tests stay green.

**3. Pilot (12–15 tasks across apps and difficulty, from both halves; harness fixes only):** per task cost, time, steps; project the full run. Stop and ask if the projection is over $6 billed.

**4. Baseline:** all 116, seed 30, pass@1, Envoy exactly as `main` has it (commit recorded). The headline.

**5. Analysis on the dev half only:** every dev failure gets one primary cause (perception; navigation and app knowledge; action mechanics; planning and recovery; verification; answer format; harness/emulator/app), with the trace evidence quoted and secondary causes noted. Ranked by count.

**6. Improvements:** the largest causes, fixed in ways that help on any app, one commit each with its rationale and the dev failures it targets, checked first on the targeted dev tasks only, plus a quick regression on Envoy's offline tests.

**7. Re-measure:** all 116 again. Report baseline vs improved for dev and held-out separately; held-out is the honest estimate. Flag any fix that helped dev but not held-out. Run-to-run noise: the paper saw 27.6–33.2% across seeds for one agent, so I'll also rerun the baseline on a stratified subset if time allows, to size the noise before claiming a change.

**8. Routines across seeds:** for tasks the agent solved at seed 30, compile from those traces (`compile_trace`, Muse Wonder, as `eval/run_routines.py`), verify by replay on seed 30 under AndroidWorld's scoring, into `eval/results/androidworld/routines/library/` (not `data/routines/`). Then, for instances 1–3 of each (three unseen seeds): the matcher fills the inputs from the new goal, the executor replays (repairs allowed, full-agent fallback counted separately), AndroidWorld scores. Same seeds with the full agent for comparison. Report success, model calls, cost, time (model vs device, since Contributor latency is ~4× standard), which steps needed repair, and which tasks change structure, not just parameters, with the seed.

**9. Report:** `docs/androidworld-results.md` + JSON under `eval/results/androidworld/`, with the setting, results by app and difficulty, before/after on both halves, the taxonomy, routines, the leaderboard comparison, the ranked list of changes for `main`, and proposed text for the design doc, `docs/meta-feedback.md` and `THIRD_PARTY.md`.

## Commands (one per stage; each records Envoy's commit, AndroidWorld's commit, seed, split, model and tier)

```bash
eval/androidworld/emulator.sh start                                    # boot AndroidWorldAvd on 5560/8560
eval/androidworld/aw.sh aw_setup.py                                    # one-time AndroidWorld setup
eval/androidworld/aw.sh run_aw.py --stage harness --agent noop --tasks …
eval/androidworld/aw.sh handsolve.py                                   # hand-solved tasks score 1
eval/androidworld/aw.sh run_aw.py --stage pilot --tasks …
eval/androidworld/aw.sh run_aw.py --stage baseline                     # all 116, seed 30
eval/androidworld/aw.sh run_aw.py --stage improved                     # all 116 after the fixes
eval/androidworld/aw.sh routines.py compile|replay|agent               # routines across seeds
uv run --project backend python eval/androidworld/report.py            # tables and JSON
```

## Estimates

- **Time per task:** ~5 s per step on Contributor (3.4 s model + settle and act) plus ~20–40 s of AndroidWorld setup and teardown. Envoy succeeds in fewer steps than the budget; failures often use all of it. Expect 1.5–3 min per task: **3–5 h per full run** of 116.
- **Cost per full run:** at most 2,369 steps; realistically ~1,500 steps and ~130 plan calls: **~$0.4–0.8 billed, ~$5–9 at standard prices.** Screenshots add ~1k tokens each (negligible billed); SAM 3.1 is $0.0025 an image and only on drawn targets.
- **Whole job:** pilot ~$0.05, baseline ~$0.7, targeted dev reruns ~$0.3, re-measure ~$0.7, routines (≈20–30 compiles at ~$0.05 on Wonder's standard price, replays nearly free, agent on 3×N seeds ~$0.4) ~$2: **about $4 billed** of the $10. `META_DAILY_COST_CAP_USD=4` in this checkout's `.env`, so no single day can overspend.
- **Calendar:** setup and harness proof Oct 27–28; pilot Oct 28; baseline Oct 28 (overnight-length); analysis and fixes Oct 29–30; re-measure Oct 30; checkpoint with the merge list by Oct 31 so anything you approve lands by Nov 1; routines Oct 31; report Nov 1.

## Checkpoints (I'll ask and send a notification)

1. **After the pilot:** cost per task, the projection, the adapter as built, blockers.
2. **After the baseline:** the headline, the first look at causes, spend so far.
3. **Before proposing merges (by Oct 31):** each change with its held-out effect.

## Risks

- **Emulator hangs** under two emulators (memory note): AndroidWorld's checkpointer resumes; recovery is killing only my qemu pid, then `emulator.sh start`.
- **uiautomator2 vs the forwarder:** handled above; if neither stopping nor restarting works, scoring-through-the-screen tasks get flagged as harness failures rather than counted.
- **App setup:** two onboarding steps failed during AndroidWorld's automatic setup (Contacts' "Don't allow", OpenTracks' "Allow"); finished by hand and noted.
- **Noise:** model non-determinism; the held-out half is 58 tasks, so a difference of a few tasks is within noise. I'll say so rather than over-claim.
- **Contributor latency** inflates the agent's time against routines; times are reported split into model and device time so they can be compared at standard latency.

## Dev-half analysis and the fixes chosen from it (Oct 28, before any re-measurement)

Written before any run with the fixes, from the **dev half only** (held-out traces not read for causes). Each of the 45 failed dev episodes of the Contributor baseline was read step by step and labeled with its decisive step and quotes (`eval/results/androidworld/baseline/labels_dev.jsonl`); mechanism counts come from `signals.py`.

| Group | Failures | Mechanism, in the traces' words |
| --- | ---: | --- |
| A. Could not open the app | 15 | The plan named no app or a wrong package (`net.osmand.plus`, `com.google.android.apps.tasks`, `…nbu.files`); launch failed with no fallback; the model wanted the app drawer but pressed back ("Placeholder to comply with schema while opening drawer"). 1,057 of 2,146 Contributor steps were on the home screen. |
| B. An action the model didn't mean, inside the app | 16 | back with a reason saying otherwise ("No, must continue timer entry"), copied from history ("Accidental back, need to recover" right after the app opened), or "to dismiss the keyboard" with none up (closing Markor's editor, discarding recipe forms). |
| C. Finished, never concluded | 8 | Two correct dones rejected by the plan's invented check ("Resume", "Thumbnail") and not repeated; six kept verifying a deletion or a setting until the budget ran out. |
| D. Couldn't read or keep content | 3 | Markor's recipes.txt (12,101 characters in one EditText) showed as its first 120; a note read and forgotten (5-step history). |
| E. Dates | 2 | The model never knew the phone's date (Sunday, October 15 2023): "this Monday October 26"; "Thursday" not mapped to October 12. |
| F. Ambiguity | 1 | "after 5:20pm" read strictly; AndroidWorld means at or after. |

Cross-cutting: a Clock timer left running by an earlier task ticks on the home screen in every later task (AndroidWorld resets the phone's clock per task), so no-op backs read as "screen changed" (255 in the dev half) and stuck detection never fired; the history echoed the model's own expectations back (375 repeats in 40 of 45 failures).

**Fixes, one commit each, all general** (none names a task, an app's screens or an answer): (1) open apps by name, the planner sees the phone's apps; (2) screen lines that change by themselves are not progress; (3) history without the model's expected text; (4) SCREEN says when the keyboard is open, back is explained, an action the model itself calls a placeholder is asked again; (5) done once the screen shows it, answers in the goal's format, a second done accepted; (6) stuck recoveries start afresh after progress; (7) the phone's date to plan and steps; (8) long text at length; (9) a routine-compiler bug on main (swipes compiled as launches, launches dropped); (10) expected_result before the action in the step schema. Harness: hide android_env's pointer overlay as AndroidWorld's agents do; count rejected dones.

**Order of measurement:** merge main into the branch (the fixes are proposed against current main); dev half on the Contributor tier with the fixes, compared with the Contributor baseline's dev half; iterate on dev only; then all 116 on the standard tier, reported by half against the standard baseline. A held-out gain is the evidence for a merge; a dev-only gain is flagged as such.

## Rounds 2–3 and the final set (Oct 28, 09:05, written while round 3 runs, before its result)

- **Round 1** (fixes 1–9, `4c3c989`): dev 27/58 against the Contributor baseline's 13 (+16 −2, p = 0.0013).
- **Round 2** (+10b, `598a6cd`): dev 25/58, against 27 for round 1 (+2 −4, p = 0.69). Back fell from 13% to 8% of actions; no score effect I can measure. Kept: it repairs how the step is written, and nothing in the traces shows harm.
- **Round 3** (+11 working memory, `23a845d`; +4b keyboard from the navigation bar, `a80b976`) is running on dev now.

**Rule for the final set, fixed before round 3's result:** the final re-measure runs the branch as it stands after round 3, unless round 3 is clearly worse than round 2 on dev: at least 4 more tasks lost than gained, or a mechanism in the traces that the change introduced (for example, steps spent writing memory instead of acting, or the keyboard line shown with no keyboard up). In that case the change responsible is reverted, in its own commit, and the final set is round 2 plus whatever of round 3 is not implicated. No round 4 on dev: further dev iteration would fit the dev half, and the held-out half is what's left to measure.

**Final re-measure:** all 116 on the standard tier, seed 30, pass@1, one run (stage `final-standard`), compared by half against `baseline-standard`. The held-out half is the estimate; dev is reported beside it and labelled as the half the fixes were chosen on.

## Routines across seeds: the code each stage runs (Oct 28, 19:20, written before any seeds run)

- **Same-seed replay** (`routines-verify`, no repair, no agent): the branch as measured in `final-standard`. The last 4 of 59 run on the same code (`d86fa7e` and later commits change no backend file).
- **Then main is merged into the branch, before `routines-seeds` and `agent-seeds`.** Since the branch was last merged, main gained three routine-repair commits (`074390a`, `265177e`, `4d5aac9`: a repair counts only on the step's own screen, a relaxed repair is turned down only by evidence against its screen, a patch that changes nothing makes no version). The seeds stages allow repair, so they should measure the executor Envoy has now, with the changes proposed here on top: main plus those changes, the configuration proposed for merging. Main's new commits change no file the agent uses on an emulator (`backend/agent/`, `backend/models/`, the Android device layer are untouched), so `agent-seeds` runs the same agent as `final-standard`. The branch's suites must pass after the merge (on main plus the branch, 249 backend tests and the 7 harness tests pass in a scratch clone).
- **Nothing else is merged mid-experiment.** Work still in other branches (routine repairs in progress, model profiles, app notes) stays out, so all six seeds runs (routines and agent, instances 1–3) use one commit.
- **Promotion** uses `routines-verify` only: a routine is replayed on other seeds if it did its own seed-30 task on its own. The verified library is fixed before the first seeds episode.
- **If main gains routine fixes before the seeds stages start** (the routine-bugs branch: popup windows read as their app, `field_equals` among twin fields, row-anchored locators, dates worked out for the matcher), they come in with main by the rule above. The fixes that change what the compiler writes don't help routines already compiled. So the routines they touch are recompiled from the same seed-30 source runs, then replayed on seed 30 again (no repair, no agent) before promotion: the 5 with a `PopupWindow` app check (both Broccoli single-delete routines, both multi-delete routines, Retro Music's playlist export) and the 2 Pro Expense deletes. The other routines keep the versions already verified. The matcher's date then comes from the phone, read the same way as the agent's TODAY (fix 7), not fixed to AndroidWorld's date. Both the first and the re-verified results for those 7 are reported.
