"""A routine skips ahead only when the screen vouches for the later step (Oct 30).

When a step's after-checks fail, the executor asks whether the app went straight to a later step's screen. A step with
no before-checks and nothing to tap (a scroll, Back, a wait) is ready on any screen, so it used to count: on DoorDash's
breakfast menu, with no Deluxe Meal, doordash_order_meal v4 jumped from the meal's scroll to the scroll for its cheese
choice and wrote a patch dropping the meal's tap. tests/traces/doordash_breakfast/store.json.gz is that menu, recorded on
envoy-real (Oct 30 10:43 ET).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import routines.executor as executor_mod
from agent.trace import TraceWriter
from devices.types import ActionResult
from policy.approvals import ScriptedApprover
from routines.executor import ExecConfig, RoutineExecutor, RunOutcome
from routines.model import Check, Locator, Routine, Step, StepAction, load_yaml
from routines.screens import load_tree, screen_from_tree

HERE = Path(__file__).parent
REPO = HERE.parents[1]
FAST = ExecConfig(pre_timeout_s=0.6, post_timeout_s=0.6, stable_s=0.2, poll_s=0.01, patch_screenshots=False)


@pytest.fixture(autouse=True)
def traces_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(executor_mod, "TraceWriter", lambda tid: TraceWriter(tid, root=tmp_path))


class NoModel:
    def call(self, *a, **kw):
        raise AssertionError("no model call expected")


def run(device, routine: Routine) -> RunOutcome:
    ex = RoutineExecutor(device, adapter=NoModel(), approver=ScriptedApprover(approve=False), config=FAST)
    return asyncio.run(ex.run(routine, {}, launch="never", allow_repair=False, allow_agent=False))


class BreakfastMenu:
    """The Chick-fil-A store on its breakfast menu: no Deluxe Meal, however far it is scrolled."""

    def __init__(self) -> None:
        self.screen = load_tree(HERE / "traces" / "doordash_breakfast" / "store.json.gz")
        self.acts: list[str] = []

    async def observe(self, screenshot: bool = False):
        return self.screen

    async def act(self, a):
        self.acts.append(a.kind)
        return ActionResult(ok=True, duration_ms=1.0)


def test_a_scroll_with_nothing_on_screen_for_it_is_not_taken_as_skipped_to():
    v4 = load_yaml((REPO / "data" / "routines" / "doordash_order_meal" / "v4.yaml").read_text())
    i = v4.step_index("find_tap_meal_item")
    assert [s.id for s in v4.steps[i:i + 3]] == ["find_tap_meal_item", "tap_meal_item", "find_tap_meal_variant"]
    assert not v4.steps[i + 2].pre  # the scroll two steps ahead has no before-checks: "ready" anywhere
    phone = BreakfastMenu()
    out = run(phone, v4.model_copy(update={"steps": v4.steps[i:]}))
    assert out.status == "failed" and out.steps[0].id == "find_tap_meal_item" and out.steps[0].status == "failed"
    assert not any("skipped ahead" in r for r in out.steps[0].rungs)
    assert not [p for p in out.patches if p.kind == "remove"] and "tap" not in phone.acts


def _app():
    """Tapping Trips used to show a one-time "What's new" screen; now the app goes straight to the trip."""
    def screen(name: str, els: list[tuple[str, str]]):
        return screen_from_tree({"package": "app", "activity": name, "signature": name, "elements": [
            {"index": i, "number": i + 1, "kind": k, "label": t, "text": t, "clickable": k == "Button", "bounds": [0, 200 * i, 1080, 200 * i + 150]}
            for i, (k, t) in enumerate(els)]})
    screens = {"home": screen("home", [("Button", "Trips"), ("Text", "Welcome")]),
               "trip": screen("trip", [("Text", "Your trip to Denver"), ("Button", "Check in")]),
               "checked_in": screen("checked_in", [("Text", "You're checked in")])}

    class Phone:
        at = "home"

        async def observe(self, screenshot: bool = False):
            return screens[self.at]

        async def act(self, a):
            label = screens[self.at].numbered[a.element - 1].label if a.element else None
            self.at = {("home", "Trips"): "trip", ("trip", "Check in"): "checked_in"}.get((self.at, label), self.at)
            return ActionResult(ok=True, duration_ms=1.0)

    def routine(later: Step) -> Routine:
        return Routine(routine="trip", app="app", intent="Check in for my trip", steps=[
            Step(id="open_trips", intent="Open Trips", action=StepAction(kind="tap", target=Locator(text="Trips", kind="Button")),
                 post=[Check(kind="element_present", locator=Locator(text="What's new", kind="Text"))]),
            Step(id="dismiss_whats_new", intent="Dismiss What's new", action=StepAction(kind="tap", target=Locator(text="Got it", kind="Button")),
                 post=[Check(kind="screen_changed")]),
            later,
            Step(id="check_in", intent="Tap Check in", action=StepAction(kind="tap", target=Locator(text="Check in", kind="Button")),
                 post=[Check(kind="element_present", locator=Locator(text="You're checked in", kind="Text"))])])
    return Phone(), routine


@pytest.mark.parametrize("later", [
    Step(id="see_trip", intent="The trip's screen", pre=[Check(kind="element_present", locator=Locator(text="Your trip to Denver", kind="Text"))],
         action=StepAction(kind="wait", seconds=0.01), post=[]),  # its own before-check
    Step(id="find_check_in", intent="Scroll to Check in", action=StepAction(kind="scroll_until", direction="down", max_scrolls=2,
         target=Locator(text="Check in", kind="Button")), post=[Check(kind="element_present", locator=Locator(text="Check in", kind="Button"))]),  # its row shows
], ids=["before-check", "scroll-row-shows"])
def test_a_skip_the_screen_vouches_for_still_drops_the_screen_that_no_longer_appears(later):
    phone, routine = _app()
    out = run(phone, routine(later))
    assert out.status == "done" and phone.at == "checked_in"
    assert any("skipped ahead" in r for r in out.steps[0].rungs)
    assert [(p.kind, p.step_id) for p in out.patches if p.kind == "remove"] == [("remove", "dismiss_whats_new")]
