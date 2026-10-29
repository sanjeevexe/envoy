# Memory and alert fixes (branch `claude/memory-alert-fixes-7387dc`, not merged)

## 1. A value that changes through a merge now alerts

- `MemoryStore.merge` (`backend/memory/store.py`) notes each attribute's current value before the merge (the kept
  entity's value first, then the other entity's). After the rechain it emits `fact_replaced` for every attribute
  whose current value changed. The event carries `merge_seq`, and its `fact` is the new current fact. The watcher
  credits that fact's source task and pushes once, as for any other new value. `fact_changed` triggers see it too.
- The rechain sometimes flags an app value newer than your edit as a conflict. When it does, `merge` now emits
  `fact_conflict`.
- `ChangeAlerts` (`backend/api/alerts.py`) now also alerts on `fact_conflict`, titled
  "Gate: SkyLark says C14, your note says B12". This covers conflicts from a plain `observe` as well as from merges.
  It goes through the same once-only and who-is-told rules.
- Offline tests (`backend/tests/test_alerts.py`):
  - A change through a merge gives one push, "Gate changed: B9 → B12".
  - The same value arriving through a second merge stays quiet.
  - A conflict with your note gives one push and no repeat.

## 2. Chat checks the app when a fact is past its freshness window (benchmark M4)

- `backend/api/chat.py`: a memory answer that uses a fact past its `FRESHNESS` window (a gate after 30 min) starts the
  check task instead, if a phone can run it. That means the app's emulator is up, or an Android phone is connected.
  `Retriever.stale_since` counts only stale facts whose value appears in the answer.
- With no phone free, memory answers and appends "(from <age>; no phone is free to check it now)".
- Offline tests (`backend/tests/test_chat_stale.py`): old gate → task; old gate with no phone → answer with its age;
  fresh gate → answered from memory.

## Checks

- `uv run --project backend pytest -q backend/tests`: 235 passed.
- `npm run build` in `web/`: passes.
- Device run on envoy-test with `eval/run_memory_alert_fixes.py` (API copy on :8751, scratch memory, fake push service):
  - **Stale gate: passed.** Memory held B9 from 3 h earlier and SkyLark showed B12. Chat started
    `skylark_get_flight_gate` and the run read "gate: B12", so memory now has B12.
  - **Change through a merge: not shown on the device.** I couldn't get a real watcher run to land on a second Flight
    entity. Even with the flight's key held back, the run resolved to the known flight, so the push I saw
    ("Gate changed: B12 → C14", once, with no repeat on the next run) came from the ordinary `fact_replaced` path.
    The merge path is covered only by the offline test.
  - **Baseline run not explained.** The baseline watcher run's check was marked BAD even though it read B12 and sent
    no push. It probably recorded a change step (the B9 → B12 change shown in the chat task). I haven't looked into it.
  - **First device attempt lost.** It collided with Phase 7's SkyLark suite on envoy-test. My re-seed at 21:01 broke
    their run, and they are rerunning it. I handed envoy-test back after my second run.
- Spend: about $0.07 over 15 Muse calls (two device runs; `logs/model_costs.jsonl`).

## Not done

- A device-level merge: it needs a natural way for an app read to reach a second Flight entity (for example, an
  email with no date).
- Chat's stale reply repeats the model's own hedge ("…but it may have changed (seen today 6:06 PM…)"). The wording
  could be tidied up.
