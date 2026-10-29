# App notes: before and after

Same tasks, same agent and profile; the only difference is the notes Envoy wrote itself during a warm-up on other tasks in the same app. Small samples (6 and 3 tasks), one run each: read the per-task rows, not just the totals.

## skylark

Profile `spark`, standard tier, agent only (no routines, no memory notes about the user).

| Pass | Success | Mean steps | Mean model calls | Mean seconds | Cost |
| --- | --- | --- | --- | --- | --- |
| cold | 6/6 | 2.83 | 5.0 | 10.7 | $0.056 |
| warmup | 6/6 | 1.33 | 3.33 | 6.5 | $0.038 |
| warm | 6/6 | 3.0 | 5.0 | 9.7 | $0.051 |

| Task | Cold | Warm | Steps cold → warm | Notes used (warm) |
| --- | --- | --- | --- | --- |
| boarding_denver | ok (done) | ok (done) | 2 → 4 | 6 |
| group_chicago | ok (done) | ok (done) | 4 → 1 | 6 |
| bags_boston | ok (done) | ok (done) | 2 → 5 | 6 |
| rewards_number | ok (done) | ok (done) | 1 → 3 | 6 |
| miami_date | ok (done) | ok (done) | 2 → 3 | 6 |
| denver_lands | ok (done) | ok (done) | 6 → 2 | 6 |

Notes Envoy wrote in the warm-up (its own words, after its filter):

- The flight date is on the trip detail screen in the Date row. (seen 2×)
- Seat assignment is on the trip detail screen in the Seat row. (seen 2×)
- The gate is on the trip detail screen in the Gate row. (seen 1×)
- Departure and arrival times appear at the top of the trip detail screen. (seen 1×)
- The upcoming trip appears on the home screen as Next trip; tapping it opens trip details. (seen 1×)
- Past trips are listed under My Trips; tap an entry to open its details. (seen 1×)
- The status tier is shown on the Profile screen in the Status row. (seen 1×)
- The rewards miles balance is shown on the Home screen. (seen 1×)

## real

Profile `spark`, standard tier, agent only (no routines, no memory notes about the user).

| Pass | Success | Mean steps | Mean model calls | Mean seconds | Cost |
| --- | --- | --- | --- | --- | --- |
| cold | 3/3 | 5.33 | 7.33 | 23.2 | $0.039 |
| warmup | 3/3 | 7.33 | 9.67 | 30.3 | $0.046 |
| warm | 3/3 | 5.67 | 7.67 | 20.1 | $0.038 |

| Task | Cold | Warm | Steps cold → warm | Notes used (warm) |
| --- | --- | --- | --- | --- |
| sb_mocha | ok (done) | ok (done) | 7 → 7 | 3 |
| dd_pizza | ok (done) | ok (done) | 2 → 3 | 2 |
| sb_flat_white | ok (done) | ok (done) | 7 → 7 | 3 |

Notes Envoy wrote in the warm-up (its own words, after its filter):

- The drink detail screen shows calories for the selected size. (seen 2×)
- Use Search Menu in Order to find a drink by name. (seen 2×)
- To browse without choosing a store, tap Skip then Yes on the skip confirmation dialog. (seen 2×)
- The first restaurant result can be a Sponsored listing. (seen 1×)
- Tapping a recent search term below the search bar runs that query. (seen 1×)

## Reading

**No measurable effect on these tasks, in either app.** Every task passed both times (SkyLark 6/6 → 6/6, real apps 3/3 →
3/3). Mean steps went 2.8 → 3.0 on SkyLark and 5.3 → 5.7 on the real apps; model calls and cost stayed level. The notes
were read on every warm run (6 on SkyLark, 2–3 on the real apps), and once a note visibly steered a run (DoorDash: "Tapping
a recent search term below the search bar runs that query"; the warm run tapped the recent "pizza"). The tasks were
already easy for Spark (1–7 steps), so there was little for a note to save. A fair test needs tasks where the agent gets
lost; this sample doesn't have them.

**What moved the per-task steps was not the notes.** In 5 of the 12 SkyLark eval runs the agent's first action was a
`back` with a reason like "Incorrect action format test", "Testing schema - invalid first move" or "Wrong template, need
correct tap action" (a sixth: "…actually tap Profile"), which leaves SkyLark and costs 2–3 steps to come back. It happened
in 2 cold runs (denver_lands, group_chicago) and 3 warm ones (bags_boston, boarding_denver, rewards_number), so it isn't
caused by the notes, and it explains every step change above 1 between the passes. It's Spark, at `low` effort, filling the
step schema like a template (the before pass's P2 reasons read "Why this action", the schema's own description of
`reason`) and picking `back`, the first action that needs no arguments. It shows up when a run starts inside the app; none
of the 60 AndroidWorld episodes (which start with a launch) has it.

**The notes themselves are good:** 8 for SkyLark and 5 for the real apps, all about where things are in the app ("The gate
is on the trip detail screen in the Gate row", "To browse without choosing a store, tap Skip then Yes on the skip
confirmation dialog"), none personal, none dropped by the filter, and note writing cost $0.03 (SkyLark) and $0.01 (real
apps). Traces: `traces/<phase>/<run>.jsonl` (each step's `app_notes` lists the note ids that call saw).
