# muse-link: report

Session muse-link, Oct 29. Details and the user's Muse checklist: `docs/muse-link.md`.

## Branches

| Stage | Branch | Tip | State |
| --- | --- | --- | --- |
| 1: `push_file`, the outbox, MCP `send_to_phone` and `phone_updates`, `heads_up` | `coord/muse-link-s1` | `fb3d926` | **In main** (fast-forward; 445 tests, web build). The `envoy-test` re-check passed first |
| 2: handoff offers, MCP `create_trigger`, the web panel, offer "Before I start" lines, download pinning | `muse-link-s2-main` | on main `fb3d926` | 455 tests, web build. Rebased over proactive's stage 2 (Repeats, weekly triggers): `app.py` keeps both builder lines; weekly triggers are described in `create_trigger`'s offer |

## What was built

- `backend/api/handoff.py` (new): the outbox watcher, typed sidecars, `HANDOFF_TEMPLATES` (a push-only `gallery` entry; creator-workflow adds Instagram), `push_file` over `adb -s` from a pool id, https downloads limited to public addresses, the `handoffs` table and the session-only routes; in stage 2, the handoff offers, the `handoff` action and the follow-up on its task.
- `backend/mcp_server/server.py`: `send_to_phone`, `phone_updates`, `create_trigger` (stage 2), `heads_up` in `run_task` and `run_routine` through the guarded preflight import, the new instructions, version 0.7.0. The icon from `3accdb8` still comes with `initialize`.
- `web/components/Handoff.tsx` (stage 2): Activity's "From your Mac" and the outbox folder under Settings › Phones, with mock fixtures.
- `backend/tests/test_handoff.py`, `backend/tests/test_mcp_link.py`, and `backend/tests/conftest.py` (every test gets its own outbox).
- Shared files, small: `app.py` (build the object, start its watcher in the lifespan, include its router), `test_api.py` (the MCP tool list), `web/lib/api.ts`, `mock.ts`, `app/page.tsx`, one line each in `Activity.tsx` and `Settings.tsx`.

## Evidence

- Tests: see the table above. They cover sidecars, the 2-second rule, files already there at start, ignored files, names that aren't paths, the adb commands with a fake that keeps a media store, downloads against a local HTTPS server, the MCP tools in process (cursors, restarts, no secrets), and, in stage 2, the offers with the real `Offers` class, `phone_ok`, captions never in a request, and `create_trigger` staying off.
- `envoy-test` (Android 15), first run (11:57, `a9d939b`): found that adb's write leaves the media row pending (hidden from galleries), and that the clip's date taken comes from its own metadata (Jan 15). Both fixed in `30a05d4`.
- `envoy-test` re-check (12:54, from a checkout of `d3df6aa`): clip `is_pending=0`, `datetaken` = the push time, and the photo `is_pending=0` (no EXIF date, so galleries use now). Google Photos shows both under "Envoy". About 1 s each.
- Web: the panel and the setting checked in mock mode at 390×844 and 1440×900 (Send to phone, Yes on the Instagram offer, a bad folder's error).

- The Muse sitting (Oct 29, 1:24–2:12 pm, the iPhone app): **E1 works** (a Muse scheduled task called `phone_updates` every ~10 min with the cursor and told you, unprompted, about the new outbox offer); **E5**: `capabilities: {}`, so no push; **E4** not possible for a custom connector (Muse draws its own generic icon and doesn't use server icons); `send_to_phone` to the emulator and `create_trigger` (made switched off) worked from Muse; asked to accept offers, Muse said there is no accept tool. Details in `docs/muse-link.md`, evidence in `eval/results/muse-link/`.
- Muse for Mac (2:43–2:54 pm): **E2 works** (the same Envoy connector; `phone_updates` and `send_to_phone` from the Mac); **E3 works** (it moved the newest video into the outbox and wrote a valid sidecar, about 90 s with two permission prompts). E3 found that the watcher's 6 s wait for a sidecar was too short (it came after 23 s); fixed on `muse-link-late-sidecar`.

- Pixel 5, Android 13 (7:56–7:59 pm): **works.** `send_to_phone` with `device="phone"` raised "Put pixel-check.mp4 on your Pixel 5?"; after your Yes the clip was in the gallery about 6 s later (`is_pending=0`, date taken = the push time). Cleaned up; `eval/results/muse-link/pixel5_push.json`. Before it, `567eb1b`: when the watcher had already asked about the emulator, Muse asking for the real phone withdraws that question and asks about the Pixel instead (579 tests).

## Spend

$0. No Meta API calls.

## Not done or not checked yet

- `heads_up` and the offer lines run against preflight's real `check` in the full suite, but the tests assert their content only with stand-ins.
- `phone_updates` items are reported again if a finished task is updated later (its `updated_at` moves). Rare; noted, not fixed.
- Re-dating covers MP4/MOV/M4V and JPEG. PNG, WebP and HEIC keep their own dates (PNG and WebP rarely carry one).
- Tests that drive `/mcp` append to `logs/mcp.jsonl`, which is linked to the main checkout's logs in every worktree. This was already happening before this work. For the Muse tests, records are filtered by the tunnel's host and the user agent.
