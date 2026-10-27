"""Structured-output schemas for Meta model calls (see docs/technical-design.md, Agent runtime).

Pydantic models are the single source of truth: they parse and validate what the model returns, and
`strict_json_schema()` turns them into a JSON schema that fits Meta's documented strict subset for
`text.format` json_schema (dev.meta.ai/docs/structured-output, checked Oct 26, 2026):
  - the root is a plain object (no root-level anyOf/oneOf/allOf/enum/not)
  - no oneOf or allOf anywhere; anyOf is allowed below the root
  - every object has additionalProperties: false, and `required` lists every property
Optional fields therefore become required-but-nullable (anyOf with null).
"""

from __future__ import annotations

import copy
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------------------------
# Agent step: one action per step, chosen from the numbered elements of the compact screen.
# --------------------------------------------------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Tap(_Strict):
    type: Literal["tap"]
    element: int = Field(description="Element number from the screen list, e.g. 4 for [4]")


class LongPress(_Strict):
    type: Literal["long_press"]
    element: int


class TypeText(_Strict):
    type: Literal["type"]
    element: int = Field(description="Number of the text field")
    text: str
    submit: bool = Field(description="Press Enter/Search/Done after typing")


class Scroll(_Strict):
    type: Literal["scroll"]
    direction: Literal["up", "down", "left", "right"] = Field(description="'down' reveals content further down")
    element: int | None = Field(description="Number of the list to scroll, or null for the whole screen")


class Swipe(_Strict):
    type: Literal["swipe"]
    from_x: int = Field(description="0-1000 grid, left to right")
    from_y: int = Field(description="0-1000 grid, top to bottom")
    to_x: int
    to_y: int


class Back(_Strict):
    type: Literal["back"]


class Home(_Strict):
    type: Literal["home"]


class Launch(_Strict):
    type: Literal["launch"]
    app: str = Field(description="Android package name, e.g. com.android.settings")


class TapPoint(_Strict):
    type: Literal["tap_point"]
    x: int = Field(description="0-1000 grid, left to right; only for screens with no usable element list")
    y: int = Field(description="0-1000 grid, top to bottom")


class Look(_Strict):
    type: Literal["look"]


class Wait(_Strict):
    type: Literal["wait"]
    seconds: float


class AskUser(_Strict):
    type: Literal["ask_user"]
    question: str


class Handoff(_Strict):
    type: Literal["handoff"]
    reason: str = Field(description="Why the user must take over: sign-in, password, bot check, ...")


class Done(_Strict):
    type: Literal["done"]
    result: str


class Fail(_Strict):
    type: Literal["fail"]
    reason: str


AgentAction = Annotated[
    Union[Tap, LongPress, TypeText, Scroll, Swipe, Back, Home, Launch, TapPoint, Look, Wait, AskUser, Handoff, Done, Fail],
    Field(discriminator="type"),
]


class StepOutput(_Strict):
    """What the step model returns each step."""

    reason: str = Field(description="One short sentence: why this action")
    action: AgentAction
    expected_result: str = Field(description="What the screen should show after the action, checkable by code")
    risk: Literal["read", "reversible", "irreversible"] = Field(
        description="read: look/scroll/open; reversible: fill a field, add to cart; irreversible: pay, order, submit, send, confirm, cancel, delete"
    )


# --------------------------------------------------------------------------------------------
# Plan (start of task)
# --------------------------------------------------------------------------------------------


class SuccessCheck(_Strict):
    kind: Literal["text_visible", "element_present", "app_foreground", "field_equals", "info"] = Field(
        description=(
            "text_visible: a text that will be on screen when the goal is done (e.g. \"You're checked in\"); "
            "element_present: a button or element label that only exists once done; "
            "app_foreground: an app package that must be in front; "
            "field_equals: a field (field_hint) must hold value; "
            "info: the goal asks a question; the answer must be read off the screen (value: what to look for)"
        )
    )
    value: str
    field_hint: str | None = Field(description="For field_equals: the field's label; otherwise null")


class Plan(_Strict):
    app: str | None = Field(description="Android package of the app the task needs, if known, e.g. com.skylark.air; else null")
    subgoals: list[str] = Field(description="2 to 6 short steps, in order")
    success_check: SuccessCheck


# --------------------------------------------------------------------------------------------
# Visual grounding (Meta docs: prompt-driven, 0-1000 grid, origin top-left)
# --------------------------------------------------------------------------------------------


class GroundedBox(_Strict):
    object_name: str
    x_min: int
    y_min: int
    x_max: int
    y_max: int


class GroundingResult(_Strict):
    objects: list[GroundedBox]


# --------------------------------------------------------------------------------------------
# Strict-subset JSON schema
# --------------------------------------------------------------------------------------------

_DROP_KEYS = {"title", "default", "discriminator", "examples"}


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic model → JSON schema in Meta's strict subset (refs kept under $defs)."""
    schema = copy.deepcopy(model.model_json_schema())

    def fix(node: Any) -> Any:
        if isinstance(node, list):
            return [fix(n) for n in node]
        if not isinstance(node, dict):
            return node
        node = {k: fix(v) for k, v in node.items() if k not in _DROP_KEYS}
        if "oneOf" in node:
            node["anyOf"] = node.pop("oneOf")
        if "const" in node:
            node["enum"] = [node.pop("const")]
        if node.get("type") == "object" or "properties" in node:
            node["type"] = "object"
            node["additionalProperties"] = False
            node["required"] = list(node.get("properties", {}).keys())
        if "$ref" in node and len(node) > 1:  # siblings next to $ref (e.g. description) are not portable
            node = {"$ref": node["$ref"]}
        return node

    return fix(schema)


def check_strict_subset(schema: dict[str, Any]) -> list[str]:
    """Problems that would make Meta reject the schema with strict: true (empty list = OK)."""
    problems: list[str] = []
    for key in ("anyOf", "oneOf", "allOf", "enum", "not"):
        if key in schema:
            problems.append(f"root has {key}")
    if schema.get("type") != "object":
        problems.append("root is not an object")

    def walk(node: Any, path: str) -> None:
        if isinstance(node, list):
            for i, n in enumerate(node):
                walk(n, f"{path}[{i}]")
            return
        if not isinstance(node, dict):
            return
        for key in ("oneOf", "allOf"):
            if key in node:
                problems.append(f"{path}: {key} not allowed")
        if node.get("type") == "object":
            if node.get("additionalProperties") is not False:
                problems.append(f"{path}: additionalProperties must be false")
            props = set(node.get("properties", {}))
            if set(node.get("required", [])) != props:
                problems.append(f"{path}: required must list every property")
        for k, v in node.items():
            walk(v, f"{path}.{k}")

    walk(schema, "$")
    return problems


STEP_SCHEMA = strict_json_schema(StepOutput)
PLAN_SCHEMA = strict_json_schema(Plan)
GROUNDING_SCHEMA = strict_json_schema(GroundingResult)
