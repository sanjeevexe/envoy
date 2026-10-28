# Proactive change alerts: report

Written Oct 28, 2026 by the `alerts` worker. Branch `claude/change-alerts-6f322a`, `main` (d909d1a) merged in, not
pushed. The plan is `prompts/alerts-plan.md`, and the end-to-end evidence is in `eval/results/alerts/alerts.md`.

## What was built

1. **Change alerts** (`backend/api/alerts.py`, new).
   - A task a trigger started now pushes when it changed a remembered fact: "Gate changed: B12 → C14", with the body
     "Flight SL 482 · SkyLark app, just now". Opening it shows the task whose `change` step has the old value, the new
     value and the source.
   - A first sighting doesn't push, and neither does the same value seen again. Each (entity, attribute, new value)
     pushes once, and a flip back to an earlier value pushes again.
   - Tasks you started show the change step without a push.
   - How it works:
     - It subscribes to memory's `fact_replaced` events, read-only, so memory's behavior is unchanged.
     - The subscriber never raises; there is a test for that.
     - It credits each change to the task whose source wrote it.
     - It reports on that task's `memory` step, so a run sends at most one push.
     - Writes with no memory step are reported after 15 s.
     - Sending goes through `Pusher.notify` with kind `change`.
2. **Alerting is a per-trigger setting**: `spec.alert`, on by default for watchers and off for the other kinds, plus
   `spec.alert_on`, which by default lists what the watcher's routine reads.
   - Why per trigger: a watcher exists to notice change, but some watchers only keep memory fresh, and those shouldn't
     buzz.
   - Why the attribute filter: memory also reads the whole final screen with the model, and a re-read can differ in
     form. That happened on the device: "Group 3" was read as "3". Those changes show in the task but don't push.
   - A change that a different background task saw first also pushes when another enabled trigger alerts on that
     attribute and its runs have read that entity. Typical cases are a fact-changed follow-up or a second watcher.
     The device run found this gap; see "Found on the device".
3. **The fact-changed trigger** (`backend/api/scheduler.py`, kind `fact_changed`).
   - The spec is `{"entity_type": "Flight", "attribute": "gate"}` (or `attributes: [...]`), validated against memory's
     types.
   - It reads memory's own event log from `after_seq` onward and fires once per `fact_replaced`.
   - It doesn't fire on first sightings, repeats, user edits, other types, or changes made by tasks it started itself.
   - Its action is fixed when it is created. The change supplies only typed, cleaned values: `{flight.number}`,
     `{trip.destination}`, `{change.attribute}`, `{change.old}`, `{change.new}`, and routine inputs through
     `inputs_from`.
4. **In the app**:
   - **Tasks**: a `change` step shows as an amber row, "Gate changed: B12 → C14 · Flight SL 482 · seen in SkyLark app,
     just now · 🔔 pushed to your devices", or why it wasn't pushed.
   - **Triggers**:
     - presets for a one-minute gate watcher with alerts and for "when my flight's departure time changes, look up its
       gate";
     - "🔔 alerts on: gate" with an Alerts on/off button on each watcher;
     - "runs when Flight.gate changes" on fact-changed rows;
     - a Recent changes list that links to each change's task.
   - **API**: `GET /api/alerts`. `GET /api/triggers` now includes each trigger's alert settings.
   - **Bug fix**: `POST /api/triggers/{id}` now updates only the fields given. Before, posting anything without
     `enabled` paused the trigger.

## Evidence

- **Offline**:
  - `backend/tests/test_alerts.py` has 11 tests: silent when nothing changed; one push per change with no repeat;
    who gets told; the case found on the device; no subscribed device; a broken event; reporting without a memory
    step; the fact-changed trigger firing on a change and not otherwise, with typed values and no self-feeding; and
    the API.
  - The fake push service decrypts every push.
  - The silent-watcher assertion in `test_phase5.py` was changed deliberately and states what it means: a watcher
    finishing "done" still doesn't push.
  - **The full suite passes, 149 tests, on `main` merged in.**
- **End to end on envoy-test** (`eval/run_alerts.py`, final run at 174f919, all checks passed):
  - Four gate changes made through SkyLark's debug broadcast, B12 → C14 → D3 → E7 → B12, gave four decrypted pushes.
  - Latency from change to push was 5.4–56.7 s, mean 30.3 s. It is dominated by waiting for the next one-minute
    watcher run. After that, the routine takes about 4 s, memory's extraction about 5 s, and alert plus push under
    0.06 s.
  - Two baseline runs and the run after the last change were silent.
  - Memory shows each gate with its source.
  - The fact-changed trigger started one status check per change, with typed values only.
  - Screenshots of Triggers and of task activity are in `eval/results/alerts/`.
- **Cost**: 62 extraction calls, $0.31 in total, at the $1 cap. Of that, $0.16 was building the scratch memory three
  times and $0.15 was the three end-to-end runs. The routines made 0 calls.

## Found on the device

- **A missed alert, now fixed** (run 2):
  - The fact-changed follow-up read the next gate (E7 → B12) before the watcher's next run did.
  - Its trigger doesn't alert, and the watcher then found nothing new, so the change was never announced.
  - The fix is in commit 174f919 with an offline test. In the final run the same timing came up, and the follow-up
    pushed for "Watch my gate" 5.4 s after the change.
- **Memory normalization** (owner: memory, Phase 7; not changed here): "Group 3" and "3" are different boarding-group
  values in `normalize_key_value`, so a re-read flips it back and forth as a change. Alerts filter it already.

## Not done

- **The iOS Simulator part (optional).** No simulator can boot on this Mac until Xcode's first-launch install runs:
  CoreSimulator is 1171.7, and this Xcode expects 1174.9.2. `xcrun simctl` started `xcodebuild -runFirstLaunch`, which
  needs an admin password, and I stopped it. To try it later:
  1. Run `sudo xcodebuild -runFirstLaunch`.
  2. Run `eval/run_alerts.py --serve-only`.
  3. Open `http://localhost:8712` in the Simulator's Safari and add it to the Home Screen.
  4. Turn on notifications.

  A real push service may still refuse the copy's `mailto:envoy@localhost` VAPID subject.
- **A conflicting user edit** (`fact_conflict`) doesn't alert. It could become "SkyLark says C14, your note says B12".
- **A paused fact-changed trigger** fires, on resume, for changes made while it was paused. Each still fires once.
- **A memory merge** re-chains history without a `fact_replaced` event, so a change that arrives through a merge
  wouldn't alert. It didn't happen in these runs: the screen resolved to the existing flight by number and date.
- **Docs** belong to their owners. Paste-ins:
  - `docs/technical-design.md`, Scheduled and event-triggered tasks, after item 3: "A watcher pushes only when its run
    changes a remembered fact it watches (a new gate, not the same gate again); a fact changing in memory can also
    start a routine or task template created in advance (the `fact_changed` trigger), with the change supplying typed
    values only."
  - `backend/api/README.md` table: "| `alerts.py` | Change alerts: a trigger-started task that changes a remembered fact
    it watches pushes once per new value ("Gate changed: B12 → C14"); the change shows in the task |". In its routes
    line, add `GET /api/alerts`.

## How to merge

The branch is ready to merge into `main` as it is. It already contains `main` at d909d1a, and the full suite passes.

- New files: `backend/api/alerts.py`, `backend/tests/test_alerts.py`, `eval/run_alerts.py` and `eval/results/alerts/`.
- Changes to shared files are additive:
  - `backend/api/app.py`: wiring, `GET /api/alerts`, the alert settings in the trigger list, and the partial trigger
    update;
  - `backend/api/push.py`: docstring only;
  - `web/components/Tasks.tsx`: the change row;
  - `web/lib/api.ts`: optional Step fields;
  - `backend/tests/test_phase5.py`: one assertion reworded.
- `backend/api/scheduler.py` and `web/components/Triggers.tsx` were owned by this work.
- Not touched: `backend/agent/`, `backend/routines/`, `backend/policy/`, `backend/memory/`, `backend/api/runner.py`, and
  the existing `eval/` files.
- After merging, rebuild the web app: `cd web && npm run build`.
- Existing triggers keep working unchanged. A watcher saved before this change alerts by default from now on. To
  silence one, use its Alerts off button.
