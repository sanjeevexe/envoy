# Real-app dress rehearsal, Oct 31: main `a594136` on the hybrid profile

The coordinator asked for this run, and the user approved it, as a rehearsal of the Nov 2 real-app numbers. `eval/run_final.py real` ran all 18 read-only workflows on envoy-real, from the Envoy-skycheck worktree at `a594136`, on the standard tier. The profile was hybrid: Muse Wonder for step, plan, repair and compile, Muse Spark for the rest. **This is the first full real-app pass on hybrid.** Every pass before it ran the agent's steps on Spark, so differences below can come from the model as well as the code.

- **Runs:** 16 workflows ran 15:09–15:24 ET (run `1031150937`). The two Gmail rows then ran again 15:25–15:27 (`1031152557`). In the first run they stopped at "Gmail is not connected": the worktree had no `data/gmail` token, which only the main checkout keeps (the same link `eval/run_real_rerun.sh` makes). Nov 2 runs in the main checkout, so it isn't affected.
- **"Uncommitted changes" in real.md is a false flag**, from a bug in `eval/final_common.code_state`. It is fixed in the same commit as this folder. Neither run had a code change.
- **Cost:** $1.63 at standard prices, plus $0.006 of key checks.
- **Redaction:** Gmail's newest message in the Primary tab was a Spotify sign-in code (from loop B's Spotify sign-in, Oct 30; spent). The code is replaced by `[code]` in every file here. DoorDash's address is redacted by the suite, except in one compile note, which quotes it.

## envoy-real's state before the run

The run checked each app read-only, with a fresh launch and a screen dump, and changed nothing.

| App | State | Could it change a row? |
| --- | --- | --- |
| Contacts | "No contacts yet", no list filters on | No |
| DoorDash | "No open carts" | No |
| Chrome | 14 tabs; the new tab page offers loop B's Google Flights tab and an "Eiffel Tower: en.m.wikipedia.org" shortcut | Not seen: the agent typed the address |
| Gmail | Opens on the inbox (Primary), not a search | Yes, through the grader (gmail_newest below) |
| Starbucks | Signed out | No: the calorie lookup needs no sign-in, and it passed |
| Installed since the last pass | Wikipedia, Calculator, Yelp, OpenTable, Spotify, Lyft, CapCut | Not seen in any row |

Afterwards, calendar_today had opened a new-event sheet and closed it without saving. All 58 calendar events are in the holidays calendar, none in the user's own.

## The four stages

| Stage | Oct 31 (`a594136`, hybrid) | Oct 28 (`00ec5d9`, spark) | Oct 29 main (`53ab459`, spark) | Oct 29 after (`736a6e4`, spark) | Oct 29 main (`059bb7f`, spark) |
| --- | --- | --- | --- | --- | --- |
| 1. First run right | 12/18 | 13/18 | 14/18 | 14/18 | 15/18 |
| 2. Compiled | 12/18 | 14/18 | 14/18 | 15/18 | 16/18 |
| 3. Same input, no model call | 9/18 (9 with a repair) | 13/18 (14 with a repair) | 9/18 (11 with a repair) | 13/18 (14 with a repair) | 12/18 (14 with a repair) |
| 4. New input, no model call | 6/11 | 4/11 | 5/11 | 6/11 | 6/11 |

Each cell: first run (agent actions) · compiled · same input · new input.

| Workflow | Oct 31 (`a594136`, hybrid) | Oct 28 (`00ec5d9`, spark) | Oct 29 main (`53ab459`, spark) | Oct 29 after (`736a6e4`, spark) | Oct 29 main (`059bb7f`, spark) |
| --- | --- | --- | --- | --- | --- |
| amazon | pass (2) · ✓ · pass · pass | pass (2) · ✓ · pass · fail | pass (2) · ✓ · pass · pass | pass (2) · ✓ · pass · pass | pass (2) · ✓ · fail · fail |
| target | bot check (0) · ✗ · – · – | bot check (0) · ✗ · – · – | bot check (0) · ✗ · – · – | bot check (0) · ✗ · – · – | bot check (0) · ✗ · – · – |
| target_search | bot check (0) · ✗ · – · – | bot check (0) · ✗ · – · – | bot check (0) · ✗ · – · – | bot check (0) · ✗ · – · – | bot check (0) · ✗ · – · – |
| starbucks | pass (7) · ✓ · pass · pass | pass (8) · ✓ · pass · pass | pass (21) · ✓ · pass · pass | pass (7) · ✓ · pass · pass | pass (7) · ✓ · pass · pass |
| chipotle | pass (12) · ✓ · fail · input not learned | pass (21) · ✓ · pass after repair · pass after repair | step_limit (21) · ✗ · – · – | pass (10) · ✓ · pass · pass | pass (9) · ✓ · pass · pass |
| doordash | pass (8) · ✗ · – · – | pass (1) · ✓ · pass · – | pass (13) · ✓ · pass · – | pass (1) · ✓ · pass · – | pass (1) · ✓ · pass · – |
| doordash_search | pass (2) · ✓ · pass · pass | pass (2) · ✓ · pass · pass after repair | pass (2) · ✓ · pass · pass | pass (2) · ✓ · pass · pass | pass (2) · ✓ · pass after repair · pass after repair |
| settings_version | pass (5) · ✓ · pass · – | pass (4) · ✓ · pass · – | pass (4) · ✓ · pass · – | pass (4) · ✓ · pass · – | pass (4) · ✓ · pass · – |
| settings_bluetooth | right, unverified (3) · ✗ · – · – | pass (6) · ✓ · pass · – | pass (13) · ✓ · fail · – | pass (3) · ✓ · pass · – | pass (3) · ✓ · pass · – |
| gmail_newest | wrong (0) · ✓ · wrong · – | pass (14) · ✓ · pass · – | pass (3) · ✓ · pass · – | pass (1) · ✓ · pass · – | pass (2) · ✓ · pass · – |
| gmail_search | pass (3) · ✓ · pass · pass | pass (3) · ✓ · pass · pass | pass (3) · ✓ · wrong · pass | pass (3) · ✓ · pass · pass | pass (3) · ✓ · pass · pass |
| calendar_today | failed (13) · ✗ · – · – | pass (0) · ✓ · pass · – | pass (0) · ✓ · pass · – | pass (0) · ✓ · pass · – | pass (0) · ✓ · pass · – |
| contacts_count | pass (0) · ✓ · pass · – | pass (0) · ✓ · pass · – | pass (0) · ✓ · pass · – | step_limit (25) · ✗ · – · – | pass (0) · ✓ · pass · – |
| maps_address | pass (2) · ✓ · pass · pass | pass (4) · ✓ · pass · pass | pass (4) · ✓ · fail · fail | pass (2) · ✓ · pass · wrong | pass (2) · ✓ · pass · pass |
| play_rating | pass (0) · ✓ · pass · fail | pass (6) · ✓ · pass · fail | pass (2) · ✓ · pass after repair · fail | pass (1) · ✓ · pass · fail | pass (1) · ✓ · pass after repair · fail |
| youtube_search | pass (2) · ✓ · pass · pass | error (4) · ✗ · – · – | pass (4) · ✓ · pass · pass | pass (2) · ✓ · pass · pass | pass (2) · ✓ · pass · pass |
| ytmusic_artist | pass (2) · ✓ · wrong · wrong | pass (6) · ✓ · pass · pass | pass (6) · ✓ · pass after repair · fail | pass (3) · ✓ · fail · fail | pass (3) · ✓ · pass · pass |
| chrome_wikipedia | right, unverified (12) · ✗ · – · – | right, unverified (10) · ✗ · – · – | error (8) · ✗ · – · – | right, unverified (5) · ✓ · pass after repair · fail | right, unverified (7) · ✓ · fail · fail |

The "Oct 28" file holds rows from four runs (`401e994`, `cddf1b2`, `524b93a`, `00ec5d9`). The Oct 29 passes carry Target's two rows over from `524b93a`.

## Each miss, its cause, and a fix before the Nov 1 22:00 cut

| Workflow | What happened | Cause | New? | Fix before the cut |
| --- | --- | --- | --- | --- |
| target, target_search | Bot check at launch | Target's "press & hold" check on emulators | Same on every pass | None (reported as bot checks) |
| gmail_newest | Answered the Primary tab's top message, graded wrong | **The grader.** The Gmail API's newest inbox message was a Promotions mail ("Welcome to Amazon…") that the app's Primary tab doesn't show | New: Promotions mail was newer than Primary's | **Done, eval code:** `_gmail` accepts the newest in Primary or in the whole inbox (and no longer counts sent mail). Under it, today's first run and same input are right |
| calendar_today | Failed after 13 actions, stuck | **The date.** Halloween shows as an all-day event, and the agent kept scrolling for timed events until it was stuck. On empty days (Oct 28, 29) it answered with 0 actions | Date-dependent | None needed if Nov 2 has no all-day holiday. The part of the holiday list read today has Nov 1 (DST ends) and Nov 11 (Veterans Day); check the Nov 2 calendar before the run |
| doordash | Right answer, 8 actions, not compiled | **Wonder's over-caution.** It labeled opening "Addresses" irreversible. The read-only suite declined the approval, so the agent answered from the home toolbar it had seen, and the address wasn't on its final screen to compile. On Spark: 1 action, compiled | Seen once before (Oct 29's guard run, on Spark); main's Spark passes answered in 1 action | Agent-side, for the coordinator. The same over-ask as SkyLark's "Check in" |
| settings_bluetooth | Answered "Bluetooth is turned on", unverified, not compiled | The answer check looks for the answer's words on screen; the state is a switch, not text. Spark's runs verified | New | Agent-side (answer check), for the coordinator |
| ytmusic_artist | First run right ("Queen"); same and new input "wrong" | **The compiler kept a routine with no outputs.** It answers nothing, so both reruns grade wrong. Spark's compiles had an `artist` output | New: before, it failed or passed but never compiled empty | Compiler-side, for the coordinator: a question run whose answer binds to no output should be NotCompilable, as doordash's was |
| chipotle | Right in 12 actions; same input failed at `select_nearby_location` | A longer route compiled a store-picking step that can't find its target on rerun | Known (Oct 29: 11- and 12-action runs failed the same way) | None safe (compile-side step pruning) |
| play_rating | New input (Spotify) fails "outputs not found" | The routine's extraction fits Duolingo's result card only. Spotify is now installed, so its Play page differs too | Same on every pass | None |
| chrome_wikipedia | Right ("1889"), unverified | The year isn't on the final screen when the agent answers | Same as Oct 28 and Oct 29 | None |

**Better than Oct 29's last main pass (`059bb7f`):** amazon (same and new input pass; they failed there), doordash_search (no repair needed). contacts_count matched it: 0 actions, compiled, reran right.

**Shape-graded answers to read by hand** (11; not checked against the apps): amazon $21.78 and $9.99, doordash_search "Pizza Zombie" and "Sushi Roku", play_rating 4.7, youtube_search's two titles.
