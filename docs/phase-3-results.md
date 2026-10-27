# Phase 3 results: the shared memory graph

Oct 27, 2026. **Gate: ⟨GATE⟩.** The gate was "email and app facts merge into one trip; 'What's my gate?' answered from memory".

⟨HEADLINE⟩

Plan: `prompts/phase-3.md` (written by Claude from the design doc, at your request to continue unattended). Reports: `eval/results/phase3/report.md` and the JSON next to it (`eval/run_memory.py`, `eval/memory_report.py`). The memory database itself (`data/memory.db`, `data/phase3/`) is not committed.

## What was built

All of it is Envoy's own code (`backend/memory/`, `backend/integrations/mail.py`, about 1,650 lines). SQLite with FTS5 is only the storage; the Google API client is only plumbing for Gmail.

| Part | Where | What it does |
| --- | --- | --- |
| Types | `types.py` | 16 declared entity types with attributes; natural keys (a reservation's confirmation code; a flight's number and date; an order's merchant and number); freshness (a gate 30 minutes, a delivery estimate 10, a points balance 7 days); source reliability; attribute synonyms; normalizers so "SL1190" = "SL 1190", "Sat, Nov 14, 2026" = "2026-11-14", "6:10 AM" = "06:10", "Atlanta (ATL)" = "ATL". |
| Store | `store.py` | Entities, facts with two timelines (`valid_from`/`valid_to`, `recorded_at`/`retired_at`), edges, sources, every source that saw each fact, natural keys, an append-only event log with subscribers, FTS5. A new value replaces the old one and the history stays; the same value seen again only refreshes it; an older observation becomes history; a user's edit outranks extracted facts and a later contradiction is flagged, not applied. Merges are reversible (`split` replays the merge event backwards). Deleting a source retires only the facts it alone supported. |
| Extraction | `extract.py` | schema.org `FlightReservation`, `LodgingReservation` and `Order` markup parsed in code (no model); plain emails and app screens read by Muse Spark (low effort, structured output) with every value checked against the source text, so a made-up value is dropped; screen facts keep the element they came from; routine outputs written directly. |
| Redaction | `redact.py` | Card numbers (pattern + Luhn), sign-in codes, ID numbers and password fields removed before storing; finance, health, messaging and password-manager apps never reach memory. |
| Service | `service.py` | The only writer. Resolving: natural keys → links in the same source (a boarding pass's flight is already linked to its trip) → keyword candidates (a rule when the evidence is strong, one Spark call when it is thin) → new. A key that turns out to belong to two entities merges them. Routine outputs are anchored on the run's own final screen. |
| Retrieval | `retrieval.py` | "my flight / gate / trip" → the next upcoming one (cancelled trips skipped); cities, codes and numbers → named entities; neighbors two links away; keyword matches; reciprocal rank fusion; current facts only; Markdown notes with the source and age of every fact, "(was B12 until …)" for a recent change and a staleness mark past the freshness window. Answers come from the notes only and are rejected if their specifics aren't in them. |
| Bridge | `bridge.py` | Notes for the agent and the routine matcher; routine inputs filled from memory (the `from_memory` hint, else what the input's name means: `trip_city` → the trip's destination); routine runs written back. `scripts/run_task.py --with-memory` gives the agent its NOTES from memory and remembers its final screen. |
| Mail | `integrations/mail.py`, `scripts/connect_gmail.py` | A local test inbox and a read-only Gmail client (recent messages, then the history API from the last history ID). |
| Test inbox | `eval/skylark_mail.py` | The confirmation emails SkyLark would send for the same bookings that seed the app: with markup or plain, forwarded, a seat change, a cancellation, promotions that mention a booked city, and a receipt, each with exact ground truth. |
| Tests | `backend/tests/test_memory_store.py`, `test_memory.py` | 18 offline tests (62 in all) with a scripted model. |

## Results

⟨TABLES⟩

## What the evaluation found, and what changed

1. **A fact seen twice lost its second source.** A forwarded confirmation only refreshed facts memory already had, so the forward was never recorded as a source (and my first extraction score undercounted it, 76% instead of 99%). Every observation now records its source (`fact_sources`), notes show "SkyLark app, today 9:41 AM (also email from SkyLark Air, Oct 12)", and deleting a source retires only the facts it alone supported.
2. **The same value, written four ways.** "SL1190" and "SL 1190", an ISO time and "6:10 AM", "Atlanta (ATL)" and "ATL" made the same fact look new. Keys and comparisons now normalize flight numbers, dates, times and airports; stored values stay as the source wrote them.
3. **A greeting is not a person.** "Hi Maya" in a seat-change email created a second Person. The extraction instructions now say so, and memory, which is one user's, folds a person whose names agree with the one person it knows.
4. **The sender line counts as source text.** A receipt's merchant appears only in the From line, and the "value must appear in the source" check dropped it until the header was included.
5. **Trips dated only through their flight.** Plain emails often put the date on the flight, not the trip; "the next upcoming trip" now falls back to its flight's date.
6. **A city can't tell two trips apart.** A routine's input `trip_city = Denver` is ambiguous with two Denver trips, so a routine's outputs are now anchored on the entities its own final screen resolved to (confirmation code, flight number and date).
7. **Routines didn't say where inputs come from.** Wonder left `from_memory` empty when the source run's city came from the request, so memory had nothing to fill. The bridge now infers it from the input's name (`trip_city` → the trip's destination, `flight_number` → the flight's number).
8. **"My gate" pulled in every gate.** The keyword part of retrieval also matched other flights with gates; the notes now say why each entity is there ("the next upcoming flight"), so the answer uses the right one.
⟨MOREFINDINGS⟩

## Honest limits

- **Gmail is built but not run against a real account**: it needs your one-time Google Cloud setup and consent (`scripts/connect_gmail.py`). Every result here is on the local test inbox, whose emails we generated: real airline emails are messier.
- **SkyLark's screens are clean.** Real apps' screens (Phase 2's checkpoint) will extract less cleanly; screen extraction was not tried on them in this phase.
- Matching is tested on one person's travel: trips, flights, one order. Places, reservations other than flights, loyalty programs and photos have types but little or no testing.
- The graph view, the WebSocket stream of events, Calendar and photos are later phases; the event log they will read is in place.

## Changes to the design

⟨DESIGN⟩

## Next

⟨NEXT⟩
