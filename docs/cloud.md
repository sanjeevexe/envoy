# Envoy in the cloud: the proof

Oct 29, 2026. **The same SkyLark routines, compiled on the Mac, ran unchanged on an Android emulator on a Google Cloud server: 48 of 48 with no model calls, at about half the Mac's speed.** That is on an emulator past its first boot; the very first run on a brand-new one passed 9 of 18 (below).

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

TBD (next commit).

## Cost

Google's list prices for `us-east1` (on demand): `n2-standard-8` about **$0.39 an hour** (8 vCPU × $0.0316 + 32 GB × $0.0042), the ephemeral public IPv4 $0.005 an hour while running, the 50 GB balanced disk about **$5 a month** whether running or not. IAP SSH is free.

| | VM running | Compute + IP | Notes |
| --- | --- | --- | --- |
| Stage 0: create, toolchain, code, boot, device timings | 19:23–19:39 UTC, 16 min | $0.10 | 13 min of it was the emulator's first-boot work and a hung SSH session (below) |
| Stage 1: portability ×2, sizes, the restart check, the clip | 19:39–19:59, 20 min | $0.13 | |
| Stage 2 | 19:59–20:04, 5 min | $0.04 | |
| **Total so far** | **41.5 min** | **$0.27** | plus the disk, about $0.17 a day while it exists, and a few MB of egress |

One emulator-hour on this VM costs about $0.39. Meta: $0 for stage 1 (no key on the VM). The VM is **stopped**; deleting it is the user's call (`scripts/cloud/delete.sh`).

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

`eval/results/cloud/clip/cloud-clip.mp4`: 40.5 s, 1920×1080, real time. The VM's terminal on the left (the instance's name, zone and machine type from the metadata server; `hostname`, `x86_64`, 8 vCPU; its own `adb devices`), and the cloud emulator on the right while three routines run: check-in, change seat and gate, each PASS with 0 model calls. Made by `scripts/cloud/vm-clip.sh` on the VM (one clock for the recording and the transcript) and `scripts/cloud/make_clip.py` on the Mac. Raw: `emulator.mp4` (re-encoded to 1.5 MB) and `terminal.tsv`. Nothing personal is in frame: the project's ID is stripped, and SkyLark shows its test passenger only. The clip's run was not one of the measured runs (the recorder takes CPU).

## Limits, plainly

- Real phones still plug into a Mac (USB). Wireless debugging over the tailnet is an untested idea.
- Real apps and sign-ins weren't tried in the cloud.
- Data-center addresses may trigger apps' bot checks; that wasn't tested.
- One VM, one emulator, one region, one afternoon. The cloud runs were k=3 like the Mac's, and they're as small a sample.
- The API and web app didn't run on the VM (stage 3, not started).

## For the write-up

> SkyLark routines compiled on a Mac ran unchanged on an Android emulator on a Google Cloud N2 server: once the new emulator had finished its first-boot setup, 48 of 48 runs on bookings they had never seen passed, with no model calls, at a median of 5.5 s (3.1 s on the Mac).
