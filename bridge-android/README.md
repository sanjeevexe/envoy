# bridge-android

Not built. The Envoy bridge was a planned Kotlin accessibility service, to be built only if uiautomator2 proved too slow
or unreliable. On a real phone (Phase 6, a Pixel 5 on Android 13), settling and set-text both held, so Envoy keeps
uiautomator2 (`docs/technical-design.md`, Device layer). Envoy's own Android code is the banner it shows while it
uses a real phone: `android/banner/`.
