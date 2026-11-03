# Envoy

**Muse has a computer. Envoy gives it a phone.**

Envoy gives a machine a new capability: it lets AI agents like Meta's Muse work real Android apps, turns a verified run,
at one tap on its task's card, into a checked routine they then call by name, and tells them what happens on the phone,
while the irreversible steps an agent starts wait for the person's yes on their iPhone.

<!-- SLOT hero GIF (from the takes: Muse on the Mac asks → Envoy's phone works the app → the iPhone yes). Add it here as
![Muse asks on the Mac, Envoy's phone posts, the person approves on the iPhone](docs/media/hero.gif) -->

![Agents call Envoy over MCP; Envoy runs every phone through one device interface; the person approves on the iPhone](docs/diagrams/architecture.png)

**From the final evaluation** (Nov 3, the `eval-final` tag, `hybrid` profile, standard tier;
[`report.md`](eval/results/final/report.md)):
- **Real apps:** on the 13 of 18 read-only workflows whose first run and replay both passed, Envoy's replay used 0 model
  calls and a median 4.88 s; the agent's first run took a median 5 calls, 19.59 s and $0.0376, and compiling each
  routine once a median $0.0455, more than that first run.
- **SkyLark (our test app), 10 tasks on 4 layouts, 3 seeds each:** Envoy's routines 120/120 on the first try at a median
  1 model call and 7.6 s, against the agent's 119/120 at 5 calls and 17.9 s.
- **Asking again (SkyLark):** requests 2–10 were 90/90 right at a median $0.0022, against $0.0869 for the first request.
- **Changed on purpose 50 times (SkyLark):** recovered 50/50, then 46/50 ran alone with no model call.

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
a poll sticker, a TikTok with a sound and a YouTube Short. None of those was within reach of Muse's connectors when we
checked (Nov 1), so today every clip means four rounds of tapping in three apps. With Envoy, the creator asks Muse on
the Mac. Envoy's phone works each app from a routine it learned from its own runs, and stops at each app's final button
until the creator says yes on their iPhone. The agent does the heavy lifting; the person keeps the keys.

<!-- SLOT measured benefit (the timed run by hand): the same clip and app features by hand vs through Envoy, as
hands-on time, elapsed time, interventions and whether every post was right, with the one-time setup kept apart from
repeat use. One trial: say so. -->

Beyond creators, the same layer is meant for anyone whose work lives in phone apps no agent can reach: a small business
that runs on its ordering and messaging apps, someone for whom tapping through apps is hard, and any agent platform that
wants a phone.

**What's new.** Agents working phone apps isn't new (Mobilerun, Gemini on Android), and SkillDroid compiles successful
runs into templates. To the best of our search, Envoy adds checks after its steps as well as before, written as code;
repairs kept as versions with a trial and a rollback; learned routines served to agents as tools of their own; and an
approval only the person can give ([`docs/technical-design.md`](docs/technical-design.md#what-is-new-honestly)).

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

**From the final evaluation.** All 10 suites ran on the `eval-final` tag (`cf78fa0`) on Nov 3, on the default `hybrid`
profile and the standard tier, for $11.68 at standard prices
([`eval/results/final/report.md`](eval/results/final/report.md)). Every suite starts from a known state and scores with
code: the app's real state, or the right answer on screen. Times and costs are medians, with the spread beside them
where the source gives one; dollars are at Meta's standard prices. AndroidWorld's runs are separate (below). Commits and
configs are in [the evidence appendix](#evidence-appendix).

### Real apps

18 read-only workflows in apps Envoy didn't build (Amazon, Starbucks, DoorDash, Gmail, Maps, YouTube…): ask a question,
check the answer; nothing ordered, posted or changed. One pass on the `envoy-real` emulator. A new input applies to 11
of the 18.

| Stage | Passed |
| --- | --- |
| The agent's first run right | 13/18 |
| Compiled into a routine | 14/18 |
| Same input, no model call | 13/18 (14 counting a repair) |
| New input, no model call | 7/11 |

Target's bot check stopped both Target workflows. DoorDash's first run failed; YouTube's search and Chrome's Wikipedia
lookup answered right but unverified (Chrome's still compiled, and its reruns passed after a repair, with 3 calls);
Amazon's new input found no price. Answers graded only by their shape were also read by a person: 3 right, 0 wrong, 8
not read yet ([`real.md`](eval/results/final/real.md)).

**The cost curve.** On the 13 workflows whose first run and same-input rerun both passed, the routine called by name
against the agent's first run:

| | Median (range) |
| --- | --- |
| The agent's first run | 5 calls (2–13), 19.59 s (8.49–52.82 s), $0.0376 ($0.0186–$0.0872) |
| Envoy's replay | 0 calls, 4.88 s (0.75–12.26 s), $0 |
| Compiling it, once (Muse Wonder) | $0.0455 ($0.0328–$0.0770) |

Asked in words instead of by name, Envoy's matcher adds one Spark call to pick the routine.

### "Make it a routine" on real apps

Run after the evaluation, on the tag, to a protocol fixed before it
([`eval/results/learn-agent-path/`](eval/results/learn-agent-path/README.md)): an agent asked each of the same 18
questions over MCP, then "Make it a routine" was pressed on each finished task, and each saved routine was shared and
called back as a tool.
- **The agent path answered 14 of 18 right.** Over MCP, `run_task` tries the routine library first, so 6 of the 18
  were answered, or tried, by routines already in it.
- **"Make it a routine" saved 8 of 18.** The rest, as the results give them: those 6 ran an existing routine, and the
  button doesn't take a routine's task; Target blocks emulators; a harness slip left a task holding the phone, so
  target_search (and Starbucks, also a library row) hit the time cap; calendar_today's answer, an empty day, couldn't be
  read back from its run's final screen, so it didn't compile; chrome_wikipedia's replay stopped at an after-check.
- **Called back as tools:** the 5 same-input calls were right with 0 model calls in Envoy's replay, and the 3 new-input
  calls were right, 2 with 0 model calls (YouTube Music's took 1).
- **Supplementary, outside the headline:** on a copy with an empty routine library, the 6 workflows the library had
  answered: the agent right 5/6, saved 5/6, new input right 3/5, all with 0 model calls in Envoy's replay. Chipotle's
  agent stopped after 25 steps; Amazon's new input read no price; Play's rating routine, given another app's name, ended
  with the Play Store not in front.

### The posting batch

Declared before the tag ([`PROTOCOL.md`](eval/results/showcase-batch/PROTOCOL.md)) and run once on it, Nov 3, on
Envoy's phone: the four posting routines (all v3), 10 attempts each, from a cold start, an open app or a saved draft,
with the test accounts. Every final button that was asked was declined, so nothing was posted. These numbers are for
this version, these workflows and inputs, one phone and one set of accounts, one afternoon
([`RESULTS.md`](eval/results/showcase-batch/RESULTS.md); every attempt in `attempts.md`).

| Workflow | Reached the final button | …with every outcome check yes | Time to the final ask, median (range) |
| --- | --- | --- | --- |
| Reel with a library song | 7/10 | 7 | 59.6 s (55.6–111.8) |
| TikTok with a library sound | 10/10 | 10 | 60.6 s (57.6–69.7) |
| Short with a library sound | 5/10 | 4 | 41.5 s (40.4–116.9) |
| Story with a poll | 10/10 | 10 (the poll checked by eye) | 32.5 s (31.4–41.5) |

- **The outcome checks stopped 5 runs before the final button,** each missing something the post would have gone out
  without. Two Reels had lost their caption: closing the keyboard with Back sometimes cancelled Instagram's caption
  edit. Three Shorts never showed their song on the editor: YouTube's sound search didn't list "Flowers", "Watermelon
  Sugar" or "Levitating" as the routine looks for them.
- **The Short works with "golden hour" and not yet with other songs.** Of its runs with another song, three stopped at
  the song check and one was finished by the agent, so its sound couldn't be checked. The likely cause, per the
  results: when the song isn't on the first screen of results, Envoy's search fallback retypes the search as "title,
  artist", with a comma, and YouTube returns nothing for it. Two more Shorts, started from a saved draft, stopped at
  YouTube's "Continue your draft video?" prompt.
- **The Reel's third miss:** Instagram's music search didn't show "Levitating", which the library check had found
  earlier, and the agent stopped at its step limit.
- **Model calls in Envoy's replay:** 95 over the 40 attempts, $1.0342. TikTok reads its drawn sound list by vision on
  every run, by design.

**After the batch, not part of it:** `instagram_reel_song` v4 (merged in `0d28e5a`) ends the caption edit with
Instagram's OK instead of Back, and types the caption again if it's empty before Share. On Envoy's phone, on a test
copy with every Share declined, 5 of 5 Reels from a cold start reached Share with clip, song and caption checked, at 0
model calls in Envoy's replay; TikTok 1 of 1, as a check that nothing else broke
([`index.json`](data/routines/instagram_reel_song/index.json), v4). The Short's song pick and draft prompt weren't
fixed.

### SkyLark (our test app)

SkyLark is an airline app we built so every run can start from a known state and be scored by the app's real state.
Every number in this table is on SkyLark, except the 14 real-app saved screens in the safety row.

| What | Result | Source |
| --- | --- | --- |
| Against simpler approaches | 10 tasks on 4 layouts, 3 seeds each (120 per system). Envoy's routines 120/120 on the first try, 1 call, 7.6 s (6.9–8.9 s by layout). The agent every time 119/120 on the first try (120/120 within 3), 5 calls, 17.9 s (17.1–19.2 s by layout). A fixed replay of the same taps 38/120 | [`systems.md`](eval/results/final/systems.md) |
| Asking again | Request 1 (the agent, then the compile): 6.0 calls, 44.5 s, $0.0869. Requests 2–10: 90/90 right at 1 call (the matcher), 7.6 s, $0.0022; each request's median 6.7–8.9 s. 84% fewer calls (1.0 against 6.4 per request) | [`repeats.md`](eval/results/final/repeats.md) |
| When the app changes | We changed SkyLark's layout on purpose, 50 times, over 5 kinds of change: recovered 50/50 (27 needed no fix, 17 a relaxed match or scroll, 2 a local repair, 4 the agent; 27 model calls in all), then 46/50 ran alone with no model call. 50 new inputs: 50/50 with no model call | [`change.md`](eval/results/final/change.md) |
| Screen sizes and Envoy's phone | SkyLark's 10 core routines on 3 new bookings each, on three emulator sizes and the Pixel 5: 30/30 on each, with no model call | [`sizes.md`](eval/results/final/sizes.md) |
| Safety | Irreversible controls on 20 saved screens (6 SkyLark, 14 real-app): 20 caught, all 20 by code rules alone; reversible controls flagged by code 0/22. 7 live runs declined at the approval: 7 held. Instructions planted on screens: the agent right in 20 of 20 runs and tried to follow them in 0; the routines 10 of 10, never. Irreversible changes without approval: 0 | [`safety.md`](eval/results/final/safety.md), [`injection.md`](eval/results/final/injection.md) |

### AndroidWorld (separate runs)

On Google's AndroidWorld benchmark (116 tasks in 20 open-source apps; seed 30, pass@1, standard tier), two runs, side
by side:

| Run | All 116 | Held-out half (58) | Mean cost per task |
| --- | --- | --- | --- |
| Oct 28, Spark profile: the agent with 13 general changes, chosen on the other half (the `androidworld` branch, `a80b976`) | 57 (49.1%) | 31 (53.4%) | $0.040 |
| Nov 3, the shipped default (`hybrid`) on `main` (`7ed4aa6`) | **74 (63.8%)** | 36 (62.1%) | $0.125 |

- **The Oct 28 run** is the clean estimate of the 13 changes: the held-out half went from 12 to 31 of 58 against the
  agent before them. They have been part of Envoy since Oct 29.
- **The Nov 3 run** is Envoy as it ships, with agent steps on Muse Wonder. Against Oct 28 it gained 20 tasks and lost 3
  overall, but on the held-out half alone the change (+8 −3, p = 0.23) is within run-to-run noise. It isn't a model-only
  comparison: `main` also has other agent changes since Oct 28 and a higher per-task cost cap. The held-out half had
  already been run on Oct 28 and 29 and helped choose `hybrid` as the default, so it's less clean than it was. Each task
  cost about 3.1 times as much
  ([`eval/results/androidworld/2026-11-03-hybrid-7ed4aa6/`](eval/results/androidworld/2026-11-03-hybrid-7ed4aa6/README.md)).
- **Routines, by cost (Oct 28, Spark profile):** the 22 of 59 routines Envoy compiled from its solved runs that redid
  their own seed-30 task did 55 of 69 new-seed instances at a median 1 model call, $0.0021 and 8.3 s; the full agent
  did 63 at 6 calls, $0.0122 and 19.0 s. Pairing each routine miss with the agent's own run on that instance gives 67
  of 69 (computed, not run) ([`docs/androidworld-results.md`](docs/androidworld-results.md)).

## Limits, said plainly

- **Learn a task once, not an app.** In the final evaluation, real-app routines answered a new input with no model call
  in 7 of 11 workflows; on SkyLark (our test app), 50 of 50. Amazon's new input still finds no price. When a step fails,
  the routine repairs that step and keeps the fix as a new version on trial, so a workflow can pass "after a repair".
- **Outcome checks are new, and narrow.** The first TikTok passed every check up to the Post button and went out without
  its sound; only its done-check, after posting, failed. Since Nov 2, before a posting routine's final step, code checks
  that the song shows on the editor, the caption is in its field and the clip is the one Envoy pushed, and stops the run
  otherwise, before any approval is asked. On Envoy's phone a wrong newest clip stopped the TikTok routine before its
  first step, and the Reel, TikTok and Short then reached their final buttons with all three checked
  ([`runs.md`](eval/results/showcase/runs/runs.md), Nov 2 19:27–20:35;
  [`test_outcome_checks.py`](backend/tests/test_outcome_checks.py)). The checks cover the posting routines' song,
  caption and clip, nothing else, and live in code, not in the routines.
  In the posting batch they stopped 5 runs before the final button.
- **The Short only works with some songs.** In the posting batch it reached Upload Short 5 times in 10: songs other
  than "golden hour" stopped at the song check or needed the agent, and runs from a saved draft stopped at YouTube's
  draft prompt. Neither is fixed.
- **The Story routine fails while a Story is already live:** its first tap opens the live Story's poll results.
- **Envoy doesn't make a routine on its own:** the person presses "Make it a routine" on a finished task, or teaches it,
  and the compiler can refuse a run. The button is new (Nov 2) and was measured once, after the evaluation: it saved 8
  of 18 real-app runs. The routines in the evaluation were compiled by the evaluation itself, and the showcase's by a
  script.
- **Teach mode** doesn't yet learn keypad entry reliably, or apps that reopen on their last screen.
- **No TikTok notifications:** TikTok sent none for any comment in testing.
- **Muse hears about phone events when it next checks** `phone_updates` (its scheduled task checked about every 10
  minutes). Envoy's own push to your iPhone is immediate.

## Setup today, the path to a product, and the platform question

Today Envoy runs on a Mac, with its own Android phone (Envoy's phone over USB, or an emulator) running the apps, and the
person's iPhone as where they approve. You sign in to each app once on the phone Envoy uses. The path from here is a
cloud phone per person, with MCP as the door for any agent; one cloud emulator was tested (SkyLark's routines and one
learn-then-replay loop, Oct 29: [`docs/cloud.md`](docs/cloud.md)). This is a hackathon build, not a product. The
showcase posted only to test accounts, the real-app passes are read-only, and every post waits for a person's yes. Some
apps push back: Target's bot check stops Envoy on emulators, banking apps are known to refuse them (we haven't tried
one), and automating an app may break its terms. Envoy drives the phone from the Mac, and Google Play forbids publishing
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
- **Any MCP client,** such as Claude Code: `claude mcp add --transport http …`, step by step in
  [`docs/agents.md`](docs/agents.md).
- **The Spark agent:** `uv run --project backend python agents/meta-agent/run.py` with the key in
  `ENVOY_AGENT_KEY_FILE`, then http://127.0.0.1:8790 ([`agents/meta-agent/README.md`](agents/meta-agent/README.md)).
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
  **Muse:** [`docs/muse-link.md`](docs/muse-link.md) · **The showcase:**
  [`docs/demo-showcase.md`](docs/demo-showcase.md) · **Cloud:** [`docs/cloud.md`](docs/cloud.md) · **Routines:**
  [`backend/routines/README.md`](backend/routines/README.md) · **A real Android phone:**
  [`docs/phase-6-results.md`](docs/phase-6-results.md)
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
| The final evaluation, suites 0–7 | 10 suites on Nov 3, `hybrid`, standard tier, $11.68 at standard prices; nothing uncommitted in any suite (`meta.code.dirty` empty). Runs: compile `1103001513`, systems `1103002528`, repeats `1103020715`, change `1103022306`, real `1103034419`, memory `1103031455`, safety `1103031031`, injection `1103025813`, interfaces `1103032630`, sizes `1103114754` (its phone step rerun with the Pixel upright) | `eval-final` = `cf78fa0` | [`report.md`](eval/results/final/report.md) and each suite's `.md` / `.json` beside it |
| The real-app cost curve, and the top real-app number | medians (range) over the 13 workflows whose first run and same-input rerun both passed; the routine is called by name, so no matcher call; compile cost is Muse Wonder's, once per routine | `cf78fa0` | computed from [`real.json`](eval/results/final/real.json) (`agent`, `routine_runs` "same input", `compile.cost_usd`) |
| "0 irreversible changes without approval" | on SkyLark: 7 declined live runs (suite 6) and 30 runs with planted instructions (suite 6b); the 20 irreversible controls are on saved screens, 6 SkyLark and 14 real-app | `cf78fa0` | `report.md`, "The design's success targets" |
| "Make it a routine" on real apps | the 18 real-app questions over MCP on a copy at the tag, then the button on each finished task, then each saved routine shared and called; the supplementary pass on a second copy with an empty routine library, outside the headline; deviations listed in its README | `cf78fa0` (harness `75b2c05`, `d259f3b`, `2f918da`) | [`learn-agent-path/`](eval/results/learn-agent-path/README.md), its `PROTOCOL.md`, `results.json`, `supplementary.json` |
| AndroidWorld (a separate run) | 116 tasks, seed 30, pass@1, Spark profile at low effort, Oct 28–29; routines on 3 new seeds of their 23 tasks | baseline and `a80b976` (the 13 changes); seeds `e9594f0`, `b82e512`, `cdd130e`; merged in `105d04e` | [`docs/androidworld-results.md`](docs/androidworld-results.md) |
| AndroidWorld, the shipped default | all 116 tasks, seed 30, pass@1, standard tier, `hybrid`, a $0.50 per-task cap; one run, Nov 3; $14.54 in all | `main` `7ed4aa6` | [`2026-11-03-hybrid-7ed4aa6/`](eval/results/androidworld/2026-11-03-hybrid-7ed4aa6/README.md) (`run.json`, `comparison-final-standard.json`) |
| The live posts | Nov 1–2 (ET), Envoy's phone, test accounts; 0 / 0 / 3 / 0 model calls in Envoy's replay for the Reel, Story, TikTok re-post and Short | tasks `task-1102-005928-4182`, `-013244-b7c8`, `-023044-d081`, `-015325-106a` | [`docs/demo-showcase.md`](docs/demo-showcase.md); versions and hand edits in each `data/routines/<name>/index.json` |
| Muse's dry run | Nov 2, Muse for Mac, every final step declined | the task rows | [`task-rows.json`](eval/results/showcase/muse-2026-11-02/task-rows.json) |
| The Spark agent's own cost | a three-post run on a test copy, Nov 1, declined at each final button | — | [`crosspost/README.md`](agents/meta-agent/evidence/2026-11-01/crosspost/README.md), "Cost" |
| The cloud phone, 48/48 | SkyLark routines compiled on the Mac, replayed on an emulator on Google Cloud, Oct 29 | — | [`docs/cloud.md`](docs/cloud.md) |
| `cross_post` on Envoy's phone | one request, four parts, a test copy of the branch, every final button declined, Nov 2 20:57–21:37 | the branch's code, merged in `79dfb8d` | [`cross-post-pixel.json`](eval/results/agent-door/cross-post-pixel.json) and the `cross-post-pixel-*.json` beside it |
| Outcome checks on Envoy's phone | the wrong-clip stop and the clean Reel, TikTok and Short runs, Nov 2 19:27–20:35, every final button declined | merged in `373eb86` | [`runs.md`](eval/results/showcase/runs/runs.md) and each run's JSON |
| The posting batch | 40 attempts, the four posting routines at v3, 10 each, cold / open / draft, Envoy's phone, Nov 3 12:27–14:55 ET, every final button declined; declared before the tag | `eval-final` = `cf78fa0` (the API copy); driver commits in each record | [`RESULTS.md`](eval/results/showcase-batch/RESULTS.md), `attempts.md`, `attempts/` |
| `instagram_reel_song` v4, after the batch | 5 cold Reels to Share and 1 TikTok, a test copy at the fix, every final button declined, Nov 3 14:57–15:10 ET | merged in `0d28e5a` | `data/routines/instagram_reel_song/index.json` (v4's `verification`), [`test_reel_caption_fix.py`](backend/tests/test_reel_caption_fix.py) |

Earlier development passes stay in `eval/results/` (for real apps: `real_pass_2026-10-28/`, `real_rerun_2026-10-29/`,
`real_rerun_2026-10-31/`, `real_rerun_2026-11-02_wsd-baseline/` and `real-apps/loop-a/`) with their own commits and
profiles. Nothing above quotes them.
