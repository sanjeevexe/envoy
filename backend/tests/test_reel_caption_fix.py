"""instagram_reel_song v4 (showcase, Nov 3): Instagram's OK ends the caption edit instead of Back, which in the showcase
batch (B1 R03, R07) sometimes left the caption empty at Share; a caption found empty before Share is typed again. The
outcome check before Share is unchanged."""

from __future__ import annotations

import asyncio
from pathlib import Path

from devices.types import ActionResult
from policy.approvals import ScriptedApprover
from routines import checks as chk
from routines.executor import ExecConfig, RoutineExecutor
from routines.model import load_yaml
from routines.screens import screen_from_tree

ROUTINES = Path(__file__).resolve().parents[2] / "data" / "routines" / "instagram_reel_song"
APP = "com.instagram.android"
HINT = "Write a caption and add hashtags…"
CAPTION = "Envoy batch R03 · test"
FAST = ExecConfig(pre_timeout_s=0.3, post_timeout_s=0.3, stable_s=0.1, poll_s=0.01, patch_screenshots=False)


def _routine(version: int = 4):  # the version these tests are about, whichever one is active now
    return load_yaml((ROUTINES / f"v{version}.yaml").read_text())


def _screen(name: str, els: list[dict]) -> object:
    out = [{"index": i, "parent": None, "number": i + 1, "label": e["label"], "text": e.get("text", e["label"]), "kind": e["kind"],
            "resource_id": f"{APP}:id/{e['id']}" if e.get("id") else "", "hint": e.get("hint", ""), "in_list": e.get("in_list", False),
            "clickable": e["kind"] in ("Button", "EditText"), "editable": e["kind"] == "EditText", "focused": e.get("focused", False),
            "bounds": e.get("bounds", [0, 150 * i, 1080, 150 * i + 120])} for i, e in enumerate(els)]
    return screen_from_tree({"package": APP, "activity": "com.instagram.modal.ModalActivity", "signature": name, "width": 1080,
                             "height": 2340, "elements": out})


def _field(caption: str, **kw) -> dict:
    return {"label": f"{HINT}: {caption}" if caption else HINT, "text": caption or HINT, "hint": HINT, "kind": "EditText",
            "id": "caption_input_text_view", "in_list": True, **kw}


def share(caption: str) -> object:
    """The reel's last screen, keyboard down: the caption field, Save draft and Share."""
    return _screen(f"share-{bool(caption)}", [{"label": "Edit cover", "kind": "Button"}, _field(caption, bounds=[44, 1144, 1036, 1276]),
                                              {"label": "Tag people", "kind": "Button"},
                                              {"label": "", "kind": "Button", "id": "share_button_container", "bounds": [0, 2058, 1080, 2274]},
                                              {"label": "Save draft", "kind": "Button", "id": "save_draft_button", "bounds": [44, 2098, 518, 2219]},
                                              {"label": "Share", "kind": "Button", "id": "share_button", "bounds": [562, 2098, 1036, 2219]}])


def editing(caption: str) -> object:
    """Typing the caption: the keyboard hides Share, and Instagram shows OK in its top bar."""
    return _screen(f"editing-{caption}", [{"label": "Back", "kind": "Button", "id": "action_bar_button_back", "bounds": [0, 136, 154, 290]},
                                          {"label": "OK", "kind": "Button", "id": "action_bar_button_text", "bounds": [932, 157, 1058, 290]},
                                          _field(caption, focused=True, bounds=[44, 424, 1036, 556]),
                                          {"label": "Tag people", "kind": "Button"}])


class _Phone:
    """The screens after each action, in order; the last one stays."""

    def __init__(self, screens: list) -> None:
        self.screens, self.i, self.acts = screens, 0, []

    async def observe(self, screenshot: bool = False):
        return self.screens[min(self.i, len(self.screens) - 1)]

    async def act(self, a):
        self.acts.append(a.kind)
        self.i += 1
        return ActionResult(ok=True, duration_ms=1.0)


def _run(phone: _Phone, version: int | None = None):
    """The routine from its caption step to Share (the steps before it are v3's), declined at Share."""
    r = _routine(version)
    ids = [s.id for s in r.steps]
    r = r.model_copy(update={"steps": r.steps[ids.index("type_caption"):], "done": []})
    approver = ScriptedApprover(approve=False)

    class NoModel:
        def call(self, *a, **kw):
            raise AssertionError("no model call expected")

    out = asyncio.run(RoutineExecutor(phone, adapter=NoModel(), approver=approver, config=FAST).run(
        r, {"song_title": "golden hour", "song_artist": "JVKE", "caption": CAPTION}, launch="never", allow_repair=False, allow_agent=False))
    return out, approver


def test_v4_ends_the_caption_with_instagrams_ok_and_has_no_back_between_the_caption_and_share():
    steps = _routine().steps
    ids = [s.id for s in steps]
    tail = ids[ids.index("type_caption"):]
    assert tail == ["type_caption", "tap_caption_ok", "retype_caption_if_cleared", "tap_caption_ok_after_retype", "tap_post"]
    assert all(s.action.kind != "back" for s in steps[ids.index("type_caption"):])
    assert steps[-1].risk == "irreversible" and all(s.optional for s in steps[ids.index("tap_caption_ok"):-1])


def test_the_caption_kept_after_ok_goes_straight_to_share():
    phone = _Phone([share(""), editing(CAPTION), share(CAPTION)])
    out, approver = _run(phone)
    assert phone.acts == ["type", "tap"]  # typed, then OK; the guard and the second OK are skipped
    assert out.status == "declined" and len(approver.requests) == 1 and "Share" in approver.requests[0].description


def test_a_caption_dropped_after_ok_is_typed_again_before_share():
    phone = _Phone([share(""), editing(CAPTION), share(""), editing(CAPTION), share(CAPTION)])
    out, approver = _run(phone)
    assert phone.acts == ["type", "tap", "type", "tap"]
    assert out.status == "declined" and len(approver.requests) == 1


def test_a_caption_still_empty_at_share_is_stopped_by_the_outcome_check():
    # The guard types into a field that never takes the text: the check before Share still stops the run.
    phone = _Phone([share(""), editing(CAPTION), share(""), editing(""), share("")])
    out, approver = _run(phone)
    assert out.status == "failed" and approver.requests == []
    assert "caption: the field on the final screen shows" in out.detail


def test_v3_pressed_back_where_v4_taps_ok():
    ids = [s.id for s in _routine(3).steps]
    assert "close_keyboard" in ids and "tap_caption_ok" not in ids
    assert [n for n, _ in chk.outcome_plan(_routine()).fields] == ["caption"]  # one check, though v4 can type it twice
