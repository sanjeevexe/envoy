"""Real-app misses from the Nov 2 baseline (run 1102175459 on 192cd29, envoy-real), each traced to the compiler.

- amazon's reruns waited on a check for a heads-up notification (CapCut's "An amazing template for you!") that was drawn over
  Amazon's start screen when the run was recorded. Checks on System UI drawn over the app are no longer compiled.
- chrome_wikipedia's agent found the article already open (Chrome restores its last tab), so its topic was never typed and the
  compiler dropped the input: the routine answered 1889 for any topic. The input now stays, as a check on the start screen.
- ytmusic_artist answered WRONG with no model call ("Royal Philharmonic Orchestra & Matthew Freeman" for Bohemian Rhapsody, and
  "Song" in the on-device A/B). The Songs filter's after-screen was a reload frame caught 45 ms after the tap, so its only
  after-check was "chip_cloud absent": it held there, and on a results page that never showed the chips, where the step then
  counted as done. The answer was read in "the Button that shows {{song_title}}": on the reload frame, the mini player.
  After-checks now come from the screen the step settled on ("Clear filters" shown), and an answer read in a list row is read
  in the first such row, never in an overlay.

The screens are small made-up ones with each app's shape (the real trees stay out of the repo).
"""

from __future__ import annotations

import asyncio
import gzip
import json

from models.schemas import CompiledRoutine
from routines import checks as chk
from routines.compiler import _passing, compile_trace
from routines.executor import extract_value
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


YTM = "com.google.android.apps.youtube.music"


def _ytm(signature: str, elements: list[dict]) -> dict:
    return {"package": YTM, "activity": "MusicActivity", "signature": signature, "width": 1080, "height": 2400, "elements": elements}


def _row(i: int, label: str, number: int) -> dict:
    return _el(i, f"{YTM}:id/two_column_item_content_parent", label, parent=20, number=number, in_list=True, clickable=True)


SEARCHED = _el(0, f"{YTM}:id/search_edit_text", "Search songs, artists, podcasts: Bohemian Rhapsody", "EditText", number=1, editable=True)
MINI = _el(30, f"{YTM}:id/mini_player_metadata", "Bohemian Rhapsody · Royal Philharmonic Orchestra & Matthew Freeman", number=40,
           clickable=True)


def _chips(selected: bool) -> list[dict]:
    return [_el(1, f"{YTM}:id/chip_cloud", "", "List", number=2, scrollable=True),
            _el(2, "", "Show song results selected" if selected else "Show song results", "Text", parent=1, in_list=True),
            _el(3, f"{YTM}:id/chip_contents", "Songs", "Text", parent=2, number=3, in_list=True, clickable=True),
            _el(4, "", "Show artist results", "Text", parent=1, in_list=True),
            _el(5, f"{YTM}:id/chip_contents", "Artists", "Text", parent=4, number=4, in_list=True, clickable=True)]


TYPING = _ytm("typing", [_el(0, f"{YTM}:id/search_edit_text", "Type to search", "EditText", number=1, editable=True,
                              hint="Type to search")])
UNFILTERED = _ytm("all", [SEARCHED, *_chips(False), _el(20, f"{YTM}:id/results_list", "", "List", number=10, scrollable=True),
                          _row(21, "Bohemian Rhapsody · Song · Queen • 5:55 • 2.7B plays", 11), MINI])
RELOADING = _ytm("reload", [SEARCHED, MINI])  # 45 ms after the tap: chips and results gone, the mini player stays
FILTERED = _ytm("songs", [SEARCHED, *_chips(True), _el(10, f"{YTM}:id/search_clear_button", "Clear filters", number=9),
                          _el(20, f"{YTM}:id/results_list", "", "List", number=10, scrollable=True),
                          _row(21, "Bohemian Rhapsody · Queen • 5:55 • 2.7B plays", 11),
                          _row(22, "Bohemian Rhapsody · RPO • 6:28", 12),  # closer to the input's words, but second
                          MINI])
SONG = {"song_title": "Bohemian Rhapsody"}


def _ytm_trace(tmp_path):
    trace = tmp_path / "ytm"
    (trace / "screens").mkdir(parents=True)
    for name, tree in (("001_before", TYPING), ("001_after", UNFILTERED), ("002_before", UNFILTERED), ("002_after", RELOADING),
                       ("003_before", FILTERED)):
        with gzip.open(trace / "screens" / f"{name}.json.gz", "wt") as f:
            json.dump(tree, f)
    def act(n: int, kind: str, target: int, **dev) -> dict:
        return {"step": n, "kind": "action", "tree_before": f"screens/{n:03d}_before.json.gz", "tree_after": f"screens/{n:03d}_after.json.gz",
                "decision": {"reason": kind, "action": {"type": kind}}, "device_action": {"kind": kind, **dev}, "changed": True,
                "result": {"ok": True}, "target": {"index": target}}
    records = [act(1, "type", 0, text="Bohemian Rhapsody", submit=True), act(2, "tap", 3),
               {"step": 3, "kind": "action", "tree_before": "screens/003_before.json.gz",
                "decision": {"reason": "the first song is by Queen", "action": {"type": "done", "result": "Queen"}}}]
    (trace / "steps.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    goal = "In the YouTube Music app, search for the song Bohemian Rhapsody and tell me the artist of the first song result."
    (trace / "run.json").write_text(json.dumps({"task_id": "t-ytm", "goal": goal, "status": "done", "result": "Queen",
                                                "check": {"passed": True, "detail": "ok"}}))
    spec = CompiledRoutine.model_validate({
        "name": "youtube_music_search_song", "intent": "Report the artist of the first song result", "description": "",
        "patterns": [], "inputs": [{"name": "song_title", "type": "text", "description": "", "from_memory": None,
                                    "example": "Bohemian Rhapsody"}],
        "steps": [{"step": 1, "id": "search_for_song", "intent": "Search {{song_title}}", "target_fixed_text": None, "choice_input": None},
                  {"step": 2, "id": "filter_to_songs", "intent": "Filter to Songs", "target_fixed_text": "Songs", "choice_input": None}],
        "outputs": [{"name": "artist", "near": "", "example": "Queen"}], "data_values": []})
    return asyncio.run(compile_trace(trace, spec=spec))


def test_after_checks_caught_mid_reload_come_from_the_screen_the_step_settled_on(tmp_path):
    routine, report = _ytm_trace(tmp_path)
    step = routine.steps[-1]
    assert step.id == "filter_to_songs"
    assert not any(c.kind == "element_absent" for c in step.post)
    shown = [c for c in step.post if c.kind == "element_present"]
    assert shown and any(c.locator.text == "Clear filters" for c in shown)
    assert any("held only while the screen changed" in w for w in report.warnings)
    for screen, holds in ((RELOADING, False), (UNFILTERED, False), (FILTERED, True)):
        assert all(chk.evaluate(c, screen_from_tree(screen), SONG).passed for c in shown) is holds


def test_an_answer_read_in_a_list_row_comes_from_the_first_row_never_an_overlay(tmp_path):
    routine, _ = _ytm_trace(tmp_path)
    ex = routine.steps[-1].extract["artist"]
    assert ex.locator.in_list and ex.locator.resource_id == "two_column_item_content_parent" and ex.segment == 1
    assert extract_value(ex, screen_from_tree(FILTERED), SONG) == "Queen"
    assert extract_value(ex, screen_from_tree(RELOADING), SONG) is None  # no answer rather than the mini player's
    # What was compiled before, on the reload frame: the Button that shows the song, i.e. the mini player.
    from routines.model import Extract
    before = Extract(locator=Locator(text_has="{{song_title}}", kind="Button"), segment=1)
    assert extract_value(before, screen_from_tree(RELOADING), SONG) == "Royal Philharmonic Orchestra & Matthew Freeman"
