"""Multi-attribute element locators (design doc, App routines › Locators).

A locator describes what an element is: resource ID, label, description, field label, type, parent
and sibling text, list membership and a rough position. To find it again, every numbered element on
the current screen is scored attribute by attribute, and the best one wins if it clears a threshold
and beats the runner-up by a margin. Two thresholds: STRICT for normal runs, RELAXED as rung 2 of
the fallback ladder (a renamed label, a moved button). Coordinates are never used to act.

Real apps often obfuscate resource IDs (Phase 0), so an ID only counts when it is usable, and the
weights are normalized over the attributes a locator actually has: without an ID, text, description
and neighbors carry the score. `text_has` is a hard filter for input-based choices ("the row that
shows {{trip_city}}"), so a routine can never pick the Denver row for a Chicago request.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from fnmatch import fnmatchcase

from devices.types import Element, ScreenState
from routines.model import Locator, render
from routines.screens import contains_value, norm, short_id, tokens, usable_id

# Tuned on SkyLark across the four layout variants (eval/tune_locators.py; see docs/phase-2-results.md).
STRICT = 0.80
RELAXED = 0.60
MARGIN = 0.08  # the winner must beat the runner-up by this much, or the match is ambiguous
# A check describes a state ("the screen titled My Trips", "the selected tab"), so it must show text
# evidence and keep its element type; an ID alone is shared across screens (screen_title is on every one).
CHECK_TEXT_MIN = 0.4

WEIGHTS = {
    "resource_id": 3.0,
    "text": 3.0,
    "desc": 2.0,
    "hint": 2.0,
    "kind": 1.0,
    "cls": 0.5,
    "parent": 1.0,
    "siblings": 1.0,
    "position": 0.75,
}


@dataclass
class Match:
    element: Element | None
    score: float
    runner_up: float
    threshold: float
    details: dict[str, float] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.element is not None

    def summary(self) -> str:
        if self.element is None:
            return f"no match (best {self.score:.2f} < {self.threshold:.2f} or ambiguous, runner-up {self.runner_up:.2f})"
        return f'[{self.element.number}] "{self.element.label[:40]}" score {self.score:.2f} (runner-up {self.runner_up:.2f})'


# ---- building ---------------------------------------------------------------------------------


def _parent_of(e: Element, screen: ScreenState) -> Element | None:
    return screen.elements[e.parent] if e.parent is not None and 0 <= e.parent < len(screen.elements) else None


def _siblings_of(e: Element, screen: ScreenState) -> list[str]:
    if e.parent is None:
        return []
    out = [s.text or s.desc for s in screen.elements if s.parent == e.parent and s.index != e.index and (s.text or s.desc)]
    return out[:4]


def build(e: Element, screen: ScreenState) -> Locator:
    """A locator for element `e` as it appears on `screen` (taken from a trace or a repair)."""
    parent = _parent_of(e, screen)
    plabel = ""
    if parent is not None:
        plabel = parent.label or parent.text or parent.desc or (short_id(parent.resource_id) if usable_id(parent.resource_id) else "")
    x1, y1, x2, y2 = e.bounds
    w, h = screen.width or 1080, screen.height or 2400
    label = e.label or e.text or e.desc
    return Locator(
        resource_id=short_id(e.resource_id) or None,
        text=label or None,
        desc=e.desc if e.desc and e.desc != label else None,
        hint=(e.hint or (label.split(":", 1)[0] if e.editable and label else "")) or None,
        kind=e.kind or None,
        cls=e.cls.rsplit(".", 1)[-1] or None,
        parent=plabel or None,
        siblings=[s for s in _siblings_of(e, screen) if s != label][:3],
        in_list=e.in_list,
        position=(round((x1 + x2) / 2 / w, 3), round((y1 + y2) / 2 / h, 3)),
    )


def from_record(rec: dict, screen: ScreenState) -> Locator:
    """A locator from a trace's element record (agent/trace.element_record), using the before-screen."""
    idx = rec.get("index")
    if idx is not None and 0 <= idx < len(screen.elements):
        return build(screen.elements[idx], screen)
    raise ValueError("element record does not belong to this screen")


# ---- scoring ----------------------------------------------------------------------------------


def text_similarity(a: str | None, b: str | None) -> float:
    """1.0 for the same label. A recorded label that is a whole " · " part of the new one, or the label before its
    colon, scores 0.95 ("Next trip" in "Next trip · Denver · …", "Address" in "Address: 20 W 34th St."). One that only appears inside a longer label is scored by
    how much of it it covers ("Check in" in "Check-in now" or in "Confirm check-in": 0.78), since the
    words alone can't tell a renamed button from a different one. Otherwise, partial credit for shared words."""
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ta, tb = tokens(na), tokens(nb)
    if not ta or not tb:
        return SequenceMatcher(None, na, nb).ratio() * 0.8
    phrase = " ".join(ta)
    head = nb.split(":", 1)[0]  # "Address: 20 W 34th St." is a label and its value, like "Address · 20 W 34th St."
    for seg in nb.split(" · ") + ([head] if ":" in nb and re.search(r"[a-z]", head) else []):
        ts = tokens(seg)
        if ts and " ".join(ts) == phrase:
            return 0.95
    for seg in nb.split(" · "):
        ts = tokens(seg)
        if ts and f" {phrase} " in f" {' '.join(ts)} ":
            return round(0.55 + 0.35 * len(ta) / len(ts), 4)
    sa, sb = set(ta), set(tb)
    inter = len(sa & sb)
    dice = 2 * inter / (len(sa) + len(sb))
    contain = inter / len(sa)  # how much of the recorded label is still there
    return round(0.5 * dice + 0.4 * contain, 4)


def _kind_compatible(loc: Locator, e: Element) -> bool:
    if loc.kind == "EditText":
        return e.editable
    if loc.kind == "List":
        return e.scrollable
    if loc.kind in ("Switch", "CheckBox", "Toggle", "Radio"):
        return e.checkable or e.clickable
    return True


def score(loc: Locator, e: Element, screen: ScreenState, *, use_ids: bool = True, role: str = "target") -> tuple[float, dict[str, float]]:
    """Score in [0, 1] of element `e` against a rendered locator (no {{slots}} left).

    role "target": an element to act on; a usable ID, type and position can carry a renamed label.
    role "check": a state to confirm; it needs some of its text and the same element type."""
    label = e.label or e.text or e.desc
    if loc.text_has and not any(contains_value(t, loc.text_has) for t in (label, e.text, e.desc, e.resource_id.replace("_", " "))):
        return 0.0, {"text_has": 0.0}
    if not _kind_compatible(loc, e):
        return 0.0, {"kind": 0.0}
    got: dict[str, float] = {}
    total = 0.0
    weight = 0.0

    def add(name: str, sim: float, w: float | None = None) -> None:
        nonlocal total, weight
        w = WEIGHTS[name] if w is None else w
        got[name] = round(sim, 3)
        total += w * sim
        weight += w

    if use_ids and loc.resource_id and usable_id(loc.resource_id):
        add("resource_id", 1.0 if id_matches(loc.resource_id, short_id(e.resource_id)) else 0.0)
    if loc.text:
        add("text", max([text_similarity(t, label) for t in [loc.text, *loc.alt_texts]] + [text_similarity(loc.text, e.text) if e.text else 0.0]))
    elif loc.text_has:
        # Several rows can show the input ("Caffè Latte", "Iced Caffè Latte"): the one that is exactly it ranks first.
        add("text", text_similarity(loc.text_has, label))
    if loc.desc:
        add("desc", text_similarity(loc.desc, e.desc or label))
    if loc.hint:
        field_label = label.split(":", 1)[0] if e.editable else label
        add("hint", max(text_similarity(loc.hint, e.hint), text_similarity(loc.hint, field_label)))
    if loc.kind:
        add("kind", 1.0 if e.kind == loc.kind else 0.0)
    if loc.cls:
        add("cls", 1.0 if e.cls.rsplit(".", 1)[-1] == loc.cls else 0.0)
    if loc.parent:
        p = _parent_of(e, screen)
        plabel = (p.label or p.text or p.desc or short_id(p.resource_id)) if p is not None else ""
        add("parent", text_similarity(loc.parent, plabel) if plabel else 0.0)
    if loc.siblings:
        sibs = [norm(s) for s in _siblings_of(e, screen)]
        hit = sum(1 for s in loc.siblings if norm(s) in sibs)
        add("siblings", hit / len(loc.siblings))
    if loc.position:
        w, h = screen.width or 1080, screen.height or 2400
        x1, y1, x2, y2 = e.bounds
        cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
        d = ((cx - loc.position[0]) ** 2 + (cy - loc.position[1]) ** 2) ** 0.5
        add("position", max(0.0, 1.0 - d / 0.5), WEIGHTS["position"] * (0.4 if loc.in_list else 1.0))
    if weight == 0:
        return 0.0, got
    if role == "check":
        if loc.kind and e.kind != loc.kind:
            return 0.0, {**got, "check": 0.0}
        text_sim = max(got.get("text", 1.0 if not loc.text else 0.0), got.get("desc", 0.0))
        if (loc.text or loc.desc) and text_sim < CHECK_TEXT_MIN:
            return 0.0, {**got, "check": 0.0}
    return total / weight, got


def id_matches(pattern: str, rid: str) -> bool:
    """Resource IDs match exactly, or by glob when booking data was cut out of them (trip_row_*)."""
    if "*" in pattern:
        return bool(rid) and fnmatchcase(rid.casefold(), pattern.casefold())
    return rid == pattern


def candidates(screen: ScreenState) -> list[Element]:
    return [e for e in screen.numbered if not e.status_bar]


def locate(loc: Locator, screen: ScreenState, inputs: dict[str, str] | None = None, *, threshold: float = STRICT,
           margin: float = MARGIN, use_ids: bool = True, role: str = "target") -> Match:
    """The element `loc` describes on `screen`, or a Match with element None (too weak or ambiguous)."""
    rendered: Locator = render(loc, inputs or {})
    scored = _ranked(rendered, screen, use_ids, role)
    if not scored:
        return Match(None, 0.0, 0.0, threshold)
    best, e, det = scored[0]
    runner = scored[1][0] if len(scored) > 1 else 0.0
    if best >= threshold and best - runner < margin and (slot := _same_slot(rendered, scored, screen, margin)) is not None:
        e, det = slot
        return Match(e, best, runner, threshold, det)
    if best < threshold or best - runner < margin:
        return Match(None, best, runner, threshold, det)
    return Match(e, best, runner, threshold, det)


def _ranked(rendered: Locator, screen: ScreenState, use_ids: bool, role: str) -> list[tuple[float, Element, dict]]:
    cands = candidates(screen)
    # A screen that exposes no usable IDs at all (a release with stripped or obfuscated IDs) can't count a missing ID
    # against any element: text, type and neighbors carry the score there, as on most real apps.
    use_ids = use_ids and any(usable_id(e.resource_id) for e in cands)
    scored = []
    for e in cands:
        sc, det = score(rendered, e, screen, use_ids=use_ids, role=role)
        if sc > 0:
            scored.append((sc, e, det))
    scored.sort(key=lambda t: -t[0])
    return scored


def all_matching(loc: Locator, screen: ScreenState, inputs: dict[str, str] | None = None, *, threshold: float = STRICT,
                 role: str = "target") -> list[Element]:
    """Every element `loc` describes well enough, best first (when the one wanted is told apart by something else)."""
    return [e for sc, e, _ in _ranked(render(loc, inputs or {}), screen, True, role) if sc >= threshold]


def _same_slot(loc: Locator, scored: list, screen: ScreenState, margin: float) -> tuple[Element, dict] | None:
    """Repeated list rows that nothing but their place tells apart ("the first store in the list"): a locator with no
    text to choose a row by (its text was booking data) means the row in the recorded slot, if one is clearly nearest."""
    if not (loc.in_list and loc.position and (loc.resource_id or loc.kind)) or loc.text or loc.text_has or loc.desc:
        return None
    tied = [(e, det) for sc, e, det in scored if scored[0][0] - sc < margin]
    same = (lambda e: id_matches(loc.resource_id, short_id(e.resource_id))) if loc.resource_id else (lambda e: e.kind == loc.kind)
    if len(tied) < 2 or not all(e.in_list and same(e) for e, _ in tied):
        return None
    w, h = screen.width or 1080, screen.height or 2400

    def dist(e: Element) -> float:
        x1, y1, x2, y2 = e.bounds
        return (((x1 + x2) / 2 / w - loc.position[0]) ** 2 + ((y1 + y2) / 2 / h - loc.position[1]) ** 2) ** 0.5

    tied.sort(key=lambda t: dist(t[0]))
    return tied[0] if dist(tied[1][0]) - dist(tied[0][0]) >= 0.03 else None


def updated(loc: Locator, e: Element, screen: ScreenState) -> Locator:
    """A locator patched to a new look of the same element (after a relaxed match or a repair).

    Input-bound parts ({{slots}}, `text_has`) are kept. For an element chosen by an input (a list row), the new
    label, neighbors and position are this run's booking data, so its old fixed text stays. An ID the new screen
    doesn't show (a build without IDs) is kept rather than dropped: such screens ignore IDs anyway."""
    fresh = build(e, screen)
    upd: dict = {"text_has": loc.text_has}
    if not fresh.resource_id and loc.resource_id:
        upd["resource_id"] = loc.resource_id
    if loc.resource_id and "{{" in loc.resource_id:
        upd["resource_id"] = loc.resource_id
    if loc.text and "{{" in loc.text:
        upd["text"] = loc.text
    if loc.text_has or loc.in_list:
        upd.update(text=loc.text, siblings=loc.siblings, position=loc.position, parent=loc.parent or fresh.parent, desc=loc.desc,
                   resource_id=loc.resource_id or fresh.resource_id)
    new_text = upd.get("text", fresh.text)
    # The old label stays known: the same routine still matches the element if the app goes back to it.
    upd["alt_texts"] = [t for t in dict.fromkeys([*loc.alt_texts, loc.text or ""]) if t and t != new_text and "{{" not in t][:4]
    return fresh.model_copy(update={k: v for k, v in upd.items() if v is not None or k in ("text", "position")})
