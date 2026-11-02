# Envoy

*Agents can search the web. Your phone knows your life.*

Envoy lets Meta's Muse models use Android apps the way you do: it reads the screen, taps and types, and asks you before
anything that can't be undone. When a task works once, Envoy compiles that run into a **routine**, a small program that
checks every screen and repairs itself when the app changes, so the next time takes seconds and few or no model calls.

**Why it fits "Push the Frontier".** Muse can act through the web and connectors, but much of what's current in a
person's life (bookings, orders, points) lives inside phone apps it can't reach. Envoy gives Muse that reach, as a custom
MCP connector in the Muse app, with approvals on your iPhone. And what Envoy learns on one run, it keeps.

- **Showcase site:** https://sanjeevexe.github.io/envoy/ (a guided tour built only from recorded runs and committed results)
- **Demo video (3 minutes):** TBD, the YouTube link goes here on Nov 4
- **The submission write-up:** [`docs/submission.md`](docs/submission.md)

Built solo for the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026, indie track). Open-source projects are
plumbing, credited in [`THIRD_PARTY.md`](THIRD_PARTY.md), which also says what Envoy builds itself.

## Results so far

Measured Oct 27–31 on development commits. The final evaluation runs on the `eval-final` tag on Nov 2, and its numbers
replace these (TBD). Every row names the file it comes from.

| What | Result | Source |
| --- | --- | --- |
| A real app, learned once | "How many calories are in a Grande Caffè Latte?" in the Starbucks app. The agent's first run: 45.6 s, 12 model calls, $0.0795. The routine compiled from it: 14.8 s, 2 calls, $0.005, the same answer (190 calories). | [`eval/results/real-apps/loop-a/runs.jsonl`](eval/results/real-apps/loop-a/runs.jsonl) (`task-1030-155711-51c2`, `task-1030-204136-b8d5`) |
| Asking again | SkyLark, our test airline app: the first request took a median 27.9 s and $0.051; requests 2–10 were 90/90 right at a median 1 model call, 5.9 s and $0.0023 (86% fewer calls) | [`eval/results/final/report.md`](eval/results/final/report.md), suite 2 |
| Against simpler approaches | SkyLark, 10 tasks on 4 layouts: Envoy's routines 40/40 on the first try (median 1 call, 5.5 s); the agent every time 40/40 (5 calls, 10.1 s); a fixed replay 14/40 | `report.md`, suite 1 |
| When the app changes | 50 injected UI changes: 50 recovered, then 50/50 ran with no model call. 50 new inputs: 50/50 with no model call | `report.md`, suite 3 |
| On a real phone | A Pixel 5 (Android 13): the 10 core routines on 3 new bookings each, 30/30 with no model call | [`eval/results/final/sizes.md`](eval/results/final/sizes.md) |
| Real apps | 18 read-only workflows on a test account: the first run right 14/18; the routine rerun right with no call 13/18; with a new input 4/11 (6/11 at the Oct 31 rehearsal); Target blocked by its bot check | `report.md`, suite 4; [`eval/results/real_rerun_2026-10-31/README.md`](eval/results/real_rerun_2026-10-31/README.md) |
| Safety | Irreversible steps caught 20/20 by code alone; 0 irreversible actions without approval over 7 declined live runs and 30 runs with planted instructions | `report.md`, suites 6 and 6b |
| AndroidWorld | 116 tasks, pass@1: Envoy as on `main` 21 (18%); with 13 general agent changes 57 (49%); on the held-out half 31 of 58 against 12; about $0.04 and 38 s a task | [`docs/androidworld-results.md`](docs/androidworld-results.md) |

What isn't there yet: new inputs on real apps work about half the time; apps that refuse emulators (Target, banking) need
a real Android phone; the emulators run on a Mac today, with a cloud copy as a second option ([`docs/cloud.md`](docs/cloud.md)).
A clip Muse for Mac hands over reaches the cloud copy too, through the Mac's outbox forwarder
([`docs/demo-creator-workflow.md`](docs/demo-creator-workflow.md)), but posting it to Instagram from a cloud phone isn't wired yet.

## Try it

- **Look first:** the [showcase site](https://sanjeevexe.github.io/envoy/), or open `site/index.html` from a checkout.
- **Run it on SkyLark,** our own test app, with no personal accounts. You need a Mac (built on Apple silicon, macOS 26),
  the Android SDK and emulator, Python 3.13 with `uv`, Node for the web app, and a Meta Model API key. Follow
  [Setup](#setup), then [Run Envoy](#run-envoy-web-app-live-view-approvals-mcp).
- **Real apps:** sign in to each app once on the `envoy-real` emulator. Every real-app result here used a test Google
  account.
- **Measure it:** [Evaluate it](#evaluate-it) runs the same suites as the table above.

## More

- Design: [`docs/technical-design.md`](docs/technical-design.md)
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
cp .env.example .env           # then fill in values (META_API_KEY at least)
```

Emulators: `scripts/start_emulator.sh envoy-test` (headless, gRPC on port 8554). To create them the first time, as
`scripts/cloud/vm-setup.sh` does on Linux (use `x86_64` there):

```bash
sdkmanager --install "platform-tools" "emulator" "system-images;android-35;google_apis_playstore;arm64-v8a"
avdmanager create avd -n envoy-test -k "system-images;android-35;google_apis_playstore;arm64-v8a" -d pixel_6
(cd testapps/skylark && ./gradlew :app:assembleDebug)                              # SkyLark, our test app
adb -s emulator-5554 install -r testapps/skylark/app/build/outputs/apk/debug/app-debug.apk   # once envoy-test is up
```

`envoy-real` is made the same way, for real apps (give it a 16 GB data partition; `docs/phase-0-findings.md` has the
settings).

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

## Which phone Envoy uses

iPhone users use Envoy's emulators; Android users use an emulator or their own phone. You sign in to each app once on the emulator. Apps that refuse emulators (Target's bot check, banking apps) need a real Android phone, so they are out of reach with only an iPhone. The emulators run on a Mac today (a cloud host later).

## Use your own Android phone

Tested on a Google Pixel 5 (Android 13) over USB: the Phase 6 gate passed there (`docs/phase-6-results.md`). Plug the phone in by USB (or pair it for wireless debugging) and allow USB debugging on it. Envoy lists it beside the emulators (the phone picker in the app, Settings › Phones). Tasks stay on an emulator unless you say "… on my phone", set the app to run on your phone, or the app refuses emulators; Envoy then asks first ("Use your Android phone?", on the Mac and as a push on the iPhone). While it works there, a banner on the phone says so; touching the phone, pressing Pause on the banner, or another app coming to the front hands the phone to you, and Resume (on the phone or in the app) gives it back. The live view and takeover work on the phone through scrcpy; sign-in screens are black there, so you sign in on the phone itself.

```bash
(cd android/banner && ./gradlew :app:assembleDebug)                    # the banner app Envoy installs on your phone (again when this build is newer)
uv run --project backend python eval/run_phase6.py portability --device phone --no-control   # SkyLark routines on the phone
uv run --project backend python eval/run_phase6.py stream --device phone                     # scrcpy frames and input
uv run --project backend python eval/phone_check.py device                                   # reading, settling and set-text on the phone
uv run --project backend python eval/phone_gate.py prepare                                   # the gate: SkyLark set up on the phone; then ask from the iPhone
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
