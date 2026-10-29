#!/usr/bin/env bash
# Install the cloud copy of Envoy on the VM (run on the Mac, after setup.sh and push.sh; the VM must be running).
#
#   scripts/cloud/envoy-setup.sh
#
# Sends vm-envoy.sh, env-linux.sh, envoy-real's hardware profile and a copy of the Mac's demo memory and test inbox
# (data/demo: SkyLark's test data, copied once, never the live data/api), runs vm-envoy.sh, starts the services, and
# seeds SkyLark on the cloud envoy-test to match that memory (scripts/demo_setup.py --app-only, no model call).
# Safe to run again: an existing state (~/envoy-state on the VM) is kept.
source "$(dirname "$0")/config.sh"
DEMO="${ENVOY_DEMO_DIR:-$HOME/Desktop/Envoy/data/demo}"

[ "$(vm_status)" = "RUNNING" ] || { echo "$VM is not running (scripts/cloud/start.sh --vm-only)" >&2; exit 1; }
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
mkdir -p "$stage/cloud-envoy"
cp "$REPO"/scripts/cloud/{vm-envoy.sh,envoy-real.config.ini} "$stage/cloud-envoy/"
if [ -f "$DEMO/memory.db" ]; then
  sqlite3 "$DEMO/memory.db" ".backup '$stage/cloud-envoy/memory.db'"  # a consistent copy, even while the Mac's API has it open
  [ -d "$DEMO/inbox" ] && cp -R "$DEMO/inbox" "$stage/cloud-envoy/inbox"
fi
vm_scp "$REPO/scripts/cloud/env-linux.sh" "$VM:~/env-linux.sh"
vm_scp --recurse "$stage/cloud-envoy" "$VM:~/"
vm_ssh --command 'bash ~/cloud-envoy/vm-envoy.sh && rm -rf ~/cloud-envoy'
vm_ssh --command "sudo systemctl start envoy-emulators && sudo systemctl restart envoy-api && sleep 5 && systemctl is-active envoy-emulators envoy-api"
vm_ssh --command "cd ~/$REMOTE_DIR && source ~/env-linux.sh && uv run --project backend python scripts/demo_setup.py --app-only"
echo "next: scripts/cloud/tailnet.sh up (the user approves the VM), then scripts/cloud/tailnet.sh serve"
