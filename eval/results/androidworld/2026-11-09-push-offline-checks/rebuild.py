"""Rebuild a recorded screen with the current checkout's screen code (number_elements, format_compact)."""
import gzip, json
from pathlib import Path
from devices.screen import number_elements, format_compact, keyboard_open
from devices.types import Element, ScreenState

def rebuild(tree: dict) -> ScreenState:
    els = []
    for d in tree["elements"]:
        els.append(Element(
            index=d["index"], parent=d.get("parent"), depth=0, cls=d.get("class", ""), package=tree.get("package", ""),
            resource_id=d.get("resource_id", ""), text=d.get("text", ""), desc=d.get("desc", ""), hint=d.get("hint", ""),
            bounds=tuple(d.get("bounds", (0, 0, 0, 0))), clickable=d.get("clickable", False), long_clickable=d.get("long_clickable", False),
            editable=d.get("editable", False), scrollable=d.get("scrollable", False), checkable=d.get("checkable", False),
            checked=d.get("checked", False), enabled=d.get("enabled", True), focused=d.get("focused", False),
            selected=d.get("selected", False), password=d.get("password", False), visible=d.get("visible", True),
            in_list=d.get("in_list", False), status_bar=d.get("status_bar", False)))
    w, h = tree.get("width", 1080), tree.get("height", 2400)
    numbered = number_elements(els, w, h)
    s = ScreenState(package=tree.get("package", ""), activity=tree.get("activity", ""), elements=els, numbered=numbered,
                    signature=tree.get("signature", ""), compact="", timestamp=0.0, width=w, height=h,
                    secure=tree.get("secure", False))
    s.compact = format_compact(s.package, s.activity, numbered, 0, s.secure, keyboard_open(els))
    return s

def load(path) -> dict:
    with gzip.open(path, "rt") as f:
        return json.load(f)
