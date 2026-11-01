# The creator workflow on the cloud phone (Nov 1, backlog #49)

One declined run on the cloud copy's **Real-app phone** (`envoy-real` on the VM `envoy-cloud`: x86_64 Android 15
emulator, `-gpu swangle`, no GPU), by the link path. **Instagram runs there, and the run reached the Share approval
112 s after the task started; it was declined, and nothing was posted** (envoy3955 still shows 2 posts afterwards).
Driver: `scripts/cloud/instagram_link.py`. Write-up: `docs/cloud.md`, "The creator workflow on the cloud phone".

| | Mac, Pixel 5 (Nov 1 dry run, `docs/demo-creator-workflow.md`) | Cloud phone (this run) |
| --- | --- | --- |
| Start | Yes to the offer | `run_task` (there is no offer for an emulator, below) |
| Start → Share asked | 45 s | **112.0 s** (the clip's download and push before it: 2.2 s) |
| What ran | the agent | routine `instagram_post_reel` v2 for its first step, which failed on Instagram's first-run screens; then the agent |
| Model calls to Share | 9 | **12** (match 1, repair 2, plan 1, step 8) |
| Meta to Share | $0.12 | **$0.155** |
| Whole task (after the decline: 1 step, 2 app notes) | | 15 calls, $0.181 |

## Does Instagram run on the cloud emulator?

Yes. Instagram 453.0.0.57.79 (the Pixel's version) installed from the Play Store in 76 s and opened at its login screen
(`first-launch.png`). The user signed in as envoy3955 through the cloud copy's live view (Google's password manager
offered the saved password) and allowed photos and videos. No bot check, no emulator warning, no crash (the emulator's
crash log stayed empty), from first launch through the run and the cleanup. The phone's WebView and Chrome were already
156 from the Oct 29 updates, so the version-124 problem didn't arise.

## The run, second by second (from the task's start, 20:38:42 UTC)

| s | What |
| --- | --- |
| −2.4 to −0.2 | `send_to_phone("https://test-videos.co.uk/…/Big_Buck_Bunny_720_10s_1MB.mp4", device="envoy-real")`: Envoy on the VM downloads it (1 MB) and puts it in the gallery (`Movies/Envoy/`) |
| 0 | `run_task("Post the newest video in my phone's gallery to Instagram as a reel with this caption: \"Envoy cloud rehearsal\"")`, the Instagram template's goal; "Before I start": anything that can't be undone waits for your OK |
| 3.5 | matched to routine `instagram_post_reel` v2 |
| 3.5–41 | its first step, `open_new_post_creation`: a permission prompt (the pop-up handler denied it), a 5 s wait, then two repairs (the first skipped "Set up on new device: allow access to contacts"); its checks still didn't match, so the full agent took over (rung 6) |
| 56 | the agent's plan |
| 59–104 | 7 agent steps: REEL, the newest video's thumbnail, close an "Edits" promo sheet, Next, OK on a bottom sheet, the caption field, type the caption |
| 112.0 | the agent taps the publishing button: **Share is asked** (`tap "Next"`, rule: target id `com.instagram.android:id/share_button`; the model also labelled it irreversible) |
| 112.6 | declined through the cloud copy's own API, after `new-reel.png` (the phone, adb) and `share-approval.jpg` (the picture on the approval) were saved |
| 116.6 | the task ends `declined`; the composer is left without posting or saving (Back, Cancel → Start over, a permission dialog dismissed with Back, gallery → Home) |

Model time was about 35 s of the 112 s (each call 1.2–6.5 s); the rest was the phone: Instagram drawing in software,
waits for screens to settle, and the routine's waits. In the agent's part alone (plan to Share, about 70 s), the model
took 24 s.

## What came up

1. **No offer on an emulator.** `send_to_phone` puts a file on an emulator at once and asks nothing, so no Instagram
   task starts by itself (`mcp_server/server.py`). The outbox route makes no offer either: the Instagram template asks
   for a real phone, and with none connected its device is empty. The run therefore started with `run_task`, as the
   creator doc's "No sidecar at all" fallback does, and as Muse would. Coming from an AI client (source `mcp`), every
   irreversible step asks, whatever the approval mode; the driver also checked that no "never" mode covered Instagram.
2. **The download fails on a host that sorts an IPv6 address first.** `Handoff._download` connects to the first of the
   name's addresses, sorted as text, and the VM has no IPv6 route. The first attempt, MDN's CC0 `flower.mp4`
   (`2600:1901:…` before `34.111.242.42`), failed in 0.5 s with "the download failed (ConnectError)", though `curl` on the
   VM fetched it. `test-videos.co.uk` (`104.21.60.65` first) worked. Nothing reached the phone in the failed attempt.
3. **A fresh install's first-run screens cost the routine its first step** (about 40 s and 3 model calls before the
   agent began). The Pixel's Instagram was past them.
4. Instagram labels its publishing button **Next** on this install, as on the Pixel's first reel; the `share_button` id
   rule caught it.

## Files

- `first-launch.png`: Instagram's login screen on the cloud phone, before the sign-in.
- `20261101-203839/run.json`: the run (send_to_phone, the task, its steps and approval, marks, spend, cleanup).
  `run-log.txt`: the driver's output.
- `20261101-203839/new-reel.png`: the phone at the Share approval (1080×2400): New reel, the caption, Save draft / Next.
- `20261101-203839/share-approval.jpg`: the picture Envoy attached to the Share approval (540 px), what the approval
  card shows.

The cloud phone was otherwise left as it was: still signed in to Instagram, with the clip in its gallery. The VM was
stopped after the run, with no key on it.
