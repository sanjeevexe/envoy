# The first plan waits for the app to draw (backlog #14, Oct 29, offline)

**Commit.** `47d87bc` on `androidworld`, which is `16ceba9` when cherry-picked onto `coord/aw-guard` `5fa03bf`. 517 tests
pass there.

**Why.**
- Every recorded DoorDash run made its plan on the app's loading view: 680–864 input tokens, against about 1,550 with the
  home screen.
- It is the only one of Phase 7's 18 workflows whose plans were made on a smaller screen than their first step's. The
  plan input minus the step-1 screen's size has a median of 63 tokens for DoorDash, against 615–688 for every other
  workflow.
- A plan made on the loading view guesses the route. On Oct 29, "Open Account or profile" took the run to DoorDash's
  Account screen, where the payment-screen rule asked for an approval. That rule stays as it is.

**The change** (`agent/loop.py`):
- **A first screen with something drawn but nothing to act on** (no clickable, editable, checkable or scrollable element)
  is read again, up to 4 times, 1.5 s apart, before planning. It's traced as `splash_wait`.
  - An empty tree is left to `wait_until_settled`, as before. Target's bot check never draws one, and waiting would only
    slow it.
- **A plan made on a screen of at most 2 elements is made again, once,** if step 1 reads a drawn screen (10 or more
  elements). That covers a splash with a clickable logo.
  - A two-button dialog that stays (YouTube Music's trial prompt, Gmail's "GOT IT" card) is planned once, as before.

**Nothing else changes** (`splash_scan.py`, deterministic, no model calls). Neither rule fires on any recorded first
screen that had already drawn:

| Runs | First screens | `is_splash` fires | Step-1 replan fires |
| --- | ---: | ---: | ---: |
| Real apps (Phase 7, Oct 27–29) | 171 | 0 | 0 |
| SkyLark | 627 | 0 | 0 |
| AndroidWorld (`final-standard`) | 118 | 0 | 0 |

So for those apps the plan is made on the same screen at the same moment as before. The check is a pure function of the
screen already read, with no extra device call.

**DoorDash's route** (`dd_splash.py`, 5fa03bf's planner with the harness's NOTES, 30 each): plan, then step 1 on the
loaded home.

| Plan made on | Taps the address | Goes to Account | Answers at once |
| --- | ---: | ---: | ---: |
| The loading view (rebuilt; plan input 870 tokens against the live 864) | 22 | 4 | 4 |
| The loaded home (what the change does) | 27 | 0 | 3 |

**Not verified offline:** the loading view itself was never recorded. Which of the two rules catches it shows in the
trace of Phase 7's next DoorDash run, as a `splash_wait` record or as a second plan at step 1.

Cost at standard prices: $0.29.
