# Showcase reliability batch: the protocol, fixed before any attempt

Written and committed on Nov 2, 2026, before the `eval-final` tag and before any batch attempt. The batch (B1) runs
after the eval, Nov 3 22:00 → Nov 4 about 08:00 ET. Nothing in this file changes once the tag is set. A deviation is
written down as a deviation in `RESULTS.md`, with its reason, and never folded back into this file.

## What it measures

How often each posting workflow in the video reaches its final button with what was asked for on screen, and what it
took to get there. Every attempt stops at that button, and the button is declined. The batch says nothing about other
apps, other phones, other accounts or other versions.

## The frozen code

- **Code:** the commit the `eval-final` tag points at. Each attempt records `git rev-parse eval-final` and the API
  copy's own `HEAD`. They must be equal. The copy runs from a clean checkout at the tag (`git status` empty), and the
  driver refuses to start otherwise.
- **Routines:** each workflow starts from the version the tagged commit has in `data/routines/` (C0). The library isn't
  reset between attempts, because a user's library isn't either. A repair that writes a trial, and a trial that
  becomes active, stay in. Each attempt records the routine version it ran (from its approval, "routine X vN") and the
  library's active version after it.
- **Model profile:** `hybrid`, the default, as recorded by the copy.
- **The driver:** `eval/run_showcase.py`, from the tag where possible. If the driver needs a fix after the tag, it runs
  from that fix's commit, which each attempt records. The API copy stays at the tag. The driver only talks to the copy
  over HTTP and to the phone with `adb -s <serial>`.

## The workflows (N = 10 each, 40 attempts)

| Code | Workflow | Routine | Inputs |
| --- | --- | --- | --- |
| R | Instagram Reel with a library song | `instagram_reel_song` | song_title, song_artist, caption |
| T | TikTok with a library sound | `tiktok_post_sound` | sound_title, sound_artist, caption |
| S | YouTube Short with a library sound | `youtube_short_sound` | sound_title, sound_artist, short_title |
| P | Instagram Story with a poll sticker | `instagram_story_poll` | poll_question, poll_option_1, poll_option_2 |

The Story is in because U5 keeps it in the V3 take.

## Setup that keeps anything from publishing

- A test API copy at the tag, on its own port (:8701 or higher, never :8700). It has its own `ENVOY_API_DIR` (a fresh
  folder: 0 push subscriptions, its own session token) and its own `ENVOY_OUTBOX`.
- Approval rules set to "always ask" for Instagram, TikTok and YouTube before each attempt. The driver reads them
  back, and refuses to start an attempt if they're not set.
- Each attempt is a routine run (`routine` + typed `inputs`), never a typed goal. No request is worded "Post…" (an
  in-app request naming the publish verb counts as consent; `prompts/demo-plan.md`, "Posting takes").
- The driver declines every approval: the final button and any other irreversible step.
- The phone: Envoy's phone (Pixel 5, Android 13), upright, on the test accounts signed in on Nov 2 (Instagram
  envoy3955, TikTok envoy803, YouTube @envoy-e8o). Nobody signs in, out or changes account settings during the batch.
  The device is claimed for the whole batch (`coord/devices.sh`).

## Clips, songs and captions, fixed now

- **Clips:** one per attempt, made before the batch. Each is 8 s, 1080×1920, H.264, silent, with a solid colour and
  its attempt code as large text ("BATCH R01" …). The colours: R orange, T blue, S red, P purple. Synthetic, with no
  people or places. They're pushed to `Movies/Envoy/` immediately before their attempt, as the newest video. The
  push's `media_uri` is recorded.
- **Songs:** attempts 01–05 use "golden hour" by JVKE, the video's input, which P3 found in all three libraries
  (`eval/results/showcase/p3.md`). Attempts 06–10 each use a different song.
  - **Library check before the batch:** each song is searched for in all three apps' libraries. This is a search only:
    nothing is added and nothing is posted.
  - A song any library lacks is swapped for its alternate below, and the swap is written in `RESULTS.md`.
  - Why: a song missing from an app's library measures the app, not Envoy.
  - If a song that passed the check is missing during the batch, that attempt is failed, with the reason.

| # | Song (song_title / sound_title) | Artist | Alternate (same artist) |
| --- | --- | --- | --- |
| 01–05 | golden hour | JVKE | none: found in all three by P3 |
| 06 | Espresso | Sabrina Carpenter | Please Please Please |
| 07 | Flowers | Miley Cyrus | Wrecking Ball |
| 08 | As It Was | Harry Styles | Watermelon Sugar |
| 09 | Blinding Lights | The Weeknd | Save Your Tears |
| 10 | Levitating | Dua Lipa | Don't Start Now |

- **Captions and titles:** R and T use `Envoy batch R01 · test` and so on, with the attempt's own code. S uses the
  same pattern as its `short_title`.
- **Story polls (P):** poll_question `Envoy batch P01: which one?` (with the attempt's code), and these options:

| # | poll_option_1 | poll_option_2 |
| --- | --- | --- |
| P01 | Coffee | Tea |
| P02 | Cats | Dogs |
| P03 | Beach | Mountains |
| P04 | Pizza | Tacos |
| P05 | Morning | Night |
| P06 | Books | Films |
| P07 | Summer | Winter |
| P08 | Sneakers | Boots |
| P09 | Sweet | Savory |
| P10 | City | Country |

## Starting states, fixed now

| State | How it is set up before the attempt |
| --- | --- |
| **cold** | The app is force-stopped. The launcher is in front. |
| **open** | The app is launched and left on its home feed for at least 5 s. Nothing is open over it. |
| **draft** | A saved, unposted draft exists, made by the driver just before the attempt. Instagram (R, P): open the Reel composer with an older clip, back out and choose "Save draft", so Create offers "Keep editing your draft?". TikTok: in the editor, choose Drafts. YouTube: force-stop the app on the Short editor, so Create offers "Continue your draft video?". The app is then force-stopped. |
| **live Story** | P only: a real Story is live on envoy3955. It isn't made for the batch. It applies only if V3's Story is still live and C1 was verified (U5). Otherwise the user deletes it before the batch, and no P attempt has this state. Each P attempt records whether a Story was live. |

Per workflow: attempts 01, 04, 07 and 10 are **cold**; 02, 05 and 08 are **open**; 03, 06 and 09 are **draft**. For
P, "live Story" is recorded on top of these, as above.

## Order and spacing

The 40 attempts run interleaved, in this order: R01 T01 S01 P01 R02 T02 S02 P02 … R10 T10 S10 P10. There are at least
2 minutes between the end of one attempt and the start of the next, and nobody touches the phone. A pause longer than
30 minutes (a harness fix, a phone problem) is written down with its reason.

**Stop rules:** the batch stops at once and is reported if any of these happens:
- a bot check, CAPTCHA, login wall or account warning;
- any sign that something was published (it shouldn't be possible);
- the phone becomes unusable.

The attempt in progress is kept, with its outcome. The attempts not run are listed as not run, never dropped.

## What each attempt records

`eval/results/showcase-batch/attempts/<code>.json`, one file per attempt, including harness errors:
- **Identity:** the attempt code, workflow, starting state (and "live Story" for P), the clip's label, file name and
  `media_uri`, and the inputs.
- **Versions:** the tag and HEAD commits; the routine version run; the active version after.
- **The task:** its id, start time, when the final button was asked (`asked_at`, which button), and its end status.
- **Steps:** per step, the rung and the ladder notes; the repairs, and any patch or trial written; model calls and
  dollars (by job).
- **Interventions:** any `taken_over` or "touched the phone" pause, any hand-back, and anything the driver did beyond
  "decline".
- **The outcome checks:** see below. Each is yes, no or not checkable, with the evidence.
- The approval screenshot is kept **outside the repo** (TikTok's post screen lists nearby places). The record keeps
  its file name and SHA-256.

`attempts.md` holds one row per attempt, in run order. `RESULTS.md` is written after the last attempt.

## The outcome taxonomy (one class per attempt)

Classes are taken in this order: the first that fits.
1. **outcome unknown:** the record can't establish what happened, for example the harness crashed mid-run, or the task
   record or approval was lost.
2. **failed:** any of these happened:
   - the run never asked at the workflow's final button;
   - it asked at a different irreversible button;
   - it ended failed or stopped;
   - an outcome check says **no** (wrong clip, song, caption or poll);
   - a stop rule fired during it.
3. **person stepped in:** a person acted. That covers rung 6 (asked the user), a `taken_over` pause, a hand-back, or
   any phone touch other than the driver's decline.
4. **agent fallback:** the full agent took over (rung 5) and the run still reached the final button.
5. **repair:** local repair (rung 4) saved at least one step.
6. **no repair:** every step held at rungs 0–3 (match; wait and retry; relaxed match; pop-up handler).

Vision lookups that a routine makes by design, such as TikTok's red check, count as model calls, not as a repair.

Outcome checks are reported next to the class, so a "no repair" with a song that was "not checkable" stays visible:
- **clip:** the label on the approval screenshot, or the media item the run picked, matches the pushed one.
- **song:** the song's title is shown on the editor or composer before the final button, by the run's own outcome
  check if the tagged code has one (C2), or else by a screen read at the final ask.
- **caption or title:** it's in the field on the final screen.
- **poll:** the question and both options are on the sticker.

Something the final screen doesn't show, and no check covered, is "not checkable". It is never "yes".

## What gets reported

Per workflow, over its 10 attempts:
- counts in each class;
- how many reached the final button with every outcome check "yes";
- the median and range of time to the final ask;
- model calls and dollars, with their scope stated: Envoy's replay, by job.

Starting states are broken out. Version changes are reported where they happened. No pooling across workflows except a
total row labelled as one. The wording stays narrow, as in Codex-r4: this version, these four workflows, these inputs,
every attempt, every intervention.
