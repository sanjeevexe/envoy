# showcase (T1c): the app-only cross-post as four routines (Nov 1, 2026)

Session `showcase`, branch `claude/showcase-414a4d` (rebased on main cd168d6). The Pixel 5 (Android 13), the test
accounts (Instagram envoy3955, the user's TikTok and YouTube test accounts), and a `:8764` API copy with its own data
dir and outbox, set to "always ask" for the three apps. **Nothing was posted**: every run stopped at the app's final
button and was declined there. No likes, follows, comments or DMs. Spend: **$3.67** of Meta's API (runs $3.40,
compiles $0.27).

## What is true now

| Routine (active version) | Feature | Replays of the active version | Learned vs tuned |
| --- | --- | --- | --- |
| `instagram_reel_song` (v2) | A Reel set to a song from Instagram's music library | **3/3** asked at Share, 49–92 s, **0 calls, $0**. Each picked the newest clip and JVKE's "golden hour" | Learned from one run; two locators tuned (the thumbnail; the track row) |
| `instagram_story_poll` (v2) | A Story with a poll sticker | **3/3** asked at "Your story", 28–31 s, **0 calls, $0**, newest clip, poll typed | Learned from one run; one locator tuned (the thumbnail) |
| `tiktok_post_sound` (v2) | A TikTok with a sound from TikTok's library | **3/3** asked at Post, 62–100 s, 7 vision calls each (no repairs), ~$0.017 | Learned from one run; a 3 s wait added, one locator tuned, its app corrected |
| `youtube_short_sound` (v4) | A Short with a sound from YouTube's library | v3+v4: **4/4** asked at "Upload Short", 72–101 s, 2–9 calls, $0.04–0.12 | Learned from one run; one stray check dropped, one locator tuned, a wait added. Still repairs one step (below) |

Per run: `eval/results/showcase/runs/` (`runs.md` and one JSON each, with every routine step's rung). The approval
screenshots, which show which labelled test clip ("REEL 2", "STORY 3"…) reached the final screen, are kept outside the
repo (the TikTok one shows the phone's nearby places). P3, which features work on the accounts: `eval/results/showcase/p3.md`.

**What the video can honestly say:** "Envoy learned each post from one run; we tuned a few steps by hand", and the
Instagram ones "replay with no model calls". Not "purely learned" until the compiler fix below lands and they're
recompiled. TikTok uses vision on its drawn sound list every run (cheap, ~$0.02). YouTube still spends a repair.

## How each routine was made
1. The agent's first run on hybrid, with `eval/run_showcase.py first --as <new name>`. The name isn't in the library,
   so the matcher is skipped and `instagram_post_reel` can't be picked. Declined at the final button.
2. `compile <trace> --name <name> --final-from-declined` (the coordinator's decision): Wonder compiles the declined
   run. The declined tap, which never ran, is added back as the last step: irreversible, with no after-check, and noted
   in the change log.
3. `add-routine`, then 3 replays of v1, declined (all in `runs.md`).
4. The v1 replays showed list locators that tie, so the tuned versions went in through `RoutineStore.add`. Each change
   log starts with what was tuned by hand. **Not through `add_trial`:** a trial becomes active only after a run that
   ends *done* with 0 calls (`lifecycle.after_run`), and a declined rehearsal never ends done, so its first replay
   would have rejected the trial.

## The source runs (for the compiler fix)
| Routine | Source task | Trace (git-ignored; a copy is in the shared notes' `showcase-source-runs/`) | Compiled v1 |
| --- | --- | --- | --- |
| instagram_reel_song | task-1101-202945-39d5 | `data/runs/task-1101-202945-39d5-r1` | `eval/results/showcase/routine/instagram_reel_song.yaml` |
| instagram_story_poll | task-1101-205058-3079 | `data/runs/task-1101-205058-3079-r1` | `…/instagram_story_poll.yaml` |
| tiktok_post_sound | task-1101-210013-7814 | `data/runs/task-1101-210013-7814-r1` | `…/tiktok_post_sound.yaml` |
| youtube_short_sound | task-1101-211106-9b42 | `data/runs/task-1101-211106-9b42-r1` | `…/youtube_short_sound.yaml` |

What the compiler got wrong, with the hand fix that worked (each `*.v2-candidate.yaml`, and YouTube's v3/v4):
- **A thumbnail in a gallery grid** (Instagram, both routines). The label is "Unselected Video thumbnail created on
  <date>", so every thumbnail fits it. The executor scrolls, then the repair picks whatever is on top: twice an Oct 30
  clip, the wrong video. Fix: the grid's first video slot (id, in the list, the recorded position, no text). This is
  the same fix as `instagram_post_reel`'s v3 candidate.
- **A result row chosen by input values** (the Instagram track; the TikTok and YouTube sound rows). The compiler
  dropped the text, leaving a wildcard id or nothing, so every row ties. Fix: `text_has` with the input slots
  ("{{song_title}} by {{song_artist}}") plus the recorded label as `text`, because `text_has` alone scores low.
- **The app** (TikTok). The first run's task had no app (Envoy doesn't know TikTok by name), and Instagram was on
  screen before the agent launched TikTok, so the routine said `com.instagram.android`.
- **A stray before-check** (YouTube's Create step): "Captions unavailable", from a video autoplaying on Home when the
  run was recorded.
- **Drawn content** (TikTok's search results have no accessibility nodes): the previous step's after-checks pass at
  once, so the visual step looked too early. A 3 s wait fixed it.

## Not done / still open
- **YouTube's sound search:** the routine's tap on "Trigger a new search with golden hour" doesn't start the search.
  A repair taps it again (2 calls), or the agent finishes the step (~$0.10). Waits of 1.5 s (v3) and 4 s (v4) didn't
  change it, so it isn't timing. Likely keyboard focus taking the first tap; it's for the executor or compiler fix.
  The agent's own first run tapped it once and it worked.
- **YouTube's start:** a run force-stopped mid-edit can leave an autosave, and the next Create opens on "Continue your
  draft video?". `run_showcase.py setup-youtube` (Create › Start over › force-stop on the empty camera) before each run
  fixed it. Whoever films needs that, or `scripts/instagram_take.py` for Instagram.
- **TikTok's start:** in 2 of 3 v2 replays the task paused at launch ("TikTok came to the front on its own"). My
  runner hands it back on the copy. **On :8700 that pause waits for someone to press Resume**, so check before filming.
- **Muse Wonder repairs twice gave a "reason" unrelated to the screen** (text about cash budgets and insurance) with a
  sensible action. Worth a look by whoever owns the repair prompt.
- **Envoy's pop-up handler denied YouTube's photos permission** during the first run, as it denies every permission
  prompt. YouTube now uses the system photo picker, which the routine learned; fine, but it differs from P3.
- **No real posts yet.** They happen only on the user's yes, relayed by the coordinator. `HANDOFF_TEMPLATES` has
  `tiktok` and `youtube` entries without a `routine` key; pointing them at these routines is a one-line change once
  the user wants the Mac-clip offer to use them.
- **Sharing:** each routine becomes an MCP tool (agent-door) only after "Share with agents" is turned on for it.
