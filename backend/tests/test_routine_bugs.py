"""Routine bugs found replaying 55 compiled AndroidWorld routines on their own seed (Oct 28, `routines-verify` on branch
androidworld): a popup menu read as another app, a typed field found again by its empty-state label, identical delete
icons down a list, and dates a request implies but doesn't write.

tests/traces/androidworld holds screens from the AndroidWorld runs those routines were compiled from: Contacts after a
phone number was typed (it added a second, empty "Phone" field), Markor's new-file dialog (the extension field's hint is
its value, ".md"), Pro Expense's list with two copies of "Public Transit", and the Broccoli run whose overflow menu was
recorded as the app "PopupWindow:2096839".
"""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from devices.android import AndroidDevice
from models.schemas import InputValue, MatchOutput
from routines import checks as chk
from routines import locators
from routines.compiler import clean, generalize_locator, load_trace
from routines.dates import facts
from routines.matcher import RoutineMatcher
from routines.model import Check, InputSpec, Locator, Routine
from routines.screens import load_tree, short_id

AW = Path(__file__).parent / "traces" / "androidworld"
BROCCOLI = "com.flauschcode.broccoli"

# `dumpsys window` (filtered as _foreground filters it) with Broccoli's overflow menu open, in the format Android 13 prints.
POPUP_DUMPSYS = f"""\
  mCurrentFocus=Window{{8a3c1b0 u0 PopupWindow:51b096d}}
  mFocusedApp=ActivityRecord{{c0b6d94 u0 {BROCCOLI}/.recipe.details.RecipeDetailsActivity}} t12}}
  Window #8 Window{{3a98cbe u0 InputMethod}}:
    mOwnerUid=10195 showForAllUsers=false package=com.google.android.inputmethod.latin appop=NONE
      fl=NOT_FOCUSABLE LAYOUT_IN_SCREEN SPLIT_TOUCH HARDWARE_ACCELERATED DRAWS_SYSTEM_BAR_BACKGROUNDS
  Window #9 Window{{8a3c1b0 u0 PopupWindow:51b096d}}:
    mOwnerUid=10153 showForAllUsers=false package={BROCCOLI} appop=NONE
      fl=LAYOUT_NO_LIMITS ALT_FOCUSABLE_IM SPLIT_TOUCH HARDWARE_ACCELERATED
  Window #10 Window{{ce55da0 u0 {BROCCOLI}/{BROCCOLI}.recipe.details.RecipeDetailsActivity}}:
    mOwnerUid=10153 showForAllUsers=false package={BROCCOLI} appop=NONE
      fl=LAYOUT_IN_SCREEN SECURE SPLIT_TOUCH HARDWARE_ACCELERATED
"""


def _device(dumpsys: str) -> AndroidDevice:
    d = AndroidDevice("emulator-5554")
    d.adb = SimpleNamespace(shell=lambda cmd: dumpsys)  # type: ignore[assignment]
    return d


# ---- 1. a popup menu is its app's ----------------------------------------------------------------


def test_a_popup_menu_reads_as_the_app_that_opened_it():
    pkg, act, secure = _device(POPUP_DUMPSYS)._foreground()
    assert (pkg, act, secure) == (BROCCOLI, f"{BROCCOLI}.recipe.details.RecipeDetailsActivity", False)
    out = chk.evaluate(Check(kind="app_foreground", package=BROCCOLI), SimpleNamespace(package=pkg), {})  # type: ignore[arg-type]
    assert out.passed, out.detail
    # The activity's own window is read as before, with its secure flag.
    activity = POPUP_DUMPSYS.replace("8a3c1b0 u0 PopupWindow:51b096d}\n", f"ce55da0 u0 {BROCCOLI}/.recipe.details.RecipeDetailsActivity}}\n", 1)
    assert _device(activity)._foreground() == (BROCCOLI, f"{BROCCOLI}.recipe.details.RecipeDetailsActivity", True)


def test_a_trace_recorded_with_the_popup_as_the_app_compiles_with_the_app():
    _, records = load_trace(AW / "broccoli_delete", confirmed=True)
    steps, _ = clean(AW / "broccoli_delete", records)
    tap_delete = next(s for s in steps if s.target is not None and s.target.label == "Delete")
    assert tap_delete.before.package == BROCCOLI  # recorded as "PopupWindow:2096839"
    assert chk.derive_pre(tap_delete.before, tap_delete.target, {}, first=False) == [Check(kind="app_foreground", package=BROCCOLI)]
    assert all("PopupWindow" not in sc.package for s in steps for sc in (s.before, s.after))


# ---- 2. a typed field is the one that holds what was typed ---------------------------------------


def test_a_typed_field_is_not_mistaken_for_the_empty_one_typing_added():
    screen = load_tree(AW / "contacts_phone_typed.json.gz")  # "Phone: +13920741751" and a new empty "Phone"
    check = Check(kind="field_equals", locator=Locator(text="Phone", kind="EditText"), value="+13920741751")
    out = chk.evaluate(check, screen, {})
    assert out.passed and out.detail == "field holds '+13920741751'" and out.element is not None and out.element.index == 82
    # A number that didn't go in is still caught.
    assert not chk.evaluate(check.model_copy(update={"value": "+19999999999"}), screen, {}).passed


def test_a_field_whose_hint_is_the_typed_value_holds_it():
    screen = load_tree(AW / "markor_extension_typed.json.gz")  # the extension field: text ".md", hint ".md"
    check = Check(kind="field_equals", locator=Locator(resource_id="new_file_dialog__ext", text="{{ext}}", kind="EditText"),
                  value="{{ext}}")
    assert chk.evaluate(check, screen, {"ext": ".md"}).passed
    empty = Check(kind="field_equals", locator=Locator(resource_id="new_file_dialog__name", kind="EditText"), value="my_note")
    assert not chk.evaluate(empty, screen, {}).passed  # the name field's hint is "my_note": typed text there is not


# ---- 3. identical icons down a list are told apart by their row ----------------------------------


def test_identical_row_icons_are_told_apart_by_their_row():
    screen = load_tree(AW / "expense_duplicates.json.gz")
    # The routine as compiled: every row's delete icon matches it ("best 1.00 … runner-up 0.98").
    compiled = Locator(resource_id="imv_delete_icon", text="", kind="Button", cls="ImageView", siblings=["Delete"], in_list=False,
                       position=(0.899, 0.608))
    assert not locators.locate(compiled, screen).ok
    # Now the locator keeps its row's text, less what every row shows ("Delete", "$").
    books = locators.build(screen.elements[87], screen)
    assert books.row == ["Books", "2023 Oct 7", "350.4"]
    assert locators.locate(books, screen).element.index == 87
    # Two copies of "Public Transit": the same row twice, so the copy in the recorded slot (the second).
    dup = locators.build(screen.elements[147], screen)
    assert locators.locate(dup, screen).element.index == 147
    assert locators.locate(dup.model_copy(update={"position": (0.899, 0.53)}), screen).element.index == 132
    # One row left: a row that isn't there costs nothing (it was only there to tell twins apart).
    alone = [e for e in screen.numbered if not (short_id(e.resource_id) == "imv_delete_icon" and e.index != 87)]
    one = dataclasses.replace(screen, numbered=alone)
    m = locators.locate(dup, one)
    assert m.element.index == 87 and "row" not in m.details and m.score >= locators.STRICT


def test_a_row_chosen_by_an_input_is_a_hard_requirement():
    screen = load_tree(AW / "expense_duplicates.json.gz")
    loc = generalize_locator(locators.build(screen.elements[87], screen), {"expense_name": "Books"}, [], None, None)
    assert loc.row_has == "{{expense_name}}" and loc.row == [] and loc.text_has is None
    assert locators.locate(loc, screen, {"expense_name": "Seminars"}).element.index == 117
    # Not on screen: no other row's icon, even at the relaxed threshold.
    assert not locators.locate(loc, screen, {"expense_name": "Groceries"}, threshold=locators.RELAXED).ok


# ---- 4. dates and times a request implies --------------------------------------------------------

TODAY = date(2023, 10, 15)  # AndroidWorld's phone date, a Sunday


def test_relative_dates_and_end_times_are_worked_out_from_the_phones_date():
    two_weeks = facts("create a calendar event in two weeks from today at 17h with the title 'Meeting with the Team'. "
                      "The event should last for 30 mins.", TODAY)
    assert two_weeks[0].startswith("'today' is Sunday, October 15, 2023")
    assert any("'in two weeks' is Sunday, October 29, 2023 (2023-10-29" in f for f in two_weeks)
    assert any("ends at 17:30" in f for f in two_weeks)
    assert any("'this thursday' is Thursday, October 19" in f for f in facts("an event for this Thursday at 5h", TODAY))
    assert any("day 16 of the month" in f for f in facts("an event for tomorrow at 20h", TODAY))
    assert any("ends at 01:00 the next day" in f for f in facts("a table at 11 pm for two hours", TODAY))
    assert facts("Check in for my flight", TODAY) == [facts("", TODAY)[0]]  # nothing implied: only today


class _Adapter:
    def __init__(self, inputs: list[InputValue]) -> None:
        self.inputs, self.content = inputs, ""

    def call(self, job, content, **kw):
        self.content = content
        out = MatchOutput(routine="calendar_create_event", confident=True, inputs=self.inputs)
        return SimpleNamespace(parsed=out, cost_usd=0.0, cost_at_standard_usd=0.0)


def test_the_matcher_keeps_a_computed_date_only_if_code_worked_it_out():
    routine = Routine(routine="calendar_create_event", app="com.simplemobiletools.calendar.pro", intent="Create a calendar event",
                      patterns=["create a calendar event"], status="active",
                      inputs={"event_title": InputSpec(description="Title", example="Call with the Team"),
                              "event_day": InputSpec(description="Day of the month", example="16")}, steps=[])
    store = SimpleNamespace(active=lambda: [routine])
    request = "In Simple Calendar Pro, create a calendar event for tomorrow at 20h with the title 'Call with the Team'."
    good = _Adapter([InputValue(name="event_title", value="Call with the Team", source="request"),
                     InputValue(name="event_day", value="16", source="computed")])
    res = asyncio.run(RoutineMatcher(store, good).match(request, today=TODAY))  # type: ignore[arg-type]
    assert res.inputs == {"event_title": "Call with the Team", "event_day": "16"} and not res.missing
    assert "DATES AND TIMES:" in good.content and "'tomorrow' is Monday, October 16, 2023" in good.content
    assert "written like '16'" in good.content and "written like 'Call" not in good.content
    # A day the model worked out itself is not kept (17 is in no fact, and "5" can't hide inside "2023-10-15").
    for wrong in ("17", "5"):
        bad = _Adapter([InputValue(name="event_title", value="Call with the Team", source="request"),
                        InputValue(name="event_day", value=wrong, source="computed")])
        assert asyncio.run(RoutineMatcher(store, bad).match(request, today=TODAY)).missing == ["event_day"]  # type: ignore[arg-type]
