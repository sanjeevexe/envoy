#!/usr/bin/env bash
# Replace MCP_BEARER_TOKEN in .env with a fresh random token. Restart the stub afterward.
set -euo pipefail
cd "$(dirname "$0")/.."
NEW="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
if grep -q '^MCP_BEARER_TOKEN=' .env; then
  sed -i '' "s|^MCP_BEARER_TOKEN=.*|MCP_BEARER_TOKEN=$NEW|" .env
else
  echo "MCP_BEARER_TOKEN=$NEW" >> .env
fi
echo "Rotated MCP_BEARER_TOKEN in .env (old token no longer works once the server restarts)."
