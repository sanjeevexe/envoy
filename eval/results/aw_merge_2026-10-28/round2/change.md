# Routines under change

Run 1029010829 on `773536a` with uncommitted changes, 2026-10-29 05:08 UTC, 22 min, standard tier. 4 model calls, $0.019 at standard prices ($0.019 billed).

## New inputs

| Task | Runs | Passed | No model call | Median s |
| --- | --- | --- | --- | --- |
| check_in | 5 | 5 | 5 | 4.2 |
| change_seat | 5 | 5 | 5 | 6.2 |
| add_ktn | 5 | 5 | 5 | 3.4 |
| gate | 5 | 5 | 5 | 1.7 |
| seat | 5 | 5 | 5 | 1.8 |
| flight_status | 5 | 5 | 5 | 2.4 |
| miles | 5 | 5 | 5 | 0.7 |
| find_trip | 5 | 5 | 5 | 1.8 |
| past_trip | 5 | 5 | 5 | 3.3 |
| gate_alerts | 5 | 5 | 5 | 1.4 |
| **All** | 50 | **50** | 50 | 2.4 |

## Injected UI changes

First: the compiled routine meets the changed layout (repair and the agent allowed). Trial: its patches as a new version, no repair or agent. After: the active version on another booking. Back: the patched version on the original layout.

| Layout | Experiments | Recovered | Saved by | Model calls (first) | Patched | Trial passed | After, no model call | Back on original |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1: moved button | 10 | **10/10** | nothing needed ×10 | 0 | 0 | 0/0 | 10/10 | 0/0 |
| 2: renamed labels | 10 | **10/10** | relaxed match or scroll ×8, nothing needed ×2 | 0 | 8 | 8/8 | 10/10 | 8/8 |
| 3: extra screen | 10 | **10/10** | nothing needed ×9, local repair ×1 | 1 | 1 | 1/1 | 10/10 | 1/1 |
| 4: hidden IDs | 10 | **10/10** | relaxed match or scroll ×7, nothing needed ×3 | 0 | 0 | 0/0 | 10/10 | 0/0 |
| 5: renamed labels + hidden IDs | 10 | **10/10** | relaxed match or scroll ×6, local repair ×2, nothing needed ×2 | 3 | 8 | 8/8 | 10/10 | 8/8 |
