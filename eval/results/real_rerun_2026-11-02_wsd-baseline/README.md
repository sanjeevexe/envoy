# Real-app pass, Nov 2: main `192cd29` on the hybrid profile (WS-D baseline)

The coordinator asked for this pass (WS-D, C6 step 1) as a fresh baseline of the real-app new-input stage before any
compiler fix, and as a guide to what the Nov 3 eval will show. `eval/run_real_rerun.sh 192cd29 wsd-baseline` ran the 16
runnable read-only workflows on envoy-real from the Envoy-realrun worktree at `192cd29`.

- **Config:** standard tier, `hybrid` profile (Muse Wonder for step, plan, repair and compile; Muse Spark for the rest).
- **Run:** `1102175459`, 17:54–18:11 ET, 17 min. 118 model calls, **$1.45** at standard prices.
- **Target's two rows** carry over from run `1028023735` on `524b93a`. Target shows a bot check on emulators, so the
  script leaves it out.
- **Redaction:** the suite redacts Gmail's newest subject and DoorDash's answer as `[redacted]`. Nothing else here is
  personal: the test accounts, public places and catalogue answers.
- **Device state before the run wasn't recorded** (Oct 31's README has a table). envoy-real was cold-booted, never
  snapshot-restored, and stopped afterwards.

## The four stages

| Stage | Nov 2 (`192cd29`, hybrid) | Oct 31 (`a594136`, hybrid) |
| --- | --- | --- |
| 1. First run right | 14/18 | 12/18 |
| 2. Compiled | 15/18 | 12/18 |
| 3. Same input, no model call | 12/18 (14 counting a repair) | 9/18 (9) |
| 4. New input, no model call | **8/11** | 6/11 |
| Bot check | 2 (target, target_search) | 2 |

Scope:
- Stages 3 and 4 count a routine's replay with **no model call** (a repair or a screenshot read counts as a call).
- Stage 4's denominator is the 11 workflows with a second input. "Input not learned" counts as a miss.
- One pass each, so single rows can swing between passes (Oct 31's README shows four earlier passes).

New-input passes tonight:
- starbucks, chipotle, doordash_search, gmail_search, maps_address, play_rating, youtube_search, ytmusic_artist.
- chipotle and play_rating, judged unfixable on Oct 31, pass here.

## Each miss and its cause

Each was traced in its run files by a read-only subagent; the fixes were tested offline and gated (SkyLark compile and
new inputs on envoy-test unchanged). `../real_rerun_2026-11-02_wsd-check/` reruns amazon and chrome_wikipedia with them.

| Workflow | What happened | Cause | Fix |
| --- | --- | --- | --- |
| amazon | Same input passed only after a repair; new input "outputs not found" | The first step's before-check named a **CapCut heads-up notification** (System UI) drawn over Amazon when the run was recorded; gone on every rerun. Traces keep element IDs but not each element's package. Separately, the price pattern is shaped on the battery listing ("( $X /count) List: $Y"), and the new-input run's results page never filled in | 94cd0b3 (in main since a1c94a6): no check on System UI drawn over the app. On envoy-real (A/B on tonight's trace), the same input then passes with 0 calls. The new input still fails (the pattern); no safe fix tonight |
| chrome_wikipedia | First run right but unverified; new input "input not learned" | **Chrome reopened on the Eiffel Tower article** (it restores its last tab after a force-stop), so the agent never typed the topic. The routine became one read-the-screenshot step, and the compiler dropped the topic as unused: it would answer 1889 for any topic | 6140caf (in main since a1c94a6): the topic is kept as a check on the page heading, so another topic fails instead of getting 1889 (stage 4 unchanged). The harness fix, about:blank before Chrome as `eval/run_loop.py` does, is 3d0df77 |
| ytmusic_artist | Same input **wrong** ("Royal Philharmonic Orchestra & Matthew Freeman"); new input right | The answer was read in "the Button that shows the song". On the Songs filter's reload frame the only such Button was the mini player, left playing by an earlier run | **None.** Keeping the result row's ID fixed it offline, but on envoy-real the filter wasn't found and the fallback read "Song" from an unfiltered row. That's still wrong, so the fix was dropped. A safe fix needs the filter's check to read the chip's selected state |
| doordash | First run failed, not compiled | Agent-side | – |
| target, target_search | Bot check | Target's press-and-hold check on emulators | – |

**For the pitch:** about 8/11 new input and 12/18 same input without a model call on this pass. A real-app replay can still
answer wrong (ytmusic_artist's same input).

## Shape-graded answers to read by hand

13 answers have not been read by a person or checked against the apps (the run log's "read by hand" lines):
- amazon: $19.99 (first run, same input).
- chipotle: "Chips & Guacamole: $5.25" (first run, same input). The new input, Chips & Queso Blanco, also read $5.25:
  worth confirming it's that item's price.
- doordash_search: "Pizza Zombie" (first run, same input), "Sushi Roku" (new input).
- play_rating: 4.7 stars (first run), 4.3 stars in 34 million reviews (new input, Spotify).
- youtube_search: "lofi hip hop radio .. beats to relax/study to" (first run, same input), "Carbonara | Basics with Babish"
  (new input).
