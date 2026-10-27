# Phase 5 results: iPhone companion and voice

Oct 27, 2026. **Gate passed on your iPhone.** The gate was "approve from the iPhone; a boarding-pass screenshot becomes a fact".

On your iPhone, Envoy runs as a Home Screen app over a private HTTPS address on your tailnet. You asked it to check you in from the iPhone's chat. The approval arrived as a push. You opened it and approved on the iPhone 170 s later, and the check-in finished with memory updated; a "Done" push followed. A SkyLark boarding-pass screenshot in the iPhone's Photos, shared with **Send to Envoy** from the Share Sheet, became facts on the existing SL 482 flight, with the source "your screenshot (shared with Send to Envoy)". The image was deleted from the Mac 4 s after it arrived. A scripted version of both halves passes 8/8 (`eval/run_phase5.py`).

Plan: `prompts/phase-5-plan.md`. Results: `eval/results/phase5/` (`gate.json` scripted, `iphone_gate.json` your run, `photos.json` screenshot accuracy).

## What was built

About 1,350 lines of Python, Swift and shell (`backend/api/auth.py`, `push.py`, `voice.py`, `backend/memory/photos.py`, `ocr.swift`, `scripts/`) and 1,000 of TypeScript and JavaScript (`web/`), all Envoy’s own. pywebpush, Tailscale, Apple's Vision framework and Shortcuts are plumbing (`THIRD_PARTY.md`).

| Part | Where | What it does |
| --- | --- | --- |
| HTTPS on your tailnet | `scripts/serve_tailnet.sh` | Tailscale Serve, HTTPS on **:8443** → the API, tailnet only (Serve's :443 already serves your "Fuel" app, left alone). The API learns its address from Tailscale and uses it in pushes and MCP approval links. It answers only to its own names (127.0.0.1, localhost, the `ts.net` name), and WebSockets check their Origin (DNS rebinding). Cookies are `Secure` over HTTPS. |
| Pairing | `api/auth.py`, `web/components/Pair.tsx`, `Companion.tsx` | The Devices tab on the Mac shows a QR code of the address and a 6-digit code (single use, 5 minutes, dead after 5 wrong tries). The iPhone's Home Screen app keeps its own cookies apart from Safari, so the code is typed inside the installed app (it pairs on the 6th digit). Each device gets its own session token, stored hashed, named, revocable. Approvals record which device decided ("user on iPhone (Home Screen app)"). |
| Device tokens | `api/auth.py` | Narrow tokens for Shortcuts: `photos` can only upload images; `code_test` can only report that a code message arrived. Neither can read, approve, take over or start tasks. |
| Home Screen app | `web/public/manifest.webmanifest`, `sw.js`, `scripts/make_icons.py`, `web/app/page.tsx` | Manifest, icons, a service worker (pushes, receipts, notification taps, the app's pages for when the Mac can't be reached), and a phone layout: bottom tabs (Chat, Phone, Approvals, Memory, More), the live phone as its own tab (streamed only while open), banners when an approval or a takeover waits, a one-handed approval page. |
| Push | `api/push.py`, `web/lib/device.ts` | Web Push with VAPID (key pair made on first start). Pushes go out when an approval is **asked**, when Envoy needs a takeover, and when a task is done, failed or declined; trigger-started tasks push only on failure. An approval your own request already gave isn't asked, so it doesn't push. A push carries a title, a line and a page; never a nonce, so it can't decide anything. Dead subscriptions are dropped. The service worker posts a receipt, which measures delivery. |
| Live view on the iPhone | `web/components/LivePhone.tsx`, `api/live.py` | Touch: tap, swipe, long press; the page doesn't scroll while you're in control. Typing through the iPhone keyboard (a hidden field forwards each character, Backspace and Return through the native `beforeinput` event). Latency is measured against the Mac's clock (ping/pong) and reported back; inputs are acknowledged. 720 px at quality 60 on the phone. |
| Voice | `api/voice.py`, `web/lib/voice.ts`, `web/public/voice-worklet.js`, `web/components/Chat.tsx` | Hold the mic (or tap once to latch). The browser resamples the microphone to 24 kHz 16-bit PCM in an AudioWorklet and streams it to `WS /api/voice`, which relays it to Muse Voice Transcribe in push-to-talk mode; the API key stays on the Mac. Partial text shows while you talk; the final transcript goes to chat as source `voice` (your own words for the approval rules). Replies are spoken with `speechSynthesis`; a task started by voice says how it ended. The relay pads silence to keep the stream at real time when the microphone stalls (below). Fallback: the browser's own speech recognition. |
| Photos and screenshots → facts | `memory/photos.py`, `memory/ocr.swift`, `POST /api/photos` | From the app's photo picker (your session) or the **Send to Envoy** Shortcut (a `photos` token). Text is read **on this Mac** with Apple's Vision framework (a full pass plus four overlapping tiles). Lines with card numbers, codes or ID numbers are blacked out in the copy sent to Muse Spark and redacted in the text kept. Spark reads the image; every value must appear in the image's text (O/0 and I/l/1 count as one glyph in codes) or it is dropped. Facts are stored with a `photo` source, merge by natural keys, and **the image is deleted** whether or not anything was saved. Off until you turn it on; screenshots only by default (camera photos carry a camera make and model). |
| Send to Envoy | `scripts/make_shortcut.py` | Writes and signs the Shortcut (`shortcuts sign`) with its own `photos` token; iCloud carries it to the iPhone. It posts the shared image and shows Envoy's one-line answer as a notification. |
| Muse route 2 | `scripts/start_muse_test.sh`, `api/app.py` | A Cloudflare quick tunnel to the running API; while it is up, the API accepts the tunnel's host for `/mcp` and nothing else (the web app, API and approval pages stay on the Mac and the tailnet). |

## Results

| Check | Result |
| --- | --- |
| Gate, on your iPhone | Passed. Approval push delivered 905 ms after sending, approved on the iPhone, check-in done, memory 14 confirmed and 1 replaced; "Done" push 687 ms. The boarding-pass screenshot, shared with Send to Envoy, merged into SL 482 (7 flights and 7 trips before and after) with a photo source; image deleted. |
| Gate, scripted (`eval/run_phase5.py`) | 8/8 in 45 s: takeover, approval and "Done" pushes to a fake push service that checks the VAPID signature and decrypts each push; the approval push opens `/approve/?id=…` and carries no nonce; the approval stays pending until the session approves; the emulator's boarding pass uploaded with a Shortcut token became facts on SL 482 with the image gone and the token unable to read anything; voice through the real Transcribe API; live view through the tailnet HTTPS address. |
| Push delivery (Apple's push service → the iPhone's service worker) | 687 to 972 ms from sending to the receipt (3 pushes); Apple accepted each in 135 to 359 ms |
| Live view on the iPhone, over the tailnet | Frame latency (capture → screen) p50 66 to 115 ms, round trip 27 to 47 ms, 76 to 108 KB per 720 px frame; input acknowledged in 10 to 241 ms. From this Mac through the same HTTPS address: 20 ms. Target was under 150 ms. |
| Takeover from the iPhone | Tap, typing with the iPhone keyboard (Backspace included), search, hand back: all worked on SkyLark |
| Voice, scripted (real Transcribe) | "What's my gate for my Chicago flight?" heard exactly. Final text 90 to 93 ms after release (connecting takes 0.25 to 1.45 s but overlaps the speech, which is buffered). Chat answered from memory in 3.4 s ("Gate B12, from your screenshot and the SkyLark app just now"): release → reply 3.5 s. Cost $0.0001 for a 2.6 s turn ($0.18 per audio hour). |
| Voice on your devices | **Pending your try** (iPhone Mirroring blocks the iPhone's microphone). The app records press → mic, release → text and release → speech itself in `logs/client_metrics.jsonl`. |
| Screenshot extraction (`eval/run_photos.py`) | **73 of 73 values right, none wrong**, on 7 SkyLark booking screens (home card, trip details, boarding passes for 3 trips); every screen merged into the trip and flight memory already knew (0 new). A flight-status lookup for another flight stored nothing: a search result isn't evidence of your booking. OCR 0.46 s, Spark 4.8 s (medians), about $0.007 per screenshot. All images deleted. |
| Sign-in codes (open question) | **Yes, while locked.** An iOS automation ("message contains 'code'", Run Immediately) forwarded a test iMessage to Envoy about 2 s after it was sent, with the iPhone locked. One catch: a Shortcut's first network call asks for permission, which a locked phone can't show, so it must run once by hand first. Envoy recorded only that a code message arrived. The automation is now set to Don't Run and its token is revoked. |
| Pairing and tokens | Wrong codes refused, the code works once, the paired iPhone is a session, a revoked device is signed out at once |
| Offline tests | 93 pass (14 new: pairing, scoped tokens, host and origin checks, push through a fake push service, no push when your request already approved, push kinds and dead subscriptions, photo upload with real OCR and deletion and redaction, the voice relay against a fake Transcribe socket, silence padding, spoken requests as your own words, no new path approves, the tunnel reaches `/mcp` only, OCR glyph confusions) |
| Cost | 70 model calls, $0.41 at standard prices ($0.37 billed); mostly photo extraction during the accuracy runs. All-time billed: $7.32. |

## What the iPhone runs found, and what changed

1. **A microphone that sends nothing ends the Transcribe stream.** iPhone Mirroring blocks the iPhone's microphone, and Muse Voice Transcribe closed the session with "Ingress audio slower than real-time". Meta's docs say to keep sending silence on a live source, so the relay now pads the stream with silence whenever the browser's audio falls 300 ms behind (a stalled microphone, a slow network), and the app says when no sound reached it. Regression test added.
2. **Vision skipped a lone code.** On one trip screen, Apple's text recognition missed the confirmation code on the right of its row, so the value Spark read correctly couldn't be checked and was dropped (missing, never wrong). A second pass over four overlapping tiles recovers it (0.25 → 0.46 s). Where Vision did read it, it read 3J8N**O**D for 3J8N**0**D, so the check now treats O/0 and I/l/1 as one glyph in codes that mix letters and digits. 72/73 became 73/73.
3. **Which device approved.** Approvals now record the device ("user on iPhone (Home Screen app)") for the audit log.
4. **iPhone Mirroring limits** (testing only): the iPhone's microphone is unavailable, iPhone notifications show on the Mac, swipe gestures don't come through (an automation can't be deleted, only set to Don't Run), and fast typing into fields with autocorrect garbles.

## Honest limits

- **Voice on your devices isn't measured yet**: the relay and the real Transcribe API are, with a recorded phrase.
- **The tailnet is the network.** The iPhone was on the same campus network (Tailscale connected directly); over cellular, frame latency will be higher. Fewer, smaller frames are one setting away (`fps`, `width`, `quality`).
- **Web Push on iOS needs the Home Screen app**, and notifications have no action buttons: tapping opens the approval page.
- **The code test used a message you sent yourself** (iMessage to your own Apple ID). A real one-time code from a service should behave the same, but that wasn't tried.
- **Photos are read by Muse Spark on Meta's servers** (with redacted regions blacked out first); only the text check is on-device.
- **Cookies are per host, not per port**, so your browser also sends Envoy's cookie to the other app on the same `ts.net` name (port 443). Both run on your Mac; noted for when either moves.

## Changes to the design

For the design doc (applied in both copies):

1. **HTTPS is Tailscale Serve on :8443**, tailnet only; the API checks Host and WebSocket Origin; a public tunnel (Muse) reaches `/mcp` only.
2. **Signing in on the iPhone is a 6-digit pairing code typed inside the Home Screen app**, because Home Screen apps keep their own cookies. Shortcuts get device tokens that can only upload images.
3. **Approvals: push never carries a nonce**, opens the approval page, and is sent only when Envoy actually asks.
4. **Voice: one Transcribe session per press** in push-to-talk mode, with silence padding to real time; final text about 90 ms after release.
5. **Photos: text is read on the Mac (Vision, with a tiled second pass)**; redacted lines are blacked out before the image goes to Spark; values must match the image's text up to OCR glyph confusions in codes; the image is deleted.
6. **Sign-in codes (answered):** a Shortcuts message automation does forward codes while the phone is locked, after one manual run grants its network permission.

## Next

- **You:** try voice once on the iPhone (in hand) and once on the Mac: hold the mic in Envoy and ask "What's my gate?". If you want the code-test automation gone, swipe left on it in Shortcuts → Automation (it's set to Don't Run). For the Muse run, start `scripts/start_muse_test.sh` and add its URL and token in Muse.
- **Phase 6 (real Android phone):** turn on Developer options and Wireless debugging on the phone; for USB, a cable to the Mac; for wireless, the Mac and phone on the same Wi-Fi (campus Wi-Fi often isolates devices, so a hotspot from the phone may be needed). Tell me its Android version (15+ hides codes from notification readers).
