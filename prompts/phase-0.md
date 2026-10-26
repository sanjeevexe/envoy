# Phase 0 — Foundations (everything except the Meta API test)

You are setting up and de-risking **Envoy**, my solo project for the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026, indie track, theme "Push the Frontier"). Envoy is a Muse-powered agent that operates Android apps on emulated phones, compiles successful runs into reusable "app routines," and keeps a shared memory graph across web, voice, iPhone and MCP clients.

The project folder is `~/Desktop/Envoy`. The full design is in `docs/technical-design.md` (diagrams in `docs/diagrams/`). **Read it before doing anything**, especially these sections: Device layer, Agent runtime, Interfaces and integrations (including "Path into Muse"), Live view and sign-in, Models and cost, Tech stack and repository, Build phases, Open questions. The live version of the doc is at https://claude.ai/artifact/Sf51zMf4SMi5ZZmJabgPR5. If the two disagree, the live version wins; tell me about any disagreement.

## Your job

Finish Phase 0 **except the Meta Model API test**. I don't have API credits yet. Do not call the Meta Model API at all, not even a single test request. Instead, prepare everything so that the API test can be run in a few minutes once credits arrive. We will run that test together afterward.

Phase 0 exists to replace guesses with measurements before Phase 1 starts. Record every number you measure.

## How to run this: unattended work first, hands-on steps last

I may be away from my desk for a while. So the work is split in two parts:

- **Part A (unattended):** everything you can do without me. Do all of it first, start to finish, without stopping to ask me anything.
  - If you hit a decision I would normally make, pick the sensible default, write it down under "Decisions made without you" in the findings, and keep going.
  - If you hit a question only I can answer, add it to the Part B checklist and keep going.
- **Part B (hands-on):** steps that need me (sign-ins, the Muse app, choosing apps, pasting rules). Start them only after Part A is completely done.
  - Before you begin, send me **one** message with the full Part B checklist, so I can do it all in one sitting.
  - If you have a way to notify me (a push notification tool, for example), use it at that moment.
  - Then wait for me.

## Permissions

I give you full permission to do whatever Phase 0 needs on this Mac. That includes:
- installing tools with Homebrew or official downloads (Android SDK, emulator, JDK, scrcpy, cloudflared, uv, and so on)
- editing my shell config (`~/.zshrc`) for environment variables
- creating emulators and snapshots
- running local servers and public tunnels
- creating files, initializing git and committing in `~/Desktop/Envoy`

These rules still apply:
- **Never type passwords or sign in to any account yourself.** Sign-ins are Part B steps that I do.
- **Never submit forms or applications on my behalf.** Draft the text; I will submit it.
- **Never commit secrets.** Keys go in `.env`, which is gitignored; commit only `.env.example`.
- **Don't touch my other Desktop projects** (for example `Meta Hackathon`, `grasp`, `CourtPulse`). They are unrelated.
- **Install only from official sources:** Homebrew, Google, PyPI, npm, GitHub releases of the named projects.

## Known facts about this Mac (verify; don't assume)

- MacBook Pro 14", Apple M5 Pro (15 cores), 24 GB RAM, macOS 26.6.2, about 645 GB free.
- Already installed: Homebrew, Python 3.14 (too new for some Android tools, so use Python 3.13 through `uv`), Node 26, npm, ffmpeg, Xcode.
- Java is Temurin 21, but it is the **x86_64 build running under Rosetta**. Install an arm64 JDK 21 and point `JAVA_HOME` at it.
- Not installed: Android SDK, emulator, adb, scrcpy, Android Studio. `ANDROID_HOME` is unset.

---

## Part A — Unattended work

Do these in order. Commit to git after each one.

### A1. Repository setup

- `git init` in `~/Desktop/Envoy` on branch `main`.
- Create the layout from the design doc: `backend/`, `bridge-android/`, `relay/`, `web/`, `ios/`, `testapps/`, `eval/`, `docs/`, `scripts/`. Leave empty folders as placeholders with a one-line README each.
- `backend/`: a `uv` project on Python 3.13 with FastAPI, Pydantic, `adbutils`, `uiautomator2`, `openai` (used later against Meta's OpenAI-compatible API), and `grpcio` plus `grpcio-tools` (for emulator screenshots).
- Add `.gitignore` (including `.env`, emulator artifacts and large screenshots), `.env.example` (with `META_API_KEY=` and other expected settings), and a short top-level `README.md`.
- Add `THIRD_PARTY.md` listing every open-source component we use or plan to use, with its license and what we use it for: uiautomator2, adbutils, scrcpy, the Tango `@yume-chan/*` libraries, the MCP SDK, and so on. The hackathon rules let us build on open source as long as we credit it, so keep this list current.

### A2. Android toolchain

- Install an arm64 JDK 21, the Android command-line tools, `platform-tools` (adb), the emulator, and the **arm64 Google Play system image for API 35** (`system-images;android-35;google_apis_playstore;arm64-v8a`). Do not use a `ps16k` image. If API 35 has problems, try API 36 and record why.
- Set `ANDROID_HOME`, `JAVA_HOME` and `PATH` in `~/.zshrc`.
- Install `scrcpy` and `cloudflared` with Homebrew.
- Create two AVDs on a Pixel 6 profile with 4 GB RAM:
  - **`envoy-test`**: for test apps and evaluation. We restore its snapshots freely.
  - **`envoy-real`**: for real apps. It is long-lived and never restored to an old snapshot, because restoring old signed-in sessions can get accounts flagged.
- Confirm each AVD boots headless (`-no-window -no-audio -no-boot-anim -memory 4096 -grpc <port>`) and appears in `adb devices`. Also confirm both can run at the same time, and record RAM and CPU usage with one and with two running.

### A3. Device control spike (`backend/devices/`)

This is the seed of Phase 1's device layer. Keep it small and clean, and use `envoy-test` only.
- Implement the `Device` protocol from the design doc's Device layer section and an `EmulatorDevice` backed by uiautomator2 and adbutils. It needs: `observe()`, `act()` (tap, long press, type, scroll, back, home, launch), `wait_until_settled()`, `snapshot_save()` / `snapshot_load()` (which must re-establish adb forwarding and the uiautomator2 server afterward), and `screenshot()`.
- Screenshots on emulators come from the **emulator's gRPC `getScreenshot`**. Generate Python stubs from the `emulator_controller.proto` that ships with the emulator. Check the emulator docs for whether the gRPC port needs a token. Fall back to `adb exec-out screencap -p`.
- Implement the **compact screen format** from the Agent runtime section of the doc (numbered interactive elements with text, resource ID and type), plus the screen signature definition from the App routines section.
- Add `scripts/measure_device.py`, which reports median and p90 over at least 20 runs for:
  - a tree read
  - a gRPC screenshot
  - an `adb screencap`
  - a tap
  - typing text that includes non-English characters
  - a snapshot restore
- Test it against built-in apps (Settings, Contacts, Chrome) and save a compact screen dump from each into the findings.

### A4. Secure-screen check (no sign-in needed)

Chrome's incognito tabs are marked secure (`FLAG_SECURE`), the same way many sign-in and payment screens are. Use them to test, without any account, whether a secure screen is **black** in:
- scrcpy video
- the gRPC screenshot
- `adb screencap`

Also check whether the accessibility tree is still readable on that screen. Part B repeats this on real apps' sign-in screens.

### A5. Muse connector stub (built and tested locally; the Muse test itself is in Part B)

This answers route 2 in the design doc's "Path into Muse" section.
- Build a stub **MCP server** in `backend/mcp_stub/` using the official MCP Python SDK. Check the current version and the 2026-07-28 spec, and use Streamable HTTP. It needs:
  - **bearer-token auth**, with the token stored in `.env`
  - two tools:
    - `memory_search(query)` returns a fake trip: SkyLark flight SL 482, ATL to ORD, Oct 30, gate B12, seat 14C, confirmation KX7Q2M.
    - `run_task(goal)` only logs the request and returns a fake task ID with a fake approval link.
  - a log of every request (method, tool, arguments, headers without the token) to `logs/mcp_stub.jsonl`.
- Build the fallback too: the same two tools as a plain REST API with an OpenAPI description.
- Test both locally with a script or the MCP Python client: calls with the right token work, and calls with no token or a wrong token are rejected.
- Write `scripts/start_muse_test.sh`, which starts the server and a Cloudflare quick tunnel (`cloudflared tunnel --url ...`, no account needed) and prints the public URL and token. Confirm the tunnel works once by calling the public URL yourself, then shut it down. Part B restarts it for the real test.

### A6. Connector application draft (I submit)

Draft a short submission for the **Muse Connector Platform** and a request to join the **Meta AI Connectors** developer preview waitlist. Describe Envoy and its MCP tools; the "approve" capability is deliberately not exposed to AI clients. Save the drafts in `docs/connector-application.md`.

### A7. Prepare the Meta API test (do NOT run it)

- **Check the real API shapes first.** Read Meta's current docs at https://dev.meta.ai/docs/ for: the Responses API, structured output (`json_schema`), reasoning effort, image input, perception grounding (points and boxes on a 0–1000 grid), prompt caching (`prompt_cache_key`), SAM 3.1, models, pricing, and Muse Voice Transcribe. The numbers in the design doc came from research summaries and may be slightly off.
- `backend/models/adapter.py`: one module that every model call will go through. It holds:
  - a per-job config (model, reasoning effort, schema)
  - a cost meter that writes tokens and dollars per call to `logs/model_costs.jsonl`, using prices from Meta's pricing page
  - timeouts and retries
  - a flag for the Contributor tier, which is allowed **only** for our own test apps
- `backend/models/schemas.py`: the action JSON schema from the Agent runtime section of the doc.
- **Capture fixtures now** in `eval/fixtures/phase0/`: 3 to 5 emulator screens from built-in apps, each with the raw tree JSON, the compact text format and a PNG screenshot. Include one tall screen with a known target element and its bounding box, to check grounding accuracy.
- `scripts/meta_api_check.py` runs the checks below. It must exit immediately if `META_API_KEY` is missing, and it supports `--dry-run`, which prints the requests without sending them.
  1. Muse Spark 1.3 reads a fixture screen and returns a valid action JSON. Then **execute that action on the emulator**: this is the Phase 0 gate.
  2. Latency over 10 runs at `minimal` and at `low` reasoning effort.
  3. Output tokens per step, including reasoning tokens.
  4. Grounding accuracy on the tall screenshot.
  5. Whether prompt caching works: compare cached-token counts on repeated calls.
  6. One SAM 3.1 call on a screenshot with the prompt "button".
  7. Whether `muse-wonder-1.0` is accessible with my credits.

  It also estimates the total cost of the whole check before running it, which should be under $2.
- `docs/meta-api-test-plan.md`: how to run the check, the expected output, and where each result goes in the findings.
- Confirm `scripts/meta_api_check.py --dry-run` runs cleanly.

### A8. Findings draft

Write `docs/phase-0-findings.md` with:
- Every measurement from A2 through A4: tables with medians and p90s, plus RAM use for one and for two emulators.
- The secure-screen results from A4.
- "Decisions made without you": every default you picked during Part A, and why.
- Answers to each item in the design doc's Open questions that Part A settles. Mark the rest as still open.
- Anything in the design doc that the measurements contradict, with a proposed change. Don't edit `technical-design.md` yourself; list the changes and I'll decide.
- "Ready for the Meta API test": a checklist confirming that everything in A7 is in place.
- Placeholder sections for the Part B results.

Commit, then move to Part B.

---

## Part B — Hands-on steps (with me)

When Part A is done, send me **one message** containing:
- a 5-line summary of Part A
- the checklist below, with exact instructions for each item and roughly how long each will take

Then wait. We'll go through the items together, in this order.

### B1. Real-app compatibility and secure screens

1. You launch `envoy-real` **with a window**. I sign in to the Play Store with a **dedicated test Google account** (not my personal one).
2. I choose 3 to 5 shopping or food apps to test. Suggestions to offer me: Target, Starbucks, DoorDash, Uber Eats, Amazon, Chipotle.
3. You install them. You may drive the Play Store install buttons; I handle any sign-in.

For each app, record:
- whether it installs and launches
- whether it blocks the emulator ("device not supported", integrity errors, crashes)
- how far it gets before a sign-in is needed
- whether its sign-in or payment screens are **black** in scrcpy video, the gRPC screenshot, and the emulator's own window
- whether the accessibility tree is still readable on those screens, and whether a password field is flagged

If I choose to sign in to an app, I do it in the emulator window. Afterward, record whether the session survives an emulator restart. Do not snapshot-restore `envoy-real`.

### B2. Muse connector test

1. Run `scripts/start_muse_test.sh`.
2. Give me step-by-step instructions for the Muse app: the exact URL and token, and what to say to Muse (ask it to add a custom connector, then ask "what's my gate?" and "check me in for my flight").
3. While I test, watch `logs/mcp_stub.jsonl`. Record whether Muse connects, which tools it calls, with what arguments, and how it presents the approval link.
4. If MCP fails, switch to the REST fallback and repeat.
5. Shut the tunnel down when we're done, and rotate the token.

### B3. Official rules and connector application

- I paste the parts of the official rules about open-source use and submission requirements. Summarize what they mean for us, and check `THIRD_PARTY.md` against them.
- I review and submit the connector application drafts from A6.

### B4. Finish the findings

Fill in the Part B sections of `docs/phase-0-findings.md`:
- the real-app compatibility table
- the secure-screen results for real apps
- the Muse connector results, and the resulting decision on which "Path into Muse" route to pursue
- the rules summary

Then commit.

## Done means

- Parts A and B are complete and committed.
- The **only** thing left for Phase 0 is running `scripts/meta_api_check.py` once I have credits. That test is the Phase 0 gate: a Meta model reads a real emulator screen and returns a valid action that runs on the phone.

When you finish, give me a short summary with:
1. What was done.
2. The key numbers.
3. Anything that changes the design.
4. Exactly what I need to do next, including adding the API key once credits arrive so we can run the API test together.
