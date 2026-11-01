# Third-party components

Envoy builds on the open-source projects below. The hackathon rules allow open source as long as it is credited, so this list is kept current: add a row when a dependency is added, and move a row from "Planned" to "In use" when it lands.

Licenses for Python packages were read from the installed package metadata (Oct 26, 2026). Licenses for planned components come from their repositories and must be re-checked when they are added.

## In use (Phases 0–7)

| Component | Version | License | What we use it for |
| --- | --- | --- | --- |
| [uiautomator2](https://github.com/openatx/uiautomator2) (and its on-device `android-uiautomator-server`) | 3.7.1 | MIT | Reads the accessibility tree, taps, types any language through its input method |
| [adbutils](https://github.com/openatx/adbutils) | 2.12.0 | MIT | Python adb client: shell, port forwarding, `screencap` |
| [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) (`mcp`) | 2.3.0 | MIT | Phase 0 MCP stub server; Envoy's MCP server at `/mcp` (Phase 4) |
| [FastAPI](https://github.com/fastapi/fastapi) | 0.162.0 | MIT | The task API, event stream, approvals and live view (Phase 4); REST fallback for the Muse connector test |
| [Starlette](https://github.com/encode/starlette) | 1.10.0 | BSD-3-Clause | ASGI layer under FastAPI and the MCP server; bearer-token middleware |
| [Uvicorn](https://github.com/encode/uvicorn) | 0.54.0 | BSD-3-Clause | ASGI server |
| [Pydantic](https://github.com/pydantic/pydantic) | 2.14.1 | MIT | Data models and the action JSON schema |
| [OpenAI Python SDK](https://github.com/openai/openai-python) | 3.39.0 | Apache-2.0 | Client for Meta's OpenAI-compatible Model API (Responses API) |
| [gRPC Python](https://github.com/grpc/grpc) (`grpcio`, `grpcio-tools`) | 1.85.0 | Apache-2.0 | Emulator gRPC screenshots; stub generation |
| [Protocol Buffers](https://github.com/protocolbuffers/protobuf) | 7.36.2 | BSD-3-Clause | Message types for the emulator gRPC API |
| Android emulator `emulator_controller.proto` (AOSP, ships with the emulator) | emulator 37.x | Apache-2.0 | Source for the generated gRPC stubs |
| [HTTPX](https://github.com/encode/httpx) | 0.28.1 | BSD-3-Clause | HTTP client for tests and the MCP client |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | 1.2.4 | BSD-3-Clause | Loads `.env` |
| [PyYAML](https://github.com/yaml/pyyaml) | 6.0.3 | MIT | Reads and writes routine files (Phase 2) |
| [SQLite](https://sqlite.org) with FTS5 (Python's `sqlite3`) | 3.53.1 | Public domain | The memory store and its keyword index (Phase 3) |
| [Google API Python client](https://github.com/googleapis/google-api-python-client) | 2.201.0 | Apache-2.0 | Gmail (read-only) for memory (Phase 3; runs once you connect an account) |
| [google-auth-oauthlib](https://github.com/googleapis/google-auth-library-python-oauthlib), google-auth, google-auth-httplib2 | 1.5.0 / 2.62.0 / 0.4.4 | Apache-2.0 | The Gmail sign-in flow and tokens |
| httplib2, uritemplate, oauthlib, requests-oauthlib | 0.32.0 / 4.2.0 / 4.0.0 / 2.0.0 | MIT / BSD-3-Clause or Apache-2.0 / BSD-3-Clause / ISC | Dependencies of the Google client |
| [Pillow](https://github.com/python-pillow/Pillow) | 13.0.0 | MIT-CMU | Screenshot decoding, black-frame detection, image crops, live-view JPEG frames |
| [websockets](https://github.com/python-websockets/websockets) | 17.3 | BSD-3-Clause | WebSocket support under Uvicorn (event stream, live view); the Phase 4 gate script's client |
| [Next.js](https://github.com/vercel/next.js) | 16.4.3 | MIT | The web app, built as a static export the API serves (Phase 4) |
| [React](https://github.com/facebook/react), React DOM | 19.3.0 | MIT | Web app UI |
| [Tailwind CSS](https://github.com/tailwindlabs/tailwindcss) (with `@tailwindcss/turbopack`) | 4.3.3 | MIT | Web app styling |
| [d3-force](https://github.com/d3/d3-force), [d3-zoom](https://github.com/d3/d3-zoom), [d3-quadtree](https://github.com/d3/d3-quadtree), [d3-selection](https://github.com/d3/d3-selection) | 3.0.0 / 3.0.0 / 3.0.1 / 3.0.0 | ISC | The memory graph: the force simulation, pan and pinch zoom, finding the node under the pointer. The graph view itself (drawing, hover focus, label fade, groups, Focus) is ours (`web/components/GraphCanvas.tsx`) |
| d3-zoom's dependencies: d3-dispatch, d3-drag, d3-interpolate, d3-transition, d3-timer, d3-color; d3-ease | 3.0.x / 3.1.0; 3.0.1 | ISC; BSD-3-Clause | Installed with d3-zoom |
| [Phosphor Icons for React](https://github.com/phosphor-icons/react) (`@phosphor-icons/react`) | 2.1.10 | MIT | The web app's icons (regular weight; fill for the active tab), from the Sage redesign |
| [Fraunces](https://github.com/undercasetype/Fraunces) by Undercase Type, self-hosted with [Fontsource](https://github.com/fontsource/fontsource) (`@fontsource-variable/fraunces`) | 5.3.0 | OFL-1.1 (font), MIT (package) | Envoy's voice in the web app: the greeting, the briefing, its replies, sheet titles |
| [Manrope](https://github.com/sharanda/manrope) by Mikhail Sharanda, self-hosted with Fontsource (`@fontsource-variable/manrope`) | 5.3.0 | OFL-1.1 (font), MIT (package) | The web app's text |
| [sharp](https://github.com/lovell/sharp) (already in `web/node_modules` through Next.js) | 0.35.5 | Apache-2.0 | Renders the app icons from `web/public/icons/mark.svg` (`scripts/make_icons.mjs`, build time) |
| [TypeScript](https://github.com/microsoft/TypeScript) | 5.9.3 | Apache-2.0 | Web app language (build time) |
| [scrcpy](https://github.com/Genymobile/scrcpy) (its server, `scrcpy-server`, from the Homebrew install) | 5.0.1 | Apache-2.0 | Phase 6: the real phone's screen and input. Envoy pushes the unmodified server to the phone and speaks its protocol itself (`backend/devices/scrcpy.py`: H.264 video socket, binary control messages); Phase 0's secure-screen test |
| [PyAV](https://github.com/PyAV-Org/PyAV) | 19.0.2 | BSD-3-Clause | Phase 6: decodes the phone's H.264 stream on the Mac (its wheels bundle FFmpeg's libraries, LGPL-2.1+, unmodified) |
| [NumPy](https://github.com/numpy/numpy) | 2.5.4 | BSD-3-Clause | Phase 6: FFT cross-correlation that finds a routine's recorded picture of a target on the screen |
| [cloudflared](https://github.com/cloudflare/cloudflared) | 2026.10.3 | Apache-2.0 | Quick tunnel giving the MCP stub (Phase 0) and Envoy's MCP server (Phase 5, `/mcp` only) a public HTTPS address for Muse |
| [pywebpush](https://github.com/web-push-libs/pywebpush) | 2.5.0 | MPL-2.0 | Web Push sending (RFC 8030/8291 encryption, VAPID) for approval, takeover and task notifications (Phase 5); unmodified |
| [py-vapid](https://github.com/web-push-libs/vapid) | 1.9.6 | MPL-2.0 | VAPID signing, used by pywebpush; unmodified |
| [http-ece](https://github.com/web-push-libs/encrypted-content-encoding) | 1.2.1 | MIT | aes128gcm content encryption, used by pywebpush (and by our fake push service in tests to decrypt) |
| [cryptography](https://github.com/pyca/cryptography) | 50.0.2 | Apache-2.0 or BSD-3-Clause | The server's VAPID key pair |
| aiohttp, requests (pulled in by pywebpush) | 3.14.5 / 2.34.2 | Apache-2.0 and MIT / Apache-2.0 | HTTP for pywebpush (Envoy uses its synchronous path) |
| [python-multipart](https://github.com/Kludex/python-multipart) | 0.0.32 | Apache-2.0 | Photo uploads from the app's picker (multipart forms) |
| [segno](https://github.com/heuer/segno) | 1.6.6 | BSD-3-Clause | The QR code of Envoy's tailnet address on the pairing screen |
| [Tailscale](https://github.com/tailscale/tailscale) (client, Serve) | 1.104.2 | BSD-3-Clause (client) | Private HTTPS on your tailnet for the iPhone (`scripts/serve_tailnet.sh`); the coordination service is Tailscale's |
| Apple Vision framework (`VNRecognizeTextRequest`), via `backend/memory/ocr.swift` | macOS 26 | Apple system framework | On-device text reading for photos and screenshots (Phase 5) |
| Apple Shortcuts (`shortcuts sign`) | macOS 26 / iOS 26 | Apple system app | Signing and running the "Send to Envoy" shortcut that `scripts/make_shortcut.py` writes |
| [Jetpack Compose](https://developer.android.com/jetpack/compose) / AndroidX | BOM 2026.09.00 | Apache-2.0 | SkyLark Air, Envoy's test app (Phase 1; the canvas seat map in Phase 6; the notice card for planted instructions in Phase 7) |
| [Matplotlib](https://github.com/matplotlib/matplotlib) | 3.11.2 | Matplotlib License (PSF-based, BSD-compatible) | Phase 7: the evaluation report's charts (`eval/final_report.py`); an eval-only dependency group, not used by Envoy itself |
| contourpy, cycler, fonttools, kiwisolver, pyparsing, python-dateutil, six, packaging (pulled in by Matplotlib) | 1.4.0 / 0.12.1 / 4.68.0 / 1.5.1 / 3.3.3 / 3.0.0 / 1.17.0 / 26.3 | BSD-3-Clause / BSD-3-Clause / MIT / BSD-3-Clause / MIT / Apache-2.0 or BSD-3-Clause / MIT / Apache-2.0 or BSD-2-Clause | Matplotlib's dependencies, unmodified |

uiautomator2 also installs its own helper APK (`app-uiautomator`, same project, MIT) on the phone when it is first used.

Envoy's own Android code (ours, built with the Android Gradle Plugin and Kotlin, Apache-2.0 build tools): SkyLark Air (`testapps/skylark`, Jetpack Compose) and, in Phase 6, the banner app (`android/banner`) that shows on a real phone while Envoy works on it.

Development tools (not shipped):
- [uv](https://github.com/astral-sh/uv) (MIT or Apache-2.0)
- Homebrew OpenJDK 21 (GPL-2.0 with Classpath Exception)
- [FFmpeg](https://ffmpeg.org) (LGPL-2.1+/GPL; run as an external tool to pull a frame from scrcpy recordings)
- Android SDK command-line tools, platform-tools, build-tools (`aapt2`, which `backend/devices/apps.py` runs on an app's APK to read the name people know it by, cached per app version) and emulator (Android Software Development Kit License; not open source, used as tools only)

## What Envoy builds itself

Envoy uses open source as plumbing (talking to phones, streaming video, serving HTTP). Everything below is Envoy's own work, and it is what the write-up and demo claim:

- **App routines** (built in Phase 2, Oct 27, `backend/routines/`): compiling one successful run into a program with inputs, code checks before and after every step, element-based locators, local self-repair saved as versioned patches with a trial period and rollback, and portability across screen sizes and devices. No routine, macro or workflow library is used; the format, compiler, locator scoring, check writer, executor, fallback ladder, patcher and store are Envoy's own code.
- **A memory graph built from phone screens** (built in Phase 3, Oct 27, `backend/memory/`; SQLite is only the storage): facts pulled from app screens, email and photos, each with screen-level provenance and two timelines; one entity per real-world thing across sources; user edits that outrank extracted facts; routine inputs filled from memory and outputs written back.
- **A device layer that routes between phones:** one interface over emulators and real phones, the compact screen format, settle detection, secure-screen detection from window flags, and the hand-off to the user for sign-in.
- **A policy engine:** three independent signals vote on irreversible actions, and approvals come only from Envoy's own screens, never from an AI client.
- **The task runner, takeover and approvals** (built in Phase 4, Oct 27, `backend/api/`): one task model for every interface, device leases where the agent waits at its next call to the phone while the user is in control, web approvals bound to the app's own screen with per-approval nonces, the live-view protocol on emulator gRPC frames, the scheduler with memory-derived triggers, chat routing, the MCP tools, and the web app (`web/`). FastAPI, the MCP SDK, Next.js, React and Tailwind are plumbing. The memory graph view (Oct 31–Nov 1, `web/components/GraphCanvas.tsx`) is drawn by Envoy on a Canvas 2D element; d3's force simulation, zoom and quadtree are plumbing under it.
- **The iPhone companion and voice** (built in Phase 5, Oct 27; `backend/api/auth.py`, `push.py`, `voice.py`, `backend/memory/photos.py`, `ocr.swift`, `web/lib/device.ts`, `web/lib/voice.ts`, `web/public/sw.js`): pairing a device with a short code typed inside the Home Screen app, scoped device tokens that can only upload images, the host and origin checks, which events push and what a push may carry (never a nonce), push receipts that measure delivery, the push-to-talk relay to Muse Voice Transcribe with silence padding to real time, the AudioWorklet resampler, touch and iPhone-keyboard input for the live view with clock-offset latency, and photos to facts: on-device OCR with a tiled second pass, redaction of the image before it leaves the Mac, Spark vision extraction checked against the image's text (tolerating only OCR glyph confusions in codes), photo sources, merging into known trips by natural keys, and deleting the image. The "Send to Envoy" shortcut is generated by `scripts/make_shortcut.py`; the icons are drawn by `scripts/make_icons.py`. pywebpush, Tailscale, Apple's Vision framework and Shortcuts are plumbing.
- **Muse integration:** Envoy as the phone layer behind the real Muse app, through a custom MCP connector (a public tunnel reaches `/mcp` and nothing else).
- **The real phone and screens with no tree** (built in Phase 6, Oct 27–28; `backend/devices/android.py`, `phone.py`, `scrcpy.py`, `backend/api/routing.py`, `backend/agent/vision.py`, `backend/routines/visual.py`, `android/banner`): one device layer over emulators and real phones; a scrcpy client of our own (the server's video and control protocols, decoded on the Mac) for the phone's live view, input and screenshots; telling your touches from Envoy's (`getevent` sees only physical input); routing between phones by the design's table, asking before your phone is used, the on-phone banner with Pause, and pausing on a touch or another app; scroll-to-reveal and scrolled-output reading that made routines portable to a smaller screen; finding drawn targets (grounding, SAM 3.1 + a model's pick, and the two combined) and routines that replay them from their recorded picture (density-scaled cross-correlation) or by looking again; SkyLark's canvas seat map for exact checks.

- **The evaluation and what it changed** (Phase 7, Oct 27–Nov 2; `eval/run_final.py` and `eval/final_*.py`, `backend/routines/lifecycle.py`): one command per suite with its commit, tier and cost recorded; the core set as seeded worlds where any side effect fails a run; the product's own routine path measured against the full agent and fixed replay; the patch lifecycle (trial on the next run, then active or rolled back) shared by the API and the evaluation; a safety suite of captured real-app and SkyLark screens with the classifier as Phase 6 left it beside the new one; planted instructions on screens and in email; and the fixes the suites found (policy rules for points, prices, calls and destructive confirmations; a step schema without `tap_point` where it can only be a guess; checks that look past the edge of the screen; outputs read from an element's whole text; the first search result chosen by its place; inferred answers reported as their screen text). matplotlib only draws the charts.

## Planned (later phases)

| Component | License | What we will use it for |
| --- | --- | --- |
| [sqlite-vec](https://github.com/asg017/sqlite-vec) | MIT or Apache-2.0 | Similarity search, only if needed |

## Considered and not used

| Component | License | Why not |
| --- | --- | --- |
| Mobilerun Portal | AGPL-3.0 | Copyleft; Envoy uses uiautomator2 (and possibly its own bridge) instead |
| Android emulator WebRTC (`android-emulator-webrtc`) | Apache-2.0 | Emulator-only, container scripts are Linux x86 only; scrcpy is used everywhere |
| [Tango](https://github.com/yume-chan/ya-webadb) `@yume-chan/adb-scrcpy`, `@yume-chan/scrcpy-decoder-webcodecs` | MIT | The design's plan for the real-phone live view (a Node relay, H.264 decoded in the browser). Phase 6 decodes on the Mac instead (PyAV), which reuses the live view's JPEG protocol and gives the agent screenshots from the same frames |
| `meta-sam-parser` (PyPI) / `@meta-sam/parser` (npm), from Meta | Not checked | SAM 3.1's box tokens are parsed by Envoy's own few lines (`backend/agent/vision.py`); masks aren't used |

## Ideas borrowed (no code used)

- **Graphiti / Zep** (Apache-2.0): bi-temporal facts (valid time and record time).
- **SkillDroid, MobileGPT, Agent Workflow Memory, Agent Skill Induction**: compiling agent runs into reusable routines. Cited in the design doc.
