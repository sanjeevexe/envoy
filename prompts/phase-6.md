# Phase 6: Real Android phone and SAM 3.1

You are continuing **Envoy**, my solo project for the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026, indie track, "Push the Frontier"). Submissions are due **Nov 4, 9:00 PM ET**; features freeze **Nov 2**, so Nov 3–4 go to evaluation, the demo video and the write-up. Envoy is a Muse-powered agent that operates Android apps on emulated phones, compiles successful runs into reusable **app routines**, and keeps a shared **memory graph** across web, voice, iPhone and MCP clients.

Phases 0–5 are done, and their gates passed. This is the last build phase: it puts Envoy on a real Android phone and handles screens that have no accessibility tree. Take your time and do your best work. You have full permission to do whatever this needs on this Mac (installs, emulators, commits, pushes to the private repo), and to drive my iPhone through iPhone Mirroring, with these exceptions:
- Never type passwords or sign in to accounts. Sign-ins are mine (including Google, Apple and Tailscale), on the Android phone too.
- Never use my payment methods.
- Before any change visible outside this Mac (making the repo public, a public tunnel, submitting forms, posting), ask me.

## Read first (in this order)

1. `docs/technical-design.md`, especially **Device layer** (the Device interface, Envoy bridge, Screenshots and video, **Backend 2: a real Android phone**, **Choosing which phone runs a task**), **Agent runtime › Screens without an accessibility tree**, **App routines** (locators, portability), **Live view and sign-in** (Streaming, Take over, Sign-in, Sign-in codes), **Safety** and **Build phases**. The live version is https://claude.ai/artifact/Sf51zMf4SMi5ZZmJabgPR5; if the two disagree, the live one wins.
2. `docs/phase-5-results.md` (the iPhone companion this phase must keep working), `docs/phase-4-results.md` (live view, takeover, approvals), and `docs/phase-2-results.md` (what routines replay, the visual-crop stub, Chipotle's store picker).
3. `docs/phase-0-findings.md` › A3 (device speed), the grounding and SAM 3.1 checks (4 and 6), and the real-app table.
4. `backend/devices/`, `backend/routines/README.md`, `testapps/README.md`, `backend/api/README.md`, `web/README.md`, and `prompts/phase-5-plan.md` (the plan format I liked).
5. The memory notes in `~/.claude/projects/-Users-sanjeevvarma-Desktop-Envoy/memory/` (durable preferences: notifying me when I'm needed, UI testing, the iPhone companion, Muse testing).

## Where things stand (Oct 27, night)

**Environment**
- MacBook Pro M5 Pro, 24 GB. `source scripts/env.sh` (already in `~/.zshrc`). Python 3.13 via uv: `uv run --project backend …`. Node 26.5, npm 11. **scrcpy 5.0.1** is installed (Homebrew); adb is in the Android SDK's `platform-tools`.
- Emulators: `envoy-test` (SkyLark; snapshots allowed; gRPC 8554) and `envoy-real` (real apps; never snapshot-restored; always stopped with `scripts/stop_emulator.sh`). Start with `scripts/start_emulator.sh <avd> [--window]`. At most two run at once.
- Repo: `~/Desktop/Envoy`, private GitHub repo `sanjeevexe/envoy` (must be public by Nov 4; I'll say when). MIT.
- Meta API: a **shared key** in `.env`, about **$30 left** ($7.36 billed so far; all spend is in `logs/model_costs.jsonl`). The Contributor tier is allowed for SkyLark test data only, never real apps or real data.
- **The Android phone** is a loan from IPaT, arriving **Wednesday, Oct 28**. I'll tell you its model and Android version when I have it, and I'll turn on Developer options. I factory-reset it when I give it back, so set it up however Envoy needs.
- **My iPhone** (iOS 26.6) has Envoy on its Home Screen, paired, with push on; Tailscale Serve gives the API `https://sanjeevs-macbook-pro.tailffb391.ts.net:8443` (tailnet only). You can drive the iPhone through iPhone Mirroring, which blocks its microphone. Muse route 2 works through `scripts/start_muse_test.sh`; I start tunnels and enter tokens.

**Running the demo (Phase 5).** The API may still be running (`curl http://127.0.0.1:8700/healthz`). If it isn't:
```bash
scripts/start_emulator.sh envoy-test
uv run --project backend python -m api                       # 127.0.0.1:8700: API, /mcp, the web app (web/out)
scripts/serve_tailnet.sh status                              # Tailscale Serve on :8443 (on|off|status)
(cd web && npm run build)                                    # after web changes (the API serves web/out as it is)
```
- **Never read `data/api/session_token`** (my login), and don't print the API's output log (it shows my sign-in link). For your own browser checks, run a test copy on port 8701 with your own token (the `envoy-ui-testing` memory note). Scripts may read the token internally.
- 93 offline tests: `uv run --project backend pytest -q backend/tests`. Scripted checks: `eval/run_phase4.py` (10/10), `eval/run_phase5.py` (8/8), `eval/run_photos.py`; `eval/iphone_gate.py prepare|report|restore` for runs on my iPhone.

**What exists that this phase builds on**
- `backend/devices/`: the `Device` interface and `EmulatorDevice`: uiautomator2 reads the tree and types (accessibility set-text, never the clipboard); the emulator's gRPC takes screenshots (6 ms) and taps (under 1 ms). There is no device for a real phone yet.
- `backend/routines/`: routines compiled from a successful run, with attribute locators (resource ID, text, description, class, neighbors), step checks, local repair and versions. `skylark_check_in_flight` replays with no model calls. The visual-crop locator for elements with no usable attributes is a stub (`routines/model.py`). Portability across screen sizes and to a real phone is untested.
- `backend/agent/`: the agent loop; `tap_point` is allowed only when the screen has no usable elements or a screenshot came with the step. `backend/models/adapter.py` has a `grounding` job and calls SAM 3.1 (Phase 0 checks), but the agent uses neither yet.
- Live view: the emulator's gRPC frames as JPEG over `WS /api/live/{avd}`, takeover leases, touch and keyboard from the web app and the iPhone.
- SkyLark (`testapps/skylark`, a debug APK): check-in, a seat map with one tagged element per seat, layout variants 0–5, and test hooks (broadcasts and a content provider) that work on any phone the debug APK is installed on.
- On `envoy-real`: Amazon, Starbucks and DoorDash routines work; Chipotle's map store picker needs gestures and visual grounding; Target's bot check returns on fresh launches.

**Facts that shape this phase** (measured or decided; don't re-derive them)
- **Connecting the phone:** USB is simplest (a cable, then I allow USB debugging on the phone). Wireless debugging (Android 11+) pairs with a code shown on the phone; campus Wi-Fi isolates devices, so wireless may need the Mac on the phone's hotspot. Samsung phones need Auto Blocker off.
- **On a real phone there is no gRPC:** screenshots come from `adb screencap` (0.5 to 2.6 s on phones) or the latest scrcpy frame, and taps go through uiautomator2 (about 150 ms). Reading the tree through uiautomator2 is fast (31 ms on the emulator).
- **Secure screens** (`FLAG_SECURE`, common for sign-in and payment) are black in scrcpy and `adb screencap` on real phones. On a real phone I sign in on the phone itself.
- **The design's live view for real phones:** the scrcpy server's H.264 stream, relayed to the browser and decoded with WebCodecs (the Tango libraries, `@yume-chan/adb` and `@yume-chan/adb-scrcpy`; pin the scrcpy server version they expect). Safari supports WebCodecs fully from iOS 26. Target: under 150 ms from the phone to the screen. If a simpler path meets the target on the Mac and the iPhone, say why you chose it.
- **Before using the real phone, Envoy asks me**, shows a banner on the phone while it works, and pauses when the screen changes in a way its last action didn't cause, or when I press Pause on the banner.
- **Android versions:** 13+ restricts accessibility access for sideloaded apps (it matters only if you build the Envoy bridge); 15+ hides codes from untrusted notification readers.
- **Grounding** (Phase 0): Muse Spark returns boxes on a 0–1000 grid (values can exceed 1000: clamp), 3 of 3 targets on 1080×2400 screenshots, center error at most 22 px, about 2 s per call. A 1080×2400 screenshot costs about 3,230 input tokens, so downscale.
- **SAM 3.1** (Phase 0): `/v1/responses` with `model: "sam-3.1"`; it returns special-token text (boxes, base85 masks), with confidences only when asked. It finds UI parts from specific phrases ("toggle switch", "search bar", "icon") and nothing for "button" or "text". About 0.55 s and $0.0025 per image. The design keeps it only if it measurably beats grounding alone.

## The job: Phase 6

Build what the design doc's **Device layer** and **Screens without an accessibility tree** sections describe. The **gate** (from the build-phases diagram): **a routine learned on the emulator runs on the real phone.**

The phone arrives on Oct 28, so start with the parts that don't need it (1–3), then do the phone work (4–6).

1. **A device for real phones.** The `Device` interface over uiautomator2 and adb for any connected serial: observe, act, launch, settle, screenshots without gRPC, and honest capabilities (real phone, SIM, no snapshots, screen size). Find connected phones on their own. Keep the emulator's fast paths.
2. **Portability before the phone.** Create a third emulator profile with a different screen size and density (a small phone, for example) and run the SkyLark routines learned on `envoy-test` there unchanged. Measure them, and fix whatever depends on screen size (scrolling to off-screen elements, coordinates, timing). Only two emulators run at once.
3. **Screens with no accessibility tree.**
   - Add a SkyLark layout variant with a screen drawn on a canvas, with no accessibility nodes (the seat map is a natural one), so results can be checked exactly.
   - Give the agent visual grounding for such screens (a description in, a `tap_point` out), and try SAM 3.1 as a helper (candidate regions the model chooses between).
   - Measure both on a fixed set of targets: the SkyLark canvas screen, plus real screens such as Chipotle's store picker on `envoy-real`. Keep SAM only if it helps, and record the numbers either way.
   - Replace the visual-crop stub, so a routine step on a no-tree screen replays, including on a different screen size.
4. **Routing between phones.** Follow the design's table for choosing the phone. Show which phone a task uses in the web app and on the iPhone. Ask me before the real phone is used, show the banner on the phone while it works, and pause as the design says. With no phone connected, a task runs on an emulator or tells me the app is unsupported, never silently.
5. **Live view and takeover for the real phone** in the web app and on the iPhone: touch and keyboard as on the emulator, and a clear note when the screen is secure (sign in on the phone itself). Measure latency on the Mac and on the iPhone over the tailnet.
6. **The gate on the real phone.**
   - Install SkyLark's debug APK on the phone and seed the same fixtures through its hooks.
   - Run `skylark_check_in_flight`, compiled on `envoy-test`, on the phone: no model calls where locators match, and local repair where they don't.
   - The approval arrives as a push on my iPhone, and I approve. Check the result through SkyLark's state hook, and check that memory updates.
   - **Stretch:** a real-app routine learned on `envoy-real` (Amazon or Starbucks, as a guest) runs on the phone. Installing apps from the Play Store needs a Google account on the phone, and that's my call.
7. **Sign-in codes on a real phone (optional; only if the phone has a SIM).** Test whether the agent can read a code from the notification shade on screen (Android 15+ hides codes from notification readers). I'll send the text. Record the answer either way, and don't build more than the test.

Write the plan as `prompts/phase-6-plan.md` first (like `prompts/phase-5-plan.md`), then build. The **Envoy bridge** stays unbuilt unless the real phone shows that settling or set-text fails; if you think it's needed, show me the measurement first.

## Testing

- **Offline tests** for the real-phone device (with fakes for adb and uiautomator2), the routing rules, asking before the real phone is used, pause on an unexpected screen change, the no-tree routine step, and parsing grounding and SAM output.
- **Scripted:** `eval/run_phase6.py`: the SkyLark routines on the second emulator profile (success, model calls, time); grounding against SAM on the no-tree target set (accuracy, latency, cost); and, once the phone is connected, the gate.
- **On the real phone** (with me for the USB prompt, pairing and any sign-in): the gate, the live view on the Mac and on the iPhone, and a takeover. When you need me, ask right away and send a notification.

## Rules and constraints

- **The demo may only show work built during the hackathon (Oct 27 – Nov 4), clearly identified**, or the project can be disqualified. Keep `THIRD_PARTY.md` current (the Tango libraries or scrcpy, for example). Open source is plumbing; the routines, memory, policy and routing are ours.
- **Budget:** spend where it makes the work better; avoid needless repeats; use `low` effort where it works; downscale screenshots. Contributor tier for SkyLark only.
- **Safety is unchanged, plus the real phone:** approvals come only from my session (or the scripted person on SkyLark); MCP, chat, voice, Shortcuts and pushes can never approve; nothing types passwords; secure screens are never stored or sent to a model; the real phone is used only after I say yes, with the banner showing and Pause working.
- Keep `envoy-real` long-lived (never restore a snapshot; stop it with `scripts/stop_emulator.sh`). At most two emulators run at once, including the new profile.
- Live design doc: edit through the Claude Docs connector with find-and-replace, check `sinceRev` first, and never overwrite someone else's edit.
- Commit after each meaningful step and push.

## Done means

- The gate passes on the real phone: SkyLark's check-in routine, learned on the emulator, runs on the phone; I approve from the iPhone; the check-in is confirmed by SkyLark's state hook; memory updates.
- Routine portability is measured on a second emulator profile. Screens with no tree work through grounding, SAM 3.1 is measured against it, and a routine step on such a screen replays.
- The live view and takeover work for the real phone, in the web app and on the iPhone, with measured latency.
- Tests and the scripted checks pass. These are updated: `docs/phase-6-results.md`, both copies of the design doc (a "Phase 6 results" section, any design changes, and the Android phone open question answered), `THIRD_PARTY.md`, `README.md`, and `docs/meta-feedback.md` (grounding and SAM 3.1 on UI screens). Everything is committed and pushed.
- Finish with a short summary:
  1. what was built
  2. the key numbers: routine success and model calls on the real phone and the second emulator profile, live-view latency for the phone, and grounding against SAM 3.1 (accuracy, latency, cost)
  3. anything that changes the design
  4. what I need to do next, including what to set up for Phase 7 (evaluation, the demo video, the write-up and making the repo public)
