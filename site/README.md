# Envoy's showcase site

A guided tour of Envoy for judges, in ten sections, built only from real recordings and eval results in this repo. It is
static: no server, no analytics, no third-party calls (fonts are self-hosted). It follows the system's light or dark setting.

## View it

Open `site/index.html` in a browser. It works from `file://` because the data is a script (`data/site-data.js`), not a fetch.

Source links on the page point at the repo's files relative to `site/` (`../eval/results/...`), so they work from a checkout.
To browse with working links, serve the repo root and open `/site/`:

```bash
python3 -m http.server 8765 --bind 127.0.0.1
```

Then open `http://127.0.0.1:8765/site/`. Once the repo is public, set `REPO_URL` in `scripts/build_site_data.py` (for example
`https://github.com/<owner>/<repo>/blob/main/`) and rebuild; every source link then points there.

Two URL parameters help with screenshots: `?step=N` opens section 2's run at step N (the default is 2, the first recorded
frame), and `?only=<section id>` shows one section alone (headless Chrome captures from the top of the page).

## Rebuild it

```bash
uv run --project backend python scripts/build_site_data.py
```

This reads only committed files and writes `site/data/` (`site-data.js`, `site-data.json`, `numbers.json`, and the webp
copies of charts, diagrams and patch evidence in `img/`). Same checkout, same bytes.

**After the Nov 2 eval:** `eval/run_final.py report` rewrites `eval/results/final/`. Run the command above and commit `site/data/`.
The "final numbers after Nov 2" markers go away by themselves: section 9's banner and each suite's marker read `report.md`'s
"Ran on" column (`eval-final` once a suite ran on the tag), and `numbers.json` lists every headline number with its commit and
whether it is final. If the report's wording changes, the build stops with an error rather than show a wrong number.

### Re-importing recordings (rarely needed)

Run traces and phone frames are gitignored, so a few were copied into `site/data/recordings/` and `site/data/img/` once:

```bash
uv run --project backend python scripts/build_site_data.py import
```

`import` reads loop A's checkout (`.claude/worktrees/loop-reliability-b4a982`), loop A's API copy (a scratchpad folder, read
with `sqlite3` in read-only mode), loop B's checkout (`funny-goldwasser-65190c`, Clock and Google Flights frames only), and
the main checkout's `data/runs/` and `data/demo/memory.db` (the demo world, read only). Those folders may be gone later; the
imported copies are what the site uses. Any new frame must be looked at for private data before it is added (checklist below).

## Where every number comes from

| Section | What it shows | Source |
| --- | --- | --- |
| 1. The claim | The claim and "what's new" | `docs/technical-design.md` › Overview |
| 1, 2, 3 | Starbucks first run: 45.6 s, 12 calls, $0.0795; replay 14.8 s, 2 calls, $0.005; new input 15.8 s | `eval/results/real-apps/loop-a/runs.jsonl` (task ids on the page) |
| 1 | Limits: 4 of 11 new-input reruns (Oct 28); 15 of 15 (Oct 30) | `eval/results/final/report.md` suite 4; `eval/results/real-apps/table.md` |
| 2 | Each step's frame, tapped element, reason, time, calls and dollars so far | `data/recordings/starbucks-first.json`, imported from loop A's trace (`steps.jsonl`, trees with element bounds), its API copy (one frame per action) and its model-cost log |
| 3 | The compiled routine; the active v4; versions; compile cost (41.5 s, $0.0806) | `eval/results/real-apps/loop-a/compiled/loop_starbucks-v1.yaml`, `data/routines/starbucks_drink_calories/`, `runs.jsonl` (mode compile) |
| 3 | The replay's step timings and rungs | `data/recordings/starbucks-replay.json` (loop A's trace) |
| 4 | SkyLark extra-screen repair: frames, reason, diff, trial | `eval/results/final/change.json`, `eval/results/final/library/change/check_in-L3/` |
| 4 | 50 injected changes by layout; new inputs 50/50 | `eval/results/final/change.md` |
| 4 | Real-app self-repairs: 1 kept, 4 rejected by trial; Starbucks v3's Wonder call | `data/routines/*/index.json`; `data/recordings/starbucks-repair.json` (loop A's cost log) |
| 5 | Each app's first runs and replays (cells copied verbatim) | `eval/results/real-apps/table.md`; versions and steps from `data/routines/<id>/` |
| 6 | Facts, sources, replaced seat, cancelled trip | `data/recordings/memory.json` (the demo world's `memory.db`, read only) |
| 6 | Extraction 459/468, stale 0 of 12, the four ages | `eval/results/final/memory.md` |
| 7 | 20/20 caught, 0/22 false flags; 20/20 with planted text, 0 followed; 0 values from planted emails | `eval/results/final/safety.md`, `eval/results/final/injection.md` |
| 7 | The approval record; the planted screen and the agent's reasons | `data/recordings/approval.json` (loop A's API copy), `data/recordings/planted.json` (`data/runs/f7-1028004422-inj-trip_notice-add_ktn-agent-r0`) |
| 8 | Wonder and Spark calls per job | the Starbucks recordings above |
| 8 | Voice: heard exactly, final text 90 to 93 ms | `docs/phase-5-results.md` (Voice, scripted) |
| 8 | SAM 3.1 on the seat map; 52 targets: 37% / 92% / 75% | `data/recordings/sam.json` (`data/runs/p6-canvas-src`), `eval/results/phase6/vision.json`, `docs/phase-6-results.md` |
| 9 | Suites, targets, charts | `eval/results/final/report.md`, `eval/results/final/charts/` |
| 9 | Pixel 5: 30/30, 0 calls | `eval/results/final/sizes.json` (devices.phone; Oct 28, `a9b923d`) |
| 9 | AndroidWorld | `docs/androidworld-results.md` (Headline; held-out half) |
| 9 | 578 test functions in 37 files | counted from `backend/tests/` by the build (a parametrized test counts once) |
| 10 | Diagrams; what Envoy built; open-source plumbing | `docs/diagrams/`, `THIRD_PARTY.md` |

Numbers measured on SkyLark, Envoy's own test app, carry an "Our test app" label wherever they appear.

## Privacy checklist

Every image on the site was looked at before it was added. Accounts: SkyLark (our test app, test persona) and the envoy3955
test Google account only. The other real-app frames (Starbucks, Chipotle, Amazon, YouTube, Play Store, Clock, Chrome) show no
account details.

| Image(s) | What it shows | Checked |
| --- | --- | --- |
| `img/starbucks-first-02` … `08` | Starbucks on envoy-real, Oct 30: location prompt, empty café map (location denied), menu, search, Caffè Latte | No account, no location, no names |
| `img/app-amazon`, `app-youtube`, `app-play`, `app-chipotle` | Search results, a video list, Duolingo's store page, Chipotle's sides menu | No account details; YouTube's avatar is the test account's letter |
| `img/app-gmail` | A DoorDash promo email in the envoy3955 test inbox | Test account only |
| `img/app-starbucks` | The Caffè Latte page, 190 calories | Clean |
| `img/app-clock`, `img/app-flights` | A 7:00 AM alarm on envoy-real; a public Google Flights results page | Clean |
| `img/repair-skylark-before`, `-after`, `img/approval-skylark`, `img/planted-trip-notice`, `img/sam-seat-map` | SkyLark screens: the test persona (Maya Patel), test bookings, a test known traveler number | Test app data only |
| `img/chart-*`, `img/diagram-*` | Eval charts and design diagrams | No personal data |

Left out on purpose: DoorDash frames (addresses), Lyft and Uber (the user's own accounts; Lyft appears as numbers only),
Instagram frames (the Pixel's account), `eval/results/phase5/` iPhone screenshots (tailnet host name), Starbucks v3's repair
frames (real but identical before and after, so they'd mislead), anything from the user's own phone or apps, the live API's
data, `data/api/session_token` and `.env` (never read).

## Fonts

Fraunces and Manrope (`fonts/`, latin subsets of the variable fonts from Fontsource), SIL Open Font License 1.1; the license
texts are beside them. Both are already credited in `THIRD_PARTY.md` for the web app.
