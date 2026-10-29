#!/usr/bin/env bash
# Start a long command on the VM, detached from the SSH session (run on the Mac); then scripts/cloud/wait.sh <name>.
#
#   scripts/cloud/bg.sh portability uv run --project backend python eval/run_phase6.py portability --device envoy-test --no-control --k 3 --name cloud
#
# A minutes-long run over one SSH session can outlive its IAP tunnel, so it runs under setsid on the VM instead:
# output in ~/envoy/logs/cloud-<name>.log, exit code in ~/envoy/logs/cloud-<name>.rc.
source "$(dirname "$0")/config.sh"
NAME="${1:?usage: $0 <name> <command> [args...]}"; shift
[ $# -gt 0 ] || { echo "usage: $0 <name> <command> [args...]" >&2; exit 2; }
CMD="$(printf '%q ' "$@")"
vm_ssh --command "cd ~/$REMOTE_DIR && mkdir -p logs && rm -f logs/cloud-$NAME.rc &&
  setsid nohup bash -c 'source ~/env-linux.sh && $CMD; echo \$? > logs/cloud-$NAME.rc' > logs/cloud-$NAME.log 2>&1 < /dev/null &
  echo started $NAME"
