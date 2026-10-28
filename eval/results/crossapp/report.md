# Cross-app answers, end to end

2026-10-28 09:24–09:56 UTC, branch `claude/cross-app-answers-522e1d` at `deb931d`, phones: envoy-real. Standard tier (`muse-spark-1.3`); every approval declined; read-only questions. 174 model calls, $0.417 at standard prices.

Parallel: through chat (pre-filter → lead → parts on the phones routing picks). Sequential: the same lead and orchestrator, each part started after the previous one ended. Wall time: from the message to the combined answer (memory is written after it, as for any task).

Overlap: seconds two phones were busy at once. Idle: seconds a phone sat unused between two parts that needed it.

| Question | Mode | Wall s | Overlap s | Idle s | Parts (phone, path, s on phone) | Calls | $ | Approvals | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R1 | parallel | 31.17 | 0.0 | 0.0 | Starbucks (envoy-real, starbucks_get_drink_calories, 11.7); DoorDash (envoy-real, doordash_search_restaurants, 11.9) | 6 | 0.015 | 0 | done |
| R1 | sequential | 31.55 | 0.0 | 2.3 | Starbucks (envoy-real, starbucks_get_drink_calories, 10.7); DoorDash (envoy-real, doordash_search_restaurants, 11.7) | 8 | 0.019 | 0 | done |
| R1 | parallel | 36.9 | 0.0 | 0.0 | Starbucks (envoy-real, starbucks_get_drink_calories, 17.9); DoorDash (envoy-real, doordash_search_restaurants, 11.9) | 8 | 0.020 | 0 | done |
| R1 | sequential | 31.15 | 0.0 | 2.3 | Starbucks (envoy-real, starbucks_get_drink_calories, 11.6); DoorDash (envoy-real, doordash_search_restaurants, 8.8) | 7 | 0.019 | 0 | done |
| R3 | parallel | 59.84 | 0.0 | 0.0 | Starbucks (envoy-real, starbucks_get_drink_calories, 31.0); Google Maps (envoy-real, google_maps_get_place_address, 22.1) | 7 | 0.028 | 0 | done |
| R3 | sequential | 37.33 | 0.0 | 2.2 | Starbucks (envoy-real, starbucks_get_drink_calories, 12.0); Google Maps (envoy-real, google_maps_get_place_address, 15.8) | 7 | 0.024 | 0 | done |
| R3 | parallel | 42.96 | 0.0 | 0.0 | Starbucks (envoy-real, starbucks_get_drink_calories, 19.5); Google Maps (envoy-real, google_maps_get_place_address, 16.1) | 7 | 0.024 | 0 | done |
| R3 | sequential | 36.54 | 0.0 | 1.9 | Starbucks (envoy-real, starbucks_get_drink_calories, 13.5); Google Maps (envoy-real, google_maps_get_place_address, 14.4) | 8 | 0.022 | 0 | done |
| R2 | parallel | 172.05 | 0.0 | 0.0 | Starbucks (envoy-real, agent, 78.0); DoorDash (envoy-real, agent, 82.9) | 57 | 0.113 | 0 | done |
| R2 | sequential | 186.97 | 0.0 | 3.9 | Starbucks (envoy-real, agent, 83.3); DoorDash (envoy-real, agent, 94.4) | 59 | 0.133 | 0 | failed |

## Medians

| Question | Parallel wall s | Sequential wall s | Saved |
| --- | --- | --- | --- |
| R1 | 34.0 (n=2) | 31.4 (n=2) | -2.7 s (-9%) |
| R3 | 51.4 (n=2) | 36.9 (n=2) | -14.5 s (-39%) |
| R2 | 172.1 (n=1) | 187.0 (n=1) | 14.9 s (8%) |

## Answers

- **R1 parallel** (How many calories are in a Caffè Latte at Starbucks, and what's the first place DoorDash shows for a latte?): A Caffè Latte has 190 calories according to Starbucks, and the first place for a latte on DoorDash is McDonald's.
  - Caffè Latte calories at Starbucks: Starbucks · the "Caffè Latte" screen · 5:27 AM
  - first place DoorDash shows for a latte: DoorDash · DashboardActivity · 5:27 AM
- **R1 sequential** (How many calories are in a Caffè Latte at Starbucks, and what's the first place DoorDash shows for a latte?): A Caffè Latte at Starbucks has 190 calories, and DoorDash's first place for a latte is McDonald's.
  - Caffè Latte calories at Starbucks: Starbucks · the "Caffè Latte" screen · 5:27 AM
  - first place for latte on DoorDash: DoorDash · DashboardActivity · 5:28 AM
- **R1 parallel** (How many calories are in a Caffè Latte at Starbucks, and what's the first place DoorDash shows for a latte?): Starbucks lists a Caffè Latte at 190 calories, and DoorDash shows McDonald's first for a latte.
  - Caffè Latte calories at Starbucks: Starbucks · the "Caffè Latte" screen · 5:28 AM
  - first place for latte on DoorDash: DoorDash · DashboardActivity · 5:28 AM
- **R1 sequential** (How many calories are in a Caffè Latte at Starbucks, and what's the first place DoorDash shows for a latte?): Starbucks shows 190 calories for a Caffè Latte, and DoorDash shows McDonald's as the first place for a latte.
  - Caffè Latte calories at Starbucks: Starbucks · the "Caffè Latte" screen · 5:29 AM
  - first place for latte on DoorDash: DoorDash · DashboardActivity · 5:29 AM
- **R3 parallel** (How many calories are in a Caffè Mocha at Starbucks, and what's the address of the Space Needle in Google Maps?): According to Starbucks, a Caffè Mocha has 370 calories, and according to Google Maps, the Space Needle is at 400 Broad St, Seattle, WA 98109.
  - Caffè Mocha calories at Starbucks: Starbucks · the "Caffè Mocha" screen · 5:29 AM
  - Space Needle address: Google Maps · MapsActivity · 5:30 AM
- **R3 sequential** (How many calories are in a Caffè Mocha at Starbucks, and what's the address of the Space Needle in Google Maps?): Starbucks lists the Caffè Mocha at 370 calories, and Google Maps lists the Space Needle at 400 Broad St, Seattle, WA 98109.
  - Caffè Mocha calories at Starbucks: Starbucks · the "Caffè Mocha" screen · 5:30 AM
  - Space Needle address: Google Maps · MapsActivity · 5:30 AM
- **R3 parallel** (How many calories are in a Caffè Mocha at Starbucks, and what's the address of the Space Needle in Google Maps?): Starbucks lists a Caffè Mocha at 370 calories, and Google Maps lists the Space Needle at 400 Broad St, Seattle, WA 98109.
  - Caffè Mocha calories at Starbucks: Starbucks · the "Caffè Mocha" screen · 5:31 AM
  - Space Needle address: Google Maps · MapsActivity · 5:31 AM
- **R3 sequential** (How many calories are in a Caffè Mocha at Starbucks, and what's the address of the Space Needle in Google Maps?): A Caffè Mocha has 370 calories per Starbucks, and the Space Needle is at 400 Broad St, Seattle, WA 98109 per Google Maps.
  - Caffè Mocha calories at Starbucks: Starbucks · the "Caffè Mocha" screen · 5:32 AM
  - Space Needle address: Google Maps · MapsActivity · 5:32 AM
- **R2 parallel** (What's a Caffè Latte at Starbucks vs on DoorDash?): Starbucks couldn't be checked, while DoorDash lists Caffè Latte at Starbucks on DoorDash is $5.75.
  - Caffè Latte price on DoorDash: DoorDash · StoreItemActivity · 5:52 AM
- **R2 sequential** (What's a Caffè Latte at Starbucks vs on DoorDash?): Starbucks: couldn't check (stopped after 25 steps); DoorDash: couldn't check (stopped after 25 steps).
