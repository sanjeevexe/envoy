# Ask Envoy: Siri, the Action Button and Control Center

Talk to Envoy without opening it. Press the iPhone's Action Button (or say "Hey Siri, Ask Envoy", or tap a Control
Center button) and say what you want:

> "Check me in for my flight." → **"On it: check me in for my flight. Confirming check-in will wait for your OK."**
> A moment later the phone shows "Envoy needs your OK". Tap it, approve, and "Done: …" arrives.
>
> "What gate is my flight?" → **"Your gate is B12."** If that may be out of date and a phone is free to check:
> **"That may have changed. I'm checking the app."**, and the answer arrives as a notification.

It's an Apple Shortcut, not an app: no developer account, and the phone's own dictation turns speech into text (free,
on the device). A native app later would call the same endpoint.

## Setup (three steps, on the Mac)

1. Envoy is on the tailnet (`scripts/serve_tailnet.sh on`, as for the iPhone app) and running a build with this feature.
2. Make the shortcut. The script reads your session itself and never prints the token:
   ```bash
   uv run --project backend python scripts/make_shortcut.py --siri
   ```
3. Open `data/api/shortcut/Ask Envoy.shortcut` and choose **Add Shortcut**. iCloud brings it to the iPhone. There,
   optionally: Settings › Action Button › Shortcut › **Ask Envoy**; Control Center › edit › add a control › Shortcuts ›
   **Ask Envoy**.

The token appears in Settings › Devices as **Ask Envoy (Siri)**: "Siri shortcut: can ask Envoy and start tasks; can't
approve anything". Remove it there and the shortcut stops working at once ("Envoy doesn't recognize this shortcut any
more. Set up Ask Envoy again.").

For a copy of the API (testing): `--base http://127.0.0.1:<port> --api-dir <that copy's API dir>` makes **Ask Envoy
(test)**, which never shadows the real one; add `--mac-test` to allow the plain `http://127.0.0.1` address for a build
that only runs on the Mac (`shortcuts run "Ask Envoy (test)" --input-path <text file>`). `--reply` picks how the
answer is given: `speak+notify` (the default), `show`, `speak+show` or `output` (see "Which actions" below).

## What it does, and what it can't

`POST /api/siri` with `{"message": "<what you said>"}` and the `siri` token goes through **chat**, exactly like a
message typed in Envoy, and answers `{"say": "<one line>", "kind": "...", "task_id"?: "..."}`. The shortcut speaks and
shows `say`.

| You say | Envoy does | Siri says |
| --- | --- | --- |
| a question memory can answer (fresh) | answers from memory | the answer: "Your gate is B12." |
| a question whose answer may be stale, with a phone free | starts the task that checks | "That may have changed. I'm checking the app." (the answer comes as "Done: …") |
| an old answer and no phone free | answers from memory | the answer with when it was seen ("…yesterday at 5:50 PM, but it may have changed.") |
| a task | starts it, source `siri` | "On it: …" plus one Before I start line (below) |
| | e.g. on envoy-test (Oct 29): "Check me in for my flight" | "On it: Check me in for my flight. Anything that can't be undone will wait for your OK." in 4.9 s; the run asked at Confirm check-in |
| something recurring ("every Friday at 6 PM, …") | drafts the trigger **switched off**, with an offer in Envoy | "I've drafted it. Say yes in Envoy to turn it on." |
| a recurring request it couldn't set up | nothing | chat's reason ("I couldn't tell exactly what to do each time.") |
| anything else | chat's reply | the reply |

**The `say` line** is plain text: no markdown, links, task ids or emoji; at most two sentences and about 200 characters
(cut at a sentence, else a word). For a task it adds **one** Before I start line (`api/preflight.py`): the first stop
line ("Chase needs your Android phone, and it isn't connected."), else the first approval line that says it will wait
for or need your OK ("Confirming check-in will wait for your OK.", "The payment step will need your OK."), else the
first warning ("Target blocks emulators: I'll ask to use your Pixel 5."). The routine-specific line comes from the
task's own `preflight` step, which the runner writes once it has matched a routine (one Spark call); `/api/siri`
waits up to 5 s for it, then falls back to `preflight.check()` without a routine ("Anything that can't be undone will
wait for your OK."). Measured: the match call is p50 1.7 s, p90 2.9 s over the recorded history, but 2.6–4.9 s on Oct 29,
when both check-in requests missed a 3 s wait and said the general line. So the wait is 5 s (`PREFLIGHT_WAIT_S`), so the
demo says the named step; it ends as soon as the step arrives, and only a slow match costs the extra seconds. When chat's line is already two sentences ("That may have changed. I'm
checking the app.") there's no wait, and only a stop line would replace its second sentence.

**What the `siri` token can do:** ask Envoy (`POST /api/siri`), and nothing else. It can't read tasks or memory, use
`/api/chat`, approve or decline, decide an offer, take over, open the live view, the event stream or voice
(WebSockets), make tokens, or use `/mcp`. A test walks every other `/api/*` route with it and gets 401 or 403 from
each.

**Limits:** 400 characters of text; 6 requests a minute and 100 a day per token ("That's a lot of requests. Try again
in a minute.").

**Errors still say something:** 400 ("I didn't catch that."), 401 (the token was removed), 429 (the limits), and any
failure inside (a model error, the cost cap): "I couldn't do that just now. Try again in a minute." Checked on the Mac:
Shortcuts' *Get Contents of URL* hands back the body of a 400, 401 and 429, so the status codes stay. Nothing logs what
you said: `api.siri` logs the kind of answer and the timings only.

## The safety model

- **Siri's requests are not "your own words" for approvals.** They get the source `siri`, which is not one of the
  approval rules' direct sources (`policy/approval_rules.py`: `web`, `chat`, `voice`, `iphone`). Siri runs shortcuts
  on a locked phone and answers anyone who says "Hey Siri", so every irreversible step waits for your OK on Envoy's own
  screens, **even one the request names** ("Check me in" still asks at Confirm check-in). Money always asks. A routine
  you set to run without asking still does, as for every source. Envoy's in-app mic (`voice`) stays direct: that's
  you, in Envoy's signed-in app.
- **Siri never turns anything on.** A recurring job is created switched off with an offer; only your yes in Envoy
  turns it on, and each firing asks you first.
- **The token** is narrow, stored hashed, named, revocable in Devices, and lives only in the signed shortcut file and
  the shortcut. The script never prints it.
- **Answers from memory are spoken.** Whether that should need an unlocked phone depends on what iOS does when locked
  (stage 2, below).

## On the iPhone (stage 2)

_To be filled in after the iPhone test: which actions listen and answer once from Siri, the Action Button and Control
Center; the locked phone; Envoy unreachable; timings; the screen recording._

### Which actions

The shortcut uses the text it was given (the Mac, the Share Sheet), else **Dictate Text** (Ask for Input would show a
keyboard on the Action Button). The answer's actions are a build option, settled on the phone:

| `--reply` | Actions | Expected |
| --- | --- | --- |
| `speak+notify` (default) | Speak Text, Show Notification | spoken once everywhere; the notification keeps the text |
| `show` | Show Result | Siri reads it aloud; elsewhere it's shown, not spoken |
| `speak+show` | Speak Text, Show Result | may be spoken twice inside Siri |
| `output` | Stop and Output (if nowhere to output: Respond) | Siri speaks it; `shortcuts run` prints it (the Mac check) |

## Troubleshooting

- **"Envoy doesn't recognize this shortcut any more."** The token was removed in Devices. Make the shortcut again.
- **"That's a lot of requests."** More than 6 a minute (or 100 a day) from this shortcut.
- **"I couldn't do that just now."** A model error or the day's cost cap. Try again in a minute; the API log says
  which (never what you said).
- **An error from Shortcuts itself, with no spoken line:** Envoy couldn't be reached at all (Tailscale off on the
  phone, the Mac asleep, the API stopped). Stage 2 records exactly what appears.
- **On the Mac, Dictate Text says to enable Dictation:** expected; the Mac check passes text in with `--input-path`.

## The demo shot

_To be filled in after the iPhone test (who presses what, the phrases, the timings and the fallback). Lead with the
Action Button: saying "Hey Siri" in a video sets off viewers' phones._
