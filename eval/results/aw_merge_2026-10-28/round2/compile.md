# Compiling the core set's routines

Run 1028235635 on `773536a` with uncommitted changes, 2026-10-29 03:56 UTC, 8 min, standard tier. 62 model calls, $0.554 at standard prices ($0.554 billed).

| Task | New | Source run | Compile attempts | Routine | Steps | Inputs | Outputs |
| --- | --- | --- | --- | --- | --- | --- | --- |
| check_in |  | 8 actions, 10 calls, 18.54 s | 1 | skylark_check_in_flight | 9 | trip_city | seat, gate, boarding_time |
| change_seat |  | 5 actions, 7 calls, 16.67 s | 1 | skylark_change_seat | 7 | trip_city, desired_seat | new_seat |
| add_ktn |  | 4 actions, 6 calls, 11.03 s | 1 | skylark_add_known_traveler_number | 5 | trip_city, known_traveler_number | save_confirmation, confirmation_code |
| gate |  | 2 actions, 4 calls, 7.29 s | 1 | skylark_get_departure_gate | 3 | trip_city | gate |
| seat | yes | 2 actions, 4 calls, 7.23 s | 1 | skylark_get_seat | 3 | trip_city | seat |
| flight_status |  | 3 actions, 5 calls, 9.9 s | 1 | skylark_check_flight_status | 3 | flight_number | route, date, status, gate, departure_time |
| miles | yes | 0 actions, 2 calls, 3.43 s | 1 | skylark_get_miles | 1 | – | skylark_miles |
| find_trip |  | 2 actions, 4 calls, 8.35 s | 1 | skylark_lookup_trip | 3 | trip_confirmation_code | destination |
| past_trip | yes | 4 actions, 6 calls, 14.98 s | 1 | skylark_get_flight_date | 3 | trip_city | flight_date |
| gate_alerts | yes | 2 actions, 4 calls, 7.34 s | 1 | skylark_turn_on_gate_change_alerts | 2 | – | – |
