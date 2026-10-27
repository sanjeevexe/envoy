"""Accessibility tree → normalized elements, the compact screen format, and the screen signature.

Compact format (Agent runtime section of the design doc): only elements that matter, each with a
short number the model refers to. Interactive elements without their own text take the text of
their children, and those children are not listed again.

Screen signature (App routines section): the app, the window title, and the sorted resource IDs
and element types outside lists, ignoring all text and list contents, so it survives changing data.
"""

from __future__ import annotations

import hashlib
import re
import time
import xml.etree.ElementTree as ET

from devices.types import Element, ScreenState

_BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
MAX_LABEL = 120  # long enough for most answers (a flight status line); the model taps "…" text to expand it otherwise
MAX_MERGED_PARTS = 3


def _bool(node: ET.Element, key: str) -> bool:
    return node.get(key) == "true"


def _short_id(resource_id: str) -> str:
    return resource_id.split(":id/", 1)[-1] if resource_id else ""


def _short_class(cls: str) -> str:
    return cls.rsplit(".", 1)[-1]


STATUS_BAR_FRACTION = 0.07  # System UI nodes entirely within the top 7% of the screen (the bar is ~5.7% on a Pixel 6)
_STATUS_IDS = re.compile(r"(status_?bar|notification_icon|notificationIcons|system_icons|clock)", re.I)


def parse_hierarchy(xml: str, screen_h: int) -> list[Element]:
    """Flatten the uiautomator2 XML dump into Elements (document order), marking list membership.

    `screen_h` must be the device's real height: a dump taken mid-launch can hold only the status bar.
    """
    root = ET.fromstring(xml)
    out: list[Element] = []

    def walk(node: ET.Element, parent: int | None, depth: int, in_list: bool) -> None:
        m = _BOUNDS.match(node.get("bounds", ""))
        bounds = tuple(int(v) for v in m.groups()) if m else (0, 0, 0, 0)
        cls = node.get("class", "")
        el = Element(
            index=len(out),
            parent=parent,
            depth=depth,
            cls=cls,
            package=node.get("package", ""),
            resource_id=node.get("resource-id", ""),
            text=(node.get("text") or "").strip(),
            desc=(node.get("content-desc") or "").strip(),
            hint=(node.get("hint") or "").strip(),
            bounds=bounds,  # type: ignore[arg-type]
            clickable=_bool(node, "clickable"),
            long_clickable=_bool(node, "long-clickable"),
            editable=cls.endswith(("EditText", "AutoCompleteTextView")),
            scrollable=_bool(node, "scrollable"),
            checkable=_bool(node, "checkable"),
            checked=_bool(node, "checked"),
            enabled=node.get("enabled", "true") == "true",
            focused=_bool(node, "focused"),
            selected=_bool(node, "selected"),
            password=_bool(node, "password"),
            visible=node.get("visible-to-user", "true") == "true",
            in_list=in_list,
        )
        el.status_bar = el.package == "com.android.systemui" and (
            0 < bounds[3] <= screen_h * STATUS_BAR_FRACTION or bool(_STATUS_IDS.search(el.resource_id.split("/")[-1]))
        )
        out.append(el)
        for child in node.findall("node"):
            walk(child, el.index, depth + 1, in_list or el.scrollable)

    for top in root.findall("node"):
        walk(top, None, 0, False)
    return out


def _interactive(e: Element) -> bool:
    return e.clickable or e.long_clickable or e.editable or e.checkable or e.scrollable


def _kind(e: Element) -> str:
    short = _short_class(e.cls)
    if e.editable:
        return "EditText"
    if e.checkable:
        for name in ("Switch", "CheckBox", "RadioButton", "ToggleButton"):
            if name in short:
                return "Radio" if name == "RadioButton" else name
        return "Toggle"
    if e.scrollable:
        return "List"
    if e.clickable or e.long_clickable:
        return "Tab" if "Tab" in short else "Button"
    if "Image" in short:
        return "Image"
    return "Text"


def _on_screen(e: Element, width: int, height: int) -> bool:
    x1, y1, x2, y2 = e.bounds
    return e.visible and not e.status_bar and x2 > x1 and y2 > y1 and x2 > 0 and y2 > 0 and x1 < width and y1 < height


def _clip(s: str) -> str:
    s = " ".join(s.split())
    return s if len(s) <= MAX_LABEL else s[: MAX_LABEL - 1] + "…"


def number_elements(elements: list[Element], width: int, height: int) -> list[Element]:
    """Pick and number the elements that matter, merging child text into interactive parents."""
    children: dict[int, list[int]] = {}
    for e in elements:
        if e.parent is not None:
            children.setdefault(e.parent, []).append(e.index)

    absorbed: set[int] = set()

    def descendant_text(idx: int, parts: list[str]) -> None:
        for c in children.get(idx, []):
            ce = elements[c]
            if _interactive(ce):
                continue  # a nested control keeps its own text
            own = ce.text or ce.desc
            if own and len(parts) < MAX_MERGED_PARTS:
                parts.append(own)
                absorbed.add(c)
            descendant_text(c, parts)

    def absorb_repeats(idx: int, label: str) -> None:
        """Children whose text only repeats the parent's own label (tab icons + captions) are not listed again."""
        for c in children.get(idx, []):
            ce = elements[c]
            if _interactive(ce):
                continue
            own = ce.text or ce.desc
            if own and own in label:
                absorbed.add(c)
            absorb_repeats(c, label)

    def repeats_ancestor(e: Element) -> bool:
        """A caption inside a listed element with the same text (a selected tab and its label)."""
        own = e.text or e.desc
        p = e.parent
        while p is not None:
            pe = elements[p]
            if pe.label and own in pe.label:
                return True
            p = pe.parent
        return False

    def text_only_group(idx: int) -> bool:
        """A container whose descendants are all non-interactive (a label/value row, a card of text)."""
        stack = list(children.get(idx, []))
        while stack:
            c = stack.pop()
            if _interactive(elements[c]):
                return False
            stack.extend(children.get(c, []))
        return True

    numbered: list[Element] = []
    for e in elements:
        if not _on_screen(e, width, height):
            continue
        e.kind = _kind(e)
        if _interactive(e):
            label = e.text or e.desc
            if label and not e.scrollable:
                absorb_repeats(e.index, label)
            if e.editable:
                # Compose and Material fields carry their label as a child text node, not a hint.
                parts = []
                descendant_text(e.index, parts)
                field_label = parts[0] if parts else e.hint
                if not e.text or e.text == field_label:
                    label = field_label
                elif field_label:
                    label = f"{field_label}: {e.text}"
            elif not label and not e.scrollable:
                parts = []
                descendant_text(e.index, parts)
                label = " · ".join(dict.fromkeys(parts))  # drop repeats such as "Order · Order"
            e.label = _clip(label)
            if e.label or e.resource_id or e.editable or e.scrollable or e.checkable:
                numbered.append(e)
        elif (e.text or e.desc) and e.index not in absorbed and not repeats_ancestor(e):
            e.label = _clip(e.text or e.desc)
            numbered.append(e)
        elif _short_id(e.resource_id) and e.index not in absorbed and children.get(e.index) and text_only_group(e.index):
            # A merged row with an ID but no text of its own ("Date" + "Fri, Oct 30"): one line, with its ID.
            parts = []
            descendant_text(e.index, parts)
            if parts:
                e.label = _clip(" · ".join(dict.fromkeys(parts)))
                numbered.append(e)

    # Parents come before children in document order, so absorbed children are already skipped.
    for i, e in enumerate(numbered, start=1):
        e.number = i
    return numbered


def format_line(e: Element) -> str:
    parts = [f"[{e.number}] {e.kind}"]
    if e.label:
        parts.append(f'"{e.label}"')
    if _short_id(e.resource_id):
        parts.append(f"(id: {_short_id(e.resource_id)})")
    flags = []
    if e.editable:
        if e.password:
            flags.append("password")
        if not e.text or (e.hint and e.text == e.hint):
            flags.append("empty")
        if e.focused:
            flags.append("focused")
    if e.checkable:
        flags.append("on" if e.checked else "off")
    if e.selected and not e.checkable:
        flags.append("selected")
    if not e.enabled:
        flags.append("disabled")
    if e.kind == "List":
        flags.append("scrollable")
    if flags:
        parts.append("(" + ", ".join(flags) + ")")
    return " ".join(parts)


def format_compact(
    package: str, activity: str, numbered: list[Element], settle_ms: float | None, secure: bool = False
) -> str:
    header = f"App: {package} · Screen: {activity.rsplit('.', 1)[-1] or '?'}"
    if settle_ms is not None:
        header += f" · settled {settle_ms:.0f} ms"
    lines = [header]
    if secure:
        lines.append("(secure screen: the app marked it private; sign-in and payment here are for the user)")
    lines += [format_line(e) for e in numbered]
    if any(e.kind == "List" for e in numbered):
        lines.append("(screen has a scrollable list; scroll to see more)")
    if not numbered:
        lines.append("(no readable elements: the tree is empty; ask for a screenshot with look)")
    return "\n".join(lines)


def signature(package: str, activity: str, elements: list[Element], width: int, height: int) -> str:
    """Hash of app, window title and sorted (resource ID, type) pairs outside lists. Ignores all text."""
    keys = sorted(
        f"{_short_id(e.resource_id)}:{e.kind or _kind(e)}"
        for e in elements
        if _on_screen(e, width, height) and not e.in_list and (e.resource_id or _interactive(e))
    )
    h = hashlib.sha1("\n".join([package, activity, *keys]).encode()).hexdigest()
    return h[:16]


def has_app_content(elements: list[Element]) -> bool:
    """False while an app is still launching: its splash window is not in the accessibility tree yet,
    so the dump holds only System UI (measured in Phase 0 on cold starts of Contacts, Chrome and Clock)."""
    return any(
        e.visible
        and not e.status_bar
        and e.package != "com.android.systemui"
        and (e.text or e.desc or e.clickable or e.editable or e.checkable)
        for e in elements
    )


def content_hash(elements: list[Element]) -> str:
    """Hash of everything visible, including text: used to decide when the screen has settled."""
    h = hashlib.sha1()
    for e in elements:
        if e.visible and not e.status_bar:
            h.update(f"{e.bounds}|{e.text}|{e.desc}|{e.checked}|{e.selected}|{e.focused}\n".encode())
    return h.hexdigest()


def build_state(
    xml: str,
    package: str,
    activity: str,
    width: int,
    height: int,
    *,
    settle_ms: float | None = None,
    read_ms: float | None = None,
    secure: bool = False,
) -> ScreenState:
    elements = parse_hierarchy(xml, height)
    package = package or next((e.package for e in elements if e.package), "")
    numbered = number_elements(elements, width, height)
    return ScreenState(
        package=package,
        activity=activity,
        elements=elements,
        numbered=numbered,
        signature=signature(package, activity, elements, width, height),
        compact=format_compact(package, activity, numbered, settle_ms, secure),
        timestamp=time.time(),
        settle_ms=settle_ms,
        read_ms=read_ms,
        width=width,
        height=height,
        has_password_field=any(e.password for e in elements if e.visible),
        secure=secure,
        raw_xml=xml,
    )
