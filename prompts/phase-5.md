# Phase 5: iPhone companion and voice

You are continuing **Envoy**, my solo project for the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026, indie track, "Push the Frontier"). Submissions are due **Nov 4, 9:00 PM ET**; features freeze **Nov 2**, so Nov 3–4 go to evaluation, the demo video and the write-up. Envoy is a Muse-powered agent that operates Android apps on emulated phones, compiles successful runs into reusable **app routines**, and keeps a shared **memory graph** across web, voice, iPhone and MCP clients.

Phases 0–4 are done, and their gates passed. This phase makes Envoy usable from my iPhone and by voice. Take your time and do your best work. You have full permission to do whatever this needs on this Mac (installs, emulators, commits, pushes to the private repo), with these exceptions:
- Never type passwords or sign in to accounts. Sign-ins are mine (including Tailscale, Apple and Google).
- Never use my payment methods.
- Before any change visible outside this Mac (making the repo public, a public tunnel, submitting forms, posting), ask me.

## Read first (in this order)

1. `docs/technical-design.md`, especially **Interfaces and integrations** (Web app, Voice, **iPhone companion app**), **Live view and sign-in** (Streaming, Take over, Sign-in codes), **Safety › Approvals** and **Photos and messages**, and **Build phases**. The live version is https://claude.ai/artifact/Sf51zMf4SMi5ZZmJabgPR5; if the two disagree, the live one wins.
2. `docs/phase-4-results.md`: the API, live view, approvals (including the configurable modes), MCP server and web app this phase builds on, and what the gate runs found.
3. `backend/api/README.md`, `web/README.md`, `backend/memory/README.md`, `prompts/phase-4.md` (the plan format I liked).
4. `docs/phase-0-findings.md` › Meta API (the Voice Transcribe row) and B2 (the Muse connector).
5. The memory notes in `~/.claude/projects/-Users-sanjeevvarma-Desktop-Envoy/memory/` (durable preferences: how I test Muse through iPhone Mirroring, notifying me when I'm needed, UI testing).

## Where things stand (Oct 27, evening)

**Environment**
- MacBook Pro M5 Pro, 24 GB. `source scripts/env.sh` (already in `~/.zshrc`). Python 3.13 via uv: `uv run --project backend …`. Node 26, npm 11.
- Emulators: `envoy-test` (SkyLark; snapshots allowed; gRPC 8554) and `envoy-real` (real apps; never snapshot-restored; always stopped with `scripts/stop_emulator.sh`). Start with `scripts/start_emulator.sh <avd> [--window]`. At most two run at once.
- Repo: `~/Desktop/Envoy`, private GitHub repo `sanjeevexe/envoy` (must be public by Nov 4; I'll say when). MIT.
- Meta API: a **shared key** in `.env`, about **$31 left** (all-time spend is in `logs/model_costs.jsonl`; $6.94 billed so far). The Contributor tier is allowed for SkyLark test data only, never real apps or real data.
- **Tailscale is installed and signed in** on the Mac (`sanjeevs-macbook-pro`) and my iPhone (`iphone174`), same tailnet. The Mac app's CLI is `/Applications/Tailscale.app/Contents/MacOS/Tailscale` (version 1.104.2; not on the PATH). Also installed: `cloudflared` (the Phase 0 Muse connector test). Not installed: mkcert.
- My iPhone: you can see and drive it through **iPhone Mirroring** on this Mac (computer use), as in the Phase 0 Muse test. I start tunnels and enter tokens myself.

**Running the demo (Phase 4).** Nothing of Envoy is running when you start: the API is stopped (`envoy-test` may still be up; `start_emulator.sh` copes either way). **Before you begin, start it:** the emulator, then `demo_setup.py`, then the API in the background, and check `curl http://127.0.0.1:8700/healthz`.
```bash
scripts/start_emulator.sh envoy-test
uv run --project backend python scripts/demo_setup.py        # SkyLark signed out + demo memory (with the API stopped)
uv run --project backend python -m api                       # 127.0.0.1:8700: API, /mcp, the web app (web/out)
open "http://127.0.0.1:8700/login?k=$(cat data/api/session_token)"   # I run this; you never read that token
(cd web && npm run build)                                    # after web changes, then restart the API
```
- **Never read `data/api/session_token`** (my login). For your own browser checks, run a test copy on port 8701 with your own token: see the `envoy-ui-testing` memory note. Scripts may read the token internally (`eval/run_phase4.py` does).
- `eval/run_phase4.py`: the Phase 4 gate with a scripted person (10/10). `eval/run_approval_modes.py`: the approval modes (4/4). 79 offline tests: `uv run --project backend pytest -q backend/tests`.

**What exists that this phase builds on**
- `backend/api/`: tasks (SQLite `data/api/envoy.db`), the runner (routine or agent; sign-in hand-off; memory written after Done), one event stream (`WS /api/events`), web approvals (`WebApprover`: only the session decides, by POST with a per-approval nonce; bound to the app's own screen; no answer is never an approval), configurable approval modes (`policy/approval_rules.py`; default "ask unless I asked for it"; money always asks), takeover leases (the agent waits at its next phone call), the live view (`WS /api/live/{avd}`: emulator gRPC frames as JPEG; input only during takeover), chat on Muse Spark (`api/chat.py`), the scheduler, and the MCP server at `/mcp` (no approve tool).
- `web/`: Next.js 16 static export served by the API: Chat, Tasks, Approvals, Memory (Cytoscape), Routines, Triggers, Settings, the live phone panel, and `/approve?id=…` (opening it decides nothing).
- `backend/memory/`: the graph store, extraction from emails and **app screens** (Muse Spark, values checked against the source), retrieval with sources and ages, redaction (cards, codes, ID numbers, password fields).
- SkyLark shows a **boarding pass** after check-in (seat, gate, boarding time, group, barcode): the natural screenshot for the gate.

**Facts that shape this phase** (measured or decided; don't re-derive them)
- iOS supports **Web Push for Home Screen web apps from iOS 16.4**, only over **HTTPS**, only after the user adds the app to the Home Screen and allows notifications from a user gesture. Web notifications have no action buttons: tapping one opens the approval page.
- **Muse Voice Transcribe** (`muse-voice-transcribe-1.0`): real-time speech to text over `wss://api.meta.ai/v1/asr/realtime`, auth in the handshake JSON, $0.18 per audio hour. The API key must stay on the server: the browser streams audio to the backend, which relays it. Read the exact protocol (audio format, events, turn detection) at dev.meta.ai/docs before building. Fallback: the browser's own speech recognition.
- Spoken replies use the device's built-in speech (`speechSynthesis`): free and on-device.
- The live view is JPEG frames over a WebSocket (18–60 ms locally). Touch on a phone screen needs pointer events tuned for touch (no hover; scroll vs. tap).
- Photos: only the photos I pick or share are sent; text is extracted on the server and **the image is deleted once its facts are saved**; every fact links to its source and can be deleted.
- Approval links may be fetched by link previews (Muse did this in Phase 0): nothing may act on a GET.

## The job: Phase 5

Build what the design doc's **iPhone companion app** and **Voice** sections describe. The **gate** (from the build-phases diagram): **approve from the iPhone; a boarding-pass screenshot becomes a fact.**

1. **HTTPS reachable from my iPhone.** The iPhone needs a trusted HTTPS address for the web app. Use **Tailscale Serve** (already set up on both devices: a real certificate on a private `*.ts.net` name, reachable only by my devices), proxying to the API on 127.0.0.1:8700. Never use Tailscale **Funnel** (public) without asking me. If Serve needs MagicDNS or HTTPS certificates turned on in the tailnet's admin console, that's my sign-in: ask me and notify me. Document the setup, and make the API's cookie, host checks and the MCP server's allowed hosts work on that address.
2. **Home Screen web app (PWA).** Web app manifest, icons, a service worker, a mobile layout (the phone panel, chat and approvals usable one-handed on an iPhone screen), and a sign-in flow that works on the iPhone without me typing the long token by hand (for example, a short one-time pairing code shown on the Mac).
3. **Push approvals.** Web Push with VAPID: subscribe from the iPhone, store subscriptions, and send a notification when an approval is requested, when the agent needs a takeover, and when a task finishes or fails. Tapping opens the approval page. Approvals still come only from my session; a push never approves anything. Respect the approval modes (no push for an approval my request already gave).
4. **Live view and takeover on the iPhone.** The same live panel, with touch: tap, swipe, typing through the iPhone keyboard. Measure latency over the network you set up.
5. **Voice.** Push to talk on the web and iPhone: microphone → backend relay → Muse Voice Transcribe → the transcript goes to chat like typed text; short spoken replies with `speechSynthesis`. Tasks started by voice count as my own words for the approval modes (source `voice`). Measure turn latency and cost.
6. **Screenshots and photos → facts.** An upload endpoint and a photo picker in the web app, plus a free iOS Shortcut ("Send to Envoy" in the share sheet) that posts an image with a device token. Extraction from images with Muse Spark (vision), checked against the image's text, redacted, stored with a `photo` source; the image deleted once facts are saved. The boarding-pass screenshot must merge into the existing trip and flight (confirmation code, flight number and date), not create new ones.
7. **Sign-in codes (optional, an open question in the design doc).** Test whether an iOS Shortcuts automation can forward messages containing "code" to Envoy while the iPhone is locked. Record the answer either way; don't build more than the test.
8. **Stretch, only if time allows:** route 2 of "Path into Muse" with the real MCP server (Muse adds Envoy as a custom connector; "check me in" from the Muse app; the approval arrives as a push on the iPhone). This needs a public HTTPS address and my token entry: ask me.

Write the plan as `prompts/phase-5-plan.md` first (like `prompts/phase-4.md`), then build.

## Testing

- **Offline tests** for push subscriptions and sending (with a fake push service), the pairing flow, image upload and deletion after extraction, the voice relay (with a fake ASR socket), and that no new path can approve.
- **Scripted:** extend `eval/run_phase4.py` or add `eval/run_phase5.py`: an approval request produces a push to a test subscription; a boarding-pass screenshot taken from SkyLark (`emulator-5554`, after a check-in) uploaded through the API becomes facts on the right flight, with a `photo` source, and the image file is gone afterwards.
- **On my iPhone** (through iPhone Mirroring, with me for sign-ins and permission prompts): add to Home Screen, allow notifications, receive an approval push, open it, approve, see the check-in finish; take a SkyLark boarding-pass screenshot (or use one saved to Photos), share it to Envoy, see the fact in Memory. When you need me, ask right away and send a notification.

## Rules and constraints

- **The demo may only show work built during the hackathon (Oct 27 – Nov 4), clearly identified**, or the project can be disqualified. Keep `THIRD_PARTY.md` current (a Web Push library, for example). Open source is plumbing; the routines, memory, policy and companion behavior are ours.
- **Budget:** spend where it makes the work better; avoid needless repeats; `low` effort where it works. Contributor tier for SkyLark only.
- **Safety is unchanged:** approvals come only from my session (or the scripted person on SkyLark); MCP, chat, voice, Shortcuts and pushes can never approve; nothing types passwords; secure screens are never stored; images are deleted after extraction; the device token for the Shortcut can only upload images (it is not a session).
- Keep `envoy-real` long-lived (never restore a snapshot; stop it with `scripts/stop_emulator.sh`); at most two emulators at once.
- Live design doc: edit through the Claude Docs connector with find-and-replace, check `sinceRev` first, never overwrite someone else's edit.
- Commit after each meaningful step and push.

## Done means

- The gate passes on my real iPhone: an approval arrives as a push, I approve from the iPhone, and the task completes; a boarding-pass screenshot sent from the iPhone becomes facts on the right flight, with its source.
- Voice works on the web app and the iPhone, with measured latency and cost.
- Tests and the scripted checks pass; `docs/phase-5-results.md`, both copies of the design doc (a "Phase 5 results" section and any design changes), `THIRD_PARTY.md`, `README.md` and `docs/meta-feedback.md` (Voice Transcribe, vision extraction) are updated; everything is committed and pushed.
- Finish with a short summary:
  1. what was built
  2. the key numbers (push delivery time, live-view latency over the network, voice turn latency and cost, screenshot extraction accuracy)
  3. anything that changes the design
  4. what I need to do next (including anything to set up for Phase 6, the real Android phone)
