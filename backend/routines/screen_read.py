"""Outputs the accessibility tree doesn't have (a web page Chrome draws without one): read from the screenshot.

Muse Spark (low effort) reads the screenshot and must quote the line the answer is in. The value is kept only if it has
the recorded shape (a regex from the run's answer: "15 May 1889" → a day, a month, a year), it is in the quoted line, and
the page names one of the routine's inputs ("Eiffel Tower" in the title or the line), so an answer read from the wrong
page is refused. The compiler runs the same check on the run's recorded final screenshot before keeping the output, and
the executor on every rerun: one verification, applied the same way each time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from models.adapter import DataScope, ModelAdapter, image_part
from models.schemas import ScreenReadOutput
from routines.screens import contains_value, norm

INSTRUCTIONS = ("You read one value from a phone screenshot. Answer only from text written on the screenshot; never from "
                "what you know. If the answer is not written there, set found to false and leave the other fields empty.")

def shape_of(example: str) -> str:
    """A regex the read value must contain, from the run's answer: a date with a year → a year (wikipedia writes
    "15 May 1889" and "October 28, 1886"), else the example with its digit runs as \\d+ ("4.7" → \\d+\\.\\d+)."""
    ex = example.strip()
    if re.search(r"\b(1\d|20)\d{2}\b", ex):
        return r"\b(1\d|20)\d{2}\b"
    return re.sub(r"(\\\d)+|\d+", r"\\d+", re.escape(ex)) if any(ch.isdigit() for ch in ex) else ""


@dataclass
class Read:
    value: str | None
    detail: str
    cost_usd: float = 0.0


def accept(got: ScreenReadOutput, shape: str, inputs: dict[str, str]) -> tuple[str | None, str]:
    """The check every screenshot read passes, at compile time and on each rerun."""
    if not got.found or not got.value.strip():
        return None, "not on the screenshot"
    value = " ".join(got.value.split())
    if shape and not re.search(shape, value, re.I):
        return None, f"{value!r} is not shaped like the recorded answer"
    if not contains_value(got.quote, value) and norm(value) not in norm(got.quote):
        return None, f"{value!r} is not in the quoted line {got.quote!r}"
    named = [v for v in inputs.values() if v]
    if named and not any(contains_value(got.page_title + " " + got.quote, v) for v in named):
        return None, f"the page ({got.page_title!r}) names none of the inputs"
    return value, "read from the screenshot"


def read(adapter: ModelAdapter, png: bytes, question: str, shape: str, inputs: dict[str, str], *,
         data_scope: DataScope = "real", task_id: str | None = None) -> Read:
    content = [{"type": "input_text", "text": f"Question: {question}"}, image_part(png)]
    out = adapter.call("screen_read", content, instructions=INSTRUCTIONS, data_scope=data_scope, task_id=task_id)
    got: ScreenReadOutput = out.parsed  # type: ignore[assignment]
    value, detail = accept(got, shape, inputs) if got is not None else (None, "no answer")
    return Read(value, detail, out.cost_at_standard_usd)
