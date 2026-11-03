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
    "row": 3.0,  # for an element with no text of its own, its row's text is what it is (the delete icon of "Public Transit")
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
        row=_row_for_locator(e, screen),
        in_list=e.in_list,
        position=(round((x1 + x2) / 2 / w, 3), round((y1 + y2) / 2 / h, 3)),
    )


# ---- rows -------------------------------------------------------------------------------------
# Identical elements repeated row after row (a delete icon on every expense, an "Add" button on every menu item) are told
# apart by the row they sit in. A row is the element's highest ancestor that holds none of its twins; with no twins on
# the screen (one row left), the nearest ancestor that shows some text besides the element and its siblings.


@dataclass
class _Rows:
    screen: ScreenState
    texts: dict[int, list[str]]  # every visible text under each node (own text or description), in tree order
    twins: dict[tuple, list[Element]]


_rows_cache: _Rows | None = None  # the last screen's: locate polls one screen many times


def _twin_key(e: Element) -> tuple:
    return (short_id(e.resource_id) if usable_id(e.resource_id) else "", e.kind, e.cls.rsplit(".", 1)[-1], norm(e.label or e.text or e.desc))


def _ancestors(e: Element, screen: ScreenState) -> list[int]:
    out: list[int] = []
    p = e.parent
    while p is not None and 0 <= p < len(screen.elements) and len(out) < 64:
        out.append(p)
        p = screen.elements[p].parent
    return out


def _rows(screen: ScreenState) -> _Rows:
    global _rows_cache
    if _rows_cache is not None and _rows_cache.screen is screen:
        return _rows_cache
    texts: dict[int, list[str]] = {}
    for x in screen.elements:
        t = (x.text or x.desc or "").strip()
        if t and x.visible and not x.status_bar:
            for a in [x.index, *_ancestors(x, screen)]:
                texts.setdefault(a, []).append(t)
    twins: dict[tuple, list[Element]] = {}
    for e in candidates(screen):
        twins.setdefault(_twin_key(e), []).append(e)
    _rows_cache = _Rows(screen, texts, twins)
    return _rows_cache


def _twins_of(e: Element, screen: ScreenState) -> list[Element]:
    return [o for o in _rows(screen).twins.get(_twin_key(e), []) if o.index != e.index]


def row_of(e: Element, screen: ScreenState) -> int | None:
    """Index of the row node `e` sits in, or None when there is none to find."""
    rows = _rows(screen)
    anc = _ancestors(e, screen)
    twins = _twins_of(e, screen)
    if twins:
        theirs = {a for o in twins for a in _ancestors(o, screen)}
        row = None
        for a in anc:
            if a in theirs:
                break
            row = a
        return row
    own = {norm(e.label or e.text or e.desc), *(norm(t) for t in _siblings_of(e, screen))}
    return next((a for a in anc[:6] if any(norm(t) not in own for t in rows.texts.get(a, []))), None)


def row_texts(e: Element, screen: ScreenState) -> list[str]:
    row = row_of(e, screen)
    return list(dict.fromkeys(_rows(screen).texts.get(row, []))) if row is not None else []


def _row_for_locator(e: Element, screen: ScreenState) -> list[str]:
    """What tells `e`'s row apart from its twins' rows: its texts, less those every row shows ("Delete", "$") and the
    element's own label. Empty for an element that has no twins (it needs no row)."""
    twins = _twins_of(e, screen)
    if not twins:
        return []
    common = set.intersection(*({norm(t) for t in row_texts(o, screen)} for o in twins))
    own = norm(e.label or e.text or e.desc)
    return [t for t in row_texts(e, screen) if norm(t) not in common and norm(t) != own][:4]


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
    row = row_texts(e, screen) if (loc.row or loc.row_has) else []
    if loc.row_has and not any(contains_value(t, loc.row_has) for t in row):
        return 0.0, {"row_has": 0.0}
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
    if loc.row and _twins_of(e, screen):  # alone on the screen (one row left), it needs no row to be told apart
        mine = {norm(t) for t in row}
        add("row", sum(1 for t in loc.row if norm(t) in mine) / len(loc.row))
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
    floor = threshold
    if rendered.nth is not None and rendered.text_has and best < threshold:
        # Rows that all show the input, and say much else besides (Uber's results: "Piedmont Park, 1320 Monroe Dr NE, …"),
        # score under the bar on how closely their words match it. The relaxed rung would take them, and their place picks
        # one: the strict pass takes them at the relaxed bar instead of waiting 5 s for that rung.
        floor = min(threshold, RELAXED)
    if rendered.nth is not None and best >= floor:
        # One of a list's look-alikes, by its place among them (the newest video: the first thumbnail of the gallery).
        ordered = in_order([x for sc, x, _ in scored if sc >= floor and best - sc < margin], screen)
        if ordered is None or rendered.nth >= len(ordered):
            return Match(None, best, runner, threshold, det)
        e = ordered[rendered.nth]
        return Match(e, best, runner, threshold, next(d for _, x, d in scored if x.index == e.index))
    if best >= threshold and best - runner < margin and (slot := _same_slot(rendered, scored, screen, margin)) is not None:
        e, det = slot
        return Match(e, best, runner, threshold, det)
    if best >= threshold and best - runner < margin and (same := _same_case(rendered, scored, margin)) is not None:
        e, det = same
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


# ---- look-alikes in a list ----------------------------------------------------------------------
# A uniform list or grid: elements of one ID and type, each in an item of its own of the same container (their lowest
# common ancestor), as a gallery's thumbnails or a results list's rows are. Its look-alikes are told apart by place.


def tied(loc: Locator, screen: ScreenState, inputs: dict[str, str] | None = None, *, threshold: float = STRICT,
         margin: float = MARGIN) -> list[Element]:
    """The elements `loc` matches equally well (within `margin` of the best), best first: one if it picks one."""
    scored = _ranked(render(loc, inputs or {}), screen, True, "target")
    if not scored or scored[0][0] < threshold:
        return []
    return [e for sc, e, _ in scored if sc >= threshold and scored[0][0] - sc < margin]


def container_of(els: list[Element], screen: ScreenState) -> int | None:
    """Index of the lowest node that holds every element of `els`."""
    if not els:
        return None
    common = set.intersection(*(set(_ancestors(e, screen)) for e in els))
    return next((a for a in _ancestors(els[0], screen) if a in common), None)


def item_of(e: Element, container: int, screen: ScreenState) -> int | None:
    """Index of the container's child that `e` sits in (`e` itself when it is one)."""
    chain = [e.index, *_ancestors(e, screen)]
    k = chain.index(container) if container in chain else 0
    return chain[k - 1] if k > 0 else None


def in_order(els: list[Element], screen: ScreenState) -> list[Element] | None:
    """`els` in reading order (rows top to bottom, then left to right) if they are one uniform list's look-alikes, else None."""
    if len(els) < 2:
        return list(els)
    shapes = {(short_id(e.resource_id) if usable_id(e.resource_id) else "", e.kind, e.cls.rsplit(".", 1)[-1]) for e in els}
    container = container_of(els, screen)
    if len(shapes) > 1 or container is None:
        return None
    items = [item_of(e, container, screen) for e in els]
    if None in items or len(set(items)) < len(items):
        return None
    return sorted(els, key=lambda e: (e.bounds[1], e.bounds[0]))


def list_head(els: list[Element], screen: ScreenState) -> Element | None:
    """The fixed item a uniform list starts with, in view only while the list is at its start (the camera tile before a
    gallery's thumbnails): its container's first child, if that holds none of the look-alikes, else None."""
    container = container_of(els, screen)
    if container is None:
        return None
    first = min((x for x in screen.elements if x.parent == container), key=lambda x: x.index, default=None)
    if first is None or first.index in {item_of(e, container, screen) for e in els}:
        return None
    if first.number and (first.label or usable_id(first.resource_id)):
        return first
    inside = [x for x in candidates(screen) if first.index in _ancestors(x, screen) and (x.label or usable_id(x.resource_id))]
    return inside[0] if inside else None


def _same_case(loc: Locator, scored: list, margin: float) -> tuple[Element, dict] | None:
    """Rows that show the input alike but for its case ("Trigger a new search with golden hour", "…with Golden Hour":
    YouTube's sound search suggestions, Nov 1): the one that shows it exactly as given, if only one does."""
    if not loc.text_has:
        return None
    want = re.compile(rf"(?<![0-9A-Za-z]){re.escape(' '.join(loc.text_has.split()))}(?![0-9A-Za-z])")
    tied = [(e, det) for sc, e, det in scored if scored[0][0] - sc < margin]
    exact = [(e, det) for e, det in tied if any(want.search(" ".join((t or "").split())) for t in (e.label, e.text, e.desc))]
    return exact[0] if len(exact) == 1 and len(tied) > 1 else None


def _same_slot(loc: Locator, scored: list, screen: ScreenState, margin: float) -> tuple[Element, dict] | None:
    """Repeated list rows that nothing but their place tells apart ("the first store in the list"): a locator with no
    text to choose a row by (its text was booking data) means the row in the recorded slot, if one is clearly nearest.
    So do twins in rows that show exactly the same ("delete one copy of each duplicate expense")."""
    tied = [(e, det) for sc, e, det in scored if scored[0][0] - sc < margin]
    if not loc.position or len(tied) < 2:
        return None
    if loc.row or loc.row_has:
        if len({_twin_key(e) for e, _ in tied}) > 1 or len({tuple(norm(t) for t in row_texts(e, screen)) for e, _ in tied}) > 1:
            return None
    elif loc.in_list and (loc.resource_id or loc.kind) and not (loc.text or loc.text_has or loc.desc):
        same = (lambda e: id_matches(loc.resource_id, short_id(e.resource_id))) if loc.resource_id else (lambda e: e.kind == loc.kind)
        if not all(e.in_list and same(e) for e, _ in tied):
            return None
    elif loc.text_has or len({e.parent for e, _ in tied}) > 1 or len({(e.kind, e.cls) for e, _ in tied}) > 1 \
            or len({round(det.get("text", -1.0), 3) for _, det in tied}) > 1:
        # Siblings of one kind that the locator's words fit equally: a launcher's results "Simple Calendar Pro0" … "Pro9",
        # whose numbers were cut out of the text as data. Anything else that tells them apart means it isn't this case.
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
    upd: dict = {"text_has": loc.text_has, "row_has": loc.row_has, "row": loc.row, "nth": loc.nth}  # what chose it stays
    if not fresh.resource_id and loc.resource_id:
        upd["resource_id"] = loc.resource_id
    if loc.resource_id and "{{" in loc.resource_id:
        upd["resource_id"] = loc.resource_id
    if loc.text and "{{" in loc.text:
        upd["text"] = loc.text
    if loc.text_has or loc.in_list or loc.nth is not None:  # chosen by an input or a place: its own words are this run's data
        upd.update(text=loc.text, siblings=loc.siblings, position=loc.position, parent=loc.parent or fresh.parent, desc=loc.desc,
                   resource_id=loc.resource_id or fresh.resource_id)
    new_text = upd.get("text", fresh.text)
    # The old label stays known: the same routine still matches the element if the app goes back to it.
    upd["alt_texts"] = [t for t in dict.fromkeys([*loc.alt_texts, loc.text or ""]) if t and t != new_text and "{{" not in t][:4]
    return fresh.model_copy(update={k: v for k, v in upd.items() if v is not None or k in ("text", "position")})
