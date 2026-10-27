# routines

App routines (design doc, App routines): one successful agent run compiled into a small program with inputs, code checks before and after every step, element-based locators, and local self-repair saved as versioned patches. Reruns make no model calls while every check passes.

| File | What |
| --- | --- |
| `model.py` | The format: `Routine`, `Step`, `Locator`, `Check`, `StepAction`, `Extract`, `InputSpec`; `{{slot}}` templating; YAML in the design doc's shape (single-key checks and actions). |
| `locators.py` | Multi-attribute scoring (resource ID, label, description, field label, type, parent and sibling text, list membership, position). STRICT 0.80 / RELAXED 0.60 / MARGIN 0.08, tuned on SkyLark (`eval/tune_locators.py`). `text_has` is a hard filter for input-based choices; data in IDs becomes a glob (`trip_row_*`). Role `check` needs text evidence and the same element type. |
| `checks.py` | Checks evaluated in code (app in front, element present or absent, text visible, field value, toggle state, screen changed, signature similarity) and written automatically by diffing a step's before and after trees. |
| `compiler.py` | Trace → routine: confirm success, clean up (pop-ups, dead taps, back-tracks; scrolls become `scroll_until`), generalize with Muse Wonder (inputs, fixed text, booking data, outputs), add checks, input witness checks, and `verify()` by replay. |
| `executor.py` | Runs a routine: wait for before-checks (5 s), locate, act through the policy gate, settle on the after-checks themselves. Fallback ladder: wait and retry → relaxed match → pop-up handler → local repair (≤2 model calls per step, ≤5 per run) → full agent → ask the user. Proposes patches (new locator, updated check, inserted, replaced or removed steps). |
| `store.py` | The library in `data/routines/<name>/`: versions, trial → active or rejected (rollback), run history, the recompile flag (more than half of the last 6 runs failed), patch evidence with before/after screenshots. |
| `matcher.py` | Request → routine: app, intent patterns, description similarity, then one Muse Spark call that confirms and fills inputs from the request and notes (values must appear there). |

## Run it

```bash
uv run --project backend python scripts/compile_routine.py <task_id>          # compile one trace and print the YAML
uv run --project backend python eval/run_routines.py record|compile|new-inputs|variants|baselines
uv run --project backend python eval/run_matching.py
uv run --project backend python eval/routines_report.py                      # eval/results/phase2/report.md
```
