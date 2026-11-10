# What the models do

Envoy runs on Meta's models: Muse Wonder 1.0, Muse Spark 1.3, SAM 3.1 and Muse Voice Transcribe. The design rule is
that **models learn and repair; replay is code.** A model works out a task the first time, turns that run into a
routine, and fixes a step when an app changes. A routine that's already learned runs as code, with checks before and
after every step and no model call while those checks pass.

Every model call goes through one adapter ([`backend/models/adapter.py`](../backend/models/adapter.py)). Each job has its
own model, reasoning effort, structured-output schema and token cap, and every call is logged with its tokens, cost and
latency.

## Who does what

On the default `hybrid` profile:

| Model | Jobs | What it does there |
| --- | --- | --- |
| **Muse Wonder 1.0** | `compile` | Turns one finished run (or a person's demonstration) into a routine: names the inputs, decides which values stay fixed, writes each step's generic intent and picks the outputs ([below](#compiling-a-run-into-a-routine)) |
| | `plan`, `step`, `repair` | Plans and acts on a task Envoy hasn't learned yet, and repairs a routine step that stopped matching the app |
| **Muse Spark 1.3** | `match` | Picks the routine for a request in words and fills its inputs, or declines when none fits |
| | `extract`, `same_entity`, `answer`, `screen_read` | Reads facts from screens, emails and photos into memory, decides whether two facts describe the same thing, and answers from memory with each fact's source and age |
| | `choose`, `grounding` | Finds a target on a screen with no accessibility tree: picks one of SAM's boxes, or grounds a description on the 0–1000 grid |
| | `chat`, `app_note` | Routes a chat message (a memory question, a task or a reply) and keeps short notes per app |
| **SAM 3.1** | vision | Proposes boxes on drawn screens, like a canvas seat map, which Spark then chooses from |
| **Muse Voice Transcribe** | dictation | Speech to text in the web app and on the iPhone |

`ENVOY_MODEL_PROFILE=spark` runs every job except `compile` on Spark, and `wonder` runs everything on Wonder. Hybrid has
been the default since Oct 30: in a comparison on 20 AndroidWorld tasks (14 of them ones the all-Spark agent had failed),
hybrid passed 14 against Spark's 9, at 3.46 times the cost per task
([`model-comparison`](../eval/results/androidworld/model-comparison/2026-10-28/README.md)). Saved routines replay with
Spark jobs or none, so the extra cost lands only on first runs and repairs.

## Compiling a run into a routine

This is the core of how Envoy learns. The compiler ([`backend/routines/compiler.py`](../backend/routines/compiler.py))
takes one agent run's trace (every screen before and after every action) and produces a versioned YAML program. Wonder
does the part that needs judgment; code does the rest and checks Wonder's answer.

1. **Confirm success (code).** Only a run that ended done, with its success check passed or the person's confirmation, is
   compiled. A run that had nothing to do, like a delete with nothing to delete, is refused.
2. **Clean up (code).** Dismissed pop-ups (a shared handler covers those), looks, failed actions, steps with no visible
   effect and back-tracks are dropped. Scrolls before a list tap become `scroll_until`. A correction is kept rather than
   taken for a back-track.
3. **Generalize (Wonder).** Wonder gets the goal, the agent's notes, the cleaned steps, the final screen and the answer,
   and returns a typed answer: which values are inputs a different request would change (a city, a seat, a song), a
   generic intent for each step using `{{slots}}`, the outputs to return, which literal values are booking data rather
   than inputs, and a name and phrasings for matching. Its instructions are
   [`COMPILE_INSTRUCTIONS`](../backend/models/prompts.py#L121).
4. **Bind and disambiguate (code).** Values equal to an input become slots in typed text, locators and checks. A list row
   chosen because it shows an input becomes an input-based locator (`text_has`). Booking data that isn't an input is
   removed, so the routine doesn't expect it next time. A locator that fits several look-alikes is told apart by the inputs
   it shows, then by its place in the list.
5. **Add checks (code).** Each step's before and after accessibility trees are diffed to write its checks: what must be on
   screen before it acts, and what must change after.
6. **Verify by replay (code).** The routine is replayed at once from a reset, with the same inputs and, where the app
   allows, a second set. Only a routine that passes enters the library.

A compiled step targets an element by what it is, never by where it was:

```yaml
- id: tap_trip_row
  intent: "Tap the trip row for {{trip_city}} in the list."
  pre:
  - {app_foreground: com.skylark.air}
  action:
    tap:
      resource_id: trip_row_*          # data in an ID becomes a glob
      text_has: "{{trip_city}}"        # the row is chosen by the input it shows
      kind: Button
      cls: View
      parent: list_trips
      in_list: true
  post:                                # what must be true after the tap
  - {screen_changed: true}
  - element_present: {resource_id: screen_title, text: "Trip to {{trip_city}}", kind: Text}
  - element_present: {resource_id: btn_checkin, text: Check in, kind: Button}
  risk: reversible
```

(One step of [`data/routines/skylark_get_flight_gate/v1.yaml`](../data/routines/skylark_get_flight_gate/v1.yaml), with
comments added; the routine also reads the gate off the next screen as its output.)
At run time each locator is scored on up to ten attributes (resource ID, text, description, field hint, kind, class,
parent, siblings, list membership, position) against every element on the screen; a strict match needs a score of 0.80
and a clear margin over the runner-up ([`locators.py`](../backend/routines/locators.py)).

**Why code checks Wonder's answer.** Wonder's answers vary from run to run. On a second compile of the same six traces,
two answers were wrong in ways that would have broken replay: one numbered the steps from 0, one returned field names
where literal values belonged. Both passed the schema. The compiler now aligns step numbers and ignores identifier-like
values in code, and the replay check caught both before they reached the library
([`meta-feedback.md`](meta-feedback.md)).

**What it costs.** On the 13 real-app workflows whose first run and rerun both passed in the final evaluation, compiling
cost a median $0.0455 once, against $0.0376 for the agent's first run; Envoy's replays after that used 0 model calls, at a
median 4.88 s instead of 19.59 s ([`real.md`](../eval/results/final/real.md)).

## When an app changes

A routine step that no longer matches climbs a ladder, cheapest first
([`executor.py`](../backend/routines/executor.py)): wait and retry; a relaxed match (score 0.60) or a scroll; the shared
pop-up handler; a **local repair** by the repair model (at most 2 calls per step and 5 per run), which reads the step's
intent and checks and acts on the new screen; the full agent from that point; and finally asking the person. A repair is
saved as a patch, a new version on trial, and becomes active only after a later run passes. Irreversible steps always
ask, in routines too.

On SkyLark, our test app, with its layout changed on purpose 50 times over 5 kinds of change, routines recovered 50/50: 27
needed no fix, 17 a relaxed match or scroll, 2 a local repair and 4 the agent, with 27 model calls in all
([`change.md`](../eval/results/final/change.md)).

## The agent on a task it hasn't learned

The agent loop ([`backend/agent/loop.py`](../backend/agent/loop.py)) plans once, then makes one model call per step. It
reads the accessibility tree as numbered elements and adds a screenshot only when it asks to look, when an action
changed nothing visible, or when the tree has fewer than 3 elements. That was about 11% of steps on AndroidWorld. Known
pop-ups are dismissed in code and sign-in screens are handed to the person, with no model call, and a run that is stuck
or going in circles replans.

Every step comes back as structured output that matches the action schema, with a risk label. Code rules back the label
up ([`backend/policy/risk.py`](../backend/policy/risk.py)): on 20 irreversible controls on saved screens, code alone
caught all 20 ([`safety.md`](../eval/results/final/safety.md)).

**Field order matters.** Meta's decoder writes JSON keys in alphabetical order, not the schema's order, so the agent was
writing its action before its reason. Naming the fields so the alphabet gives the intended order (`1_reason`,
`2_expected_result`, `3_action`) cut `back` actions, which the model often chose as a placeholder, from 13% of all
actions to 8% on its own. With the other
AndroidWorld changes, the agent on SkyLark takes a median 2 steps per task instead of 4
([`androidworld-results.md`](androidworld-results.md), fix 10b).

## Screens with no accessibility tree

Some apps draw controls as pixels (a canvas seat map, TikTok's sound list). There, Envoy's vision path
([`backend/agent/vision.py`](../backend/agent/vision.py)) asks SAM 3.1 for candidate boxes from shape phrases ("square
button", "icon"), draws them as numbered boxes, and has Spark pick one; when Spark says none is the target, a Spark
grounding call finds it. On 52 targets (16 canvas seats, 36 real-app targets whose trees served as the answer key): the
step model's own coordinates found 37%, grounding 92%, SAM and a pick 75% (never a wrong box), and SAM then grounding
100%, in each of two samples ([`phase-6-results.md`](phase-6-results.md)).

## Memory

Spark reads facts from what Envoy sees in apps, emails and photos. Every fact keeps its source and time, a newer source
replaces an older value while the old one stays as history, and answers warn when a fact may be stale. On 62 labelled
test items: 454 of 468 attributes right (97%), 0 wrong values, and 0 of 12 stale facts served without a warning
([`memory.md`](../eval/results/final/memory.md)).

## Tiers

Meta's Contributor tier (Meta may train on inputs) is used only with test apps and synthetic data (SkyLark, and
AndroidWorld's development rounds), never with real apps (`META_CONTRIBUTOR_TIER` in `.env.example`). Every timed
comparison ran on the standard tier.

More on how each model behaved, good and bad: [`meta-feedback.md`](meta-feedback.md).
