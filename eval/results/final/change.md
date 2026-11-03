# change

Run 1103022306 on `eval-final`, 2026-11-03 07:23 UTC, 32 min, standard tier, the `hybrid` profile (Muse Wonder for compile, plan, repair, step; Muse Spark for the rest). 52 model calls, $1.037 at standard prices ($1.037 billed).

## New inputs

| Task | Runs | Passed | No model call | Median s |
| --- | --- | --- | --- | --- |
| check_in | 5 | 5 | 5 | 4.3 |
| change_seat | 5 | 5 | 5 | 6.7 |
| add_ktn | 5 | 5 | 5 | 3.5 |
| gate | 5 | 5 | 5 | 1.8 |
| seat | 5 | 5 | 5 | 1.8 |
| flight_status | 5 | 5 | 5 | 2.5 |
| miles | 5 | 5 | 5 | 0.7 |
| find_trip | 5 | 5 | 5 | 4.2 |
| past_trip | 5 | 5 | 5 | 3.0 |
| gate_alerts | 5 | 5 | 5 | 1.4 |
| **All** | 50 | **50** | 50 | 3.0 |

## Injected UI changes

First: the compiled routine meets the changed layout (repair and the agent allowed). Trial: its patches as a new version, no repair or agent. After: the active version on another booking. Back: the patched version on the original layout.

| Layout | Experiments | Recovered | Saved by | Model calls (first) | Patched | Trial passed | After, no model call | Back on original |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1: moved button | 10 | **10/10** | nothing needed ×10 | 0 | 0 | 0/0 | 10/10 | 0/0 |
| 2: renamed labels | 10 | **10/10** | relaxed match or scroll ×8, nothing needed ×2 | 0 | 8 | 8/8 | 10/10 | 8/8 |
| 3: extra screen | 10 | **10/10** | nothing needed ×9, local repair ×1 | 1 | 1 | 1/1 | 10/10 | 1/1 |
| 4: hidden IDs | 10 | **10/10** | relaxed match or scroll ×4, nothing needed ×4, the agent ×2 | 12 | 0 | 0/0 | 8/10 | 0/0 |
| 5: renamed labels + hidden IDs | 10 | **10/10** | relaxed match or scroll ×5, the agent ×2, nothing needed ×2, local repair ×1 | 14 | 8 | 6/8 | 8/10 | 6/6 |
