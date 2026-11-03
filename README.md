# Envoy

**Muse has a computer. Envoy gives it a phone.**

Envoy gives a machine a new capability: it lets AI agents like Meta's Muse work real Android apps, turns a verified run,
at one tap on its task's card, into a checked routine they then call by name, and tells them what happens on the phone,
while the irreversible steps an agent starts wait for the person's yes on their iPhone.

<!-- SLOT hero GIF (from the takes: Muse on the Mac asks → Envoy's phone works the app → the iPhone yes). Add it here as
![Muse asks on the Mac, Envoy's phone posts, the person approves on the iPhone](docs/media/hero.gif) -->

![Agents call Envoy over MCP; Envoy runs every phone through one device interface; the person approves on the iPhone](docs/diagrams/architecture.png)

**Three numbers** (development numbers until the final evaluation on Nov 3; each is one pass, scoped in
[the evidence appendix](#evidence-appendix)):
<!-- SLOT final numbers: replace all three from eval/results/final/report.md after `eval/run_final.py report` (Nov 3). 1 is
suite 4's real.json (medians over the workflows whose first run and same-input rerun both passed); 2 is suite 3; 3 is the
"Irreversible actions taken without approval" target row. -->
- **Real apps, the 12 of 18 read-only workflows whose first run and replay both passed:** Envoy's replay used 0 model
  calls and a median 5.40 s; the agent's first run took a median 5 calls, 19.36 s and $0.0368, and compiling each routine
  once a median $0.0415, more than that first run (Nov 2, `hybrid` profile, standard tier).
- **SkyLark (our test app), changed on purpose 50 times:** 50 recovered (25 needed no fix), then 50 of 50 ran with no
  model call (Spark profile, standard tier).
- **Irreversible actions without approval: 0,** over 7 declined live runs and 30 runs with planted instructions on
  SkyLark (our test app; Spark profile, standard tier).

> **Meta models: who does what.** Wonder turns task experience into reusable routines; Spark handles matching and
> extraction; SAM helps locate drawn controls when the accessibility tree is missing. Muse is the front door, and the
> tool list an agent sees grows as Envoy learns: a routine shared with agents is a tool of its own at the agent's next
> `tools/list`, with no restart. On the default `hybrid` profile, Wonder also plans and takes the agent's steps on a task
> Envoy hasn't learned yet ([`backend/models/adapter.py`](backend/models/adapter.py)).

- **Showcase site:** https://sanjeevexe.github.io/envoy/ (a guided tour built only from recorded runs and results)
- **Demo video (3 minutes):** TBD, the YouTube link goes here on Nov 4
- **The write-up:** [`docs/submission.md`](docs/submission.md)

Built solo for the Meta Global AI Developer Hackathon (indie track; submissions close Nov 4, 2026), from the first
commit on Oct 26 (the repository layout and the design plan, no code yet) to the last. Open-source projects are
plumbing, credited in [`THIRD_PARTY.md`](THIRD_PARTY.md), which also says what Envoy builds itself.

## Who it's for

A creator finishes a clip and wants it out as an Instagram Reel with a song from Instagram's music library, a Story with
a poll sticker, a TikTok with a sound and a YouTube Short. None of those was within reach of Muse's connectors when we checked (Nov 1), so today every clip means four rounds of tapping in three apps. With Envoy, the creator asks Muse on the Mac. Envoy's phone works each
app from a routine it learned from its own runs, and stops at each app's final button until the creator says yes on
their iPhone. The agent does the heavy lifting; the person keeps the keys.

<!-- SLOT measured benefit (the timed run by hand): the same clip and app features by hand vs through Envoy, as
hands-on time, elapsed time, interventions and whether every post was right, with the one-time setup kept apart from
repeat use. One trial: say so. -->

Beyond creators, the same layer is meant for anyone whose work lives in phone apps no agent can reach: a small business
that runs on its ordering and messaging apps, someone for whom tapping through apps is hard, and any agent platform that
wants a phone.

**What's new.** Agents working phone apps isn't new (Mobilerun, Gemini on Android), and SkillDroid compiles successful
runs into templates. To the best of our search, Envoy adds checks after its steps as well as before, written as code; repairs kept as versions with a trial and a
rollback; learned routines served to agents as tools of their own; and an approval only the person can give
([`docs/technical-design.md`](docs/technical-design.md#what-is-new-honestly)).

## What works today

| | What | Evidence |
| --- | --- | --- |
| **Agents call it** | MCP at `/mcp` (Streamable HTTP), 13 built-in tools: run a task or a routine, post to several apps in one request, search memory, send a file to the phone, get files back, propose a trigger, list phones, read phone updates… Muse for Mac and the Muse app add it as a custom connector | [`backend/mcp_server/README.md`](backend/mcp_server/README.md), [`docs/muse-link.md`](docs/muse-link.md) |
| **Any MCP agent** | Muse; the Spark agent, a small agent on Meta's Muse Spark that reaches Envoy only over MCP; and any MCP client (Claude Code tested). Each has its own key and tool groups; every task says which agent asked | [`docs/agents.md`](docs/agents.md), [`agents/meta-agent/evidence/2026-11-01/`](agents/meta-agent/evidence/2026-11-01/) |
| **Learned tasks become tools** | Share a routine in Settings › Agents (off by default) and it appears in agents' tool lists under its own name, with typed inputs, no restart. In a Nov 2 dry run, Muse called the Reel, TikTok and Short routines by name; each reached its final button and was declined, and the two tries at the poll Story failed. Nothing was posted | [`eval/results/agent-door/`](eval/results/agent-door/) (`tools-before.json`, `tools-after.json`, `call.json`), [`eval/results/showcase/muse-2026-11-02/task-rows.json`](eval/results/showcase/muse-2026-11-02/task-rows.json) |
| **App-only posts** | One clip from the Mac → an Instagram Reel with a library song, a Story with a poll sticker, a TikTok with a sound and a YouTube Short with a sound. All four went live on test accounts on the night of Nov 1, each started by the Spark agent and approved on the iPhone: the Reel, Story and Short with 0 model calls in Envoy's replay, the TikTok with 3. The agent that calls pays for its own turns: in a declined dry run on a test copy (Nov 1), the Spark agent used 11 model calls ($0.044) to drive three posts. Which routines were tuned by hand is in [the write-up](docs/submission.md#hand-edits-stated-exactly) | [`docs/demo-showcase.md`](docs/demo-showcase.md), [`data/routines/`](data/routines/) (each `index.json`), [`agents/meta-agent/evidence/2026-11-01/crosspost/`](agents/meta-agent/evidence/2026-11-01/crosspost/README.md) |
| **One request, every post** | `cross_post` runs the shared posting routines as one task with a part per destination, one after another. Each part ends done, failed, declined, waiting, outcome unknown (the post tap went through before its check) or not started, and a retry runs only the parts that didn't post; an outcome-unknown part is never posted again by itself. On Envoy's phone (Nov 2, a test copy, every final button declined): one request started four parts and returned in 0.26 s; three reached their final button and were declined, a YouTube search part finished, and a retry re-ran only those three | [`eval/results/agent-door/cross-post-pixel.json`](eval/results/agent-door/cross-post-pixel.json), [`backend/tests/test_crosspost.py`](backend/tests/test_crosspost.py) |
| **Watches** | A notification on Envoy's phone can start a task or reach the agent; each app is off until you allow it, and codes are hidden before anything is stored. An Instagram comment reached the iPhone 1.57 s after it landed on Envoy's phone. Plus time, email and changed-fact triggers, change alerts, and habits | [`docs/demo-showcase.md`](docs/demo-showcase.md), [`eval/results/alerts/`](eval/results/alerts/alerts.md), [`eval/results/recurring/`](eval/results/recurring/recurring.md) |
| **Learns** | In Envoy, a finished agent task's card has a "Make it a routine" button: Envoy compiles that run, replays it once strictly on the same phone, and saves it with the share off. Teach mode compiles what a person shows the same way, and the compiler can refuse a run. A routine has checks before and after its steps, targets found by what they are, a local repair when the app changes (the agent finishes if that fails), versions with a trial and a rollback | [`backend/routines/README.md`](backend/routines/README.md), [`backend/api/teach.py`](backend/api/teach.py) (`learn_task`) and its tests in [`backend/tests/test_teach.py`](backend/tests/test_teach.py), [Results](#results) |
| **Teach mode** | Do a task once through the live view; Envoy compiles it and replays it once before saving. A scripted Google Calendar lesson (7 steps) passed its verification replay, all 7 steps, with 0 model calls in Envoy's replay | [`site/data/recordings/teach.json`](site/data/recordings/teach.json), [`eval/results/teach_trials_2026-11-01/`](eval/results/teach_trials_2026-11-01/README.md) |
| **Phones** | "Envoy's phone" (a Pixel 5, Android 13, over USB) and emulators on the Mac; agents pick one with `list_phones`. A copy of Envoy on Google Cloud was tested too: routines for SkyLark (our test app) compiled on the Mac ran there 48/48 with no model calls, once the new emulator had finished its first boot (its very first pass: 9/18) | [`docs/phase-6-results.md`](docs/phase-6-results.md), [`docs/cloud.md`](docs/cloud.md) |
| **Files** | `send_to_phone` puts a Mac clip on the phone (a real phone waits for your OK); `get_file` gives the agent the final screen, the screen you approved, or a link from its own task | [`docs/muse-link.md`](docs/muse-link.md) |
| **You approve** | An irreversible step that an agent or a trigger starts waits for your yes in Envoy on the iPhone, unless you set that routine to run without asking. When you ask Envoy yourself, your request is the yes ("Always ask" in Settings changes that). Spending money always asks. No agent has an approve tool; asked to approve, Claude Code and the Spark agent each said only you can | [`backend/policy/approval_rules.py`](backend/policy/approval_rules.py), [`docs/agents.md`](docs/agents.md) |

## Results

**Development numbers, not final.** Measured Oct 27 – Nov 2 on development commits, each row with its model profile
and the standard tier. The final evaluation runs Nov 3, 17:00–22:00 ET, on the `eval-final` tag with the `hybrid`
profile; `eval/run_final.py report` then rewrites [`eval/results/final/report.md`](eval/results/final/report.md), and
its numbers replace the rows that cite it. The AndroidWorld and Starbucks numbers stay development numbers. Times and costs are
medians, with the spread beside them where the source gives one; dollars are at Meta's standard prices. Commits and configs are in
[the evidence appendix](#evidence-appendix).

### Real apps

18 read-only workflows in apps Envoy didn't build (Amazon, Starbucks, DoorDash, Gmail, Maps, YouTube…): ask a question,
check the answer; nothing ordered, posted or changed. Each row is one pass on the `envoy-real` emulator, with its profile
(Oct 28's assembled from 4 runs that day). A new input applies to 11 of the 18.

| Pass | First run right | Compiled into a routine | Same input, no model call | New input, no model call |
| --- | --- | --- | --- | --- |
| Oct 28, Spark profile (4 runs) | 14/18 | 14/18 | 13/18 (14 with a repair) | 4/11 |
| Oct 31, `hybrid` (a rehearsal) | 12/18 | 12/18 | 9/18 (9) | 6/11 |
| Nov 2, `hybrid` (a baseline) | 14/18 | 15/18 | 12/18 (14) | 8/11 |
| Nov 3, final, `hybrid` | TBD | TBD | TBD | TBD |

Target's bot check stopped both Target workflows on every pass. The passes differ in profile as well as code, so read
them as separate measurements, not a before and after.

**The cost curve.** On the workflows whose first run and same-input rerun both passed, the routine called by name
against the agent's first run:

| Pass | Workflows | The agent's first run | Envoy's replay | Compiling it, once |
| --- | --- | --- | --- | --- |
| Oct 28, Spark profile | 13 | 6 calls (2–19), 19.3 s (4.39–47.89 s), $0.0105 | 0 calls, 7.88 s (1.13–21.41 s), $0 | $0.0449 (Wonder) |
| Oct 31, `hybrid` | 9 | 4 calls (2–9), 17.87 s (5.95–28.73 s), $0.0308 | 0 calls, 6.08 s (0.72–27.43 s), $0 | $0.0476 (Wonder) |
| Nov 2, `hybrid` | 12 | 5 calls (2–13), 19.36 s (6.62–43.82 s), $0.0368 | 0 calls, 5.40 s (0.74–15.18 s), $0 | $0.0415 (Wonder) |
| Nov 3, final | TBD | TBD | TBD | TBD |

Asked in words instead of by name, Envoy's matcher adds one Spark call to pick the routine.

<!-- SLOT final: fill both "Nov 3, final" rows from eval/results/final/real.json. The cost curve uses the same rule as
above: medians and ranges over the workflows whose first run and same-input rerun both passed. -->

**The showcase batch** was declared before the final evaluation's tag: the four posting workflows (Reel, TikTok, Short, Story),
10 attempts each on the tagged code, every attempt kept and every final button declined
([`eval/results/showcase-batch/PROTOCOL.md`](eval/results/showcase-batch/PROTOCOL.md)). It runs after the evaluation.

<!-- SLOT reliability batch (run on the tag after the eval): its table goes here, reported narrowly (this version, these
workflows, these inputs, every attempt). -->

### SkyLark (our test app)

SkyLark is an airline app we built so every run can start from a known state and be scored by the app's real state.
Every number in this table is on SkyLark, except the 14 real-app saved screens in the safety row; all measured Oct 27–28
on the Spark profile, standard tier.

| What | Result | Source |
| --- | --- | --- |
| Asking again | Request 1 (the agent, then the compile): 5.5 calls, 27.9 s, $0.051. Requests 2–10: 90/90 right at 1 call (the matcher), 5.9 s, $0.0023; each request's median 5.2–6.6 s. 86% fewer calls on average (1.0 against 7.4 per request) | [`repeats.md`](eval/results/final/repeats.md) |
| Against simpler approaches | 10 tasks on 4 layouts. Envoy's routines 40/40 on the first try, 1 call, 5.5 s (4.8–6.0 s by layout). The agent every time 40/40, 5 calls, 10.1 s (9.2–12.0 s). A fixed replay of the same taps 14/40 | [`systems.md`](eval/results/final/systems.md) |
| When the app changes | We changed SkyLark's layout on purpose, 50 times, over 5 kinds of change: 50 recovered (25 needed no fix, 22 a relaxed match, 3 a local repair; 4 model calls in all), then 50/50 ran with no model call. 50 new inputs: 50/50 with no model call | [`change.md`](eval/results/final/change.md) |
| On Envoy's phone | SkyLark's 10 core routines on 3 new bookings each, on the Pixel 5: 30/30 with no model call | [`sizes.md`](eval/results/final/sizes.md) |
| Safety | Irreversible controls on 20 saved screens (6 SkyLark, 14 real-app): 20 caught, all 20 by code rules alone. 7 live runs on SkyLark declined at the approval: 7 held. Instructions planted on screens: the agent right in 20 of 20 runs and tried to follow them in 0; the routines never tried (10 runs) | [`safety.md`](eval/results/final/safety.md), [`injection.md`](eval/results/final/injection.md) |

### AndroidWorld, by cost

On Google's AndroidWorld benchmark (116 tasks in 20 open-source apps; Spark profile at low effort, standard tier, one seed, pass@1),
the 22 of 59 routines Envoy compiled from its solved runs that redid their own seed-30 task did 55 of 69 new-seed
instances at a median 1 model call, $0.0021 and
8.3 s; the full agent did 63 at 6 calls, $0.0122 and 19.0 s. Pairing each routine miss with the agent's own run on that
instance gives 67 of 69 (computed, not run). Separately, 13 general agent changes, chosen on half the tasks, took the
held-out half from 12 to 31 of 58; they have been part of Envoy since Oct 29
([`docs/androidworld-results.md`](docs/androidworld-results.md)).

## Limits, said plainly

- **Learn a task once, not an app.** New inputs on real apps passed 4 to 6 of 11 in five passes, Oct 28–31 (the Spark
  profile, then `hybrid` on Oct 31), and 8 of 11 in the Nov 2 `hybrid` baseline; on SkyLark (our test app), 50 of 50.
  A two-workflow check after two compiler fixes (Nov 2): Amazon's same input now passes with no model call, but its new
  input still finds no price; Chrome's Wikipedia lookup now learns its topic and answered a new one right, with 1 model
  call to read the year from the screen
  ([`real_rerun_2026-11-02_wsd-check/`](eval/results/real_rerun_2026-11-02_wsd-check/README.md)). When a step fails, the routine repairs that step and keeps
  the fix as a new version on trial, so a workflow can pass "after a repair".
- **A routine's first days are rough.** In an Oct 30 development loop on `envoy-real` (`hybrid`), the agent's first run
  of a Starbucks calorie question took 45.6 s and 12 model calls. Over the 26 replays of the routine compiled from it,
  the median was 66.95 s and 4 calls (14.2–148.8 s, 2–12 calls), many on an overloaded emulator. After one automatic
  repair and two hand fixes, v4's replays used 2 calls each (the matcher and the answer's extraction), but took 61–66 s
  until the emulator was cold-rebooted; on the loop's last commit, on the rebooted emulator, its 4 replays took
  14.8–15.9 s, three of them with a new drink ([`runs.jsonl`](eval/results/real-apps/loop-a/runs.jsonl),
  [`table.md`](eval/results/real-apps/table.md), [`index.json`](data/routines/starbucks_drink_calories/index.json)).
- **A replay can answer wrong.** On Nov 2, the YouTube Music routine's same-input replay read the artist from a mini
  player an earlier run had left playing, and gave a wrong answer with no model call.
- **Outcome checks are new, and narrow.** The first TikTok passed every check up to the Post button and went out without
  its sound; only its done-check, after posting, failed. Since Nov 2, before a posting routine's final step, code checks
  that the song shows on the editor, the caption is in its field and the clip is the one Envoy pushed, and stops the run
  otherwise, before any approval is asked. On Envoy's phone a wrong newest clip stopped the TikTok routine before its
  first step, and the Reel, TikTok and Short then reached their final buttons with all three checked
  ([`runs.md`](eval/results/showcase/runs/runs.md), Nov 2 19:27–20:35; [`test_outcome_checks.py`](backend/tests/test_outcome_checks.py)).
  The checks cover the posting routines' song, caption and clip, nothing else, and live in code, not in the routines.
- **The Story routine fails while a Story is already live:** its first tap opens the live Story's poll results.
- **Envoy doesn't make a routine on its own:** the person presses "Make it a routine" on a finished task, or teaches it,
  and the compiler can refuse a run. The button is new (Nov 2); the routines shown here were compiled before it, by the
  evaluation or a script.
- **Teach mode** doesn't yet learn keypad entry reliably, or apps that reopen on their last screen.
- **No TikTok notifications:** TikTok sent none for any comment in testing.
- **Muse hears about phone events when it next checks** `phone_updates` (its scheduled task checked about every 10
  minutes). Envoy's own push to your iPhone is immediate.

## Setup today, the path to a product, and the platform question

Today Envoy runs on a Mac, with its own Android phone (Envoy's phone over USB, or an emulator) running the apps, and the
person's iPhone as where they approve. You sign in to each app once on the phone Envoy uses. The path from here is a
cloud phone per person, with MCP as the door for any agent; one cloud emulator was tested (SkyLark's routines and one
learn-then-replay loop, Oct 29: [`docs/cloud.md`](docs/cloud.md)). This is a
hackathon build, not a product. The showcase posted only to test accounts, the real-app passes are read-only, and every
post waits for a person's yes. Some apps push back: Target's bot check stops Envoy on emulators, banking apps are
known to refuse them (we haven't tried one), and automating an app may break its terms. Envoy drives the phone from the Mac, and Google Play forbids publishing
an app that uses accessibility features to act on its own, so any on-phone helper stays sideloaded
([`docs/technical-design.md`](docs/technical-design.md)).

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
email and password, then the test SMS code `demo_setup.py` printed), then checks you in, because asking was your OK. To
approve it on your iPhone first, set approvals to "Always ask" in Settings, or send the same request from an agent over
MCP. Real apps
use a second emulator, `envoy-real`, made the same way with a 16 GB data partition
([`docs/phase-0-findings.md`](docs/phase-0-findings.md)).

**Connect an agent.** Make it a key in Settings › Agents, then:
- **Any MCP client,** such as Claude Code: `claude mcp add --transport http …`, step by step in [`docs/agents.md`](docs/agents.md).
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
- **Build logs:** [`prompts/`](prompts/README.md) holds the plans and reports written while building; the evidence is in
  `eval/results/` and `docs/`.
- **Layout:** `backend/` (Python 3.13: device layer, agent, routines, memory, models, the API and MCP server) ·
  `agents/` (the Spark agent) · `web/` (the web app, also the iPhone's Home Screen app) · `site/` (the showcase) ·
  `eval/` (task sets, runners, results) · `testapps/` (SkyLark) · `scripts/` · `android/`, `bridge-android/`,
  `relay/`, `ios/` (the on-phone banner, an optional accessibility service, a scrcpy relay, an optional iPhone app)

## Evidence appendix

Every number above, with its scope, configuration and commit. The profiles are in
[`backend/models/adapter.py`](backend/models/adapter.py): `hybrid` (the default since Oct 30) runs plan, step, repair
and compile on Muse Wonder 1.0 and the rest on Muse Spark 1.3; the Spark profile runs plan, step and repair on Spark
(steps at low effort) and compiles on Wonder. Every run below used the standard tier.

| Number | Scope | Commit | Evidence |
| --- | --- | --- | --- |
| Real apps, Oct 28 | 18 workflows on `envoy-real`, Spark profile; rows from 4 runs that day | `401e994`, `524b93a`, `cddf1b2`, `00ec5d9` | [`real.md`](eval/results/final/real.md), `real.json` (suite 4) |
| Real apps, Oct 31 | the same 18, `hybrid`; Gmail's two rows rerun after a missing token | `a594136` (runs `1031150937`, `1031152557`) | [`real_rerun_2026-10-31/`](eval/results/real_rerun_2026-10-31/README.md) |
| Real apps, Nov 2 | the same 18, `hybrid`: 16 run (run `1102175459`), Target's two carried over from `524b93a`; 13 shape-graded answers not yet read by a person | `192cd29` | [`real_rerun_2026-11-02_wsd-baseline/`](eval/results/real_rerun_2026-11-02_wsd-baseline/README.md) |
| Real apps, Nov 2 check | amazon and chrome_wikipedia only, `hybrid`, after two compiler fixes and a blank Chrome page before each run; its `real.md` totals mix runs, so only its README and these two rows count | `3d0df77` | [`real_rerun_2026-11-02_wsd-check/`](eval/results/real_rerun_2026-11-02_wsd-check/README.md) |
| New inputs, 4 to 6 of 11, then 8 | five passes, Oct 28–31: four on the Spark profile, then `hybrid` on Oct 31; 8 of 11 on Nov 2, `hybrid` | `00ec5d9`, `53ab459`, `736a6e4`, `059bb7f`, `a594136` | `real_rerun_2026-10-31/README.md`, "The four stages" |
| The cost curve, and the top real-app number | medians (range) over the workflows whose first run and same-input rerun both passed; the routine is called by name, so no matcher call; compile cost is Wonder's, once per routine | as the pass | computed from each pass's `real.json` (`agent`, `routine_runs` "same input", `compile.cost_usd`) |
| SkyLark suites 1, 2, 3, 3b, 6, 6b | SkyLark (our test app), Spark profile | `ad9a67b`, `5c3d716`, `6c507f3`, `5504260` (emulators) and `a9b923d` (Pixel), `849e51a`, `7395743` | [`report.md`](eval/results/final/report.md) and each suite's `.md` / `.json` |
| "0 irreversible actions without approval" | on SkyLark: 7 declined live runs (suite 6) and 30 runs with planted instructions (suite 6b); the 20 irreversible controls are on saved screens, 6 SkyLark and 14 real-app | `849e51a`, `7395743` | `report.md`, "The design's success targets" |
| Starbucks loop | every replay in the loop (26, one declined at a repair); the file doesn't record the profile, and `hybrid` was the default on those commits; v4 came after one automatic repair and two hand fixes; the fast replays followed a cold reboot of the emulator (`table.md`, the 19:25 note) | each row names its commits, `a2ecceb` … `55abacf` | [`runs.jsonl`](eval/results/real-apps/loop-a/runs.jsonl) |
| AndroidWorld | 116 tasks, seed 30, pass@1, Spark profile at low effort; routines on 3 new seeds of their 23 tasks | baseline and `a80b976` (the 13 changes); seeds `e9594f0`, `b82e512`, `cdd130e`; merged in `105d04e` | [`docs/androidworld-results.md`](docs/androidworld-results.md) |
| The live posts | Nov 1–2 (ET), Envoy's phone, test accounts; 0 / 0 / 3 / 0 model calls in Envoy's replay for the Reel, Story, TikTok re-post and Short | tasks `task-1102-005928-4182`, `-013244-b7c8`, `-023044-d081`, `-015325-106a` | [`docs/demo-showcase.md`](docs/demo-showcase.md); versions and hand edits in each `data/routines/<name>/index.json` |
| Muse's dry run | Nov 2, Muse for Mac, every final step declined | the task rows | [`task-rows.json`](eval/results/showcase/muse-2026-11-02/task-rows.json) |
| The Spark agent's own cost | a three-post run on a test copy, Nov 1, declined at each final button | — | [`crosspost/README.md`](agents/meta-agent/evidence/2026-11-01/crosspost/README.md), "Cost" |
| The cloud phone, 48/48 | SkyLark routines compiled on the Mac, replayed on an emulator on Google Cloud, Oct 29 | — | [`docs/cloud.md`](docs/cloud.md) |
| `cross_post` on Envoy's phone | one request, four parts, a test copy of the branch, every final button declined, Nov 2 20:57–21:37 | the branch's code, merged in `79dfb8d` | [`cross-post-pixel.json`](eval/results/agent-door/cross-post-pixel.json) and the `cross-post-pixel-*.json` beside it |
| Outcome checks on Envoy's phone | the wrong-clip stop and the clean Reel, TikTok and Short runs, Nov 2 19:27–20:35, every final button declined | merged in `373eb86` | [`runs.md`](eval/results/showcase/runs/runs.md) and each run's JSON |

`report.md` marks the development runs "(uncommitted changes)", and each suite's JSON lists what was uncommitted
(`meta.code.dirty`). Suites 3 and 4 flagged only routine data, and the Pixel run of 3b only build output and logs.
Suites 0, 1 and 6 ran with uncommitted code (`backend/routines/compiler.py`, `backend/models/prompts.py`,
`backend/policy/risk.py` among others), suites 2, 5 and 6b with uncommitted eval files, and suite 7 with docs. The final
run, on the `eval-final` tag, replaces them all.
