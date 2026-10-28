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

## Phase 7: the final evaluation

One command per suite, `uv run --project backend python eval/run_final.py <suite>`, and `eval/run_final.sh` for all of them in order (one emulator of ours at a time). Each writes `results/final/<suite>.json` and `<suite>.md` with the commit (and whether it is the `eval-final` tag), the tier, and the model calls, tokens and dollars it caused (summed from `logs/model_costs.jsonl` by the suite's task-ID prefix). `run_final.py report` builds `results/final/report.md` and `results/final/charts/`.

| File | What |
| --- | --- |
| `run_final.py`, `run_final.sh` | The entry points |
| `final_common.py` | Suite metadata, cost attribution, saving |
| `final_core.py` | The core set as 10 parameterized tasks over seeded *worlds* (new bookings, past trips, balances); `compile` (source runs → routines, verified), `systems` (full agent, fixed replay, Envoy routines × 4 layouts × 3 seeds, up to 3 tries), `repeats` (first run vs 10 requests), `change` (new inputs; layouts 1–5: repair → trial → after → back), `sizes` (envoy-small, envoy-test, envoy-large, the phone) |
| `final_real.py` | The 18 real-app workflows (`run_real_apps.py`) with fresh agent runs and compiles |
| `final_memory.py` | Extraction on labeled emails, screens and screenshots; entity matching; stale facts served |
| `final_safety.py`, `capture_safety.py` | 20 irreversible controls and ~20 reversible ones on captured screens (code signals, the model's label, the gate); live declines on SkyLark; planted instructions on SkyLark's screens and in the test inbox |
| `final_interfaces.py` | The Phase 4 and 5 scripted checks through the API on the current commit |
| `final_report.py` | The report and its charts (matplotlib) |
