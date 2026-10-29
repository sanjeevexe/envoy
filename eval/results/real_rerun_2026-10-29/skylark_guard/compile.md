# Compiling the core set's routines

Run 1029151131 on `5fa03bf` with uncommitted changes, 2026-10-29 19:11 UTC, 9 min, standard tier. 61 model calls, $0.544 at standard prices ($0.544 billed).

| Task | New | Source run | Compile attempts | Routine | Steps | Inputs | Outputs |
| --- | --- | --- | --- | --- | --- | --- | --- |
| check_in |  | 8 actions, 10 calls, 40.62 s | 1 | skylark_check_in_flight | 9 | trip_city | seat, gate, boarding_time |
| change_seat |  | 5 actions, 7 calls, 19.86 s | 1 | skylark_change_seat | 7 | trip_city, desired_seat | seat, flight_number |
| add_ktn |  | 4 actions, 6 calls, 12.78 s | 1 | skylark_add_known_traveler_number | 5 | trip_city, known_traveler_number | confirmation_code, known_traveler_number, save_confirmation |
| gate |  | 2 actions, 4 calls, 8.08 s | 1 | skylark_get_departure_gate | 3 | trip_city | gate |
| seat | yes | 2 actions, 4 calls, 7.51 s | 1 | skylark_get_seat | 3 | trip_city | seat |
| flight_status |  | 3 actions, 5 calls, 10.84 s | 1 | skylark_check_flight_status | 3 | flight_number | route, date, status, gate, departure_time |
| miles | yes | 0 actions, 2 calls, 5.81 s | 1 | skylark_get_miles | 1 | – | skylark_miles |
| find_trip |  | 2 actions, 4 calls, 11.88 s | 1 | skylark_look_up_trip | 3 | confirmation_code | destination |
| past_trip | yes | 3 actions, 5 calls, 13.92 s | 1 | skylark_find_trip_date | 2 | trip_city | trip_date |
| gate_alerts | yes | 2 actions, 4 calls, 9.15 s | 1 | skylark_turn_on_gate_change_alerts | 2 | – | gate_change_alerts |
