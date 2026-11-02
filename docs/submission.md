# Envoy: the submission

A draft answer for each field of the hackathon's submission form (the fields are listed in `docs/phase-0-findings.md` ›
B3). Every claim points at a file in the repo.

**These numbers are from before the final evaluation.** It runs Nov 3, 17:00–22:00 ET, on the `eval-final` tag. Until
then, every number here comes from a development commit (Oct 27 – Nov 2) and is marked "measured"; "TBD (Nov 3)" marks
what the final run fills in from `eval/results/final/report.md`. The README's results and the site use the same numbers.
Each number's scope, configuration and commit is in [Results](#results).

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

Envoy gives a machine a new capability: it lets AI agents like Meta's Muse work real Android apps, turns each task it
does into a checked routine they can call by name, and tells them what happens on the phone, while a person approves
every irreversible step on their iPhone.

Envoy is the phone layer AI agents call. Muse, Meta's assistant, is the front door: it adds Envoy as a custom MCP
connector. Any MCP agent can do the same; the Spark agent (a small agent built on Meta's Muse Spark) and Claude Code have
(`docs/agents.md`). Envoy's own app on the person's iPhone is where they approve and watch.

- **Acts.** Envoy works real Android apps the way a person does: it reads the screen, taps and types. It uses "Envoy's
  phone" (a Pixel 5) or an emulator, and agents can choose which; a copy on Google Cloud was tested too. The showcase
  uses features only the apps have: one clip from the Mac became an Instagram Reel with a library song, an Instagram
  Story with a poll sticker, a YouTube Short with a sound, and a TikTok with a sound. On the night of Nov 1 all four
  went live on test accounts, each one started by the Spark agent and approved on the iPhone (`docs/demo-showcase.md`).
- **Learns.** A successful run compiles into a **routine**: Muse Wonder writes a small program with inputs, a check
  before and after every step, and targets found by what they are rather than where they were. When the app changes,
  the routine repairs only the broken step and keeps the fix as a new version, on trial until it passes. The Reel, the
  Story and the Short went live with 0 model calls in Envoy's replay, the TikTok with 3; the agent that calls Envoy pays
  for its own turns (the Spark agent used 11 model calls, $0.044, to drive a three-post run:
  `agents/meta-agent/evidence/2026-11-01/crosspost/README.md`). On 9 read-only real-app workflows (Oct 31, measured),
  the routine replayed with 0 model calls at a median 6.08 s, against the agent's first run at a median 4 calls and
  17.87 s ([Results](#results)).
- **Learned tasks become tools.** A routine the person shares becomes a tool of its own for every agent allowed to run
  tasks, such as `instagram_reel_song(song_title, song_artist, caption)`, with no restart
  (`eval/results/agent-door/tools-before.json`, `tools-after.json`). Teach mode learns a routine from the person doing
  the task once (`eval/results/teach_trials_2026-11-01/`).
- **Watches.** A notification on Envoy's phone can start a task or reach the agent. Each app stays off until the person
  allows it. An Instagram comment reached the iPhone 1.57 s after it landed on Envoy's phone (`docs/demo-showcase.md`).
  Time, email and changed-fact triggers, change alerts and habits run on the same scheduler, and agents read what
  happened through `phone_updates`.

Envoy also keeps a **memory** of what it sees in apps, email and photos, where every fact records where and when it was
seen, so it can answer from memory and notice when something changed (`backend/memory/README.md`).

### Who it's for

A creator finishes a clip and wants it out as an Instagram Reel with a song from Instagram's music library, a Story with
a poll sticker, a TikTok with a sound and a YouTube Short. Each is a feature only the app has, so today every clip means
four rounds of tapping in three apps. With Envoy, the creator asks Muse on the Mac. Envoy's phone works each app from a
routine it learned from its own runs and stops at each final button until the creator says yes on their iPhone. The
agent does the heavy lifting; the person keeps the keys.

<!-- SLOT measured benefit (the timed run by hand): hands-on time, elapsed time, interventions and whether every post was
right, by hand vs through Envoy, with the one-time setup kept apart from repeat use. One trial: say so. -->

Beyond creators, the same layer is meant for anyone whose work lives in phone apps no agent can reach: a small business
that runs on its ordering and messaging apps, someone for whom tapping through apps is hard, and any agent platform that
wants a phone.

### What's new

Agents that operate phone apps exist: Mobilerun and Gemini on Android, among others. The closest prior work on learning
from runs is SkillDroid (April 2026), which compiles successful phone-agent runs into parameterized templates, checks the
screen before each step, and fixes stuck steps with one model call. Envoy's additions (`docs/technical-design.md` › "What
is new, honestly"):
- **Checked routines:** a check after every step as well as before, written as code.
- **Repairs that are kept:** a local repair is patched back into the routine as a new version, with a trial and a
  rollback.
- **Routines as agent tools:** a learned routine shows up in any MCP agent's tool list under its own name, with typed
  inputs, the moment the person shares it.
- **An approval no agent can give:** Envoy has no approve tool, so an irreversible step waits for the person.

### Trust

In the showcase, every post waited for the person's yes on their iPhone. An agent's request never counts as the person
asking, so an irreversible step always asks unless the person gave that routine a standing approval, and anything that
spends money always asks (`backend/policy/approval_rules.py`). The posts went only to test accounts, and the real-app
passes are read-only. With instructions planted on our test app's screens, the agent did 20 of 20 runs right and tried
to follow the text in none, and the routines never tried in 10 runs; across those 30 runs and 7 declined live runs, no
irreversible change happened without approval. Instructions planted in emails put 0 values into memory (measured:
`eval/results/final/injection.md`, `safety.md`). Each agent has its own key and tool groups, and what the tools return
is content, never instructions.

### Setup today, the path to a product, and the platform question

Today Envoy runs on a Mac, with its own Android phone (Envoy's phone over USB, or an emulator) running the apps, and the
person's iPhone as where they approve. The person signs in to each app once on the phone Envoy uses. The path from here
is a cloud phone per person, which is tested (`docs/cloud.md`), with MCP as the door for any agent. This is a hackathon
build, not a product. Some apps push back: Target's bot check stops Envoy on emulators, banking apps refuse them, and
automating an app may break its terms. Envoy drives the phone from the Mac, and Google Play forbids publishing an app
that uses accessibility features to act on its own, so any on-phone helper stays sideloaded (`docs/technical-design.md`).

### Hand edits, stated exactly

Each showcase routine was compiled by Muse Wonder from one agent run. Its versions, and every change made to it by hand
or by Envoy, are listed in `data/routines/<name>/index.json`.

| Routine (active version) | By hand | Since |
| --- | --- | --- |
| `instagram_reel_song` (v3) | none to its steps | recompiled once after a compiler fix, from the same run; after the live post, Envoy repaired two after-checks on its own, and that version passed its trial in Muse's dry run (0 calls, declined at Share) |
| `instagram_story_poll` (v3) | none | recompiled twice after compiler fixes, from the same run |
| `tiktok_post_sound` (v3) | a 3 s wait before tapping TikTok's drawn sound list; the app's name corrected (the source run predates TikTok in Envoy's app list); the launch step's before-checks dropped | recompiled after compiler fixes, from the same run, with those edits re-applied: it now checks that the editor names the sound |
| `youtube_short_sound` (v3) | one before-check dropped (a "Captions unavailable" label from a video playing when the run was recorded) | recompiled once after a compiler fix, from the same run; after the live post, Envoy repaired one after-check on its own, and that version passed its trial in Muse's dry run (0 calls, declined at Upload Short) |

## Public GitHub repository

https://github.com/sanjeevexe/envoy

- **The README** opens with what Envoy does, three numbers and the architecture, then says what works with the evidence
  for each claim, gives the results, and shows how to run Envoy. SkyLark is our own test app, so the quickstart needs no
  personal accounts.
- **The showcase site** is a guided tour built only from recorded runs and committed results:
  https://sanjeevexe.github.io/envoy/

## Demo video (YouTube, 3 minutes or less)

TBD: the YouTube link, by Nov 4.

## Use of Meta products

| Product | What Envoy uses it for | Where |
| --- | --- | --- |
| Muse (Muse for Mac and the Muse app) | The front door. Envoy is a custom MCP connector: Muse runs tasks, calls learned routines as tools by name, puts files on the phone, and reads what happened (`phone_updates`, which a Muse scheduled task checked about every 10 minutes) | `docs/muse-link.md`, `docs/agents.md` |
| Muse Spark 1.3 | Matching a request to a routine, reading facts from screens, email and photos into memory, telling whether two things are the same, answering from memory, chat routing, app notes, and grounding on screens with no accessibility tree. On the `spark` profile, also the plan, the steps and repairs. Structured output on every call. The Spark agent, a second agent that calls Envoy over MCP, runs on it too | `backend/models/adapter.py` (`JOBS`), `agents/meta-agent/README.md` |
| Muse Wonder 1.0 | Compiling a run, or a person's demonstration, into a routine: the four showcase routines were each compiled from one agent run. On the default `hybrid` profile, also the plan, the steps and repairs of a task Envoy hasn't learned yet | `backend/models/adapter.py` (`PROFILES`), `data/routines/*/index.json` |
| SAM 3.1 | Boxes on drawn screens with no accessibility tree (a canvas seat map); Spark picks the box | `docs/phase-6-results.md` |
| Muse Voice Transcribe | Dictation in the web app and on the iPhone | `docs/phase-5-results.md` |
| Instagram (the Android app) | What Envoy acts in for the showcase (a Reel with a library song, a Story with a poll sticker) and watches (comment notifications) | `docs/demo-showcase.md` |

The Contributor tier (Meta may train on inputs) is used only with our own test apps, never with real apps
(`.env.example`, `META_CONTRIBUTOR_TIER`). Every timed comparison here ran on the standard tier.

## Why Meta's models matter

**Wonder turns task experience into reusable routines; Spark handles matching and extraction; SAM helps locate drawn
controls when the accessibility tree is missing.**

- **Muse gets a phone, and an agent's tool list grows as Envoy learns.** In a dry run on Nov 2, Muse for Mac copied a
  clip into Envoy's outbox, called `send_to_phone`, then called the Reel, TikTok and Short routines by name. Each reached
  its final button in about 1 min 15 s, with 0, 3 and 0 model calls in Envoy's replay, and Muse read each result back.
  Every final step was declined (`eval/results/showcase/muse-2026-11-02/task-rows.json`). On Nov 1, Muse saw a tool
  newly added to a test connector without reconnecting (`docs/muse-link.md` › "Nov 1–2").
- **Wonder turns a run into an API.** Each showcase routine was compiled by Muse Wonder from one agent run; Instagram's
  two needed no hand edits to their steps ([above](#hand-edits-stated-exactly)). Shared with agents, each becomes a typed
  MCP tool. On the default `hybrid` profile Wonder also plans and takes the agent's steps on a first run. Compiling is
  paid once: on 9 real-app workflows, a median $0.0476 to compile against $0.0308 for the first run itself; after that,
  Envoy's replay used 0 model calls (measured Oct 31).
- **An agent on Meta's own API calls Envoy.** The Spark agent runs on Muse Spark 1.3 through the Responses API, reaches
  Envoy only over MCP with its own key, and started the real posts. Asked to approve, it said only the person can
  (`agents/meta-agent/evidence/2026-11-01/`).
- **Structured output that always fits the action schema.** Every step comes back as an action Envoy can run, with a
  risk label that feeds the approval gate. Code rules back up the label: on 20 irreversible controls, code alone caught
  20 (measured: `eval/results/final/safety.md`; final: TBD (Nov 3)).
- **Reading the model's output order closely made the agent cheaper.** Meta's decoder writes JSON keys in alphabetical
  order, so Envoy's agent was writing its action before its reason. Envoy now names the fields in the order a person
  decides (`docs/androidworld-results.md`, fix 10b). With this and AndroidWorld's other 12 changes, on SkyLark the agent
  went 120 of 120 (without the changes, the same evening: 119 of 119) at a median 2 steps instead of 4, $0.0074 instead
  of $0.0090 (`eval/results/aw_merge_2026-10-28/README.md`, round 1). That A/B covers all 13 changes, not this one alone.
- **Wonder where it pays.** In the model comparison on 20 AndroidWorld tasks (14 of them ones the all-Spark agent had
  failed), the hybrid split passed 14 against Spark's 9, at 3.46× the cost per task
  (`eval/results/androidworld/model-comparison/2026-10-28/README.md`). Saved routines replay on Spark jobs or none, so
  that cost lands on first runs.
- **SAM 3.1 and grounding for drawn screens.** On screens without an accessibility tree, SAM's boxes plus a Spark pick,
  with grounding where SAM's boxes missed, found 52 of 52 targets in each of two samples; grounding alone found 92% and
  49 of 52. 16 of each 52 are seats on our own test app's canvas map; the rest are real-app targets on saved screens
  (`docs/phase-6-results.md`).

## Feedback on Meta products

The full log, kept as we went, with dates and evidence: `docs/meta-feedback.md`. The short version:

- **What worked:**
  - Structured output was schema-valid every time, and automatic prompt caching needed no setup.
  - Muse Spark at `low` took about 0.9 s and $0.001 to $0.0015 per agent step (the all-Spark profile).
  - Extraction from emails and screenshots was precise (131 of 133 attributes, then 73 of 73, none wrong).
  - Voice Transcribe returned final text 74 to 296 ms after the audio ended, on a real Mac and iPhone.
  - SAM 3.1's boxes were pixel-exact.
  - In the Muse app, the connector kept the token out of chat and never tried to approve on the person's behalf.
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

Not entered.
<!-- SLOT: if the author posts on X before submitting, the post's link goes here instead. -->

## Publicity grant

Yes. The repo, the site and the video show only test accounts and test data: SkyLark (our own test app) and its Maya
Patel persona, a test Google account, and the Instagram, TikTok and YouTube test accounts the showcase posted to.

Before the repo went public, a sweep of the files and the full git history (Oct 31) found no keys, tokens or passwords.
Runs on the author's own accounts (ride fares) were stored as numbers only.

## Results

From `eval/results/final/report.md` once its "Ran on" column says `eval-final` for every suite. The measured column is
what the report shows today, on development commits, with the commit each ran on: this table is the evidence appendix.
Configuration: the SkyLark suites and the Oct 28 real-app pass ran the agent's steps on Muse Spark 1.3 (low effort) and
compiled on Muse Wonder 1.0; the Oct 31 real-app pass and the final run use the default `hybrid` profile (Wonder plans,
steps, repairs and compiles; Spark does the rest). All on the standard tier.

| Suite | Measured (commit) | Final on `eval-final` |
| --- | --- | --- |
| 0. Core routines compiled and verified | 10 of 10 (`ad9a67b`) | TBD |
| 1. Three systems on SkyLark (10 tasks × 4 layouts) | Envoy routines 40/40 first try, median 1 call, 5.5 s; the agent every time 40/40, 5 calls, 10.1 s; fixed replay 14/40 (`ad9a67b`) | TBD |
| 2. First run vs later runs | request 1 median 5.5 calls, $0.051, 27.9 s; requests 2–10 90/90, median 1 call, $0.0023, 5.9 s (`5c3d716`) | TBD |
| 3. Routines under change | new inputs 50/50 with no model call; injected changes recovered 50/50, then 50/50 alone (`6c507f3`) | TBD |
| 3b. Screen sizes and Envoy's phone | envoy-test 30/30, envoy-small 30/30, envoy-large 29/30 (`5504260`); Pixel 5 30/30, 0 calls (`a9b923d`, `sizes.md`) | TBD |
| 4. Real apps (18 read-only workflows) | Oct 28, agent on Spark (rows from 4 runs; last `00ec5d9`): first run 14/18, compiled 14/18, rerun with no call 13/18, new input 4/11. Oct 31, `hybrid` (`a594136`): 12/18, 12/18, 9/18, 6/11 | TBD |
| 4. Real apps: the cost curve | Oct 31, `hybrid`, the 9 workflows whose first run and rerun both passed: the agent's first run median 4 calls (2–9), 17.87 s, $0.0308; Envoy's replay 0 calls, 6.08 s (0.72–27.43 s); compile $0.0476 once | TBD |
| 5. Memory | extraction 459/468 (98%), 0 wrong; stale facts served without a warning 0/12 (`5c3d716`) | TBD |
| 6. Safety: irreversible actions | caught 20/20 (code alone 20); reversible flagged 0/22; live declines held 7/7 (`849e51a`) | TBD |
| 6b. Safety: planted instructions | agent right 20/20, followed it 0; irreversible without approval 0; injected values stored 0 (`7395743`) | TBD |
| 7. Interfaces end to end | web, approval modes, iPhone: all passed (`e18e434`) | TBD |
| AndroidWorld (116 tasks, pass@1, seed 30, agent on Spark) | before the 13 changes 21 (18%); with them 57 (49%); held-out half 31 of 58 against 12, re-measured on what merged 30.5 of 58. Routines on 3 new seeds: 55 of 69 at a median 1 call and $0.0021, against the agent's 63 at 6 calls and $0.0122 (`docs/androidworld-results.md`) | these stand unless rerun |

The real-app cost curve is computed from each pass's `real.json`: medians (and ranges) over the workflows whose first
run and same-input rerun both passed. The routine is called by name, so no matcher call is counted; asked in words, the
matcher adds one Spark call. `report.md` marks the development runs "(uncommitted changes)": a false flag from a bug,
fixed Oct 31, that counted routine data as code (`eval/results/real_rerun_2026-10-31/README.md`).

<!-- SLOT reliability batch: the pre-registered runs of the showcase workflows on the tag (after the eval), reported
narrowly: this version, these workflows, these inputs, every attempt and every intervention. -->

<!-- SLOT cold start: the routine that didn't exist, its first run and compile (timed), the share, Muse listing the new
tool, a second input someone else picked, and the checked answer. -->

Measured outside the evaluation (these stay as they are):

| What | Result | Source |
| --- | --- | --- |
| Real posts, night of Nov 1 | Instagram Reel with a library song, Instagram Story with a poll, YouTube Short with a sound: live, 0 model calls each in Envoy's replay. TikTok with a sound: live, 3 calls (the first post lost its song to a compiler bug, since fixed; the re-post has it) | `docs/demo-showcase.md`; tasks `task-1102-005928-4182`, `task-1102-013244-b7c8`, `task-1102-015325-106a`, `task-1102-023044-d081` |
| The calling agent's cost | The Spark agent: 11 model calls, $0.044, to drive a three-post run on a test copy (Nov 1, declined at each final button) | `agents/meta-agent/evidence/2026-11-01/crosspost/README.md` |
| Notifications, Nov 2 | Instagram comment: on the iPhone 1.57 s after it landed on Envoy's phone. YouTube: Envoy's part 3.6 s (YouTube took about 2 minutes to notify). TikTok: no notification came | `docs/demo-showcase.md` |
| The cloud phone, Oct 29 | Routines for SkyLark (our own test app) compiled on the Mac: 48/48 with no model calls on an emulator on Google Cloud | `docs/cloud.md` |
| A learned routine as a tool | `skylark_get_flight_gate` shared, then called over MCP: done, 0 model calls in Envoy's replay, $0 | `eval/results/agent-door/call.json` |
| Muse end to end, Nov 2 (a dry run) | `send_to_phone`, then the Reel, TikTok and Short routines called by name: each at its final button in about 1 min 15 s, 0 / 3 / 0 model calls in Envoy's replay, every final step declined | `eval/results/showcase/muse-2026-11-02/task-rows.json` |

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

- **Learn a task once, not an app.** New inputs on real apps passed 4 of 11 on Oct 28, then 5, 6, 6 and 6 of 11 in the
  four passes through Oct 31 (`eval/results/real_rerun_2026-10-31/README.md`). Routines on our own test app do far
  better (50 of 50). A failed step is repaired locally and kept as a new version on trial.
- **Step checks aren't outcome checks.** The first TikTok passed every step check and went out without its sound. Its
  routine now checks that the editor names the sound, but Envoy doesn't yet check every outcome (the right clip, sound
  and caption) before the final button.
  <!-- SLOT outcome checks: if they land before the eval, say what is checked now and link the negative tests. -->
- **The Story routine fails while a Story is already live:** its first tap opens the live Story's poll results.
- **Teach mode** doesn't yet learn keypad entry reliably, or apps that reopen on their last screen.
- **TikTok** sent no phone notification for any comment in testing, so Envoy can't watch TikTok comments yet.
- **Muse hears about phone events when it next checks** `phone_updates` (a Muse scheduled task checked about every 10
  minutes). Envoy's own push to the iPhone is immediate.
- **One post per Muse turn:** in the Nov 2 dry run Muse started one post, ended its turn, and waited for a tap before
  the next.
- **Apps that refuse emulators** (Target's bot check, banking apps) need a real Android phone. iPhone-only users can't
  reach them.
- **Where it runs:** on a Mac today, with Envoy's phone over USB. The cloud phone was tested (`docs/cloud.md`), but it
  isn't the default, and the showcase ran on Envoy's phone.
- **AndroidWorld's changes:** we don't claim they help on real apps.
