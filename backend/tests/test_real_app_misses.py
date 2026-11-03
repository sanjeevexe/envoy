"""Real-app misses from the Nov 2 baseline (run 1102175459 on 192cd29, envoy-real), each traced to the compiler.

- amazon's reruns waited on a check for a heads-up notification (CapCut's "An amazing template for you!") that was drawn over
  Amazon's start screen when the run was recorded. Checks on System UI drawn over the app are no longer compiled.
- chrome_wikipedia's agent found the article already open (Chrome restores its last tab), so its topic was never typed and the
  compiler dropped the input: the routine answered 1889 for any topic. The input now stays, as a check on the start screen.

The screens are small made-up ones with each app's shape (the real trees stay out of the repo).
"""

from __future__ import annotations

import asyncio
import gzip
import json

from models.schemas import CompiledRoutine
from routines import checks as chk
from routines.compiler import _passing, compile_trace
from routines.model import Check, Locator
from routines.screens import screen_from_tree


def _screen(package: str, elements: list[dict]):
    return screen_from_tree({"package": package, "activity": "Main", "width": 1080, "height": 2400, "elements": elements})


def _el(i: int, rid: str, label: str, kind: str = "Button", parent: int | None = None, number: int | None = None, **kw) -> dict:
    return {"index": i, "parent": parent, "number": number, "resource_id": rid, "label": label, "text": label, "kind": kind,
            "bounds": [0, 100 * i, 1080, 100 * i + 90], **kw}


AMAZON = "com.amazon.mShop.android.shopping"
HOME = _screen(AMAZON, [
    _el(0, "com.android.systemui:id/expandableNotificationRow", "CapCut · An amazing template for you!", number=1),
    _el(1, "android:id/notification_headerless_view_column", "An amazing template for you!", "Text", parent=0, number=2),
    _el(2, f"{AMAZON}:id/chrome_search_hint_view", "Search Amazon", "Text", number=3),
])


def test_a_check_on_a_notification_drawn_over_the_app_is_not_compiled():
    over = Check(kind="element_present", locator=Locator(resource_id="notification_headerless_view_column",
                                                         text="An amazing template for you!", kind="Text"))
    assert _passing(over, HOME, None, {}) == "a system notification drawn over the app"
    own = Check(kind="element_present", locator=Locator(resource_id="chrome_search_hint_view", text="Search Amazon", kind="Text"))
    assert _passing(own, HOME, None, {}) is None


CHROME = "com.android.chrome"


def _article(topic: str, year: str) -> dict:
    return {"package": CHROME, "activity": "Main", "width": 1080, "height": 2400, "elements": [
        _el(0, f"{CHROME}:id/url_bar", f"en.m.wikipedia.org/wiki/{topic.replace(' ', '_')}", "EditText", number=1, editable=True),
        _el(1, "firstHeading", topic, "Text", number=2),
        _el(2, "", f"Opened · {year}", "Text", number=3)]}


def test_an_input_shown_only_on_the_screen_the_app_opens_to_is_kept_as_a_check(tmp_path):
    trace = tmp_path / "trace"
    (trace / "screens").mkdir(parents=True)
    with gzip.open(trace / "screens" / "001_before.json.gz", "wt") as f:
        json.dump(_article("Eiffel Tower", "1889"), f)
    goal = "In Chrome, go to en.m.wikipedia.org, search for Eiffel Tower and tell me the year it opened."
    (trace / "run.json").write_text(json.dumps({"task_id": "t-wiki", "goal": goal, "status": "done", "result": "1889",
                                                "check": {"passed": True, "detail": "ok"}}))
    (trace / "steps.jsonl").write_text(json.dumps({"step": 1, "kind": "action", "tree_before": "screens/001_before.json.gz",
                                                   "decision": {"reason": "the year is on the page", "action": {"type": "done"}}}) + "\n")
    spec = CompiledRoutine.model_validate({
        "name": "wikipedia_year_opened", "intent": "Find the year a place opened on Wikipedia", "description": "", "patterns": [],
        "inputs": [{"name": "article_topic", "type": "text", "description": "", "from_memory": None, "example": "Eiffel Tower"}],
        "steps": [], "outputs": [{"name": "year_opened", "near": "Opened", "example": "1889"}], "data_values": []})
    routine, report = asyncio.run(compile_trace(trace, spec=spec))
    assert "article_topic" in routine.inputs
    read = routine.steps[0]
    assert read.id == "read_answer"
    witness = next(c for c in read.pre if c.kind == "element_present")
    assert witness.locator.text_has == "{{article_topic}}"
    # On another topic's page it fails, so the routine never answers one topic with another's year.
    assert chk.evaluate(witness, screen_from_tree(_article("Eiffel Tower", "1889")), {"article_topic": "Eiffel Tower"}).passed
    assert not chk.evaluate(witness, screen_from_tree(_article("Eiffel Tower", "1889")), {"article_topic": "Statue of Liberty"}).passed
    assert any("article_topic" in w and "read_answer" in w for w in report.warnings)
