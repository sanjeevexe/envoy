#!/usr/bin/env bash
# A public HTTPS address for Muse's custom connector (route 2 of "Path into Muse"): a Cloudflare quick tunnel.
#
#   scripts/start_muse_test.sh          # Envoy's real MCP server: the running API's /mcp (Phase 5)
#   scripts/start_muse_test.sh mcp      # Phase 0: the MCP stub (Streamable HTTP) at <public URL>/mcp
#   scripts/start_muse_test.sh rest     # Phase 0: REST fallback, OpenAPI at <public URL>/openapi.json
#
# Prints the public URL and the bearer token, then stays in the foreground. Ctrl-C stops the tunnel (and the stub).
# In api mode the API must already be running; while the tunnel is up the API accepts its host for /mcp and nothing
# else (the web app, API and approval pages stay on this Mac and your tailnet), and the URL file is removed on exit.
set -euo pipefail

MODE="${1:-api}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
mkdir -p logs

[ -f .env ] || { echo "No .env; copy .env.example to .env and set MCP_BEARER_TOKEN" >&2; exit 1; }
set -a; source .env; set +a
[ -n "${MCP_BEARER_TOKEN:-}" ] || { echo "MCP_BEARER_TOKEN is empty in .env" >&2; exit 1; }

case "$MODE" in
  api)  PORT="${ENVOY_PORT:-8700}"; MODULE="";              SUFFIX=/mcp ;;
  mcp)  PORT="${MCP_PORT:-8765}";  MODULE=mcp_stub.server; SUFFIX=/mcp ;;
  rest) PORT="${REST_PORT:-8766}"; MODULE=mcp_stub.rest;   SUFFIX="" ;;
  *) echo "usage: $0 [api|mcp|rest]" >&2; exit 2 ;;
esac
URL_FILE="data/api/mcp_public_url"

if [ "$MODE" = api ]; then
  curl -sf "http://127.0.0.1:$PORT/healthz" >/dev/null || { echo "Start Envoy first: uv run --project backend python -m api" >&2; exit 1; }
elif lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $PORT is already in use; stop the other server first." >&2; exit 1
fi

TUNNEL_LOG="logs/cloudflared-$MODE.log"
: > "$TUNNEL_LOG"
cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:$PORT" >"$TUNNEL_LOG" 2>&1 &
TUNNEL_PID=$!
SERVER_PID=""
cleanup() {
  [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null || true
  kill "$TUNNEL_PID" 2>/dev/null || true
  rm -f "logs/muse_test_$MODE.pids"
  [ "$MODE" = api ] && rm -f "$URL_FILE"
  echo "Stopped the tunnel$( [ -n "$SERVER_PID" ] && echo " and the stub")."
}
trap cleanup EXIT INT TERM

PUBLIC_URL=""
for _ in $(seq 1 60); do
  PUBLIC_URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" | head -1 || true)"
  [ -n "$PUBLIC_URL" ] && break
  sleep 0.5
done
[ -n "$PUBLIC_URL" ] || { echo "Tunnel did not report a URL; see $TUNNEL_LOG" >&2; exit 1; }

if [ "$MODE" = api ]; then
  # The running API reads this file on each request: its host is accepted for /mcp only, while the tunnel is up.
  printf '%s\n' "$PUBLIC_URL" > "$URL_FILE"
  echo "$TUNNEL_PID" > "logs/muse_test_$MODE.pids"
  for _ in $(seq 1 60); do  # quick tunnels take a few seconds to resolve; /mcp answers 401 without the token
    [ "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$PUBLIC_URL/mcp")" = 401 ] && break
    sleep 1
  done
else
  # The stub needs the public host for its Host-header check and for the approval links it returns.
  (cd backend && MCP_PUBLIC_URL="$PUBLIC_URL" exec uv run --quiet python -m "$MODULE") >"logs/$MODE-server.out" 2>&1 &
  SERVER_PID=$!
  echo "$SERVER_PID $TUNNEL_PID" > "logs/muse_test_$MODE.pids"
  for _ in $(seq 1 60); do
    curl -sf "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1 && break
    sleep 0.5
  done
  for _ in $(seq 1 60); do
    curl -sf "$PUBLIC_URL/healthz" >/dev/null 2>&1 && break
    sleep 1
  done
fi

cat <<EOF

  Envoy $( [ "$MODE" = api ] && echo "MCP server (the real one)" || echo "$MODE stub") is live.
  URL:    $PUBLIC_URL$SUFFIX
  Token:  $MCP_BEARER_TOKEN
  Header: Authorization: Bearer $MCP_BEARER_TOKEN
$( [ "$MODE" = rest ] && echo "  OpenAPI: $PUBLIC_URL/openapi.json" )
  Log:    tail -f logs/mcp_stub.jsonl
  Stop:   Ctrl-C (then rotate the token: scripts/rotate_mcp_token.sh)

EOF
wait "${SERVER_PID:-$TUNNEL_PID}"
