# muse-link: report

Session muse-link, Oct 29. Details and the user's Muse checklist: `docs/muse-link.md`.

## Branches

| Stage | Branch | Tip | State |
| --- | --- | --- | --- |
| 1: `push_file`, the outbox, MCP `send_to_phone` and `phone_updates`, `heads_up` | `claude/jolly-khayyam-b99b59` | `30a05d4` (on main `ce747cb`) | Sent as "branch ready". 389 backend tests, web build passes |
| 2: handoff offers, MCP `create_trigger`, the web panel | `muse-link-s2` | `3bd4860` | Built on stage 1 plus a dev-only merge of proactive's `5cf36dc` (commit `8c99122`), so it runs against the real `Offers`. 417 tests, web build passes. To be rebased onto main once proactive's stage 1 is in, dropping that merge |

Merging stage 1 after proactive's stage 1 gives one small conflict in `backend/api/app.py`: both add a line after `ctx.alerts = alerts`, and both add an `include_router` before the web mount. Keep both, offers first (resolved that way in `8c99122`).

## What was built

- `backend/api/handoff.py` (new): the outbox watcher, typed sidecars, `HANDOFF_TEMPLATES` (a push-only `gallery` entry; creator-workflow adds Instagram), `push_file` over `adb -s` from a pool id, https downloads limited to public addresses, the `handoffs` table and the session-only routes; in stage 2, the handoff offers, the `handoff` action and the follow-up on its task.
- `backend/mcp_server/server.py`: `send_to_phone`, `phone_updates`, `create_trigger` (stage 2), `heads_up` in `run_task` and `run_routine` through the guarded preflight import, the new instructions, version 0.7.0. The icon from `3accdb8` still comes with `initialize`.
- `web/components/Handoff.tsx` (stage 2): Activity's "From your Mac" and the outbox folder under Settings › Phones, with mock fixtures.
- `backend/tests/test_handoff.py`, `backend/tests/test_mcp_link.py`, and `backend/tests/conftest.py` (every test gets its own outbox).
- Shared files, small: `app.py` (build the object, start its watcher in the lifespan, include its router), `test_api.py` (the MCP tool list), `web/lib/api.ts`, `mock.ts`, `app/page.tsx`, one line each in `Activity.tsx` and `Settings.tsx`.

## Evidence

- Tests: see the table above. They cover sidecars, the 2-second rule, files already there at start, ignored files, names that aren't paths, the adb commands with a fake that keeps a media store, downloads against a local HTTPS server, the MCP tools in process (cursors, restarts, no secrets), and, in stage 2, the offers with the real `Offers` class, `phone_ok`, captions never in a request, and `create_trigger` staying off.
- `envoy-test` (Android 15), first run: found that adb's write leaves the media row pending (hidden from galleries), and that the clip's date taken comes from its own metadata. Both fixed in `30a05d4` and checked offline with `ffprobe` and `ffmpeg`. Not yet re-run on a device.
- Web: the panel and the setting checked in mock mode at 390×844 and 1440×900 (Send to phone, Yes on the Instagram offer, a bad folder's error).

## Spend

$0. No Meta API calls.

## Not done or not checked yet

- The fixed `push_file` on `envoy-test` and on the Pixel 5 (Android 13), checked in the media store and in Photos or Files. Waiting for a device slot from the coordinator.
- The Muse tests E1–E5, with the user (the coordinator is batching the user's time).
- `heads_up` with the real preflight check: tested with stand-ins only, because preflight's stage 1 isn't in main.
- `phone_updates` items are reported again if a finished task is updated later (its `updated_at` moves). Rare; noted, not fixed.
- Re-dating covers MP4/MOV/M4V and JPEG. PNG, WebP and HEIC keep their own dates (PNG and WebP rarely carry one).
- Tests that drive `/mcp` append to `logs/mcp.jsonl`, which is linked to the main checkout's logs in every worktree. This was already happening before this work. For the Muse tests, records are filtered by the tunnel's host and the user agent.
