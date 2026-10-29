#!/usr/bin/env bash
# Run a command in ~/envoy on the VM, with the Linux toolchain environment (run on the Mac).
#
#   scripts/cloud/run.sh uv run --project backend python eval/run_phase6.py portability --device envoy-test --no-control --k 3 --name cloud
#   scripts/cloud/run.sh uv run --project backend python eval/run_final.py sizes --device envoy-test
#   scripts/cloud/run.sh adb -s emulator-5554 shell getprop ro.product.cpu.abi
source "$(dirname "$0")/config.sh"
[ $# -gt 0 ] || { echo "usage: $0 <command> [args...]" >&2; exit 2; }
vm_ssh --command "cd ~/$REMOTE_DIR && source ~/env-linux.sh && $(printf '%q ' "$@")"
