# Routine repair fixes (Oct 28, 2026)

The four fixes from `prompts/routine-repair-fixes.md` (step 2), each with a test in `backend/tests/test_repair_fixes.py`.

## a. Starbucks calories with recent searches in the app

`starbucks_get_drink_calories` (`eval/results/final/real_compiled/starbucks.yaml`) tapped the recent search for the drink.
envoy-real's Starbucks now shows five recent searches, among them "Caffè Latte" and "Caffe Latte". The locator folds
accents, so the two tie, the match is ambiguous, and the step waited 5 s. Repair then tapped the recent search, which
opens the Results list. The step's after-check ("{{size_name}} Caffè Latte. Add to order", with `size_name`, which is not
an input) matched the list's "Add to order" button at the relaxed threshold, and the run ended "outputs not found:
calories".

The routine is now v2, repaired by hand:
- `search_drink_name` types the drink and presses Enter, and requires the Results list. Recent searches no longer matter.
- `find_open_drink_product` requires the Results list before it looks for the row: the typeahead's suggestions look
  like results while the search loads (run 4 below).
- `open_drink_product` requires the drink's own page: its title (a Text, where the list has a Button) and "Size options".

Device check on envoy-real, with the recent searches left in the app (`starbucks_device_check.json`):

| Run | Drink | Result | Model calls | Seconds |
| --- | --- | --- | --- | --- |
| 1 | Caffè Latte | 190 calories | 0 | 13.3 |
| 2 | Caffè Latte | 190 calories | 0 | 20.6 |
| 3 | Caffè Latte | 190 calories | 0 | 16.9 |
| 4 | Caramel Macchiato | 250 calories | 0 | 12.5 |

The only slower steps were the app's home screen at launch (`tap_order` waited, or scrolled to find Order). An earlier
Caramel Macchiato run (before the Results before-check) failed during a network outage. The results never loaded, the
typeahead was taken for them, and the repair call couldn't reach the API. That run is why `find_open_drink_product` now
needs the Results list.

## b. A repair that reaches the wrong screen is accepted

`executor._repair` accepted a screen whose after-checks held only at the relaxed threshold. Now a relaxed-only match
counts only when what comes next is on screen too: the next required step's before-checks and target (relaxed). After
the last step, its outputs must read and the routine's done-checks must hold. A step whose only after-check is "the
screen changed" needs the same evidence. The rung-2 shortcut "the after-checks failed but the next step is ready" now
also needs that next step to have an anchor. A scroll step, which has none, was "ready" on any screen.

Tests: the failed cross-app run replayed on the recorded screens now opens the drink's page (190 calories) instead of
stopping on the list. A repair onto a look-alike screen is rejected, and one onto a reworded screen whose next step is
there is still accepted. Both look-alike tests fail on main's executor.

## c. Repairs that change nothing mint new versions

`RoutineStore.propose` compares the patched routine with the one that ran, as saved (version bookkeeping aside). If they
are the same, it logs the attempt in the index (`patch_attempts`, result "unchanged") and makes no version or trial.
`after_run` reports `{"unchanged": n}`, and the API shows no note. Test: the repeats suite's `look_up_trip` v2–v4 are
identical to v1, as reported, and the same patch now leaves the library at v1.

## d. A check repair hard-coded an input

Re-run first, as asked: change_seat at layout 5 on main's code (`faf09f0`, the same booking: Omaha, 13C) kept
`{{trip_city}}` and `{{new_seat}}`. v2 holds no "Omaha" and no "Seat 13C" (`change_seat_L5_main.json`). The Oct 28
00:10 v2 came from a run that started at 23:49, two minutes before e875c4a (23:51). It doesn't happen on current code,
so no new guard was added. A test pins it down: a check bound to `{{trip_city}}`, and one whose rewrite would name the
run's value, both stay unpatched.

One thing noticed in that v2, not fixed: the `tap_change_seat` locator patch keeps the flight row's text ("SL 1834 · ATL
2:15 PM → OMA 5:25 PM") among its siblings. That's booking data in a soft attribute: it lowers the score a little on
other bookings, and the next run passed with no model call.

## The SkyLark change suite on this branch

`change_variants_branch.json`: the injected-UI experiments (10 tasks × layouts 1–5) rerun on this branch into a scratch
library, to check that b and c cost no recoveries. 50 experiments, 134 runs, all passed, 19 min, 4 model calls, $0.016.

| Layout | Recovered | Saved by | Model calls (first) | Patched (trial passed) | After, no model call | Back on original | Unchanged patches logged | Phase 7 (`final/change.md`) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1: moved button | 10/10 | nothing ×10 | 0 | 0 | 10/10 | – | 0 | same |
| 2: renamed labels | 10/10 | relaxed ×8, nothing ×2 | 0 | 8 (8/8) | 10/10 | 8/8 | 0 | same |
| 3: extra screen | 10/10 | nothing ×9, local repair ×1 | 1 | 1 (1/1) | 10/10 | 1/1 | 0 | same |
| 4: hidden IDs | 10/10 | relaxed ×7, nothing ×3 | 0 | **0** | 10/10 | – | **7** | 8 patched (8/8): no-op copies |
| 5: renamed + hidden IDs | 10/10 | relaxed ×6, local repair ×2, nothing ×2 | 3 | 8 (8/8) | 10/10 | 8/8 | 0 | same |

The one difference is c working: at layout 4 a relaxed match "updates" a locator to what it already was (the hidden ID
is kept), which Phase 7 saved as 8 new versions that each passed a trial. Now each is one line in `patch_attempts`. No
proposed version holds a run's input value in place of its `{{slot}}` (checked for every experiment).
