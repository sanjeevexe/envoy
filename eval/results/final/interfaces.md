# Interfaces, end to end

Run 1028010615 on `849e51a` with uncommitted changes, 2026-10-28 05:06 UTC, 2 min, standard tier. 6 model calls, $0.035 at standard prices ($0.035 billed).

| Check | Result | Time | What it covers |
| --- | --- | --- | --- |
| phase4 | passed | 122 s | sign-in hand-off and takeover, approval with a screenshot by the person, check-in done, memory updated, MCP (no approve tool), chat from memory, live view |
| approval_modes | passed | 53 s | your own request isn't asked again; the same request from MCP asks; a standing approval; always ask |
| phase5 | passed | 50 s | approval and Done pushes (decrypted by a fake push service, no nonce), a screenshot into memory, voice through Muse Voice Transcribe, live view over the tailnet |

The Muse route (the Muse app on the iPhone through a public tunnel to `/mcp`) needs you to start the tunnel; it isn't scripted here.
