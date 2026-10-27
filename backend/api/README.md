# api

Envoy's API, event stream, live view, approvals, chat, scheduler and the MCP server, in one process (Phase 4), plus the iPhone companion's pairing, push, voice and photos (Phase 5):

```bash
uv run --project backend python -m api [--profile demo|real]   # http://127.0.0.1:8700
```

`demo` uses SkyLark's test memory (`data/demo/memory.db`, from `scripts/demo_setup.py`); `real` uses your memory (`data/memory.db`).

| File | What |
| --- | --- |
| `app.py` | Routes, auth (your session from the printed sign-in link; AI clients only through `/mcp` with their own token), serving `web/out` |
| `store.py` | Tasks, steps, approvals and triggers in SQLite (`data/api/envoy.db`; `ENVOY_API_DIR` moves it) |
| `runner.py` | Runs a task: routine (matcher + memory) or agent, phone lease, sign-in hand-off, web approvals, memory write-back after Done |
| `devices.py` | Phone leases and takeover: the agent's next call to the phone waits while you are in control |
| `approvals.py` | Web approvals: only your session decides, by POST with the approval's nonce; bound to the app's own screen; no answer is never an approval |
| `live.py` | `WS /api/live/{avd}`: emulator gRPC frames as JPEG (shows secure sign-in screens); your taps, swipes and typing only during a takeover, never logged |
| `events.py` | `WS /api/events`: task, step, approval, takeover and memory events |
| `chat.py` | Envoy's assistant on Muse Spark: a memory answer, a task, or a reply |
| `scheduler.py` | Triggers: time, before a remembered event (moves when it changes), watchers, new email; typed values only |
| `auth.py` | Your session, paired devices (6-digit code typed in the iPhone's Home Screen app), scoped Shortcut tokens (`photos`, `code_test`), the tailnet address, host checks (a public tunnel reaches `/mcp` only) |
| `push.py` | Web Push (VAPID): approval asked, takeover needed, task done/failed/declined; never a nonce; receipts measure delivery (`logs/push.jsonl`) |
| `voice.py` | `WS /api/voice`: push-to-talk relay to Muse Voice Transcribe (the key stays here), silence padding to real time, cost per turn |

Main routes: `POST /api/tasks`, `GET /api/tasks/{id}`, `POST /api/tasks/{id}/stop`, `GET|POST /api/approvals/{id}`, `POST /api/devices/{avd}/takeover|handback`, `POST /api/chat`, `GET /api/memory/graph`, `GET /api/memory/entity/{id}`, `POST /api/memory/entity/{id}/fact`, `DELETE /api/memory/source/{id}`, `GET /api/routines`, `GET|POST /api/triggers`; Phase 5: `POST /api/pair/start` (Mac only), `POST /api/pair`, `GET /api/paired`, `POST /api/tokens`, `POST /api/push/subscribe|unsubscribe|test|receipt`, `POST /api/photos` (session or `photos` token; image deleted after), `GET|POST /api/settings/photos`, `WS /api/voice`, `POST /api/metrics`, `POST /api/codes/test`. Browser POSTs carry `X-Envoy: 1`.
