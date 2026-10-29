# Envoy in the cloud: the proof

Oct 29, 2026. **Draft: the runs are in progress; every TBD is filled from the VM's results before this merges.**

Today Envoy runs on the user's Mac: the API, the web app, the emulators and the Pixel 5's USB connection. Only the model calls go to Meta. The design always said "a cloud host later" (`docs/technical-design.md`, "Later, in the cloud"). This is the first step: the same code and the same routines on a Google Cloud server, measured against the Mac's recorded numbers.

Brief: `prompts/cloud-proof.md`. Results: `eval/results/cloud/`. Scripts: `scripts/cloud/`.

## What ran, and where

| | Mac (the numbers already recorded) | Google Cloud |
| --- | --- | --- |
| Machine | Apple M5 Pro | `n2-standard-8` (8 vCPU, 32 GB), `us-east1-b`, nested virtualization (KVM) |
| OS | macOS | Ubuntu 24.04.5 LTS |
| Emulator | 37.2.12, Metal | TBD, SwiftShader (software rendering: the VM has no GPU) |
| `envoy-test` | Android 15 (API 35) Play Store image, **arm64** | the same image, **x86_64**; the same hardware profile (1080×2400, 420 dpi, 4 GB, Pixel 6) |
| Code | the commits named in each result | `git archive` of main TBD; SkyLark's debug APK, sha256 TBD |

SkyLark is our own Kotlin app, so the CPU architecture doesn't change it. The routines were compiled on the Mac and copied unchanged (they are tracked files in the archive).

## The numbers beside the Mac's

TBD (`python3 scripts/cloud/compare.py`).

## Cost

TBD: VM hours × $0.39, disk, and what each stage spent of Google's credit and Meta's.

## The commands

From a clean Google Cloud project, on the Mac, after `gcloud auth login` and `gcloud config set project <id>`:

```bash
scripts/cloud/create.sh            # network + IAP-only firewall rule + VM (prints the project's CPU quotas first)
scripts/cloud/setup.sh             # JDK 21, Android SDK, emulator, the x86_64 image, uv + Python 3.13, the envoy-test AVD
scripts/cloud/push.sh              # git archive of main + SkyLark's APK, then uv sync
scripts/cloud/start.sh             # boot envoy-test on the VM
scripts/cloud/run.sh uv run --project backend python eval/run_phase6.py portability --device envoy-test --no-control --k 3 --name cloud
scripts/cloud/fetch.sh eval/results/phase6/cloud.json eval/results/cloud/portability.json
scripts/cloud/stop.sh              # stop the emulator, then the VM (a stopped VM costs only its disk)
scripts/cloud/delete.sh --yes-delete-envoy-cloud   # the user's call
```

## How it is kept closed

- The VM sits on its own network, `envoy-cloud`, whose only ingress rule allows SSH from Google's IAP range (`35.235.240.0/20`). Every SSH and copy goes through `gcloud compute ssh --tunnel-through-iap`. It has an ephemeral public IPv4 for downloads only; no rule lets anything reach it.
- No service account: nothing on the VM can call Google APIs.
- The emulator's gRPC listens on `127.0.0.1` with its per-launch token, as on the Mac. The VM's adb server, emulator and code are its own; nothing is forwarded to the Mac, whose adb server would list a forwarded port as a phone (`devices/phone.py`) or an emulator slot.
- Code travels as `git archive` (tracked files only): no `.env`, `data/api`, logs or demo memory.
- The VM powers itself off after about 45 idle minutes (`envoy-idle-stop`: no SSH session and no Envoy run).
- The Meta key, for stage 2 only, goes in through SSH stdin (`scripts/cloud/key.sh`), with a $1 daily cap on the VM, and is removed and checked for afterwards.

## What's different on Linux

- **The SDK path.** The repo's scripts and `devices/android.py` assume `~/Library/Android/sdk`. On the VM the SDK is in `~/android-sdk`, linked there, so nothing changes.
- **`scripts/env.sh`** sets the Mac's paths; `scripts/cloud/env-linux.sh` is its Linux twin (JDK, SDK, `uv`, `XDG_RUNTIME_DIR`, `-gpu swiftshader_indirect`).
- **The gRPC token's discovery file** is in `$XDG_RUNTIME_DIR/avd/running` on Linux (the Mac: `~/Library/Caches/TemporaryItems/avd/running`). `devices/emulator_grpc.py` already reads both. The VM keeps `/run/user/<uid>` alive between SSH sessions (`loginctl enable-linger`), so the token survives the session that started the emulator.
- **No GPU:** the emulator renders with SwiftShader. TBD what that costs.

## The trial's limits, as found

- One project, billing on the trial account. Under an organization, but its policies don't block nested virtualization or external IPs.
- **CPUs: 12 across all regions** (`CPUS_ALL_REGIONS`), so one `n2-standard-8` fits, and not two. us-east1: 200 N2 vCPUs, 250 GB SSD, 8 in-use addresses, 24 instances. **GPUs: 0.**
- Turning on the Compute Engine API also made Google's `default` network with its default rules (SSH and RDP open to the internet). Envoy's VM isn't on it; it was left as Google made it.

## Limits, plainly

- Real phones still plug into a Mac (USB). Wireless debugging over the tailnet is an untested idea.
- Real apps and sign-ins weren't tried in the cloud.
- Data-center addresses may trigger apps' bot checks; that wasn't tested.
- One VM, one emulator, one region, one day.

## For the write-up

TBD: one sentence that is exactly true.
