# api

Envoy's API, event stream, live view, approvals, chat, scheduler and the MCP server, in one process (Phase 4), plus the iPhone companion's pairing, push, voice and photos (Phase 5), and your real Android phone (Phase 6):

```bash
uv run --project backend python -m api [--profile demo|real]   # http://127.0.0.1:8700
```

`demo` uses SkyLark's test memory (`data/demo/memory.db`, from `scripts/demo_setup.py`); `real` uses your memory (`data/memory.db`).

| File | What |
| --- | --- |
| `app.py` | Routes, auth (your session from the printed sign-in link; AI clients only through `/mcp` with their own token), serving `web/out` |
| `store.py` | Tasks, steps, approvals and triggers in SQLite (`data/api/envoy.db`; `ENVOY_API_DIR` moves it) |
| `runner.py` | Runs a task: routine (matcher + memory) or agent, the phone (asking first before your own), phone lease, sign-in hand-off, web approvals, memory write-back after Done |
| `devices.py` | Phone leases and takeover: the agent's next call to the phone waits while you are in control. Lists the emulators and any connected Android phone; while a task uses your phone, `watch()` hands it to you on a touch, Pause on its banner, or another app coming to the front |
| `routing.py` | Which phone runs a task (the design's table): an emulator by default, your phone when you ask ("… on my phone"), when the app is set to it (Settings › Phones) or blocks emulators: the starting list `emulator_blocked.json`, or an app Envoy saw show a bot check on an emulator (the runner sets it to your phone) |
| `install.py` | An app the task names that the emulator doesn't have: its Play Store page read in code, free apps installed, a paid one asked about through approvals (Envoy never pays), sign-ins handed to you |
| `approvals.py` | Web approvals: only your session decides, by POST with the approval's nonce; bound to the app's own screen; no answer is never an approval |
| `live.py` | `WS /api/live/{id}`: emulator gRPC frames, or a real phone's scrcpy frames, as JPEG (emulators show secure sign-in screens; a phone shows them black, so the page says to use the phone); your taps, swipes and typing only during a takeover, never logged |
| `events.py` | `WS /api/events`: task, step, approval, takeover and memory events |
| `chat.py` | Envoy's assistant on Muse Spark: a memory answer, a task, or a reply |
| `scheduler.py` | Triggers: time, before a remembered event (moves when it changes), watchers, new email; typed values only |
| `auth.py` | Your session, paired devices (6-digit code typed in the iPhone's Home Screen app), scoped Shortcut tokens (`photos`, `code_test`), the tailnet address, host checks (a public tunnel reaches `/mcp` only) |
| `push.py` | Web Push (VAPID): approval asked, takeover needed, task done/failed/declined; never a nonce; receipts measure delivery (`logs/push.jsonl`) |
| `voice.py` | `WS /api/voice`: dictation relay to Muse Voice Transcribe (its push-to-talk mode, one session per dictation) (the key stays here), silence padding to real time, cost per turn |
| `routine_view.py` | A routine's detail for the web app, read only: steps (locators, checks, risk), versions as a timeline (each repair's changed locator or check before and after, Muse's reason, its screenshots, its trial), runs against the agent run it was compiled from (model calls, seconds, dollars at standard prices) |

Main routes: `POST /api/tasks`, `GET /api/tasks/{id}`, `POST /api/tasks/{id}/stop`, `GET|POST /api/approvals/{id}`, `POST /api/devices/{avd}/takeover|handback`, `POST /api/chat`, `GET /api/memory/graph`, `GET /api/memory/entity/{id}`, `POST /api/memory/entity/{id}/fact`, `DELETE /api/memory/source/{id}`, `GET /api/routines`, `GET /api/routines/{name}/detail` and the repair screenshots it lists, `GET|POST /api/triggers`; Phase 5: `POST /api/pair/start` (Mac only), `POST /api/pair`, `GET /api/paired`, `POST /api/tokens`, `POST /api/push/subscribe|unsubscribe|test|receipt`, `POST /api/photos` (session or `photos` token; image deleted after), `GET|POST /api/settings/photos`, `WS /api/voice`, `POST /api/metrics`, `POST /api/codes/test`; Phase 6: `POST /api/tasks` takes `phone` (`phone`, `emulator`, a device id), `POST /api/tasks/{id}/phone` (your answer to "use your Android phone?", session only), `GET|POST /api/settings/phones`. Browser POSTs carry `X-Envoy: 1`.
