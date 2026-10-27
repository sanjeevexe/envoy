# How agents deal with bot checks (research notes, Oct 27, 2026)

These notes come from web research done for this project. Every claim links its source. Three claims were checked against their sources by hand and are marked ✓. The rest come from the research pass, and some of those are from search excerpts or press reports, as noted.

Four approaches show up: **(a)** hand the step to the user, **(b)** run in the user's own browser, device or session, so risk scoring passes quietly, **(c)** identify as an agent (signed requests, verified bots), **(d)** evasion (stealth browsers, residential proxies, CAPTCHA-solving services). For (d) these notes only record that it exists. Envoy does not do it.

## What agents do today

| Agent | Approach | Notes |
| --- | --- | --- |
| Meta Muse | unclear | Meta's announcement describes a cloud "Muse Secure VM" and asks before sending email or paying, but says nothing about CAPTCHAs or whether Muse identifies itself ([Meta](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/)). A third-party analysis says it pauses for the user to take over ([Kodem](https://www.kodemsecurity.com/resources/meta-muse-ai-agent-security-model)); not confirmed by Meta. |
| xAI Grok Bot | (a) | ✓ "Passwords, two-factor codes, CAPTCHAs, and similar human-only steps use a computer takeover" ([FAQ](https://docs.x.ai/grok-bot/faq)). "GrokBot" also names a crawler; claims that it spoofs browser user-agents are unverified. |
| Hermes Agent (Nous) | (a)(b), (d) via backends | Can attach to the user's own Chrome, and its headed mode lets the user step in. Its cloud browser backends advertise CAPTCHA solving and proxies ([docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/browser)). |
| OpenClaw | (a)(b) | ✓ "Automated logins often trigger anti-bot defenses and can lock the account"; sandboxed sessions are flagged more. Users are told to sign in manually ([docs](https://docs.openclaw.ai/tools/browser-login)). Unofficial community skills wrap CAPTCHA solvers. |
| OpenAI (Operator, ChatGPT agent, Atlas) | (a)(b)(c) | Asks the user to take over for logins, payments and CAPTCHAs ([OpenAI](https://openai.com/index/introducing-operator/)). The ChatGPT agent signs its requests with Web Bot Auth ([help](https://help.openai.com/en/articles/11845367), from a search excerpt). |
| Anthropic (Claude in Chrome) | (a)(b) | Bypassing CAPTCHAs is prohibited, and it pauses for the user ([support](https://support.claude.com/en/articles/12902428-use-claude-in-chrome-safely)). |
| Google (Chrome auto browse) | (a), (c) experimental | Pauses for sign-in. Some "Google-Agent" fetches are signed with Web Bot Auth ([Google](https://developers.google.com/crawling/docs/crawlers-fetchers/web-bot-auth)). |
| Perplexity Comet | (b) | Runs as the user's own browser. Cloudflare accused Perplexity of undeclared "stealth" crawling and delisted it as a verified bot ([Cloudflare](https://blog.cloudflare.com/perplexity-is-using-stealth-undeclared-crawlers-to-evade-website-no-crawl-directives/)). Amazon sued over Comet; per the press, the injunction was later vacated ([GeekWire](https://www.geekwire.com/2026/judge-blocks-perplexitys-ai-bot-from-shopping-on-amazon-in-early-test-of-agentic-commerce/), [Sovereign](https://www.sovereignmagazine.com/article/ninth-circuit-perplexity-comet-amazon-cfaa-ruling)). |
| Browserbase-style infrastructure | (c), (d) | Sells sessions its bot-protection partners recognize, plus Web Bot Auth in beta ([docs](https://docs.browserbase.com/platform/identity/overview)); also offers stealth and CAPTCHA solving. |

## Agent identity

- **Web Bot Auth:** HTTP Message Signatures (RFC 9421), being standardized at the IETF. Cloudflare's "signed agents" category started with ChatGPT agent, Goose, Browserbase and Anchor, and agents apply through a form ([Cloudflare](https://blog.cloudflare.com/signed-agents/)). Visa's Trusted Agent Protocol and Mastercard Agent Pay build on it. HUMAN, Akamai and DataDome have agent-verification products. They cover web traffic; HUMAN's says it covers "web and mobile applications", from a search excerpt only.
- **Native mobile: no equivalent found.**
  - ✓ Play Integrity attests the device and app, not the agent. Emulators get no device verdict (only Google Play Games for PC emulators can pass). Its `appAccessRiskVerdict` tells apps when another app can view or control the screen, except for accessibility tools Google has reviewed ([Android](https://developer.android.com/google/play/integrity/verdicts)).
  - Android AppFunctions is gated to a few apps and system agents ([Android](https://developer.android.com/ai/appfunctions)).
  - ByteDance's SAEP lets apps allow or refuse its phone agent; 151 apps refused ([Yicai](https://www.yicaiglobal.com/news/wechat-taobao-honor-of-kings-among-151-apps-to-reject-doubao-phone-assistant)).
- **Envoy:** signing only helps with web requests Envoy makes itself. In native apps, Envoy drives the screen, not the app's own network calls, so being recognized needs the app (or its bot-defense vendor) to choose to recognize Envoy.

## Mobile infrastructure

- **Mobilerun** offers virtual cloud phones, linked personal phones and hosted physical phones ([docs](https://docs.mobilerun.ai/device-types)), and recommends locale-matched proxies. No public statement on Play Integrity or app bot checks was found.
- **HUMAN** says some of its detections block emulator-based solves ([docs](https://docs.humansecurity.com/docs/human-challenge-integration-testing-process)). That fits Target's check coming back on most fresh launches on our emulator.
- **On real phones, other signals still matter.**
  - Android now hides the ADB and developer-options settings from third-party apps ([Android](https://developer.android.com/reference/android/provider/Settings.Global)).
  - Some banks restrict access while accessibility services are on.
  - ByteDance's Doubao phone agent ran on real hardware and still triggered WeChat and Alipay risk controls ([36Kr](https://eu.36kr.com/en/p/3601001372828672)).

## For Envoy

- Visible challenges should be much rarer on the user's own phone with their own accounts than on an emulator, but not zero. No public data says how often they appear.
- Legitimate options:
  - a good hand-off (pause, notify, the user does only the blocked step, then resume)
  - the user's own device by default
  - Web Bot Auth for any web traffic of Envoy's own
  - AppFunctions and App Intents as they open up
  - partnering with apps or their bot-defense vendors, and honoring app opt-outs
- Not an option: presenting Envoy as an accessibility tool to avoid `appAccessRiskVerdict`. Envoy isn't one.
- **Unknown:**
  - whether uiautomator2 or adb control trips `appAccessRiskVerdict` on a real phone
  - how often real phones get challenged
  - Muse's own CAPTCHA behavior

The first two can be measured by running the real-app test set on a real phone.
