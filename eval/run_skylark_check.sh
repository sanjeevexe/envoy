#!/bin/bash
# The SkyLark check of an agent change, as one command: compile, the agent and routine arms (1 seed × 4 layouts), 9 more
# check-ins on the original layout (where Home's card for the next trip has its own Check in), and the planted-text
# suite, on a given commit in its own worktree, written to eval/results/skylark_check_<date>[_<label>]/ there.
#
#   eval/run_skylark_check.sh <commit> [label]          # about 35 min on envoy-test
#   PREPARE_ONLY=1 eval/run_skylark_check.sh <commit>   # the worktree and its environment only
#
# Like eval/run_real_rerun.sh: the key is checked first, envoy-test is claimed through ~/Desktop/Envoy/coord/devices.sh
# as phase7 and released at the end, whatever happens. SkyLark's state is read before anything runs (each suite then
# seeds its own world; nothing left on the device is relied on).
set -uo pipefail
COMMIT=${1:?usage: $0 <commit> [label]}
LABEL=${2:-}
MAIN=/Users/sanjeevvarma/Desktop/Envoy
WT=/Users/sanjeevvarma/Desktop/Envoy-skycheck
COORD=$MAIN/coord/devices.sh
OUT_NAME="skylark_check_$(date +%Y-%m-%d)${LABEL:+_$LABEL}"
HERE=$(cd "$(dirname "$0")/.." && pwd)

git -C "$MAIN" rev-parse --verify -q "$COMMIT^{commit}" >/dev/null || { echo "no commit $COMMIT"; exit 2; }
if [ -d "$WT" ]; then
  [ -z "$(git -C "$WT" status --porcelain --untracked-files=no)" ] || { echo "$WT has uncommitted changes; clean it first"; exit 2; }
  git -C "$WT" checkout -q --detach "$COMMIT"
else
  git -C "$MAIN" worktree add -q --detach "$WT" "$COMMIT"
fi
cd "$WT"
for link in .env logs testapps/skylark/app/build; do
  [ -L "$link" ] && continue
  [ -e "$link" ] && { echo "$WT/$link exists and is not a link; remove it first"; exit 2; }
  mkdir -p "$(dirname "$link")" && ln -s "$MAIN/$link" "$link"
done
echo "worktree $WT at $(git rev-parse --short HEAD) ($(git log -1 --format=%s | cut -c1-70))"
if [ -n "${PREPARE_ONLY:-}" ]; then
  (cd backend && uv sync -q) && echo "prepared (no key check, no device)"; exit 0
fi

uv run --project backend python "$HERE/scripts/check_model_key.py" || { echo "the model key fails: no run"; exit 3; }

source scripts/env.sh >/dev/null
export GRPC_VERBOSITY=ERROR
"$COORD" claim envoy-test phase7 60 "SkyLark check on $(git rev-parse --short HEAD)${LABEL:+ ($LABEL)}" || { echo "envoy-test claim refused: ask the coordinator"; exit 4; }
trap 'scripts/stop_emulator.sh envoy-test >/dev/null 2>&1; "$COORD" release envoy-test phase7' EXIT
pgrep -f "qemu-system.*-avd envoy-test( |$)" >/dev/null || scripts/start_emulator.sh envoy-test || { echo "envoy-test did not start"; exit 5; }
adb devices | grep -q "^emulator-5554" || { echo "envoy-test is not on adb"; exit 5; }
uv run --project backend python - <<'PY'
from testapps.skylark import SkyLark
s = SkyLark("emulator-5554").state()
print("SkyLark before the check: signed_in", s.get("signed_in"), "| trips", len(s.get("trips") or []), "| variant", s.get("variant"))
PY

F="uv run --project backend python eval/run_final.py"
mkdir -p "logs/$OUT_NAME"
run() {
  local name=$1; shift
  echo "== $(date '+%H:%M') $name"
  $F "$@" > "logs/$OUT_NAME/$name.log" 2>&1; echo "   exit $? ($(date '+%H:%M'))"
  grep -E "^(saved|FAIL|REJECT|error|Traceback)" "logs/$OUT_NAME/$name.log" | head -6
}
run compile compile
run systems systems --systems agent,routine --seeds 1
for k in 1 2 3; do run checkin-extra-$k systems --systems agent --tasks check_in --layouts 0 --tries 1 --append --name systems-checkin-extra; done
run injection injection --parts screens

mkdir -p "eval/results/$OUT_NAME"
for f in compile systems systems-checkin-extra injection; do cp eval/results/final/$f.json eval/results/final/$f.md "eval/results/$OUT_NAME/" 2>/dev/null; done
git checkout -q -- eval/results/final && git clean -fdq eval/results/final
echo "results: $WT/eval/results/$OUT_NAME/ (not committed)"
