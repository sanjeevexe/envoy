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
_OPENS = re.compile(r"^(?:view|open|see|show|go to) (.+)$")  # a button named for the screen it opens (normalized text)
# An app saying there is nothing to count (normalized text): "No contacts yet", "No results", "Nothing planned", "No events".
_EMPTY_STATE = re.compile(r"\bno (?:\w+ ){0,3}(?:yet|found)\b|\bno results\b|\bnothing (?:planned|here|yet|to show|found)\b|"
                          r"\bno (?:contacts|events|messages|emails|items|notes|alarms|files|orders|trips)\b")


def answer_tokens(result: str) -> list[str]:
    """Distinctive tokens of an answer: anything with a digit, or a capitalized word that isn't a stop word."""
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9,:\-]*", result)
    keep = [t.strip(",:") for t in tokens if re.search(r"\d", t) or (t[0].isupper() and t.lower() not in _STOP and len(t) > 2)]
    return keep


def answer_on_screen(result: str, screen: ScreenState) -> CheckResult:
    text = _norm(_screen_text(screen))
    tokens = answer_tokens(result)
    if not tokens:
        # An answer in lower case with no numbers ("lofi hip hop radio 📚 beats to relax/study to", a video title): all of
        # its longer words must be on screen.
        words = [w for w in re.findall(r"[A-Za-z]{4,}", result) if w.lower() not in _STOP]
        if len(words) >= 2:
            missing = [w for w in words if _norm(w) not in text]
            if not missing:
                return CheckResult(True, True, f"the answer's words are on screen: {', '.join(words[:4])}")
            return CheckResult(False, True, f"{missing[:5]} from the answer are not on the current screen")
        return CheckResult(False, True, "the answer has nothing specific to look for on screen")
    found = [t for t in tokens if _norm(t) in text]
    if found:
        return CheckResult(True, True, f"answer visible on screen: {', '.join(found[:4])}")
    empty = _EMPTY_STATE.search(text)
    if empty and all(t == "0" for t in tokens if re.search(r"\d", t)) and any(re.search(r"\d", t) for t in tokens):
        # A count of nothing read from an empty state ("0" from "No contacts yet"): the screen never shows the number. The
        # answer used to pass only when it happened to capitalize a word the screen has ("…the Contacts app shows…").
        return CheckResult(True, True, f"a count of 0, and the screen shows an empty state: {empty.group(0)!r}")
    return CheckResult(False, True, f"none of {tokens[:5]} is visible on the current screen")


# An answer that states a setting's state ("Bluetooth is turned on", "Wi-Fi is off", "Dark theme is enabled").
_ON_OFF = re.compile(r"\b(?:is|are|was|turned|switched|currently|set to)\s+(on|off)\b|\b(enabled|disabled)\b", re.I)


def switch_agrees(result: str, screen: ScreenState) -> str | None:
    """Why an on/off answer is confirmed by a switch on screen, or None. The switch must sit in the row whose words name what
    the answer is about: Settings draws "Use Bluetooth" as one element and its switch, unlabelled, as another (Oct 31, on
    hybrid: a right answer failed a check worded "Bluetooth on/off status", and the run wasn't compiled)."""
    m = _ON_OFF.search(result)
    subjects = answer_tokens(result)
    if not m or not subjects:
        return None
    on = (m.group(1) or m.group(2)).casefold() in ("on", "enabled")
    for sw in (e for e in screen.numbered if e.checkable):
        mid = (sw.bounds[1] + sw.bounds[3]) / 2
        row = [e for e in screen.numbered if e.label and e.bounds[1] <= mid <= e.bounds[3]]
        words = " ".join(_norm(e.label) for e in row + [sw])
        if any(_norm(t) in words for t in subjects):
            if sw.checked != on:
                return None  # the switch says otherwise
            name = next((e.label for e in [sw] + row if e.label), subjects[0])
            return f"the switch for {name!r} is {'on' if on else 'off'}, as the answer says"
    return None


def evaluate(check: SuccessCheck | None, screen: ScreenState, result: str, field_value: str | None = None) -> CheckResult:
    if check is None:
        return CheckResult(True, False, "no success check")
    if check.kind in ("info", "text_visible"):
        res = _evaluate(check, screen, result, field_value)
        if not res.passed and (why := switch_agrees(result, screen)):
            return CheckResult(True, True, why)
        return res
    return _evaluate(check, screen, result, field_value)


def _evaluate(check: SuccessCheck, screen: ScreenState, result: str, field_value: str | None) -> CheckResult:
    text = _norm(_screen_text(screen))
    value = _norm(check.value)
    if check.kind == "info":
        return answer_on_screen(result, screen)
    if check.kind == "text_visible":
        ok = value in text
        return CheckResult(ok, True, f"{check.value!r} {'is' if ok else 'is not'} visible")
    if check.kind == "element_present":
        ok = any(value in _norm(e.label) or value == _norm(e.resource_id) for e in screen.numbered)
        if not ok and (m := _OPENS.match(value)):
            # "View boarding pass" names the button that opens the boarding pass: being on it shows the same thing. The plan
            # writes the check before seeing the app, and SkyLark's check-in ends on the boarding pass, where no such button is.
            if any(_norm(e.label) == m.group(1) for e in screen.numbered):
                return CheckResult(True, True, f"element {check.value!r}: its screen {m.group(1)!r} is open")
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
