# Phase 5: iPhone companion and voice (plan)

Written by Claude from `prompts/phase-5.md` and the design doc on Oct 27, 2026. The build-phases diagram defines this phase as: the web app on the iPhone's Home Screen (approvals, live view, photos), and voice. **Gate:** approve from the iPhone; a boarding-pass screenshot becomes a fact.

## Rules (unchanged)

- Never type passwords or sign in to accounts (Tailscale, Apple, Google sign-ins are yours). Never use payment methods.
- Ask before anything visible outside this Mac: no Tailscale **Funnel**, no public tunnel, no repo visibility change, no posting.
- Contributor tier only for SkyLark test data; photos and voice are your data and always use the standard tier.
- `envoy-real` is never snapshot-restored and is stopped with `scripts/stop_emulator.sh`; at most two emulators.
- The demo shows only work built during the hackathon; `THIRD_PARTY.md` lists every new library.
- Live design doc: find-and-replace through the Claude Docs connector, `sinceRev` checked first.
- Commit and push after each meaningful step. When something needs you, ask right away and send a notification.

## What I found before planning

- Tailscale is signed in on both devices, MagicDNS and HTTPS certificates are already on (`<mac>.<tailnet>.ts.net`).
- **Serve's port 443 is already in use** by another app of yours (`/` → `127.0.0.1:8787`, "Fuel"). Envoy will not replace it: it goes on Serve's other HTTPS port, **8443** (`https://<mac>.<tailnet>.ts.net:8443`), tailnet only.
- Muse Voice Transcribe (dev.meta.ai, read today): `wss://api.meta.ai/v1/asr/realtime`; the first text frame is the handshake (`authorization.accessToken = "Bearer <key>"`, `audioEncoding` `PCM_24KHZ`|`PCM_16KHZ`, `model`, `mode` `PUSH_TO_TALK`|`ENDPOINTING`|`DIARIZATION`, `partialMode`, `emitAudioProgress`, `keywords`, `languageBias`), acknowledged by `{"sessionId"}`; audio is binary 16-bit little-endian mono PCM at about real time (80 ms chunks); in push-to-talk a turn ends with `{"type": "endStream"}` (it ends the session), then a `transcript` with `final: true` and a `1000` close. Partials are cumulative. Billed per processed second at $0.18/hour.
- Images go to Spark as `input_image` data URLs (JPEG/PNG; a ~1280 px image is about 1,300 to 1,500 tokens).
- An iPhone Home Screen app keeps its own cookies and storage, separate from Safari. So signing in must happen **inside the installed app**, which is why a short code beats a link.

## What gets built

All in the one API process (`python -m api`), served to the iPhone through Tailscale Serve.

| Part | What it does |
| --- | --- |
| HTTPS on the tailnet | `scripts/serve_tailnet.sh on|off|status`: Tailscale Serve, HTTPS on :8443 → `127.0.0.1:8700`, tailnet only. The API learns its public address from Tailscale (or `ENVOY_PUBLIC_URL`): approval links in pushes and MCP use it; a host allow-list (127.0.0.1, localhost, the `ts.net` name) blocks DNS rebinding; WebSockets check their Origin; the session cookie is `Secure` over HTTPS; the MCP server accepts the `ts.net` host. |
| Pairing | Settings › Devices on the Mac shows a 6-digit code (one use, 5 minutes, 5 tries). The iPhone app's sign-in screen takes the code and gets **its own device session** (stored hashed, named, revocable, last seen). A device session can do what you can on the Mac. |
| Home Screen app | Web app manifest, icons (drawn for Envoy), `apple-touch-icon`, standalone display, safe areas, a service worker (push and notification taps; the app shell cached so it opens offline with a "can't reach your Mac" note). A phone layout: bottom tabs (Chat, Phone, Approvals, Memory, More), thumb-sized buttons, the approval page one-handed. |
| Push | Web Push with VAPID keys made on first start (`data/api/vapid.json`). The app subscribes after you tap "Turn on notifications"; subscriptions are stored per device. Pushes go out when an approval is **asked** (an approval your request already gave doesn't ask, so it doesn't push), when Envoy needs you to take over, and when a task is done, failed or declined. Tapping opens the approval page (or the task). A push carries no nonce and decides nothing; the page still needs your session and a POST. Dead subscriptions (404/410) are dropped. The service worker sends a receipt, which measures delivery time. |
| Live view on the iPhone | The same stream, sized for the phone. Touch: tap, swipe and long press; the page doesn't scroll while you're in control. Typing through the iPhone keyboard (a hidden field forwards each character, Backspace and Return). Latency measured with a clock-offset ping, and reported back by the app. |
| Voice | A push-to-talk button in chat (web and iPhone). The browser captures the microphone, resamples to 24 kHz 16-bit PCM in an AudioWorklet, and streams it to `WS /api/voice`, which relays it to Muse Voice Transcribe with the key (the key never leaves the Mac). Partial text shows while you talk; the final transcript goes to chat as your own words with source `voice` (so "check me in" said aloud is your OK, like typed). Short replies are spoken with `speechSynthesis`. Fallback: the browser's own speech recognition. Turn latency and audio cost are logged per turn. |
| Photos and screenshots → facts | `POST /api/photos` takes images from your session (a photo picker in the app) or from the **Send to Envoy** Shortcut with an **upload-only device token** (it can't read anything, approve or start tasks). On the Mac: text is read **on-device** with Apple's Vision OCR; lines that redaction flags (card numbers, codes, ID numbers) are blacked out in the image before it leaves the Mac; Muse Spark reads the image and returns facts; every value must appear in the OCR text or it is dropped; facts are stored with a `photo` source (the redacted OCR text as its snapshot); **the image file is deleted** whether or not extraction succeeds. A boarding pass resolves to the existing trip and flight through their natural keys (confirmation code; flight number and date). Photos are off until you turn them on in Settings (scope: screenshots only by default). |
| Sign-in codes (test only) | Whether an iOS message automation forwards a "code" message while the iPhone is locked. A test endpoint records only that a message arrived and when (digits redacted, nothing kept). The answer goes in the design doc either way. |
| Stretch: Muse route 2 | Only with your OK (it needs a public HTTPS address and your token entry): "check me in" from the Muse app, with the approval arriving as a push on the iPhone. |

## Gate test

1. On the iPhone: add Envoy to the Home Screen, pair with the code shown on the Mac, allow notifications.
2. "Check me in for my flight" (from the Mac, chat or voice) with "always ask" set for the gate run. SkyLark is signed in through the live view if needed.
3. The approval arrives on the iPhone as a push; you tap it, see the screenshot, approve; the check-in finishes.
4. A SkyLark boarding-pass screenshot (from the emulator, saved to the iPhone's Photos, or taken on the iPhone from the live view) is shared to **Send to Envoy** (or picked in the app); the facts land on the right Trip and Flight in Memory, with a photo source; the image is gone from the Mac.

Scripted (`eval/run_phase5.py`): an approval request produces a push to a test subscription (a local fake push service that decrypts it); a boarding-pass screenshot taken from SkyLark after a check-in, uploaded through the API with the device token, becomes facts on the right flight with a `photo` source, and the image file is gone afterwards; the device token can't read or approve; voice relays a recorded phrase through the real Transcribe API and starts a chat turn.

## Done means

- The gate passes on your iPhone. Voice works on the Mac and the iPhone, with measured latency and cost.
- Offline tests for push (with a fake push service), pairing, photo upload and deletion, the voice relay (with a fake ASR socket), and that no new path can approve.
- `docs/phase-5-results.md`, both copies of the design doc, `THIRD_PARTY.md`, `README.md` and `docs/meta-feedback.md` updated; committed and pushed.
