# The template-like first `back` (found in 2b; Oct 28)

**What:** on SkyLark's home screen, the agent's first step sometimes returns `back` with a reason like "Placeholder to comply
with schema while intending to open My Trips - actually need tap My Trips", "Testing schema - invalid first move" or (the
before pass's P2) "Why this action", the schema's own description of `reason`. Back leaves SkyLark, so the run needs 2–3
steps to come back, or gets stuck: P2 in the before pass failed this way.

**How often (on the device):** 6 of 35 Envoy agent runs on SkyLark in this checkout tonight (2b: 2 of 6 cold, 3 of 6 warm,
0 of 6 warm-up; the before pass's P2). None of the 60 AndroidWorld episodes (they start with a launch).

**Replayed** (Spark, `low`, standard tier; the recorded first-step prompt of two 2b runs, 10 times per condition;
`replay_first_step.py`, `replay_fixes.py`; $0.13 in all):

| Condition | `back` returned |
| --- | --- |
| denver_lands, notes off / on | 1/10 / 4/10 |
| bags_boston, notes off / on | 3/10 / 4/10 |
| the same with one more rule in the instructions ("never return a placeholder, template or trial action…") | 2, 3, 4, 2 of 10: no better |
| bags_boston, notes on, **medium** effort | 2/10 |
| bags_boston, notes on, schema with `action` **before** `reason` | **10/10** |
| bags_boston, notes on, **re-asked once** when the `back` contradicts its reason | **0/10** (2 re-asks, both then tapped My Trips) |

So it isn't the notes (10/40 with notes off, 13/40 with them on, across conditions), more instructions or more effort don't
fix it, and making the model commit to the action before it explains it makes it certain: Spark falls back to `back`, the
first action in the union that needs no arguments, when it doesn't settle the action. Writing the reason first helps about
70% of the time.

**The fix (not made here; `agent/loop.py`):** treat a `back` as a rejected decision, as done and tap_point already are, and
ask once more with feedback, when its reason names another action or element, or talks of a placeholder, test, template,
schema or format, or when it would leave the goal's app on the first step. One extra step call, only when it fires.
The scripts read `$TMPDIR/notes-skylark.db` (2b's notes) and this folder's traces.
