# Connector application drafts (you submit; nothing here has been sent)

Two drafts:
1. A submission to the **Muse Connector Platform** (listed connector, reviewed).
2. A request to join the **Meta AI Connectors** developer preview (waitlist form).

Fields in [brackets] are yours to fill in. The field lists come from the public pages as read on Oct 26, 2026 (platform.muse.ai/docs and dev.meta.ai/products/connectors). The forms themselves may ask for more.

## Before you submit: two cautions

- **The Muse Connector Platform review expects an organization.** It asks for business verification, authority to submit, brand assets, a privacy policy and product terms, support and security contacts, a data-processing questionnaire, and a test account that stays available throughout review. As a solo hackathon project, Envoy has no company website or privacy policy yet. Submitting is still worth it on day one, as the design doc's route 3 says, but treat a rejection or "incomplete" as likely. If the form insists on a company, say so plainly rather than inventing one.
- **Meta AI Connectors wants a REST API ("live or in active development").** Envoy's REST fallback (OpenAPI) fits this. Pick "in active development (launching within 60 days)".

---

## 1. Muse Connector Platform submission

### Connector overview

**Name:** Envoy

**One-line description:** Envoy lets Muse act inside the user's Android phone apps and answer from what those apps show, with every irreversible step approved by the user.

**Intended users:** People who want their assistant to finish tasks that only exist inside phone apps (airline check-in, order status, loyalty points, delivery tracking) and to answer questions about their own bookings and orders.

**Supported tasks:**
- Answer questions from the user's own app data with sources, for example "what's my gate?". Answers come from a memory of facts Envoy has seen on app screens, in confirmation emails and in shared screenshots. Each fact records where and when it was seen.
- Run a task inside a phone app, such as "check me in for my flight" or "track my order".
  - Envoy operates an Android phone (a cloud emulator, or the user's own Android phone) the way a person would.
  - It compiles successful runs into reusable routines, so repeat tasks are fast and need no model calls.
- Run a routine the user already has, with inputs filled from memory.

**How it improves on browser use:** Many services have no full website, or keep the useful state (boarding passes, gate changes, app-only deals, delivery status) only in their mobile app. Envoy reaches the app itself. It also answers across apps that never share data, for example "cheapest delivery for this order".

**Account, plan or regional limits:**
- Each user signs in to their own apps themselves, through Envoy's live view. Envoy never sees or stores passwords.
- Apps that block emulators run on the user's own Android phone instead.
- Finance, health, messaging, password-manager and government apps are blocked by default.

### Tools (MCP, Streamable HTTP; REST with OpenAPI also available)

| Tool | Inputs | Output | Read/Write | Sensitive | Side effects |
| --- | --- | --- | --- | --- | --- |
| `memory_search` | `query` | Matching facts, each with source and time | Read | No | None |
| `memory_get` | `entity_id` | One entity, its facts and links | Read | No | None |
| `get_task` | `task_id` | Status, steps so far, pending approvals with an approval link | Read | No | None |
| `list_routines` | none | The user's learned routines and their inputs | Read | No | None |
| `memory_note` | `text`, `links?` | The new note's ID | Write | No | Adds a note to the user's memory, recorded with the assistant as its author |
| `run_task` | `goal`, `apps?`, `deadline?` | Task ID, status, approval link if needed | Write | **Yes** | Operates the user's phone apps. Irreversible steps (pay, order, submit, send, confirm, cancel, delete) pause for the user's approval |
| `run_routine` | `name`, `inputs` | Task ID, status, approval link if needed | Write | **Yes** | Same as `run_task` |

**Approval is deliberately not a tool.**
- No AI client, Muse included, can approve an irreversible step.
- Envoy's policy engine classifies every action before it runs, using rules, screen context and a model risk label. Any irreversible action waits for the user.
- The user approves only on Envoy's own approval page or through its iPhone notification. The page is bound to the exact screen shown, so a change in price or content asks again.
- Approvals are never automatic, and timeouts pause the task rather than approve it.

**Status handling:**
- `run_task` returns immediately with a task ID.
- `get_task` reports `queued`, `running`, `waiting_for_approval` (with `approve_url`), `waiting_for_user` (sign-in hand-off), `done` (with result) or `failed` (with reason).

**Errors and limits:**
- 401 for a missing or wrong token.
- 429 with `Retry-After` for rate limits; [your chosen limit, e.g. 30 tasks per hour per user].
- Tasks have step and cost limits and stop with a reason when they hit them.

### Data processing questionnaire (draft answers)

- **What data is accessed, and why:**
  - Text and screenshots of the user's phone app screens while a task runs, to operate the app.
  - Facts extracted from those screens, from confirmation emails (Gmail, read-only, if the user connects it) and from screenshots the user shares, to answer questions and fill task inputs.
- **What is never accessed:** passwords (sign-in is done by the user, with the agent paused and nothing logged), payment card numbers (redacted before storage), and apps in blocked categories.
- **How it is protected:**
  - Redaction runs before anything is stored.
  - Data lives in one encrypted database per user.
  - API keys live server-side only.
  - Every action goes to an audit log.
- **Who receives it:**
  - The user.
  - Meta's Model API, which processes screens at standard tier, so the content is not used for training.
  - The AI assistant that called a tool, which gets only that tool's result.
- **Retention:**
  - Full screenshots and raw screen dumps are deleted after 7 days.
  - Redacted screen text is kept while a remembered fact cites it.
  - The user can delete any fact or source, and deleting a source deletes the facts that only it supports.
- **Deletion:** per fact or source in the memory graph, or the whole account on request.

### Integration credentials

- **Endpoint:** [public HTTPS URL]/mcp (Streamable HTTP, MCP 2026-07-28, also answers 2025-11-25). REST: [URL]/openapi.json.
- **Auth:** bearer token per user (`Authorization: Bearer <token>`), revocable. OAuth 2.1 can be added if the platform requires it.
- **Credentials:** [test token, sent through the platform's secure credential channel, not in this document]. Label it as test.

### Test account

- A dedicated Envoy test user, pre-loaded with a demo trip:
  - SkyLark Air test app, flight SL 482, ATL to ORD.
  - Confirmation code KX7Q2M.
- It runs against Envoy's own test airline app, so check-in can be tested end to end without touching a real airline.
- Transactions: Envoy does not take payments. Irreversible steps always stop at the approval page.

### Contacts and terms (yours to fill)

- Developer and maintainer: [your name], [email]
- Support contact and security contact: [email]
- Privacy policy and product terms: [URL, to be written]
- Brand assets: [Envoy logo]

---

## 2. Meta AI Connectors developer preview (waitlist form)

| Field | Draft answer |
| --- | --- |
| First / last name | [ ] |
| Company name | Envoy (independent project, Meta Global AI Developer Hackathon 2026) |
| Company website | [GitHub or project URL] |
| Work email | [ ] |
| Role | Backend/API Developer |
| Team size | 1 |
| Industry | Consumer software / productivity |
| API status | In active development (launching within 60 days) |
| Protocol | REST API (OpenAPI/Swagger); also an MCP server |
| API docs link | [public URL]/openapi.json |
| AI platforms integrated with | Meta Model API (Muse Spark 1.3, Muse Wonder); MCP clients |
| Meta surfaces wanted | Meta AI app and web; AI glasses |
| How soon you could start | Immediately |

**What does your service do?**
> Envoy gives Meta AI a phone layer. It operates Android apps on the user's behalf on a cloud phone or their own Android phone, and remembers what those apps show: bookings, orders, gates, points. Meta AI can then answer "what's my gate?" from the airline app and finish "check me in for my flight" inside the app. Successful runs become reusable routines, so repeat tasks are fast and cheap. Every irreversible step (pay, order, submit, confirm) waits for the user's own approval on Envoy's approval screen; the assistant is never given an approve tool.

**Why are you interested?**
> Envoy is built on Muse Spark and Muse Wonder for the Meta Global AI Developer Hackathon (theme: Push the Frontier). Phone apps are where much of a person's current state lives, and Meta AI on glasses is exactly where you want "check me in" or "where's my order" without opening an app. We'd like to test Envoy as a connector during the preview and give feedback on how approvals and account linking should work for agents that take actions.
