# Envoy docs

**Envoy is the phone layer agents call.** It **acts** in Android apps, **learns** the tasks it does there, and
**watches** the phone for events. Muse has a computer; Envoy gives it a phone.

Envoy isn't a rival assistant. Muse, or any other MCP agent, is the front door: the person asks there, and the agent
calls Envoy. Envoy's own app, on the person's iPhone, is where they approve anything irreversible and watch the phone
work.

This page is the map. It describes main as of Nov 2, 2026 (`947bf44`). The final evaluation runs Nov 3, 17:00–22:00
ET, on the `eval-final` tag. Until then, every number here comes from development commits (Oct 27–Nov 2), and each
one names its source.

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
  | Acts | Real Android apps, run step by step by an agent on Muse Spark 1.3 (or replayed by a routine), on Envoy's phone, an emulator, or a cloud phone. Anything irreversible waits for the person's yes on their iPhone. | [technical-design.md](technical-design.md) (Agent runtime, Safety), [app-routing-onboarding.md](app-routing-onboarding.md), [preflight-and-autofill.md](preflight-and-autofill.md) |
  | Learns | A successful run compiles into a **routine**: a program that checks every screen, repairs itself when the app changes, and keeps versions. A routine replays in seconds, with few or no model calls. Teach mode learns a routine from the person doing the task once. A routine shared with agents becomes an MCP tool of its own. | [technical-design.md](technical-design.md) (App routines), [../backend/routines/README.md](../backend/routines/README.md), [teach-mode trials](../eval/results/teach_trials_2026-11-01/README.md) |
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
| [../agents/meta-agent/README.md](../agents/meta-agent/README.md) | The Spark agent: an agent on Muse Spark 1.3 that uses Envoy only over MCP, with a page made for filming |
| [connector-application.md](connector-application.md) | Drafts for Meta's listed-connector review and the Connectors preview (not sent) |
| [siri.md](siri.md) | Not an agent: the person's own "Ask Envoy" from Siri, the Action Button or Control Center |

No agent can approve anything. Envoy has no approve tool, and no tool that accepts an offer or answers Envoy's
questions. An agent is told that the task waits for the person's OK in Envoy.

## The phones

| Phone | What it is | Read |
| --- | --- | --- |
| **Envoy's phone** | A Pixel 5 on Android 13, plugged into the Mac over USB. Envoy asks the person before each task uses it, and shows a banner on it while it works. | [technical-design.md](technical-design.md) (Device layer), [phase-6-results.md](phase-6-results.md) |
| Emulators on the Mac | `envoy-test` (SkyLark, our own test airline app) and `envoy-real` (real apps, signed in). | [technical-design.md](technical-design.md) (Device layer), [app-routing-onboarding.md](app-routing-onboarding.md) |
| A cloud phone | The same emulators on a Google Cloud server, with Envoy running there too. Tested Oct 29 and Nov 1; stopped now. | [cloud.md](cloud.md) |

An agent can see the phones with `list_phones` and pick one with `phone` on `run_task`, `run_routine` and the routine
tools. The person's own phone still asks them first.

## The showcase

- **[demo-showcase.md](demo-showcase.md)** is the app-only cross-post. One clip from the Mac goes out as an Instagram
  Reel with a library song, a TikTok with a sound, a YouTube Short with a sound, and an Instagram Story with a poll
  sticker. Each is a routine Envoy learned, called as a tool, and each feature exists only in the app.
- **[demo-creator-workflow.md](demo-creator-workflow.md)** is the earlier Instagram scene: a clip from the Mac's outbox,
  an offer on the iPhone, a Reel. Its file path (outbox, offer, post) is still how a clip reaches the phone.

## Results

**The final numbers come from the Nov 3 run on `eval-final`.** Until then, these are from development commits.
Each row names the file it comes from. After the final run, `eval/run_final.py report` rewrites
[../eval/results/final/report.md](../eval/results/final/report.md), and this table follows it.

| What | Result | Source |
| --- | --- | --- |
| SkyLark core set, three systems, 4 layouts | Envoy routines 40/40 first try, median 1.0 model call, 5.5 s. Full agent every time 40/40, median 5.0 calls, 10.1 s. Fixed replay 14/40 | [final/report.md](../eval/results/final/report.md) suite 1 (`ad9a67b`, Oct 28) |
| First run against later runs | Request 1: median $0.051 and 27.9 s. Requests 2–10: 90/90 right, median 1.0 call, $0.0023, 5.9 s | [final/report.md](../eval/results/final/report.md) suite 2 (`5c3d716`) |
| Routines under change | New inputs 50/50, all with no model call. Injected UI changes recovered 50/50, then 50/50 ran alone with no model call | [final/report.md](../eval/results/final/report.md) suite 3 (`6c507f3`) |
| Screen sizes | `envoy-test` 30/30, `envoy-small` 30/30, `envoy-large` 29/30 | [final/report.md](../eval/results/final/report.md) suite 3b (`5504260`) |
| Envoy's phone (the Pixel 5) | The 10 core routines, compiled on an emulator: 30/30 on bookings they hadn't seen, no model calls | [phase-6-results.md](phase-6-results.md) (Oct 28) |
| Real apps, 18 read-only workflows | First run 14/18; rerun right with no model call 13/18; a new input 4/11 (Oct 28), then 6/11 on Oct 31 | [final/report.md](../eval/results/final/report.md) suite 4 (`00ec5d9`); [real_rerun_2026-10-31/real.md](../eval/results/real_rerun_2026-10-31/real.md) |
| Memory | Extraction 459/468 (98%) on 62 labeled items, 0 wrong; stale facts served without a warning 0/12 | [final/report.md](../eval/results/final/report.md) suite 5 (`5c3d716`) |
| Safety | Irreversible actions caught 20/20; live declines held 7/7; planted instructions followed 0 times in 20 | [final/report.md](../eval/results/final/report.md) suites 6 and 6b |
| AndroidWorld (Google's 116 tasks) | Held-out half: 31 of 58 (53.4%), against 12 for Envoy before the changes; 30.5 of 58 when re-measured Oct 29 | [androidworld-results.md](androidworld-results.md) |
| The cloud phone | SkyLark routines compiled on the Mac: 48/48 on a Google Cloud emulator, no model calls, median 5.5 s (3.1 s on the Mac) | [cloud.md](cloud.md) |
| The showcase, real posts (night of Nov 1) | All four app-only features went live once. The Reel with a song, the Story with a poll and the YouTube Short at 0 model calls each. The TikTok first went up without its sound (a routine defect, since fixed); the re-post had it, at 3 calls | [demo-showcase.md](demo-showcase.md), [showcase-report.md](../prompts/showcase-report.md) |
| Muse end to end (Nov 2, a dry run, every final step declined) | Muse called the shared routine tools by name. The Reel, the TikTok and the Short each reached their final button with the song: 0, 3 and 0 model calls, about 1 min 15 s each | [muse-link.md](muse-link.md) |
| Notifications (Nov 2) | An Instagram comment reached the iPhone 1.57 s after it landed on Envoy's phone. For YouTube, Envoy's part took 3.6 s, but YouTube took about 2 minutes to notify | [phone-watch-report.md](../prompts/phone-watch-report.md) |

The per-phase result pages (below) have the detail and the method for each number up to Oct 29.

## Known gaps

- The poll Story routine fails while a Story is already live (backlog #64).
- Teach mode can't yet learn keypad entry, or apps that reopen on their last screen.
- Target and banking apps refuse emulators, so they need Envoy's phone.
- No TikTok notification came through in testing (three comments), so TikTok notifications are unproven.
- An agent hears about phone events only when it checks `phone_updates`: Muse checks about every 10 minutes on its own,
  or right away if asked. Envoy's push to the iPhone is immediate.
- New inputs on real apps: 4 of 11 (Oct 28) and 6 of 11 (Oct 31). So a learned task is the claim, not a learned app.
- Envoy runs on a Mac today. The cloud copy is a tested option, not the default.

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
| [meta-feedback.md](meta-feedback.md) | A running log of feedback on Meta's products, for the submission |

[submission.md](submission.md) is the hackathon write-up.
