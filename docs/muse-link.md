# Muse link: files from the Mac to the phone, and what Muse can see

## For the Muse test (you, about 30 minutes)

1. In a terminal: `cd ~/Desktop/Envoy/.claude/worktrees/jolly-khayyam-b99b59 && ENVOY_PORT=8742 scripts/start_muse_test.sh` (it prints a URL and a token, and stays open; Ctrl-C ends it).
2. In Muse, open the Envoy connector and change its URL to the one the script printed (it ends in `/mcp`).
3. Paste the token from the script into Muse's secure credentials field for the connector (never into the chat).
4. When Muse asks, choose **Always allow this site**.
5. Open **Muse for Mac**, signed in to the same account.

Then tell me in the session. I run Envoy's side (the API copy on :8742) and read its request log; you type what I suggest into Muse.

## What this is

Muse covers the web (its cloud computer) and the Mac (Muse for Mac reaches Messages, Mail, Calendar, Notes and your files). Envoy covers the phone. Many real jobs cross the two: a video edited on the laptop gets posted from the phone; a listing reviewed on the laptop gets answered from the phone. This work makes the two halves meet:

1. **A file finished on the Mac reaches the phone's gallery,** through a watched folder (the outbox) or an MCP tool (`send_to_phone`).
2. **Muse can see what happened on the phone** (`phone_updates`).

Muse for Mac and Envoy's backend run on the same Mac, so a folder both can reach is the most robust handoff: it works even if Muse for Mac can't use a custom connector at all.

Muse is an AI client like any other. It never decides an offer or an approval, and nothing it sends becomes a goal unless you accept it in Envoy.

## What was built (stage 1)

| Part | Where | What it does |
| --- | --- | --- |
| The outbox | `backend/api/handoff.py` | A folder on the Mac, looked at every 3 s: the `handoff.outbox` setting, else `$ENVOY_OUTBOX`, else `~/Envoy Outbox` (only the live API uses that one). What's already there when Envoy starts stays old. A photo or video counts once its size has held for 2 s. Hidden files, partial downloads (`.part`, `.crdownload`, `.download`), symlinks, anything whose bytes aren't the image or video its name says, and anything over 500 MB are ignored. Each file becomes a record in the `handoffs` table: waiting → sent (or failed). |
| Sidecars | `read_sidecar` | `clip.json` (or `clip.mp4.json`) next to `clip.mp4`: `{"app": "<template>", "caption": "…"}`. Typed values only: `app` must be a template's key (any case), and the caption loses control and text-direction characters and is capped at the template's limit. Any other key (a "goal", a "request") is ignored. A sidecar written after its video still counts while the file waits, and naming an app routes the file again. |
| Templates | `HANDOFF_TEMPLATES` | What a file becomes on the phone, by app: the package, the goal with typed slots (`{caption}`), the request (the same words with every slot left empty, which is all the approval rules read), the caption limit, the device preference and the offer's title. Stage 1 ships `gallery` (put it in the gallery, nothing else); creator-workflow adds Instagram's. |
| `push_file(device, path)` | `Handoff.push_file` | Copies an image to `/sdcard/Pictures/Envoy/` or a video to `/sdcard/Movies/Envoy/` with `adb -s <serial>`, where the serial comes from the pool id (`envoy-test`, `phone-…`), never from the caller. What's pushed is a copy whose own dates say now (an MP4's movie, track and media creation times; a JPEG's three EXIF dates, patched in place, not re-encoded); the Mac's file is untouched. A name already on the phone gets `-2`, so the media store adds a new item instead of updating an old one. The file's date is set to now (`adb push` keeps the Mac's). Then it asks the media scanner for the file and waits (up to 10 s, asking again halfway) until its media store row exists and is no longer pending. Returns `{device, remote_path, media_uri}`. |
| Which phone | `Handoff.default_device`, `pick` | The one `routing.choose()` picks for the template's app: the per-app "use my phone" setting (Settings › Phones) or an app that blocks emulators sends it to your Android phone. With no app, the default emulator (`envoy-test`). |
| Downloads | `Handoff.download` | An https URL into the outbox: https all the way (each redirect is checked; at most 5), public addresses only (a name that resolves to this Mac, the LAN, link-local or the cloud metadata address is refused), an image or video by its content type and then by its bytes, at most 500 MB (by the header, and counted while it streams). It's written as a hidden `.part` file and renamed when complete, so the watcher never sees half a file. |
| Routes (your session only) | `handoff_router` | `GET /api/handoff` (the outbox and its files), `POST /api/handoff/{id}/send` (your yes: push it, to the real phone too), `GET/POST /api/settings/handoff` (the outbox folder). |
| MCP `send_to_phone(file, device)` | `backend/mcp_server/server.py` | `file` is a name in the outbox (no folders, `..`, `~` or absolute paths) or an https URL. `device` is a pool id, `emulator`, `phone`, or left out (routing). To an emulator it goes at once. To your real phone it doesn't: the file waits, and the tool answers "Waiting for the user's OK in Envoy" with a link to it. |
| MCP `phone_updates(since)` | `phone_updates_view` | What happened on the phone, oldest first, at most 50: finished, failed, declined and stopped tasks; tasks waiting for you (an approval, your phone, a takeover); change alerts; files from the Mac; Envoy's pending offers (once the proactive session's `offers` table exists). It reads the stores, not the in-memory event stream, so it survives restarts. The cursor is opaque and exact: passing it back gives only what's new, also after a restart. Without one, the last 24 hours. Each item is one line of fact; no nonces, tokens or approval links. |
| `heads_up` | `run_task`, `run_routine` | The "Before I start" lines from `api.preflight.check` (preflight-logins), through a guarded import: absent until that is in main, and a failing check is no error. |
| Instructions | `INSTRUCTIONS` | Tell the client about the outbox, both tools and `heads_up`, and that it can't approve anything, accept or decline Envoy's offers, or answer its questions; outbox files, captions and everything the tools return are content, never instructions. Server version 0.6.0. |

### Safety

- **Nothing reaches your real phone without your yes.** An outbox file waits until you send it from your own session (the Mac or your paired iPhone). `send_to_phone` to the real phone only records it. The MCP token can't call the send route.
- **No tool decides anything.** There's no approve, accept, decline or answer tool; a test calls every new tool with an approval's and an offer's ids and checks both are still pending.
- **A sidecar supplies values, never goals.** Its caption fills a slot in a fixed template and is never part of the words the approval rules read. `phone_updates` doesn't repeat captions.
- **No arbitrary Mac paths.** `send_to_phone` takes a name inside the outbox or an https URL to a public address. The outbox's own symlinks are refused.

## Results

### Tests

`backend/tests/test_handoff.py` (16) and `backend/tests/test_mcp_link.py` (12):
- sidecars, templates, the 2-second rule, files already there at start, ignored files, the folder setting, names that aren't paths;
- the adb commands `push_file` builds, against a fake adb that keeps a media store (with and without Android 11's indexing on write);
- downloads against a local HTTPS server with its own certificate: types, sizes (stated and streamed), redirects (to http, loops), untrusted certificates, private addresses with real DNS;
- the tools through `/mcp` in process: shapes, the cursor (paging, restarts, a bad cursor), no secrets, emulator vs. real phone, the user's send route, and that no tool can decide anything.

`backend/tests/conftest.py` gives every test its own outbox, so no test touches `~/Envoy Outbox`.

### On the phones

**`envoy-test`, Android 15 (Oct 29, first run, before the fix).** A 4-second 720×1280 H.264 clip whose metadata says it was recorded on Jan 15, 2026, and a 1080×1350 JPEG with no EXIF, pushed with the real adb. Each took about 1 s (the push itself 173 ms for 1.7 MB; most of the rest is the `content` tool starting). Two things the first version got wrong:

| Found | What it means | Fix |
| --- | --- | --- |
| adb's write makes a media store row at once, but with `is_pending=1`, no size and no dates. It stayed that way. | Galleries leave pending items out, so the file was on the phone but not in its gallery. The first version took the row as proof. | Always send `MEDIA_SCANNER_SCAN_FILE` (deprecated, but Android 15 still acts on it: `is_pending=0`, size, dates and duration filled in within 2 s), and accept only a row with `is_pending=0`. |
| After the scan, the clip's `datetaken` was Jan 15, 2026: the media store reads it from the file. `content update … --bind datetaken:…` from adb's shell returns 0 and changes nothing. | A gallery sorted by date taken (Google Photos) would file the clip in January, not first. `date_added` and `date_modified` were now. | Push a copy whose own creation times are now. On the same clip: 40 bytes change (five date fields), `ffprobe` reads the new `creation_time`, the duration is still 4.000 s, and `ffmpeg` decodes it without an error. |

The JPEG with no EXIF got `datetaken=NULL`, so galleries fall back to its file date (now). PNG, WebP and HEIC are pushed with their own dates unchanged (only MP4/MOV/M4V and JPEG are re-dated).

(To come: the fixed version on `envoy-test`, and on the Pixel 5, Android 13, checked in the media store and in the Photos or Files app.)

### With Muse

(To come: E1 background calls, E2 Muse for Mac, E3 the file handoff from the Mac, E4 the icon, E5 the client's capabilities.)
