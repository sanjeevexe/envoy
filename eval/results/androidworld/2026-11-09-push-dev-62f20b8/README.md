# AndroidWorld dev half, round 4 tuning run (`62f20b8`), Nov 9 2026

**44 of 58 on the dev half**, against the Nov 3 run's 38 (+8 −2, p = 0.11), at $7.14 against $7.30. This is the half the changes were chosen on, so it isn't an estimate. The estimate is the held-out half of the final run (`2026-11-09-push-all-3e557d1`).

- **Code:** branch `claude/aw-push-853c98` at `62f20b8`, the round's first five changes. Same setting as the final run: hybrid, seed 30, pass@1, standard tier, the $0.50 cap. The cold boot re-ran AndroidWorld's setup, which restored 24 of 24 app snapshots; VLC's APK failed to install on arm64, as it always does.
- **What it led to:** three follow-ups, all on dev evidence:
  - `a66759d`: on the last step, done only when the screen shows it. 4 of 12 last-step dones here were guesses.
  - `0dec38c`: scroll reports count items new to the task.
  - `3e557d1`: row text only for row-sized containers.
- **Noise:** the final run's dev half on `3e557d1` got 41 (+3 −6 against this run).

Files as in the final run's folder: `episodes/`, `traces/`, `run.json`, `summary.json`, `comparison-2026-11-03-hybrid.json`.
