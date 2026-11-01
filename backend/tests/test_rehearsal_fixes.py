"""Two fixes from the pre-filming dress rehearsal (Oct 31).

1. DoorDash with no card on the account opened "Select Payment Method", so Place Order (doordash_order_meal's optional,
   irreversible last step) never showed; the routine skipped it as "only optional steps are left" and the order ended
   "done, all steps and checks passed" with nothing ordered and nothing asked.
2. The live view of envoy-test showed "frame: _InactiveRpcError" after the emulator restarted: the gRPC client kept the
   old launch's token until the API restarted.
"""

from __future__ import annotations

import asyncio

import grpc
import pytest

import devices.emulator_grpc as eg
import routines.executor as executor_mod
from agent.trace import TraceWriter
from devices.grpc_gen import emulator_controller_pb2 as pb
from devices.types import ActionResult
from policy.approvals import ScriptedApprover
from routines.executor import ExecConfig, RoutineExecutor
from routines.model import Check, Locator, Routine, Step, StepAction
from routines.screens import screen_from_tree

FAST = ExecConfig(pre_timeout_s=0.6, post_timeout_s=0.6, stable_s=0.2, poll_s=0.01, patch_screenshots=False)


@pytest.fixture(autouse=True)
def traces_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(executor_mod, "TraceWriter", lambda tid: TraceWriter(tid, root=tmp_path))


class NoModel:
    def call(self, *a, **kw):
        raise AssertionError("no model call expected")


def _screen(name: str, els: list[tuple[str, str]]):
    return screen_from_tree({"package": "com.dd.doordash", "activity": name, "signature": name, "elements": [
        {"index": i, "number": i + 1, "kind": k, "label": t, "text": t, "clickable": k == "Button", "bounds": [0, 200 * i, 1080, 200 * i + 150]}
        for i, (k, t) in enumerate(els)]})


class Checkout:
    """The cart, then checkout: with a card on the account it shows Place Order, without one DoorDash's payment sheet."""

    def __init__(self, card: bool) -> None:
        self.screens = {"cart": _screen("cart", [("Text", "Your cart from Chick-fil-A"), ("Button", "Continue")]),
                        "checkout": _screen("checkout", [("Text", "Checkout"), ("Button", "Place Order")] if card
                                            else [("Text", "Select Payment Method"), ("Button", "Add Card")])}
        self.at = "cart"
        self.taps: list[str] = []

    async def observe(self, screenshot: bool = False):
        return self.screens[self.at]

    async def act(self, a):
        label = self.screens[self.at].numbered[a.element - 1].label if a.element else None
        self.taps.append(label)
        if (self.at, label) == ("cart", "Continue"):
            self.at = "checkout"
        return ActionResult(ok=True, duration_ms=1.0)


ORDER = Routine(routine="order", app="com.dd.doordash", intent="Order my usual", steps=[
    Step(id="continue", intent="Continue to checkout", action=StepAction(kind="tap", target=Locator(text="Continue", kind="Button")),
         post=[Check(kind="screen_changed")]),
    Step(id="place_order", intent="Place the order (the payment step: it waits for your OK)", optional=True, risk="irreversible",
         pre=[Check(kind="element_present", locator=Locator(text="Place Order", kind="Button"))],
         action=StepAction(kind="tap", target=Locator(text="Place Order", kind="Button")), post=[Check(kind="screen_changed")])])


def _order(phone: Checkout):
    ex = RoutineExecutor(phone, adapter=NoModel(), approver=ScriptedApprover(approve=False), config=FAST)
    return asyncio.run(ex.run(ORDER, {}, launch="never", allow_repair=False, allow_agent=False))


def test_an_order_whose_pay_step_never_shows_needs_you_instead_of_ending_done():
    phone = Checkout(card=False)
    out = _order(phone)
    assert out.status == "needs_user" and "never got to 'place_order'" in out.detail
    assert out.steps[-1].id == "place_order" and out.steps[-1].status == "skipped"
    assert phone.taps == ["Continue"] and not out.approvals


def test_with_a_card_the_pay_step_still_asks():
    phone = Checkout(card=True)
    out = _order(phone)
    assert out.status == "declined" and phone.taps == ["Continue"]  # asked, declined, never tapped


class _Refused(grpc.RpcError):
    def __init__(self, code: grpc.StatusCode) -> None:
        self._code = code

    def code(self) -> grpc.StatusCode:
        return self._code


def _emulator(monkeypatch, launch: dict[str, str], fail: grpc.StatusCode = grpc.StatusCode.UNAUTHENTICATED) -> list[str]:
    """A fake emulator that accepts only the current launch's token; returns the tokens it saw, one per call."""
    seen: list[str] = []

    class Stub:
        def __init__(self, channel) -> None:
            pass

        def getScreenshot(self, request, timeout, metadata):
            token = dict(metadata).get("authorization", "")
            seen.append(token)
            if token != f"Bearer {launch['grpc.token']}":
                raise _Refused(fail)
            return pb.Image(format=pb.ImageFormat(width=2, height=1), image=bytes(6))

    monkeypatch.setattr(eg, "read_discovery", lambda port: dict(launch))
    monkeypatch.setattr(eg.pb_grpc, "EmulatorControllerStub", Stub)
    return seen


def test_the_live_view_reconnects_with_the_new_token_after_the_emulator_restarts(monkeypatch):
    launch = {"grpc.port": "8554", "grpc.token": "first"}
    seen = _emulator(monkeypatch, launch)
    g = eg.EmulatorGrpc(8554)
    assert g.frame(2).size == (2, 1)
    launch["grpc.token"] = "second"  # the emulator restarted: a new per-launch token
    assert g.frame(2).size == (2, 1)
    assert seen == ["Bearer first", "Bearer first", "Bearer second"]
    assert g.frame(2).size == (2, 1) and seen[-1] == "Bearer second"  # and it stays on the new one


def test_other_errors_are_not_retried(monkeypatch):
    launch = {"grpc.port": "8554", "grpc.token": "first"}
    seen = _emulator(monkeypatch, launch, fail=grpc.StatusCode.INVALID_ARGUMENT)
    g = eg.EmulatorGrpc(8554)
    g.connect()
    launch["grpc.token"] = "second"
    with pytest.raises(grpc.RpcError):
        g.frame(2)
    assert seen == ["Bearer first"]
