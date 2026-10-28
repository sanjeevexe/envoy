# Per-app phone routing and install on demand

Oct 28, 2026. Branch `app-routing` (worktree `~/Desktop/Envoy-app-routing`), cut from main `a4142d5`. Prompt:
`prompts/app-routing-onboarding.md`. Results: `eval/results/app_onboarding/`.

## What changed

**1. Envoy sets "use my phone" for an app itself after a bot check.**

- Apps that block emulators are data: `backend/api/emulator_blocked.json` is the starting list (Target, Uber Eats, and
  the common US banking and payment apps: Chase, Bank of America, Wells Fargo, Capital One, Citi, U.S. Bank, PNC, Ally,
  Discover, Amex, PayPal, Venmo, Cash App, Google Wallet; package ids checked on play.google.com). Routing reads it;
  adding an app is a line of JSON. A request can name them ("my Bank of America balance").
- When an app shows a bot check on an emulator, the runner sets the app to your phone in Settings › Phones and
  keeps why beside it (`phone_apps` plus `phone_apps_learned`). The check is the detector that was in
  `eval/run_real_apps.py`, now `backend/policy/botcheck.py` (the eval keeps `bot_check`), seen at launch or after a
  hand-off whose screen or reason is a bot check. It counts only when the app itself shows it. A website's CAPTCHA in
  Chrome doesn't make Chrome "block emulators".
- That task then: with a phone connected, Envoy asks through PhoneAsk ("Shop blocks emulators: Envoy wants to use
  your Galaxy S22 for this task") and, on your yes, moves the task there. One ask per task; only your session
  answers; no answer is never a yes. With no phone, or on a no, the hand-off says plainly: "Shop blocks emulators; it
  needs a real Android phone. Connect your Android phone (USB, or wireless debugging) and ask again. You can also try
  clearing the bot check on envoy-real yourself."
- Later tasks for the app go to your phone, asking first. With no phone connected they don't touch the emulator: the
  task ends at once with "Target blocks emulators; it needs a real Android phone. …". "On the emulator" in a request
  still wins.
- Settings › Phones shows apps by name, marks what Envoy set ("Set by Envoy: it showed a bot check (HSBlockActivity)
  on the emulator (10/28/2026)"), and lists the starting set. Unticking an app Envoy set undoes it for good. The iPhone
  push for "use your phone?" now says why.

**2. Install on demand** (`backend/api/install.py`, called by the runner on emulators only).

- Which app: one Envoy knows (`APP_NAMES`, the starting list, apps it installed before), or the name a request gives
  ("in the Wikipedia app", "install Duolingo", "In AccuWeather, …"). By name it first looks among the apps already on
  the phone (package ids, plus Android's own: Messages, Phone, Files…), then searches the Play Store. An app Envoy
  doesn't know yet now goes to envoy-real, not SkyLark's envoy-test (see "Before").
- The Play Store is read in code, with no model call: the matched result's own button, or the app's page (Install, a
  price, Open, "isn't compatible", "isn't available", sign in). Only the app's own part of a page counts, never a
  sponsored app or a suggestion (see the first measured run).
- Free: tap Install, wait for the package (`pm list packages`; Skip if the Play Store asks to finish account setup),
  then the task carries on. The agent is told the app was just installed, so it expects first-run screens. The name
  is remembered, so the next request that names it goes straight to it.
- Paid: Envoy never pays. It asks through the existing approval flow ("Minecraft: Dream it, Build it! costs $6.99 on
  the Play Store: buy it yourself?"); a yes hands the phone to you to buy it, a no or no answer ends the task as
  declined. The price button is never tapped.
- Sign-ins: the Play Store's own (no Google account on the emulator) and the app's first sign-in screen use the
  existing hand-off ("sign in as you go"). No batch sign-in, no Apps page.
- "Isn't compatible" on an emulator means the app blocks emulators: it is learned exactly like a bot check.

Tests: 16 new in `backend/tests/test_phase6.py`, beside the routing tests, on real Play Store pages captured from
envoy-real (`backend/tests/screens/playstore_*.xml`, account names scrubbed). Full suite: 229 passed.

## Before: a request naming an app the emulator doesn't have

Measured on envoy-real with the code on main (`today*.json`), for "In the Wikipedia app, search for Eiffel Tower and
tell me the year it opened." Wikipedia wasn't installed.

- **Routed to the wrong emulator.** Envoy didn't know the app, so the task had no app, and routing sent app-less tasks
  to envoy-test (SkyLark's). With envoy-test off it failed in 0 s: "The emulator for this app (envoy-test) isn't running
  right now."
- **On envoy-real (picked by hand), the agent improvised.** It tried to launch Wikipedia and failed, circled the Play
  Store for about 18 steps, then searched, tapped Install itself (no free-or-paid check, no rule about it), opened the
  app and ran out of steps in its onboarding: failed, 25 steps, 27 model calls, $0.051, 67 s. It left Wikipedia
  installed (removed afterwards).
- A known app (in `APP_NAMES`) that isn't installed fails at launch ("has no launcher activity (is it installed?)").
  Every app in `APP_NAMES` is on envoy-real, so this one is from the code. On your own phone: "isn't installed on your
  phone (install it from the Play Store)", which is unchanged.

## Measured on envoy-real

RERUN_TABLE

## Weak spots

- **Bot checks are tested offline, not on a device.** Target, the app that showed one, is on the starting list, so it
  never reaches the emulator now. No other app showed a bot check on envoy-real. Learning, the plain message and
  moving to the phone are covered with fakes.
- **Moving a task to the phone isn't run on the Pixel 5.** The Pixel 5 has no Google account and so no Play Store apps;
  a task moved there for an app it lacks ends with "install it from the Play Store". Needs your OK to try.
- **The banking apps are listed by reputation** (device-integrity checks are common in banking apps), not tested:
  Envoy doesn't sign in, so we can't see their checks. Any of them can be removed from the JSON.
- **Install by name leans on the Play Store's layout as of Oct 28**: result cards with their own buttons, and a
  "Sponsored" label above ads. If that changes, the safe failure is "no app called … in the results" or a result
  without a button opening its page; the ad rule depends on that label.
- **Names are only taken from "… app" phrasing** (or "install X"), so "look up X on Wikipedia" alone still runs with no
  app. Learned names likewise match only when named as an app, so an installed Weather app doesn't take every
  question about the weather.
- **A generic name gets the Play Store's best match** ("in the Notes app" may install a notes app you didn't mean).
  The task's steps say what was installed, and it's free; uninstalling stays yours.
- **Warm cache:** Wikipedia had been installed on envoy-real before, so its later installs may be faster than a cold one.

## Spend

SPEND

## Merge

MERGE
