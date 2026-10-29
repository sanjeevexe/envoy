# Three systems on SkyLark's core set

Run 1029152037 on `5fa03bf` with uncommitted changes, 2026-10-29 19:20 UTC, 8 min, standard tier. 93 model calls, $0.190 at standard prices ($0.190 billed).

Success over cells (task × seed); medians over first tries. Calls, tokens and dollars include the routine matcher's call; dollars are at standard prices.

| System | Layout | First try | Within 3 | Median calls | Median tokens | Median $ | Median s | Median steps | Interventions | Approvals | Side effects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Full agent | 0: original | 10/10 (100%) | 10/10 (100%) | 4.0 | 10663 | $0.0076 | 10.9 | 2.0 | 0 | 2 | 0 |
| Full agent | 1: moved button | 4/4 (100%) | 4/4 (100%) | 7.0 | 22880 | $0.01315 | 36.0 | 5.0 | 0 | 2 | 0 |
| Envoy routines | 0: original | 10/10 (100%) | 10/10 (100%) | 1.0 | 1137 | $0.0023 | 5.6 | 3.0 | 0 | 3 | 0 |
| Envoy routines | 1: moved button | 4/4 (100%) | 4/4 (100%) | 1.0 | 1245 | $0.0024 | 8.5 | 6.0 | 0 | 3 | 0 |
