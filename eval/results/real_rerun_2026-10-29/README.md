# Real-app passes, Oct 29: main against the AndroidWorld merge with the over-checking fix

All passes ran on envoy-real the same afternoon, standard tier, through `eval/run_real_rerun.sh`. Each was a fresh agent run and a fresh compile of the 16 read-only workflows (Target is left out because its bot check blocks emulators, so its two rows are carried over from Phase 7).

- **Main** is `53ab459`. Its agent code is the same as today's main.
- **After** is `736a6e4`. That's `53ab459` with `integrate/aw-final` (`fdce597`) merged in, plus AndroidWorld's over-checking fix (`b630d3f`, `9a573f8`).
- **The merge bar:** no workflow worse than main, row by row. Where repeats on the same commit disagree, the difference is called variance.

| Stage | Main | After |
| --- | --- | --- |
| 1. First run right | 14/18 | 14/18 |
| 2. Compiled | 14/18 | 15/18 |
| 3. Same input, no model call | 9/18 (11 with a repair) | 13/18 (14 with a repair) |
| 4. New input, no model call | 5/11 | 6/11 |

| Workflow | Main: first run, actions, same input, new input | After: first run, actions, same input, new input | |
| --- | --- | --- | --- |
| chipotle | step limit, 21 actions, –, – | pass, 10 actions, pass, pass | better |
| settings_bluetooth | pass, 13 actions, fail, n/a | pass, 3 actions, pass, n/a | better |
| gmail_search | pass, 3 actions, wrong, pass | pass, 3 actions, pass, pass | better |
| maps_address | pass, 4 actions, fail, fail | pass, 2 actions, pass, wrong | better (same input) |
| play_rating | pass, 2 actions, pass after repair, fail | pass, 1 action, pass, fail | better |
| chrome_wikipedia | error, 8 actions, –, – | right but unverified, 5 actions, compiled, pass after repair, fail | better |
| ytmusic_artist | pass, 6 actions, pass after repair, fail | pass, 3 actions, fail, fail | same failure, variance (below) |
| **contacts_count** | **pass ×3**, 0 actions each | **step limit, right but unverified, pass** | **worse** |
| amazon, starbucks, doordash, doordash_search, settings_version, gmail_newest, calendar_today, youtube_search | all pass on both | all pass on both | same; after takes fewer actions (starbucks 7 vs 21, doordash 1 vs 13, gmail_newest 1 vs 3, youtube_search 2 vs 4) |

- **contacts_count:** a real regression, though intermittent, and the over-checking fix does not reach it. The looping run's plan was "View the full contacts list". "Full list" sends the step model into the Contacts list filters, where it toggles filters until the step limit. The plans that answered at once said "read the list or its empty state". All three of main's plans were of the second kind. Over every run of the merged agent so far (last night's 1f1fc11 and today's three), the loop happened in 2 of 4. The cause is the planner's wording, not the done rule the fix changed.
- **ytmusic_artist:** on both commits the compiled routine's strict runs fail the same way ("outputs not found: artist"), and repair recovered it once on main but not after. That is the same compiler gap on both sides, not this merge.
- **Cost:** the six passes cost $2.19, including the key checks.

## The planner guard (`5fa03bf` = `736a6e4` + AndroidWorld's `edfab2b`), 15:11–15:35

A network outage to the Meta API, 15:29:39–15:34:46 ET (37 calls with "APIConnectionError: Connection error"), spoiled the end of this round:
- in the real-app pass (`guard/`), ytmusic_artist and chrome_wikipedia, and both extra contacts runs (they failed at the key check, so there are no folders for them);
- on SkyLark (`skylark_guard/`), the end of systems, the 9 extra check-ins and the planted-text screens.

What stands:

- **Real apps, all 16:** first run 12/18, compiled 12/18, same input 8/18 (9 with a repair), new input 5/11. Leaving out the two rows the outage spoiled, two misses are real.
  - **contacts_count looped again for 25 steps.** The plan was clean ("Open the Contacts app / View the contacts list / Read the number of contacts shown"), so the guard did its job on the plan. But step 1 reasoned "Verify if filters hide contacts before concluding count". The step model over-verifies on its own: 3 loops in 5 merged runs since Oct 28, against 0 of 3 on main.
  - **doordash failed.** At step 5 the agent labelled opening "Addresses · 1 location" irreversible and asked for an approval, which the read-only suite declines. That's the same over-caution as SkyLark's extra "Check in" approval. Main passed it, and so did `736a6e4` this afternoon (1 action).
- **SkyLark:** compile 10/10, all on the first attempt. Systems before the outage: agent 14/14 and routines 14/14, no side effects.

Not merged: the merged agent still fails the bar on real apps, at the step level.
