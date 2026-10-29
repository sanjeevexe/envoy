#!/usr/bin/env bash
# Install the toolchain and the envoy-test AVD on the VM (run on the Mac; the VM must be running).
#
#   scripts/cloud/setup.sh
#
# Copies vm-setup.sh, env-linux.sh, the AVD hardware profile and the Android SDK licenses already accepted on this
# Mac ($ANDROID_HOME/licenses) to ~/cloud-setup on the VM, then runs vm-setup.sh there. Safe to run again.
source "$(dirname "$0")/config.sh"
source "$REPO/scripts/env.sh"

[ "$(vm_status)" = "RUNNING" ] || { echo "$VM is not running (scripts/cloud/start.sh --vm-only)" >&2; exit 1; }
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
mkdir -p "$stage/cloud-setup/licenses"
cp "$REPO"/scripts/cloud/{vm-setup.sh,env-linux.sh,envoy-test.config.ini} "$stage/cloud-setup/"
cp "$ANDROID_HOME"/licenses/* "$stage/cloud-setup/licenses/"
vm_scp --recurse "$stage/cloud-setup" "$VM:~/"
vm_ssh --command 'bash ~/cloud-setup/vm-setup.sh'
echo "next: scripts/cloud/push.sh"
