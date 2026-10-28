# Feedback on Meta products (running log for the submission)

The submission form asks for "feedback from your experience using Meta products". Add an entry whenever something surprises us, good or bad, with the date and evidence, so the final answer is specific rather than written from memory on Nov 4.

## Muse app: custom MCP connector (Oct 26–27, Phase 0 test B2)

**What worked well**
- Custom connectors work on the free tier. Muse built and verified an MCP client for our server, then called our tools with the user's words as arguments.
- **The token never stays in chat.** Muse sent the bearer token to a "Secure credentials store" card instead of using the copy pasted into the conversation.
- **It treated our approval link correctly.** It said the check-in was "waiting for your approval, not mine", repeating our tool description's rule that it cannot approve.
- **It reasons about provenance.** It read a `note` field in our tool result (marking data as from a test stub) and declined to rely on it. That's exactly what we want from an assistant reading sourced facts.
- The client identifies itself clearly (`clientInfo.name = "muse-custom-connector"`), which makes server logs easy to read.

**What could be better**
- **Protocol version:** Muse's connector speaks MCP 2025-11-25, not the current 2026-07-28 spec. A server that only supported the newest version would fail.
- **Setup needs several "Allow once" prompts.** We got three (verify the connection, list tools, check the server) before setup finished. One prompt covering the setup steps would be smoother.
- **Asking in chat produces link previews, not a connection.** Pasting the URL and token first made the app open the URL in its in-app browser and fetch a link preview, both unauthenticated. A clear "add connector" entry point in settings would avoid this.
- **Link previews fetch URLs from tool results automatically.** The app's preview crawler (`facebookexternalhit`) fetched our approval URL before the user tapped it. Developers must keep such URLs free of side effects; the connector docs should say so.
- **Egress is undocumented.** Each request came from a different IPv6 address in `2606:54c1:1::/48` and opened a new MCP session. That's fine with bearer auth, but documenting egress ranges and session behavior would help developers.

## Meta Model API docs (Oct 26, read while preparing the API test; no API calls yet)

**What worked well**
- The OpenAI-compatible Responses API, with clear usage fields (cached tokens, reasoning tokens) and published per-model prices and rate limits.
- Structured output is guaranteed by constrained decoding, and the strict JSON-schema subset is documented precisely.

**What could be better**
- The structured-output guide has no Responses API example. `text.format` appears only in the schema reference.
- Prompt-caching semantics are easy to misread: caching is automatic, `prompt_cache_key` is only a routing hint, and 24-hour retention is a separate `prompt_cache_retention` parameter. The minimum cacheable prompt length isn't documented.
- No maximum output tokens are documented for any model.
- SAM 3.1 returns special-token text rather than JSON, so a parser library is needed. A JSON option would make it easier to use.
- The docs use `MODEL_API_KEY`, which the OpenAI SDK doesn't read by default, so it must be passed explicitly.

## Meta Model API in use (Oct 27, Phase 0 gate: 37 calls, $0.06)

**What worked well**
- **Structured output just works.** Every step returned schema-valid action JSON on the first try, and the first live call picked the right element and ran on the phone.
- **Speed and cost:** Muse Spark 1.3 at `low` effort took a median 0.87 s per agent step, with only about 88 reasoning tokens, so a step costs about $0.001. That's cheap enough to run an agent loop freely.
- **Automatic prompt caching** hit on 19/20 repeated calls with no configuration, and it caches screenshots too.
- **Visual grounding** on tall 1080×2400 phone screenshots was precise: a 137×126 px toggle was located within 1 px.
- SAM 3.1 segments UI parts well when given specific noun phrases ("toggle switch", "search bar").

**Agent loop in Phase 1 (Oct 27, 480 calls, $0.91)**
- **What worked well:** Muse Spark 1.3 at `low` drove a phone agent through 69 of 69 evaluation runs on our test app, including three changed layouts. Steps took a median of 850 ms and cost $0.0015, and the cache served 73% of input tokens.
- **A preamble before structured JSON.** In 18 of 480 calls (3.75%) with `text.format` json_schema, the response came as two text parts: a sentence of commentary, then the schema JSON, so `output_text` is not valid JSON. The last message part was always valid. Either constrain all output text to the schema, or document that only the last part is constrained.

**What could be better**
- **`minimal` effort was no faster than `low`** in our test (median 0.99 s against 0.87 s) and was less accurate on a simple element choice (11/15 against 10/10). Guidance on when `minimal` helps would be useful.
- **A full-resolution phone screenshot costs about 3,200 input tokens**, about twice the docs' "~1,300–1,500 for ~1280 px". A documented token formula per resolution would help budgeting.
- SAM 3.1 returns nothing for generic UI phrases such as "button" or "text". Examples of good prompts for screenshots would help.
- **Billing:** our own account's billing was not working, so the $50 balance and the hackathon's $150 credits couldn't be used, and we fell back to a teammate's key. Faster billing support during a 10-day hackathon would matter.

## Muse Wonder and Muse Spark in Phase 2: compiling app routines (Oct 27)

**What worked well**
- **Muse Wonder accepts `json_schema` structured output** on the Responses API, so the routine compiler gets a typed answer (inputs, step names, outputs, booking data) in one call. At `medium` effort a compile took a median 14 s, about 2,300 output tokens (1,700 reasoning) and about $0.05.
- **Wonder's generalization is good where it matters.** Given a cleaned agent trace, it named inputs sensibly (`trip_city`, `desired_seat`, `known_traveler_number` with `from_memory`), wrote generic step intents with `{{slots}}`, and picked the right fixed text inside merged labels ("Next trip" out of "Next trip · Chicago · Fri, Oct 30 …").
- **Spark at `medium` repaired a broken routine step in one call** (7.2 s, $0.006): on SkyLark's extra-confirmation layout it read the step's intent and after-checks and tapped "Looks good"; the repair was saved as a patch and later runs needed no model.
- **Spark at `low` matches requests to routines well**: 12/12 on our matching set, including inputs filled from notes and three requests that no routine covers (it declined "Cancel my Denver trip" rather than matching check-in).

**What could be better**
- **Wonder's answers vary run to run, sometimes structurally.** On a second compile of the same six traces, two answers were wrong in ways that broke replay: one numbered the steps from 0 although the prompt listed them from 1, and one returned field names (`"flight_number"`, `"route"`) in a field described as literal values. Both passed the schema. Envoy now aligns step numbers and ignores identifier-like values in code, and verification by replay caught both before they reached the library. A `strict` schema can't express "these are values, not names"; examples in the docs of prompting Wonder for extraction-style answers would help.
- **Wonder at `medium` reasons a lot for small jobs**: a one-line naming question used 1,210 reasoning tokens (11 s, $0.025). Guidance on when `low` is enough for Wonder would help budgeting.
- **Contributor-tier latency**: one `muse-spark-1.3-contributor` call took 5.9 s for a 400-token reply, against about 0.9 s for a typical standard-tier step. We kept all timed comparisons on the standard tier so the Contributor tier wouldn't distort them. Documented latency expectations for the Contributor tier would help.

## Muse Spark in Phase 3: extracting memory from emails and screens (Oct 27)

**What worked well**
- **Extraction with structured output is precise.** On 28 test confirmation emails (18 bookings), Muse Spark at `low` read the plain-text ones with **131 of 133 attributes right and none wrong**; every value it returned was found verbatim in the email, so our "the value must appear in the source" check dropped nothing. About $0.006 per email.
- **It follows "a promotion is not a booking".** Fare promotions naming a booked city and listing flight numbers produced no trip or flight in every run.
- **One cheap call settles thin matches.** When keys don't decide whether two descriptions are one trip, a `low` call with both descriptions answers; with the rule "different dates mean different trips" in the instructions, two trips to Denver were never merged.

**What could be better**
- **Values are copied but not normalized.** The same flight arrives as "SL 1190" and "SL1190", a departure as "6:10 AM" and an ISO time, an airport as "Atlanta (ATL)" and "ATL". That's what we asked for (verbatim values are checkable), so Envoy normalizes keys in code; a documented way to get both a verbatim span and a normalized value in one structured answer would help.
- **Attribute placement varies.** Plain emails sometimes put the trip's date only on the flight, never on the trip, so "the next upcoming trip" had to fall back to the trip's flight in code.

## Muse Spark as the agent on 18 real-app workflows (Oct 27, real-app test set)

**What worked well**
- 13 of 18 first runs gave a right answer on apps it had never seen (Settings, Gmail, Calendar, Contacts, Maps, Play Store, YouTube Music, Chrome, five shopping and food apps), at `low` effort, typically in 3 to 7 steps.
- It handles one-time prompts sensibly (declines notification and permission prompts, continues without an account when told to) and hands off at a bot check instead of trying it.

**What could be better**
- **Placeholder actions.** In 12 of 18 runs it chose a coordinate tap with made-up coordinates ("tap_point" at 0,0 or 500,500, with the stated reason "Placeholder") 52 times. That happened even though the screen's elements were listed and the instructions say coordinate taps are only for screens without elements. Each costs a call and a step, and twice the agent lost the app afterwards. It looks like the model fills an action when it is unsure instead of choosing `look` or `scroll`. We will stop offering that action when elements are listed. A model that never emits a self-described placeholder would be better.

## Muse Spark as Envoy's chat assistant (Oct 27, Phase 4)

**What worked well**
- As a router (memory question, task, or reply) with a three-field structured output, it made the right call on every message we sent ("What's my gate?" → memory; "Check me in for my flight" → task), at `low` effort and about a second.
- Answers from memory kept the source and age we asked for ("Gate B12, from the SkyLark app just now").

**What could be better**
- Nothing new beyond the placeholder actions noted above; the chat path was only tried on a handful of messages.


## Muse Voice Transcribe (Oct 27, Phase 5: dictation on the web app and iPhone)

**What worked well**
- **Fast and exact on short commands.** "What's my gate for my Chicago flight?" came back word for word, and the final transcript arrived **90 to 93 ms** after we sent `endStream` (4 runs). Cumulative partials arrived while the audio streamed, so the app can show text as you talk.
- **Just as fast on real devices.** Eight dictations on the user's Mac and iPhone got their final text 74 to 296 ms after `endStream`.
- **Cheap enough to leave on.** A 2.6 s turn cost $0.0001 ($0.18 per audio hour, billed per whole second).
- **The protocol is small and easy to relay.** A handshake JSON with the key inside it (so a server can hold the key and relay a browser's audio), binary PCM, `endStream`, a final `transcript`. The keyword list (`keywords`) is a nice touch for app names like "SkyLark".

**What could be better**
- **Connecting takes a while:** 0.25 to 1.45 s from opening the socket to the `{"sessionId"}` acknowledgement. We buffer audio during the handshake so the user doesn't wait, but each dictation opens a new session in push-to-talk mode (the docs say `endStream` ends the session), so a way to keep one session open across turns in push-to-talk mode would remove it.
- **"Ingress audio slower than real-time" closes the stream.** When a browser's microphone delivered nothing (the iPhone's mic is blocked during iPhone Mirroring), the server closed the session. The docs do say to keep sending silence on a live source; we now pad silence in the relay. A grace period, or an error that names the fix, would help.
- **The docs disagree with themselves on the handshake.** The speech-to-text page says the handshake has nine fields; the schema lists eight. The realtime reference shows four. One complete table on the realtime page would save a round of reading.
- **No browser example.** Browsers capture 44.1 or 48 kHz float audio; an example AudioWorklet that produces 24 kHz 16-bit PCM (or accepting 48 kHz) would help web developers.

## Muse Spark vision: screenshots and photos into memory (Oct 27, Phase 5)

**What worked well**
- **Accurate on real UI screenshots.** On 7 SkyLark booking screens (trip details, boarding passes, the home card), Spark at `low` with structured output returned **73 of 73 values right and none wrong**; it copied codes, times and flight numbers exactly as drawn. It correctly stored nothing from a flight-status search result, which isn't the user's booking.
- **It reads values that OCR misses or misreads.** Spark read the confirmation code 3J8N0D where Apple's on-device OCR missed it once and read "3J8NOD" another time.
- About **$0.007 and 4.8 s** per phone screenshot sent at a 1,600 px long side (about 2,500 input tokens).

**What could be better**
- **Latency:** 4 to 8 s per screenshot at `low` effort, and one call in 9 timed out at 30 s and succeeded on retry. For a share-sheet action that waits for an answer, a faster vision path, or a documented latency expectation, would help.
- **No per-value location.** For screens we pass element numbers as evidence; for images there is no way to ask where a value was seen (a box), which would let us check values against the image region instead of OCR text. Spark's grounding can return boxes, but not inside an extraction answer.

## Muse app with Envoy's real MCP server (Oct 27, Phase 5: route 2 again)

**What worked well**
- **Setup from one chat message.** "Add a custom MCP connector called Envoy at <URL>" brought up the "Add custom connector" card with the URL already filled in; only the key was typed, into the secure store. Muse then listed all seven of our tools and summarized them accurately.
- **It never tried to approve.** After `run_task`, Muse checked the task twice, said the check-in was "waiting for your approval on the final step", showed our approval link as a card, and said "I can't approve that for you". After the user approved on our page, "Is the check-in done?" made it call `get_task` and report the seat, gate and boarding time correctly.
- **Chat-time tool calls didn't prompt**; only setup did.

**What could be better**
- **Setup still needs three "Allow once" prompts** (verify, list tools, verify again), the same as in Phase 0.
- **The pasted URL is still fetched as a link** by the in-app browser and `facebookexternalhit`, unauthenticated, even when the message asks to add a connector.
- **No follow-up on long tasks.** Muse checked the task status twice within 5 s, then stopped; it reported completion only when asked. A way for a connector to tell Muse that a task finished (or for Muse to poll a running task for a while) would let it close the loop itself. We rely on our own push notification for that.
- **A custom connector needs a public URL**, and a quick tunnel's address changes every run, so the connector is re-added each time. A way to reach a server on the user's private network (or to change a connector's URL instead of adding it again) would help.

## SAM 3.1 and Muse Spark grounding on phone screens (Oct 27, Phase 6: screens with no accessibility tree)

Measured on 52 targets (seats on a seat map drawn on a canvas, at two screen sizes, and buttons, fields and icons on real-app screenshots whose accessibility tree gave the truth), then again on a fresh 52.

**What worked well**
- **SAM 3.1's boxes are pixel-exact.** On the seat map, the box Muse Spark picked from SAM's candidates was 1 px from the seat's centre (median), and 15 of 16 picks were right.
- **Shown numbered boxes, Muse Spark never picked a wrong one.** In 104 targets it either picked the right box or said none of them was the target. That makes SAM + a pick a safe first pass with a fallback.
- **Grounding is strong on labelled UI**: 35 of 36 real-app targets (median error 10 px), about 2 s and $0.003 each.
- **Together they found all 104** (SAM first, grounding when SAM's candidates don't include the target), against 37% for the step model reading coordinates off its own 540 px screenshot.

**What could be better**
- **SAM 3.1 needs shape words, not UI words.** "seat", "button" and "text" return nothing on a phone screenshot; "square button" returns every seat (84 boxes) and "icon" returns icons. Text buttons ("OKAY", "Compose", a search field) were never among the candidates. A UI-element mode, or documented phrases for UI screenshots, would make it usable alone.
- **Grounding drifts on dense, repeated grids.** On a 720×1280 screen it landed one seat row off 3 times in 16 (46 to 71 px), where SAM's boxes were exact.
- **SAM's output is special-token text** (`<|box;x1=…;w=…;h=…;c=…|>` plus base85 masks, about 38 KB for one image) rather than JSON. A structured response, or masks only on request, would save parsing and bandwidth.
- **The pick slows with many candidates**: choosing among 84 numbered boxes took 15 s once (about 3 s typically). A way to ask SAM for the top N candidates would help.
