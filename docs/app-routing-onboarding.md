# Per-app phone routing and install on demand

Oct 28, 2026. In `main` since that day (`e0789e1`). Results: `eval/results/app_onboarding/`.

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
  on the emulator (10/28/2026)"), and lists the starting set. Unticking an app Envoy set undoes it for good (checked in
  the browser on a test copy of the API). The iPhone push and the web prompt for "use your phone?" now say why; for an
  app that blocks emulators the other answer reads "Not my phone" instead of "Use an emulator".

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

Tests: 17 new in `backend/tests/test_phase6.py`, beside the routing tests, on real Play Store pages captured from
envoy-real (`backend/tests/screens/playstore_*.xml`, account names scrubbed). Full suite: 230 passed.

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

Standard tier (Muse Spark 1.3), through the task runner (the same path as a request from the web app), with its own
data folder, no phone (discovery off), and nobody answering: approvals and "use your phone?" are declined by the
script. Every app installed was uninstalled afterwards; envoy-real is back to its 9 third-party apps.

**First build** (`install.json`):

| Request | Result | Time | Model calls | Cost |
| --- | --- | --- | --- | --- |
| In the Wikipedia app, … the year the Eiffel Tower opened | done, "1889"; installed in 22 s | 82 s | 20 | $0.035 |
| In the Google Translate app, translate "good morning" … | **wrong app**: a sponsored look-alike installed and used; failed at 25 steps | 104 s | 27 | $0.062 |
| In the Wikipedia app, … Statue of Liberty dedicated (known now) | done, "1886"; no search, no install | 24 s | 8 | $0.013 |
| In the Minecraft app, … ($6.99) | declined through the approval flow; price never tapped | 6 s | 0 | $0 |
| The price of AirPods Pro at Target | "Target blocks emulators; it needs a real Android phone. …" (no phone connected) | 0 s | 0 | $0 |

The Google Translate run was the important finding. The results page put a sponsored translator, with its own
Install button, above Google Translate. The first build read the results page as if it were an app's page and
tapped the first Install: the ad's. That bug is fixed, and the real page is now a test fixture (only the matched
result's own button counts, and the result after "Sponsored" is never picked). Titles were wrong too ("Sponsored",
"New!"), also fixed.

**After the fix** (`install-after-fix*.json`):

| Request | Install | Task | Time | Model calls | Cost |
| --- | --- | --- | --- | --- | --- |
| In the Wikipedia app, … Eiffel Tower | right app, 22 s (find 2, download and install 20) | failed: 25 steps in the article | 103 s | 26 | $0.045 |
| (again, after the note below) | right app, 8 s (find 3, install 5) | failed: 25 steps in the article | 86 s | 27 | $0.047 |
| In the Google Translate app, translate "good morning" … | right app, 6 s | failed: the app said "Can't translate · Check your connection" on every try | 105 s | 28 | $0.060 |
| In the Merriam-Webster app, look up serendipity (never installed before) | right app, 26 s (find 2, download and install 24) | done: "the ability to find valuable or agreeable things not sought for" | 63 s | 10 | $0.026 |
| In the Wikipedia app, … Statue of Liberty (known now) | none needed | done, "1886" | 24 s | 6 | $0.010 |
| In the Minecraft app, … | paid, $6.99: asked, declined; price never tapped | declined | 4 s | 0 | $0 |
| The price of AirPods Pro at Target | | "Target blocks emulators; it needs a real Android phone. …" | 0 s | 0 | $0 |

What this shows. Finding and installing the app is now right every time: after the fix 4 of 4 installs got the app
asked for (and the first build's Wikipedia install did too), in 6 to 26 s, with no model calls. What follows depends on the agent in an app it has never seen. Wikipedia's Eiffel
Tower question passed 1 of 3 first runs. Twice the agent reached the article but didn't find the year in its
collapsed "Quick facts" box within 25 steps (the baseline agent ran out of steps too, still in the onboarding). Merriam-Webster passed. Translate
couldn't reach its service from the emulator. The agent's first step after an install was often Back on the welcome
screen, which closed Wikipedia, so the note it gets after an install now says to use the screen's own Skip, Next or
Forward. On the rerun it still pressed Back once, with a garbled reason ("UNUSED - placeholder"), which looks like the
step-schema ordering issue the AndroidWorld branch fixes. Compared with before: the same Wikipedia request went to
SkyLark's emulator (or, on envoy-real, spent 18 steps finding the Play Store before installing by itself); now it is
installed in 8 to 22 s before the agent starts.

## Weak spots

- **Bot checks are tested offline, not on a device.** Target, the app that showed one, is on the starting list, so it
  never reaches the emulator now. No other app showed a bot check on envoy-real. Learning, the plain message and
  moving to the phone are covered with fakes.
- **Moving a task to the phone wasn't run on the Pixel 5 in this pass.** It had no Play Store apps on Oct 28, and has
  since run Instagram, TikTok, YouTube and Uber.
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

$0.36 on the Meta key, all standard tier and real-app scope: 189 calls (183 Muse Spark 1.3, plus 6 empty $0 rows),
from this worktree's own cost log (`logs/model_costs.jsonl`). The baseline run cost $0.051, the first build's runs
$0.109, the runs after the fix $0.187; the other $0.011 was finished tasks writing what they saw into the run's own
throwaway memory. Unit tests make no model calls.
