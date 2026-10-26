#!/usr/bin/env bash
# Generate Python gRPC stubs from the emulator_controller.proto that ships with the emulator.
# Output: backend/devices/grpc_gen/ (committed, so a fresh clone works without regenerating).
set -euo pipefail
source "$(dirname "$0")/env.sh"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PROTO_DIR="$ANDROID_HOME/emulator/lib"
OUT="$REPO/backend/devices/grpc_gen"
cd "$REPO/backend"
uv run python -m grpc_tools.protoc -I"$PROTO_DIR" \
  --python_out="$OUT" --grpc_python_out="$OUT" --pyi_out="$OUT" \
  "$PROTO_DIR/emulator_controller.proto"
# protoc writes absolute imports; make them package-relative.
sed -i '' 's/^import emulator_controller_pb2 as/from . import emulator_controller_pb2 as/' "$OUT/emulator_controller_pb2_grpc.py"
grep -E '^(Pkg.Revision|emulator)' "$ANDROID_HOME/emulator/source.properties" > "$OUT/EMULATOR_VERSION" || true
echo "Generated stubs in $OUT from $(grep Pkg.Revision "$ANDROID_HOME/emulator/source.properties")"
