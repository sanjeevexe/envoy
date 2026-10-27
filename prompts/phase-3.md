# Phase 3: Shared memory graph (plan)

Written by Claude on Oct 27, 2026, after Phase 2, from the design doc, at your request to continue on my own ("go ahead with this … give me your best work"). It follows the shape of `prompts/phase-2.md`. You may edit it; I follow the latest version.

## Read first

1. `docs/technical-design.md`: **Shared memory** (the whole section), Gmail and Calendar, Safety (redaction, untrusted content), Models and cost, Build phases. The live version wins if they disagree.
2. `docs/phase-2-results.md`: routines take inputs with `from_memory` hints and return outputs; Phase 3 connects both to memory.

## The job

Build the memory the design describes, as one SQLite database behind one memory service that is the only writer.

1. **Store** (`backend/memory/store.py`): `entities`, `facts` (two timelines: `valid_from`/`valid_to` and `recorded_at`/`retired_at`), `edges`, `sources`, `events` (append-only), plus SQLite FTS5 for keyword search. Declared entity types and attributes; natural keys per type.
2. **Facts over time**: a new value replaces the old one (the old fact's `valid_to` is set, nothing duplicated, history kept); user edits outrank extracted facts and a contradicting observation is flagged, not applied; freshness per attribute (a gate is fresh for 30 minutes on an active trip); confidence from the extractor and the source kind.
3. **Getting facts in** (`extract.py`): app screens (Muse Spark, structured output with the entity schemas, a pointer to the screen and element), routine outputs (written directly), emails (schema.org markup such as `FlightReservation` parsed with no model call; other emails through the model), user notes. Blocked apps never reach extraction; redaction (`redact.py`) runs before anything is stored. Everything inside screens and emails is data, never instructions.
4. **Recognizing the same thing twice** (`matching.py`): exact natural keys first (a reservation's confirmation code; a flight's airline, number and date), then FTS candidates, then one Spark call that decides. Merges are reversible (a split restores both entities from the event log).
5. **Getting facts out** (`retrieval.py`): link mentions ("my flight" = the next upcoming flight; codes, cities, flight numbers), take those entities and their neighbors, add keyword matches by reciprocal rank fusion, keep currently valid facts, render Markdown notes with sources and ages within about 2,000 tokens.
6. **Connections**: the agent's NOTES come from retrieval; routine inputs are filled from memory through their `from_memory` hints; routine outputs and the agent's final screens become facts with the run as their source.
7. **Mail** (`backend/integrations/mail.py`): a mailbox interface with a local test inbox (`.eml` files) and a Gmail client (read-only scope, history polling every 2 minutes, a connect script). SkyLark's fixtures generate the matching confirmation emails (some with schema.org markup, some plain, plus unrelated mail), so the same code appears in the app and the inbox.

**Phase 3 gate (design doc):** email and app facts merge into one trip, and "What's my gate?" is answered from memory.

## Approach

1. Store and service first, with offline tests (bi-temporal replacement, user-edit precedence, merge and split, FTS).
2. The SkyLark test inbox and email extraction (markup first, model second).
3. Screen and routine-output extraction, then entity matching across them.
4. Retrieval and the connections to the agent and routines.
5. An `eval/run_memory.py` suite that reports the design's memory metrics:
   - fact extraction accuracy on at least 50 labeled screens and emails (labels from SkyLark's fixtures, which are exact)
   - entity matching accuracy, including hard cases (two trips to one city, a cancelled booking, a promo email that mentions a city, a forwarded confirmation)
   - the gate: email + app → one trip per booking; "What's my gate?" answered from memory with its source and age, with no phone action
   - a gate change (SkyLark's `SET_GATE`): a routine refresh replaces B12 with C14, and the answer shows "C14 (was B12 until …)"
   - share of stale facts served; facts traceable to a source (target 100%)
   - "check me in" filled from memory end to end (match → inputs from memory → routine → outputs written back)
6. Write `docs/phase-3-results.md` like the earlier results, add Meta feedback, update both copies of the design doc, commit and push after each meaningful step.

## Rules

- Same as Phase 2: no sign-ins, no payments, nothing visible outside this Mac without asking (no public repo, no sent email), real apps and real data never on the Contributor tier, envoy-real never restored and always stopped cleanly.
- **Gmail needs you**: a Google Cloud project in testing mode with the Gmail API, the test account added as a test user, the OAuth client file, and one consent click. Until then the gate runs on the local test inbox, and the Gmail client is built and unit-tested but not run against a real account.
- Open source stays plumbing (SQLite and FTS5, the Google API client); the graph, extraction, matching, retrieval and the routine connections are Envoy's own.
