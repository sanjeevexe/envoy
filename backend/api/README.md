# api

Envoy's API, event stream, live view, approvals, chat, scheduler and the MCP server, in one process (Phase 4):

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

Main routes: `POST /api/tasks`, `GET /api/tasks/{id}`, `POST /api/tasks/{id}/stop`, `GET|POST /api/approvals/{id}`, `POST /api/devices/{avd}/takeover|handback`, `POST /api/chat`, `GET /api/memory/graph`, `GET /api/memory/entity/{id}`, `POST /api/memory/entity/{id}/fact`, `DELETE /api/memory/source/{id}`, `GET /api/routines`, `GET|POST /api/triggers`. Browser POSTs carry `X-Envoy: 1`.
