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
