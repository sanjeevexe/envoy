"""Types shared by every Device backend (see docs/technical-design.md, Device layer)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class Capabilities:
    real_phone: bool
    has_sim: bool
    can_snapshot: bool
    width: int
    height: int
    density: int


@dataclass
class Element:
    """One accessibility node, normalized. `number` is set only for elements shown to the model."""

    index: int  # position in the flattened tree
    parent: int | None
    depth: int
    cls: str
    package: str
    resource_id: str
    text: str
    desc: str
    hint: str
    bounds: tuple[int, int, int, int]  # x1, y1, x2, y2 in device pixels
    clickable: bool
    long_clickable: bool
    editable: bool
    scrollable: bool
    checkable: bool
    checked: bool
    enabled: bool
    focused: bool
    selected: bool
    password: bool
    visible: bool
    in_list: bool = False  # has a scrollable ancestor
    status_bar: bool = False  # System UI status bar (clock, signal, battery): never shown, hashed or signed
    number: int | None = None
    label: str = ""  # text shown to the model (own text, else desc, else merged child text)
    kind: str = ""  # Button, Text, EditText, Image, Switch, CheckBox, List, ...
    full_label: str = ""  # the label before clipping, when it was clipped: routines read outputs from it
    row: str = ""  # for an unlabeled control in a list row (a menu, a delete icon): the row's text, shown to the model only
    text_key: str = ""  # set when the element's text is shown in parts (devices/screen.py, TEXT_PAGE_OVERLAP)

    @property
    def center(self) -> tuple[int, int]:
        x1, y1, x2, y2 = self.bounds
        return (x1 + x2) // 2, (y1 + y2) // 2

    @property
    def area(self) -> int:
        x1, y1, x2, y2 = self.bounds
        return max(0, x2 - x1) * max(0, y2 - y1)

    def to_json(self) -> dict:
        return {
            "index": self.index,
            "parent": self.parent,
            "number": self.number,
            "kind": self.kind,
            "class": self.cls,
            "resource_id": self.resource_id,
            "text": self.text,
            "desc": self.desc,
            "hint": self.hint,
            "label": self.label,
            **({"full_label": self.full_label} if self.full_label else {}),
            **({"row": self.row} if self.row else {}),
            "bounds": list(self.bounds),
            "clickable": self.clickable,
            "long_clickable": self.long_clickable,
            "editable": self.editable,
            "scrollable": self.scrollable,
            "checkable": self.checkable,
            "checked": self.checked,
            "enabled": self.enabled,
            "focused": self.focused,
            "selected": self.selected,
            "password": self.password,
            "in_list": self.in_list,
            "status_bar": self.status_bar,
        }


@dataclass
class ScreenState:
    package: str
    activity: str
    elements: list[Element]  # every node in the tree, flattened
    numbered: list[Element]  # the elements shown to the model, numbered from 1
    signature: str
    compact: str
    timestamp: float
    settle_ms: float | None = None
    read_ms: float | None = None
    screenshot_png: bytes | None = None
    width: int = 0
    height: int = 0
    has_password_field: bool = False
    secure: bool = False  # focused window has FLAG_SECURE (black in scrcpy/screencap, NOT in emulator gRPC)
    raw_xml: str = field(default="", repr=False)

    def element(self, number: int) -> Element:
        if not 1 <= number <= len(self.numbered):
            raise InvalidElement(f"element [{number}] is not on the current screen (1..{len(self.numbered)})")
        return self.numbered[number - 1]

    def tree_json(self) -> dict:
        return {
            "package": self.package,
            "activity": self.activity,
            "signature": self.signature,
            "width": self.width,
            "height": self.height,
            "has_password_field": self.has_password_field,
            "secure": self.secure,
            "elements": [e.to_json() for e in self.elements],
        }


# A scroll drags from SCROLL_FRACTION of the list's height below its center to as far above it (the other way for "up"):
# 60% of the list per scroll. The agent loop uses it to tell a full scroll from one that hit the list's end.
SCROLL_FRACTION = 0.3


class InvalidElement(ValueError):
    """The action referred to an element number that is not on the screen; re-observe and retry once."""


ActionKind = Literal[
    "tap", "long_press", "type", "scroll", "swipe", "back", "home", "launch", "tap_point", "wait"
]


class Action(BaseModel):
    """A device-level action. Agent-only actions (look, ask_user, handoff, done, fail) never reach a Device."""

    kind: ActionKind
    element: int | None = Field(default=None, description="Element number from the last observed screen")
    text: str | None = None
    submit: bool = False
    direction: Literal["up", "down", "left", "right"] | None = None
    x: int | None = None  # tap_point / swipe start, device pixels
    y: int | None = None
    x2: int | None = None  # swipe end
    y2: int | None = None
    package: str | None = None
    seconds: float | None = None


class ActionResult(BaseModel):
    ok: bool
    error: str | None = None
    duration_ms: float
    target: dict | None = None  # the element acted on, for traces and routines


class StreamHandle(Protocol):
    """Live video for the live view (Phase 4: the Node scrcpy relay)."""

    url: str


class Device(Protocol):
    id: str
    capabilities: Capabilities

    async def observe(self, screenshot: bool = False) -> ScreenState: ...
    async def act(self, action: Action) -> ActionResult: ...
    async def launch(self, package: str) -> None: ...
    async def wait_until_settled(self, timeout_s: float = 5) -> ScreenState: ...
    async def snapshot_save(self, name: str) -> None: ...
    async def snapshot_load(self, name: str) -> None: ...
    async def screenshot(self) -> bytes: ...
    def video_stream(self) -> StreamHandle: ...
