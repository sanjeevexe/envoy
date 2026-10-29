#!/usr/bin/env bash
# Wait for a command started with scripts/cloud/bg.sh, printing its log as it grows; exits with its exit code.
#
#   scripts/cloud/wait.sh portability [poll_seconds]
source "$(dirname "$0")/config.sh"
NAME="${1:?usage: $0 <name> [poll_seconds]}"
POLL="${2:-20}"
LOG="logs/cloud-$NAME.log"
seen=0
while :; do
  # Complete lines only: the VM reports how many the log has, and sends the ones after `seen`.
  out="$(vm_ssh --command "cd ~/$REMOTE_DIR && n=\$(wc -l < $LOG) && sed -n \"$((seen + 1)),\${n}p\" $LOG && echo \"@@ \$n \$(cat logs/cloud-$NAME.rc 2>/dev/null)\"" 2>/dev/null)" ||
    { sleep "$POLL"; continue; }
  last="$(printf '%s\n' "$out" | tail -1)"
  printf '%s\n' "$out" | sed '$d'
  seen="$(echo "$last" | cut -d' ' -f2)"
  rc="$(echo "$last" | cut -d' ' -f3)"
  [ -n "$rc" ] && exit "$rc"
  sleep "$POLL"
done
