# Before I start, and saved logins

Two features from the final wave (Oct 29 – Nov 1, 2026). **Before I start** tells you what to expect before Envoy starts a task. **Saved logins** would let the phone's own password manager fill a sign-in, so Envoy never sees, reads or types a password. The second is an experiment first, and it is built only if that experiment comes out clean.

## Before I start

Before a task runs, Envoy says in a few plain lines what it already expects:

> Target blocks emulators: I'll ask to use your Pixel 5.
> DoorDash asked you to sign in on your Pixel 5 last time (Oct 27).
> The payment step will need your OK.
> Using routine skylark_check_in_flight v1: usually 9 s, no model calls.

The same lines show in three places:
- **The task view:** a "Before I start" card at the top, with Envoy's avatar in its thinking mood. Warnings are apricot and a stop is brick.
- **An offer's card,** before its Yes (the proactive session adds this).
- **MCP's `heads_up`** on `run_task` and `run_routine`, so Muse can warn you too (the muse-link session adds this).

### The contract

`api/preflight.py`: `check(runner, goal, *, request=None, source=None, app=None, routine=None, inputs=None, phone=None, phone_ok=None)`. It returns at most five `{kind, text, level}` lines, the most important first: `stop`, then `warn`, then `info`.

- **No model call, no device action, never raises.** A part that fails costs only its own line. It took 0.1–13 ms on a copy of the live task history, and under 6 ms on a test history of 5,000 tasks (the budget is 50 ms).
- `routine` is a routine's name, or the routine itself (the runner passes the version it decided to run).
- `phone_ok` is optional. It names the phone your yes already covers (an accepted handoff offer, `runner.start(..., phone_ok=)`), so the device line doesn't promise an ask that won't happen. It is an addition to the plan's contract 2, and callers that don't pass it get the plain lines.
- Callers outside the runner import it guarded (`try: from api.preflight import check except ImportError: check = None`) and carry on without the lines if it raises.

### The lines, and where each comes from

| Kind | Level | Said when | From |
| --- | --- | --- | --- |
| `blocked` | stop | Routing finds no phone that can run it: the app blocks emulators and your phone isn't connected (or hasn't allowed USB debugging), or you asked for your phone and it isn't there | `routing.choose()` with the phones as last seen |
| `device` | warn | It will run on your phone and Envoy will ask first: the app blocks emulators, you asked for your phone, the app is set to your phone, or you picked it | the same |
| `device` | info | Your yes already covers the phone (`phone_ok`), or the app is set to your phone but it isn't connected, so the emulator runs it | the same |
| `signin` | warn | The **last** task of this app on the phone it will use was handed to you for the app's own sign-in (not the Play Store's). A later run without one means you're signed in, so nothing is said | `handoff` steps whose text starts `sign-in needed` |
| `install` | info | On an emulator only: the last run there found the app missing and didn't install it, or the request names an app Envoy has never used ("in the Wikipedia app"). Otherwise nothing: apps Envoy knows by name are set up on its emulators | install notes in the task history, `apps_installed` |
| `approval` | info | What `policy/approval_rules.decide()` will do: money always asks; then the mode (always, a standing approval); then whether the source is direct and the request names the step. For an agent task (steps unknown), only a payment, or "Anything that can't be undone will wait for your OK" when Muse or a trigger asked for something irreversible | the routine's irreversible steps, the approval rules setting |
| `routine` | info | A routine runs it: its usual time and model calls (median of its last 10 finished runs), else its time when it was verified | the routine's `index.json` |
| `app_note` | info | One or two app notes that predict an obstacle (a pop-up, a location or permission prompt, a bot check, an ad in the way) | `memory/app_notes.py` |

The approval line never says more than the rules can know before the screens are seen. "Will go ahead: you asked for it" still depends on the screen showing the details you gave (Denver, SL 1190), which only the run can check.

### In the runner

Right after planning (routine or agent, inputs), `_run()` writes one `preflight` step: `{"kind": "preflight", "text": "before I start: …", "lines": [...]}`.

- **Once per task.** A task that moves to your phone runs `_run()` again, and keeps its one step.
- **The task's own source and request** are passed, so a task from Muse or a trigger says "will wait for your OK".
- **If `check()` fails,** there is no step and the run goes on.
- **Your phone:** when a line is about your phone and Envoy hasn't seen any phone yet (a fresh API), it looks once (`adb devices`) and asks again, so "it isn't connected" is true. Otherwise there is no extra device call.
- **Nothing else changes.** The evaluations count steps only by the kinds they care about (`action`, `routine_step`, `note`, `memory`, `change`, `approval`, `timeline`, `answer`), or log every step as it is. A new kind changes none of their results.

### Real lines

From a copy of the live task history and routine library (Oct 29). The SkyLark sign-in line shows on each SkyLark task and is left out after the first:

```
Check me in for my flight to Chicago   (web, routine skylark_check_in_flight)
  warn  SkyLark asked you to sign in on envoy-test last time (Oct 28).
  info  Confirming check-in will go ahead: you asked for it.
  info  Using routine skylark_check_in_flight v1: usually 9 s, no model calls.
Check me in for my flight to Chicago   (mcp)
  info  Confirming check-in will wait for your OK.
What's my gate?                        (trigger:Watch my gate)
  info  Using routine skylark_get_flight_gate v1: usually 1.7 s, no model calls.
Check the price of AirPods Pro at Target
  stop  Target needs your Android phone, and it isn't connected.         (no phone)
  warn  Target blocks emulators: I'll ask to use your Pixel 5.           (Pixel 5 connected)
Post the newest video … to Instagram as a reel   (mcp)
  info  Anything that can't be undone will wait for your OK.
In the Wikipedia app, look up Paris
  info  I haven't used Wikipedia on envoy-real before: if it isn't there, I'll install it from the Play Store (free apps only).
```

## Saved logins (experiment)

Not run yet. It needs `envoy-real` and the Pixel 5, and the user saves one throwaway login in the phone's password manager. This section records the result, whatever it is.
