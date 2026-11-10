# Getting started

Run every command from the repository root.

You need a Mac on Apple silicon (built on macOS 26), Homebrew's `openjdk@21` (`scripts/env.sh` expects it there), the
Android command-line tools in `~/Library/Android/sdk/cmdline-tools/latest`, `uv`, Node, about 9 GB free, and a Meta Model
API key for chat and `demo_setup.py`'s memory step. It runs on SkyLark, our own test app, so it needs no personal accounts.
With those in place, a fresh clone reached a checked-in flight in about 5 minutes in our test (the first run also downloads about 4 GB of Android tools).

```bash
source scripts/env.sh                                    # JAVA_HOME, ANDROID_HOME, PATH
(cd backend && uv sync)                                  # Python 3.13 environment
cp .env.example .env                                     # then set META_API_KEY and MCP_BEARER_TOKEN (the API needs it:
                                                         # python3 -c "import secrets; print(secrets.token_urlsafe(32))")
```

The test phone, once (on Linux use `x86_64`, as `scripts/cloud/vm-setup.sh` does):

```bash
sdkmanager --install "platform-tools" "emulator" "system-images;android-35;google_apis_playstore;arm64-v8a"
avdmanager create avd -n envoy-test -k "system-images;android-35;google_apis_playstore;arm64-v8a" -d pixel_6
sed -i '' 's/^hw.keyboard=no/hw.keyboard=yes/' ~/.android/avd/envoy-test.avd/config.ini      # so you can type during sign-in
(cd testapps/skylark && ./gradlew :app:assembleDebug)                                       # SkyLark
scripts/start_emulator.sh envoy-test                                                         # headless, gRPC 8554
adb -s emulator-5554 install -r testapps/skylark/app/build/outputs/apk/debug/app-debug.apk
```

Then Envoy:

```bash
uv run --project backend python scripts/demo_setup.py    # SkyLark signed out + demo memory (envoy-test up, API stopped)
(cd web && npm install && npm run build)                 # once, and after web changes
uv run --project backend python -m api                   # http://127.0.0.1:8700, MCP at /mcp; prints a sign-in link
```

Open the sign-in link it prints and type "Check me in for my flight" in the Ask Envoy box. When Envoy says it needs you,
click Take over, click a field on the phone (if the page only scrolls, click it again) and type (any email and password, then the test SMS code `demo_setup.py`
printed), then click Hand back. It checks you in, because asking was your OK. To
approve it on your iPhone first, set approvals to "Always ask" in Settings, or send the same request from an agent over
MCP. Real apps
use a second emulator, `envoy-real`, made the same way with a 16 GB data partition
([`docs/phase-0-findings.md`](phase-0-findings.md)).

**No key?** The tests pass without one (`cd backend && uv run pytest -q`), and saved routines replay with no model calls.
Do the test phone steps and the `web` build above, set `MCP_BEARER_TOKEN`, and skip the plain `demo_setup.py` line, which
stops at its memory step without a key. Then:

```bash
uv run --project backend python scripts/demo_setup.py --app-only --signed-in
uv run --project backend python -m api                   # keeps running; open the sign-in link it prints in your browser
```

In a second terminal:

```bash
curl -c /tmp/envoy -s -o /dev/null "<the sign-in link>"
curl -b /tmp/envoy -H 'X-Envoy: 1' -H 'Content-Type: application/json' -d '{"routine":"skylark_check_in_flight","inputs":{"trip_city":"Chicago"}}' http://127.0.0.1:8700/api/tasks
```

Then, in the web app: Activity › Review › Confirm check-in. To repeat it, run the `demo_setup.py` line again first. Chat,
memory and the Routines page's Run button need a key.

**Connect an agent.** Make it a key in Settings › Agents, then:
- **Any MCP client,** such as Claude Code: `claude mcp add --transport http …`, step by step in
  [`docs/agents.md`](agents.md).
- **The Spark agent:** `uv run --project backend python agents/meta-agent/run.py` with the key in
  `ENVOY_AGENT_KEY_FILE`, then http://127.0.0.1:8790 ([`agents/meta-agent/README.md`](../agents/meta-agent/README.md)).
- **Muse:** `scripts/start_muse_test.sh` opens a public HTTPS tunnel that serves `/mcp` and nothing else; add it in Muse
  as a custom connector with `MCP_BEARER_TOKEN` ([`docs/muse-link.md`](muse-link.md)).

**Your iPhone.** `scripts/serve_tailnet.sh on` serves Envoy over HTTPS on your tailnet only (restart the API after).
In the web app, Settings › Devices › "Pair your iPhone": scan the code, add the page to the Home Screen, type the
pairing code, and turn on notifications ([`docs/phase-5-results.md`](phase-5-results.md)).

**Evaluate it.** Every suite starts from a known state, scores with code, and records its commit, tier and cost
([`eval/README.md`](../eval/README.md)):

```bash
eval/run_final.sh                                              # every suite, one emulator at a time (about 4.5 hours)
uv run --project backend python eval/run_final.py systems      # one suite (compile runs first)
uv run --project backend python eval/run_final.py report       # eval/results/final/report.md and its charts
```
