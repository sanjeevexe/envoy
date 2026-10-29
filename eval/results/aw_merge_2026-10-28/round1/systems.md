# Three systems on SkyLark's core set

Run 1028211901 on `2ecbbbf` with uncommitted changes, 2026-10-29 01:19 UTC, 54 min, standard tier. 998 model calls, $1.870 at standard prices ($1.870 billed).

Success over cells (task × seed); medians over first tries. Calls, tokens and dollars include the routine matcher's call; dollars are at standard prices.

| System | Layout | First try | Within 3 | Median calls | Median tokens | Median $ | Median s | Median steps | Interventions | Approvals | Side effects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Full agent | 0: original | 30/30 (100%) | 30/30 (100%) | 4.0 | 10040 | $0.0074 | 8.6 | 2.0 | 0 | 6 | 0 |
| Full agent | 1: moved button | 30/30 (100%) | 30/30 (100%) | 4.0 | 9996 | $0.00785 | 8.6 | 2.0 | 0 | 7 | 0 |
| Full agent | 2: renamed labels | 30/30 (100%) | 30/30 (100%) | 4.5 | 11072 | $0.0074 | 9.8 | 2.5 | 0 | 7 | 0 |
| Full agent | 3: extra screen | 30/30 (100%) | 30/30 (100%) | 4.0 | 10042 | $0.0072 | 9.1 | 2.0 | 0 | 7 | 0 |
| Envoy routines | 0: original | 28/30 (93%) | 30/30 (100%) | 1.0 | 1052 | $0.00255 | 5.8 | 3.0 | 0 | 12 | 3 |
| Envoy routines | 1: moved button | 30/30 (100%) | 30/30 (100%) | 1.0 | 1045 | $0.0024 | 5.9 | 3.0 | 0 | 7 | 0 |
| Envoy routines | 2: renamed labels | 30/30 (100%) | 30/30 (100%) | 1.0 | 1060 | $0.0025 | 6.3 | 3.0 | 0 | 6 | 0 |
| Envoy routines | 3: extra screen | 30/30 (100%) | 30/30 (100%) | 1.0 | 1094 | $0.00255 | 5.6 | 3.0 | 0 | 7 | 0 |

Failed tries, by kind (layouts and tries counted):

| System | Task | What went wrong | Tries | Layouts |
| --- | --- | --- | --- | --- |
| Envoy routines | check_in | acted on another booking | 3 | 0 |
