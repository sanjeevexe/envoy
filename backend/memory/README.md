# memory

The shared memory graph (design doc, Shared memory): one SQLite database behind one writer. Every fact records its source and two timelines; the same trip seen in an email and in the app becomes one entity.

| File | What |
| --- | --- |
| `types.py` | Entity types and attributes, natural keys (a reservation's confirmation code; a flight's number and date), freshness rules, source reliability, attribute synonyms, `from_memory` paths, date/time/airport normalization. |
| `store.py` | `MemoryStore`: entities, facts (`valid_from`/`valid_to` and `recorded_at`/`retired_at`), edges, sources, every source that saw a fact, natural keys, an append-only event log and an FTS5 index. New values replace old ones (history kept), older observations become history, user edits win and contradictions are flagged, merges are reversible (`split`). |
| `extract.py` | Facts in: schema.org markup in emails (no model), Muse Spark for plain emails and app screens (every value must appear in the source), routine outputs directly. |
| `redact.py` | Card numbers (Luhn), sign-in codes, ID numbers and password fields removed before storing; blocked apps (finance, health, messaging, password managers) never reach memory. |
| `service.py` | `MemoryService`, the only writer: resolve each extracted entity (keys → links in the same source → keyword candidates with a rule or one Spark call → new), write facts and links, merge entities that turn out to share a key. Routine outputs can be anchored on the run's final screen. |
| `retrieval.py` | Facts out: link mentions ("my flight" = the next upcoming flight; codes, cities, numbers), neighbors, keyword matches by reciprocal rank fusion, valid facts only, Markdown notes with source and age within about 2,000 tokens, stale facts marked; answers from memory, checked against the notes. |
| `app_notes.py` | App notes: short facts about how each app works, written by Envoy after its own runs (one Spark call reads the trace and proposes add / confirm / update / retire), filtered for personal and run data and for text that reads like an instruction or a permission (a planted notice), merged, capped at 15 per app, read into the agent's and repairs' prompts. `App note` entities with `task_trace` sources; never in memory's notes, answers, graph or alerts. `ENVOY_APP_NOTES=off` turns them off. |
| `bridge.py` | Memory ↔ routines and the agent: notes for the agent and the matcher, routine inputs from `from_memory` hints, routine runs written back. |
| `photos.py`, `ocr.swift` | Photos and screenshots (Phase 5): text read on the Mac with Apple's Vision (full pass + tiles), redacted lines blacked out before Muse Spark reads the image, values checked against that text, a `photo` source, the image deleted. `eval/run_photos.py` measures it. |

```bash
uv run --project backend python eval/run_memory.py emails     # extraction + matching from the SkyLark test inbox
uv run --project backend python eval/run_memory.py gate       # the Phase 3 gate on the phone
uv run --project backend python scripts/run_task.py "check me in" --skylark --approve-all --with-memory
```
