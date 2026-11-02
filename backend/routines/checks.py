"""Routine checks: evaluated in code on a screen, and written automatically from tree diffs.

Evaluating: every check is a pure function of the current screen (plus the screen before the action,
for `screen_changed`), so the executor can poll it cheaply and needs no model while checks pass.
`field_equals` reads the field with get_text when the tree can't be trusted (the XML dump turns
emoji into "..", Phase 0).

Writing (`derive_post`, `derive_pre`): the compiler compares a step's before and after trees and
keeps what must be true before (the app, a distinctive element of the screen) and what must change
after (a new screen with its distinctive elements, a toggle's new state, a field's value, a message
that appeared, a dialog that closed). Distinctive means stable across runs: a usable resource ID,
short static text, not inside a list, and no booking data unless it is an input.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Awaitable, Callable

from devices.types import Element, ScreenState
from routines import locators
from routines.model import Check, Locator, render, render_str
from routines.screens import body, contains_value, jaccard, norm, screen_text, short_id, signature_keys, usable_id

FieldReader = Callable[[Element], Awaitable[str | None]]


@dataclass
class CheckOutcome:
    check: Check
    passed: bool
    detail: str
    relaxed: bool = False  # passed only at the relaxed locator threshold
    element: Element | None = None


def _norm_value(v: str | None) -> str:
    return "".join((v or "").split()).casefold()


def evaluate(check: Check, screen: ScreenState, inputs: dict[str, str], *, before: ScreenState | None = None,
             relaxed: bool = False, field_text: dict[int, str] | None = None) -> CheckOutcome:
    """One check on one screen. `relaxed` lets element checks pass at the relaxed threshold.
    `field_text` holds values read with get_text, by element index (for field_equals)."""
    c: Check = render(check, inputs)
    k = c.kind
    if k == "app_foreground":
        ok = screen.package == c.package
        return CheckOutcome(check, ok, f"app in front is {screen.package}")
    if k in ("text_visible", "text_absent"):
        present = norm(c.text) in norm(screen_text(screen)) if c.text else False
        ok = present if k == "text_visible" else not present
        return CheckOutcome(check, ok, f"{c.text!r} {'visible' if present else 'not visible'}")
    if k == "screen_changed":
        if before is None:
            return CheckOutcome(check, True, "no before-screen to compare")
        ok = screen.signature != before.signature or body(screen) != body(before)
        return CheckOutcome(check, ok, "screen changed" if ok else "screen did not change")
    if k == "screen_like":
        sim = jaccard(signature_keys(screen), c.keys or [])
        ok = sim >= (c.min_similarity or 0.6)
        return CheckOutcome(check, ok, f"signature similarity {sim:.2f}")
    assert c.locator is not None
    m = locators.locate(c.locator, screen, threshold=locators.STRICT, margin=0.0, role="check")
    used_relaxed = False
    if not m.ok and relaxed:
        m = locators.locate(c.locator, screen, threshold=locators.RELAXED, margin=0.0, role="check")
        used_relaxed = m.ok
    if k == "element_present":
        return CheckOutcome(check, m.ok, m.summary(), used_relaxed, m.element)
    if k == "element_absent":
        strict = locators.locate(c.locator, screen, threshold=locators.STRICT, margin=0.0, role="check")
        return CheckOutcome(check, not strict.ok, "absent" if not strict.ok else f"still present: {strict.summary()}")
    if not m.ok or m.element is None:
        return CheckOutcome(check, False, f"element not found: {m.summary()}")
    e = m.element
    if k == "field_equals":
        def held(f: Element) -> str:
            # An empty field shows its hint as its text. When the hint is the expected value (Markor's ".md" extension
            # field), the field shows the value either way, so what it shows is what it holds.
            empty = bool(f.hint) and f.text == f.hint and _norm_value(f.text) != _norm_value(c.value)
            return (field_text or {}).get(f.index, "" if empty else f.text)

        value = held(e)
        ok = _norm_value(value) == _norm_value(c.value)
        if not ok:
            # Typing can add a field the locator describes as well: Contacts adds an empty "Phone" row once a number is
            # typed, and the new empty row matches the recorded label ("Phone") better than the filled one ("Phone:
            # +13920741751"). The field typed into is the one, among those the locator describes, that holds the value.
            th = locators.RELAXED if used_relaxed else locators.STRICT
            typed_into = next((f for f in locators.all_matching(c.locator, screen, threshold=th, role="check")
                               if _norm_value(held(f)) == _norm_value(c.value)), None)
            if typed_into is not None:
                return CheckOutcome(check, True, f"field holds {held(typed_into)!r}", used_relaxed, typed_into)
        return CheckOutcome(check, ok, f"field holds {value!r}", used_relaxed, e)
    if k == "toggle_is":
        state = "on" if e.checked else "off"
        return CheckOutcome(check, state == (c.value or "on"), f"toggle is {state}", used_relaxed, e)
    return CheckOutcome(check, False, f"unknown check {k}")


def evaluate_all(checks: list[Check], screen: ScreenState, inputs: dict[str, str], **kw) -> list[CheckOutcome]:
    return [evaluate(c, screen, inputs, **kw) for c in checks]


def needs_field_read(checks: list[Check], inputs: dict[str, str]) -> bool:
    """field_equals with non-ASCII values must be read with get_text (the dump garbles emoji)."""
    return any(c.kind == "field_equals" and any(ord(ch) > 127 for ch in (render_str(c.value, inputs) or "")) for c in checks)


# ---- writing checks from trees ----------------------------------------------------------------

_DIGITS = re.compile(r"\d")


def _anchor_key(e: Element) -> tuple[str, str, str]:
    return (short_id(e.resource_id) if usable_id(e.resource_id) else "", e.kind, norm(e.label))


_SYSTEM_PKGS = ("com.android.systemui", "com.google.android.permissioncontroller", "com.android.permissioncontroller",
                "com.google.android.gms", "android")
_POPUP_TEXT = re.compile(r"(allow .{0,40} to access|send you notifications|turn on notifications|enjoying|rate (us|this app)|"
                         r"leave a review|isn.?t responding|location data|while using the app|only this time|don.?t allow)", re.I)


def _popup_like(e: Element, screen: ScreenState) -> bool:
    """System dialogs and known interruptions: the shared pop-up handler covers them, so checks must not expect them
    (Android stops showing a permission prompt after it was denied, so such a check would never pass again)."""
    return (e.package or screen.package) in _SYSTEM_PKGS or bool(_POPUP_TEXT.search(e.label or ""))


def _distinctiveness(e: Element, screen: ScreenState, inputs: dict[str, str]) -> float:
    """How good an element is as a check anchor: stable across runs and specific to this screen."""
    if e.status_bar or not (e.label or usable_id(e.resource_id)) or _popup_like(e, screen):
        return -9.0
    s = 0.0
    rid = short_id(e.resource_id)
    if usable_id(e.resource_id):
        s += 2.0
        if "title" in rid or "header" in rid:
            s += 1.0
    if e.in_list or re.search(r"(row|cell|item|index|position)[-_]?\d", rid or ""):
        s -= 3.0  # list contents are data: another booking or seat shows other rows (also rows numbered in their IDs)
    label = e.label or ""
    has_input = any(v and contains_value(label, v) for v in inputs.values())
    if has_input:
        s += 1.0
    elif _DIGITS.search(label):
        s -= 1.5  # booking data (flight numbers, dates, seats) changes between runs
    if len(label) > 60:
        s -= 1.0
    if " · " in label:
        s -= 1.0  # a merged label/value row ("Status · On time"): the value part is booking data
    if e.kind in ("Text",) and label and not _DIGITS.search(label):
        s += 0.5
    if e.kind == "Button" and rid in ("btn_back",) or norm(label) in ("back", "navigate up"):
        s -= 2.0  # present on every screen, says nothing
    return s


def anchor_locator(e: Element, screen: ScreenState) -> Locator:
    """A lean locator for a check: ID, label and type (no position or neighbors, which change)."""
    full = locators.build(e, screen)
    text = full.text
    if text and " · " in text and not e.editable:
        text = text.split(" · ", 1)[0]  # keep the row's label ("Status"), not its value
    return Locator(resource_id=full.resource_id, text=text, kind=full.kind, desc=full.desc)


def _with_input(loc: Locator, e: Element, inputs: dict[str, str]) -> Locator:
    """An anchor that keeps a row's label, not its value ("Music" of "Music · golden hour"), still names an input its value
    shows: TikTok's editor reads "Music" whatever the sound, so a step that added none passed (Nov 2, a post without its
    song). The input becomes `text_has`, and the compiler writes it as its {{slot}}."""
    label = e.label or e.text or e.desc or ""
    if not loc.text or " · " not in label or e.editable:
        return loc
    value = label.split(" · ", 1)[1]
    shown = max((v for v in inputs.values() if v and contains_value(value, v)), key=len, default=None)
    return loc.model_copy(update={"text_has": shown}) if shown else loc


def derive_pre(before: ScreenState, target: Element | None, inputs: dict[str, str], first: bool) -> list[Check]:
    checks = [Check(kind="app_foreground", package=before.package)]
    if first:
        # The routine's starting screen: one distinctive element besides the target.
        cands = [e for e in before.numbered if target is None or e.index != target.index]
        cands.sort(key=lambda e: -_distinctiveness(e, before, inputs))
        if cands and _distinctiveness(cands[0], before, inputs) >= 2.0:
            checks.append(Check(kind="element_present", locator=anchor_locator(cands[0], before)))
    return checks


def derive_post(before: ScreenState, after: ScreenState, action_kind: str, target: Element | None,
                typed: str | None, inputs: dict[str, str], max_anchors: int = 2, submit: bool = False) -> list[Check]:
    checks: list[Check] = []
    after_target = None
    if target is not None:
        after_target = next((e for e in after.elements if e.index == target.index and e.resource_id == target.resource_id
                             and e.cls == target.cls), None)
        if after_target is None and usable_id(target.resource_id):
            after_target = next((e for e in after.elements if e.resource_id == target.resource_id), None)

    if action_kind == "type" and target is not None and typed is not None and not submit:
        checks.append(Check(kind="field_equals", locator=anchor_locator(target, before), value=typed))
        return checks
    # Typing with Enter (a search) leaves the field's screen: check where the app went, like a tap.
    if target is not None and target.checkable and after_target is not None and after_target.checked != target.checked:
        checks.append(Check(kind="toggle_is", locator=anchor_locator(target, before), value="on" if after_target.checked else "off"))

    before_keys = {_anchor_key(e) for e in before.numbered}
    after_keys = {_anchor_key(e) for e in after.numbered}
    appeared = [e for e in after.numbered if _anchor_key(e) not in before_keys]
    disappeared = [e for e in before.numbered if _anchor_key(e) not in after_keys]
    new_screen = after.signature != before.signature
    if after.package in _SYSTEM_PKGS or any(_popup_like(e, after) for e in after.numbered[:3]):
        # A pop-up came up right after the action: nothing behind it can be checked here. The shared handler
        # dismisses it at run time, and the next step's before-checks show where the app went.
        return [Check(kind="screen_changed")] if new_screen else [Check(kind="app_foreground", package=before.package)]

    if new_screen:
        checks.insert(0, Check(kind="screen_changed"))
    good = [e for e in appeared if _distinctiveness(e, after, inputs) >= 1.0]
    good.sort(key=lambda e: -_distinctiveness(e, after, inputs))
    seen_ids: set[str] = set()
    for e in good:
        rid = short_id(e.resource_id)
        if rid and rid in seen_ids:
            continue
        seen_ids.add(rid)
        checks.append(Check(kind="element_present", locator=_with_input(anchor_locator(e, after), e, inputs)))
        if len([c for c in checks if c.kind == "element_present"]) >= max_anchors:
            break
    if not any(c.kind in ("element_present", "toggle_is") for c in checks) and disappeared:
        gone = sorted(disappeared, key=lambda e: -_distinctiveness(e, before, inputs))
        if _distinctiveness(gone[0], before, inputs) >= 1.0:
            checks.append(Check(kind="element_absent", locator=anchor_locator(gone[0], before)))
    if not checks:
        checks.append(Check(kind="screen_changed"))
    return checks
