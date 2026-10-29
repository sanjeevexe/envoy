#!/bin/bash
# The real-app pass on any commit, as one command: fresh agent runs and compiles of the read-only workflows on envoy-real
# (Target is left out: its bot check blocks emulators), written to eval/results/real_rerun_<date>[_<label>]/ in a
# worktree of that commit. Used to judge a branch before it merges (the bar: no workflow worse than main's last pass).
#
#   eval/run_real_rerun.sh <commit> [label]      # e.g. eval/run_real_rerun.sh 425f12e aw-final
#   PREPARE_ONLY=1 eval/run_real_rerun.sh <commit> # step 1 only, and the backend environment built (no API, no device)
#   HELD=1 eval/run_real_rerun.sh <commit> <label> # envoy-real already claimed by the caller (passes back to back)
#   WORKFLOWS=contacts_count eval/run_real_rerun.sh <commit> <label>   # only some workflows (repeats of one)
#
# What it does, in order (stops at the first failure):
#  1. A worktree of <commit> at ~/Desktop/Envoy-realrun (detached; reused if it exists and is clean), with .env, logs and
#     data/gmail linked from the main checkout before anything runs there (Gmail's answers need the test account's token).
#  2. The model key check (scripts/check_model_key.py): no device time on a failing key.
#  3. envoy-real claimed through ~/Desktop/Envoy/coord/devices.sh as phase7 (refused: stop, ask the coordinator), cold-booted
#     (never a snapshot), the pass run, envoy-real stopped with scripts/stop_emulator.sh and released.
set -uo pipefail
COMMIT=${1:?usage: $0 <commit> [label]}
LABEL=${2:-}
MAIN=/Users/sanjeevvarma/Desktop/Envoy
WT=/Users/sanjeevvarma/Desktop/Envoy-realrun
COORD=$MAIN/coord/devices.sh
OUT_NAME="real_rerun_$(date +%Y-%m-%d)${LABEL:+_$LABEL}"
ONLY=${WORKFLOWS:-amazon,starbucks,chipotle,doordash,doordash_search,settings_version,settings_bluetooth,gmail_newest,gmail_search,calendar_today,contacts_count,maps_address,play_rating,youtube_search,ytmusic_artist,chrome_wikipedia}
HERE=$(cd "$(dirname "$0")/.." && pwd)

# 1. The worktree.
git -C "$MAIN" rev-parse --verify -q "$COMMIT^{commit}" >/dev/null || { echo "no commit $COMMIT"; exit 2; }
if [ -d "$WT" ]; then
  [ -z "$(git -C "$WT" status --porcelain --untracked-files=no)" ] || { echo "$WT has uncommitted changes; clean it first"; exit 2; }
  git -C "$WT" checkout -q --detach "$COMMIT"
else
  git -C "$MAIN" worktree add -q --detach "$WT" "$COMMIT"
fi
cd "$WT"
for link in .env logs data/gmail; do
  [ -L "$link" ] && continue
  [ -e "$link" ] && { echo "$WT/$link exists and is not a link; remove it first"; exit 2; }
  mkdir -p "$(dirname "$link")" && ln -s "$MAIN/$link" "$link"
done
echo "worktree $WT at $(git rev-parse --short HEAD) ($(git log -1 --format=%s | cut -c1-70))"
if [ -n "${PREPARE_ONLY:-}" ]; then
  (cd backend && uv sync -q) && echo "prepared (no key check, no device)"; exit 0
fi

# 2. The key.
uv run --project backend python "$HERE/scripts/check_model_key.py" || { echo "the model key fails: no run"; exit 3; }

# 3. The device and the pass.
source scripts/env.sh >/dev/null
export GRPC_VERBOSITY=ERROR
if [ -z "${HELD:-}" ]; then  # HELD=1: the caller holds envoy-real across several passes, and stops and releases it after
  "$COORD" claim envoy-real phase7 90 "real-app rerun on $(git rev-parse --short HEAD)${LABEL:+ ($LABEL)}" || { echo "envoy-real claim refused: ask the coordinator"; exit 4; }
  release() { scripts/stop_emulator.sh envoy-real >/dev/null 2>&1; "$COORD" release envoy-real phase7; }
  trap release EXIT
fi
pgrep -f "qemu-system.*-avd envoy-real( |$)" >/dev/null || scripts/start_emulator.sh envoy-real || { echo "envoy-real did not start"; exit 5; }
adb devices | grep -q "^emulator-5556" || { echo "envoy-real is not on adb"; exit 5; }
mkdir -p logs/real_rerun
echo "== $(date '+%H:%M') real-app pass: $ONLY"
uv run --project backend python eval/run_final.py real --only "$ONLY" > "logs/real_rerun/$OUT_NAME.log" 2>&1
echo "   exit $? ($(date '+%H:%M'))"
grep -E "^(saved|error|Traceback)" "logs/real_rerun/$OUT_NAME.log" | tail -3

# The results, beside the frozen ones (eval/results/final/real.* goes back to the commit's own copy).
mkdir -p "eval/results/$OUT_NAME"
cp eval/results/final/real.json eval/results/final/real.md "eval/results/$OUT_NAME/"
cp -R eval/results/final/real_compiled "eval/results/$OUT_NAME/"
git checkout -q -- eval/results/final && git clean -fdq eval/results/final
sed -n '3,12p' "eval/results/$OUT_NAME/real.md"
echo "results: $WT/eval/results/$OUT_NAME/ (not committed)"
