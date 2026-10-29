#!/usr/bin/env bash
# Start the VM and boot envoy-test on it (run on the Mac). Billing for the VM's CPUs runs until scripts/cloud/stop.sh.
#
#   scripts/cloud/start.sh            # the VM, then the emulator (scripts/start_emulator.sh envoy-test, SwiftShader)
#   scripts/cloud/start.sh --vm-only  # just the VM
#
# The emulator's adb server, gRPC (127.0.0.1:8554, with its token) and console stay on the VM. Nothing is forwarded
# to the Mac, whose adb server would take a forwarded port for a phone or an emulator slot.
source "$(dirname "$0")/config.sh"

if [ "$(vm_status)" != "RUNNING" ]; then
  "${GC[@]}" compute instances start "$VM" --zone "$ZONE"
fi
for _ in $(seq 1 30); do vm_ssh --command true 2>/dev/null && break; sleep 5; done
echo "$VM running in $ZONE"
[ "${1:-}" = "--vm-only" ] && exit 0
vm_ssh --command "cd ~/$REMOTE_DIR && source ~/env-linux.sh && scripts/start_emulator.sh envoy-test"
