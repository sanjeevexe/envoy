#!/usr/bin/env bash
# The rest of eval/run_phase2.sh after the original-layout, next-trip and extra-screen compiles, with resets through
# SkyLark's fixture hook (ENVOY_RESET=fixtures) after the emulator hung twice on snapshot restores in one session.
cd "$(dirname "$0")"
export GRPC_VERBOSITY=ERROR ENVOY_RESET=fixtures
R="uv run --project ../backend python run_routines.py"

rm -rf results/phase2/library-v4
$R compile --tag=-v4 --src-variant 4 --reuse-spec
uv run --project ../backend python run_matching.py
$R new-inputs --k 5
$R variants --variants 1,2,3,4,5
$R variants --families check_in_next --variants 1,2,3 --append
$R variants --tag=-v3 --src-variant 3 --families check_in --variants 0
$R new-inputs --tag=-v4 --src-variant 4 --k 3
$R variants --tag=-v4 --src-variant 4 --variants 5
$R baselines --variants 0 --systems routine
$R baselines --families gate,flight_status,find_trip --variants 0,1,2,3 --systems fixed
$R baselines --variants 4,5 --systems agent,fixed
uv run --project ../backend python routines_report.py > /dev/null
echo "report: eval/results/phase2/report.md"
