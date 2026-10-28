# Invalidated baseline episodes

These two episodes ran with a forwarder restore that handed AndroidWorld an empty screen: right after the forwarder
restarts, its first tree has 0 elements, and the restore accepted it as ready. Both tasks are scored by reading the
screen, and Envoy had ended both itself (done), so their 0 scores are not trustworthy. The fix
(eval/androidworld/aw_env.py: wait for two non-empty reads) was checked by hand: a paused and a running stopwatch both
score 1. The two tasks were rerun in the baseline with the fix; their first runs are kept here for the record.

- ClockStopWatchPausedVerify: Envoy done_unverified (its final tree shows Start and Stopwatch x3 in DeskClock), scored 0
- ClockStopWatchRunning: Envoy done (its own check passed), scored 0

Other baseline episodes before the fix were unaffected: the Browser tasks and ClockTimerEntry ended at the step limit
(AndroidWorld scores those 0 whatever the screen shows), and the other tasks are not scored from the screen.
