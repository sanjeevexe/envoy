#!/usr/bin/env bash
# A permanent public address for Muse's Envoy connector, so it's set up once (a quick tunnel, scripts/start_muse_test.sh,
# changes address every run). Tailscale Funnel on a port of its own serves /mcp and nothing else; the API accepts that
# address for /mcp alone (MCP_PERMANENT_URL in .env) and refuses anything else Tailscale marks as from the internet.
# Every call still needs MCP_BEARER_TOKEN: rotate it if it leaks (scripts/rotate_mcp_token.sh, then the API and Muse).
# Funnel has to be allowed on the tailnet first, an admin setting: the first `on` prints Tailscale's link to allow it.
#
#   scripts/muse_funnel.sh on       # https://<mac>.<tailnet>.ts.net:10000/mcp, public → http://127.0.0.1:8700/mcp
#   scripts/muse_funnel.sh off      # closes that port to the internet; the tailnet-only app on :8443 is left alone
#   scripts/muse_funnel.sh status
#
# Port 10000: Funnel opens a whole port to the internet, and 443 and 8443 serve tailnet-only things (8443 is all of Envoy).
set -euo pipefail

TS="${TAILSCALE:-/Applications/Tailscale.app/Contents/MacOS/Tailscale}"
PORT=10000
TARGET="http://127.0.0.1:${ENVOY_PORT:-8700}/mcp"

host() { "$TS" status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))'; }

case "${1:-status}" in
  on)
    "$TS" funnel --bg --yes --https="$PORT" --set-path=/mcp "$TARGET"
    URL="https://$(host):$PORT/mcp"
    echo "Envoy's MCP server is public at $URL (/mcp only)."
    echo "In .env: MCP_PERMANENT_URL=$URL, then restart the API. Muse's connector: that URL and MCP_BEARER_TOKEN."
    ;;
  off)
    "$TS" funnel --https="$PORT" off >/dev/null
    echo "Port $PORT is closed to the internet."
    ;;
  status)
    "$TS" funnel status
    ;;
  *)
    echo "usage: $0 on|off|status" >&2
    exit 2
    ;;
esac
