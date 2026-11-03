# Showcase reliability batch (B1): results

What `PROTOCOL.md` fixed, run once: the four showcase routines at the `eval-final` tag (cf78fa0, all four at v3), ten
attempts each, interleaved, on the Pixel 5 ("Envoy's phone"), with the test accounts. No attempt went past its app's
final button, and every final button that was asked was declined: nothing was posted. Nov 3, 12:27–14:55 ET. It ran on
the tag: the API copy was a clean checkout of `eval-final` (its code checked unchanged before the run, and recorded in
every attempt), with its own data folder and no push subscriptions. Driver: `eval/showcase_batch.py` (versions per
attempt in each record). Every attempt is in `attempts/<code>.json` and `attempts.md`, in run order.

The records name the driver commits as they were during the run. The branch was later rebased onto main, which renamed
them: 7259133 (R01–S03) is now 9656422, d03caf8 (P03–P10) is now 495947f, and the earlier 27e920b, c8b19c7 and 0e5fbe1
are now 3ac96f5, e0ae433 and 0b8cd21. The code is unchanged.

The numbers below are for this version, these four workflows, these inputs, on one phone and one set of accounts, over
one afternoon. N is 10 per workflow.

## Per workflow

| Workflow | No repair | Repair | Agent fallback | Person stepped in | Failed | Outcome unknown | Reached the final button | …with every outcome check yes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Reel with a library song (`instagram_reel_song`, R) | 7 | 0 | 0 | 0 | 3 | 0 | 7 | 7 |
| TikTok with a library sound (`tiktok_post_sound`, T) | 10 | 0 | 0 | 0 | 0 | 0 | 10 | 10 |
| Short with a library sound (`youtube_short_sound`, S) | 4 | 0 | 1 | 0 | 5 | 0 | 5 | 4 |
| Story with a poll (`instagram_story_poll`, P) | 9 | 1 | 0 | 0 | 0 | 0 | 10 | 10 (poll by eye, below) |

Classes are the protocol's, the first that fits. "No repair" allows rungs 0–3 (wait and retry, relaxed match, pop-up
handler); TikTok's routine reads its sound results by vision on every run, by design, which counts as model calls and
not as a repair.

**Time to the final ask** (seconds from the task's start, over the attempts that reached it):

| Workflow | Median | Range |
| --- | --- | --- |
| R | 59.6 | 55.6–111.8 (7) |
| T | 60.6 | 57.6–69.7 (10) |
| S | 41.5 | 40.4–116.9 (5) |
| P | 32.5 | 31.4–41.5 (10) |

**Model calls and dollars, in Envoy's replay, by job** (the coding sessions' own calls are not counted):

| Workflow | Calls | $ | By job |
| --- | --- | --- | --- |
| R | 31 | 0.4608 | agent 28 (plan 3, step 25: all in R10), repair 3 |
| T | 30 | 0.0723 | the routine's own sound-result reads: choose 10, sam 20 (3 per run) |
| S | 33 | 0.4851 | agent 23 (plan 3, step 20), repair 10 |
| P | 1 | 0.016 | repair 1 (P05) |
| Total (all four, one row) | 95 | 1.0342 | |

## By starting state

| Workflow | Cold (4) | Open (3) | Draft (3) |
| --- | --- | --- | --- |
| R | 2 no repair, 2 failed (R07, R10) | 3 no repair | 2 no repair, 1 failed (R03) |
| T | 4 no repair | 3 no repair | 3 no repair (T03 ran from a cold start: below) |
| S | 2 no repair, 2 failed (S07, S10) | 2 no repair, 1 failed (S08) | 1 agent fallback (S06), 2 failed (S03, S09) |
| P | 4 no repair | 2 no repair, 1 repair (P05) | 3 no repair |

No routine version changed: all 40 attempts ran v3, and v3 was still active after each one.

## Outcome checks

The run's own checks before the final button (in the tagged code since C2) cover the song, the typed text and the
clip. The poll isn't on the final screen as text, so it was checked by eye on the approval screenshots (kept outside
the repo, by file name and SHA-256 in each record): all ten stickers read "Envoy batch Pnn: which one?" with that
attempt's pair of options, on the purple clip. In S06 the full agent finished the run, so the routine's checks didn't
run. Its screenshot shows the right clip ("BATCH S06") and title, but not the sound. YouTube's suggested hashtags
(#taylorsversion, #aicover) hint the agent may have picked another sound, so its song stays **not checkable**.

**Five runs were stopped by those checks before the final button**, each with something missing that the final button would
have posted without:
- **R03 and R07 (caption):** `type_caption`'s own check held, then `close_keyboard` (Back) sometimes cancelled
  Instagram's caption edit, and the field was empty at Share. The seven Reels that reached Share had their caption.
- **S07, S08 and S10 (song):** YouTube's sound search didn't list "Flowers, Miley Cyrus", "Watermelon Sugar, Harry
  Styles" or "Levitating, Dua Lipa" as the routine looks for it. The routine went on without a sound (S07, S08) or with
  a looser match (S10), and the check found the song never shown on the editor.

## The other failures

- **S03 and S09 (YouTube, from a draft):** Create opened YouTube's "Continue your draft video?", which the routine's
  first step doesn't expect. The full agent asked to tap "Start over" (it discards the draft), which the batch declines
  like every approval, so the run ended. In S06 the agent reached Upload Short from the same prompt (19 calls).
- **R10 (Instagram, "Levitating"):** Instagram's music search didn't show "Levitating by Dua Lipa" (the library check at
  12:1x had found it). The full agent stopped at its 25-step limit, and the run ended asking for a person. No approval
  was asked.

## The library check and swaps

Before the batch, songs 06–10 were searched for in all three apps (search only), and alternates where needed
(`songs.json`, `songs-alternates-instagram.json`, `songs-alternates-tiktok-youtube.json`):
- 06 Espresso: not in Instagram's library on the test account → **Please Please Please** (in all three).
- 08 As It Was: not in Instagram's library → **Watermelon Sugar** (in all three).
- 09 Blinding Lights: not in Instagram's library, and neither is its alternate Save Your Tears → **golden hour** by
  JVKE (the coordinator's ruling: the protocol doesn't cover a missing alternate).
- 07 Flowers and 10 Levitating: in all three by the check (but see YouTube below).

The check called a song found when any element showed its title and artist. That held for Instagram (its search box
holds the title only) and TikTok, where the batch itself attached every song (T06–T10, song check yes). In YouTube the
executor's own search rung retypes the search as "<title>, <artist>", and the search box then shows exactly that, so
YouTube's "yes" can come from the search box alone. Its screenshots (outside the repo) do show result rows for
Espresso, As It Was, Watermelon Sugar and Levitating, each with all credited artists ("Harry Styles, Mitch Rowland").
"Flowers" by Miley Cyrus, "Please Please Please" and "Blinding Lights" show only the search box, over an empty list.
A search after the batch (Nov 3, search only) found "Flowers" by Miley Cyrus in YouTube's library, at row #0.

## Deviations from PROTOCOL.md

- **Timing:** the protocol set Nov 3 22:00 → Nov 4 about 08:00 ET. The eval's schedule moved B1 to Nov 3 about
  12:15–15:15 ET, before the author's takes. At 14:00 the author widened that to "done by 7/8" (no attempt after 18:30).
  All 40 had run by 14:55. No attempt was rerun or reordered.
- **No live Story:** no Story was live during the batch (C1 isn't fixed; the live-Story state wasn't used).
- **Live Caption:** Android's Live Caption was on when the Pixel was handed over (found 11:57, during the first library
  check). Its box hid TikTok's screen from Envoy. That check was stopped, the author turned Live Caption off at 12:00,
  and the check was run again from the start at 12:01. No attempt ran with Live Caption on.
- **Auto-rotate** was off on the Pixel for the batch (the coordinator turned it off before handing it over).
- **Clips:** all 40 were made before the batch (`showcase_batch.py clips`, hashes in a manifest outside the repo).
- **Draft setup:** T03's setup made no draft (TikTok's launch check failed during setup), so **T03 ran from a cold
  start**. From P03 on (driver d03caf8, now 495947f), a setup that stops before the editor is tried again, and TikTok's draft is
  saved from its post screen (Next, then Drafts). To load that, the runner was stopped after S03 and resumed after the
  2-minute gap; no attempt was rerun.
- **The library check's swaps** are above; the alternate-missing rule is the coordinator's.

## After the batch (not part of it)

- **The Reel's caption loss** (R03, R07) is fixed in `instagram_reel_song` v4: Instagram's OK ends the caption edit
  instead of Back, and a caption found empty before Share is typed again. Checked on the Pixel on a test copy at the fix
  commit, every final button declined: **Reel 5/5** from a cold start with golden hour reached Share with clip, song and
  caption yes, at 0 model calls (in the first run OK left the caption empty and the retype put it back); **TikTok 1/1**
  (no change, v3); **Short not run** (the check was stopped when the phone was needed). Merged as main 0d28e5a, with
  the device check recorded in f064d5a. B1 itself ran v3, as above.
- **YouTube's song pick** (S07, S08, S10) stays open. The cause was found after the batch, by a search-only
  diagnostic on the Pixel (Nov 3), not measured in it. Enter in YouTube's Sounds search box doesn't search: only
  tapping its "Trigger a new search with …" suggestion does. v3 skips that tap, because its check sees the editor behind
  the search sheet, so the list stays on YouTube's trending sounds, where golden hour was and the other songs weren't.
  A fix was tried after the batch and not merged. YouTube lists suggestions that differ only in case ("flowers",
  most likely from search history, and "Flowers"), so it needs a tie-break in the locator matcher. Evidence: branch
  `claude/yt-song-fix` and `yt-song-fix-writeup.md` here.
- YouTube's draft prompt (S03, S06, S09) and Instagram's search missing a song it had listed earlier (R10) are open too.
