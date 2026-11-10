# Envoy docs

**Envoy is the phone layer agents call.** It **acts** in Android apps, **learns** the tasks it does there, and
**watches** the phone for events. Envoy gives AI agents a phone.

Envoy isn't a rival assistant. It's an MCP server: Muse, Claude Code or any other MCP agent is a way in. The
person asks there, and the agent calls Envoy. Envoy's own app, on the person's iPhone, is where they approve anything irreversible and watch the phone
work.

This page is the map. The final numbers come from the Nov 3 evaluation on the `eval-final` tag.

## Start here

| Read | For |
| --- | --- |
| [models.md](models.md) | What each Meta model does, how a run is compiled into a routine, repair, vision and memory |
| [features.md](features.md) | Every feature, what it does, and the evidence for it |
| [results.md](results.md) | Every result with its scope, configuration and commit |
| [getting-started.md](getting-started.md) | Setup on a Mac, with or without a model key, the iPhone, and running the evaluation |
| [reports/](reports/README.md) | Engineering reports from building each feature, cited as evidence |

## The current design

- **[technical-design.md](technical-design.md)**: the whole system, in sections:
  - Overview and Architecture: the three pillars and how one request flows.
  - Device layer: the phones, and how a task's phone is chosen.
  - Agent runtime, App routines and Shared memory: the core.
  - Interfaces: MCP, the iPhone app, voice, triggers.
  - Safety: approvals, redaction, prompt injection.

  The diagrams are in [diagrams/](diagrams/). The [architecture](diagrams/architecture.png) and the
  [routine lifecycle](diagrams/routine-lifecycle.png) are current. The [build phases](diagrams/build-phases.png)
  diagram is the Oct 26 plan.
- **Each pillar, and where it's built:**

  | Pillar | What it is | Read |
  | --- | --- | --- |
  | Acts | Real Android apps, run step by step by an agent on Meta's models (or replayed by a routine), on Envoy's phone, an emulator, or a cloud phone. Anything irreversible waits for the person's yes on their iPhone. | [technical-design.md](technical-design.md) (Agent runtime, Safety), [app-routing-onboarding.md](app-routing-onboarding.md), [preflight-and-autofill.md](preflight-and-autofill.md) |
  | Learns | A successful run compiles into a **routine**: a program that checks its screens, repairs itself when the app changes, and keeps versions. A routine replays in seconds, with few or no model calls. Teach mode learns a routine from the person doing the task once. A routine shared with agents becomes an MCP tool of its own. | [technical-design.md](technical-design.md) (App routines), [../backend/routines/README.md](../backend/routines/README.md), [teach-mode trials](../eval/results/teach_trials_2026-11-01/README.md) |
  | Watches | Notification triggers (a phone notification starts a task or reaches the agent), time triggers, change alerts, habits, and `phone_updates` for agents. | [technical-design.md](technical-design.md) (Scheduled and event-triggered tasks) |
  | Remembers | A memory graph built from app screens, Gmail (read-only) and shared screenshots. Every fact keeps its source. | [technical-design.md](technical-design.md) (Shared memory), [../backend/memory/README.md](../backend/memory/README.md) |

## How agents connect

Three agents have called Envoy: **Muse** (Meta's assistant, on the Mac and in its iPhone app), **the Spark agent**
(a small agent on Meta's models, in this repo) and **Claude Code**. Any MCP client can use the same server.

| Read | For |
| --- | --- |
| [agents.md](agents.md) | Connecting any agent: the per-agent key, the tool groups, Claude Code, the Spark agent, any other client |
| [../backend/mcp_server/README.md](../backend/mcp_server/README.md) | The exact tool list and what each tool does |
| [muse-link.md](muse-link.md) | Muse: files from the Mac to the phone (`send_to_phone`), files back (`get_file`), `phone_updates`, and what was tested with Muse |
| [../agents/meta-agent/README.md](../agents/meta-agent/README.md) | The Spark agent: an agent on Muse Spark 1.3 that uses Envoy only over MCP, with a page showing the conversation and every MCP call |
| [siri.md](siri.md) | Not an agent: the person's own "Ask Envoy" from Siri, the Action Button or Control Center |

No agent can approve anything. Envoy has no approve tool, and no tool that accepts an offer or answers Envoy's
questions. An agent is told that the task waits for the person's OK in Envoy.

## The phones

| Phone | What it is | Read |
| --- | --- | --- |
| **Envoy's phone** | A Pixel 5 on Android 13, plugged into the Mac over USB. Envoy asks the person before each task uses it, and shows a banner on it while it works. | [technical-design.md](technical-design.md) (Device layer), [phase-6-results.md](phase-6-results.md) |
| Emulators on the Mac | `envoy-test` (SkyLark, our own test airline app) and `envoy-real` (real apps, signed in). | [technical-design.md](technical-design.md) (Device layer), [app-routing-onboarding.md](app-routing-onboarding.md) |
| A cloud phone | The same emulators on a Google Cloud server, with Envoy running there too. Tested Oct 29 and Nov 1. | [cloud.md](cloud.md) |

An agent can see the phones with `list_phones` and pick one with `phone` on `run_task`, `run_routine` and the routine
tools. The person's own phone still asks them first.

## The showcase

- **[demo-showcase.md](demo-showcase.md)** is the app-only cross-post. One clip from the Mac goes out as an Instagram
  Reel with a library song, a TikTok with a sound, a YouTube Short with a sound, and an Instagram Story with a poll
  sticker. Each is a routine Envoy learned, called as a tool, and each feature exists only in the app.
- **[demo-creator-workflow.md](demo-creator-workflow.md)** is the earlier Instagram scene: a clip from the Mac's outbox,
  an offer on the iPhone, a Reel. Its file path (outbox, offer, post) is still how a clip reaches the phone.

## Results

The final numbers are in [results.md](results.md) and
[final/report.md](../eval/results/final/report.md). The per-phase pages below have the detail and the method up to
Oct 29.

## Historical records

These record what was planned, measured or found at the time. They aren't updated, so later work may have changed
what they describe.

| Page | What it records |
| --- | --- |
| [phase-0-findings.md](phase-0-findings.md) | Oct 26–27: what Meta's models, the emulator, real apps and Muse's connector could do before any build |
| [meta-api-test-plan.md](meta-api-test-plan.md) | The Phase 0 gate's test plan |
| [phase-1-results.md](phase-1-results.md) | The agent loop on SkyLark |
| [phase-2-results.md](phase-2-results.md) | Routines: compile, replay, repair, versions |
| [phase-3-results.md](phase-3-results.md) | The memory graph |
| [phase-4-results.md](phase-4-results.md) | The web app, live view, approvals and the first MCP server |
| [phase-5-results.md](phase-5-results.md) | The iPhone app, push, voice and photos |
| [phase-6-results.md](phase-6-results.md) | Envoy's phone (the Pixel 5) and SAM 3.1 |
| [phase-7-results.md](phase-7-results.md) | The final evaluation's measurement passes and teach mode, before the final run |
| [androidworld-results.md](androidworld-results.md) | Envoy on AndroidWorld (Oct 28–29) |
| [real-app-test-set.md](real-app-test-set.md) | The first real-app results (Oct 27) |
| [research/agents-and-bot-checks.md](research/agents-and-bot-checks.md) | Background research on phone agents and bot checks |
| [meta-feedback.md](meta-feedback.md) | Notes on Meta's AI tools: what worked and what could be better |
