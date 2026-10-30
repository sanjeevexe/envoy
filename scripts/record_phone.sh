#!/bin/bash
# A full-resolution recording of the real phone's screen on this Mac, for the demo's takes (docs/demo-creator-workflow.md).
#
#   scripts/record_phone.sh                      # until Ctrl-C, into ~/Movies/Envoy takes/phone-<date>-<time>.mp4
#   scripts/record_phone.sh -o <file.mp4>        # somewhere else
#   scripts/record_phone.sh -f 30                # at most 30 fps (default 60)
#   kill <its pid>                               # stops it from another script (SIGTERM, like Ctrl-C)
#
# A second scrcpy beside Envoy's own: Envoy's uses its own server file (envoy-scrcpy-server.jar) and a random scid, so
# the two don't collide (checked Oct 30 during routine rehearsals: no errors; Envoy ran ~4 s slower at 60 fps, ~2 s at
# 30, since the phone encodes twice). This one is read-only
# (--no-control: it never sends a touch, key or clipboard), has no window and no audio, and records at the phone's own
# resolution (1080x2340 on the Pixel 5; --no-downsize-on-error makes it fail rather than quietly record smaller), up to
# 60 fps (scrcpy sends a frame only when the screen changes), 16 Mbit/s H.264.
#
# The Pixel 5's encoder tags its video as YCgCo although it is ordinary BT.601 (devices/scrcpy.py found the same), which
# FFmpeg refuses to convert and editors may show in the wrong colours; after the recording stops, the tag is rewritten to
# BT.601 without re-encoding (a few seconds). The untouched file is kept as <name>.raw.mp4 if that step fails.
set -uo pipefail
OUT=""
FPS=60
while [ $# -gt 0 ]; do
  case "$1" in
    -o) OUT="$2"; shift 2 ;;
    -f) FPS="$2"; shift 2 ;;
    *) echo "usage: $0 [-o file.mp4] [-f fps]" >&2; exit 2 ;;
  esac
done
ADB=${ADB:-$(command -v adb || echo "$HOME/Library/Android/sdk/platform-tools/adb")}
SERIAL=${ANDROID_SERIAL:-$("$ADB" devices | awk 'NR>1 && $2=="device" && $1 !~ /^emulator-/ {print $1; exit}')}
[ -n "$SERIAL" ] || { echo "no real phone connected over adb" >&2; exit 1; }
if [ -z "$OUT" ]; then
  mkdir -p "$HOME/Movies/Envoy takes"
  OUT="$HOME/Movies/Envoy takes/phone-$(date +%Y%m%d-%H%M%S).mp4"
fi
RAW="${OUT%.*}.raw.${OUT##*.}"
echo "recording $SERIAL into $OUT (Ctrl-C, or kill $$, stops and saves it)"
# In the background so this script gets the signal and passes it on as SIGTERM, which scrcpy treats like Ctrl-C (a
# background job of a script ignores SIGINT itself, so `kill -INT` would never reach it).
scrcpy --serial="$SERIAL" --no-window --no-control --no-audio --no-downsize-on-error --max-fps="$FPS" --video-bit-rate=16M \
  --record="$RAW" &
pid=$!
trap 'kill -TERM $pid 2>/dev/null' INT TERM
wait $pid
wait $pid 2>/dev/null  # the first wait returns as soon as a signal is trapped; this one waits for scrcpy to finish the file
if ffmpeg -loglevel error -y -i "$RAW" -c copy -bsf:v h264_metadata=matrix_coefficients=6 "$OUT"; then
  rm -f "$RAW"
  echo "saved $OUT ($(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 "$OUT"), $(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT" | cut -d. -f1) s)"
else
  echo "the colour tag couldn't be rewritten; the recording is $RAW" >&2
  exit 1
fi
