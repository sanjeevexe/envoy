# web

Envoy's web app (Phase 4): Next.js, built as a static export that the API serves (`backend/api/app.py` serves `web/out`), so the app, its API and the live view share one origin and the session cookie.

```bash
npm install && npm run build      # then restart the API; telemetry is off in the scripts
```

Tabs: Chat, Tasks (live steps with thumbnails, risk and approvals), Approvals, Memory (Cytoscape graph with facts, sources, history, edits), Routines, Triggers; the live phone (Take over / Hand back) sits beside them. `/approve?id=…` is the standalone approval page that approval links open.

Phase 5 (the iPhone companion): the same app added to the iPhone's Home Screen (`public/manifest.webmanifest`, icons from `scripts/make_icons.py`, `public/sw.js` for pushes and notification taps). On a phone it switches to bottom tabs with the live phone as its own tab (touch, long press, the iPhone keyboard). Unpaired devices see the pairing screen (`components/Pair.tsx`); the Devices tab (`components/Companion.tsx`) pairs devices, turns on notifications, sets photo permissions and makes the Shortcut's token. Chat has hold-to-talk (`lib/voice.ts`, `public/voice-worklet.js`) and a photo picker (`lib/device.ts`).
