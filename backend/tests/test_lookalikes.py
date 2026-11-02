"""Look-alike targets: a compiled locator that matches several elements on the screen it was recorded on (Nov 1, the
showcase's first Instagram runs on the Pixel 5). Every gallery thumbnail reads "Unselected Video thumbnail created on
<date>", so the clip's locator fit all of them, the executor scrolled to look, and a repair picked an Oct 30 clip. Every
track row of a song search has a catalogue ID and, once its words were cut out as data, nothing else, so all of them tied
and the executor scrolled past the results.

tests/traces/lookalikes holds the screens of that run (task-1101-202945-39d5-r1): the gallery, the music search before
and after the search, the selected track, a scrolled gallery and another search's results from its replays, and an
Oct 29 gallery of six clips whose grid can't scroll.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import shutil
from pathlib import Path

from models.schemas import CompiledRoutine
from routines import checks as chk
from routines import locators
from routines.compiler import compile_trace, disambiguate
from routines.executor import list_choice
from routines.model import Check, Locator, dump_yaml, load_yaml
from routines.screens import load_tree, short_id

LA = Path(__file__).parent / "traces" / "lookalikes"
IG = "com.instagram.android"
INPUTS = {"song_title": "golden hour", "song_artist": "JVKE"}
NEWEST = "Unselected Video thumbnail created on November 1, 2026 7:19 PM"


def _screen(name: str):
    return load_tree(LA / f"{name}.json.gz")


def _thumbs(s):
    thumbs = [e for e in s.numbered if short_id(e.resource_id) == "gallery_grid_item_thumbnail"]
    return sorted(thumbs, key=lambda e: (e.bounds[1], e.bounds[0]))


def _record(n: int, before: str, after: str, target: int, action: dict, reason: str) -> dict:
    return {"step": n, "kind": "action", "tree_before": f"screens/{before}.json.gz", "tree_after": f"screens/{after}.json.gz",
            "decision": {"reason": reason, "expected_result": "", "action": action}, "risk": {"level": "reversible"},
            "device_action": {"kind": action["type"], "element": action.get("element"), "text": action.get("text"),
                              "submit": action.get("submit", False)},
            "result": {"ok": True}, "target": {"index": target}, "changed": True}


def _compile(tmp_path: Path):
    """The run's three steps that matter here (the clip, the search, the track), compiled with Wonder's own answer."""
    trace = tmp_path / "trace"
    (trace / "screens").mkdir(parents=True)
    for name in ("gallery", "gallery_after", "search", "tracks", "tracks_after"):
        shutil.copy(LA / f"{name}.json.gz", trace / "screens" / f"{name}.json.gz")
    goal = 'Make a reel of the newest video in my gallery with the song "golden hour" by JVKE from Instagram\'s music library'
    (trace / "run.json").write_text(json.dumps({"task_id": "t-lookalikes", "goal": goal, "status": "done", "result": "Added the song.",
                                                "check": {"passed": True, "detail": "ok"}, "plan": {"app": "Instagram"}}))
    records = [
        _record(1, "gallery", "gallery_after", 86, {"type": "tap", "element": 15}, "Newest video thumbnail"),
        _record(2, "search", "tracks", 122, {"type": "type", "element": 16, "text": "golden hour", "submit": True}, "Search the song"),
        _record(3, "tracks", "tracks_after", 150, {"type": "tap", "element": 23}, "golden hour by JVKE is the first result"),
    ]
    (trace / "steps.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n")
    spec = CompiledRoutine.model_validate({
        "name": "instagram_reel_song", "intent": "Make a reel set to a song", "description": "", "patterns": [],
        "inputs": [{"name": "song_title", "type": "text", "description": "", "from_memory": None, "example": "golden hour"},
                   {"name": "song_artist", "type": "text", "description": "", "from_memory": None, "example": "JVKE"}],
        "steps": [{"step": 1, "id": "tap_newest_video_thumbnail", "intent": "Tap the newest video",
                   "target_fixed_text": "Video thumbnail created on", "choice_input": None},
                  {"step": 2, "id": "search_song_title", "intent": "Type {{song_title}}", "target_fixed_text": "Search...",
                   "choice_input": None},
                  {"step": 3, "id": "tap_matching_track", "intent": "Tap the track {{song_title}} by {{song_artist}}",
                   "target_fixed_text": "Select track", "choice_input": "song_title"}],
        "outputs": [], "data_values": ["November 1, 2026 7:19 PM", "3:29"]})
    return asyncio.run(compile_trace(trace, spec=spec))


def _ready(step, s, inputs) -> object | None:
    """What a rerun taps on this screen without climbing the ladder: before-checks pass and the target is found."""
    if not all(o.passed for o in chk.evaluate_all(step.pre, s, inputs)):
        return None
    return list_choice(step.action.target, s, inputs, locators.STRICT).element


# ---- (b) the gallery's newest clip: its place among look-alikes, with the list at its start ------------------------------


def test_the_newest_clip_is_the_first_thumbnail_after_the_camera_tile(tmp_path):
    routine, report = _compile(tmp_path)
    clip = next(s for s in routine.steps if s.id == "tap_newest_video_thumbnail")
    assert clip.action.target.nth == 0 and clip.action.target.position is None
    assert clip.action.target.text == "Video thumbnail created on"  # Wonder's fixed text stays
    assert Check(kind="element_present", locator=Locator(text="Open camera", kind="Button")) in clip.pre
    assert any("now the first of them in its list" in w for w in report.warnings)
    assert not report.ambiguous

    assert _ready(clip, _screen("gallery"), INPUTS).label == NEWEST
    # Oct 29's gallery: six clips, a grid that can't scroll (its list node isn't on screen), the first clip is the newest.
    six = _screen("gallery_six_clips")
    assert _ready(clip, six, INPUTS).index == _thumbs(six)[0].index
    # A replay's gallery scrolled down to Oct 30: the newest clip isn't there, and nothing else is taken for it.
    scrolled = _screen("gallery_scrolled")
    assert locators.locate(clip.action.target, scrolled, INPUTS).ok  # the place alone would pick the top Oct 30 clip...
    assert _ready(clip, scrolled, INPUTS) is None  # ...but the list isn't at its start


def test_a_place_among_look_alikes_survives_yaml_and_patches():
    loc = Locator(resource_id="gallery_grid_item_thumbnail", text="Video thumbnail created on", kind="Button", in_list=True, nth=1)
    s = _screen("gallery")
    second = _thumbs(s)[1]
    assert locators.locate(loc, s).element.index == second.index
    assert "nth=1" in loc.describe()
    assert locators.updated(loc, second, s).nth == 1
    # A patch keeps the fixed words, not the clip's date, even where the grid's cells aren't marked as a list (Oct 29).
    six = _screen("gallery_six_clips")
    patched = locators.updated(loc.model_copy(update={"in_list": False, "nth": 0}), _thumbs(six)[2], six)
    assert patched.text == "Video thumbnail created on" and patched.position is None and patched.nth == 0
    from routines.model import Routine, Step, StepAction
    r = Routine(routine="r", app=IG, intent="i", steps=[Step(id="a", intent="i", action=StepAction(kind="tap", target=loc))])
    assert "nth: 1" in dump_yaml(r) and load_yaml(dump_yaml(r)).steps[0].action.target.nth == 1


def test_look_alikes_in_rows_of_different_shapes_have_no_place():
    s = _screen("gallery")
    assert locators.in_order(_thumbs(s), s) is not None
    camera = next(e for e in s.numbered if e.label == "Open camera")
    assert locators.in_order([camera, *_thumbs(s)], s) is None  # not one ID and type
    assert locators.list_head(_thumbs(s), s).label == "Open camera"
    assert locators.list_head(_thumbs(_screen("gallery_scrolled")), _screen("gallery_scrolled")) is None  # it starts with clips


# ---- (a) the track: the row that shows the inputs ---------------------------------------------------------------------


def test_the_track_is_the_row_that_shows_the_song_and_its_artist(tmp_path):
    routine, report = _compile(tmp_path)
    track = next(s for s in routine.steps if s.id == "tap_matching_track")
    assert track.action.target.text_has == "{{song_title}} by {{song_artist}}"
    assert any("now the one that shows {{song_title}} by {{song_artist}}" in w for w in report.warnings)
    # The artist is used by the tap now: no check on one track's catalogue ID, and no "only works when" limit.
    assert not any("audio_browser_track_0" in (c.locator.resource_id or "") for c in track.pre if c.locator)
    assert "Only works when" not in routine.description
    # Like any row chosen by an input, it is scrolled to first if a longer list puts it lower.
    i = routine.step_index("tap_matching_track")
    assert routine.steps[i - 1].action.kind == "scroll_until" and routine.steps[i - 1].action.target == track.action.target

    assert _ready(track, _screen("tracks"), INPUTS).label == "Select track golden hour by JVKE,3:29"
    assert _ready(track, _screen("tracks"), {"song_title": "Golden Hour", "song_artist": "Kacey Musgraves"}).label \
        == "Select track Golden Hour by Kacey Musgraves,3:18"
    # Another search's results: one shows JVKE ("this is what autumn feels like"), none shows "golden hour by JVKE".
    other = _screen("tracks_other_search")
    assert any("JVKE" in e.label for e in other.numbered)
    assert _ready(track, other, INPUTS) is None


# ---- unchanged and (c) ambiguous ----------------------------------------------------------------------------------------


def test_a_locator_that_already_picks_its_element_is_left_exactly_as_it_is():
    s = _screen("tracks_after")
    done = next(e for e in s.numbered if short_id(e.resource_id) == "audio_bar_select_tap_target")
    loc = locators.build(done, s)
    got, pre, how, n = disambiguate(loc, done, s, INPUTS, [])
    assert got is loc and pre == [] and how is None and n == 1
    # Too weak to find anything is another problem: left alone too.
    weak = Locator(text="Nothing like this", kind="Button")
    assert disambiguate(weak, done, s, INPUTS, [])[2] is None


def test_look_alikes_that_nothing_tells_apart_are_reported_ambiguous():
    s = _screen("gallery_scrolled")  # no fixed item at the list's start, and no input in the labels
    target = _thumbs(s)[0]
    loc = Locator(resource_id="gallery_grid_item_thumbnail", text="Video thumbnail created on", kind="Button", cls="Button", in_list=True)
    got, pre, how, n = disambiguate(loc, target, s, INPUTS, [])
    assert how == "ambiguous" and got is loc and pre == [] and n == len(_thumbs(s))
    # A target reached by scrolling has no place to keep either: how far the list went decides it.
    g = _screen("gallery")
    assert disambiguate(loc, _thumbs(g)[0], g, INPUTS, [], scrolled=True)[2] == "ambiguous"
    # A text field isn't chosen by the input it holds: on another run it holds something else.
    t = _screen("tracks")
    row = next(e for e in t.numbered if e.label == "Select track golden hour by JVKE,3:29")
    rows = Locator(resource_id="audio_browser_track_*_*", kind="Button", cls="Button", parent="music_list", in_list=True)
    assert disambiguate(rows, row, t, INPUTS, [])[2] == "text_has"
    got, _, how, _ = disambiguate(rows, dataclasses.replace(row, editable=True), t, INPUTS, [])
    assert how != "text_has" and got.text_has is None


# ---- checks on something only passing through the screen ----------------------------------------------------------------
# Nov 1, a recompiled story replay: step 1's after-check was Instagram's fast-scroll "Today", which shows only while the
# gallery grid moves (here, for a moment as it opens). It failed, the executor scrolled to find it, and the gallery was left
# at Oct 29: the next step's "Open camera" check failed and the repair took the top clip there, the wrong one.

TODAY = Check(kind="element_present", locator=Locator(resource_id="fast_scroll_container", text="Today", kind="Text"))


def test_a_check_on_a_scroll_indicator_or_on_what_is_gone_a_moment_later_is_not_compiled():
    from routines.compiler import _passing
    opening, settled = _screen("story_gallery_opening"), _screen("story_gallery")
    assert chk.evaluate(TODAY, opening, {}).passed and not chk.evaluate(TODAY, settled, {}).passed
    assert _passing(TODAY, opening, None, {}) == "a scroll indicator"
    # Named otherwise, it is still gone from the same screen when the next step starts.
    assert _passing(Check(kind="text_visible", text="Today"), opening, settled, {}) == "gone from the same screen when the next step starts"
    assert _passing(Check(kind="text_visible", text="Today"), opening, _screen("tracks"), {}) is None  # another screen says nothing
    title = Check(kind="element_present", locator=Locator(resource_id="gallery_title_container", text="Add to story", kind="Text"))
    assert _passing(title, opening, settled, {}) is None


def test_the_gallery_opening_step_keeps_its_title_check_and_drops_today(tmp_path):
    trace = tmp_path / "trace"
    (trace / "screens").mkdir(parents=True)
    for name in ("tracks_after", "story_gallery_opening", "story_gallery", "gallery_after"):
        shutil.copy(LA / f"{name}.json.gz", trace / "screens" / f"{name}.json.gz")
    music, opening, settled = _screen("tracks_after"), _screen("story_gallery_opening"), _screen("story_gallery")
    assert TODAY in chk.derive_post(music, opening, "tap", None, None, {})  # what the compiler wrote before
    back = next(e for e in music.numbered if e.label == "Back")
    newest = _thumbs(settled)[0]
    run = {"task_id": "t-today", "goal": "Pick the newest video in my story gallery", "status": "done", "result": "Picked it.",
           "check": {"passed": True, "detail": "ok"}}
    (trace / "run.json").write_text(json.dumps(run))
    (trace / "steps.jsonl").write_text("\n".join(json.dumps(r) for r in [
        _record(1, "tracks_after", "story_gallery_opening", back.index, {"type": "tap", "element": back.number}, "Back to the gallery"),
        _record(2, "story_gallery", "gallery_after", newest.index, {"type": "tap", "element": newest.number}, "Newest video"),
    ]) + "\n")
    spec = CompiledRoutine.model_validate({
        "name": "instagram_story_clip", "intent": "Pick the newest clip", "description": "", "patterns": [], "inputs": [],
        "steps": [{"step": 1, "id": "open_gallery", "intent": "Open the gallery", "target_fixed_text": "Back", "choice_input": None},
                  {"step": 2, "id": "select_newest_video", "intent": "Tap the newest video",
                   "target_fixed_text": "Video thumbnail created on", "choice_input": None}],
        "outputs": [], "data_values": []})
    routine, report = asyncio.run(compile_trace(trace, spec=spec))
    opened = routine.steps[0]
    assert TODAY not in opened.post and not any("fast_scroll" in c.describe() for c in opened.post)
    assert any(c.locator is not None and c.locator.text == "Add to story" for c in opened.post)
    assert any("fast_scroll_container" in w and "a scroll indicator; dropped" in w for w in report.warnings)
    assert routine.steps[1].action.target.nth == 0


class _Gallery:
    """A gallery that a scroll up brings back to its start and a scroll down takes to Oct 30."""

    def __init__(self, at_start: bool) -> None:
        self.screen = _screen("gallery") if at_start else _screen("gallery_scrolled")
        self.moves: list[str] = []

    async def act(self, a):
        self.moves.append(a.direction)
        self.screen = _screen("gallery") if a.direction == "up" else _screen("gallery_scrolled")

    async def observe(self, screenshot: bool = False):
        return self.screen


def _clip_step(nth: int | None, pre: list[Check]):
    from routines.model import Step, StepAction
    return Step(id="clip", intent="Tap the newest video", pre=pre, action=StepAction(kind="tap", target=Locator(
        resource_id="gallery_grid_item_thumbnail", text="Video thumbnail created on", kind="Button", cls="Button", in_list=True, nth=nth)))


def test_a_place_among_look_alikes_is_looked_for_back_at_the_lists_start():
    from types import SimpleNamespace
    from routines.executor import RoutineExecutor
    start = [Check(kind="element_present", locator=Locator(text="Open camera", kind="Button"))]
    dev = _Gallery(at_start=False)
    found = asyncio.run(RoutineExecutor(dev)._reveal(SimpleNamespace(inputs={}), _clip_step(0, start)))
    assert dev.moves == ["up"] and found is not None and found[1].element.label == NEWEST
    # Back at the start and still not ready: it stays there (a repair then sees the newest clips), never scrolls down.
    dev = _Gallery(at_start=True)
    never = [Check(kind="element_present", locator=Locator(text="Nothing like this", kind="Button"))]
    assert asyncio.run(RoutineExecutor(dev)._reveal(SimpleNamespace(inputs={}), _clip_step(0, never))) is None
    assert set(dev.moves) == {"up"} and dev.screen is not None and any(e.label == "Open camera" for e in dev.screen.numbered)
    # Any other target is looked for below first, as before.
    dev = _Gallery(at_start=True)
    asyncio.run(RoutineExecutor(dev)._reveal(SimpleNamespace(inputs={}), _clip_step(None, never)))
    assert dev.moves[0] == "down"
