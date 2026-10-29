#!/usr/bin/env bash
# Run a script from eval/androidworld/ in AndroidWorld's own Python 3.11 venv (third_party/aw-venv), with AndroidWorld
# (third_party/android_world, not pip-installed) on the path. Envoy's backend stays on its own Python 3.13 venv.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
source "$ROOT/scripts/env.sh"
export PYTHONPATH="$ROOT/third_party/android_world:$HERE${PYTHONPATH:+:$PYTHONPATH}"
export GRPC_VERBOSITY=ERROR
script="$1"; shift
exec "$ROOT/third_party/aw-venv/bin/python" "$HERE/$script" "$@"
