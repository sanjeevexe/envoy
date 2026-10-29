#!/usr/bin/env bash
# For the user: a public HTTPS address for Muse's connector to the cloud copy (scripts/start_muse_test.sh, on the VM).
#
#   scripts/cloud/muse-tunnel.sh      # prints <public URL>/mcp; stays in the foreground; Ctrl-C stops the tunnel
#
# Then in Muse: a custom connector at that URL, with the cloud copy's MCP token (scripts/cloud/muse-token.sh puts it on
# the clipboard). While the tunnel is up the cloud API accepts its host for /mcp only, as on the Mac.
source "$(dirname "$0")/config.sh"
vm_ssh_once --ssh-flag=-t --command "cd ~/$REMOTE_DIR && scripts/start_muse_test.sh"
