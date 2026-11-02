"""Round trips and corrections (Nov 2, TikTok: the real post went up without its song).

The source run (task-1101-210013-7814) chose the sound with the result's check mark, then tapped its row, which TikTok
reads as "no sound", and closed the sheet: the editor said "Music · Add sound". It went on to the post screen and typed
the caption, then saw no sound, went back, opened the sheet, tapped the row (now "on"), pressed Back ("Music · golden
hour") and came back to the post screen. The compiler took that correction for a round trip (post screen to post screen)
and dropped it, so the routine learned the failed first try; and its after-check on the editor read only "Music".

The screens here are a small made-up app with TikTok's shape (its own trees hold other people's videos and places).
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from routines import checks as chk
from routines.compiler import _toward_goal, clean, generalize_check
from routines.model import Check, Locator
from routines.screens import screen_from_tree

GOAL = 'Post my newest video with the sound "golden hour" by JVKE and the caption "hello"'


def _el(i: int, rid: str, label: str, kind: str = "Button", **kw) -> dict:
    return {"index": i, "parent": None, "number": i + 1, "resource_id": f"app:id/{rid}", "label": label, "text": label, "kind": kind,
            "class": "android.widget.Button", "bounds": [0, 100 * i, 1080, 100 * i + 90], "clickable": True, **kw}


def _editor(music: str) -> dict:
    return {"package": "app", "activity": "Editor", "signature": "editor",
            "elements": [_el(0, "music", f"Music · {music}"), _el(1, "next", "Next")]}


def _sheet(state: str) -> dict:
    return {"package": "app", "activity": "Editor", "signature": "sheet",
            "elements": [_el(0, "sheet_title", "Sounds", "Text"), _el(1, "apply", "Use"),
                         _el(2, "row", "golden hour · JVKE", in_list=True), _el(3, "state", state, "Text")]}


def _post(caption: str, activity: str = "Editor") -> dict:
    # TikTok's post screen is in the editor's activity, as its sound sheet is: the caption's draft survives going back.
    return {"package": "app", "activity": activity, "signature": "post",
            "elements": [_el(0, "caption", "Add description..." + (f": {caption}" if caption else ""), "EditText", editable=True),
                         _el(1, "post", "Post")]}


SCREENS = {"editor_none": _editor("Add sound"), "editor_song": _editor("golden hour"), "sheet_off": _sheet("No music"),
           "sheet_on": _sheet("Music · Sound"), "post_empty": _post(""), "post_typed": _post("hello"),
           "doc_empty": _post("", "Document"), "doc_typed": _post("hello", "Document"), "doc_saved": _post("hello", "Document")}
SCREENS["doc_saved"]["elements"][1]["enabled"] = False  # Markor's Save goes disabled once the note is saved
TARGET = {"music": 0, "next": 1, "apply": 1, "row": 2, "caption": 0}


def _trace(tmp_path: Path, steps: list[tuple[str, str, str, str | None]]) -> Path:
    """steps: (before, action, after, target) in a trace in the agent's format."""
    trace = tmp_path / "trace"
    (trace / "screens").mkdir(parents=True)
    for name, tree in SCREENS.items():
        with gzip.open(trace / "screens" / f"{name}.json.gz", "wt") as f:
            json.dump(tree, f)
    records = []
    for n, (before, kind, after, target) in enumerate(steps, 1):
        dev = {"kind": kind, "element": TARGET[target] + 1 if target else None, "text": "hello" if kind == "type" else None,
               "submit": False}
        records.append({"step": n, "kind": "action", "tree_before": f"screens/{before}.json.gz", "tree_after": f"screens/{after}.json.gz",
                        "decision": {"reason": f"step {n}", "action": {"type": kind}}, "risk": {"level": "reversible"},
                        "device_action": dev, "result": {"ok": True}, "changed": True,
                        **({"target": {"index": TARGET[target]}} if target else {})})
    (trace / "steps.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return trace


def _kept(tmp_path: Path, steps: list) -> list[tuple[int, str]]:
    trace = _trace(tmp_path, steps)
    records = [json.loads(line) for line in (trace / "steps.jsonl").read_text().splitlines()]
    kept, _ = clean(trace, records, GOAL)
    return [(t.n, t.moved) for t in kept]


def test_a_correction_that_returns_to_the_same_state_is_spliced_and_its_typing_moved(tmp_path):
    # As the TikTok run: the check mark turns the sound on, the row turns it off, the first try closes the sheet with no
    # sound, the caption is typed, then back, the row (on), Back: "Music · golden hour", and Next.
    kept = _kept(tmp_path, [
        ("editor_none", "tap", "sheet_off", "music"),     # 1 open the sound sheet
        ("sheet_off", "tap", "sheet_on", "apply"),        # 2 the check mark: on
        ("sheet_on", "tap", "sheet_off", "row"),          # 3 the row: off again
        ("sheet_off", "back", "editor_none", None),       # 4 close it: no sound
        ("editor_none", "tap", "post_empty", "next"),     # 5 Next
        ("post_empty", "type", "post_typed", "caption"),  # 6 the caption
        ("post_typed", "back", "editor_none", None),      # 7 back to the editor: no sound
        ("editor_none", "tap", "sheet_off", "music"),     # 8 the sheet again
        ("sheet_off", "tap", "sheet_on", "row"),          # 9 the row: on
        ("sheet_on", "back", "editor_song", None),        # 10 Back: "Music · golden hour"
        ("editor_song", "tap", "post_typed", "next"),     # 11 Next (the caption is still there)
    ])
    # The state after 2 is the state after 9: everything between goes, but the caption is typed after the last Next.
    assert [n for n, _ in kept] == [1, 2, 10, 11, 6]
    assert kept[-1][1] == "moved after trace step 11: typed during the round trip 3–9"


def test_a_round_trip_that_made_a_screen_show_the_goal_is_a_correction(tmp_path):
    # Post screen to post screen, but on the way the editor came to show the sound the goal asks for: kept.
    steps = [
        ("post_empty", "back", "editor_none", None),
        ("editor_none", "tap", "sheet_off", "music"),
        ("sheet_off", "tap", "sheet_on", "row"),
        ("sheet_on", "back", "editor_song", None),
        ("editor_song", "tap", "post_empty", "next"),
    ]
    assert [n for n, _ in _kept(tmp_path, steps)] == [1, 2, 3, 4, 5]
    # A plain detour (the sheet opened and closed, nothing chosen) is still dropped.
    assert _kept(tmp_path / "b", [("editor_none", "tap", "sheet_off", "music"), ("sheet_off", "back", "editor_none", None),
                                  ("editor_none", "tap", "post_empty", "next")]) == [(3, "")]


def test_toward_goal_needs_a_part_of_the_goal_that_was_not_there():
    from types import SimpleNamespace
    none, song = screen_from_tree(_editor("Add sound")), screen_from_tree(_editor("golden hour"))
    other = screen_from_tree(_editor("Rust Ritual"))
    stretch = [SimpleNamespace(before=none, after=song)]
    assert _toward_goal(stretch, GOAL)
    assert not _toward_goal([SimpleNamespace(before=none, after=other)], GOAL)  # another sound: not what was asked
    assert not _toward_goal(stretch, "")


def test_typing_left_by_leaving_its_activity_is_not_moved(tmp_path):
    # Markor's shape: typing in a document, then leaving its editor (which saves it) and opening it again. The round trip
    # was the save: nothing moves and nothing is dropped.
    kept = _kept(tmp_path, [
        ("editor_none", "tap", "doc_empty", "next"),
        ("doc_empty", "type", "doc_typed", "caption"),
        ("doc_typed", "back", "editor_none", None),
        ("editor_none", "tap", "doc_saved", "next"),
    ])
    assert kept == [(1, ""), (2, ""), (3, ""), (4, "")]


def test_round_trip_typing_stays_when_its_screen_never_comes_back(tmp_path):
    # The caption is typed in a round trip, and the post screen never comes back afterwards: nothing is dropped.
    kept = _kept(tmp_path, [
        ("editor_none", "tap", "post_empty", "next"),
        ("post_empty", "type", "post_typed", "caption"),
        ("post_typed", "back", "editor_none", None),
        ("editor_none", "tap", "sheet_off", "music"),
    ])
    assert [n for n, _ in kept] == [1, 2, 3, 4]


def test_an_after_check_names_the_input_a_labels_value_shows():
    before, after = screen_from_tree(_sheet("Music · Sound")), screen_from_tree(_editor("golden hour"))
    inputs = {"sound_title": "golden hour", "sound_artist": "JVKE"}
    post = chk.derive_post(before, after, "back", None, None, inputs)
    music = next(c for c in post if c.locator is not None and c.locator.resource_id == "music")
    assert music.locator.text == "Music" and music.locator.text_has == "golden hour"
    general = generalize_check(music, inputs, [])
    assert general.locator.text_has == "{{sound_title}}" and general.locator.text == "Music"
    # It holds on the editor with the sound, and not on the one without: the step that added no sound fails.
    assert chk.evaluate(general, after, inputs).passed
    assert not chk.evaluate(general, screen_from_tree(_editor("Add sound")), inputs).passed
    # A value that shows no input keeps the label alone, as before.
    plain = chk.derive_post(before, screen_from_tree(_editor("Add sound")), "back", None, None, inputs)
    assert all(c.locator.text_has is None for c in plain if c.locator is not None)
    label_only = Check(kind="element_present", locator=Locator(text="Music", kind="Button"))
    assert generalize_check(label_only, inputs, []).locator.text_has is None
