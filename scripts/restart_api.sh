#!/bin/bash
# Restart the live API on :8700 (the web app, the iPhone companion, MCP) on the main checkout's current code, after a
# key change or a merge. It checks the model key first and refuses to restart on a failing key. The API's output goes to
# logs/api.out as before; this script never prints it (it holds the sign-in link).
#
#   scripts/restart_api.sh            # check the key, stop the API (and stale API processes of this checkout), start it
#   scripts/restart_api.sh --no-check # skip the key check
#   ENVOY_REPO=~/Desktop/Envoy …      # restart another checkout than the one holding this script
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "${ENVOY_REPO:-$HERE/..}" && pwd)
cd "$REPO"
PROFILE=${ENVOY_PROFILE:-demo}

if [ "${1:-}" != "--no-check" ]; then
  uv run --project backend python "$HERE/check_model_key.py" || { echo "the model key fails: not restarting"; exit 2; }
fi

live=$(lsof -nP -t -iTCP:8700 -sTCP:LISTEN 2>/dev/null | head -1)
# Every `python -m api` started from this checkout: the live one and any that lost the port but stayed alive.
ours=""
for p in $(pgrep -f "python -m api"); do
  [ "$(lsof -a -p "$p" -d cwd -Fn 2>/dev/null | grep '^n' | cut -c2-)" = "$REPO" ] && ours="$ours $p"
done
echo "live on :8700: ${live:-none}; API processes of this checkout:${ours:- none}"
for p in $ours; do kill -TERM "$p" 2>/dev/null; done
for _ in $(seq 1 20); do lsof -nP -iTCP:8700 -sTCP:LISTEN >/dev/null 2>&1 || break; sleep 1; done
if lsof -nP -iTCP:8700 -sTCP:LISTEN >/dev/null 2>&1; then
  echo ":8700 is still taken after 20 s; stopping it hard"; kill -KILL $(lsof -nP -t -iTCP:8700 -sTCP:LISTEN) 2>/dev/null; sleep 1
fi
# A freed port isn't a stopped API: one with a phone's live view open (a scrcpy session) lets go of :8700 but can ignore
# SIGTERM and keep that session on the phone. Give the old processes 10 s to exit, then stop them hard.
left=""
for _ in $(seq 1 10); do
  left=""; for p in $ours; do kill -0 "$p" 2>/dev/null && left="$left $p"; done
  [ -z "$left" ] && break; sleep 1
done
if [ -n "$left" ]; then
  echo "still running 10 s after SIGTERM:$left; stopping it hard (SIGKILL)"; kill -KILL $left 2>/dev/null; sleep 1
fi

nohup uv run --project backend python -m api --profile "$PROFILE" >> logs/api.out 2>&1 &
for _ in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8700/healthz 2>/dev/null)
  [ "$code" = "200" ] && { echo "API up on :8700 (profile $PROFILE, commit $(git rev-parse --short HEAD), pid $(lsof -nP -t -iTCP:8700 -sTCP:LISTEN | head -1))"; exit 0; }
  sleep 1
done
echo "the API did not answer /healthz within 60 s; see logs/api.out (it holds the sign-in link: read it yourself)"; exit 1
