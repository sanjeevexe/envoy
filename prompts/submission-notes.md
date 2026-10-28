# Submission: notes for the final step (not a prompt yet)

The submission was taken out of Phase 7 on Oct 27; you'll run it as its own step at the end, after the frozen evaluation (Nov 2). This file keeps what it needs so nothing is lost. Turn it into a prompt (`prompts/submission.md`) when it's time. The Phase 7 chat adds the final numbers and pointers to the section at the bottom.

## Deadlines (ET)

- **Nov 2 (Sun):** features freeze; the final evaluation runs on the `eval-final` tag.
- **Nov 4 (Tue), 9:00 PM:** the submission form, and Meta's $150 credit claim (a separate form, yours).
- Judging Nov 4–8: a pass/fail theme check, a 0–10 rubric ("creativity, technical ambition, and whether it works"), then a top-5 final per track where **the videos are watched live**. Closing ceremony Nov 9.

## What the form asks for (`docs/phase-0-findings.md` › B3)

| Field | Starting point |
| --- | --- |
| Team name, members | Team of one; "Envoy" |
| Track | Indie |
| Problem statement | "Push the Frontier": Envoy gives Muse a capability it lacks, operating phone apps |
| Project description | The design doc's overview: "Agents can search the web. Your phone knows your life." |
| Public GitHub repository | `sanjeevexe/envoy`, public by Nov 4 (your click) |
| 3-minute demo video (YouTube) | Hard cap 3:00 |
| Use of Meta products | Muse Spark 1.3 (agent, plans, extraction, chat, vision), Muse Wonder (routine compiling), SAM 3.1 and grounding (drawn screens), Muse Voice Transcribe (dictation), and the Muse app as the front end through a custom MCP connector |
| Why Meta's models matter | Structured output that always matches the action schema; risk labels; grounding on the 0–1000 grid; SAM's exact boxes. Muse acts through web and connectors but can't operate phone apps; Envoy gives it that |
| Feedback on Meta products | `docs/meta-feedback.md` (kept current through every phase) |
| Most Viral track (optional) | An X post link; a short clip of Muse checking you in through Envoy |
| Publicity grant | Meta and Cerebral Valley may publish the submission: no personal data in the video or the repo |

## The video

- **Hard cap: 3:00.** The judges watch it live in the final, so show the product working, not slides.
- **Storyboard draft (from Phase 0, update it):**
  1. Muse: "check me in";
  2. Envoy works the phone;
  3. the approval arrives on the iPhone;
  4. memory updates;
  5. a routine reruns with no model calls;
  6. a broken screen gets repaired.

  Candidates to add if they earn their seconds: the real Android phone with its banner and pause; dictation; a drawn screen (the canvas seat map, SAM then grounding); the evaluation's headline charts; AndroidWorld's result.
- **Deliverables:** a shot list with timings, what's on screen and the narration (spoken in under 3 minutes); a deterministic setup for every shot (`scripts/demo_setup.py` and friends), the same state every take; at least two clean end-to-end rehearsals.
- **Only work built during the hackathon (Oct 27 – Nov 4), clearly identified**, or the project can be disqualified; open source is plumbing (`THIRD_PARTY.md`).
- **Test accounts and test data only** on screen: SkyLark, the test Google account, no real orders, nothing from your personal apps.
- **Yours:** narration, final editing, the YouTube upload, the optional X post.

## The write-up

- Every form field drafted (as `docs/submission.md`), each claim pointing at evidence in the repo, every number from the `eval-final` tag, honest about limits.

## The repo, before it goes public

- A README quickstart a judge can run without your accounts (SkyLark, the emulator, the web app), and what each part needs.
- **A secrets sweep of the files and the whole git history:** keys, tokens, the session token, `.env` values. `.env` is gitignored and has never been committed, but check.
- **A personal-data sweep:**
  - your name and email beyond the license and git authorship;
  - the iPhone and Muse screenshots in `eval/results/phase5/` (`muse_*.jpg`, which show the tailnet host name);
  - the tailnet host name in docs;
  - the test Gmail account's content;
  - anything from your real phone or real apps.
- Anything found goes to you with a fix proposed; rewriting history is your call.
- `THIRD_PARTY.md` complete; "what Envoy builds itself" accurate; large files out of git.
- **Making it public is your click**, after you've seen the sweep.

## Your own checklist

- [ ] The $150 credit claim (Meta's form), by Nov 4, 9 PM ET
- [ ] Narration, editing, the YouTube upload
- [ ] Making the repo public (after the sweep)
- [ ] Submitting the form, by Nov 4, 9 PM ET
- [ ] Optional: the Meta AI Connectors waitlist; the Most Viral track post

## From the evaluation (the Phase 7 chat fills this in)

- Final numbers and where they live (`eval/results/final/report.md`, the charts):
- AndroidWorld (from the `androidworld` branch, `docs/androidworld-results.md`):
- Claims we can make, and claims we can't:
- Demo-worthy moments the evaluation found:
- Phase 6 on the real phone (done, or still open):
