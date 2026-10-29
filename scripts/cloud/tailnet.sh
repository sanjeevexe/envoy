#!/usr/bin/env bash
# The cloud copy on the user's tailnet (run on the Mac). Tailnet only: Tailscale Serve, never Funnel.
#
#   scripts/cloud/tailnet.sh up       # join as "envoy-cloud": prints a login link; the user opens it and approves the VM
#   scripts/cloud/tailnet.sh serve    # https://envoy-cloud.<tailnet>.ts.net:8443 → the VM's API (scripts/serve_tailnet.sh),
#                                     # then restarts the API so its links use that address
#   scripts/cloud/tailnet.sh status
#   scripts/cloud/tailnet.sh off      # stop serving (the VM stays on the tailnet; remove it in the Tailscale admin)
source "$(dirname "$0")/config.sh"
case "${1:-status}" in
  up)
    vm_ssh --command 'set -e
      if tailscale status >/dev/null 2>&1; then echo "already on the tailnet as $(tailscale status --json | python3 -c "import json,sys; print(json.load(sys.stdin)[\"Self\"][\"DNSName\"].rstrip(\".\"))")"; exit 0; fi
      rm -f /tmp/tailscale-up.log
      sudo setsid nohup tailscale up --hostname=envoy-cloud --operator="$(id -un)" > /tmp/tailscale-up.log 2>&1 < /dev/null &
      for _ in $(seq 1 30); do url=$(grep -oE "https://login.tailscale.com/[^ ]+" /tmp/tailscale-up.log | head -1); [ -n "$url" ] && break; sleep 1; done
      echo "Open this link and approve envoy-cloud (single use): $url"'
    ;;
  serve)
    vm_ssh --command "cd ~/$REMOTE_DIR && TAILSCALE=tailscale scripts/serve_tailnet.sh on && sudo systemctl restart envoy-api"
    ;;
  status)
    vm_ssh --command "tailscale status --self=true --peers=false 2>&1 | head -3; tailscale serve status 2>&1 | head -6"
    ;;
  off)
    vm_ssh --command "cd ~/$REMOTE_DIR && TAILSCALE=tailscale scripts/serve_tailnet.sh off && sudo systemctl restart envoy-api"
    ;;
  *) echo "usage: $0 up|serve|status|off" >&2; exit 2 ;;
esac
