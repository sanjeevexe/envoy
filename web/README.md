# web

Envoy's web app (Phase 4): Next.js, built as a static export that the API serves (`backend/api/app.py` serves `web/out`), so the app, its API and the live view share one origin and the session cookie.

```bash
npm install && npm run build      # then restart the API; telemetry is off in the scripts
```

**Look (Sage).** Every color, type size, corner and shadow is a token in `app/globals.css` (with dark values under `prefers-color-scheme: dark`); Tailwind's own palette and type scale are switched off. Fraunces is Envoy's voice (the greeting, the briefing, its replies, sheet titles) and Manrope everything else, both self-hosted (Fontsource). Icons are Phosphor. Shared pieces are in `components/ui.tsx` and `components/Sheet.tsx`; the avatar, its seven moods and the mark in `components/Avatar.tsx`, with the mood picked from real state in `lib/mood.ts`. The app icons are rendered from `public/icons/mark.svg` by `node scripts/make_icons.mjs`.

**Places.** On a phone: Home, Activity, Phone, Memory and Routines as tabs, with Settings from the header. On a wider screen: a sidebar with the same places and the live phone on the right.
- **Home** (`components/Home.tsx`): the greeting and a briefing from `GET /api/briefing` (read only, no model call), what needs your OK, today's changes and finished tasks, what's next, your routines as suggestions, and the composer. Typing or speaking moves into the conversation (`components/Chat.tsx`).
- **Activity** (`components/Activity.tsx`, `components/Tasks.tsx`): approvals as cards, phone asks, then every task; a task shows its steps as they stream, where Envoy remembered things from, and what it cost.
- **Approvals** (`components/Approvals.tsx`): one sheet, in the app and on `/approve/?id=…` (the page approval links and notifications open).
- **Phone** (`components/LivePhone.tsx`): the live screen, Take over and Hand back, touch and the iPhone keyboard (streamed only while it's open on a phone).
- **Memory** (`components/MemoryGraph.tsx`), **Routines** (`components/Routines.tsx`, `RoutineDetail.tsx`, `Triggers.tsx`, `AppNotes.tsx`), **Settings** (`components/Settings.tsx`: approvals, phones, and devices in `Companion.tsx`).

**Mock mode.** `?mock=1` (or `NEXT_PUBLIC_ENVOY_MOCK=1`) answers the API and the event stream from fixtures in the page (`lib/mock.ts`, loaded only then): a task streaming steps, a payment waiting for approval, a phone ask, a filled memory, routines and triggers, two devices. `?mock=quiet` (a watcher rerunning, nothing waiting), `idle`, `offline` and `pair` show the other states; `?mock=0` turns it off. The live phone shows a still frame and opens no socket. Use it with `npm run dev` to design and check screens without a Mac, a phone or a model, and to take clean screenshots.

Phase 5 (the iPhone companion): the same app added to the iPhone's Home Screen (`public/manifest.webmanifest`, `public/sw.js` for pushes and notification taps). Unpaired devices see the pairing screen (`components/Pair.tsx`); Settings › Devices pairs devices, turns on notifications, sets photo permissions and makes the Shortcut's token. The composer has dictation into the message box (`lib/voice.ts`, `public/voice-worklet.js`) and a photo picker (`lib/device.ts`).
