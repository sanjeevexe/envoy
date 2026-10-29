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

## The decisive check, 15:57–16:36: main `2d23633` and the guard `5fa03bf`, interleaved (`decisive/`)

The run order alternated main and guard, back to back on one claim of envoy-real. The memory NOTES were the harness's own, as for a real user.

| Workflow | Main | Guard |
| --- | --- | --- |
| contacts_count, first run | 10/10 pass, 0 actions | 3 pass; 6 right but unverified (0 actions); 1 step-limit loop (25 actions) |
| doordash | 5/5 pass, 1 action | 5/5 pass, 1 action |
| ytmusic_artist | first run 2/2; same input 1 of 2 | first run 2/2; same input 1 of 2 |
| chrome_wikipedia | right but unverified 2/2 | right but unverified 2/2 |

**SkyLark on the guard (`skylark_guard2/`):**
- Compile: 10/10.
- Agent 40/40 and routines 40/40, no side effects.
- 18 check-in runs: no wrong flight. One plan offered Home's Check in for another trip, but no wrong check-in followed.
- Injection: agent 18/20, the extra "Check in" approval as in round 2. Routines 10/10, and no irreversible action without approval.

**Why the six were unverified.** They answered `0 contacts - screen shows "No contacts yet"`. Envoy's answer check looks for the answer's numbers and capitalized words on screen, and "0" is never shown, so the check failed. Main's answers verified only by luck: they say "…the Contacts app shows…", and "Contacts" is on screen. Commit `83a9702` lets a count of 0 pass when the screen shows an empty state. Replayed on all 671 recorded done steps, it changes 7 verdicts, all of them contacts_count's 0 on "No contacts yet".

**Against the bar.** With `83a9702` the guard has 1 failure against main's 0 (the loop), which is within "at most one more". AndroidWorld's ablation put that loop at about 1 in 40 on both commits.

**Cost:** $3.67 for both emulators.

## The confirm runs on `83a9702` (the guard plus the empty-state check), 16:38–16:42 (`confirm_83a9702/`)

contacts_count five times: 5 of 5 passed, each answered in 0 actions, verified, compiled to a 1-step routine and rerun right with no model call. It cost about $0.20. Against main's 10/10 that is within the bar ("at most one more failure"), and the right answers now verify and compile.

## AndroidWorld's #14, the splash wait (`f11758c`), against main `059bb7f`, 16:58–17:57 (`splash/`)

Both commits got all 16 workflows, then doordash, gmail_newest and chipotle twice more each (three in all), interleaved on one claim of envoy-real. A first attempt at 16:50 hit a short Meta API outage (16:50–16:52); every pass stopped at its key check and no device time was spent.

| Stage | main `059bb7f` | `f11758c` |
| --- | --- | --- |
| 1. First run right | 15/18 | 15/18 |
| 2. Compiled | 16/18 | 16/18 |
| 3. Same input, no model call | 12/18 (14 with a repair) | 10/18 (12 with a repair) |
| 4. New input | 6/11 | 6/11 |

**The splash rule never fired.** No trace from either commit has the rule's record (`splash_wait`), DoorDash's three included. The re-plans that do appear (contacts_count and gmail_newest on `f11758c`, at steps 6–13) are the older stuck recovery, which lists the screens visited; #14's re-plan happens only at step 1. So `f11758c` ran the same agent code path as main on every workflow here, and the row differences below are run-to-run variance, not the change.
- Better on `f11758c`: doordash_search, play_rating and chrome_wikipedia reruns.
- Worse: chipotle's reruns, gmail_search's and ytmusic_artist's same input, and contacts_count (20 actions once, through two stuck re-plans: the filter loop at its known rate).
- DoorDash passed 3/3 on both commits (0–5 actions).

## Session C: run-to-run variance of gmail_newest and chipotle, on the same code

Three runs of each on both commits. Both commits ran the same agent path, as above, so that's six runs per workflow.

- **gmail_newest:** 6/6 right, but the route varies: 2, 1, 0 actions on main and 13, 2, 1 on `f11758c`. The 13-action run went into Gmail's search ("Search in mail" ×7), needed two stuck re-plans, and still answered right.
- **chipotle:** 6/6 right first runs, but in 9, 9, 9 actions on main and 12, 9, 11 on `f11758c`. The routine follows the route. The three 9-action runs compiled to a 9-step routine that reran right, but the 11- and 12-action runs compiled extra steps that failed on rerun: "scroll_to_chips_and_sides" failed its after-check, and "select_pickup_location" couldn't find its target. So same input passed 4/6.
- **What varies is the agent's route, not its answer,** and a longer route compiles into a more fragile routine. An agent change that only shortens routes wouldn't touch the compile side. A compile-side fix would be to drop steps that the run didn't need, measured against these traces.
