#!/usr/bin/env bash
# Start an Envoy emulator headless and wait until it has booted.
#
#   scripts/start_emulator.sh envoy-test            # headless, console 5554, gRPC 8554
#   scripts/start_emulator.sh envoy-real            # headless, console 5556, gRPC 8556
#   scripts/start_emulator.sh envoy-real --window   # with a window (for sign-ins)
#   scripts/start_emulator.sh envoy-small           # Phase 6: a smaller screen (720x1280, 320 dpi), console 5558, gRPC 8558
#
# envoy-test: snapshots allowed (the agent saves and loads named snapshots); quick-boot
#   state is not saved on exit, so every run starts from the same default boot.
# envoy-real: always a cold boot with snapshots off (-no-snapshot). Its state lives only
#   in userdata, like a real phone that restarts. It is never restored to an old snapshot.
set -euo pipefail
source "$(dirname "$0")/env.sh"

AVD="${1:?usage: $0 envoy-test|envoy-real|envoy-small [--window]}"
WINDOW="${2:-}"

case "$AVD" in
  envoy-test) CONSOLE=5554; GRPC=8554; SNAP=(-no-snapshot-save) ;;
  envoy-real) CONSOLE=5556; GRPC=8556; SNAP=(-no-snapshot) ;;
  envoy-small) CONSOLE=5558; GRPC=8558; SNAP=(-no-snapshot-save) ;;
  *) echo "unknown AVD: $AVD" >&2; exit 2 ;;
esac
SERIAL="emulator-$CONSOLE"

if pgrep -f "qemu-system.*-avd $AVD( |$)" >/dev/null; then
  if adb devices | grep -q "^$SERIAL"; then echo "$AVD already running as $SERIAL"; exit 0; fi
  echo "$AVD process exists but is not on adb (still shutting down?); try again shortly" >&2; exit 1
fi

# -grpc alone listens on every interface with no auth (measured in Phase 0), so anyone on the
# same Wi-Fi could control the phone. With -grpc-use-token it binds to 127.0.0.1 only and requires
# a per-launch token (grpc.token in the emulator's discovery file, read by backend/devices/emulator_grpc.py)
# as "authorization: Bearer <token>" metadata.
# -feature -WiFiPacketStream: emulator 37.2.12 crashed (double free in NetsimWifiTransport::readThread)
# on snapshot load in Phase 0; this keeps Wi-Fi in-process instead of going through netsim.
ARGS=(-avd "$AVD" -port "$CONSOLE" -grpc "$GRPC" -grpc-use-token -memory 4096 -no-audio -no-boot-anim
      -feature -WiFiPacketStream "${SNAP[@]}" ${EMULATOR_EXTRA_ARGS:-})
[ "$WINDOW" = "--window" ] || ARGS+=(-no-window)

LOG_DIR="$(cd "$(dirname "$0")/.." && pwd)/logs"
mkdir -p "$LOG_DIR"
nohup emulator "${ARGS[@]}" >"$LOG_DIR/emulator-$AVD.log" 2>&1 &
echo "Started $AVD (pid $!) as $SERIAL, gRPC on 127.0.0.1:$GRPC; log: logs/emulator-$AVD.log"

START=$(date +%s)
adb -s "$SERIAL" wait-for-device
until [ "$(adb -s "$SERIAL" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; do
  sleep 1
  if [ $(( $(date +%s) - START )) -gt 300 ]; then echo "boot timed out" >&2; exit 1; fi
done
echo "$AVD booted in $(( $(date +%s) - START ))s"
