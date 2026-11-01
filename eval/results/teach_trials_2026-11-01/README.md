# Teach-mode trials on real apps (Oct 31, 21:39–22:02 ET; Nov 1 UTC)

Teach mode on two of the apps slated for uninstall from envoy-real, Wikipedia and Google Calculator, on Loop B's tasks,
so its agent runs are the comparison (eval/results/real-apps/loop-b/runs.json, Oct 30, main b31d3da). Code: main
9c464ad. Test API copy on :8753 with its own `ENVOY_API_DIR` and token (push_subs 0). Model spend $0.28, all of it five
Muse Wonder compiles; every replay made 0 model calls.

**The demonstrator was a script, not a person.** `eval/teach_person.py` starts a teach session through the API and drives
the phone through the live view's WebSocket, sending the messages the web app sends (taps as screen fractions, typing key
by key, drags). It finds what to tap by reading the screen through `build_state`. It answers the question when it
finishes ("Done, it worked").

Yelp (sign-up screen) and OpenTable (location prompt) still open on first-launch screens that are the user's to answer,
so they were skipped and left untouched. Spotify needs a sign-in.

## Results

| | Calculator: "what is 1234 times 5678?" | Wikipedia: "what year did the Golden Gate Bridge open?" |
| --- | --- | --- |
| Agent (Loop B) | 3/3 right; 38.8 / 40.6 / 42.4 s, $0.080 / $0.077 / $0.084, 13 calls each | 3/3 right; 50.5 / 51.0 / 43.3 s, $0.083 / $0.073 / $0.064, 13–14 calls |
| Agent's routine | none: it tapped each digit with the whole number as its text; 0/1 (145 s, $0.30, agent fallback hit its step limit); removed | `wikipedia_find_opening_year`, read after one article's words; replays with repair and agent allowed: 5/5 same subject (2 by the routine alone), new subject 0/1 by the routine; not in the library |
| Teach once | 10 taps in 10.6 s; compile $0.067 | 11 steps in 32.1 s (search, open the article, scroll to the sentence); compile $0.051; the last of ten sessions (see below) |
| Teach's verification replay | 10/10 steps, 0 calls, 6.3 s, 7006652: **saved** as `calculator_multiply_numbers` v1 | **failed** at step 1 (the Search tab's after-checks), 2.4 s, so nothing was saved |
| 3 strict replays | **3/3**, 0 calls, 6.3 / 6.3 / 6.0 s, 7006652 | **3/3** from the compiled file (not in the library), 0 calls, 11.8 / 11.8 / 12.6 s, "May 27, 1937" |
| New input | 4321 × 8765: **37873565, right**, 0 calls, 5.9 s | Brooklyn Bridge: **0/2**, both stopped at step 1 (2.4 s, 2.2 s), before the read |

Strict replays use `eval/teach_trials.py` straight on the phone (no API copy running). Each one launches the app fresh and
runs with no repair and no agent, as teach mode's own verification replay does. Approvals are declined; none were asked.
Loop B's routine replays ran through the API with repair and the agent allowed, so they aren't the same condition.

## What it shows

- **Calculator: teaching produced the routine the agent couldn't.** Wonder turned the ten taps into one input per digit
  (`first_operand_digit_1`…`second_operand_digit_4`; the request's numbers fill them). So the routine multiplies any two
  four-digit numbers, with no model, in about 6 s instead of about 40 s and $0.08. It is fixed to four digits each,
  because the number of taps is fixed.
- **Wikipedia: the demonstration was never the problem; reading the answer was.** The year is prose inside the
  article's web page, with no ID. Attempts and what each one showed:

  | Sessions (teach-1031-…) | Answer | Outcome |
  | --- | --- | --- |
  | 213927, 214816 | — | The phone was still on the article from my exploration (teach start's launch didn't take effect), so the script found no Search tab; cancelled, nothing kept |
  | 214108 | 1937 | Refused, $0.054: the year was below the fold on the final screen |
  | 214233 | 1937 | Refused, $0.052: on screen, but the words before it hold digits ("May 27"), and the compiler won't anchor a read on them (right: that anchor is one article's wording) |
  | 214856 | May 27, 1937 | Refused, $0.053: the scroll went past the sentence |
  | 214959, 215054, 215222, 215344 | — | Script couldn't find the sentence: the app reopens an article where you last left it (History, from my exploration), so scrolling down never met it; cancelled, nothing kept |
  | 215540 | May 27, 1937 | Compiled, $0.051: up to the top, then down until the sentence shows. The read is anchored on that sentence's own words ("…The bridge opened to the public on"), the same flaw as the agent's routine. Verification replay failed at step 1 |

  The article's "Quick facts" table has an Opened row in every bridge's article, a shape the compiler reads well (the
  value after its label). But its expand control is web-page text that isn't marked clickable. The recorder logs that
  tap as a coordinate tap, and routines drop those.
- **Wikipedia's start is unsteady under strict replay.** A fresh launch sometimes reopens the last article, and the first
  tap right after launch can land on the wrong tab while the bottom bar lays out. Once it hit Activity, which opened its
  intro screen; I left that with Back. In all: 3 of 6 strict runs passed (one batch of 3), and 3 failed at step 1
  (teach's own verification replay and both Brooklyn runs). Brooklyn never reached the read, which would have failed on
  the anchored words anyway.

## Findings for teach mode (not changed here)

1. Teach start swallows a failed launch. The phone stayed where it was twice, probably because my separate screen-reading
   processes had reset the phone's UI connection (in normal use only the API drives the phone). A person would just
   navigate from there.
2. A failed compile's cost isn't added to the session (`cost_usd` 0.0 while Wonder cost about $0.05).
3. A tap on web-page text (not marked clickable) can't become a routine step: map it to that text element, as an agent
   taps it by number.

## Files

`calculator/` and `wikipedia/`: `teach.json` (the session as the API reported it, with its verification replay),
`demonstration/` (the taught trace: `run.json`, `steps.jsonl.gz`), `routine.yaml` (as compiled), `replays.json`,
`new_input*.json`. The Calculator routine was saved only in the test copy's library; it is not in main's
`data/routines`.

Left on envoy-real: Calculator's history (two results); Wikipedia's reading history (Golden Gate Bridge, Brooklyn
Bridge) and its Activity intro, unanswered. Nothing was signed in to, saved or approved. envoy-real was stopped and
released at 22:02.
