"""Routine repair fixes (Oct 28): a routine that doesn't depend on an app's recent searches, repairs that count only on the
screen the step was meant to reach, no new version for a patch that changes nothing, and checks bound to an input are
never rewritten with one run's value.

tests/traces/starbucks_search holds Starbucks screens recorded on envoy-real: the menu, the search screen with the five
recent searches that broke the compiled routine ("Caffè Latte" and "Caffe Latte" among them), the Results list for a
typed "Caffè Latte", and the drink's page; and the routine as Phase 7 compiled it (starbucks_v1.yaml).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

import routines.executor as executor_mod
from agent.trace import TraceWriter
from devices.types import ActionResult
from models.schemas import Fail, StepOutput, Tap
from policy.approvals import ScriptedApprover
from routines.executor import ExecConfig, Patch, RoutineExecutor, RunOutcome
from routines.lifecycle import after_run
from routines.model import Check, Locator, Routine, Step, StepAction, load_yaml
from routines.screens import load_tree, norm, screen_from_tree
from routines.store import RoutineStore, same_program

HERE = Path(__file__).parent
REPO = HERE.parents[1]
SB = HERE / "traces" / "starbucks_search"
FAST = ExecConfig(pre_timeout_s=0.6, post_timeout_s=0.6, stable_s=0.2, poll_s=0.01, patch_screenshots=False)


@pytest.fixture(autouse=True)
def traces_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(executor_mod, "TraceWriter", lambda tid: TraceWriter(tid, root=tmp_path))


class NoModel:
    def call(self, *a, **kw):
        raise AssertionError("no model call expected")


class Model:
    """Repair answers in order: a tap on the element with that label (as the model chose in the failed run), else give up."""

    def __init__(self, taps: list[str]) -> None:
        self.taps, self.calls = list(taps), 0
        self.screen = None

    def call(self, job, content, **kw):
        self.calls += 1
        label = self.taps.pop(0) if self.taps else None
        el = next((e for e in self.screen().numbered if label and e.label == label), None) if label else None
        action = Tap(type="tap", element=el.number) if el is not None else Fail(type="fail", reason="nothing to try")
        out = StepOutput(reason=f"tap {label}", action=action, expected_result="", risk="read")
        return SimpleNamespace(parsed=out, cost_usd=0.0, cost_at_standard_usd=0.0)


class Starbucks:
    """Starbucks as recorded on envoy-real. The search screen keeps its recent searches; typing a drink and pressing Enter
    or tapping a recent search opens the Results list; the drink's row there opens its page."""

    def __init__(self, at: str) -> None:
        self.at, self.acts = at, []
        self.screens = {n: load_tree(SB / f"{n}.json.gz") for n in ("menu", "recent_searches", "results", "product")}

    async def observe(self, screenshot: bool = False):
        return self.screens[self.at]

    async def act(self, a):
        el = self.screens[self.at].numbered[a.element - 1] if a.element else None
        self.acts.append((a.kind, el.label if el else None, a.text))
        if self.at == "menu" and a.kind == "tap" and el.label == "Search Menu":
            self.at = "recent_searches"
        elif self.at == "recent_searches" and a.kind == "type" and a.submit:
            self.at = "results"
        elif self.at == "recent_searches" and a.kind == "tap" and el.cls.endswith("LinearLayout") and el.label != "RECENT SEARCHES":
            self.at = "results"
        elif self.at == "results" and a.kind == "tap" and el.cls.endswith("RelativeLayout") and norm(el.label) == norm("Caffè Latte"):
            self.at = "product"
        return ActionResult(ok=True, duration_ms=1.0)


def run(device, routine: Routine, inputs: dict[str, str], adapter=None, **kw) -> RunOutcome:
    ex = RoutineExecutor(device, adapter=adapter or NoModel(), approver=ScriptedApprover(approve=False), config=FAST)
    return asyncio.run(ex.run(routine, inputs, launch="never", allow_agent=False, **kw))


def from_step(r: Routine, step_id: str) -> Routine:
    return r.model_copy(update={"steps": r.steps[r.step_index(step_id):]})


# ---- a. Starbucks calories with recent searches in the app -------------------------------------------------------------------

def test_the_starbucks_routine_types_the_drink_whatever_the_recent_searches_show():
    r = load_yaml((REPO / "eval" / "results" / "final" / "real_compiled" / "starbucks.yaml").read_text())
    phone = Starbucks("menu")
    out = run(phone, from_step(r, "tap_search_menu"), {"drink_name": "Caffè Latte"}, allow_repair=False)
    assert out.status == "done" and out.outputs == {"calories": "190 calories"} and out.model_calls == 0
    assert ("type", "Search Menu", "Caffè Latte") in phone.acts and phone.at == "product"
    assert not [a for a in phone.acts if a[0] == "tap" and a[1] in ("Caffe Latte", "Caffè Mocha", "Caffe Mocha", "Caramel Macchiato")]


def test_the_compiled_starbucks_routine_stalls_on_the_recent_searches():
    """Why it was rewritten: its step taps the recent search for the drink, and "Caffè Latte" and "Caffe Latte" tie."""
    v1 = load_yaml((SB / "starbucks_v1.yaml").read_text())
    out = run(Starbucks("menu"), from_step(v1, "tap_search_menu"), {"drink_name": "Caffè Latte"}, allow_repair=False)
    assert out.status == "failed" and "select_recent_search_result" in out.detail and "no match" in out.detail


def test_the_starbucks_drink_step_needs_the_drinks_page_not_the_results_list():
    r = load_yaml((REPO / "eval" / "results" / "final" / "real_compiled" / "starbucks.yaml").read_text())
    step = r.steps[r.step_index("open_drink_product")]
    ex = RoutineExecutor(Starbucks("results"), adapter=NoModel(), config=FAST)
    screens = Starbucks("results").screens
    assert not ex._check(ex._specific(step.post), screens["results"], {"drink_name": "Caffè Latte"}, relaxed=True)[0]
    assert ex._check(ex._specific(step.post), screens["product"], {"drink_name": "Caffè Latte"})[0]
    assert "size_name" not in r.slots() and r.slots() <= set(r.inputs)


# ---- b. a repair counts only on the screen the step was meant to reach ---------------------------------------------------

def test_a_repair_onto_a_look_alike_of_the_drinks_page_does_not_count():
    """The failed cross-app run, replayed: the compiled routine's last step, from the recent-search screen, with the model
    tapping the recent search as it did. That opens the Results list, whose "Add to order" button relaxed-matches the
    page's "{{size_name}} Caffè Latte. Add to order" check: it was accepted and the run ended "outputs not found". Now the
    list is only the step's own starting screen, and the step then opens the drink's page."""
    v1 = load_yaml((SB / "starbucks_v1.yaml").read_text())
    phone = Starbucks("recent_searches")
    model = Model(["Caffè Latte"])
    model.screen = lambda: phone.screens[phone.at]
    out = run(phone, from_step(v1, "open_drink_product"), {"drink_name": "Caffè Latte"}, adapter=model)
    assert out.status == "done" and out.outputs == {"calories": "190 calories"} and phone.at == "product"
    # Since the routine fixes (Oct 28), the step first searches for the drink when no recent search names it the way
    # it expects, so it reaches the page with no repair; a repair, if one runs, is still the tap that reached its screen.
    assert out.model_calls <= 1
    assert [p.kind for p in out.patches] in ([], ["insert_before"])  # never "the element moved"


def _trip_app(after_tap: str) -> tuple[object, Routine]:
    """Home has a renamed "Journeys" button (the step wants "Trips"). Tapping it opens `after_tap`: the trip's screen with
    its title reworded (relaxed match) and its Check in button, or a look-alike with a similar title and no Check in."""
    def screen(name: str, els: list[tuple[str, str]]):
        return screen_from_tree({"package": "app", "activity": name, "signature": name, "elements": [
            {"index": i, "number": i + 1, "kind": k, "label": t, "text": t, "clickable": k == "Button", "bounds": [0, 200 * i, 1080, 200 * i + 150]}
            for i, (k, t) in enumerate(els)]})
    screens = {"home": screen("home", [("Button", "Journeys"), ("Text", "Welcome")]),
               "trip": screen("trip", [("Text", "Your trip to Denver is coming up"), ("Button", "Check in")]),
               "lookalike": screen("lookalike", [("Text", "Your trip to Denver was cancelled"), ("Button", "Rebook")]),
               "checked_in": screen("checked_in", [("Text", "You're checked in")])}

    class Phone:
        at = "home"

        async def observe(self, screenshot: bool = False):
            return screens[self.at]

        async def act(self, a):
            label = screens[self.at].numbered[a.element - 1].label
            self.at = {("home", "Journeys"): after_tap, ("trip", "Check in"): "checked_in"}.get((self.at, label), self.at)
            return ActionResult(ok=True, duration_ms=1.0)

    r = Routine(routine="trip", app="app", intent="Check in for my {{city}} trip", inputs={"city": {"example": "Denver"}}, steps=[
        Step(id="open_trip", intent="Open the trip", action=StepAction(kind="tap", target=Locator(text="Trips", kind="Button")),
             post=[Check(kind="element_present", locator=Locator(text="Trip to {{city}}", kind="Text"))]),
        Step(id="check_in", intent="Tap Check in", action=StepAction(kind="tap", target=Locator(text="Check in", kind="Button")),
             post=[Check(kind="element_present", locator=Locator(text="You're checked in", kind="Text"))])])
    return Phone(), r


def test_a_repair_that_lands_on_a_look_alike_screen_is_rejected():
    phone, r = _trip_app("lookalike")
    model = Model(["Journeys"])
    model.screen = lambda: asyncio.run(phone.observe())
    out = run(phone, r, {"city": "Denver"}, adapter=model)
    assert phone.at == "lookalike" and out.status == "failed"
    assert out.steps[0].status == "failed" and "repair gave up" in out.steps[0].detail
    assert out.patches == []  # nothing from the look-alike goes on trial


def test_a_repair_onto_the_renamed_screen_is_accepted_by_the_next_steps_anchor():
    phone, r = _trip_app("trip")
    model = Model(["Journeys"])
    model.screen = lambda: asyncio.run(phone.observe())
    out = run(phone, r, {"city": "Denver"}, adapter=model)
    assert out.status == "done" and phone.at == "checked_in" and out.model_calls == 1
    assert [p.kind for p in out.patches] == ["locator"] and out.patches[0].locator.text == "Journeys"


def test_a_relaxed_repair_followed_by_back_is_accepted_for_lack_of_evidence_against_it():
    """Chipotle (real-app pass, Oct 28): the zip field's check held only relaxed and the next step was Back, which shows
    nothing to look for. The repair must count, as before: only evidence against the screen rejects it."""
    phone, r = _trip_app("lookalike")
    r.steps[1] = Step(id="go_back", intent="Go back", action=StepAction(kind="back"), post=[Check(kind="screen_changed")])
    model = Model(["Journeys"])
    model.screen = lambda: asyncio.run(phone.observe())
    out = run(phone, r, {"city": "Denver"}, adapter=model)
    assert out.steps[0].status == "done" and out.model_calls == 1 and [p.kind for p in out.patches] == ["locator"]


# ---- c. a patch that changes nothing makes no version ------------------------------------------------------------------------

def _look_up_trip() -> Routine:
    return load_yaml((REPO / "eval" / "results" / "final" / "library" / "repeats" / "skylark_look_up_trip" / "v1.yaml").read_text())


def test_the_repeats_suites_look_up_trip_versions_were_identical():
    lib = REPO / "eval" / "results" / "final" / "library" / "repeats" / "skylark_look_up_trip"
    v1 = load_yaml((lib / "v1.yaml").read_text())
    assert all(same_program(v1, load_yaml((lib / f"v{n}.yaml").read_text())) for n in (2, 3, 4))
    assert not same_program(v1, v1.model_copy(update={"intent": "something else"}))


def test_a_patch_that_changes_nothing_logs_the_attempt_and_makes_no_version(tmp_path):
    store = RoutineStore(tmp_path)
    v1 = store.add(_look_up_trip())
    step = v1.steps[v1.step_index("open_trip_by_confirmation_code")]
    same = Patch("locator", step.id, "target found only by relaxed match; locator updated to the same", locator=step.action.target.model_copy())
    out = RunOutcome(v1.routine, 1, "t-same", "done", patches=[same])
    assert store.propose(v1, [same], "t-same") is None
    idx = store.index(v1.routine)
    assert [v["version"] for v in idx["versions"]] == [1] and not (tmp_path / v1.routine / "v2.yaml").exists()
    assert idx["patch_attempts"][-1]["result"] == "unchanged" and idx["patch_attempts"][-1]["source_task"] == "t-same"
    assert after_run(store, v1, out) == {"unchanged": 1}
    assert len(store.index(v1.routine)["patch_attempts"]) == 2 and store.index(v1.routine)["runs"][-1]["task_id"] == "t-same"
    moved = Patch("locator", step.id, "moved", locator=step.action.target.model_copy(update={"kind": "Text"}))
    assert after_run(store, v1, RunOutcome(v1.routine, 1, "t-moved", "done", patches=[moved])) == {"proposed": 2, "changes": ["moved"]}


# ---- d. a check bound to an input is never rewritten with the run's value ---------------------------------------------------

def test_a_relaxed_check_bound_to_an_input_is_not_patched_with_the_runs_value():
    """change_seat at L5 (Oct 28, 00:10): its trip-row check, {{trip_city}}, became "Omaha" in v2. That run started at 23:49,
    before e875c4a (23:51); re-run on faf09f0 the same case kept the slot (eval/results/repair/change_seat_L5_main.json)."""
    def screen(name, els):
        return screen_from_tree({"package": "app", "activity": name, "signature": name, "elements": [
            {"index": i, "number": i + 1, "kind": k, "label": t, "text": t, "clickable": k == "Button", "in_list": lst,
             "bounds": [0, 200 * i, 1080, 200 * i + 150]} for i, (k, t, lst) in enumerate(els)]})
    screens = {"home": screen("home", [("Button", "Trips", False)]),
               "trips": screen("trips", [("Text", "Upcoming trip to Omaha", False), ("Button", "Trip to Omaha · SL 1834", True),
                                         ("Button", "Trip to Denver · SL 220", True)])}

    class Phone:
        at = "home"

        async def observe(self, screenshot: bool = False):
            return screens[self.at]

        async def act(self, a):
            self.at = "trips"
            return ActionResult(ok=True, duration_ms=1.0)

    r = Routine(routine="trips", app="app", intent="Open my {{trip_city}} trip", inputs={"trip_city": {"example": "Denver"}}, steps=[
        Step(id="open_trips", intent="Open My Trips", action=StepAction(kind="tap", target=Locator(text="Trips", kind="Button")),
             post=[Check(kind="element_present", locator=Locator(text_has="{{trip_city}}", resource_id="trip_row_*", kind="Button", in_list=True)),
                   Check(kind="element_present", locator=Locator(text="Upcoming trip", kind="Text"))])])
    out = run(Phone(), r, {"trip_city": "Omaha"})
    assert out.status == "done" and out.steps[0].rung == 2  # both checks held only at the relaxed threshold
    assert not [p for p in out.patches if "Omaha" in p.description or (p.check and "Omaha" in p.check.describe())]
