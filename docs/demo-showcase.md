# Demo: the app-only cross-post (Instagram + TikTok + YouTube Shorts)

The video's climax (T1c, `prompts/phone-layer-plan.md` §5 "showcase"). One clip is posted from Envoy's phone (the Pixel
5) to Instagram, TikTok and YouTube Shorts. Each post uses a feature that the website and Muse's connectors don't have,
and each is a routine Envoy learned, which an agent calls as a tool (agent-door's routine tools).

Status, Nov 1 (night): four routines in the library, each learned from one agent run (declined at the final button)
and recompiled with the compiler fix (main ffde928); `prompts/showcase-report.md` has the details:

| Tool (routine, v2) | Inputs | Replays | Learned vs tuned |
| --- | --- | --- | --- |
| `instagram_reel_song` | song_title, song_artist, caption | 3/3 at Share, 0 calls unless Instagram shows a tip | learned |
| `instagram_story_poll` (v3) | poll_question, poll_option_1, poll_option_2 | 3/3 at "Your story", 0 calls, right clip | learned |
| `tiktok_post_sound` | sound_title, sound_artist, caption | 3/3 at Post, ~7 vision calls (~$0.02) | learned, one step added |
| `youtube_short_sound` | sound_title, sound_artist, short_title | 3/3 at "Upload Short", 2–8 calls | learned, one step tuned |

The song for all three: JVKE's "golden hour" (in all three libraries). Which features work on the test accounts is
pre-check P3 (`eval/results/showcase/p3.md`).

## Before a take
- The newest video in the gallery is the clip: every routine picks the gallery's first slot. Push it last.
- Instagram: `scripts/instagram_take.py` (a reel started earlier comes back as "Keep editing your draft?").
- YouTube: `uv run --project backend python eval/run_showcase.py setup-youtube` (an autosaved draft makes Create open
  on "Continue your draft video?").
- TikTok: the launch pause ("came to the front on its own") didn't recur after main 8f7a082 (2 runs). If the
  task pauses anyway, press Resume on the phone's Envoy banner.
- Each routine is a tool for Muse only once "Share with agents" is on (its page in Envoy).

## Kept honest on purpose

- **Test accounts only:** Instagram `envoy3955`, plus the TikTok and YouTube test accounts the user made and signed in to
  on the Pixel. Envoy and the sessions never sign in, create accounts or type passwords.
- **Every post stops at the app's final button** (Instagram's Share, or Next with id `share_button`; TikTok's Post;
  YouTube's Upload Short) and waits for the user's OK. Rehearsals decline it. A real post happens only after the user
  says yes in chat.
- **No likes, follows, comments or DMs.** `eval/run_showcase.py tap` refuses them, and any publishing button, whatever
  flag it's given.
- **Wording:** "no connector" for TikTok and YouTube, never "Muse can't". Muse posts plain Instagram content itself, so
  the Instagram post must use an app-only feature (library music on a Reel, a poll sticker on a Story).

## The features (P3)

Sources: `prompts/app-only-research.md`.

| App | Feature | Why it's app-only | On the test account |
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

Claim the Pixel first (`~/Desktop/Envoy/coord/devices.sh claim pixel5 showcase 60 "<purpose>"`) and keep it upright.

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
- `replay --routine <name> --input caption="…"` replays it three times, declined at the post.

Calls, seconds and dollars go to `eval/results/showcase/runs/`. Before every run the copy is set to "always ask" for
the three apps: a request typed in Envoy's own app counts as approval for a button it names (`policy/approval_rules.py`).

**Cross-posting from the Mac:** a sidecar `{"app": "TikTok" | "YouTube", "caption": "…"}` next to a clip in the outbox
gets the same offer as Instagram ("Put clip.mp4 on Envoy's phone and post it to TikTok?"). The templates are
`tiktok` and `youtube` in `api/handoff.py` `HANDOFF_TEMPLATES`. A Short's caption is its title (100 characters at most).
