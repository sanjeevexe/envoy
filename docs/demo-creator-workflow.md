# Demo: the creator workflow (Mac → phone → Instagram)

The headline scene of the video. A clip finished on the Mac goes to the Android phone, Envoy offers to post it, the user
approves the Share, and the next time it runs from the routine Envoy learned. Instagram is Meta's app and Muse is Meta's
assistant: Envoy gives Muse the one surface it can't reach.

Kept honest on purpose: a **test account**, **every post approved by the user on Instagram's own Share screen**, low
volume, and **no likes, follows or DMs**.

Status: measured Oct 29 on the Pixel 5 (Instagram 453, test account envoy3955): two real posts approved by the user and
four rehearsals (`eval/results/creator/runs/runs.md`; details in `prompts/creator-workflow-report.md`).

## Before recording

| Where | State |
| --- | --- |
| Mac | Envoy's web app open on the API that runs the demo (the live API after the coordinator's restart). Muse for Mac open. A Finder window on `~/Envoy Outbox` (empty). The clip (`pier.mp4`) on the desktop. |
| iPhone | Envoy's companion (the PWA), paired, notifications on, screen recording ready. |
| Pixel 5 | Plugged in over USB, unlocked, screen on. Instagram signed in to the **test account** (envoy3955), on Home. Instagram's photos-and-videos, camera and microphone access allowed (done Oct 29), so no Android dialog pauses the run. Optional: delete the rehearsal drafts (New reel › Drafts: they show as "Drafts · N" on the gallery screen). Its live view open in Envoy on the Mac. **Nobody touches the phone during a take**: a touch pauses Envoy ("Envoy paused · Resume"). |
| Envoy settings | Settings › Phones: Instagram on "use my phone". Proactivity: Important (handoff offers push). |
| Second take | Routine `instagram_post_reel` (v2) active in the library (Routines page); Instagram's offer runs it. A second clip (`pier-2.mp4`) on the desktop. |

## Shot list

| # | Screen | Who does what | What it shows | Expected time |
| --- | --- | --- | --- | --- |
| 1 | Mac | The creator asks Muse for Mac: "Send pier.mp4 to my phone for Instagram with the caption *Golden hour at the pier. Made on my Mac, posted from my phone.*" | Muse moves the clip into `~/Envoy Outbox` and writes `pier.json` (`{"app": "Instagram", "caption": "…"}`) | not measured here: the runs wrote the sidecar and clip themselves (Muse for Mac is muse-link's sitting) |
| 2 | iPhone | The phone buzzes: **"Put pier.mp4 on your Pixel 5 and post it to Instagram?"** The card says what Envoy will do, word for word, and its "Before I start" lines ("I'll use your Pixel 5", "Sharing will need your OK"). The user taps **Yes**. | The offer: nothing moves without a yes | offer 4–6 s after the clip lands |
| 3 | Mac (live view of the Pixel) | Nobody: Envoy puts the clip on the phone, opens Instagram, starts a reel, picks the newest video (it is first in the gallery), goes on, types the caption, OK | The agent on the real phone | ~50 s from Yes to the approval (post 2: 49 s, 12 model calls, $0.05) |
| 4 | iPhone | **"Approve: tap Share"** with the screenshot of the "New reel" screen (caption filled in). The user checks the caption and taps **Approve**. (On an account's very first reel the button reads **Next** and one more screen with Share follows; both are `share_button`, both ask. The test account is past that.) | Publishing is never automatic: the request doesn't cover a public post, and the rule flags the button by its id whatever it's labelled | the user's time |
| 5 | Pixel / Mac | Instagram posts the reel ("Done posting"); Envoy says it's done | The post on the test account's profile | ~10 s after Approve |
| 6 | Mac | Second clip, second caption, same steps 1–2. On the task page: **Routine steps** (Open new post creation … Tap share), then the same Share approval | "The next time, learned and almost free" | ~40 s from Yes to the approval, 2 model calls, ~$0.01 (rehearsals: 38.3–43.9 s) |
| 7 | Mac | Activity / the task page side by side: first run vs routine (steps, seconds, model calls, cost) | The learning, in numbers | – |

### Captions (exact)

- Take 1: `Golden hour at the pier. Made on my Mac, posted from my phone.`
- Take 2: `Same pier, five minutes later. Envoy remembered how.`
- Rehearsals: `Envoy rehearsal <time>` (declined at Share: never posted)

Plain ASCII on purpose: the caption is typed through the ADB keyboard (checked in stage 0); emoji weren't tried.

## Fallbacks

| If | Then |
| --- | --- |
| Muse for Mac can't write the sidecar (or asks for a permission mid-take) | Drag `pier.mp4` and a prepared `pier.json` into `~/Envoy Outbox` together (the sidecar first). A sidecar that arrives up to 30 s after the clip still counts; a later one replaces the offer. |
| No sidecar at all | The offer is "Put pier.mp4 on your Pixel 5?" (push only). Say yes, then ask Envoy "Post the newest video in my phone's gallery to Instagram as a reel with this caption: …" (Share still asks). |
| Instagram shows a pop-up (seen in stage 0: a "Brand survey" on opening, "Others can now download and share your reels" on the last screen, an "Add to your story" tip) | The agent handles pop-ups; if it stalls, the user takes over in the live view, closes it, and hands back. Open Instagram once before recording so the survey is gone. |
| The run stops at a step it can't do | Take over in the live view, finish up to Share, hand back; the Share approval still comes. |
| The post fails, or Instagram is down | Cut to the pre-recorded take of the first real post. |
| The routine fails on take 2 | It falls back to repair and then the agent by itself; the take still ends at the Share approval (just slower). Re-record take 2. |
| Instagram's Create opens the camera or "Keep editing your draft?" instead of the gallery | Expected: it depends on how the composer was last left. The routine repairs it with ~2 model calls (the 2 calls in shot 6). After take 2 posts, Envoy proposes a patched routine with that screen as an optional step (trial, then active after a run with 0 model calls). |
| Someone touches the phone mid-run ("Envoy paused") | Press **Resume** on the banner at the top of the Pixel's screen; Envoy goes on from what's on screen. If you tapped Share on the phone yourself, an Approve given afterwards in Envoy taps nothing (the screen changed). |

## Rehearsing

```bash
uv run --project backend python eval/run_creator.py rehearse --clip <clip.mp4> --caption "Envoy rehearsal" --api-dir <the copy's data dir>
```

Runs the whole flow on an API copy, says yes to the offer from that copy's session, and **declines at Share**, so nothing
is posted; then it discards the draft on the phone. It fails loudly if the task ever ends done without Share having been
asked. Rehearsal timing: ~45–52 s from the clip to the declined Share with the routine (2 model calls, ~$0.01); ~2 min with
the agent alone (14 calls, $0.06).
