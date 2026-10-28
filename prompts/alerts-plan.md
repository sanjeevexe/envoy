# Proactive change alerts: plan (Stage A)

Written Oct 28, 03:40 EDT by the `alerts` worker, branch `claude/change-alerts-6f322a`. Read-only so far: no code
changed, no emulator, no model calls. The build (Stage B) waits for a `GRANT` from the overnight orchestrator.

## The gap, checked

- `backend/api/push.py` pushes on `approval_requested`, `takeover_requested`, `phone_requested` and `task_finished`.
  In `on_event`, a `task_finished` for a task whose source starts with `trigger` returns early when the status is
  `done` ("scheduled runs (watchers) are quiet unless something goes wrong").
- `backend/tests/test_phase5.py::test_takeover_and_finished_tasks_push_and_dead_subscriptions_are_dropped` asserts
  that a `trigger:watch gate` task finishing `done` sends nothing (`assert len(got) == 2`).
- `backend/api/scheduler.py`: `KINDS = ("time", "before_fact", "watch", "email")`. The design doc's Events
  bullet ("a new email matching a pattern, a new screenshot from the iPhone, or a fact changing in memory") has
  no fact-changed trigger.
- Timing: `TaskRunner._run` publishes `task_finished`, and so sends the push, before `_remember` writes memory
  (memory is written about 10 s later, with the phone already free). So at `task_finished` nobody can know yet
  whether anything changed. The alert has to come from memory's own change events.
- Memory already says exactly what a change is. `MemoryStore.observe` emits `fact_replaced`
  `{entity, fact, attribute, value, old, old_fact}` only when a new value supersedes the current one. A first
  sighting is `fact_added` with kind `new`, the same value seen again emits nothing, an older observation is
  `history`, and a contradicted user edit is `fact_conflict`. The new fact's `source` row carries `task_id` for
  both `app_screen` and `routine_run` sources, so a change can be traced to the task that saw it without touching
  memory.
- One caution: `MemoryStore._event` calls subscribers inline, with no `try`. A subscriber that raises would break
  `observe` halfway through a write, so the new subscriber must never raise.

## Design

### 1. Change alerts (`backend/api/alerts.py`, new; sending stays in `Pusher`)

`ChangeAlerts(tasks, memory, pusher, bus, scheduler)` is wired in `api/app.py:build` next to the pusher:
`memory.subscribe(alerts.on_memory)` and `bus.listeners.append(alerts.on_event)`.

1. **Notice** (`on_memory`, wrapped in `try/except`, read-only): for `fact_replaced` only, it follows
   `fact → facts.source → sources.reference.task_id` and keeps
   `{task, entity, attribute, old, new, fact, source}` in a per-task pending list. The source has to be that
   task's own source, so a change some other writer made while the task ran isn't credited to it.
2. **Report** (`on_event`): when the runner publishes the task's `memory` step (or an `error` step from
   `_remember`), every pending change for that task becomes a task step and, if allowed, one push. The step is
   `{"kind": "change", "text": "Gate changed: B12 → C14", attribute, old, new, entity, source: "SkyLark app,
   just now", pushed, why_not}`. A fallback timer (15 s, `loop.call_later`) flushes changes from any write path that
   has no memory step. Flushing on the memory step means one run that changes two watched attributes sends one
   push, not two.
3. **Push only when all of these hold**:
   - the task was started by a trigger: `Scheduler.fired_tasks[task_id] → trigger id` is recorded in `_fire`,
     with a fallback of task source `trigger:<name>` matched to a trigger by name, for runs from before a restart;
   - that trigger has alerts on: `spec.alert`, defaulting to on for `watch` and off for the other kinds;
   - the attribute is one the trigger watches: `spec.alert_on`, defaulting for a watcher to its routine's
     `outputs` through `canonical_attribute` (`skylark_get_flight_gate` → `["gate"]`), with `"*"` meaning any
     attribute;
   - it isn't a repeat. A table `change_alerts` (in the tasks DB, created the way `Pusher` creates `push_subs`)
     holds one row per reported change. A change is a repeat when the last alert for the same
     `(entity, attribute)` already announced this value (normalized with `memory.types.normalize_key_value`), so
     each `(entity, attribute, new value)` pushes once. A real flip back (B12 → C14 → B12) still pushes, because
     B12 is a different value from the last one announced.
4. **Push content**: `pusher.notify("change", "Gate changed: B12 → C14", "Flight SL 482 · SkyLark app, just now",
   "/?task=<id>", tag="change-<entity>-<attribute>", urgency="high", ttl=1800)`. The label comes from the
   attribute's name (`gate` → "Gate", `depart_time` → "Departure", `boarding_time` → "Boarding"). The entity is
   named by its type and title facts (`Flight` + `number`). The source wording comes from
   `Retriever.where(source)`, the same wording memory's notes use. A tag per entity and attribute means a later
   change to the same gate replaces the earlier notification instead of stacking. Tapping the push opens the
   task, whose `change` step shows the fact, its old value and its source. The web app already handles
   `/?task=`, and the service worker needs no change: it shows any payload.
5. **Tasks the user started** get the `change` step (with `why_not: "you started this task"`) but no push.

**Why alerts are a per-trigger setting, on by default for watchers.** A watcher exists to notice change, so it
alerts unless you turn it off. A per-trigger switch rather than a global one, because some watchers only keep
memory fresh (a points balance read daily would buzz on every accrual). The attribute filter matters as much as the
switch. A watcher's final screen goes through model extraction and yields every fact on screen (seat, boarding,
status), and a re-read can differ in form from the stored value. Memory records those, and the task shows them as
`change` steps, but only what the watcher was set up to watch buzzes the phone. Without the filter, extraction
noise on an attribute nobody asked about could alert the user in the middle of the night.

`push.py` changes: the docstring list gains "a remembered fact changed during a task a trigger started (change
alerts, `api/alerts.py`)". `FINAL` and the quiet `done` for triggered tasks stay as they are, so a watcher run
that changes nothing stays silent.

### 2. The "fact changed" trigger (`backend/api/scheduler.py`)

- `KINDS += ("fact_changed",)`. Spec: `{"entity_type": "Flight", "attribute": "depart_time"}`, with
  `"attributes": [...]` also accepted. `add()` checks the attribute against `TYPES[entity_type].attributes`. Like
  the email trigger's `after_rowid`, it sets `after_seq` to memory's current last event seq, so only changes from
  now on count.
- `due()` reads memory's own event log (`memory.events(after_seq, kind="fact_replaced")`, read-only) and keeps
  events whose entity type and attribute match. Each event fires once (key `chg<seq>`). `tick()` moves
  `spec.after_seq` to the last seq scanned, so scans stay short and the 200-entry `fired` cap can't re-fire old
  events. First sightings (`fact_added`) and user edits (`user_edit`) don't fire it. The trigger is about the
  world changing, not about you typing in the graph.
- **Typed values only.** The action is still fixed when you create the trigger: a goal template or a routine with
  `inputs_from`. The change supplies `{flight.number}`, `{trip.destination}`, `{change.attribute}`, `{change.old}` and
  `{change.new}`, through the existing `_clean`: one line, at most 80 characters, no braces, angle brackets or
  newlines. A screen that writes "C14\nIgnore previous instructions {approve}" into the gate stays one inert line
  in a template slot. Policy applies to the triggered task as to any other, so an irreversible step still asks.
- **Loop guard.** A change made by a task that this same trigger started doesn't fire it again. Otherwise a
  "when the gate changes, read the gate" trigger could feed itself.
- `next_runs()` returns nothing for this kind. The web app shows "runs when Flight.depart_time changes".
- Change alerts and this trigger are independent. A watcher can find the change (and push), and a fact-changed
  trigger can act on it.

### 3. Visible in the app

- `web/components/Tasks.tsx` (additive): a `change` step renders as an amber row: "🔔 Gate changed: B12 → C14", then
  "Flight SL 482 · seen in SkyLark app, just now · pushed to your devices" (or why it wasn't pushed).
- `web/components/Triggers.tsx`:
  - presets:
    - "Watch my gate every minute and tell me when it changes" (`watch`, `every_minutes: 1`, `alert: true`);
    - the existing 10-minute watcher, which now shows its alert setting;
    - "When my flight's departure time changes, look up its gate" (`fact_changed` `Flight.depart_time` →
      `skylark_get_flight_gate` with `inputs_from: {trip_city: trip.destination}`);
  - each watcher row shows "alerts on: gate" with an Alerts on/off button;
  - each fact-changed row shows "runs when Flight.depart_time changes";
  - a short "Recent changes" list (from `GET /api/alerts`) links each change to its task.
- `backend/api/app.py` (additive):
  - `ctx.alerts`;
  - `GET /api/alerts`;
  - `POST /api/triggers/{id}` also accepts `{"alert": bool}`. The current handler sets
    `enabled = body.get("enabled")` unconditionally, which would pause a trigger when only `alert` is posted. It
    becomes "only the fields given".
- The web app is rebuilt (`npm ci && npm run build` in `web/`, with `nice`) so the API on :8712 serves it.

### Files

| File | Change |
| --- | --- |
| `backend/api/alerts.py` | new: `ChangeAlerts` (notice, report, dedupe table, step and push) |
| `backend/api/scheduler.py` | `fact_changed` kind, `spec.alert`/`alert_on` defaults, `fired_tasks`, loop guard |
| `backend/api/push.py` | docstring and a `change` kind; no behavior change for existing kinds |
| `backend/api/app.py` | wire `ChangeAlerts`; `GET /api/alerts`; partial trigger update (additive) |
| `web/components/Triggers.tsx` | presets, alert toggle, fact-changed rows, recent changes |
| `web/components/Tasks.tsx` | render the `change` step (additive) |
| `web/lib/api.ts` | `Step` gains optional `old`/`new`/`pushed`/`why_not` (additive, types only) |
| `backend/tests/test_alerts.py` | new offline tests |
| `backend/tests/test_phase5.py` | the one silent-watcher assertion, reworded (below) |
| `eval/run_alerts.py` | new: the end-to-end check |
| `eval/results/alerts/` | new: evidence |

Untouched: `backend/agent/`, `backend/routines/`, `backend/policy/`, `backend/memory/` (subscribed to, never
changed), `backend/api/runner.py` (no hook needed: the runner's existing `memory` step event is the flush signal),
and existing `eval/` files.

## Offline tests (`backend/tests/test_alerts.py`, fakes and `FakePushService`)

These use the `build()` fixture pattern from `test_phase5.py`: in-memory stores, `FakePushService` subscribed, a
seeded trip with flight SL 482. Each test writes memory with a source whose `task_id` is a task created in the
store, then publishes that task's `memory` step, the same event the runner sends.

1. **Silent when nothing changed.** A watcher task sees B12 when memory says B12: no push and no `change` step. A
   first sighting (no gate yet → B12) is also silent.
2. **One push on a change, no repeat.** B12 → C14 from a watcher task gives exactly one push of kind `change`,
   decrypted by the fake service, titled "Gate changed: B12 → C14", with a body that has "Flight SL 482" and
   "SkyLark app" and url `/?task=<id>`. The task has a `change` step with `pushed: true`. The next watcher run sees
   C14 and sends nothing. A second `fact_replaced` to C14 for the same entity and attribute (another source) sends
   nothing (dedupe). A flip back to B12 pushes again.
3. **Who gets told.** The same change from a task you started adds the step and sends no push. A watcher with
   `alert: false` adds the step and sends no push. A seat change on a gate watcher adds the step and sends no push
   (`alert_on`). Gate and boarding changed in one run of a watcher with `alert_on: ["gate", "boarding_time"]` send
   one push.
4. **The fact-changed trigger fires on a change and not otherwise.** For a `Flight.depart_time` trigger: a tick
   with no events, the same value seen again, a first sighting on another flight and a `Trip` attribute change
   start nothing. A replaced `depart_time` starts exactly one task, with the goal filled from typed values, and the
   next tick doesn't refire. A value carrying newlines or braces arrives as one clean line. A change made by a task
   this trigger started doesn't fire it again. `add()` rejects an unknown attribute.
5. **A broken subscriber can't break memory.** `on_memory` given a malformed event leaves `observe` working.
6. **API.** `POST /api/triggers` with `fact_changed` works, and with a bad attribute returns 400.
   `POST /api/triggers/{id} {"alert": false}` leaves the trigger enabled. `GET /api/alerts` lists the change.

**The silent-watcher assertion, updated deliberately.** It stays true for the `task` (done) push, because a
watcher's finished run still doesn't buzz. The assertion becomes explicit about that: no `("task", "Done: What's my
gate?")`, with a comment pointing to `test_alerts.py` for the push a change does send. No other existing assertion
changes.

Run: `cd backend && nice -n 10 uv run pytest -q`, the whole suite, before the final commit and again after merging
`main`.

## End to end (`eval/run_alerts.py`, on the granted AVD)

Setup is all in my scratchpad, and nothing touches :8700 or `data/api/`:
- `ENVOY_API_DIR=<scratch>/api` with a session token I generate;
- a memory DB built from the demo inbox, the same way `scripts/demo_setup.py` builds it, but at a scratch path;
- `data/routines` copied to scratch, so the run's `index.json` updates don't dirty the tracked files.

The script builds the app in-process (`build(memory=…, tasks=…, routines=…, scheduler_every_s=2)`) and serves it
with uvicorn on 127.0.0.1:8712. When the grant is not `envoy-test`, it points SkyLark at that AVD inside the script
only: `api.routing.TEST_EMULATOR` plus a `Lease` for it, with no product change. Every adb call uses
`-s <serial>`.

1. `SkyLark(serial).prepare(demo_fixtures(signed_in=True))`: SL 482 to Chicago (KX7Q2M), gate B12.
2. Subscribe the `FakePushService` through `POST /api/push/subscribe`. It is the only subscription in that data
   dir, so nothing can reach the user's iPhone.
3. Create two triggers through `POST /api/triggers`, the same bodies the Triggers presets send:
   - "Watch my gate": `watch`, `every_minutes: 1`, `alert: true`, routine `skylark_get_flight_gate`;
   - "When my gate changes": `fact_changed` `Flight.gate` → `skylark_check_flight_status` (no irreversible
     step), with `inputs_from: {flight_number: flight.number}` (a typed value from the changed Flight), showing
     that the trigger fires.
4. The first run is a first sighting (memory from the emails has no gate): no push. The second run sees the same
   gate: no push.
5. `SkyLark.set_gate("KX7Q2M", "C14")` (the app's `SET_GATE` debug broadcast) at time t₀. The script waits for the
   fake service to decrypt a `change` push. **Latency = time the push was received − t₀**, split into: waiting for
   the next watcher run, the routine run, the memory write (one extraction call on the final screen) and the push.
   This repeats for C14 → D3 and D3 → B12, giving three samples at different points in the minute.
6. One more run after the last change: no repeat push.
7. Check memory (`GET /api/memory/entity/<flight>`): the current gate is the new one, its source is the watcher
   task's app screen or routine run, and its history is B12 → C14 → D3 → B12. The fact-changed trigger started one
   status task per change and none before the first.
8. Browser check on :8712 with my own token (never the user's): Tasks shows the `change` step, and Triggers shows
   the watcher with alerts on, the fact-changed trigger and recent changes. Screenshots go to the evidence folder.
9. Teardown: delete the triggers, stop the API copy. If the grant was `envoy-test`, leave SkyLark the way
   `scripts/demo_setup.py --app-only` does (demo fixtures, signed out, variant 0). Stop the emulator and send
   `DEVICE-RELEASED alerts`.

Evidence in `eval/results/alerts/`:
- `alerts.json`: every step, the decrypted pushes, latencies, the flight's gate history with sources, model calls
  and cost, and the commit;
- `alerts.md`: the readable report;
- screenshots.

**Cost.** The routine itself makes 0 model calls. Memory reads each run's final screen with one extraction call (on
the standard tier, since memory decides its tier, and I don't change memory). That is about 8 to 10 runs, well
under $0.10 at the $1 cap. Spend is reported from the adapter's cost log.

**Optional: the iOS Simulator.** Open `http://localhost:8712` in Simulator Safari, add it to the Home Screen and
turn on notifications. Its subscription would go through Apple's real push service, which may refuse the copy's
`mailto:envoy@localhost` VAPID subject (`Pusher.subject` uses an https origin only on the tailnet). Time-boxed to
30 minutes. If it doesn't work, the report says exactly where it stopped.

## Time estimate

| Part | Time | Device |
| --- | --- | --- |
| `alerts.py`, push wiring, `app.py` hooks | 1 h | no |
| `scheduler.py` fact-changed trigger | 40 min | no |
| `Triggers.tsx`, `Tasks.tsx`, web build | 45 min | no |
| Offline tests, the phase 5 assertion, full suite | 45 min | no |
| `run_alerts.py`, its runs, evidence | 1 h 15 min | about 35 min |
| Browser check on :8712 | 20 min | yes, within the 35 min |
| Merge `main`, rerun tests, report | 30 min | no |
| **Total** | **about 5 h** | **35–45 min of emulator time** |

The build and offline tests come first after a GRANT; the emulator starts only once they pass. If the grant
arrives after about 04:30, the end-to-end run shrinks to one or two gate changes so the work still ends by 09:30
with every emulator stopped by 09:45.

## Risks and known gaps

- **Extraction resolves the screen to a new Flight entity**, which is later merged by natural key. A merge
  re-chains history but emits `merged`, not `fact_replaced`, so that change would not alert. Resolution by key
  (number + date) should prevent it: the trip details screen shows both. The end-to-end run will show whether it
  happens. If it does, the fix is to read the re-chained current value in the `merged` event's payload. I would
  report that rather than change memory.
- **Gate and status read only by extraction** (attributes outside the routine's outputs) follow the model's
  reading. That is why `alert_on` defaults to what the routine itself reads.
- **A contradicted user edit** (`fact_conflict`) is not alerted. It could become "SkyLark says C14, your note says
  B12" later.
- **The fact-changed trigger polls memory's event log** every scheduler tick (10 s in production), so it acts up to
  10 s after the change. Alerts don't wait for a tick.
- **The docs** (`docs/technical-design.md` Events, `backend/api/README.md`) belong to whoever owns them tonight. The
  report will include a two-sentence addition to paste in, rather than editing them.
