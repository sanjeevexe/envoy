# Phase 3 evaluation: the shared memory graph on SkyLark Air

## The test inbox: extraction and matching (no phone)

14 emails for 7 bookings (Chicago, Denver, four new bookings, a second Denver trip on another date): confirmations with schema.org markup or as plain text, forwards, a seat change, a cancellation, two promotions and a receipt. 11 model calls, $0.0539.

| Measure | Result |
| --- | --- |
| Attributes extracted right (recall) | 87/88 (99%) |
| Extracted values that were right (precision) | 100% (0 wrong) |
| Markup emails (no model) | 27/27 attributes |
| Plain emails (Muse Spark) | 60/61 attributes |
| Bookings → exactly one Trip and one Flight | 7/7 |
| Trips created from promotions | 0 |
| Cancellation applied to its trip | yes |
| Two trips to Denver kept apart | yes |
| Facts traceable to a source | 100% |

| Email | Kind | Read by | Resolved as | Found | Wrong | Missing |
| --- | --- | --- | --- | --- | --- | --- |
| 000-plain-KX7Q2M | plain | model | Trip new, Flight new, Person new | 9 | 0 | 0 |
| 001-markup-PT4R8Z | markup | markup | Trip new, Flight new, Person rule | 9 | 0 | 0 |
| 002-forward-PT4R8Z | forward | model | Trip key, Flight key, Person link | 9 | 0 | 0 |
| 003-plain-0Q8P5W | plain | model | Trip new, Flight new, Person rule | 9 | 0 | 0 |
| 004-markup-3J8N0D | markup | markup | Person key, Trip new, Flight new | 9 | 0 | 0 |
| 005-plain-MU10UN | plain | model | Trip new, Flight new, Person rule | 8 | 0 | 1 |
| 006-markup-U0HVOP | markup | markup | Person key, Trip new, Flight new | 9 | 0 | 0 |
| 007-forward-U0HVOP | forward | model | Trip key, Flight key, Person link | 9 | 0 | 0 |
| 008-plain-DN7Q4X | plain | model | Trip new, Flight new, Person rule | 9 | 0 | 0 |
| 009-seat-PT4R8Z | seat_change | model | Flight key | 3 | 0 | 0 |
| 010-cancel-DN7Q4X | cancellation | model | Trip key, Flight key | 2 | 0 | 0 |
| 011-promo-Chicago | promo | model | – | 0 | 0 | 0 |
| 012-promo-Phoenix | promo | model | – | 0 | 0 | 0 |
| 013-receipt | receipt | model | Order new, Item new | 2 | 0 | 0 |

## The gate on the phone

**Passed** (18/18 steps, 190.5 s). Memory at the end: {'Trip': 7, 'Flight': 7, 'Person': 1, 'Order': 1}, 144 facts, 175 events.

| Step | OK | Detail |
| --- | --- | --- |
| inbox ingested | ✅ | emails: 14; trips: 7; flights: 7 |
| app read for Chicago KX7Q2M | ✅ | inputs: {'trip_city': 'Chicago'}; input_sources: {'trip_city': 'Trip Chicago · Fri, Oct 30, 2026 (destination): email from SkyLark Air, Oct 1'}; outputs: {'gate': 'B12'}; screen_resolved: [['Trip', 'key'], ['Flight', 'key']]; routine_resolved: [['Trip', 'anchor'], ['Flight', 'anchor']]; dropped: [] |
| app read for Denver PT4R8Z | ✅ | inputs: {'trip_city': 'Denver'}; input_sources: {'trip_city': 'Trip Denver · Sat, Nov 14, 2026 (destination): email from SkyLark Air, Oct 2'}; outputs: {'gate': 'A7'}; screen_resolved: [['Trip', 'key'], ['Flight', 'key']]; routine_resolved: [['Trip', 'anchor'], ['Flight', 'anchor']]; dropped: [] |
| app read for Louisville 0Q8P5W | ✅ | inputs: {'trip_city': 'Louisville'}; input_sources: {'trip_city': 'Trip Louisville · Fri, Dec 4, 2026 (destination): email from SkyLark Air, Oct 3'}; outputs: {'gate': 'E3'}; screen_resolved: [['Trip', 'key'], ['Flight', 'key']]; routine_resolved: [['Trip', 'anchor'], ['Flight', 'anchor']]; dropped: [] |
| app read for Savannah 3J8N0D | ✅ | inputs: {'trip_city': 'Savannah'}; input_sources: {'trip_city': 'Trip Savannah · Sun, Nov 22, 2026 (destination): email from SkyLark Air, Oct 4'}; outputs: {'gate': 'C13'}; screen_resolved: [['Trip', 'key'], ['Flight', 'key']]; routine_resolved: [['Trip', 'anchor'], ['Flight', 'anchor']]; dropped: [] |
| app read for Boise MU10UN | ✅ | inputs: {'trip_city': 'Boise'}; input_sources: {'trip_city': 'Trip Boise · Wed, Nov 25, 2026 (destination): email from SkyLark Air, Oct 5'}; outputs: {'gate': 'A28'}; screen_resolved: [['Trip', 'key'], ['Flight', 'key']]; routine_resolved: [['Trip', 'anchor'], ['Flight', 'anchor']]; dropped: [] |
| app read for Tampa U0HVOP | ✅ | inputs: {'trip_city': 'Tampa'}; input_sources: {'trip_city': 'Trip Tampa · Thu, Dec 10, 2026 (destination): email from SkyLark Air, Oct 6'}; outputs: {'gate': 'E27'}; screen_resolved: [['Flight', 'key'], ['Trip', 'link']]; routine_resolved: [['Trip', 'anchor'], ['Flight', 'anchor']]; dropped: [] |
| one trip for Chicago KX7Q2M | ✅ | trips: 1; flights: 1; sources: ['app_screen', 'email'] |
| one trip for Denver PT4R8Z | ✅ | trips: 1; flights: 1; sources: ['app_screen', 'email', 'email_markup'] |
| one trip for Louisville 0Q8P5W | ✅ | trips: 1; flights: 1; sources: ['app_screen', 'email'] |
| one trip for Savannah 3J8N0D | ✅ | trips: 1; flights: 1; sources: ['app_screen', 'email_markup'] |
| one trip for Boise MU10UN | ✅ | trips: 1; flights: 1; sources: ['app_screen', 'email'] |
| one trip for Tampa U0HVOP | ✅ | trips: 1; flights: 1; sources: ['app_screen', 'email', 'email_markup'] |
| What's my gate? (from memory) | ✅ | answer: Gate B12, from the SkyLark app just now.; stale: False; supported: True |
| gate change replaces the old value | ✅ | answer: Gate C14, from the SkyLark app just now.; history: ['B12', 'C14'] |
| a 45-minute-old gate is marked stale | ✅ | answer: Gate C14, from the SkyLark app 45 minutes ago, but it may have changed.; stale_lines: 10 |
| check me in, filled from memory | ✅ | routine: skylark_check_in_flight; inputs: {'trip_city': 'Chicago'}; sources: {}; outputs: {'seat': '14C', 'gate': 'B12', 'boarding_time': '5:30 AM', 'boarding_group': 'Group 3', 'flight': 'SL 482'}; memory_seat: 14C; model_calls: 1 |
| every fact has a source | ✅ | facts: 144; traceable: 144 |

Notes the answer was given from (retrieval output):

```markdown
## Flight: SL 482 · Fri, Oct 30, 2026  [[Trip Chicago · Fri, Oct 30, 2026]]  (the next upcoming flight)
- Airline: SkyLark Air — email from SkyLark Air, Oct 1
- Number: SL 482 — SkyLark app, just now (also email from SkyLark Air, Oct 1)
- Date: Fri, Oct 30, 2026 — SkyLark app, just now (also email from SkyLark Air, Oct 1)
- From: Atlanta (ATL) — SkyLark app, just now (also email from SkyLark Air, Oct 1)
- To: Chicago (ORD) — SkyLark app, just now (also email from SkyLark Air, Oct 1)
- Departs: 6:10 AM — SkyLark app, just now (also email from SkyLark Air, Oct 1)
- Arrives: 7:25 AM — SkyLark app, just now (also email from SkyLark Air, Oct 1)
- Gate: B12 — SkyLark app (routine skylark_get_flight_gate), just now (also SkyLark app, just now)
- Seat: 14C — SkyLark app, just now (also email from SkyLark Air, Oct 1)
- Boarding: 5:30 AM — SkyLark app, just now
- Boarding group: Group 3 — SkyLark app, just now
- Status: On time — SkyLark app, just now
- Confirmation: KX7Q2M — SkyLark app, just now (also email from SkyLark Air, Oct 1)

## Trip: Chicago · Fri, Oct 30, 2026  [[Flight SL 482 · Fri, Oct 30, 2026]] [[Person Maya Patel]]  (the next upcoming trip)
- Destination: Chicago — SkyLark ap
```

