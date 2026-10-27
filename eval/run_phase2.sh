#!/usr/bin/env bash
# Phase 2 final evaluation on SkyLark Air (envoy-test), all on the final code. Model calls use the standard tier.
#
#   eval/run_phase2.sh            # about 40 minutes; writes eval/results/phase2/*.json, then report.md
#
# The source agent runs (record) are not repeated here: the routines are recompiled from the same traces with the
# final compiler, reusing Wonder's cached answers where the cleaned steps are unchanged (no model cost).
cd "$(dirname "$0")"
export GRPC_VERBOSITY=ERROR
R="uv run --project ../backend python run_routines.py"

rm -rf ../data/routines                                                   # the library is rebuilt from scratch
$R compile --reuse-spec                                                   # 6 families, original layout
$R compile --families check_in_next --reuse-spec                          # the next-trip-only routine (Phase 1 trace)
$R compile --tag=-v3 --src-variant 3 --families check_in                  # fresh Wonder answer: the cleaned steps changed
$R compile --tag=-v4 --src-variant 4 --reuse-spec                         # compiled with IDs hidden
uv run --project ../backend python run_matching.py

$R new-inputs --k 5                                                       # 30 runs on bookings never seen
$R variants --variants 1,2,3,4,5                                          # 30 injected-change experiments
$R variants --families check_in_next --variants 1,2,3 --append            # replace patches (the Home button is gone in v1)
$R variants --tag=-v3 --src-variant 3 --families check_in --variants 0    # remove patches (the review screen is gone in v0)
$R new-inputs --tag=-v4 --src-variant 4 --k 3                             # IDs hidden: new bookings
$R variants --tag=-v4 --src-variant 4 --variants 5                        # IDs hidden, then labels renamed

$R baselines --variants 0 --systems routine                               # routine cells for the comparison (v1-5 come from variants)
$R baselines --families gate,flight_status,find_trip --variants 0,1,2,3 --systems fixed
$R baselines --variants 4,5 --systems agent,fixed

uv run --project ../backend python routines_report.py > /dev/null
echo "report: eval/results/phase2/report.md"
