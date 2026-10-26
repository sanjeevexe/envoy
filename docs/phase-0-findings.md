# Phase 0 findings

Oct 26, 2026. Part A (unattended) is done. The Part B sections at the end are placeholders. The only Phase 0 item left after Part B is the Meta API test (`scripts/meta_api_check.py`), which waits for credits.

Raw data: `eval/results/phase0/` (device timings, resource samples, secure-screen results) and `eval/fixtures/phase0/` (screens). Scripts that produced them are named in each section, so every number can be re-measured.

## Summary

- **Toolchain:**
  - Both emulators run headless and side by side: an arm64 JDK 21, the API 35 Google Play arm64 image, emulator 37.2.12, scrcpy 5.0.1 and cloudflared 2026.10.3.
  - Each emulator boots cold in 12 to 19 s.
- **The device layer is much faster than the design assumed:**
  - A tree read takes 31 ms (the doc assumed 0.5 to 1 s) and a gRPC screenshot 6 ms raw.
  - A tap through the emulator's gRPC takes under 1 ms.
  - The slow part is waiting for the screen to settle: about 1.5 s after a tap that opens a new screen.
- **Secure screens:**
  - Chrome incognito is black in scrcpy video and `adb screencap`, but **not in the emulator's gRPC screenshot**.
  - The accessibility tree stays readable.
- **Three problems found and fixed:**
  - gRPC was open to the whole network with no auth.
  - uiautomator2 typed by pasting through the clipboard.
  - The emulator crashed in its Wi-Fi simulator (netsim) when loading snapshots.
- **MCP stub:** works locally on both MCP protocol versions, with token auth and a request log. The public-tunnel check was blocked by my permission settings and moves to Part B.
- **Meta API test:** ready. The dry run sends nothing and estimates $0.16 expected and $0.54 worst case for 28 calls. The gate pipeline passed end to end with a stubbed model reply.

## This Mac (verified)

| Item | Expected | Measured |
| --- | --- | --- |
| Chip / cores / RAM | M5 Pro, 15 cores, 24 GB | Apple M5 Pro, 15 cores, 24 GiB |
| macOS | 26.6.2 | 26.6.2 (25G83) |
| Free disk | ~645 GB | 638 GB before installs |
| Java | Temurin 21 x86_64 under Rosetta | Confirmed. The arm64 Homebrew OpenJDK 21.0.13 is installed next to it. |
| Python | 3.14 | 3.14.6. Python 3.13.17 is installed through uv for the backend. |
| Node / Homebrew | Node 26 | Node 26.5.1, Homebrew 7.0.7 |
| Memory before any emulator | not given | 22 GB "used" (10 GB compressed), 46% free. Chrome alone held about 8.4 GB. |

## A2. Android toolchain

**Installed**
- Homebrew OpenJDK 21 (arm64), `uv` 0.13.5, `scrcpy` 5.0.1 and `cloudflared` 2026.10.3.
- From Google, into `~/Library/Android/sdk`:
  - cmdline-tools 23.0 (arm64 zip, SHA-1 matched Google's repository manifest)
  - platform-tools 37.0.1
  - emulator 37.2.12
  - `platforms;android-35`
  - `system-images;android-35;google_apis_playstore;arm64-v8a` (revision 9)
- API 35 worked, so API 36 was not needed.
- `sdkmanager` now prints a deprecation notice in favor of the new `android` CLI. It still works.

**Environment:** `scripts/env.sh` sets `JAVA_HOME`, `ANDROID_HOME` and `PATH`. Writing `~/.zshrc` was blocked by my permission settings, so adding the source line is a Part B step.

**AVDs** (Pixel 6 profile, 1080×2400 at 420 dpi, 4 GB RAM, 4 cores, Play Store on)

| AVD | Console / adb serial | gRPC | Data partition | Snapshots |
| --- | --- | --- | --- | --- |
| `envoy-test` | 5554 / `emulator-5554` | 127.0.0.1:8554 | 10 GB | Named snapshots allowed. Quick-boot state is never saved on exit (`-no-snapshot-save`). |
| `envoy-real` | 5556 / `emulator-5556` | 127.0.0.1:8556 | 16 GB | None. Always a cold boot (`-no-snapshot`). The code refuses `snapshot_load` on it. |

Start with `scripts/start_emulator.sh <avd> [--window]`. Stop with `scripts/stop_emulator.sh <avd>`, which shuts Android down cleanly.

**Boot and shutdown**
- First cold boot: 19 s for `envoy-test`, 16 s for `envoy-real` (with `envoy-test` already running).
- Later cold boots: 12 to 13 s. The script waits for `sys.boot_completed`.
- Clean shutdown (`reboot -p`): 7.5 s.

**RAM and CPU** (`scripts/measure_resources.py`, 30 s of samples). Chrome, Claude, Codex and Spotify were open throughout, as on a normal working day.

| State | Emulator CPU (median / max, % of one core) | Emulator memory footprint | Emulator resident memory | Mac |
| --- | --- | --- | --- | --- |
| No emulator | n/a | n/a | n/a | 22 GB used (10 GB compressed), 46% free |
| One idle (`envoy-test`) | 9% / 13% | 6.7 GB | 2.8 GB | 36% free, 7.1 GB swap used |
| Two, just after `envoy-real`'s first boot | test 3% / 33%; real 42% / 159% | 6.6 GB + 7.3 GB | 1.0 GB + 3.1 GB | 35% free, 9.9 GB swap used |
| Two, settled (3 min later) | test 6% / 19%; real 4% / 32% | 6.7 GB + 7.3 GB | 1.1 GB + 1.5 GB | Overall CPU 97% idle; 37% free, 10.4 GB swap used |

- **CPU is not a constraint.**
- **Memory is.** Each emulator's footprint is about 7 GB, not 4. With today's other apps open, macOS kept two emulators running by compressing and swapping: resident memory fell to about 1 GB each and swap reached 10.4 GB.
- They stayed responsive while idle. Expect slowdowns under real app load unless Chrome and other heavy apps are closed.

**Security: gRPC was open to the network**
- With plain `-grpc 8554`, the emulator logged `security: Insecure, auth: none` and listened on `*:8554`.
- I took a screenshot with no credentials, and the port answered on the Mac's campus IP (10.90.65.11). Anyone on the same Wi-Fi could have watched and controlled the phone.
- With `-grpc-use-token` it binds to 127.0.0.1 only and rejects missing or wrong tokens (`UNAUTHENTICATED`).
- The token is per launch and is stored as `grpc.token` in the emulator's discovery file (`~/Library/Caches/TemporaryItems/avd/running/pid_*.ini`). It is not the console token in `~/.emulator_console_auth_token`. The device code reads it automatically.

**Stability: netsim crash on snapshot load**
- Emulator 37.2.12 aborted with a double free in `NetsimWifiTransport::readThread()` while loading a snapshot. The crash report is in `~/Library/Logs/DiagnosticReports/qemu-system-aarch64-headless-2026-10-26-185309.ips`.
- Launching with `-feature -WiFiPacketStream` (Wi-Fi in-process instead of through netsim) fixed it: 20/20 snapshot restores afterward.
- Networking still works. Wi-Fi is enabled, and mobile data (HSPA) is the default network.

**Persistence of `envoy-real`**
- `avdmanager` wrote a full default `config.ini` with placeholders (`avd.name=<build>`, `disk.dataPartition.path=<temp>`). I replaced them.
- A file written to `/data/local/tmp` survived a cold restart, so user data persists.
- A settings value written seconds before `adb emu kill` (a hard power-off) was lost. A shell-written global setting was also gone after a clean shutdown, which suggests Android drops unknown keys rather than a storage problem.
- **Always stop `envoy-real` with `stop_emulator.sh`** (a clean shutdown), never `emu kill`.

**Disk**
- Each snapshot is 3.8 GB, because RAM is saved uncompressed.
- `envoy-test` is 11 GB with one snapshot (`phase0-gate`). `envoy-real` is 2.2 GB.

## A3. Device control spike

Code is in `backend/devices/`:
- `types.py`: the `Device` protocol, `ScreenState`, `Action`.
- `screen.py`: tree parsing, the compact format and the screen signature.
- `emulator_grpc.py`: gRPC screenshots and touch.
- `emulator.py`: `EmulatorDevice`.

Stubs are generated from the emulator's own `emulator_controller.proto` (`scripts/gen_emulator_grpc.sh`).

**Timings** (`scripts/measure_device.py`, 20 runs each, `envoy-test` alone, Settings app)

| Measurement | Median | p90 | Notes |
| --- | --- | --- | --- |
| Tree read (uiautomator2 dump) | **31 ms** | 36 ms | Doc assumed 0.5 to 1 s |
| `observe()`: dump, foreground app, parse, compact text | 68 ms | 77 ms | About 80 ms after adding the secure-window check (10-run average) |
| gRPC screenshot, raw RGB888 | **6 ms** | 7 ms | 1080×2400, 7.8 MB |
| gRPC screenshot, PNG encoded locally | 20 ms | 20 ms | Pillow, compression level 1 |
| gRPC screenshot, PNG encoded by the emulator | 32 ms | 32 ms | |
| `adb exec-out screencap -p` | 142 ms | 152 ms | Fallback |
| Tap via uiautomator2 | 151 ms | 160 ms | Call returns after injection |
| Tap via emulator gRPC `sendTouch` | **0.6 ms** | 0.8 ms | Registered 5/5 in a separate check (opened Settings search). Now the default for taps on emulators. |
| Tap → next screen settled | **1,520 ms** | 1,577 ms | Tap "Search settings"; the tree keeps changing for about 1.3 s (window transition, then the keyboard), plus the 250 ms quiet window |
| Type non-English text (set-text) | 120 ms | 132 ms | `Café Ñandú 東京 Привет 😀`: 20/20 exact when read back with `get_text`. The clipboard stayed empty. |
| Snapshot restore: load, reconnect uiautomator2 and gRPC, observe | **1,798 ms** | 2,057 ms | Back on the saved screen 20/20 |
| Snapshot restore: emulator load only | 1,377 ms | 1,573 ms | |
| Snapshot save | 1.4 s | | Single run |

**What the spike changed in the code**
- **Typing**
  - uiautomator2 3.7.1's `send_keys` puts the text on the clipboard and pastes it, so Gboard showed a "Clipboard" chip and kept the text in its history. That would leak anything the agent types.
  - `EmulatorDevice` now types with accessibility set-text (`ACTION_SET_TEXT` through uiautomator2), which handles every script and emoji without the bridge. `send_keys` is a fallback that clears the clipboard afterward.
  - `adb shell input text` with non-ASCII text crashes with a `NullPointerException`.
- **Emoji in tree dumps:** the XML dump shows emoji as `..`, so 0/20 typed strings matched exactly in the dump. Code that checks a field's value (routine `field_equals`) must use `get_text`, not the dump.
- **Settling**
  - On cold app starts the dump holds only System UI for 0.5 to 1 s, because the splash window isn't in the accessibility tree. The settle loop used to stop there.
  - It now also requires app content: a non-System UI element with text, or one that is tappable or editable.
- **Status bar:** the clock, signal and battery icons are in every dump, and the clock changes each minute. They are excluded from the compact list, the signature and settle detection.
- **Secure windows:** each observation reads the focused window's `FLAG_SECURE` flag from `dumpsys window` (about 25 ms, folded into the foreground-app call). See A4 for why black frames can't be used for this.

**Compact screens** (more in `eval/fixtures/phase0/*/compact.txt`)

Settings:
```text
App: com.android.settings · Screen: Settings · settled 784 ms
[1] List (id: settings_homepage_container) (scrollable)
[2] Button "Profile picture, double tap to open Google Account" (id: account_avatar)
[3] Text "Settings" (id: homepage_title)
[4] Button "Search settings" (id: search_action_bar)
[5] List (id: main_content_scrollable_container) (scrollable)
[6] Button "Network & internet · Mobile, Wi‑Fi, hotspot"
[7] Button "Connected devices · Bluetooth, pairing"
[8] Button "Apps · Assistant, recent apps, default apps"
[9] Button "Notifications · Notification history, conversations"
[10] Button "Battery · 100%"
[11] Button "Storage · 49% used - 8.18 GB free"
[12] Button "Sound & vibration · Volume, haptics, Do Not Disturb"
(screen has a scrollable list; scroll to see more)
```

Contacts (no account):
```text
App: com.google.android.contacts · Screen: PeopleActivity · settled 1311 ms
[1] EditText "Search contacts" (id: open_search_bar) (empty)
[2] Button "Search"
[3] Button "Signed in as Device Account and settings." (id: selected_account_disc)
[4] Button "Device"
[5] Button "View labels"
[6] Toggle "Show list filters" (off)
[7] Text "No contacts yet" (id: text1)
[8] Button "Create contact" (id: floating_action_button)
[9] Text "Contacts" (id: contacts) (selected)
[10] Button "Highlights" (id: highlights)
[11] Button "Organize" (id: nav_organize)
```

Chrome (first run, then a normal tab on example.com):
```text
App: com.android.chrome · Screen: FirstRunActivity · settled 1160 ms
[1] List (scrollable)
[2] Text "Welcome to Chrome" (id: title)
[3] Text "Sign in to browse easier across devices" (id: subtitle)
[4] Button "Add account to device" (id: signin_fre_continue_button)
[5] Button "Use without an account" (id: signin_fre_dismiss_button)
[6] Button "By continuing, you agree to the Terms of Service. To help improve the app, Chro…" (id: signin_fre_footer)

App: com.android.chrome · Screen: Main · settled 42 ms
[1] List "Example Domain" (scrollable)
[2] Text "This domain is for use in documentation examples without needing permission. Th…"
[3] Text "هذا النطاق مُخصص للاستخدام في أمثلة التوثيق دون الحاجة إلى إذن. هذه ليست خدمة، …"
[4] Text "该域名仅用于文档示例，无需获得许可。这并非一项服务，请勿将其用于测试和监控目的。"
  … (French, Russian, Spanish lines)
[8] Button "Open the home page" (id: home_button)
[9] Button "Connection is secure" (id: location_bar_status)
[10] EditText "example.com" (id: url_bar)
[11] Button "Switch or close tabs" (id: tab_switcher_button)
[12] Button "Customize and control Google Chrome" (id: menu_button)
```

These screens are 500 to 800 characters each, a few hundred tokens, as the design assumed.

## A4. Secure screens (Chrome incognito, no account)

`scripts/secure_screen_check.py`. Thumbnails are in `eval/fixtures/phase0/secure/`. The incognito window's flags include `SECURE`.

| Path | Normal tab | Incognito tab (FLAG_SECURE) |
| --- | --- | --- |
| scrcpy video (recorded headless, last frame) | Visible | **Black** (99.5% black pixels; only the status bar shows) |
| `adb screencap` | Visible | **Black** (99.5%) |
| Emulator gRPC `getScreenshot` | Visible | **Visible.** The full incognito page is captured. |
| Accessibility tree | 57 nodes, readable | **62 nodes, readable** (all text, URL bar, buttons) |

**What this means**
1. The emulator's gRPC stream can show sign-in screens. The design already anticipated this ("or through the emulator's gRPC screen stream if Phase 0 shows it captures secure screens"). On emulators, the user could sign in from the web app or iPhone through a gRPC-fed live view instead of the emulator window on the laptop.
2. The agent's screenshot path on emulators captures secure screens too. The doc's hand-off rule ("a black frame with a non-empty tree") never fires there, so the device layer now reports `ScreenState.secure` from the window flag. The agent must hand off and take no screenshots while `secure` is true, and redaction must assume a screenshot can contain payment fields.
3. On real phones (scrcpy and screencap) secure screens stay black, as designed.

Part B repeats this on real apps' sign-in and payment screens.

## A5. Muse connector stub

`backend/mcp_stub/`:
- MCP Python SDK **2.3.0** with Streamable HTTP at `/mcp`. It serves protocol **2026-07-28** (which the SDK's own client used) and **2025-11-25**.
- The REST fallback (`mcp_stub/rest.py`) exposes the same two tools with an OpenAPI description at `/openapi.json`.

**Tools**
- `memory_search(query)` returns the fake SkyLark trip: SL 482, ATL to ORD, Oct 30, gate B12, seat 14C, KX7Q2M. Each fact has a source.
- `run_task(goal)` returns a fake task ID and an `approve_url`. That page has no buttons; it only proves the link reached the user.

**Auth and logging**
- A static bearer token from `.env` (`MCP_BEARER_TOKEN`), compared in constant time.
- Every request is logged to `logs/mcp_stub.jsonl`: HTTP method, path, JSON-RPC method, tool, arguments, client info and headers, with `authorization` and cookies redacted.

**Local test** (`scripts/test_mcp_stub.py`): **11/11 passed.**
- The official MCP client lists both tools and calls both.
- Missing or wrong tokens get 401.
- A raw `initialize` with the right token gets 200.
- REST calls with the token work, and without it get 401.
- The OpenAPI document lists both operations.
- No token value appears in the log.

**Public tunnel:** `scripts/start_muse_test.sh [mcp|rest]` starts a Cloudflare quick tunnel and the server, waits until the public URL answers, and prints the URL and token. **I could not run it.** My permission settings blocked opening a public tunnel, so the one-time public check moves to B2.

## A6. Connector application drafts

`docs/connector-application.md` has both drafts. The approve capability is deliberately absent, and the drafts explain why.
- **Muse Connector Platform:** the review asks for business verification, a privacy policy, a data-processing questionnaire and a test account that stays live during review. A solo project is unlikely to clear it before Nov 4. Submitting still costs little.
- **Meta AI Connectors waitlist:** wants a REST API, "live or in active development". The REST fallback with OpenAPI fits.

## A7. Meta API test: ready, not run

**Nothing was sent to Meta's API.** The API shapes come from Meta's docs (dev.meta.ai/docs), read Oct 26:

| Topic | Design doc said | Meta docs say |
| --- | --- | --- |
| Spark 1.3 prices | $1.25 / $4.25, cached $0.15 | Confirmed |
| Wonder 1.0 | $4 / $20, preview | Confirmed; cached input $0.20; "in preview" on the models page |
| SAM 3.1 | $2.50 per 1,000 images | Confirmed. Called through `/v1/responses` with `model: "sam-3.1"`. Returns **special-token text** (`<\|box;x1=…\|>`, base85 masks), not JSON, and no scores unless `metadata.include_confidence: "true"`. Parser: `meta-sam-parser`. |
| Voice Transcribe | $0.18/hour, public preview | Price confirmed; **no preview label** now. WebSocket `wss://api.meta.ai/v1/asr/realtime`, with auth in the handshake JSON. |
| Contributor tier | $0.10 / $0.20 | Confirmed; cached $0.002. It is a **separate model ID** (`muse-spark-1.3-contributor`) limited to **150 RPM** (standard is 3,000 RPM), with no `max` effort. |
| Reasoning | Can't be turned off; billed as output | Confirmed. `effort: "none"` returns 400. `minimal` is valid. |
| Structured output | `json_schema` | Confirmed. Goes in `text.format` (Responses API). Decoding is constrained; `strict: false` behaves like true. |
| Tool calling | Only `auto`; arguments not guaranteed | Confirmed |
| Prompt caching | `prompt_cache_key`, 24 h | **Different.** Caching is automatic. `prompt_cache_key` is only a routing hint. 24 h retention is a separate `prompt_cache_retention: "24h"` (a hint, not a guarantee). |
| Grounding | 0–1000 grid | Confirmed. Prompt-driven; the model returns plain JSON text. Values can exceed 1000, so clamp. |
| Max output tokens, minimum cacheable prompt | (open question) | **Not documented** |
| API key name | `META_API_KEY` | Docs use `MODEL_API_KEY`. Envoy keeps `META_API_KEY` and passes it explicitly. |

**What is in place**
- `backend/models/adapter.py`:
  - Per-job config (step, plan, repair, grounding, extract, compile).
  - A cost meter that writes `logs/model_costs.jsonl`, logging cost at standard prices as well, with a daily cap (`META_DAILY_COST_CAP_USD`).
  - 30 s timeouts and two retries on 429/5xx, honoring `Retry-After`. Meta says not to retry other 4xx errors or 504.
  - `store: false`.
  - The Contributor tier only when both `META_CONTRIBUTOR_TIER=true` and `data_scope="test_app"`; otherwise it raises.
- `backend/models/schemas.py`:
  - The action schema from the Agent runtime section (15 actions, plus reason, expected_result and risk).
  - Generated from Pydantic into Meta's strict subset and checked by `check_strict_subset()` (0 problems).
- `backend/models/prompts.py`: the stable, cacheable step instructions.
- `backend/models/translate.py`: model action → device action, with the 0–1000 grid converted to pixels.
- Fixtures: 5 screens in `eval/fixtures/phase0/`, each with `tree.json`, `compact.txt`, `screen.png` and `meta.json`.
  - The Settings home and Network screens carry known targets for grounding. The Airplane mode switch is 137×126 px at `[834, 427, 961, 479]` on the 0–1000 grid.
  - `envoy-test` has the snapshot `phase0-gate` (Settings home) for check 1.
- `scripts/meta_api_check.py` and `docs/meta-api-test-plan.md`.

## Ready for the Meta API test

- [x] `META_API_KEY` slot in `.env` (empty). The script exits with code 2 and sends nothing when it is missing (verified).
- [x] `--dry-run` runs cleanly. It builds all 28 requests and prints them with images and schemas shortened.
- [x] Cost estimate before running: expected **$0.16**, worst case **$0.54** (every call at its output cap). The script refuses to run above `--max-cost` (default $2) and asks for confirmation.
- [x] Check 1 (gate): restore snapshot → live observe → model → validate → execute → verify Battery settings opened. Passed end to end with a **stubbed** model reply.
- [x] Checks 2–7: request building and result handling exercised offline with fake replies (latency, tokens, caching counts, grounding IoU, SAM box parsing, Wonder listing and error capture).
- [x] Fixtures, snapshot, adapter, schemas, cost meter and test plan are committed.
- [ ] Add the key, start `envoy-test`, run `scripts/meta_api_check.py` (with you).

## Decisions made without you

1. **`~/.zshrc`:** writing it was blocked by my permission settings. The same variables are in `scripts/env.sh`; adding one `source` line is a Part B step.
2. **Public tunnel:** opening one was blocked by my permission settings. The tunnel script is written; the public check moves to B2, where you run it.
3. **Android SDK licenses:** accepted. `sdkmanager` requires this to install the packages you asked for.
4. **JDK:** Homebrew `openjdk@21` (arm64, keg-only, no sudo). The Temurin cask would install into the same `/Library/Java` folder as your x86 Temurin. The x86 JDK is untouched.
5. **SDK location:** `~/Library/Android/sdk` (Android Studio's default). The command-line tools came from Google's zip, checksum verified.
6. **AVD config:** fixed avdmanager's placeholder values; set `PlayStore.enabled=true` and GPU on; gave `envoy-real` a 16 GB data partition for real apps.
7. **Ports:** `envoy-test` uses 5554 (console) and 8554 (gRPC); `envoy-real` uses 5556 and 8556.
8. **gRPC:** always launched with `-grpc-use-token`, after measuring that plain `-grpc` is open to the network.
9. **Wi-Fi:** netsim Wi-Fi disabled (`-feature -WiFiPacketStream`) on both AVDs after the crash.
10. **Snapshots and shutdown:** `envoy-real` always cold-boots with snapshots off and stops with a clean shutdown. `envoy-test` never overwrites its quick-boot state.
11. **Taps and typing:** taps go through emulator gRPC (uiautomator2 as fallback); typing uses accessibility set-text (clipboard paste only as a cleared fallback).
12. **Naming:** the future MCP package is `backend/mcp_server/`, not `mcp/`, which would shadow the SDK's `import mcp`. The Phase 0 stub is `backend/mcp_stub/` as you asked.
13. **MCP stub transport:** stateless HTTP with JSON responses (`MCP_STATELESS=1`, `MCP_JSON_RESPONSE=1`), the most tolerant setting for a remote client behind a tunnel. Both can be switched to streaming by environment variable.
14. **MCP stub host checks:** DNS-rebinding protection stays on; the tunnel host is allowlisted at start.
15. **Open pages:** the stub's fake approval page and the REST `/openapi.json` need no token (there's nothing to protect, and Muse must be able to read the OpenAPI file). Every tool endpoint requires the token.
16. **Meta API check tier:** uses the **standard** tier. Built-in apps are not "our own test apps", so the Contributor rule applies.
17. **Responses not stored:** `store: false` on every model call; we never use `previous_response_id`.
18. **Chrome first run on `envoy-test`:**
    - The incognito test needs Chrome past its first-run screen, whose footer says continuing accepts Chrome's Terms of Service.
    - I took the private options each time: "Use without an account", usage and crash reporting **turned off** under "Manage", and "No thanks" to Chrome's notifications prompt.
    - No account is signed in.
19. **Clipboard:** cleared on `envoy-test` after the one `send_keys` test that used it.
20. **Fixtures:** five built-in screens (Settings home, Settings › Network, Contacts, Chrome first run, Clock). Contacts and Chrome are empty because no account is signed in.
21. **Snapshot cleanup:** deleted the 3.8 GB `phase0-measure` snapshot (the measurement script re-creates it); kept `phase0-gate`.
22. **Commits:** made as your existing git identity (Sanjeev Varma), one commit per Part A step.

## Open questions from the design doc

| Question | Status after Part A |
| --- | --- |
| Credits (do they cover Wonder, SAM 3.1, Voice?) | **Open.** Prices confirmed from the docs. Coverage → API test checks 6 and 7. |
| Speed of a Spark 1.3 step | **Open** for the model → check 2. **Device side settled:** about 0.07 s to read a screen, under 1 ms to tap, about 1.5 s to settle after a screen change. |
| Grounding on tall screenshots; SAM 3.1 on UI | **Open** → checks 4 and 6. Fixtures with known boxes are ready. |
| Limits: max output tokens, minimum cacheable prompt | **Open.** Neither is documented. Check 5 shows whether our roughly 2.5k-token prefix gets cached. |
| Path into Muse | **Open** → B2. The stub is ready. Route 3 now looks harder (organization-level review). |
| Real apps on the emulator | **Open** → B1 |
| Android phone (IPaT loan, Oct 28) | **Open** |
| Sign-in codes on iPhone (Shortcuts while locked) | **Open** |
| Official rules | **Open** → B3 |
| Apple account | Already decided (Home Screen web app) |

Settled by Part A, though not on the list:
- **Can two emulators run at once?** Yes. Memory is the limit; see A2.
- **Does emulator gRPC capture secure screens?** Yes; see A4.
- **Is the Envoy bridge needed for read speed?** No; see A3.

## Where measurements contradict the design doc (proposed changes; your call)

1. **Device layer › Envoy bridge.** "About 0.5 to 1 second for `uiautomator dump`" → 31 ms through uiautomator2's server (68–80 ms for a full observation).
   - *Proposal:* drop read speed as a reason for the bridge. Build it only if Phase 1 shows settle detection or set-text failing on real apps.
2. **Agent runtime › Actions and Device layer.** "`type` uses the bridge's set-text" and "uiautomator2 … types any language through its own input method" → uiautomator2 3.7.1 types by pasting through the clipboard by default, which leaks text. Accessibility set-text through uiautomator2 handles every language and emoji (20/20) without the bridge.
   - *Proposal:* "type = accessibility set-text; the clipboard is never used."
3. **Device layer › Screenshots and video.**
   - Emulator gRPC screenshots take 6 ms raw / 20 ms as PNG.
   - `adb screencap` takes 142 ms on the emulator; the "0.5 to 2.6 seconds" figure may still hold for real phones.
   - gRPC taps take under 1 ms against 151 ms for uiautomator2.
   - *Proposal:* add "emulator taps and screenshots use gRPC".
4. **Device layer › Backend 1 › Launch.** "`-grpc <port>`" alone opens control of the phone to the whole network.
   - *Proposal:* the launch line becomes `-grpc <port> -grpc-use-token -feature -WiFiPacketStream`, with a note on why.
5. **Device layer › Backend 1 › "4 GB each, at most two".** Each emulator's footprint is about 7 GB.
   - *Proposal:* "about 7 GB each. Two run at once, but close the browser and other heavy apps first. Keep the second emulator for comparison tasks", which matches the risk table.
6. **Snapshots.** Not quantified in the doc.
   - *Proposal:* add "restore in 1.8 s (p90 2.1 s) including reconnect; 3.8 GB on disk each, so prune old ones".
7. **Live view and sign-in › Secure screens.**
   - *Proposal:* "black in scrcpy video and `adb screencap`; **the emulator's gRPC screenshot captures them**". Then:
     - (a) Emulators can offer a gRPC-fed live view for remote sign-in.
     - (b) The agent detects secure screens from the window's `FLAG_SECURE` flag, not black frames, and takes no screenshots while it is set. **Safety › Redaction** should say screenshots from emulators may include secure content.
8. **Agent runtime › How the screen is shown.** The example "settled 220 ms" is optimistic. After a tap that opens a new screen, settling took 1.5 s (p90 1.6 s).
   - *Proposal:*
     - Budget about 1.6 s of device time per step on top of the model call.
     - The 10-step, 30-second routine target still holds (about 17 s of device time) as long as no model call is needed.
     - Phase 1 can try settling on structure and text only (ignoring bounds animation) to save about 0.2 s.
9. **App routines › Checks.**
   - *Proposal:* add "`field_equals` reads the field with `get_text`; the XML dump shows emoji as `..`". Also note that cold app starts show only System UI for up to 1 s, so settle waits for app content.
10. **Models and cost** (from Meta's docs):
    - Caching is automatic; `prompt_cache_key` is a routing hint; retention is `prompt_cache_retention: "24h"`.
    - Contributor is a separate model ID with **150 RPM**: enough for one emulator, but it would throttle parallel evaluation.
    - Wonder cached input is $0.20.
    - SAM output is special-token text that needs a parser.
    - Voice Transcribe is no longer labeled preview.
11. **Tech stack and repository.** `backend/mcp/` → `backend/mcp_server/` (avoids shadowing the MCP SDK). MCP SDK is v2.3.0, serving 2026-07-28 and 2025-11-25.
12. **Path into Muse, route 3.** The Muse Connector Platform review needs business verification, a privacy policy and a long-lived test account. *Proposal:* mark route 3 as "very unlikely for a solo project". The Meta AI Connectors waitlist (REST + OpenAPI) is the better ask.
13. **Device layer › Backend 1.** *Proposal:* add "stop `envoy-real` with a clean shutdown; a hard kill can lose recent writes".

---

## Part B results (to fill in together)

### B1. Real-app compatibility (`envoy-real`)

| App | Installs | Launches | Blocks emulator? | How far before sign-in | Sign-in screen black in scrcpy / gRPC / emulator window | Tree readable on sign-in; password field flagged | Session survives restart |
| --- | --- | --- | --- | --- | --- | --- | --- |
| | | | | | | | |

### B1. Secure screens on real apps

_(to fill)_

### B2. Muse connector test

- Tunnel public check (one-time):
- Did Muse connect (MCP)?
- Tools called, with arguments (from `logs/mcp_stub.jsonl`):
- How Muse presented the approval link:
- REST fallback (if needed):
- Token rotated after the test: [ ]
- **Decision on the "Path into Muse" route:**

### B3. Official rules

- Open-source use:
- Submission requirements (materials, demo video length):
- `THIRD_PARTY.md` check:
- Connector applications submitted: [ ] Muse Connector Platform  [ ] Meta AI Connectors waitlist

### B4. Remaining for Phase 0

- [ ] Run `scripts/meta_api_check.py` once credits arrive (the Phase 0 gate)
