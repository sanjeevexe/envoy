#!/usr/bin/env bash
# Envoy over HTTPS on your tailnet (design doc, Live view › Streaming: "Tailscale Serve for HTTPS inside the private
# network"). Tailscale Serve gives the Mac a real certificate on its private *.ts.net name, reachable only by your own
# devices; it proxies to the API on 127.0.0.1:8700. Never Funnel (public) from here.
#
#   scripts/serve_tailnet.sh on       # https://<mac>.<tailnet>.ts.net:8443 → http://127.0.0.1:8700
#   scripts/serve_tailnet.sh off      # removes only Envoy's port; anything else you serve is left alone
#   scripts/serve_tailnet.sh status
#
# Port 8443, not 443: Serve's 443 may already serve something else of yours. Serve allows HTTPS on 443, 8443 and 10000.
set -euo pipefail

TS="${TAILSCALE:-/Applications/Tailscale.app/Contents/MacOS/Tailscale}"
PORT="${ENVOY_SERVE_PORT:-8443}"
TARGET="http://127.0.0.1:${ENVOY_PORT:-8700}"

host() { "$TS" status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))'; }

case "${1:-status}" in
  on)
    "$TS" serve --bg --yes --https="$PORT" "$TARGET" >/dev/null
    echo "Envoy on your tailnet: https://$(host):$PORT (tailnet only; restart the API so it picks up the address)"
    ;;
  off)
    "$TS" serve --https="$PORT" off >/dev/null
    echo "Envoy is no longer served on :$PORT"
    ;;
  status)
    "$TS" serve status
    ;;
  *)
    echo "usage: $0 on|off|status" >&2
    exit 2
    ;;
esac
