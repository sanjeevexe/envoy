"""A system dialog in front of a routine's done-check (backlog #59).

Nov 2, real post 3 (task-1102-014139-7f5e): tiktok_post_sound posted, then Android asked "Allow TikTok to access your
contacts?" over the app, and the done-check ("the caption is visible") failed behind it, so a posted video ended "failed".
A step's after-checks already dismiss known pop-ups; the done-check now does too (denied, never allowed), then reads once
more.
"""

from __future__ import annotations

import asyncio

from devices.types import ActionResult
from policy.approvals import ScriptedApprover
from routines.executor import ExecConfig, RoutineExecutor
from routines.model import Check, InputSpec, Routine, Step, StepAction
from routines.screens import screen_from_tree

TIKTOK = "com.zhiliaoapp.musically"
CAPTION = "Posted by Envoy · test"
FAST = ExecConfig(pre_timeout_s=0.3, post_timeout_s=0.3, stable_s=0.1, poll_s=0.01, patch_screenshots=False)


def _screen(package: str, activity: str, labels: list[tuple[str, str]]):
    return screen_from_tree({"package": package, "activity": activity, "width": 1080, "height": 2400, "elements": [
        {"index": i, "parent": None, "number": i + 1, "label": label, "text": label, "kind": kind, "clickable": kind == "Button",
         "bounds": [0, 200 * i, 1080, 200 * i + 150]} for i, (label, kind) in enumerate(labels)]})


DIALOG = _screen("com.google.android.permissioncontroller", "com.android.permissioncontroller.permission.ui.GrantPermissionsActivity",
                 [("Allow TikTok to access your contacts?", "Text"), ("Allow", "Button"), ("Don’t allow", "Button")])
POSTED = _screen(TIKTOK, "com.ss.android.ugc.aweme.main.MainActivity", [("Profile", "Text"), (CAPTION, "Text")])
FEED = _screen(TIKTOK, "com.ss.android.ugc.aweme.main.MainActivity", [("For You", "Text")])


class _Phone:
    """The app's screen after posting, behind `prompts` permission dialogs that "Don't allow" closes one by one."""

    def __init__(self, prompts: int, behind=POSTED) -> None:
        self.prompts, self.behind, self.taps = prompts, behind, []

    async def observe(self, screenshot: bool = False):
        return DIALOG if self.prompts else self.behind

    async def act(self, a):
        if a.kind == "tap":
            label = (DIALOG if self.prompts else self.behind).numbered[a.element - 1].label
            self.taps.append(label)
            if self.prompts and label != "Allow":
                self.prompts -= 1
        return ActionResult(ok=True, duration_ms=1.0)


def _routine(intent: str = "Post a gallery video to TikTok with a sound and a caption") -> Routine:
    return Routine(routine="tiktok_post", app=TIKTOK, intent=intent, inputs={"caption": InputSpec(example=CAPTION)},
                   steps=[Step(id="tap_post", intent="Tap Post", action=StepAction(kind="wait", seconds=0.01))],
                   done=[Check(kind="text_visible", text="{{caption}}")])


def _run(phone: _Phone, routine: Routine | None = None):
    class NoModel:
        def call(self, *a, **kw):
            raise AssertionError("no model call expected")

    ex = RoutineExecutor(phone, adapter=NoModel(), approver=ScriptedApprover(approve=False), config=FAST)
    return asyncio.run(ex.run(routine or _routine(), {"caption": CAPTION}, launch="never", allow_repair=False, allow_agent=False))


def test_a_permission_dialog_in_front_of_the_done_check_is_denied_and_the_check_read_again():
    phone = _Phone(prompts=1)
    out = _run(phone)
    assert out.status == "done" and out.model_calls == 0
    assert phone.taps == ["Don’t allow"]  # never "Allow"
    assert out.popups == ["permission prompt: deny"]
    assert out.detail == "all steps and checks passed (a system dialog in front of the done-check was dismissed: permission prompt: deny)"


def test_dialogs_one_after_another_are_each_denied():
    phone = _Phone(prompts=2)
    out = _run(phone)
    assert out.status == "done" and phone.taps == ["Don’t allow", "Don’t allow"]


def test_without_a_dialog_nothing_changes():
    phone = _Phone(prompts=0)
    out = _run(phone)
    assert out.status == "done" and out.detail == "all steps and checks passed" and phone.taps == []
    # A done-check that fails for itself still fails, and nothing is tapped.
    phone = _Phone(prompts=0, behind=FEED)
    out = _run(phone)
    assert out.status == "failed" and out.detail.startswith("done-check failed") and phone.taps == []


def test_a_dialog_denied_with_the_proof_still_missing_fails_as_before():
    phone = _Phone(prompts=1, behind=FEED)
    out = _run(phone)
    assert out.status == "failed" and out.detail.startswith("done-check failed") and phone.taps == ["Don’t allow"]


def test_a_routine_about_that_permission_leaves_the_dialog_to_the_user():
    # The shared handler never answers a prompt the routine's own goal is about.
    phone = _Phone(prompts=1)
    out = _run(phone, _routine("Allow TikTok to access my contacts"))
    assert out.status == "failed" and phone.taps == []
