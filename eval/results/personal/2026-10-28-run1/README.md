# Personal-tasks benchmark: run1

We wrote these tasks ourselves, for our own product, so this is **not a neutral benchmark**. Several are meant to be hard.

- Date: 2026-10-29 02:05 UTC; branch `claude/wonder-appnotes` at `25073f5`; profile `spark`; app notes on
- Phones: envoy-test, envoy-real; envoy-real for S4 and C2 (22:04); envoy-test for the SkyLark tasks later; C1, C3, C4 when both phones are free
- App notes at the start: 5, written by Envoy itself in step 2b's warm-up tasks (different tasks in the same apps): com.dd.doordash 2, com.starbucks.mobilecard 3
- Model calls: 9, $0.028 (this checkout's cost log, standard tier for real apps)

**Score: 2/2 graded** (18 not run or skipped)

| Category | Passed |
| --- | --- |
| single | 1/1 (3 skipped) |
| cross | 1/1 (3 skipped) |
| memory | 0/0 (4 skipped) |
| repeat | 0/0 (4 skipped) |
| safety | 0/0 (3 skipped) |
| proactive | 0/0 (1 skipped) |

| Task | Category | Result | Why | Route | Phone calls | Calls | Cost | Wall s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M1 | memory | not run | | | | | | |
| M2 | memory | not run | | | | | | |
| M4 | memory | not run | | | | | | |
| M3 | memory | not run | | | | | | |
| S1 | single | not run | | | | | | |
| S2 | single | not run | | | | | | |
| S3 | single | not run | | | | | | |
| S4 | single | pass | ok | task | 0 | 3 | $0.009 | 18.4 |
| C1 | cross | not run | | | | | | |
| C2 | cross | pass | ok | task | 0 | 6 | $0.019 | 35.1 |
| C3 | cross | not run | | | | | | |
| C4 | cross | not run | | | | | | |
| R1 | repeat | not run | | | | | | |
| R2 | repeat | not run | | | | | | |
| R3 | repeat | not run | | | | | | |
| R4 | repeat | not run | | | | | | |
| P1 | safety | not run | | | | | | |
| P2 | safety | not run | | | | | | |
| P3 | safety | not run | | | | | | |
| P4 | proactive | not run | | | | | | |

## Answers

- **S4** How many calories are in a Caffè Latte at Starbucks? → calories: 190 calories
- **C2** How many calories are in a Caffè Latte at Starbucks, and what's the first place DoorDash shows for a latte? → A Caffè Latte at Starbucks has 190 calories, and the first place DoorDash shows for a latte is Coupa Cafe.
