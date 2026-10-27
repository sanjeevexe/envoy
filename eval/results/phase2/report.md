# Phase 2 evaluation: app routines on SkyLark Air

## Source runs (the full agent, once per routine family, on the Denver booking)

| Family | Passed | Steps | Model calls | Time | Cost |
| --- | --- | --- | --- | --- | --- |
| check_in | ✅ | 8 | 10 | 19.2 s | $0.0183 |
| change_seat | ✅ | 5 | 8 | 14.75 s | $0.0216 |
| add_ktn | ✅ | 4 | 6 | 11.73 s | $0.0096 |
| gate | ✅ | 2 | 4 | 7.27 s | $0.0065 |
| flight_status | ✅ | 3 | 5 | 8.78 s | $0.0075 |
| find_trip | ✅ | 2 | 4 | 7.43 s | $0.0073 |

## Compiling

### Compiled on the original layout

| Family | Routine | Steps | Inputs | Outputs | Trace steps dropped | Compiler | Compile cost | Verified (same / second inputs) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| check_in | `skylark_air_check_in_flight` | 9 | trip_city | seat, gate, boarding_time | 0 | cached | $0.066 | ✅ / ✅ |
| change_seat | `skylark_change_seat` | 7 | trip_city, desired_seat | seat | 1 | cached | $0.048 | ✅ / ✅ |
| add_ktn | `skylark_add_known_traveler_number` | 5 | trip_city, user_known_traveler_number | known_traveler_number, confirmation_code | 0 | cached | $0.069 | ✅ / ✅ |
| gate | `skylark_get_flight_gate` | 3 | trip_city | gate | 0 | cached | $0.038 | ✅ / ✅ |
| flight_status | `skylark_check_flight_status` | 3 | flight_number | flight_status, route, date, gate, departure_time | 0 | cached | $0.046 | ✅ / ✅ |
| find_trip | `skylark_lookup_trip_destination` | 3 | trip_confirmation_code | destination | 0 | cached | $0.052 | ✅ / ✅ |
| check_in_next | `skylark_check_in_flight` | 6 | trip_city | seat, gate, boarding_time, boarding_group, flight | 0 | cached | $0.000 | ✅ |

### Compiled with IDs hidden (variant 4)

| Family | Routine | Steps | Inputs | Outputs | Trace steps dropped | Compiler | Compile cost | Verified (same / second inputs) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| check_in | `skylark_check_in_flight` | 9 | trip_city |  | 1 | cached | $0.062 | ✅ / ✅ |
| change_seat | `skylark_change_seat` | 7 | trip_city, desired_seat | seat, flight_number | 1 | cached | $0.043 | ✅ / ✅ |
| add_ktn | `skylark_add_known_traveler_number` | 5 | trip_city, user_known_traveler_number | known_traveler_number, save_confirmation | 1 | cached | $0.050 | ✅ / ✅ |
| gate | `skylark_get_gate` | 3 | trip_city |  | 0 | cached | $0.043 | ❌ all steps and checks passed / ❌ all steps and checks passed |
| flight_status | `skylark_check_flight_status` | 3 | flight_number | flight_status_summary | 0 | cached | $0.047 | ✅ / ✅ |
| find_trip | `skylark_lookup_trip_destination` | 3 | confirmation_code | destination | 0 | cached | $0.051 | ✅ / ✅ |

### Compiled on the extra-screen layout (variant 3)

| Family | Routine | Steps | Inputs | Outputs | Trace steps dropped | Compiler | Compile cost | Verified (same / second inputs) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| check_in | `skylark_check_in_flight` | 14 | trip_city | check_in_status, seat, gate, boarding_time, boarding_group | 0 | muse-wonder-1.0 | $0.055 | ✅ / ✅ |

## Routines on bookings they have never seen

### Original layout

| Family | Runs | Success | Model calls (total) | Median time | Max time |
| --- | --- | --- | --- | --- | --- |
| check_in | 5 | 5/5 (100%) | 0 | 3.77 s | 5.19 s |
| change_seat | 5 | 5/5 (100%) | 0 | 4.02 s | 5.51 s |
| add_ktn | 5 | 5/5 (100%) | 0 | 3.24 s | 4.58 s |
| gate | 5 | 5/5 (100%) | 0 | 1.64 s | 3.19 s |
| flight_status | 5 | 5/5 (100%) | 0 | 2.22 s | 2.37 s |
| find_trip | 5 | 5/5 (100%) | 0 | 1.61 s | 3.16 s |
| **all** | 30 | **30/30 (100%)** | 0 | 3.14 s | 5.51 s |

## Injected UI changes

Each experiment: (1) the compiled routine meets the changed layout on a new booking, with repair and the agent allowed; (2) any patches become a trial version, replayed at once from a reset snapshot on another new booking with no repair and no agent allowed; it becomes active if it passes, else it is rejected (rollback); (3) the active version runs on a third booking (does it now need no model?); (4) a patched version runs on the original layout.

### Routines compiled on the original layout

| Change | Experiments | Recovered | Saved by (highest rung) | Model calls | Median time | Cost | Patches | Trial passed | Patched version alone (0 model calls) | Still works on the original layout |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1: moved button | 6 | 6/6 (100%) | none needed ×6 | 0 | 2.85 s | $0.0000 | – | – | – | – |
| 2: renamed labels | 6 | 6/6 (100%) | relaxed match ×6 | 0 | 3.5 s | $0.0000 | check ×13, locator ×3 | 6/6 (100%) | 6/6 (100%) | 6/6 (100%) |
| 3: extra screen | 6 | 6/6 (100%) | none needed ×5, local repair ×1 | 1 | 2.75 s | $0.0061 | insert_after ×1 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) |

Per experiment:

| Routine | Change | First run | Rung | Calls | Time | Patches | Trial | Next run | Original layout |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| check_in | 1 | ✅ done | 0 | 0 | 3.69 s | – | – | ✅ 0 calls, rung 0 | – |
| check_in | 2 | ✅ done | 2 | 0 | 7.42 s | step 'open_my_trips': after-check 1 matched only relaxed; updated to {text='Trips', resour; step 'open_my_trips': after-check 2 matched only relaxed; updated to {text='Trips', resour; step 'start_check_in': after-check 2 matched only relaxed; updated to {text='Next', resour; step 'continue_after_passenger': target found only by relaxed match; locator updated to {t; step 'continue_after_hazmat': target found only by relaxed match; locator updated to {text | ✅ v2 | ✅ 0 calls, rung 0 | ✅ |
| check_in | 3 | ✅ done | 4 | 1 | 12.72 s | after 'continue_after_hazmat', an extra screen appeared; inserted continue_after_hazmat_ex | ✅ v2 | ✅ 0 calls, rung 0 | ✅ |
| change_seat | 1 | ✅ done | 0 | 0 | 4.11 s | – | – | ✅ 0 calls, rung 0 | – |
| change_seat | 2 | ✅ done | 2 | 0 | 5.85 s | step 'open_my_trips': after-check 1 matched only relaxed; updated to {text='Trips', resour; step 'open_my_trips': after-check 2 matched only relaxed; updated to {text='Trips', resour; step 'open_change_seat': target found only by relaxed match; locator updated to {text='Sea | ✅ v2 | ✅ 0 calls, rung 0 | ✅ |
| change_seat | 3 | ✅ done | 0 | 0 | 5.85 s | – | – | ✅ 0 calls, rung 0 | – |
| add_ktn | 1 | ✅ done | 0 | 0 | 3.18 s | – | – | ✅ 0 calls, rung 0 | – |
| add_ktn | 2 | ✅ done | 2 | 0 | 3.91 s | step 'open_my_trips': after-check 1 matched only relaxed; updated to {text='Trips', resour; step 'open_my_trips': after-check 2 matched only relaxed; updated to {text='Trips', resour | ✅ v2 | ✅ 0 calls, rung 0 | ✅ |
| add_ktn | 3 | ✅ done | 0 | 0 | 3.19 s | – | – | ✅ 0 calls, rung 0 | – |
| gate | 1 | ✅ done | 0 | 0 | 1.6 s | – | – | ✅ 0 calls, rung 0 | – |
| gate | 2 | ✅ done | 2 | 0 | 2.47 s | step 'tap_my_trips': after-check 1 matched only relaxed; updated to {text='Trips', resourc; step 'tap_my_trips': after-check 2 matched only relaxed; updated to {text='Trips', resourc | ✅ v2 | ✅ 0 calls, rung 0 | ✅ |
| gate | 3 | ✅ done | 0 | 0 | 1.58 s | – | – | ✅ 0 calls, rung 0 | – |
| flight_status | 1 | ✅ done | 0 | 0 | 2.52 s | – | – | ✅ 0 calls, rung 0 | – |
| flight_status | 2 | ✅ done | 2 | 0 | 3.08 s | step 'tap_flight_status': after-check 1 matched only relaxed; updated to {text='Status', r; step 'tap_flight_status': after-check 2 matched only relaxed; updated to {text='Status', r | ✅ v2 | ✅ 0 calls, rung 0 | ✅ |
| flight_status | 3 | ✅ done | 0 | 0 | 2.31 s | – | – | ✅ 0 calls, rung 0 | – |
| find_trip | 1 | ✅ done | 0 | 0 | 1.61 s | – | – | ✅ 0 calls, rung 0 | – |
| find_trip | 2 | ✅ done | 2 | 0 | 2.49 s | step 'tap_my_trips': after-check 1 matched only relaxed; updated to {text='Trips', resourc; step 'tap_my_trips': after-check 2 matched only relaxed; updated to {text='Trips', resourc | ✅ v2 | ✅ 0 calls, rung 0 | ✅ |
| find_trip | 3 | ✅ done | 0 | 0 | 1.63 s | – | – | ✅ 0 calls, rung 0 | – |

## Three systems compared

### Three systems on the same requests

Each cell is one request per routine family on a booking none of the systems was built from (6 families). Full agent: plan + one model call per step. Fixed replay: the recorded taps at their coordinates with the recorded text, a screen-similarity check before each, and the full agent on a mismatch (like Mobilerun macros). Envoy routine: the compiled routine with its checks and fallback ladder (first run on the changed layout, before any patch).

| Layout | System | Success | Median model calls | Median time | Median cost (standard prices) | Wrong-booking or wrong-answer runs |
| --- | --- | --- | --- | --- | --- | --- |
| 0: original | Full agent | 6/6 (100%) | 5.5 | 12.05 s | $0.0100 | 0 |
| 0: original | Fixed replay | 0/3 (0%) | 0 | 3.93 s | $0.0000 | 3 |
| 0: original | Envoy routine | 6/6 (100%) | 0.0 | 2.73 s | $0.0000 | 0 |
| 1: moved button | Full agent | 6/6 (100%) | 6.0 | 12.84 s | $0.0100 | 0 |
| 1: moved button | Fixed replay | 2/3 (67%) | 9 | 19.65 s | $0.0200 | 1 |
| 1: moved button | Envoy routine | 6/6 (100%) | 0.0 | 2.85 s | $0.0000 | 0 |
| 2: renamed labels | Full agent | 6/6 (100%) | 5.5 | 11.69 s | $0.0100 | 0 |
| 2: renamed labels | Fixed replay | 0/3 (0%) | 0 | 3.96 s | $0.0000 | 3 |
| 2: renamed labels | Envoy routine | 6/6 (100%) | 0.0 | 3.5 s | $0.0000 | 0 |
| 3: extra screen | Full agent | 6/6 (100%) | 5.5 | 10.67 s | $0.0100 | 0 |
| 3: extra screen | Fixed replay | 1/3 (33%) | 0 | 4.0 s | $0.0000 | 2 |
| 3: extra screen | Envoy routine | 6/6 (100%) | 0.0 | 2.75 s | $0.0000 | 0 |

Across these cells, routines used **1 model calls against 159 for the full agent (99% fewer)**, with a median of 3.08 s against 11.25 s.

## Real-app checkpoint (envoy-real, read-only)

| App | Agent run | Compiled | Rerun (inputs) | Without repair | With repair allowed |
| --- | --- | --- | --- | --- | --- |
| target | handoff · 3 steps · 4 calls · 19.12 s · $0.0074 | no: run ended 'handoff' with check None; only verified runs are  | – | – | – |
| chipotle | done · 14 steps · 18 calls · 47.44 s · $0.0308 | 11 steps, inputs zip_code, outputs price | same-inputs {'zip_code': '10001'} | ❌ failed, rung 1, 0 calls, 11.83 s: step select_zip_code_suggestion: target not found: no match (best 0.98 | ❌ failed, rung 4, 3 calls, 57.02 s: step scroll_to_chips_and_sides: after-checks failed: no match (best 0. |
| amazon | done · 2 steps · 4 calls · 23.01 s · $0.0102 | 2 steps, inputs search_query, outputs first_result_price | same-inputs {'search_query': 'AA batteries'} | ✅ done, rung 1, 0 calls, 8.9 s | not needed |
| amazon |  |  | second-input {'search_query': 'USB-C cable'} | ✅ done, rung 1, 0 calls, 9.46 s | not needed |
| doordash | failed · 19 steps · 24 calls · 73.34 s · $0.0494 | no: run ended 'failed' with check None; only verified runs are c | – | – | – |
| starbucks | – | 8 steps, inputs drink_name, outputs calories | same-inputs {'drink_name': 'Caffe Latte'} | ✅ done, rung 1, 0 calls, 9.14 s | not needed |
| starbucks |  |  | second-input {'drink_name': 'Caramel Macchiato'} | ✅ done, rung 1, 0 calls, 9.24 s | not needed |

## Matching requests to routines

12/12 correct (routine and every input right, or no routine when none fits); 12 model calls, $0.0327 at standard prices.

| Request | Expected | Matched | Inputs | Correct |
| --- | --- | --- | --- | --- |
| Check me in for my Denver flight | skylark_air_check_in_flight | skylark_air_check_in_flight | {'trip_city': 'Denver'} | ✅ |
| I need to check in for my trip to Tampa | skylark_air_check_in_flight | skylark_air_check_in_flight | {'trip_city': 'Tampa'} | ✅ |
| Check me in | skylark_air_check_in_flight or skylark_check_in_flight | skylark_check_in_flight | {'trip_city': 'Chicago'} | ✅ |
| Move me to seat 21C on the Denver flight | skylark_change_seat | skylark_change_seat | {'trip_city': 'Denver', 'desired_seat': '21C'} | ✅ |
| Change my seat to 22A | skylark_change_seat | skylark_change_seat | {'trip_city': 'Tampa', 'desired_seat': '22A'} | ✅ |
| Add my TSA PreCheck number to my Tampa trip | skylark_add_known_traveler_number | skylark_add_known_traveler_number | {'trip_city': 'Tampa', 'user_known_traveler_number': '55501234'} | ✅ |
| Which gate is my Boise flight at? | skylark_get_flight_gate | skylark_get_flight_gate | {'trip_city': 'Boise'} | ✅ |
| Is SL 1190 on time? | skylark_check_flight_status | skylark_check_flight_status | {'flight_number': 'SL 1190'} | ✅ |
| Where does trip PT4R8Z go? | skylark_lookup_trip_destination | skylark_lookup_trip_destination | {'trip_confirmation_code': 'PT4R8Z'} | ✅ |
| Cancel my Denver trip | (none) | (none) | {} | ✅ |
| What seat am I in on my Denver flight? | (none) | (none) | {} | ✅ |
| How many SkyLark miles do I have? | (none) | (none) | {} | ✅ |

