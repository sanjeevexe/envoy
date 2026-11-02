# Docs refresh, Nov 2: README and write-up (docs-readme)

Branch `claude/docs-readme-04fc31`, on main `947bf44`. Docs only: `README.md`, `docs/submission.md`, `THIRD_PARTY.md`.
Not pushed. No devices, no API, no model calls, $0.

## What changed

- **`README.md`** (153 → 142 lines), rewritten for "the phone layer agents call":
  - **The first screen:** the one-liner, acts / learns / watches, Muse as the front door, the iPhone as where you
    approve. "Why a phone layer" uses app-only features, "no TikTok connector" and Muse's own words, and never says Muse
    can't post to Instagram. One paragraph walks through the Muse → Envoy's phone → iPhone flow.
  - **"What works today":** one table, ten rows (MCP, three agents, routines as tools, app-only posts, watches, learns,
    teach mode, phones, files, approvals). Each row names its evidence.
  - **"Results so far":** still one table, each row naming its source, headed "Development numbers, not final", with
    the eval date now Nov 3, 17:00–22:00 ET. The rows and sources are as before. Wording changes: "A real-app task,
    learned once"; suite 3 reads "we changed SkyLark's layout on purpose, 50 times"; the Pixel row is "On Envoy's phone".
  - **"Limits, said plainly":** every gap on the fact sheet.
  - **"Run it":** checked against the code (below). It adds "Connect an agent" (Claude Code, the Spark agent, Muse).
    The real-phone and routines how-tos are now links.
  - **"More":** pointers to the docs, the phase results and the layout. The site and the write-up are at the top.
- **`docs/submission.md`:** every form field redrafted. That includes the optional partner-tech field, which was
  missing ("Not used").
  - Problem statement and description follow the frame.
  - Use of Meta products adds Muse as the front door, the Spark agent on Spark, Wonder compiling the showcase routines,
    and Instagram as the app Envoy acts in and watches.
  - Why Meta's models matter leads with Muse calling learned tools, Wonder turning a run into an API, and the Spark
    agent.
  - Feedback adds the Nov 1–2 findings.
  - A "Measured outside the evaluation" table holds the posts, the notifications, the cloud run and the routine tool.
    These stay as they are after the eval.
  - "TBD (Nov 2)" is now "TBD (Nov 3)", and the limits match the README.
- **`THIRD_PARTY.md`** › "What Envoy builds itself": two bullets added, "The phone layer agents call" (routine tools,
  agent keys, the notification watcher, files back, the Spark agent's own MCP client) and "Teach mode". Also fixed
  `scripts/make_icons.py` → `make_icons.mjs` (the .py is gone).

## Checked against the code

- **`.env` is at the repo root** (`load_dotenv(REPO_ROOT / ".env")`). The old block ran `cd backend && uv sync` and then
  `cp .env.example .env`, which would have run inside `backend/` and failed. It's now `(cd backend && uv sync)`.
- **Sign-in:** the API prints its sign-in link (`api/__main__.py`), so the README says to open that link, not
  `cat data/api/session_token`.
- **SkyLark's SMS code:** `demo_setup.py` prints it, so the README says that rather than hard-coding it.
- **Commands and paths:** every script, port and UI label used exists as written: `start_emulator.sh` (5554 / gRPC
  8554), `vm-setup.sh`'s sdkmanager and avdmanager lines, `run_final.sh` and the `run_final.py` subcommands,
  `agents/meta-agent/run.py` with `ENVOY_AGENT_KEY_FILE` and :8790, `start_muse_test.sh`, `serve_tailnet.sh`,
  Settings › Agents, "Share with agents" and "Pair your iPhone".
- **MCP:** 12 built-in tools (`server.py`), five tool groups (`auth.py`), six trigger kinds (`scheduler.py` `KINDS`).
- **Numbers:** each one is re-read from its file. The Starbucks rows are in `runs.jsonl`; the Pixel's 30/30 is in
  `sizes.md`; the AndroidWorld headline is in `docs/androidworld-results.md`; the A/B's $0.0074 is in
  `aw_merge_2026-10-28/README.md`; the cloud's 48/48 is in `docs/cloud.md`.
- **Links:** all 142 relative links and backticked repo paths in both files resolve in this checkout.

## Not sure it's true, or no committed evidence

1. **Muse and the routine tools.** Two claims have no committed evidence yet:
   - P1, Nov 1: Muse saw a newly added tool without reconnecting.
   - The Nov 2 Muse dry run: `send_to_phone`, then the three routine tools by name; 0 / 3 / 0 calls, about 1 min 15 s
     each.

   Their sources are pivot §11 and the demo-plan banner, which aren't in git. Both files point at `docs/muse-link.md`.
   I asked docs-folder to add a short section there. If it doesn't, either commit the evidence somewhere or cut those
   two sentences (README "Learned tasks become tools"; submission "Why Meta's models matter" bullet 1 and the two Muse
   feedback lines).
2. **Muse's quote:** "On its own, Muse can't open and tap around in apps on your phone." It's from the user's Muse for
   Mac chat on Nov 1 (pivot §1) and isn't in the repo. The fact sheet says to quote Muse rather than assert the limit,
   so I quoted it. **The user decides** whether to keep it, and whether to back it with a screenshot.
3. **YouTube Short, "0 model calls":** this comes from the fact sheet and the demo-plan banner. The showcase report's
   real-post table gives no call count for `task-1102-015325-106a`. A read-only look at that task would settle it.
4. **The TikTok re-post:** the fact sheet only says the TikTok posted without its song. `docs/demo-showcase.md` and
   `prompts/showcase-report.md` (both committed) say a v3 re-post went live with "golden hour" at 02:30. I wrote "the
   re-post has it", and "each started by the Spark agent and approved on the iPhone" for all of them, per the report's
   intro.
5. **Instagram on emulators:** the fact sheet says it's untested, but `docs/cloud.md` (Nov 1, backlog #49) has
   Instagram reaching Share on the cloud emulator (declined). I claim neither. The site session may care.
6. **The Story limit's detail** ("its first tap opens the live Story's poll results") comes from the banner (#64),
   which isn't committed.
7. **Teach mode, "doesn't yet learn keypad entry reliably":** a scripted Calculator lesson worked on Oct 31
   (`eval/results/teach_trials_2026-11-01/`), and a hand-taught one failed on Nov 2 (#61, not committed). The wording
   covers both.
8. **Approvals:** the fact sheet says anything irreversible stops for the person's yes. `policy/approval_rules.py` also
   allows a standing approval per routine (mode `never`), and money always asks. So both files say "unless you set that
   routine to run without asking". The site may want the same caveat.

## Privacy

- **The author's name** is gone from `docs/submission.md`, which now says "A team of one: the author named in
  `LICENSE`". The fact sheet allows the name only in the license and git authorship. The form itself still needs the
  name typed in.
- **Handles and hosts:** no handles, no `*.ts.net` host, no keys, nothing from real accounts. The only handle is
  `sanjeevexe`, inside the repo and site URLs, as before.
- **Outside my files, for the sweep:** `backend/tests/test_briefing.py` uses the first name, and several
  `backend/tests/traces/*/run.json` and `data/routines/*/patches.json` files hold absolute paths that include the Mac's
  user name.

## For other sessions

- **docs-folder:**
  - `docs/meta-feedback.md` stops at Oct 28. The submission's feedback now has Nov 1–2 items the log doesn't: the
    allowed-list step for a new tool, one post per Muse turn, and Wonder's off-screen repair reasons.
  - `docs/phase-5-results.md` still names `scripts/make_icons.py`.
- **The coordinator, after the eval:** update the README's "Results so far" rows and the submission's "Final numbers"
  column from `report.md`. Then change "Development numbers, not final" and the line under it. Nothing parses
  README.md, so the site build isn't affected.

## For the user to decide

- Keep Muse's quote (item 2)?
- Publish the two Muse claims (item 1) before their evidence is in the repo, or hold them?
