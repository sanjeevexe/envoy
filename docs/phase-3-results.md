# Phase 3 results: the shared memory graph

Oct 27, 2026. **Gate passed.** The gate was "email and app facts merge into one trip; 'What's my gate?' answered from memory".

On the phone, every booking's email and app facts merged into one trip and one flight; "What's my gate?" was answered from memory ("Gate B12, from the SkyLark app just now") with no phone action; when the gate changed in the app, a routine refresh replaced B12 with C14 and kept the history; 45 minutes later the answer warned it may have changed; and "check me in" ran with its trip filled from memory. Extraction was 99% right on 28 test emails and 98% on 12 app screens, with no wrong value stored. All of Phase 3 used 76 model calls and $0.45.

Reports: `eval/results/phase3/report.md` and the JSON next to it (`eval/run_memory.py`, `eval/memory_report.py`). The memory database itself (`data/memory.db`, `data/phase3/`) is not committed.

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
| Mail | `integrations/mail.py`, `scripts/connect_gmail.py`, `scripts/ingest_mail.py` | A local test inbox and a read-only Gmail client (recent messages, then the history API from the last history ID, kept between runs). |
| Test inbox | `eval/skylark_mail.py` | The confirmation emails SkyLark would send for the same bookings that seed the app: with markup or plain, forwarded, a seat change, a cancellation, promotions that mention a booked city, and a receipt, each with exact ground truth. |
| Tests | `backend/tests/test_memory_store.py`, `test_memory.py` | 18 offline tests (62 in all) with a scripted model. |

## Results

Reports: `eval/results/phase3/report.md`. Ground truth comes from the bookings that seed both SkyLark and the test inbox, so every number is exact.

### The gate on the phone (`eval/run_memory.py gate`)

**Passed, 18/18 steps** in 190 s. Seven bookings (Chicago is the next trip; a second Denver trip is cancelled), their 14-email inbox ingested, then each upcoming trip's details read in SkyLark by the gate routine with its input filled from memory.

| Step | Result |
| --- | --- |
| Routine inputs filled from memory | 6/6 (`trip_city` from the trip found in the inbox, with its source: "email from SkyLark Air, Oct 1") |
| One trip and one flight per booking, holding email and app facts | 6/6 (the app's screen matched the email's trip by confirmation code, its flight by number and date; the routine's outputs were anchored on that screen) |
| "What's my gate?" from memory | "Gate B12, from the SkyLark app just now", the next trip's gate, with **0 phone actions** |
| The gate changes in the app (B12 → C14) and a routine refreshes it | "Gate C14, from the SkyLark app just now"; history B12 → C14; the notes say "(was B12 until just now)" |
| 45 minutes later | "Gate C14, from the SkyLark app 45 minutes ago, but it may have changed" (the 30-minute freshness rule) |
| "Check me in for my flight" | the matcher chose the check-in routine and filled Chicago from memory's notes (1 model call); the routine checked in with no model call; seat, gate and boarding time were written back |
| Facts traceable to a source | 144/144 (175 events logged) |

### Extraction and matching

| Set | Items | Attributes right | Wrong values stored | Matching |
| --- | --- | --- | --- | --- |
| Large test inbox (`emails_large`) | 28 emails, 18 bookings | 212/214 (99%): markup 81/81, plain (Spark) 131/133 | 0 | 18/18 bookings → exactly one trip and one flight; 0 trips from promotions; the cancellation applied to its trip; two Denver trips kept apart |
| The gate's inbox (`emails`) | 14 emails, 7 bookings | 87/88 (99%): markup 27/27, plain 60/61 | 0 | 7/7; same hard cases passed |
| App screens (`screens`) | 12 trip-details screens | 82/84 (98%) | 0 | every fact kept the element it was read from |

That is 54 labeled emails and screens against the design's 50. Precision is 100% by construction as much as by the model: a value the model returns that is not in the source is dropped (none had to be).

### Cost

76 model calls, **$0.45**: 72 extractions (about $0.004 an email, $0.007 a screen), 3 answers and 1 routine match. Muse Spark at `low` throughout; no Wonder calls (routines were compiled in Phase 2).

## What the evaluation found, and what changed

1. **A fact seen twice lost its second source.** A forwarded confirmation only refreshed facts memory already had, so the forward was never recorded as a source (and my first extraction score undercounted it, 76% instead of 99%). Every observation now records its source (`fact_sources`), notes show "SkyLark app, today 9:41 AM (also email from SkyLark Air, Oct 12)", and deleting a source retires only the facts it alone supported.
2. **The same value, written four ways.** "SL1190" and "SL 1190", an ISO time and "6:10 AM", "Atlanta (ATL)" and "ATL" made the same fact look new. Keys and comparisons now normalize flight numbers, dates, times and airports; stored values stay as the source wrote them.
3. **A greeting is not a person.** "Hi Maya" in a seat-change email created a second Person. The extraction instructions now say so, and memory, which is one user's, folds a person whose names agree with the one person it knows.
4. **The sender line counts as source text.** A receipt's merchant appears only in the From line, and the "value must appear in the source" check dropped it until the header was included.
5. **Trips dated only through their flight.** Plain emails often put the date on the flight, not the trip; "the next upcoming trip" now falls back to its flight's date.
6. **A city can't tell two trips apart.** A routine's input `trip_city = Denver` is ambiguous with two Denver trips, so a routine's outputs are now anchored on the entities its own final screen resolved to (confirmation code, flight number and date).
7. **Routines didn't say where inputs come from.** Wonder left `from_memory` empty when the source run's city came from the request, so memory had nothing to fill. The bridge now infers it from the input's name (`trip_city` → the trip's destination, `flight_number` → the flight's number).
8. **"My gate" pulled in every gate.** The keyword part of retrieval also matched other flights with gates; the notes now say why each entity is there ("the next upcoming flight"), so the answer uses the right one.

## Honest limits

- **Gmail is connected, but the real inbox is nearly empty.** The test account (Google Cloud project `envoy-personal`, testing mode, `gmail.readonly` only) was connected on Oct 27. Its 6 emails (account notices, one DoorDash promotion) were read for $0.024: memory kept only the account holder's name and address and nothing from the promotion or security notices, which is right but is not a test of real confirmations. Every extraction number here is on the local test inbox, whose emails we generated: real airline emails are messier.
- **SkyLark's screens are clean.** Real apps' screens (Phase 2's checkpoint) will extract less cleanly; screen extraction was not tried on them in this phase.
- Matching is tested on one person's travel: trips, flights, one order. Places, reservations other than flights, loyalty programs and photos have types but little or no testing.
- The graph view, the WebSocket stream of events, Calendar and photos are later phases; the event log they will read is in place.

## Changes to the design

For the design doc's Shared memory section (applied in both copies):

1. **Every observation records its source** (`fact_sources`), not only the first: provenance shows every place a fact was seen, and deleting a source retires only what it alone supported.
2. **Values stay as the source wrote them; keys are normalized in code** (flight numbers, dates, times, airports), so checks against the source text keep working.
3. **Extracted values must appear in their source** (headers included) or they are dropped; answers from memory are rejected if their specifics aren't in the notes.
4. **Routine outputs are anchored on the run's own final screen**, since a routine's inputs (a city) may not identify one entity; routine inputs are filled through `from_memory` hints or, when the compiler left none, the input's name.
5. **Memory is one user's**: a person whose names agree with the one known person is that person; a greeting is not a person.

## Next

- **You (optional):** forward a few real travel or order confirmations to the test account; `scripts/ingest_mail.py` then reads only what is new. In testing mode Google ends the sign-in every 7 days: rerun `scripts/connect_gmail.py`.
- **Phase 4** (web app, live view, full approvals, MCP server): the MCP `memory_search` / `memory_get` / `memory_note` tools can now read this store; the event log is ready for the WebSocket stream and the graph view.
