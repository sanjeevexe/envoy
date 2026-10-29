# Compiling the core set's routines

Run 1028210913 on `2ecbbbf` with uncommitted changes, 2026-10-29 01:09 UTC, 10 min, standard tier. 96 model calls, $0.681 at standard prices ($0.681 billed).

| Task | New | Source run | Compile attempts | Routine | Steps | Inputs | Outputs |
| --- | --- | --- | --- | --- | --- | --- | --- |
| check_in |  | 15 actions, 17 calls, 29.89 s | 0 | ❌ rejected | – | – | – |
| change_seat |  | 5 actions, 7 calls, 14.11 s | 1 | skylark_change_seat | 7 | trip_city, desired_seat | seat, confirmation_message |
| add_ktn |  | 4 actions, 6 calls, 11.84 s | 1 | skylark_add_known_traveler_number | 5 | trip_city, known_traveler_number | known_traveler_number |
| gate |  | 2 actions, 4 calls, 7.68 s | 1 | skylark_get_departure_gate | 3 | trip_city | gate |
| seat | yes | 2 actions, 4 calls, 6.36 s | 1 | skylark_get_seat | 3 | trip_city | seat |
| flight_status |  | 3 actions, 5 calls, 10.34 s | 1 | skylark_check_flight_status | 3 | flight_number | flight_status, gate, departure_time, route, flight_date |
| miles | yes | 0 actions, 2 calls, 3.24 s | 1 | skylark_check_miles_balance | 1 | – | miles_balance |
| find_trip |  | 2 actions, 4 calls, 8.36 s | 1 | skylark_look_up_trip | 3 | trip_confirmation_code | destination |
| past_trip | yes | 3 actions, 5 calls, 11.47 s | 3 | ❌ rejected | – | – | – |
| gate_alerts | yes | 2 actions, 4 calls, 8.13 s | 1 | skylark_turn_on_gate_alerts | 2 | – | – |
