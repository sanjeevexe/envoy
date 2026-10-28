# Envoy

*Agents can search the web. Your phone knows your life.*

Envoy is a Muse-powered agent that operates Android apps on emulated phones, compiles successful runs into reusable **app routines**, and keeps a shared **memory graph** across web, voice, iPhone and MCP clients. Built solo for the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026, indie track).

- Design: [`docs/technical-design.md`](docs/technical-design.md) (live version: https://claude.ai/artifact/Sf51zMf4SMi5ZZmJabgPR5)
- Phase results: [`docs/phase-0-findings.md`](docs/phase-0-findings.md) · [`docs/phase-1-results.md`](docs/phase-1-results.md) (agent loop) · [`docs/phase-2-results.md`](docs/phase-2-results.md) (app routines) · [`docs/phase-3-results.md`](docs/phase-3-results.md) (memory graph) · [`docs/phase-4-results.md`](docs/phase-4-results.md) (web app, live view, approvals, MCP) · [`docs/phase-5-results.md`](docs/phase-5-results.md) (iPhone companion, voice, photos) · [`docs/phase-6-results.md`](docs/phase-6-results.md) (real Android phone, SAM 3.1) · [`docs/real-app-test-set.md`](docs/real-app-test-set.md)
- The final evaluation: [`eval/results/final/report.md`](eval/results/final/report.md) (how to run it: [Evaluate it](#evaluate-it))
- Open-source credits: [`THIRD_PARTY.md`](THIRD_PARTY.md) · License: MIT ([`LICENSE`](LICENSE))

## Layout

| Folder | What |
| --- | --- |
| `backend/` | Python 3.13 (`uv`): device layer, agent runtime, routines, memory, model adapter, the API (`api/`) and MCP server (`mcp_server/`) |
| `bridge-android/` | Optional Kotlin accessibility service |
| `relay/` | Node scrcpy video relay (real phones, Phase 6) |
| `web/` | Next.js web app (static export, served by the API) |
| `ios/` | Optional native iPhone companion |
| `testapps/` | Our own Android test apps (SkyLark Air) |
| `eval/` | Task sets, fixtures, runners, reports |
| `scripts/` | Measurement, setup and test scripts |

## Setup

```bash
source scripts/env.sh          # JAVA_HOME, ANDROID_HOME, PATH
cd backend && uv sync          # Python 3.13 environment
cp .env.example .env           # then fill in values
```

Emulators: `scripts/start_emulator.sh envoy-test` (headless, gRPC on port 8554).

## Run Envoy (web app, live view, approvals, MCP)

```bash
scripts/start_emulator.sh envoy-test                                  # the test phone
uv run --project backend python scripts/demo_setup.py                 # SkyLark signed out + demo memory (API stopped)
(cd web && npm install && npm run build)                              # once, and after web changes
uv run --project backend python -m api                                # http://127.0.0.1:8700, MCP at /mcp
open "http://127.0.0.1:8700/login?k=$(cat data/api/session_token)"    # sign in this browser once
```

Then ask in Chat: "Check me in for my flight". Envoy asks you to take over for SkyLark's sign-in (any email and password, test code 482913), then asks you to approve the check-in. `eval/run_phase4.py` runs the same path with a scripted person. How the API works: [`backend/api/README.md`](backend/api/README.md).

## Use it from your iPhone (Home Screen app, push approvals, voice, photos)

```bash
scripts/serve_tailnet.sh on                                           # https://<mac>.<tailnet>.ts.net:8443, tailnet only (restart the API after)
uv run --project backend python scripts/make_shortcut.py              # the "Send to Envoy" Share Sheet shortcut (signed; open it to add)
```

On the Mac, open the **Devices** tab: scan the QR code with the iPhone, add the page to the Home Screen (Share → Add to Home Screen), open Envoy from there and type the 6-digit pairing code, then turn on notifications. Approvals arrive as pushes; the Phone tab is the live phone with touch and the iPhone keyboard; tap the mic in Chat to dictate (Muse Voice Transcribe), check the words, then send; turn on Photos in Devices, then share a screenshot with **Send to Envoy** or pick one in Chat. `eval/run_phase5.py` checks push, photos, voice and the live view with scripts; `eval/run_photos.py` measures screenshot extraction. For Muse (route 2), `scripts/start_muse_test.sh` opens a public tunnel to `/mcp` only.

## Use your own Android phone

Plug the phone in by USB (or pair it for wireless debugging) and allow USB debugging on it. Envoy lists it beside the emulators (the phone picker in the app, Settings › Phones). Tasks stay on an emulator unless you say "… on my phone", set the app to run on your phone, or the app refuses emulators; Envoy then asks first ("Use your Android phone?", on the Mac and as a push on the iPhone). While it works there, a banner on the phone says so; touching the phone, pressing Pause on the banner, or another app coming to the front hands the phone to you, and Resume (on the phone or in the app) gives it back. The live view and takeover work on the phone through scrcpy; sign-in screens are black there, so you sign in on the phone itself.

```bash
(cd android/banner && ./gradlew :app:assembleDebug)                    # the banner app Envoy installs on your phone
uv run --project backend python eval/run_phase6.py portability --device phone --no-control   # SkyLark routines on the phone
uv run --project backend python eval/run_phase6.py stream --device phone                     # scrcpy frames and input
uv run --project backend python eval/run_phase6.py vision                                    # grounding vs SAM 3.1 on drawn targets
```

`ENVOY_TEST_PHONE=emulator-5558` makes an emulator stand in for a phone (development without one).

## App routines in one minute

```bash
uv run --project backend python scripts/run_task.py "Check me in for my flight to Denver" --skylark --approve-all   # the agent, once
uv run --project backend python scripts/compile_routine.py <task_id>                                               # its trace → a routine
eval/run_phase2.sh                                                                                                  # the Phase 2 evaluation
```

How routines work: [`backend/routines/README.md`](backend/routines/README.md). How memory works: [`backend/memory/README.md`](backend/memory/README.md) (`eval/run_memory.py`, `scripts/show_memory.py`; real mail: `scripts/connect_gmail.py` once, then `scripts/ingest_mail.py`). Example routines: [`eval/results/phase2/compiled/`](eval/results/phase2/compiled/); the library with versions and patch evidence: [`data/routines/`](data/routines/) and [`eval/results/phase2/library/`](eval/results/phase2/library/).

## Evaluate it

The final evaluation (the design doc's Evaluation section) is one command per suite and one for all of them. Every suite starts from a known state, scores with code (SkyLark's real state, or the right answer on screen), and writes `eval/results/final/<suite>.json` and `.md` with the commit it ran on, the tier and what it cost.

```bash
eval/run_final.sh                                                       # every suite, one emulator at a time (about 4.5 hours)
uv run --project backend python eval/run_final.py systems               # one suite: compile, systems, repeats, change, sizes, real,
                                                                        # memory, safety, injection, interfaces
uv run --project backend python eval/run_final.py report                # eval/results/final/report.md and charts/
```

`compile` must run first (it records and compiles the 10 core routines the SkyLark suites use). `real` needs `envoy-real` signed in to the test Google account; its answers that can only be graded by their shape (a price, a title) are also read by a person against the screen they came from (`eval/results/final/real_hand_checks.json`); `interfaces --restart-api` restarts the API on the current commit; `sizes --device phone` needs a phone connected. What each suite measures: [`eval/README.md`](eval/README.md).
