#!/usr/bin/env bash
# Keep the VM from powering itself off when idle (run on the Mac): for a day the cloud option is the one in use.
#
#   scripts/cloud/keep-awake.sh on|off|status
# With it on, the VM runs (about $0.39 an hour) until scripts/cloud/stop.sh or keep-awake.sh off.
source "$(dirname "$0")/config.sh"
case "${1:-status}" in
  on) vm_ssh --command 'sudo touch /etc/envoy-keep-awake && echo "keep-awake on: the VM stays up until stop.sh"' ;;
  off) vm_ssh --command 'sudo rm -f /etc/envoy-keep-awake && echo "keep-awake off: the VM powers off after ~45 idle minutes"' ;;
  status) vm_ssh --command '[ -e /etc/envoy-keep-awake ] && echo on || echo off' ;;
  *) echo "usage: $0 on|off|status" >&2; exit 2 ;;
esac
