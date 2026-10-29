# Wonder, app notes, personal benchmark: interim report (Oct 28, 22:15 ET)

Branch `claude/wonder-appnotes` (worktree `.claude/worktrees/wonder-appnotes`), not merged, not pushed. Since 21:15 the
**Envoy coordinator** session holds the device locks (`~/Desktop/Envoy/coord/devices.sh`) and does every merge into main,
so this branch goes to it when done instead of being merged here. Device stages run in the coordinator's windows.

## Done

**0. Plan:** `prompts/wonder-appnotes-plan.md`.

**1a. Model profiles** (`ENVOY_MODEL_PROFILE=spark|hybrid|wonder`, per-job overrides, Wonder limits, profile in the cost log
and task records). Verified live on Wonder: `low` effort, structured output, images, grounding.

**1b. AndroidWorld comparison: spark stays the default.** Same 20 tasks, seed 30, standard tier, one run each
(`eval/results/androidworld/model-comparison/2026-10-28/`):

| Profile | Passed | Per task | Total | Mean steps | Mean s |
| --- | --- | --- | --- | --- | --- |
| spark | 9/20 | $0.030 | $0.60 | 10.8 | 39 |
| hybrid (plan, step, repair, compile on Wonder) | 14/20 | $0.104 | $2.09 | 9.7 | 51 |
| wonder (every job on Wonder) | 13/20 | $0.104 | $2.07 | 9.4 | 57 |

Hybrid is +5 (the rule's margin) but 3.46× the cost per task (the rule asks under 3×), so `spark` stays the default and
`hybrid` stays available. In 5 of hybrid's 6 gains Spark ran out of steps on a wrong strategy; all three of Wonder's losses
were a replan after the work was done. A full 116-task rerun: about $4.70 under spark, about $16 under hybrid or wonder
(not run; the user's call).

**2a. App notes** and **3a. the benchmark** (task file, driver): built and reviewed earlier. Since then: run 1 starts with
the notes Envoy wrote in 2b's warm-ups (`--notes-from`), results folders take `--date` (a resume after midnight), 2b keeps
each run's step log with the note ids it saw, and the benchmark's runner never installs an app.

**2b on real apps** (spark, envoy-real, read-only; `eval/results/app-notes/2026-10-28/`): 3/3 before and after; steps 5.3 →
5.7, calls 7.3 → 7.7, $0.039 → $0.038. These read tasks were already easy for Spark; the notes were read (2–3 per call) and
didn't change the outcome. Envoy wrote 5 notes, none personal ("To browse without choosing a store, tap Skip then Yes on the
skip confirmation dialog").

**3b, the before pass** (run 2: spark, notes off): 15/17 graded; S4 and C2 passed on envoy-real. M4 failed (memory's old
gate served as "may have changed" instead of re-checking) and P2 failed (the agent left the app before the paid step).
**Run 1** (spark, notes on): S4 and C2 pass.

## Still to run (booked with the coordinator)

| When | Device | What |
| --- | --- | --- |
| ~00:05 | envoy-test (25 min) | 2b on SkyLark: 6 tasks cold, 6 warm-up, the 6 again warm |
| ~01:20 | envoy-test (20 min) | run 1's SkyLark and memory tasks, starting with 2b's SkyLark notes too |
| after Phase 7's real-app pass | both phones (20 min) | C1, C3, C4 for run 1 and for run 2 |

Then: merge main, full suite and `npm run build`, hand the branch to the coordinator, final report.

Spend so far: **$5.34 of $30** ($4.76 comparison, $0.58 here).

```bash
# 2b on SkyLark (envoy-test claimed through devices.sh):
ENVOY_MODEL_PROFILE=spark META_DAILY_COST_CAP_USD=6 nice -n 10 uv run --project backend python eval/run_app_notes.py --phase skylark --date 2026-10-28
# run 1, the envoy-test tasks:
ENVOY_MODEL_PROFILE=spark nice -n 10 uv run --project backend python eval/run_personal.py --label run1 --data $TMPDIR/envoy-personal-run1 --resume --date 2026-10-28 --profile spark --notes on --notes-from $TMPDIR/notes-skylark.db --budget 12
# C1, C3, C4 with both phones, for each run:
... --label run1 --data $TMPDIR/envoy-personal-run1 --resume --date 2026-10-28 --tasks C1,C3,C4 --profile spark --notes on
... --label run2-spark-notesoff --data $TMPDIR/envoy-personal-run2 --resume --date 2026-10-28 --tasks C1,C3,C4 --profile spark --notes off
```
