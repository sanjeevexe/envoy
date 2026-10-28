# systems

Run 1027220657 on `ad9a67b` with uncommitted changes, 2026-10-28 02:06 UTC, 35 min, standard tier. 462 model calls, $0.884 at standard prices ($0.884 billed).

Success over cells (task × seed); medians over first tries. Calls, tokens and dollars include the routine matcher's call; dollars are at standard prices.

| System | Layout | First try | Within 3 | Median calls | Median tokens | Median $ | Median s | Median steps | Interventions | Approvals | Side effects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Full agent | 0: original | 10/10 (100%) | 10/10 (100%) | 5.0 | 11190 | $0.0081 | 10.0 | 3.0 | 0 | 2 | 0 |
| Full agent | 1: moved button | 10/10 (100%) | 10/10 (100%) | 4.5 | 9840 | $0.00705 | 10.2 | 2.5 | 0 | 2 | 0 |
| Full agent | 2: renamed labels | 10/10 (100%) | 10/10 (100%) | 4.5 | 9848 | $0.007 | 9.2 | 2.5 | 0 | 2 | 0 |
| Full agent | 3: extra screen | 10/10 (100%) | 10/10 (100%) | 6.5 | 14784 | $0.0088 | 12.0 | 4.5 | 0 | 2 | 0 |
| Fixed replay | 0: original | 2/10 (20%) | 2/10 (20%) | 0.0 | 0 | $0.0 | 2.7 | 2.5 | 0 | 0 | 9 |
| Fixed replay | 1: moved button | 5/10 (50%) | 7/10 (70%) | 0.0 | 0 | $0.0 | 2.8 | 2.5 | 0 | 3 | 0 |
| Fixed replay | 2: renamed labels | 4/10 (40%) | 4/10 (40%) | 0.0 | 0 | $0.0 | 2.7 | 2.5 | 0 | 1 | 6 |
| Fixed replay | 3: extra screen | 3/10 (30%) | 4/10 (40%) | 0.0 | 0 | $0.0 | 2.5 | 2.5 | 0 | 2 | 6 |
| Envoy routines | 0: original | 10/10 (100%) | 10/10 (100%) | 1.0 | 976 | $0.00225 | 4.8 | 3.0 | 0 | 2 | 0 |
| Envoy routines | 1: moved button | 10/10 (100%) | 10/10 (100%) | 1.0 | 956 | $0.00175 | 5.7 | 3.0 | 0 | 2 | 0 |
| Envoy routines | 2: renamed labels | 10/10 (100%) | 10/10 (100%) | 1.0 | 959 | $0.00175 | 6.0 | 3.0 | 0 | 2 | 0 |
| Envoy routines | 3: extra screen | 10/10 (100%) | 10/10 (100%) | 1.0 | 1020 | $0.002 | 5.2 | 3.0 | 0 | 2 | 0 |

Failed tries, by kind (layouts and tries counted):

| System | Task | What went wrong | Tries | Layouts |
| --- | --- | --- | --- | --- |
| Fixed replay | add_ktn | acted on another booking | 9 | 0, 2, 3 |
| Fixed replay | change_seat | acted on another booking | 9 | 0, 2, 3 |
| Fixed replay | check_in | acted on another booking | 3 | 0 |
| Fixed replay | check_in | step_limit | 3 | 1, 3 |
| Fixed replay | find_trip | wrong answer | 12 | 0, 1, 2, 3 |
| Fixed replay | flight_status | wrong answer | 9 | 0, 2, 3 |
| Fixed replay | gate | wrong answer | 12 | 0, 1, 2, 3 |
| Fixed replay | past_trip | wrong answer | 4 | 0, 1 |
| Fixed replay | seat | wrong answer | 12 | 0, 1, 2, 3 |
