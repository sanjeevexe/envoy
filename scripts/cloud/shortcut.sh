#!/usr/bin/env bash
# Build "Ask Envoy (cloud)": the Siri shortcut, pointed at the cloud copy (run on the Mac; the VM must be on the tailnet).
#
#   scripts/cloud/shortcut.sh   # → ~/Desktop/Envoy/captures/cloud/Ask Envoy (cloud).shortcut; open it to add it
#
# scripts/make_shortcut.py --siri --base <the cloud copy's tailnet address>, with the cloud copy's session token fetched
# into a private temporary folder (never printed) and deleted after. The shortcut holds a `siri` token of the cloud copy
# (revoke it in the cloud copy's Devices). Its own name, so it never shadows the Mac's "Ask Envoy".
source "$(dirname "$0")/config.sh"
host="$(vm_ssh --command "tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)[\"Self\"][\"DNSName\"].rstrip(\".\"))'" 2>/dev/null)"
[ -n "$host" ] || { echo "the VM isn't on the tailnet yet (scripts/cloud/tailnet.sh up)" >&2; exit 1; }
tmp="$(mktemp -d)"; chmod 700 "$tmp"
trap 'rm -rf "$tmp"' EXIT
(umask 077; vm_ssh --command 'cat ~/envoy-state/api/session_token' >"$tmp/session_token" 2>/dev/null)
(cd "$REPO" && uv run --project backend python scripts/make_shortcut.py --siri --base "https://$host:8443" --api-dir "$tmp")
OUT="$HOME/Desktop/Envoy/captures/cloud"
mkdir -p "$OUT" && mv "$tmp/shortcut/Ask Envoy (test).shortcut" "$OUT/Ask Envoy (cloud).shortcut" && chmod 600 "$OUT/Ask Envoy (cloud).shortcut"
echo "built: $OUT/Ask Envoy (cloud).shortcut  (open it on the Mac; Shortcuts asks to add it, and iCloud brings it to the iPhone)"
