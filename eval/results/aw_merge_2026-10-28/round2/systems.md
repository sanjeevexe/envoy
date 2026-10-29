# Three systems on SkyLark's core set

Run 1029000435 on `773536a` with uncommitted changes, 2026-10-29 04:04 UTC, 47 min, standard tier. 768 model calls, $1.487 at standard prices ($1.487 billed).

Success over cells (task × seed); medians over first tries. Calls, tokens and dollars include the routine matcher's call; dollars are at standard prices.

| System | Layout | First try | Within 3 | Median calls | Median tokens | Median $ | Median s | Median steps | Interventions | Approvals | Side effects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Full agent | 0: original | 30/30 (100%) | 30/30 (100%) | 4.0 | 10471 | $0.00725 | 9.1 | 2.0 | 0 | 7 | 0 |
| Full agent | 1: moved button | 30/30 (100%) | 30/30 (100%) | 4.5 | 11458 | $0.00765 | 8.6 | 2.5 | 0 | 7 | 0 |
| Full agent | 2: renamed labels | 30/30 (100%) | 30/30 (100%) | 5.0 | 12686 | $0.0081 | 9.6 | 3.0 | 0 | 7 | 0 |
| Full agent | 3: extra screen | 30/30 (100%) | 30/30 (100%) | 4.0 | 10433 | $0.0073 | 9.1 | 2.0 | 0 | 6 | 0 |
| Envoy routines | 0: original | 30/30 (100%) | 30/30 (100%) | 1.0 | 1144 | $0.00235 | 4.7 | 3.0 | 0 | 6 | 0 |
| Envoy routines | 1: moved button | 30/30 (100%) | 30/30 (100%) | 1.0 | 1098 | $0.0018 | 5.2 | 3.0 | 0 | 6 | 0 |
| Envoy routines | 2: renamed labels | 30/30 (100%) | 30/30 (100%) | 1.0 | 1104 | $0.0021 | 5.6 | 3.0 | 0 | 6 | 0 |
| Envoy routines | 3: extra screen | 30/30 (100%) | 30/30 (100%) | 1.0 | 1126 | $0.002 | 4.8 | 3.0 | 0 | 6 | 0 |
