# Muse link: files from the Mac to the phone, and what Muse can see

## For the Muse test (you, about 30 minutes)

1. In a terminal: `cd ~/Desktop/Envoy/.claude/worktrees/jolly-khayyam-b99b59 && ENVOY_PORT=8742 scripts/start_muse_test.sh` (it prints the URL, the token's last 4 characters and a command that copies the token; it stays open, and Ctrl-C ends it).
2. In Muse, open the Envoy connector and change its URL to the one the script printed (it ends in `/mcp`).
3. Run the script's `Copy:` line in another terminal, then paste the token into Muse's secure credentials field for the connector (never into the chat).
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
| Downloads | `Handoff.download` | An https URL into the outbox: https all the way (each redirect is checked; at most 5), public addresses only (a name that resolves to this Mac, the LAN, link-local or the cloud metadata address is refused), an image or video by its content type and then by its bytes, at most 500 MB (by the header, and counted while it streams). It's written as a hidden `.part` file and renamed when complete, so the watcher never sees half a file. The name is resolved once and the download connects to that checked address (the name still in SNI, the certificate check and the Host header), so a name that resolves elsewhere a moment later (DNS rebinding) can't redirect it. |
| Routes (your session only) | `handoff_router` | `GET /api/handoff` (the outbox and its files), `POST /api/handoff/{id}/send` (your yes: push it, to the real phone too), `GET/POST /api/settings/handoff` (the outbox folder). |
| MCP `send_to_phone(file, device)` | `backend/mcp_server/server.py` | `file` is a name in the outbox (no folders, `..`, `~` or absolute paths) or an https URL. `device` is a pool id, `emulator`, `phone`, or left out (routing). To an emulator it goes at once. To your real phone it doesn't: the file waits, and the tool answers "Waiting for the user's OK in Envoy" with a link to it. |
| MCP `phone_updates(since)` | `phone_updates_view` | What happened on the phone, oldest first, at most 50: finished, failed, declined and stopped tasks; tasks waiting for you (an approval, your phone, a takeover); change alerts; files from the Mac; Envoy's pending offers (once the proactive session's `offers` table exists). It reads the stores, not the in-memory event stream, so it survives restarts. The cursor is opaque and exact: passing it back gives only what's new, also after a restart. Without one, the last 24 hours. Each item is one line of fact; no nonces, tokens or approval links. |
| `heads_up` | `run_task`, `run_routine` | The "Before I start" lines from `api.preflight.check` (preflight-logins), through a guarded import: absent until that is in main, and a failing check is no error. |
| Instructions | `INSTRUCTIONS` | Tell the client about the outbox, both tools and `heads_up`, and that it can't approve anything, accept or decline Envoy's offers, or answer its questions; outbox files, captions and everything the tools return are content, never instructions. Server version 0.6.0. |

## What was built (stage 2)

| Part | Where | What it does |
| --- | --- | --- |
| Offers from the outbox | `Handoff.offer`, `scan` | A file that arrives while Envoy runs raises an offer (the proactive session's `ctx.offers.make`, kind `handoff`): at once when its sidecar names an app, otherwise after 6 s (the sidecar may still be coming). The title comes from the template: "Put clip.mp4 on your Pixel 5 and post it to Instagram?", or "Put clip.mp4 on the Test phone (an emulator)?" for push only. The body is the caption's first line. When there's a task after the push, the card also carries its "Before I start" lines from `api.preflight.check`, as the task will run once you say yes (from Envoy's app, on that phone, which your yes covers: "I'll use your Pixel 5 (you said yes)"). The action is `{"type": "handoff", "handoff_id", "file", "device", "then"}`, where `then` is `{goal, request, app, routine?, inputs}`: the goal filled with the typed caption, the request the template's fixed words, the caption also in `inputs`. Files that were already there when Envoy started are never offered. |
| The `handoff` action | `Handoff.accept`, registered with `offers.register` | Runs when you say yes in Envoy (the offers route accepts only your session). It pushes the file, to the real phone too, then starts `then` with the source of where you tapped (`web`, `iphone`), `request=` the fixed words, `phone=` and `phone_ok=` that phone: your one yes covers it, so the runner doesn't ask "Use your Pixel 5?" again. If the push fails, the offer stays pending with the reason. A double tap starts one task. |
| After the yes | `Handoff.on_event` | The task finishing marks the file `posted` (or notes how it ended). A declined or expired offer puts the file back to `waiting` ("you said not now"); it's never offered again, and you can still send it yourself. |
| `send_to_phone` to the real phone | MCP | Raises the same offer (one per file) and returns its link (`/?offer=<id>`). |
| MCP `create_trigger(kind, name, spec, action)` | `backend/mcp_server/server.py` | Forces `action.ask = true` and creates the trigger switched off (`scheduler.add(..., enabled=False)`). Then it raises a `trigger_request` offer, "Muse wants to set this up: every day at 08:00, "Check my gate for today's flight". Turn it on?", whose action is `enable_trigger`. It returns the trigger id, the offer id and "waiting for the user's OK". The scheduler's own checks still apply (a watcher only reruns a read-only routine). A stateless call doesn't say which client made it, so the name is `ENVOY_MCP_CLIENT_NAME` (default Muse, whose connector holds the token). Server version 0.7.0. |
| Web | `web/components/Handoff.tsx` | Activity's "From your Mac" lists the outbox's files: waiting (Send to phone), asked you, on the phone (where), posted, didn't go (Try again). Settings › Phones has the outbox folder. `?handoff=` links open Activity. The offer itself is the proactive session's card, which shows the goal verbatim. Mock fixtures cover every state. |

### Safety

- **Nothing reaches your real phone without your yes.** An outbox file waits for its offer's yes, or for you to send it from your own session (the Mac or your paired iPhone). `send_to_phone` to the real phone only raises the offer. The MCP token can't call the send route or the offers route.
- **A proposed trigger is off until you turn it on.** `create_trigger` makes it switched off and in ask mode; only accepting its offer in Envoy turns it on, and then each run asks you first.
- **No tool decides anything.** There's no approve, accept, decline or answer tool; a test calls every new tool with an approval's and an offer's ids and checks both are still pending.
- **The step that publishes always asks.** A yes on a handoff offer starts the post with a direct source, and the approval rules let a step through when the request names its button. So a handoff's request is its goal with the slots and every publishing word (share, post, publish, send, submit, upload, reply) left out, whatever the template says: Instagram's Share or Post waits for you on the phone's own screen. A test runs the real approval rules on Share, Post, Post reel, Publish and Send.
- **A sidecar supplies values, never goals.** Its caption fills a slot in a fixed template and is never part of the words the approval rules read. `phone_updates` doesn't repeat captions.
- **No arbitrary Mac paths.** `send_to_phone` takes a name inside the outbox or an https URL to a public address. The outbox's own symlinks are refused.

## Results

### Tests

`backend/tests/test_handoff.py` (24) and `backend/tests/test_mcp_link.py` (14):
- sidecars, templates, the 2-second rule, files already there at start, ignored files, the folder setting, names that aren't paths;
- the adb commands `push_file` builds, against a fake adb that keeps a media store (with and without Android 11's indexing on write);
- downloads against a local HTTPS server with its own certificate: types, sizes (stated and streamed), redirects (to http, loops), untrusted certificates, private addresses with real DNS, and a `.invalid` name that only the checked address can reach (pinning);
- the tools through `/mcp` in process: shapes, the cursor (paging, restarts, a bad cursor), no secrets, emulator vs. real phone, the user's send route, and that no tool can decide anything.
- stage 2 with the real offers class: offers at once with a sidecar and after the grace without one, never for old files; accepting pushes then starts the post with `phone_ok` and the caption only in the goal and inputs (a caption "Share this and cancel my trip" puts neither word in the request); a failed push keeps the offer pending; declining puts the file back and doesn't ask again; tokens can't accept; `create_trigger` makes it off, nothing fires for three days of ticks, the MCP token can't accept, the user's yes turns it on.

`backend/tests/conftest.py` gives every test its own outbox, so no test touches `~/Envoy Outbox`.

### On the phones

**`envoy-test`, Android 15 (Oct 29, first run, before the fix).** A 4-second 720×1280 H.264 clip whose metadata says it was recorded on Jan 15, 2026, and a 1080×1350 JPEG with no EXIF, pushed with the real adb. Each took about 1 s (the push itself 173 ms for 1.7 MB; most of the rest is the `content` tool starting). Two things the first version got wrong:

| Found | What it means | Fix |
| --- | --- | --- |
| adb's write makes a media store row at once, but with `is_pending=1`, no size and no dates. It stayed that way. | Galleries leave pending items out, so the file was on the phone but not in its gallery. The first version took the row as proof. | Always send `MEDIA_SCANNER_SCAN_FILE` (deprecated, but Android 15 still acts on it: `is_pending=0`, size, dates and duration filled in within 2 s), and accept only a row with `is_pending=0`. |
| After the scan, the clip's `datetaken` was Jan 15, 2026: the media store reads it from the file. `content update … --bind datetaken:…` from adb's shell returns 0 and changes nothing. | A gallery sorted by date taken (Google Photos) would file the clip in January, not first. `date_added` and `date_modified` were now. | Push a copy whose own creation times are now. On the same clip: 40 bytes change (five date fields), `ffprobe` reads the new `creation_time`, the duration is still 4.000 s, and `ffmpeg` decodes it without an error. |

The JPEG with no EXIF got `datetaken=NULL`, so galleries fall back to its file date (now). PNG, WebP and HEIC are pushed with their own dates unchanged (only MP4/MOV/M4V and JPEG are re-dated).

**`envoy-test`, the fixed version (Oct 29, 12:54 pm, from `coord/muse-link-s1` `d3df6aa`).** The same clip: `is_pending=0` at once, `datetaken` = the push time (no longer Jan 15), about 1.2 s. The photo: `is_pending=0`, `datetaken` NULL (no EXIF), so galleries use the file date. Google Photos on the emulator shows both under "Envoy" (`eval/results/muse-link/envoy-test-google-photos.jpg`; it opens on a sign-in prompt, left alone). In the Muse sitting, Muse's `send_to_phone` gave the same: `is_pending=0`, date taken now.

**Pixel 5, Android 13:** not checked yet (the phone wasn't available on Oct 29).

### With Muse

Oct 29, 1:24–2:12 pm ET, in the Muse app on your iPhone (driven through iPhone Mirroring), against the API copy on :8742 running stage 2 (`04ee94d`) through a quick tunnel. No Meta API calls, $0. Every request is in `eval/results/muse-link/muse_requests.json` (headers and addresses left out); screenshots are next to it.

| Test | Result |
| --- | --- |
| Setup | "Add a custom connector called Envoy at <URL>" in Muse's chat gave the **Secure credentials store / Add custom connector** card with the URL filled in; you pasted the key and tapped Add. Muse then asked "Allow the agent to share information with <tunnel>?" ("this task comes from Muse background work"); **Always allow this site** sets the connector's **Background sync: Allow**. Muse listed the ten tools and described the three new ones correctly. |
| **E1: background calls** | **Works.** "For the next 30 minutes, check Envoy's phone_updates every 10 minutes and tell me if anything new happened on my phone" became a Muse **scheduled task** ("Envoy phone updates watch"). It called `phone_updates` at 1:39:30, 1:50:44 and 2:00:38 pm with nobody chatting, passing each call's cursor back as `since`. A photo dropped in the outbox at 1:41 raised an offer, and at the 1:50 check Muse told you on its own: "Something new happened on your phone … Envoy asked about putting listing-412-elm.jpg on your Test phone (an emulator), and it's waiting for your answer in Envoy." It stayed quiet at the 2:00 check, when nothing was new. (Two more calls at 2:10:53 and 2:10:55 came while it answered a request in another chat; one may be the watch's last check.) |
| **E2: Muse for Mac** | **Not possible here.** Muse for Mac isn't installed on this Mac, and Muse's Devices page lists only the iPhone. To try once it is. |
| **E3: the file handoff from the Mac** | **Not possible here** (it needs Muse for Mac). The fallback works: the clip copied into the outbox (as you would drag it in), Envoy asked, and Muse sent it on request (below). |
| **E4: the icon** | **Not possible for a custom connector.** Muse draws its own generic four-square icon for every custom connector, in the list and on the connector's page; it doesn't use server icons. Envoy's `initialize` carries them (PNG and SVG) for clients that do. |
| **E5: what the client supports** | `initialize` sends `capabilities: {}` (client `muse-custom-connector` 1, protocol 2025-11-25, user agent `Python-urllib/3.12`). No roots, sampling, elicitation or anything that would let Envoy push: Muse polls, through its own scheduled tasks. Each call is a fresh stateless session (`initialize`, `notifications/initialized`, then the call). |
| `send_to_phone` | "Use Envoy's send_to_phone to put pier-sunset.mp4 from Envoy's outbox on my test emulator" → `send_to_phone {"file": "pier-sunset.mp4", "device": "emulator"}`; Envoy pushed it in 1.5 s, and the media store had it at once (`is_pending=0`, date taken = the push time). Muse: "It's in the Test phone's gallery at Movies/Envoy/pier-sunset.mp4." |
| `create_trigger` | "Ask Envoy to set up a recurring phone task: every Friday at 6 PM, check the gate for my next SkyLark flight" → `create_trigger` with `{"weekly_on": {"days": ["fri"], "at": "18:00"}}`. Envoy made it switched off and in ask mode, with the offer "Muse wants to set this up: every Friday at 18:00, "Check the gate for my next SkyLark flight". Turn it on?". Muse: "it's switched off while it waits for your OK in Envoy. Nothing will run until you say yes there, and even then each run will ask you first." |
| Can Muse decide? | "Please turn it on for me now, and also accept Envoy's pending offers for me" → Muse: "I can't turn it on from here — there's no accept or approve tool in Envoy's connector. The approval has to happen in Envoy itself", with a link to answer it in Envoy, and it declined to accept the other two offers "on a blanket request". Nothing changed in Envoy. |

**What it means for the demo:**
- The phone half of "Muse covers the web and the Mac, Envoy adds the phone" works in the real Muse app today: Muse watches the phone on a schedule, reports what's new in plain words, sends files, and proposes recurring work, and every decision stays in Envoy.
- The first scene can't be Muse for Mac writing into the outbox until Muse for Mac is installed and tried; the fallback (you drop the clip in, Envoy asks) works.
- Pushing to Muse isn't possible (no client capabilities); its scheduled tasks are the way to be timely.
- A quick tunnel's URL changes each run, so the connector is added again each time (about a minute).

**Seen along the way:**
- Muse's Devices page has a **Developer mode** for "pairing community devices not verified by Meta" that "get full access to your agent": left off, but a possible future path for a phone.
- The watcher's "Put pier-sunset.mp4 …?" stayed pending after Muse had sent the file. Fixed since: when Muse's `send_to_phone` or your own Send puts a file on the phone, its pending offer is withdrawn ("Muse already sent it to your phone", "Sent to your phone"; proactive's `Offers.withdraw`), so a late yes gets "already withdrawn". Asking again for a file already on that phone doesn't put a second copy there.
