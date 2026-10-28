# Interfaces, end to end

Run 1028035004 on `e18e434` with uncommitted changes, 2026-10-28 07:50 UTC, 5 min, standard tier. 23 model calls, $0.145 at standard prices ($0.110 billed).

| Check | Result | Time | What it covers |
| --- | --- | --- | --- |
| phase4 | passed | 117 s | sign-in hand-off and takeover, approval with a screenshot by the person, check-in done, memory updated, MCP (no approve tool), chat from memory, live view |
| approval_modes | passed | 50 s | your own request isn't asked again; the same request from MCP asks; a standing approval; always ask |
| phase5 | passed | 39 s | approval and Done pushes (decrypted by a fake push service, no nonce), a screenshot into memory, voice through Muse Voice Transcribe, live view over the tailnet |

The Muse route (the Muse app on the iPhone through a public tunnel to `/mcp`) needs you to start the tunnel; it isn't scripted here.
