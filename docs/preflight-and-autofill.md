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
- **An offer's card,** before its Yes (the offers feature adds this).
- **MCP's `heads_up`** on `run_task` and `run_routine`, so Muse can warn you too (the Muse link adds this, `docs/muse-link.md`).

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

Muse uses stored credentials without seeing them. On Android the equivalent is the phone's own password manager: Envoy taps the saved-login suggestion, the manager fills the fields, and Envoy never sees, reads or types a password. The experiment finds out whether that works cleanly, before any feature code. The author saves one throwaway login and makes every sign-in tap; Envoy only observes and records.

### Step 1: is an autofill service active? (Oct 29, read-only)

**envoy-real** (cold boot, claimed and released through the shared device lock script, about 5 minutes; nothing signed in or out):

| Setting | Value |
| --- | --- |
| Android | 15 (SDK 35), Google Play services 26.41.31 |
| `secure autofill_service` | `com.google.android.gms/.autofill.service.AutofillService`: **Google's** |
| `secure credential_service` (and `_primary`) | Google Password Manager (`…credman.service.PasswordAndPasskeyService`) |
| Augmented autofill | `com.google.android.as` (Android System Intelligence), enabled |
| A Google account | present (the Play Store's) |
| The keyboard | **`com.github.uiautomator/.AdbKeyboard`**, the keyboard Envoy's device layer types with (Gboard is installed, not active) |

So autofill is on, and it is Google's. The keyboard is what decides where a suggestion appears. AdbKeyboard doesn't show inline suggestions, so on envoy-real a saved login would be offered as the autofill **dropdown**: a small window of its own under the focused field. Whether Envoy's screen reading (the uiautomator dump) sees that window is exactly what step 2 has to find out.

**The Pixel 5** (Android 13) has the user's keyboard (Gboard), so a saved login might come **inline, in the keyboard's strip**, instead. It doesn't: it comes as the same sheet, at first (see "The Pixel 5" below).

### Steps 2–5 (envoy-real, Oct 29, 12:48–13:30, with the user)

**The setup:**
- **The app:** Wikipedia, installed free from its Play Store page for the test and uninstalled afterwards. Its login uses ordinary Android fields.
  - SkyLark was ruled out: its sign-in is Jetpack Compose fields that don't take part in Android autofill, so it would say nothing about real apps.
- **The account:** a throwaway Wikipedia account the author made on the web.
- **Saving it:** the author signed in once in envoy-real's window and tapped Save on Google's prompt. Google wanted a **captcha-style check** before it would save the password. Then the author logged out in the app.
- **The saved login:** it lives in Google Password Manager for envoy3955@gmail.com, envoy-real's Google account.
- **Readings:** taken with `eval/autofill_probe.py` and saved under `eval/results/autofill/2026-10-29/`. Every text field is reduced to its length and whether it's masked, and the password text is scrubbed everywhere. A check against the live field found the password in none of the 12 files saved up to step 3. The later files hold only yes/no values, or a screen with no password field.

| Step | Result |
| --- | --- |
| **2. Does the suggestion appear where Envoy can find it?** | **Yes.** On focusing Username, Google Play services showed a sheet, *"Use your saved password for Wikipedia?"*, listing the saved login twice ("Envoytest" and "envoytest": Wikipedia capitalizes the name, and both were saved) with a *No thanks* button. It isn't the dropdown step 1 expected; it's a sheet in its own window, owned by the system. Envoy's ordinary screen reading lists it as numbered elements, with the password shown only as `••••••••`. The rows aren't marked clickable (they're list items), so a tap has to land on the row's bounds. With nothing saved (the baseline), focusing the field showed no sheet at all. |
| **3. Does tapping it fill both fields, with the password masked in everything Envoy reads?** | **It fills both** (one tap on "Envoytest", made by Envoy with the author's OK): Username 9 characters, Password 8. **Masking: it failed at first, and is fixed in main.** uiautomator2's dump carries a filled password field's text in plain text (letters and digits, not bullets). Envoy's screen layer put it in the field's label (`Password: <text>`), and an agent stopping at a sign-in screen wrote that screen's text and tree to its trace on disk. That was a gap in existing code, not only in this feature. It was fixed (`beeeb5b`, `devices/screen.py` `mask_passwords()`), and a scan of 8,517 past run files found none that held a password. Re-checked on envoy-real with the field still filled: after the screen layer the field reads `••••••••`, and the password is in none of the compact text, the tree, the stored XML or any element. Only the raw `u2.dump_hierarchy()` still has it, so code must read screens through `build_state`. |
| **4. Secure windows (`FLAG_SECURE`)?** | **Not exercised.** Neither Wikipedia's login screen nor Google's sheet is marked secure. Envoy reads a secure window's tree as usual (the flag stops pictures, not the accessibility tree) and takes no screenshot there. Its fields are masked the same way since `beeeb5b`. |
| **5. Does pressing the app's sign-in button complete it?** | **Yes.** The author pressed Log in on the filled form, and it signed in. Then Wikipedia asked to allow notifications and opened its home page, with no password field left on screen. |

**Cleanup:**
- Wikipedia was uninstalled, which also ended the throwaway session. Nothing else was signed in or out.
- envoy-real's third-party apps match the list taken before the test: Amazon, Chipotle, DoorDash, Starbucks, Target, `com.github.uiautomator`, and Google's `contactkeys`, `safetycore` and `verifier`. That's 9 packages, before and after (`envoy-real-apps-before.txt` and `-after.txt`).
- envoy-real was stopped with `scripts/stop_emulator.sh` and released.
- The throwaway login stays in envoy3955's Password Manager for a live run of the finished feature. Delete it at passwords.google.com once that's done, or now if there won't be one.

### What it means

On envoy-real, steps 2, 3 (with `beeeb5b`) and 5 work: Envoy can find the saved-login sheet, one tap fills both fields without Envoy ever seeing the password, and the app's own button signs in.

Two things a feature would have to handle:
- **The sheet.** It is a system-owned sheet with unclickable list rows. The feature finds it by its title and taps a row's bounds. The label a row shows is the saved username, which may repeat in different capitals.
- **Its first appearance.** The sheet appears on focusing the username field. Before that, the screen looks exactly like any sign-in.

### The Pixel 5 (Oct 29, 19:38–19:55, with the user)

**Step 1, read-only:**

| | Pixel 5 |
| --- | --- |
| Android | 13 (SDK 33) |
| Autofill service | `com.google.android.gms/.autofill.service.AutofillService` (Google), as on envoy-real |
| Credential Manager | not set (Android 13 predates it) |
| Keyboard | Gboard 11.7, with inline suggestions enabled |
| Google account | envoy3955@gmail.com, the same account as envoy-real, so the throwaway login was already there |
| Third-party apps | `ai.envoy.banner`, Instagram (signed in to the test account) and SkyLark: the same 3 before and after |

**Steps 2–5** (Wikipedia installed by the author from its Play Store page for the test, and uninstalled afterwards). The readings are `pixel5-*.json` and `pixel5-*.xml` in `eval/results/autofill/2026-10-29/`.

| Step | Result |
| --- | --- |
| **2. The suggestion** | **The same sheet as envoy-real,** not a keyboard strip: *"Use your saved password for Wikipedia?"*, owned by Google Play services, with the login as "Envoytest" and "envoytest" and the password as `••••••••`. The held feature's finder (`autofill.suggestions`) found it on the live screen as it does on the recorded one. |
| **The sheet shows once** | When the sheet closes without a pick (here it closed by itself while the author was answering a question), the login moves to **Gboard's strip**: chips "Envoytest ···" above the keys, and a tip "Autofill suggestions are now above your keyboard". **The chips aren't in the accessibility tree:** Gboard draws them in a surface, with no text Envoy can read. Tapping the already-focused field again doesn't bring the sheet back. The feature's own code, run live, said "your phone's password manager offered no saved login for Wikipedia" and handed the phone back, which is correct. Opening the login screen again brings the sheet back. |
| **3. The fill** | The feature's code tapped Username and then the row ("Envoytest"). The first time on this phone, Google showed its one-time **"Autofill with Google"** screen (the account, and Continue) before filling. That's a consent screen, so the author accepted it. The feature waited 4 s, said "the saved login didn't fill the fields" and handed the phone back, which is correct. After Continue, both fields filled (9 and 8 characters). **Masking holds on the Pixel:** the raw uiautomator dump has the password in plain text, as on envoy-real, but after Envoy's screen layer (`beeeb5b`) it reads only `••••••••`. The feature's readers saw both fields filled and found the Log in button. The probe saved only the length. |
| **4. Secure windows** | Not exercised: no window was marked secure. |
| **5. Log in** | The author pressed Log in. **Wikipedia showed an hCaptcha** ("Move the correct piece to complete the pattern") over the form. **It's a gap in the held feature:** with the captcha up, the password field isn't on screen, so `sign_in_reason()` reads "not a sign-in", and the feature would have said "Signed in". Fixed in the branch: after the button, the feature waits for the screen to settle and checks `policy/botcheck.bot_check_reason()`, which names this screen ("captcha"). A captcha now ends in "Wikipedia asked you to prove you're human after Log in: that's yours to do" and the hand-off. The test uses this recorded screen. The captcha wasn't solved, since it wasn't needed for the test. |

**Cleanup:**
- Wikipedia was uninstalled. The third-party apps match the list taken before (`pixel5-apps-before.txt` and `-after.txt`).
- Instagram is still signed in, and nothing was signed out. The "Autofill with Google" consent the author gave stays on the phone, as a Google setting.
- The Pixel was released at 19:55.

### The decision

**The Pixel doesn't differ in shape:** it shows the same sheet, the finder reads it, and the password stays masked. So the feature is clean on both kinds of phone, and **the branch is ready, off by default for both.** What the Pixel added:
- **One fix:** a captcha after the button.
- **Two hand-offs, both correct as built:**
  - the sheet already dismissed, leaving only Gboard chips Envoy can't see;
  - Google's one-time consent screen.

On a real phone the feature therefore signs in only when the sheet is fresh and nothing else asks. Everything else goes to you, as before.

## Saved logins: the feature (built Oct 29; ready after the Pixel check)

It was built on a branch and held until the Pixel 5 check. That check is done (above): it's ready, off by default for both kinds of phone.

- **The setting:** `signin.autofill` (`GET/POST /api/settings/signin`, `{"autofill": {"emulator": bool, "phone": bool}}`). Both are **off by default**, and they switch separately. Settings › Phones has the row "Use saved logins from your phone's password manager" (`web/components/SavedLogins.tsx`).
- **Where it runs:** `runner._saved_login`, in the runner's two sign-in branches: the app opening on a sign-in screen, and an agent or routine handing off with "sign-in needed". It runs only when the setting is on for that kind of phone; otherwise, or when it returns False, the phone is handed to you exactly as before.
- **What it does** (`api/autofill.py`, only taps):
  1. Taps the username field.
  2. Waits up to 4 s for a saved-login row: a row outside the app with an account name beside a password shown as dots. Android's autofill dialog, with Google's rows in it, is what envoy-real and the Pixel 5 showed. Gboard's chips can't be read (they aren't in the tree), so they don't count.
  3. Taps that row. One account saved under two spellings counts as one; two different accounts are yours to choose.
  4. Checks that both fields filled, without reading the password: each field must no longer show its hint. A filled password reads as dots, and an empty one as its hint (main `53ab459`).
  5. Asks you through the normal approval, "Sign in to Wikipedia as Envoytest with your saved login?".
  6. On your yes, taps the app's own Sign in / Log in button and waits up to 20 s for the sign-in screen to go. A captcha in its place (`bot_check_reason`) isn't a sign-in: it's yours.
- **Every sign-in asks.** The approval names no button (`target=""`), so `approval_rules.decide()` has nothing to match the request's words against. "Sign in to Wikipedia as Envoytest with my saved login" in the request doesn't approve it. A test proves this: with a named target, it fails.
- **It never** types (no `type` action exists in the module), reads a field's value, photographs a screen or stores anything. A secure sign-in screen works the same way, again without a picture.
- **When anything doesn't match,** it says why in one step and hands the phone to you: no saved login offered, two accounts, fields that don't fill, a no, no sign-in button, or a sign-in or a captcha still there afterwards.
- **Tests** (`backend/tests/test_autofill.py`, 13): six screens recorded from this experiment (`tests/screens/autofill_*.xml`; the throwaway username, and a made-up stand-in for the password). They cover the screens as read; a sign-in with taps only; a password never typed, read or photographed in any outcome; a no that leaves Log in unpressed; no saved login; a sign-in that fails afterwards; a captcha after Log in (the Pixel's hCaptcha); a secure screen; two accounts; the setting (off by default, per kind); and in the runner, that the sign-in asks even when the request's words name it, and that with the setting off for that kind the phone is handed over as before.
- **Not run end to end:**
  - The whole feature through the runner, with an approval and the button, hasn't run on a device: its parts have.
  - On the Pixel, the feature's code tapped the field and the row, and was handed back at the consent screen and the Gboard chips.
  - The readers recognised the filled form and its button.
  - The author pressed Log in on both devices.

**A live run of the finished feature** is yours to do, or to OK, on the throwaway account:
1. Start envoy-real (`scripts/start_emulator.sh envoy-real --window`) and install Wikipedia.
2. Turn on Settings › Phones › Use saved logins › On the emulators.
3. Ask Envoy, from the web app: "In the Wikipedia app, open my watchlist".
4. The sign-in screen should bring up the approval "Sign in to Wikipedia as Envoytest with your saved login?". Say yes, and the task goes on signed in.
5. Uninstall Wikipedia afterwards, and turn the setting off again.
