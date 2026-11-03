# memory

Run 1103031455 on `eval-final`, 2026-11-03 08:14 UTC, 12 min, standard tier, the `hybrid` profile (Muse Wonder for compile, plan, repair, step; Muse Spark for the rest). 74 model calls, $0.370 at standard prices ($0.370 billed).

## Extraction

**62 labeled items: 454/468 (97%) of attributes right, 0 wrong values.**

| Set | Items | Right | Wrong | Missing |
| --- | --- | --- | --- | --- |
| Phase 3's large test inbox | 28 emails | 211/214 (99%) | 0 | 3 |
| A fresh inbox (new bookings) | 15 emails | 94/97 (97%) | 0 | 3 |
| SkyLark trip screens | 12 app screens | 76/84 (90%) | 0 | 8 |
| Screenshots (Phase 5's set) | 7 screenshots | 73/73 (100%) | 0 | 0 |

## Entity matching

| Set | Bookings → one trip and one flight | Trips from promotions | Cancellation applied | Same city kept apart | Traceable |
| --- | --- | --- | --- | --- | --- |
| Phase 3's large test inbox | 18/18 | 0 | True | True | True |
| A fresh inbox (new bookings) | 8/8 | 0 | True | n/a | True |

Screenshots merged into the trip and flight memory already knew: 7 of 7; a status lookup of another flight created no trip or flight: True; every image deleted: True.
Missing attributes: Trip.confirmation_code ×8, Trip.start_date ×6.

## Stale facts

24 answers from memory at four ages. **Stale facts served without a warning: 0 of 12.** Replaced values served as current: 0. The right value given: 24 of 24. Fresh facts given a warning anyway: 0 of 12. The memory's clock starts at 2026-10-28 09:00 (when these ages were first measured, before its flight on Oct 30) and moves forward by each age, whatever day the run is on.

| Age | Question | Stale | Warned | Answer |
| --- | --- | --- | --- | --- |
| just now | What's my gate for my Chicago flight? |  |  | Gate C14, from the SkyLark app just now. |
| just now | What seat do I have on my Chicago flight? |  |  | Seat 14C, from the SkyLark app just now. |
| just now | Is my Chicago flight on time? |  |  | Yes, on time, from the SkyLark app just now. |
| just now | When does boarding start for my Chicago flight? |  |  | Boarding starts at 5:30 AM, from the SkyLark app just now. |
| just now | How many SkyLark miles do I have? |  |  | You have 38,240 SkyLark miles, from the SkyLark app just now. |
| just now | When will my DoorDash order arrive? |  |  | 7:45 PM, from the DoorDash app just now. |
| 45 minutes later | What's my gate for my Chicago flight? | yes | yes | Gate C14, from the SkyLark app 45 minutes ago, but it may have changed. |
| 45 minutes later | What seat do I have on my Chicago flight? |  |  | Seat 14C, from the SkyLark app 45 minutes ago. |
| 45 minutes later | Is my Chicago flight on time? | yes | yes | Yes, on time from the SkyLark app 45 minutes ago, but it may have changed. |
| 45 minutes later | When does boarding start for my Chicago flight? |  |  | Boarding is 5:30 AM, from the SkyLark app 45 minutes ago. |
| 45 minutes later | How many SkyLark miles do I have? |  |  | You have 38,240 SkyLark miles, from the SkyLark app 45 minutes ago. |
| 45 minutes later | When will my DoorDash order arrive? | yes | yes | 7:45 PM from the DoorDash app 45 minutes ago, but it may have changed. |
| 8 hours later | What's my gate for my Chicago flight? | yes | yes | Gate C14, from the SkyLark app 8 hours ago, but it may have changed. |
| 8 hours later | What seat do I have on my Chicago flight? |  |  | Seat 14C, from the SkyLark app 8 hours ago. |
| 8 hours later | Is my Chicago flight on time? | yes | yes | Yes, on time from the SkyLark app 8 hours ago, but it may have changed. |
| 8 hours later | When does boarding start for my Chicago flight? | yes | yes | Boarding starts at 5:30 AM, from the SkyLark app 8 hours ago, but it may have changed. |
| 8 hours later | How many SkyLark miles do I have? |  |  | You have 38,240 SkyLark miles, from the SkyLark app 8 hours ago. |
| 8 hours later | When will my DoorDash order arrive? | yes | yes | 7:45 PM from the DoorDash app 8 hours ago, but it may have changed. |
| 10 days later | What's my gate for my Chicago flight? | yes | yes | Gate C14, from the SkyLark app 10 days ago, but it may have changed. |
| 10 days later | What seat do I have on my Chicago flight? |  |  | Seat 14C, from the SkyLark app 10 days ago. |
| 10 days later | Is my Chicago flight on time? | yes | yes | On time, from the SkyLark app 10 days ago, but it may have changed. |
| 10 days later | When does boarding start for my Chicago flight? | yes | yes | Boarding starts at 5:30 AM, from the SkyLark app 10 days ago, but it may have changed. |
| 10 days later | How many SkyLark miles do I have? | yes | yes | You have 38,240 miles, from the SkyLark app 10 days ago, but it may have changed. |
| 10 days later | When will my DoorDash order arrive? | yes | yes | 7:45 PM from the DoorDash app 10 days ago, but it may have changed. |
