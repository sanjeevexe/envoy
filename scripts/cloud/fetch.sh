#!/usr/bin/env bash
# Copy a file or folder from ~/envoy on the VM to the Mac (run on the Mac).
#
#   scripts/cloud/fetch.sh eval/results/phase6/cloud.json eval/results/cloud/
source "$(dirname "$0")/config.sh"
[ $# -eq 2 ] || { echo "usage: $0 <path under ~/envoy on the VM> <local destination>" >&2; exit 2; }
vm_scp --recurse "$VM:~/$REMOTE_DIR/$1" "$2"
