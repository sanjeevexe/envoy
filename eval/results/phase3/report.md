# Phase 3 evaluation: the shared memory graph on SkyLark Air

## The large test inbox: extraction and matching (no phone)

28 emails for 18 bookings (Chicago, Denver, new bookings, a second Denver trip on another date): confirmations with schema.org markup or as plain text, forwards, a seat change, a cancellation, two promotions and a receipt. 19 model calls, $0.1131.

| Measure | Result |
| --- | --- |
| Attributes extracted right (recall) | 212/214 (99%) |
| Extracted values that were right (precision) | 100% (0 wrong) |
| Markup emails (no model) | 81/81 attributes |
| Plain emails (Muse Spark) | 131/133 attributes |
| Bookings → exactly one Trip and one Flight | 18/18 |
| Trips created from promotions | 0 |
| Cancellation applied to its trip | yes |
| Two trips to Denver kept apart | yes |
| Facts traceable to a source | 100% |

| Email | Kind | Read by | Resolved as | Found | Wrong | Missing |
| --- | --- | --- | --- | --- | --- | --- |
| 000-plain-KX7Q2M | plain | model | Trip new, Flight new, Person new | 9 | 0 | 0 |
| 001-markup-PT4R8Z | markup | markup | Trip new, Flight new, Person rule | 9 | 0 | 0 |
| 002-forward-PT4R8Z | forward | model | Trip key, Flight key, Person link | 9 | 0 | 0 |
| 003-plain-8V7EN3 | plain | model | Trip new, Flight new, Person rule | 9 | 0 | 0 |
| 004-markup-UYVWMU | markup | markup | Person key, Trip new, Flight new | 9 | 0 | 0 |
| 005-plain-BQ6U0H | plain | model | Trip new, Flight new, Person rule | 8 | 0 | 1 |
| 006-markup-JQYVV3 | markup | markup | Person key, Trip new, Flight new | 9 | 0 | 0 |
| 007-forward-JQYVV3 | forward | model | Trip key, Flight key, Person link | 9 | 0 | 0 |
| 008-plain-LAJ2PW | plain | model | Trip new, Flight new, Person rule | 9 | 0 | 0 |
| 009-markup-10METT | markup | markup | Person key, Trip new, Flight new | 9 | 0 | 0 |
| 010-plain-6OUWC8 | plain | model | Trip new, Flight new, Person rule | 9 | 0 | 0 |
| 011-markup-F6LP5K | markup | markup | Person key, Trip new, Flight new | 9 | 0 | 0 |
| 012-forward-F6LP5K | forward | model | Trip key, Flight key, Person link | 9 | 0 | 0 |
| 013-plain-8UAHRB | plain | model | Trip new, Flight new, Person rule | 9 | 0 | 0 |
| 014-markup-UR32NZ | markup | markup | Person key, Trip new, Flight new | 9 | 0 | 0 |
| 015-plain-3AHVAO | plain | model | Trip new, Flight new, Person rule | 9 | 0 | 0 |
| 016-markup-1VA6V9 | markup | markup | Person key, Trip new, Flight new | 9 | 0 | 0 |
| 017-forward-1VA6V9 | forward | model | Trip key, Flight key, Person link | 9 | 0 | 0 |
| 018-plain-BVTQ5K | plain | model | Trip new, Flight new, Person rule | 8 | 0 | 1 |
| 019-markup-X1L6GD | markup | markup | Person key, Trip new, Flight new | 9 | 0 | 0 |
| 020-plain-NG1GR1 | plain | model | Trip new, Flight new, Person rule | 9 | 0 | 0 |
| 021-markup-DN7Q4X | markup | markup | Person key, Trip new, Flight new | 9 | 0 | 0 |
| 022-forward-DN7Q4X | forward | model | Trip key, Flight key, Person link | 9 | 0 | 0 |
| 023-seat-PT4R8Z | seat_change | model | Flight key | 3 | 0 | 0 |
| 024-cancel-DN7Q4X | cancellation | model | Trip key, Flight key | 2 | 0 | 0 |
| 025-promo-Chicago | promo | model | – | 0 | 0 | 0 |
| 026-promo-Phoenix | promo | model | – | 0 | 0 | 0 |
| 027-receipt | receipt | model | Order new, Item new | 2 | 0 | 0 |

## The gate's test inbox: extraction and matching (no phone)

14 emails for 7 bookings (Chicago, Denver, new bookings, a second Denver trip on another date): confirmations with schema.org markup or as plain text, forwards, a seat change, a cancellation, two promotions and a receipt. 11 model calls, $0.0539.

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

## App screens: extraction

12 SkyLark trip-details screens, each reached by the gate routine (no model) and read by Muse Spark; scored on confirmation code, destination, flight number, date, gate, seat and departure time. 12 model calls, $0.0862.

Attributes right: 82/84 (98%); precision 100%. Every fact kept the element it was read from.

| Booking | City | Found | Wrong | Missing | Facts with element evidence |
| --- | --- | --- | --- | --- | --- |
| KX7Q2M | Chicago | 6 | 0 | 1 | 13/13 |
| PT4R8Z | Denver | 7 | 0 | 0 | 14/14 |
| LRK51J | Spokane | 7 | 0 | 0 | 16/16 |
| M1W6JU | Dallas | 7 | 0 | 0 | 14/14 |
| 9RF5TP | Portland | 7 | 0 | 0 | 14/14 |
| 4VPHVZ | Louisville | 6 | 0 | 1 | 13/13 |
| TYV7EN | Sacramento | 7 | 0 | 0 | 16/16 |
| L3N6SJ | Minneapolis | 7 | 0 | 0 | 16/16 |
| 8GYFPZ | Buffalo | 7 | 0 | 0 | 14/14 |
| S4PDGI | Omaha | 7 | 0 | 0 | 16/16 |
| MQZ5ZZ | Boise | 7 | 0 | 0 | 14/14 |
| CS6BIJ | Albuquerque | 7 | 0 | 0 | 14/14 |

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

