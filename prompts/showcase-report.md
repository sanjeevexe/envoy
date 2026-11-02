# showcase (T1c): the app-only cross-post as four routines (Nov 1, 2026)

Session `showcase`, branch `claude/showcase-414a4d` (rebased on main cd168d6). The Pixel 5 (Android 13), the test
accounts (Instagram envoy3955, the user's TikTok and YouTube test accounts), and a `:8764` API copy with its own data
dir and outbox, set to "always ask" for the three apps. **Nothing was posted**: every run stopped at the app's final
button and was declined there. No likes, follows, comments or DMs. Spend: **$4.37** of Meta's API (all runs and
compiles).

## What is true now (recompiled with the compiler fix, main ffde928)

The user's call was "tune now, compiler later", and the compiler fix landed the same night. So the four routines in
the library are **v1** (the first compile, retired) and **v2** (recompiled from the same source run with the fixed
compiler, reusing Wonder's cached answer at $0). The hand-tuned versions never went into the library. They're kept as
evidence in `eval/results/showcase/routine/*.v2-candidate.yaml` (and YouTube's v3/v4 candidates).

| Routine v2 | Hand edits | Replays (3 each, declined at the final button) |
| --- | --- | --- |
| `instagram_reel_song` | none: purely learned | 3/3 at Share. Two at **0 calls** (48–76 s); one met Instagram's one-time "Explore audio" tip and the agent finished (144 s, 16 calls). The newest clip and JVKE's "golden hour" every time |
| `instagram_story_poll` (v3) | none: purely learned | v3, recompiled once more with the compiler's transient-check fix (1645c09): **3/3 at "Your story", 29–32 s, 0 calls, the right clip each time**. (v2 went 3/3 too, but once with the wrong clip, from the "Today" check below; v3 doesn't have it) |
| `tiktok_post_sound` | a 3 s wait before the visual tap; the app corrected (the source run predates TikTok's name in Envoy) | 3/3 at Post, 71–76 s, 7–8 vision calls (~$0.02), the newest clip each time. On main 98d96de (agent-door's launch fix 8f7a082): 2 more runs, **no "came to the front on its own" pause**. One of them paused at 107 s on "you touched the phone" while nobody else held the Pixel (a real touch, or a false one: not seen again), and the other ran clean to Post in 74 s with 7 vision calls |
| `youtube_short_sound` | its stray "Captions unavailable" before-check dropped | 3/3 at "Upload Short", 94–144 s, 2–8 calls ($0.04–0.14), the newest clip each time. The search tap still needs a repair or the agent. **With the locator case fix (953b014): 1 more replay, 42 s, 0 calls, $0.** The search step now starts the search |

How "which clip" was checked: before each replay a labelled test clip ("REEL 2", "STORY 3", "TIKTOK 1"…, each its own
colour) was pushed. The approval screenshot at the final button (kept outside the repo) shows which one it was.
**Correction (Nov 2):** I wrote here that the track or sound was "confirmed by the step's own `text_has` on title and
artist". That check is on the result row that gets tapped, not on the editor, so it never showed the sound was
attached. For TikTok it wasn't (below). Instagram's reel shows the song on the posted reel. YouTube's add step has an
after-check on the editor's sound button, "{{sound_title}} Adjust or change sound".

## The real posts (Nov 2, 01:00–02:00 ET)

meta-agent started each one from its page on :8700 on the user's word. The user allowed Envoy's phone and approved the
final button in Envoy on their iPhone. I prepped the Pixel (take setup, the "ENVOY TEST / Nov 1" clip pushed last) and
followed each task read-only over MCP.

| Post | Task | Routine | Result |
| --- | --- | --- | --- |
| Instagram Reel + song | task-1102-005928-4182 | `instagram_reel_song` v2 | **live** as envoy3955, "JVKE · golden hour", caption "Posted by Envoy · test"; 0 calls, rung 2 (2 after-checks relaxed, so Envoy put a v3 on trial) |
| Instagram Story + poll | task-1102-013244-b7c8 | `instagram_story_poll` v3 | **live**, poll "Did Envoy post this?" Yes / No; 0 calls, rung 1, 36 s |
| TikTok + sound | task-1102-014139-7f5e | `tiktok_post_sound` v2 | **posted without the sound** ("Original sound by envoy"), 7 vision calls. Envoy said "failed" because its done-check didn't see the caption. The user kept it |
| TikTok re-post | task-1102-023044-d081 (02:30–02:31) | `tiktok_post_sound` v3 | **live** as envoy, "Posted by Envoy · test 2", **♫ golden hour - JVKE**; done, 3 calls, 53 s, close_sound_sheet at rung 0 |
| YouTube Short + sound | task-1102-015325-106a | `youtube_short_sound` v2 | **live** as @envoy-e8o, public. Before Upload Short, the details screen showed YouTube's music notice and #goldenhour/#jvke, and the Short's sound tile is in use by 281K Shorts. The add-sound step passed only on a relaxed check (likely the "Swipe up to edit" hint) |

**Why TikTok has no sound.** In the source run (task-1101-210013-7814) the agent's first try left the editor's sound
label (`tv_top_text`) at "Add sound":
- Steps 11–14: red check, then the row, then a tap on the preview.
- At step 19 the agent went back to check, saw "Add sound", and redid it: 20 open the sheet, 21 the row, 23 Back. The
  label then read "golden hour".
- The compiler dropped 19–24 as "back-track: returned to the same screen" and kept the first try.
- `close_sound_sheet`'s only after-check is the word "Music", so no run could see the sound was missing. Rehearsals
  stop at Post, whose screen doesn't show the sound.

The compiler session has the case. Then: recompile, rehearse on the copy (checking "golden hour" in the editor before
Post), and re-post after the user deletes the songless one.

**TikTok v3, rehearsed (Nov 2, 02:19–02:24).** Compiled with the compiler's fix (bebaa50, main 9cfc1be) from the
same source run, using the compiler session's Wonder answer remapped by trace number ($0, `compile --spec`). v2's hand
edits were re-applied: the app name, the 3 s wait, and no before-check on the launch. The new path is search, the red
check, **Back**, Next, caption, Back, Post. close_sound_sheet now requires the editor's sound label (e1v/e1x) to name
{{sound_title}}.

Three replays on the :8764 copy, each declined at Post:
| Replay | Steps | Clip | close_sound_sheet | Time to Post | Calls |
| --- | --- | --- | --- | --- | --- |
| 1 | tap_create needed a local repair after TikTok's cold start | right | rung 0 | 115 s | 5 ($0.049) |
| 2 | all | right | rung 0 | 57 s | 3 ($0.007) |
| 3 | all | right | rung 0 | 57 s | 3 ($0.007) |

After replay 2's decline, Back to the editor read **"Music · golden hour"** (e1x, e1v).

**Why TikTok said "failed".** A routine learned from a declined post kept a done-check, the plan's "the caption is
visible". No run had seen it after the post, and TikTok leaves the composer after Post. `compile --final-from-declined`
now drops it and says so in the changes (07de462). `youtube_short_sound` v3 is v2 without it. YouTube's own passed
tonight because YouTube lands on the channel page, which shows the title.

**Wording for the video:** Instagram's two are "learned from one run" (no hand edits). TikTok's and YouTube's are
"learned, one step tuned". TikTok's can't be said to post "with a song" until its re-post. Instagram's replay with no model calls when the app shows no tip. TikTok uses vision on
its drawn sound list every run (~$0.02). YouTube still repairs its search step.

Still open in the compiled routines (for the compiler session):
- **Fixed (1645c09):** a transient after-check (`instagram_story_poll`, open_story_creation): `fast_scroll_container` "Today", the
  gallery's date label that shows only while the grid scrolls (the same check `instagram_post_reel` v2 dropped on
  Oct 29). The executor scrolled the grid to find it, so the next step's "list start" check ("Open camera") failed,
  and the repair picked the top visible thumbnail: the wrong clip. Fix: never an after-check. Then recompile (cached)
  and replay.
- **Fixed (953b014):** YouTube's search tap (tap_trigger_search). The compiler flagged it as ambiguous ("golden hour" and "Golden Hour"
  suggestions), and the tap doesn't start the search. Hand waits of 1.5 s and 4 s didn't help.
- **Fixed (8f7a082), as far as 2 runs show:** TikTok's launch. In every v2 replay before it, the task paused at launch ("TikTok came to the front on its own"), even with
  the app corrected. The routine starts with a fresh launch *and* a learned `launch_tiktok` step; the second launch
  may be what trips it. On :8700 that pause waits for someone to press Resume.

## How each routine was made
1. The agent's first run on hybrid, with `eval/run_showcase.py first --as <new name>`. The name isn't in the library,
   so the matcher is skipped and `instagram_post_reel` can't be picked. Declined at the final button.
2. `compile <trace> --name <name> --final-from-declined` (the coordinator's decision): Wonder compiles the declined
   run. The declined tap, which never ran, is added back as the last step: irreversible, with no after-check, and noted
   in the change log.
3. `add-routine`, then 3 replays of v1, declined (all in `runs.md`).
4. The v1 replays showed list locators that tie. The tuned versions were tried first (all four reached the final
   button), then replaced by recompiles with the compiler fix plus the two hand edits the coordinator named. They went
   in through `RoutineStore.add`, and each change log starts with what, if anything, was edited by hand. **Not through `add_trial`:** a trial becomes active only after a run that
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

## `instagram_post_reel` with the new compiler (not added: it's switched off)
Recompiled from its own source run (task-1029-202418-9af5-r1, Oct 29, cached Wonder answer, $0):
`eval/results/showcase/routine/instagram_post_reel.recompiled-1645c09.yaml`. The same 7 steps. The one change is
`select_newest_gallery_video`, which becomes "the first thumbnail in the grid, which must show 'Open camera'" in
place of v2's text-plus-position locator. That's the fix its hand-edited v3 candidate made, now learned. The
compiler also drops the gallery's "Today" check by itself (v2 had dropped it by hand). Nothing else differs.
