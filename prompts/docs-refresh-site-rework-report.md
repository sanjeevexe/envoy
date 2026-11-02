# Docs refresh: the showcase site rework (Nov 2)

Session site-rework, branch `claude/site-rework-3da8f9` on main `947bf44`. Only `site/**`, `scripts/build_site_data.py` and
this report (with its screenshots in `prompts/docs-refresh-site-rework-report/`) changed. Not pushed, not merged: pushing
main redeploys https://sanjeevexe.github.io/envoy/, so that waits for the user's OK through the coordinator. No devices, no
model calls, $0.

## What changed

**The opening tells the new story.** Section 1 is now "The phone layer agents call":
- **The one-liner:** "Muse has a computer. Envoy gives it a phone."
- **The lede:** acts, learns, watches; Muse or any MCP agent as the front door; anything irreversible waits for the
  person's yes in Envoy on their iPhone.
- **A small diagram, in HTML rather than an image:** the front door (Muse, the Spark agent, Claude Code), then MCP, then
  Envoy, then Envoy's phone, emulators and the cloud phone, with the person's iPhone under Envoy.
- **Four headline cards, each linked to its section:**
  - 3 agents;
  - 4 posts from 1 request;
  - Starbucks 45.6 s → 14.8 s;
  - 1.57 s from an Instagram comment to the iPhone.
- **"Limits, plainly", rewritten from the fact sheet:**
  - Envoy runs on a Mac;
  - it learns a task, not an app (4/11 and 6/11);
  - agents hear about the phone when they next poll;
  - no TikTok notifications;
  - the Story poll fails while a Story is live, and teach mode's gaps;
  - Target and banking apps refuse emulators;
  - the final evaluation runs Nov 3. This line switches by itself once the eval is final.

**Five new sections, each built from files in the repo:**
| # | Section | Evidence |
| --- | --- | --- |
| 2 | Agents call it | The Spark agent's four-post cross-post rendered from its own event log (`agents/meta-agent/evidence/2026-11-01/crosspost/run2-four-posts.json`): the request, the four routine-tool calls with arguments, the phone asks, each final button and its decline, Spark's words, 11 calls, $0.043. Two of its page captures. Muse: two Oct 29 captures (Muse for Mac filling the outbox; Muse saying there's no accept or approve tool) plus the Nov 2 end-to-end dry run **in words only**. Claude Code: its three task rows from the live API and its refusal to approve |
| 3 | Learned routines become tools | `eval/results/agent-door/`: the tool list before and after one share switch, the new tool exactly as agents see it, one call to it. The Spark agent calling `skylark_check_flight_status` by name (event log and capture). A crop of Settings › Agents › Agent tools |
| 4 | Acts, in the apps | The four showcase routines from `data/routines/` (version, steps, inputs, how made). Each one's first run and the replays of its active version, copied from `eval/results/showcase/runs/runs.md`. Its real post from `prompts/showcase-report.md`. One P3 frame of the Story poll sticker on the Pixel, labeled as driven by hand before the routine existed. A "flaws included" callout: TikTok's songless post, the live-Story failure, YouTube's search repair |
| 5 | Watches | The six trigger kinds read from `backend/api/scheduler.py`. The Nov 2 live comment table copied from `prompts/phone-watch-report.md` (Instagram +1.57 s; YouTube's ~2 min delay; TikTok none; the code comment not notified). Muse's scheduled task polling `phone_updates` (Oct 29 capture, cropped) |
| 6 | A key per agent | Tool groups and the 30-a-minute limit read from the code. A crop of Settings › Agents (Add an agent). The Spark agent on a read-only key: 6 tools, an unknown tool refused, "only you can approve in Envoy" |

**The proof sections are kept and moved after the layer:** first run, learned, repairs, real apps, teach, memory, safety,
models and results (sections 7–15), then how it's built (16). A short "Underneath the layer" band introduces them. Their
content is unchanged except:
- "final numbers after Nov 2" is now "after Nov 3" everywhere (chips, banner, the AndroidWorld note);
- the results section's eyebrow reads "The results";
- the old hero's Starbucks proof card and the "what's new vs. existing phone agents" grid are gone (the old framing). Their
  numbers live on in the Learns card and sections 7–8.

**Build script (`scripts/build_site_data.py`):**
- New: `spark_run` (reads a Spark agent event log), `agents`, `tools`, `showcase`, `watches`, `keys`.
- `image()` can crop a capture.
- Dropped `claim()`. The build no longer parses `docs/technical-design.md`'s Overview, so the docs session can rewrite it
  freely.
- Still deterministic: two builds give identical bytes.
- Ten new webp images in `site/data/img/`; the site is 2.1 MB.

**`site/README.md`:** the sixteen sections, a new source row for every new number, the files the build parses, the Nov 3
eval path, and privacy rows for every new image.

## Checked

- **Browser:** served from Bash on 127.0.0.1:8781.
  - Widths: desktop at 1440 (headless Chrome, per section) and phone at 375 (the browser pane).
  - Themes: light and dark.
  - No console errors.
  - No horizontal overflow at 375 px.
  - The only 404 was headless Chrome's `/favicon.ico` (the page's icon is inline).
- **Source links:** all 80 distinct paths the page links to are files or folders git tracks. The links point at
  `github.com/sanjeevexe/envoy/blob/main/`, so they work once this branch is merged and pushed.
- **The post-eval path, simulated:** I edited `eval/results/final/report.md` to "10 of 10 suites on the `eval-final` tag"
  with every row on `eval-final`, then rebuilt.
  - The banner read "Final numbers", every pending chip cleared, and `numbers.json` marked the suites final.
  - Restored with the backup; `site/data/` came back byte-identical.
- **Privacy:** every new image was looked at full size. The pre-crop captures were checked too.
  - `muse-link/e1` had the user's now-playing album art in the Dynamic Island, so it's cropped below the status bar.
  - The Muse for Mac capture is cropped to Muse's window (no Dock).
  - Test accounts' handles are removed from the real-post results (envoy3955, envoy, @envoy-e8o). They're already in
    committed docs, but they don't need to be on the page.
  - No `*.ts.net`, keys, tokens or real-account data anywhere.
- **Screenshots:** `prompts/docs-refresh-site-rework-report/`.
  - `01`–`06` are the six new sections at desktop width.
  - `07` is the layer diagram at phone width.
  - `08` is the hero in dark.

## Sections without real footage

- **Muse end to end (Nov 2):** no capture or task rows are in the repo. The page states it in words, with a chip
  "Dry run, Nov 2 · no capture in the repo yet", and no source link. I asked the coordinator whether a capture or a
  read-only task-row dump could be committed (like `claude-code/task-rows.json`). If one lands, it can replace the words.
- **Muse seeing a new tool without reconnecting (P1):** in words only, labeled "no capture in the repo".
- **Watches:** no capture of the notification on the Pixel or the push on the iPhone. The section is the timing table plus
  the Oct 29 Muse capture. I mentioned to the coordinator that an iPhone push still (no handles) would help, if cheap.
- **App-only posts:** no frame from Envoy's own runs.
  - The showcase source traces have screen trees but no screenshots.
  - The approval screenshots stayed outside the repo on purpose (TikTok's shows nearby places).
  - The one frame shown is the P3 poll sticker, driven by hand, and the caption says so.
  - The page doesn't link the live posts.
- Everything in sections 7–15 is unchanged real footage.

## Unsure, or worth a second look

- **The TikTok re-post with the sound.** `prompts/showcase-report.md` and `docs/demo-showcase.md` say task-1102-023044-d081
  went live with "♫ golden hour - JVKE". The fact sheet only mentions the songless first post. The page shows both, cited
  to the report. I asked the coordinator to confirm.
- **The YouTube Short's model calls on its real post** aren't in any committed file, so the page doesn't claim "0 calls"
  for it. It shows "live, public".
- **Replays per routine** count only runs after the active version was compiled. Earlier rows reuse the same version
  number for hand-tuned candidates. For the reel this gives 3/3 with 0–16 calls; the report's own "3/3, two at 0 calls"
  agrees.
- **"3 agents"** counts Muse, the Spark agent and Claude Code, per the fact sheet. The Claude Code card says its check-in
  approval was never answered (an API restart stopped it).

## For the user to decide

1. **Link the live posts?** The public Reel and Short URLs are in the (uncommitted) demo plan, on test accounts. The page
   doesn't link them now.
2. **Show the test accounts' handles?** They're removed from the page now.
3. **A phone capture for Watches?** An iPhone push for an Instagram comment, if the coordinator can take one cleanly.
4. **The navigation has 16 entries** and scrolls sideways on narrower screens. Shorter names or fewer stops are possible if
   it feels long.

## For the other docs sessions

- **docs-folder, already messaged:** the build parses these lines in `docs/`, and a reworded line stops the build:
  - `docs/androidworld-results.md`: "**Headline.**" and "**Held-out half:**";
  - `docs/phase-5-results.md`: the "Voice, scripted" row;
  - `docs/diagrams/*.png`.
- **The page links to these `docs/` files:** `cloud.md`, `muse-link.md`, `agents.md`, `demo-showcase.md`,
  `phase-6-results.md` and `androidworld-results.md`. A rename needs a matching change in `site/`.
