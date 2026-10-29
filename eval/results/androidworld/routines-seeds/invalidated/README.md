# Set-aside episodes of routines-seeds (kept for the record, not counted)

## adb-restart/ (26 episodes, Oct 28, about 22:32–22:33 EDT)

After 43 normal episodes, AndroidWorldAvd stalled during SimpleSmsSend (instance 2): AndroidWorld could not read the
accessibility tree, and `adb shell dumpsys window` timed out after 30 s. android_env's AdbController then did what it
does after any failed device command: `adb kill-server` and `start-server` on port 5037, the adb server every session on
this Mac shares. That also crashed Phase 7's SkyLark runs on envoy-test. After the restart, emulator-5560 was briefly not
registered, so the next 26 episodes ended at once with a harness exception (`adb ... whoami` failed). AndroidWorld
scored them 0. They don't measure the routines. The agent-seeds stage that followed couldn't launch at all
(`TooManyRestartsError`) and recorded nothing.

The tasks: SimpleSmsSend (instances 2 and 3), and all three instances of SimpleSmsSendClipboardContent,
SystemBluetoothTurnOffVerify, SystemBluetoothTurnOnVerify, SystemBrightnessMaxVerify, SystemBrightnessMinVerify,
SystemBrightnessMin, SystemWifiTurnOff and TurnOnWifiAndOpenApp. Their checkpoints are in
`data/androidworld/routines-seeds/invalidated-checkpoint/`. All 26 were rerun into the same stage after the fix.

Fix (`3631542`, `eval/androidworld/aw_env.py`): android_env's server restart is replaced by a wait and `adb devices`,
and any adb command that would kill, start or reconnect the server raises instead. The same restart had fired, unseen,
on every AndroidWorld setup since Oct 27 (its VLC APK always fails to install on arm64) and on two failed shell commands
in final-standard. None of those runs' episodes were affected: AndroidWorld retried the command and went on.
