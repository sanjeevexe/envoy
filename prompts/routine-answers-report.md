# Routines that run every step but give the wrong answer (Oct 29)

Branch `claude/routine-answers-d04bb1`, built on `aw-merge` (773536a, fast-forwarded from main 8b5e9c2). Not merged and not
pushed. Tests: `uv run --project backend pytest -q backend/tests` gives 293 passed (283 before, plus 10 new in
`test_routine_answers.py`), and `npm run build` in `web/` passes. Each new test fails on 773536a and passes here. No device
time was used. Model spend was $0.56: 11 Muse Wonder compiles, one per AndroidWorld source trace, cached as `spec.json`, so
every recompile and test since then runs offline.

This covers backlog items 1, 8 and 9. All the fixes are general: nothing in the code names an app, a task or AndroidWorld.

## Results

**The three question routines that answered 0/9 on new seeds (#8)** now read the agent's own answer on all 9 screens the
agent answered from on those seeds. The screens are recorded in `backend/tests/traces/androidworld/new_seeds/`. This is
offline: it doesn't cover the matcher filling the new input or the replay itself on a device.

| Task (source, seed 30) | Before (`aw-merge`) | After | New seeds 1–3 |
| --- | --- | --- | --- |
| NotesRecipeIngredientCount | `pattern: (?P<v>\d+/\d+\ cup)\s*spirulina`; the ingredient input is dropped | `ingredient_name` is an input; the value is read from the line that names `{{ingredient_name}}`, up to the ingredient | 2 teaspoons, 1/2 cup, 1/2 cup ✓ |
| NotesMeetingAttendeeCount | `pattern: (?P<v>\d+)\s*individuals\ were\ present` | `pattern: (?P<v>\d+)(?:\s+\D.*)?`: the first line of the note that starts with a number | 80, 45, 50 ✓ |
| SimpleCalendarLocationOfEvent | `event_location` with `expect_digits: true` | the same, without `expect_digits` | Virtual, The Coffee Bean, Sarah's apartment ✓ |

**The eight routines that finished every step and check yet scored 0 on their own seed (#1).** Recompiled offline from
their traces with the cached specs:

| Task | Before | After |
| --- | --- | --- |
| SimpleCalendarAnyEventsOnDate | no output ("not on the final screen"); the date input is dropped; the routine taps a recorded picture of "28" | `event_date` is an input. The tap is `date cell {{event_date:day}} in the {{event_date:month}} month grid`, located by grounding, with no picture. The answer is every event row of the day: "Game night, Product demo, Date night" |
| SimpleCalendarEventsOnDate | the first event row; no date input | the same as the previous row. On the October 28 screen it reads all three events |
| SimpleCalendarEventOnDateAtTime | the first event row ("Review session…"); no date or time input | the date and time are inputs. The answer is every row that shows `{{schedule_time:time24}}`: 8:00pm gives "Product demo", 10:15 am gives "Meeting with Bob", 6pm gives nothing |
| SimpleCalendarNextEvent | the first event row ("Call with Marketing"); the answer was "Board meeting" | **not compiled.** No fixed place on the screen holds "the next event after now", so the agent answers it |
| NotesIsTodo | the answer is "Convert to note" | "True" when the menu offers "Convert to note", else "False" |
| MarkorEditNote | never left the editor, so the note was not saved; the done-check passed on unsaved text; typed seed 30's note back in | leaves the editor and opens the file again, as the agent did, so the done-check sees the saved note. It types `{{text_to_add}}\n{{_field}}`, the field's own text on this run |
| SystemBrightnessMax (scored 0 with the routine from MaxVerify, reporting 0.0) | the routine from MaxVerify opened the slider and read it | MaxVerify's run is **not compiled** (brightness was already at its maximum). The run that dragged the slider compiles |
| MarkorCreateNoteAndSms (0.5) | the matcher filled `txt` and `Actions speak louder than words..` | the matcher writes values like the example: `.txt`, `…words.` |

The YAMLs are in `eval/results/routine_answers_2026-10-29/recompiled/`, the refused runs as `.refused.txt`. The reads are
in `recompile.json`.

## 1. Outputs tied to the source run (#8)

- **An input the goal names anchors the answer.** "What quantity of spirulina…": the answer's line holds the
  ingredient, so the extract is the element that shows `{{ingredient_name}}`, read up to that ingredient. That keeps
  Wonder's input, which used to be dropped as unused. The number-then-words pattern is not used when the words name an
  input. When a merged label holds several lines, which happens when the ingredient asked about is the recipe's first, the
  read takes the line that names the input.
- **A pattern keeps fixed words only when other rows repeat them.** Amazon's "$x ( $y /count)" repeats down the results,
  so it stays. "25 individuals were present" is the note's own sentence, so the pattern becomes the first list line that
  starts with a number of that shape.
- **`expect_digits` is set only for a number with at most one word**, judged on the value's first part: "190 calories",
  "$13.49", "2:05 PM · Group 5", "8am open". It is not set for "100 Main St Chicago".

## 2. Outputs dropped or meaningless (#1)

- **Plural answers read every row** (`Extract.every`). When the example is a list, or the output's name is plural, each
  value must lead a list row with the same ID and type. All such rows are read and joined with ", ". When the list holds
  other rows too, the input that every answer row shows, and no other row does, picks them.
- **Date and time inputs by part** (`routines/dates.py`, `{{name:part}}` in `model.py`). For the step whose intent names
  a date input, or that Wonder says chose by it, the parts become slots: day, month, mon, year, iso. A month grid's "28"
  then binds as `{{event_date:day}}`. The time part `time24` binds a "20:00" in a row to an input recorded as "8:00pm".
  These slots render from whatever the matcher filled ("October 24", or "tomorrow" through the existing date facts). A
  visual target with a slot drops its recorded picture.
- **Yes/no answers** (`Extract.answers`). When an answer of True/False/Yes/No was inferred from text on the screen, the
  routine reports the answer when that text is present and its opposite when it isn't.
- **Every output is read back on the run's own final screen, and dropped if it gives another value.** Before, it was
  kept with a warning. A question whose answer can't be read back isn't compiled (`NotCompilable`): it is left to the
  agent instead of answering wrongly.

## 3. Weak verification (#1, #9)

- **A run with nothing to do isn't compiled** (`compiler.degenerate`, checked before the Wonder call). There are three
  cases:
  - The goal asks for something irreversible at the start of a clause (delete, send, reply, share, pay, …), but no step
    was irreversible or approved.
  - Nothing changed (no typing, drag, irreversible step, or switch that flipped on its own screen), and the agent's answer
    says "already".
  - The goal turns or sets something on, off, to its max or min, and nothing changed.

  Of the 59 AndroidWorld sources the study compiled, 7 are refused (`degenerate_scan.json`): the black-garlic delete,
  Bluetooth on/off "Verify", brightness max/min "Verify", and Wi-Fi on/off "Verify". Every run that toggled, dragged or
  deleted still compiles.
- **Leaving an editor and opening the file again is not a back-track.** The back-track test now compares enabled states
  too: Markor's Save and Undo go from enabled to disabled when the note is saved. A Back that leaves the activity is never
  marked optional as "closes the keyboard".
- **Typing that keeps a field's text.** When the agent typed the field's previous text back around the input, the
  routine types `{{_field}}` there. The executor fills it with the field's text just before typing. The field's
  after-check uses the same slot, and the hint is dropped when it was the note's own text.

## What this costs on AndroidWorld's numbers

Four of the 22 verified routines are now refused. Across seeds they scored 3/3 (Bluetooth off), 3/3 (Bluetooth on), 3/3
(brightness max) and 1/3 (the black-garlic delete). AndroidWorld's `*Verify` tasks start in the state they ask for on
every seed (`system.py`: "Precondition: Screen brightness is at maximum"), so a routine that does nothing passes them. On
a phone where Bluetooth is off, the same routine would report success without turning it on. On `SystemBrightnessMax`,
whose instance starts at minimum, the do-nothing brightness routine reported `0.0` and scored 0. The agent did all 9 of
the Verify episodes. If AndroidWorld's routines are recompiled with this compiler, its "routine" column loses up to 9
successes on those tasks, and the 9 question episodes should become answerable.

## Nothing else changed

Every cached Wonder spec in `eval/results` (76, 74 with their trace on this Mac) was recompiled offline by `aw-merge`'s
compiler and by this one (`regression.json`). 70 come out identical, including all 10 of `final/compiled` (SkyLark) and
13 of the 14 in `final/real_compiled` that have a trace here. The other 4:
- Maps' street address (three copies) no longer has `expect_digits`: an address is not a number.
- Phase 2's old `compiled-v4/flight_status` is refused. Its output read "SL 1190" for a flight-status question, on its own
  screen. The current `final/compiled/flight_status` is unchanged.

### Real-app routines, compiled as the real-app eval compiles them

At the coordinator's request, every real-app spec was recompiled again, this time with each workflow's own memory
(`eval/run_real_apps.py`'s `WORKFLOWS`). The sets were Phase 7's `final/real_compiled`, `real_apps/compiled`, the Oct 28
real pass, and Session A's `routine_fixes_2026-10-28/{pass,unseen}`. Chrome's compile-time screenshot read was given the
same answer for both compilers. The results are in `real_apps.json`:
- **47 specs:** 42 compile identically, and 2 compile under neither compiler (Target has no compiled source run in
  Phase 7, and the real pass's YouTube source ended in an error).
- **None is newly refused.** No pattern changed, and no plural or yes/no extract appeared.
- **The 3 that differ are all Maps' `street_address`, which drops `expect_digits`.** Read on every tree of every Maps
  run in `data/runs` (87 screens, for both Empire State Building and Space Needle), it gives the same value with and
  without `expect_digits`. It is not a regression on any recorded screen. It would now also accept an address with no
  street number.
- **The only read-back warning in any real-app compile under 773536a** was Amazon's product, which read a search
  suggestion in Phase 7's compile. Session A's row fix already corrects it, and both compilers give the same Amazon
  routine.

## Not done

- **Not run on a device.** The new-seed reads are offline, on the screens the agent answered from. A replay would also
  test the matcher filling `ingredient_name` and the date, and Spark's grounding of `date cell 24 in the October month
  grid`. It needs AndroidWorld's harness (the androidworld branch) with the YAMLs in
  `eval/results/routine_answers_2026-10-29/recompiled/`, about 15 minutes on the AndroidWorld emulator. That is the
  coordinator's call.
- **Day with no events.** "Do I have any events on …?" for a day with none finds no rows, so the output is missing and
  the agent takes over.
- **A date in another month.** The routine taps the day in the month shown and doesn't page through months.
- **Visual targets can still carry source data.** One calendar target reads `the date cell for {{event_date:day}}
  showing Trivia Niq`, where the event title was clipped, so it isn't caught as booking data.
- **The "words.." rule** in the matcher is narrow: it drops a doubled final full stop only.
- **The routine libraries on the androidworld branch** are not recompiled here.

## Files

- `backend/routines/compiler.py`: `degenerate`, `_effect`, `_numeric`, `_opposite`, `_plural`, `_every_rows`,
  `_part_examples`, `_prior_text`; the outputs block (read-back drop, refusing a question with no readable answer);
  enabled states in `_layout_key`.
- `backend/routines/executor.py`: reads for `every` and `answers`, the merged-label line for an input-anchored extract,
  and filling `{{_field}}`.
- `backend/routines/model.py`: `{{name:part}}` slots, `slot_names`, `FIELD`, and `Extract.every` / `Extract.answers`.
- `backend/routines/dates.py`: `parse_date`, `parse_time`, `formatted`, `parts`.
- `backend/routines/matcher.py`: `like_example`.
- `backend/tests/test_routine_answers.py`, and the fixtures in `backend/tests/traces/androidworld/` (13 source traces,
  trees only, with `spec.json`; `new_seeds/`).
- `eval/results/routine_answers_2026-10-29/`: the recompiled YAMLs, `recompile.json`, `degenerate_scan.json`,
  `regression.json`.
