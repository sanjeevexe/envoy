# Phase 2 results: app routines

Oct 27, 2026. **Gate passed.** The gate was "a routine works on a new booking (new inputs) and recovers from an injected UI change (SkyLark variants 1–3)".

- **New bookings:** compiled routines succeeded on **30/30 bookings they had never seen, with 0 model calls** (median 3.3 s), and 18/18 more for routines compiled with IDs hidden.
- **Injected UI changes:** **21/21 recovered on variants 1–3** (7 routines × 3 layouts) and **18/18 more on two harder layouts** we added (hidden IDs; renamed labels and hidden IDs). A moved button needed nothing; renamed labels were carried by the relaxed match with no model; an extra screen took one local repair (about $0.005). Every patched version passed its trial replay, then ran with no model calls, and still ran on the original layout.
- **Against the full agent** on the same requests: **7 model calls against 242 (97% fewer)**, median **4.2 s against 11.7 s**, no cost against about a cent per request. Fixed replay (recorded coordinates, like Mobilerun macros) acted on the wrong booking or answered from the wrong one in 14 of 24 cells on the first four layouts.
- **Matching** requests to routines: 12/12. **Real apps:** Amazon, Starbucks and DoorDash routines rerun in 6–12 s with no model calls, on a second input too; Chipotle's does not; Target's store-hours routine compiles correctly but Target shows a bot check on most fresh launches, so it can't run unattended.
- **Phase 2 used 859 model calls and $3.48**, about half of it Muse Wonder compiles (35 calls, many of them recompiles while the compiler was being fixed).

Full tables: `eval/results/phase2/report.md` (generated from the JSON next to it by `eval/routines_report.py`). The final numbers come from one run of every suite on the finished code (`eval/run_phase2.sh` for compiling, then `eval/run_phase2_final.sh`). Routines: `data/routines/` (the library), `eval/results/phase2/compiled*/` (as compiled), `eval/results/phase2/library/` (one library per injected-change experiment, with patched versions, their status and before/after screenshots of each repair).

## What was built

All of it is Envoy's own code (`backend/routines/`, about 2,850 lines); no routine, macro or workflow library is used. PyYAML (MIT) reads and writes the files.

| Part | Where | What it does |
| --- | --- | --- |
| Routine format | `model.py` | The design doc's YAML: name, app, version, intent, typed inputs with `from_memory` hints, outputs, steps (intent, before-checks, action with a multi-attribute locator, after-checks, risk, optional `extract`), `scroll_until`, element-anchored `swipe`, `{{slot}}` templating. |
| Locators | `locators.py` | Score every listed element on resource ID, label, description, field label, type, class, parent and sibling text, list membership and position. STRICT 0.80 / RELAXED 0.60 / MARGIN 0.08, tuned on SkyLark. `text_has` is a hard filter for input-based choices; data in IDs becomes a glob (`trip_row_*`). Two roles: a **check** needs text evidence and the same element type; a **target** may lean on ID, type and position. Visual crops stay a stub. |
| Checks | `checks.py` | Evaluated in code: app in front, element present or absent, text visible, field value (read with get_text when the dump can't show it), toggle state, screen changed, signature similarity. Written automatically by diffing each step's before and after trees. |
| Compiler | `compiler.py` | Trace → routine: only verified runs; cleanup (pop-ups, dead taps, rejected actions, back-tracks; scrolls become `scroll_until`); generalization with Muse Wonder (inputs, fixed text, booking data, outputs), checked deterministically; input witness checks; outputs; verification by replay. |
| Executor | `executor.py` | Before-checks (wait up to 5 s) → locate → the policy gate (irreversible always asks) → act → settle on the after-checks themselves. Fallback ladder: wait and retry → relaxed match → pop-up handler → local repair (≤2 model calls per step, ≤5 per run) → full agent → ask the user. No model calls while checks pass. |
| Patching and versions | `store.py` | Repairs become candidate patches (new locator, rewritten checks, inserted, replaced or removed steps) saved as a version on trial, replayed at once from a reset snapshot, then activated or rejected (rollback). Run history and the recompile flag (more than half of the last 6 runs failed). |
| Matching | `matcher.py` | App → intent patterns → description similarity → one Muse Spark call that confirms and fills inputs from the request and notes (values must appear there). |
| SkyLark | `testapps/skylark`, `eval/skylark_routines.py` | A booking generator for new inputs (seeded through fixtures, below Home's "Next trip"), and two harder layouts: **4 hidden IDs** (no test tags, like an obfuscated release) and **5 renamed labels + hidden IDs**. |
| Evaluation | `eval/run_routines.py`, `baselines.py`, `tune_locators.py`, `run_matching.py`, `run_real_apps.py` | The suites below, the fixed-replay baseline, threshold tuning, matching, and the real-app checkpoint. |
| Tests | `backend/tests/test_routines.py` | 20 offline tests (43 in all) on real SkyLark screens and a real agent trace with Wonder's answer cached. |

## Results

Ground truth is SkyLark's real state (the right trip checked in, its seat changed, its known traveler number saved, and no other trip touched) or the returned outputs, checked on word boundaries. Model calls ran on the standard tier.

### Compiling (`run_routines.py record` + `compile`)

Six source runs by the full agent on the Denver booking (2–12 actions, 4–14 calls, $0.007–0.022 each). Each was compiled by Muse Wonder ($0.04–0.07, about 14 s) and verified by replay on the same booking and on one it had never seen; only routines that passed both entered the library.

| Routine | Steps | Inputs | Outputs |
| --- | --- | --- | --- |
| `skylark_air_check_in_flight` | 9 | trip_city | seat, gate, boarding_time |
| `skylark_change_seat` | 7 | trip_city, desired_seat | seat |
| `skylark_add_known_traveler_number` | 5 | trip_city, known traveler number (from memory) | known_traveler_number, confirmation_code |
| `skylark_get_flight_gate` | 3 | trip_city | gate |
| `skylark_check_flight_status` | 3 | flight_number | status, route, date, gate, departure_time |
| `skylark_lookup_trip_destination` | 3 | trip_confirmation_code | destination |
| `skylark_check_in_flight` (Phase 1's trace, next trip only) | 6 | trip_city (must be the trip on Home's card) | seat, gate, boarding time and group, flight |

The same six were also compiled from runs on the hidden-ID layout and one from the extra-screen layout. All passed verification. Verification rejected 8 compiled routines over the phase: 2 from bad Wonder answers, 1 from the back-track bug, and 5 whose outputs couldn't be read without IDs (all fixed, below).

### New inputs (`new-inputs`)

| Routines | Runs | Success | Model calls | Median time | Slowest |
| --- | --- | --- | --- | --- | --- |
| Compiled on the original layout, run on it | 30 (6 routines × 5 bookings, 1 of them the next trip) | **30/30** | 0 | 3.3 s | 5.8 s (a seat change that scrolls) |
| Compiled with IDs hidden, run with IDs hidden | 18 (6 × 3) | **18/18** | 0 | 3.3 s | 6.2 s |

### Injected UI changes (`variants`)

Each experiment: the routine meets the changed layout on a new booking (repair and the agent allowed); its patches become a trial version, replayed at once on another new booking with no repair or agent allowed, then activated or rejected; the active version runs on a third booking; a patched version runs back on the original layout.

| Change | Experiments | Recovered | Saved by | Model calls | Median time | Patches | Trial passed | Patched version alone, 0 calls | Original layout still works |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1: moved button | 7 | **7/7** | nothing needed ×6, local repair ×1 | 2 | 3.2 s | replace ×1 | 1/1 | 1/1 | 1/1 |
| 2: renamed labels | 7 | **7/7** | relaxed match ×7 | 0 | 4.0 s | locator ×5, check ×12, post ×2 | 7/7 | 7/7 | 7/7 |
| 3: extra screen | 7 | **7/7** | nothing needed ×5, local repair ×2 | 2 | 3.3 s | insert ×2 | 2/2 | 2/2 | 2/2 |
| 4: hidden IDs | 6 | **6/6** | relaxed match ×6 | 0 | 4.3 s | locator ×6, check ×7 | 6/6 | 6/6 | 6/6 |
| 5: renamed + hidden IDs | 6 | **6/6** | relaxed ×4, local repair ×2 | 3 | 6.2 s | locator ×16, check ×19, post ×1 | 6/6 | 6/6 | 6/6 |
| Extra screen removed (compiled on variant 3, run on the original) | 1 | **1/1** | relaxed (the screen was skipped) | 0 | 7.7 s | remove ×1 | 1/1 | 1/1 | 1/1 |
| Renamed + hidden IDs (compiled with IDs hidden) | 6 | **6/6** | relaxed ×4, local repair ×2 | 3 | 4.1 s | locator ×11, check ×2 | 6/6 | 6/6 | 6/6 |

Every patch kind the design names appeared and was verified: a new locator, an updated or rewritten check, an inserted step (the extra review screen), a replaced step (the Home "Check in" button gone in variant 1: "tap the trip card, then Check in"), and a removed step (the review screen gone). Variants 1 and 3 touch only check-in, which is why most routines needed nothing there.

### Three systems on the same requests

One request per routine family on a booking none of the systems was built from (the routine row on variants 1–5 is its first run on the changed layout, before any patch).

| Layout | Full agent | Fixed replay | Envoy routine |
| --- | --- | --- | --- |
| 0: original | 6/6 · 5.5 calls · 12.1 s | 0/6 (6 on the wrong booking) · 3.6 s | **6/6 · 0 calls · 2.8 s** |
| 1: moved button | 6/6 · 6 calls · 12.8 s | 3/6 (3 wrong) · 14.7 s | **7/7 · 0 calls · 3.2 s** |
| 2: renamed labels | 6/6 · 5.5 calls · 11.7 s | 0/6 (6 wrong) · 3.5 s | **7/7 · 0 calls · 4.0 s** |
| 3: extra screen | 6/6 · 5.5 calls · 10.7 s | 1/6 (5 wrong) · 3.5 s | **7/7 · 0 calls · 3.3 s** |
| 4: hidden IDs | 6/6 · 6 calls · 13.9 s | 6/6 (all handed to the agent) · 15.0 s | **6/6 · 0 calls · 4.3 s** |
| 5: renamed + hidden IDs | 6/6 · 6.5 calls · 15.0 s | 6/6 (all handed to the agent) · 15.9 s | **6/6 · 0 calls · 6.2 s** |

Medians per cell. Across all of them, **routines used 7 model calls against 242 for the full agent (97% fewer)**, a median of 4.2 s against 11.7 s, $0.00 against about $0.01 per request. Fixed replay is fast when it acts, but it replays the Denver booking's taps and text whatever the request says; it only succeeds by handing the whole task to the agent when the screen looks different.

### Locators (`eval/tune_locators.py`)

8,268 cases: 24 routine locators against recorded SkyLark screens from all layouts, scored with and without IDs. Chosen: **STRICT 0.80, RELAXED 0.60, MARGIN 0.08**. With IDs, the right element always wins at strict on unchanged screens, 95–100% of renamed elements are recovered at relaxed, and no wrong element wins anywhere. Without IDs, renamed buttons are recoverable without a model 76% of the time, and a check that names one button ("Check in") can't tell two screens apart, which is why compiled checks pair a title with the button.

### Speed

A routine step costs about 0.3–0.5 s of device time: two reads where the target sits still, the tap, and two passing reads of the after-check (settling on the checks themselves instead of a generic quiet window). Check-in (9 steps) runs in about 3.8 s; a 10-step routine would be about 5 s, well under the 30-second target.

## Real-app checkpoint (envoy-real, read-only)

Read-only workflows on the long-lived real-app emulator (never snapshot-restored, stopped cleanly), on the standard tier. Every approval was declined by the script and nothing was ordered or signed in to. Each workflow ran once with the full agent; its trace was compiled and the routine rerun from a fresh app launch, with the same input and with a second one.

| App | Agent, once | Routine reruns (0 model calls unless noted) | What broke, and what changed |
| --- | --- | --- | --- |
| **Amazon** (guest): search, first result's price | done: 2 actions, 4 calls, 23 s, $0.010 ("$13.49") | ✅ "AA batteries" 8.9 s → $13.49 · ✅ "USB-C cable" 9.5 s → $15.49 | Typing with Enter got a field check that can't hold after the search; results load after the step settles; "the first result's price" has no label or ID. **Fixed** (findings 7, 8, 10). The first product's title had nothing stable to anchor on, so that output is dropped at compile time. |
| **Starbucks** (guest): calories of a drink | done: 7 actions, 9 calls, 26 s, $0.013 ("190 calories") | ✅ Caffè Latte 9.1 s → 190 calories · ✅ Caramel Macchiato 9.2 s → 250 calories | Typed "Caffe Latte" vs shown "Caffè Latte"; two rows containing the input; a "- calories" placeholder read before the number loaded. **Fixed** (findings 7, 9). |
| **Chipotle** (guest): price of a menu item | done: 14 actions, 18 calls, 47 s, $0.031 ("$5.25") | ❌ without repair (11.8 s) · ❌ with repair (3 calls, 57 s) | One-time screens (a location notice, Android's permission prompt) were baked into checks; **fixed** (findings 6, 12). Duplicate zip suggestions are ambiguous, so the routine safely refuses and repair picks one. **Not fixed:** the store picker is a map with a bottom sheet the agent dragged by hand; the routine can't reproduce that state, so it never reaches the store list. A store's "CURRENTLY CLOSED" also ended up in a check (time-dependent text with no digits looks like UI text). |
| **Target** (guest): store hours | first try: handoff at launch, twice. After you cleared the check: done, 4 actions, 7 calls, 22 s, $0.017 ("8am open – 11pm close") | ❌ bot check again on the next fresh launch · checked on the recorded screens instead: ✅ store row found strictly, ✅ 8am open / 11pm close / 10/27 | Opens on a "press and hold" bot check (`HSBlockActivity`); the agent hands off, as designed: Envoy never attempts bot checks. The check came back on most fresh launches, so Target routines can't run unattended on an emulator. Two compile bugs found and **fixed** (findings 13, 14). |
| **Target** (guest): search, first result's price | handoff (bot check) | – | Not compiled: only verified runs are. |
| **DoorDash** (signed in): saved address | first try: failed after 19 actions (no address saved). After an address was set: done, 1 action, 3 calls, 7.8 s | ✅ 5.7 s | Opened on a mandatory "Search an Address" screen until an address was saved (with your go-ahead: a public address, Meta's 1 Hacker Way). The agent should have asked instead of trying for 19 steps. |
| **DoorDash** (signed in): search, first restaurant | done: 3 actions, 5 calls, 13 s, $0.009 ("Mountain Mike's Pizza") | ✅ "pizza" 12.4 s → Mountain Mike's Pizza · ✅ "sushi" 12.1 s → La Casa De Los Huevos (checked on screen) | The first compile returned the search term ("pizza", "sushi") as the restaurant: the output was anchored on "the element showing the query", and the search chip shows only the query. **Fixed** (finding 15). |

**What this says.** Where a real app's flow is a few taps and a typed search (Amazon, Starbucks), routines work as on SkyLark: one agent run (4–9 calls, 23–26 s) becomes a routine that reruns in about 9 s with no model calls, on new inputs too. Real apps broke routines in ways SkyLark never did: one-time screens, late content, accents, values with no labels, gestures, bot checks and setup gates. The fixes that generalize are in; map-and-sheet pickers need gestures and visual grounding, which this phase didn't build.

**Follow-up (Oct 27, after the address was set and Target's check cleared).** Three more compile/locate fixes came out of DoorDash and Target (findings 13–15). Recompiling all 19 routines from their cached compile answers (no model calls) changed only the two affected routines; the 14 SkyLark routines and Amazon, Starbucks and Chipotle compile identically, and the offline tests (67) pass.

## What the evaluation found, and what changed

Verification by replay earned its place: it rejected 8 bad routines before they reached the library. Each finding below led to a general fix, not a SkyLark-specific one.

1. **The "first card" trap.** The Phase 1 check-in trace used Home's "Check in", which always means the next trip. Compiled naively, the routine would have checked in Chicago when asked for Denver. Now an input that no action uses must be visible before the step that depends on it (an **input witness check**), and the routine's description says it only works for the next trip. On another trip it fails loudly and climbs the ladder.
2. **Back-tracks that weren't.** A run that checked in and then returned Home looked like a round trip, so cleanup dropped ten steps, and the routine "passed" its own checks without checking in. Verification's state check caught it. Back-tracks may no longer cross an effect (an approved or irreversible action, typing, a toggle) and must match layout as well as labels; a compile that loses the run's approved irreversible step is refused.
3. **Checks need text.** At the relaxed threshold, "the screen titled My Trips" also passed on other screens, because `screen_title` is on every screen and an ID plus type scores 0.57. Checks now need text evidence and the same element type; tap targets can still lean on IDs, which is how renamed buttons recover without a model.
4. **Words alone can't tell buttons apart.** "Check in" scored 0.98 against "Confirm check-in". A label found inside a longer one is now scored by coverage (0.78), and the ambiguity margin refuses to act when two candidates tie.
5. **Wonder's answers vary.** On a second compile of the same traces, Wonder numbered steps from 0 once and returned field names instead of values once; both answers fit the schema. The compiler now aligns step numbers, ignores identifier-like values and generalizes data-looking ID parts itself. Replay with a second booking rejected both routines before the fix.
6. **Pop-ups don't belong in checks.** A Chipotle step's after-check captured Android's location prompt; Android stops asking after a denial, so the check could never pass again. System dialogs and known interruptions are now excluded when checks are written.
7. **Late-loading content.** Amazon results and the Starbucks detail page render after the step settles. Outputs are now read from the screen the agent answered from, the executor keeps reading missing outputs for up to 5 s, and a value recorded as a number must be one ("- calories" is a placeholder).
8. **Values without labels or IDs.** "The first result's price" is read as the first list element shaped like the recorded value (`\$\d+\.\d+`); a value that is its own element is read after its label ("Seat", then "22F", once IDs are hidden); an output with no anchor at all is dropped at compile time rather than promised.
9. **Accents.** People type "Caffe Latte" where Starbucks shows "Caffè Latte"; text matching now folds accents, and an element that *is* the input outranks one that contains it ("Iced Caffè Latte").
10. **Typing with Enter is navigation.** A search box's "field holds the text" check fails once the results replace it, and a repair "fixed" that by going back. Submitting steps now get navigation checks.
11. **Removed screens are found one step earlier.** Skipping a step because the next step's target was visible skipped a needed Chipotle step. A dropped screen is now detected when the previous step's after-check fails and a later step is ready; that step is removed by patch, and its after-checks move to the step before.
12. **Over-specific checks.** When a navigation step's after-check fails but the next step is clearly ready, the run continues (rung 2) and the check is rewritten from what happened.
13. **A value several elements after its label** (Target's hours: "Today", "10/27", "8am open", "11pm close", each its own element with no ID). Only "the element right after the label" was supported, so opening and closing times were dropped and the routine reported the date. Outputs now record how many elements after their label they sit, stepping back over other values to the nearest fixed label.
14. **Identical list rows told apart by their place.** Target's store list rows share one ID and differ only by store name, which is booking data and so not kept: the first row (the saved store) and the second scored 1.00 and 0.99, so the strict match refused and a model repair picked it. When a locator has nothing but its ID and slot to go on and every tied candidate is a row with that ID, the row in the recorded slot is chosen if it is clearly nearest.
15. **A search term is not a result.** DoorDash rows read "Mountain Mike's Pizza, 9.2 mi away, …" with no ID; the compiler anchored the output on "the element showing the query", and on replay the search chip ("pizza") matched first. Outputs that lead a list row are now read by the row's shape (the value, then a fixed-shape detail such as "N mi away", numbers generalized) from the first matching row; and an input-anchored output never takes an element that shows only the input.

The two harder layouts (hidden IDs; renamed labels and hidden IDs) and the final reruns found eight more, all fixed in code and rerun:

13. **IDs that a screen doesn't show can't count against anyone.** With no test tags at all, every check that had an ID topped out at 0.57, below the relaxed threshold, so check-in fell to the full agent (12 calls, 31 s). A screen that exposes no usable IDs now ignores the ID attribute, which is what the no-ID tuning assumed. The same run then needed no model.
14. **Outputs without IDs or merged rows.** Without test tags, "Seat" and "22F" are separate elements and the output locator was ID-only. Outputs now fall back to their label and read the element right after it.
15. **A full-agent rescue was marked a failure.** When the agent took over (rung 5) and finished, the executor wrote to the run's already-closed trace and reported failed. Fixed; the run now counts as recovered by the agent.
16. **A weak after-check passed by itself.** A step whose only after-check was "the screen changed" was judged against nothing during repair, so it passed and the step was skipped untapped. Repair now judges it against the screen it started from.
17. **Repairs judged success too strictly.** After a repair on a changed app, the next screen's checks may only match at the relaxed threshold; repair now accepts that, so renamed labels with hidden IDs are fixed by one or two repair calls instead of the full agent.
18. **Patches copied booking data.** A relaxed match on a trip row copied that run's whole row label (city, date, code) into the patched locator and dropped an ID the screen hid; the patched version then failed on another booking. Patched locators keep their fixed text, globbed IDs and input filter.
19. **Patches forgot old labels.** A patch learned on renamed labels replaced the old label, so without IDs the patched routine failed back on the old layout. Patched locators now keep earlier labels (`alt_texts`).
20. **"Removed" steps became optional.** Deleting a step whose screen disappeared broke the patched routine on the layout that still had it; the step is now kept as optional, like inserted ones.

Two environment notes: the emulator hung twice on snapshot restores after dozens of them in one session (adb stopped answering; only killing the emulator process recovered it), so the final run resets SkyLark through its fixture hook, as Phase 1 did; snapshot restores were used for verification and trials before that. And a SkyLark debug broadcast failed once while the app was starting; the hooks now retry.

## Honest limits

- **SkyLark is our own app.** Its test tags make variants 1–3 gentle: renamed labels are carried by stable IDs, and the moved button and extra screen touch only check-in. Variants 4 and 5 (hidden IDs) are the harder test, and the real apps are the honest one.
- **Real apps are stateful.** Without snapshot resets, first-run screens (location notices, store pickers) get baked into routines and don't come back. Map and bottom-sheet pickers (Chipotle) didn't replay; that needs gestures and visual grounding, which this phase didn't build.
- **Target can't run unattended:** it opens on a "press and hold" bot check on most fresh launches (the agent hands off, by design). Its routine was checked on the recorded screens, not live. DoorDash works since an address was set.
- Visual-crop locators are a stub; portability across screen sizes and to a real phone is untested (Phase 3+).
- The full-agent baseline was run once per cell, not repeated; the variant experiments ran once each.
- The final run reset SkyLark through its fixture hook, not snapshots (see the environment note above); verification and trials used snapshot restores earlier in the phase without a problem.
- After a scroll, a list row can stop at the screen's edge and match only at the relaxed level (the trip lookup on new bookings); it still works with no model, but a short extra scroll would make it strict.

## Changes to the design

These change the design doc's App routines section (applied in both copies):

1. **Locators have two roles.** A check must show text evidence and keep its element type, since an ID alone is shared across screens; a tap target may lean on ID, type and position. Thresholds were tuned rather than taken from prior work: STRICT 0.80, RELAXED 0.60, MARGIN 0.08.
2. **Input witness checks.** An input that no action uses must be visible before the step that depends on it, so a routine learned on "the next trip" never acts on the wrong booking.
3. **Cleanup can't remove effects.** Back-tracks never cross an approved or irreversible action, typing or a toggle; a compile that loses the run's irreversible step is refused. Pop-ups never become checks.
4. **The compiler validates Wonder's answer in code** (step alignment, values vs names, data in IDs). Verification by replay with a second booking stays mandatory: it rejected 8 routines this phase.
5. **Settle on the after-checks.** Two passing reads plus a still target replace the generic 250 ms quiet window. About 0.3–0.5 s of device time per step on SkyLark, 9 s for a whole real-app routine.
6. **Removed screens** are detected at the previous step's after-check (a later step is ready), not by skipping a step whose target is missing. **Over-specific navigation checks** are accepted when the next step is clearly ready, and rewritten by patch.
7. **Outputs:** read from the screen the agent answered from, wait for late content, reject placeholders, and support a value some elements after its label, "the first list element shaped like the value", and a value leading a list row read by the row's shape. Repeated list rows that only their place tells apart are chosen by slot.
8. **Real apps are stateful.** With no reset, first-run screens must be optional, and a routine should start from a known screen (a fresh launch is not always one).

## Next

- Phase 3 (memory) is done: `docs/phase-3-results.md`. Routine inputs are now filled from memory and outputs written back.
- DoorDash's address is set and its routines work. Target's bot check returns on fresh launches, so Target stays a hand-off case; Chipotle's store picker needs gestures and visual grounding (Phase 6).
