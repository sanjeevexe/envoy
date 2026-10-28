# Cross-app answers: report

Worker `crossapp`, branch `claude/cross-app-answers-522e1d`, Oct 28 2026. Plan: `prompts/crossapp-plan.md`.
Granted `envoy-real` only (AndroidWorld held the other slot), so parts ran back to back on one phone there; two phones
at once are shown offline with fake phones.

## What it does

Ask chat a question that needs two apps ("How many calories are in a Caffè Latte at Starbucks, and what's the first
place DoorDash shows for a latte?"):

1. **Pre-filter, in code.** Only a message that names two or more apps, or one app plus a comparison or a second
   question, goes further. Every other message takes today's chat path, byte for byte (tested).
2. **Lead step.** One Muse Spark call (standard tier, structured output) splits it into one part per app: the app, a
   goal that stands on its own, and typed inputs for that app's routines. Code keeps only known apps, and inputs that
   belong to that app's routines and whose values appear in the request. If the lead says it's one app, chat goes on
   as before.
3. **Parts are ordinary tasks** (`runner.start(..., parent=…)`): the matcher, the routine with repair and the agent
   behind it, sign-in hand-offs, the approval gate, on the phone `routing.py` picks. Parts on different phones run at
   the same time; parts on the same phone wait for its lease, like any two tasks.
4. **Combine.** One more call writes the answer. Each cited value must appear in its part's result, and each number in a
   result or the request (or be the difference of two result numbers); otherwise the answer is built in code. Each
   value's source (app · screen · time) comes from the part's own final screen, added in code, never by the model.
5. **Memory.** Each part writes its facts like any task. The combined answer becomes a Note whose source
   (`cross-app answer`) lists each part's task, app, screen and time.
6. **Web app.** The task list nests parts under their parent; the parent's view has a card per part (app, phone, its
   own live status, its result) and the answer with its sources. The parent waits on you when a part does (an
   approval, a sign-in), saying which app.

## Files

| File | Change |
| --- | --- |
| `backend/api/crossapp.py` | new: pre-filter, lead, checks, parent task, combine, sources, memory |
| `backend/api/runner.py` | `start(parent=)`, `on_final` hook (final screen + outputs), `crossapp` slot (+14/−3) |
| `backend/api/store.py` | `parent` column and its migration (+5/−2) |
| `backend/api/chat.py` | ask the lead first when the pre-filter fires (+19/−2) |
| `backend/api/app.py` | wire `CrossApp` in `build()` (+2) |
| `web/components/Tasks.tsx`, `web/lib/api.ts`, `web/app/page.tsx` | parts under their parent, part cards with live status |
| `backend/tests/test_crossapp.py` | 21 offline tests |
| `eval/run_crossapp.py`, `eval/results/crossapp/` | end to end and its evidence |

Not touched: `backend/agent/`, `backend/routines/`, `backend/policy/`, `backend/memory/`, `backend/models/`, existing
`eval/` files.

## Evidence

### Offline: two phones at once (`backend/tests/test_crossapp.py`, 21 tests; `eval/results/crossapp/offline.txt`)

A real `TaskRunner` (its routing, per-phone lease, statuses, approvals) with fake phones whose routine work takes 0.5 s:

| Case | Result |
| --- | --- |
| SkyLark part (envoy-test) + Starbucks part (envoy-real) | both phones busy at once for > 0.4 s of 0.5 s; answer in < 0.85 s |
| Starbucks + DoorDash (both envoy-real) | no overlap; the second part shows "waiting for envoy-real"; ≥ 0.95 s |
| `sequential=True` on two phones | no overlap (the baseline) |
| One-app requests (3) | same model calls, same task started, same reply as a runner without cross-app answers |
| Lead says one app / lead call fails | today's path, same task (+1 call when the lead ran) |
| Split checks | unknown apps, inputs not in the request, inputs not of that app's routines: dropped; > 4 parts trimmed |
| Combine | an invented number falls back to the answer built from the parts; a difference of two prices is allowed |
| Partial / all failed / declined / stop | named in the answer / parent failed with no combine call / declined part named / parts stopped |
| Live status | parent `waiting_approval` with "Starbucks: …" while a part waits; each answer shows as it comes in |
| Memory | a Note with the answer; source `cross-app answer` with each part's task, app, screen and time |

Full backend suite: 159 passed (138 before this work + 21 new) with `main` d909d1a merged in; the web build passes.

### End to end on envoy-real (`eval/results/crossapp/report.md`, `runs.json`)

Granted envoy-real only, so parts took turns on one phone. API copy on :8713 with its own data, token and routine
library (SkyLark + Phase 7's `real_compiled`); standard tier; every approval declined; apps closed after each part.

| Question | Path | Runs | Answer | Wall s, parallel / sequential |
| --- | --- | --- | --- | --- |
| R1 Caffè Latte calories at Starbucks + DoorDash's first latte place | 2 routines, 0 calls on the phone | 2 + 2 | 190 calories · McDonald's | 31.2, 36.9 / 31.6, 31.2 |
| R3 Caffè Mocha calories at Starbucks + Space Needle's address in Maps | 2 routines (1 self-repair for the new drink) | 2 + 2 | 370 calories · 400 Broad St, Seattle, WA 98109 | 59.8, 43.0 / 37.3, 36.5 |
| R2 "What's a Caffè Latte at Starbucks vs on DoorDash?" (price) | the agent in both apps (no price routine) | 1 + 1 | DoorDash $5.75 (Starbucks for DoorDash); Starbucks as a guest shows no price | 172.1 / 187.0 (failed) |

- **Every run** went through chat's pre-filter and lead, split into the right two apps, asked for **no approval**, and
  gave one answer whose values each carry app · screen · time (e.g. `Starbucks · the "Caffè Latte" screen · 5:27 AM`;
  Starbucks names its activities `dIu`, so the screen is named by its title).
- **Cost per question** with routines: 6–8 calls, $0.015–0.028 (lead 1, matcher 2, combine 1, memory extraction 2–3).
  The lead adds ~2–3 s before the parts start and the combine ~2 s at the end.
- **One phone can't be faster in parallel, and wasn't.** What the orchestrator changes there: the phone is never idle
  between parts (0.0 s, against 1.9–2.3 s in sequential mode while the next part is matched). The slower parallel runs
  come from the apps, not the orchestration: R3's first parallel run repaired the Starbucks routine for a new drink
  (+1 repair call, +19 s), and in the other two Starbucks happened to run second (its part takes 18–20 s after another
  app, 11–13 s first). Parts on one phone take the phone in the order they're ready, so that order varies.
- **R2 is the pitch's price comparison**, and the agent's limits show: DoorDash found the price in 1 of 2 runs; the
  Starbucks app as a guest needs a store before it shows prices, and its agent stopped at the 25-step limit both times.
  The answer says which app couldn't be checked (`ui_parent_partial.jpg`).
- **Two fixes found by the real runs** (`r2_before_fix.json`): first, the lead rewrote the price question to fit the
  learned routines (calories at Starbucks, the first DoorDash restaurant); then it kept the words but read "What's a
  Caffè Latte" literally (Starbucks returned its description). The lead now keeps the user's question whether or not a
  routine answers it, and reads a bare comparison across shopping or delivery apps as a price; the combine says when a
  result answers something else.
- **A device failure** (`device_failure.json`): envoy-real's system server died mid-run (`DeadSystemRuntimeException`,
  the hang Phase 7 also saw). Both parts failed on the device and the parent reported each app's reason. The clean stop
  hung on `adb emu kill`; ending envoy-real's qemu process (SIGTERM) recovered it, and it cold-booted with its account
  and apps.
- **Web app**: `ui_list_queued.jpg` (live: Starbucks running, DoorDash "waiting for a phone"),
  `ui_parent_live.jpg` (the parent with a card per part and the real-app phone live beside it),
  `ui_parent_partial.jpg` (a partial answer: DoorDash's price, Starbucks named as missing).
- **Spend**: $0.59 in 244 standard-tier calls in this worktree today (the 10 kept runs: 174 calls, $0.42; the rest are
  the first R1 pair, the pre-fix R2 runs and the device-failure runs).

## Not done

- **Two real phones at once.** Not granted (AndroidWorld held the second slot); proven offline only. `eval/run_crossapp.py
  --questions T1,T2` is ready: it seeds SkyLark on envoy-test the way the routine suites do (untested on a device).
- **Event-loop stalls** (plan § 6): `runner._thumbnail` grabs a frame on the loop at every step, which may cut real
  two-phone overlap a little. Unmeasured without two phones; the fix (take it in a thread) would be a small runner change.
- **MCP**: Muse's `start_task` calls `runner.start` directly, so cross-app answers come through chat and voice only.
  Routing it through the lead is a small follow-up in `mcp_server/server.py`.
- **Matcher precision** (not my files): for "a Caffè Latte on DoorDash" without the word price, the matcher chose the
  first-restaurant routine. The lead's price rule avoids that wording now.
- The parent's `cost_usd` doesn't include matcher calls (the runner doesn't count their cost); the cost log is the
  reference, and the eval reports from it.
- The design doc's "Several phones at once" still calls this a stretch goal; suggested text: "Built: a lead step (one Muse
  Spark call) splits a request that needs several apps into one task per app; each runs through the matcher, routine and
  agent on the phone routing picks, at the same time on different phones; one answer cites each app's screen and time."

## Merging

From the main checkout: `git merge claude/cross-app-answers-522e1d` (main d909d1a is already merged in; no conflicts).
Shared files touched, all additively: `backend/api/runner.py`, `store.py`, `chat.py`, `app.py`, `web/components/Tasks.tsx`,
`web/lib/api.ts`, `web/app/page.tsx`. After merging: `uv run --project backend pytest backend/tests -q` and
`npm run build` in `web/`. The `parent` column is added to existing task databases on the API's next start.
