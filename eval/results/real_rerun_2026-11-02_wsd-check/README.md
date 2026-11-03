# Real-app check, Nov 2: amazon and chrome_wikipedia on `3d0df77`

The coordinator asked for this check before the eval. It reruns the two workflows touched since the baseline
(`../real_rerun_2026-11-02_wsd-baseline/`), with fresh agent runs, on main `3d0df77`. That commit holds:
- 94cd0b3 and 6140caf (merged in a1c94a6): no check on System UI drawn over the app; an input shown only on the app's
  opening screen kept as a check;
- 3d0df77 itself: the real-app harness opens about:blank in Chrome before the agent's run and each routine run.

- **Command:** `WORKFLOWS=amazon,chrome_wikipedia eval/run_real_rerun.sh 3d0df77 wsd-check` on envoy-real.
- **Config:** standard tier, `hybrid` profile.
- **Run:** `1102191753`, 19:17–19:21 ET. 21 model calls, **$0.24** at standard prices.

**Only the amazon and chrome_wikipedia rows are from this run.** `eval/run_final.py real --only` keeps the commit's other
16 tracked rows, which come from Oct 28 runs. So `real.md`'s stage totals mix runs: don't cite them.

| Workflow | First run | Compiled | Same input | New input |
| --- | --- | --- | --- | --- |
| amazon | pass ($19.99, 2 actions) | ✅ 2 steps | **pass, 0 calls** (baseline: pass after a repair) | fail: "outputs not found" (baseline: fail) |
| chrome_wikipedia | right, unverified (1889, 6 actions) | ✅ 3 steps, input `article_subject` | right (1889), 3 calls | **right (1886)**, 1 call (baseline: input not learned) |

- **amazon:** the start screen's before-check no longer names a passing notification, so the rerun needs no repair. The
  new input still finds no price. The compiled pattern is shaped on the battery listing ("( $X /count) List: $Y"), and
  "USB-C cable"'s first result doesn't have that shape. That's a known limit, with no fix before the eval.
- **chrome_wikipedia:** with a blank page first, the agent typed the address and the topic. The routine learned the
  topic, and the Statue of Liberty run answered 1886, which is right.
  - The suite grades both reruns "pass after repair": the year is read from the screenshot (no tree text), and that
    read counts as a model call. No repair ran.
  - So the row is right on a new input with 1 model call. Stage 4 ("no model call") still doesn't count it.
