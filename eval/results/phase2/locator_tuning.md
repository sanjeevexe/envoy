# Locator threshold tuning (SkyLark, all four layouts)

7760 cases: 24 routine locators × recorded screens that contain their element, each scored with and without resource IDs. Right = the true element wins (score ≥ threshold and ahead of the runner-up by the margin); wrong = another element wins.

**Chosen:** STRICT 0.8, RELAXED 0.6, MARGIN 0.08 (no wrong element wins at either threshold, then most right answers).

In use: STRICT 0.8, RELAXED 0.6, MARGIN 0.08.

### Chosen thresholds (0.8 / 0.6 / 0.08)

| Role | IDs | Variant | Positive cases | Right at strict | Right at strict or relaxed | Hard negatives | Wrong element at strict | Wrong element at relaxed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| check | ids | 0 | 831 | 100% | 100% | 1507 | 0 | 0 |
| check | ids | 1 | 101 | 100% | 100% | 175 | 0 | 0 |
| check | ids | 2 | 128 | 79% | 95% | 211 | 0 | 0 |
| check | ids | 3 | 98 | 100% | 100% | 179 | 0 | 0 |
| check | no-ids | 0 | 468 | 100% | 100% | 1507 | 88 | 92 |
| check | no-ids | 1 | 56 | 100% | 100% | 175 | 0 | 0 |
| check | no-ids | 2 | 73 | 62% | 90% | 211 | 0 | 0 |
| check | no-ids | 3 | 53 | 100% | 100% | 179 | 10 | 10 |
| target | ids | 0 | 657 | 100% | 100% | 2 | 0 | 0 |
| target | ids | 1 | 79 | 95% | 100% | 0 | 0 | 0 |
| target | ids | 2 | 95 | 76% | 100% | 0 | 0 | 0 |
| target | ids | 3 | 71 | 100% | 100% | 0 | 0 | 0 |
| target | no-ids | 0 | 657 | 100% | 100% | 2 | 0 | 2 |
| target | no-ids | 1 | 79 | 95% | 100% | 0 | 0 | 0 |
| target | no-ids | 2 | 95 | 36% | 76% | 0 | 0 | 0 |
| target | no-ids | 3 | 71 | 100% | 100% | 0 | 0 | 0 |

### Hardest cases without IDs (true element below the relaxed threshold)

- skylark_air_check_in_flight:start_check_in:check3 (variant 2): true 0.00, best wrong 0.00
- skylark_air_check_in_flight:start_check_in:check3 (variant 2): true 0.00, best wrong 0.00
- skylark_air_check_in_flight:start_check_in:check3 (variant 2): true 0.00, best wrong 0.00
- skylark_air_check_in_flight:start_check_in:check3 (variant 2): true 0.00, best wrong 0.00
- skylark_air_check_in_flight:start_check_in:check3 (variant 2): true 0.00, best wrong 0.00
- skylark_air_check_in_flight:start_check_in:check3 (variant 2): true 0.00, best wrong 0.00
- skylark_air_check_in_flight:start_check_in:check3 (variant 2): true 0.00, best wrong 0.00
- skylark_change_seat:open_change_seat:target (variant 2): true 0.51, best wrong 0.53
- skylark_change_seat:open_change_seat:target (variant 2): true 0.52, best wrong 0.53
- skylark_change_seat:open_change_seat:target (variant 2): true 0.52, best wrong 0.53
- skylark_change_seat:open_change_seat:target (variant 2): true 0.52, best wrong 0.53
- skylark_change_seat:open_change_seat:target (variant 2): true 0.52, best wrong 0.53
