# Third-party components

Envoy builds on the open-source projects below. The hackathon rules allow open source as long as it is credited, so this list is kept current: add a row when a dependency is added, and move a row from "Planned" to "In use" when it lands.

Licenses for Python packages were read from the installed package metadata (Oct 26, 2026). Licenses for planned components come from their repositories and must be re-checked when they are added.

## In use (Phase 0)

| Component | Version | License | What we use it for |
| --- | --- | --- | --- |
| [uiautomator2](https://github.com/openatx/uiautomator2) (and its on-device `android-uiautomator-server`) | 3.7.1 | MIT | Reads the accessibility tree, taps, types any language through its input method |
| [adbutils](https://github.com/openatx/adbutils) | 2.12.0 | MIT | Python adb client: shell, port forwarding, `screencap` |
| [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) (`mcp`) | 2.3.0 | MIT | Phase 0 MCP stub server (Streamable HTTP); the real MCP server later |
| [FastAPI](https://github.com/fastapi/fastapi) | 0.162.0 | MIT | REST fallback for the Muse connector test; task API later |
| [Starlette](https://github.com/encode/starlette) | 1.10.0 | BSD-3-Clause | ASGI layer under FastAPI and the MCP server; bearer-token middleware |
| [Uvicorn](https://github.com/encode/uvicorn) | 0.54.0 | BSD-3-Clause | ASGI server |
| [Pydantic](https://github.com/pydantic/pydantic) | 2.14.1 | MIT | Data models and the action JSON schema |
| [OpenAI Python SDK](https://github.com/openai/openai-python) | 3.39.0 | Apache-2.0 | Client for Meta's OpenAI-compatible Model API (Responses API) |
| [gRPC Python](https://github.com/grpc/grpc) (`grpcio`, `grpcio-tools`) | 1.85.0 | Apache-2.0 | Emulator gRPC screenshots; stub generation |
| [Protocol Buffers](https://github.com/protocolbuffers/protobuf) | 7.36.2 | BSD-3-Clause | Message types for the emulator gRPC API |
| Android emulator `emulator_controller.proto` (AOSP, ships with the emulator) | emulator 37.x | Apache-2.0 | Source for the generated gRPC stubs |
| [HTTPX](https://github.com/encode/httpx) | 0.28.1 | BSD-3-Clause | HTTP client for tests and the MCP client |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | 1.2.4 | BSD-3-Clause | Loads `.env` |
| [Pillow](https://github.com/python-pillow/Pillow) | 13.0.0 | MIT-CMU | Screenshot decoding, black-frame detection, image crops |
| [scrcpy](https://github.com/Genymobile/scrcpy) | 5.0.1 | Apache-2.0 | Phone screen video (Phase 0 secure-screen test; live view later through the relay) |
| [cloudflared](https://github.com/cloudflare/cloudflared) | 2026.10.3 | Apache-2.0 | Quick tunnel giving the MCP stub a public HTTPS address |

uiautomator2 also installs its own helper APK (`app-uiautomator`, same project, MIT) on the phone when it is first used.

Development tools (not shipped):
- [uv](https://github.com/astral-sh/uv) (MIT or Apache-2.0)
- Homebrew OpenJDK 21 (GPL-2.0 with Classpath Exception)
- [FFmpeg](https://ffmpeg.org) (LGPL-2.1+/GPL; run as an external tool to pull a frame from scrcpy recordings)
- Android SDK command-line tools, platform-tools and emulator (Android Software Development Kit License; not open source, used as tools only)

## What Envoy builds itself

Envoy uses open source as plumbing (talking to phones, streaming video, serving HTTP). Everything below is Envoy's own work, and it is what the write-up and demo claim:

- **App routines:** compiling one successful run into a program with inputs, code checks before and after every step, element-based locators, local self-repair saved as versioned patches with a trial period and rollback, and portability across screen sizes and devices.
- **A memory graph built from phone screens:** facts pulled from app screens, email and photos, each with screen-level provenance and two timelines; one entity per real-world thing across sources; user edits that outrank extracted facts; routine inputs filled from memory and outputs written back.
- **A device layer that routes between phones:** one interface over emulators and real phones, the compact screen format, settle detection, secure-screen detection from window flags, and the hand-off to the user for sign-in.
- **A policy engine:** three independent signals vote on irreversible actions, and approvals come only from Envoy's own screens, never from an AI client.
- **Muse integration:** Envoy as the phone layer behind the real Muse app, through a custom MCP connector.

## Planned (later phases)

| Component | License | What we will use it for |
| --- | --- | --- |
| [Tango](https://github.com/yume-chan/ya-webadb) `@yume-chan/adb`, `@yume-chan/adb-scrcpy`, `@yume-chan/scrcpy-decoder-webcodecs` | MIT | Node video relay and in-browser WebCodecs decoding for the live view |
| [Next.js](https://github.com/vercel/next.js), [React](https://github.com/facebook/react) | MIT | Web app |
| [Tailwind CSS](https://github.com/tailwindlabs/tailwindcss) | MIT | Web app styling |
| [Cytoscape.js](https://github.com/cytoscape/cytoscape.js) | MIT | Memory graph view |
| [APScheduler](https://github.com/agronholm/apscheduler) 3.x | MIT | Scheduled tasks and watchers |
| [SQLite](https://sqlite.org) (FTS5) | Public domain | Memory store |
| [sqlite-vec](https://github.com/asg017/sqlite-vec) | MIT or Apache-2.0 | Similarity search, only if needed |
| [PyAV](https://github.com/PyAV-Org/PyAV) | BSD-3-Clause | Decoding scrcpy frames for the agent |
| [Google API Python client](https://github.com/googleapis/google-api-python-client) | Apache-2.0 | Gmail and Calendar |
| [Jetpack Compose](https://developer.android.com/jetpack/compose) / AndroidX | Apache-2.0 | Test apps (SkyLark Air) |
| `meta-sam-parser` (PyPI) / `@meta-sam/parser` (npm), from Meta | License to check when added | Parsing SAM 3.1's special-token output (Phase 6) |

## Considered and not used

| Component | License | Why not |
| --- | --- | --- |
| Mobilerun Portal | AGPL-3.0 | Copyleft; Envoy uses uiautomator2 (and possibly its own bridge) instead |
| Android emulator WebRTC (`android-emulator-webrtc`) | Apache-2.0 | Emulator-only, container scripts are Linux x86 only; scrcpy is used everywhere |

## Ideas borrowed (no code used)

- **Graphiti / Zep** (Apache-2.0): bi-temporal facts (valid time and record time).
- **SkillDroid, MobileGPT, Agent Workflow Memory, Agent Skill Induction**: compiling agent runs into reusable routines. Cited in the design doc.
