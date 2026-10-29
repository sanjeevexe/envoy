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
    target: str = Field(description="What you are tapping, as someone would see it on screen, e.g. 'seat 21A' or 'the blue map pin labelled Main St'")


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


# The same step without tap_point, for screens that list their elements and came with no screenshot: a point there can only
# be a guess (the runtime rejected such taps anyway; on 18 real-app runs the model sent 55 of them, 51 rejected, each a
# wasted call: "tap_point 500,500 · Advance past welcome screens" eight times beside a listed "Got it" button).
AgentActionListed = Annotated[
    Union[Tap, LongPress, TypeText, Scroll, Swipe, Back, Home, Launch, Look, Wait, AskUser, Handoff, Done, Fail],
    Field(discriminator="type"),
]


class StepOutputListed(StepOutput):
    action: AgentActionListed  # type: ignore[assignment]


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


class ChooseOutput(_Strict):
    number: int = Field(description="The number of the box that is the target, or 0 if none is")


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


# --------------------------------------------------------------------------------------------
# Routines: compiling a trace (Muse Wonder) and local repair
# --------------------------------------------------------------------------------------------


class CompileInput(_Strict):
    name: str = Field(description="snake_case, e.g. trip_city, confirmation_code, last_name, seat, known_traveler_number")
    type: Literal["text", "code", "date", "phone", "choice"]
    description: str = Field(description="What the value is, in a few words")
    from_memory: str | None = Field(description="Where memory can fill it, e.g. trip.city, trip.confirmation_code, user.last_name; null if only the request can give it")
    example: str = Field(description="The value exactly as it appears in this run (copied from the goal, notes, a typed text or a tapped label)")


class CompileStep(_Strict):
    step: int = Field(description="The step number from STEPS")
    id: str = Field(description="snake_case step id, e.g. open_trips")
    intent: str = Field(description="What the step does in any run; write inputs as {{name}}")
    target_fixed_text: str | None = Field(description="The words of the target's label that identify it in every run (no booking data, no input values); null if there are none")
    choice_input: str | None = Field(description="If the target was chosen because it shows an input's value (a list row for the trip, a seat), that input's name; else null")


class CompileOutputValue(_Strict):
    name: str = Field(description="snake_case output name, e.g. gate, seat, boarding_time, status")
    near: str = Field(description="The label shown next to the value on the final screen, e.g. Gate")
    example: str = Field(description="The value in this run")


class CompiledRoutine(_Strict):
    name: str = Field(description="app_verb_object in snake_case, e.g. skylark_check_in")
    intent: str = Field(description="One generic line, e.g. check in for a SkyLark flight")
    description: str = Field(description="One or two sentences on what the routine does and returns")
    patterns: list[str] = Field(description="3 to 6 short phrases a user might say for this, with no specific values")
    inputs: list[CompileInput]
    steps: list[CompileStep]
    outputs: list[CompileOutputValue]
    data_values: list[str] = Field(description="Values in this run that come from the booking or account but are not inputs (flight numbers, dates, gates, times): they change between runs and must not be hard-coded")


class MatchOutput(_Strict):
    routine: str | None = Field(description="The routine name that does what the request asks, or null if none does")
    confident: bool = Field(description="True only if the routine clearly does what the request asks")
    inputs: list["InputValue"] = Field(description="A value for every input the routine needs, from the request or the notes")


class ScreenReadOutput(_Strict):
    found: bool = Field(description="True only if the answer is written on this screenshot")
    page_title: str = Field(description="The page or screen title as written on the screenshot, or empty")
    quote: str = Field(description="The line of text on the screenshot that holds the answer, copied exactly, or empty")
    value: str = Field(description="The answer as written in that line (a date, a number, a name), or empty")


class InputValue(_Strict):
    name: str
    value: str | None = Field(description="The value, or null if neither the request, the notes nor the dates and times give it")
    source: Literal["request", "notes", "computed", "missing"]


MatchOutput.model_rebuild()
COMPILE_SCHEMA = strict_json_schema(CompiledRoutine)


# --------------------------------------------------------------------------------------------
# Memory: extraction from screens and emails, entity matching, answers from memory
# --------------------------------------------------------------------------------------------

EntityTypeName = Literal["Person", "Trip", "Flight", "Reservation", "Order", "Item", "Place", "App", "Account", "Loyalty program",
                         "Subscription", "Event", "Preference", "Note"]


class ExtractedFactOut(_Strict):
    attribute: str = Field(description="One of the type's attributes, e.g. gate, seat, confirmation_code")
    value: str = Field(description="The value copied exactly as the source writes it")
    evidence: str | None = Field(description="For screens: the element number it was read from, e.g. \"6\"; for emails: null")


class ExtractedEntityOut(_Strict):
    ref: str = Field(description="A short local id for links, e.g. e1")
    type: EntityTypeName
    facts: list[ExtractedFactOut]


class ExtractedLinkOut(_Strict):
    from_ref: str
    relation: Literal["includes", "travels_on", "booked_with", "member_of", "at", "for"]
    to_ref: str


class ExtractionOutput(_Strict):
    entities: list[ExtractedEntityOut]
    links: list[ExtractedLinkOut]


class SameEntityOutput(_Strict):
    same: bool = Field(description="True only if both descriptions are the same real-world thing")
    reason: str


class MemoryAnswer(_Strict):
    answer: str = Field(description="The answer in one short sentence, with where and when it was seen; or say memory doesn't have it")
    found: bool
    stale: bool = Field(description="True if the notes mark the fact as possibly out of date")


class AppNoteOp(_Strict):
    op: Literal["add", "confirm", "update", "retire"]
    note_id: str = Field(description="For confirm, update and retire: the id of a CURRENT NOTE; else empty")
    text: str = Field(description="For add and update: the note, one short sentence about the app; else empty")
    step: int = Field(description="The RUN line the note comes from; 0 if none")
    reason: str


class AppNoteOutput(_Strict):
    ops: list[AppNoteOp] = Field(description="0 to 3 operations")


class ChatRoute(_Strict):
    """Envoy's assistant deciding what a chat message asks for."""

    kind: Literal["memory", "task", "reply"] = Field(description="memory: a question memory can answer; task: something to do in a phone app; reply: anything else")
    goal: str = Field(description="For task (and for memory, the task that would check it in the app): the goal as one instruction, e.g. 'Check me in for my flight to Chicago'; else empty")
    reply: str = Field(description="For reply: a short answer to the user; else empty")

