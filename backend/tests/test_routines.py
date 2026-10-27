"""Offline tests for app routines: format, locators, checks, compiler, extraction, patches and the store.

Screens are real SkyLark captures (tests/screens/*.xml); tests/traces/add_ktn is a real agent trace
("Add my known traveler number to my Denver trip") with Wonder's compile answer cached in spec.json,
so the compiler runs here without a model call.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from devices.screen import build_state
from devices.types import ScreenState
from models.schemas import CompiledRoutine
from routines import checks as chk
from routines import locators
from routines.compiler import _glob_data_segments, bind_inputs, clean, compile_trace, generalize_check, load_trace
from routines.executor import Patch, extract_value
from routines.model import Check, Extract, Locator, Step, StepAction, dump_yaml, load_yaml, render
from routines.screens import contains_value
from routines.store import RoutineStore, apply_patches

HERE = Path(__file__).parent
SCREENS = HERE / "screens"
TRACE = HERE / "traces" / "add_ktn"


def screen(name: str) -> ScreenState:
    return build_state((SCREENS / f"{name}.xml").read_text(), "com.skylark.air", "com.skylark.air.MainActivity", 1080, 2400)


def by_id(s: ScreenState, rid: str):
    return next(e for e in s.numbered if e.resource_id.endswith(rid))


@pytest.fixture(scope="module")
def compiled():
    spec = CompiledRoutine.model_validate_json((TRACE / "spec.json").read_text())
    return asyncio.run(compile_trace(TRACE, memory="Known traveler number: 55501234", spec=spec))


# ---- format -----------------------------------------------------------------------------------

def test_yaml_round_trip_keeps_every_field(compiled):
    routine, _ = compiled
    again = load_yaml(dump_yaml(routine))
    assert again.model_dump() == routine.model_dump()
    text = dump_yaml(routine)
    assert "type:" in text and "{{" in text and "field_equals:" in text  # the design doc's shape: single-key checks and actions


def test_render_fills_slots_everywhere():
    step = Step(id="s", intent="Open {{city}}", action=StepAction(kind="tap", target=Locator(text_has="{{city}}", resource_id="row_{{code}}")),
                post=[Check(kind="text_visible", text="Trip to {{city}}")])
    r = render(step, {"city": "Tampa", "code": "AB12CD"})
    assert r.intent == "Open Tampa" and r.action.target.text_has == "Tampa" and r.action.target.resource_id == "row_AB12CD"
    assert r.post[0].text == "Trip to Tampa"


# ---- locators ---------------------------------------------------------------------------------

def test_text_similarity_segments_renames_and_traps():
    sim = locators.text_similarity
    assert sim("Next trip", "Next trip · Denver · Sat, Nov 14, 2026") == 0.95  # a whole part of a merged label
    assert sim("Check in", "Check-in now") == pytest.approx(0.783, abs=0.01)  # a rename
    assert sim("Check in", "Confirm check-in") < locators.STRICT  # a different button must not pass on words alone
    assert sim("Continue", "Next") == 0.0


def test_locator_finds_a_button_by_id_text_and_type():
    s = screen("skylark_trip")
    target = by_id(s, "btn_change_seat")
    loc = locators.build(target, s)
    m = locators.locate(loc, s)
    assert m.ok and m.element.index == target.index and m.score > 0.95


def test_renamed_button_needs_the_relaxed_threshold_and_ids_carry_it():
    s = screen("skylark_trip")
    target = by_id(s, "btn_change_seat")
    loc = locators.build(target, s).model_copy(update={"text": "Pick seats"})  # as if the label was renamed since recording
    assert not locators.locate(loc, s).ok
    m = locators.locate(loc, s, threshold=locators.RELAXED)
    assert m.ok and m.element.index == target.index


def test_input_based_locator_never_picks_another_trip():
    s = screen("skylark_trips")
    loc = Locator(resource_id="trip_row_*", text_has="{{trip_city}}", kind="Button", in_list=True)
    chicago = locators.locate(loc, s, {"trip_city": "Chicago"})
    assert chicago.ok and "Chicago" in chicago.element.label
    assert not locators.locate(loc, s, {"trip_city": "Dallas"}, threshold=locators.RELAXED).ok  # not on screen: no match at all


def test_check_role_needs_text_evidence():
    s = screen("skylark_home")
    title = Locator(resource_id="screen_title", text="My Trips", kind="Text")  # the trips screen's title
    assert not locators.locate(title, s, threshold=locators.RELAXED, role="check").ok  # "SkyLark Air" shares the ID only
    assert locators.locate(title, screen("skylark_trips"), role="check").ok  # on the right screen it passes strict


def test_data_segments_in_ids_become_globs():
    assert _glob_data_segments("trip_row_PT4R8Z") == "trip_row_*"
    assert _glob_data_segments("btn_confirm_checkin") == "btn_confirm_checkin"
    assert locators.id_matches("trip_row_*", "trip_row_KX7Q2M") and not locators.id_matches("trip_row_*", "trip_rows")


def test_contains_value_respects_word_boundaries():
    assert contains_value("Seat 12C, aisle", "12C") and not contains_value("Seat 112C", "12C")


# ---- checks -----------------------------------------------------------------------------------

def test_derived_post_checks_describe_the_new_screen():
    before, after = screen("skylark_home"), screen("skylark_trip")
    tap = by_id(before, "card_next_trip")
    post = chk.derive_post(before, after, "tap", tap, None, {"trip_city": "Chicago"})
    kinds = [c.kind for c in post]
    assert kinds[0] == "screen_changed" and "element_present" in kinds
    assert all(chk.evaluate(c, after, {}, before=before).passed for c in post)
    assert not all(chk.evaluate(c, before, {}, before=before).passed for c in post)


def test_generalized_checks_drop_booking_data_but_keep_inputs():
    c = Check(kind="element_present", locator=Locator(resource_id="screen_title", text="Trip to Chicago", kind="Text"))
    g = generalize_check(c, {"trip_city": "Chicago"}, [])
    assert g is not None and g.locator.text == "Trip to {{trip_city}}"
    gate = Check(kind="element_present", locator=Locator(resource_id="row_gate", text="Gate · B12", kind="Text"))
    g2 = generalize_check(gate, {"trip_city": "Chicago"}, ["B12"])
    assert g2 is not None and g2.locator.text is None and g2.locator.resource_id == "row_gate"
    assert generalize_check(Check(kind="text_visible", text="SL 482"), {}, []) is None
    assert bind_inputs("Seat changed to 12C", {"seat": "12C"}) == "Seat changed to {{seat}}"


# ---- compiler -----------------------------------------------------------------------------------

def test_only_verified_runs_compile(tmp_path):
    bad = tmp_path / "t"
    bad.mkdir()
    (bad / "run.json").write_text(json.dumps({"task_id": "t", "goal": "g", "status": "done_unverified", "check": {"passed": False}}))
    (bad / "steps.jsonl").write_text("")
    from routines.compiler import NotCompilable
    with pytest.raises(NotCompilable):
        load_trace(bad)


def test_clean_keeps_the_four_real_actions():
    _, records = load_trace(TRACE)
    steps, dropped = clean(TRACE, records)
    assert [s.kind for s in steps] == ["tap", "tap", "type", "tap"]


def test_compiled_routine_generalizes_trip_and_number(compiled):
    routine, report = compiled
    assert set(routine.inputs) >= {"trip_city"}
    ktn_input = next(n for n, s in routine.inputs.items() if s.example == "55501234")
    assert routine.inputs[ktn_input].from_memory
    kinds = [s.action.kind for s in routine.steps]
    assert kinds == ["tap", "scroll_until", "tap", "type", "tap"]  # a scroll_until was added before the input-based list tap
    row = routine.steps[2].action.target
    assert row.text_has == "{{trip_city}}" and row.resource_id == "trip_row_*"
    typed = routine.steps[3]
    assert typed.action.value == "{{" + ktn_input + "}}"
    assert any(c.kind == "field_equals" for c in typed.post)
    for st in routine.steps:  # no booking data hard-coded in any check
        for c in st.pre + st.post:
            assert "PT4R8Z" not in c.model_dump_json() and "SL 1190" not in c.model_dump_json()


# ---- outputs ----------------------------------------------------------------------------------

def test_extract_value_reads_parts_and_strips_labels():
    s = screen("skylark_trip")
    assert extract_value(Extract(near="Gate", locator=Locator(resource_id="row_gate", kind="Text"), segment=1), s, {}) == "B12"
    assert extract_value(Extract(near="Seat"), s, {}) == "14C"
    assert extract_value(Extract(near="Nothing like this"), s, {}) is None


# ---- patches and the store --------------------------------------------------------------------

def _routine():
    spec = CompiledRoutine.model_validate_json((TRACE / "spec.json").read_text())
    r, _ = asyncio.run(compile_trace(TRACE, memory="Known traveler number: 55501234", spec=spec))
    return r


def test_apply_patches_inserts_replaces_removes_and_relocates():
    r = _routine()
    extra = Step(id="extra", intent="Tap Looks good", action=StepAction(kind="tap", target=Locator(text="Looks good")), optional=True)
    new_loc = Locator(resource_id="btn_save_ktn", text="Save number", kind="Button")
    patched, changes = apply_patches(r, [
        Patch("insert_after", r.steps[0].id, "inserted", steps=[extra]),
        Patch("locator", r.steps[-1].id, "relabelled", locator=new_loc),
        Patch("remove", r.steps[1].id, "removed"),
    ])
    assert len(changes) == 3
    ids = [s.id for s in patched.steps]
    assert ids[1] == "extra" and r.steps[1].id not in ids
    assert patched.steps[-1].action.target.text == "Save number"
    assert r.steps[1].id in [s.id for s in r.steps]  # the base version is untouched


def test_store_trial_activate_and_rollback(tmp_path):
    store = RoutineStore(tmp_path)
    v1 = store.add(_routine())
    assert v1.version == 1 and store.index(v1.routine)["active"] == 1
    extra = Step(id="extra", intent="x", action=StepAction(kind="back"), optional=True)
    t2 = store.propose(v1, [Patch("insert_after", v1.steps[0].id, "inserted", steps=[extra])], "task")
    assert t2.version == 2 and t2.status == "trial" and store.index(v1.routine)["active"] == 1
    store.reject(v1.routine, 2, {"passed": False})
    assert store.index(v1.routine)["active"] == 1 and store.get(v1.routine, 2).status == "rejected"
    t3 = store.propose(v1, [Patch("insert_after", v1.steps[0].id, "inserted", steps=[extra])], "task")
    store.activate(v1.routine, t3.version, {"passed": True})
    assert store.index(v1.routine)["active"] == 3 and store.get(v1.routine, 1).status == "retired"


def test_recompile_flag_after_most_recent_runs_fail(tmp_path):
    from routines.executor import RunOutcome
    store = RoutineStore(tmp_path)
    r = store.add(_routine())
    flags = [store.record_run(r.routine, RunOutcome(r.routine, 1, f"t{i}", status)) for i, status in
             enumerate(["done", "agent_done", "failed", "agent_done", "failed"])]
    assert flags[-1] is True and flags[2] is False


def _labels_screen(labels: list[tuple[str, str, bool]]) -> ScreenState:
    """A tiny screen: (kind, label, in_list) per element, stacked top to bottom."""
    from routines.screens import screen_from_tree
    els = [{"index": i, "parent": None, "number": i + 1, "kind": k, "class": "android.widget.TextView", "label": lab, "text": lab,
            "bounds": [0, 100 * i, 1080, 100 * i + 90], "in_list": in_list} for i, (k, lab, in_list) in enumerate(labels)]
    return screen_from_tree({"package": "app", "activity": "A", "elements": els, "width": 1080, "height": 2400})


def test_extract_next_element_and_first_in_list():
    s = _labels_screen([("Text", "Seat", False), ("Text", "22F", False), ("Button", "KODAK AA (24 Pack)", True),
                        ("Button", "$13.49", True), ("Button", "$23.99", True)])
    assert extract_value(Extract(near="Seat", next_element=True), s, {}) == "22F"
    assert extract_value(Extract(pattern=r"\$\d+\.\d+", first_in_list=True), s, {}) == "$13.49"


def test_accents_do_not_break_input_matching():
    assert contains_value("Caffè Latte", "Caffe Latte")
    s = _labels_screen([("Button", "Caffè Latte", True), ("Button", "Iced Caffè Latte", True)])
    m = locators.locate(Locator(text_has="{{drink}}", kind="Button"), s, {"drink": "Caffe Latte"})
    assert m.element is not None and m.element.label == "Caffè Latte"  # the row that is exactly the input wins over one that contains it


def test_screen_without_ids_does_not_count_ids_against_elements():
    s = _labels_screen([("Text", "SkyLark Air", False), ("Button", "My Trips", False), ("Button", "Profile", False)])
    title = Locator(resource_id="screen_title", text="SkyLark Air", kind="Text")
    assert locators.locate(title, s, role="check").ok  # strict: the app shows no IDs anywhere, so the label carries it
    tab = Locator(resource_id="nav_trips", text="My Trips", kind="Button")
    assert locators.locate(tab, s).element.label == "My Trips"
