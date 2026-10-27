"""Approvals for irreversible actions.

Only a person approves. Phase 1 asks in the terminal; Phase 4 adds the web and iPhone flow. The eval
runner uses a scripted approver that decides per task and records every request, so tests can check
that the gate fired exactly where it should.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ApprovalRequest:
    task_id: str
    goal: str
    app: str
    description: str  # e.g. 'Tap "Confirm check-in" in com.skylark.air'
    reasons: list[str]
    screen: str  # the compact screen the action is bound to
    screenshot_path: str | None = None


@dataclass
class ApprovalDecision:
    approved: bool
    by: str  # "user" (terminal), "eval-policy", ...
    note: str = ""
    decided_at: float = field(default_factory=time.time)


class Approver(Protocol):
    def request(self, req: ApprovalRequest) -> ApprovalDecision: ...


class TerminalApprover:
    """Asks in the terminal. No answer (EOF) or anything but y/yes means no: never auto-approve."""

    def request(self, req: ApprovalRequest) -> ApprovalDecision:
        print("\n" + "=" * 72)
        print(f"APPROVAL NEEDED  {req.description}")
        print(f"Task: {req.goal}")
        print("Why: " + "; ".join(req.reasons))
        print("-" * 72 + "\n" + req.screen + "\n" + "-" * 72)
        try:
            answer = input("Approve this action? [y/N] ").strip().lower()
        except EOFError:
            answer = ""
        return ApprovalDecision(answer in ("y", "yes"), by="user")


class ScriptedApprover:
    """For eval on our own test apps: approve or deny everything, and keep a log of the requests."""

    def __init__(self, approve: bool) -> None:
        self.approve = approve
        self.requests: list[ApprovalRequest] = []

    def request(self, req: ApprovalRequest) -> ApprovalDecision:
        self.requests.append(req)
        return ApprovalDecision(self.approve, by="eval-policy", note="test app" if self.approve else "denied by task setup")
