"""Run traces: every step with its before/after screens, action, element, reason, timing and cost.

Traces feed the routine compiler (Phase 2), the evaluation suite and the task view. Layout:

  data/runs/<task_id>/
    run.json                 goal, plan, outcome, totals (written at the end)
    steps.jsonl              one record per step
    screens/NNN_before.json.gz, NNN_after.json.gz   full normalized trees (for compiling checks)
    screens/NNN_before.png   downscaled screenshot, when one was taken (never on secure screens)
"""

from __future__ import annotations

import gzip
import json
import shutil
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable

from devices.types import Element, ScreenState

REPO = Path(__file__).resolve().parents[2]
RUNS = REPO / "data" / "runs"


def element_record(e: Element, screen: ScreenState) -> dict[str, Any]:
    """The target's full description, plus parent and sibling text: what a routine locator scores."""
    rec = e.to_json()
    parent = screen.elements[e.parent] if e.parent is not None else None
    if parent is not None:
        rec["parent"] = {"resource_id": parent.resource_id, "class": parent.cls, "label": parent.label or parent.text or parent.desc}
        sibs = [s for s in screen.elements if s.parent == e.parent and s.index != e.index and (s.text or s.desc)]
        rec["sibling_text"] = [s.text or s.desc for s in sibs][:4]
    return rec


def screen_record(s: ScreenState) -> dict[str, Any]:
    return {
        "package": s.package,
        "activity": s.activity,
        "signature": s.signature,
        "secure": s.secure,
        "has_password_field": s.has_password_field,
        "settle_ms": s.settle_ms,
        "compact": s.compact,
    }


class TraceWriter:
    # Called with (task_id, record) for every step and (task_id, {"kind": "finish", ...}) at the end: the API turns these
    # into live events. Listeners must be quick and never raise; a failing one is skipped.
    listeners: list[Callable[[str, dict[str, Any]], None]] = []

    def __init__(self, task_id: str, root: Path = RUNS) -> None:
        self.task_id = task_id
        self.dir = root / task_id
        if (self.dir / "steps.jsonl").exists():  # a rerun with the same task id replaces the old trace (compiling mixed runs would be wrong)
            shutil.rmtree(self.dir)
        (self.dir / "screens").mkdir(parents=True, exist_ok=True)
        self._steps = (self.dir / "steps.jsonl").open("a")

    def save_tree(self, step: int, which: str, s: ScreenState) -> str:
        path = self.dir / "screens" / f"{step:03d}_{which}.json.gz"
        with gzip.open(path, "wt") as f:
            json.dump(s.tree_json(), f)
        return str(path.relative_to(self.dir))

    def save_png(self, step: int, which: str, png: bytes) -> str:
        path = self.dir / "screens" / f"{step:03d}_{which}.png"
        path.write_bytes(png)
        return str(path.relative_to(self.dir))

    def step(self, record: dict[str, Any]) -> None:
        record = {"time": time.time(), **record}
        self._steps.write(json.dumps(record, default=_default, ensure_ascii=False) + "\n")
        self._steps.flush()
        self._notify(record)

    def finish(self, summary: dict[str, Any]) -> None:
        (self.dir / "run.json").write_text(json.dumps(summary, default=_default, indent=2, ensure_ascii=False))
        self._steps.close()
        self._notify({"kind": "finish", **summary})

    def _notify(self, record: dict[str, Any]) -> None:
        for listener in list(self.listeners):
            try:
                listener(self.task_id, record)
            except Exception:  # noqa: BLE001 - a live view must never break a run
                pass


def _default(o: Any) -> Any:
    if is_dataclass(o):
        return asdict(o)
    if hasattr(o, "model_dump"):
        return o.model_dump()
    return str(o)
