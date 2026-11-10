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
# An element's own long text (a note's body, a message, an open file) is shown at length, up to MAX_TEXT, within MAX_TEXT_SCREEN
# for the whole screen. Clipped to MAX_LABEL the model could not read a file it had opened (AndroidWorld: Markor's recipes.txt,
# 12,101 characters in one EditText, showed as its first 120; scrolling it changes nothing in the tree, so it could not page).
# Rows that merge their children's text stay at MAX_LABEL.
MAX_TEXT = 4000
MAX_TEXT_SCREEN = 8000
MAX_MERGED_PARTS = 3
# Text longer than its cap is shown in parts. Scrolling over it doesn't change the tree (an EditText holds its whole text
# however it is scrolled), so the device moves the part shown instead (AndroidWorld: a 12,101-character recipes file of
# which the model could only ever read the first 4,000 characters, then failed as stuck). Parts overlap a little.
TEXT_PAGE_OVERLAP = 200


def text_key(e: Element, whole: str) -> str:
    """Names a long text across reads of the same screen: its element and its first words."""
    return f"{e.resource_id}|{e.cls}|{len(whole)}|{whole[:80]}"


def text_page_step(cap: int = MAX_TEXT) -> int:
    return max(1, cap - TEXT_PAGE_OVERLAP)


def _bool(node: ET.Element, key: str) -> bool:
    return node.get(key) == "true"


def _short_id(resource_id: str) -> str:
    return resource_id.split(":id/", 1)[-1] if resource_id else ""


def _short_class(cls: str) -> str:
    return cls.rsplit(".", 1)[-1]


STATUS_BAR_FRACTION = 0.07  # System UI nodes entirely within the top 7% of the screen (the bar is ~5.7% on a Pixel 6)
BANNER_PACKAGE = "ai.envoy.banner"  # Envoy's own banner on a real phone: like the status bar, never shown, hashed or signed
_STATUS_IDS = re.compile(r"(status_?bar|notification_icon|notificationIcons|system_icons|clock)", re.I)
# The on-screen keyboard's own window (keys, its toolbar's "Delete", "Done", "Clipboard") and the system's keyboard buttons
# in the navigation bar: never part of the app's screen. A keyboard's "Delete" beside an app's buttons misleads the model,
# the policy rules and routine checks alike (a check was once written on Gboard's "Clipboard").
_KEYBOARD_PACKAGES = re.compile(r"(inputmethod|honeyboard|swiftkey|\.keyboard\b|gboard)", re.I)
_KEYBOARD_IDS = re.compile(r"^input_method_nav_", re.I)
# System UI drawn over the app for a moment: the "Copied" clipboard preview after typing (with "Send to nearby device"),
# the screenshot preview. Like the keyboard, not the app's screen: two visits to the same page must look the same.
_OVERLAY_IDS = re.compile(r"^com\.android\.systemui:id/(clipboard_|screenshot_)", re.I)


# What a filled password field's text becomes: the same for every password, so not even its length is kept.
PASSWORD_MASK = "••••••••"


def mask_passwords(xml: str) -> str:
    """The dump with every filled password field's text replaced by PASSWORD_MASK. uiautomator2 returns the password
    itself (Android 15, a saved login filled in), so this runs before anything reads, keeps or logs the screen: the
    compact view, the element tree, traces and model inputs never carry it."""
    if 'password="true"' not in xml:
        return xml
    root = ET.fromstring(xml)
    # An empty field reports its hint as its text ("Password" / "Password"): that one stays as it is, so it still reads empty.
    filled = [n for n in root.iter() if n.get("password") == "true" and (n.get("text") or "").strip() and n.get("text") != n.get("hint")]
    for n in filled:
        n.set("text", PASSWORD_MASK)
    return ET.tostring(root, encoding="unicode") if filled else xml


def parse_hierarchy(xml: str, screen_h: int) -> list[Element]:
    """Flatten the uiautomator2 XML dump into Elements (document order), marking list membership.

    `screen_h` must be the device's real height: a dump taken mid-launch can hold only the status bar.
    """
    root = ET.fromstring(mask_passwords(xml))
    out: list[Element] = []

    def walk(node: ET.Element, parent: int | None, depth: int, in_list: bool, overlay: bool = False) -> None:
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
        el.status_bar = el.package == BANNER_PACKAGE or el.package == "com.android.systemui" and (
            0 < bounds[3] <= screen_h * STATUS_BAR_FRACTION or bool(_STATUS_IDS.search(el.resource_id.split("/")[-1]))
        ) or bool(_KEYBOARD_PACKAGES.search(el.package)) or bool(_KEYBOARD_IDS.search(el.resource_id.split("/")[-1]))
        overlay = overlay or bool(_OVERLAY_IDS.search(el.resource_id))
        el.status_bar = el.status_bar or overlay
        out.append(el)
        for child in node.findall("node"):
            walk(child, el.index, depth + 1, in_list or el.scrollable, overlay)

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


def _clip(s: str, cap: int = MAX_LABEL) -> str:
    s = " ".join(s.split())
    return s if len(s) <= cap else s[: cap - 1] + "…"


def _set_label(e: Element, text: str, cap: int = MAX_LABEL) -> None:
    """The model sees at most `cap` characters; the whole text stays on the element for reading outputs."""
    e.label = _clip(text, cap)
    whole = " ".join(text.split())
    e.full_label = whole if whole != e.label else ""


def _show_long(e: Element, text: str, cap: int, offsets: dict[str, int] | None) -> None:
    """Label an element whose own text may run past `cap`: the part from its offset (0 unless the model scrolled it), and
    where that part sits in the whole text."""
    whole = " ".join(text.split())
    if cap <= MAX_LABEL or len(whole) <= cap:
        _set_label(e, text, cap)
        return
    key = text_key(e, whole)
    start = max(0, min((offsets or {}).get(key, 0), len(whole) - 1))
    end = min(len(whole), start + cap)
    more = "; scroll down on it for the next part" if end < len(whole) else "; this is the end of it"
    e.label = (("…" if start else "") + whole[start:end] + ("…" if end < len(whole) else "")
               + f" [characters {start + 1:,}-{end:,} of {len(whole):,}{more}]")
    e.full_label = whole
    e.text_key = key


def number_elements(elements: list[Element], width: int, height: int, text_offsets: dict[str, int] | None = None) -> list[Element]:
    """Pick and number the elements that matter, merging child text into interactive parents. `text_offsets`: where each
    long text that was scrolled starts (devices/android.py keeps them; see TEXT_PAGE_OVERLAP)."""
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

    room = MAX_TEXT_SCREEN

    def text_cap(text: str) -> int:
        """How much of an element's own text to show: long text at length while the screen's budget lasts."""
        nonlocal room
        n = len(" ".join(text.split()))
        if n <= MAX_LABEL or room <= MAX_LABEL:
            return MAX_LABEL
        cap = min(MAX_TEXT, room)
        room -= min(n, cap)
        return cap

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
            if e.editable and e.text:
                _show_long(e, label, text_cap(label), text_offsets)
            else:
                _set_label(e, label, MAX_LABEL)
            if e.label or e.resource_id or e.editable or e.scrollable or e.checkable:
                numbered.append(e)
        elif (e.text or e.desc) and e.index not in absorbed and not repeats_ancestor(e):
            _show_long(e, e.text or e.desc, text_cap(e.text or e.desc), text_offsets)
            numbered.append(e)
        elif _short_id(e.resource_id) and e.index not in absorbed and children.get(e.index) and text_only_group(e.index):
            # A merged row with an ID but no text of its own ("Date" + "Fri, Oct 30"): one line, with its ID.
            parts = []
            descendant_text(e.index, parts)
            if parts:
                _set_label(e, " · ".join(dict.fromkeys(parts)))
                numbered.append(e)

    # Parents come before children in document order, so absorbed children are already skipped.
    for i, e in enumerate(numbered, start=1):
        e.number = i
    # An unlabeled control in a list row (an overflow menu, a delete icon) says which row it is in. On AndroidWorld's Retro
    # Music the model tapped "[19] Button (id: menu)" by its place in the list and lost track of which song it was for.
    shown = {e.index: e for e in numbered}
    for e in numbered:
        if not e.label and e.in_list and e.kind not in ("List", "EditText"):
            e.row = _row_text(e, elements, children, shown, height)
    return numbered


ROW_MAX_SHARE = 0.25  # a row is at most this share of the screen's height; a bigger container (a launcher page) is no row


def _row_text(e: Element, elements: list[Element], children: dict[int, list[int]], shown: dict[int, Element], height: int) -> str:
    """The first label shown inside the list row that holds `e` (the row: the ancestor that is a direct child of the
    list). Never looks past that row, so it can't take another row's text, and never past a container taller than a row
    (the home screen's pager is a "list" whose rows are whole pages: its search card was once "in row Gmail")."""
    p = e.parent
    while p is not None and not elements[p].scrollable:
        y1, y2 = elements[p].bounds[1], elements[p].bounds[3]
        if height and y2 - y1 > ROW_MAX_SHARE * height:
            return ""
        if p in shown and shown[p].label:
            return shown[p].label
        stack = list(reversed(children.get(p, [])))
        while stack:  # the row's other elements, in document order
            c = stack.pop()
            ce = shown.get(c)
            if c != e.index and ce is not None and ce.label and ce.kind != "List":
                return ce.label
            if c != e.index:
                stack.extend(reversed(children.get(c, [])))
        parent = elements[p].parent
        if parent is None or elements[parent].scrollable:
            return ""  # p was the row itself
        p = parent
    return ""


def format_line(e: Element) -> str:
    parts = [f"[{e.number}] {e.kind}"]
    if e.label:
        parts.append(f'"{e.label}"')
    if _short_id(e.resource_id):
        parts.append(f"(id: {_short_id(e.resource_id)})")
    if e.row:
        parts.append(f'(in row "{_clip(e.row, 60)}")')
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
    package: str, activity: str, numbered: list[Element], settle_ms: float | None, secure: bool = False, keyboard: bool = False
) -> str:
    header = f"App: {package} · Screen: {activity.rsplit('.', 1)[-1] or '?'}"
    if settle_ms is not None:
        header += f" · settled {settle_ms:.0f} ms"
    lines = [header]
    if keyboard:  # its keys are not listed; without this line the model pressed back "to close the keyboard" when none was up
        lines.append("(the on-screen keyboard is open over the bottom of the screen)")
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


def keyboard_open(elements: list[Element]) -> bool:
    """The on-screen keyboard's own window is in the tree (its keys are dropped from the screen, not from the tree), or
    the system's keyboard buttons are in the navigation bar. Some dumps leave the keyboard's window out (AndroidWorld's
    emulator: no key in any tree), but the navigation bar's input_method_nav_* buttons appear exactly while it is up
    (after 78 of 87 typing steps; after 6 of 138 backs)."""
    return any(e.visible and (_KEYBOARD_PACKAGES.search(e.package) or _KEYBOARD_IDS.search(e.resource_id.split("/")[-1]))
               for e in elements)


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
    text_offsets: dict[str, int] | None = None,
) -> ScreenState:
    xml = mask_passwords(xml)
    elements = parse_hierarchy(xml, height)
    package = package or next((e.package for e in elements if e.package), "")
    numbered = number_elements(elements, width, height, text_offsets)
    return ScreenState(
        package=package,
        activity=activity,
        elements=elements,
        numbered=numbered,
        signature=signature(package, activity, elements, width, height),
        compact=format_compact(package, activity, numbered, settle_ms, secure, keyboard_open(elements)),
        timestamp=time.time(),
        settle_ms=settle_ms,
        read_ms=read_ms,
        width=width,
        height=height,
        has_password_field=any(e.password for e in elements if e.visible),
        secure=secure,
        raw_xml=xml,
    )
