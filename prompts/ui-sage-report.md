# The Sage redesign: report

Branch `claude/great-blackwell-3e6ce6` (the brief's `ui-sage`), rebased on main `34102f9` (wonder-appnotes included). Backend tests: 343 passed at the merge (`uv run --project backend pytest backend/tests -q`: main's 338 plus 5 for the briefing); 344 with the MCP icon test. Web build (`npm run build` in the worktree): passes, static export of `/`, `/approve`.

The app now looks like the approved Sage canvas: cream and sage tokens, Fraunces for Envoy's voice and Manrope for the rest, Phosphor icons, no emoji, and the avatar on every screen showing what Envoy is doing. Everything in the brief is built, dark mode included, except the ring on the approval target (why below).

## What changed

| Area | What | Where |
| --- | --- | --- |
| Mock mode | `?mock=1` (or `NEXT_PUBLIC_ENVOY_MOCK=1`) answers the API and the event stream in the page: a task streaming steps, a payment waiting for approval with its screenshot, a phone ask, a filled memory graph, routines with versions and repairs, triggers, app notes, two devices. `?mock=quiet` (a watcher rerunning: working, thinking, done), `idle`, `offline`, `pair`; `?mock=0` ends it. Approving, declining, stopping, chatting and dictating play out as events. The live phone shows a still frame and opens no socket. The fixtures load only in mock mode, in their own chunk. | `web/lib/mock.ts`, `web/lib/api.ts` |
| Tokens and type | Every color, size, corner and shadow is a token (`globals.css`); Tailwind's own palette and type scale are switched off, so a raw `stone-500` or `text-sm` can't come back. Fraunces and Manrope are self-hosted (Fontsource), so the static build and the iPhone app work without Google. 4px grid, 20px cards, 16px blocks, pills, 28px sheet corners, 44px targets. | `web/app/globals.css`, `web/app/layout.tsx` |
| Shared pieces | Button, icon button, card, chip, list row, section, segmented control, the step marks, the sheet (bottom sheet on a phone, dialog wider; Escape, scrim and focus handled), the composer. No component library. | `web/components/ui.tsx`, `Sheet.tsx`, `Chat.tsx` |
| Navigation | Phone: Home, Activity, Phone, Memory, Routines, with Settings from the header. Activity is tasks plus approvals (cards on top); Routines holds triggers and app notes; Devices moved into Settings. Desktop: a sidebar with the mark, the content at a readable width, the live phone on the right (the Phone place shows it large instead). `?task=`, `?phone=`, notification links (`route()`), the service worker and `/approve/?id=` all still work. | `web/app/page.tsx`, `Activity.tsx` |
| Avatar | `<Avatar mood size />` with the canvas's paths and keyframes, cheeks included, in all seven moods. The page picks the mood from real state in the brief's order (offline after a 2.5 s grace; needs; listening; working while steps arrive within 1.5 s; thinking; done for 3 s; idle). It is large on Home and Pair, 44px beside replies, 52px on sheets, small in the header, sidebar and toasts. | `web/components/Avatar.tsx`, `web/lib/mood.ts` |
| The mark | Every icon (Home Screen, maskable with the face in the safe zone, apple-touch opaque, favicon PNG and SVG, the one-color notification badge with the eyes cut out) is rendered from one SVG, `web/public/icons/mark.svg`, by `node scripts/make_icons.mjs` (sharp), which replaces `make_icons.py`. Manifest and theme color are cream (`#F6F3EC`; deep green in dark mode). | `web/public/icons/`, `scripts/make_icons.mjs` |
| Home and the briefing | The greeting: avatar, "Good evening, Maya", the briefing in Fraunces, needs-your-OK cards (Review opens the sheet; a phone ask answers in place; a task waiting on you offers Take over), Today (changes with the app and time, finished tasks, routine runs), Coming up, your routines as suggestion chips, the composer with the mic. Typing or speaking moves into the conversation. | `web/components/Home.tsx`, `Chat.tsx` |
| `GET /api/briefing` | Read only, deterministic, no model call. Needs (pending approvals, phone asks, tasks in needs_you or waiting_approval without an approval), today (change alerts from the last day, one per fact; tasks and routine runs finished since midnight, not cross-app parts), next (enabled triggers due within a day; not watchers, whose reruns aren't news), suggestions (routines by number of runs, then last run), and up to three sentences in Envoy's voice. The name only when memory holds exactly one person with a real name (`Maya`; the real profile's `envoy` email name doesn't count). 5 tests. | `backend/api/briefing.py`, a 4-line route in `app.py`, `backend/tests/test_briefing.py` |
| Task view | Header with back, title, the mood line ("Working on your Pixel 5") and Stop; your request as a bubble; Envoy's answer in Fraunces (a `k: v; …` result as labeled pairs) with "Remembered from DoorDash · Oct 21" chips from the steps' `sources`; the timeline (done checks, a spinner on a step still running or a "Looking at the screen" row while the task runs, a lock on what waits for your OK, each step opening to its screenshot, reason, risk and repair rung); routine version, model calls, cost and time; Watch live (the Phone tab on a phone, the side panel on desktop). | `web/components/Tasks.tsx` |
| Approvals | One sheet in the app and on `/approve`: the avatar asking, the title in words ("Tap “Confirm check-in” in SkyLark"; the routine on its own line), What Envoy will tap with the approval's screenshot, the reasons as labeled rows, the brick "can't be undone" marker, Decline and "Approve and pay" or the action's own words ("Confirm check-in"). The nonce flow is unchanged and opening the sheet or the page decides nothing. | `web/components/Approvals.tsx`, `web/app/approve/page.tsx` |
| Every other screen | Memory (cytoscape nodes and edges in the palette, Manrope labels, colors read from the tokens; the facts panel with sources, edit and delete), routines and their detail (stat cards, segmented panels, the version timeline), triggers (controls under the text on a phone), app notes, settings (approvals, phones, devices), Pair (the avatar and "Hi, I'm Envoy"), the phone ask, the toast, and the chrome around the live phone (its streaming code untouched). | `web/components/*.tsx` |
| Motion | CSS only, 150–550 ms: Home's staggered rise, steps rising in as they stream, the sheet sliding up (a dialog wider), a crossfade between tabs, the avatar's moods, the toast's spring. All off under `prefers-reduced-motion`. | `globals.css` |
| Dark mode | The same tokens mapped to a deep green-black under `prefers-color-scheme: dark` (text keeps 4.5:1 or more; sage and apricot keep their fills); text on ink fills reads an `on-ink` token. | `globals.css` |
| Credits | Phosphor (MIT), Fraunces and Manrope (OFL-1.1, via Fontsource, MIT), sharp (Apache-2.0). | `THIRD_PARTY.md` |

## Before and after

Phone screens at 390×844 in mock mode (the same fixtures before and after: "before" is the old UI at the mock-mode commit). Desktop screens are at 1440×900, captured at the browser pane's size (800×500).

| Screen | Before | After |
| --- | --- | --- |
| Home | ![](ui-sage-report/before-home.jpg) | ![](ui-sage-report/after-home.jpg) |
| Home, a quiet day (a watcher thinking) | | ![](ui-sage-report/after-home-quiet.jpg) |
| Listening, then the conversation | | ![](ui-sage-report/after-listening.jpg) ![](ui-sage-report/after-conversation.jpg) |
| A task waiting for approval | ![](ui-sage-report/before-task.jpg) | ![](ui-sage-report/after-task.jpg) |
| The approval | ![](ui-sage-report/before-approvals.jpg) | ![](ui-sage-report/after-approval.jpg) |
| Activity (was Tasks) | ![](ui-sage-report/before-tasks.jpg) | ![](ui-sage-report/after-activity.jpg) |
| Phone | ![](ui-sage-report/before-phone.jpg) | ![](ui-sage-report/after-phone.jpg) |
| Memory | ![](ui-sage-report/before-memory.jpg) | ![](ui-sage-report/after-memory.jpg) |
| Routines | ![](ui-sage-report/before-routines.jpg) | ![](ui-sage-report/after-routines.jpg) |
| A routine | | ![](ui-sage-report/after-routine-detail.jpg) |
| App notes | | ![](ui-sage-report/after-app-notes.jpg) |
| Triggers | ![](ui-sage-report/before-triggers.jpg) | ![](ui-sage-report/after-triggers.jpg) |
| Settings | ![](ui-sage-report/before-settings.jpg) | ![](ui-sage-report/after-settings.jpg) |
| Pair | ![](ui-sage-report/before-pair.jpg) | ![](ui-sage-report/after-pair.jpg) |
| `/approve` | ![](ui-sage-report/before-approve-page.jpg) | ![](ui-sage-report/after-approve-page.jpg) |
| Offline | ![](ui-sage-report/before-offline.jpg) | ![](ui-sage-report/after-offline.jpg) |
| Dark mode | | ![](ui-sage-report/after-home-dark.jpg) |
| Desktop: Home | ![](ui-sage-report/before-desktop-home.jpg) | ![](ui-sage-report/after-desktop-home.jpg) |
| Desktop: task, approval, memory | | ![](ui-sage-report/after-desktop-task.jpg) ![](ui-sage-report/after-desktop-approval.jpg) ![](ui-sage-report/after-desktop-memory.jpg) |

**Real data** (my own API copy on :8701, demo profile, its own data directory and token, a backup of the task store and a copy of the demo memory): Home with Maya and two real memory changes, a real check-in task, a real pending approval with its real screenshot (added to my copy only, never decided), the real memory graph. These four were taken before two fixes the real data prompted: the approve button now reads "Confirm check-in" instead of wrapping "Approve: Confirm check-in", and trips and flights now differ in lightness.

![](ui-sage-report/after-real-home.jpg) ![](ui-sage-report/after-real-task.jpg) ![](ui-sage-report/after-real-approval.jpg) ![](ui-sage-report/after-real-memory.jpg)

## Which icon Muse reads

None of Envoy's icon files, as far as the logs show. Every one of the 1,087 requests that reached Envoy through the Muse tunnel (`logs/mcp.jsonl`) was to `/mcp`; nothing ever asked for `/favicon.ico`, `/icons/…` or `apple-touch-icon.png`, and the tunnel host answers nothing but `/mcp` anyway (`api/app.py`'s `dispatch` returns 421 for any other path there). The MCP server's `initialize` reply carries no icon either: `build_mcp` (`backend/mcp_server/server.py`) passes a name, title and description but not `icons` or `website_url`, which the SDK's `MCPServer` accepts. So the connector card showed whatever Muse uses by default. **Fixed after the merge** (with the coordinator's OK): `build_mcp` now sends Envoy's mark in `serverInfo.icons` as data URIs, the 192px PNG rendered from `mark.svg` and the SVG itself (`envoy_icons()`), and `test_muse_gets_envoys_icon_with_the_server_info` initializes through the tunnel as Muse does and decodes them. Whether Muse's card then draws it is for the next Muse session to see.

## Not done, or not checked

- **The ring on the approval target: not drawn.** `WebApprover.request` (`api/approvals.py`) gets an `ApprovalRequest` with the target's words (`target`) but no bounds or element index; the agent builds that request (`policy/approvals.py`, from `backend/agent/`). Finding the element by its label on the observed screen would be a guess, so per the brief the sheet shows the screenshot without a ring.
- **The task view's reply box and suggestion chips** ("Reply to Envoy", "Make it spicy") from `Task.dc.html`: not built, because no API takes a reply to a running task. Home's composer is the conversation.
- **The iPhone check** (Home Screen app, notifications, the new icon and badge on a real device): pending, after the merge, on the user's live app.
- **The live phone panel against a real device:** not opened outside mock mode (no device claimed); its streaming code is unchanged, only the chrome around it.
- **Reduced motion:** checked by the CSS rule (every animation and transition off), not by emulating the setting in a browser.
- **Intermediate commits** are logical steps but don't each build on their own (the navigation commit imports screens restyled later); the tip builds and passes.

## Notes

- The dev server's Tailwind loader caches `globals.css`: after a token change, restart `next dev`. The static build is unaffected.
- A preview against a real API needs `data/demo/memory.db` in the worktree (the API resolves profiles from its own checkout); I used a copy so as not to share the live API's file.
