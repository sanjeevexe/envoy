# eval

Task sets, injected UI changes, runners and reports. `fixtures/phase0/` holds the emulator screens captured in Phase 0 for the Meta API check.

| File | What |
| --- | --- |
| `skylark_tasks.py`, `run_skylark.py` | Phase 1: the 13-task agent set and runner |
| `skylark_routines.py` | Phase 2: routine families (check-in, seat change, known traveler number, gate, flight status, trip lookup) and a booking generator for new inputs |
| `run_routines.py` | Phase 2: record source runs, compile + verify, new inputs, injected changes (patch → trial → active or rollback), baselines |
| `baselines.py` | Fixed replay (recorded coordinates + screen-similarity check, like Mobilerun macros) |
| `tune_locators.py` | Locator thresholds tuned on SkyLark screens from all layouts, with and without IDs |
| `run_matching.py` | Request → routine matching set |
| `run_real_apps.py` | The real-app test set on envoy-real (read-only): 18 workflows across shopping, food, Google's apps, maps, media and the web, each scored at first run, compile, same-input rerun and new-input rerun, against ground truth where there is one. `--regression` after any routines change (no agent runs, cached compile answers: 0 model calls unless a repair runs). Results: `results/real_apps/report.md` |
| `run_phase2.sh`, `routines_report.py` | The whole Phase 2 evaluation and its report (`results/phase2/report.md`) |
