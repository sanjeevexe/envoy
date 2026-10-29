#!/usr/bin/env bash
# Runs ON the VM, from ~/envoy (scripts/cloud/clip.sh copies it and starts it): a screen recording of envoy-test during
# three SkyLark routines (unmeasured: the recorder takes CPU), plus a timestamped terminal transcript for the clip.
#
# Writes ~/envoy/eval/results/cloud/clip/{emulator.mp4,terminal.tsv}: each transcript line is "<seconds since the
# recording started>\t<text>". Nothing personal: the instance's name, zone and machine type come from the metadata
# server, with the project's path stripped.
set -uo pipefail
OUT=eval/results/cloud/clip
SERIAL=emulator-5554
mkdir -p "$OUT"
md() { curl -s -H Metadata-Flavor:Google "http://metadata.google.internal/computeMetadata/v1/instance/$1" | sed 's|.*/||'; }

adb -s "$SERIAL" shell rm -f /sdcard/cloud-clip.mp4
adb -s "$SERIAL" shell screenrecord --time-limit 45 --bit-rate 6000000 /sdcard/cloud-clip.mp4 &
REC=$!
START=$(date +%s.%N)
stamp() { awk -v s="$START" '{ c = "date +%s.%N"; c | getline t; close(c); printf "%.1f\t%s\n", t - s, $0; fflush() }'; }
{
  echo "\$ curl metadata.google.internal …/instance/{name,zone,machine-type}"
  echo "instance $(md name) · zone $(md zone) · $(md machine-type)"
  echo "\$ hostname -s; uname -m; nproc"
  echo "$(hostname -s) · $(uname -m) · $(nproc) vCPU"
  echo "\$ adb devices    # the VM's own adb server and emulator"
  adb devices | sed -n '2p'
  echo "\$ uv run python eval/run_phase6.py portability --device envoy-test --families check_in,change_seat,gate --k 1"
  uv run --project backend python eval/run_phase6.py portability --device envoy-test --no-control --k 1 \
    --families check_in,change_seat,gate --name clip 2>&1 | grep --line-buffered -E '^(PASS|FAIL|==)' | stdbuf -oL cut -c1-120
} | stamp > "$OUT/terminal.tsv"
wait "$REC"
adb -s "$SERIAL" pull /sdcard/cloud-clip.mp4 "$OUT/emulator.mp4" >/dev/null
adb -s "$SERIAL" shell rm -f /sdcard/cloud-clip.mp4
ls -l "$OUT"
