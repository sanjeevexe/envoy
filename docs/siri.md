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
3. Open `data/api/shortcut/Ask Envoy.shortcut` and choose **Add Shortcut**. iCloud brings it to the iPhone within
   seconds. There, optionally: Settings › Action Button › **Shortcut** › **Ask Envoy**; Control Center › **+** › **Add a
   Control** › search "Shortcut" › **Shortcut** › **Ask Envoy** (iPhone Mirroring can't open Control Center: do this one
   on the phone).

The first run asks three things, once each: speech recognition (**Allow**), "Allow "Ask Envoy" to send 1 text item to
"…ts.net"?" (**Always Allow**; Allow Once would ask every time), and notifications (**Allow**).

The token appears in Settings › Devices under the shortcut's name, **Ask Envoy**: "Siri shortcut: can ask Envoy and start tasks; can't
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
| | e.g. from the iPhone (Oct 29, live API): "Check me in for my flight" | "On it: Check me in for my flight. Anything that can't be undone will wait for your OK." in 6.8 s; the run asked at Confirm check-in and waited for the tap in Envoy |
| something recurring ("every Friday at 6 PM, …") | drafts the trigger **switched off**, with an offer in Envoy | "I've drafted it. Say yes in Envoy to turn it on." |
| a recurring request it couldn't set up | nothing | chat's reason ("I couldn't tell exactly what to do each time.") |
| anything else | chat's reply | the reply |

**The `say` line** is plain text: no markdown, links, task ids or emoji; at most two sentences and about 200 characters
(cut at a sentence, else a word). For a task it adds **one** Before I start line (`api/preflight.py`): the first stop
line ("Chase needs your Android phone, and it isn't connected."), else the first approval line that says it will wait
for or need your OK ("Confirming check-in will wait for your OK.", "The payment step will need your OK."), else the
first warning ("Target blocks emulators: I'll ask to use your Pixel 5."). The routine-specific line comes from the
task's own `preflight` step, which the runner writes once it has matched a routine (one Spark call); `/api/siri`
waits up to 7 s for it, then falls back to `preflight.check()` without a routine ("Anything that can't be undone will
wait for your OK."). Measured: the match call is p50 1.7 s, p90 2.9 s over the recorded history, but 2.6–4.9 s on Oct 29,
when both check-in requests missed a 3 s wait and said the general line. On the iPhone a 5 s wait missed too: the
check-in's match took 4.95 s and its step landed 5.01 s after the task began, so Siri said the general line after the
full 5 s (see "On the iPhone"). So the wait is 7 s (`PREFLIGHT_WAIT_S`), so the demo says the named step; it ends as soon
as the step arrives, and only a slow match costs the extra seconds. When chat's line is already two sentences ("That
may have changed. I'm checking the app.") there's no wait, and only a stop line would replace its second sentence.

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
- **Answers from memory are spoken, even on a locked phone.** On the iPhone (Oct 29) the Action Button and "Hey Siri,
  Ask Envoy" ran and answered with the screen locked, with no Face ID or passcode. So anyone holding your phone, or
  whom Siri answers, can hear what Envoy remembers (a gate, a booking date) and start a task. A task still can't finish anything irreversible: that waits for your OK in Envoy, which needs
  your session. If memory answers should need an unlocked phone, it's a policy choice (refuse memory answers for source
  `siri`, or turn off "Allow Siri When Locked"); it isn't changed here.

## On the iPhone (stage 2)

Tested Oct 29 on the user's iPhone (iOS 18.7) against the live API (:8700 at `059bb7f`, over Tailscale), with two
screen recordings (mic on). One shortcut, the default `speak+notify` build, works on every surface; no second build
was needed.

| Surface | Result | Press to answer (phone) |
| --- | --- | --- |
| Action Button (press and hold) | Listens at once ("Now listening…"), speaks the answer, then the notification keeps the text | about 6.5–7 s with a three-word question: about 3.5 s after you stop talking |
| "Hey Siri, Ask Envoy" | Siri runs it, asks "What's the text?", shows and speaks the answer, then shows "Done." | about 16 s (Siri's own steps); the answer comes about 2 s after you finish |
| "Hey Siri, Envoy" | **Not recognized** ("I didn't get that. Could you try again?", four tries): Siri needs the shortcut's whole name | |
| Control Center button | Same as the Action Button | about 7 s |
| Locked phone (screen dark) | Action Button and "Hey Siri, Ask Envoy" both ran and answered **without Face ID or a passcode** (see the safety model) | |
| Tailscale off | iOS's own alert: "A server with the specified host name could not be found." Nothing is spoken | |

**Server side** (`api.siri`'s timing line), 13 requests: plain replies 1.7–3.5 s (median 2.9 s over the 8 in part 1,
one model call each); memory answers 3.3–6.4 s (two calls: on the phone the first one, "What day is my flight?", took
about 12 s from the press); tasks 3.9 s (a stale gate: no wait) and 6.8 s (the check-in: 1.7 s of chat, then the full
5 s wait that was then in place).

What it said (part 2, the demo take):

| You said | Siri said | Then |
| --- | --- | --- |
| "What day is my flight?" | "Fri, Oct 30, 2026, from the SkyLark app yesterday at 5:50 PM." | |
| "What gate is my flight?" | "That may have changed. I'm checking the app." | a task on envoy-test read Gate B12 in 8.3 s and "Done: …" was pushed |
| "What gate is my flight?" (twice) | "Gate B12, from the SkyLark app just now." | |
| "Check me in for my flight." | "On it: Check me in for my flight. Anything that can't be undone will wait for your OK." | the routine ran 5 steps on envoy-test and asked at Confirm check-in 10 s after the request; you decided on the iPhone app 80 s later |

Two things to know from the test:

- **The approval was pushed, but Do Not Disturb hid it.** Envoy sent "Envoy needs your OK" at once, and the iPhone app's
  service worker reported showing it 0.7 s later (`logs/push.jsonl`). The phone was in Do Not Disturb, so no banner
  appeared; it was waiting in the Envoy app. Ask Envoy's own notifications did show (Shortcuts was allowed through). For
  the demo, turn Focus off, or add Envoy (the Home Screen app) to the Focus's allowed apps.
- **The check-in said the general line.** Its routine match took 4.95 s (4.9 s in the stage 1 device check too), so its
  `preflight` step ("Confirming check-in will wait for your OK.") landed 5.01 s after the task began: about a tenth of
  a second past the 5 s wait. The gate's match takes about 2.6 s. Since then `PREFLIGHT_WAIT_S` is 7 s, which covers the
  check-in; it ends as soon as the step lands, so only a slow match waits longer.

### Which actions

The shortcut uses the text it was given (the Mac, the Share Sheet), else **Dictate Text** (Ask for Input would show a
keyboard on the Action Button). The answer's actions are a build option, settled on the phone:

| `--reply` | Actions | Expected |
| --- | --- | --- |
| `speak+notify` (default) | Speak Text, Show Notification | **checked on the iPhone:** spoken once on the Action Button, Control Center and in Siri (Siri shows the text as it speaks, then "Done."); the notification keeps the text |
| `show` | Show Result | Siri reads it aloud; elsewhere it's shown, not spoken |
| `speak+show` | Speak Text, Show Result | may be spoken twice inside Siri |
| `output` | Stop and Output (if nowhere to output: Respond) | Siri speaks it; `shortcuts run` prints it (the Mac check) |

## Troubleshooting

- **"Envoy doesn't recognize this shortcut any more."** The token was removed in Devices. Make the shortcut again.
- **"That's a lot of requests."** More than 6 a minute (or 100 a day) from this shortcut.
- **"I couldn't do that just now."** A model error or the day's cost cap. Try again in a minute; the API log says
  which (never what you said).
- **"A server with the specified host name could not be found."** (an iOS alert, nothing spoken): Envoy couldn't be
  reached. Turn Tailscale on in the iPhone; check the Mac is awake and the API is running.
- **"I didn't get that. Could you try again?"** from Siri: say the whole name, "Hey Siri, **Ask** Envoy". "Hey Siri,
  Envoy" isn't recognized.
- **No "Envoy needs your OK" banner:** a Focus (Do Not Disturb) is on. The approval is still waiting in Envoy; allow
  Envoy in the Focus, or turn it off.
- **It asks "Allow … to send 1 text item" every time:** you chose Allow Once; run it and choose Always Allow.
- **On the Mac, Dictate Text says to enable Dictation:** expected; the Mac check passes text in with `--input-path`.

## The demo shot

About 40 seconds, iPhone in hand, a screen recording with the mic on. Lead with the Action Button: saying "Hey Siri" in
a video sets off viewers' phones.

Before: Envoy on the tailnet; envoy-test running with SkyLark at `demo_fixtures(signed_in=True)`; the first-run
prompts already answered; and **turn off Do Not Disturb, or allow Envoy in the Focus**, or the approval banner won't
show (it didn't on Oct 29).

1. Press and hold the Action Button: "What gate is my flight?" → "That may have changed. I'm checking the app." (about
   7 s), and a few seconds later "Done: … Gate B12" arrives. Ask again for the instant answer: "Gate B12, from the
   SkyLark app just now."
2. Press and hold: "Check me in for my flight." → "On it: … Confirming check-in will wait for your OK." (about 12 s:
   the answer waits for the routine match, about 5 s)
3. "Envoy needs your OK" arrives about 10 s after the request. Tap it and approve; "Done: …" follows. (Decline instead
   to keep SkyLark as it was; after an approve, reseed with `scripts/demo_setup.py --signed-in --app-only`.)

Fallback: the Control Center button does the same as the Action Button. The Oct 29 take is the part 2 recording
(the user's `RPReplay_Final1793309109.MP4`, 3 min 45 s; not in the repo): steps 1 and 2 with the approval opened from
the app because of Do Not Disturb.
