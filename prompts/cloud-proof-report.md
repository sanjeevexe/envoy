# cloud-proof: report

Oct 29, 2026. Branch `claude/brave-kepler-5457be`. Brief: `prompts/cloud-proof.md`. Full write-up: `docs/cloud.md`.

**Stages 0, 1 and 2 are done (in main at `b3bad38`). Stage 3 (all of Envoy in the cloud, as a second option) is built and measured; see below.** No product code changed: `scripts/cloud/`, `docs/cloud.md`, `eval/results/cloud/`, a two-line pointer in `docs/phase-0-findings.md`, and this report.

## Results

| | Mac (recorded earlier, not re-run) | Google Cloud `n2-standard-8`, `us-east1-b` |
| --- | --- | --- |
| Phase 6 portability (6 routines × 3 unseen bookings) | 18/18, 0 model calls, median 3.6 s, max 6.6 s | **18/18**, 0 model calls, median 6.2 s, max 12.0 s |
| Phase 7 sizes (10 core routines × 3 unseen bookings) | 30/30, 0 calls, median 2.8 s | **30/30**, 0 calls, median 5.4 s |
| A brand-new emulator's first run | (not applicable) | 9/18: the first nine runs failed while Android did its first-boot work; then everything passed |
| Right after a restart (cold boot, not first boot) | | 6/6 |
| Cold boot | 19 s first, 12–13 s later | 33 s first, 32 s after a restart |
| Tree read / raw gRPC screenshot / gRPC tap | 31 ms / 6 ms / 0.6 ms | 85 ms / 32 ms / 0.9 ms |
| Stage 2: agent run on the Denver check-in | 10 actions, 12 calls, 22.3 s, $0.023 | 8 actions, 10 calls, 25.3 s, $0.019 |
| Stage 2: compile (Wonder), verify | $0.049, 12.3 s; 4.6 s + 4.0 s | $0.051, 17.4 s; 9.6 s + 9.4 s |
| Stage 2: the cloud-learned routine on unseen bookings | | **3/3**, 0 calls, 9.2–9.4 s |

Routines are about 2× slower in the cloud (1.6–2.3× each), because the VM has no GPU (SwiftShader) and every screen read is 2–5× slower. The slowest routine run was 12 s, inside the 30 s target. The agent run was 13% slower, but that is one run.

**Two findings that matter for stage 3:**
1. **A new AVD needs a warm-up before use.** Its first-boot work (Play services, app updates, compiling apps) used 134% CPU, and routine steps timed out. A restarted AVD was fine at once.
2. **IAP SSH is flaky for long sessions.** Connections sometimes fail to open, and one long session hung on the Mac after the VM had finished it. `bg.sh`/`wait.sh` (detached runs, short polls), retries and keepalives fixed it for the rest of the day.

## The clip and the sentence

- `eval/results/cloud/clip/cloud-clip.mp4` (40.5 s, 1920×1080, real time): the VM's terminal (instance, zone, machine type, hostname, `x86_64`, its own `adb devices`), and the cloud emulator running check-in, change seat and gate, each PASS with 0 model calls. Raw: `emulator.mp4`, `terminal.tsv`.
- Git ignores `*.mp4`, so **the videos are in `~/Desktop/Envoy/captures/cloud/`** (an ignored folder), not in the branch; `terminal.tsv` is tracked.
- Nothing personal in frame (the project ID is stripped; SkyLark's test passenger only).
- For the write-up (exactly true):
  > SkyLark routines compiled on a Mac ran unchanged on an Android emulator on a Google Cloud N2 server: once the new emulator had finished its first-boot setup, 48 of 48 runs on bookings they had never seen passed, with no model calls, at a median of 5.5 s (3.1 s on the Mac).

  > Envoy then learned the check-in in the cloud too: one agent run, compiled there into a routine that replayed 3 of 3 on new bookings with no model calls, for 7 cents.

## The trial's limits, as found

- Project `project-0dac894c-cef8-41b5-9cd` (under an organization; its policies allow nested virtualization and external IPs), billing on the trial account.
- **12 vCPUs across all regions**: one `n2-standard-8` fits, two don't. us-east1: 200 N2 vCPUs, 250 GB SSD, 8 addresses. **0 GPUs.**
- Turning on the Compute API created Google's `default` network with SSH and RDP open to the internet. Nothing is on it. Deleting those rules (or the network) is the user's call.

## Spend

- **Google:** the VM ran 41.5 min in all (stage 0: 16 min, stage 1: 20 min, stage 2: 5 min), about **$0.27** of compute and IP at $0.39/h, plus the 50 GB disk at about $5 a month (about $0.17 a day) while it exists. Total so far is about $0.28 of the $15 cap. Billing data lags a day, so these are list-price estimates.
- **Meta:** stage 1 **$0** (no key on the VM). Stage 2 **$0.070** (11 calls, standard tier), under its $1 cap. The VM's own guard was set to $1.

## The VM's state

- `envoy-cloud` is **stopped** (TERMINATED) since 20:04 UTC. Its 50 GB disk keeps the toolchain, the AVD (past its first boot) and the code at `c8204b4`, about $5 a month.
- **The Meta key was deleted.** `key.sh remove` searched the code folder, shell history and `/tmp` and found it nowhere.
- `envoy-idle-stop` powers the VM off after about 45 idle minutes if it's ever left running.
- **Deleting is the user's call:** `scripts/cloud/delete.sh --yes-delete-envoy-cloud` removes the VM, its disk, the firewall rule and the network. Keeping it stopped costs about $5 a month and saves about 3 minutes of setup if stage 3 happens.

## Not tried

- Stage 3: the API and the web app on the VM, the iPhone and Muse against a cloud copy, the live-view lag, real apps and their bot checks from a data-center address.
- Real phones (they stay on a Mac over USB). Snapshots on the cloud AVD (`--skip-snapshot`). More than one emulator per VM. Other regions or machine types (an `n2-standard-4` might do, at half the price).
- A GPU: the trial allows none.

## Recommendation on stage 3

**Worth doing as a copy after the Nov 1 cut, if the coordinator has room. Don't move the demo.** On the bars in the brief:

- **Routines pass at the Mac's rate:** yes, on a warmed AVD (48/48).
- **Agent runs within about 20% of the Mac's time:** one run at +13%; needs a few more.
- **The live-view lag on the iPhone:** untested. It's the real unknown. The VM grabs a raw frame in 32 ms, but frames would then cross IAP or the tailnet.
- **No new bot checks:** untested. Needs the user signed in to an app or two.
- **A rollback in minutes:** trivially yes, since the Mac setup is untouched.

So the demo stays on the Mac by default, and the cloud appears in the video as stage 1's clip and sentence.

If stage 3 runs, it found no code change needed so far. The likely items:
- a warm-up step for new AVDs (a script);
- the API's `ENVOY_API_DIR` and port on the VM (environment variables);
- Tailscale on the VM (the user approves it);
- possibly `META_CONTRIBUTOR_TIER` for SkyLark there.

The $60 stage 3 budget is about 150 VM-hours.

## Branch

- Stage 1: `95afc9b`.
- Stage 2: this commit.
- Backend suite: 493 passed. One earlier run stopped at a flaky `test_mcp_link.py::test_at_most_fifty_newest_last_and_a_cursor_pages_forward` (an `IntegrityError` in `api/store.py`). It passed 3/3 alone and in the full rerun; it's not touched by this branch.
- No web changes, so no web build is needed.

## Stage 3: the cloud copy (Oct 29 evening)

The user asked for the full move as **an alternative, not a replacement**: two complete setups, one picked before the Nov 3 recording. No product code changed. Full write-up: `docs/cloud.md`, "Stage 3".

### Built

- **The cloud copy on the VM:** the API, web app and MCP from main, envoy-test (SkyLark) and envoy-real (Play Store; the user's sign-ins).
- **Its own data:** `~/envoy-state` holds its `.env` with its own MCP token, its own session token and VAPID keys, and a copy of the demo memory and test inbox.
- **Started at boot** by systemd. Reached only over the tailnet at `https://envoy-cloud.tailffb391.ts.net:8443` (Tailscale Serve, approved by the user).
- **Scripts:**
  - `envoy-setup.sh`, `vm-envoy.sh`, `tailnet.sh`
  - `login.sh`, `keep-awake.sh`, `key.sh` (now line-based)
  - `shortcut.sh` (builds "Ask Envoy (cloud)")
  - `muse-tunnel.sh`, `muse-token.sh`
  - `fallback.sh` (a machine image to start in another zone)
  - `live_lag.py`, `voice_check.py`
- **The switch,** in `docs/cloud.md`: the one-time setup, how to choose the cloud, how to switch back.

### The bars

| Bar (the brief) | Result |
| --- | --- |
| Routines pass at the Mac's rate | **SkyLark: yes**, 48/48 with no model call (stage 1), and the interfaces suite's flows passed. **Real apps: nearly**: same-input reruns passed 5 of 6 compiled (Starbucks didn't read its output back); the Mac did 6 of 6 |
| Agent runs within about 20% of the Mac's time | **SkyLark: yes**: the stage 2 agent run took +13%, and the interfaces suite's phase4 +9% (but approval_modes +62%). **Real apps: not comparable**: a fresh phone's first-run screens made the agent take 2–17× the steps. Per step it was 1.1–1.6× the Mac |
| The live-view lag on the iPhone is acceptable | **No, by the target**: 290 ms frame lag p50 on the iPhone during the sitting (the Mac copy: 66–115 ms; target under 150 ms), and 147 ms from the Mac at idle. Usable for a sign-in; visibly laggy to watch |
| No new bot checks on the demo's apps | **Mostly**: no bot check at launch on 7 apps. **Amazon and Chipotle refused to create accounts** from the cloud phone; Amazon then signed in with a laptop-made account, **Chipotle silently would not sign in**. Starbucks's "browser outdated" was the image's old WebView (124): after updating it in the Play Store, sign-in and even sign-up worked. Google and DoorDash signed in |
| A tested rollback to the Mac in minutes | **Yes**: nothing on the Mac changes, so switching back is repointing the iPhone icon, the Siri shortcut's name and Muse's connector |

Also measured:
- **Muse to the cloud copy works**: an "Envoy Cloud" connector in Muse for Mac, through a tunnel from the VM. Muse answered "B12" from the cloud copy's memory; the MCP log shows 6 authenticated calls (`eval/results/cloud/stage3/muse-envoy-cloud.jpg`).
- **Voice** works: 3 of 3 heard exactly; the chat reply takes 4.4–4.6 s (Mac 2.6 s).
- **Pushes** work.
- **Screenshots and photos into memory don't:** they need Apple's Vision framework for OCR. That's a code change for later, not done.

### Found on the way (all handled from outside, no product code)

1. **The emulator crashed under real apps** with SwiftShader (DoorDash, then Amazon three times: a `RenderThread` segfault), and once more on `swangle` while apps played video. Both phones now start with `-gpu swangle -feature -HardwareDecoder`, only through systemd, and the API restarts with them (it kept stale per-launch gRPC tokens otherwise).
1. **A new cloud phone's browser is old** (WebView and Chrome 124, May 2024). Web-based sign-ins fail as "outdated browser" until both are updated in the Play Store.
2. **The sitting used the wrong phone.** My instructions said "envoy-real"; the web app says "Real-app phone". With the user's OK the two AVDs were swapped on the VM, so their sign-ins are on the Real-app phone now.
3. **A zone stockout** on the first restart (n2-standard-8 in us-east1-b). Start the VM well ahead on recording day and keep it awake. `fallback.sh` can start a copy in us-east1-c or d.
4. **The tailnet path goes through a Tailscale relay** (DERP, Miami), because Google blocks inbound UDP. Opening UDP 41641 would allow a direct path; it wasn't done.
5. **A brand-new emulator needs a warm-up** (stage 1). The new envoy-real got one before the sitting.
6. **A `pkill -f` pattern killed its own SSH session** (my mistake; now a PID-based kill). The safety check also blocked one key command that read a token line; the plain `key.sh` path was used instead.

### Spend (stage 3)

- **Meta: $0.615** of the $3 cap: the real-app set $0.37, the interfaces suite $0.10, diagnosing the crashes $0.11, voice and chat $0.03.
- **Google:** about $0.87 so far (about 2.2 VM-hours).
- **All stages so far:** Google about $1.14 plus the disk; Meta $0.685.

### Not done (yet)

- **The real-app retries:** a Starbucks sign-in retry (perhaps after updating the phone's web view in the Play Store), DoorDash with an address set, Chipotle, and Gmail (its answer key needs the Mac's Gmail API sign-in).
- **On the iPhone:** "Ask Envoy (cloud)" (`shortcut.sh`; the user adds it), and the cloud copy's Home Screen icon.
- **The machine image:** taken when the VM is stopped at the end, without the key.

### Recommendation

**Keep the demo on the Mac and hold the cloud copy as the fallback.** The cloud option works end to end for SkyLark and for read-only real apps. Against the Mac it is:
- slower: 2–4× on real-app screens, about 2× on SkyLark;
- laggier on the iPhone;
- unable to do the Instagram scene (the Pixel 5 is USB) or screenshots into memory.

Pick the cloud only if the Mac setup breaks. For that case:
- start the VM at least an hour ahead, then `keep-awake.sh on` and `key.sh put 3`;
- know that what the Mac copy learned (routines, memory, signed-in apps) isn't on the cloud copy.
