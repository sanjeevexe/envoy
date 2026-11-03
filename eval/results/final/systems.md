# systems

Run 1103002528 on `eval-final`, 2026-11-03 05:25 UTC, 102 min, standard tier, the `hybrid` profile (Muse Wonder for compile, plan, repair, step; Muse Spark for the rest). 893 model calls, $5.877 at standard prices ($5.877 billed).

Success over cells (task × seed); medians over first tries. Calls, tokens and dollars include the routine matcher's call; dollars are at standard prices.

| System | Layout | First try | Within 3 | Median calls | Median tokens | Median $ | Median s | Median steps | Interventions | Approvals | Side effects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Full agent | 0: original | 29/30 (97%) | 30/30 (100%) | 4.5 | 8703 | $0.0321 | 19.2 | 2.5 | 0 | 9 | 0 |
| Full agent | 1: moved button | 30/30 (100%) | 30/30 (100%) | 5.0 | 9636 | $0.0337 | 18.2 | 3.0 | 0 | 10 | 0 |
| Full agent | 2: renamed labels | 30/30 (100%) | 30/30 (100%) | 4.5 | 8690 | $0.03305 | 17.8 | 2.5 | 0 | 9 | 0 |
| Full agent | 3: extra screen | 30/30 (100%) | 30/30 (100%) | 5.0 | 9440 | $0.03195 | 17.1 | 3.0 | 0 | 11 | 0 |
| Fixed replay | 0: original | 6/30 (20%) | 6/30 (20%) | 0.0 | 0 | $0.0 | 3.5 | 3.0 | 0 | 0 | 9 |
| Fixed replay | 1: moved button | 17/30 (57%) | 18/30 (60%) | 0.0 | 0 | $0.0 | 4.8 | 3.5 | 0 | 7 | 0 |
| Fixed replay | 2: renamed labels | 6/30 (20%) | 6/30 (20%) | 0.0 | 0 | $0.0 | 3.5 | 3.0 | 0 | 0 | 9 |
| Fixed replay | 3: extra screen | 9/30 (30%) | 9/30 (30%) | 0.0 | 0 | $0.0 | 3.4 | 3.0 | 0 | 4 | 6 |
| Envoy routines | 0: original | 30/30 (100%) | 30/30 (100%) | 1.0 | 1098 | $0.0021 | 8.9 | 3.0 | 0 | 12 | 0 |
| Envoy routines | 1: moved button | 30/30 (100%) | 30/30 (100%) | 1.0 | 1100 | $0.00215 | 8.5 | 3.0 | 0 | 12 | 0 |
| Envoy routines | 2: renamed labels | 30/30 (100%) | 30/30 (100%) | 1.0 | 1136 | $0.0023 | 7.2 | 3.0 | 0 | 12 | 0 |
| Envoy routines | 3: extra screen | 30/30 (100%) | 30/30 (100%) | 1.0 | 1145 | $0.0023 | 6.9 | 3.0 | 0 | 12 | 0 |

Failed tries, by kind (layouts and tries counted):

| System | Task | What went wrong | Tries | Layouts |
| --- | --- | --- | --- | --- |
| Fixed replay | add_ktn | acted on another booking | 9 | 0, 2, 3 |
| Fixed replay | change_seat | acted on another booking | 9 | 0, 2, 3 |
| Fixed replay | check_in | acted on another booking | 6 | 0, 2 |
| Fixed replay | find_trip | wrong answer | 12 | 0, 1, 2, 3 |
| Fixed replay | flight_status | wrong answer | 10 | 0, 1, 2, 3 |
| Fixed replay | gate | wrong answer | 12 | 0, 1, 2, 3 |
| Fixed replay | past_trip | wrong answer | 12 | 0, 1, 2, 3 |
| Fixed replay | seat | wrong answer | 12 | 0, 1, 2, 3 |
| Full agent | flight_status | wrong answer | 1 | 0 |
