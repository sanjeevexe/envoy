"""Shared pop-up handler: dismiss common interruptions without spending a model call.

Each handler recognizes one kind of interruption from the compact screen and answers it with the
declining option (design doc: "permission prompts are denied unless the app's settings allow them").
Handlers are deliberately narrow; anything unrecognized goes to the model as usual.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from devices.types import Element, ScreenState

_PERMISSION_PKGS = ("com.google.android.permissioncontroller", "com.android.permissioncontroller")
_DENY = re.compile(r"^(don.?t allow|deny|not now|no,? thanks|no thanks|maybe later|later|not this time|skip)$", re.I)
_RATING = re.compile(r"(enjoying|rate (us|this app)|leave a review|how would you rate|love .* app\?)", re.I)
_NOTIFY = re.compile(r"(send you notifications|turn on notifications|notifications make things easier|stay in the loop)", re.I)
_ANR = re.compile(r"(isn.?t responding|has stopped|keeps stopping)", re.I)


@dataclass
class PopupAction:
    handler: str
    element: Element


def _button(screen: ScreenState, pattern: re.Pattern[str]) -> Element | None:
    return next((e for e in screen.numbered if e.kind == "Button" and pattern.match(e.label.strip())), None)


def _text(screen: ScreenState) -> str:
    return " ".join(e.label for e in screen.numbered)


def match_popup(screen: ScreenState, goal: str) -> PopupAction | None:
    """The tap that dismisses a known interruption on this screen, or None."""
    text = _text(screen)
    goal_l = goal.lower()

    if screen.package in _PERMISSION_PKGS:
        # A goal that is about this permission ("allow location") is the user's call: let the model handle it.
        if not re.search(r"\b(allow|permission|enable)\b", goal_l):
            if (b := _button(screen, _DENY)) is not None:
                return PopupAction("permission prompt: deny", b)
    if _RATING.search(text) and "rat" not in goal_l and "review" not in goal_l:
        if (b := _button(screen, _DENY)) is not None:
            return PopupAction("rating prompt: not now", b)
    if _NOTIFY.search(text) and "notif" not in goal_l and "alert" not in goal_l:
        if (b := _button(screen, _DENY)) is not None:
            return PopupAction("notification prompt: no thanks", b)
    if _ANR.search(text):
        if (b := _button(screen, re.compile(r"^wait$", re.I))) is not None:
            return PopupAction("app not responding: wait", b)
    return None
