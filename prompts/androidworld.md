# Envoy on AndroidWorld

You are working on **Envoy**, my solo project for the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026, indie track, "Push the Frontier"; features freeze **Nov 2**, submissions due **Nov 4, 9:00 PM ET**). Envoy is a Muse-powered agent that operates Android apps: it reads the accessibility tree first (numbered elements, screenshots only when needed), acts through a policy gate, compiles a successful run into an **app routine** that reruns with no model calls, and keeps a shared **memory graph**. Phases 0–6 are built (Phase 6's gate on a real phone waits for the hardware, which isn't yours to touch); the main chat is now on Phase 7 (evaluation and submission).

**Your job is to run Envoy on AndroidWorld**, Google Research's benchmark of 116 parameterized tasks across 20 real open-source Android apps, and learn as much from it as we can.
- **Best case:** a credible success rate, with Envoy's cost and speed beside it, that belongs in the write-up.
- **In every case:** a precise, evidence-backed account of where Envoy fails and why, the general improvements that fixes, and the measured effect of each.

A bad number honestly explained is worth more to me than a good number I can't defend. Take your time, think it through, and do your best work.

You have full permission to do whatever this needs on this Mac (installs, a new emulator and system image, a separate checkout, commits and pushes of **your own branch** to the private repo), with these exceptions:
- Never type passwords or sign in to accounts. Never use my payment methods.
- Before any change visible outside this Mac (making anything public, posting, forms, a public tunnel), ask me.
- Never touch my real Android phone or my iPhone; never touch the main chat's emulators, its API, or its branch.

## You run in parallel with the Phase 7 chat

The main chat (`prompts/phase-7.md`) is evaluating Envoy and preparing the submission on `main`, on the same Mac, at the same time. Isolation keeps both honest:

- **Your own checkout.** A git worktree on its own branch, `~/Desktop/Envoy-androidworld` on `androidworld` (already created, with `.env` copied in; if it's missing, create it with `git -C ~/Desktop/Envoy worktree add ~/Desktop/Envoy-androidworld -b androidworld main` and copy `~/Desktop/Envoy/.env`). Work only there; `.env` is gitignored, never commit it. Commit and push only the `androidworld` branch; never commit to, merge into or push `main`.
- **Your own emulator, on your own ports.** The main chat uses `envoy-test` (console 5554, gRPC 8554), `envoy-real` (5556/8556), `envoy-small` (5558/8558) and, from Oct 28, my real phone. AndroidWorld's defaults are console **5554** and gRPC **8554**, which collide. Run yours on console **5560** and gRPC **8560** (serial `emulator-5560`) and make AndroidWorld and Envoy both use them. Always pass `-s emulator-5560` to adb; never `adb kill-server` (the adb server is shared).
- **At most two emulators run on this Mac at once** (24 GB; about 7 GB each), counting the main chat's. Yours is one of them, often for hours. Never start a second of your own, never stop one that isn't yours, and stop yours cleanly (`adb -s emulator-5560 emu kill` after a `sync`, or the emulator's own shutdown) whenever you pause for long, so the main chat can use the slot.
- **Your own logs and budget.** Your checkout has its own `logs/model_costs.jsonl`. Your budget is **$10** of the shared Meta key (about $29 is left; the main chat has $14). Set `META_DAILY_COST_CAP_USD` to protect it. Report your spend at each checkpoint, and ask me before going over.
- **Envoy's code.** On your branch you may change Envoy's agent, prompts and device layer to fix what AndroidWorld reveals; that is the point. Keep each change small, general and in its own commit. Nothing reaches `main` unless I say so, and only by **Nov 1**, so the main chat's frozen final evaluation (Nov 2) can include it; later changes stay on the branch and go in the write-up as findings.
- **Documents.** Write only your own: `prompts/androidworld-plan.md`, `docs/androidworld-results.md` (including proposed text for the design doc and for `docs/meta-feedback.md`), and results under `eval/results/androidworld/`. The main chat owns the design doc, the README and the submission, and reads your results from your branch.

## Read first (in this order)

1. AndroidWorld itself: the repository (github.com/google-research/android_world): its README, setup, `run.py`, the agent interface (`android_world/agents/base_agent.py`, and `t3a.py` / `m3a.py` as references for how agents use the environment), the environment and action types (`env/`), how tasks set up, score and tear down, how information-retrieval answers are scored, its seeds and per-task step limits. Also the paper, and the current leaderboard and how it labels each entry's setting. Verify every fact below against the code; where they disagree, the code wins.
2. Envoy: `docs/technical-design.md` › **Agent runtime** (observe → decide → policy → act → verify; text first; screens without a tree), **App routines**, **Device layer**, **Evaluation** (AndroidWorld is listed there as a stretch). The live version is https://claude.ai/artifact/Sf51zMf4SMi5ZZmJabgPR5.
3. `docs/phase-1-results.md` (the agent, its failure fixes), `docs/phase-2-results.md` (routines, the real-app checkpoint), `docs/phase-6-results.md` (vision on screens with no tree: SAM 3.1 then grounding), and `docs/real-app-test-set.md`.
4. The code you'll touch: `backend/agent/loop.py`, `backend/models/prompts.py` and `schemas.py`, `backend/agent/vision.py`, `backend/devices/`, `backend/routines/` (compiler, executor, matcher), and `eval/run_skylark.py` and `eval/run_real_apps.py` as examples of Envoy's evaluation style.
5. The memory notes in `~/.claude/projects/-Users-sanjeevvarma-Desktop-Envoy/memory/` (eval practice, hung-emulator recovery, notifying me when I'm needed).

## What I know (verify it; don't trust it blindly)

- **AndroidWorld** runs on an emulator from an AVD named `AndroidWorldAvd`: a Pixel 6 on API 33 (Tiramisu). On this Apple-silicon Mac that needs the **arm64** Google APIs image (`system-images;android-33;google_apis;arm64-v8a`; only API 35 is installed now). It is launched with a gRPC port, and its first run takes a setup flag that installs its apps and data. Its loader takes the console port; check how it chooses the gRPC port and set both to yours.
- **Its Python:** read its requirements. Envoy's backend is pinned to Python 3.13 (`uv`, `backend/pyproject.toml`). If AndroidWorld needs another version or conflicting packages, give it its own environment and connect the two (below). Don't loosen Envoy's pins for it.
- **The emulator's gRPC port without `-grpc-use-token` listens on every network interface with no auth** (measured in Phase 0): anyone on the same Wi-Fi could control it. Use the token if AndroidWorld's client works with it; if it can't, keep the plain port only behind the macOS firewall, and tell me.
- **Envoy's agent:** Muse Spark 1.3 at `low` effort with structured output. One model call per step (about $0.001 text-only, more with a screenshot). It plans first, sees a compact numbered element list, asks for a screenshot (`look`) when it needs one, and taps drawn targets with `tap_point` + SAM 3.1 then grounding. It handles pop-ups, sign-in hand-off, stuck screens and cycles in code. Its own success check runs before `done`. Its actions go through uiautomator2 (tree, typing by accessibility set-text) and the emulator's gRPC (taps, screenshots) via `EmulatorDevice`.
- **Envoy's launch action takes a package name.** AndroidWorld tasks name apps the way a person would ("Simple Calendar Pro", "Markor"). How Envoy opens an app it doesn't know the package of is likely its first gap.
- **uiautomator2 runs a UiAutomation session**, which can suppress other accessibility services. If any task's setup or scoring reads the screen through AndroidWorld's own accessibility service, the two may conflict. Check it in the pilot.
- **Model tier:** use the **Contributor tier** for AndroidWorld, as for SkyLark: its apps hold only synthetic test data, so I allow it here. It is a separate model ID (`muse-spark-1.3-contributor`), limited to 150 requests a minute, with no `max` effort; Envoy picks it when a run passes `contributor=True` (see how `eval/run_routines.py` and `eval/run_phase6.py` do it). It is never for real apps or real data.
- **Approvals:** Envoy's policy asks before irreversible steps (delete, send, confirm). On AndroidWorld's synthetic test apps, a scripted person may approve them, the way it does on SkyLark. That is my permission for this benchmark only. Count every approval and report it.

## The job

Write the plan first as `prompts/androidworld-plan.md` (like `prompts/phase-6-plan.md` in the main repo): setup steps, the adapter's design, the protocol below, cost and time estimates, and checkpoints. Commit it on your branch, then work through these in order.

1. **Set up, and prove the harness before measuring anything.**
   - Worktree, system image, AVD and AndroidWorld's environment; its one-time app setup on your ports.
   - Run a few tasks with a trivial agent (AndroidWorld's random or no-op agent, never one that calls an outside model API): tasks must initialize, score 0 when nothing is done, and tear down cleanly.
   - Then do a few tasks correctly by hand through adb, so they score 1. That proves the scoring and the answer path for information-retrieval tasks.
2. **The adapter: Envoy as an AndroidWorld agent.** AndroidWorld sets up each task, gives the goal, and scores the result with its own checks. Envoy does the phone work with its own device layer on the same emulator. The interaction loop itself is yours to design. Write the design and its trade-offs in the plan; prefer the simplest design that keeps the benchmark's scoring untouched. Requirements:
   - **No task-specific help.** No hints, prompts or code keyed to task names, app names or expected answers. Envoy sees only the goal text and the screen, as with any request. Nothing reads AndroidWorld's task internals, parameters or solutions during a run.
   - **The benchmark's own limits.** Use AndroidWorld's per-task step budget (or its standard one), map Envoy's `done` answer onto AndroidWorld's answer channel for information-retrieval tasks, and score only with AndroidWorld's checks. Envoy's own success check is not the score.
   - **One run, one record.** Keep Envoy's trace for every run (steps, screens, calls, tokens, cost, time, approvals, pop-ups, stuck recoveries), linked from the results.
   - **Memory off.** No memory notes and no routines in the baseline: the agent alone.
3. **Pilot (10–15 tasks across apps and difficulty).** Fix harness problems, not agent behavior. Measure cost and time per task and project the full run. If the projection is over $6, propose a smaller, stratified set and ask me.
4. **The protocol for honest improvement.** Before looking at any results, split the 116 tasks into a **dev half** and a **held-out half** with a fixed seed, stratified by app and difficulty, and commit the split. Then:
   - **Baseline:** all 116 tasks, AndroidWorld's standard seed, pass@1, the agent exactly as `main` has it today. This number is the honest headline.
   - **Analyze the dev half only.** Put every failure in a cause:
     - perception: a missing or misleading tree, drawn screens;
     - navigation and app knowledge: finding or opening the app;
     - action mechanics: typing, date and time pickers, scrolling, long press, text editing;
     - planning and recovery;
     - verification: claimed done when it wasn't;
     - answer format, harness, or an emulator or app problem.
   - Quote the trace evidence for each. Rank the causes by how many failures each explains.
   - **Improve generally.** Fix the largest causes in ways that would help on any app. Each fix is a separate commit with its rationale and the failures it targets.
   - **Re-measure:** all 116 again. Report the baseline and the improved result for each half separately; the held-out half is the honest estimate of what the fixes are worth. Note any fix that helped dev but not held-out.
5. **Routines across seeds: Envoy's own angle.** AndroidWorld randomizes each task's parameters per seed, which is exactly what routines are for.
   - For tasks the agent solved, compile routines from those runs, the way `eval/run_routines.py` does: compiled, then verified by replay. Keep them in a separate library, not `data/routines/`.
   - Replay each routine on 3 other seeds, with the new goal text supplying the inputs (the matcher, or the compiler's input binding).
   - Report:
     - success on unseen seeds;
     - model calls, cost and time against the agent on the same seeds;
     - which steps needed repair;
     - where routines can't apply: tasks whose structure, not just parameters, changes with the seed.
6. **The report.** `docs/androidworld-results.md`, with JSON under `eval/results/androidworld/`:
   - **Setting:** model, effort, inputs (tree first, screenshots on demand), action space, step limits, seeds, AndroidWorld's commit and version, the emulator image, and what differs from the official protocol.
   - **Results:** success by app and difficulty, cost, time, steps, calls and approvals per task.
   - **Before and after** the improvements, on both halves.
   - **The failure taxonomy**, with counts and examples.
   - **Routines across seeds.**
   - **Comparison with the leaderboard:** only like-for-like where the setting matches, labeled clearly where it doesn't. No claim of state of the art unless it's true in the same setting.
   - **What Envoy should change** on `main`, ranked, each with the evidence and the measured effect, so I can decide what to merge by Nov 1.
   - **Proposed text** for the design doc's Evaluation section and for `docs/meta-feedback.md` (Muse Spark and SAM 3.1 on AndroidWorld's apps).

## Checkpoints (ask me, and notify me)

- After the pilot: cost per task, the projection, the adapter design, anything that blocks.
- After the baseline: the headline number, the first look at causes, the spend so far.
- Before proposing merges into `main` (by Nov 1): the list of changes, each with its held-out effect.

## Testing

- Offline tests for the adapter: goal in, answer out, step limits, traces linked, nothing reads task internals. Envoy's existing 111 tests stay green on your branch.
- Every run is reproducible from one command per stage (setup check, pilot, baseline, re-measure, routines). It records the Envoy commit, AndroidWorld's commit, the seed, the split, the model and the tier.

## Rules and constraints

- **Integrity first.** No tuning to specific tasks and no peeking at expected answers. Report every number with its setting. Never report a selected subset as if it were the full benchmark.
- **The hackathon rule:** the demo may only show work built during the hackathon, clearly identified. AndroidWorld is Google's benchmark (credit it, with its license, in your proposed `THIRD_PARTY.md` text); the adapter, the analysis and the improvements are ours.
- **Budget:** $10, Contributor tier, `low` effort as Envoy uses it; avoid needless repeats; ask before exceeding. Report costs at both the billed price and the standard price (the adapter logs both), so the numbers compare with other agents.
- **Safety is unchanged:** nothing types passwords; no real accounts or real data; no real phone; secure screens are never stored; the scripted person approves only on AndroidWorld's synthetic apps.
- Commit after each meaningful step and push your branch (`androidworld` only).
- When you need me (a decision, the budget, a blocker), ask right away and send a notification.

## Done means

- The harness is proven (trivial agent scores 0, hand-solved tasks score 1); the adapter is tested.
- The baseline on all 116 tasks, the dev/held-out improvement cycle, and the routines-across-seeds experiment have run, or their scope was cut with my OK and the cut is stated.
- `docs/androidworld-results.md` and its JSON are complete, honest and committed on `androidworld`, with the ranked list of changes proposed for `main`.
- Finish with a short summary:
  1. the headline success rate (baseline and improved, by half) with its setting, cost and time
  2. the top failure causes, with counts
  3. what routines did across seeds
  4. the changes you recommend merging into `main`, ranked, with their held-out effect
  5. what's left or uncertain
