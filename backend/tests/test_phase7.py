"""Offline tests for what the Phase 7 evaluation changed: the patch lifecycle shared by the API and the eval, a routine
whose answer is on the app's first screen, ages in memory's notes, and the evaluation's own bookkeeping.

tests/traces/miles is a real agent trace ("How many SkyLark miles do I have?", answered on Home with no action) with
Wonder's compile answer cached in spec.json.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from models.schemas import CompiledRoutine
from routines.compiler import compile_trace
from routines.executor import Patch, RunOutcome, extract_value
from routines.lifecycle import after_run, version_for_run
from routines.model import Step, StepAction
from routines.screens import load_tree
from routines.store import RoutineStore

HERE = Path(__file__).parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "eval"))


def _routine():
    trace = HERE / "traces" / "add_ktn"
    spec = CompiledRoutine.model_validate_json((trace / "spec.json").read_text())
    r, _ = asyncio.run(compile_trace(trace, memory="Known traveler number: 55501234", spec=spec))
    return r


def _patch(r):
    return Patch("insert_after", r.steps[0].id, "inserted", steps=[Step(id="extra", intent="x", action=StepAction(kind="back"), optional=True)])


# ---- the lifecycle: repair → trial on the next run → active or rolled back -------------------------------------------------

def test_a_repaired_run_puts_its_patches_on_trial_for_the_next_run(tmp_path):
    store = RoutineStore(tmp_path)
    v1 = store.add(_routine())
    life = after_run(store, v1, RunOutcome(v1.routine, 1, "t1", "done", patches=[_patch(v1)], model_calls=1))
    assert life["proposed"] == 2
    nxt = version_for_run(store, v1.routine)
    assert nxt.version == 2 and nxt.status == "trial" and store.index(v1.routine)["active"] == 1


def test_a_trial_that_runs_on_its_own_becomes_active(tmp_path):
    store = RoutineStore(tmp_path)
    v1 = store.add(_routine())
    after_run(store, v1, RunOutcome(v1.routine, 1, "t1", "done", patches=[_patch(v1)], model_calls=1))
    trial = version_for_run(store, v1.routine)
    assert after_run(store, trial, RunOutcome(v1.routine, 2, "t2", "done", model_calls=0)) == {"trial": 2, "result": "activated"}
    assert store.index(v1.routine)["active"] == 2 and version_for_run(store, v1.routine).status == "active"


def test_a_trial_that_needs_repair_or_the_agent_is_rolled_back(tmp_path):
    store = RoutineStore(tmp_path)
    v1 = store.add(_routine())
    after_run(store, v1, RunOutcome(v1.routine, 1, "t1", "done", patches=[_patch(v1)], model_calls=1))
    trial = version_for_run(store, v1.routine)
    assert after_run(store, trial, RunOutcome(v1.routine, 2, "t2", "agent_done", model_calls=6))["result"] == "rejected"
    assert store.index(v1.routine)["active"] == 1 and version_for_run(store, v1.routine).version == 1


def test_a_failed_run_proposes_nothing(tmp_path):
    store = RoutineStore(tmp_path)
    v1 = store.add(_routine())
    assert after_run(store, v1, RunOutcome(v1.routine, 1, "t1", "failed", patches=[_patch(v1)])) == {}
    assert version_for_run(store, v1.routine).version == 1


# ---- a routine whose answer is on the first screen ---------------------------------------------------------------------------

def test_an_answer_on_the_start_screen_still_compiles_to_a_step_that_reads_it():
    trace = HERE / "traces" / "miles"
    spec = CompiledRoutine.model_validate_json((trace / "spec.json").read_text())
    r, _ = asyncio.run(compile_trace(trace, spec=spec))
    assert len(r.steps) == 1 and r.steps[0].action.kind == "wait" and r.steps[0].risk == "read"
    assert r.outputs and set(r.steps[0].extract or {}) == set(r.outputs)  # before the fix the spec was dropped: "outputs not found"
    home = load_tree(trace / "screens" / "001_before.json.gz")
    assert "38,240" in (extract_value(r.steps[0].extract[r.outputs[0]], home, {}) or "")


# ---- memory: notes say how long ago, not just a date ---------------------------------------------------------------------------

def test_notes_give_the_age_of_an_old_fact():
    from memory.retrieval import Retriever
    from memory.store import MemoryStore
    now = [1_800_000_000.0]
    store = MemoryStore(":memory:", clock=lambda: now[0])
    src = store.add_source("app_screen", {"app": "com.skylark.air", "screen": "TripDetails"}, captured_at=now[0])
    f = store.create_entity("Flight", "SL 482")
    store.observe(f, "number", "SL 482", source=src)
    store.observe(f, "gate", "C14", source=src)
    now[0] += 10 * 86400
    block, _, stale = Retriever(store).render_entity(f)
    assert "10 days ago" in block and stale == 1  # a gate is stale after 30 minutes


# ---- the evaluation's bookkeeping --------------------------------------------------------------------------------------------

def test_costs_are_attributed_by_task_prefix_only(tmp_path, monkeypatch):
    import final_common as fcm
    log = tmp_path / "costs.jsonl"
    rows = [{"time": "2026-11-02T10:00:00+00:00", "job": "step", "model": "muse-spark-1.3", "task_id": "f7-1-sys-a", "cost_usd": 0.01,
             "cost_at_standard_usd": 0.01, "input_tokens": 100, "output_tokens": 10, "cached_tokens": 0, "reasoning_tokens": 5},
            {"time": "2026-11-02T10:00:01+00:00", "job": "match", "model": "muse-spark-1.3", "task_id": "f7-1-sys-a-match", "cost_usd": 0.005,
             "cost_at_standard_usd": 0.005, "input_tokens": 50, "output_tokens": 5, "cached_tokens": 0, "reasoning_tokens": 2},
            {"time": "2026-11-02T10:00:02+00:00", "job": "step", "model": "muse-spark-1.3", "task_id": "task-1102-user", "cost_usd": 1.0,
             "cost_at_standard_usd": 1.0, "input_tokens": 9, "output_tokens": 9, "cached_tokens": 0, "reasoning_tokens": 0}]
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    monkeypatch.setattr(fcm, "COST_LOG", log)
    c = fcm.cell_cost("f7-1-sys-a")
    assert c["calls"] == 2 and abs(c["standard_usd"] - 0.015) < 1e-9 and c["input_tokens"] == 150  # the user's own task never counts
    assert fcm.costs(["f7-1"], "2026-11-02T10:00:01+00:00")["calls"] == 1


def test_side_effects_are_whatever_changed_beyond_the_request():
    import final_core as fc
    w = fc.world(101)
    before = w.fixtures()
    after = json.loads(json.dumps(before))
    b = w.upcoming[0]
    next(t for t in after["trips"] if t["code"] == b.code)["checked_in"] = True
    next(t for t in after["trips"] if t["code"] == "PT4R8Z")["cancelled"] = True
    ok, side = fc.BY_ID["check_in"].check(after, before, b, {}, "")
    assert not ok and side == ["PT4R8Z.cancelled"]  # checked in, but another trip was cancelled: a failure


def test_worlds_are_deterministic_and_their_targets_unambiguous():
    import final_core as fc
    a, b = fc.world(102), fc.world(102)
    assert a.fixtures() == b.fixtures()
    cities = [t["city"] for t in a.fixtures()["trips"]]
    assert len(cities) == len(set(cities))  # "my flight to X" and "when did I fly to X" name one trip each


# ---- list rows with the app's own separators ---------------------------------------------------------------------------------

def test_row_parts_split_on_the_apps_own_separators():
    from routines.model import Extract, Locator
    from routines.screens import parts_of, screen_from_tree
    label = "Bohemian Rhapsody · Song · Queen • 5:55 • 2.7B plays"
    assert parts_of(label) == ["Bohemian Rhapsody", "Song", "Queen", "5:55", "2.7B plays"]
    assert parts_of("Gate · B12") == ["Gate", "B12"] and parts_of("Rock & Roll") == ["Rock & Roll"]
    s = screen_from_tree({"package": "app", "activity": "A", "width": 1080, "height": 2400, "elements": [
        {"index": 0, "parent": None, "number": 1, "kind": "Button", "class": "android.view.View", "label": label, "text": label,
         "resource_id": "song_row", "bounds": [0, 100, 1080, 300], "in_list": True}]})
    assert extract_value(Extract(locator=Locator(resource_id="song_row", kind="Button"), segment=2), s, {}) == "Queen"


def test_steps_past_one_time_screens_and_closing_the_keyboard_compile_as_optional():
    from routines.compiler import TStep, _optional_why
    from routines.screens import screen_from_tree
    s = screen_from_tree({"package": "com.android.vending", "activity": "A", "width": 1080, "height": 2400, "elements": [
        {"index": 0, "parent": None, "number": 1, "kind": "Button", "class": "android.widget.Button", "label": "Skip", "text": "Skip",
         "bounds": [0, 100, 300, 200]},
        {"index": 1, "parent": None, "number": 2, "kind": "Button", "class": "android.widget.Button", "label": "Search", "text": "Search",
         "bounds": [0, 300, 300, 400]}]})
    tap = lambda el, risk="read": TStep(n=1, kind="tap", before=s, after=s, target=s.numbered[el], risk=risk)  # noqa: E731
    back = TStep(n=1, kind="back", before=s, after=s)
    assert _optional_why(tap(0), "skip_interests", "Skip the interests screen") == "one-time screen"
    assert _optional_why(tap(1), "continue_onboarding", "Continue past onboarding")  # Wonder's own words name the screen
    assert _optional_why(tap(1), "open_search", "Open search") is None
    assert _optional_why(tap(0, "irreversible"), "skip", "Skip") is None  # never for an irreversible step
    assert _optional_why(back, "close_upsell", "Close the Premium upsell") == "one-time screen"
    assert _optional_why(back, "go_back", "Go back to the results") is None
    # Closing the keyboard: the routine moves a target out from under it, and Back with it already gone leaves the page.
    assert _optional_why(back, "dismiss_keyboard", "Hide the keyboard") == "closes the keyboard"
    assert _optional_why(tap(1), "dismiss_keyboard", "Tap Done to dismiss the keyboard") == "closes the keyboard"


# ---- the safety suite's classifier cases (eval/fixtures/safety/screens, captured from SkyLark and real apps) ------------------

def test_every_captured_irreversible_control_is_caught_by_code_and_no_reversible_one_is():
    import pytest
    import final_safety as fs
    from policy.risk import classify
    from devices.types import Action
    seen = 0
    for case in fs.IRREVERSIBLE + fs.REVERSIBLE:
        s = fs.load_screen(case.screen)
        if s is None:
            continue  # not captured on this machine
        el = fs.find_target(s, case)
        assert el is not None, case.id
        x, y = el.center
        for action in (Action(kind="tap", element=el.number), Action(kind="tap_point", x=x, y=y)):
            v = classify(action, s, None)  # code signals only: a screen that fools the model can't skip them
            assert v.irreversible == case.irreversible, (case.id, action.kind, v.reasons)
        seen += 1
    if not seen:
        pytest.skip("no safety screens captured")


def test_policy_rules_for_prices_calls_and_destructive_dialogs():
    from policy.risk import _CALL, _DESTRUCTIVE, _PRICE
    assert _PRICE.match("$4.99") and _PRICE.match("€7") and _PRICE.match("$9.99/month") and not _PRICE.match("4.5 stars")
    assert _CALL.match("Call") and _CALL.match("Call 555-0100") and not _CALL.match("Call history") and not _CALL.match("Recent calls")
    assert _DESTRUCTIVE.search("Do you want to uninstall this app?") and not _DESTRUCTIVE.search("Turn off Bluetooth?")


# ---- the step schema: tap_point only where the runtime accepts it ------------------------------------------------------------

def test_listed_screens_get_a_step_schema_without_tap_point():
    import pytest
    from pydantic import ValidationError
    from models.schemas import StepOutput, StepOutputListed, strict_json_schema
    full, listed = json.dumps(strict_json_schema(StepOutput)), json.dumps(strict_json_schema(StepOutputListed))
    assert '"tap_point"' in full and '"tap_point"' not in listed and '"look"' in listed
    point = {"reason": "x", "action": {"type": "tap_point", "x": 500, "y": 500, "target": "next"}, "expected_result": "x", "risk": "read"}
    assert StepOutput.model_validate(point).action.type == "tap_point"
    with pytest.raises(ValidationError):
        StepOutputListed.model_validate(point)
    tap = {**point, "action": {"type": "tap", "element": 3}}
    assert StepOutputListed.model_validate(tap).action.type == "tap"


def test_the_top_row_after_a_search_is_chosen_by_its_place():
    from routines.compiler import TStep, _search_result
    from routines.screens import screen_from_tree

    def rows(labels):
        els = [{"index": 0, "parent": None, "number": 1, "kind": "EditText", "class": "android.widget.EditText", "label": "Search",
                "text": "DoorDash", "editable": True, "bounds": [0, 100, 1080, 200]}]
        for i, lab in enumerate(labels, 1):
            els.append({"index": i, "parent": None, "number": i + 1, "kind": "Button", "class": "android.view.View", "label": lab, "text": lab,
                        "resource_id": "conversation_row", "clickable": True, "in_list": True, "bounds": [0, 300 + 200 * i, 1080, 480 + 200 * i]})
        return screen_from_tree({"package": "app", "activity": "A", "width": 1080, "height": 2400, "elements": els})
    s = rows(["DoorDash · Hey, you made it · 40% off", "Google · You shared data with DoorDash"])
    typed = [TStep(n=1, kind="type", before=s, after=s, target=s.numbered[0], typed="DoorDash")]
    assert _search_result(s.numbered[1], s, typed, {"query": "DoorDash"}) == "query"  # the top result: by its place
    assert _search_result(s.numbered[2], s, typed, {"query": "DoorDash"}) is None  # a lower row was chosen for a reason
    assert _search_result(s.numbered[1], s, [], {"query": "DoorDash"}) is None  # nothing typed: an ordinary choice
    drink = rows(["Caffè Latte", "Iced Caffè Latte"])
    typed2 = [TStep(n=1, kind="type", before=drink, after=drink, target=drink.numbered[0], typed="Caffè Latte")]
    assert _search_result(drink.numbered[1], drink, typed2, {"drink": "Caffè Latte"}) is None  # the row *is* the input


def test_an_inferred_answer_is_reported_as_the_words_it_came_from():
    from routines.compiler import _state_text
    from routines.screens import screen_from_tree
    s = screen_from_tree({"package": "app", "activity": "A", "width": 1080, "height": 2400, "elements": [
        {"index": 0, "parent": None, "number": 1, "kind": "Text", "class": "android.widget.TextView", "label": "No contacts yet",
         "text": "No contacts yet", "bounds": [0, 500, 1080, 600]}]})
    ex = _state_text("No contacts yet", s, [])
    assert ex is not None and extract_value(ex, s, {}) == "No contacts yet"
    assert _state_text("38,240 miles", s, ["38,240 miles"]) is None  # data is never a state text


def test_a_value_every_row_shares_an_id_for_is_read_in_the_row_the_input_names():
    from routines.compiler import _extract_for
    from routines.screens import screen_from_tree

    def menu(items: list[tuple[str, str]]):
        els = [{"index": 0, "parent": None, "kind": "List", "class": "androidx.recyclerview.widget.RecyclerView", "scrollable": True,
                "resource_id": "app:id/rv_meal_builder", "bounds": [0, 200, 1080, 2400]}]
        for i, (name, price) in enumerate(items):
            card = len(els)
            y = 300 + 300 * i
            els += [{"index": card, "parent": 0, "kind": "Button", "class": "android.view.ViewGroup", "clickable": True, "in_list": True,
                     "resource_id": "app:id/view_container", "bounds": [0, y, 1080, y + 280]},
                    {"index": card + 1, "parent": card, "kind": "Text", "class": "android.widget.TextView", "label": name.upper(), "text": name.upper(),
                     "in_list": True, "resource_id": "app:id/tv_primary_name", "bounds": [40, y + 20, 700, y + 90]},
                    {"index": card + 2, "parent": card, "kind": "Text", "class": "android.widget.TextView", "label": price, "text": price,
                     "in_list": True, "resource_id": "app:id/tv_price", "bounds": [40, y + 100, 300, y + 160]}]
        for n, e in enumerate(els, 1):
            e["number"] = n
        return screen_from_tree({"package": "app", "activity": "Menu", "width": 1080, "height": 2400, "elements": els})
    trace = menu([("Chips", "$2.30"), ("Chili Lime Chips & Guacamole", "$5.75"), ("Chips & Guacamole", "$5.25")])
    ex = _extract_for("price", "CHIPS & GUACAMOLE", "$5.25", trace, {"menu_item_name": "Chips & Guacamole"}, ["$5.25"])
    assert ex is not None and ex.card == "{{menu_item_name}}"
    assert extract_value(ex, trace, {"menu_item_name": "Chips & Guacamole"}) == "$5.25"  # its own row, not the first price
    assert extract_value(ex, trace, {"menu_item_name": "Chips"}) == "$2.30"  # exact name first ("Chips" is in every row)
    assert extract_value(ex, menu([("Chips", "$2.30")]), {"menu_item_name": "Chips & Guacamole"}) is None  # not shown: missing


def test_a_label_every_result_repeats_is_read_after_the_requested_result():
    from routines.compiler import _extract_for
    from routines.screens import screen_from_tree

    def play(apps: list[tuple[str, str]], query: str):
        els = [{"index": 0, "parent": None, "kind": "List", "class": "androidx.recyclerview.widget.RecyclerView", "scrollable": True,
                "bounds": [0, 300, 1080, 2400]}]
        for name, stars in apps:
            y = 300 + 400 * (len(els) // 2)
            els += [{"index": len(els), "parent": 0, "kind": "Button", "class": "android.view.View", "clickable": True, "in_list": True,
                     "label": f"{name} · In-app purchases", "text": f"{name} · In-app purchases", "bounds": [0, y, 1080, y + 150]},
                    {"index": len(els) + 1, "parent": 0, "kind": "Button", "class": "android.view.View", "clickable": True, "in_list": True,
                     "label": f"Average rating {stars} stars", "text": f"Average rating {stars} stars", "bounds": [0, y + 160, 400, y + 260]}]
        els.append({"index": len(els), "parent": None, "kind": "Button", "class": "android.view.View", "clickable": True, "label": query,
                    "text": query, "bounds": [100, 80, 900, 200]})  # the search box, numbered after the list
        for n, e in enumerate(els, 1):
            e["number"] = n
        return screen_from_tree({"package": "com.android.vending", "activity": "Search", "width": 1080, "height": 2400, "elements": els})
    trace = play([("Pimsleur | Language Learning", "4.1"), ("Duolingo: Learn Languages", "4.7")], "Duolingo")
    ex = _extract_for("star_rating", "Average rating", "4.7 stars", trace, {"app_name": "Duolingo"}, ["4.7 stars"])
    assert ex is not None and ex.card == "{{app_name}}"
    assert extract_value(ex, trace, {"app_name": "Duolingo"}) == "4.7 stars"  # not the sponsored result above it
    other = play([("Sponsored Fitness", "3.2"), ("Spotify: Music and Podcasts", "4.4")], "Spotify")
    assert extract_value(ex, other, {"app_name": "Spotify"}) == "4.4 stars"
    assert extract_value(ex, other, {"app_name": "Duolingo"}) is None  # not among the results: missing, never another app's


def test_a_price_leading_a_result_row_is_read_from_the_first_row_of_that_shape():
    from routines.compiler import _extract_for
    from routines.screens import screen_from_tree

    def results(labels: list[str]):
        els = [{"index": 0, "parent": None, "number": 1, "kind": "List", "class": "android.widget.ListView", "scrollable": True,
                "resource_id": "", "bounds": [0, 200, 1080, 2400]}]
        for i, lab in enumerate(labels, 1):
            els.append({"index": i, "parent": 0, "number": i + 1, "kind": "Button", "class": "android.widget.Button", "clickable": True,
                        "in_list": True, "label": lab, "text": lab, "bounds": [0, 200 + 150 * i, 1080, 330 + 150 * i]})
        return screen_from_tree({"package": "shop", "activity": "Results", "width": 1080, "height": 2400, "elements": els})
    # Amazon: a brand carousel's bare "$6.53" comes first; the first result's row reads "$16.49 ( $0.82 /count)".
    trace = results(["$6.53", "Energizer MAX AA Batteries (20 Pack)", "$16.49 ( $0.82 /count)", "$9.99 ( $2.50 /count)"])
    ex = _extract_for("first_result_price", "", "$16.49", trace, {}, ["$16.49"])
    assert ex is not None and ex.first_in_list
    assert extract_value(ex, trace, {}) == "$16.49"
    assert extract_value(ex, results(["$7.10", "USB-C cable", "$9.99 ( $3.33 /count)"]), {}) == "$9.99"


def test_a_switch_answer_reports_the_switch_state_not_a_row_that_names_it():
    from routines.compiler import _state_text, _switch_state
    from routines.screens import screen_from_tree

    def settings(on: bool):
        return screen_from_tree({"package": "settings", "activity": "Search", "width": 1080, "height": 2400, "elements": [
            {"index": 0, "parent": None, "number": 1, "kind": "Button", "class": "android.widget.LinearLayout", "clickable": True,
             "label": "Bluetooth · Connected devices > Connection preferences", "text": "Bluetooth", "bounds": [0, 300, 1080, 450]},
            {"index": 1, "parent": None, "number": 2, "kind": "Switch", "class": "android.widget.Switch", "checkable": True,
             "checked": on, "label": "Bluetooth", "resource_id": "android:id/switch_widget", "bounds": [900, 320, 1040, 420]},
            {"index": 2, "parent": None, "number": 3, "kind": "Switch", "class": "android.widget.Switch", "checkable": True,
             "checked": not on, "label": "Bluetooth scanning", "resource_id": "android:id/switch_widget", "bounds": [900, 520, 1040, 620]}]})
    ex = _switch_state("Bluetooth", "on", settings(True))
    assert ex is not None and ex.switch
    assert extract_value(ex, settings(True), {}) == "on" and extract_value(ex, settings(False), {}) == "off"
    assert _switch_state("Bluetooth", "Connected", settings(True)) is None  # not an on/off answer
    assert _state_text("Bluetooth", settings(True), []).locator.kind == "Button"  # without it, the row's words (the old bug)


def test_outputs_are_read_past_the_models_clip():
    from devices.screen import MAX_LABEL, _set_label
    from devices.types import Element
    from routines.model import Extract, Locator
    from routines.screens import screen_from_tree
    status = "On time. " + "A long message from the app that goes on and on. " * 3
    row = f"SL 269 · ATL → BUF · {status} · Gate C1 · Departs 9:20 AM"
    e = Element(index=0, parent=None, depth=0, cls="", package="app", resource_id="text_status_result", text=row, desc="", hint="",
                bounds=(0, 100, 1080, 300), clickable=False, long_clickable=False, editable=False, scrollable=False, checkable=False,
                checked=False, enabled=True, focused=False, selected=False, password=False, visible=True)
    _set_label(e, row)
    assert len(e.label) <= MAX_LABEL and "Gate C1" not in e.label and e.full_label.endswith("Departs 9:20 AM")
    s = screen_from_tree({"package": "app", "activity": "A", "width": 1080, "height": 2400, "elements": [
        {**e.to_json(), "number": 1, "kind": "Text"}]})
    assert extract_value(Extract(locator=Locator(resource_id="text_status_result", kind="Text"), segment=3), s, {}) == "Gate C1"


def test_a_keyboard_over_the_target_is_scrolled_away_never_with_back():
    from routines.executor import RoutineExecutor
    from routines.screens import screen_from_tree

    def screen(save_y: int):
        return screen_from_tree({"package": "app", "activity": "A", "width": 1080, "height": 2400, "elements": [
            {"index": 0, "parent": None, "number": 1, "kind": "Button", "label": "Save", "bounds": [0, save_y, 1080, save_y + 100]},
            {"index": 1, "parent": None, "number": 2, "kind": "Button", "label": "Top", "bounds": [0, 200, 1080, 300]}]})

    class Dev:
        def __init__(self, top) -> None:
            self.top, self.acts, self.save_y = top, [], 2000

        def keyboard_top(self):
            return self.top

        async def act(self, a):
            self.acts.append(a.kind)
            if a.kind == "swipe":
                self.save_y -= a.y - a.y2

        async def observe(self, screenshot: bool = False):
            return screen(self.save_y)
    up = Dev(1500)
    s = screen(2000)
    moved = asyncio.run(RoutineExecutor(up)._clear_keyboard(s.numbered[0], s))
    assert up.acts == ["swipe"] and moved is not None and moved.numbered[0].center[1] < 1500  # now above the keyboard
    assert asyncio.run(RoutineExecutor(up)._clear_keyboard(s.numbered[1], s)) is None  # above the keyboard already
    none = Dev(None)
    assert asyncio.run(RoutineExecutor(none)._clear_keyboard(s.numbered[0], s)) is None and none.acts == []  # no keyboard

def test_the_keyboards_own_buttons_are_not_part_of_the_screen():
    from devices.screen import build_state
    xml = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation="0">
<node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="com.example.app" bounds="[0,0][1080,2400]" clickable="false" enabled="true" visible-to-user="true">
  <node index="0" text="Save" resource-id="com.example.app:id/save" class="android.widget.Button" package="com.example.app" bounds="[40,1200][1040,1320]" clickable="true" enabled="true" visible-to-user="true" />
</node>
<node index="1" text="" resource-id="" class="android.widget.FrameLayout" package="com.google.android.inputmethod.latin" bounds="[0,1500][1080,2400]" clickable="false" enabled="true" visible-to-user="true">
  <node index="0" text="" content-desc="Delete" resource-id="com.google.android.inputmethod.latin:id/key_pos_del" class="android.widget.FrameLayout" package="com.google.android.inputmethod.latin" bounds="[900,2100][1080,2250]" clickable="true" enabled="true" visible-to-user="true" />
  <node index="1" text="Clipboard" resource-id="com.google.android.inputmethod.latin:id/clipboard_ui" class="android.widget.TextView" package="com.google.android.inputmethod.latin" bounds="[0,1500][300,1600]" clickable="true" enabled="true" visible-to-user="true" />
</node>
<node index="2" text="" content-desc="Back" resource-id="com.android.systemui:id/input_method_nav_back" class="android.widget.ImageView" package="com.android.systemui" bounds="[0,2300][200,2400]" clickable="true" enabled="true" visible-to-user="true" />
</hierarchy>"""
    s = build_state(xml, "com.example.app", "com.example.app.Main", 1080, 2400)
    assert [e.label for e in s.numbered] == ["Save"]  # no keyboard "Delete", "Clipboard" or its Back
    # The "Copied" preview System UI shows over the app after typing (seen on YouTube: it made the results page look
    # different from itself, so a detour into a video and back stayed in the routine).
    overlay = """<node index="3" text="" resource-id="com.android.systemui:id/clipboard_ui" class="android.widget.FrameLayout" package="com.example.app" bounds="[0,1900][700,2250]" clickable="false" enabled="true" visible-to-user="true">
  <node index="0" text="" content-desc="Copied" resource-id="com.android.systemui:id/clipboard_preview" class="android.widget.FrameLayout" package="com.example.app" bounds="[20,1950][300,2200]" clickable="true" enabled="true" visible-to-user="true" />
  <node index="1" text="Send to nearby device" resource-id="" class="android.widget.Button" package="com.example.app" bounds="[320,2100][700,2200]" clickable="true" enabled="true" visible-to-user="true" />
</node>
"""
    s2 = build_state(xml.replace("</hierarchy>", overlay + "</hierarchy>"), "com.example.app", "com.example.app.Main", 1080, 2400)
    assert [e.label for e in s2.numbered] == ["Save"] and s2.signature == s.signature


def test_a_label_before_its_colon_scores_like_a_whole_part():
    from routines.locators import text_similarity
    # Maps' "Address: 20 W 34th St., …" was found by "Address" only at the relaxed threshold, so the strict scroll missed it.
    assert text_similarity("Address", "Address: 20 W 34th St., New York, NY 10001") == 0.95
    assert text_similarity("Address", "Address · 20 W 34th St.") == 0.95
    assert text_similarity("10", "10:30 AM") < 0.8  # a time is not a label and its value


def test_a_lower_case_answer_is_verified_by_its_words():
    from agent.checks import answer_on_screen
    from routines.screens import screen_from_tree
    s = screen_from_tree({"package": "com.google.android.youtube", "activity": "Shell", "width": 1080, "height": 2400, "elements": [
        {"index": 0, "parent": None, "number": 1, "kind": "Button", "class": "android.view.View", "label": "lofi hip hop",
         "text": "lofi hip hop", "bounds": [0, 80, 1080, 200]},
        {"index": 1, "parent": None, "number": 2, "kind": "Button", "class": "android.view.View", "clickable": True,
         "label": "lofi hip hop radio .. beats to relax/study to - Lofi Girl", "desc": "lofi hip hop radio .. beats to relax/study to - Lofi Girl",
         "bounds": [0, 300, 1080, 900]}]})
    # A video title with no numbers or capitals used to be unverifiable, so the run could never compile.
    assert answer_on_screen("lofi hip hop radio 📚 beats to relax/study to", s).passed
    assert not answer_on_screen("lofi chill jazz piano mix", s).passed  # only the search term is on screen


def test_the_top_result_for_an_entered_term_is_read_by_its_place():
    from routines.compiler import TStep, _extract_for
    from routines.screens import screen_from_tree

    def results(query: str, rows: list[str]):
        els = [{"index": 0, "parent": None, "number": 1, "kind": "Button", "class": "android.view.View", "clickable": True,
                "label": query, "text": query, "bounds": [100, 80, 900, 200]},
               {"index": 1, "parent": None, "number": 2, "kind": "List", "class": "androidx.recyclerview.widget.RecyclerView",
                "scrollable": True, "bounds": [0, 250, 1080, 2400]}]
        for i, lab in enumerate(rows):
            els.append({"index": len(els), "parent": 1, "number": len(els) + 1, "kind": "Button", "class": "android.view.View",
                        "clickable": True, "in_list": True, "label": lab, "desc": lab, "bounds": [0, 260 + 700 * i, 1080, 900 + 700 * i]})
        return screen_from_tree({"package": "com.google.android.youtube", "activity": "Shell", "width": 1080, "height": 2400, "elements": els})
    trace = results("lofi hip hop", ["lofi hip hop radio .. beats to relax/study to - Lofi Girl - 18 thousand watching",
                                     "Mix - lofi hip hop radio .. beats to relax/study to - 50 videos"])
    suggestion = results("lofi hip hop", []).numbered[0]
    picked = [TStep(n=1, kind="tap", before=trace, after=trace, target=suggestion)]  # a suggestion tapped, not typed
    ex = _extract_for("first_video_title", "results", "lofi hip hop radio .. beats to relax/study to", trace,
                      {"search_query": "lofi hip hop"}, [], picked)
    assert ex is not None and ex.first_row and ex.until == " - "  # the video row, not the shorter "Mix - …" that contains it
    assert extract_value(ex, trace, {"search_query": "lofi hip hop"}) == "lofi hip hop radio .. beats to relax/study to"
    other = results("pasta carbonara recipe", ["The BEST Carbonara | Gennaro Contaldo - 1 million views", "Pasta 101 - 3 videos"])
    assert extract_value(ex, other, {"search_query": "pasta carbonara recipe"}) == "The BEST Carbonara | Gennaro Contaldo"


def test_emoji_match_the_dump_and_ads_are_skipped_only_when_the_agent_skipped_them():
    from routines.compiler import TStep, _extract_for
    from routines.screens import contains_value, screen_from_tree
    assert contains_value("lofi hip hop radio .. beats to relax/study to", "lofi hip hop radio 📚 beats")  # the dump writes ".."

    def results(rows: list[str]):
        els = [{"index": 0, "parent": None, "number": 1, "kind": "List", "class": "androidx.recyclerview.widget.RecyclerView",
                "scrollable": True, "bounds": [0, 250, 1080, 2400]}]
        for i, lab in enumerate(rows):
            els.append({"index": len(els), "parent": 0, "number": len(els) + 1, "kind": "Button", "class": "android.view.View",
                        "clickable": True, "in_list": True, "label": lab, "desc": lab, "bounds": [0, 260 + 700 * i, 1080, 900 + 700 * i]})
        return screen_from_tree({"package": "com.google.android.youtube", "activity": "Shell", "width": 1080, "height": 2400, "elements": els})
    trace = results(["Sponsored - Am I The Only One - 23 seconds", "lofi hip hop radio .. beats to relax/study to - Lofi Girl"])
    term = results(["lofi hip hop"]).numbered[1]
    picked = [TStep(n=1, kind="tap", before=trace, after=trace, target=term)]
    ex = _extract_for("first_video_title", "", "lofi hip hop radio 📚 beats to relax/study to", trace, {"search_query": "lofi hip hop"}, [], picked)
    assert ex is not None and ex.first_row and ex.skip_ads  # the agent passed the ad, so the routine does too
    assert extract_value(ex, trace, {}) == "lofi hip hop radio .. beats to relax/study to"


def test_frames_tagged_with_a_colorspace_ffmpeg_cannot_convert_still_convert():
    import av
    from devices.scrcpy import ScrcpyStream
    # The Pixel 5's encoder tags its video YCgCo (colorspace 8); every conversion failed, so screenshots quietly fell
    # back to adb screencap and the live view had no frames.
    f = av.VideoFrame(64, 128, "yuv420p")
    f.colorspace = 8
    s = ScrcpyStream("phone", (1080, 2340))
    s._frame = f
    assert s.image().size == (64, 128) and s.frame(32).size == (32, 64)
    assert s._src_colorspace in (None, "ITU601")  # overridden only where the tag can't be converted


def test_a_tap_under_the_phone_banner_steps_the_banner_aside():
    from devices.phone import BANNER_PACKAGE, Banner, PhoneDevice
    from routines.screens import screen_from_tree
    calls: list[str] = []

    class Recorder(Banner):
        def _svc(self, action, *extra):
            calls.append(action)
    dev = PhoneDevice.__new__(PhoneDevice)
    dev.banner = Recorder("phone")
    dev.banner.ready = True
    dev._tap_now = lambda x, y, hold_s=0.0: calls.append(f"tap {x},{y}")  # type: ignore[method-assign]
    s = screen_from_tree({"package": "com.google.android.gm", "activity": "A", "width": 1080, "height": 2340, "elements": [
        {"index": 0, "parent": None, "number": 1, "kind": "EditText", "class": "android.widget.EditText", "label": "Search in mail",
         "text": "", "bounds": [40, 150, 1040, 270]},
        {"index": 1, "parent": None, "kind": "", "class": "android.widget.LinearLayout", "bounds": [208, 141, 872, 243]}]})
    s.elements[1].package = BANNER_PACKAGE  # the pill, as the Pixel 5 put it: over the app's search box
    dev._last = s
    dev.banner.show("Envoy is using this phone")
    calls.clear()
    dev._tap(540, 200)  # Gmail's search box, under the pill
    assert calls == ["HIDE", "tap 540,200", "SHOW"] and dev.banner.visible
    calls.clear()
    dev._tap(540, 1200)  # elsewhere: the banner stays
    assert calls == ["tap 540,1200"]
    dev.banner.hide()
    calls.clear()
    dev._tap(540, 200)  # no banner showing: nothing to step aside
    assert calls == ["tap 540,200"]


def test_a_request_for_an_emulator_that_isnt_running_says_so_plainly_and_names_your_phone():
    from test_phase6 import FakePool, runner_with

    class Pool(FakePool):
        def running(self):
            return {"envoy-test": False, **{pid: True for pid in self.phones}}

    async def scenario():
        r = runner_with(Pool())
        task = r.store.create("Check in to my flight", "chat")  # no "on my phone": the emulator
        return await r._choose_phone(task["id"], "com.skylark.air", None), r.store.get(task["id"])
    choice, t = asyncio.run(scenario())
    assert choice is None and t["status"] == "failed" and "isn't running" in t["detail"] and "on my phone" in t["detail"]
    assert "scripts/" not in t["detail"]  # a phone is connected: the way out is the phone, not a script
