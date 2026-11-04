"""Tied look-alike rows named by an input, when their list can't scroll right now (Uber's results for "State Farm Arena",
Nov 4): a routine with no irreversible step takes the top one. Everything else that ties stays ambiguous."""

from __future__ import annotations

import asyncio

from devices.types import ActionResult
from routines import locators
from routines.executor import RoutineExecutor, list_choice
from routines.model import InputSpec, Locator, Routine, Step, StepAction
from test_done_dialogs import FAST, ScriptedApprover
from test_policy_and_screens import _buttons

ROWS = ("State Farm Arena - State Farm Drive Lot, 1 State Farm Dr, Atlanta, GA", "State Farm Arena - Ruby Lot, 1 State Farm Dr, Atlanta, GA",
        "State Farm Arena Diamond Deck Parking Lot, 100 CNN Center, Atlanta, GA")
INPUT = Locator(text_has="{{destination}}", kind="Button", cls="Button", in_list=True, position=(0.5, 0.388))
IN = {"destination": "State Farm Arena"}


def test_a_tie_takes_the_top_row_even_under_the_strict_bar():
    s = _buttons(*ROWS, "Back")
    assert not any(e.in_list for e in s.numbered)  # the list can't scroll: the plain fallback finds no rows
    assert not list_choice(INPUT, s, IN, locators.STRICT).ok
    m = list_choice(INPUT, s, IN, locators.STRICT, top_on_tie=True)
    assert m.ok and m.element.label == ROWS[0]


def test_the_top_row_wins_wherever_the_rows_sit_in_the_tree_order():
    s = _buttons(ROWS[2], ROWS[0], ROWS[1])
    m = list_choice(INPUT, s, IN, locators.RELAXED, top_on_tie=True)
    assert m.ok and m.element.label == ROWS[2]


def test_it_stays_off_without_the_flag_and_a_plain_locate_is_unchanged():
    s = _buttons(*ROWS)
    assert not list_choice(INPUT, s, IN, locators.STRICT).ok
    assert not locators.locate(INPUT, s, IN).ok


def test_a_tie_on_rows_that_would_ask_stays_ambiguous():
    rows = ("State Farm Arena - Pay now, 1 State Farm Dr", "State Farm Arena - Pay later, 1 State Farm Dr")
    assert not list_choice(INPUT, _buttons(*rows), IN, locators.STRICT, top_on_tie=True).ok


def test_a_locator_with_no_input_stays_ambiguous():
    fixed = Locator(text_has="State Farm Arena", kind="Button", cls="Button", in_list=True, position=(0.5, 0.388))
    assert not list_choice(fixed, _buttons(*ROWS), {}, locators.STRICT, top_on_tie=True).ok


def test_a_locator_not_chosen_from_a_list_stays_ambiguous():
    loc = INPUT.model_copy(update={"in_list": False})
    assert not list_choice(loc, _buttons(*ROWS), IN, locators.STRICT, top_on_tie=True).ok


def test_a_value_in_no_row_still_fails():
    m = list_choice(INPUT, _buttons(*ROWS), {"destination": "Truist Park"}, locators.RELAXED, top_on_tie=True)
    assert not m.ok


def test_one_row_is_no_tie_and_the_search_box_text_is_never_taken():
    assert not list_choice(INPUT, _buttons(ROWS[0], "Back"), IN, locators.STRICT, top_on_tie=True).ok
    m = list_choice(INPUT, _buttons("State Farm Arena", *ROWS), IN, locators.RELAXED, top_on_tie=True)
    assert m.element is None or m.element.label != "State Farm Arena"


class _Phone:
    def __init__(self):
        self.screen, self.taps = _buttons(*ROWS), []

    async def observe(self, screenshot: bool = False):
        return self.screen

    async def act(self, a):
        if a.kind == "tap":
            self.taps.append(self.screen.numbered[a.element - 1].label)
        return ActionResult(ok=True, duration_ms=1.0)


def _run(*extra: Step):
    class NoModel:
        def call(self, *a, **kw):
            raise AssertionError("no model call expected")

    phone = _Phone()
    pick = Step(id="pick", intent="Tap the result for {{destination}}", action=StepAction(kind="tap", target=INPUT), risk="reversible")
    r = Routine(routine="fare", app="com.ubercab", intent="Check a fare", inputs={"destination": InputSpec(example="State Farm Arena")},
                steps=[pick, *extra])
    ex = RoutineExecutor(phone, adapter=NoModel(), approver=ScriptedApprover(approve=False), config=FAST)
    return asyncio.run(ex.run(r, IN, launch="never", allow_repair=False, allow_agent=False)), phone


def test_a_routine_with_nothing_irreversible_taps_the_top_row():
    out, phone = _run()
    assert out.status == "done" and phone.taps == [ROWS[0]]


def test_a_routine_with_an_irreversible_step_anywhere_stays_ambiguous_and_taps_nothing():
    pay = Step(id="pay", intent="Wait", action=StepAction(kind="wait", seconds=0.01), risk="irreversible")
    out, phone = _run(pay)
    assert out.status != "done" and phone.taps == []
