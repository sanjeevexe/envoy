# phone-watch: notifications on Envoy's phone as a trigger source (T1b, contract 3)

Stage 1, Nov 1. Branch `claude/phone-watch-ddc0ae`. Stage 2 (the live check on the Pixel, with the user commenting from their own phone) is not done yet.

## What is true now

- **A sixth trigger kind, `notification`.** Spec: `{"package": "com.instagram.android"}`, or a list of up to 5 apps, plus optional `contains` (title or text), `title_contains`, `text_contains`, `phone` (a list_phones id; Envoy's phone by default) and `push` (on by default).
  - The action may be left out: the trigger then only tells the user (a push) and agents (`notification_events`, which phone_updates reads).
  - Or it runs a goal or a routine through the scheduler's existing path, ask mode included.
  - `create_trigger` (MCP) takes the kind. Like every agent-proposed trigger, it's created switched off, and the user's Yes turns it on. Muse's card reads: "Muse wants to set this up: when Instagram, TikTok or YouTube notifies Envoy's phone with "comment", tell you and Muse. Turn it on?"
- **The watcher** (`backend/api/notifications.py`):
  - Reads `dumpsys notification --noredact` every 3 s, only while an enabled notification trigger names an app the user lets Envoy watch, and only on that trigger's phone.
  - One adb call per phone per poll (`date +%s%3N; dumpsys … p <pkg>` for each package), through `devices/android.py`'s `adb()`. The same call reads the phone's clock.
  - It fires once per notification key and post time, and only for notifications posted after the trigger started being watched. Turning a trigger on doesn't replay what's already in the shade.
  - An update fires when its words changed or Android alerted the user again (`mInterruptionTimeMs`). A silent re-post doesn't fire. Group summaries and ongoing notifications never fire.
  - Unplugging: the watcher backs off (5 s, then up to 30 s) and catches up on replug, so what landed while the phone was unplugged fires then.
- **Writes, pushes, runs:**
  - Each match writes contract 3's row to `notification_events`, redacted (below).
  - It pushes "Instagram: <title>" with the text (push.py kind `notification`, urgency high). Tapping the push opens `/?trigger=<id>`.
  - If ask mode raised a "Should I…?" offer that pushes, that offer is the only push: the user doesn't get two buzzes for one comment.
- **Settings › Phones › Watch notifications:**
  - Lists the third-party apps on Envoy's phone (`pm list packages -3`, read when the user opens it, cached 10 min) plus Instagram, TikTok and YouTube. All are off.
  - A trigger, or an agent proposing one, can't turn an app on.
  - A status line says what's being watched and when it was last checked.
- **Triggers:**
  - A form: chips for the watched apps, optional words, then "Just tell me" or "Ask me first" with a goal.
  - The trigger's row says when it fires, and warns when one of its apps isn't watched.
  - A "Caught on Envoy's phone" list. The web app shows a toast when a notification is caught.
- **Privacy (contract 6):**
  - The dump is parsed in memory and dropped. Only matched notifications are stored.
  - Before storing: digit runs of 4–8 (and 3+3) become "••••", and the rest of the line after code/OTP/PIN/password becomes "[hidden]".
  - `logs/notifications.jsonl` has ids, packages and timings, never words. The trigger's fired keys are hashes.
  - Matching reads the words before redaction, in memory.
- **For agent-door's reader:** `api.notifications.update_line(row, phone_name)` returns contract 3's line (`Instagram on Envoy's phone: "<title>: <text>"`).

## Checked on a device

- **envoy-test (Android 15), with notifications I posted myself (fake text):**
  - P2 report (counts only): package, key, title, text and post time are present for every posted notification. Multi-line text parses exactly.
  - The system's automatic group summary has no words and is skipped.
- **Latency on a :8763 test copy** (scratch `ENVOY_API_DIR`, 0 push subscriptions), 10 notifications posted at random moments, 10/10 caught:
  - From landing on the phone to the push being queued: median ~1.25 s, max 3.0 s.
  - From the `adb … notification post` command to the event being readable over HTTP: median 1.4 s, max 3.1 s.
  - One poll takes 60–130 ms on the emulator. The target is under 10 s.
  - The push to a real iPhone wasn't measured: the test copy has no subscriptions. Stage 2 on :8700 measures it with push receipts.

- **The Pixel (Android 13), P2, Nov 1 ~19:20, read-only, counts only:**
  - Flags print in hex. Every notification in the shade has a key and a post time.
  - Instagram's one notification has a title, a text and a bigText.
  - TikTok and YouTube had no notifications yet: nothing has happened on those accounts.
  - Found and fixed two Android 13 layout facts the fake samples hadn't covered:
    - Apps add their own extras keys (not `android.*`) between the standard ones.
    - A multi-line title or ticker prints its later lines from column 0.
  - Each one made a Play services notification parse with no words. After the fix, every notification with a title and text parses both.
  - Both cases are now in the fake sample.

## Not done / not verified

- **Stage 2:** the user comments on the test account's post from their own phone, and we time it to the push and to phone_updates.
- **phone_updates** shows these events only once agent-door's reader lands (contract 3).
- An API restart doesn't replay notifications that landed while it was down.

## What the video can honestly claim

- "Envoy watches the notifications on its phone, for the apps you allow, and tells Muse and your iPhone within a few seconds." On the emulator: median ~1.25 s from landing to the push being queued. Measure on the Pixel before quoting a number.
- "Codes are hidden before anything is stored; nothing else is kept."
- Not yet: any claim about TikTok or YouTube comments specifically. On the Pixel they had no notifications at P2; Stage 2 will show whether their comment notifications carry the words.
