# web

Envoy's web app (Phase 4): Next.js, built as a static export that the API serves (`backend/api/app.py` serves `web/out`), so the app, its API and the live view share one origin and the session cookie.

```bash
npm install && npm run build      # then restart the API; telemetry is off in the scripts
```

Tabs: Chat, Tasks (live steps with thumbnails, risk and approvals), Approvals, Memory (Cytoscape graph with facts, sources, history, edits), Routines, Triggers; the live phone (Take over / Hand back) sits beside them. `/approve?id=…` is the standalone approval page that approval links open.
