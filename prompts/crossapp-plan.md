# Cross-app answers on separate phones: plan

Worker `crossapp`, branch `claude/cross-app-answers-522e1d`, written Oct 28 03:30 EDT (Stage A: read-only, nothing built).
Stage B starts only on a `GRANT` from the overnight orchestrator.

## 1. The gap, verified

- `docs/technical-design.md` › Agent runtime › "Several phones at once" is still a stretch goal: "a lead agent splits the
  task into subtasks, runs each on its own emulator in parallel, and combines the results".
- Nothing in `backend/` or `web/` implements it: no `subtask`, `parent` or orchestrator code anywhere (grep, Oct 28).
- The pitch (design doc, line 16) lists "Cross-app answers: compare prices across delivery or ride apps"; today a request
  naming two apps becomes one task in one app on one phone (`runner.app_for` returns a single app).

What already exists and is reused unchanged:

| Piece | Where | Why it matters here |
| --- | --- | --- |
| One task, end to end: matcher → routine (repair, agent fallback) → agent | `api/runner.py` `TaskRunner.start/_run` | each subtask is an ordinary task |
| Phone choice: SkyLark → envoy-test, real apps → envoy-real, your phone on request | `api/routing.py` `choose` | each subtask's phone |
| One task per phone: `Lease.run_lock`, with a "waiting for envoy-real" step | `api/devices.py`, `runner._run` | same-phone subtasks queue for free |
| Model and device calls run in threads (`asyncio.to_thread`) | agent loop, executor, `devices/android.py` | two `_run`s on two phones really overlap |
| Approvals through the gate, per task | `api/approvals.py` `WebApprover` | subtasks ask like any task |
| Memory with provenance: routine runs and final screens as sources (app, screen, task, time) | `memory/bridge.remember_run`, `MemoryService.ingest_screen` | each subtask's facts are saved as today |

## 2. Design

```
chat("What's a Grande Caffè Latte's calories at Starbucks, and DoorDash's first latte place?")
  │ code pre-filter: does it name ≥2 apps, or 1 app + a comparison/"and" clause?  ── no ──▶ normal chat path, untouched
  ▼ yes
lead step: 1 Muse Spark call (standard tier, structured output) ─ not multi-app ─▶ normal chat path (same calls as today)
  ▼ 2–4 parts: {app, goal, label, inputs[{name, value}]}
parent task (kind "crossapp", source/request = the user's words)
  ├─ child 1: runner.start(goal, app, inputs, parent) → matcher → routine/agent → envoy-real
  └─ child 2: runner.start(goal, app, inputs, parent) → matcher → routine/agent → envoy-real (queues) / envoy-test (overlaps)
  ▼ all children ended (done / failed / declined / needs_you timed out / stopped)
combine: 1 Muse Spark call → one sentence; every value checked against its child's result; sources added in code
  ▼
parent result: "Starbucks says 190 calories for a Grande Caffè Latte; DoorDash's first latte place is …"
   + per value: app · screen · time   →  memory: a Note with a "cross-app answer" source naming each child task
```

### 2.1 Lead step (`api/crossapp.py`)

- **Pre-filter in code, no model call.** `apps_in(message)`: the apps named (`runner.APP_NAMES`, the apps of active
  routines by their display names), SkyLark for travel words (`runner.TRAVEL`), Google Maps for
  drive/directions/commute/traffic/"how far". It fires when it finds two or more apps, or one app plus a comparison or a
  second question (`vs`, `versus`, `compare`, `cheaper`, `both`, `, and what/how/where/when`). A message it doesn't fire
  on goes through today's code byte for byte.
- **One Spark call** with a `JobConfig("lead", "muse-spark-1.3", "low", LeadSplit, max_output_tokens=3000)` defined in
  the module (no edit to `models/`; `adapter.call` accepts a `JobConfig`), `data_scope="real"`, never Contributor.
  Input: the request, and the app catalog: each app with its routines' intents and inputs (name, type, example), as
  data. Output schema:
  `LeadSplit{multi_app: bool, parts: [{app, label, goal, inputs: [{name, value}]}], relation: "compare" | "separate"}`.
- **Checks in code** (like the matcher's "a value must appear in the request"): an unknown app drops its part; an input
  is kept only if its name belongs to a routine of that app and its value appears in the request; at most 4 parts;
  fewer than 2 parts, or one app only, falls back to the normal path. Each part's `goal` must be a self-contained
  instruction (the agent never sees `inputs`), so the goal keeps the user's specifics.
- When the pre-filter fires but the lead says `multi_app=false`, chat continues exactly as today (one extra call; the
  started task is identical; tested).

### 2.2 Subtasks through the product's own path

- `CrossApp.start(message, split, source)` creates the parent (`store.create(message, source, kind="crossapp",
  request=message)`), registers its coroutine in `runner.jobs[parent]` (so the existing Stop button cancels it), and
  calls `runner.start(part.goal, source, inputs=part.inputs, app=part.app, request=message, parent=parent_id)` per part.
  Children keep the parent's source and the user's own words as `request`, so approval rules treat them as the user's.
- The matcher, `version_for_run`, `fill_inputs`, the routine with repair and the agent behind it, sign-in hand-offs and
  routing all run unchanged inside each child.
- **Concurrency comes from the runner as it is:** children on different phones run as separate asyncio tasks; children
  that route to the same phone wait on that phone's `run_lock` (their matcher call still overlaps). The orchestrator
  adds no lock of its own.
- `sequential=True` (an internal option, not in the UI) starts each child only after the previous one ends: the
  baseline for timing, through the same code.

### 2.3 Live status

- A bus listener (`bus.listeners`) follows the children. The parent mirrors them: `running` while any runs,
  `needs_you` / `waiting_approval` when a child waits on you (with that child's reason in `detail`), and its `result`
  fills in as children finish ("Starbucks: 190 calories · DoorDash: checking…").
- The parent's steps record milestones only: the split (app, goal, inputs per part), each child's end (status, phone,
  seconds), the combine, the memory write, and a timeline step `{parts: [{task_id, app, device, queued_at, phone_at,
  ended_at, status}]}` (phone_at = when the child got its phone, from its `device` being set under the lease). That
  timeline is the overlap evidence.

### 2.4 Combine

- One Spark call (`JobConfig("combine", "muse-spark-1.3", "low", CrossAppAnswer)`, standard tier): the question and each
  part's label, app and result text → `{answer, cites: [{part, value}]}`.
- **Verified in code:** each cited value must appear in its part's result (`routines.screens.contains_value`), and every
  number in the answer must appear in some part's result. Otherwise, or if the call fails, the answer is built in code
  from the parts ("Starbucks: calories 190 · DoorDash: first restaurant …").
- **Sources are never written by the model:** per part, code appends `value — app, screen, time`, from a small runner
  hook that hands over the child's final screen (`package`, `activity` short name, `timestamp`) and routine outputs.
- Partial results: a failed, declined or stopped child is named in the answer ("DoorDash: couldn't check (reason)");
  parent `done` if any part answered, `failed` if none did.

### 2.5 Memory

- Each child writes its own facts exactly as any task does (routine outputs and final screen, with the run as source).
- After the children's memory writes finish, the parent writes the combined answer through `MemoryStore`'s public API
  (no edit to `memory/`): a `Note` entity whose `body` is the answer, from a source of kind `cross-app answer` whose
  reference lists the parent task and, per part, `{task_id, app, screen, captured_at}`. Apps blocked from memory
  (`MemoryService.allow_apps`) are left out. `Retriever.where` renders it as "cross-app answer, 2 min ago", so chat can
  answer it again later with its source.

### 2.6 Approvals and safety

- Approvals stay per child and go through `WebApprover` and the gate as today; the inbox shows them with the child's
  goal. A read-only question should create none (asserted in tests and counted in the end-to-end evidence).
- The lead and combine never approve or act; they only plan and write text. Stopping the parent stops every child.

## 3. Files

| File | Change |
| --- | --- |
| `backend/api/crossapp.py` (new, ~350 lines) | pre-filter, `LeadSplit`/`CrossAppAnswer` schemas and prompts, `CrossApp` (start, follow, combine, remember), `sequential` option |
| `backend/api/runner.py` (hook, ~8 lines) | `start(..., parent=None)` passes `parent` to `store.create`; `self.crossapp = None` slot; `self.on_final: list` called with `(tid, final_screen, outputs)` right after the final `observe()` |
| `backend/api/store.py` (hook, 2 lines) | migration adds a `parent TEXT` column, same pattern as `request` (so every task endpoint returns `parent` with no `app.py` change). Fallback if store.py must stay untouched: `crossapp.py` runs the same `ALTER TABLE` on the store's connection |
| `backend/api/chat.py` (hook, ~10 lines) | before the route call: if `runner.crossapp` and the pre-filter fires → lead; ≥2 parts → start the parent and reply "Asking Starbucks and DoorDash at once…"; else the existing code |
| `backend/api/app.py` (1 line) | `runner.crossapp = CrossApp(...)` in `build()` (or done lazily from `chat.py` if app.py must stay untouched) |
| `web/lib/api.ts` (1 line) | `parent?: string \| null` on `Task` |
| `web/components/Tasks.tsx` (additive) | `TaskList` nests children under their parent (each with its app, phone and its own live badge) and hides them from the top level; `TaskDetail` of a crossapp parent shows a Subtasks panel (one card per child: app, phone, live status, result, opens the child) above the steps |
| `web/app/page.tsx` (1 prop) | pass the live task map to `TaskDetail` so child badges update from the existing `task` events (no second websocket, no polling) |
| `backend/tests/test_crossapp.py` (new) | offline tests (§4) |
| `eval/run_crossapp.py` (new), `eval/results/crossapp/` (new) | end to end and evidence (§5) |

Not touched: `backend/agent/`, `backend/routines/`, `backend/policy/`, `backend/memory/`, `backend/models/`, existing
`eval/` files. Optional, with the orchestrator's OK: a two-paragraph update of the design doc's "Several phones at once".

## 4. Offline tests (`backend/tests/test_crossapp.py`, fake devices, fake adapter, no network)

1. **Single-app requests are untouched:** a message the pre-filter doesn't fire on makes only the `chat` call, and
   `runner.start` gets exactly the arguments today's chat gives (recorded with a spy runner, compared to `main`'s chat).
2. **Lead says one app** ("What's my gate and seat for Denver?" fires the filter): normal path, same `runner.start` call.
3. **Split checks:** an unknown app is dropped; an input not in the request, or not a routine input of that app, is
   dropped; one usable part → normal path; children carry `parent`, the user's `request` and the parent's `source`.
4. **Two phones overlap:** a real `TaskRunner` with a fake pool (leases for envoy-test and envoy-real, fake devices),
   `_plan` returning a routine, and a fake `RoutineExecutor` that sleeps 0.5 s: the children's phone intervals
   intersect, both phones are used, and the parent's wall time is < 0.8 s (not ~1.0 s).
5. **Same phone queues:** two real-app parts: intervals don't intersect, the second child has the "waiting for
   envoy-real" step, wall time ≈ the sum.
6. **`sequential=True`** never has two children on phones at once.
7. **Combine:** cited values that appear in the results are kept; an invented number falls back to the code-built
   answer; each value line has app, screen and time from the final-screen hook; a failing combine call also falls back.
8. **Partial and failed:** one child fails → parent done with that app named; all fail → parent failed.
9. **Live status:** a child waiting on an approval or a sign-in puts the parent in `waiting_approval` / `needs_you`
   with that child's reason; the parent's result fills in as children finish.
10. **Approvals:** a child's approval is created under the child's task id and goes through `WebApprover`; declining
    it ends that child `declined` and the answer says so. The fake read-only runs create no approval.
11. **Stop:** stopping the parent cancels every running child (`stopped`).
12. **Memory:** after combine, a Note with the answer exists, its source is `cross-app answer` with each child's
    task id, app, screen and time; `Retriever.where` renders it; a blocked app is left out.

Then the full suite with `nice -n 10 uv run --project backend pytest backend/tests -q`, and `nice -n 10 npm run build`
in `web/` (with `web/node_modules` symlinked from the main checkout, read-only, or `npm ci` if it isn't there).

## 5. End to end

### Setup (under a GRANT only)

- API copy on **:8713**, run in-process by `eval/run_crossapp.py`: `ENVOY_API_DIR` and memory in my scratchpad, a token I
  generate, `build(memory=MemoryStore(<scratch>/memory.db), routines=RoutineStore(<scratch>/routines))`. The routine
  library is assembled in the scratchpad from `data/routines` (SkyLark) and the Phase 7 real-app routines
  (`eval/results/final/real_compiled/*.yaml` in the main checkout, copied read-only). Push is never configured.
- `.env` symlinked from the main checkout (never printed); `META_DAILY_COST_CAP_USD=2`; standard tier only.
- Before starting an AVD: `pgrep -fl qemu-system` shows at most one other emulator and not this one; start with
  `scripts/start_emulator.sh <avd>`; every adb call uses `adb -s <serial>`.
- Warm-up: one connection per phone before timing (the pool's first connect is serialized), reported separately.
- The script declines every approval it sees, force-stops each subtask's app when that subtask ends
  (`adb -s <serial> shell am force-stop <pkg>`), never asks about Target, and never types into a sign-in.

### Questions

| Id | Question | Parts (expected path) | Phones |
| --- | --- | --- | --- |
| R1 | "How many calories are in a Grande Caffè Latte at Starbucks, and what's the first place DoorDash shows for a latte?" | Starbucks calories routine (drink_name; Grande is preselected) · DoorDash search routine (search_query): 0 model calls each | envoy-real, back to back |
| R2 | "What's a Caffè Latte at Starbucks vs on DoorDash?" (the pitch's price comparison) | no routine for prices: the matcher declines, the agent runs in each app | envoy-real, back to back |
| T1 | "What's my gate for my Denver flight, and what's the address of the Space Needle?" | SkyLark gate routine (trip_city) · Maps address routine (place_name): 0 model calls each | envoy-test ∥ envoy-real |
| T2 | "What's my gate for my Denver flight, and how long is the drive from 1 Hacker Way to SFO?" | SkyLark gate routine · Maps directions by the agent | envoy-test ∥ envoy-real |

SkyLark is seeded with the Denver booking and signed in the way the SkyLark suites do (`eval/skylark_routines.py`
fixtures through `testapps.skylark.SkyLark`), with no snapshot saved or deleted. R2 may end partial if Starbucks needs
a store before it shows prices; that is reported as it happens.

### Measurement

- For each question: `parallel` (through `chat()`, the product path) and `sequential` (same orchestrator,
  `sequential=True`), alternated P S P S, 2 pairs for R1 and T1, 1 pair for R2 and T2 if time allows.
- Recorded per run: wall time from the message to the combined answer, per-child queued/phone/end times (overlap
  in seconds), model calls and cost per stage (lead, matcher, routine/agent, combine, memory), approvals requested
  (expected 0), the answer and its sources.
- Expected: T1 parallel ≈ max(child) + lead + combine vs sequential ≈ sum; R1 parallel ≈ sequential minus the overlapped
  matcher call (one phone), which shows the queueing is correct rather than a speed-up.

### Evidence (`eval/results/crossapp/`)

`runs.json` (every run, raw timings and events), `report.md` (table: question, mode, wall s, overlap s, calls, $, answer
with sources), `timeline.png` (per-child bars, parallel vs sequential, from `runs.json`), `parent_view.png` (the
parent task in the web app with its live subtasks, from the :8713 copy in the built-in browser), and `offline.txt` (the
test output). Answers show only what the test account already shows (no addresses beyond the saved 1 Hacker Way).
Reproduce: `META_DAILY_COST_CAP_USD=2 uv run --project backend python eval/run_crossapp.py --questions R1,T1 --pairs 2`.

### Per grant

| Grant | Runs |
| --- | --- |
| envoy-real only | R1, then R2; two-phone overlap is shown by the offline test only |
| envoy-test + envoy-real | T1 and R1 first (routine-only, clean timing), then T2 and R2 |
| envoy-test only | not enough for a cross-app answer (non-SkyLark apps route to envoy-real); I ask for envoy-real |

When done with a device for good: `scripts/stop_emulator.sh <avd>`, then `DEVICE-RELEASED crossapp <avd>`. All
emulators off by 09:45 EDT; on `REVOKE`, stop at once.

## 6. Risks

- **Event-loop stalls cut the overlap.** Trace listeners run synchronously, and `runner._thumbnail` grabs a gRPC frame
  (up to 2 s timeout) on the loop for every step, so one child's screenshot briefly pauses the other's coroutine
  (its device and model work, already in threads, continues). I measure it first; if the overlap suffers, the fix is
  a small runner change (take the thumbnail in a thread), offered as a separate commit since `alerts` also edits
  `runner.py`.
- **First connection is serialized** (`DevicePool._connect_lock`): warm-up before timing; cold numbers reported too.
- **Routines can fail on a real app** (an onboarding screen, a changed layout): repair and the agent take over, which
  costs model calls and time; reported as measured. Starbucks prices as a guest may need a store (R2).
- **The pre-filter misses a multi-app request** that names no app and no task word: it then runs as one task, as today.
  The filter's word lists are tested; a missed case costs nothing new.
- **Shared files:** `alerts` also edits `runner.py` and `Tasks.tsx`; my hooks are small and in separate places, and
  I merge `main` before the final commit and rerun the tests.
- **Memory writes of real-app screens** run extraction calls (a few cents per child); counted in the spend.

## 7. Time estimate (after a GRANT)

| Step | Time |
| --- | --- |
| `crossapp.py`, runner/store/chat/app hooks | 1 h 45 min |
| Offline tests, full suite | 1 h |
| UI (Tasks.tsx, api.ts, page.tsx), web build | 45 min |
| E2E setup (API copy, routine library, SkyLark seed, warm-up) | 40 min |
| E2E runs (R1, T1, then R2, T2) | 45 min |
| Evidence, report, merge `main`, rerun tests | 40 min |
| **Total** | **≈ 5 h 35 min** |

Model spend: ≈ $0.30 for R1 and T1 (lead, matcher, combine, memory; routines need no calls), ≈ $0.30–0.60 more with R2
and T2 (agent runs). Well under the $2 cap.

**If the grant comes late**, in this order of cuts (09:30 EDT is fixed): drop T2/R2 → one pair per question → the
timeline chart → UI polish (keep the subtask list and live badges). The offline overlap test, R1 or T1, and the
report are never cut.

## 8. Merging

One branch, commits by step (module, hooks, tests, UI, eval). Before the last commit: merge `main`, resolve any
overlap with `alerts` in `runner.py` / `Tasks.tsx` additively, rerun the suite and the web build. The report ends with
the merge command and a list of the shared files touched.
