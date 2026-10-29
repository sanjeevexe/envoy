# Three systems on SkyLark's core set

Run 1029160540 on `5fa03bf` with uncommitted changes, 2026-10-29 20:05 UTC, 16 min, standard tier. 248 model calls, $0.486 at standard prices ($0.486 billed).

Success over cells (task × seed); medians over first tries. Calls, tokens and dollars include the routine matcher's call; dollars are at standard prices.

| System | Layout | First try | Within 3 | Median calls | Median tokens | Median $ | Median s | Median steps | Interventions | Approvals | Side effects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Full agent | 0: original | 10/10 (100%) | 10/10 (100%) | 4.5 | 11987 | $0.0084 | 9.5 | 2.5 | 0 | 3 | 0 |
| Full agent | 1: moved button | 10/10 (100%) | 10/10 (100%) | 4.0 | 10562 | $0.007 | 8.8 | 2.0 | 0 | 3 | 0 |
| Full agent | 2: renamed labels | 10/10 (100%) | 10/10 (100%) | 4.0 | 10723 | $0.0073 | 9.1 | 2.0 | 0 | 2 | 0 |
| Full agent | 3: extra screen | 10/10 (100%) | 10/10 (100%) | 4.5 | 11844 | $0.008 | 11.0 | 2.5 | 0 | 2 | 0 |
| Envoy routines | 0: original | 10/10 (100%) | 10/10 (100%) | 1.0 | 1091 | $0.0021 | 4.8 | 3.0 | 0 | 2 | 0 |
| Envoy routines | 1: moved button | 10/10 (100%) | 10/10 (100%) | 1.0 | 1080 | $0.00165 | 4.8 | 3.0 | 0 | 2 | 0 |
| Envoy routines | 2: renamed labels | 10/10 (100%) | 10/10 (100%) | 1.0 | 1078 | $0.00175 | 6.2 | 3.0 | 0 | 2 | 0 |
| Envoy routines | 3: extra screen | 10/10 (100%) | 10/10 (100%) | 1.0 | 1174 | $0.002 | 5.3 | 3.0 | 0 | 2 | 0 |
