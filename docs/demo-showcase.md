# Demo: the app-only cross-post (Instagram + TikTok + YouTube Shorts)

The video's climax (T1c, `prompts/phone-layer-plan.md` §5 "showcase"). One clip is posted from Envoy's phone (the Pixel
5) to Instagram, TikTok and YouTube Shorts. Each post uses a feature that the website and Muse's connectors don't have,
and each is a routine Envoy learned, which an agent calls as a tool (agent-door's routine tools).

Status, Nov 1: prepared, not yet run on the phone. Which features work on the test accounts is pre-check P3 (below). The
user picks the showcase from that report.

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
| Instagram | A song from the music library on a Reel | The computer flow has no audio step; the API takes only original audio | not checked yet |
| Instagram | A poll sticker on a Story | The website can't post Stories; the API rejects stickers | not checked yet |
| TikTok | A sound from the library | The official FAQ starts "In the TikTok app" (web sound support: sources conflict) | not checked yet |
| TikTok | An effect | App only | not checked yet |
| TikTok | Voiceover | App only | not checked yet |
| TikTok | Duet | App only | not checked yet |
| YouTube Shorts | A sound from the library | Android and iPhone only | not checked yet |
| YouTube Shorts | Green screen | Android and iPhone only | not checked yet |
| YouTube Shorts | Remix | Android and iPhone only | not checked yet |

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
