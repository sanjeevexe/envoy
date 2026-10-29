# Compiling the core set's routines

Run 1029014818 on `1f1fc11` with uncommitted changes, 2026-10-29 05:48 UTC, 7 min, standard tier. 61 model calls, $0.561 at standard prices ($0.561 billed).

| Task | New | Source run | Compile attempts | Routine | Steps | Inputs | Outputs |
| --- | --- | --- | --- | --- | --- | --- | --- |
| check_in |  | 8 actions, 10 calls, 34.01 s | 1 | skylark_check_in_flight | 9 | trip_city | seat, gate, boarding_time |
| change_seat |  | 5 actions, 7 calls, 13.56 s | 1 | skylark_change_seat | 7 | trip_city, desired_seat | new_seat |
| add_ktn |  | 4 actions, 6 calls, 11.49 s | 1 | skylark_add_known_traveler_number | 5 | trip_city, known_traveler_number | known_traveler_number, save_confirmation, confirmation_code |
| gate |  | 2 actions, 4 calls, 7.09 s | 1 | skylark_get_departure_gate | 3 | trip_city | gate |
| seat | yes | 2 actions, 4 calls, 8.05 s | 1 | skylark_get_seat | 3 | trip_city | seat |
| flight_status |  | 3 actions, 5 calls, 9.2 s | 1 | skylark_check_flight_status | 3 | flight_number | flight_status, route, date, gate, departure_time |
| miles | yes | 0 actions, 2 calls, 3.54 s | 1 | skylark_check_miles | 1 | – | miles |
| find_trip |  | 2 actions, 4 calls, 7.13 s | 1 | skylark_look_up_trip | 3 | trip_confirmation_code | destination |
| past_trip | yes | 3 actions, 5 calls, 12.33 s | 1 | skylark_find_flight_date | 2 | trip_city | flight_date |
| gate_alerts | yes | 2 actions, 4 calls, 8.57 s | 1 | skylark_turn_on_gate_change_alerts | 2 | – | – |
