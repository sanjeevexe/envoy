# SkyLark eval: p1-fix-parse

2026-10-27T02:56:21+00:00

| Suite | Runs | Success | Median steps | Median model calls | Median time | Median cost | Total cost | Approval gate correct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | 4 | 50% | 12.0 | 15.0 | 32.765 s | $0.03065 | $0.1241 | 4/4 |
| core | 4 | 50% | 12.0 | 15.0 | 32.765 s | $0.03065 | $0.1241 | 4/4 |
| core_variant_0 | 4 | 50% | 12.0 | 15.0 | 32.765 s | $0.03065 | $0.1241 | 4/4 |

| Task | Variant | Pass | Status | Steps | Calls | Time | Cost | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| past_trip | 0 | ✅ | done | 3 | 5 | 11.82 s | $0.00699 | Tue, Mar 3, 2026 - Flight SL 1708 ATL 8:20 AM → SEA 10:55 AM |
| past_trip | 0 | ✅ | done | 2 | 4 | 8.5 s | $0.00668 | Tue, Mar 3, 2026 - Seattle trip SL 1708 ATL → SEA |
| gate_alerts | 0 | ❌ | step_limit | 21 | 26 | 53.71 s | $0.05616 | stopped after 25 steps |
| gate_alerts | 0 | ❌ | step_limit | 21 | 25 | 56.42 s | $0.05431 | stopped after 25 steps |
