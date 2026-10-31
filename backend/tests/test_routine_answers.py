"""Routines that run every step and pass their own checks but give the wrong answer (AndroidWorld, Oct 28–29: routines
verified on seed 30 answered 0/9 on new seeds, and eight more finished every step and check on their own seed yet scored 0).

tests/traces/androidworld/<task> holds the seed-30 runs those routines were compiled from (trees only, no screenshots), each
with Muse Wonder's compile answer cached in spec.json, so they recompile offline. new_seeds/ holds the screens the full
agent answered from on three other seeds of the three question tasks (index.json: each one's goal and answer): the screens
the compiled routines stopped on with "outputs not found".

- Outputs tied to the source run: a pattern holding the example's ingredient and unit, or the note's own wording;
  expect_digits on an address that happened to start with a number.
- Outputs dropped or meaningless: a list answer that is no single element; a date picked in a month grid that never became an
  input; the event at an hour read from the first row; a yes/no answered with the menu item it was inferred from; an output
  that reads something else on the run's own final screen.
- Weak verification: a run that had nothing to do (nothing to delete, brightness already at its maximum) taught a routine that
  does nothing; Markor's edit was saved by leaving the editor, a step the compiler dropped as a back-track, so the routine's
  done-check passed on unsaved text; and the edit typed the source note's own words back in.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

import routines.executor as executor_mod
from agent.trace import TraceWriter
from devices.types import ActionResult
from models.schemas import CompiledRoutine, InputValue, MatchOutput
from policy.approvals import ScriptedApprover
from routines import locators
from routines.compiler import NotCompilable, _done_screen, _numeric, clean, compile_trace, degenerate, load_trace
from routines.executor import ExecConfig, RoutineExecutor, extract_value
from routines.matcher import RoutineMatcher, like_example
from routines.model import Routine, render_str
from routines.screens import load_tree, screen_from_tree

AW = Path(__file__).parent / "traces" / "androidworld"
NEW = AW / "new_seeds"
REAL = Path(__file__).parent / "traces" / "real_1f1fc11"  # Phase 7's envoy-real sources from its pass on 1f1fc11
REAL_SMOKE = Path(__file__).parent / "traces" / "real_49685b0"  # and from its Oct 31 smoke on 49685b0
FAST = ExecConfig(pre_timeout_s=0.6, post_timeout_s=0.6, stable_s=0.2, poll_s=0.01, patch_screenshots=False)


@pytest.fixture(autouse=True)
def traces_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(executor_mod, "TraceWriter", lambda tid: TraceWriter(tid, root=tmp_path))


class NoModel:
    def call(self, *a, **kw):
        raise AssertionError("no model call expected")


def compiled(task: str, root: Path = AW) -> tuple[Routine, list[str]]:
    d = root / task
    spec = CompiledRoutine.model_validate_json((d / "spec.json").read_text())
    routine, report = asyncio.run(compile_trace(d, adapter=NoModel(), confirmed=True, spec=spec))
    return routine, report.warnings


def final_screen(task: str, root: Path = AW):
    d = root / task
    return _done_screen(d, [json.loads(line) for line in (d / "steps.jsonl").read_text().splitlines() if line.strip()])


def outputs(r: Routine, screen, inputs: dict[str, str]) -> dict[str, str | None]:
    ex = {n: e for st in r.steps for n, e in (st.extract or {}).items()}
    return {n: extract_value(e, screen, inputs, ex) for n, e in ex.items()}


def edited(task: str, change, root: Path = AW) -> object:
    """The task's final screen with `change(elements)` applied to its recorded tree: another instance of the same screen."""
    d = root / task
    rec = next(json.loads(line) for line in reversed((d / "steps.jsonl").read_text().splitlines())
               if line.strip() and json.loads(line).get("decision", {}).get("action", {}).get("type") == "done")
    with gzip.open(d / rec["tree_before"], "rt") as f:
        tree = json.load(f)
    change(tree["elements"])
    return screen_from_tree(tree)


# ---- outputs tied to the source run (backlog #8) ----------------------------------------------------------------------


def test_the_ingredient_the_question_names_is_an_input_and_the_answer_is_read_beside_it():
    """Seed 30: "3/4 cup spirulina". The old extract was the pattern `(\\d+/\\d+ cup)\\s*spirulina`, and the ingredient was
    dropped as an unused input; new seeds asked for buckwheat groats (2 teaspoons, the recipe's first line, merged into
    its "Ingredients:" heading), arrowroot powder and almond flour."""
    r, _ = compiled("ingredient")
    assert r.inputs["ingredient_name"].example == "spirulina"
    ex = r.steps[-1].extract["ingredient_quantity"]
    assert "spirulina" not in ex.model_dump_json() and "cup" not in ex.model_dump_json()
    assert outputs(r, final_screen("ingredient"), {"recipe_name": "Chicken Alfredo", "ingredient_name": "spirulina"}) == \
        {"ingredient_quantity": "3/4 cup"}
    for k, ingredient, answer in ((1, "buckwheat groats", "2 teaspoons"), (2, "arrowroot powder", "1/2 cup"), (3, "almond flour", "1/2 cup")):
        assert outputs(r, load_tree(NEW / f"ingredient_{k}.json.gz"), {"ingredient_name": ingredient}) == {"ingredient_quantity": answer}


def test_a_count_is_read_by_its_shape_not_by_the_notes_own_words():
    """Seed 30's note said "25 individuals were present"; the others say "80 individuals attended", "45 participants were
    present", "50 individuals attended"."""
    r, _ = compiled("attendees")
    ex = r.steps[-1].extract["attendee_count"]
    assert "individuals" not in (ex.pattern or "") and "present" not in (ex.pattern or "")
    assert outputs(r, final_screen("attendees"), {}) == {"attendee_count": "25"}
    for k, answer in ((1, "80"), (2, "45"), (3, "50")):
        assert outputs(r, load_tree(NEW / f"attendees_{k}.json.gz"), {}) == {"attendee_count": answer}


def test_a_location_is_not_expected_to_be_a_number():
    """Seed 30's location was "100 Main St Chicago", so the output required digits; the others were "Virtual", "The Coffee
    Bean" and "Sarah's apartment"."""
    r, _ = compiled("event_location")
    assert not r.steps[-1].extract["location"].expect_digits
    for k, answer in ((1, "Virtual"), (2, "The Coffee Bean"), (3, "Sarah's apartment")):
        assert outputs(r, load_tree(NEW / f"event_location_{k}.json.gz"), {}) == {"location": answer}
    # A number with at most a unit still has to be one (a placeholder "- calories" is not the value yet).
    assert all(_numeric(v) for v in ("190 calories", "$13.49", "2:05 PM", "3/4 cup", "25", "65535.0", "12C"))
    assert not any(_numeric(v) for v in ("100 Main St Chicago", "Virtual", "Oct 29"))


# ---- outputs dropped or meaningless (backlog #1) ----------------------------------------------------------------------


def test_a_list_answer_is_every_row_of_the_day_and_the_day_is_an_input():
    """"Do I have any events October 28?" → "Game night, Product demo, Date night": no single element holds it, so the
    output was dropped; and the day was tapped in the month grid from a recorded picture of "28", so the date input was
    dropped too. The routine answered nothing, about October 28 whatever the request."""
    r, warnings = compiled("any_events_on_date")
    assert r.outputs == ["event_titles"] and r.inputs["event_date"].example == "October 28"
    tap = next(st for st in r.steps if st.action.target is not None and st.action.target.visual)
    assert tap.action.target.visual == "date cell {{event_date:day}} in the {{event_date:month}} month grid"
    assert tap.action.target.crop is None  # a picture of "28" is never the day another request asks for
    assert render_str(tap.action.target.visual, {"event_date": "October 24"}) == "date cell 24 in the October month grid"
    assert outputs(r, final_screen("any_events_on_date"), {}) == {"event_titles": "Game night, Product demo, Date night"}
    # Another day, recorded by the run that asked about October 24: its one event.
    assert outputs(r, final_screen("events_on_date"), {}) == {"event_titles": "Trivia Night"}
    # Compiled from that one-event run, the plural answer still reads every row.
    r24, _ = compiled("events_on_date")
    assert outputs(r24, final_screen("any_events_on_date"), {}) == {"event_titles": "Game night, Product demo, Date night"}


def test_the_event_at_an_hour_is_the_row_that_shows_that_hour():
    """"What is on my schedule for October 27 2023 at 8:00pm?" → "Product demo" (20:00 - 20:15), the third of the day's
    events. The routine read the first row ("Review session for Annual Report") and took no date or time input."""
    r, _ = compiled("event_at_time")
    assert set(r.inputs) == {"schedule_date", "schedule_time"}
    ex = r.steps[-1].extract["event_titles"]
    assert ex.every and ex.locator.text_has == "{{schedule_time:time24}}"
    day = final_screen("event_at_time")
    assert outputs(r, day, {"schedule_time": "8:00pm"}) == {"event_titles": "Product demo"}
    assert outputs(r, day, {"schedule_time": "10:15 am"}) == {"event_titles": "Meeting with Bob"}
    assert outputs(r, day, {"schedule_time": "6pm"}) == {"event_titles": None}  # nothing then: missing, not another event


def test_a_yes_no_question_is_answered_true_or_false():
    """"Is the note 'To-Do List' a todo?" was answered "Convert to note" (the menu item the agent inferred True from)."""
    r, _ = compiled("is_todo")
    assert outputs(r, final_screen("is_todo"), {"note_title": "To-Do List"}) == {"is_todo": "True"}

    def plain_note(els):  # a note that isn't a to-do: its menu offers the other conversion
        for e in els:
            if e.get("text") == "Convert to note" or e.get("label") == "Convert to note":
                e["text"] = e["label"] = "Convert to todo"
    assert outputs(r, edited("is_todo", plain_note), {"note_title": "To-Do List"}) == {"is_todo": "False"}


def test_an_answer_read_wrong_on_the_runs_own_screen_is_not_kept(tmp_path):
    """"What is my next upcoming event?" → "Board meeting" (the first after now, 15:34); the routine read the day's first
    row, "Call with Marketing", even on the screen it was compiled from. A question with no readable answer is left to the
    agent; on a task that isn't a question, an output that reads wrong is dropped and the routine keeps its steps."""
    with pytest.raises(NotCompilable, match="Call with Marketing"):
        compiled("next_event")
    d = tmp_path / "next_event"
    shutil.copytree(AW / "next_event", d)
    run = json.loads((d / "run.json").read_text())
    (d / "run.json").write_text(json.dumps({**run, "goal": "Show my upcoming events in Simple Calendar Pro as a list."}))
    spec = CompiledRoutine.model_validate_json((d / "spec.json").read_text())
    r, report = asyncio.run(compile_trace(d, adapter=NoModel(), confirmed=True, spec=spec))
    assert r.outputs == [] and r.steps[-1].extract is None
    assert any("reads 'Call with Marketing'" in w and w.endswith("dropped") for w in report.warnings)
    # Asked as "… tell me …", it is still a question: no routine that answers nothing (YouTube Music, Oct 31).
    (d / "run.json").write_text(json.dumps({**run, "goal": "Open Simple Calendar Pro and tell me the title of my next upcoming event."}))
    with pytest.raises(NotCompilable, match="Call with Marketing"):
        asyncio.run(compile_trace(d, adapter=NoModel(), confirmed=True, spec=spec))


# ---- weak verification (backlog #1, #9) -------------------------------------------------------------------------------


def test_a_run_with_nothing_to_do_does_not_become_a_routine():
    """Seed 30's "delete the recipes that use black garlic" had none to delete; "turn brightness to the max" found it at
    the max. Both runs succeeded, and their routines did nothing on every other instance while passing their own checks.
    They are refused before the model call."""
    with pytest.raises(NotCompilable, match="nothing to delete"):
        asyncio.run(compile_trace(AW / "delete_by_ingredient_none", adapter=NoModel(), confirmed=True))
    with pytest.raises(NotCompilable, match="changed nothing"):
        asyncio.run(compile_trace(AW / "brightness_already_max", adapter=NoModel(), confirmed=True))
    # Runs that did the work still compile: the slider dragged to the max, the note created and sent by SMS.
    assert compiled("brightness_max")[0].steps and compiled("note_and_sms")[0].steps
    # A goal's nouns are not verbs: "the following text", "in order"; a question has nothing to change.
    assert degenerate("Create a new note in Markor named a.txt with the following text: Hi.", "Created", [], []) is None
    assert degenerate("Create a playlist with the following songs, in order: A, B", "Created", [], []) is None
    assert degenerate("Is the note titled 'To-Do List' a todo?", "True", [], []) is None
    assert "nothing to reply" in degenerate("Reply to the most recent text message with: hi", "Replied", [], [])
    assert "already so" in degenerate("Turn bluetooth off.", "Bluetooth is off", [], [])


def test_the_markor_edit_saves_by_leaving_the_editor_and_keeps_the_notes_own_text():
    """The agent typed "Hello, World!" + the note's text, left the editor (which saves it) and opened the file again. The
    round trip ended on a screen that looked the same, so it was dropped as a back-track; the routine never left the
    editor and its done-check passed on unsaved text. And it typed seed 30's note back in, on any note."""
    r, _ = compiled("markor_edit")
    ids = [st.id for st in r.steps]
    assert ids.index("return_to_file_list") < ids.index("reopen_note_file")
    assert not r.steps[r.step_index("return_to_file_list")].optional
    typing = next(st for st in r.steps if st.action.kind == "type")
    assert typing.action.value == "{{text_to_add}}\n{{_field}}"
    assert "water the plants" not in r.model_dump_json()
    assert [c.value for c in typing.post if c.kind == "field_equals"] == ["{{text_to_add}}\n{{_field}}"]

    # Run that step on another note: it keeps that note's text under the new line, and its after-check holds.
    d = AW / "markor_edit"
    rec = next(json.loads(line) for line in (d / "steps.jsonl").read_text().splitlines()
               if line.strip() and json.loads(line).get("decision", {}).get("action", {}).get("type") == "type")
    with gzip.open(d / rec["tree_before"], "rt") as f:
        tree = json.load(f)
    editor = next(e for e in tree["elements"] if e.get("editable"))
    editor["text"] = editor["label"] = "Buy milk."

    class Markor:
        def __init__(self):
            self.screen, self.typed = screen_from_tree(tree), None

        async def observe(self, screenshot: bool = False):
            return self.screen

        async def act(self, a):
            if a.kind == "type":
                self.typed = a.text
                editor["text"] = editor["label"] = a.text
                self.screen = screen_from_tree(tree)
            return ActionResult(ok=True, duration_ms=1.0)

    phone = Markor()
    one = r.model_copy(update={"steps": [typing], "done": [], "outputs": []})
    ex = RoutineExecutor(phone, adapter=NoModel(), approver=ScriptedApprover(approve=False), config=FAST)
    out = asyncio.run(ex.run(one, {"note_file_name": "note_x.txt", "text_to_add": "Hi there"}, launch="never", allow_agent=False,
                             allow_repair=False))
    assert phone.typed == "Hi there\nBuy milk." and out.status == "done", out.detail


def test_the_matcher_writes_a_value_the_way_the_example_is_written():
    """Note-and-SMS on its own seed scored 0.5: the matcher gave the extension as "txt" (the routine's example is ".txt",
    typed into a field that keeps the dot) and the text as "Actions speak louder than words.." (the request's own full
    stop after the text's)."""
    r, _ = compiled("note_and_sms")
    request = ("Create a new note in Markor named fair_ant_XOdi.txt with the following text: Actions speak louder than words.. "
               "Share the entire content of the note with the phone number +13192815309 via SMS using Simple SMS Messenger")
    given = {"note_name": "fair_ant_XOdi", "file_extension": "txt", "note_text": "Actions speak louder than words..",
             "recipient_phone_number": "+13192815309"}
    answer = MatchOutput(routine=r.routine, confident=True,
                         inputs=[InputValue(name=n, value=v, source="request") for n, v in given.items()])

    class Matcher:
        def call(self, *a, **kw):
            return SimpleNamespace(parsed=answer, cost_usd=0.0, cost_at_standard_usd=0.0)

    m = RoutineMatcher(SimpleNamespace(active=lambda: [r]), adapter=Matcher())  # type: ignore[arg-type]
    res = asyncio.run(m.match(request))
    assert res.inputs["file_extension"] == ".txt" and res.inputs["note_text"] == "Actions speak louder than words."
    assert res.inputs["note_name"] == "fair_ant_XOdi" and res.inputs["recipient_phone_number"] == "+13192815309"
    assert like_example("Wait...", "Hi.") == "Wait..." and like_example("13192815309", "+13192815309") == "13192815309"


# ---- Phase 7's real-app pass on 1f1fc11 ----------------------------------------------------------------------------------


def test_a_price_with_its_unit_price_is_read_by_that_shape_even_on_the_only_such_row():
    """Amazon on envoy-real: the first result's price is "$9.99 ( $0.83 /count)", the only row of that shape on the screen.
    1f1fc11 took the words of a row no other row repeats for the item's own (a note's "individuals were present"), fell
    back to "the first $x.xx in the list" (a carousel's $6.53), and dropped the output: the same-input rerun answered
    nothing. Words around another number are the app's."""
    r, warnings = compiled("amazon", REAL)
    ex = r.steps[-1].extract["first_result_price"]
    assert "/count" in ex.pattern and ex.first_in_list
    assert outputs(r, final_screen("amazon", REAL), {"search_query": "AA batteries"}) == {"first_result_price": "$9.99"}
    assert not any("dropped" in w for w in warnings)


def test_the_days_heading_is_read_by_its_fixed_words_and_the_first_screen_waits_for_the_app():
    """Google Calendar on envoy-real: "do I have any events today?" was answered from the agenda the app opens to,
    "Thursday 29 October 2026, Open Day View" then "Nothing planned. Tap to create.". The date had nothing before it to
    anchor on and was dropped; it leads its element, followed by the app's words. And the strict rerun read nothing
    straight after launch: the read waits for the app to be in front now, and a miss leaves the screen as evidence."""
    r, warnings = compiled("calendar_today", REAL)
    assert r.outputs == ["todays_date", "todays_events_status"]
    read = r.steps[-1]
    assert read.id == "read_answer" and [c.describe() for c in read.pre] == ["app com.google.android.calendar in front"]
    assert outputs(r, final_screen("calendar_today", REAL), {}) == \
        {"todays_date": "Thursday 29 October 2026", "todays_events_status": "Nothing planned. Tap to create."}

    def next_day(els):  # the same agenda a day later, with an event
        for e in els:
            for k in ("text", "desc", "label"):
                if e.get(k):
                    e[k] = e[k].replace("Thursday 29 October 2026", "Friday 30 October 2026").replace(
                        "Nothing planned. Tap to create.", "Standup, 09:00 – 09:15")
    other = outputs(r, edited("calendar_today", next_day, REAL), {})
    assert other == {"todays_date": "Friday 30 October 2026", "todays_events_status": None}  # missing, never the wrong words


def test_an_empty_state_wonder_lists_as_data_still_answers_the_count():
    """Contacts on envoy-real, Phase 7's Oct 31 smoke: "how many contacts do I have?" → '0 contacts — "No contacts yet"'.
    About 1 compile in 4, Wonder listed "No contacts yet" among the run's data values, so the inferred 0 had nothing to be
    read from and the question wasn't compiled. The answer quotes those words and 0 is nowhere on the screen: they are the
    screen's own."""
    r, warnings = compiled("contacts_count", REAL_SMOKE)
    assert r.outputs == ["contact_count"]
    assert any("inferred from 'No contacts yet'" in w for w in warnings)
    assert outputs(r, final_screen("contacts_count", REAL_SMOKE), {}) == {"contact_count": "No contacts yet"}


def test_a_routine_whose_outputs_are_missing_leaves_the_screen_it_looked_at(tmp_path):
    r, _ = compiled("calendar_today", REAL)
    screen = edited("calendar_today", lambda els: [e.update(text="", desc="", label="") for e in els  # the agenda not drawn yet
                                                     if "Open Day View" in (e.get("label") or "") or "Nothing planned" in (e.get("label") or "")], REAL)

    class Calendar:
        async def observe(self, screenshot: bool = False):
            return screen

        async def act(self, a):
            return ActionResult(ok=True, duration_ms=1.0)

    ex = RoutineExecutor(Calendar(), adapter=NoModel(), approver=ScriptedApprover(approve=False), config=FAST)
    out = asyncio.run(ex.run(r, {}, launch="never", allow_agent=False, allow_repair=False))
    assert out.status == "failed" and out.detail.startswith("outputs not found: ")
    assert list(tmp_path.rglob("*outputs_missing*")), "no tree saved for the missing outputs"


# ---- AndroidWorld's replay of this library (androidworld e0e68ad), backlog #10 and #11 ----------------------------------


def test_a_drag_starts_where_the_recorded_one_did_inside_its_target():
    """Brightness to the max: the agent dragged the slider from its thumb near the left end (x 144) to x 1007, then from
    x 756 to x 1048, past the track's right end (42–1038). The routine started both drags at the slider's centre (540) with
    the same vectors, so the second one ended at x 832: brightness 51915, and every check passed. Started where the
    recorded drags were, inside the slider, they end where those did, whatever the brightness was before."""
    r, _ = compiled("brightness_max")
    swipes = [st for st in r.steps if st.action.kind == "swipe"]
    d = AW / "brightness_max"
    rec = next(json.loads(line) for line in (d / "steps.jsonl").read_text().splitlines()
               if line.strip() and (json.loads(line).get("device_action") or {}).get("kind") == "swipe")
    with gzip.open(d / rec["tree_before"], "rt") as f:
        tree = json.load(f)

    class Slider:
        """The brightness dialog: the value follows the finger to where it lifts on the track (x 42–1038)."""

        def __init__(self, value: float):
            self.value, self.drags = value, []

        def screen(self):
            for e in tree["elements"]:
                if "Display brightness" in (e.get("label") or ""):
                    e["label"] = e["text"] = f"Display brightness · {self.value:.1f}"
            return screen_from_tree(tree)

        async def observe(self, screenshot: bool = False):
            return self.screen()

        async def act(self, a):
            if a.kind == "swipe":
                self.drags.append((a.x, a.x2))
                self.value = float(round(max(0.0, min(1.0, (a.x2 - 42) / (1038 - 42))) * 65535))
            return ActionResult(ok=True, duration_ms=1.0)

    for start in (0.0, 65535.0):  # at the minimum, as AndroidWorld sets it, and already at the maximum
        phone = Slider(start)
        drags = r.model_copy(update={"steps": swipes})
        ex = RoutineExecutor(phone, adapter=NoModel(), approver=ScriptedApprover(approve=False), config=FAST)
        out = asyncio.run(ex.run(drags, {}, launch="never", allow_agent=False, allow_repair=False))
        assert out.status == "done", out.detail
        assert out.outputs == {"brightness_level": "65535.0"} and phone.drags == [(143, 1005), (756, 1047)], (out.outputs, phone.drags)
    assert [st.action.grip for st in swipes] == [(0.102, 0.262), (0.717, 0.802)]


def test_identical_results_differ_only_by_their_slot():
    """The launcher's search for "Simple Calendar Pro" lists "Simple Calendar Pro0" … "Pro9": the compiler cut the numbers
    out as data, so the tap's locator ("Simple Calendar Pro", a Button under search_results_list_view) fits all ten alike,
    and the recorded top one won 0.81 to 0.79, inside the margin: "target not found". Siblings the locator's words fit
    equally are told apart by the recorded slot, as repeated list rows already were."""
    r, _ = compiled("events_on_date")
    tap = r.steps[r.step_index("tap_simple_calendar_pro_result")].action.target
    assert tap.text == "Simple Calendar Pro"
    d = AW / "events_on_date"
    _, records = load_trace(d, confirmed=True)
    results = next(s for s in clean(d, records)[0] if s.target is not None and s.target.label == "Simple Calendar Pro0").before
    m = locators.locate(tap, results, {})
    assert m.element is not None and m.element.label == "Simple Calendar Pro0", m.summary()
    # Words that fit the siblings differently still decide by score, never by the slot.
    other = tap.model_copy(update={"text": "Simple Calendar Pro3"})
    assert locators.locate(other, results, {}).element.label == "Simple Calendar Pro3"


def test_an_after_check_that_held_before_the_step_is_not_kept():
    """YouTube Music on envoy-real, Oct 31: filter_by_songs' after-check was the "Songs" chip, which is there selected or not.
    On reruns the step looked done before it ran ("its after-checks already hold"), was skipped, and the routine read the
    unfiltered results: "Royal Philharmonic Orchestra & Matthew Freeman" instead of Queen."""
    from routines.compiler import _effect_checks
    from routines.model import Check, Locator

    def results(*labels: str):
        return screen_from_tree({"package": "com.google.android.apps.youtube.music", "activity": "Search", "width": 1080,
                                 "height": 2400, "elements": [
            {"index": i, "parent": None, "number": i + 1, "kind": "Button", "class": "android.widget.Button", "label": t,
             "text": t, "clickable": True, "bounds": [0, 200 * i, 1080, 200 * i + 150]} for i, t in enumerate(labels)]})
    before = results("Songs", "Albums", "Bohemian Rhapsody · Royal Philharmonic Orchestra")
    chip = Check(kind="element_present", locator=Locator(text="Songs", kind="Button"))
    row = Check(kind="element_present", locator=Locator(text="Bohemian Rhapsody · Queen", kind="Button"))
    keep, held = _effect_checks([Check(kind="screen_changed"), chip, row], before, {})
    assert held == [chip] and keep == [Check(kind="screen_changed"), row]
