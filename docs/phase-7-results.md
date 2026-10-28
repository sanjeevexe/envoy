# Phase 7 results: the final evaluation

**Status (Oct 27, night): measurement pass under way; not the final numbers.** The final numbers come from one run of every suite on the frozen commit, tagged `eval-final` on Nov 2. Until then this file records what the measurement passes found and what changed because of it. Plan: `prompts/phase-7-plan.md`. Report: `eval/results/final/report.md`.

## What was built

All of it is Envoy's own code (about 2,300 lines of Python in `eval/` and `backend/`, plus a small SkyLark change); matplotlib draws the charts.

| Part | Where | What it does |
| --- | --- | --- |
| One command per suite | `eval/run_final.py`, `eval/run_final.sh` | compile, systems, repeats, change, sizes, real, memory, safety, injection, interfaces, report; the script runs them in order with one emulator of ours at a time |
| Suite records | `eval/final_common.py` | Each suite's JSON says the commit (and whether it is the `eval-final` tag), the tier, the devices, and the model calls, tokens and dollars it caused, summed from the cost log by the suite's task-ID prefix so nothing else on the Mac is counted |
| The core set over seeded worlds | `eval/final_core.py` | Phase 1's 10 tasks, each asked about a booking, past trip or balance the routine has never seen; a world is one seed's SkyLark state (4 new bookings below the next trip, 3 new past trips spread through the list, a new balance). Every run fails on any side effect in the app the request didn't ask for |
| The three systems | `eval/final_core.py` | Full agent; fixed replay (recorded taps, a similarity check, the agent on a mismatch); Envoy routines through the product's own path (the matcher, then the routine with repair and the agent behind it, patches on trial) |
| Safety suite | `eval/final_safety.py`, `eval/capture_safety.py` | 20 irreversible and ~20 reversible controls on captured SkyLark and real-app screens, classified by the code signals, the model's label and the gate; live declines; planted instructions on SkyLark's screens (a fixture-driven notice card) and in the test inbox |
| Memory suite | `eval/final_memory.py` | Extraction on labeled emails, screens and screenshots; entity matching; stale facts served at four ages |
| Report | `eval/final_report.py` | `report.md`, the design's success targets measured, and the charts |

## What the evaluation found, and what changed (so far)

1. **The compiler dropped the answer of a routine with no steps.** "How many SkyLark miles do I have?" is answered on the screen the app opens to, so the agent's run had no actions. Outputs are read by steps, so the routine promised `miles` and could never read it: verification rejected it three times. A routine whose answer is on the first screen now gets one read-only step that carries its outputs. Test: `test_an_answer_on_the_start_screen_still_compiles_to_a_step_that_reads_it`.
2. **The product never patched its routines.** Local repairs became versions on trial only in the evaluation harness; the API's runner ran routines and discarded their patches. `routines/lifecycle.py` is now shared: a repaired run puts its patches on trial, the next run decides it (active if it runs with no model call, rolled back otherwise).
3. **Memory said "yesterday" for a fact seen 10 days ago.** The notes gave old facts a bare date ("Oct 27"), and the model turned it into a relative age against its own idea of today. Notes now give the age ("10 days ago (Oct 27)") and the answer step gets the current time.
4. **One-time screens stay optional.** Play Store's interests onboarding and Calendar's welcome pages were compiled as required steps, so the routine waited for screens that never return. Steps that only get past a one-time screen (Skip, Not now, Got it, or Wonder's own words for an onboarding or welcome step) compile as optional, and a run of optional steps is skipped when the first required step after them is ready.
5. **List rows use the app's own separators.** "Queen • 5:55 • 2.7B plays" was read whole because only Envoy's " · " split a row into parts; " • " and " | " split it too.
6. **The Contributor tier's model behaved differently.** On SkyLark's check-in the Contributor model backed out of an enabled Continue button again and again ("Wrong action placeholder - need correct JSON") and hit the step limit; the standard model did the same task in 10 actions. Measurement passes therefore run on the standard tier (a controlled comparison is in the report).
7. **Fixed replay takes irreversible actions without approval.** Replaying recorded taps bypasses the policy gate: on the original layout it checked in and changed the seat on the recorded booking (Denver) instead of the requested one, with no approval asked. That is the baseline's nature (Mobilerun-style macros), and part of why routines carry their own risk labels and gate.

## Not finished yet

- [ ] Every suite's measurement pass; fixes; the final run on `eval-final` (Nov 2).
- [ ] The Phase 6 gate on the real phone (the loan is due Oct 28 in the evening), and the phone's portability, stream and live-view numbers.
- [ ] AndroidWorld's results from the `androidworld` branch.
- [ ] Both copies of the design doc, `docs/meta-feedback.md`, `prompts/submission-notes.md`.
