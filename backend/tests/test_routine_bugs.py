"""Routine bugs found replaying 55 compiled AndroidWorld routines on their own seed (Oct 28, `routines-verify` on branch
androidworld): a popup menu read as another app, a typed field found again by its empty-state label, identical delete
icons down a list, and dates a request implies but doesn't write.

tests/traces/androidworld holds screens from the AndroidWorld runs those routines were compiled from: Contacts after a
phone number was typed (it added a second, empty "Phone" field), Markor's new-file dialog (the extension field's hint is
its value, ".md"), Pro Expense's list with two copies of "Public Transit", and the Broccoli run whose overflow menu was
recorded as the app "PopupWindow:2096839".
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from types import SimpleNamespace

from devices.android import AndroidDevice
from routines import checks as chk
from routines import locators
from routines.compiler import clean, generalize_locator, load_trace
from routines.model import Check, Locator
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
