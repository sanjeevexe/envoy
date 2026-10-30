# Envoy in the cloud: the proof

Oct 29, 2026. **The same SkyLark routines, compiled on the Mac, ran unchanged on an Android emulator on a Google Cloud server: 48 of 48 with no model calls, at about half the Mac's speed.** That is on an emulator past its first boot; the very first run on a brand-new one passed 9 of 18 (below). Stage 2 then ran the whole learn-then-replay loop there: one agent run, a routine compiled from it on the VM, and that routine replayed 3 of 3 on bookings it had never seen, for $0.07 of Meta credit.

Today Envoy runs on the user's Mac: the API, the web app, the emulators and the Pixel 5's USB connection. Only the model calls go to Meta. The design always said "a cloud host later" (`docs/technical-design.md`, "Later, in the cloud"). This is the first step: the same code and the same routines on a Google Cloud server, measured against the numbers the Mac already recorded. Nothing was re-measured on the Mac.

Brief: `prompts/cloud-proof.md`. Results: `eval/results/cloud/`. Scripts: `scripts/cloud/`. Report: `prompts/cloud-proof-report.md`.

## What ran, and where

| | Mac (numbers already recorded) | Google Cloud |
| --- | --- | --- |
| Machine | Apple M5 Pro | `n2-standard-8`: 8 vCPU (Intel Xeon @ 2.80 GHz), 32 GB, `us-east1-b`, nested virtualization (KVM) |
| OS | macOS | Ubuntu 24.04.5 LTS, kernel 7.0.0-1014-gcp |
| Emulator | 37.2.12, GPU (Metal) | 37.2.12, **SwiftShader** (software rendering: the VM has no GPU) |
| `envoy-test` | Android 15 (API 35) Play Store image rev 9, **arm64** | the same image rev 9, **x86_64**, and the same hardware profile (1080×2400, 420 dpi, 4 GB, Pixel 6), copied from the Mac's `config.ini` |
| Code | the commits in each result file | `git archive` of main `c8204b4`; SkyLark's debug APK, sha256 `13f74ffc…a1a39c` (the Mac's build) |
| Toolchain | | JDK 21, cmdline-tools 23.0, platform-tools 37.0.1, uv 0.13.5, Python 3.13.17 (`eval/results/cloud/vm-versions.txt`) |

SkyLark is our own Kotlin app, so the CPU architecture doesn't change it. The routines are tracked files, so they came in the archive exactly as the Mac compiled them. The VM's code has no `.git`, so the cloud result files show an empty commit; it is `c8204b4`.

## The numbers beside the Mac's

From `python3 scripts/cloud/compare.py`. Success is SkyLark's own state check, as on the Mac. No Meta key was on the VM for these runs.

| Suite | Where | Passed | No model call | Model calls | Median s | Max s |
| --- | --- | --- | --- | --- | --- | --- |
| Phase 6 portability: 6 routine families × 3 unseen bookings | Mac | **18/18** | 18 | 0 | 3.6 | 6.6 |
| | Cloud | **18/18** | 18 | 0 | 6.2 | 12.0 |
| Phase 7 sizes: the 10 core routines × 3 unseen bookings | Mac | **30/30** | 30 | 0 | 2.8 | 6.3 |
| | Cloud | **30/30** | 30 | 0 | 5.4 | 12.0 |
| Both | Mac | **48/48** | 48 | 0 | 3.1 | |
| | Cloud | **48/48** | 48 | 0 | 5.5 | |

Every routine ran in rung 0 (as recorded) except `find_trip` on one booking in each suite, which needed rung 2 (a relaxed match, no model call). The Mac's sizes row for `envoy-test` was recorded on `e875c4a`; since then only `skylark_check_flight_status`'s compiled routine changed (7 lines).

**Per routine, the cloud takes about twice as long** (sizes, median seconds):

| Routine | Mac | Cloud | Ratio |
| --- | --- | --- | --- |
| check_in | 4.3 | 9.4 | 2.2× |
| change_seat | 4.3 | 8.9 | 2.1× |
| add_ktn | 3.3 | 7.1 | 2.2× |
| gate | 1.8 | 3.6 | 2.0× |
| seat | 1.7 | 3.6 | 2.1× |
| flight_status | 2.9 | 5.5 | 1.9× |
| miles | 0.7 | 1.1 | 1.6× |
| find_trip | 1.7 | 3.6 | 2.1× |
| past_trip | 4.8 | 7.7 | 1.6× |
| gate_alerts | 1.3 | 3.0 | 2.3× |
| **All 30 runs** | 82.8 s | 163.1 s | **2.0×** |

### The device, measured the same way (`scripts/measure_device.py --skip-snapshot`, 20 runs each)

| Measurement | Mac median (`docs/phase-0-findings.md`) | Cloud median | Cloud p90 |
| --- | --- | --- | --- |
| Cold boot (`scripts/start_emulator.sh`) | 19 s first, then 12–13 s | 33 s first, 32 s after a restart | |
| Tree read (uiautomator2 dump) | 31 ms | 85 ms | 115 ms |
| `observe()`: dump, foreground app, parse, compact | 68 ms | 141 ms | 147 ms |
| gRPC screenshot, raw RGB888 | 6 ms | 32 ms | 35 ms |
| gRPC screenshot, PNG encoded locally | 20 ms | 83 ms | 86 ms |
| gRPC screenshot, PNG from the emulator | 32 ms | 84 ms | 85 ms |
| `adb exec-out screencap -p` | 142 ms | 318 ms | 323 ms |
| Tap via uiautomator2 | 151 ms | 185 ms | 200 ms |
| Tap via emulator gRPC `sendTouch` | 0.6 ms | 0.9 ms | 1.0 ms |
| Tap → next screen settled | 1,520 ms | 1,821 ms | 1,994 ms |
| Type non-English text (set-text) | 120 ms | 677 ms | 726 ms |

Typing came back exact 20 of 20, and the clipboard stayed empty, as on the Mac. Raw: `eval/results/cloud/measure_device.json`.

**What software rendering costs.** Everything that draws or reads the screen is 2–5× slower: a tree read 2.7×, a raw screenshot 5×, typing 5.6×. A tap itself is nearly free either way. A routine step waits for the screen to settle and reads it several times, so a routine takes about twice as long. That is still well inside the design's 30-second target: the slowest routine run was 12.0 s.

### The first boot of a new emulator

The very first run, on a brand-new AVD about 13 minutes after its first boot, passed **9 of 18** (`eval/results/cloud/portability-cold.json`). All nine failures were the first nine runs, every one at the routine's first step ("open My Trips"): the step waited about 5 s for its target, then asked for a model repair, and with no key on the VM that ended the run (`ContributorNotAllowed`, 0 calls made). From the tenth run on, everything passed.

The cause was the image's first-boot work, not the routines. The emulator was using 134% CPU with nothing running (Play services, app updates, compiling apps), and had spent 34 CPU-minutes in its first 23 minutes. Once that settled it idled at 9%. Then:
- the measured run passed 18 of 18 (the table above);
- after a **restart** (a cold boot, but not a first boot), a run started right away passed 6 of 6 (`portability-restart.json`).

So a new cloud emulator needs a warm-up before it's used. A restarted one doesn't. On the Mac, `envoy-test` was long past its first boot when the recorded numbers were taken.

## Stage 2: the agent in the cloud

The whole learn-then-replay loop, on the VM: `eval/run_final.py compile --tasks check_in` (the Phase 7 compile suite, standard tier), then `eval/run_final.py sizes --device envoy-test --tasks check_in` to replay what it learned. The Meta key was on the VM only for these two commands. Results: `eval/results/cloud/stage2/`.

1. **The agent** checked in for the Denver flight ("Check me in for my flight to Denver."), and SkyLark's state check confirmed it.
2. **Muse Wonder compiled the run** into `skylark_check_in_flight` (9 steps, input `trip_city`; outputs seat, gate, boarding time and group). It was verified by replay on the same booking and on one it had never seen (Tampa), and became version 2 in the VM's own library.
3. **That routine replayed 3 of 3** on three more bookings it had never seen, with no model calls.

| | Mac (Phase 7 compile suite, standard tier) | Cloud |
| --- | --- | --- |
| Agent run on the Denver booking | 10 actions, 12 calls, 22.3 s, $0.023 | 8 actions, 10 calls, 25.3 s, $0.019 |
| Compile (Muse Wonder) | $0.049, 12.3 s | $0.051, 17.4 s |
| Verify: same booking, then a new one | 4.6 s and 4.0 s, both pass | 9.6 s and 9.4 s, both pass |
| Replays on unseen bookings | (the Mac-compiled routine: 4.3 s median, sizes) | **3 of 3**, 0 calls, 9.2–9.4 s |
| Meta spend | | **$0.070** (11 calls: 1 plan, 9 steps, 1 compile) |

The agent run took 3 s longer on the VM, with fewer steps. Its time is mostly model calls, which cost the same from either place, so software rendering matters less there than for a routine. Phase 1 recorded check-in at 6–9 actions and about 15 s. This is one run each, so it is no comparison of the agent's skill. It shows the loop works end to end in the cloud.

The learned routine lives only in the VM's copy (`eval/results/final/library/compiled/` there). The YAML is in `eval/results/cloud/stage2/check_in-routine.yaml` for reference; nothing was copied into the Mac's `data/routines/`.

## Stage 3: Envoy in the cloud, as a second option

At the user's request (Oct 29), the cloud copy is a full **alternative** to the Mac setup, not a replacement. Before the Nov 3 recording the user picks whichever works better. Nothing on the Mac changes when the cloud is chosen.

### What the cloud copy is

| | Mac (as today) | Cloud copy |
| --- | --- | --- |
| Where | this Mac | VM `envoy-cloud`, us-east1-b |
| API, web app, MCP | `127.0.0.1:8700`; tailnet `https://<mac>.<tailnet>.ts.net:8443` | the VM's `127.0.0.1:8700`; tailnet `https://envoy-cloud.<tailnet>.ts.net:8443` only |
| Code | the main checkout | `git archive` of main (`scripts/cloud/push.sh`), the web app built on the VM |
| Data | `data/api`, `data/demo/memory.db` | its own: `~/envoy-state` (`.env` with its own MCP token, the API's own session token and VAPID keys, a copy of the demo memory and test inbox taken Oct 29) |
| Phones | envoy-test, envoy-real (signed in), the Pixel 5 over USB | envoy-test, envoy-real (new: sign-ins are the user's step), **no Pixel 5** |
| Starts | when you start it | `scripts/cloud/start.sh --vm-only`: systemd starts both emulators and the API at boot |
| Costs | nothing extra | about $0.39 an hour while running; the disk about $5 a month |

The two copies don't share anything: a routine learned, a memory fact or a paired device on one is not on the other.

### The bars, measured

**The live view and takeover** (`scripts/cloud/live_lag.py`, envoy-test, 720 px at quality 60, the same WebSocket the web app and the iPhone use; screen changes made by the VM's own adb). Results: `eval/results/cloud/live-*.json`.

| | Mac copy (Phase 5, recorded) | Cloud copy, from the Mac over the tailnet | Cloud copy, from the Mac over IAP SSH |
| --- | --- | --- | --- |
| Frame: capture → received, p50 (max) | 24 ms (45) from the Mac; 66–115 ms on the iPhone | **147 ms** (294) | 130 ms (254) |
| Round trip | 0 ms on the Mac; 27–47 ms on the iPhone | 39 ms | 17 ms |
| The server's capture + JPEG encode per frame | | 64 + 28 ms | 66 + 30 ms |
| A takeover input → its ack, p50 (max) | 10–241 ms on the iPhone | 143 ms (298) | 129 ms (295) |
| A takeover input → the first new frame, p50 (max) | | **327 ms** (444) | 291 ms (391) |

Half the inputs were a 150 ms swipe, which the ack waits for. The tailnet path from the Mac goes through Tailscale's relay in Miami (`tailscale ping`: "via DERP(mia)", 36 ms), because Google's firewall blocks the inbound UDP a direct connection needs. Opening UDP 41641 would allow a direct path; it wasn't done, since it is a public port. Two-thirds of the frame lag is the VM drawing and grabbing the screen in software (about 92 ms a frame), not the network. The design's target was under 150 ms: the cloud copy is at the edge of it from the Mac; the iPhone adds its own network. The iPhone, from the user's sitting: 290 ms (below).

**Task times, end to end through the API** (the Phase 7 interfaces suite, `eval/run_final.py interfaces`, run on the VM against the cloud copy, standard tier, $0.143 at standard prices):

| Check | Mac (Oct 28, `e18e434`) | Cloud (Oct 29) |
| --- | --- | --- |
| phase4: sign-in hand-off and takeover, approval with a screenshot, check-in, memory, MCP, chat, live view | passed, 117 s | **passed, 127 s** |
| approval_modes: the four approval modes | passed, 50 s | **passed, 81 s** |
| phase5: pushes (a fake push service), a screenshot into memory, voice, live view over the tailnet | passed, 39 s | **pushes passed; the screenshot failed; voice and the tailnet view not run by the script** (below) |

- **Pushes work** (takeover, approval and Done, VAPID-signed and encrypted, no nonce), and the person's approval decides, not the push.
- **Screenshots and photos into memory don't work in the cloud copy.** They read text with Apple's Vision framework (`memory/photos.py` compiles `memory/ocr.swift`), which doesn't exist on Linux. The "Send to Envoy" shortcut is a Mac-only feature until it gets another OCR backend. That is a code change, not done here.
- **Voice works** (`scripts/cloud/voice_check.py`, 3 runs from the Mac over the tailnet; Phase 5's script makes its speech with macOS's `say`, so it was made on the Mac). "What's my gate for my Chicago flight?" was heard exactly 3/3 and answered from memory ("Gate B12"). Mac (one run) against cloud (3 runs): connect 919 ms against 638–858; release → text 89 against 198–247 ms; the chat reply 2.6 s against 4.4–4.6 s.
- **The model calls themselves** were mixed from the VM (p50 from the logs, small samples): chat 2.3 s (Mac 1.7 s), answer 1.6 s (1.8 s), match 4.1 s (1.6 s). Transcribe 149 ms.

The suite changed the cloud copy's SkyLark and memory; both were put back afterwards (a backup of the memory and the task database, then `demo_setup.py --app-only`).

**The iPhone** (the user's sitting, Oct 29 evening: the cloud copy paired as "Envoy Cloud", its live view used for 20–30 minutes while apps installed and signed in; the web app reports its own latency to `/api/metrics`): frame lag p50 **290 ms** (median of 26 sessions; 204–404), round trip 64 ms, a tap acknowledged in 74 ms. The Mac's browser in the same sitting: 230 ms (159–304). The Mac copy's iPhone record is 66–115 ms. Under that load (two emulators, Play Store installs), the cloud copy's live view is about 2.5–4× the Mac copy's and over the 150 ms target: usable for a sign-in, visibly laggy to watch.

**Real apps and sign-ins from a data-center address** (the user signed in on the cloud phone and typed every password; Oct 29):

| App | Result on the cloud phone (two sittings, Oct 29 evening) |
| --- | --- |
| Google (Play Store, Gmail; the phone's test account) | **Signed in**, no challenge |
| Amazon | **Creating an account was refused** ("detected suspicious activity"). An account made on the user's laptop **signed in** |
| Starbucks | First "your browser is outdated, try again". The image's WebView and Chrome were version 124 (May 2024) and had never been updated; after updating both to 156 in the Play Store, **sign-in worked, and so did creating an account on the emulator** |
| DoorDash | **Signed in** with Google; after the renderer fix (below) it worked |
| Chipotle | **Creating an account was refused**, as with Amazon. An account made on the laptop **would not sign in**, even with the browser updated: no error, the login page just stays. The likeliest cause is a silent block of the address or of emulators; not established |
| Target | Not tried: it shows a bot check to emulators on the Mac too |

So: two apps refused to create accounts from the cloud phone (Amazon, Chipotle), and one silently refused to sign in (Chipotle). Every other sign-in worked, once the phone's browser was current. **A new cloud phone needs Android System WebView and Chrome updated in the Play Store first**; until then, web-based sign-ins (Starbucks) fail as "outdated browser".

**The emulator crashed under real apps** with SwiftShader, the renderer stage 1 used. The Test phone died while DoorDash drew its screens (a segfault in the emulator's `RenderThread`, in the kernel log). The Real-app phone died about a minute into an Amazon run, three times. Turning off the emulator's host video decoder (`-feature -HardwareDecoder`) didn't help. **Switching to `-gpu swangle`** (ANGLE on SwiftShader) did: the same Amazon run then completed. Later the Test phone also died on plain SwiftShader, and once on `swangle` while apps played video ("h264 no frame" in its log). So both phones now start with `-gpu swangle -feature -HardwareDecoder` (`scripts/cloud/env-linux.sh`), only through systemd; that setup came through the browser updates and the user's last sitting. On `swangle`, SkyLark did 18/18 but slower (median 7.3 s against 6.2 s), and one run fell to the agent.

**A mix-up, and the fix.** The sitting's instructions said "envoy-real", but the web app calls the phones **Test phone** (envoy-test, shown first) and **Real-app phone** (envoy-real), so the sign-ins went onto the Test phone. With the user's OK, the two AVDs were swapped on the VM (both stopped cleanly, their folders renamed): the signed-in phone is now the Real-app phone, which always cold-boots and never loads a snapshot, and the fresh one is the Test phone, with SkyLark reinstalled and seeded. The Real-app phone kept its 10 GB data partition.

**Muse to the cloud copy works** (Oct 29, 23:20–23:30 UTC). The user started `scripts/cloud/muse-tunnel.sh` (a Cloudflare quick tunnel from the VM). Through it, `/mcp` without the token was refused (401) and the web app's pages weren't reachable at all (421). In Muse for Mac, "Add a custom connector called Envoy Cloud at <tunnel>/mcp" made the connector. The user pasted the cloud copy's MCP token (`scripts/cloud/muse-token.sh`) and allowed the tunnel's host. Muse listed the cloud copy's ten tools. Then "Using Envoy Cloud, what's my gate for my Chicago flight?" was answered "**B12** — SkyLark SL 482, ATL to ORD on Friday, Oct 30", with the cloud copy's own note that the gate was last seen in the app the evening before. The cloud copy's MCP log shows 6 calls from Meta's servers, all authenticated, 200/202, about 3 ms each on the VM. Screenshot: `eval/results/cloud/stage3/muse-envoy-cloud.jpg`. The Mac's own Envoy connector was left as it was.

**The real-app set on the cloud phone** (`eval/run_final.py real --only …`, read-only, every approval declined, standard tier, after the sign-ins and the swap, `swangle`; $0.37; `eval/results/cloud/stage3/real.json`). Mac: Phase 7's recorded rows (`eval/results/final/real.json`).

| Workflow | Agent, Mac | Agent, cloud | Routine, same input: Mac | cloud | New input: Mac | cloud |
| --- | --- | --- | --- | --- | --- | --- |
| amazon (search, first price) | done, 2 steps, 25.6 s | done, 9 steps, 183.1 s | pass, 21.2 s | pass, 66.1 s | fail | pass after a repair, 203.8 s, 0 calls |
| starbucks (a drink's calories) | done, 8 steps, 32.4 s | done, 14 steps, 90.9 s | pass, 21.4 s | **fail** (the output wasn't read) | pass | **fail** |
| doordash (the saved address) | done, 1 step, 12.5 s | **failed**: no address is saved on this account (skipped at sign-in) | pass, 9.6 s | – | | |
| doordash_search (first restaurant) | done, 2 steps, 18.4 s | done, 5 steps, 52.7 s | pass, 16.3 s | pass, 30.5 s | pass after a repair | pass after a repair, 128.2 s, 2 calls |
| settings_version | done, 4 steps, 15.3 s | done, 14 steps, 76.8 s | pass, 7.9 s | pass, 23.6 s | | |
| calendar_today | done, 0 steps, 4.4 s | done, 17 steps, 85.8 s | pass, 1.5 s | pass, 4.9 s | | |
| play_rating | done, 6 steps, 19.6 s | done, 3 steps, 18.1 s | pass, 5.0 s | pass, 21.7 s | fail | pass, 12.3 s |

- **No bot check** at any launch, and the agent got a right answer in 6 of 7 (the seventh had no saved address to find).
- **The agent took far more steps on the cloud phone** (Calendar 17 against 0, Settings 14 against 4): a fresh phone shows each app's first-run screens, which the Mac's `envoy-real` had cleared long ago. So these agent times are not a like-for-like comparison. Per step it was about 1.1–1.6× the Mac's. The one comparable pair (play_rating, 3 against 6 steps) took 18.1 s against 19.6 s.
- **Routines, same input, ran 2–4× the Mac's time** (23.6 against 7.9 s, 30.5 against 16.3 s, 66.1 against 21.2 s): real apps draw much more than SkyLark, and every screen is drawn in software.
- Gmail and Chipotle weren't run: Gmail's answer key needs the Mac's Gmail API sign-in, and Chipotle's first run sets a pickup store (73 s on the Mac).

### Choosing the cloud (and back): the switch

One-time setup (the user, once the VM is on the tailnet):
1. **Sign in on the Mac:** `scripts/cloud/login.sh` opens the cloud copy's sign-in link in the Mac's browser. Its token is never printed.
2. **The iPhone:** in that browser window, open Settings › Devices › "Pair your iPhone" › "Show a pairing code", as with the Mac copy. Then on the iPhone, Safari › `https://envoy-cloud.<tailnet>.ts.net:8443`, type the code, Share › Add to Home Screen, and name it **Envoy Cloud**. The Mac's **Envoy** icon stays as it is: one icon per host. Allow notifications from the new icon too.
3. **Siri:** `scripts/cloud/shortcut.sh` builds **Ask Envoy (cloud)**. Open it on the Mac; Shortcuts adds it, and iCloud brings it to the iPhone. It never replaces the Mac's **Ask Envoy**.
4. **Muse (optional):** `scripts/cloud/muse-tunnel.sh` prints a public `…/mcp` address. In Muse, add a second custom connector, **Envoy Cloud**, at that address. Paste its API key from `scripts/cloud/muse-token.sh`, which puts the cloud copy's MCP token on the clipboard.
5. **Real apps:** in the cloud copy's web app, open the live phone `envoy-real`, Take over, and sign in to Google Play and the apps the demo needs. You type every password. Hand back.

**To choose the cloud** (about 5 minutes; the Mac keeps running as it is):
1. `scripts/cloud/start.sh --vm-only` (if it reports a stockout, run it again; see below), then `scripts/cloud/keep-awake.sh on` and `scripts/cloud/key.sh put 3` (the Meta key, for the agent and chat; the VM's own cap is $3 a day).
2. Use the **Envoy Cloud** icon on the iPhone, and `scripts/cloud/login.sh` on the Mac.
3. Siri: in Shortcuts, rename **Ask Envoy** to **Ask Envoy (Mac)** and **Ask Envoy (cloud)** to **Ask Envoy**, so "Hey Siri, Ask Envoy" goes to the cloud.
4. Muse: run `scripts/cloud/muse-tunnel.sh` and use the **Envoy Cloud** connector, after updating its URL if the tunnel's address changed (quick tunnels get a new one each time). Turn the Mac's connector off for the session, so Muse doesn't pick the wrong one.

**To switch back to the Mac:**
1. Use the **Envoy** icon. Rename the shortcuts back. Use the Mac's Muse connector and tunnel (`scripts/start_muse_test.sh`), and turn the cloud one off.
2. `scripts/cloud/key.sh remove`, `scripts/cloud/keep-awake.sh off`, then `scripts/cloud/stop.sh`.

Nothing migrates either way, so switching back takes as long as the steps above. Anything done on the cloud copy (tasks, learned routines, memory) stays there.

**What only the Mac option can do:** the Pixel 5 (USB), and so the Instagram creator scene; the real apps already signed in on the Mac's `envoy-real`; the Mac's memory and routine history.

**A stopped VM may not start on demand.** On Oct 29 the first restart failed with Google's `ZONE_RESOURCE_POOL_EXHAUSTED` (no n2-standard-8 free in us-east1-b), and the retry 17 s later worked. For a recording, start the VM well ahead and keep it awake. Start it well ahead and keep it awake on recording day. If a stockout lasts, `scripts/cloud/fallback.sh start us-east1-c` (or `-d`) starts a copy of the VM from its machine image in another zone, with the same tailnet name, so nothing on the iPhone or in Muse changes; then `export ENVOY_GCP_ZONE=us-east1-c` for the other scripts. Never run the copy and the original at once (one Tailscale identity).

## Cost

Google's list prices for `us-east1` (on demand): `n2-standard-8` about **$0.39 an hour** (8 vCPU × $0.0316 + 32 GB × $0.0042), the ephemeral public IPv4 $0.005 an hour while running, the 50 GB balanced disk about **$5 a month** whether running or not. IAP SSH is free.

| | VM running | Compute + IP | Notes |
| --- | --- | --- | --- |
| Stage 0: create, toolchain, code, boot, device timings | 19:23–19:39 UTC, 16 min | $0.10 | 13 min of it was the emulator's first-boot work and a hung SSH session (below) |
| Stage 1: portability ×2, sizes, the restart check, the clip | 19:39–19:59, 20 min | $0.13 | |
| Stage 2: the key on, compile + verify, 3 replays, the key off | 19:59–20:04, 5 min | $0.04 | |
| Stage 3: the cloud copy, the bars, the user's sittings, the renderer crashes, the real-app set, Muse | 20:25–23:56, 3.5 h | about $1.39 | |
| **Total** | **about 4.2 h** | **about $1.66** | plus the disk, about $0.17 a day while it exists; the machine image, about $0.80 a month; a few MB of egress |

One emulator-hour on this VM costs about $0.39; with two phones and the API running, the cloud option costs about $0.39 an hour of use and $5 a month standing still. Meta: $0 for stage 1 (no key on the VM), **$0.070 for stage 2** (cap $1), **$0.615 for stage 3** (cap $3: the real-app set $0.37, the interfaces suite $0.10, diagnosing the crashes and `swangle` $0.11, voice and chat $0.03). **The VM is stopped (Oct 29, 23:56 UTC), with no key on it**, and `envoy-cloud-image` (15.9 GB, us-east1, no key) is there for `fallback.sh`. Standing still they cost about $5 + $0.80 a month. Deleting them is the user's call (`scripts/cloud/delete.sh`).

## The commands

From a clean Google Cloud project, on the Mac, after `gcloud auth login` and `gcloud config set project <id>`:

```bash
scripts/cloud/create.sh            # network + IAP-only firewall rule + VM (prints the project's CPU quotas first)
scripts/cloud/setup.sh             # JDK 21, Android SDK, emulator, the x86_64 image, uv + Python 3.13, the envoy-test AVD
scripts/cloud/push.sh              # git archive of main + SkyLark's APK, then uv sync
scripts/cloud/start.sh             # boot envoy-test on the VM (a new AVD: let it settle first, see above)
scripts/cloud/bg.sh portability uv run --project backend python eval/run_phase6.py portability --device envoy-test --no-control --k 3 --name cloud
scripts/cloud/wait.sh portability  # follows the log until it ends
scripts/cloud/fetch.sh eval/results/phase6/cloud.json eval/results/cloud/portability.json
scripts/cloud/stop.sh              # stop the emulator, then the VM (a stopped VM costs only its disk)
scripts/cloud/delete.sh --yes-delete-envoy-cloud   # the user's call
```

Also: `run.sh` (a short command on the VM), `key.sh put|remove` (the Meta key, stage 2 only), `vm-clip.sh` + `make_clip.py` (the clip), `compare.py` (the table above).

## How it is kept closed

- The VM sits on its own network, `envoy-cloud`, whose only ingress rule allows SSH from Google's IAP range (`35.235.240.0/20`). Every SSH and copy goes through `gcloud compute ssh --tunnel-through-iap`. It has an ephemeral public IPv4 for outbound downloads only; no rule lets anything reach it.
- No service account: nothing on the VM can call Google APIs.
- The emulator's gRPC, console and adb ports listen on `127.0.0.1` only (checked with `ss`), and gRPC needs its per-launch token, as on the Mac.
- The VM's adb server, emulator and code are its own. Nothing is forwarded to the Mac, whose adb server would list a forwarded port as the user's phone (`devices/phone.py`) or as an emulator slot.
- Code travels as `git archive` (tracked files only): no `.env`, `data/api`, logs or demo memory.
- The VM powers itself off after about 45 idle minutes (`envoy-idle-stop`: no SSH session and no Envoy run).
- The Meta key, for stage 2 only, went in through SSH stdin (`scripts/cloud/key.sh`), never on a command line, with Envoy's daily cap set to $1 on the VM. Afterwards it was deleted, and a search of the VM's code folder, shell history and `/tmp` found it nowhere.

## What's different on Linux

No product code changed. Everything was handled from outside:
- **The SDK path.** The repo's scripts and `devices/android.py` assume `~/Library/Android/sdk`. On the VM the SDK is in `~/android-sdk`, linked to that path, so `start_emulator.sh`, `stop_emulator.sh` and adb's lookup work unchanged.
- **`scripts/env.sh`** sets the Mac's paths; `scripts/cloud/env-linux.sh` is its Linux twin (JDK, SDK, `uv`, `XDG_RUNTIME_DIR`, `-gpu swiftshader_indirect`).
- **The gRPC token's discovery file** is in `$XDG_RUNTIME_DIR/avd/running` on Linux (`/run/user/1001/avd/running` here). `devices/emulator_grpc.py` already reads it there. The VM keeps `/run/user/<uid>` between SSH sessions (`loginctl enable-linger`), so the token outlives the session that started the emulator.
- **No GPU:** SwiftShader. See "What software rendering costs".
- **The Contributor tier** isn't enabled on the VM (no `.env`). It didn't matter for the measured runs, which made no model calls. It is why the first-boot failures ended at once instead of being repaired.
- **cmdline-tools 23.0's `sdkmanager`** now wraps a new "Android CLI" that downloads itself on first use and collects usage metrics unless `--no-metrics` is given. Worth knowing for a server.

### Things that went wrong on the way (and what the scripts now do)

- **IAP tunnels sometimes fail to open** ("Failed to lookup instance", "Connection is already closed"): `vm_ssh` and `vm_scp` retry on ssh's exit code 255.
- **A minutes-long command over one SSH session hung on the Mac** after the VM had finished it (the measurement run, about 8 minutes lost). Long runs now go through `bg.sh` (detached on the VM with `setsid`, output in `logs/cloud-<name>.log`) and `wait.sh` (short polls), and SSH sends keepalives.

## The trial's limits, as found

- One project, created on Oct 29 under an organization, with billing on the trial account. The organization's policies don't block nested virtualization (`compute.disableNestedVirtualization` not enforced) or external IPs.
- **CPUs: 12 across all regions** (`CPUS_ALL_REGIONS`), so one `n2-standard-8` fits, and not two. In us-east1: 200 N2 vCPUs, 250 GB SSD, 2,048 GB disk, 8 in-use addresses, 24 instances. **GPUs: 0.**
- Turning on the Compute Engine API also made Google's `default` network with its default rules (SSH and RDP open to the internet). Envoy's VM isn't on it; it was left as Google made it.

## The clip

`eval/results/cloud/clip/cloud-clip.mp4`: 40.5 s, 1920×1080, real time. The VM's terminal on the left (the instance's name, zone and machine type from the metadata server; `hostname`, `x86_64`, 8 vCPU; its own `adb devices`), and the cloud emulator on the right while three routines run: check-in, change seat and gate, each PASS with 0 model calls. Made by `scripts/cloud/vm-clip.sh` on the VM (one clock for the recording and the transcript) and `scripts/cloud/make_clip.py` on the Mac. Raw: `emulator.mp4` (re-encoded to 1.5 MB) and `terminal.tsv`. Git ignores `*.mp4`, so the two videos are not in the repo: copies are in `~/Desktop/Envoy/captures/cloud/` (an ignored folder), with `terminal.tsv` tracked here. Nothing personal is in frame: the project's ID is stripped, and SkyLark shows its test passenger only. The clip's run was not one of the measured runs (the recorder takes CPU).

## Limits, plainly

- Real phones still plug into a Mac (USB). Wireless debugging over the tailnet is an untested idea.
- Real apps and sign-ins weren't tried in the cloud.
- Data-center addresses may trigger apps' bot checks; that wasn't tested.
- One VM, one emulator, one region, one afternoon. The cloud runs were k=3 like the Mac's, and they're as small a sample.
- The API and web app didn't run on the VM (stage 3, not started).

## For the write-up

> SkyLark routines compiled on a Mac ran unchanged on an Android emulator on a Google Cloud N2 server: once the new emulator had finished its first-boot setup, 48 of 48 runs on bookings they had never seen passed, with no model calls, at a median of 5.5 s (3.1 s on the Mac).

And for stage 2:

> Envoy then learned the check-in in the cloud too: one agent run, compiled there into a routine that replayed 3 of 3 on new bookings with no model calls, for 7 cents.
