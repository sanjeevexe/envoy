# Envoy

*Agents can search the web. Your phone knows your life.*

Envoy is a Muse-powered agent that operates Android apps on emulated phones, compiles successful runs into reusable **app routines**, and keeps a shared **memory graph** across web, voice, iPhone and MCP clients. Built solo for the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026, indie track).

- Design: [`docs/technical-design.md`](docs/technical-design.md) (live version: https://claude.ai/artifact/Sf51zMf4SMi5ZZmJabgPR5)
- Phase results: [`docs/phase-0-findings.md`](docs/phase-0-findings.md) · [`docs/phase-1-results.md`](docs/phase-1-results.md) (agent loop) · [`docs/phase-2-results.md`](docs/phase-2-results.md) (app routines) · [`docs/phase-3-results.md`](docs/phase-3-results.md) (memory graph) · [`docs/phase-4-results.md`](docs/phase-4-results.md) (web app, live view, approvals, MCP) · [`docs/real-app-test-set.md`](docs/real-app-test-set.md)
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

## App routines in one minute

```bash
uv run --project backend python scripts/run_task.py "Check me in for my flight to Denver" --skylark --approve-all   # the agent, once
uv run --project backend python scripts/compile_routine.py <task_id>                                               # its trace → a routine
eval/run_phase2.sh                                                                                                  # the Phase 2 evaluation
```

How routines work: [`backend/routines/README.md`](backend/routines/README.md). How memory works: [`backend/memory/README.md`](backend/memory/README.md) (`eval/run_memory.py`, `scripts/show_memory.py`; real mail: `scripts/connect_gmail.py` once, then `scripts/ingest_mail.py`). Example routines: [`eval/results/phase2/compiled/`](eval/results/phase2/compiled/); the library with versions and patch evidence: [`data/routines/`](data/routines/) and [`eval/results/phase2/library/`](eval/results/phase2/library/).
