#!/usr/bin/env bash
# Delete the VM, its disk, the firewall rule and the network (run on the Mac). The user's call: it can't be undone,
# and everything on the VM (the AVD, results not yet fetched) goes with it.
#
#   scripts/cloud/delete.sh --yes-delete-envoy-cloud
source "$(dirname "$0")/config.sh"
[ "${1:-}" = "--yes-delete-$VM" ] || { echo "usage: $0 --yes-delete-$VM   (deletes $VM, its disk and network $NETWORK in $PROJECT)" >&2; exit 2; }
[ -n "$(vm_status)" ] && "${GC[@]}" compute instances delete "$VM" --zone "$ZONE" --delete-disks=all
"${GC[@]}" compute firewall-rules delete "$NETWORK-iap-ssh" 2>/dev/null || true
"${GC[@]}" compute networks subnets delete "$NETWORK-$REGION" --region "$REGION" 2>/dev/null || true
"${GC[@]}" compute networks delete "$NETWORK" 2>/dev/null || true
echo "deleted $VM and network $NETWORK"
