# Wonder, app notes, personal benchmark: interim report (Oct 29, 00:30 ET)

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

**2b, app notes before/after** (spark; `eval/results/app-notes/2026-10-28/`): **no measurable effect.** SkyLark 6/6 → 6/6,
steps 2.8 → 3.0; real apps (read-only) 3/3 → 3/3, steps 5.3 → 5.7; calls and cost level. The tasks were already easy (1–7
steps). Envoy wrote 13 notes (8 SkyLark, 5 Starbucks/DoorDash), none personal, none dropped, for $0.04. The step changes
between passes come from a Spark quirk, not the notes (below).

**3b, the benchmark** (17 of 20 graded in both runs; C1, C3, C4 wait for two free phones):

| | Run 2: spark, notes off | Run 1: spark, notes on (2b's 13 notes) |
| --- | --- | --- |
| graded | 15/17 | 15/17 |
| failed | M4 (memory's old gate), P2 (agent left the app) | M4 (same), P2 (chat's router said "no routine for that") |

Same score, same costs within a cent per task. M4 is fixed in main already (Session B's 85a5d32: chat checks the app when
a fact is past its freshness); it gets re-run after the merge.

**Found: a template-like first `back`** (`eval/results/app-notes/2026-10-28/first-step-back/`). In 6 of 35 SkyLark agent
runs, Spark's first step returned `back` with a reason like "Placeholder to comply with schema while intending to open My
Trips", leaving the app (it caused run 2's P2 failure). Replayed 110 times ($0.13): 10–40% of the time on the same prompt,
with or without notes; an extra instruction or medium effort doesn't fix it; putting `action` before `reason` in the schema
makes it 10/10; re-asking once when the `back` contradicts its reason fixes 10/10. That re-ask is the proposed next fix.

**Merge rehearsed:** main (with Session B and app-routing) merged into a throwaway branch: one import-line conflict
(`models/adapter.py`), and one real bug found and fixed on this branch (80acbd7: the runner read `trace_dir` from results that
main's new phone tests fake without one). After that: 304/304 backend tests, `npm run build` passes.

## Still to run (booked with the coordinator)

| When | Device | What |
| --- | --- | --- |
| ~02:30 | both phones (20 min) | C1, C3, C4 for run 1 and for run 2; then M4 again on the merged code |

Then: merge main, full suite and `npm run build`, hand the branch to the coordinator, final report.

Spend so far: **$5.87 of $30** ($4.76 comparison, $1.11 here: benchmark, 2b $0.34, probes $0.13).

```bash
# C1, C3, C4 with both phones (envoy-test and envoy-real claimed through devices.sh), for each run:
ENVOY_MODEL_PROFILE=spark nice -n 10 uv run --project backend python eval/run_personal.py --label run1 --data $TMPDIR/envoy-personal-run1 --resume --date 2026-10-28 --tasks C1,C3,C4 --profile spark --notes on --budget 12
ENVOY_MODEL_PROFILE=spark nice -n 10 uv run --project backend python eval/run_personal.py --label run2-spark-notesoff --data $TMPDIR/envoy-personal-run2 --resume --date 2026-10-28 --tasks C1,C3,C4 --profile spark --notes off --budget 12
```
