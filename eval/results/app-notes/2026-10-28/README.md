# App notes: before and after

Same tasks, same agent and profile; the only difference is the notes Envoy wrote itself during a warm-up on other tasks in the same app. Small samples (6 and 3 tasks), one run each: read the per-task rows, not just the totals.

## real

Profile `spark`, standard tier, agent only (no routines, no memory notes about the user).

| Pass | Success | Mean steps | Mean model calls | Mean seconds | Cost |
| --- | --- | --- | --- | --- | --- |
| cold | 3/3 | 5.33 | 7.33 | 23.2 | $0.039 |
| warmup | 3/3 | 7.33 | 9.67 | 30.3 | $0.046 |
| warm | 3/3 | 5.67 | 7.67 | 20.1 | $0.038 |

| Task | Cold | Warm | Steps cold → warm | Notes used (warm) |
| --- | --- | --- | --- | --- |
| sb_mocha | ok (done) | ok (done) | 7 → 7 | 3 |
| dd_pizza | ok (done) | ok (done) | 2 → 3 | 2 |
| sb_flat_white | ok (done) | ok (done) | 7 → 7 | 3 |

Notes Envoy wrote in the warm-up (its own words, after its filter):

- The drink detail screen shows calories for the selected size. (seen 2×)
- Use Search Menu in Order to find a drink by name. (seen 2×)
- To browse without choosing a store, tap Skip then Yes on the skip confirmation dialog. (seen 2×)
- The first restaurant result can be a Sponsored listing. (seen 1×)
- Tapping a recent search term below the search bar runs that query. (seen 1×)
