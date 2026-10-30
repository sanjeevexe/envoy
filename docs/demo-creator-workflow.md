# Demo: the creator workflow (Mac → phone → Instagram)

The headline scene of the video. A clip finished on the Mac goes to the Android phone, Envoy offers to post it, the user
approves the Share, and the next time it runs from the routine Envoy learned. Instagram is Meta's app and Muse is Meta's
assistant: Envoy gives Muse the one surface it can't reach.

Kept honest on purpose: a **test account**, **every post approved by the user on Instagram's own Share screen**, low
volume, and **no likes, follows or DMs**.

Status: draft. Timings and screens marked *(to measure)* are filled in from stage 0's recon and the rehearsal
(`eval/run_creator.py rehearse`), recorded in `prompts/creator-workflow-report.md`.

## Before recording

| Where | State |
| --- | --- |
| Mac | Envoy's web app open on the API that runs the demo (the live API after the coordinator's restart). Muse for Mac open. A Finder window on `~/Envoy Outbox` (empty). The clip (`pier.mp4`) on the desktop. |
| iPhone | Envoy's companion (the PWA), paired, notifications on, screen recording ready. |
| Pixel 5 | Plugged in over USB, unlocked, screen on. Instagram signed in to the **test account** (envoy3955), on Home. No drafts in Instagram (New reel › Drafts: "No drafts yet"). Photos-and-videos access allowed for Instagram (done Oct 29). Its live view open in Envoy on the Mac. |
| Envoy settings | Settings › Phones: Instagram on "use my phone". Proactivity: Important (handoff offers push). |
| Second take | Routine `instagram_post_reel` active in the library (Routines page). A second clip (`pier-2.mp4`) on the desktop. |

## Shot list

| # | Screen | Who does what | What it shows | Expected time |
| --- | --- | --- | --- | --- |
| 1 | Mac | The creator asks Muse for Mac: "Send pier.mp4 to my phone for Instagram with the caption *Golden hour at the pier. Made on my Mac, posted from my phone.*" | Muse moves the clip into `~/Envoy Outbox` and writes `pier.json` (`{"app": "Instagram", "caption": "…"}`) | *(to measure)* |
| 2 | iPhone | The phone buzzes: **"Put pier.mp4 on your Pixel 5 and post it to Instagram?"** The card says what Envoy will do, word for word, and its "Before I start" lines. The user taps **Yes**. | The offer: nothing moves without a yes | offer within ~5 s of the sidecar |
| 3 | Mac (live view of the Pixel) | Nobody: Envoy puts the clip on the phone, opens Instagram, starts a reel, picks the newest video (it is first in the gallery), goes on, types the caption | The agent on the real phone | *(to measure)* |
| 4 | iPhone | **The approval for Instagram's last button** with the screenshot of the "New reel" screen (caption filled in). On Instagram 453 that button reads **Next** (its id is `share_button`; Envoy's rules know it publishes). The user checks the caption and taps **Approve**. | Publishing is never automatic: the request doesn't cover a public post, and the rule flags the button whatever it's called | *(to measure)* |
| 5 | Pixel / Mac | Instagram posts the reel; Envoy says it's done | The post on the test account's profile | *(to measure)* |
| 6 | Mac | Second clip, second caption, same steps 1–2. On the task page: **routine instagram_post_reel**, 0 model calls before Share | "The next time, in seconds and almost free" | *(to measure)* |
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

## Rehearsing

```bash
uv run --project backend python eval/run_creator.py rehearse --clip <clip.mp4> --caption "Envoy rehearsal" --api-dir <the copy's data dir>
```

Runs the whole flow on an API copy, says yes to the offer from that copy's session, and **declines at Share**, so nothing
is posted; then it discards the draft on the phone. It fails loudly if the task ever ends done without Share having been
asked. Rehearsal timing: *(to measure)*.
