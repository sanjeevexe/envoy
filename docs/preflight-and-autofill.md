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

Muse uses stored credentials without seeing them. On Android the equivalent is the phone's own password manager: Envoy taps the saved-login suggestion, the manager fills the fields, and Envoy never sees, reads or types a password. The experiment finds out whether that works cleanly, before any feature code. The user saves one throwaway login and makes every sign-in tap; Envoy only observes and records.

### Step 1: is an autofill service active? (Oct 29, read-only)

**envoy-real** (cold boot, claimed and released through `coord/devices.sh`, about 5 minutes; nothing signed in or out):

| Setting | Value |
| --- | --- |
| Android | 15 (SDK 35), Google Play services 26.41.31 |
| `secure autofill_service` | `com.google.android.gms/.autofill.service.AutofillService`: **Google's** |
| `secure credential_service` (and `_primary`) | Google Password Manager (`…credman.service.PasswordAndPasskeyService`) |
| Augmented autofill | `com.google.android.as` (Android System Intelligence), enabled |
| A Google account | present (the Play Store's) |
| The keyboard | **`com.github.uiautomator/.AdbKeyboard`**, the keyboard Envoy's device layer types with (Gboard is installed, not active) |

So autofill is on, and it is Google's. The keyboard is what decides where a suggestion appears. AdbKeyboard doesn't show inline suggestions, so on envoy-real a saved login would be offered as the autofill **dropdown**: a small window of its own under the focused field. Whether Envoy's screen reading (the uiautomator dump) sees that window is exactly what step 2 has to find out.

**The Pixel 5** (Android 13) isn't connected yet. Its keyboard is the user's (Gboard), so a saved login would most likely be offered **inline, in the keyboard's suggestion strip**, which is a different window and a different thing to find. envoy-real's result therefore doesn't settle the Pixel; both are worth one look.

### Steps 2–5 (envoy-real, Oct 29, 12:48–13:30, with the user)

**The setup:**
- **The app:** Wikipedia, installed free from its Play Store page for the test and uninstalled afterwards. Its login uses ordinary Android fields.
  - SkyLark was ruled out: its sign-in is Jetpack Compose fields that don't take part in Android autofill, so it would say nothing about real apps.
- **The account:** a throwaway Wikipedia account the user made on the web.
- **Saving it:** the user signed in once in envoy-real's window and tapped Save on Google's prompt. Google wanted a **captcha-style check** before it would save the password. Then the user logged out in the app.
- **The saved login:** it lives in Google Password Manager for envoy3955@gmail.com, envoy-real's Google account.
- **Readings:** taken with `eval/autofill_probe.py` and saved under `eval/results/autofill/2026-10-29/`. Every text field is reduced to its length and whether it's masked, and the password text is scrubbed everywhere. A check against the live field found the password in none of the 12 files saved up to step 3. The later files hold only yes/no values, or a screen with no password field.

| Step | Result |
| --- | --- |
| **2. Does the suggestion appear where Envoy can find it?** | **Yes.** On focusing Username, Google Play services showed a sheet, *"Use your saved password for Wikipedia?"*, listing the saved login twice ("Envoytest" and "envoytest": Wikipedia capitalizes the name, and both were saved) with a *No thanks* button. It isn't the dropdown step 1 expected; it's a sheet in its own window, owned by the system. Envoy's ordinary screen reading lists it as numbered elements, with the password shown only as `••••••••`. The rows aren't marked clickable (they're list items), so a tap has to land on the row's bounds. With nothing saved (the baseline), focusing the field showed no sheet at all. |
| **3. Does tapping it fill both fields, with the password masked in everything Envoy reads?** | **It fills both** (one tap on "Envoytest", made by Envoy with the user's OK): Username 9 characters, Password 8. **Masking: it failed at first, and is fixed in main.** uiautomator2's dump carries a filled password field's text in plain text (letters and digits, not bullets). Envoy's screen layer put it in the field's label (`Password: <text>`), and an agent stopping at a sign-in screen wrote that screen's text and tree to its trace on disk. That was a gap in existing code, not only in this feature. The coordinator fixed it (`beeeb5b`, `devices/screen.py` `mask_passwords()`) and scanned 8,517 past run files: none held a password. Re-checked on envoy-real with the field still filled: after the screen layer the field reads `••••••••`, and the password is in none of the compact text, the tree, the stored XML or any element. Only the raw `u2.dump_hierarchy()` still has it, so code must read screens through `build_state`. |
| **4. Secure windows (`FLAG_SECURE`)?** | **Not exercised.** Neither Wikipedia's login screen nor Google's sheet is marked secure. Envoy reads a secure window's tree as usual (the flag stops pictures, not the accessibility tree) and takes no screenshot there. Its fields are masked the same way since `beeeb5b`. |
| **5. Does pressing the app's sign-in button complete it?** | **Yes.** The user pressed Log in on the filled form, and it signed in. Then Wikipedia asked to allow notifications and opened its home page, with no password field left on screen. |

**Cleanup:**
- Wikipedia was uninstalled, which also ended the throwaway session. Nothing else was signed in or out.
- envoy-real's third-party apps match the list taken before the test: Amazon, Chipotle, DoorDash, Starbucks, Target, `com.github.uiautomator`, and Google's `contactkeys`, `safetycore` and `verifier`. That's 9 packages, before and after (`envoy-real-apps-before.txt` and `-after.txt`).
- envoy-real was stopped with `scripts/stop_emulator.sh` and released.
- The throwaway login stays in envoy3955's Password Manager for the Pixel check. Delete it at passwords.google.com once that's done.

### What it means

On envoy-real, steps 2, 3 (with `beeeb5b`) and 5 work: Envoy can find the saved-login sheet, one tap fills both fields without Envoy ever seeing the password, and the app's own button signs in.

Two things a feature would have to handle:
- **The sheet.** It is a system-owned sheet with unclickable list rows. The feature finds it by its title and taps a row's bounds. The label a row shows is the saved username, which may repeat in different capitals.
- **Its first appearance.** The sheet appears on focusing the username field. Before that, the screen looks exactly like any sign-in.

**Still open: the Pixel 5** (Android 13, Gboard), where the suggestion may come inline in the keyboard strip instead. It's checked at the next sitting with the same steps.

**The build decision** stays as agreed: the feature is built only if it's clean, off by default, and the Pixel doesn't differ.

## Saved logins: the feature (built Oct 29, held until the Pixel check)

The coordinator asked for it to be built now on a branch and held: no branch-ready until the Pixel 5 check. If that check doesn't happen by the Nov 1 cut, the coordinator decides whether the emulator path merges alone.

- **The setting:** `signin.autofill` (`GET/POST /api/settings/signin`, `{"autofill": {"emulator": bool, "phone": bool}}`). Both are **off by default**, and they switch separately. Settings › Phones has the row "Use saved logins from your phone's password manager" (`web/components/SavedLogins.tsx`).
- **Where it runs:** `runner._saved_login`, in the runner's two sign-in branches: the app opening on a sign-in screen, and an agent or routine handing off with "sign-in needed". It runs only when the setting is on for that kind of phone; otherwise, or when it returns False, the phone is handed to you exactly as before.
- **What it does** (`api/autofill.py`, only taps):
  1. Taps the username field.
  2. Waits up to 4 s for a saved-login row: a row outside the app with an account name beside a password shown as dots. Android's autofill dialog, with Google's rows in it, is what envoy-real showed.
  3. Taps that row. One account saved under two spellings counts as one; two different accounts are yours to choose.
  4. Checks that both fields filled, without reading the password: each field must no longer show its hint. A filled password reads as dots, and an empty one as its hint (main `53ab459`).
  5. Asks you through the normal approval, "Sign in to Wikipedia as Envoytest with your saved login?".
  6. On your yes, taps the app's own Sign in / Log in button and waits up to 20 s for the sign-in screen to go.
- **Every sign-in asks.** The approval names no button (`target=""`), so `approval_rules.decide()` has nothing to match the request's words against. "Sign in to Wikipedia as Envoytest with my saved login" in the request doesn't approve it. A test proves this: with a named target, it fails.
- **It never** types (no `type` action exists in the module), reads a field's value, photographs a screen or stores anything. A secure sign-in screen works the same way, again without a picture.
- **When anything doesn't match,** it says why in one step and hands the phone to you: no saved login offered, two accounts, fields that don't fill, a no, no sign-in button, or the sign-in still there afterwards.
- **Tests** (`backend/tests/test_autofill.py`, 12): five screens recorded from this experiment (`tests/screens/autofill_*.xml`; the throwaway username, and a made-up stand-in for the password). They cover the screens as read; a sign-in with taps only; a password never typed, read or photographed in any outcome; a no that leaves Log in unpressed; no saved login; a sign-in that fails afterwards; a secure screen; two accounts; the setting (off by default, per kind); and in the runner, that the sign-in asks even when the request's words name it, and that with the setting off for that kind the phone is handed over as before.
- **Not measured:** the Pixel 5's inline suggestions in Gboard. The finder skips the keyboard's window on purpose until the Pixel check shows what they look like.

**A live run of the finished feature** is yours to do, or to OK, on the throwaway account:
1. Start envoy-real (`scripts/start_emulator.sh envoy-real --window`) and install Wikipedia.
2. Turn on Settings › Phones › Use saved logins › On the emulators.
3. Ask Envoy, from the web app: "In the Wikipedia app, open my watchlist".
4. The sign-in screen should bring up the approval "Sign in to Wikipedia as Envoytest with your saved login?". Say yes, and the task goes on signed in.
5. Uninstall Wikipedia afterwards, and turn the setting off again.
