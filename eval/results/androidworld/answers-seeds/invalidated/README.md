# Set-aside episodes of answers-seeds (kept for the record, not counted)

## api-billing-402/ (39 episodes, Oct 29, from 02:13:34 EDT)

From 02:13:34 every call to Meta's API answered 402 "Billing verification failed" (the account's billing, not this
run). Each of these episodes ended at its first model call (the matcher) with `envoy exited 1`, and AndroidWorld scored
it 0. They don't measure the routines. Their checkpoints are in `data/androidworld/answers-seeds/invalidated-checkpoint/`
(matched by task and seed: three Verify tasks have the same goal on every instance), so a resume reruns them.

Tasks (instances): SimpleCalendarEventsOnDate (1), SimpleCalendarLocationOfEvent (2), SimpleSmsReply (3), SimpleSmsReplyMostRecent (3), SimpleSmsSend (3), SimpleSmsSendClipboardContent (3), SystemBluetoothTurnOffVerify (3), SystemBluetoothTurnOnVerify (3), SystemBrightnessMax (3), SystemBrightnessMaxVerify (3), SystemBrightnessMin (3), SystemBrightnessMinVerify (3), SystemWifiTurnOff (3), TurnOnWifiAndOpenApp (3).
