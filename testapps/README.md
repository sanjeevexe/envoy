# testapps

Envoy's own Android test apps. Real apps can't be reset or checked exactly, so the agent, routines and evaluation are developed and measured on these first.

## SkyLark Air (`skylark/`)

A fake airline app in Kotlin + Jetpack Compose (package `com.skylark.air`). It has a seeded trip (KX7Q2M, SL 482 ATL→ORD, gate B12, seat 14C), check-in, seat map, known traveler number, flight status, profile, a fake sign-in with an SMS code, and a list longer than one screen.

```bash
cd testapps/skylark && ./gradlew :app:assembleDebug        # needs scripts/env.sh (JDK 21, Android SDK 37.2)
adb -s emulator-5554 install -r app/build/outputs/apk/debug/app-debug.apk
```

**Test hooks** (explicit broadcasts plus a content provider). From Python, use `backend/testapps/skylark.py`.

| Hook | Command |
| --- | --- |
| Reset to bundled fixtures | `am broadcast -n com.skylark.air/.DebugReceiver -a com.skylark.air.RESET` |
| Seed custom fixtures | `… -a com.skylark.air.SEED --es json_b64 <base64 JSON>` |
| Layout variant | `… -a com.skylark.air.VARIANT --ei variant N`: 0 original, 1 moved button, 2 renamed labels, 3 extra confirmation screen |
| Change a gate | `… -a com.skylark.air.SET_GATE --es code KX7Q2M --es gate C14` |
| Sign out | `… -a com.skylark.air.SIGN_OUT` |
| Read state | `content read --uri content://com.skylark.air.debug/state` (JSON) |

Every element the agent needs has a Compose test tag, exposed as its resource ID (`testTagsAsResourceId`), e.g. `btn_checkin`, `field_ktn`, `seat_12C`.

`scripts/skylark_smoke.py` drives every flow through Envoy's device layer, with no model, in all four variants.
