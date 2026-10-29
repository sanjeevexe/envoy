# Wonder, app notes, personal benchmark: report (Oct 29, 15:20 ET)

**Done.** The branch's code is in main: the coordinator fast-forwarded main to `claude/wonder-appnotes` at 34102f9 after
338/338 backend tests and `npm run build` passed. Since then, two branches have gone to the coordinator:
- **`claude/wonder-appnotes`** (rebased on main 38237e8): results only. That's the Oct 29 runs below and this report.
- **`claude/router-no-routine`** (896fa65, on `coord/aw-rerun`): one instruction line for chat's router, with a test. The
  coordinator merges it after the AndroidWorld branch.

The default profile stays `spark`, as the decision rule says. Every stage has now run.
- **Billing:** the Meta API's billing failures (02:16–about 13:00) ended with the new account.
- **The coordinator:** the **Envoy coordinator** session holds the device locks (`~/Desktop/Envoy/coord/devices.sh`) and does
  every merge into main.

## Needs you

Nothing is blocking. Two calls are yours, with no rush:
- Whether to rerun AndroidWorld in full under `hybrid` (116 tasks, about $16, about 2–3 hours on AndroidWorldAvd). Spark's
  full run already exists (`final-standard`, $4.67).
- Whether to build the next fix: the re-ask on a contradicting first `back` (below). It isn't built here because it would
  change the agent between benchmark runs.

## Headline numbers

**AndroidWorld, 20 tasks** (the same 20, seed 30, standard tier, one run per profile;
`eval/results/androidworld/model-comparison/2026-10-28/`):

| Profile | Passed | Per task | Total | Mean steps | Mean s |
| --- | --- | --- | --- | --- | --- |
| spark | 9/20 | $0.030 | $0.60 | 10.8 | 39 |
| hybrid (plan, step, repair, compile on Wonder) | 14/20 | $0.104 | $2.09 | 9.7 | 51 |
| wonder (every job on Wonder) | 13/20 | $0.104 | $2.07 | 9.4 | 57 |

The rule asks for +5 tasks at under 3× the cost per task. Hybrid gained exactly 5 tasks but cost 3.46× per task, so `spark`
stays the default and `hybrid` stays available.
- **Hybrid's gains:** in 5 of its 6, Spark had picked a wrong strategy and ran out of steps.
- **Wonder's losses:** all three were a replan after the work was already done.

**App notes, before/after** (spark; `eval/results/app-notes/2026-10-28/`): **no measurable effect.**

| | Before notes | After notes |
| --- | --- | --- |
| SkyLark, 6 tasks | 6/6, mean 2.8 steps | 6/6, mean 3.0 steps |
| Real apps (read-only), 3 tasks | 3/3, mean 5.3 steps, $0.039 | 3/3, mean 5.7 steps, $0.038 |

- The tasks were already easy (1–7 steps), so there was little for a note to save.
- Envoy wrote 13 notes for $0.04: 8 for SkyLark and 5 for Starbucks and DoorDash. None was personal and none was dropped.
- The step changes between passes come from a Spark quirk (the template-like first `back`, below), not from the notes.

**Personal benchmark** (20 tasks we wrote ourselves, so not a neutral benchmark; grading is done in code, with no model
judge). Results: `eval/results/personal/2026-10-28-run2-spark-notesoff/` and `…/2026-10-28-run1/`.

| Category | Run 2: spark, notes off | Run 1: spark, notes on (2b's 13 notes) |
| --- | --- | --- |
| single (4) | 4/4 | 4/4 |
| memory (4) | 3/4 (M4) | 3/4 (M4) |
| cross (4) | 4/4 | 4/4 |
| repeat (4) | 4/4 | 4/4 |
| safety (3) | 2/3 (P2) | 2/3 (P2) |
| proactive (1) | 1/1 | 1/1 |
| **score** | **18/20**, $0.40 | **18/20**, $0.38 |

The two runs scored the same and cost the same to within a cent per task.
- **M4** failed both times the same way. **P2** failed for a different reason each time. See "Failures" below for both.
- The notes didn't change a result in either direction.
- **After the runs:** M4 passes on main. It ran twice, once on fb3d926 and once on 38237e8 (chat changed in between), each
  time with fresh memory. Each time chat saw the 3-hour-old gate, checked SkyLark and answered B12
  (`eval/results/personal/2026-10-29-postmerge/`).
- **Run code:** both runs kept one backend throughout. C1, C3 and C4 ran on Oct 29 from a checkout at 55ba723. Its backend
  matches the code the other 17 tasks ran on (9ccc800 and d4eb4fb) apart from a runner check that changes no result.
- **C4's DoorDash half:** the first coffee place differed between the runs (Peet's, then Gregorys). DoorDash's list is live,
  and the grade checks the SkyLark half ("delayed") and that both halves finished.

## Per step

| Step | What | Commits | Tests |
| --- | --- | --- | --- |
| 0 | Plan: `prompts/wonder-appnotes-plan.md` | cf93c24 | |
| 1a | Model profiles (`ENVOY_MODEL_PROFILE=spark\|hybrid\|wonder`, per-job overrides, Wonder's limits, the profile in the cost log and task records). Checked live on Wonder: `low` effort, structured output, images, grounding. | c5cad68 | 9 new in `test_adapter.py` |
| 1b | AndroidWorld comparison: a report script, the results, and the adb finding (below). In the comparison checkout (`claude/aw-model-compare`): eafd184 (profiles, per-episode cap) and f4f943f (AndroidWorld's adb fix). | 8d2025c, 25073f5, ddf8ee0 | `test_run_aw.py` 8/8 |
| 2a | App notes: Envoy writes, merges and reads its own notes about each app; they go into the plan, step and repair prompts; a web view to list and retire them; a before/after driver. After the coordinator's review, a note that reads like an instruction or a permission (a planted notice) is dropped in code. | c03c957, 50fc7f0, b665d5f, c1613a7, 80acbd7, d4c0332 | 59 in `test_app_notes.py`, 1 in `test_api.py` |
| 2b | Before/after runs, each run's step log, and the first-step `back` replays | d62e40d, 5eaf29c, 9ccc800, 77706ea, 01582ef, 0130f6f | |
| 3a | Benchmark: 20 tasks in six categories and their driver (`--notes-from`, `--date`, never installs an app) | adb1b92, c1613a7, 292fb98, d52963d, fcb366f, 99b7811 | 10 in `test_personal_bench.py` |
| 3b | Run 2, then run 1 (Oct 28); C1, C3, C4 for both (Oct 29) | d4eb4fb, 20c8e81, a18c437, 64bc6ca | |
| Merge | Main merged in. The one conflict was the `models.schemas` import in `models/adapter.py`; both sides' names are kept. The coordinator fast-forwarded main to 34102f9. | 503373b | **338/338**, web build passes |
| After | M4 on main (12e1b14, 9ed9ef5). P2's router replay (54e37a6). The router line on its own branch (`claude/router-no-routine`, 896fa65, with `test_chat_router.py`). | | 515/515 on that branch |

The branch adds 79 tests. Before the merge it passed 255/255, and 304/304 right after the merge.

**Devices** (ET; each claimed through `devices.sh` after Oct 28, 21:15):

| When | Device | What |
| --- | --- | --- |
| Oct 28, 17:48–18:07 | envoy-test | Run 2: the 15 SkyLark tasks |
| 20:38–20:39 | envoy-real | Run 2: S4, C2 (read-only) |
| 20:40–21:39 | AndroidWorldAvd | 1b: spark, then hybrid, then wonder |
| 21:59–22:04 | envoy-real | 2b real apps (read-only, every approval declined) |
| 22:04 | envoy-real | Run 1: S4, C2 |
| 23:06–23:10 | envoy-test | 2b SkyLark |
| 23:44–23:50 | envoy-test | Run 1: the 15 SkyLark tasks |
| Oct 29, 14:45–14:47 | envoy-test | M4 on main fb3d926 |
| 14:48–14:51 | envoy-test | M4 on main 38237e8 |
| 15:03–15:10 | envoy-test + envoy-real | C1, C3, C4 for run 1, then run 2 (read-only on envoy-real) |

## Failures

- **M4 (both runs), fixed on main:** memory answered with gate B9, seen 3 hours earlier, without checking the app, which
  shows B12.
  - Session B's 85a5d32 makes chat check the app when a fact is past its freshness.
  - It passes on main fb3d926 and 38237e8.
- **P2, run 2: the template-like first `back`** (`eval/results/app-notes/2026-10-28/first-step-back/`).
  - On SkyLark's home screen, Spark's first step returned `back` with a reason like "Placeholder to comply with schema while
    intending to open My Trips". That left the app.
  - It happened in 6 of 35 SkyLark agent runs (none of the 60 AndroidWorld episodes, which start with a launch).
  - Replayed 110 times ($0.13). It happens 10–40% of the time on the same prompt, with or without notes.
  - What doesn't fix it: one more instruction (no better) or medium effort (2/10).
  - Putting `action` before `reason` in the schema makes it happen every time (10/10).
  - Re-asking once when the `back` contradicts its own reason fixes it (0/10).
- **P2, run 1: chat's router refused, fix on a branch** (`eval/results/personal/2026-10-28-run1/p2-router/`).
  - It replied "Sorry, I can't add a checked bag to your Chicago trip — I don't have a routine for that in the SkyLark app"
    instead of starting a task.
  - The router sees a list headed "APPS (learned routines)": SkyLark has six there, none for bags, and nothing said a task
    doesn't need one.
  - Replayed ($0.57), as is vs with one instruction line ("A task needs no learned routine: …"):

| Request | Right route | As is | With the line |
| --- | --- | --- | --- |
| Add a checked bag to my Chicago trip. (no routine) | task | 6/40 replied "can't" | 0/40 |
| Which seat am I in on my Denver flight? | memory or task | 0/20 wrong | 0/20 wrong |
| Turn on Wi-Fi. (no routine either) | task | 0/20 wrong | 0/20 wrong |
| What can you do? | reply | 0/20 wrong | 0/20 wrong |

  The line is on `claude/router-no-routine` (896fa65), queued to merge after AndroidWorld's; Phase 7's Nov 2 eval measures it.
- **AndroidWorld under Spark:** wrong strategies that run out of steps (5 of hybrid's 6 gains). Under Wonder: a replan after
  the work is done (all three of its losses).

**The single most valuable next fix: re-ask once when a step's `back` contradicts its own reason** (`agent/loop.py`).
- **What it does:** treat that `back` as a rejected decision, as `done` and `tap_point` already are. That covers a reason that
  names another action or element, or talks of a placeholder, test, template, schema or format, and a `back` that would leave
  the goal's app on the first step.
- **Why it comes first:**
  - It hit about 1 in 6 SkyLark agent runs. It costs a task outright when the agent can't find its way back (run 2's P2).
  - It costs one extra call, and only when it fires.
  - In replay it took the rate from 1–4 in 10 to 0 in 10.
- **Next after it:** from 1b, finish instead of replanning once the last irreversible step has succeeded and the screen
  shows the result.

## Not run

- **The full 116-task AndroidWorld rerun:** your call (command below).
- **The re-ask fix:** not built. It would change the agent between benchmark runs, so it's a decision for after.

## Incidents

- **AndroidWorld's harness restarted the adb server that every session shares.**
  - android_env's `AdbController` runs `kill-server` then `start-server` whenever a device command fails its first try.
  - In 1b that happened three times (about 20:38, 20:45 and 21:01). The 21:01 restart broke Phase 7's repeats suite on
    envoy-test.
  - Reported to the coordinator and the AndroidWorld session. AndroidWorld fixed its harness in androidworld 3631542 (on the
    comparison branch as f4f943f).
  - Envoy's own device code only uses `adb -s <serial>`. Any future AndroidWorld run needs a checkout with that commit.
- **My wait loop counted as an emulator** (Oct 29, about 14:47–14:48).
  - `devices.sh` read every process's command line for `qemu-system`, and my background loop's command line contained one. So
    for about a minute it counted 2 of 2 emulators and could refuse a claim.
  - I stopped the loop and told the coordinator, and the coordinator hardened `devices.sh`: it now matches only the emulator
    binary.
- **An M4 rerun that didn't count.** The first rerun on 38237e8 reused the earlier run's memory, which already held a fresh
  B12, so it answered from memory and tested nothing. I discarded it and ran again with fresh memory.
- **2b's step logs were gitignored** (`*.jsonl`), so the 27 traces the 2b README and the replays read hadn't reached the
  branch. They're committed now (01582ef), with an exception in `.gitignore`. Before adding them I checked them: no
  screenshots, no names or emails, and the only address is the emulator's simulated location.

## Spend: $6.75 in all

| Share | Spent | Budget |
| --- | --- | --- |
| AndroidWorld comparison (`~/Desktop/Envoy-aw-compare`) | $4.76 | $8 |
| App notes: 2b $0.33, first-step replays $0.13 | $0.47 | $6 |
| Benchmark, Oct 28: run 1 $0.26, run 2 $0.26, smoke runs and checks $0.10 | $0.62 | $12 |
| Wonder's live checks (1a) | $0.02 | |
| **Oct 28 total** | **$5.87** | **$30** |
| Oct 29: C1, C3, C4 for both runs $0.26, M4 on main twice $0.04 (and $0.007 for the discarded rerun), P2's router replay $0.57 | $0.88 | $10 |

Each figure comes from the checkout's cost log, at standard tier.

## Command for what's left

The full AndroidWorld rerun under hybrid (about $16, 2–3 hours). Use `~/Desktop/Envoy-aw-compare`, which has the profiles
and the adb fix:

```bash
~/Desktop/Envoy/coord/devices.sh claim AndroidWorldAvd <owner> 210 "AndroidWorld 116 tasks under hybrid"
eval/androidworld/emulator.sh start
ENVOY_MODEL_PROFILE=hybrid META_DAILY_COST_CAP_USD=20 nice -n 10 eval/androidworld/aw.sh run_aw.py --stage final-hybrid --config '{"tier": "standard"}' --note "116 tasks under hybrid"
eval/androidworld/emulator.sh stop
```

The same command with `ENVOY_MODEL_PROFILE=spark` and `--stage final-spark` (about $4.70) would repeat `final-standard`,
since spark is already the default.
