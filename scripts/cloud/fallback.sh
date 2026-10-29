#!/usr/bin/env bash
# A way around a zone stockout (run on the Mac): a machine image of the VM, startable in another zone of the region.
#
#   scripts/cloud/fallback.sh image          # (re)make envoy-cloud-image from the stopped VM (run after stop.sh)
#   scripts/cloud/fallback.sh start us-east1-c   # when us-east1-b has no n2-standard-8: a copy of the VM in that zone
#
# The image holds the whole disk: the toolchain, both AVDs with their sign-ins, the code, ~/envoy-state and the
# Tailscale identity, but no Meta key (key.sh remove runs first; key.sh put adds it back). The copy comes up as
# "envoy-cloud" on the tailnet, so the iPhone icon, the shortcut and Muse's URL keep working. Never run both: the copy
# and the original share one Tailscale identity. After a start, use the other zone for the other scripts:
#   export ENVOY_GCP_ZONE=us-east1-c
# Storage: about $0.05 per GB-month of the image (14 GB used on Oct 29).
source "$(dirname "$0")/config.sh"
IMAGE="${VM}-image"
case "${1:-}" in
  image)
    [ "$(vm_status)" = "TERMINATED" ] || { echo "stop the VM first (scripts/cloud/stop.sh), so the image is consistent" >&2; exit 1; }
    "${GC[@]}" compute machine-images delete "$IMAGE" 2>/dev/null || true
    "${GC[@]}" compute machine-images create "$IMAGE" --source-instance "$VM" --source-instance-zone "$ZONE" --storage-location "$REGION"
    ;;
  start)
    to="${2:?usage: $0 start <zone, e.g. us-east1-c>}"
    [ "$to" != "$ZONE" ] || { echo "that's the VM's own zone; use scripts/cloud/start.sh" >&2; exit 2; }
    [ "$(vm_status)" != "RUNNING" ] || { echo "$VM is running in $ZONE: never run the copy beside it" >&2; exit 1; }
    "${GC[@]}" compute instances create "$VM" --zone "$to" --source-machine-image "$IMAGE"
    echo "started a copy of $VM in $to; now: export ENVOY_GCP_ZONE=$to (and key.sh put 3 if the cloud copy is in use)"
    ;;
  *) echo "usage: $0 image | start <zone>" >&2; exit 2 ;;
esac
