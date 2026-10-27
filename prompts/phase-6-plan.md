# Phase 6: Real Android phone and SAM 3.1 (plan)

Written by Claude from `prompts/phase-6.md` and the design doc on Oct 27, 2026 (evening). The build-phases diagram defines this phase as: the real-phone backend, routing between phones, and SAM 3.1 for screens without an accessibility tree. **Gate:** a routine learned on the emulator runs on the real phone.

## Rules (unchanged, plus the phone)

- Never type passwords or sign in to accounts, on the Android phone too. Never use payment methods.
- Ask before anything visible outside this Mac.
- Contributor tier only for SkyLark test data; real apps and real data use the standard tier.
- `envoy-real` is never snapshot-restored and is stopped with `scripts/stop_emulator.sh`; at most two emulators run at once, including the new one.
- The demo shows only work built during the hackathon; `THIRD_PARTY.md` lists every new library.
- Live design doc: find-and-replace through the Claude Docs connector, `sinceRev` checked first.
- Commit and push after each meaningful step. When something needs you (the USB prompt, a pairing code, a sign-in, an approval), ask right away and send a notification.
- The phone is a loan you factory-reset on return, so Envoy installs what it needs (SkyLark's debug APK, uiautomator2's helper, the scrcpy server, the banner app) without a cleanup list.

## What I found before planning

- **No phone yet** (`adb devices` shows only `envoy-test`); it arrives Oct 28. Everything below except the gate is built and tested on emulators first; a `PhoneDevice` pointed at an emulator serial exercises the real-phone code path (no gRPC, scrcpy, physical-touch watcher, banner).
- Everything that talks to a phone's screen outside the agent goes through `device.grpc` today: the live view (`api/live.py`), approval screenshots (`api/approvals.py`) and step thumbnails (`api/runner.py`). The pool (`api/devices.py`) knows only the two AVDs, and the web app's phone switcher is hard-coded to them.
- Routines drop `tap_point` steps ("not supported in routines"); the locator's `crop` field is a stub. The agent's `tap_point` takes coordinates from the step model's own reading of a 540 px screenshot; the adapter has a `grounding` job and SAM 3.1 pricing from Phase 0, unused by the agent.
- SkyLark's seat map is 40 dp boxes with one tagged, described element per seat; the layout variants stop at 5.
- **scrcpy 5.0.1** is installed with its server (`/opt/homebrew/share/scrcpy/scrcpy-server`). Not installed in the backend: **numpy**, **PyAV** (H.264 decoding).
- Phase 2 routines eval (`eval/run_routines.py`, `eval/skylark_routines.py`) already has the 7 SkyLark families with input binding and code success checks on SkyLark's state; the portability run reuses them on another device.

## What gets built

### 1. A device for real phones (`backend/devices/`)

| File | What |
| --- | --- |
| `android.py` | `AndroidDevice`: everything uiautomator2 and adb do, for any serial: tree reads, settle, tap/type/scroll/swipe/keys (typing stays accessibility set-text, never the clipboard), secure-window detection, `adb screencap`, honest capabilities (real phone, SIM state from `gsm.sim.state`, no snapshots, size, density). A `stream` attribute is the device's screen I/O (frames, tap, swipe, text, keys) for everything outside the agent. |
| `emulator.py` | `EmulatorDevice(AndroidDevice)`: the gRPC fast paths (6 ms frames, <1 ms taps), snapshots, `stream` = the gRPC client. Unchanged behavior. |
| `phone.py` | `PhoneDevice(AndroidDevice)` and `discover()`: connected phones from `adb devices -l` (not emulators), named by model. Screenshots come from the scrcpy stream's latest frame (fallback `screencap`). Starts and stops the banner, and watches for physical touches. |
| `scrcpy.py` | A scrcpy 5.0.1 session in Python: pushes the pinned server, opens the video socket (H.264 decoded with PyAV into frames) and the control socket (touch down/move/up, keys, text, as scrcpy's binary messages). Same methods as the gRPC client, so the live view, approvals and thumbnails don't care which phone it is. |

`device.grpc` call sites move to `device.stream`. The pool lists the AVDs plus discovered phones (id `phone-<serial>`), each with a lease, so takeover and the live view work the same on a phone.

### 2. Portability before the phone

- A third AVD, **`envoy-small`**: 720×1280 at 320 dpi (about 640 dp tall against 915 dp on `envoy-test`), same Android 15 Play image, console 5558, gRPC 8558, snapshots allowed. `start_emulator.sh` learns it.
- `eval/run_phase6.py portability`: the 7 SkyLark routines (compiled on `envoy-test`) on `envoy-small`, unchanged, with new bookings: success by SkyLark's state, model calls, time, which rungs fired. Whatever depends on screen size (off-screen targets, scroll distances, swipe vectors) gets fixed in the executor, then re-measured.

### 3. Screens with no accessibility tree

- **SkyLark variant 6:** the seat map drawn on a `Canvas`, with no semantics (one opaque node), tapped by position like a real custom-drawn map. The bottom bar stays native. A debug hook publishes the drawn seat rectangles (screen pixels), so every grounding answer can be checked exactly.
- **`agent/vision.py`, locating a described target on a screenshot:**
  - *grounding*: Muse Spark's grounding job on a downscaled screenshot (0–1000 grid, clamped);
  - *SAM + choose*: SAM 3.1 segments candidates from a short phrase ("seat", "icon", "map pin"), the candidates are drawn as numbered boxes on the screenshot, and Spark picks one (structured output);
  - each returns a box, a point, the method, latency and cost. Secure screens are never sent.
- **Agent:** `tap_point` gains a `target` ("seat 21A, a window seat"). The runtime takes a fresh full screenshot, locates the target with the chosen method, and taps its center; the step model's own coordinates are the fallback. The trace records the description, the box and a crop.
- **Routines:** the compiler keeps these steps as `tap` with a **visual locator** (description, crop, recorded position, recorded density). The executor tries the crop first (normalized cross-correlation, scaled by the density ratio, numpy only; no model call), then re-grounds the description (one call), then the usual ladder. Post checks are unchanged (here: "Selected: 21A" appears).
- **Measurement** (`eval/run_phase6.py vision`): the same targets through (a) the step model's own coordinates, (b) grounding, (c) SAM + choose:
  - SkyLark's canvas seat map (exact boxes from the hook), on `envoy-test` and `envoy-small`;
  - real-app screens on `envoy-real` where the tree gives the truth but the methods see only the image (Amazon, Starbucks, DoorDash, Chipotle, Settings);
  - Chipotle's map store picker (no tree), scored by eye on saved screenshots.
  Accuracy (center inside the box), latency, cost. SAM stays only if it beats grounding.

### 4. Routing between phones

- `api/routing.py`, the design's table in code:
  - a request that names the phone ("on my phone"), or the app's setting "runs on my phone" → the real phone;
  - an app known to refuse emulators → the real phone;
  - otherwise SkyLark on `envoy-test` and real apps on `envoy-real`;
  - no phone connected when one is needed → the emulator if the app works there, else a clear "connect your phone" and no run.
  The task shows the phone it uses and why.
- **Asking first:** before a task touches the real phone it waits on a "Use your Android phone for …?" request. It's on the web app and pushed to the iPhone, and only your session can answer. "Use an emulator instead" reroutes. No answer is never a yes.
- **The banner** (`testapps/banner`, a tiny Kotlin app): an overlay at the top of the phone ("Envoy is using this phone · Pause") while a task runs there. Its permission is granted over adb (`appops … SYSTEM_ALERT_WINDOW allow`). Pause is read by the Mac within a second, and becomes Resume.
- **Pausing:** a physical touch on the phone (seen by `getevent`; Envoy's own input is injected and never shows there), the foreground app changing without an action of Envoy's, or Pause on the banner. Each moves the phone to you, like a takeover ("Paused: you touched the phone"); the run continues when you resume, from the web app, the iPhone or the banner.

### 5. Live view and takeover for the real phone

- `WS /api/live/{id}` serves the phone through the scrcpy session: the same JPEG frames and input messages as for emulators, so the web app and the iPhone need no new client. Input goes through scrcpy's control socket.
- **Why not H.264 to the browser (the design's Tango + WebCodecs):** this reuses the protocol, metrics and touch handling already measured on the iPhone; one decoder on the Mac also gives the agent fast screenshots. If the latency target (<150 ms) fails, the browser decoder is the next step.
- **Secure screens are black from scrcpy** on a phone: the live view says "This screen is protected: sign in on the phone itself", and no frame of it is kept.
- The web app's phone switcher lists every phone the API knows (emulators and connected phones, with a running/off state).

### 6. The gate on the real phone

1. You connect the phone by USB and allow debugging. Envoy finds it, installs SkyLark's debug APK and the banner, and seeds the same fixtures through the hooks.
2. "Check me in for my flight **on my phone**" (from the web app or the iPhone). Envoy asks to use the phone; you allow it.
3. `skylark_check_in_flight` v1, compiled on `envoy-test`, runs on the phone: no model calls where locators match, and local repair if one doesn't. The banner shows the whole time.
4. The approval arrives as a push on the iPhone; you approve. The check-in is confirmed by SkyLark's state hook, and memory updates.
5. Also measured on the phone: the live view's latency on the Mac and the iPhone, a takeover, and Pause from a touch.

A scripted version (`eval/run_phase6.py gate`) runs the same routine on the phone with the scripted person (SkyLark only). **Stretch:** an `envoy-real` routine (Amazon or Starbucks as a guest) on the phone, if the phone has the app without a sign-in of mine. **Optional:** sign-in codes from the notification shade, only if the phone has a SIM.

## Testing

- **Offline:** the phone device with fake adb and uiautomator2; discovery; scrcpy's control messages (byte layouts) and stream parsing; routing rules; asking first (no answer is never a yes; only the session answers); pausing on a touch or a foreground change; the visual locator (crop match across densities, grounding fallback, compile from a trace); SAM output parsing; the live view on a fake stream.
- **Scripted (`eval/run_phase6.py`):** `portability`, `vision`, `stream` (the scrcpy path on an emulator: frame latency, input), `gate` (once the phone is connected).
- **On the real phone, with you:** the USB prompt, the gate, the live view and takeover on the Mac and the iPhone, a touch that pauses.

## Done means

- The gate passes on the real phone, scripted and with you approving from the iPhone.
- Portability is measured on `envoy-small`; grounding is measured against SAM 3.1 and the step model on no-tree targets, with a decision; a routine step on SkyLark's canvas seat map replays on both emulators.
- The live view and takeover work for the phone in the web app and on the iPhone, with measured latency.
- Tests and scripted checks pass. `docs/phase-6-results.md`, both copies of the design doc (a "Phase 6 results" section, design changes, the Android phone question answered), `THIRD_PARTY.md`, `README.md` and `docs/meta-feedback.md` (grounding and SAM 3.1 on UI screens) are updated; everything is committed and pushed.
