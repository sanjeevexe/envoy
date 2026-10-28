# Real-app test set: first results

Oct 27, 2026. 18 read-only workflows on `envoy-real` across shopping, food, Google's own apps, maps, the Play Store, media and the web. 11 are graded against ground truth (the phone's settings over adb, the Gmail API, published facts such as an address or a year), the rest by the answer's shape (a price, a rating); in the final evaluation (`eval/run_final.py real`) a person also reads each shape-graded answer against the screen it came from, and a right-shaped wrong value doesn't count (`eval/results/final/real_hand_checks.json`). Run with `eval/run_real_apps.py`. After any change to routines, rerun it with `--regression`: no agent runs and cached compile answers, so no model calls unless a repair runs. Full table: `eval/results/real_apps/report.md`.

The point of the set is to show where learning breaks before we try to improve it, so nothing below has been fixed yet.

## Where it stands

| Stage | Passed |
| --- | --- |
| 1. First run: the agent gives a right answer | 13/18 |
| 2. Compile: the trace becomes a routine | 13/18 |
| 3. Same input: the routine reruns right with no model call | 5/18 |
| 4. New input: right with a second input, no model call | 5/11 |
| Stopped by a bot check | 2 (Target, both workflows) |

Fully working, learned once and rerun with no model calls: Amazon search, Starbucks calories, DoorDash address, DoorDash search, Settings › Bluetooth. Partly working: Maps (right for the Space Needle, not for the Empire State Building) and Gmail search (right for "Security alert", wrong email for "DoorDash").

## Why things fail

Grouped by the stage where each workflow first failed.

**First run (5 misses)**
- **Placeholder taps (Muse Spark).** In 12 of the 18 runs the agent sent coordinate taps with made-up points ("tap_point 500,500", reason "Placeholder") even though every element was listed. That happened 52 times. Envoy rejects them, but each one costs a model call and a step, and in Settings and Gmail the agent got lost after them. Our prompt says tap_point is only for screens with no elements, but the action schema still offers it on every step. Likely fix: drop it from the schema when the screen lists elements.
- **The test phone itself.** YouTube is an outdated version that shows "update available" and returned server errors. Gmail's sync is off on the emulator, so the inbox looked empty. Both are test-bed problems, not Envoy's.
- **Right but unverified.** In Chrome the agent read "1889" from Wikipedia, but its own check couldn't see the text on the final screen, so the run isn't trusted and wasn't compiled.
- **Bot check.** Target's search hit Target's press-and-hold check.

**Rerun (8 misses among the 13 compiled)**
- **One-time screens baked into the routine (2):** the Play Store's interests onboarding and Calendar's welcome pages. The routine expects them on every run, and they never come back. This is the same class as Chipotle's location notice in Phase 2, so the earlier fix only covered part of it.
- **Wrong output from a list row (2):**
  - Gmail search: the output was anchored on "the row containing the query", so it took the second email (the one with "DoorDash" in its subject) instead of the newest one.
  - YouTube Music: the routine returned "Queen • 5:55 • 2.7B plays", because only " · " splits a row into parts and "•" doesn't.
- **No output learned (1):** Contacts. The answer "0 contacts" was inferred from "No contacts yet", which never appears on screen as a value, so the routine has nothing to read.
- **Navigation that doesn't replay (2):** Maps (a scroll step for one place) and Chipotle (the map and bottom-sheet store picker from Phase 2).
- **Bot check (1):** Target store hours, on every fresh launch.

## What the data suggests, when we come back to optimize

1. **Stop placeholder taps in the agent.** This is the biggest lever on first-run success and cost, and probably a small change.
2. **Make one-time screens optional when compiling.** Mark onboarding and dismissal steps ("Skip", "Got it", "Not now") as steps that may not appear again.
3. **Read list rows by structure.** Use the row's own parts (any separator: ·, •, commas) and the row's position, not "the row containing the input".
4. **Learn answers that are inferred, not shown** (zero contacts, no events), or have the routine report the screen state ("No contacts yet") instead.

Fix the test bed separately: update YouTube and turn on Gmail sync on the emulator.

All of Envoy's first runs used 214 model calls. Compiles reused Phase 2's cached answers for the 7 existing workflows and called Muse Wonder for the 7 new ones that had a verified run.
