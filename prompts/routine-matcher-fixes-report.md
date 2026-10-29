# Routine and matcher fixes (Oct 28)

Branch `claude/routine-matcher-fixes-af80bc`: 547e854 (fixes and tests), the measurement script, 808bb4f and the final commit (fixes found live), and d50c217 (merge of
`claude/intelligent-poitras-dce98e`, the AndroidWorld routine-bug fixes, so the two land together). Not merged into main
and not pushed. Tests: `uv run --project backend pytest -q backend/tests` gives 253 passed, and `npm run build` in `web/` passes.

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

Run on envoy-real at 21:40–22:00, on commit 808bb4f, standard tier, every approval declined. Amazon and Play are
from the 21:53 pass, and Chrome from the 21:56 rerun after the compiler fix described below.

| Row | Before (real_pass_2026-10-28) | After: Phase 7's second input | After: an item no pass has used |
| --- | --- | --- | --- |
| amazon, same input (AA batteries) | pass (0 calls) | pass, 0 calls: PHILIPS AA 12 Pack, $9.99 | pass, 0 calls |
| amazon, new input | wrong value: XIAWAO with the $9.99 of the row above | **pass**, 0 calls: USB-C cable → Amazon Official USB-C cable, $14.99 (first row under Results, price from that row) | **pass**, 0 calls: wireless mouse → wegear USB Wireless Mouse, $9.99 |
| play_rating, same input (Duolingo) | pass (0 calls) | pass, 0 calls: 4.7 | pass, 0 calls: 4.7 |
| play_rating, new input | wrong value: "Spotify: Learn Languages" (no such app), Duolingo's 4.7 read | **pass**, 0 calls: Spotify 4.3 (34 million reviews) | **pass**, 0 calls: Pinterest 4.2 (10 million reviews) |
| chrome_wikipedia, compile | not compiled (unverified) | **compiled**: 5 steps, output opened_date read from the screenshot | compiled the same way |
| chrome_wikipedia, same input (Eiffel Tower) | – | pass, 3 calls (screenshot reads): 15 May 1889 | strict failed once (7 reads, never accepted), then passed: 15 May 1889 |
| chrome_wikipedia, new input | – | **pass**, 1 call: Statue of Liberty → October 28, 1886 | **pass**, 3 calls: Golden Gate Bridge → May 27, 1937 |

Chrome is listed by the harness as "pass after repair" because it counts any model call as a repair. These calls are
the screenshot reads; no step was repaired. Its answers are graded by truth (1889, 1886, 1937). Amazon's and Play's
answers were read against their screens while debugging: the Spotify card showed 4.3, and the USB-C row showed $14.99.

**What the first live run found, fixed in 808bb4f:**
- **Amazon, a badge above the title:** "Featured from Amazon brands" sat above the first result's title. The title is
  now, of the top three rows, the one that says most of the search, then the longest.
- **Amazon, a tapped suggestion:** the routine taps a recent-search suggestion, which a new term doesn't have. A tap on
  an input-named target that isn't found now searches for the term, and counts only if the step's after-checks then
  hold.
- **Play, the search box:** after the search, the input-named target matched the search box that shows only "Spotify".
  `executor.list_choice` now takes the top list row that names the term.
- **Play, sponsored ratings:** the results page shows a sponsored app's rating first. The rating is now read after the
  row that names the app (`Extract.card = {{app_name}}`, set by the compiler only when that read gives the recorded
  answer).

**And in the Chrome rerun:**
- The compiler dropped the screenshot output because the infobox screenshot shows no page title. A read is now refused
  only when a title is in view and names none of the inputs.
- A trailing scroll with nothing in the tree to stop at is dropped, because the screenshot read scrolls itself.
- These two changes were made after 808bb4f, in the final commit.

**Another session's test:** `test_repair_fixes.py`'s look-alike test now accepts the step reaching the drink's page by
searching, with no repair call, as well as the old repair path. The right answer (190 calories) is still required.

## Spend

$0.26 at standard prices, 31 model calls (logs/model_costs.jsonl: this pass's rp10282*- task prefixes and the probe runs). That is the Chrome Wonder compiles (two, about $0.02 each) and the screenshot reads. Amazon and Play made no calls. Tests are offline.

## Not done / weak spots

- The close-call rule judges by words, so a request that names the right output in other words ("how much") still needs
  that word in the routine's patterns.
- The search fallback trusts the first editable field on screen. On a screen with a non-search field it could type
  into that field instead. The post-check after it (the target must be found) limits the damage.
- Screenshot outputs depend on Muse Spark reading the page, and they cost a call per read.
- The SkyLark "past trip" list-row case (Phase 7 completion) is on their branch `aw-rowfix` (183cc60). It touches
  different functions in compiler.py.
