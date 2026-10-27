# Envoy

*Agents can search the web. Your phone knows your life.*

Envoy is a Muse-powered agent that operates Android apps on emulated phones, compiles successful runs into reusable **app routines**, and keeps a shared **memory graph** across web, voice, iPhone and MCP clients. Built solo for the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026, indie track).

- Design: [`docs/technical-design.md`](docs/technical-design.md) (live version: https://claude.ai/artifact/Sf51zMf4SMi5ZZmJabgPR5)
- Phase 0 findings: [`docs/phase-0-findings.md`](docs/phase-0-findings.md)
- Open-source credits: [`THIRD_PARTY.md`](THIRD_PARTY.md) · License: MIT ([`LICENSE`](LICENSE))

## Layout

| Folder | What |
| --- | --- |
| `backend/` | Python 3.13 (`uv`): device layer, agent runtime, routines, memory, model adapter, MCP |
| `bridge-android/` | Optional Kotlin accessibility service |
| `relay/` | Node scrcpy video relay |
| `web/` | Next.js web app |
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
