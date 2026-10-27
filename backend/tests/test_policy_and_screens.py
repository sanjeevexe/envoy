"""Offline tests on real SkyLark Air screens captured from envoy-test (tests/screens/*.xml)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.checks import answer_tokens, evaluate
from agent.popups import match_popup
from devices.screen import build_state
from devices.types import Action, ScreenState
from models.schemas import PLAN_SCHEMA, STEP_SCHEMA, SuccessCheck, check_strict_subset
from policy.risk import classify
from policy.signin import sign_in_reason

SCREENS = Path(__file__).parent / "screens"


def screen(name: str) -> ScreenState:
    return build_state((SCREENS / f"{name}.xml").read_text(), "com.skylark.air", "com.skylark.air.MainActivity", 1080, 2400)


def el(s: ScreenState, rid: str) -> int:
    return next(e.number for e in s.numbered if e.resource_id == rid)


# ---- compact format -----------------------------------------------------------------------------

def test_info_rows_merge_into_one_line_with_id():
    s = screen("skylark_trip")
    gate = next(e for e in s.numbered if e.resource_id == "row_gate")
    assert gate.label == "Gate · B12"
    assert '[%d] Text "Gate · B12" (id: row_gate)' % gate.number in s.compact


def test_empty_compose_field_is_labeled_by_its_floating_label():
    s = screen("skylark_trip")
    ktn = next(e for e in s.numbered if e.resource_id == "field_ktn")
    assert ktn.label == "Known traveler number"
    assert "(empty)" in s.compact.splitlines()[ktn.number]


def test_status_bar_is_not_listed():
    s = screen("skylark_home")
    assert not any(e.status_bar for e in s.numbered)


# ---- risk ---------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name, rid, expected",
    [
        ("skylark_confirm_checkin", "btn_confirm_checkin", "irreversible"),
        ("skylark_trip", "btn_checkin", "reversible"),  # only starts the flow
        ("skylark_trip", "btn_change_seat", "reversible"),
        ("skylark_bag_dialog", "btn_pay_bag", "irreversible"),
        ("skylark_bag_dialog", "btn_dialog_cancel", "reversible"),  # plain "Cancel" dismisses
        ("skylark_trip", "btn_cancel_trip", "irreversible"),
    ],
)
def test_rules_classify_taps(name, rid, expected):
    s = screen(name)
    v = classify(Action(kind="tap", element=el(s, rid)), s, model_risk="reversible")
    assert v.level == expected, v.reasons


def test_model_label_alone_can_force_approval():
    s = screen("skylark_trip")
    v = classify(Action(kind="tap", element=el(s, "btn_change_seat")), s, model_risk="irreversible")
    assert v.irreversible and v.reasons == ["model: labeled irreversible"]


def test_navigation_is_read():
    s = screen("skylark_trips")
    assert classify(Action(kind="scroll", direction="down"), s, model_risk="read").level == "read"


# ---- sign-in, pop-ups ---------------------------------------------------------------------------

def test_sign_in_screen_is_detected_and_others_are_not():
    assert sign_in_reason(screen("skylark_signin")) == "password field on screen"
    for name in ("skylark_home", "skylark_trip", "skylark_trips", "skylark_confirm_checkin"):
        assert sign_in_reason(screen(name)) is None, name


def test_rating_prompt_is_dismissed_without_a_model_call():
    pop = match_popup(screen("skylark_rating"), "check me in")
    assert pop is not None and pop.element.label == "Not now"
    assert match_popup(screen("skylark_rating"), "rate the app five stars") is None
    assert match_popup(screen("skylark_home"), "check me in") is None


# ---- success checks -----------------------------------------------------------------------------

def test_info_answer_must_be_visible():
    s = screen("skylark_trip")
    check = SuccessCheck(kind="info", value="gate", field_hint=None)
    assert evaluate(check, s, "Your gate is B12").passed
    assert not evaluate(check, s, "Gate C99").passed


def test_answer_tokens():
    assert "B12" in answer_tokens("Your gate is B12")
    assert answer_tokens("38,240 miles") == ["38,240"]


def test_text_visible_check():
    s = screen("skylark_confirm_checkin")
    assert evaluate(SuccessCheck(kind="text_visible", value="Confirm check-in", field_hint=None), s, "").passed
    assert not evaluate(SuccessCheck(kind="text_visible", value="You're checked in", field_hint=None), s, "").passed


def test_schemas_fit_metas_strict_subset():
    assert check_strict_subset(STEP_SCHEMA) == []
    assert check_strict_subset(PLAN_SCHEMA) == []
