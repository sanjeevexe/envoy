"""Your usual order from a place: a fact you state, used when you ask for "my usual" (design doc, Shared memory).

    You (chat, or the Memory page's form): "My usual from Thai Basil is a pad see ew and a Thai iced tea, on <app>."
    Later: "Order my usual from Thai Basil"  →  goal "Order my usual from Thai Basil on <app>: a pad see ew and a Thai iced tea"

One `Usual` entity per place (the place is its natural key, so saying it again replaces the order and keeps the old one
as history), with the order and, when you name it, the app you order it on. You are its only source: Envoy never writes
one from what it reads in an app or an email. Everything here is code, with no model call: `said` reads a statement,
`remember` stores it, `resolve` finds the usual a request names, and `with_usual` puts it in the task's goal, so the
routine matcher and the agent see the order itself and Before I start shows it (api/preflight.py).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from memory.store import MemoryStore
from memory.types import normalize_key_value

TYPE = "Usual"
VIA = {"chat": "chat", "voice": "chat"}  # chat sources that can state a usual (your own words in Envoy's app) → the source's `via`

# A greeting or "remember that" before the statement, as typed or as dictation delivers it ("hey envoy remember that …").
_LEAD = r"^[\s,.;:!]*(?:(?:hey|hi|ok|okay)\s+envoy\b[\s,.;:!]*)?(?:(?:please\s+)?(?:remember|note|save)(?:\s+that)?\b[\s,.;:!]*)?"
_STATEMENTS = (
    re.compile(_LEAD + r"my\s+usual\s+(?:order\s+)?(?:from|at)\s+(?P<place>.+?)\s+(?:is|=)\s+(?P<order>.+?)[\s.!]*$", re.I | re.S),
    re.compile(_LEAD + r"my\s+usual\s+(?P<place>.+?)\s+order\s+(?:is|=)\s+(?P<order>.+?)[\s.!]*$", re.I | re.S),
)
_ASKED = re.compile(r"\b(?:my|the|our)\s+usual\b", re.I)
MAX_PLACE, MAX_ORDER = 60, 300


@dataclass
class Usual:
    place: str
    order: str
    app: str | None = None  # the app you order it on, as you named it
    entity: str | None = None
    source: str | None = None  # the order fact's source id


def said(text: str, apps: Iterable[str] = ()) -> Usual | None:
    """Your statement of a usual ("my usual from <place> is <order>", "my usual <place> order is <order>"), or None.
    `apps` are the app names Envoy knows: one named with on/via/through/using/in ("…, on <app>", "On <app>, my usual …",
    "my usual <app> order from …") is the app you order it on, and is left out of the order."""
    for name in sorted({a for a in apps if a}, key=len, reverse=True):
        cleaned, app = _without_app(text, name)
        if app and (u := _statement(cleaned)) is not None:
            u.app = app
            return u
    return _statement(text)


def _without_app(text: str, name: str) -> tuple[str, str | None]:
    n = re.escape(name)
    for pat in (rf"[,;]?\s*\b(?:on|via|through|using|in|with)\s+(?:the\s+)?(?P<app>{n})(?:\s+app)?\b", rf"\b(?P<app>{n})\s+(?=order\b)"):
        m = re.search(pat, text, re.I)
        if m:
            return text[:m.start()] + " " + text[m.end():], m.group("app")
    return text, None


def _statement(text: str) -> Usual | None:
    for pat in _STATEMENTS:
        m = pat.match(text or "")
        if m:
            place = m.group("place").strip(" \"'“”,.;:")
            order = " ".join(m.group("order").split()).strip(" \"'“”,;:")
            if place and order and len(place) <= MAX_PLACE and len(order) <= MAX_ORDER:
                return Usual(place, order)
    return None


def remember(store: MemoryStore, usual: Usual, via: str = "chat") -> tuple[str, bool]:
    """Store it with you as its source (one source for the statement); a usual already known for that place is updated,
    and an app you didn't name this time is kept. Returns (entity id, whether that place already had a usual)."""
    key = "place=" + normalize_key_value("place", usual.place)
    known = store.find_by_key(TYPE, key)
    eid = known or store.create_entity(TYPE)
    src = store.add_source("user", {"via": via})
    for attr, value in (("place", usual.place), ("order", usual.order), ("app", usual.app)):
        cur = store.current(eid, attr) if known else None
        if value and not (cur and normalize_key_value(attr, cur["value"]) == normalize_key_value(attr, value)):
            store.user_edit(eid, attr, value, source=src)
    store.commit()
    return eid, known is not None


def resolve(store: MemoryStore, text: str) -> Usual | None:
    """The usual a request asks for: "my usual" (or "the usual") and a place you have a usual from, named in the request.
    When two places are named, the longer name wins ("Blue Bottle Coffee" over "Blue Bottle"). None otherwise."""
    if not _ASKED.search(text or ""):
        return None
    best: Usual | None = None
    for e in store.entities(TYPE):
        cur = {f["attribute"]: f for f in store.current_facts(e["id"])}
        place, order = cur.get("place"), cur.get("order")
        if place is None or order is None or not names_place(text, place["value"]):
            continue
        if best is None or len(place["value"]) > len(best.place):
            best = Usual(place["value"], order["value"], (cur.get("app") or {}).get("value"), e["id"], order["source"])
    return best


def names_place(text: str, place: str) -> bool:
    """The place, however it's written: "Pho 24", "pho-24" and "pho24" are the same place; "Pho" isn't in "phone"."""
    return _mentions(text, place)


def _mentions(text: str, phrase: str) -> bool:
    words = re.findall(r"[a-z0-9]+", phrase.casefold())
    if not words:
        return False
    return re.search(r"(?<![a-z0-9])" + r"[\W_]*".join(map(re.escape, words)) + r"(?![a-z0-9])", (text or "").casefold()) is not None


def with_usual(goal: str, usual: Usual, add_app: bool = False) -> str:
    """The goal with the order spelled out (and the app, when the goal names none). A goal that already has it is kept."""
    if _mentions(goal, usual.order):
        return goal
    base = goal.rstrip(" .!?")
    if add_app and usual.app:
        base += f" on {usual.app}"
    return f"{base}: {usual.order}"
