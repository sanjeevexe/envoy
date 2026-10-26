#!/usr/bin/env bash
# Shut an Envoy emulator down:  scripts/stop_emulator.sh envoy-test|envoy-real [--hard]
#
# Default is a clean Android shutdown (reboot -p), then wait for the emulator process to exit.
# `adb emu kill` is a hard power-off: Android can lose writes it has not flushed yet (measured in
# Phase 0: a settings value written seconds before was gone after restart). envoy-real must
# always stop cleanly; --hard is only for envoy-test or a hung emulator.
set -euo pipefail
source "$(dirname "$0")/env.sh"
AVD="${1:?usage: $0 envoy-test|envoy-real [--hard]}"
case "$AVD" in
  envoy-test) SERIAL=emulator-5554 ;;
  envoy-real) SERIAL=emulator-5556 ;;
  *) echo "unknown AVD: $AVD" >&2; exit 2 ;;
esac

running() { pgrep -f "qemu-system.*-avd $AVD( |$)" >/dev/null; }
running || { echo "$AVD is not running"; exit 0; }

if [ "${2:-}" = "--hard" ]; then
  adb -s "$SERIAL" emu kill >/dev/null 2>&1 || true
else
  adb -s "$SERIAL" shell sync >/dev/null 2>&1 || true
  adb -s "$SERIAL" shell reboot -p >/dev/null 2>&1 || true
fi
for _ in $(seq 1 90); do
  running || { echo "$AVD stopped"; exit 0; }
  sleep 1
done
echo "$AVD still running after 90s; forcing" >&2
adb -s "$SERIAL" emu kill >/dev/null 2>&1 || pkill -f "qemu-system.*-avd $AVD( |$)" || true
