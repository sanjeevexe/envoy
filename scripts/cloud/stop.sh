#!/usr/bin/env bash
# Stop the emulator cleanly, then stop the VM (run on the Mac). A stopped VM costs only its disk.
#
#   scripts/cloud/stop.sh
source "$(dirname "$0")/config.sh"
if [ "$(vm_status)" = "RUNNING" ]; then
  vm_ssh --command "[ -x ~/$REMOTE_DIR/scripts/stop_emulator.sh ] && cd ~/$REMOTE_DIR && source ~/env-linux.sh && scripts/stop_emulator.sh envoy-test" || true
  "${GC[@]}" compute instances stop "$VM" --zone "$ZONE"
fi
echo "$VM: $(vm_status)"
