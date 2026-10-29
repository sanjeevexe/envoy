"""Routine bugs found replaying 55 compiled AndroidWorld routines on their own seed (Oct 28, `routines-verify` on branch
androidworld): a popup menu read as another app, a typed field found again by its empty-state label, identical delete
icons down a list, and dates a request implies but doesn't write.

tests/traces/androidworld holds screens from the AndroidWorld runs those routines were compiled from: Contacts after a
phone number was typed (it added a second, empty "Phone" field), Markor's new-file dialog (the extension field's hint is
its value, ".md"), Pro Expense's list with two copies of "Public Transit", and the Broccoli run whose overflow menu was
recorded as the app "PopupWindow:2096839".
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from devices.android import AndroidDevice
from routines import checks as chk
from routines.compiler import clean, load_trace
from routines.model import Check

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
