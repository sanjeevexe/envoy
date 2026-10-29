# The contacts loop: a planner line (Oct 29, offline)

Phase 7's same-day real-app rerun of the answer fix (`coord/aw-rerun` `736a6e4` against `main` `53ab459`) still had
`contacts_count` loop once in 3 runs: 25 steps in the list's filters on a screen saying "No contacts yet". Every loop's
plan said "View the full contacts list". Every quick answer's plan read the list or its empty state, as all 3 of
`main`'s did. No run had app notes.

**Method.**
- All replays use `736a6e4`'s own prompts, from a separate checkout so they don't count against the held-out run's
  cost cap.
- Each case is replayed on the loop run's own first screen (`Envoy-realrun f7-1029142430`).
- The rebuilt inputs are within 4 tokens of the live plan call (1,018 against 1,014) and 23 of the live step call (2,724
  against 2,747).

**The line** (`edfab2b`, appended to the subgoals bullet of `PLAN_INSTRUCTIONS`): "For a question, read the answer where
the app shows it, an empty state ("none yet") included; plan no step that changes filters or settings, and no "full" or
"complete" list unless the goal asks for one."
- A first draft said "as it opens" and "views". Both were dropped, because AndroidWorld's questions must open a recipe,
  a note or a calendar day.

## Contacts (`contacts_guard_ab.py`, 30 per cell)

Plans that ask for a full list, or for filters:

| Run | Current | The line |
| --- | ---: | ---: |
| 1 | 5/30, 9/30 | 0/30, 0/30 (first draft) |
| 2 | 8/30 | 0/30 |
| 3 | 11/30 | 0/30, 0/30 |
| All | 33/120 | 0/90 final wording (0/60 first draft) |

Step 1 under the live "full" plan, opening filters:
- The current step prompt: 4, 9, 8, 7 and 8 of 30.
- The tried step clauses help little: 2, 2 and 3 of 30, or 9/30 for the minimal one.

That's why the line goes in the planner: it removes the plans that lead there.

Plan, then step 1 (each variant's own plan), opening filters:

| Run | Current | The line |
| --- | ---: | ---: |
| 1 | 2/30 | 1/30 (first draft) |
| 2 | 0/30 | 0/30 (with a step clause) |
| 3 | 1/30 | 0/30, and 0/30 with a step clause |

**Real apps, fresh plans** (`realapp_ab.py`, 8 each):
- Contacts answers at once: 6/8 and 7/8 on the current prompts, against 8/8 with the line.
- Calendar answers at once: 8/8 against 7/8.
- DoorDash taps the address: 7/8 either way.

## What the line could break (`guard_suite.py`)

- **SkyLark check-in plans whose first step offers Home's "Check in" for another trip** (f93ce08's case): 5/120 on the
  current prompts, 4/120 with the line. For the next trip itself, where the button is right: 47/60 and 54/60.
  - The current prompts' 5/120 differs from 773536a's 0/40 for the same case. So f93ce08's line isn't airtight on
    `736a6e4`, with or without this line.
- **AndroidWorld's 25 question tasks, plan then step 1:**
  - plans with a filter, settings or sort step: 5/125 → 1/125;
  - a premature answer at step 1: 0/125 both ways (every first step launches the app).
- **The step prompt is untouched**, so the safety probe, the irreversible-step replays and the answer steps can't move.

## Step clauses tried and dropped

- **"A list answers as the app shows it (scroll it if it goes on), even when the plan says the full or complete list:
  don't open its filters, sorting or settings to check it."**
  - Under a full plan: 21/90 → 7/90.
  - But it changed final answer steps: 74 → 63 of 90 the same. Partly rephrasings ("Android 15"), partly scrolls before
    answering AndroidWorld's calendar lists (2/5), and the real calendar tapped the day 4/5 instead of answering.
- **The minimal "…, even when the plan says to view the full or complete list"** didn't help under a full plan (9/30
  against 7/30).

## Where "the full list" comes from (`plan_attr.py`, 40 plans each)

The planner alone, on the loop run's first screen, counting plans that ask for a full list or for filters:

| Planner | Full/filter plans |
| --- | ---: |
| `main` `53ab459`'s own prompt, schema and inputs | 1/40 |
| `736a6e4` | 7/40 |
| `736a6e4` without the APPS input | 9/40 |
| `736a6e4` without the TODAY input | 5/40 |
| `736a6e4` without either input | 4/40 |
| `736a6e4` without f93ce08's line | 6/40 |
| `main`'s prompt text, `736a6e4`'s inputs | 4/40 |
| `main`'s prompt text and inputs, `736a6e4`'s schema and adapter | 3/40 |

- No single change from the 13 or the follow-ups explains it. Removing any one leaves 4 to 9 in 40, against `main`'s 1.
- The rise is spread across the planner's inputs, prompt and schema, as the wrong-route rise f93ce08 fixed was.
- So the targeted line is the fix, not reverting one change. In all runs, `736a6e4` makes such a plan 40 times in 160.
- This attribution cost $0.72.

Cost at standard prices: $8.88 for the replays above, plus $0.72 for this attribution.
