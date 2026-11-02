# Envoy: the submission

A draft answer for each field of the hackathon's submission form (the fields are listed in `docs/phase-0-findings.md` ›
B3). Every claim points at a file in the repo.

**These numbers are from before the final evaluation.** It runs Nov 3, 17:00–22:00 ET, on the `eval-final` tag. Until
then, every number here comes from a development commit (Oct 27 – Nov 2) and is marked "measured". **TBD (Nov 3)** marks
what the final run fills in from `eval/results/final/report.md`. Use the same numbers in the README's results table
and on the site (`scripts/build_site_data.py`).

## Team name and members

Envoy. A team of one: the author named in `LICENSE`.

## Track

Indie.

## Problem statement

**Push the Frontier:** give a machine a new capability. Envoy gives agents a phone.

Agents already work the web and a growing set of connectors. The phone is still out of reach, and three things live only
there:
- **features only the apps have**, like a Reel set to a song from Instagram's music library or a Story with a poll
  sticker (`docs/demo-showcase.md`);
- **apps no connector covers**, like TikTok for Muse;
- **the notifications** that say something just happened.

Asked on Nov 1, Muse described its own limit: "On its own, Muse can't open and tap around in apps on your phone."

An agent that works an app step by step also pays for every step, every time. So Envoy is a layer agents call, not
another assistant. It **acts** in real Android apps with the person's approval, **learns** each task into a routine
that replays for almost nothing, and **watches** the phone so the agent hears what happened.

## Project description

**Muse has a computer. Envoy gives it a phone.**

Envoy is the phone layer AI agents call. Muse, Meta's assistant, is the front door: it adds Envoy as a custom MCP
connector, and so can any MCP agent. Three call it today: Muse, the Spark agent (a small agent built on Meta's Muse
Spark) and Claude Code (`docs/agents.md`). Envoy's own app on the person's iPhone is where they approve and watch.
Irreversible steps wait for their yes there, unless they set a routine to run without asking, and anything that spends
money always asks. No agent has a tool to approve (`backend/policy/approval_rules.py`).

- **Acts.** Envoy works real Android apps the way a person does: it reads the screen, taps and types. It uses "Envoy's
  phone" (a Pixel 5) or an emulator, and agents can choose which; a copy on Google Cloud was tested too. The showcase
  uses features only the apps have. One clip from the Mac became an Instagram Reel with a library song, an Instagram Story with a poll sticker,
  a YouTube Short with a sound, and a TikTok with a sound. On the night of Nov 1 all four went live on test accounts,
  each one started by the Spark agent and approved on the iPhone (`docs/demo-showcase.md`).
- **Learns.** A successful run compiles into a **routine**: Muse Wonder writes a small program with inputs, a check
  before and after every step, and targets found by what they are rather than where they were. When the app changes,
  the routine repairs only the broken step and saves the fix as a new version. The Reel, the Story and the Short
  replayed with 0 model calls, the TikTok with 3 (`prompts/showcase-report.md`). In the Starbucks app, the agent's first run took 45.6 s
  and 12 model calls; the routine compiled from it took 14.8 s and 2 calls, with the same answer (measured:
  `eval/results/real-apps/loop-a/runs.jsonl`).
- **Learned tasks become tools.** A routine the person shares becomes a tool of its own for every agent allowed to run
  tasks, such as `instagram_reel_song(song_title, song_artist, caption)`, with no restart (`prompts/agent-door-report.md`).
  Teach mode learns a routine from the person doing the task once (`backend/api/README.md`, `teach.py`).
- **Watches.** A notification on Envoy's phone can start a task or reach the agent. Each app stays off until the person
  allows it. An Instagram comment reached the iPhone 1.6 s after it landed on Envoy's phone
  (`prompts/phone-watch-report.md`). Time, email and changed-fact triggers, change alerts and habits run on the same
  scheduler, and agents read what happened through `phone_updates`.

Envoy also keeps a **memory** of what it sees in apps, email and photos, where every fact records where and when it was
seen, so it can answer from memory and notice when something changed (`backend/memory/README.md`).

## Public GitHub repository

https://github.com/sanjeevexe/envoy

- **The README** says what works, with the evidence for each claim, gives the results table, and shows how to run Envoy.
  SkyLark is our own test app, so the quickstart needs no personal accounts.
- **The showcase site** is a guided tour built only from recorded runs and committed results:
  https://sanjeevexe.github.io/envoy/

## Demo video (YouTube, 3 minutes or less)

TBD: the YouTube link, by Nov 4.

## Use of Meta products

| Product | What Envoy uses it for | Where |
| --- | --- | --- |
| Muse (Muse for Mac and the Muse app) | The front door. Envoy is a custom MCP connector: Muse runs tasks, calls learned routines as tools by name, puts files on the phone, and reads what happened (`phone_updates`, which a Muse scheduled task checked about every 10 minutes) | `docs/muse-link.md`, `docs/agents.md` |
| Muse Spark 1.3 | Matching a request to a routine, reading facts from screens, email and photos into memory, telling whether two things are the same, answering from memory, chat routing, app notes, and grounding on screens with no accessibility tree. On the `spark` profile, also the plan, the steps and repairs. Structured output on every call. The Spark agent, a second agent that calls Envoy over MCP, runs on it too | `backend/models/adapter.py` (`JOBS`), `agents/meta-agent/README.md` |
| Muse Wonder 1.0 | Compiling a run, or a person's demonstration, into a routine: the four showcase routines were each compiled from one agent run. On the default `hybrid` profile, also the plan, the steps and repairs of a task the agent hasn't seen | `backend/models/adapter.py` (`PROFILES`), `prompts/showcase-report.md` |
| SAM 3.1 | Exact boxes on drawn screens with no accessibility tree (a canvas seat map); Spark picks the box | `docs/phase-6-results.md` |
| Muse Voice Transcribe | Dictation in the web app and on the iPhone | `docs/phase-5-results.md` |
| Instagram (the Android app) | What Envoy acts in for the showcase (a Reel with a library song, a Story with a poll sticker) and watches (comment notifications) | `docs/demo-showcase.md`, `prompts/phone-watch-report.md` |

The Contributor tier (Meta may train on inputs) is used only with our own test apps, never with real apps
(`.env.example`, `META_CONTRIBUTOR_TIER`).

## Why Meta's models matter

- **Muse gets a phone, and its tool list grows as Envoy learns.** In a dry run on Nov 2, Muse for Mac copied a clip
  into Envoy's outbox, called `send_to_phone`, then called the Reel, TikTok and Short routines by name. Each reached
  its final button in about 1 min 15 s, with 0, 3 and 0 model calls, and Muse read each result back. Every final step
  was declined (`eval/results/showcase/muse-2026-11-02/task-rows.json`). On Nov 1, Muse saw a tool newly added to a test connector without reconnecting (`docs/muse-link.md` › "Nov 1–2").
- **Wonder turns a run into an API.** Each showcase routine was learned from one agent run and compiled by Muse Wonder.
  Instagram's two needed no hand edits. Shared with agents, each becomes a typed MCP tool that replays for almost
  nothing (`prompts/showcase-report.md`, `prompts/agent-door-report.md`).
- **An agent on Meta's own API calls Envoy.** The Spark agent runs on Muse Spark 1.3 through the Responses API, reaches
  Envoy only over MCP with its own key, and started the real posts. Asked to approve, it said only the user can
  (`prompts/meta-agent-report.md`, `agents/meta-agent/evidence/2026-11-01/`).
- **Structured output that always fits the action schema.** Every step comes back as an action Envoy can run, with a
  risk label that feeds the approval gate. Code rules back up the label: on 20 irreversible controls, code alone caught
  20 (measured: `eval/results/final/safety.md`; final: TBD (Nov 3)).
- **Reading the model's output order closely made the agent cheaper.** Meta's decoder writes JSON keys in alphabetical
  order, so Envoy's agent was writing its action before its reason. Envoy now names the fields in the order a person
  decides (`docs/androidworld-results.md`, fix 10b). With this and AndroidWorld's other 12 changes, on SkyLark the agent
  went 120 of 120 (`main`'s agent the same evening: 119 of 119) at a median 2 steps instead of 4, $0.0074 instead of
  $0.0090 (`eval/results/aw_merge_2026-10-28/README.md`, round 1). That A/B covers all 13 changes, not this one alone.
- **Wonder where it pays.** Wonder compiles routines and handles first runs; Spark does the cheap repeat work. In the
  model comparison on 20 AndroidWorld tasks (14 of them ones the all-Spark agent had failed), the hybrid split passed 14
  against Spark's 9, at 3.46× the cost per task
  (`eval/results/androidworld/model-comparison/2026-10-28/README.md`). Saved routines replay mostly on Spark jobs, so
  that cost lands on first runs.
- **SAM 3.1 and grounding for drawn screens.** On screens without an accessibility tree, SAM's boxes plus a Spark pick,
  with grounding as the fallback, found all 104 targets. The step model reading coordinates off its own screenshot found
  37% (`docs/meta-feedback.md`, Phase 6).

## Feedback on Meta products

The full log, kept as we went, with dates and evidence: `docs/meta-feedback.md`. The short version:

- **What worked:**
  - Structured output was schema-valid every time, and automatic prompt caching needed no setup.
  - Muse Spark at `low` took about 0.9 s and $0.001 to $0.0015 per agent step.
  - Extraction from emails and screenshots was precise (131 of 133 attributes, then 73 of 73, none wrong).
  - Voice Transcribe returned final text 74 to 296 ms after the audio ended, on a real Mac and iPhone.
  - SAM 3.1's boxes were pixel-exact.
  - In the Muse app, the connector kept the token out of chat and never tried to approve on the user's behalf.
  - Muse saw a tool newly added to a test connector live, with no reconnect (Nov 1). That's what lets a routine you
    share join Envoy's tools in Muse.
- **What would help:**
  - Document that strict JSON output writes keys alphabetically. It silently changes how a model reasons when a
    schema's order matters.
  - A way for a connector to tell Muse that a long task finished. Today Muse polls, and in the Nov 2 dry run it ended
    its turn after starting each post and waited for a tap before the next.
  - Say in the connector UI that a newly listed tool needs one more step (Muse adds it to its allowed list) before its
    first call.
  - Fewer "Allow once" prompts when adding a connector.
  - Support for MCP's current protocol version.
  - Don't let link previews fetch URLs from tool results.
  - A documented token cost for screenshots.
  - SAM output as structured data rather than special tokens.
  - Clearer docs for caching and the voice handshake.
  - Muse Wonder twice gave a repair "reason" unrelated to the screen, with a sensible action
    (`prompts/showcase-report.md`).

## Feedback on partner tech (optional)

Not used. Envoy calls Meta's Model API directly; the cloud phone test ran on Google Cloud (`docs/cloud.md`).

## Most Viral track (optional)

TBD: the user's X post link, if any.

## Publicity grant

Yes. The repo, the site and the video show only test accounts and test data: SkyLark (our own test app) and its Maya
Patel persona, a test Google account, and the Instagram, TikTok and YouTube test accounts the showcase posted to.

Before the repo went public, a sweep of the files and the full git history (Oct 31) found no keys, tokens or passwords.
Runs on the user's own accounts (ride fares) were stored as numbers only.

## Final numbers (TBD, Nov 3)

From `eval/results/final/report.md` once its "Ran on" column says `eval-final` for every suite. The measured column is
what the report shows today, on development commits.

| Suite | Measured (commit) | Final on `eval-final` |
| --- | --- | --- |
| 0. Core routines compiled and verified | 10 of 10 (`ad9a67b`) | TBD |
| 1. Three systems on SkyLark (10 tasks × 4 layouts) | Envoy routines 40/40 first try, median 1 call, 5.5 s; the agent every time 40/40, 5 calls, 10.1 s; fixed replay 14/40 (`ad9a67b`) | TBD |
| 2. First run vs later runs | request 1 median $0.051, 27.9 s; requests 2–10 90/90, median 1 call, $0.0023, 5.9 s (`5c3d716`) | TBD |
| 3. Routines under change | new inputs 50/50 with no model call; injected changes recovered 50/50, then 50/50 alone (`6c507f3`) | TBD |
| 3b. Screen sizes and Envoy's phone | envoy-test 30/30, envoy-small 30/30, envoy-large 29/30 (`5504260`); Pixel 5 30/30, 0 calls (`a9b923d`, `sizes.md`) | TBD |
| 4. Real apps (18 read-only workflows) | first run 14/18, compiled 14/18, rerun with no call 13/18, new input 4/11 (`00ec5d9`); Oct 31 rehearsal 12/18, 12/18, 9/18, 6/11 (`a594136`) | TBD |
| 5. Memory | extraction 459/468 (98%), 0 wrong; stale facts served without a warning 0/12 (`5c3d716`) | TBD |
| 6. Safety: irreversible actions | caught 20/20 (code alone 20); reversible flagged 0/22; live declines held 7/7 (`849e51a`) | TBD |
| 6b. Safety: planted instructions | agent right 20/20, followed it 0; irreversible without approval 0; injected values stored 0 (`7395743`) | TBD |
| 7. Interfaces end to end | web, approval modes, iPhone: all passed (`e18e434`) | TBD |
| AndroidWorld (116 tasks, pass@1, seed 30) | `main` 21 (18%); with the 13 changes 57 (49%); held-out half 31 of 58 against 12, re-measured on what merged 30.5 of 58 (`docs/androidworld-results.md`) | TBD if rerun; otherwise these stand |

Measured outside the evaluation (these stay as they are):

| What | Result | Source |
| --- | --- | --- |
| Real posts, night of Nov 1 | Instagram Reel with a library song, Instagram Story with a poll, YouTube Short with a sound: live, 0 model calls each. TikTok with a sound: live, 3 calls (the first post lost its song to a compiler bug, since fixed; the re-post has it) | `docs/demo-showcase.md`, `prompts/showcase-report.md` |
| Notifications, Nov 2 | Instagram comment: on the iPhone 1.6 s after it landed on Envoy's phone. YouTube: Envoy's part 3.6 s (YouTube took about 2 minutes to notify). TikTok: no notification came | `prompts/phone-watch-report.md` |
| The cloud phone, Oct 29 | Routines for SkyLark (our own test app) compiled on the Mac: 48/48 with no model calls on an emulator on Google Cloud | `docs/cloud.md` |
| A learned routine as a tool | `skylark_get_flight_gate` shared, then called over MCP: done, 0 model calls, $0 | `eval/results/agent-door/call.json` |
| Muse end to end, Nov 2 (a dry run) | `send_to_phone`, then the Reel, TikTok and Short routines called by name: each at its final button in about 1 min 15 s, 0 / 3 / 0 model calls, every final step declined | `eval/results/showcase/muse-2026-11-02/task-rows.json` |

## Built during the hackathon

- **The history:** all of Envoy is in this repo's history, from the first commit on Oct 26, the day the hackathon
  started (the empty repository layout), to the last.
- **Open source:** projects like uiautomator2, scrcpy, FastAPI, the MCP SDK, Next.js and d3-force are plumbing,
  credited with their licenses in `THIRD_PARTY.md`.
- **What Envoy builds itself:** the agent runtime; the routine compiler, executor and repair; teach mode; the memory;
  the device layer; the safety gate; the web app and the iPhone companion; and the phone layer for agents (learned
  routines as MCP tools, a key per agent, notification triggers, files back to the agent, and the Spark agent).
  `THIRD_PARTY.md` › "What Envoy builds itself" draws the line.
- **AndroidWorld** (Google, Apache-2.0) is the benchmark only. Its 116 tasks score Envoy; none of its code runs inside
  Envoy.

## Limits, said plainly

- **Learn a task once, not an app.** New inputs on real apps work about half the time (4 of 11 on Oct 28, 6 of 11 on
  Oct 31). Routines on our own test app do far better (50 of 50).
- **The Story routine fails while a Story is already live:** its first tap opens the live Story's poll results.
- **Teach mode** doesn't yet learn keypad entry reliably, or apps that reopen on their last screen.
- **TikTok** sent no phone notification for any comment in testing, so Envoy can't watch TikTok comments yet.
- **Muse hears about phone events when it next checks** `phone_updates` (a Muse scheduled task checked about every 10
  minutes). Envoy's own push to the iPhone is immediate.
- **Apps that refuse emulators** (Target's bot check, banking apps) need a real Android phone. iPhone-only users can't
  reach them.
- **Sign-in:** the person signs in to each app once on the phone Envoy uses.
- **Where it runs:** on a Mac today, with Envoy's phone over USB. The cloud phone was tested (`docs/cloud.md`), but it
  isn't the default, and the showcase ran on Envoy's phone.
- **AndroidWorld's changes:** we don't claim they help on real apps.
