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

**What could be better**
- **`minimal` effort was no faster than `low`** in our test (median 0.99 s against 0.87 s) and was less accurate on a simple element choice (11/15 against 10/10). Guidance on when `minimal` helps would be useful.
- **A full-resolution phone screenshot costs about 3,200 input tokens**, about twice the docs' "~1,300–1,500 for ~1280 px". A documented token formula per resolution would help budgeting.
- SAM 3.1 returns nothing for generic UI phrases such as "button" or "text". Examples of good prompts for screenshots would help.
- **Billing:** our own account's billing was not working, so the $50 balance and the hackathon's $150 credits couldn't be used, and we fell back to a teammate's key. Faster billing support during a 10-day hackathon would matter.
