"""Screen helpers shared by the compiler, locators, checks and executor.

Traces store full trees as JSON (agent/trace.py); `screen_from_tree` turns one back into a
ScreenState so checks and locators run the same way offline (compiling, tests, tuning) as live.
"""

from __future__ import annotations

import gzip
import json
import re
import unicodedata
from pathlib import Path

from devices.screen import _kind, _on_screen, _short_id, format_compact
from devices.types import Element, ScreenState

# Resource IDs that say nothing about the element (Phase 0: the Play Store's are all obfuscated).
_OBFUSCATED = re.compile(r"(^|/)(0_resource_name_obfuscated|obfuscated)$|^[a-z]{1,2}\d*$", re.I)
_WORD = re.compile(r"[0-9A-Za-zÀ-ÿ]+")


def short_id(resource_id: str | None) -> str:
    return _short_id(resource_id or "")


def usable_id(resource_id: str | None) -> bool:
    rid = short_id(resource_id)
    return bool(rid) and not _OBFUSCATED.search(rid)


def fold(s: str | None) -> str:
    """Accents removed: people type "Caffe Latte" where the app shows "Caffè Latte" (seen on Starbucks)."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(ch))


def norm(s: str | None) -> str:
    return " ".join(fold(s).replace("’", "'").split()).casefold()


def tokens(s: str | None) -> list[str]:
    return [t.casefold() for t in _WORD.findall(fold(s))]


def contains_value(haystack: str | None, value: str | None) -> bool:
    """`value` appears in `haystack` on word boundaries, ignoring case and spacing ("12C" is not in "112C")."""
    if not haystack or not value:
        return False
    h, v = norm(haystack), norm(value)
    if not v:
        return False
    return re.search(rf"(?<![0-9a-z]){re.escape(v)}(?![0-9a-z])", h) is not None


_PART_SEPARATORS = re.compile(r"\s[·•|]\s")


def parts_of(label: str) -> list[str]:
    """A row's parts: Envoy joins child texts with " · ", and apps use their own separators ("Queen • 5:55 • 2.7B plays")."""
    return [p.strip(" :,") for p in _PART_SEPARATORS.split(label) if p.strip(" :,")]


def element_text(e: Element) -> str:
    """Everything the element shows: its label (merged child text) plus own text and description."""
    parts = [e.label, e.text, e.desc]
    return " · ".join(dict.fromkeys(p for p in parts if p))


def screen_text(s: ScreenState) -> str:
    parts: list[str] = []
    for e in s.elements:
        if e.visible and not e.status_bar:
            parts += [e.text, e.desc]
    parts += [e.label for e in s.numbered]
    return "\n".join(p for p in parts if p)


def signature_keys(s: ScreenState) -> list[str]:
    """The parts the screen signature hashes: sorted (resource ID, type) outside lists, ignoring text."""
    keys = sorted(
        f"{short_id(e.resource_id)}:{e.kind or _kind(e)}"
        for e in s.elements
        if _on_screen(e, s.width or 10**6, s.height or 10**6) and not e.in_list
        and (e.resource_id or e.clickable or e.long_clickable or e.editable or e.checkable or e.scrollable)
    )
    return keys


def jaccard(a: list[str] | set[str], b: list[str] | set[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / max(1, len(sa | sb))


def body(s: ScreenState) -> str:
    """The compact screen without its header line (which carries the settle time)."""
    return s.compact.split("\n", 1)[1] if "\n" in s.compact else ""


def screen_from_tree(tree: dict) -> ScreenState:
    els: list[Element] = []
    for d in tree["elements"]:
        e = Element(
            index=d["index"], parent=d.get("parent"), depth=0, cls=d.get("class", ""), package=tree.get("package", ""),
            resource_id=d.get("resource_id", ""), text=d.get("text", ""), desc=d.get("desc", ""), hint=d.get("hint", ""),
            bounds=tuple(d.get("bounds", (0, 0, 0, 0))),  # type: ignore[arg-type]
            clickable=d.get("clickable", False), long_clickable=d.get("long_clickable", False),
            editable=d.get("editable", False), scrollable=d.get("scrollable", False), checkable=d.get("checkable", False),
            checked=d.get("checked", False), enabled=d.get("enabled", True), focused=d.get("focused", False),
            selected=d.get("selected", False), password=d.get("password", False), visible=True,
            in_list=d.get("in_list", False), status_bar=d.get("status_bar", False), number=d.get("number"),
            label=d.get("label", ""), kind=d.get("kind", ""),
        )
        els.append(e)
    numbered = sorted((e for e in els if e.number), key=lambda e: e.number or 0)
    s = ScreenState(
        package=tree.get("package", ""), activity=tree.get("activity", ""), elements=els, numbered=numbered,
        signature=tree.get("signature", ""), compact="", timestamp=0.0, width=tree.get("width", 1080),
        height=tree.get("height", 2400), has_password_field=tree.get("has_password_field", False), secure=tree.get("secure", False),
    )
    s.compact = format_compact(s.package, s.activity, numbered, None, s.secure)
    return s


def load_tree(path: Path) -> ScreenState:
    with gzip.open(path, "rt") as f:
        return screen_from_tree(json.load(f))
