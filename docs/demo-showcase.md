# Demo: the app-only cross-post (Instagram + TikTok + YouTube Shorts)

The video's climax. One clip is posted from Envoy's phone (the Pixel 5) to Instagram, TikTok and YouTube Shorts. Each
post uses a feature Muse's connectors can't reach: library music on a Reel, a Story poll, a library sound on TikTok and
on a Short (TikTok's web support for sounds is unclear). Muse had no connector for TikTok or YouTube when we checked
(Nov 1). Each post is a routine Envoy learned from one agent run (TikTok's and YouTube's with small hand edits), which
an agent calls as a tool of its own (`docs/technical-design.md`, "Routines as agent tools").

**Where it stands (Nov 2):**
- **Real posts, night of Nov 1.** All four app-only features have each gone live once. The Reel with a library song,
  the Story with a poll and the YouTube Short went live with 0 model calls each in Envoy's replay (the Spark agent's own
  calls aside). The TikTok first went up without its sound; the re-post (v3, 3 calls) went live with "golden hour".
  Each was started from the Spark agent on the author's go and approved on the iPhone (details below).
- **Muse, Nov 2 (a dry run, nothing posted).** Muse for Mac moved the clip to Envoy's outbox, called `send_to_phone`,
  then started five tasks through the routine tools, by name. The Reel, the TikTok and the Short each reached their
  final button with the song and the caption and were declined, at 0, 3 and 0 model calls in Envoy's replay (Muse's own
  calls aside): 195.5, 75.1 and 77.4 s from Muse's call to the end, phone ask and approval wait included. The poll
  Story failed twice: an unanswered phone ask (fixed in `947bf44`) and the live-Story gap below. Record:
  `eval/results/showcase/muse-2026-11-02/task-rows.json`, and `docs/muse-link.md`, "Nov 1–2: routine tools and the
  cross-post dry run".
- **Comments come back.** One Instagram comment on a showcase post reached the iPhone 1.57 s after it landed on Envoy's
  phone (Nov 2; agents see it at their next `phone_updates` check). A YouTube comment took about 2 minutes, all but
  3.6 s of it YouTube's own delay. No TikTok notification came (`prompts/phone-watch-report.md`).
- **Known gap:** the Story routine fails while a Story is already live: its first tap opens the live
  Story's poll results. One Story take per 24 hours, unless the live one is deleted.
- **Showcase routines don't run in the cloud.** Every run here was on the Pixel, except one dry-run Story task that an
  unanswered phone ask moved to an emulator, where it failed (fixed). Library songs and stickers are untested on
  emulators.

Status, Nov 1 (night): four routines in the library, each learned from one agent run (declined at the final button)
and recompiled with the compiler fix (main ffde928); `prompts/showcase-report.md` has the details:

| Tool (routine, v2) | Inputs | Replays (calls in Envoy's replay) | Learned vs tuned |
| --- | --- | --- | --- |
| `instagram_reel_song` | song_title, song_artist, caption | 3/3 at Share; 2 at 0 calls, 1 finished by the agent (16 calls) after Instagram's one-time audio tip | learned |
| `instagram_story_poll` (v3) | poll_question, poll_option_1, poll_option_2 | 3/3 at "Your story", 0 calls, right clip | learned |
| `tiktok_post_sound` | sound_title, sound_artist, caption | 3/3 at Post (each paused at launch and was resumed by the test script), 7–8 vision calls (~$0.02), **but no sound attached** (below) | learned; one step added, and the app and a launch check fixed by hand |
| `youtube_short_sound` | sound_title, sound_artist, short_title | v2 reached Upload Short every run (2 of the first 3 with the agent's help, 2–8 calls); with the case fix (953b014), 0 calls (1 rehearsal, then the live post) | learned, one step tuned |

Since Nov 2 the library runs v3 of all four. The Reel's and the Short's v3 are automatic repairs Envoy made during the
live posts (after-checks rewritten); both passed their trial in Muse's dry run at 0 calls in Envoy's replay. Each
`data/routines/<name>/index.json` lists every version and every hand edit. On Nov 3 the Reel moved to v4, a hand edit
after the posting batch: the caption edit ends with Instagram's OK instead of Back, and the caption is typed again if
it's empty before Share (`eval/results/showcase-batch/RESULTS.md`, "After the batch"). Since Nov 4 it runs v5, another
hand edit: an optional wait after Share. `data/routines/instagram_reel_song/index.json` has each version's runs; v6,
Envoy's own repair, is on trial.

The song for all three: JVKE's "golden hour" (in all three libraries). Which features work on the test accounts is
pre-check P3 (`eval/results/showcase/p3.md`).

**The real posts (Nov 2, about 01:00–02:31 ET).** meta-agent started each one on :8700 on the author's word, and the
author approved each in Envoy on the iPhone:
- Reel (`instagram_reel_song` v2): live, with the song, 0 model calls in Envoy's replay.
- Story with a poll (`instagram_story_poll` v3): live, 0 model calls in Envoy's replay.
- TikTok (`tiktok_post_sound` v2): went up **without the sound** ("Original sound by envoy"). The routine never attaches
  it. In its source run the agent's first try left the editor at "Add sound". The agent noticed and redid it (steps
  19–24), but the compiler dropped that correction as a "back-track". The step's after-checks look only for the label
  "Music", never the sound's name, and the rehearsals stopped at Post, whose screen doesn't show the sound. That post
  was left up.
- TikTok re-post (`tiktok_post_sound` v3, built with the compiler fix, v2's hand edits re-applied, and rehearsed 3/3):
  live as envoy, captioned "Posted by Envoy · test 2", with **♫ golden hour - JVKE**. 3 calls, 53 s, the editor's sound
  checked before Next.
- YouTube Short (`youtube_short_sound` v2): live and public. The details screen showed YouTube's music notice and
  #goldenhour, so the sound was on before Upload Short.

A routine learned from a declined post kept a done-check ("the caption is visible") that no run had seen after the post.
TikTok's ended a real post "failed". `compile --final-from-declined` drops it now (`tiktok_post_sound` v3 has none; the
library's `youtube_short_sound` v3 is an automatic repair that still has it).

## Before a take
- The newest video in the gallery is the clip: every routine picks the gallery's first slot. Push it last.
- Instagram: `scripts/instagram_take.py` (a reel started earlier comes back as "Keep editing your draft?").
- YouTube: `uv run --project backend python eval/run_showcase.py setup-youtube` (an autosaved draft makes Create open
  on "Continue your draft video?").
- TikTok: the launch pause ("came to the front on its own") didn't recur after main 8f7a082 (2 runs; one of them
  paused for another reason, "you touched the phone"). If the
  task pauses anyway, press Resume on the phone's Envoy banner.
- Each routine is a tool for Muse only once "Share with agents" is on (its page in Envoy).

## Kept honest on purpose

- **Test accounts only:** Instagram `envoy3955`, plus the TikTok and YouTube test accounts the author made and signed in
  to on the Pixel. Envoy and the coding sessions that built it never sign in, create accounts or type passwords.
- **Every post stops at the app's final button** (Instagram's Share, or Next with id `share_button`; TikTok's Post;
  YouTube's Upload Short) and waits for the person's OK. Rehearsals decline it. A real post happens only after the
  author says yes in chat.
- **No likes, follows, comments or DMs.** `eval/run_showcase.py tap` refuses them, and any publishing button, whatever
  flag it's given.
- **Wording:** "no connector" for TikTok and YouTube, never "Muse can't". Muse posts plain Instagram content itself, so
  the Instagram post must use an app-only feature (library music on a Reel, a poll sticker on a Story).

## The features (P3)

Sources: the apps' and APIs' own help pages, collected Nov 1 (the research notes themselves aren't in the repo).

| App | Feature | Why it's app-only (per the help pages, Nov 1) | On the test account |
| --- | --- | --- | --- |
| Instagram | A song from the music library on a Reel | The computer flow has no audio step; the API takes only original audio | **works** |
| Instagram | A poll sticker on a Story | The website can't post Stories; the API rejects stickers | **works** ("Multi-option Poll Sticker") |
| TikTok | A sound from the library | The official FAQ starts "In the TikTok app" (web sound support: sources conflict) | **works**; search results have no accessibility nodes (one point tap) |
| TikTok | An effect | App only | **works** (Edit › Effects) |
| TikTok | Voiceover | App only | found; records the room's microphone |
| TikTok | Duet | App only | found; record-only (films the room) |
| YouTube Shorts | A sound from the library | Android and iPhone only | **works** up to "Create channel" (the account has none yet) |
| YouTube Shorts | Green screen | Android and iPhone only | found; record-only (films the room) |
| YouTube Shorts | Remix | Android and iPhone only | **works** as "Use this sound" + a gallery clip |

## How it's run

Claim the Pixel first with the shared device lock (a local script outside the repo: `devices.sh claim pixel5 showcase 60
"<purpose>"`) and keep it upright.

**Stage 0 (P3), by hand, with no model calls:** `uv run --project backend python eval/run_showcase.py …`

- `facts` shows the phone and the apps' versions.
- `open <app> [--fresh]`, `tap "<label>"`, `type`, `swipe`, `key back` drive a flow.
- `look <label>` saves the masked screen under `eval/results/showcase/recon/`.
- `gate <dump> --app <app>` checks that the final button is irreversible by rule.
- `leave <app>` gets out of the composer without saving or posting.

Screenshots stay outside the repo until checked (`keep <stem>`), and none is taken while a camera viewfinder is open.

**Stage 1, on a test copy of the API** (`:8764`, its own data dir and outbox):

- `first --app <app> --goal "…"` is the agent's first run, declined at the post.
- `compile <trace> --name <new name> [--final-from-declined]` compiles it under a new name, never `instagram_post_reel`.
- `add-routine <yaml>` puts it in the library.
- `replay --routine <name> --input caption="…"` replays it once, declined at the post (each routine got three).

Calls, seconds and dollars go to `eval/results/showcase/runs/`. Before every run the copy is set to "always ask" for the
three apps: a request typed in Envoy's own app counts as approval for a button it names (`policy/approval_rules.py`).

**Cross-posting from the Mac:** a sidecar `{"app": "TikTok" | "YouTube", "caption": "…"}` next to a clip in the outbox
gets the same kind of offer as Instagram ("Put clip.mp4 on Envoy's phone and post it to TikTok?"): a plain post with
the caption; it doesn't use the sound routines yet. The templates are
`tiktok` and `youtube` in `api/handoff.py` `HANDOFF_TEMPLATES`. A Short's caption is its title (100 characters at most).
