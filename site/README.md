# Envoy's showcase site

A guided tour of Envoy for judges and other readers, built only from real recordings, captures and eval results in this
repo. It tells the Nov 1 frame first: **Envoy is the phone layer agents call** ("Muse has a computer. Envoy gives it a
phone."). It acts in apps, learns each task into a routine, and watches the phone, with Muse or any MCP agent as the front
door and approvals on the person's iPhone. Sixteen sections:

- **1, the phone layer:** the one-liner, how agents, Envoy, its phones and the person's iPhone fit, four headline numbers,
  and the limits.
- **2–6, the layer:** agents call it, learned routines become tools, the app-only posts, watching the phone, a key per agent.
- **7–15, underneath:** a first run, the routine it became, repairs, real apps, teach mode, memory, safety, Meta's models
  and the results. These are the Oct 27–31 proof sections, kept and moved after the layer.
- **16:** how it's built.

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

Two URL parameters help with screenshots: `?step=N` opens the first run (section 7) at step N (the default is 2, the first recorded
frame), and `?only=<section id>` shows one section alone (headless Chrome captures from the top of the page).

## Rebuild it

```bash
uv run --project backend python scripts/build_site_data.py
```

This reads only committed files and writes `site/data/` (`site-data.js`, `site-data.json`, `numbers.json`, and the webp
copies of charts, diagrams, captures and patch evidence in `img/`). Same checkout, same bytes.

**After the Nov 3 eval:** `eval/run_final.py report` rewrites `eval/results/final/`. Run the command above and commit `site/data/`.
The "final numbers after Nov 3" markers go away by themselves: the results section's banner and each suite's marker read
`report.md`'s "Ran on" column (`eval-final` once a suite ran on the tag), and `numbers.json` lists every headline number with its
commit and whether it is final. If the report's wording changes, the build stops with an error rather than show a wrong number.

**What else the build parses** (it stops with an error if the wording changes, so a docs edit can't put a wrong number on the
page): `docs/androidworld-results.md` ("**Headline.**", "**Held-out half:**"), `docs/phase-5-results.md` (the "Voice,
scripted" row), `prompts/showcase-report.md` (the real-posts table: Post, Task, Routine, Result), `prompts/phone-watch-report.md`
(the Stage 2 table with "Landed on the Pixel"), `eval/results/showcase/runs/runs.md`, `backend/api/scheduler.py` (`KINDS`),
`backend/api/auth.py` (`TOOL_GROUPS`) and `backend/api/agents.py` (`RUN_PER_MINUTE`).

### Re-importing recordings (rarely needed)

Run traces and phone frames are gitignored, so a few were copied into `site/data/recordings/` and `site/data/img/` once:

```bash
uv run --project backend python scripts/build_site_data.py import
```

`import` reads loop A's checkout (`.claude/worktrees/loop-reliability-b4a982`), loop A's API copy (a scratchpad folder, read
with `sqlite3` in read-only mode), loop B's checkout (`funny-goldwasser-65190c`, Clock and Google Flights frames only), and
the main checkout's `data/runs/` and `data/demo/memory.db` (the demo world, read only), and teach mode's recordings in the
coordinator's shared notes folder (`teach-recordings/`). Those folders may be gone later; the
imported copies are what the site uses. Any new frame must be looked at for private data before it is added (checklist below).

## Where every number comes from

Section numbers are positions on the page (the page numbers itself).

| Section | What it shows | Source |
| --- | --- | --- |
| 1. The phone layer | The one-liner and the frame | The frame the user adopted on Nov 1; the words are in `site/index.html` |
| 1 | Four headline numbers: 3 agents; 4 posts from 1 request; Starbucks 45.6 s → 14.8 s; 1.57 s | sections 2, 4, 7–8 and 5 below, each from its own file |
| 1 | Limits | `eval/results/final/report.md` suite 4, `eval/results/real_rerun_2026-10-31/README.md`, `docs/cloud.md`, `prompts/phone-watch-report.md`, `prompts/showcase-report.md` |
| 2. Agents call it | The Spark agent's cross-post: the request, each tool call, each ask on the iPhone and how it ended, Spark's words, its calls and dollars | `agents/meta-agent/evidence/2026-11-01/crosspost/run2-four-posts.json` (the agent page's event log), its `README.md`, and `run1-three-posts.json` |
| 2 | Muse's Oct 29 captures (the Mac outbox; no accept or approve tool) | `eval/results/muse-link/`, `docs/muse-link.md` |
| 2 | Muse end to end, Nov 2 (a dry run, every final post declined): its five tasks, their calls and times, and the notes on the two Story failures (#63 fixed in `947bf44`, #64 open) | `eval/results/showcase/muse-2026-11-02/task-rows.json` (the live API's task rows, read read-only by the coordinator) |
| 2 | Claude Code's tasks on the live API (agent "Claude", 0 model calls) and its refusal to approve | `agents/meta-agent/evidence/2026-11-01/claude-code/task-rows.json` and `README.md` |
| 3. Routines become tools | The tool list before and after one share switch, the tool as agents see it, one call to it | `eval/results/agent-door/tools-before.json`, `tools-after.json`, `call.json` |
| 3 | The Spark agent calling `skylark_check_flight_status` by name | `agents/meta-agent/evidence/2026-11-01/routine-tool-run.json` and `.png` |
| 3 | Settings › Agents › Agent tools | `eval/results/agent-door/agent-tools-new-1080p.png` (cropped) |
| 3 | Muse saw a new tool without reconnecting | **No file in the repo** (pre-check P1, Nov 1). The page says so |
| 4. App-only posts | Each routine's first run (the agent) and the replays of its active version | `eval/results/showcase/runs/runs.md` (rows copied; replays after the active version was compiled, per its `compiled_from.compiled_at`) |
| 4 | Each routine's version, steps, inputs and how it was made | `data/routines/<name>/index.json` and `v<active>.yaml` |
| 4 | The real posts, Nov 2 | `prompts/showcase-report.md` › "The real posts" (each Result cell's first sentence; test accounts' handles taken out) |
| 4 | The poll sticker frame | `eval/results/showcase/recon/20-ig-story-with-poll.png` (P3, by hand, before the routine) |
| 5. Watches | The six trigger kinds | `backend/api/scheduler.py` (`KINDS`) |
| 5 | Real comments → the iPhone: +0.66 s stored, +0.78 s push sent, +1.57 s shown (Instagram); YouTube's ~2 min; TikTok none | `prompts/phone-watch-report.md` › Stage 2 (table copied) |
| 5 | Muse's scheduled task polling `phone_updates` every 10 min | `eval/results/muse-link/e1-muse-tells-you-unprompted.jpg` (cropped below the status bar) |
| 6. A key per agent | Tool groups; 30 run calls a minute | `backend/api/auth.py` (`TOOL_GROUPS`), `backend/api/agents.py` (`RUN_PER_MINUTE`) |
| 6 | The Spark agent on a read-only key: 6 tools, an unknown tool refused, "only you can approve" | `agents/meta-agent/evidence/2026-11-01/readonly-key-run.json` and `.png` |
| 6 | Settings › Agents (Add an agent) | `eval/results/agent-door/agent-tools-new-1080p.png` (cropped) |
| 7. First run | Starbucks first run: 45.6 s, 12 calls, $0.0795; each step's frame, tapped element, reason, time, calls and dollars so far | `eval/results/real-apps/loop-a/runs.jsonl`; `data/recordings/starbucks-first.json`, imported from loop A's trace (`steps.jsonl`, trees with element bounds), its API copy (one frame per action) and its model-cost log |
| 8. Learned | The compiled routine; the active v4; versions; compile cost (41.5 s, $0.0806); replay 14.8 s, 2 calls, $0.005; new input 15.8 s | `eval/results/real-apps/loop-a/compiled/loop_starbucks-v1.yaml`, `data/routines/starbucks_drink_calories/`, `runs.jsonl` (mode compile) |
| 8 | The replay's step timings and rungs | `data/recordings/starbucks-replay.json` (loop A's trace) |
| 9. Repairs | SkyLark extra-screen repair: frames, reason, diff, trial | `eval/results/final/change.json`, `eval/results/final/library/change/check_in-L3/` |
| 9 | 50 injected changes by layout; new inputs 50/50 | `eval/results/final/change.md` |
| 9 | Real-app self-repairs: 1 kept, 4 rejected by trial; Starbucks v3's Wonder call | `data/routines/*/index.json`; `data/recordings/starbucks-repair.json` (loop A's cost log) |
| 10. Real apps | Each app's first runs and replays (cells copied verbatim) | `eval/results/real-apps/table.md`; versions and steps from `data/routines/<id>/` |
| 11. Teach it | The Calendar demonstration (7 steps, 14.5 s), its routine ($0.0529), the replay (7/7, 0 calls, 6.2 s); SkyLark flight status | `data/recordings/teach.json`, imported from teach mode's recordings (the shared notes folder's `teach-recordings/`, made by `eval/teach_person.py` on Oct 31) |
| 11 | Why Calendar: the Oct 30 loops' Calendar rows | `eval/results/real-apps/table.md` |
| 12. Memory | Facts, sources, replaced seat, cancelled trip | `data/recordings/memory.json` (the demo world's `memory.db`, read only) |
| 12 | Extraction 459/468, stale 0 of 12, the four ages | `eval/results/final/memory.md` |
| 13. Safety | 20/20 caught, 0/22 false flags; 20/20 with planted text, 0 followed; 0 values from planted emails | `eval/results/final/safety.md`, `eval/results/final/injection.md` |
| 13 | The approval record; the planted screen and the agent's reasons | `data/recordings/approval.json` (loop A's API copy), `data/recordings/planted.json` (`data/runs/f7-1028004422-inj-trip_notice-add_ktn-agent-r0`) |
| 14. Models | Wonder and Spark calls per job | the Starbucks recordings above |
| 14 | Voice: heard exactly, final text 90 to 93 ms | `docs/phase-5-results.md` (Voice, scripted) |
| 14 | SAM 3.1 on the seat map; 52 targets: 37% / 92% / 75% | `data/recordings/sam.json` (`data/runs/p6-canvas-src`), `eval/results/phase6/vision.json`, `docs/phase-6-results.md` |
| 15. Results | Suites, targets, charts | `eval/results/final/report.md`, `eval/results/final/charts/` |
| 15 | Pixel 5: 30/30, 0 calls | `eval/results/final/sizes.json` (devices.phone; Oct 28, `a9b923d`) |
| 15 | AndroidWorld | `docs/androidworld-results.md` (Headline; held-out half) |
| 15 | Test functions (counted at each build) | counted from `backend/tests/` by the build (a parametrized test counts once) |
| 16. How it's built | Diagrams; what Envoy built; open-source plumbing | `docs/diagrams/`, `THIRD_PARTY.md` |

Numbers measured on SkyLark, Envoy's own test app, carry an "Our test app" label wherever they appear.

## Privacy checklist

Every image on the site was looked at, at full size, before it was added. Accounts: SkyLark (our test app, test persona), the
envoy3955 test Google account, and the test accounts on Envoy's phone. The other real-app frames (Starbucks, Chipotle, Amazon,
YouTube, Play Store, Clock, Chrome) show no account details.

| Image(s) | What it shows | Checked |
| --- | --- | --- |
| `img/starbucks-first-02` … `08` | Starbucks on envoy-real, Oct 30: location prompt, empty café map (location denied), menu, search, Caffè Latte | No account, no location, no names |
| `img/app-amazon`, `app-youtube`, `app-play`, `app-chipotle` | Search results, a video list, Duolingo's store page, Chipotle's sides menu | No account details; YouTube's avatar is the test account's letter |
| `img/app-gmail` | A DoorDash promo email in the envoy3955 test inbox | Test account only |
| `img/app-starbucks` | The Caffè Latte page, 190 calories | Clean |
| `img/app-clock`, `img/app-flights` | A 7:00 AM alarm on envoy-real; a public Google Flights results page | Clean |
| `img/repair-skylark-before`, `-after`, `img/approval-skylark`, `img/planted-trip-notice`, `img/sam-seat-map` | SkyLark screens: the test persona (Maya Patel), test bookings, a test known traveler number | Test app data only |
| `img/teach-shown-01` … `07`, `img/teach-replay-01` … `07` | Google Calendar on envoy-real, the envoy3955 test account: the Halloween holiday, a new "Dentist" event, the time picker, the saved events | Test account only; no other events or contacts |
| `img/chart-*`, `img/diagram-*` | Eval charts and design diagrams | No personal data |
| `img/agents-spark-four-asks`, `agents-spark-all-declined`, `tools-spark-by-name`, `keys-spark-read-only` | The Spark agent's page (1920×1080 headless captures, Nov 1) against Envoy test copies on 127.0.0.1: tool calls, task ids, SkyLark's test persona | No keys, no handles, no tailnet name |
| `img/muse-mac-outbox` | Muse for Mac moving a test clip (pier-sunset.mp4) into Envoy's outbox, Oct 29 | Cropped to Muse's window (the Dock and desktop left out); no account names |
| `img/muse-no-accept-tool` | Muse in the iPhone app declining to accept Envoy's offers, Oct 29 | Test files and SkyLark triggers only |
| `img/muse-watches-updates` | Muse's scheduled task reporting a phone update, Oct 29 | Cropped below the status bar: the Dynamic Island showed the user's now-playing album art |
| `img/tools-settings-agent-tools`, `img/keys-settings-agents` | Envoy's Settings › Agents on agent-door's test copy (SkyLark demo data), two crops of one capture | Muse's key is named only by its variable, never shown |
| `img/showcase-story-poll` | Instagram's Story editor on Envoy's phone with a poll sticker over a test-pattern clip (P3, Nov 1) | Test account; no handle on screen |

Left out on purpose: DoorDash frames (addresses), Lyft and Uber (the user's own accounts; Lyft appears as numbers only),
Instagram feed and profile frames, YouTube's upload screen (`recon/91-yt-upload-details.png` names the test channel's handle),
TikTok frames (other people's videos and nearby places), the cross-post's approval screenshots (kept outside the repo),
`eval/results/phase5/` iPhone screenshots (tailnet host name), `muse-link/e1` uncropped (album art), Starbucks v3's repair
frames (real but identical before and after, so they'd mislead), anything from the user's own phone or apps, the live API's
data, `data/api/session_token` and `.env` (never read). The test accounts' handles are taken out of the real-post results.

## Fonts

Fraunces and Manrope (`fonts/`, latin subsets of the variable fonts from Fontsource), SIL Open Font License 1.1; the license
texts are beside them. Both are already credited in `THIRD_PARTY.md` for the web app.
