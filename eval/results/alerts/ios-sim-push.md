# iPhone alert check in the iOS Simulator (Oct 28, 2026): where it stops

Goal: the Envoy web app as a Home Screen app in the iOS Simulator, notifications on, then a SkyLark gate change on
envoy-test (as `eval/run_alerts.py` makes it) arriving as a notification.

Setup: an API copy on `http://localhost:8721` (its own data dir, token and scratch memory; the API on :8700 was not
touched), iPhone 17 Simulator, iOS 27.0 runtime, Xcode 27.1 (27A9275), macOS 26.6.2.

| Step | Result |
| --- | --- |
| Open the web app in Safari, sign in | ✅ |
| Share → Add to Home Screen ("Open as Web App" on) | ✅ icon on the Home Screen |
| Open it from the Home Screen, pair with a code from the copy | ✅ "Paired: iPhone (Home Screen app)" |
| Devices → Notifications on this device | ❌ stays "…": the "Turn on notifications" button never appears |
| Push subscription reaches the API | ❌ none (so no gate change was made and nothing was pushed) |

Why: the web app's `pushState()` waits on `pushManager.getSubscription()`, which never resolves, because the Simulator's
web push daemon doesn't run. WebKit's networking process connects to `com.apple.webkit.webpushd.service`; launchd in
the Simulator starts `webpushd` and it is killed at launch every time:

```
launchctl print user/501/com.apple.webkit.webpushd
    state = spawn scheduled
    runs = 9
    last exit reason = OS_REASON_CODESIGNING
```

So web push stops in the Simulator runtime itself (its `webpushd` fails code-signing validation on this Mac), before
Envoy or Apple's push service is involved. Envoy's side was already shown end to end with a push service that checks VAPID
and decrypts (`alerts.md`), and on the paired real iPhone in Phase 5. Possible next steps: a different Simulator runtime,
or the real iPhone over the tailnet companion URL.

Screenshot: `ios-sim-push-blocked.png` (paired and signed in; the notification state stuck at "…").
