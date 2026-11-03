# Interfaces, end to end

Run 1103032630 on `eval-final`, 2026-11-03 08:26 UTC, 8 min, standard tier, the `hybrid` profile (Muse Wonder for compile, plan, repair, step; Muse Spark for the rest). 28 model calls, $0.297 at standard prices ($0.280 billed).

| Check | Result | Time | What it covers |
| --- | --- | --- | --- |
| phase4 | passed | 102 s | sign-in hand-off and takeover, approval with a screenshot by the person, check-in done, memory updated, MCP (no approve tool), chat from memory, live view |
| approval_modes | passed | 139 s | your own request isn't asked again; the same request from MCP asks; a standing approval; always ask |
| phase5 | passed | 57 s | approval and Done pushes (decrypted by a fake push service, no nonce), a screenshot into memory, voice through Muse Voice Transcribe, live view over the tailnet |

The Muse route (the Muse app on the iPhone through a public tunnel to `/mcp`) needs you to start the tunnel; it isn't scripted here.

The demo profile's world date is pinned to Oct 29, 2026 for "my flight" and "my trip" (`WORLD_DATES` in `backend/api/app.py`): SkyLark has no clock and its bookings are fixed, with Chicago SL 482 (Oct 30, 6:10 AM) first, so on the real calendar "my flight" would have moved to the Denver trip from Oct 31 while the app still shows Chicago. Every other clock in these checks is real.
