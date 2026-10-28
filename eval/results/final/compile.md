# Compiling the core set's routines

Run 1027220628 on `ad9a67b` with uncommitted changes, 2026-10-28 02:06 UTC, 0 min, standard tier. 0 model calls, $0.000 at standard prices ($0.000 billed).

| Task | New | Source run | Compile attempts | Routine | Steps | Inputs | Outputs |
| --- | --- | --- | --- | --- | --- | --- | --- |
| check_in |  | 10 actions, 12 calls, 22.3 s | 1 | skylark_check_in_flight | 9 | trip_city | seat, gate, boarding_time, boarding_group |
| change_seat |  | 9 actions, 11 calls, 22.7 s | 1 | skylark_change_seat | 7 | trip_city, new_seat | confirmed_seat, flight_number |
| add_ktn |  | 8 actions, 10 calls, 23.28 s | 1 | skylark_add_known_traveler_number | 5 | trip_city, user_known_traveler_number | known_traveler_number, save_confirmation, confirmation_code |
| gate |  | 2 actions, 4 calls, 7.63 s | 1 | skylark_get_departure_gate | 3 | trip_city | gate |
| seat | yes | 2 actions, 4 calls, 7.62 s | 1 | skylark_get_flight_seat | 3 | trip_city | seat |
| flight_status |  | 6 actions, 8 calls, 15.5 s | 1 | skylark_check_flight_status | 4 | flight_number | flight_status, route, flight_date, gate, departure_time |
| find_trip |  | 2 actions, 4 calls, 7.06 s | 1 | skylark_look_up_trip | 3 | trip_confirmation_code | destination |
| past_trip | yes | 3 actions, 5 calls, 9.79 s | 1 | skylark_get_trip_date | 3 | trip_city | flight_date, flight |
| gate_alerts | yes | 2 actions, 4 calls, 8.96 s | 1 | skylark_turn_on_gate_change_alerts | 2 | – | – |
| miles | yes | 0 actions, 2 calls, 5.25 s | 1 | skylark_get_miles | 1 | – | skylark_miles |
