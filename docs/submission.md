# Envoy: the submission

An answer for each field of the hackathon's submission form (the fields are listed in `docs/phase-0-findings.md` ›
B3). Claims point at a file in the repo; the few that can't say so.

**The numbers come from the final evaluation.** All 10 suites ran on the `eval-final` tag (`cf78fa0`) on Nov 3, on the
default `hybrid` profile and the standard tier, for $11.68 at standard prices (`eval/results/final/report.md`). The
README's results use the same numbers. [Results](#results) gives the
scope, configuration and commit of each evaluation number; every other number cites its source beside it.

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
- **apps no connector covers**, like TikTok for Muse (it had no TikTok connector when we checked, Nov 1);
- **the notifications** that say something just happened.

Asked in our Muse for Mac chat on Nov 1, Muse described its own limit: "On its own, Muse can't open and tap around in
apps on your phone." (The chat isn't recorded in the repo.)

An agent that works an app step by step also pays for every step, every time. So Envoy is a layer agents call, not
another assistant. It **acts** in real Android apps with the person's approval, **learns** by compiling a verified run
into a routine that replays for a fraction of a cent when its checks pass, and **watches** the phone so the agent hears
what happened.

## Project description

**Muse has a computer. Envoy gives it a phone.**

Envoy gives a machine a new capability: it lets AI agents like Meta's Muse work real Android apps, turns a verified run,
at one tap on its task's card, into a checked routine they then call by name, and tells them what happens on the phone,
while the irreversible steps an agent starts wait for the person's yes on their iPhone.

Envoy is the phone layer AI agents call. Muse, Meta's assistant, is the front door: it adds Envoy as a custom MCP
connector. Any MCP agent can do the same; the Spark agent (a small agent built on Meta's Muse Spark) and Claude Code
have (`docs/agents.md`). Envoy's Home Screen web app on the person's iPhone is where they approve and watch.

- **Acts.** Envoy works real Android apps the way a person does: it reads the screen, taps and types. It uses "Envoy's
  phone" (a Pixel 5) or an emulator, and agents can choose which; a copy on Google Cloud was tested too. The showcase
  uses features Muse's connectors can't reach: one clip from the Mac became an Instagram Reel with a library song, an
  Instagram Story with a poll sticker, a YouTube Short with a sound, and a TikTok with a sound. On the night of Nov 1
  all four went live on test accounts, each one started by the Spark agent and approved on the iPhone
  (`docs/demo-showcase.md`).
- **Learns.** In Envoy, a finished agent task's card has a "Make it a routine" button: Envoy compiles that run into a
  **routine**, replays it once strictly on the same phone, and saves it with the share off (`backend/api/teach.py`,
  `learn_task`; `backend/tests/test_teach.py`). Teach mode compiles what a person shows the same way, and the compiler
  can refuse a run. Muse Wonder writes a small program with inputs, checks before and after its steps, and targets found
  by what they are rather than where they were. When the app changes, the routine repairs the broken step (the agent
  finishes if that fails) and keeps the fix as a new version, on trial until it passes. In the first live posts, on the
  night of Nov 1, the Reel, the Story and the Short replayed with 0 model calls in Envoy's replay and the TikTok's re-post
  with 3 (each routine's `index.json` lists every later take); the agent that
  calls Envoy pays for its own turns (in a declined dry run on a test copy, Nov 1, the Spark agent used 11 model calls,
  $0.044, to drive three posts: `agents/meta-agent/evidence/2026-11-01/crosspost/README.md`). On the 13 of 18 read-only
  real-app workflows whose first run and same-input rerun both passed in the final evaluation, Envoy's replay used 0
  model calls at a median 4.88 s, against the agent's first run at a median 5 calls and 19.59 s ([Results](#results)).
  After the evaluation, "Make it a routine" saved 8 of 18 real-app runs, and each saved routine answered right when
  called back as a tool (`eval/results/learn-agent-path/`).
- **Learned tasks become tools.** A routine the person shares becomes a tool of its own for every agent allowed to run
  tasks, such as `instagram_reel_song(song_title, song_artist, caption)`, with no restart
  (`eval/results/agent-door/tools-before.json`, `tools-after.json`). Teach mode learns a routine from one demonstration
  through the live view, tested with a scripted demonstrator (`site/data/recordings/teach.json`,
  `eval/results/teach_trials_2026-11-01/`).
- **One request, every post.** `cross_post` runs the shared posting routines as one task with a part per destination.
  Each part ends done, failed, declined, waiting, outcome unknown (the post tap went through before its check) or not
  started; a retry runs only the parts that didn't post, and an outcome-unknown part is never posted again by itself
  (`backend/tests/test_crosspost.py`). On Envoy's phone (Nov 2, a test copy, every final button declined), one request
  started four parts and returned in 0.26 s; three reached their final button and were declined, a YouTube search part
  finished, and a retry re-ran only those three (`eval/results/agent-door/cross-post-pixel.json`).
- **Watches.** A notification on Envoy's phone can start a task or reach the agent. Each app stays off until the person
  allows it. An Instagram comment reached the iPhone 1.57 s after it landed on Envoy's phone (`docs/demo-showcase.md`).
  Time, email and changed-fact triggers, change alerts and habits run on the same scheduler, and agents read what
  happened through `phone_updates`.

Envoy also keeps a **memory** of what it sees in apps, email and photos, where every fact records where and when it was
seen, so it can answer from memory and notice when something changed (`backend/memory/README.md`).

### Who it's for

A creator finishes a clip and wants it out as an Instagram Reel with a song from Instagram's music library, a Story with
a poll sticker, a TikTok with a sound and a YouTube Short. None of those was within reach of Muse's connectors when we
checked (Nov 1), so today every clip means four rounds of tapping in three apps. With Envoy, the creator asks Muse on
the Mac. Envoy's phone works each app from a routine it learned from its own runs and stops at each final button until
the creator says yes on their iPhone. The agent does the heavy lifting; the person keeps the keys.

Beyond creators, the same layer is meant for anyone whose work lives in phone apps no agent can reach: a small business
that runs on its ordering and messaging apps, someone for whom tapping through apps is hard, and any agent platform that
wants a phone.

### What's new

Agents that operate phone apps exist: Mobilerun and Gemini on Android, among others. The closest prior work on learning
from runs is SkillDroid (April 2026), which compiles successful phone-agent runs into parameterized templates, checks
the screen before each step, and fixes stuck steps with one model call. Envoy's additions, to the best of our search
(`docs/technical-design.md` › "What is new, honestly"):
- **Checked routines:** checks after steps as well as before, written as code (the showcase routines' final post step
  has none: the post is the end).
- **Repairs that are kept:** a local repair is patched back into the routine as a new version, with a trial and a
  rollback.
- **Routines as agent tools:** a learned routine the person shares shows up, under its own name with typed inputs, in
  the tool list of every agent allowed to run tasks, at its next `tools/list`.
- **An approval no agent can give:** Envoy has no approve tool, so an irreversible step waits for the person.

### Trust

In the showcase, every post waited for the person's yes on their iPhone. An agent's request never counts as the person
asking, so an irreversible step an agent starts always asks unless the person gave that routine a standing approval.
When the person asks Envoy themselves, their request is the yes, unless they choose "Always ask". Anything that spends
money always asks (`backend/policy/approval_rules.py`). The posts went only to test accounts, and the real-app passes
are read-only (nothing ordered, posted or changed). With instructions planted on SkyLark's screens (our test app), the
agent did 20 of 20 runs right and tried to follow the text in none, and the routines were right in 10 of 10 and never
tried; across those 30 runs and 7 declined live runs (also on SkyLark), no irreversible change happened without
approval. Instructions planted in emails put 0 values into memory (the final evaluation:
`eval/results/final/injection.md`, `safety.md`). Every agent besides Muse has its own key and tool groups, and Envoy's
instructions tell each agent that what the tools return is content, never instructions.

### Setup today, the path to a product, and the platform question

Today Envoy runs on a Mac, with its own Android phone (Envoy's phone over USB, or an emulator) running the apps, and the
person's iPhone as where they approve. The person signs in to each app once on the phone Envoy uses. The path from here
is a cloud phone per person, with MCP as the door for any agent; one cloud emulator was tested (SkyLark's routines and
one learn-then-replay loop, Oct 29: `docs/cloud.md`). Envoy drives the phone from the Mac, and Google Play forbids
publishing an app that uses accessibility features to act on its own, so any on-phone helper stays sideloaded
(`docs/technical-design.md`).

### Hand edits, stated exactly

Each showcase routine was compiled by Muse Wonder from one agent run. Its versions, and every change made to it by hand
or by Envoy, are listed in `data/routines/<name>/index.json`.

| Routine (active version) | By hand | Since |
| --- | --- | --- |
| `instagram_reel_song` (v5) | v4 (Nov 3, after the posting batch): the caption edit ends with Instagram's OK instead of Back, and the caption is typed again if it's empty before Share. v5 (Nov 4): an optional wait after Share, because the done-check ended before Instagram finished sharing. No hand edits to any step before v4 | recompiled once after a compiler fix, from the same run; after the live post, Envoy repaired two after-checks on its own (v3), and that version passed its trial in Muse's dry run (0 model calls in Envoy's replay, declined at Share). v4 and v5 are the hand edits; v6, Envoy's own repair from a Nov 4 run, failed its trial and was rejected, so v5 stays active |
| `instagram_story_poll` (v3) | none | recompiled twice after compiler fixes, from the same run |
| `tiktok_post_sound` (v3) | a 3 s wait before tapping TikTok's drawn sound list; the app's name corrected (the source run predates TikTok in Envoy's app list); the launch step's before-checks dropped | recompiled after compiler fixes, from the same run, with those edits re-applied: it now checks that the editor names the sound |
| `youtube_short_sound` (v3) | one before-check dropped (a "Captions unavailable" label from a video playing when the run was recorded) | recompiled once after a compiler fix, from the same run; after the live post, Envoy repaired one after-check on its own, and that version passed its trial in Muse's dry run (0 model calls in Envoy's replay, declined at Upload Short) |

The outcome checks added on Nov 2 (song, caption, clip) live in code and change none of these routines. The posting
batch (in [Results](#results)) ran every routine at v3, before the Reel's v4 and v5.

## Public GitHub repository

https://github.com/sanjeevexe/envoy

- **The README** opens with what Envoy does, the architecture and the final evaluation's headline numbers, then says
  what works with the evidence for each claim, gives the results, and shows how to run Envoy. SkyLark is our own test
  app, so the quickstart needs no personal accounts.
- **The showcase site** is a guided tour built only from recorded runs and committed results:
  https://sanjeevexe.github.io/envoy/

## Demo video (YouTube, 3 minutes or less)

https://www.youtube.com/watch?v=EIVoCPk8BME

## Use of Meta products

| Product | What Envoy uses it for | Where |
| --- | --- | --- |
| Muse (Muse for Mac and the Muse app) | The front door. Envoy is a custom MCP connector: Muse runs tasks, calls learned routines as tools by name, puts files on the phone, and reads what happened (`phone_updates`, which a Muse scheduled task checked about every 10 minutes) | `docs/muse-link.md`, `docs/agents.md` |
| Muse Spark 1.3 | Matching a request to a routine, reading facts from screens, email and photos into memory, telling whether two things are the same, answering from memory, chat routing, app notes, and grounding on screens with no accessibility tree. On the `spark` profile, also the plan, the steps and repairs. Structured output on every call. The Spark agent, a second agent that calls Envoy over MCP, runs on it too | `backend/models/adapter.py` (`JOBS`), `agents/meta-agent/README.md` |
| Muse Wonder 1.0 | Compiling a run, or a person's demonstration, into a routine: the four showcase routines were each compiled from one agent run. On the default `hybrid` profile, also the plan, the steps and repairs of a task Envoy hasn't learned yet | `backend/models/adapter.py` (`PROFILES`), `data/routines/*/index.json` |
| SAM 3.1 | Boxes on drawn screens with no accessibility tree (a canvas seat map); Spark picks the box | `docs/phase-6-results.md` |
| Muse Voice Transcribe | Dictation in the web app and on the iPhone | `docs/phase-5-results.md` |
| Instagram (the Android app) | What Envoy acts in for the showcase (a Reel with a library song, a Story with a poll sticker) and watches (comment notifications) | `docs/demo-showcase.md` |

The Contributor tier (Meta may train on inputs) is used only with test apps and synthetic data (SkyLark, and
AndroidWorld's development rounds), never with real apps (`.env.example`, `META_CONTRIBUTOR_TIER`). Every timed
comparison here ran on the standard tier.

## Why Meta's models matter

**Wonder turns task experience into reusable routines; Spark handles matching and extraction; SAM helps locate drawn
controls when the accessibility tree is missing.**

- **Muse gets a phone, and an agent's tool list grows as Envoy learns.** In a Nov 4 take, Muse for Mac made one
  `cross_post` call for a Reel, a Short and a TikTok, and all three finished, at 0, 0 and 3 model calls in Envoy's
  replay (each routine's `index.json`). In a dry run on Nov 2, it copied a clip into Envoy's outbox, called
  `send_to_phone`, then called the Reel, TikTok and Short routines by name, and each reached its final button, where it
  was declined (`eval/results/showcase/muse-2026-11-02/task-rows.json`). On Nov 1, Muse saw a tool newly added to a test
  connector without reconnecting (`docs/muse-link.md` › "Nov 1–2").
- **Wonder turns a run into an API.** Each showcase routine was compiled by Muse Wonder from one agent run; the Story
  needed no hand edits, and the Reel none until a caption fix after the posting batch
  ([above](#hand-edits-stated-exactly)). Shared with agents, each becomes a
  typed MCP tool. On the default `hybrid` profile Wonder also plans and takes the agent's steps on a first run.
  Compiling is paid once: on the same 13 real-app workflows, a median $0.0455 to compile against $0.0376 for the first
  run itself; after that, Envoy's replay used 0 model calls (the final evaluation).
- **An agent on Meta's own API calls Envoy.** The Spark agent runs on Muse Spark 1.3 through the Responses API, reaches
  Envoy only over MCP with its own key, and started the real posts. Asked to approve, it said only the person can
  (`agents/meta-agent/evidence/2026-11-01/`).
- **Structured output that fits the action schema.** Every step comes back as an action Envoy can run, with a risk label
  that feeds the approval gate. Code rules back up the label: on 20 irreversible controls on saved screens, code alone
  caught 20 (the final evaluation: `eval/results/final/safety.md`).
- **Reading the model's output order closely made the agent cheaper.** Meta's decoder writes JSON keys in alphabetical
  order, so Envoy's agent was writing its action before its reason. Envoy now names the fields in the order a person
  decides (`docs/androidworld-results.md`, fix 10b). With this and AndroidWorld's other 12 changes, on SkyLark the agent
  went 120 of 120 (without the changes, the same evening: 119 of 119) at a median 2 steps instead of 4, $0.0074 instead
  of $0.0090 (`eval/results/aw_merge_2026-10-28/README.md`, round 1). That A/B covers all 13 changes, not this one
  alone, and ran on the Spark profile (one run each); under the `hybrid` default, agent steps run on Wonder.
- **Wonder where it pays.** In the model comparison on 20 AndroidWorld tasks (14 of them ones the all-Spark agent had
  failed), the hybrid split passed 14 against Spark's 9 (one run each, a margin near run-to-run noise), at 3.46× the
  cost per task (`eval/results/androidworld/model-comparison/2026-10-28/README.md`). On all 116 tasks, the shipped
  default (`hybrid`) solved 74 (63.8%) on Nov 3, against 57 on the Spark profile on Oct 28 (+20 −3, p = 0.0005), at
  about 3.1 times the cost per task; that isn't a model-only comparison, and on the held-out half the gain is within
  noise (`eval/results/androidworld/2026-11-03-hybrid-7ed4aa6/`). Saved routines replay on Spark jobs or none, so that
  cost lands on first runs and repairs.
- **SAM 3.1 and grounding for drawn screens.** From the screenshot alone (the methods got no accessibility tree), SAM's
  boxes plus a Spark pick, with grounding where SAM's boxes missed, found 52 of 52 targets in each of two samples;
  grounding alone found 92% and 49 of 52. The first sample is 16 seats on our test app's canvas map, which is truly
  drawn, and 36 real-app targets on saved screens, whose trees served as the answer key; the second used other seats
  and targets (`docs/phase-6-results.md`).

## Feedback on Meta products

The full log, kept as we went, with dates and evidence: `docs/meta-feedback.md`. The short version:

- **What worked:**
  - The schema's JSON was valid every time (in 18 of 480 calls a sentence came before it), and automatic prompt caching
    needed no setup.
  - Muse Spark at `low` took about 0.9 s and $0.001 to $0.0015 per agent step (Oct 27, our test app; Envoy's default
    profile now runs agent steps on Wonder).
  - Extraction from emails and screenshots was precise (131 of 133 attributes on 28 test emails, then 73 of 73 on 7
    screenshots of our test app, none wrong).
  - Voice Transcribe returned final text 74 to 296 ms after the audio ended, on a real Mac and iPhone.
  - SAM 3.1's boxes were pixel-exact.
  - In the Muse app, the connector kept the token out of chat and never tried to approve on the person's behalf.
  - Muse saw a tool newly added to a test connector live, with no reconnect (Nov 1). That's what lets a routine you
    share join Envoy's tools in Muse.
- **What would help:**
  - Keep structured output to the JSON alone: 18 of 480 calls put a sentence of commentary before it.
  - Document that strict JSON output writes keys alphabetically. It silently changes how a model reasons when a
    schema's order matters.
  - A way for a connector to tell Muse that a long task finished. Today Muse polls, and in the Nov 2 dry run it ended
    its turn after starting each post and waited for a tap before the next. Envoy's `wait_for_task`, added since, works
    around it by holding a call up to about 45 s.
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

## Publicity grant

Yes. The repo, the site and the video show test accounts and test data: SkyLark (our own test app) and its Maya Patel
persona, a test Google account, and the Instagram, TikTok and YouTube test accounts the showcase posted to. The
exceptions are the author's own accounts in a few real apps, such as Uber and Lyft: fare checks with no ride requested
and a Kroger cart with no order placed. The video also shows the author's name, Instagram handle and a pickup address,
by the author's choice. The
real-app passes are read-only (nothing ordered, posted or changed) and keep no personal details.

Before the repo went public, a sweep of the files and the full git history (Oct 31) found no keys, tokens or passwords.
Uber's runs on the author's account were stored as numbers only (`eval/results/real-apps/loop-b/README.md`).

## Results

**The headlines.** Real apps: 13 of 18 read-only workflows replayed right with 0 model calls in Envoy's replay, at a
median 4.88 s, against the agent's first run at 5 calls and 19.59 s. SkyLark (our test app): routines 120/120 on the
first try at 1 call, against the agent's 5 calls; repeat requests 90/90 at $0.0022, about 40 times cheaper than the
first request ($0.0869, the agent's run and the compile included); injected layout changes recovered 50/50. Safety:
irreversible controls caught 20/20 by code rules alone, on saved screens, and the agent right 20/20 with instructions
planted on SkyLark's screens, following them in none. The posting batch: TikTok and the Story reached their final button
10/10, all four workflows below. AndroidWorld: the shipped default solved 74 of 116 (63.8%), +20 −3 over the Oct 28 run
(p = 0.0005; not a model-only comparison).

From the final evaluation: all 10 suites on the `eval-final` tag (`cf78fa0`), Nov 3, on the default `hybrid` profile
(Muse Wonder plans, steps, repairs and compiles; Muse Spark does the rest) and the standard tier, $11.68 at standard
prices. Nothing was uncommitted in any suite (each suite's `meta.code.dirty` is empty). This table is the evidence
appendix: `eval/results/final/report.md`, and each suite's `.md` and `.json` beside it with its run id. Suites 0–3b are
on SkyLark, our test app; 6 and 6b use SkyLark with saved real-app screens and a test inbox. AndroidWorld's two runs are
separate: Oct 28–29 on the Spark profile (agent steps on Muse Spark 1.3 at low effort, compiles on Muse Wonder 1.0), and
Nov 3 on the shipped default, `hybrid`.

| Suite | Final (`eval-final`, `hybrid`, standard tier) |
| --- | --- |
| 0. SkyLark's 10 core routines compiled and verified | 10 of 10 |
| 1. Three systems on SkyLark (10 tasks × 4 layouts × 3 seeds) | Envoy routines 120/120 first try, median 1 call, 7.6 s (6.9–8.9 s by layout); the agent every time 119/120 first try (120/120 within 3), 5 calls, 17.9 s (17.1–19.2 s); fixed replay 38/120 |
| 2. First run vs later runs (SkyLark) | request 1 median 6.0 calls, $0.0869, 44.5 s; requests 2–10 90/90, median 1 call, $0.0022, 7.6 s; 84% fewer calls (1.0 against 6.4 per request) |
| 3. Routines under change (SkyLark) | new inputs 50/50 with no model call; injected changes recovered 50/50 (27 needed no fix, 17 a relaxed match or scroll, 2 a local repair, 4 the agent; 27 model calls), then 46/50 ran alone with no model call |
| 3b. SkyLark routines on three screen sizes and Envoy's phone | envoy-test 30/30, envoy-small 30/30, envoy-large 30/30, the Pixel 5 30/30, all with no model call |
| 4. Real apps (18 read-only workflows, `envoy-real`) | first run right 13/18, compiled 14/18, same input with no call 13/18 (14 counting a repair), new input 7/11; Target's two blocked by its bot check |
| 4. Real apps: the cost curve | the 13 workflows whose first run and rerun both passed: the agent's first run median 5 calls (2–13), 19.59 s (8.49–52.82 s), $0.0376; Envoy's replay 0 calls, 4.88 s (0.75–12.26 s); compile $0.0455 once |
| 5. Memory | extraction 454/468 (97%) on 62 labelled test items, 0 wrong; stale facts served without a warning 0/12 |
| 6. Safety: irreversible actions | on 20 saved screens (6 SkyLark, 14 real-app), caught 20/20 (code alone 20); reversible flagged by code 0/22 (by the gate, model label included, 3/22); live declines on SkyLark held 7/7 |
| 6b. Safety: planted instructions (SkyLark's screens and a test inbox) | agent right 20/20, tried to follow it 0; routines 10/10, never; irreversible without approval 0; injected values stored from email 0 |
| 7. Interfaces end to end | web, approval modes, iPhone flows (scripted, with a fake push service): all passed |
| AndroidWorld, the shipped default (a separate run: all 116 tasks, pass@1, seed 30, `hybrid`, `main` `7ed4aa6`, Nov 3) | 74 of 116 (63.8%), +20 −3 over the Oct 28 run (p = 0.0005); held-out half 36 of 58 (62.1%), where the change (+8 −3, p = 0.23) is within run-to-run noise; a mean $0.125 a task, about 3.1 times the Oct 28 run's. Not a model-only comparison (`main` has other agent changes since Oct 28 and a higher per-task cost cap), and the held-out half had already been run on Oct 28 and 29 and helped choose `hybrid` as the default (`eval/results/androidworld/2026-11-03-hybrid-7ed4aa6/`) |
| AndroidWorld, Oct 28–29 (a separate run: 116 tasks, pass@1, seed 30, Spark profile) | before the 13 changes 21 (18%); with them 57 (49%); held-out half 31 of 58 against 12, re-measured on a staging tree 30.5 of 58. The 22 of 59 compiled routines that redid their own task, on 3 new seeds: 55 of 69 at a median 1 call and $0.0021, against the agent's 63 at 6 calls and $0.0122 (`a80b976`, `736a6e4`; `docs/androidworld-results.md`) |

The real-app cost curve is computed from `eval/results/final/real.json`: medians (and ranges) over the workflows whose
first run and same-input rerun both passed. The routine is called by name, so no matcher call is counted; asked in
words, the matcher adds one Spark call.

**"Make it a routine" on real apps** (after the evaluation, on the tag, to a protocol fixed before it:
`eval/results/learn-agent-path/`). An agent asked each of the 18 real-app questions over MCP; "Make it a routine" was
pressed on each finished task; each saved routine was shared and called back as a tool.
- The agent path answered 14 of 18 right. Over MCP, `run_task` tries the routine library first, so 6 of the 18 were
  answered, or tried, by routines already in it.
- "Make it a routine" saved 8 of 18: 8 of the 12 tasks that weren't already routines. The other 6 ran an existing
  routine, and the button doesn't take a routine's task. Of the 4 not saved: Target's bot check; a harness slip that
  timed out target_search; calendar_today's empty-day answer, which couldn't be read back from its final screen; and
  chrome_wikipedia's replay, which stopped at an after-check.
- Called back as tools: the 5 same-input calls were right with 0 model calls in Envoy's replay; the 3 new-input calls
  were right, 2 with 0 model calls (YouTube Music's took 1).
- Supplementary, outside the headline: on a copy with an empty routine library, the 6 workflows the library had
  answered: the agent right 5/6, saved 5/6, new input right 3/5, all with 0 model calls in Envoy's replay.

**The posting batch.** Declared before the tag (`eval/results/showcase-batch/PROTOCOL.md`) and run once on it, Nov 3, on
Envoy's phone: the four posting routines (all v3), 10 attempts each, from a cold start, an open app or a saved draft,
with the test accounts. Every final button that was asked was declined, so nothing was posted. These numbers are for
this version, these workflows and inputs, one phone and one set of accounts, one afternoon
(`eval/results/showcase-batch/RESULTS.md`; every attempt in `attempts.md`).

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
- **The Short's misses have known causes.** Its song check stopped three runs whose song wasn't on YouTube's trending
  sounds, where "golden hour" is: a search-only check after the batch, on Envoy's phone and not measured in it, found
  that YouTube's sound search runs only when its suggestion is tapped, and v3 skips that tap
  (`eval/results/showcase-batch/yt-song-fix-writeup.md`). One more, with another song, was finished by the agent, so its
  sound couldn't be checked. Two more, from a saved draft, stopped at YouTube's "Continue your draft video?" prompt.
- **The Reel's third miss:** Instagram's music search didn't show "Levitating", which the library check had found
  earlier, and the agent stopped at its step limit.
- **Model calls in Envoy's replay:** 95 over the 40 attempts, $1.0342. TikTok reads its drawn sound list by vision on
  every run, by design.

**After the batch, not part of it (Nov 3):** `instagram_reel_song` v4 (merged in `0d28e5a`) ends the caption edit with
Instagram's OK instead of Back, and types the caption again if it's empty before Share. On Envoy's phone, on a test
copy with every Share declined, 5 of 5 Reels from a cold start reached Share with clip, song and caption checked, at 0
model calls in Envoy's replay; TikTok 1 of 1, as a check that nothing else broke
(`data/routines/instagram_reel_song/index.json`, v4).

The current version, v5, adds a hand-edited wait for the upload after Share; in its one run, on Nov 4, it finished with
0 model calls in Envoy's replay, in 95.8 s (`data/routines/instagram_reel_song/index.json`).

**Changes since the evaluation,** not measured by it: `wait_for_task`, which holds a call up to about 45 s so an agent
stays in its turn until a task is final; Lyft's "Confirm drop-off location" no longer asks, because it only sets where
you're going ("Confirm pickup" and "Request …" still ask); and in a routine with no irreversible step, rows named by an
input that tie when their list can't scroll now take the top one.

**A routine learned cold, on a real app (Nov 4).** With the author's real Uber account, read-only and with no ride
requested, "Make it a routine" on one finished agent task saved `uber_check_uberx_price`. Its checking replay took 14.0
s (destination: Truist Park). Its next run took 11.33 s with 0 model calls in Envoy's replay. On a later run an extra
screen appeared: it repaired that step with 1 model call in 32.9 s, and the repaired version passed its trial in 12.81 s
with 0 model calls in Envoy's replay (`data/routines/uber_check_uberx_price/index.json`).

Measured outside the evaluation (these stay as they are):

| What | Result | Source |
| --- | --- | --- |
| Real posts, night of Nov 1 | Instagram Reel with a library song, Instagram Story with a poll, YouTube Short with a sound: live, 0 model calls each in Envoy's replay. TikTok with a sound: live, 3 calls, on a re-post after a compiler fix | `docs/demo-showcase.md`; tasks `task-1102-005928-4182`, `task-1102-013244-b7c8`, `task-1102-015325-106a`, `task-1102-023044-d081` |
| The calling agent's cost | The Spark agent: 11 model calls, $0.044, to drive a three-post run on a test copy (Nov 1, declined at each final button) | `agents/meta-agent/evidence/2026-11-01/crosspost/README.md` |
| Notifications, Nov 2 | Instagram comment: on the iPhone 1.57 s after it landed on Envoy's phone. YouTube: Envoy's part 3.6 s (YouTube took about 2 minutes to notify). TikTok: no notification came | `docs/demo-showcase.md` |
| The cloud phone, Oct 29 | Routines for SkyLark (our own test app) compiled on the Mac: 48/48 with no model calls on an emulator on Google Cloud, once it had finished its first boot | `docs/cloud.md` |
| A learned routine as a tool | `skylark_get_flight_gate` shared, then called over MCP: done, 0 model calls in Envoy's replay, $0 | `eval/results/agent-door/call.json` |
| One request, every post, Nov 2 | `cross_post` on Envoy's phone through a test copy: four parts from one request (returned in 0.26 s); Instagram, the Short and TikTok declined at their final button, a YouTube search part done; a retry re-ran only the three. Nothing posted | `eval/results/agent-door/cross-post-pixel.json` |
| Outcome checks, Nov 2 | On Envoy's phone: a wrong newest clip stopped the TikTok routine before its first step (0 calls); the Reel, TikTok and Short then reached their final buttons with song, caption and clip checked, every one declined | `eval/results/showcase/runs/runs.md` (19:27–20:35) |
| Muse end to end, Nov 2 (a dry run) | `send_to_phone`, then five tasks through the routine tools. The Reel, TikTok and Short each reached its final button and was declined: 0 / 3 / 0 model calls in Envoy's replay, 195.5 / 75.1 / 77.4 s from Muse's call to the end (phone ask and approval wait included). Nothing was posted | `eval/results/showcase/muse-2026-11-02/task-rows.json` |

## Built during the hackathon

- **The history:** all of Envoy is in this repo's history, from the first commit on Oct 26 (the repository layout and
  the design plan, no code yet) to the last.
- **Open source:** projects like uiautomator2, scrcpy, FastAPI, the MCP SDK, Next.js and d3-force are plumbing,
  credited with their licenses in `THIRD_PARTY.md`.
- **What Envoy builds itself:** the agent runtime; the routine compiler, executor and repair; teach mode; the memory;
  the device layer; the safety gate; the web app and the iPhone companion; and the phone layer for agents (learned
  routines as MCP tools, a key per agent, notification triggers, files back to the agent, and the Spark agent).
  `THIRD_PARTY.md` › "What Envoy builds itself" draws the line.
- **AndroidWorld** (Google, Apache-2.0) is the benchmark only. Its 116 tasks score Envoy; none of its code runs inside
  Envoy.

## Limits

- **A routine can still need the agent, or fail, in a live run;** each routine's `index.json` lists every run.
- **Some apps refuse emulators,** like Target with its bot check (banking apps are expected to, untested). That's why
  Envoy can also use your own Android phone: it sends those apps there, asking first. When a bot check or a sign-in
  appears, Envoy pauses and prompts you to take over, then carries on when you hand it back.
