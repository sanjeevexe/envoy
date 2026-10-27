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
| check_in | `skylark_air_check_in_flight` | 9 | trip_city | seat, gate, boarding_time | 0 | muse-wonder-1.0 (cached answer) | $0.066 | ✅ / ✅ |
| change_seat | `skylark_change_seat` | 7 | trip_city, desired_seat | seat | 1 | muse-wonder-1.0 (cached answer) | $0.048 | ✅ / ✅ |
| add_ktn | `skylark_add_known_traveler_number` | 5 | trip_city, user_known_traveler_number | known_traveler_number, confirmation_code | 0 | muse-wonder-1.0 (cached answer) | $0.069 | ✅ / ✅ |
| gate | `skylark_get_flight_gate` | 3 | trip_city | gate | 0 | muse-wonder-1.0 (cached answer) | $0.038 | ✅ / ✅ |
| flight_status | `skylark_check_flight_status` | 3 | flight_number | flight_status, route, date, gate, departure_time | 0 | muse-wonder-1.0 (cached answer) | $0.046 | ✅ / ✅ |
| find_trip | `skylark_lookup_trip_destination` | 3 | trip_confirmation_code | destination | 0 | muse-wonder-1.0 (cached answer) | $0.052 | ✅ / ✅ |
| check_in_next | `skylark_check_in_flight` | 6 | trip_city | seat, gate, boarding_time, boarding_group, flight | 0 | muse-wonder-1.0 (cached answer) | $0.000 | ✅ |

### Compiled with IDs hidden (variant 4)

| Family | Routine | Steps | Inputs | Outputs | Trace steps dropped | Compiler | Compile cost | Verified (same / second inputs) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| check_in | `skylark_check_in_flight` | 9 | trip_city | seat, gate, boarding | 1 | muse-wonder-1.0 (cached answer) | $0.062 | ✅ / ✅ |
| change_seat | `skylark_change_seat` | 7 | trip_city, desired_seat | seat, flight_number | 1 | muse-wonder-1.0 (cached answer) | $0.043 | ✅ / ✅ |
| add_ktn | `skylark_add_known_traveler_number` | 5 | trip_city, user_known_traveler_number | known_traveler_number | 1 | muse-wonder-1.0 (cached answer) | $0.050 | ✅ / ✅ |
| gate | `skylark_get_gate` | 3 | trip_city | gate | 0 | muse-wonder-1.0 (cached answer) | $0.043 | ✅ / ✅ |
| flight_status | `skylark_check_flight_status` | 3 | flight_number | flight_status_summary | 0 | muse-wonder-1.0 (cached answer) | $0.047 | ✅ / ✅ |
| find_trip | `skylark_lookup_trip_destination` | 3 | confirmation_code | destination | 0 | muse-wonder-1.0 (cached answer) | $0.051 | ✅ / ✅ |

### Compiled on the extra-screen layout (variant 3)

| Family | Routine | Steps | Inputs | Outputs | Trace steps dropped | Compiler | Compile cost | Verified (same / second inputs) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| check_in | `skylark_check_in_flight` | 14 | trip_city | check_in_status, seat, gate, boarding_time, boarding_group | 0 | muse-wonder-1.0 (cached answer) | $0.055 | ✅ / ✅ |

## Routines on bookings they have never seen

### Original layout

| Family | Runs | Success | Model calls (total) | Median time | Max time |
| --- | --- | --- | --- | --- | --- |
| check_in | 5 | 5/5 (100%) | 0 | 3.85 s | 5.34 s |
| change_seat | 5 | 5/5 (100%) | 0 | 4.24 s | 5.77 s |
| add_ktn | 5 | 5/5 (100%) | 0 | 3.29 s | 4.96 s |
| gate | 5 | 5/5 (100%) | 0 | 1.65 s | 3.37 s |
| flight_status | 5 | 5/5 (100%) | 0 | 2.32 s | 2.33 s |
| find_trip | 5 | 5/5 (100%) | 0 | 1.69 s | 3.53 s |
| **all** | 30 | **30/30 (100%)** | 0 | 3.32 s | 5.77 s |

### IDs hidden (routines compiled on variant 4, run on variant 4)

| Family | Runs | Success | Model calls (total) | Median time | Max time |
| --- | --- | --- | --- | --- | --- |
| check_in | 3 | 3/3 (100%) | 0 | 3.87 s | 4.56 s |
| change_seat | 3 | 3/3 (100%) | 0 | 5.92 s | 6.19 s |
| add_ktn | 3 | 3/3 (100%) | 0 | 3.24 s | 3.38 s |
| gate | 3 | 3/3 (100%) | 0 | 1.65 s | 1.65 s |
| flight_status | 3 | 3/3 (100%) | 0 | 3.22 s | 3.31 s |
| find_trip | 3 | 3/3 (100%) | 0 | 1.65 s | 3.42 s |
| **all** | 18 | **18/18 (100%)** | 0 | 3.28 s | 6.19 s |

## Injected UI changes

Each experiment: (1) the compiled routine meets the changed layout on a new booking, with repair and the agent allowed; (2) any patches become a trial version, replayed at once from a reset snapshot on another new booking with no repair and no agent allowed; it becomes active if it passes, else it is rejected (rollback); (3) the active version runs on a third booking (does it now need no model?); (4) a patched version runs on the original layout.

### Routines compiled on the original layout

| Change | Experiments | Recovered | Saved by (highest rung) | Model calls | Median time | Cost | Patches | Trial passed | Patched version alone (0 model calls) | Still works on the original layout |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1: moved button | 7 | 7/7 (100%) | none needed ×6, local repair ×1 | 2 | 3.19 s | $0.0096 | replace ×1 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) |
| 2: renamed labels | 7 | 7/7 (100%) | relaxed match ×7 | 0 | 4.02 s | $0.0000 | check ×12, locator ×5, post ×2 | 7/7 (100%) | 7/7 (100%) | 7/7 (100%) |
| 3: extra screen | 7 | 7/7 (100%) | none needed ×5, local repair ×2 | 2 | 3.33 s | $0.0109 | insert_after ×2 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) |
| 4: hidden IDs | 6 | 6/6 (100%) | relaxed match ×6 | 0 | 4.27 s | $0.0000 | check ×7, locator ×6 | 6/6 (100%) | 6/6 (100%) | 6/6 (100%) |
| 5: renamed + hidden IDs | 6 | 6/6 (100%) | relaxed match ×4, local repair ×2 | 3 | 6.24 s | $0.0100 | check ×19, locator ×16, post ×1 | 6/6 (100%) | 6/6 (100%) | 6/6 (100%) |

Per experiment:

| Routine | Change | First run | Rung | Calls | Time | Patches | Trial | Next run | Original layout |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| check_in | 1 | ✅ done | 0 | 0 | 4.55 s | – | – | ✅ 0 calls, rung 0 | – |
| check_in | 2 | ✅ done | 2 | 0 | 7.58 s | step 'open_my_trips': after-check 1 matched only relaxed; updated to {text='Trips', resour; step 'open_my_trips': after-check 2 matched only relaxed; updated to {text='Trips', resour; step 'start_check_in': after-checks failed (no match (best 0.00 < 0.80 or ambiguous, runne; step 'continue_after_passenger': target found only by relaxed match; locator updated to {t; step 'continue_after_hazmat': target found only by relaxed match; locator updated to {text | ✅ v2 | ✅ 0 calls, rung 0 | ✅ |
| check_in | 3 | ✅ done | 4 | 1 | 13.77 s | after 'continue_after_hazmat', an extra screen appeared; inserted continue_after_hazmat_ex | ✅ v2 | ✅ 0 calls, rung 0 | ✅ |
| check_in | 4 | ✅ done | 2 | 0 | 5.67 s | step 'find_select_trip': after-check 0 matched only relaxed; updated to {text='Savannah', ; step 'select_trip': target found only by relaxed match; locator updated to {text_has='{{tr | ✅ v2 | ✅ 0 calls, rung 2 | ✅ |
| check_in | 5 | ✅ done | 4 | 2 | 29.83 s | step 'open_my_trips': target found only by relaxed match; locator updated to {text='Trips'; step 'open_my_trips': after-check 1 matched only relaxed; updated to {text='Trips', kind='; step 'open_my_trips': after-check 2 matched only relaxed; updated to {text='Trips', kind='; step 'find_select_trip': after-check 0 matched only relaxed; updated to {text='Boise', kin; step 'select_trip': target found only by relaxed match; locator updated to {text_has='{{tr; step 'start_check_in': after-checks failed (no match (best 0.00 < 0.80 or ambiguous, runne; step 'continue_after_passenger': the element moved or changed; new locator {text='Next', r; step 'continue_after_hazmat': the element moved or changed; new locator {text='Next', reso; step 'confirm_check_in': target found only by relaxed match; locator updated to {text='Com | ✅ v2 | ✅ 0 calls, rung 2 | ✅ |
| change_seat | 1 | ✅ done | 0 | 0 | 4.21 s | – | – | ✅ 0 calls, rung 0 | – |
| change_seat | 2 | ✅ done | 2 | 0 | 5.93 s | step 'open_my_trips': after-check 1 matched only relaxed; updated to {text='Trips', resour; step 'open_my_trips': after-check 2 matched only relaxed; updated to {text='Trips', resour; step 'open_change_seat': target found only by relaxed match; locator updated to {text='Sea | ✅ v2 | ✅ 0 calls, rung 0 | ✅ |
| change_seat | 3 | ✅ done | 0 | 0 | 6.07 s | – | – | ✅ 0 calls, rung 0 | – |
| change_seat | 4 | ✅ done | 2 | 0 | 7.95 s | step 'find_open_trip': after-check 0 matched only relaxed; updated to {text='Savannah', ki; step 'open_trip': target found only by relaxed match; locator updated to {text_has='{{trip; step 'find_select_seat': after-check 0 matched only relaxed; updated to {text='Seat 10C, a; step 'select_seat': target found only by relaxed match; locator updated to {text_has='{{de | ✅ v2 | ✅ 0 calls, rung 2 | ✅ |
| change_seat | 5 | ✅ done | 4 | 1 | 19.45 s | step 'open_my_trips': target found only by relaxed match; locator updated to {text='Trips'; step 'open_my_trips': after-check 1 matched only relaxed; updated to {text='Trips', kind='; step 'open_my_trips': after-check 2 matched only relaxed; updated to {text='Trips', kind='; step 'find_open_trip': after-check 0 matched only relaxed; updated to {text='Boise', kind=; step 'open_trip': target found only by relaxed match; locator updated to {text_has='{{trip; step 'open_change_seat': the element moved or changed; new locator {text='Seats', resource; step 'find_select_seat': after-check 0 matched only relaxed; updated to {text='Seat 21D, a; step 'select_seat': target found only by relaxed match; locator updated to {text_has='{{de | ✅ v2 | ✅ 0 calls, rung 2 | ✅ |
| add_ktn | 1 | ✅ done | 0 | 0 | 3.19 s | – | – | ✅ 0 calls, rung 0 | – |
| add_ktn | 2 | ✅ done | 2 | 0 | 4.02 s | step 'open_my_trips': after-check 1 matched only relaxed; updated to {text='Trips', resour; step 'open_my_trips': after-check 2 matched only relaxed; updated to {text='Trips', resour | ✅ v2 | ✅ 0 calls, rung 0 | ✅ |
| add_ktn | 3 | ✅ done | 0 | 0 | 3.33 s | – | – | ✅ 0 calls, rung 0 | – |
| add_ktn | 4 | ✅ done | 2 | 0 | 4.95 s | step 'find_open_trip': after-check 0 matched only relaxed; updated to {text='Savannah', ki; step 'open_trip': target found only by relaxed match; locator updated to {text_has='{{trip | ✅ v2 | ✅ 0 calls, rung 2 | ✅ |
| add_ktn | 5 | ✅ done | 2 | 0 | 6.99 s | step 'open_my_trips': target found only by relaxed match; locator updated to {text='Trips'; step 'open_my_trips': after-check 1 matched only relaxed; updated to {text='Trips', kind='; step 'open_my_trips': after-check 2 matched only relaxed; updated to {text='Trips', kind='; step 'find_open_trip': after-check 0 matched only relaxed; updated to {text='Boise', kind=; step 'open_trip': target found only by relaxed match; locator updated to {text_has='{{trip | ✅ v2 | ✅ 0 calls, rung 2 | ✅ |
| gate | 1 | ✅ done | 0 | 0 | 1.67 s | – | – | ✅ 0 calls, rung 0 | – |
| gate | 2 | ✅ done | 2 | 0 | 2.54 s | step 'tap_my_trips': after-check 1 matched only relaxed; updated to {text='Trips', resourc; step 'tap_my_trips': after-check 2 matched only relaxed; updated to {text='Trips', resourc | ✅ v2 | ✅ 0 calls, rung 0 | ✅ |
| gate | 3 | ✅ done | 0 | 0 | 1.69 s | – | – | ✅ 0 calls, rung 0 | – |
| gate | 4 | ✅ done | 2 | 0 | 3.58 s | step 'find_tap_trip_row': after-check 0 matched only relaxed; updated to {text='Savannah',; step 'tap_trip_row': target found only by relaxed match; locator updated to {text_has='{{t | ✅ v2 | ✅ 0 calls, rung 2 | ✅ |
| gate | 5 | ✅ done | 2 | 0 | 5.48 s | step 'tap_my_trips': target found only by relaxed match; locator updated to {text='Trips',; step 'tap_my_trips': after-check 1 matched only relaxed; updated to {text='Trips', kind='T; step 'tap_my_trips': after-check 2 matched only relaxed; updated to {text='Trips', kind='T; step 'find_tap_trip_row': after-check 0 matched only relaxed; updated to {text='Boise', ki; step 'tap_trip_row': target found only by relaxed match; locator updated to {text_has='{{t | ✅ v2 | ✅ 0 calls, rung 2 | ✅ |
| flight_status | 1 | ✅ done | 0 | 0 | 2.36 s | – | – | ✅ 0 calls, rung 0 | – |
| flight_status | 2 | ✅ done | 2 | 0 | 3.23 s | step 'tap_flight_status': after-check 1 matched only relaxed; updated to {text='Status', r; step 'tap_flight_status': after-check 2 matched only relaxed; updated to {text='Status', r | ✅ v2 | ✅ 0 calls, rung 0 | ✅ |
| flight_status | 3 | ✅ done | 0 | 0 | 2.24 s | – | – | ✅ 0 calls, rung 0 | – |
| find_trip | 1 | ✅ done | 0 | 0 | 1.67 s | – | – | ✅ 0 calls, rung 2 | – |
| find_trip | 2 | ✅ done | 2 | 0 | 2.57 s | step 'tap_my_trips': after-check 1 matched only relaxed; updated to {text='Trips', resourc; step 'tap_my_trips': after-check 2 matched only relaxed; updated to {text='Trips', resourc | ✅ v2 | ✅ 0 calls, rung 2 | ✅ |
| find_trip | 3 | ✅ done | 0 | 0 | 1.64 s | – | – | ✅ 0 calls, rung 2 | – |
| find_trip | 4 | ✅ done | 2 | 0 | 3.58 s | step 'find_tap_trip_by_confirmation_code': after-check 0 matched only relaxed; updated to ; step 'tap_trip_by_confirmation_code': target found only by relaxed match; locator updated  | ✅ v2 | ✅ 0 calls, rung 2 | ✅ |
| find_trip | 5 | ✅ done | 2 | 0 | 5.44 s | step 'tap_my_trips': target found only by relaxed match; locator updated to {text='Trips',; step 'tap_my_trips': after-check 1 matched only relaxed; updated to {text='Trips', kind='T; step 'tap_my_trips': after-check 2 matched only relaxed; updated to {text='Trips', kind='T; step 'find_tap_trip_by_confirmation_code': after-check 0 matched only relaxed; updated to ; step 'tap_trip_by_confirmation_code': target found only by relaxed match; locator updated  | ✅ v2 | ✅ 0 calls, rung 2 | ✅ |
| check_in_next | 1 | ✅ done | 4 | 2 | 18.62 s | step 'tap_check_in' replaced by tap None, tap Check in | ✅ v2 | ✅ 0 calls, rung 0 | ✅ |
| check_in_next | 2 | ✅ done | 2 | 0 | 5.33 s | step 'tap_check_in': after-checks failed (no match (best 0.00 < 0.80 or ambiguous, runner-; step 'tap_continue_after_passenger': target found only by relaxed match; locator updated t; step 'tap_continue_after_hazmat': target found only by relaxed match; locator updated to { | ✅ v2 | ✅ 0 calls, rung 0 | ✅ |
| check_in_next | 3 | ✅ done | 4 | 1 | 9.12 s | after 'tap_continue_after_hazmat', an extra screen appeared; inserted tap_continue_after_h | ✅ v2 | ✅ 0 calls, rung 0 | ✅ |
| flight_status | 4 | ✅ done | 2 | 0 | 3.3 s | step 'enter_flight_number': after-check 0 matched only relaxed; updated to {text='Flight n | ✅ v2 | ✅ 0 calls, rung 2 | ✅ |
| flight_status | 5 | ✅ done | 2 | 0 | 5.14 s | step 'tap_flight_status': target found only by relaxed match; locator updated to {text='St; step 'tap_flight_status': after-check 1 matched only relaxed; updated to {text='Status', k; step 'tap_flight_status': after-check 2 matched only relaxed; updated to {text='Status', k; step 'enter_flight_number': after-check 0 matched only relaxed; updated to {text='Flight n | ✅ v2 | ✅ 0 calls, rung 2 | ✅ |

### A routine compiled on the extra-screen layout, run on the original

| Change | Experiments | Recovered | Saved by (highest rung) | Model calls | Median time | Cost | Patches | Trial passed | Patched version alone (0 model calls) | Still works on the original layout |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0: original | 1 | 1/1 (100%) | relaxed match ×1 | 0 | 7.72 s | $0.0000 | remove ×1 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) |

Per experiment:

| Routine | Change | First run | Rung | Calls | Time | Patches | Trial | Next run | Original layout |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| check_in | 0 | ✅ done | 2 | 0 | 7.72 s | step 'confirm_trip_review' removed: its screen no longer appears after 'continue_after_haz | ✅ v2 | ✅ 0 calls, rung 0 | ✅ |

### Routines compiled with IDs hidden

| Change | Experiments | Recovered | Saved by (highest rung) | Model calls | Median time | Cost | Patches | Trial passed | Patched version alone (0 model calls) | Still works on the original layout |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5: renamed + hidden IDs | 6 | 6/6 (100%) | relaxed match ×4, local repair ×2 | 3 | 4.12 s | $0.0102 | locator ×11, check ×2 | 6/6 (100%) | 6/6 (100%) | 6/6 (100%) |

Per experiment:

| Routine | Change | First run | Rung | Calls | Time | Patches | Trial | Next run | Original layout |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| check_in | 5 | ✅ done | 4 | 2 | 28.33 s | step 'open_my_trips': target found only by relaxed match; locator updated to {text='Trips'; step 'continue_after_passenger': the element moved or changed; new locator {text='Next', k; step 'continue_after_hazardous_materials': the element moved or changed; new locator {text; step 'confirm_check_in': target found only by relaxed match; locator updated to {text='Com | ✅ v2 | ✅ 0 calls, rung 0 | ✅ |
| change_seat | 5 | ✅ done | 4 | 1 | 15.84 s | step 'open_my_trips': target found only by relaxed match; locator updated to {text='Trips'; step 'open_change_seat': the element moved or changed; new locator {text='Seats', kind='Bu; step 'find_select_desired_seat': after-check 0 matched only relaxed; updated to {text='Sea; step 'select_desired_seat': target found only by relaxed match; locator updated to {text_h | ✅ v2 | ✅ 0 calls, rung 2 | ✅ |
| add_ktn | 5 | ✅ done | 2 | 0 | 4.15 s | step 'open_my_trips': target found only by relaxed match; locator updated to {text='Trips' | ✅ v2 | ✅ 0 calls, rung 0 | ✅ |
| gate | 5 | ✅ done | 2 | 0 | 2.63 s | step 'open_my_trips': target found only by relaxed match; locator updated to {text='Trips' | ✅ v2 | ✅ 0 calls, rung 0 | ✅ |
| flight_status | 5 | ✅ done | 2 | 0 | 4.09 s | step 'open_flight_status': target found only by relaxed match; locator updated to {text='S; step 'enter_flight_number': after-check 0 matched only relaxed; updated to {text='Flight n | ✅ v2 | ✅ 0 calls, rung 2 | ✅ |
| find_trip | 5 | ✅ done | 2 | 0 | 2.61 s | step 'tap_my_trips': target found only by relaxed match; locator updated to {text='Trips', | ✅ v2 | ✅ 0 calls, rung 0 | ✅ |

## Three systems compared

### Three systems on the same requests

Each cell is one request per routine family on a booking none of the systems was built from (6 families). Full agent: plan + one model call per step. Fixed replay: the recorded taps at their coordinates with the recorded text, a screen-similarity check before each, and the full agent on a mismatch (like Mobilerun macros). Envoy routine: the compiled routine with its checks and fallback ladder (first run on the changed layout, before any patch).

| Layout | System | Success | Median model calls | Median time | Median cost (standard prices) | Wrong-booking or wrong-answer runs |
| --- | --- | --- | --- | --- | --- | --- |
| 0: original | Full agent | 6/6 (100%) | 5.5 | 12.05 s | $0.0100 | 0 |
| 0: original | Fixed replay | 0/6 (0%) | 0.0 | 3.6 s | $0.0000 | 6 |
| 0: original | Envoy routine | 6/6 (100%) | 0.0 | 2.84 s | $0.0000 | 0 |
| 1: moved button | Full agent | 6/6 (100%) | 6.0 | 12.84 s | $0.0100 | 0 |
| 1: moved button | Fixed replay | 3/6 (50%) | 5.5 | 14.71 s | $0.0100 | 3 |
| 1: moved button | Envoy routine | 7/7 (100%) | 0 | 3.19 s | $0.0000 | 0 |
| 2: renamed labels | Full agent | 6/6 (100%) | 5.5 | 11.69 s | $0.0100 | 0 |
| 2: renamed labels | Fixed replay | 0/6 (0%) | 0.0 | 3.5 s | $0.0000 | 6 |
| 2: renamed labels | Envoy routine | 7/7 (100%) | 0 | 4.02 s | $0.0000 | 0 |
| 3: extra screen | Full agent | 6/6 (100%) | 5.5 | 10.67 s | $0.0100 | 0 |
| 3: extra screen | Fixed replay | 1/6 (17%) | 0.0 | 3.52 s | $0.0000 | 5 |
| 3: extra screen | Envoy routine | 7/7 (100%) | 0 | 3.33 s | $0.0000 | 0 |
| 4: hidden IDs | Full agent | 6/6 (100%) | 6.0 | 13.91 s | $0.0100 | 0 |
| 4: hidden IDs | Fixed replay | 6/6 (100%) | 5.5 | 14.95 s | $0.0100 | 0 |
| 4: hidden IDs | Envoy routine | 6/6 (100%) | 0.0 | 4.27 s | $0.0000 | 0 |
| 5: renamed + hidden IDs | Full agent | 6/6 (100%) | 6.5 | 15.04 s | $0.0100 | 0 |
| 5: renamed + hidden IDs | Fixed replay | 6/6 (100%) | 6.5 | 15.85 s | $0.0100 | 0 |
| 5: renamed + hidden IDs | Envoy routine | 6/6 (100%) | 0.0 | 6.24 s | $0.0000 | 0 |

Across these cells, routines used **7 model calls against 242 for the full agent (97% fewer)**, with a median of 4.21 s against 11.69 s.

## Real-app checkpoint (envoy-real, read-only)

| App | Agent run | Compiled | Rerun (inputs) | Without repair | With repair allowed |
| --- | --- | --- | --- | --- | --- |
| target | handoff · 3 steps · 4 calls · 19.12 s · $0.0074 | no: run ended 'handoff' with check None; only verified runs are  | – | – | – |
| chipotle | done · 14 steps · 18 calls · 47.44 s · $0.0308 | 11 steps, inputs zip_code, outputs price | same-inputs {'zip_code': '10001'} | ❌ failed, rung 1, 0 calls, 11.83 s: step select_zip_code_suggestion: target not found: no match (best 0.98 | ❌ failed, rung 4, 3 calls, 57.02 s: step scroll_to_chips_and_sides: after-checks failed: no match (best 0. |
| amazon | done · 2 steps · 4 calls · 23.01 s · $0.0102 | 2 steps, inputs search_query, outputs first_result_price | same-inputs {'search_query': 'AA batteries'} | ✅ done, rung 1, 0 calls, 8.9 s | not needed |
| amazon |  |  | second-input {'search_query': 'USB-C cable'} | ✅ done, rung 1, 0 calls, 9.46 s | not needed |
| doordash | failed · 19 steps · 24 calls · 73.34 s · $0.0494 | no: run ended 'failed' with check None; only verified runs are c | – | – | – |
| starbucks | done · 7 steps · 9 calls · 25.72 s · $0.0129 | 8 steps, inputs drink_name, outputs calories | same-inputs {'drink_name': 'Caffe Latte'} | ✅ done, rung 1, 0 calls, 9.14 s | not needed |
| starbucks |  |  | second-input {'drink_name': 'Caramel Macchiato'} | ✅ done, rung 1, 0 calls, 9.24 s | not needed |

## Matching requests to routines

12/12 correct (routine and every input right, or no routine when none fits); 12 model calls, $0.0350 at standard prices.

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

