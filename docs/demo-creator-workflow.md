# Demo: the creator workflow (Mac → phone → Instagram)

A clip finished on the Mac goes to the Android phone, Envoy offers to post it, the person
approves the Share, and the next time it runs from the routine Envoy learned. Instagram is Meta's app and Muse is Meta's
assistant: Envoy gives Muse the one surface it can't reach.

Ground rules: a **test account**, **every post approved by the person on Instagram's own Share screen**, low
volume, and **no likes, follows or DMs**.

Status: measured Oct 29 on the Pixel 5 (Instagram 453, test account envoy3955): two real posts approved by the author and
four rehearsals (`eval/results/creator/runs/runs.md`; details in `docs/reports/creator-workflow-report.md`). Rehearsed again
Oct 30 on the hybrid model profile, with the take setup in one command, a full-resolution recording of the phone, and the
phone called "Envoy's phone" on screen (`docs/reports/creator-rehearsal-report.md`).

On screen the Pixel is **Envoy's phone**: name it so in Settings › Phones (the name field under the phone), and offers,
"Before I start" and the task's notes say "Envoy's phone" instead of "your Pixel 5". `scripts/instagram_take.py --api-dir`
sets it too.

## Before recording

| Where | State |
| --- | --- |
| Mac | Envoy's web app open on the API that runs the demo (the live API, after its restart). Muse for Mac open. A Finder window on `~/Envoy Outbox` (empty). The clip (`pier.mp4`) on the desktop. |
| iPhone | Envoy's companion (the PWA), paired, notifications on, screen recording ready. |
| Pixel 5 | Plugged in over USB, unlocked, screen on. Instagram signed in to the **test account** (envoy3955). Instagram's photos-and-videos, camera and microphone access allowed (done Oct 29), so no Android dialog pauses the run. Then **`scripts/instagram_take.py --routine off`** (take 1) or **`--routine on`** (take 2), below: it leaves Instagram on Home with Create opening the gallery. Optional: delete the rehearsal drafts by hand (Create › Drafts › ⋯ › Delete; they show as "Drafts · N" on the gallery screen). Its live view open in Envoy on the Mac. **Nobody touches the phone during a take**: a touch pauses Envoy ("Envoy paused · Resume"). |
| Envoy settings | Settings › Phones: the Pixel named **Envoy's phone**; Instagram on "use my phone". Proactivity: Important (handoff offers push). |
| Warm-up | In a checkout that hasn't run the agent on the Pixel yet, the first agent run spends ~55 s reading the phone's app names (`data/apps/labels.json`, once per checkout and app version; routines don't need it). `scripts/instagram_take.py` reads them first (52 s the first time, ~1 s after), so take 1 doesn't pay it. |
| Second take | Routine `instagram_post_reel` active in the library (Routines page); Instagram's offer runs it. A second clip (`pier-2.mp4`) on the desktop. |
| Recording | `scripts/record_phone.sh` in a terminal before the take (below); Ctrl-C after. |

## Shot list

| # | Screen | Who does what | What it shows | Expected time |
| --- | --- | --- | --- | --- |
| 1 | Mac | The creator asks Muse for Mac: "Send pier.mp4 to my phone for Instagram with the caption *Golden hour at the pier. Made on my Mac, posted from my phone.*" | Muse moves the clip into `~/Envoy Outbox` and writes `pier.json` (`{"app": "Instagram", "caption": "…"}`) | not measured here: the runs wrote the sidecar and clip themselves (Muse for Mac is covered in `docs/muse-link.md`) |
| 2 | iPhone | The phone buzzes: **"Put pier.mp4 on Envoy's phone and post it to Instagram?"** The card says what Envoy will do, word for word, and its "Before I start" lines ("I'll use Envoy's phone (you said yes).", "Sharing will need your OK."). The creator taps **Yes**. | The offer: nothing moves without a yes | offer 4–6 s after the clip lands |
| 3 | Mac (live view of the Pixel) | Nobody: Envoy puts the clip on the phone, opens Instagram, starts a reel, picks the newest video (it is first in the gallery), goes on, types the caption, OK | The agent on the real phone | hybrid (Oct 30): 46–50 s from Yes to the approval, 9 model calls, ~$0.12 (105 s on a checkout that hadn't read the phone's app names: see Warm-up). Spark (Oct 29): 49 s, 12 calls, $0.06 |
| 4 | iPhone | **"Approve: tap Share"** with the screenshot of the "New reel" screen (caption filled in). The creator checks the caption and taps **Approve**. (On an account's very first reel the button reads **Next** and one more screen with Share follows; both are `share_button`, both ask. The test account is past that.) | Publishing is never automatic: the request doesn't cover a public post, and the rule flags the button by its id whatever it's labelled | the creator's time |
| 5 | Pixel / Mac | Instagram posts the reel ("Done posting"); Envoy says it's done | The post on the test account's profile | ~10 s after Approve |
| 6 | Mac | Second clip, second caption, same steps 1–2. On the task page: **Routine steps** (Open new post creation … Tap share), then the same Share approval | "The next time, learned and almost free" | v2 on hybrid (Oct 30): 47–54 s from Yes to the approval, 2 repair calls, ~$0.03; once in five runs the repair asked an extra approval. The v3 candidate (`eval/results/creator/routine/`, not in the library): 18–20 s, 0 calls. Spark, Oct 29: 38–44 s, 2 calls |
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
| No sidecar at all | The offer is "Put pier.mp4 on Envoy's phone?" (push only). Say yes, then ask Envoy "Post the newest video in my phone's gallery to Instagram as a reel with this caption: …" (Share still asks). |
| Instagram shows a pop-up (seen in stage 0: a "Brand survey" on opening, "Others can now download and share your reels" on the last screen, an "Add to your story" tip) | The agent handles pop-ups; if it stalls, the creator takes over in the live view, closes it, and hands back. Open Instagram once before recording so the survey is gone. |
| The run stops at a step it can't do | Take over in the live view, finish up to Share, hand back; the Share approval still comes. |
| The post fails, or Instagram is down | Wait and re-record the take. |
| The routine fails on take 2 | It falls back to repair and then the agent by itself; the take still ends at the Share approval (just slower). Re-record take 2. |
| Instagram's Create opens "Keep editing your draft?" or the camera instead of the gallery | Run `scripts/instagram_take.py` again before the take. Any visit to the reel editor (a rehearsal, a stopped run) leaves a half-made reel that comes back after Instagram restarts, and every run restarts it; the script clears it with "Start new video" (it becomes a private draft) and checks Create twice after a restart. During a run, the routine repairs it with ~2 model calls. |
| An approval you didn't expect, before Share ("tap Unselected Video thumbnail …" or "tap Gallery") | v2's repair on hybrid (Muse Wonder) sometimes labels the gallery taps irreversible: 1 of 5 Oct 30 runs asked you (another was covered by the request). Approve it; Share still asks. The v3 candidate (below) makes no repair there. |
| Someone touches the phone mid-run ("Envoy paused") | Press **Resume** on the banner at the top of the Pixel's screen; Envoy goes on from what's on screen. If you tapped Share on the phone yourself, an Approve given afterwards in Envoy taps nothing (the screen changed). |

## Muse reports back (check once with Muse for Mac)

Shot 5's "Posted" from Muse comes from Envoy's `phone_updates` tool. Envoy's side was checked on the copy (Oct 30): after
each rehearsal it reads `"rehearse-1-032054.mp4" is in the gallery of Envoy's phone (Movies/Envoy/…)` and the task's
`Failed: "Post the newest video …" (User declined …)`. After a real post it reads `"pier.mp4" was posted from Envoy's
phone` and `Finished: "Post the newest video …"` (`tests/test_phone_name.py`); the file turns `posted` only when the task
ends done, so only a real post shows it. Seen through Muse for Mac on Nov 1 (a dry run on the Pixel and the live API,
declined at Share): Muse answered "pier.mp4 is in the gallery of Envoy's phone, at Movies/Envoy/pier.mp4" and that the
Instagram task "did not complete… approval to tap Share… was declined", then "So the video made it to your phone, it
just wasn't posted to Instagram." Yes to the Share approval took 45 s (agent, 9 model calls, $0.12). What to expect on a take:

- **The permanent address** (`scripts/muse_funnel.sh on`, Tailscale Funnel on port 10000, /mcp only, `MCP_PERMANENT_URL`
  in `.env`) is set up in Muse once, with "Always allow"; takes need no tunnel. With a quick tunnel instead, every new
  address means re-pointing the connector: ask Muse to update the Envoy connector's URL; it shows a Connect card where
  you paste the key again (same key), then asks "Allow Muse to share information with <host>?" once.
- Muse **copies** the clip into `~/Envoy Outbox` (the original stays on the Desktop), writes the sidecar, and also calls
  `send_to_phone`; it's still one offer.
- Muse's reply ends with an **"Approve it here"** card showing the Mac's tailnet address (`send_to_phone` returns the
  app's link). Crop or blur it in the edit.

The steps (the author does 2's tunnel, the key, and the iPhone):

1. The live API on main with the phone name (after the merge and the API's restart); Settings › Phones: Envoy's phone.
2. `scripts/instagram_take.py --routine off` from the main checkout. Muse reaches Envoy at the permanent address (or,
   without it, `ENVOY_PORT=8700 scripts/start_muse_test.sh` and re-point the connector).
3. Muse for Mac: "Send pier.mp4 to my phone for Instagram with the caption …"; allow its two prompts (Always allow, for
   takes without prompts).
4. iPhone: "Put pier.mp4 on Envoy's phone and post it to Instagram?" → Yes. At Share: Approve only on the real take
   (a public post on envoy3955); Decline for a dry check (then step 5 shows "Failed", not "Posted").
5. Ask Muse: "Check Envoy's phone_updates: what happened to pier.mp4?" Expect it to relay "was posted from Envoy's
   phone" and the finished task; note its exact words for the voice-over. Optionally, before step 4, ask Muse to check
   phone_updates every 2 minutes and tell you when the post is done (E1 showed scheduled checks work, ~10 min apart).

## When Envoy runs in the cloud: the outbox forwarder

The outbox forwarder was built and merged Nov 1 (`869271f`). Muse for Mac always writes the clip to `~/Envoy Outbox`, and the
person never picks a route:

| Where the clip is | Envoy on the Mac | Envoy in the cloud (`docs/cloud.md`) |
| --- | --- | --- |
| On the Mac, in `~/Envoy Outbox` | Envoy's own watcher, as above | The **outbox forwarder** sends it through Envoy's **door** |
| Online, an https link | `send_to_phone` with the link | The same |

- **The door** is `/mcp/outbox`, beside `/mcp`, with the same MCP key (`MCP_BEARER_TOKEN`) and nothing else: no
  session token, no other path. Because it sits under `/mcp`, it is reached wherever Muse reaches `/mcp`: the tailnet
  address, a quick tunnel, or Funnel's `/mcp` path: Tailscale passes the paths under `--set-path=/mcp` on, so
  `scripts/muse_funnel.sh` needs no change (checked Nov 1 on the live Funnel: `/mcp/outbox` reached the API, which
  answered 401 without the key; other paths got Tailscale's 404). On a public host it is the only path
  besides `/mcp` (`api/app.py` dispatch). A clip and its sidecar sent there land in that Envoy's outbox as if dropped in:
  the same handoff, the same offer ("Put pier.mp4 on … and post it to Instagram?"), the same yes. It takes photos and
  videos only (by their bytes), at most 500 MB, cleans the name (no folders, hidden names or control characters; otherwise
  as sent, so Muse's file name still finds it), and logs each call to `logs/door.jsonl` (never the key).
- **The forwarder** is a small Mac-side process, no phones and no models (`backend/api/forwarder.py`). In the Mac's
  `.env`, the user sets `ENVOY_REMOTE_URL` to the cloud Envoy's MCP address (the one Muse's connector uses, such as
  `https://envoy-cloud.<tailnet>.ts.net:8443/mcp`) and `ENVOY_REMOTE_TOKEN` to its MCP key (`scripts/cloud/muse-token.sh`
  puts it on the clipboard). Then:

  ```bash
  uv run --project backend python -m api.forwarder        # until Ctrl-C
  ```

  With no `ENVOY_REMOTE_URL`, or one that names this Mac, it says "Envoy runs on this Mac" and stops: the watcher already
  handles the outbox. If an Envoy also answers on this Mac, it stops too (each clip would be offered twice) unless started
  with `--also-here`.
- **What it does.** Each new clip goes once its size has held for 2 s, with its sidecar if one is there; a sidecar that
  comes later follows on its own, and the cloud Envoy's watcher treats it exactly as here (up to 30 s late it makes the
  first offer; later, it replaces the offer). Sent files move to `~/Envoy Outbox/Sent/` (never deleted; a second
  `pier.mp4` becomes `pier-2.mp4` there), and one line says what went where and what Envoy is doing with it, for example
  `Sent pier.mp4 (49.2 MB) with pier.json to Envoy at envoy-cloud.<tailnet>.ts.net. Envoy has pier.mp4 and is asking you
  in its app: "…" Moved to Sent/pier.mp4.` Offline or while that Envoy restarts, the clip stays and is tried again (5, 10,
  30 s, then every minute; said once); a retry of a clip the door already has is recognized, so it isn't offered twice. A
  clip Envoy refuses (too big, not a video) stays, said once. What was already in the outbox when it started stays, as
  with the watcher (`--send-waiting` sends it).
- **Muse doesn't know where Envoy runs.** It writes the clip and the sidecar and calls `send_to_phone("pier.mp4")` as it
  does now; on the cloud Envoy that call waits while the clip is still coming through the door (up to 50 s), and a few
  seconds for one not there yet while the forwarder is in touch. `list_phones` tells Muse each phone's kind (`cloud`,
  `emulator` on the Mac, or `real`), whether it is online, and its apps, so it can say "post it from the cloud phone".
- **No offer from a cloud phone.** Instagram's handoff asks for a real phone, so a clip for Instagram waits in the
  cloud outbox. The Nov 1 cloud run went round it: `send_to_phone` put the clip on the emulator and `run_task` took it
  to Share (`docs/cloud.md`).

## Setting up a take (one command)

From the checkout whose API films the take (claim `pixel5` first):

```bash
uv run --project backend python scripts/instagram_take.py --routine off   # take 1: the agent's first run
```

```bash
uv run --project backend python scripts/instagram_take.py --routine on    # take 2: from the learned routine
```

It takes ~30–45 s (about a minute more the first time in a checkout) and ends with `READY` or `NOT READY` and the reason. In order: anything in the outbox is moved to
"`<outbox> before <time>`" beside it (never deleted); the routine is switched on or off in that checkout's library
(`RoutineStore.switch`: off, an offer that names it runs the agent; its versions and runs stay); on the phone, Instagram
is restarted and checked to be signed in to envoy3955 (from Home's story tray; anything else stops it), and Create is
opened until it shows the gallery ("New reel") right after a restart twice in a row, then back to Home; last, the
phone's app names are read for the agent (Warm-up, above). It taps only a
fixed list of Instagram's buttons (Create, Back to Home, Gallery, Cancel, Start over, Keep editing, Start new video, a
pop-up's close) and never Share, Next, Post, Save draft, Follow or Like. With `--api-dir <the API's data dir>` (and
`--api http://127.0.0.1:<port>`) it also answers that API's pending handoff offers "not now" and names the phone
"Envoy's phone" there (`--phone-name`). `--check` changes nothing and says how things stand.

Run it before every take and every rehearsal: a run that visited the reel editor leaves a half-made reel that Instagram
offers back after a restart ("Keep editing your draft?"); its only answer that sticks is "Start new video", which keeps
it as a private draft, so each rehearsal adds one draft (delete them by hand before filming if "Drafts · N" bothers you).
Measured Oct 30: 19 setups READY (every one that ran to the end), each with Create → gallery twice after a restart (the first version of the
script missed the delayed "Keep editing your draft?"; fixed).

## Recording Envoy's phone

```bash
scripts/record_phone.sh                     # Ctrl-C stops; the file is ~/Movies/Envoy takes/phone-<date>-<time>.mp4
```

`-o <file.mp4>` saves it elsewhere; `kill <pid>` stops it from a script. A second scrcpy beside Envoy's own (each has its
own server file and session id): read-only (`--no-control`), no window, no audio, the phone's full 1080×2340, up to 60 fps,
16 Mbit/s H.264 (`-f 30` for at most 30 fps). scrcpy sends a frame only when the screen changes, so the file has a
variable frame rate (~25 fps average in a take at 60). After it stops, the script rewrites the stream's colour tag to BT.601 without re-encoding: the Pixel 5
tags its video YCgCo, which FFmpeg refuses to convert and editors may show in the wrong colours. Measured Oct 30 during
routine rehearsals: no errors on either side, but Envoy is a little slower while it records, since the phone encodes
twice: the v3 candidate took 23–25 s from Yes to Share at 60 fps and 22 s at 30 fps (`-f 30`), against 18–20 s
unrecorded. Fine for a time-lapsed take. Files are ~1.1 MB/s (49 MB for 45 s). The recording shows Envoy's banner ("Envoy is using this phone · Pause") over Instagram's
title bar while Envoy works. `adb shell screenrecord` is the fallback (3 minutes at most, written on the phone first).

## Rehearsing

```bash
uv run --project backend python eval/run_creator.py rehearse --clip <clip.mp4> --caption "Envoy rehearsal" --api http://127.0.0.1:<port> --api-dir <the copy's data dir>
```

Runs the whole flow on an API copy, says yes to the offer from that copy's session, and **declines at Share**, so nothing
is posted; then it leaves the composer with Start over (no draft saved; the next `instagram_take.py` clears what comes
back). It fails loudly if the task ever ends done without Share having been asked, or if anything before Share waited for
the user. Timings are in the shot list and `docs/reports/creator-rehearsal-report.md`; Oct 29 (Spark): ~45–52 s from the clip
to the declined Share with the routine (2 model calls, ~$0.01), ~2 min with the agent alone (14 calls, $0.06).
