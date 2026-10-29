# preflight-logins: report

Branch `claude/bold-payne-71c942`, on main `ce747cb`. Model spend: **$0**: nothing in this work calls the Meta API.

| Stage | State | Commits |
| --- | --- | --- |
| 0: `runner.start(..., phone_ok=)` and Instagram in `APP_NAMES` | **In main** (`823fbb8`, merged at `ce747cb`) | `823fbb8` |
| 1: Before I start | Branch ready, sent to the coordinator | `862b597`, `96b1699` |
| 2: saved logins (autofill) | Experiment step 1 done; steps 2–5 wait for the user | `d08518b`, `7b44f3f` |

Tests: 378 backend tests pass (`uv run --project backend pytest backend/tests -q`), 23 of them in the new `backend/tests/test_preflight.py` (5 for stage 0, 18 for stage 1). `npm run build` in `web/` passes.

## Stage 0: the two runner changes others build on

- **`runner.start(..., phone_ok: str | None = None)`.** It records that your yes already covers that phone (`phone_allowed[task_id]`) right after the task is created, before its run is scheduled. `_choose_phone` then skips "Use your Pixel 5?" for that phone only; any other phone routing picks still asks. The entry is dropped when the task ends, so a yes never outlives its task (also when the task ran on an emulator).
- **Instagram in `APP_NAMES`.** Goals that name it resolve to `com.instagram.android`, and it shows in Settings › Phones and the approvals list. The only model input this changes is one more line in the cross-app lead's app catalog. Word-boundary matching, so "instagrammable" doesn't resolve.
- **Tests:** with `phone_ok` there's no second ask; without it the ask is unchanged; a `phone_ok` for another phone still asks; it's dropped on an emulator run; Instagram resolves and no other app moves. Each fails on the code before the change.

## Stage 1: Before I start

`backend/api/preflight.py`: `check(runner, goal, *, request, source, app, routine, inputs, phone, phone_ok=None)`. It returns at most five lines `{kind, text, level}`, stop first. It makes no model call and takes no device action, never raises, and takes 0.1–13 ms on a copy of the live history (under 6 ms on a test history of 5,000 tasks). The full contract, each line's source, and the rules behind each line are in `docs/preflight-and-autofill.md`.

**Real lines** (from a copy of the live task history and routine library):

```
Check me in for my flight to Chicago   (web, routine)
  warn  SkyLark asked you to sign in on envoy-test last time (Oct 28).
  info  Confirming check-in will go ahead: you asked for it.
  info  Using routine skylark_check_in_flight v1: usually 9 s, no model calls.
The same from Muse (mcp)
  info  Confirming check-in will wait for your OK.
Check the price of AirPods Pro at Target
  stop  Target needs your Android phone, and it isn't connected.     (no phone)
  warn  Target blocks emulators: I'll ask to use your Pixel 5.       (Pixel 5 connected)
Post the newest video … to Instagram as a reel   (mcp)
  info  Anything that can't be undone will wait for your OK.
In the Wikipedia app, look up Paris
  info  I haven't used Wikipedia on envoy-real before: if it isn't there, I'll install it from the Play Store (free apps only).
```

- **The runner** writes one `preflight` step per task right after planning: `{kind, text, lines}`. A task that moves to your phone keeps its one step, and a failing check leaves no step. It looks for phones once more only when a line is about your phone and none has been seen yet. An unconditional look shifted a background task's writes into `test_briefing`'s "nothing written" window, so the look is kept that narrow.
- **The evaluations:** I read every place in `eval/` and `backend/tests/` that reads task steps. Each filters by the kinds it cares about or logs every step, so a new kind changes no result.
- **The web:** a "Before I start" card at the top of the task view (`BeforeIStart`, exported for an offer's card), with the avatar thinking, warnings in apricot and a stop in brick. The step itself stays out of the step list. Mock fixtures cover a stop (Chase), sign-in and device warnings (DoorDash), a routine (check-in) and both streaming tasks.

Screenshots (mock mode):

| 390, dark: warnings and info | 390, light: a stop | 1440, light: a routine |
| --- | --- | --- |
| ![](preflight-logins-report/before-i-start-390-dark-doordash.jpg) | ![](preflight-logins-report/before-i-start-390-light-stop.jpg) | ![](preflight-logins-report/before-i-start-1440-light-routine.jpg) |

**Contract additions** (told to the coordinator):
- `phone_ok=` is an optional extra keyword. With it, the device line says "I'll use your Pixel 5 (you said yes)" rather than promising an ask.
- `routine=` also takes a Routine object.

## Stage 2: saved logins, the experiment so far

**Step 1 (envoy-real, Oct 29, read-only):**
- Google's autofill service is active (Android 15, Play services 26.41), with Google Password Manager as the credential provider and a Google account present.
- Its keyboard is uiautomator2's **AdbKeyboard**, the one Envoy types with. So a saved login there would be offered as the autofill **dropdown** window, while the Pixel 5's Gboard would likely offer it **inline** in the keyboard strip. Both are worth one look.
- Claimed, cold-booted, stopped with `scripts/stop_emulator.sh` and released, in about 6 minutes.

**Ready for steps 2–5:**
- `eval/autofill_probe.py` reads the sign-in screen the way Envoy does and saves redacted dumps: every field reduced to its length and whether it's masked, and password text scrubbed everywhere else. It also saves the window list.
- It taps the username field, and one element by its exact label only when you say so.
- It refuses text fields and sign-in buttons, never types and takes no screenshots.

**Waiting on:** the coordinator is batching everything that needs you. For this test you'll be asked to save one throwaway login, in an app that isn't signed in on the device, and to make the sign-in taps.

## Not done or not checked

- Stage 2, steps 2–5, and whether to build the feature at all (only if those steps all work on at least one device).
- Using the card's lines on an offer's card and in MCP's `heads_up` is for proactive and muse-link, through their guarded imports.
- I haven't seen the card live on the iPhone (:8443). It's checked in mock mode at 390 and 1440 only. The live API restarts on the new build only after the coordinator merges.
- `memory/retrieval.py` names apps for memory answers from its own short list, so Instagram would show there as "android app". That's memory's lane, not changed here.
