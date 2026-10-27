"""Success checks, evaluated in code on the final screen (never by asking a model).

The planner writes one check per task. When the agent says done, the check must pass; otherwise
done is rejected and the agent is told what is missing. For questions ("what's my gate?") the
check is "info": the answer must be visible on the current screen, so the agent cannot finish
with an answer it made up.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from devices.types import ScreenState
from models.schemas import SuccessCheck


@dataclass
class CheckResult:
    passed: bool
    evaluable: bool
    detail: str


def _screen_text(screen: ScreenState) -> str:
    parts: list[str] = []
    for e in screen.elements:
        if e.visible and not e.status_bar:
            parts += [e.text, e.desc]
    parts += [e.label for e in screen.numbered]
    return " \n".join(p for p in parts if p)


def _norm(s: str) -> str:
    return re.sub(r"[\s’'`]+", " ", s).strip().casefold()


_STOP = {"the", "your", "you", "is", "at", "on", "in", "to", "for", "and", "my", "a", "an", "of", "it", "from", "gate", "seat", "flight"}


def answer_tokens(result: str) -> list[str]:
    """Distinctive tokens of an answer: anything with a digit, or a capitalized word that isn't a stop word."""
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9,:\-]*", result)
    keep = [t.strip(",:") for t in tokens if re.search(r"\d", t) or (t[0].isupper() and t.lower() not in _STOP and len(t) > 2)]
    return keep


def answer_on_screen(result: str, screen: ScreenState) -> CheckResult:
    text = _norm(_screen_text(screen))
    tokens = answer_tokens(result)
    if not tokens:
        return CheckResult(False, True, "the answer has nothing specific to look for on screen")
    found = [t for t in tokens if _norm(t) in text]
    if found:
        return CheckResult(True, True, f"answer visible on screen: {', '.join(found[:4])}")
    return CheckResult(False, True, f"none of {tokens[:5]} is visible on the current screen")


def evaluate(check: SuccessCheck | None, screen: ScreenState, result: str, field_value: str | None = None) -> CheckResult:
    if check is None:
        return CheckResult(True, False, "no success check")
    text = _norm(_screen_text(screen))
    value = _norm(check.value)
    if check.kind == "info":
        return answer_on_screen(result, screen)
    if check.kind == "text_visible":
        ok = value in text
        return CheckResult(ok, True, f"{check.value!r} {'is' if ok else 'is not'} visible")
    if check.kind == "element_present":
        ok = any(value in _norm(e.label) or value == _norm(e.resource_id) for e in screen.numbered)
        return CheckResult(ok, True, f"element {check.value!r} {'present' if ok else 'not present'}")
    if check.kind == "app_foreground":
        ok = screen.package == check.value
        return CheckResult(ok, True, f"foreground app is {screen.package}")
    if check.kind == "field_equals":
        if field_value is None:
            return CheckResult(False, False, f"field {check.field_hint!r} not found")
        ok = _norm(field_value) == value
        return CheckResult(ok, True, f"field {check.field_hint!r} holds {field_value!r}")
    return CheckResult(False, False, f"unknown check {check.kind}")
