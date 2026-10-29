# Routine and matcher fixes (Oct 28)

Branch `claude/routine-matcher-fixes-af80bc`: 547e854 (fixes and tests), the measurement script, and d50c217 (merge of
`claude/intelligent-poitras-dce98e`, the AndroidWorld routine-bug fixes, so the two land together). Not merged into main
and not pushed. Tests: `uv run --project backend pytest -q backend/tests` gives 251 passed, and `npm run build` in `web/` passes.

## 1. The matcher and vague wording

"a Caffè Latte on DoorDash" ran DoorDash's first-restaurant routine. Phase 7 never compiled a price routine.
`matcher.close_call` now catches this case. All three of these must hold:
- the model's pick scores above the shortlist floor;
- the request names nothing the pick does beyond its app;
- a runner-up within 0.15 reports different outputs.

When they do, no routine runs. `MatchResult.ambiguous` names both routines, and the runner logs a note and hands the
task to the agent ("name what you want back, e.g. the price"). The check runs in code, after the one match call, so it
adds no model cost.

Two cases are exempt:
- **Two routines that report the same thing** (SkyLark's two check-in versions): either one is fine.
- **A paraphrase below the floor** ("is SL 1190 on time"): the model's pick stands.

Tests:
- the latte request runs neither the first-restaurant routine nor a price routine placed next to it;
- requests that say "price" or "first restaurant" still run their routine;
- the SkyLark matching requests checked have no close calls.

## 2. Amazon and Play Store on a second input

**Amazon.** The compiled routine's product read was already wrong on its own learned screen: it read a search
suggestion ("Search for rechargable aa batteries"). Its price was the first `$x.xx ( $y /count)` in the list, so on a
new search the product and the price came from different rows.

The routine now reads outputs by row structure:
- **The product:** the first row under the "Results" heading, skipping the controls recorded above the title
  (`Extract.first_row` with `below` and `skip_labels`).
- **The price:** the first `$x.xx` inside the product's row, whatever that row's shape (`Extract.row_of`,
  `executor.in_row`, which walks the tree's parent links). "Limited time deal $8.49 …" is read as $8.49.

On the recorded "USB-C cable" screen, the result is now Anker at $9.99, both from the first row. Before, the routine
reported XIAWAO with Anker's $9.99.

**Play.** There were two causes:
- **The input:** Wonder's input example was the listing title "Duolingo: Learn Languages", so a second input became
  "Spotify: Learn Languages", which no listing matches. The compiler now shortens an example to the user's own word
  when the goal names only its head ("Duolingo").
- **The search:** the agent found Duolingo among the Search tab's suggestions and never searched. A list choice whose
  target is an input now types that input into the screen's search box when the list doesn't show it. It uses the
  field, or a "Search …" bar that opens one (not a one-word tab), and goes through the same policy gate as other
  actions. The scroll after it must then find the target.

Tests use the recorded traces and screens, with no model calls.

## 3. Chrome and Wikipedia: an output read from the screenshot

The article page has no accessibility tree, only the status bar. So the agent's answer couldn't be checked, and an
unverified run never compiled.

`compiler.screen_only` now admits a `done_unverified` run only when two things hold: its check failed because the words
were not visible, and its last screen has no app text. For such a run, the compiler reads each output from the
recorded last screenshot (`routines/screen_read.py`, one Muse Spark call), and keeps the output only if the read gives
the agent's answer.

The executor repeats the same check on every rerun (`screen_read.accept`):
- the value has the recorded shape (for a date, a year);
- the value is in the line the model quotes;
- the page names one of the inputs.

If a read fails, the executor scrolls and reads again, up to 6 times. A read that never passes fails the run; it is
never reported as an answer. Each read costs one model call, so this row can't be "rerun with no model call".

## Before and after on envoy-real

**Before:** `eval/results/real_pass_2026-10-28/real_pass.md` (frozen, not changed).
**After:** `eval/results/routine_fixes_2026-10-28/pass/` (Phase 7's second inputs) and `…/unseen/` (items no pass has
used: wireless mouse, Pinterest, Golden Gate Bridge).

AFTER_TABLE

## Spend

SPEND

## Not done / weak spots

- The close-call rule judges by words, so a request that names the right output in other words ("how much") still needs
  that word in the routine's patterns.
- The search fallback trusts the first editable field on screen. On a screen with a non-search field it could type
  into that field instead. The post-check after it (the target must be found) limits the damage.
- Screenshot outputs depend on Muse Spark reading the page, and they cost a call per read.
- The SkyLark "past trip" list-row case (Phase 7 completion) is on their branch `aw-rowfix` (183cc60). It touches
  different functions in compiler.py.
