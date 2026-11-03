# Envoy's showcase site

A guided tour of Envoy for judges and other readers, built only from real recordings, captures and eval results in this
repo. Five sections tell one story, the same one as the demo video, then an evidence appendix keeps the rest:

- **1, the idea:** "Muse has a computer. Envoy gives it a phone." One plain line on what Envoy is, how an agent, Envoy,
  Envoy's phone and the person's iPhone fit, one live post start to finish, and three numbers.
- **2, learns:** a first run step by step, the checked routine a verified run can be compiled into, first run vs routine on
  real apps, a new input, repairs,
  and a routine shared as an agent's tool; Meta's models by job.
- **3, acts:** the four app-only posts (how each was made, its rehearsals, its live post), the Spark agent's one-request dry
  run, Muse's dry run, and "only a person approves".
- **4, watches:** real comments on the live posts reaching the iPhone, the trigger kinds, and how an agent hears.
- **5, results:** real apps first (one pass per row, then first run vs routine as medians with their range), SkyLark second
  as the stress test, AndroidWorld framed by cost, and the limits.
- **Evidence** (not numbered, every group closed until clicked): every run cited with its date, phone, commit, profile and
  task ids; the Starbucks routine, call by call; all 50 SkyLark repairs; real apps workflow by workflow; the design's
  targets and charts; the share switch; SAM; safety tests; agent keys; Claude Code; teach mode; memory; how it's built.

Task ids and commits stay out of the five sections' prose (each number names its model profile); they live in the evidence.

It is static: no server, no analytics, no third-party calls (fonts are self-hosted). It's light by default, whatever the
device's setting; the sun/moon button in the top bar switches to dark and is remembered in that browser.

## View it

Online: https://sanjeevexe.github.io/envoy/ (GitHub Pages, from `.github/workflows/pages.yml`, which uploads `site/` as it
is on every push to main that touches it).

Locally: open `site/index.html` in a browser. It works from `file://` because the data is a script (`data/site-data.js`),
not a fetch.

Source links on the page point at the repo on GitHub (`REPO_URL` in `scripts/build_site_data.py`,
`https://github.com/sanjeevexe/envoy/blob/main/`). Set it to `""` and rebuild to make them relative to `site/`
(`../eval/results/...`) instead; then serve the repo root and open `/site/` to follow them:

```bash
python3 -m http.server 8765 --bind 127.0.0.1
```

URL parameters for links and screenshots: `?step=N` opens the first run (section 2) at step N (the default is 2, the first
recorded frame); `?only=<section id>` shows one section alone (`claim`, `learns`, `acts`, `watches`, `results`, `evidence`;
headless Chrome captures from the top of the page); `?open=1` opens every evidence group; `#ev-<group>` opens one (`#ev-runs`).

## Rebuild it

```bash
uv run --project backend python scripts/build_site_data.py
```

This reads only committed files and writes `site/data/` (`site-data.js`, `site-data.json`, `numbers.json`, and the webp
copies of charts, diagrams, captures and patch evidence in `img/`). To check that a rebuild changes nothing, run it on a clean
checkout and then `git diff --exit-code site/data`: it prints nothing and exits 0.

**After the Nov 3 eval:** `eval/run_final.py report` rewrites `eval/results/final/`. Run the command above and commit `site/data/`.
The "final numbers after Nov 3" markers go away by themselves: the results banner reads `report.md`'s "Ran on" line, and
`real.json`'s `is_eval_final` turns its pass into the "Final evaluation" row of the real-app table and the source of every
real-app median (section 1's "Learns" number, section 2, section 5). `numbers.json` lists every suite with its commit and
whether it is final. If a file's wording changes, the build stops with an error rather than show a wrong number.

**What else the build parses** (it stops with an error if the wording changes, so a docs edit can't put a wrong number on the
page):
- `eval/results/final/real.json` and `real.md` ("Rows come from N runs"), and the cost curve's pass's `real.json`;
- `README.md`'s cost-curve table ("**The cost curve.**"; columns Pass, Workflows, The agent's first run, Envoy's replay,
  Compiling it, once): the row for the curve's pass must give the site's numbers, or the build stops. It's skipped while the
  README has no such table or the row says TBD;
- each pass's `real.md` (the "Stage | Passed" table) and the Oct 31 README's "Stage" table (its two Oct 29 columns);
- `docs/androidworld-results.md` ("**Headline.**", "**Held-out half:**", the "**Routines.**" bullets, the "| Model |" row);
- each suite's JSON beside `report.md` (`meta.models`: the profile and tier named on the page; hybrid when Muse Wonder
  decides the agent's steps, else the Spark profile);
- `docs/phase-6-results.md` ("SAM then grounding N of N; grounding alone N of N");
- `eval/results/androidworld/2026-11-03-hybrid-7ed4aa6/summary.json` (its `stage` names the date, profile and commit) and
  `compare_final-standard.json`;
- `eval/results/showcase/live-2026-11-02/task-rows.json` (with the build's note for the songless TikTok, keyed by task id;
  every other row must be "done");
- `prompts/phone-watch-report.md` (the Stage 2 table with "Landed on the Pixel");
- `eval/results/showcase-batch/RESULTS.md` (its per-workflow table: the build's counts from the attempts must match it);
- `eval/results/learn-agent-path/README.md` (its two "**Agent path:** … **Learn rate:** … **New input:**" headlines must match
  the counts from `results.json` and `supplementary.json`);
- `eval/results/showcase/runs/runs.md`; `eval/results/showcase/muse-2026-11-02/task-rows.json` (with the build's own notes for
  the two Story tasks, keyed by task id);
- `agents/meta-agent/evidence/2026-11-01/crosspost/README.md` (run 2's commit);
- `data/routines/<name>/index.json` for the four posting routines: the build's wording of each one's hand edits
  (`HAND_EDITS`) is checked against the version's own changes;
- `backend/api/scheduler.py` (`KINDS`), `backend/api/auth.py` (`TOOL_GROUPS`) and `backend/api/agents.py` (`RUN_PER_MINUTE`).

### Re-importing recordings (rarely needed)

Run traces and phone frames are gitignored, so a few were copied into `site/data/recordings/` and `site/data/img/` once:

```bash
uv run --project backend python scripts/build_site_data.py import
```

`import` reads the Oct 30 reliability loop's checkout (`.claude/worktrees/loop-reliability-b4a982`) and its API copy (a
scratchpad folder, read with `sqlite3` in read-only mode), the main checkout's `data/runs/` and `data/demo/memory.db` (the demo
world, read only), and teach mode's recordings in the sessions' shared notes folder (`teach-recordings/`). Those folders may be gone later; the
imported copies are what the site uses. Any new frame must be looked at for private data before it is added (checklist below).

## Where every number comes from

Section numbers are positions on the page (the page numbers itself); "E:" is a group in the evidence appendix.

| Section | What it shows | Source |
| --- | --- | --- |
| 1. The idea | The one-liner and the plain line | The words are in `site/index.html` |
| 1 | One post, start to finish; the four posts and which went live | `eval/results/showcase/live-2026-11-02/task-rows.json` (the live API's rows for the five real posts, read read-only); "live" for each done row, per `docs/demo-showcase.md` |
| 1 | Learns: first run vs routine, medians over the real-app workflows | the cost curve's pass (see section 5) |
| 1 | Watches: 1.57 s | `prompts/phone-watch-report.md` (see section 4) |
| 2. Learns | Starbucks first run: each step's frame, tapped element, reason, time, calls and dollars so far; the run's total; its compile | `eval/results/real-apps/loop-a/runs.jsonl`; `site/data/recordings/starbucks-first.json` (imported from the run's trace, its API copy and its model-cost log) |
| 2 | Then it replays: first run vs routine on real apps (medians, ranges); compile cost | the cost curve's pass (see section 5) |
| 2 | Starbucks's own replays and first runs (medians, ranges, 8 code versions) | `eval/results/real-apps/loop-a/runs.jsonl` (task `starbucks`/`starbucks2`, ok rows) |
| 2 | A new input (Caramel Macchiato, one run); new inputs pass by pass | `runs.jsonl`; `eval/results/real_rerun_2026-10-31/README.md` |
| 2 | Real-app self-repairs proposed and kept; the Reel's and Short's repairs and their trials | `data/routines/*/index.json` (versions with a `source_task`); trials matched to `eval/results/showcase/muse-2026-11-02/task-rows.json` |
| 2 | SkyLark, 50 injected changes | `eval/results/final/change.md` |
| 2 | "Make it a routine", measured on the eval-final tag: the agent path, routines saved, new inputs, what wasn't saved and why; the empty-library pass | `eval/results/learn-agent-path/results.json` and `supplementary.json` (counted by the build, retry rows left out), checked against the headlines in its `README.md` |
| 2 | The Spark agent's Envoy tools and its first call | `agents/meta-agent/evidence/2026-11-01/crosspost/run2-four-posts.json` |
| 2 | Muse saw a new tool without reconnecting | **No file in the repo** (pre-check P1, Nov 1). The page says so |
| 2 | Meta's models by job; SAM then grounding 52 of 52, grounding alone 49 | `docs/phase-6-results.md` (Results, the fresh sample) |
| 3. Acts | Each posting routine: version, steps, inputs, how it was made (hand edits), automatic repair | `data/routines/<name>/index.json` and `v<active>.yaml`; `HAND_EDITS` in the build, checked against them |
| 3 | The posting batch on the final tag, per routine: reached the final button, every check yes, median seconds to the final button, Envoy's model calls, the version it ran, what stopped its runs and its songs | `eval/results/showcase-batch/attempts/*.json` (counted by the build), checked against `RESULTS.md`'s per-workflow table; the Story's "every check yes" cell (the poll read by eye) is shown as RESULTS.md writes it |
| 3 | After the batch, not part of it: the Reel's v4 and its device check (5 of 5 cold Reels to Share) | `data/routines/instagram_reel_song/index.json` (v4's `verification.device`) |
| E: batch | Each of the 40 attempts: start, song, class, reached, the clip, song and text checks, calls | `eval/results/showcase-batch/attempts/*.json` |
| 3 | The real posts: what each carried (its inputs), Envoy's model calls, and the songless TikTok in the build's words (`LIVE_NOTES`, from the file's notes) | `eval/results/showcase/live-2026-11-02/task-rows.json` |
| 3 | The Spark agent's four-post dry run: request, calls, asks, answers, its calls and dollars; two captures | `agents/meta-agent/evidence/2026-11-01/crosspost/` (event log, README, PNGs) |
| 3 | Muse's Nov 2 dry run: five tasks, how each ended, calls, time | `eval/results/showcase/muse-2026-11-02/task-rows.json` (the live API's rows, read read-only); the Story notes are the build's words for the file's notes |
| 3 | Muse for Mac's outbox; "there's no accept or approve tool" | `eval/results/muse-link/` (Oct 29) |
| 3 | Only a person approves: per-agent keys, 30 a minute, a read-only key's refusal; 20/20 caught, 0 of 20 followed | `backend/api/auth.py`, `backend/api/agents.py`, `agents/meta-agent/evidence/2026-11-01/readonly-key-run.json`; `eval/results/final/safety.md`, `injection.md` |
| 4. Watches | Real comments → the iPhone (+1.57 s Instagram; YouTube ~2 min; TikTok none) | `prompts/phone-watch-report.md` › Stage 2 (table copied) |
| 4 | Six trigger kinds; Muse's scheduled task | `backend/api/scheduler.py` (`KINDS`); `eval/results/muse-link/e1-muse-tells-you-unprompted.jpg` (cropped) |
| 5. Results | The banner | `eval/results/final/report.md` ("Ran on") |
| 5 | Real apps, one pass per row | each pass's own published stage table: `eval/results/final/real.md` (Oct 28 until the eval, then the final row), `eval/results/real_rerun_2026-10-31/real.md`, `eval/results/real_rerun_2026-11-02_wsd-baseline/real.md`; the two Oct 29 passes from `eval/results/real_rerun_2026-10-31/README.md` (its Oct 28 column is left out: its first-run cell is real.json's 13, the published table says 14) |
| 5 | First run vs routine (calls, time, cost) and compiling once: the cost curve | `eval/results/real_rerun_2026-11-02_wsd-baseline/real.json` (the newest full pass on the hybrid profile, `REAL_CURVE`) until the eval, then `eval/results/final/real.json`. Medians and ranges over the workflows whose first run and same-input rerun both passed, with no repair (`agent`, `routine_runs` "same input", `compile.cost_usd`). The README's cost curve uses the same pass and rule, and the build checks they agree |
| 5 | Posting routines' rehearsals, all four | `runs.md`, as in section 3 |
| 5 | SkyLark suites | `eval/results/final/report.md` (suites 0–3b, 5–7) |
| 5 | Pixel 5: 30/30, 0 calls | `eval/results/final/sizes.json` (devices.phone) |
| 5 | AndroidWorld, Oct 28–29 (the Spark profile): the held-out half, the routines by cost | `docs/androidworld-results.md` (Headline, Routines) |
| 5 | AndroidWorld, the shipped default (hybrid) on main, Nov 3: overall, held-out, median cost and time per task; the held-out change from Oct 28 and its p value | `eval/results/androidworld/2026-11-03-hybrid-7ed4aa6/summary.json` and `compare_final-standard.json` (`AW_HYBRID` in the build) |
| 5 | Limits | the sections above, plus `docs/cloud.md` |
| E: runs | Every run cited: when, where, commit, profile, task ids | the files above; the first run's profile from its model calls |
| E: routine | The Starbucks routine as compiled and v4; every model call; one replay's steps; versions | `eval/results/real-apps/loop-a/compiled/loop_starbucks-v1.yaml`, `data/routines/starbucks_drink_calories/`, `site/data/recordings/starbucks-replay.json`, `starbucks-repair.json` |
| E: repairs | SkyLark's extra-screen repair; 50 changes by layout; real-app self-repairs | `eval/results/final/change.json`, `change.md`, `eval/results/final/library/change/check_in-L3/`, `data/routines/*/index.json` |
| E: real | Each real-app workflow | the cost curve's pass |
| E: targets | Design targets, four charts | `eval/results/final/report.md`, `eval/results/final/charts/` |
| E: tools | The tool list before and after one share switch; the tool; one call; Settings › Agent tools; the Spark agent calling it by name | `eval/results/agent-door/`; `agents/meta-agent/evidence/2026-11-01/routine-tool-run.json` and `.png` |
| E: models | SAM 3.1 on the seat map; 52 targets | `site/data/recordings/sam.json`, `eval/results/phase6/vision.json`, `docs/phase-6-results.md` |
| E: safety | The approval record; the planted screen | `site/data/recordings/approval.json`, `planted.json`; `safety.md`, `injection.md` |
| E: keys | Tool groups; Settings › Agents; the read-only key | `backend/api/auth.py`; `eval/results/agent-door/agent-tools-new-1080p.png` (cropped); `readonly-key-run.json` and `.png` |
| E: claude | Claude Code's tasks | `agents/meta-agent/evidence/2026-11-01/claude-code/task-rows.json` |
| E: teach | The Calendar demonstration, its routine and replay; SkyLark | `site/data/recordings/teach.json`; `eval/results/real-apps/table.md` |
| E: memory | Facts and sources; extraction; stale facts | `site/data/recordings/memory.json`; `eval/results/final/memory.md` |
| E: built | Diagrams; what Envoy built; plumbing; test functions | `docs/diagrams/`, `THIRD_PARTY.md`, `backend/tests/` (counted at each build) |

Numbers measured on SkyLark, Envoy's own test app, carry an "Our test app" label wherever they appear, and SkyLark appears in
the five sections only as the stress test.

## Privacy checklist

Every image on the site was looked at, at full size, before it was added. Accounts: SkyLark (our test app, test persona), the
envoy3955 test Google account, and the test accounts on Envoy's phone. The Starbucks frames show no account details.

| Image(s) | What it shows | Checked |
| --- | --- | --- |
| `img/starbucks-first-02` … `08` | Starbucks on envoy-real, Oct 30: location prompt, empty café map (location denied), menu, search, Caffè Latte | No account, no location, no names |
| `img/repair-skylark-before`, `-after`, `img/approval-skylark`, `img/planted-trip-notice`, `img/sam-seat-map` | SkyLark screens: the test persona (Maya Patel), test bookings, a test known traveler number | Test app data only |
| `img/teach-shown-01` … `07`, `img/teach-replay-01` … `07` | Google Calendar on envoy-real, the envoy3955 test account: the Halloween holiday, a new "Dentist" event, the time picker, the saved events | Test account only; no other events or contacts |
| `img/chart-*`, `img/diagram-*` | Eval charts and design diagrams | No personal data |
| `img/agents-spark-four-asks`, `agents-spark-all-declined`, `tools-spark-by-name`, `keys-spark-read-only` | The Spark agent's page (1920×1080 headless captures, Nov 1) against Envoy test copies on 127.0.0.1: tool calls, task ids, SkyLark's test persona | No keys, no handles, no tailnet name |
| `img/muse-mac-outbox` | Muse for Mac moving a test clip (pier-sunset.mp4) into Envoy's outbox, Oct 29 | Cropped to Muse's window (the Dock and desktop left out); no account names |
| `img/muse-no-accept-tool` | Muse in the iPhone app declining to accept Envoy's offers, Oct 29 | Test files and SkyLark triggers only |
| `img/muse-watches-updates` | Muse's scheduled task reporting a phone update, Oct 29 | Cropped below the status bar: the Dynamic Island showed the phone owner's now-playing album art |
| `img/tools-settings-agent-tools`, `img/keys-settings-agents` | Envoy's Settings › Agents on agent-door's test copy (SkyLark demo data), two crops of one capture | Muse's key is named only by its variable, never shown |

Left out on purpose: DoorDash frames (addresses), Lyft and Uber (the author's own accounts),
Instagram feed and profile frames, YouTube's upload screen (`recon/91-yt-upload-details.png` names the test channel's handle),
TikTok frames (other people's videos and nearby places), the cross-post's approval screenshots (kept outside the repo),
`eval/results/phase5/` iPhone screenshots (tailnet host name), `muse-link/e1` uncropped (album art), Starbucks v3's repair
frames (real but identical before and after, so they'd mislead), anything from the author's own phone or apps, the live API's
data, `data/api/session_token` and `.env` (never read). The test accounts' handles are taken out of the real-post results.

## Fonts

Fraunces and Manrope (`fonts/`, latin subsets of the variable fonts from Fontsource), SIL Open Font License 1.1; the license
texts are beside them. Both are already credited in `THIRD_PARTY.md` for the web app.
