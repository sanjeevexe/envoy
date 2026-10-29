#!/usr/bin/env bash
# For the user: open the cloud copy's sign-in link in this Mac's browser (its own session token, never printed).
# Then pair the iPhone from its Settings, as with the Mac's copy, and add it to the Home Screen as a second icon.
#
#   scripts/cloud/login.sh
source "$(dirname "$0")/config.sh"
host="$(vm_ssh --command "tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)[\"Self\"][\"DNSName\"].rstrip(\".\"))'" 2>/dev/null)"
[ -n "$host" ] || { echo "the VM isn't on the tailnet yet (scripts/cloud/tailnet.sh up)" >&2; exit 1; }
open "https://$host:8443/login?k=$(vm_ssh --command 'cat ~/envoy-state/api/session_token' 2>/dev/null)"
