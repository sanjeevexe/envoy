# Hybrid as the default: the personal benchmark, row by row (Oct 30)

The same 20 tasks, app notes on with the same 13 seeded notes (2b's), standard tier, one run each. **spark-same-code** and
**hybrid** ran on `coord/hybrid-default` (75f12ec, main 2d69938 plus the default change). **run1** is the Oct 28 spark run
(9ccc800), for history. Each cell: result, cost, wall time, model calls.

| Task | 2026-10-28-run1 | 2026-10-30-spark-same-code | 2026-10-30-hybrid |
| --- | --- | --- | --- |
| S4 | pass $0.009 18s 3c | pass $0.007 19s 3c | pass $0.009 21s 3c |
| C2 | pass $0.019 35s 6c | pass $0.018 26s 6c | pass $0.018 35s 6c |
| M1 | pass $0.011 8s 2c | pass $0.009 9s 2c | pass $0.007 7s 2c |
| M2 | pass $0.007 4s 2c | pass $0.006 5s 2c | pass $0.007 5s 2c |
| M4 | **FAIL** $0.006 4s 2c | pass $0.017 16s 4c | pass $0.018 18s 4c |
| M3 | pass $0.015 13s 3c | pass $0.015 19s 3c | pass $0.013 48s 3c |
| S1 | pass $0.006 4s 2c | pass $0.006 4s 2c | pass $0.006 4s 2c |
| S2 | pass $0.011 12s 4c | pass $0.013 15s 4c | pass $0.014 16s 4c |
| S3 | pass $0.020 41s 9c | pass $0.021 43s 9c | pass $0.074 52s 9c |
| C1 | pass $0.028 74s 12c | pass $0.027 94s 12c | pass $0.128 77s 12c |
| C3 | pass $0.073 45s 21c | pass $0.062 47s 18c | pass $0.160 67s 19c |
| C4 | pass $0.022 23s 6c | pass $0.018 18s 6c | pass $0.018 24s 6c |
| R1 | pass $0.031 31s 6c | pass $0.036 47s 6c | pass $0.032 40s 6c |
| R2 | pass $0.019 26s 6c | pass $0.016 26s 6c | pass $0.016 29s 6c |
| R3 | pass $0.029 31s 6c | pass $0.034 44s 6c | pass $0.035 44s 6c |
| R4 | pass $0.030 38s 6c | pass $0.031 73s 6c | pass $0.032 51s 6c |
| P1 | pass $0.009 15s 2c | pass $0.011 17s 2c | pass $0.008 12s 2c |
| P2 | **FAIL** $0.007 5s 1c | pass $0.008 48s 8c | pass $0.079 37s 8c |
| P3 | pass $0.006 9s 2c | pass $0.007 12s 2c | pass $0.006 14s 2c |
| P4 | pass $0.020 137s 3c | pass $0.033 146s 3c | pass $0.022 140s 3c |
| total | **18/20** $0.38 29s mean | **20/20** $0.39 36s mean | **20/20** $0.70 37s mean |

**Reading it**

- **No regression, and no gain on these tasks:** both profiles pass 20/20 on the same code.
- **M4 and P2 are fixed by main's code, not by the profile.** M4 is fixed by Session B's stale-gate check. P2 is fixed by the
  router line (3529761), and spark passes both on the same code.
- **Cost:** hybrid is $0.70 against $0.39 (1.8×). The extra comes from Wonder's plan, step and repair calls on the first
  runs and repairs: S3 $0.074 vs $0.021, C1 $0.128 vs $0.027 (two Wonder repairs, $0.069), C3 $0.160 vs $0.062, P2
  $0.079 vs $0.008. Memory answers, routine replays (R1–R4, M3) and the trigger (P4) cost the same, because they don't call
  Wonder.
- **Time:** the mean is 37 s against 36 s.
  - M3's 48 s under hybrid is not Wonder. M3 is a routine replay with no Wonder call, and its memory save (a Spark
    extraction) was retried once by the API and took 37 s.
  - C3 is +20 s and S3 +9 s, which is Wonder's latency.
  - C1 is −17 s and R4 −22 s, which is noise.
- **Infrastructure, rerun:** in the spark pass, envoy-test's Android system crashed at 00:41 ("The system died", then "Can't
  find service: activity"). R1–P4 all ended with driver errors before reaching the model. I restarted envoy-test and reran
  those eight. The table shows the reruns.
- **Spend:** $1.11 in all, from the shared cost log, 00:19–01:05 ET: hybrid $0.70, spark $0.41 (the rerun included).
