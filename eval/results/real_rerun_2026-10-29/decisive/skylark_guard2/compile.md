# Compiling the core set's routines

Run 1029155746 on `5fa03bf` with uncommitted changes, 2026-10-29 19:57 UTC, 8 min, standard tier. 62 model calls, $0.541 at standard prices ($0.541 billed).

| Task | New | Source run | Compile attempts | Routine | Steps | Inputs | Outputs |
| --- | --- | --- | --- | --- | --- | --- | --- |
| check_in |  | 8 actions, 10 calls, 21.39 s | 1 | skylark_check_in_flight | 9 | trip_city | seat, gate, boarding_time |
| change_seat |  | 5 actions, 7 calls, 16.85 s | 1 | skylark_change_seat | 7 | trip_city, desired_seat | new_seat |
| add_ktn |  | 4 actions, 6 calls, 12.54 s | 1 | skylark_add_known_traveler_number | 5 | trip_city, known_traveler_number | known_traveler_number, save_confirmation, confirmation_code |
| gate |  | 2 actions, 4 calls, 8.36 s | 1 | skylark_get_departure_gate | 3 | trip_city | gate |
| seat | yes | 2 actions, 4 calls, 8.57 s | 1 | skylark_get_seat | 3 | trip_city | seat |
| flight_status |  | 3 actions, 5 calls, 11.06 s | 1 | skylark_check_flight_status | 3 | flight_number | flight_status, route, flight_date, gate, departure_time |
| miles | yes | 0 actions, 2 calls, 6.17 s | 1 | skylark_check_miles | 1 | – | skylark_miles |
| find_trip |  | 2 actions, 4 calls, 9.9 s | 1 | skylark_lookup_trip_destination | 3 | trip_confirmation_code | destination_city |
| past_trip | yes | 4 actions, 6 calls, 15.31 s | 1 | skylark_get_trip_date | 3 | trip_city | flight_date |
| gate_alerts | yes | 2 actions, 4 calls, 9.49 s | 1 | skylark_turn_on_gate_change_alerts | 2 | – | – |
