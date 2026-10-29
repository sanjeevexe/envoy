# Aborted runs (kept for the record, not counted)

- `fixes1-dev-no-labels/` (2 episodes) and `check-apps-no-labels/` (1): the first dev run with the fixes, stopped after two
  episodes. Inside an episode the app index had no labels (android_env deletes ANDROID_HOME; Envoy's .env then gives
  "~/Library/Android/sdk" unexpanded, so aapt2 wasn't found), so `launch Files` failed in BrowserMaze. Fixed in the
  commit "Agent: app names are read from the phone even when ANDROID_HOME has a "~" …"; `../check-apps2/` is the same
  episode after the fix (launch Files opened Files at step 1). The dev run was then restarted from the start as `fixes1-dev`.
