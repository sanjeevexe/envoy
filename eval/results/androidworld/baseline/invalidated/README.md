# Invalidated baseline episodes (kept for the record, not counted)

Every task here was rerun once the harness problem was fixed; the counted episode is the rerun in `../episodes/`.

## empty-screen/ (2 episodes)

These ran with a forwarder restore that handed AndroidWorld an empty screen: right after AndroidWorld's accessibility
forwarder restarts, its first tree has 0 elements, and the restore accepted it as ready. Both tasks are scored by reading
the screen, and Envoy had ended both itself, so their 0 scores can't be trusted.
- ClockStopWatchPausedVerify: Envoy `done_unverified`; its final tree shows Start and "Stopwatch" x3 in DeskClock; scored 0
- ClockStopWatchRunning: Envoy `done` (its own check passed); scored 0

Fix: `aw_env.restore_forwarder` waits for two non-empty reads. Checked by hand: a paused and a running stopwatch both
score 1 through the restore path (`hv-paused`, `hv-running`).

## no-app-reset/ (8 episodes)

These ran after the emulator was restarted (the user asked for a pause on Oct 27). On API 33, Android's boot-time
`reconcileAppsData` deletes `/data/data/android_world`, where AndroidWorld keeps each app's post-setup snapshot, because
no package owns it (confirmed with a marker file and a reboot on Oct 28). AndroidWorld then only logs "Skipping app
snapshot loading" and apps keep their state from task to task. These eight tasks ran that way:
ClockTimerEntry, ClockStopWatchPausedVerify, ClockStopWatchRunning, ContactsAddContact, ContactsNewContactDraft,
ExpenseAddMultiple, ExpenseAddMultipleFromGallery, ExpenseAddMultipleFromMarkor.

Fix: `run_aw.py` checks the snapshots before every stage and runs AndroidWorld's setup again when they are missing
(`aw_env.ensure_setup`). The seven episodes before the first restart (AudioRecorder x2, Browser x3, Camera x2) ran with
the snapshots; none of them is scored from the screen after an agent `done`, so they stand.
