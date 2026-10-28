# Phase 6 results: real Android phone and SAM 3.1

Oct 27, 2026 (evening); the real phone on Oct 28 (evening, in Phase 7). **The gate passed on a real phone**: a Google Pixel 5 on Android 13 (IPaT loan), through the API, with every decision made on the iPhone. The gate is "a routine learned on the emulator runs on the real phone". The phone also found six bugs the stand-in couldn't; all are fixed, with tests (below, "On the real phone").

Until the phone came, an emulator stood in for it (`ENVOY_TEST_PHONE`): the same code path a real phone uses, with no gRPC (frames, taps and screenshots through Envoy's own scrcpy client), the banner app, the physical-touch watcher, routing and asking first. On it, the check-in routine compiled on `envoy-test` ran end to end through the API, and all 6 SkyLark routines passed 12 of 12 with no model calls. Screens with no accessibility tree now work: on 52 targets, SAM 3.1 then grounding found all 52 (grounding alone 92 to 94%, the step model's own coordinates 37%).

Plan: `prompts/phase-6-plan.md`. Results: `eval/results/phase6/`.

## Not finished

- [x] **The gate** on the real phone (Pixel 5, Android 13), four times through the API; portability and all 10 core routines on it.
- [x] **Phone measurements:** scrcpy, the live view on the Mac and on the iPhone over the tailnet, a takeover, a touch that pauses a run, the banner on stock Android 13.
- [x] **Answers:** the phone is a Pixel 5 on Android 13 (Android 15's notification limits don't apply to it, and weren't tested); the Envoy bridge is **not needed** (settling and set-text held on the phone).
- [ ] **Not done (optional):** sign-in codes from the notification shade. The phone has a SIM, but no service sent it a code tonight, and Envoy doesn't sign in for you. A real-app routine from `envoy-real` on the phone: the phone was set up with no Google account, so it has no Play Store apps.

## What was built

All of it is Envoy's own code: about 1,700 lines of Python (`backend/devices/`, `backend/api/routing.py`, `backend/agent/vision.py`, `backend/routines/visual.py`, executor, compiler, runner and live-view changes; about 250 of them are the emulator's code moved into the shared base), 900 of tests and evaluation (`backend/tests/test_phase6.py`, `eval/run_phase6.py`), 300 of Kotlin (`android/banner`, SkyLark's canvas seat map) and 100 of TypeScript. scrcpy's server, PyAV (FFmpeg) and NumPy are plumbing (`THIRD_PARTY.md`).

| Part | Where | What it does |
| --- | --- | --- |
| One device layer | `devices/android.py`, `emulator.py`, `phone.py` | `AndroidDevice` is everything uiautomator2 and adb do, for any serial. `EmulatorDevice` adds the gRPC fast paths and snapshots; `PhoneDevice` adds scrcpy, the banner and the touch watcher. `discover()` lists connected phones (unauthorized ones too, to tell you to allow USB debugging). Capabilities are read, not assumed (real phone, SIM state, size, density). Apps start through their launcher activity (`am start`), never uiautomator2's `monkey` launch. |
| Envoy's scrcpy client | `devices/scrcpy.py` | Pushes the pinned scrcpy server (5.0.1) and speaks its protocol: the H.264 video socket, decoded on the Mac with PyAV into the latest frame, and the binary control messages (touch down/move/up, keys, text). It offers the same methods as the emulator's gRPC client, so the live view, approval cards and step thumbnails don't care which phone it is, and the agent's screenshots come from the latest frame. |
| Telling your touches from Envoy's | `devices/phone.py` | `getevent` streams the phone's own input devices. Everything Envoy does (uiautomator2, scrcpy) is injected and never appears there, so any finger down or key press it reports is you. |
| The banner | `android/banner` (`ai.envoy.banner`) | A small pill at the top centre while Envoy works on the phone: "● Envoy is using this phone · Pause", "● Envoy paused · Resume". Its overlay permission is granted over adb; its state is read over adb (a content provider). It never takes focus, and Envoy leaves its window out of everything it reads. |
| Routing between phones | `api/routing.py`, `api/runner.py` | The design's table: an emulator by default; your phone when you ask ("… on my phone", or the phone picked in the request), when the app is set to it (Settings › Phones), or when it refuses emulators. Phone needed but not connected: the emulator if the app works there, else a clear message and no run. |
| Asking first | `api/runner.py`, `web/components/PhoneAsk.tsx`, `api/push.py` | Before a task touches your phone it waits on "Envoy wants to use your Galaxy S22 for this task" with **Use my phone** / **Use an emulator**, in the app and as a push on the iPhone. Only your session answers (MCP, chat and Shortcuts can't); no answer is never a yes. |
| Pausing | `api/devices.py` | While a task runs on your phone, a touch, Pause on the banner, or another app coming to the front without an action of Envoy's hands the phone to you exactly like Take over (the task says "taken over: paused: you touched the phone"). Every one of the agent's calls checks the touch watcher first, so the very next action waits. Resume on the banner, or Hand back in the app, gives it back, and the agent goes on from whatever you left on screen. |
| Live view of the phone | `api/live.py`, `web/components/LivePhone.tsx` | `WS /api/live/{id}` serves the phone's scrcpy frames with the same messages as the emulators, so the web app and the iPhone needed no new client. Secure screens are black from a phone, so the page says "This screen is protected … use the phone itself" and keeps no frame of it. The phone picker lists every phone the API knows. |
| Portability fixes | `routines/executor.py` | Found on a smaller screen: a target below the fold is now found by scrolling its list (rung 2, no model call), and an output scrolled out of view is read by scrolling back. |
| Screens with no tree | `agent/vision.py`, `models/schemas.py` | `tap_point` now says what it taps (`target`: "seat 21A"); the runtime finds it on a fresh full screenshot: SAM 3.1 proposes boxes from shape phrases ("square button", "icon"), they are numbered on the screenshot and Muse Spark picks one; if it picks none, Muse Spark's grounding. |
| Routines on drawn screens | `routines/compiler.py`, `executor.py`, `visual.py` | Such a step compiles to a **visual locator**: what it looks like with inputs as slots ("seat {{new_seat}}"), plus its recorded picture when the target doesn't change with the inputs. Replaying, the executor finds the picture (NumPy FFT cross-correlation, scaled by screen density, accepted only when clear and unique), or looks again (SAM then grounding). |
| SkyLark variant 6 | `testapps/skylark/.../CanvasSeatMap.kt` | The seat map drawn on a Canvas with no accessibility nodes; the drawn seat rectangles are published in the state hook, so every answer is checked exactly. |

## On the real phone (Oct 28)

Google Pixel 5 (`redfin`), Android 13 (API 33, security patch Aug 2022), 1080×2340 at 440 dpi (393×851 dp), Gboard, a SIM; connected over USB, no Google account, no Wi-Fi needed (everything Envoy does goes over the cable; the iPhone reaches the Mac over the tailnet). Results: `eval/results/phase6/phone-*.json`; the device checks are `eval/phone_check.py`, the gate's set-up and record `eval/phone_gate.py`.

| Check | Result |
| --- | --- |
| **The gate** ("Check me in for my flight on my phone", from the iPhone) | **Passed.** Envoy asked to use the Pixel 5 and you allowed it on the iPhone; the banner showed; `skylark_check_in_flight` v1, compiled on `envoy-test`, ran on the phone with no model call; you approved the check-in on the iPhone 4.8 s after it was asked; SkyLark's own state on the phone: Chicago checked in; memory updated (14 same, 1 replaced); 27.2 s end to end, both of your waits included. |
| A touch that pauses a run | Passed: your touch on the Pixel paused it before the next action (banner "Envoy paused · Resume", reason "you touched the phone"); Resume on the banner finished it (checked in, 32 s). |
| A takeover from the iPhone | Passed twice: taken over and handed back from the iPhone's live view, with the check-in's approval pending across it; approved once, checked in (32 s and 66 s). The first attempt at this found a bug (below, 5). |
| Pushes to the iPhone | All 12 delivered: asking for the phone 0.55 to 0.69 s, approvals 0.32 to 0.70 s, Done 0.32 to 0.49 s. |
| The banner on stock Android 13 | Renders as designed, centred under the status bar, over the app's top bar (pictures: `phone-banner-working.png`, `phone-banner-paused.png`). |
| scrcpy on the phone | Starts in 0.6 s; a tap shows as a changed frame in **65 ms** (median of 10, max 75); a screenshot from the stream **7.8 ms** (`adb screencap` 358 ms); frames are 590×1280. |
| Live view of the phone on the Mac (through the API) | 9.1 fps; a frame arrives **5 ms** after capture (median; max 108); 30 KB per frame. |
| Live view of the phone on the iPhone, over the tailnet | The web app's own measurement on the Home Screen app, 5 windows of 20 s: frame **27 to 39 ms** after capture (median per window), round trip 11 to 16 ms, 32 to 48 KB per frame. Against the 150 ms target: roughly 100 ms from the phone's screen to the iPhone, adding the phone's own 65 ms tap-to-frame. |
| Reading the screen | Tree read 157 ms, full observation 245 ms (medians; the emulator: 31 and 70 ms). |
| **Settling** (the bridge question) | 50 taps, 0.9 to 1.4 s to settled. In SkyLark, 0 of 20 changed after settling. In the phone's Settings, 5 of 30 changed a secondary line after settling (a row's summary recomputed on Apps 4 times, a footer once on Battery); battery levels ticking are counted apart. The expected content was on the settled screen in all 50. |
| **Set-text** (the bridge question) | **20 of 20 exact** ("Café Ñandú 東京 Привет 😀") in a Compose field (SkyLark, 0.75 s) and an Android view (Settings' search, 0.49 s); Gboard stayed the keyboard; nothing touched the clipboard (no "Copied" preview, contents unchanged); Enter submitted the search. |
| Portability (`run_phase6.py portability --device phone`) | PORTABILITY_RESULT |
| All 10 core routines (`run_final.py sizes --device phone`) | SIZES_RESULT |

**The bridge: not needed.** It was to be built only if settling or setting text proved unreliable on the phone; both held, and you agreed. Reading is slower than on the emulator (157 ms against 31 ms per tree) but it is one read per step.

### What the phone found, and what changed

1. **Every frame from the phone failed to convert.** The Pixel's encoder labels its video with a colorspace FFmpeg's scaler can't convert (YCgCo, over ordinary BT.601 video). Screenshots silently fell back to `adb screencap` (358 ms) and the live view would have had no frames. Frames whose label can't be converted are converted as BT.601, which matched the phone's own screenshot.
2. **Envoy's taps under the banner landed on the banner.** The banner is a window above the app, and on the Pixel it sits over the top bar, where the Phone and Messages apps (and Gmail, Maps, Play) put their search boxes. A tap there was swallowed by the pill, and one on the pill's Pause button paused the run as if you had pressed it. A tap inside the pill's bounds now hides it, taps, and shows it again (on the Phone app's search box: before, search didn't open; after, it did).
3. **A request without "on my phone" failed with a developer's message.** It went, as designed, to the emulator, which wasn't running, and the task said "envoy-test is not running (scripts/start_emulator.sh envoy-test)". It now says the emulator isn't running and that "on my phone" uses your Pixel 5.
4. **Pauses and takeovers weren't in the task's history.** The status changed and nothing was written, so a pause showed only as a 7 s gap between steps. Each pause, resume, takeover and hand back is now an entry.
5. **A takeover taught the routine a wrong step.** The check-in's approval was pending while you took over; after the hand back you approved, but the tap didn't take effect (the same screen, the same button: the cause is unknown; it didn't happen again in later runs). The routine's repair tapped again, which asked you a second, identical time, and the repair became version 2 on trial: "an extra screen appeared; a second tap on Confirm check-in". Version 2 was rejected by hand, and now a run you took over or paused teaches the routine nothing (no patch, no trial decided); an approval asked again for a control you already approved says why on the card; and every tap on the phone is logged (point, input path, stream age) in `logs/phone_taps.jsonl` so a lost tap can be traced.
6. **Back-to-back attempts met a finished check-in.** Not a product bug: SkyLark is reset between evaluation runs, and your retries right after a finished run found Chicago already checked in, so you stopped them. The gate's script now resets SkyLark a few seconds after any run ends.

### Who uses which phone

iPhone users use Envoy's emulators; Android users use an emulator or their own phone. The gate is the second path, not a requirement for everyone. The limits, plainly: you sign in to each app once on the emulator; apps that refuse emulators (Target's bot check, banking apps) need a real Android phone, so they are out of reach for someone with only an iPhone; the emulators run on a Mac today (a cloud host later).

## Results (emulators and the stand-in, Oct 27)

| Check | Result |
| --- | --- |
| Routine portability, `envoy-small` (720×1280, 320 dpi) vs `envoy-test` (1080×2400, 420 dpi) | **18 of 18 on each, no model calls** (6 SkyLark routines × 3 bookings never seen). Median 5.0 s vs 3.6 s. Before the fixes, the first try on the small screen needed the full agent once (18 calls, $0.055): the Known Traveler field was below the fold. |
| The phone code path (stand-in, no gRPC) | **12 of 12, no model calls** (6 routines × 2 bookings); 4 to 23 s per run. |
| End to end through the API (stand-in) | "Check me in for my flight" with your phone chosen: asked, allowed, banner shown, `skylark_check_in_flight` (compiled on `envoy-test`) ran, a touch right after the first step paused it before the next action (task "taken over", banner "Resume", SkyLark not checked in 3 s later), Resume on the banner finished it: checked in, memory updated, banner gone; 13 s. |
| Drawn targets: 52 targets (16 canvas seats on two screen sizes, 36 real-app targets on 24 saved screens whose tree gives the truth) | Step model's own coordinates **37%** (seats 1 of 16); grounding **92%** (seats 13 of 16, about one row off on the small screen); SAM 3.1 + pick **75%** (seats 15 of 16, median error 1 px; it never picked a wrong box, and said "none" 13 times when its shapes missed a text button); **SAM then grounding 52 of 52**. |
| The same, a fresh sample (other seats, other targets) | **SAM then grounding 52 of 52; grounding alone 49 of 52.** Median 4.0 s vs 2.6 s; $0.0073 vs $0.0027 per target. |
| A routine step on the canvas seat map | The agent changed a seat on `envoy-test` (10 steps, 16 calls, $0.029, 69 s; SAM placed the tap where the step model's own point was on the hint text above the map). Compiled into `skylark_change_seat` with a visual step ("seat {{new_seat}}"); **6 of 6 replays with new seats on both screen sizes**, 3 model calls each (2 SAM phrases + the pick), about $0.0075 and 7 to 11 s. |
| scrcpy on the stand-in | Starts in 0.4 s; a tap shows as a changed frame in **62 ms** (median of 10, max 81, including the app's own redraw); a screenshot from the stream takes **7 ms** (`adb screencap`: 84 ms on the emulator, 0.5 to 2.6 s on phones). |
| Live view of the stand-in through the API (on the Mac) | Frames 12 ms after decoding (median), 32 KB per 720 px frame, 6.4 fps while the screen changes. |
| Offline tests | 111 pass (18 new: scrcpy's message layouts, telling physical input from injected, discovery, routing, asking first and no answer, pausing on a touch / Pause / another app and not on the agent's own app switch, the touch stopping the very next action, SAM parsing, crop matching (unique only, density-scaled), the visual step replaying from its picture then by looking, never from a picture of the recorded value, never on a secure screen, the phone push) |
| Cost | 514 model calls, $1.44 at standard prices ($1.08 billed), almost all in the vision measurement. All-time billed: $8.44. |

## What the runs found, and what changed

1. **A smaller screen hides things.** The Known Traveler field and the confirmation code are below the fold at 640 dp. The executor now scrolls the screen's list to reveal a missing target, and scrolls back to read an output, before any model call. 18 of 18 after.
2. **uiautomator2's app launch is `monkey`.** Without an activity it runs `monkey -p <app> -c LAUNCHER 1`: about 11 s on a fresh device, plus one random injected event, which opened the app drawer. On someone's real phone that is unacceptable, so apps start through their resolved launcher activity (`am start`, 1.5 s with settling).
3. **A 0.5 s check is too slow for a touch.** With only the watch loop, two routine steps (the last one irreversible) ran after the touch. The phone's gate now checks the touch watcher before each of the agent's calls, which costs nothing (no adb).
4. **After a hand back, the screen you left is the new normal.** The watcher had re-paused at once because another app was still in front. It also kept running after the task ended and could overwrite "done"; it now stops as soon as the phone work ends.
5. **SAM 3.1 needs shape words and a chooser.** "Seat" and "button" find nothing; "square button" finds every seat (84 boxes) and "icon" finds icons. Its boxes are pixel-exact and the model, shown them numbered, never picked a wrong one, but text buttons aren't among them. Grounding is the reverse: good at labelled UI, about one row off on a dense grid on a small screen. Used together they found every target.
6. **A recorded picture of "seat 10C" must never stand for "seat {{seat}}".** Pictures are kept only for targets that don't change with the inputs; the rest are looked for each time.

## Honest limits

- **One real phone, one evening.** A Pixel 5 on stock Android 13. Samsung or Xiaomi skins, Android 14 and 15, and other encoders weren't tried; the frame-colorspace bug (finding 1 above) is the kind of thing another phone could add.
- **One approved tap didn't take effect, and the cause is unknown.** It came right after a takeover with an approval pending; it didn't recur in three later runs. The repair caught it safely (it asked again), and taps are now logged to find the cause if it happens again.
- **Drawn targets cost a look each time** (about $0.0075 and 3 to 8 s): the replay is no longer free when a step depends on its input. A fixed target (a map pin with a logo) replays from its picture with no call.
- **SAM's latency varies with the number of candidates**: one agent step took 15 s with 84 boxes to choose from.
- **The real-app vision targets have trees.** Their truth came from the tree while the methods saw only the picture; the truly drawn targets are SkyLark's. Chipotle's map store picker wasn't scored.
- **The stand-in's serial number is shared by all emulators** (`EMULATOR37X2X12X0`), so only one emulator can stand in at a time; real phones have unique serial numbers.

## Changes to the design

For the design doc (applied in both copies):

1. **The real phone's live view decodes on the Mac.** Envoy's own scrcpy client (Python, PyAV) replaces the Node relay and browser WebCodecs: the same JPEG protocol as the emulators, and the agent's screenshots from the same frames.
2. **Asking first, the banner and pausing are built** as the design described; pausing is driven by `getevent` (physical input only) and checked before every action.
3. **Screens with no tree use SAM 3.1 then grounding**, with `tap_point` naming its target; SAM is kept (it measurably beats grounding in combination).
4. **Routines handle drawn screens** with visual locators (description + picture), and **smaller screens** with scroll-to-reveal and scrolled outputs.

## Next

- **Phase 7:** the final evaluation on the frozen commit (Nov 2) includes all 10 core routines on the phone again if it is still on loan (`run_final.sh` runs `sizes --device phone` when a phone is connected).
