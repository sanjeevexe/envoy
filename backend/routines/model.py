"""The app routine format (design doc, App routines › What a routine contains).

A routine is data, not code: inputs, outputs and a list of steps, each with checks before and after
its action. It is stored as YAML in the shape the design doc shows, e.g.

  routine: skylark_check_in
  app: com.skylark.air
  version: 3
  inputs:
    trip_city: {type: text, from_memory: trip.city, example: Chicago}
  steps:
    - id: open_trips
      intent: Open My Trips
      pre:  [app_foreground: com.skylark.air]
      action: {tap: {resource_id: nav_trips, text: My Trips, kind: Tab}}
      post: [screen_changed: true, element_present: {text: Find a trip}]

Values written `{{name}}` are filled from the inputs at run time (`render`).
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

Risk = Literal["read", "reversible", "irreversible"]
InputType = Literal["text", "code", "date", "phone", "choice"]

_SLOT = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Locator(_Model):
    """What an element is, scored attribute by attribute (routines/locators.py). Never coordinates.

    `text_has` is a hard requirement (the element must show that text, matched on word boundaries);
    it carries input-based choices ("the row for {{trip_city}}"). Every other attribute only adds score.
    """

    resource_id: str | None = None
    text: str | None = None  # the element's label as the agent saw it (own text, else desc, else merged child text)
    text_has: str | None = None
    alt_texts: list[str] = Field(default_factory=list)  # earlier labels of the same element (kept by patches: "Change seat" → "Seats")
    desc: str | None = None
    hint: str | None = None  # a text field's label
    kind: str | None = None  # Button, Text, EditText, Toggle, Switch, List, Tab, ...
    cls: str | None = None  # Android class, short form
    parent: str | None = None  # parent's label or resource ID
    siblings: list[str] = Field(default_factory=list)
    # An element repeated row after row with nothing of its own to tell it apart (each expense's delete icon): the texts
    # of its row ("Public Transit"), and `row_has`, a hard requirement like `text_has` (the row for {{expense_name}}).
    row: list[str] = Field(default_factory=list)
    row_has: str | None = None
    in_list: bool | None = None
    position: tuple[float, float] | None = None  # centre as a fraction of the screen (weak tiebreaker only)
    # Phase 6: a target drawn on screen with no accessibility node (a canvas seat map, a map pin). The executor looks
    # for the recorded picture first (no model call), then asks Muse Spark's grounding for `visual` (one call).
    visual: str | None = None  # what it looks like, with inputs as {{slots}}: "seat {{seat}}"
    crop: str | None = None  # its picture when recorded (base64 PNG, device pixels)
    region: tuple[float, float, float, float] | None = None  # where it was, as fractions of the screen (x1, y1, x2, y2)
    density: int | None = None  # screen density it was recorded at, to scale the picture on another phone

    def describe(self) -> str:
        bits = []
        for k in ("visual", "text_has", "row_has", "text", "desc", "hint", "resource_id", "kind"):
            v = getattr(self, k)
            if v:
                bits.append(f"{k}={v!r}")
        return "{" + ", ".join(bits) + "}"


CheckKind = Literal[
    "app_foreground", "element_present", "element_absent", "text_visible", "text_absent",
    "field_equals", "toggle_is", "screen_changed", "screen_like",
]


class Check(_Model):
    """A condition evaluated in code on a screen (routines/checks.py). Never a model judgment."""

    kind: CheckKind
    package: str | None = None  # app_foreground
    locator: Locator | None = None  # element_present / element_absent / field_equals / toggle_is
    text: str | None = None  # text_visible / text_absent
    value: str | None = None  # field_equals ("{{ktn}}"); toggle_is ("on" / "off")
    keys: list[str] | None = None  # screen_like: signature keys of the expected screen
    min_similarity: float | None = None  # screen_like

    def describe(self) -> str:
        if self.kind == "app_foreground":
            return f"app {self.package} in front"
        if self.kind in ("element_present", "element_absent"):
            return f"{self.kind.split('_')[1]}: {self.locator.describe() if self.locator else '?'}"
        if self.kind in ("text_visible", "text_absent"):
            return f"{self.kind.replace('_', ' ')}: {self.text!r}"
        if self.kind == "field_equals":
            return f"field {self.locator.describe() if self.locator else '?'} holds {self.value!r}"
        if self.kind == "toggle_is":
            return f"toggle {self.locator.describe() if self.locator else '?'} is {self.value}"
        if self.kind == "screen_changed":
            return "the screen changed"
        return f"screen like the recorded one (≥{self.min_similarity})"


ActionKind = Literal["tap", "long_press", "type", "scroll_until", "swipe", "back", "launch", "wait"]


class StepAction(_Model):
    kind: ActionKind
    target: Locator | None = None  # tap / long_press / type (the field) / scroll_until (the element to reveal)
    value: str | None = None  # type
    submit: bool = False  # type: press Enter afterwards
    direction: Literal["up", "down", "left", "right"] | None = None  # scroll_until
    max_scrolls: int | None = None  # scroll_until
    container: Locator | None = None  # scroll_until: the list to scroll (None: the largest list on screen)
    package: str | None = None  # launch
    seconds: float | None = None  # wait
    vector: tuple[float, float] | None = None  # swipe: the drag as fractions of the screen (dx, dy), from the target's centre
    start: tuple[float, float] | None = None  # swipe: where it started on the recorded screen (used only without a target)


class Extract(_Model):
    """Where an output is read: the value after `near` in the same element ("Seat · 14C"), else the next element."""

    near: str | None = None
    locator: Locator | None = None
    segment: int | None = None  # which " · "-separated part of the label holds the value, when there are several
    after: str | None = None  # fixed text that follows the value in its part ("21C. Tap a seat to change it.")
    pattern: str | None = None  # the value's shape, for values with no label or ID ("$13.49" → \$\d+\.\d+); group `v`, if
    # present, is the value inside a longer label ("Mountain Mike's Pizza, 9.2 mi away, …" → (?P<v>.+?), \d+\.\d+ mi away…)
    first_in_list: bool = False  # with pattern: the first element in a list with that shape ("the first result's price")
    next_element: bool = False  # the value is the element right after the one labelled `near` ("Seat", then "22F")
    offset: int | None = None  # with next_element: how many elements after the label ("Today", "10/27", "8am open" → 2)
    expect_digits: bool = False  # the recorded value starts with a number: a placeholder ("- calories") is not the value yet
    switch: bool = False  # the value is the element's on/off state ("Is Bluetooth on?"), not its words
    card: str | None = None  # an ID every row shares (each menu item's price): read it in the row that shows this text
    first_row: bool = False  # the top result row of the locator's type, by its place ("the first video" for a search)
    until: str | None = None  # with first_row: the value ends where this separator starts ("<title> - <channel> - …")
    skip_ads: bool = False  # with first_row: the top row that isn't an ad ("Sponsored - …"), as the agent chose
    below: str | None = None  # with first_row: the first row under the heading with this label ("Results"), not the
    # suggestions and ads above it
    skip_labels: list[str] = Field(default_factory=list)  # with below: controls in a row above its title ("View Sponsored
    # information or leave ad feedback"), as recorded between the heading and the row the agent read
    row_of: str | None = None  # with pattern: read in the row (nearest ancestor) of this other output's element, not the
    # first match anywhere: a result's price, wherever that row puts it ("$8.49" under "Limited time deal")
    from_screenshot: str | None = None  # not in the tree: read from the screenshot by the model, then accepted only if it
    # matches this shape (a regex) and the answer's anchor (`near`) is on screen; re-read and re-checked on every run


class Step(_Model):
    id: str
    intent: str
    pre: list[Check] = Field(default_factory=list)
    action: StepAction
    post: list[Check] = Field(default_factory=list)
    risk: Risk = "read"
    extract: dict[str, Extract] | None = None
    optional: bool = False  # inserted by a patch: skipped when its screen doesn't appear and the next step is ready
    note: str | None = None  # provenance: trace step, patch, ...


class InputSpec(_Model):
    type: InputType = "text"
    description: str = ""
    from_memory: str | None = None  # where memory can fill it, e.g. trip.city or user.last_name
    example: str | None = None  # the value in the run it was compiled from
    choices: list[str] | None = None


class Routine(_Model):
    routine: str
    app: str
    version: int = 1
    status: Literal["draft", "trial", "active", "rejected", "retired"] = "draft"
    intent: str
    description: str = ""
    patterns: list[str] = Field(default_factory=list)  # short phrases for request matching
    inputs: dict[str, InputSpec] = Field(default_factory=dict)
    outputs: list[str] = Field(default_factory=list)
    start: Literal["fresh_launch", "current_screen"] = "fresh_launch"
    steps: list[Step]
    done: list[Check] = Field(default_factory=list)  # end-of-routine checks (the run's success check, generalized)
    parent_version: int | None = None
    changes: list[str] = Field(default_factory=list)  # what this version changed against its parent
    compiled_from: dict[str, Any] = Field(default_factory=dict)

    # ---- helpers ----------------------------------------------------------------------------

    def step_index(self, step_id: str) -> int:
        return next(i for i, s in enumerate(self.steps) if s.id == step_id)

    def slots(self) -> set[str]:
        return set(_SLOT.findall(self.model_dump_json()))

    def missing_inputs(self, inputs: dict[str, str]) -> list[str]:
        return sorted(n for n in self.inputs if not str(inputs.get(n, "")).strip())


# ---- templating -----------------------------------------------------------------------------


def render_str(s: str | None, inputs: dict[str, str]) -> str | None:
    if s is None:
        return None
    return _SLOT.sub(lambda m: str(inputs.get(m.group(1), m.group(0))), s)


def render(obj: Any, inputs: dict[str, str]) -> Any:
    """A copy of a routine part with every {{slot}} filled (pydantic models, dicts, lists and strings)."""
    if isinstance(obj, BaseModel):
        return type(obj).model_validate(render(obj.model_dump(), inputs))
    if isinstance(obj, dict):
        return {k: render(v, inputs) for k, v in obj.items()}
    if isinstance(obj, list):
        return [render(v, inputs) for v in obj]
    if isinstance(obj, tuple):
        return tuple(render(v, inputs) for v in obj)
    if isinstance(obj, str):
        return render_str(obj, inputs)
    return obj


def has_slot(s: str | None) -> bool:
    return bool(s) and bool(_SLOT.search(s or ""))


# ---- YAML in the design doc's shape ---------------------------------------------------------
# Checks and actions are single-key mappings ({element_present: {...}}, {tap: {...}}); empty and
# default fields are left out so the file stays readable.


def _clean(d: Any) -> Any:
    if isinstance(d, dict):
        out = {}
        for k, v in d.items():
            v = _clean(v)
            if v is None or v == [] or v == {} or (k in ("submit", "optional") and v is False):
                continue
            out[k] = v
        return out
    if isinstance(d, list):
        return [_clean(v) for v in d]
    if isinstance(d, tuple):
        return [round(v, 3) if isinstance(v, float) else v for v in d]
    return d


def _check_out(c: Check) -> dict[str, Any]:
    k = c.kind
    loc = _clean(c.locator.model_dump()) if c.locator else None
    if k == "app_foreground":
        return {k: c.package}
    if k in ("element_present", "element_absent"):
        return {k: loc}
    if k in ("text_visible", "text_absent"):
        return {k: c.text}
    if k == "field_equals":
        return {k: {"field": loc, "value": c.value}}
    if k == "toggle_is":
        return {k: {"target": loc, "value": c.value}}
    if k == "screen_changed":
        return {k: True}
    return {k: {"keys": c.keys, "min": c.min_similarity}}


def _check_in(d: dict[str, Any]) -> Check:
    (k, v), = d.items()
    if k == "app_foreground":
        return Check(kind=k, package=v)
    if k in ("element_present", "element_absent"):
        return Check(kind=k, locator=Locator.model_validate(v))
    if k in ("text_visible", "text_absent"):
        return Check(kind=k, text=v)
    if k == "field_equals":
        return Check(kind=k, locator=Locator.model_validate(v["field"]), value=v["value"])
    if k == "toggle_is":
        return Check(kind=k, locator=Locator.model_validate(v["target"]), value=v["value"])
    if k == "screen_changed":
        return Check(kind=k)
    if k == "screen_like":
        return Check(kind=k, keys=v["keys"], min_similarity=v["min"])
    raise ValueError(f"unknown check {k}")


def _action_out(a: StepAction) -> dict[str, Any]:
    k = a.kind
    tgt = _clean(a.target.model_dump()) if a.target else None
    if k in ("tap", "long_press"):
        return {k: tgt}
    if k == "type":
        return {k: _clean({"field": tgt, "value": a.value, "submit": a.submit})}
    if k == "scroll_until":
        return {k: _clean({"target": tgt, "direction": a.direction, "max_scrolls": a.max_scrolls,
                           "container": a.container.model_dump() if a.container else None})}
    if k == "swipe":
        return {k: _clean({"from": tgt, "vector": list(a.vector or ()), "start": list(a.start or ())})}
    if k == "back":
        return {k: True}
    if k == "launch":
        return {k: a.package}
    return {k: a.seconds}


def _action_in(d: dict[str, Any]) -> StepAction:
    (k, v), = d.items()
    if k in ("tap", "long_press"):
        return StepAction(kind=k, target=Locator.model_validate(v))
    if k == "type":
        return StepAction(kind=k, target=Locator.model_validate(v["field"]), value=v.get("value"), submit=v.get("submit", False))
    if k == "scroll_until":
        return StepAction(kind=k, target=Locator.model_validate(v["target"]), direction=v.get("direction", "down"),
                          max_scrolls=v.get("max_scrolls"), container=Locator.model_validate(v["container"]) if v.get("container") else None)
    if k == "swipe":
        return StepAction(kind=k, target=Locator.model_validate(v["from"]) if v.get("from") else None,
                          vector=tuple(v["vector"]) if v.get("vector") else None, start=tuple(v["start"]) if v.get("start") else None)
    if k == "back":
        return StepAction(kind=k)
    if k == "launch":
        return StepAction(kind=k, package=v)
    if k == "wait":
        return StepAction(kind=k, seconds=v)
    raise ValueError(f"unknown action {k}")


def to_dict(r: Routine) -> dict[str, Any]:
    d = r.model_dump(exclude={"steps", "done", "inputs"})
    out: dict[str, Any] = {"routine": d.pop("routine"), "app": d.pop("app"), "version": d.pop("version"), "status": d.pop("status"),
                           "intent": d.pop("intent")}
    out.update({k: v for k, v in d.items() if k not in ("compiled_from", "changes", "parent_version")})
    out["inputs"] = {n: _clean(s.model_dump()) for n, s in r.inputs.items()}
    out["steps"] = []
    for s in r.steps:
        sd: dict[str, Any] = {"id": s.id, "intent": s.intent}
        if s.optional:
            sd["optional"] = True
        if s.pre:
            sd["pre"] = [_check_out(c) for c in s.pre]
        sd["action"] = _action_out(s.action)
        if s.post:
            sd["post"] = [_check_out(c) for c in s.post]
        sd["risk"] = s.risk
        if s.extract:
            sd["extract"] = {n: _clean(e.model_dump(exclude_defaults=True)) for n, e in s.extract.items()}
        if s.note:
            sd["note"] = s.note
        out["steps"].append(sd)
    out["done"] = [_check_out(c) for c in r.done]
    out["parent_version"] = r.parent_version
    out["changes"] = r.changes
    out["compiled_from"] = r.compiled_from
    return _clean(out)


def from_dict(d: dict[str, Any]) -> Routine:
    d = copy.deepcopy(d)
    steps = []
    for sd in d.pop("steps"):
        steps.append(Step(
            id=sd["id"], intent=sd.get("intent", ""), optional=sd.get("optional", False),
            pre=[_check_in(c) for c in sd.get("pre", [])], action=_action_in(sd["action"]),
            post=[_check_in(c) for c in sd.get("post", [])], risk=sd.get("risk", "read"),
            extract={n: Extract.model_validate(e) for n, e in sd["extract"].items()} if sd.get("extract") else None,
            note=sd.get("note"),
        ))
    done = [_check_in(c) for c in d.pop("done", [])]
    inputs = {n: InputSpec.model_validate(s or {}) for n, s in (d.pop("inputs", None) or {}).items()}
    return Routine(steps=steps, done=done, inputs=inputs, **d)


class _Dumper(yaml.SafeDumper):
    pass


def _str_presenter(dumper: yaml.SafeDumper, s: str) -> yaml.ScalarNode:
    return dumper.represent_scalar("tag:yaml.org,2002:str", s, style='"' if (":" in s or "{{" in s or s != s.strip()) else None)


_Dumper.add_representer(str, _str_presenter)


def dump_yaml(r: Routine) -> str:
    return yaml.dump(to_dict(r), Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=140, default_flow_style=None)


def load_yaml(text: str) -> Routine:
    return from_dict(yaml.safe_load(text))


def load(path: Path) -> Routine:
    return load_yaml(path.read_text())
