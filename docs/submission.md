# Envoy: the submission

A draft answer for each field of the hackathon's submission form (the fields are listed in `docs/phase-0-findings.md` ›
B3). Every number points at a committed file.

**TBD (Nov 2)** marks a number that comes from the final evaluation on the `eval-final` tag. Fill it in from
`eval/results/final/report.md` after the run, and use the same numbers in the README's table and on the site
(`scripts/build_site_data.py`). Until then, each field shows the latest measurement with its source, marked "measured".

## Team name and members

Envoy. Sanjeev Varma, solo.

## Track

Indie.

## Problem statement

**Push the Frontier.**

Agents can search the web, but a lot of what's true about your life right now (your flight's gate, your order, your
points) lives inside phone apps that have no API and no website an agent can use. Muse can't operate phone apps today.
Envoy gives it that capability. And because a phone agent that thinks through every tap is slow and costly, Envoy makes
it learn: one good run becomes a routine that runs again in seconds with few or no model calls.

## Project description

*Agents can search the web. Your phone knows your life.*

Envoy is a phone layer for agents. It runs Android emulators on a Mac (and, when you allow it, your own Android phone)
and lets Meta's Muse models use apps the way you do: read the screen, tap, type, and stop to ask before anything that
can't be undone. You can ask from Envoy's web app, by voice on your iPhone, or from the Muse app itself through a custom
MCP connector. Approvals arrive on your iPhone.

What's new is what happens after the first run. Envoy compiles a successful run into a **routine**: a small program
with inputs, a check before and after every step, and targets found by what they are rather than where they were. When
the app changes, the routine repairs only the broken step and saves the fix as a new version. In the Starbucks app,
the agent's first run took 45.6 s and 12 model calls; the routine compiled from it took 14.8 s and 2 calls, with the
same answer (`eval/results/real-apps/loop-a/runs.jsonl`).

Envoy also keeps a **memory** of what it sees in apps, email and photos, where every fact records where and when it was
seen, so it can answer from memory and notice when something changed.

## Public GitHub repository

https://github.com/sanjeevexe/envoy

- **The showcase site,** a guided tour built only from recorded runs and committed results:
  https://sanjeevexe.github.io/envoy/
- **The README** has the results table and how to run it. SkyLark is our own test app, so it runs with no personal
  accounts.

## Demo video (YouTube, 3 minutes or less)

TBD: the YouTube link, by Nov 4.

## Use of Meta products

| Product | What Envoy uses it for | Where |
| --- | --- | --- |
| Muse Spark 1.3 | Matching a request to a routine, reading facts from screens, email and photos into memory, telling whether two things are the same, answering from memory, chat routing, app notes, and grounding on screens with no accessibility tree. On the `spark` profile, also the plan, the steps and repairs. Structured output on every call. | `backend/models/adapter.py` (`JOBS`) |
| Muse Wonder 1.0 | Compiling a run into a routine. On the default `hybrid` profile, also the plan, the steps and repairs of a task the agent hasn't seen. | `backend/models/adapter.py` (`PROFILES`) |
| SAM 3.1 | Exact boxes on drawn screens (a canvas seat map) that have no accessibility tree; Spark picks the box | `docs/phase-6-results.md` |
| Muse Voice Transcribe | Dictation in the web app and on the iPhone | `docs/phase-5-results.md` |
| The Muse app | The front end: a custom MCP connector to Envoy (run a task, read memory, see what changed on the phone) | `docs/muse-link.md`, `docs/phase-5-results.md` |

The Contributor tier (Meta may train on inputs) is used only with our own test apps, never with real apps
(`.env.example`, `META_CONTRIBUTOR_TIER`).

## Why Meta's models matter

- **Muse can't reach phone apps; Envoy gives it that.** In the Muse app, "check me in for my flight" goes to Envoy's
  connector, Envoy works the phone, and Muse says the check-in is waiting for your approval, not its own
  (`docs/phase-5-results.md`, `docs/meta-feedback.md`).
- **Structured output that always fits the action schema.** Every step comes back as an action Envoy can run, with a
  risk label that feeds the approval gate. Code rules back up the label: on 20 irreversible controls, code alone caught
  20 (measured: `eval/results/final/safety.md`; final: TBD (Nov 2)).
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
- **What would help:**
  - Document that strict JSON output writes keys alphabetically. It silently changes how a model reasons when a
    schema's order matters.
  - Fewer "Allow once" prompts when adding a connector.
  - A way for a connector to tell Muse that a long task finished.
  - Support for MCP's current protocol version.
  - Don't let link previews fetch URLs from tool results.
  - A documented token cost for screenshots.
  - SAM output as structured data rather than special tokens.
  - Clearer docs for caching and the voice handshake.

## Most Viral track (optional)

TBD: the user's X post link, if any.

## Publicity grant

Yes. The repo, the site and the video show only test accounts and test data: SkyLark, its Maya Patel persona, and a
test Google account.

Before the repo went public, a sweep of the files and the full git history (Oct 31) found no keys, tokens or passwords.
Runs on the user's own accounts (ride fares) were stored as numbers only.

## Final numbers (TBD, Nov 2)

From `eval/results/final/report.md` once its "Ran on" column says `eval-final` for every suite. The measured column is
what the report shows today, on development commits.

| Suite | Measured (commit) | Final on `eval-final` |
| --- | --- | --- |
| 0. Core routines compiled and verified | 10 of 10 (`ad9a67b`) | TBD |
| 1. Three systems on SkyLark (10 tasks × 4 layouts) | Envoy routines 40/40 first try, median 1 call, 5.5 s; the agent every time 40/40, 5 calls, 10.1 s; fixed replay 14/40 (`ad9a67b`) | TBD |
| 2. First run vs later runs | request 1 median $0.051, 27.9 s; requests 2–10 90/90, median 1 call, $0.0023, 5.9 s (`5c3d716`) | TBD |
| 3. Routines under change | new inputs 50/50 with no model call; injected changes recovered 50/50, then 50/50 alone (`6c507f3`) | TBD |
| 3b. Screen sizes and the real phone | envoy-test 30/30, envoy-small 30/30, envoy-large 29/30 (`5504260`); Pixel 5 30/30, 0 calls (`a9b923d`, `sizes.md`) | TBD |
| 4. Real apps (18 read-only workflows) | first run 14/18, compiled 14/18, rerun with no call 13/18, new input 4/11 (`00ec5d9`); Oct 31 rehearsal 12/18, 12/18, 9/18, 6/11 (`a594136`) | TBD |
| 5. Memory | extraction 459/468 (98%), 0 wrong; stale facts served without a warning 0/12 (`5c3d716`) | TBD |
| 6. Safety: irreversible actions | caught 20/20 (code alone 20); reversible flagged 0/22; live declines held 7/7 (`849e51a`) | TBD |
| 6b. Safety: planted instructions | agent right 20/20, followed it 0; irreversible without approval 0; injected values stored 0 (`7395743`) | TBD |
| 7. Interfaces end to end | web, approval modes, iPhone: all passed (`e18e434`) | TBD |
| AndroidWorld (116 tasks, pass@1, seed 30) | `main` 21 (18%); with the 13 changes 57 (49%); held-out half 31 of 58 against 12, re-measured on what merged 30.5 of 58 (`docs/androidworld-results.md`) | TBD if rerun; otherwise these stand |

## Built during the hackathon

- **The history:** all of Envoy is in this repo's history, from the first commit on Oct 26, the day the hackathon
  started (the empty repository layout), to the last.
- **Open source:** projects like uiautomator2, scrcpy, FastAPI, the MCP SDK, Next.js and d3-force are plumbing,
  credited with their licenses in `THIRD_PARTY.md`.
- **What Envoy builds itself:** the agent runtime, the routine compiler, executor and repair, the memory, the device
  layer, the safety gate, the web app and the iPhone companion. `THIRD_PARTY.md` › "What Envoy builds itself" draws the
  line.
- **AndroidWorld** (Google, Apache-2.0) is the benchmark only. Its 116 tasks score Envoy; none of its code runs inside
  Envoy.

## Limits, said plainly

- **New inputs on real apps** work about half the time (4 of 11 on Oct 28, 6 of 11 on Oct 31). Routines on our own
  test app do far better (50 of 50).
- **Apps that refuse emulators** (Target's bot check, banking apps) need a real Android phone. iPhone-only users can't
  reach them.
- **Sign-in:** you sign in to each app once on the emulator.
- **Where it runs:** the emulators run on a Mac today. A cloud copy was proven (`docs/cloud.md`), but it isn't the
  default.
- **AndroidWorld's changes:** we don't claim they help on real apps. That rerun decides it.
