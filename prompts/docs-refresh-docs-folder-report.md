# Docs refresh, Nov 2: the docs folder and component READMEs (report)

Session `docs-folder`, branch `claude/docs-folder-042308`, on main `947bf44`. Docs only: no code, no devices, no live API,
no model spend. Not pushed.
- **Commits:** `1b21ec7` (the docs) and the one that adds this report.
- **Checked against:** `prompts/docs-refresh-facts.md`, the phase-layer reports in `prompts/`, and the code in main.

## What changed

**New:**
- **`docs/README.md`, the index.** It covers the frame, the current design and its pillars, how agents connect, the
  phones, the showcase, results, known gaps, and the historical records (marked as such).
  - **Results** are one table. Each row names its file and commit, and says development commits until the Nov 3
    `eval-final` run.
- **`docs/diagrams/architecture.html`:** the source of the new architecture diagram, so it can be edited later.

**`docs/technical-design.md`.** The dated header says what was updated. The phase-results sections are untouched apart
from Phase 7's date.
- **Overview:** the frame (acts, learns, watches), "not a rival assistant", and what's new. Muse's own words are quoted,
  not asserted. The three agents tested.
- **Goals:** goals 7–12, added Nov 1.
- **Architecture:** callers, backend, models, devices. A new end-to-end walk-through: the Nov 2 Muse dry run, with
  routine tools by name, the phone ask, the approval and `phone_updates`.
- **Device layer:**
  - the cloud as tested;
  - Envoy's phone over USB;
  - the phone-choice table with an agent's `phone`;
  - `list_phones`;
  - the "use Envoy's phone?" ask: no answer in 15 min ends the task (947bf44), and only a "no" moves it to an emulator;
  - the banner app.
- **Agent runtime:** cross-app answers are built. A restart marks tasks stopped, not failed.
- **App routines:** new subsections "Teach mode" and "Routines as agent tools".
- **Interfaces:**
  - the table, with Siri added, Gmail only, and the MCP row;
  - the web app's real sections;
  - the MCP server (all 12 built-in tools plus routine tools);
  - a new "Agents: a key and a tool set each";
  - Path into Muse, with Nov 2 status.
- **Gmail:** a script reads mail, the API doesn't poll, and Calendar wasn't built.
- **Scheduled and event-triggered tasks:** six kinds, ask mode, offers, habits, change alerts, recurring jobs from chat,
  agent-proposed triggers. A new "Phone notifications" section with the Nov 2 measurements.
- **Safety:**
  - approvals are web pushes without buttons, and no answer in 15 min counts as no;
  - a new "Agents get no way around it";
  - the filming note about requests typed in Envoy's own app;
  - untrusted content now includes files, sidecars and tool results.
- **Tech stack and repo tree:** as built. Not built: the bridge, the Node relay, the shop app, the native iOS app,
  `sqlite-vec`, OAuth and Calendar.
- **Build phases, risks and open questions:** dates fixed (the eval is Nov 3), plus how the risks turned out.

**`docs/diagrams/architecture.png`, redrawn.** The old one was wrong about the architecture:
- It showed the bridge on every phone, but the bridge isn't built.
- It said "adb over Wi-Fi, later", but Envoy's phone is on USB now.
- It listed ChatGPT among MCP clients (untested), and "Gmail and Calendar" (Calendar isn't built).
- It had no agents front door, no keys and no routine tools.

The new one was checked at full size: generic labels only. `routine-lifecycle.png` is still right. `build-phases.png`
is the Oct 26 plan, and the docs now say so.

**`backend/mcp_server/README.md`, rewritten.** The tool list matches `server.py` exactly, with each tool's group,
routine tools, `phone`, what no tool can do, and its tests.

**Other docs:**
- **`docs/agents.md`:**
  - the three tested agents;
  - a section on learned routines as tools;
  - "Phones and files" and "Hearing back";
  - the Claude Code test record;
  - "on your phone" → "on your iPhone" for approvals;
  - protocol versions;
  - the reference to an untracked prompt removed.
- **`docs/muse-link.md`:** the stale "For the Muse test" section (an old worktree, :8742) is replaced by "How Muse
  connects". It names no host: only that it's the Mac's Tailscale name on port 10000. Also:
  - what was built since;
  - a new record, "Nov 2: one request, end to end", with the 947bf44 fix and #64.
- **`docs/cloud.md`:**
  - "Where this stands (Nov 2)": the showcase never ran in the cloud, `list_phones` kind `cloud`, the forwarder, the VM
    stopped;
  - the offer finding marked still open;
  - the switch-back step uses the permanent Funnel;
  - "Limits, plainly" corrected: it still said stage 3 hadn't run.
- **`docs/demo-showcase.md`:** status (Nov 2): the real posts, Muse's dry run, comment notifications, #64, and that the
  showcase never ran in the cloud. Untracked prompt references removed.
- **`docs/connector-application.md`** (drafts):
  - the tool table, approvals, statuses and limits match main;
  - REST/OpenAPI marked as not built.
- **Stale lines:**
  - `docs/demo-creator-workflow.md`: the forwarder "merged after the Nov 2 eval" is now "merged Nov 1, `869271f`";
  - `docs/phase-7-results.md`: the eval date is Nov 3, and only the date changed;
  - `docs/app-routing-onboarding.md`: its prompt is marked "not in the public repo".

**Component READMEs:**
- **`backend/api`:** agents, sharing, notifications, offers, repeats, alerts, recurring, crossapp and siri. The
  scheduler has six kinds. The phone-layer routes are added.
- **`backend/policy`:** `approval_rules.py`, and the stale "arrives in Phase 4" removed.
- **`backend/routines`:** lifecycle, dates, screen_read, visual and screens; taught routines; sharing.
- **`backend/agent`:** `vision.py`.
- **`backend/integrations`:** the scheduler is in api, and Calendar wasn't built.
- **`eval/README.md`:** every runner group, and the eval date.
- **`agents/meta-agent`:** "What it has done", plus the warm-up note.
- **`ios`, `bridge-android`:** both say "not built", and why.

## What I left, and why

- **Historical records stay as written** (the brief's rule): `phase-0-findings.md`, `phase-1…6-results.md`,
  `meta-api-test-plan.md`, `real-app-test-set.md`, `androidworld-results.md` and `research/`. The index marks them
  historical.
  - The design doc's own "Phase N results" sections are records too: Phase 4's "7 tools" and the Oct 29 "ten tools"
    are true for their day.
  - Phase 7 got only its eval date fixed, since that run is still ahead.
- **`siri.md` and `preflight-and-autofill.md`** describe features as built (Oct 29 – Nov 1). Nothing in them
  contradicts the fact sheet that I found.
- **`meta-feedback.md`** is a running log for the submission. Not mine to extend without the facts behind new entries.
- **`app-routing-onboarding.md` and `demo-creator-workflow.md`** are dated feature records. I fixed only what was
  wrong.
- **The build-phases and routine-lifecycle diagrams:** not wrong about the architecture.

## Not sure it's true, or worth a look

1. **"Instagram on emulators is untested"** (fact sheet) vs `docs/cloud.md`. The cloud doc records a plain Reel
   reaching Share on the cloud emulator on Nov 1 (declined; `eval/results/cloud/instagram/`).
   - What I wrote: the showcase's features (library song, poll sticker, TikTok, YouTube) are untested on emulators,
     and a plain Reel reached Share in the cloud.
   - The README and site sessions should say the same.
2. **Teach mode's source.** The fact sheet points to `docs/phase-7-results.md`, which doesn't mention teach mode.
   - It's now in `technical-design.md` › "Teach mode", from `backend/api/teach.py` and
     `eval/results/teach_trials_2026-11-01/README.md`.
   - The "Calendar add event (Oct 31)" success in `prompts/demo-plan.md` has no evidence file I could find, so I didn't
     cite it.
3. **The TikTok re-post.** `prompts/showcase-report.md` (tracked) records a v3 re-post, live with the sound (Nov 2,
   02:30, 3 calls, 53 s). The fact sheet's "Proven live" doesn't mention it.
   - I kept the record in the docs, as `docs/demo-showcase.md` already had it.
   - If the user deleted that post or doesn't want it claimed, say so.
4. **The Muse dry run of Nov 2** (0/3/0 calls, about 1 min 15 s each, 5 taps) comes only from the coordinator's banner
   in `prompts/demo-plan.md`, which isn't in git. I recorded it in `docs/muse-link.md`, citing the coordinator's notes;
   there's no evidence file in the repo.
5. **Routine tools appearing live in Muse.** The no-reconnect evidence is the P1 probe (a probe server, not Envoy's
   tools). With Envoy's own tools, the Nov 2 rehearsal shows Muse calling them by name. I worded it exactly that way.
6. **The approval timeout.** `WebApprover`'s `timeout_s=900` marks the approval expired, with decision "no". I wrote
   "no answer within 15 minutes counts as no". The old text said the task "is paused".
7. **MCP protocol versions** (2026-07-28 and the handshake versions up to 2025-11-25) come from the installed MCP SDK
   2.3.0, not from Envoy's code.
8. **Since `cd168d6`, YouTube's Upload, TikTok's Repost and TikTok's "Your Story" count as publishing buttons.**
   - The demo-plan banner says they "always ask". The commit says the rules "catch" them, which makes them irreversible
     steps under the normal approval modes.
   - I wrote the latter. Check before saying "always" on screen.

## For other sessions' files (not edited)

- **README.md (the README session):**
  - It could link `docs/README.md` as the docs map.
  - Its Phase-6 paragraph says "Use your Android phone?" and "your phone". Fine for a general user's phone, but the
    Pixel is "Envoy's phone" in demo wording.
- **`docs/submission.md`:** it still says "TBD (Nov 2)" in several places. The eval is Nov 3.
- **site (the site session):** `site/data/img/diagram-architecture.webp` is the old architecture diagram. The new one
  is `docs/diagrams/architecture.png`, with its source `docs/diagrams/architecture.html`.
- **No owner named:**
  - `relay/README.md` still says the Node relay was "Built in Phase 4". Phase 6 replaced it with Envoy's own Python
    scrcpy client, and `relay/` holds only that README.
  - `testapps/README.md` wasn't checked against the shop app, which wasn't built.
- **Code, not docs:** `backend/mcp_server/server.py`'s module docstring names ChatGPT as a client; it's untested.

## For the user to decide

- **Linking the live posts:** I didn't link them (the Reel and Short URLs in `prompts/demo-plan.md`). `envoy3955` was already in committed docs, and the
  YouTube handle `@envoy-e8o` only in `prompts/showcase-report.md`; I added neither anywhere new.
- **Muse's quote:** `technical-design.md` quotes Muse's answer from the user's own Muse chat (Nov 1): "On its own, Muse
  can't open and tap around in apps on your phone." Keep it public?
- **`docs/connector-application.md`:** it's still unsent drafts with [bracketed] fields. Keep it in the public repo?

## Self-check

- **Wording:**
  - The Pixel is "Envoy's phone" throughout. "Your iPhone" is used only for approvals.
  - Nothing says or implies that Muse can't post to Instagram, and nothing claims TikTok notifications.
  - "Muse hears it" always comes with the polling caveat. "Learn a task", never "learn an app".
  - SkyLark appears only as our test app or the stress test.
  - The cloud is "tested"; the showcase never ran there.
- **Privacy:**
  - No `*.ts.net` host name. I removed the placeholder form from my own text; `docs/cloud.md` already had a
    placeholder.
  - No tokens, keys, `.env` values, personal names or emails, or real-account data.
  - The one image added (the architecture diagram) was checked at full size.
- **Links:** every relative Markdown link in the changed files resolves, checked by script. Backtick paths were
  checked too. The only missing one is `prompts/app-routing-onboarding.md`, marked "not in the public repo".
