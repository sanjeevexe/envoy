"""Approvals from the web app (design doc, Safety › Approvals).

- A request shows a screenshot, a one-line description and the reasons, in the approvals inbox, and goes out as an
  event to every interface.
- Only a person decides: through the web app's session, by POST (`decide`). No MCP tool and no chat tool can approve,
  and opening an approval link never decides anything (link previews fetch links on their own).
- No answer within the time limit means no: the action is not taken and the task stops to wait. Never auto-approved.
- The approval is bound to the screen it was shown for: if the screen changed by the time it is approved, the action
  is not taken and the agent looks again (and asks again if the step is still needed).

`request` runs in a worker thread (the agent calls approvers through `asyncio.to_thread`), so it blocks on a
threading event and reaches the phone through the API's event loop.
"""

from __future__ import annotations

import asyncio
import io
import threading
from typing import Any, Callable

from policy.approval_rules import ApprovalRules, decide as already_approved
from policy.approvals import ApprovalDecision, ApprovalRequest

from api.store import API_DIR, TaskStore

SHOTS = API_DIR / "approvals"


def _key(screen: Any) -> tuple[str, ...]:
    """What the user approved looking at: the app and every label of the app's own elements. A new pop-up in the app, a
    changed price or another screen all change it; the status bar's clock and the on-screen keyboard (other windows,
    which come and go on their own) don't."""
    own = [e for e in screen.numbered if not e.status_bar and e.label and getattr(e, "package", screen.package) == screen.package]
    return (screen.package, *sorted(e.label for e in own))


class WebApprover:
    def __init__(self, store: TaskStore, bus: Any, loop: asyncio.AbstractEventLoop, task_id: str,
                 phone: Callable[[], Any], on_wait: Callable[[str | None], None], timeout_s: float = 900,
                 rules: Callable[[], ApprovalRules] = ApprovalRules) -> None:
        self.store, self.bus, self.loop, self.task_id = store, bus, loop, task_id
        self.phone = phone  # the raw (ungated) device, for the screenshot and the screen check
        self.on_wait = on_wait  # tells the runner the task is waiting (approval id) or not (None)
        self.timeout_s = timeout_s
        self.rules = rules  # the user's approval settings (read on every request: changes apply at once)
        self._events: dict[str, threading.Event] = {}
        self.requests: list[ApprovalRequest] = []

    # Called by the web app's POST handler (never from MCP or chat).
    def decide(self, approval_id: str, approved: bool, by: str = "user") -> dict[str, Any] | None:
        rec = self.store.decide_approval(approval_id, "approved" if approved else "declined", by)
        if rec is not None:
            ev = self._events.get(approval_id)
            if ev:
                ev.set()
            self.bus.publish("approval_decided", approval=rec, task_id=self.task_id)
        return rec

    def _save_shot(self, approval_id: str, shot: bytes | None) -> None:
        if not shot:
            return
        path = SHOTS / f"{approval_id}.jpg"
        path.write_bytes(shot)
        with self.store.lock:
            self.store.db.execute("UPDATE approvals SET screenshot=? WHERE id=?", (path.name, approval_id))
            self.store.db.commit()

    def _run(self, coro: Any, timeout: float = 15) -> Any:
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    def request(self, req: ApprovalRequest) -> ApprovalDecision:
        self.requests.append(req)
        device = self.phone()
        shot = None
        screen = None
        try:
            screen = self._run(device.observe())
            if not screen.secure:  # never keep a picture of a secure (sign-in, payment) screen
                img = device.frame(540)
                SHOTS.mkdir(parents=True, exist_ok=True)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=70)
                shot = buf.getvalue()
        except Exception:  # noqa: BLE001 - an approval without a picture is still an approval request
            pass
        task = self.store.get(self.task_id) or {}
        auto = already_approved(self.rules(), goal=task.get("request") or task.get("goal") or "", source=task.get("source") or "",
                                app=req.app, routine=task.get("routine"), origin=req.origin, target=req.target,
                                screen_text=req.screen, inputs=task.get("inputs") or {})
        rec = self.store.add_approval(self.task_id, req.description, req.reasons, req.app, req.screen, None)
        if auto is not None:
            # Done without asking, and said so: the approval is on record with who gave it and why.
            self._save_shot(rec["id"], shot)
            final = self.store.decide_approval(rec["id"], "approved", auto.by, auto.why)
            self.bus.publish("approval_decided", approval={k: v for k, v in (final or rec).items() if k != "nonce"}, task_id=self.task_id, auto=True)
            seq = self.store.add_step(self.task_id, {"kind": "approval", "text": f"{req.target or req.description}: done without asking ({auto.by})",
                                                     "reason": auto.why})
            self.bus.publish("step", task_id=self.task_id, step={"seq": seq, "kind": "approval", "text": f"{req.target or req.description}: done without asking ({auto.by})",
                                                               "reason": auto.why})
            return ApprovalDecision(True, by=auto.by, note=auto.why)
        done = threading.Event()
        self._events[rec["id"]] = done  # registered at once, so a decision that comes right away still wakes us
        if shot:
            self._save_shot(rec["id"], shot)
            rec = self.store.approval(rec["id"])
        self.on_wait(rec["id"])
        self.bus.publish("approval_requested", approval={k: v for k, v in rec.items() if k != "nonce"}, task_id=self.task_id)
        try:
            if not done.wait(self.timeout_s) and self.store.decide_approval(rec["id"], "expired", "timeout",
                                                                            "no answer in time: not done, never auto-approved"):
                self.bus.publish("approval_decided", approval=self.store.approval(rec["id"]), task_id=self.task_id)
                return ApprovalDecision(False, by="timeout", note="no answer in time")
            final = self.store.approval(rec["id"]) or {}
            if final.get("status") != "approved":
                return ApprovalDecision(False, by=final.get("decided_by") or "user", note="declined")
            # Bound to the screen it was shown for: if it changed while waiting, don't act on the old picture.
            try:
                now = self._run(device.observe())
                if screen is not None and _key(now) != _key(screen):
                    before, after = set(_key(screen)), set(_key(now))
                    diff = "; ".join([*(f"gone: {x[:40]}" for x in sorted(before - after)), *(f"new: {x[:40]}" for x in sorted(after - before))])[:300]
                    self.store.db.execute("UPDATE approvals SET note=? WHERE id=?", (f"the screen changed before the action ran ({diff}): asked again", rec["id"]))
                    self.store.db.commit()
                    return ApprovalDecision(False, by="screen_changed", note="the screen changed while waiting")
            except Exception:  # noqa: BLE001
                pass
            return ApprovalDecision(True, by=final.get("decided_by") or "user")
        finally:
            self._events.pop(rec["id"], None)
            self.on_wait(None)
