# YouTube Shorts song pick: why it fails, and why it isn't fixed in the routine

Found after the showcase batch (B1), Nov 3 15:30–16:02 ET, with search-only diagnostics on the Pixel; not part of the
batch's measurements. Not merged: branch `claude/yt-song-fix` (741e525, `youtube_short_sound` v4) is a failed attempt,
kept only as evidence.

## Cause (found on the Pixel, search only, nothing picked or posted)

1. **Enter doesn't search.** After the routine types the title into YouTube's Sounds search box (`type_sound_title`,
   submit), the list underneath stays on YouTube's trending sounds for at least 4 s, with no result chips. The search runs
   only when a "Trigger a new search with …" suggestion is tapped.
2. **v3 skips that tap.** `tap_trigger_search`'s after-checks are the editor's "More tools" and "Edit", which stay in the
   screen tree behind the Sounds sheet. So whenever the suggestion doesn't match on the first look, the executor finds the
   after-checks already holding and skips the step as done. The list stays on trending sounds, where golden hour is (it
   was in that list every time it was checked) and the batch's other songs aren't: S07, S08 and S10.
3. **The suggestion can't be told apart by the routine's locator.** YouTube lists case twins ("flowers", most likely from
   search history, then the suggestion "Flowers") and near-titles ("Flowers In December", "Flowers (Sunship Radio Edit)").
   - v3's target ("Trigger a new search with" + text_has title) is ambiguous for Flowers and Watermelon Sugar: four
     suggestions within the 0.08 margin. `_same_case` doesn't settle it, because several hold the title as a whole word.
     It works for Levitating, golden hour and Espresso.
   - v4's exact target ("Trigger a new search with {{sound_title}}") ties at 1.00/1.00 between the case twins. Then
     the executor's search rung retypes the target text into the search box ("Trigger a new search with Flowers").
     YT-S1 went to the full agent (12 calls), which reached Upload Short (declined), song not checked.
   - The keyboard's search key isn't in YouTube's screen tree, so a routine can't tap it.

When the right suggestion is tapped, the search works: the right song was row #0 for Flowers, Watermelon Sugar,
Levitating and Espresso. Its row reads "<title>, <artists…>, 1 minute, …", which the existing find step matches.
Miley Cyrus's "Flowers" is in YouTube's library, which B1's library check hadn't established.

## The fix that would work, and why it stopped there

Two parts:
- **Routine** (as in v4): `tap_trigger_search`'s after-check becomes the results' "Official music" chip, so the step
  isn't skipped before the search runs.
- **Matcher** (`backend/routines/locators.py`): when the tied candidates' labels are equal ignoring case, take the
  first in reading order. They run the same search. About 5 lines, plus a test.

The second part reaches the matcher, which was past this task's limit ("if it reaches the compiler or matcher, stop
and write it up"), and locators.py belongs to another workstream. So nothing is merged: YouTube stays a known limit.
Golden hour works as before, and the outcome check stops a Short with no song before Upload Short.

## Evidence

- YT-S1 (task-1103-154523-091c), v4 on a test copy: the full agent took over at `tap_trigger_search` (12 model calls),
  reached Upload Short, which was declined; the song wasn't checked. Its record is kept outside the repo.
- YT-S2 (task-1103-154946-c3a5): stopped and void, because a diagnostic overlapped it on the phone.
- The suggestion lists, result rows and the 1.00/1.00 tie came from search-only diagnostics, not kept in the repo.

## Side effects on the phone

- The search-only diagnostics added "flowers", "watermelon sugar", "levitating", "espresso" and "golden hour" to the
  YouTube test account's Sounds search history (likely the lowercase twins above).
- The stopped YT-S2 run may have left one autosaved YouTube draft.
