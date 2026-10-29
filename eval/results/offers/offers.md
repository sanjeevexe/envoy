# Offers on envoy-test (2026-10-29T12:48:13, e73ef85)

**PASS**, model calls: 0, spend: $0.0

| | |
| --- | --- |
| Offer | Check in for SL 482? |
| What I'll do (goal) | Check me in for my flight SL 482 to Chicago |
| Request (what approvals read) | Check me in for my flight to |
| Push | `/?offer=offer-1029-124816-9e19`, 0.155 s after the offer |
| Task | done on envoy-test, source web, routine skylark_check_in_flight |
| Result | seat: 14C; gate: B12; boarding time: 5:30 AM; boarding group: Group 3; flight: SL 482 |
| Trigger → offer | 2.25 s |
| Yes → done | 6.1 s |

## Approvals

- tap "Confirm check-in" in com.skylark.air (routine skylark_check_in_flight v1): approved by your request

## Steps

- envoy-test is running: ok
- SkyLark signed in, the next trip not checked in yet: ok
- API copy up: ok
- the fake push service is the only subscription: ok
- proactivity: ok
- ask-mode trigger created: ok
- the trigger fired an offer: ok
- the offer: ok
- nothing started before the yes: ok
- the offer pushed (fake service, decrypted): ok
- you said yes (this copy's session): ok
- the task: ok
- Confirm check-in went through as your request: ok
- no approval waited for a person: ok
- the trigger keeps its credit: ok
- SkyLark: the trip is checked in: ok
- model calls: ok
