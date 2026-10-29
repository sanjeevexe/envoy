# Set-aside routine replays (kept for the record, not counted)

## overlap/ (2 episodes, Oct 28, 18:04:53–18:05:30 EDT)

Another session (the Wonder appnotes benchmark) started its own AndroidWorld runner on emulator-5560 at 18:04:53,
believing it was free, while this stage was still replaying. It stopped before 18:05:30 and recorded nothing. No Envoy
agent ran, but AndroidWorld's environment connect and possibly a reset or the start of a task's setup may have touched
the emulator. I stopped this stage at 18:05:20. The two replays that finished inside that window are set aside and rerun:
- SimpleCalendarLocationOfEvent (finished 18:04:57, scored 1)
- SimpleCalendarNextEvent (finished 18:05:11, scored 0)
The replay in progress when the stage stopped was never scored or checkpointed, so a resume reruns it. The 39 replays
that finished before 18:04:53 stand.
