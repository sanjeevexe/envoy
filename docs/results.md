# Results

**From the final evaluation.** All 10 suites ran on the `eval-final` tag (`cf78fa0`) on Nov 3, on the default `hybrid`
profile and the standard tier, for $11.68 at standard prices
([`eval/results/final/report.md`](../eval/results/final/report.md)). Every suite starts from a known state and scores with
code: the app's real state, or the answer on screen (its value where the truth is known, its shape where it changes
daily, like a price). Times and costs are medians, with the spread beside them
where the source gives one; dollars are at Meta's standard prices. AndroidWorld's runs are separate (below). Commits and
configs are in [the evidence appendix](#evidence-appendix). The design set seven success targets on Oct 26, before any
code; on the tag all seven were met, most on SkyLark
([the table](../eval/results/final/report.md#the-designs-success-targets)).

## Real apps

18 read-only workflows in apps Envoy didn't build (Amazon, Starbucks, DoorDash, Gmail, Maps, YouTube…): ask a question,
check the answer; nothing ordered, posted or changed. One pass on the `envoy-real` emulator. A new input applies to 11
of the 18.

| Stage | Passed |
| --- | --- |
| The agent's first run right | 13/18 |
| Compiled into a routine | 14/18 |
| Same input, no model call | 13/18 (14 counting a repair) |
| New input, no model call | 7/11 |

Target's bot check stopped both Target workflows; every row is in [`real.md`](../eval/results/final/real.md). Of the 11
answers graded only by their shape, a person read 3: all 3 right.

**The cost curve.** On the 13 workflows whose first run and same-input rerun both passed, the routine called by name
against the agent's first run:

| | Median (range) |
| --- | --- |
| The agent's first run | 5 calls (2–13), 19.59 s (8.49–52.82 s), $0.0376 ($0.0186–$0.0872) |
| Envoy's replay | 0 calls, 4.88 s (0.75–12.26 s), $0 |
| Compiling it, once (Muse Wonder) | $0.0455 ($0.0328–$0.0770) |

Asked in words instead of by name, Envoy's matcher adds one Spark call to pick the routine.

## "Make it a routine" on real apps

Run after the evaluation, on the tag, to a protocol fixed before it
([`eval/results/learn-agent-path/`](../eval/results/learn-agent-path/README.md)): an agent asked each of the same 18
questions over MCP, then "Make it a routine" was pressed on each finished task, and each saved routine was shared and
called back as a tool.
- **The agent path answered 14 of 18 right.** Over MCP, `run_task` tries the routine library first, so 6 of the 18
  were answered, or tried, by routines already in it.
- **"Make it a routine" saved 8 of 18: 8 of the 12 tasks that weren't already routines.** The other 6 ran an existing
  routine, and the button doesn't take a routine's task. Of the 4 not saved: Target's bot check; a harness slip that
  timed out target_search; calendar_today's empty-day answer, which couldn't be read back from its final screen; and
  chrome_wikipedia's replay, which stopped at an after-check.
- **Called back as tools:** the 5 same-input calls were right with 0 model calls in Envoy's replay, and the 3 new-input
  calls were right, 2 with 0 model calls (YouTube Music's took 1).
- **Learned cold, on a real account (Nov 4):** with the author's own Uber account, read-only and with no ride requested,
  the button saved `uber_check_uberx_price` from one finished agent task. Its next run took 11.33 s with 0 model calls.
  When Uber later showed an extra screen, it repaired that step with 1 model call, and the new version passed its trial
  in 12.81 s with 0 ([`index.json`](../data/routines/uber_check_uberx_price/index.json)).
- **Supplementary, outside the headline:** on a copy with an empty routine library, the 6 workflows the library had
  answered: the agent right 5/6, saved 5/6, new input right 3/5, all with 0 model calls in Envoy's replay.

## The posting batch

Declared before the tag ([`PROTOCOL.md`](../eval/results/showcase-batch/PROTOCOL.md)) and run once on it, Nov 3, on
Envoy's phone: the four posting routines (all v3), 10 attempts each, from a cold start, an open app or a saved draft,
with the test accounts. Every final button that was asked was declined, so nothing was posted. These numbers are for
this version, these workflows and inputs, one phone and one set of accounts, one afternoon
([`RESULTS.md`](../eval/results/showcase-batch/RESULTS.md); every attempt in `attempts.md`).

| Workflow | Reached the final button | …with every outcome check yes | Time to the final ask, median (range) |
| --- | --- | --- | --- |
| Reel with a library song | 7/10 | 7 | 59.6 s (55.6–111.8) |
| TikTok with a library sound | 10/10 | 10 | 60.6 s (57.6–69.7) |
| Short with a library sound | 5/10 | 4 | 41.5 s (40.4–116.9) |
| Story with a poll | 10/10 | 10 (the poll checked by eye) | 32.5 s (31.4–41.5) |

- **The outcome checks stopped 5 runs before the final button,** each missing something the post would have gone out
  without. Two Reels had lost their caption: closing the keyboard with Back sometimes cancelled Instagram's caption
  edit. Three Shorts never showed their song on the editor: YouTube's sound search didn't list "Flowers", "Watermelon
  Sugar" or "Levitating" as the routine looks for them.
- **The Short's misses have known causes.** Its song check stopped three runs whose song wasn't on YouTube's trending
  sounds, where "golden hour" is: a search-only check after the batch, on Envoy's phone and not measured in it, found
  that YouTube's sound search runs only when its suggestion is tapped, and v3 skips that tap
  ([`yt-song-fix-writeup.md`](../eval/results/showcase-batch/yt-song-fix-writeup.md)). One more, with another song, was
  finished by the agent, so its sound couldn't be checked. Two more, from a saved draft, stopped at YouTube's "Continue
  your draft video?" prompt.
- **The Reel's third miss:** Instagram's music search didn't show "Levitating", which the library check had found
  earlier, and the agent stopped at its step limit.
- **Model calls in Envoy's replay:** 95 over the 40 attempts, $1.0342. TikTok reads its drawn sound list by vision on
  every run, by design.

**After the batch, not part of it (Nov 3):** `instagram_reel_song` v4 (merged in `0d28e5a`) ends the caption edit with
Instagram's OK instead of Back, and types the caption again if it's empty before Share. On Envoy's phone, on a test
copy with every Share declined, 5 of 5 Reels from a cold start reached Share with clip, song and caption checked, at 0
model calls in Envoy's replay; TikTok 1 of 1, as a check that nothing else broke
([`index.json`](../data/routines/instagram_reel_song/index.json), v4).

The current version, v5, adds a hand-edited wait for the upload after Share; in its one run, on Nov 4, it finished with
0 model calls in Envoy's replay, in 95.8 s.

## SkyLark (our test app)

SkyLark is an airline app we built so every run can start from a known state and be scored by the app's real state.
Every number in this table is on SkyLark, except the 14 real-app saved screens in the safety row and the 36 real-app
targets in the drawn-buttons row, and the test inboxes in the memory row.

| What | Result | Source |
| --- | --- | --- |
| Against simpler approaches | 10 tasks on 4 layouts, 3 seeds each (120 per system). Envoy's routines 120/120 on the first try, 1 call, $0.00225, 7.6 s (6.9–8.9 s by layout). The agent every time 119/120 on the first try (120/120 within 3), 5 calls, $0.03235, 17.9 s (17.1–19.2 s by layout). A fixed replay of the same taps 38/120, and in 24 of those first tries it acted on another booking; Envoy's routines and the agent never did | [`systems.md`](../eval/results/final/systems.md) |
| Asking again | Request 1 (the agent, then the compile): 6.0 calls, 44.5 s, $0.0869. Requests 2–10: 90/90 right at 1 call (the matcher), 7.6 s, $0.0022; each request's median 6.7–8.9 s. 84% fewer calls (1.0 against 6.4 per request) | [`repeats.md`](../eval/results/final/repeats.md) |
| When the app changes | We changed SkyLark's layout on purpose, 50 times, over 5 kinds of change: recovered 50/50 (27 needed no fix, 17 a relaxed match or scroll, 2 a local repair, 4 the agent; 27 model calls in all), then 46/50 ran alone with no model call. 50 new inputs: 50/50 with no model call | [`change.md`](../eval/results/final/change.md) |
| Drawn buttons | On Oct 27 (Phase 6, before the final evaluation), on screens that are only pixels, SAM's boxes plus a Spark pick, with grounding where SAM's boxes missed, found 52 of 52 targets (16 canvas seats on SkyLark, 36 on real apps' saved screens) in each of two samples | [`docs/phase-6-results.md`](phase-6-results.md) |
| Screen sizes and Envoy's phone | SkyLark's 10 core routines on 3 new bookings each, on three emulator sizes and the Pixel 5: 30/30 on each, with no model call | [`sizes.md`](../eval/results/final/sizes.md) |
| Memory | Facts read from 62 labelled test items (emails, SkyLark screens, screenshots): 454 of 468 attributes right (97%), 0 wrong values, every fact traceable to its source. Stale facts served without a warning: 0 of 12; the right value in 24 of 24 answers | [`memory.md`](../eval/results/final/memory.md) |
| Safety | Irreversible controls on 20 saved screens (6 SkyLark, 14 real-app): 20 caught, all 20 by code rules alone (14 before this suite found its gaps, on the same screens); reversible controls flagged by code 0/22. 7 live runs declined at the approval: 7 held. Instructions planted on screens: the agent right in 20 of 20 runs and tried to follow them in 0; the routines 10 of 10, never. Irreversible changes without approval: 0 | [`safety.md`](../eval/results/final/safety.md), [`injection.md`](../eval/results/final/injection.md) |

## AndroidWorld (separate runs)

On Google's AndroidWorld benchmark (116 tasks in 20 open-source apps; seed 30, pass@1, standard tier), Envoy went from
**21 to 57 to 74 to 85 of 116 tasks (18.1% to 73.3%)** between Oct 28 and Nov 10, solving 89% of the easy tasks and 42%
of the hard ones in the last run. The last step changed only the agent's code (same model, profile, cost cap and
settings): a paired +15 −4 (p = 0.019), and on the held-out half, which its five changes weren't chosen on, 36 to 44 of
58 (+9 −1, p = 0.021). 73.3% is over twice the benchmark paper's best agent (GPT-4 Turbo, 30.6%) and above every
tree-only entry on the public, self-reported leaderboard (best 59.5%); Envoy reads the tree and adds a screenshot on
about 8% of steps. It's not like for like, and the board's top entries use frontier models with screenshots
([the comparison](androidworld-results.md#against-the-leaderboard)).

**It keeps improving, by a repeatable loop:** study the failures, ship general fixes rather than app-specific ones, and
check them on held-out tasks and on Envoy's own suites before they ship. We'll keep running it as Envoy grows, and each task
Envoy learns can then replay as a routine at a fraction of the cost (below).

| Run | All 116 | Held-out half (58) | Mean cost per task |
| --- | --- | --- | --- |
| Nov 9–10, the shipped default (`hybrid`) with five general changes (`3e557d1`, now on `main`) | **85 (73.3%)** | **44 (75.9%)** | $0.125 |
| Nov 3, the shipped default (`hybrid`) on `main` (`7ed4aa6`) | 74 (63.8%) | 36 (62.1%) | $0.125 |
| Oct 28, Spark profile: the agent with 13 general changes, chosen on the other half (the `androidworld` branch, `a80b976`) | 57 (49.1%) | 31 (53.4%) | $0.040 |
| Oct 28, before those changes (Spark profile, `main`) | 21 (18.1%) | 12 (20.7%) | about $0.04 |

- **The Nov 9–10 run** adds five general changes, chosen from the Nov 3 run's dev-half failures: the step count near the
  limit, replans that know what's done, scroll reports, row labels for unlabeled icons, and long text in parts. It is one
  run on one seed. AndroidWorld passed two runs that the agent itself ended as failed; counting only runs it finished,
  the held-out half is 43 of 58. Envoy's real-app, SkyLark and safety checks held
  ([`eval/results/androidworld/2026-11-09-push-all-3e557d1/`](../eval/results/androidworld/2026-11-09-push-all-3e557d1/README.md),
  [round 4](androidworld-results.md#round-4-nov-910-five-general-changes-on-the-shipped-default)).
- **The Nov 3 run** has agent steps on Muse Wonder, at about 3.1 times the cost per task of Oct 28. On the
  held-out half alone the change against Oct 28 (+8 −3, p = 0.23) is within run-to-run noise, and that half had already
  been run on Oct 28 and 29 and helped choose `hybrid` as the default
  ([`eval/results/androidworld/2026-11-03-hybrid-7ed4aa6/`](../eval/results/androidworld/2026-11-03-hybrid-7ed4aa6/README.md)).
- **The Oct 28 run** is the clean estimate of the 13 changes: the held-out half went from 12 to 31 of 58 against the
  agent before them (+20 −1, p < 0.0001). They have been part of Envoy since Oct 29.
- **Routines, by cost (Oct 28, Spark profile):** the 22 of 59 routines Envoy compiled from its solved runs that redid
  their own seed-30 task did 55 of 69 new-seed instances at a median 1 model call, $0.0021 and 8.3 s; the full agent
  did 63 at 6 calls, $0.0122 and 19.0 s. Pairing each routine miss with the agent's own run on that instance gives 67
  of 69 (computed, not run) ([`docs/androidworld-results.md`](androidworld-results.md)).

## Changes since the evaluation

Made after the `eval-final` tag, and not measured by it:
- **`wait_for_task`:** a new tool that holds a call for up to about 45 s and says whether the task is still going, so an
  agent can stay in its turn until the task is final ([`backend/mcp_server/README.md`](../backend/mcp_server/README.md)).
- **Lyft's "Confirm drop-off location"** no longer asks for approval, because it only sets where you're going. "Confirm
  pickup" and "Request …" still ask ([`backend/policy/risk.py`](../backend/policy/risk.py)).
- **Tied rows:** in a routine with no irreversible step, when rows named by an input tie and their list can't scroll
  right now, the routine takes the top one instead of failing.

## Evidence appendix

Every number above, with its scope, configuration and commit. The profiles are in
[`backend/models/adapter.py`](../backend/models/adapter.py): `hybrid` (the default since Oct 30) runs plan, step, repair
and compile on Muse Wonder 1.0 and the rest on Muse Spark 1.3; the Spark profile runs plan, step and repair on Spark
(steps at low effort) and compiles on Wonder. Every run below used the standard tier.

| Number | Scope | Commit | Evidence |
| --- | --- | --- | --- |
| The final evaluation, suites 0–7 | 10 suites on Nov 3, `hybrid`, standard tier, $11.68 at standard prices; nothing uncommitted in any suite (`meta.code.dirty` empty). Runs: compile `1103001513`, systems `1103002528`, repeats `1103020715`, change `1103022306`, real `1103034419`, memory `1103031455`, safety `1103031031`, injection `1103025813`, interfaces `1103032630`, sizes `1103114754` (its phone step rerun with the Pixel upright) | `eval-final` = `cf78fa0` | [`report.md`](../eval/results/final/report.md) and each suite's `.md` / `.json` beside it |
| The real-app cost curve, and the top real-app number | medians (range) over the 13 workflows whose first run and same-input rerun both passed; the routine is called by name, so no matcher call; compile cost is Muse Wonder's, once per routine | `cf78fa0` | computed from [`real.json`](../eval/results/final/real.json) (`agent`, `routine_runs` "same input", `compile.cost_usd`) |
| "0 irreversible changes without approval" | on SkyLark: 7 declined live runs (suite 6) and 30 runs with planted instructions (suite 6b); the 20 irreversible controls are on saved screens, 6 SkyLark and 14 real-app | `cf78fa0` | `report.md`, "The design's success targets" |
| "Make it a routine" on real apps | the 18 real-app questions over MCP on a copy at the tag, then the button on each finished task, then each saved routine shared and called; the supplementary pass on a second copy with an empty routine library, outside the headline; deviations listed in its README | `cf78fa0` (harness `75b2c05`, `d259f3b`, `2f918da`) | [`learn-agent-path/`](../eval/results/learn-agent-path/README.md), its `PROTOCOL.md`, `results.json`, `supplementary.json` |
| AndroidWorld (a separate run) | 116 tasks, seed 30, pass@1, Spark profile at low effort, Oct 28–29; routines on 3 new seeds of their 23 tasks | baseline and `a80b976` (the 13 changes); seeds `e9594f0`, `b82e512`, `cdd130e`; merged in `105d04e` | [`docs/androidworld-results.md`](androidworld-results.md) |
| AndroidWorld, the shipped default | all 116 tasks, seed 30, pass@1, standard tier, `hybrid`, a $0.50 per-task cap; one run, Nov 3; $14.54 in all | `main` `7ed4aa6` | [`2026-11-03-hybrid-7ed4aa6/`](../eval/results/androidworld/2026-11-03-hybrid-7ed4aa6/README.md) (`run.json`, `comparison-final-standard.json`) |
| The live posts | Nov 1–2 (ET), Envoy's phone, test accounts; 0 / 0 / 3 / 0 model calls in Envoy's replay for the Reel, Story, TikTok re-post and Short | tasks `task-1102-005928-4182`, `-013244-b7c8`, `-023044-d081`, `-015325-106a` | [`docs/demo-showcase.md`](demo-showcase.md); versions and hand edits in each `data/routines/<name>/index.json` |
| Muse's dry run | Nov 2, Muse for Mac, every final step declined | the task rows | [`task-rows.json`](../eval/results/showcase/muse-2026-11-02/task-rows.json) |
| The Spark agent's own cost | a three-post run on a test copy, Nov 1, declined at each final button | — | [`crosspost/README.md`](../agents/meta-agent/evidence/2026-11-01/crosspost/README.md), "Cost" |
| The cloud phone, 48/48 | SkyLark routines compiled on the Mac, replayed on an emulator on Google Cloud, Oct 29 | — | [`docs/cloud.md`](cloud.md) |
| `cross_post` on Envoy's phone | one request, four parts, a test copy of the branch, every final button declined, Nov 2 20:57–21:37 | the branch's code, merged in `79dfb8d` | [`cross-post-pixel.json`](../eval/results/agent-door/cross-post-pixel.json) and the `cross-post-pixel-*.json` beside it |
| Outcome checks on Envoy's phone | the wrong-clip stop and the clean Reel, TikTok and Short runs, Nov 2 19:27–20:35, every final button declined | merged in `373eb86` | [`runs.md`](../eval/results/showcase/runs/runs.md) and each run's JSON, [`test_outcome_checks.py`](../backend/tests/test_outcome_checks.py) |
| The posting batch | 40 attempts, the four posting routines at v3, 10 each, cold / open / draft, Envoy's phone, Nov 3 12:27–14:55 ET, every final button declined; declared before the tag | `eval-final` = `cf78fa0` (the API copy); driver commits in each record | [`RESULTS.md`](../eval/results/showcase-batch/RESULTS.md), `attempts.md`, `attempts/` |
| `instagram_reel_song` v4, after the batch | 5 cold Reels to Share and 1 TikTok, a test copy at the fix, every final button declined, Nov 3 14:57–15:10 ET | merged in `0d28e5a` | `data/routines/instagram_reel_song/index.json` (v4's `verification`), [`test_reel_caption_fix.py`](../backend/tests/test_reel_caption_fix.py) |
| The Reel's v5, and Muse's `cross_post` take | single live runs, Nov 4, Envoy's phone; each row gives its version, status, model calls and seconds | the runs' task ids in each file | `runs` and `versions` in `data/routines/instagram_reel_song/index.json`, `tiktok_post_sound/index.json`, `youtube_short_sound/index.json`; the take's task rows in [`task-rows.json`](../eval/results/showcase/muse-2026-11-04/task-rows.json) |
| The Uber routine | one routine learned on the author's account, Nov 4, read-only, no ride requested; each row gives its version, status, model calls and seconds | the runs' task ids in the file | `data/routines/uber_check_uberx_price/index.json` |
| Drawn buttons, 52 of 52 | two samples, Oct 27, Phase 6: 16 canvas seats on SkyLark, 36 real-app targets on saved screens; not a suite of the final evaluation | — | [`docs/phase-6-results.md`](phase-6-results.md) |
| Changes since the evaluation | code only, not in any measured run above | `2a8e029` (`wait_for_task`), `7a0520b` (Lyft), `bbf1e0f` (tied rows) | the commits, and their tests |

Earlier development passes stay in `eval/results/` (for real apps: `real_pass_2026-10-28/`, `real_rerun_2026-10-29/`,
`real_rerun_2026-10-31/`, `real_rerun_2026-11-02_wsd-baseline/` and `real-apps/loop-a/`) with their own commits and
profiles. Nothing above quotes them.
