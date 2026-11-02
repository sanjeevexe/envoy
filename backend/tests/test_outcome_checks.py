"""Outcome checks before a routine's irreversible step (C2): what the typed inputs asked for is what's on screen.

Nov 2: a real TikTok went out without its song after passing every step check. The routine had learned a path that
picks the sound from the list and closes the sheet without applying it, and its only check afterwards was the word
"Music". These checks come from the routine's inputs and run in code just before the step that asks for the OK. The
song must have shown on the editor after it was picked, the caption field must still hold the caption, and the
gallery's newest clip must be the one Envoy pushed. The four posting routines' YAMLs aren't touched.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from api import handoff as hf
from api.store import TaskStore
from devices.types import ActionResult
from policy.approvals import ScriptedApprover
from routines import checks as chk
from routines.executor import ExecConfig, RoutineExecutor
from routines.model import InputSpec, Locator, Routine, Step, StepAction, load_yaml
from routines.screens import screen_from_tree

ROUTINES = Path(__file__).resolve().parents[2] / "data" / "routines"
APP = "com.zhiliaoapp.musically"
SONG, ARTIST, CAPTION = "golden hour", "JVKE", "Posted by Envoy · test"
FAST = ExecConfig(pre_timeout_s=0.3, post_timeout_s=0.3, stable_s=0.1, poll_s=0.01, patch_screenshots=False)


def _active(name: str) -> Routine:
    v = json.loads((ROUTINES / name / "index.json").read_text())["active"]
    return load_yaml((ROUTINES / name / f"v{v}.yaml").read_text())


def _screen(name: str, els: list[dict]) -> object:
    out = []
    for i, e in enumerate(els):
        label = e["label"]
        out.append({"index": i, "parent": None, "number": i + 1, "label": label, "text": e.get("text", label), "kind": e["kind"],
                    "resource_id": e.get("id", ""), "hint": e.get("hint", ""), "in_list": e.get("in_list", False),
                    "clickable": e["kind"] in ("Button", "EditText"), "editable": e["kind"] == "EditText",
                    "bounds": [0, 150 * i, 1080, 150 * i + 120]})
    return screen_from_tree({"package": APP, "activity": name, "signature": name, "width": 1080, "height": 2400, "elements": out})


SEARCH = _screen("search", [{"label": "Search", "kind": "EditText", "id": "hwf", "hint": "Search", "text": ""}])
RESULTS = _screen("results", [{"label": f"Search: {SONG}", "kind": "EditText", "id": "hwf", "hint": "Search", "text": SONG},
                              {"label": "Results", "kind": "List"},
                              {"label": f"{SONG} · {ARTIST} · 1:00", "kind": "Button", "in_list": True}])


def _editor(sound: str, caption: str = CAPTION) -> object:
    return _screen("editor", [{"label": f"Music · {sound}", "kind": "Text", "id": "e1v"},
                              {"label": f"Add description...: {caption}", "kind": "EditText", "id": "h_n", "hint": "Add description...",
                               "text": caption},
                              {"label": "Post", "kind": "Button", "id": "post"}])


def _routine() -> Routine:
    field = Locator(resource_id="hwf", hint="Search", kind="EditText")
    return Routine(routine="tiktok_like", app=APP, intent="Post the newest gallery video to TikTok with a chosen sound and caption",
                   inputs={"sound_title": InputSpec(description="Title of the sound to find"), "sound_artist": InputSpec(description="Artist"),
                           "caption": InputSpec(description="Caption for the post")},
                   steps=[Step(id="search", intent="Search for the sound", action=StepAction(kind="type", target=field, value="{{sound_title}}", submit=True)),
                          Step(id="pick", intent="Tap the sound", action=StepAction(kind="tap", target=Locator(text_has="{{sound_title}}", kind="Button", in_list=True))),
                          Step(id="close_sound_sheet", intent="Close the sheet", action=StepAction(kind="back")),
                          Step(id="type_caption", intent="Type the caption", action=StepAction(
                              kind="type", target=Locator(resource_id="h_n", hint="Add description...", kind="EditText"), value="{{caption}}")),
                          Step(id="tap_post", intent="Tap Post", risk="irreversible", action=StepAction(kind="tap", target=Locator(text="Post", kind="Button")))])


class _Phone:
    """The screens after each action, in order; the last one stays."""

    def __init__(self, screens: list, serial: str | None = None, newest: str | None = None) -> None:
        self.screens, self.i, self.acts = screens, 0, []
        if serial:
            self.serial = serial
            uri_id = newest.rsplit("/", 1)[-1] if newest else "1"
            self.adb = SimpleNamespace(shell=lambda cmd: f"Row: 0 _id={uri_id}, _display_name=newest.mp4, relative_path=DCIM/Camera/, "
                                                          f"date_added=1793604707, owner_package_name={APP}\n"
                                                          "Row: 1 _id=7, _display_name=old.mp4, relative_path=Movies/Envoy/, date_added=1, "
                                                          "owner_package_name=com.android.shell\n")

    async def observe(self, screenshot: bool = False):
        return self.screens[min(self.i, len(self.screens) - 1)]

    async def act(self, a):
        self.acts.append(a.kind)
        self.i += 1
        return ActionResult(ok=True, duration_ms=1.0)


def _run(phone: _Phone, caption: str = CAPTION):
    class NoModel:
        def call(self, *a, **kw):
            raise AssertionError("no model call expected")

    approver = ScriptedApprover(approve=False)
    ex = RoutineExecutor(phone, adapter=NoModel(), approver=approver, config=FAST)
    out = asyncio.run(ex.run(_routine(), {"sound_title": SONG, "sound_artist": ARTIST, "caption": caption},
                             launch="never", allow_repair=False, allow_agent=False))
    return out, approver


# ---- the plan, from the four posting routines' own inputs (their YAMLs untouched) ---------------------------------

@pytest.mark.parametrize("name,picks,fields", [
    ("instagram_reel_song", ["song_title"], ["caption"]),
    ("tiktok_post_sound", ["sound_title"], ["caption"]),
    ("youtube_short_sound", ["sound_title"], ["short_title"]),
    ("instagram_story_poll", [], ["poll_question", "poll_option_1", "poll_option_2"]),
])
def test_each_posting_routine_promises_its_song_its_typed_text_and_the_newest_clip(name, picks, fields):
    plan = chk.outcome_plan(_active(name))
    assert plan.picks == picks  # the title, not the artist: the editors show the title ("Music · golden hour")
    assert [n for n, _ in plan.fields] == fields and plan.gallery


def test_a_routine_with_no_media_and_no_gallery_promises_nothing_to_check():
    r = Routine(routine="r", app="a", intent="Check a flight's status", inputs={"flight": InputSpec(type="code")},
                steps=[Step(id="s", intent="Search", action=StepAction(kind="type", target=Locator(hint="Flight number"), value="{{flight}}"))])
    plan = chk.outcome_plan(r)
    assert plan.picks == [] and plan.fields == [] and not plan.gallery  # a code isn't free text, and nothing is posted from a gallery


# ---- the song: picked from a list, then shown on the editor --------------------------------------------------------

def test_a_song_picked_then_shown_on_the_editor_passes_and_one_left_in_the_sheet_does_not():
    plan = chk.OutcomePlan(picks=["sound_title"])
    good = chk.OutcomeWatch(plan, {"sound_title": SONG})
    for s in (SEARCH, RESULTS, _editor(SONG)):
        good.see(s)
    assert good.state == {"sound_title": "shown"} and good.problems() == []
    bad = chk.OutcomeWatch(plan, {"sound_title": SONG})
    for s in (SEARCH, RESULTS, _editor("Add sound")):  # Nov 2: the sheet closed without applying it
        bad.see(s)
    assert bad.state == {"sound_title": "picking"}
    assert bad.problems() == [f"sound_title {SONG!r} was picked from a list but never showed on the editor afterwards, so it may not be attached"]


def test_a_caption_that_mentions_the_song_doesnt_count_as_picking_it_again():
    w = chk.OutcomeWatch(chk.OutcomePlan(picks=["sound_title"]), {"sound_title": SONG})
    for s in (RESULTS, _editor(SONG, caption=f"{SONG} vibes")):  # the caption field isn't a search field
        w.see(s)
    assert w.problems() == []


# ---- the executor stops before the final button, with the reason -----------------------------------------------------

def test_a_songless_editor_stops_the_run_before_the_final_step():
    out, approver = _run(_Phone([SEARCH, RESULTS, RESULTS, _editor("Add sound"), _editor("Add sound")]))
    assert out.status == "failed" and approver.requests == []  # never asked: the Post button was never offered
    assert out.detail.startswith("stopped before the final step (outcome check): sound_title 'golden hour' was picked from a list")


def test_with_the_song_on_the_editor_the_run_reaches_the_final_step_and_asks():
    out, approver = _run(_Phone([SEARCH, RESULTS, RESULTS, _editor(SONG), _editor(SONG)]))
    assert out.status == "declined" and len(approver.requests) == 1


def test_a_caption_field_that_doesnt_hold_the_caption_stops_the_run():
    wrong = _editor(SONG, caption="Something else")
    out, approver = _run(_Phone([SEARCH, RESULTS, RESULTS, _editor(SONG), wrong]))
    assert out.status == "failed" and approver.requests == []
    assert "caption: the field on the final screen shows 'Something else', not 'Posted by Envoy · test'" in out.detail


# ---- the clip: the gallery's newest is the one Envoy pushed ------------------------------------------------------------

@pytest.fixture()
def pushes(tmp_path, monkeypatch):
    f = tmp_path / "pushes.json"
    monkeypatch.setattr(hf, "_pushes_file", lambda: f)
    return f


def test_another_clip_newer_than_the_pushed_one_stops_the_run_before_any_step(pushes):
    hf.remember_push(pushes, "SERIAL1", "video", "/sdcard/Movies/Envoy/clip.mp4", f"{hf.MEDIA['video']}/7")
    phone = _Phone([SEARCH, RESULTS, RESULTS, _editor(SONG), _editor(SONG)], serial="SERIAL1", newest=f"{hf.MEDIA['video']}/9")
    out, approver = _run(phone)
    assert out.status == "failed" and phone.acts == [] and approver.requests == []
    assert out.detail == ("stopped before starting (outcome check): the gallery's newest video is newest.mp4 (DCIM/Camera/, saved by "
                          f"{APP}), not clip.mp4, the clip Envoy put on the phone: the routine takes the newest, so it would post the wrong one")


def test_the_pushed_clip_still_newest_lets_the_run_through(pushes):
    hf.remember_push(pushes, "SERIAL1", "video", "/sdcard/Movies/Envoy/clip.mp4", f"{hf.MEDIA['video']}/9")
    out, approver = _run(_Phone([SEARCH, RESULTS, RESULTS, _editor(SONG), _editor(SONG)], serial="SERIAL1", newest=f"{hf.MEDIA['video']}/9"))
    assert out.status == "declined" and len(approver.requests) == 1


def test_an_old_push_is_not_an_expectation(pushes):
    hf.remember_push(pushes, "SERIAL1", "video", "/sdcard/Movies/Envoy/clip.mp4", f"{hf.MEDIA['video']}/7", at=1000.0)
    assert hf.recent_push("SERIAL1", now=1000.0 + hf.PUSH_FRESH_S + 1) is None
    assert hf.recent_push("SERIAL1", now=1001.0)["name"] == "clip.mp4"


def test_the_newest_media_is_read_by_date_then_id():
    rows = ("Row: 0 _id=5, _display_name=a.mp4, relative_path=Movies/Envoy/, date_added=20, owner_package_name=com.android.shell\n"
            "Row: 1 _id=6, _display_name=b.mp4, relative_path=Movies/Envoy/, date_added=20, owner_package_name=com.android.shell\n"
            "Row: 2 _id=9, _display_name=c.mp4, relative_path=Movies/Envoy/, date_added=10, owner_package_name=com.android.shell\n")
    assert hf.newest_media(lambda cmd: rows, "video") == {"media_uri": f"{hf.MEDIA['video']}/6", "name": "b.mp4", "path": "Movies/Envoy/",
                                                          "owner": "com.android.shell"}
    assert hf.newest_media(lambda cmd: "No result found.", "video") is None


def test_pushes_are_recorded_next_to_a_real_store_and_never_for_an_in_memory_one(tmp_path):
    assert hf.pushes_file_of(TaskStore(":memory:")) is None  # tests and eval/run_creator.py's push write nowhere
    assert hf.pushes_file_of(TaskStore(tmp_path / "envoy.db")) == tmp_path / "pushes.json"
    stand_in = SimpleNamespace(lock=threading.Lock(), db=sqlite3.connect(":memory:"))
    assert hf.pushes_file_of(stand_in) is None
