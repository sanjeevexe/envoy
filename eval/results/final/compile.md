# Compiling the core set's routines

Run 1103001513 on `eval-final`, 2026-11-03 05:15 UTC, 10 min, standard tier, the `hybrid` profile (Muse Wonder for compile, plan, repair, step; Muse Spark for the rest). 64 model calls, $0.912 at standard prices ($0.912 billed).

| Task | New | Source run | Compile attempts | Routine | Steps | Inputs | Outputs |
| --- | --- | --- | --- | --- | --- | --- | --- |
| check_in |  | 8 actions, 10 calls, 49.68 s | 1 | skylark_check_in_flight | 9 | trip_city | seat, gate, boarding_time, boarding_group |
| change_seat |  | 6 actions, 8 calls, 37.79 s | 1 | skylark_change_seat | 8 | trip_city, desired_seat | seat, gate, boarding, confirmation |
| add_ktn |  | 4 actions, 6 calls, 21.12 s | 1 | skylark_add_known_traveler_number | 5 | trip_city, known_traveler_number | known_traveler_number_saved |
| gate |  | 2 actions, 4 calls, 14.46 s | 1 | skylark_get_departure_gate | 3 | trip_city | gate |
| seat | yes | 2 actions, 4 calls, 19.91 s | 1 | skylark_get_seat | 3 | trip_city | seat |
| flight_status |  | 3 actions, 5 calls, 21.42 s | 1 | skylark_check_flight_status | 3 | flight_number | flight_status |
| miles | yes | 0 actions, 2 calls, 18.93 s | 1 | skylark_check_miles | 1 | – | skylark_miles |
| find_trip |  | 4 actions, 6 calls, 31.8 s | 1 | skylark_look_up_trip | 5 | trip_confirmation_code, user_last_name | destination |
| past_trip | yes | 3 actions, 5 calls, 18.55 s | 1 | skylark_find_flight_date | 2 | trip_city | flight_date |
| gate_alerts | yes | 2 actions, 4 calls, 21.23 s | 1 | skylark_turn_on_gate_change_alerts | 2 | – | – |
