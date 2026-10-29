# siri-voice report: "Ask Envoy" from Siri, the Action Button and Control Center

Branch `claude/lucid-poitras-a8c23b` (session siri-voice). Brief: `prompts/siri-voice.md` (untracked, main checkout).
Docs: `docs/siri.md`.

## Stage 1: the endpoint, the scope, the shortcut (Should)

### What was built

| Part | Where | What |
| --- | --- | --- |
| `POST /api/siri/token` | `backend/api/siri.py` | Session only. Issues a `siri` token named "Ask Envoy (Siri)" and returns `{token, scope, ask_url}`, shown once. `/api/tokens` is untouched. |
| `POST /api/siri` | `backend/api/siri.py` | A `siri` token or a session (the `/api/photos` pattern, CSRF included). Body `{"message"}`, whitespace collapsed, capped at 400 characters. Calls `chat(..., source="siri")`, publishes the `chat` event with `source="siri"`, answers `{say, kind, task_id?}`. |
| The `say` line | `say_for`, `heads_up`, `plain`, `fit` | Chat's `spoken` (or `reply`), plain (no markdown, links, ids, emoji; chat's "(from …)" age aside dropped, since the memory answer already says when), at most 2 sentences and 200 characters. A task adds one Before I start line: the task's own `preflight` step if it arrives within 3 s, else `preflight.check(..., source="siri")` without a routine. First stop line, else the first approval line that waits for / needs your OK, else the first warning; never repeated; a stop line replaces chat's second sentence. A drafted recurring job (offer present): "I've drafted it. Say yes in Envoy to turn it on." |
| Limits | closure in `siri_router` | 6 a minute and 100 a day per token (keyed by `device_id`, or `owner` for your session), clock replaceable (`api.siri.now`). 429 with a `say`. |
| Errors | `ask` | 400/401/403/429 answer `{"say", "kind": "error"}` (never `{"detail"}`); anything raised in chat answers 200 with "I couldn't do that just now. Try again in a minute." and logs only the exception's type. |
| Scope | `backend/api/auth.py` | `siri` in `SCOPES`; module and `Caller` docstrings. `app.py`: the import, one `include_router` line, the docstring line. No change to `backend/policy/`, `chat.py` or `push.py`; `siri` is not in `DIRECT_SOURCES`. |
| Shortcut builder | `scripts/make_shortcut.py` | `--siri`, `--base`, `--api-dir`, `--mac-test`, `--reply`. `siri_workflow(ask_url, token, reply)` is pure: If Shortcut Input has any value → Request = input, Otherwise → Dictate Text → Request; Get Contents of URL (POST JSON `{"message": Request}`, `Authorization: Bearer …` header only); Get `say`; then Speak Text + Show Notification (default), Show Result, Speak + Show Result, or Stop and Output. "Ask Envoy" for the live API; "Ask Envoy (test)" for any other base or API dir. Without `--mac-test` only https is accepted; with it, only `http://127.0.0.1` / `localhost`. Written mode 700/600; the unsigned file is removed even if signing fails. |
| Web | `Tasks.tsx`, `Companion.tsx`, `lib/mock.ts` | `siri` reads "from Siri" / "Started by Siri" (only that expression in preflight-logins' `Tasks.tsx`); the Devices row reads "Siri shortcut: can ask Envoy and start tasks; can't approve anything"; mock fixtures for both. |

### Evidence

- **Tests:** `backend/tests/test_siri.py`, 26 tests. Full suite: 519 passed. `npm run build` passes.
  - the `siri` token gets 401/403 from every other `/api/*` route (walked from the app's routes, 60+), the three WebSockets and `/mcp`; a revoked token is refused with a `say`; your session can ask; a browser POST without X-Envoy is refused with a `say`
  - the source: a Siri task has source `siri` and your words as its request; `decide()` returns None for `siri` at the named step and auto-approves the same for `chat`; money asks for both; a standing approval applies to both; the real `WebApprover` waits (times out unapproved) for `siri` and records "your request" for `chat`; preflight says "will wait for your OK" for `siri`, "will go ahead" for `chat`
  - `say` fixtures: fresh memory answer, old answer without a phone (age said once), stale answer that became a task (no wait), the task's own step in time, the fallback when it's late (called with `source="siri"`), payment, blocked app, stop line, nothing worth saying, stop line replacing chat's second sentence, drafted and rejected recurring jobs, plain and capped
  - recurring through Siri (real chat, recorded adapter): trigger off, ask mode, offer source `siri`, the `siri` token can't accept it, your session can
  - limits (6/min, 100/day, per token, with the replaceable clock), the 400-character cap, bad bodies; a model failure answers a `say` and logs no words
  - the shortcut's actions in order, the token in the header only
- **UI (mock mode, 390 and 1440):** the Devices row and the task row/view. Screenshots in the session scratchpad (`screens/devices-390.jpg`, `devices-1440.jpg`, `task-390.jpg`, `task-1440.jpg`).
- **Mac check (my copy on :8746, demo profile, copied memory, an adb stand-in that sees no devices, so nothing could reach an emulator):**
  - Imported "Ask Envoy (test)" (`--reply output`): every action shows, none unknown ("Receive Text and Files from Share Sheet; if there's no input: Continue", If / Set variable / Otherwise / Dictate Text / Set variable / End If, Get contents of, Get Value for `say`, Stop and output). The default build (Speak, Show notification) also previews clean.
  - Status codes: Shortcuts hands back the body of a 400 ("I didn't catch that."), a 401 (revoked token) and a 429 (7th in a minute), so they stay.
  - `shortcuts run "Ask Envoy (test)" --input-path …`:

    | Input | Said | Seconds (whole shortcut) | Model calls |
    | --- | --- | --- | --- |
    | What gate is my flight? | "Gate B12, from the SkyLark app yesterday at 5:50 PM, but it may have changed. (from yesterday 5:50 PM; no phone is free to check it now)" → the aside is now dropped | 6.1 | 2 |
    | Check me in for my flight | "On it: Check me in for my flight. Anything that can't be undone will wait for your OK." (the task's own step came at 3.42 s, just past the 3 s wait: fallback line) | 5.0 | 2 |
    | purple monkey dishwasher | "Sorry, I didn't understand that — could you rephrase what you'd like me to do?" | 1.3 | 1 |
- **Device check (envoy-test, SkyLark, Oct 29 15:36–15:40; claimed through `devices.sh`; my copy on :8746 at `9894daa`, demo profile, copied memory; `POST /api/siri` with the copy's `siri` token):**

  | Request | `say` (HTTP time) | The task | Calls, cost |
  | --- | --- | --- | --- |
  | What gate is my flight? | "That may have changed. I'm checking the app." (4.98 s) | source `siri`; routine `skylark_get_flight_gate` (preflight step at +2.64 s, the match call 2.58 s); done in 7.1 s; result "gate: B12" | chat 2.5 s + answer 2.0 s, then match + memory extract: 4 calls, $0.0195 |
  | Check me in for my flight | "On it: Check me in for my flight. Anything that can't be undone will wait for your OK." (4.89 s) | source `siri`; its preflight step (at +4.94 s): "Confirming check-in will wait for your OK."; the routine ran 5 steps and **asked at Confirm check-in** (8.8 s; reasons: the rule "target says 'Confirm check-in'", the step's irreversible label), although the request names it. **Declined** in my copy (owner session, the endpoint the web app's Decline button calls): `confirm_check_in` declined, task `declined`. SkyLark not checked in | chat 1.8 s + match 4.9 s: 2 calls, $0.0088 |

  envoy-test was stopped when I claimed it; I started it (booted in 13 s), and stopped and released it afterwards. Screenshot of the approval's screen: `screens/device-confirm-checkin.jpg` (scratchpad). I declined through the API rather than the web app so my copy's session token never went into a browser URL; the decision path is the same (`POST /api/approvals/{id}`, decided by "user").
- **How long the task's own preflight step takes** (the 3 s wait): it comes right after the routine match (one Spark call). Recorded history: match p50 1.7 s, p90 2.9 s (655 calls). Today on the new account: 3.35 s, 2.58 s, 4.88 s. So both check-in requests today missed the 3 s wait and Siri said the general line ("Anything that can't be undone will wait for your OK.") instead of the named one; the gate request didn't wait at all (two sentences already). I kept 3 s, as the brief asks (a quick reply matters more). If the demo should say "Confirming check-in will wait for your OK.", `PREFLIGHT_WAIT_S = 5` in `api/siri.py` does it, at up to 2 s more in slow cases only.

### Spend

| Run | Calls | Cost |
| --- | --- | --- |
| Mac check (3 requests, 6 for the 429 check) | 11 Spark | $0.024 |
| Device check (2 requests, 2 tasks) | 6 Spark | $0.028 |
| **Stage 1 total** | 17 | **$0.052** |

## Stage 2: the real iPhone

_Pending._

## Not done / not checked / notes for the coordinator

- The offer card in the app doesn't say a recurring job came from Siri (`offers.source` is `siri`; the card is proactive's file).
- `Tasks.tsx` (preflight-logins' file): only the `source` expression changed.
