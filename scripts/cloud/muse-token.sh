#!/usr/bin/env bash
# For the user: copy the cloud copy's MCP token to this Mac's clipboard (never printed), to paste into Muse's
# connector as its API key. The cloud copy's token is its own; the Mac's .env is untouched.
#
#   scripts/cloud/muse-token.sh
source "$(dirname "$0")/config.sh"
vm_ssh --command "grep '^MCP_BEARER_TOKEN=' ~/envoy-state/.env | cut -d= -f2-" 2>/dev/null | tr -d '\n' | pbcopy
echo "the cloud copy's MCP token is on the clipboard"
