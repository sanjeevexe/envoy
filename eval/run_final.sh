#!/usr/bin/env bash
# Phase 7: every suite of the final evaluation, in order, on the current commit (tag it eval-final first), one emulator
# of ours at a time (the AndroidWorld chat may hold the second slot).
#
#   git tag eval-final && eval/run_final.sh            # about 4.5 hours; then eval/results/final/report.md
#   eval/run_final.sh --from real                       # resume at a step: compile systems tiers repeats change injection
#                                                       # safety memory interfaces small large real phone report
#
# The API on :8700 is restarted on this commit for the interface checks (your sign-in survives: its token file is kept);
# with several sessions on this Mac, tell the coordinator before starting. The model key is checked first (a failing key
# stops the run before any device time). Each device is claimed through the coordinator's locks (~/Desktop/Envoy/coord/
# devices.sh, owner phase7) before it is started, and released when the run moves on; without that folder the script
# runs as before. Standard tier throughout (reported dollars are always at standard prices). The model profile is the
# adapter's default unless ENVOY_MODEL_PROFILE is set; it is printed here and recorded in every suite's results.
set -uo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh >/dev/null
export GRPC_VERBOSITY=ERROR
F="uv run --project backend python eval/run_final.py"
LOG=logs/final; mkdir -p "$LOG"
FROM="${2:-compile}"; [ "${1:-}" = "--from" ] || FROM=compile
STEPS=(compile systems tiers repeats change injection safety memory interfaces small large real phone report)
started=0
COORD=${ENVOY_COORD:-$HOME/Desktop/Envoy/coord/devices.sh}
held=""  # the device this run holds a lock on

step() {  # step <name>: true once the resume point is reached
  [ "$1" = "$FROM" ] && started=1
  [ $started = 1 ]
}

ours() { pgrep -fl "qemu-system.*-avd envoy-" | sed -E 's/.*-avd (envoy-[a-z]+).*/\1/' | sort -u; }

claim() {  # claim <device> <minutes>: release the device held before, wait for this one, take it (no locks: nothing)
  [ -x "$COORD" ] || return 0
  [ "$held" = "$1" ] && { "$COORD" extend "$1" phase7 "$2" >/dev/null; return 0; }
  [ -n "$held" ] && "$COORD" release "$held" phase7
  held=""
  "$COORD" wait "$1" phase7 && "$COORD" claim "$1" phase7 "$2" "final evaluation on $(git rev-parse --short HEAD), ${PROFILE%% *} profile" \
    || { echo "could not claim $1: ask the coordinator"; exit 4; }
  held=$1
}
trap '[ -n "$held" ] && [ -x "$COORD" ] && "$COORD" release "$held" phase7' EXIT

only() {  # only <avd>: stop our other emulators cleanly, claim <avd>, wait for a free slot, start it
  for a in $(ours); do [ "$a" != "$1" ] && scripts/stop_emulator.sh "$a"; done
  claim "$1" 240
  until [ "$(pgrep -f qemu-system | wc -l | tr -d ' ')" -lt 2 ] || pgrep -f "qemu-system.*-avd $1( |$)" >/dev/null; do
    echo "two emulators are running (one is not ours); waiting for a slot..."; sleep 60
  done
  scripts/start_emulator.sh "$1"
}

uv run --project backend python scripts/check_model_key.py || { echo "the model key fails: no run"; exit 3; }
PROFILE=$(uv run --project backend python -c 'import os; from models.adapter import JOBS, WONDER, active_profile, model_for
p = active_profile(); print(p, "(" + ("ENVOY_MODEL_PROFILE" if os.environ.get("ENVOY_MODEL_PROFILE", "").strip() else "the adapter default") + "; Muse Wonder for",
      ", ".join(sorted(j for j in JOBS if model_for(j, p) == WONDER)) or "no job", end=")")') || { echo "unknown model profile: no run"; exit 3; }
echo "model profile: $PROFILE"

run() {  # run <log name> <args...>
  local name=$1; shift
  echo "== $(date '+%H:%M') $name"
  $F "$@" 2>&1 | tee "$LOG/final-$name.log" | grep -E "^(saved|SKIP|FAIL|error)" || true
}

git describe --exact-match --tags HEAD 2>/dev/null | grep -qx eval-final || echo "note: HEAD is not tagged eval-final; these are measurements, not the final numbers"

if step compile; then only envoy-test; run compile compile; fi
if step systems; then only envoy-test; run systems systems; fi
if step tiers; then only envoy-test; run tiers systems --systems agent --layouts 0 --seeds 1 --tries 1 --contributor --name systems-contributor; fi
if step repeats; then only envoy-test; run repeats repeats; fi
if step change; then only envoy-test; run change change; run sizes-test sizes --device envoy-test; fi
if step injection; then only envoy-test; run injection injection; fi
if step safety; then only envoy-test; run safety safety; fi
if step memory; then only envoy-test; run memory memory; fi
if step interfaces; then only envoy-test; run interfaces interfaces --restart-api; fi
if step small; then only envoy-small; run sizes-small sizes --device envoy-small; fi
if step large; then only envoy-large; run sizes-large sizes --device envoy-large; fi
if step real; then only envoy-real; run real real; scripts/stop_emulator.sh envoy-real; fi
if step phone; then
  if adb devices | awk 'NR>1 && $2=="device" && $1 !~ /^emulator-/' | grep -q .; then claim pixel5 30; run sizes-phone sizes --device phone
  else echo "no real phone connected: skipping the phone"; fi
fi
if step report; then run report report; fi
if [ -x "$COORD" ]; then
  [ -n "$held" ] && "$COORD" release "$held" phase7; held=""   # other sessions are waiting for the devices
else
  only envoy-test >/dev/null 2>&1 || true   # leave the test phone up for the demo
fi
echo "done: eval/results/final/report.md"
