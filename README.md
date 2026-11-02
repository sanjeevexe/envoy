# Envoy

**Muse has a computer. Envoy gives it a phone.**

Envoy is the phone layer AI agents call. It **acts** in real Android apps, **learns** each task it does into a routine
that replays in seconds with few or no model calls, and **watches** the phone for what an agent should hear about.
Muse, Meta's assistant, is the front door: it calls Envoy as a custom MCP connector, and so can any MCP agent. Envoy's
own app on your iPhone is where you approve and watch. Nothing irreversible (a post, an order, a check-in) happens
without your yes.

**Why a phone layer.** Agents already work the web and a growing list of connectors, but some things exist only in
phone apps: a Reel set to a song from Instagram's music library, a Story with a poll sticker, a TikTok (Muse has no
TikTok connector). Asked on Nov 1, Muse described its own limit: "On its own, Muse can't open and tap around in apps on
your phone." And an agent that works an app step by step pays for every step, every time. Envoy replays what it learned
for almost nothing, which is also what makes watching the phone affordable.

**What that looks like.** You ask Muse on your Mac to post a clip with a song to Instagram, TikTok and YouTube. Muse
puts the clip on Envoy's phone (`send_to_phone`), then calls the routine Envoy learned for each app as a tool, by name.
Envoy's phone runs each one and stops at the app's final button until you approve on your iPhone.

- **Showcase site:** https://sanjeevexe.github.io/envoy/ (a guided tour built only from recorded runs and results)
- **Demo video (3 minutes):** TBD, the YouTube link goes here on Nov 4
- **The write-up:** [`docs/submission.md`](docs/submission.md)

Built solo for the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026, indie track). Open-source projects are
plumbing, credited in [`THIRD_PARTY.md`](THIRD_PARTY.md), which also says what Envoy builds itself.

## What works today

| | What | Evidence |
| --- | --- | --- |
| **Agents call it** | MCP at `/mcp` (Streamable HTTP), 12 tools: run a task or a routine, search memory, send a file to the phone, get files back, propose a trigger, list phones, read phone updates… Muse for Mac and the Muse app add it as a custom connector | [`backend/mcp_server/README.md`](backend/mcp_server/README.md), [`docs/muse-link.md`](docs/muse-link.md) |
| **Three agents** | Muse; the Spark agent, a small agent on Meta's Muse Spark that reaches Envoy only over MCP; and Claude Code. Each has its own key and tool groups; every task says which agent asked | [`docs/agents.md`](docs/agents.md), [`agents/meta-agent/evidence/2026-11-01/`](agents/meta-agent/evidence/2026-11-01/) |
| **Learned tasks become tools** | Share a routine in Settings › Agents (off by default) and it appears in agents' tool lists under its own name, with typed inputs, no restart. Muse saw a newly added tool without reconnecting | [`prompts/agent-door-report.md`](prompts/agent-door-report.md), [`eval/results/agent-door/`](eval/results/agent-door/) |
| **App-only posts** | One clip from the Mac → an Instagram Reel with a library song, an Instagram Story with a poll sticker, a YouTube Short and a TikTok with a sound. Live on test accounts the night of Nov 1, each started by the Spark agent and approved on the iPhone; the Reel, Story and Short replayed with 0 model calls. The first TikTok lost its song (a compiler bug, since fixed); the re-post has it | [`docs/demo-showcase.md`](docs/demo-showcase.md), [`prompts/showcase-report.md`](prompts/showcase-report.md) |
| **Watches** | A notification on Envoy's phone can start a task or reach the agent; each app is off until you allow it, and codes are hidden before anything is stored. An Instagram comment reached the iPhone 1.6 s after it landed on Envoy's phone; YouTube works too (Envoy's part 3.6 s). Plus time, email and changed-fact triggers, change alerts, and habits | [`prompts/phone-watch-report.md`](prompts/phone-watch-report.md), [`prompts/proactive-report.md`](prompts/proactive-report.md), [`prompts/alerts-report.md`](prompts/alerts-report.md) |
| **Learns** | A successful run compiles into a routine: a check before and after every step, targets found by what they are, a local repair when the app changes, versions with a trial and a rollback | [`backend/routines/README.md`](backend/routines/README.md), [Results](#results-so-far) |
| **Teach mode** | Do a task once through the live view; Envoy compiles it and replays it once before saving. A Google Calendar lesson (7 steps) replayed 7/7 with 0 model calls | [`backend/api/README.md`](backend/api/README.md) (`teach.py`), [`site/README.md`](site/README.md), [`eval/results/teach_trials_2026-11-01/`](eval/results/teach_trials_2026-11-01/README.md) |
| **Phones** | "Envoy's phone" (a Pixel 5, Android 13, over USB) and emulators on the Mac; agents pick one with `list_phones`. A copy of Envoy on Google Cloud was tested too: routines for SkyLark, our own test app, compiled on the Mac ran there 48/48 with no model calls | [`docs/phase-6-results.md`](docs/phase-6-results.md), [`docs/cloud.md`](docs/cloud.md) |
| **Files** | `send_to_phone` puts a Mac clip on the phone (a real phone waits for your OK); `get_file` gives the agent the final screen, the screen you approved, or a link from its own task | [`docs/muse-link.md`](docs/muse-link.md), [`prompts/file-delivery-report.md`](prompts/file-delivery-report.md) |
| **You approve** | An irreversible step waits for your yes in Envoy on the iPhone, unless you set that routine to run without asking; spending money always asks. No agent has an approve tool; asked to approve, Claude Code and the Spark agent each said only you can | [`backend/policy/approval_rules.py`](backend/policy/approval_rules.py), [`docs/agents.md`](docs/agents.md) |

## Results so far

**Development numbers, not final.** Measured Oct 27–31 on development commits. The final evaluation runs Nov 3,
17:00–22:00 ET, on the `eval-final` tag; `eval/run_final.py report` then rewrites
[`eval/results/final/report.md`](eval/results/final/report.md), and its numbers replace these. Each row names its source.

| What | Result | Source |
| --- | --- | --- |
| A real-app task, learned once | "How many calories are in a Grande Caffè Latte?" in the Starbucks app. The agent's first run: 45.6 s, 12 model calls, $0.0795. The routine compiled from it: 14.8 s, 2 calls, $0.005, the same answer (190 calories) | [`eval/results/real-apps/loop-a/runs.jsonl`](eval/results/real-apps/loop-a/runs.jsonl) (`task-1030-155711-51c2`, `task-1030-204136-b8d5`) |
| Asking again | SkyLark, our own test airline app: the first request took a median 27.9 s and $0.051; requests 2–10 were 90/90 right at a median 1 model call, 5.9 s and $0.0023 (86% fewer calls) | [`report.md`](eval/results/final/report.md), suite 2 |
| Against simpler approaches | SkyLark, 10 tasks on 4 layouts: Envoy's routines 40/40 on the first try (median 1 call, 5.5 s); the agent every time 40/40 (5 calls, 10.1 s); a fixed replay 14/40 | `report.md`, suite 1 |
| When the app changes | We changed SkyLark's layout on purpose, 50 times: 50 recovered, then 50/50 ran with no model call. 50 new inputs: 50/50 with no model call | `report.md`, suite 3 |
| On Envoy's phone | The Pixel 5 (Android 13): the 10 core routines on 3 new bookings each, 30/30 with no model call | [`eval/results/final/sizes.md`](eval/results/final/sizes.md) |
| Real apps | 18 read-only workflows on test accounts: the first run right 14/18; the routine rerun right with no call 13/18; with a new input 4/11 (6/11 at the Oct 31 rehearsal); Target blocked by its bot check | `report.md`, suite 4; [`eval/results/real_rerun_2026-10-31/README.md`](eval/results/real_rerun_2026-10-31/README.md) |
| Safety | Irreversible steps caught 20/20 by code alone; 0 irreversible actions without approval over 7 declined live runs and 30 runs with planted instructions | `report.md`, suites 6 and 6b |
| AndroidWorld | 116 tasks, pass@1: Envoy as on `main` 21 (18%); with 13 general agent changes 57 (49%); on the held-out half 31 of 58 against 12; about $0.04 and 38 s a task | [`docs/androidworld-results.md`](docs/androidworld-results.md) |

## Limits, said plainly

- **Learn a task once, not an app:** new inputs on real apps passed 4 of 11 (Oct 28) and 6 of 11 (Oct 31). On our own
  test app, 50 of 50.
- **The Story routine fails while a Story is already live:** its first tap opens the live Story's poll results.
- **Teach mode** doesn't yet learn keypad entry reliably, or apps that reopen on their last screen.
- **No TikTok notifications:** TikTok sent none for any comment in testing.
- **Muse hears about phone events when it next checks** `phone_updates` (its scheduled task checked about every 10
  minutes). Envoy's own push to your iPhone is immediate.
- **Apps that refuse emulators** (Target's bot check, banking apps) need a real Android phone.
- **Envoy runs on a Mac today,** with Envoy's phone over USB; the cloud phone is a tested option, and the showcase ran on
  Envoy's phone. You sign in to each app once on the phone Envoy uses.

## Run it

You need a Mac (built on Apple silicon, macOS 26), the Android SDK and emulator, Python 3.13 with `uv`, Node, and a Meta
Model API key. It runs on SkyLark, our own test app, so it needs no personal accounts.

```bash
source scripts/env.sh                                    # JAVA_HOME, ANDROID_HOME, PATH
(cd backend && uv sync)                                  # Python 3.13 environment
cp .env.example .env                                     # then set META_API_KEY (and MCP_BEARER_TOKEN for Muse)
```

The test phone, once (on Linux use `x86_64`, as `scripts/cloud/vm-setup.sh` does):

```bash
sdkmanager --install "platform-tools" "emulator" "system-images;android-35;google_apis_playstore;arm64-v8a"
avdmanager create avd -n envoy-test -k "system-images;android-35;google_apis_playstore;arm64-v8a" -d pixel_6
(cd testapps/skylark && ./gradlew :app:assembleDebug)                                       # SkyLark
scripts/start_emulator.sh envoy-test                                                         # headless, gRPC 8554
adb -s emulator-5554 install -r testapps/skylark/app/build/outputs/apk/debug/app-debug.apk
```

Then Envoy:

```bash
uv run --project backend python scripts/demo_setup.py    # SkyLark signed out + demo memory (envoy-test up, API stopped)
(cd web && npm install && npm run build)                 # once, and after web changes
uv run --project backend python -m api                   # http://127.0.0.1:8700, MCP at /mcp; prints a sign-in link
```

Open the sign-in link it prints and ask in Chat: "Check me in for my flight". Envoy hands you SkyLark's sign-in (any
email and password, then the test SMS code `demo_setup.py` printed), then asks you to approve the check-in. Real apps
use a second emulator, `envoy-real`, made the same way with a 16 GB data partition
([`docs/phase-0-findings.md`](docs/phase-0-findings.md)).

**Connect an agent.** Make it a key in Settings › Agents, then:
- **Claude Code** (or any MCP client): `claude mcp add --transport http …`, step by step in [`docs/agents.md`](docs/agents.md).
- **The Spark agent:** `uv run --project backend python agents/meta-agent/run.py` with the key in `ENVOY_AGENT_KEY_FILE`,
  then http://127.0.0.1:8790 ([`agents/meta-agent/README.md`](agents/meta-agent/README.md)).
- **Muse:** `scripts/start_muse_test.sh` opens a public HTTPS tunnel that serves `/mcp` and nothing else; add it in Muse
  as a custom connector with `MCP_BEARER_TOKEN` ([`docs/muse-link.md`](docs/muse-link.md)).

**Your iPhone.** `scripts/serve_tailnet.sh on` serves Envoy over HTTPS on your tailnet only (restart the API after).
In the web app, Settings › Devices › "Pair your iPhone": scan the code, add the page to the Home Screen, type the
pairing code, and turn on notifications ([`docs/phase-5-results.md`](docs/phase-5-results.md)).

**Evaluate it.** Every suite starts from a known state, scores with code, and records its commit, tier and cost
([`eval/README.md`](eval/README.md)):

```bash
eval/run_final.sh                                              # every suite, one emulator at a time (about 4.5 hours)
uv run --project backend python eval/run_final.py systems      # one suite (compile runs first)
uv run --project backend python eval/run_final.py report       # eval/results/final/report.md and its charts
```

## More

- **Design:** [`docs/technical-design.md`](docs/technical-design.md) · **Agents:** [`docs/agents.md`](docs/agents.md) ·
  **Muse:** [`docs/muse-link.md`](docs/muse-link.md) · **The showcase:** [`docs/demo-showcase.md`](docs/demo-showcase.md)
  · **Cloud:** [`docs/cloud.md`](docs/cloud.md) · **Routines:** [`backend/routines/README.md`](backend/routines/README.md)
  · **A real Android phone:** [`docs/phase-6-results.md`](docs/phase-6-results.md)
- **Results by phase:** [0](docs/phase-0-findings.md) · [1](docs/phase-1-results.md) (agent loop) ·
  [2](docs/phase-2-results.md) (routines) · [3](docs/phase-3-results.md) (memory) · [4](docs/phase-4-results.md) (web
  app, approvals, MCP) · [5](docs/phase-5-results.md) (iPhone, voice, photos) · [6](docs/phase-6-results.md) (real
  phone, SAM 3.1) · [7](docs/phase-7-results.md) (evaluation) · [AndroidWorld](docs/androidworld-results.md)
- **Feedback on Meta's tools:** [`docs/meta-feedback.md`](docs/meta-feedback.md) · **Credits:**
  [`THIRD_PARTY.md`](THIRD_PARTY.md) · **License:** MIT ([`LICENSE`](LICENSE))
- **Layout:** `backend/` (Python 3.13: device layer, agent, routines, memory, models, the API and MCP server) ·
  `agents/` (the Spark agent) · `web/` (the web app, also the iPhone's Home Screen app) · `site/` (the showcase) ·
  `eval/` (task sets, runners, results) · `testapps/` (SkyLark) · `scripts/` · `android/`, `bridge-android/`,
  `relay/`, `ios/` (the on-phone banner, an optional accessibility service, a scrcpy relay, an optional iPhone app)
