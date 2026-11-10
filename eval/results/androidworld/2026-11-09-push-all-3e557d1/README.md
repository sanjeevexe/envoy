# AndroidWorld, all 116, round 4 (`3e557d1`), Nov 9–10 2026

**85 of 116 (73.3%); held-out half 44 of 58 (75.9%).** That's against the Nov 3 run on the same model, profile, cap and settings (`2026-11-03-hybrid-7ed4aa6`: 74 and 36): +15 −4 overall (p = 0.019) and +9 −1 on held-out (p = 0.021). Counting only episodes Envoy ended as done, it's 83 and 43 (held-out +8 −1, p = 0.039). Total cost $14.54, the same as Nov 3.

The write-up, with the changes, the per-task wins and losses, the mechanisms, the offline checks and the caveats, is in `docs/androidworld-results.md`, "Round 4".

## Setting
- **Envoy:** branch `claude/aw-push-853c98` at `3e557d1`. That is `main` `ed98762` plus the round's changes (`7eb4c97` … `3e557d1`). Every episode records this commit, with a clean `backend/`.
  - Between Nov 3's `7ed4aa6` and `ed98762` the only agent-side change is a Lyft-only policy rule, so this run against Nov 3's measures the round's changes.
  - `d91db22`, after this run, only relabels last-step dones as `done_unverified`. No decision or score changes.
- **Models:** the default `hybrid` profile, with plan, step and repair on Muse Wonder 1.0 and the rest on Spark 1.3. No `ENVOY_MODEL_*` was set. Every episode records profile `hybrid` and step model `muse-wonder-1.0`.
- **Run settings:** `low` effort and the shipped $0.50 per-task cap. Standard tier: `--config '{"tier":"standard"}'` is the run's only config.
- **AndroidWorld:** `55ddaf5`, all 116 tasks of seed 30 instance 0, pass@1, AndroidWorld's own step budgets and scoring.
- **Emulator:** AndroidWorldAvd (Pixel 6, API 33 arm64), cold-booted for the dev run before this one. AndroidWorld's setup had re-run then and restored 24 of 24 app snapshots.
- **adb:** the shared 5037 server with the `never_restart_the_adb_server` guard, `adb -s emulator-5560` only. No other device was attached.
- **When:** Nov 9 21:45 to Nov 10 00:16 ET, one session, no stops. There were no API retries, crash dialogs or harness exceptions.

## Files
- `run.json`: the setting and the session.
- `episodes/`: AndroidWorld's score joined with Envoy's record for each task.
- `traces/`: digests of Envoy's traces, which now keep each step's scroll report.
- `summary.json`: `report.py` on this stage.
- `compare_2026-11-03-hybrid-7ed4aa6.json`: `report.py 2026-11-03-hybrid-7ed4aa6 2026-11-09-push-all-3e557d1`.
- `comparison-2026-11-03-hybrid.json`: `eval/androidworld/compare_runs.py`. It holds the paired comparison by half, difficulty and app, cost and time, and mechanism counts from the traces.

## Publishing
This is on a branch, not on `main`, and nothing published changes. Using these numbers in the README or on the site waits for the user's OK.
