#!/usr/bin/env bash
# AndroidWorld's emulator for Envoy, on its own ports so it never collides with Envoy's emulators
# (envoy-test 5554/8554, envoy-real 5556/8556, envoy-small 5558/8558).
#
#   eval/androidworld/emulator.sh start    # headless, console 5560, gRPC 8560 (token required), waits for boot
#   eval/androidworld/emulator.sh stop     # sync, then a clean shutdown so the main chat can use the slot
#   eval/androidworld/emulator.sh status
#
# AVD: AndroidWorldAvd, a Pixel 6 (1080x2400, 420 dpi) on API 33 Google APIs arm64 (AndroidWorld's setting; Google APIs,
# not Play, so `adb root` works, which AndroidWorld's setup and scoring need). -grpc-use-token binds gRPC to 127.0.0.1 and
# requires the per-launch token; eval/androidworld/aw_bridge.py passes it to android_env. Cold boot every time
# (-no-snapshot), as AndroidWorld's README launches it; its installed apps and data live in userdata and persist.
set -euo pipefail
source "$(dirname "$0")/../../scripts/env.sh"

AVD=AndroidWorldAvd
CONSOLE=5560
GRPC=8560
SERIAL="emulator-$CONSOLE"
LOG_DIR="$(cd "$(dirname "$0")/../.." && pwd)/logs"

case "${1:-status}" in
  start)
    if pgrep -f "qemu-system.*-avd $AVD( |$)" >/dev/null; then
      adb devices | grep -q "^$SERIAL" && { echo "$AVD already running as $SERIAL"; exit 0; }
      echo "$AVD process exists but is not on adb (still shutting down?)" >&2; exit 1
    fi
    mkdir -p "$LOG_DIR"
    nohup emulator -avd "$AVD" -port "$CONSOLE" -grpc "$GRPC" -grpc-use-token -memory 4096 -no-window -no-audio \
      -no-boot-anim -no-snapshot -feature -WiFiPacketStream ${EMULATOR_EXTRA_ARGS:-} >"$LOG_DIR/emulator-$AVD.log" 2>&1 &
    echo "Started $AVD (pid $!) as $SERIAL, gRPC 127.0.0.1:$GRPC; log: logs/emulator-$AVD.log"
    START=$(date +%s)
    adb -s "$SERIAL" wait-for-device
    until [ "$(adb -s "$SERIAL" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; do
      sleep 1
      [ $(( $(date +%s) - START )) -gt 400 ] && { echo "boot timed out" >&2; exit 1; }
    done
    echo "$AVD booted in $(( $(date +%s) - START ))s"
    ;;
  stop)
    adb -s "$SERIAL" shell sync || true
    adb -s "$SERIAL" emu kill || true
    for _ in $(seq 60); do pgrep -f "qemu-system.*-avd $AVD( |$)" >/dev/null || { echo "$AVD stopped"; exit 0; }; sleep 1; done
    echo "$AVD still running after 60 s" >&2; exit 1
    ;;
  status)
    pgrep -fl "qemu-system.*-avd $AVD( |$)" || echo "$AVD not running"
    ;;
  *) echo "usage: $0 start|stop|status" >&2; exit 2 ;;
esac
