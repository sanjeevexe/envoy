"""When Envoy may skip asking: what you asked for, standing approvals, and the cases that always ask (money, a
different action, different details, requests that didn't come from you)."""

from __future__ import annotations

import threading
from types import SimpleNamespace

from policy.approval_rules import ApprovalRules, decide, details_missing, names_action

CONFIRM = "Step 3 of 3\nConfirm check-in\nPassenger · Maya Patel\nFlight · SL 482 · Fri, Oct 30, 2026\nSeat · 14C"
RULES = ApprovalRules()  # default: don't ask for what you asked for


def ask(rules=RULES, **kw):
    base = dict(goal="Check me in for my flight", source="chat", app="com.skylark.air", routine="skylark_check_in_flight",
                origin="routine_step", target="Confirm check-in", screen_text=CONFIRM, inputs={"trip_city": "Chicago"})
    return decide(rules, **{**base, **kw})


def test_what_you_asked_for_runs_without_asking():
    auto = ask()
    assert auto is not None and auto.by == "your request" and "Check me in" in auto.why
    assert ask(goal="please check in for my Chicago trip") is not None  # Chicago is the trip's input
    assert names_action("change my seat to 21C", "Confirm seat") and not names_action("check me in", "Confirm")


def test_still_asks_for_anything_else():
    assert ask(target="Cancel trip") is None  # not what was asked
    assert ask(target="Confirm") is None  # says nothing about what it does
    assert ask(goal="Check me in for my Denver flight") is None  # the screen and the inputs are Chicago's
    assert details_missing("Change my seat to 21C", "Seat · 22F") == ["21C"]
    assert ask(goal="Add a checked bag to my trip", target="Add a checked bag ($35)") is None  # money always asks
    assert ask(target="Confirm check-in", screen_text=CONFIRM + "\nTotal due $35.00") is None
    assert ask(source="mcp") is None and ask(source="trigger:check in 24h before") is None  # not your own words
    assert ask(rules=ApprovalRules(default="always")) is None
    assert ask(rules=ApprovalRules(apps={"com.skylark.air": "always"})) is None


def test_a_button_that_commits_an_order_always_asks_even_when_you_named_it():
    """"schedule an order from Thai Basil", said by voice, used to skip asking at a checkout's "Schedule Order" when the
    screen didn't say "order total" or "payment method": an order is money, whatever the screen says."""
    cart = "Your cart from Thai Basil · Delivery 6:00 PM · Total $23.46 · Gift card"
    for verb in ("Schedule", "Place", "Submit", "Confirm", "Complete", "Finalize"):
        target = f"{verb} Order"
        assert decide(RULES, goal=f"{verb.lower()} an order from thai basil", source="voice", app="com.example.food", routine=None,
                      origin="agent", target=target, screen_text=cart) is None, target
    assert ask(target="Confirm check-in") is not None  # what isn't an order still runs when you asked for it


def test_standing_approval_covers_the_routine_only():
    standing = ApprovalRules(routines={"skylark_check_in_flight": "never"})
    auto = ask(rules=standing, source="trigger:check in 24h before", goal="Check me in for my flight to Chicago")
    assert auto is not None and auto.by == "standing approval"
    assert ask(rules=standing, source="mcp", origin="repair") is None  # a step a repair found isn't the routine's own
    assert ask(rules=standing, target="Pay $35", source="trigger:x") is None  # never for money
    assert ApprovalRules.from_dict({"default": "never", "apps": {"com.skylark.air": "never"}}).to_dict() == \
        {"default": "unless_requested", "apps": {}, "routines": {}}  # "never" only for a routine, by name


def test_the_approver_records_an_approval_you_already_gave():
    from api.approvals import WebApprover
    from api.store import TaskStore
    from policy.approvals import ApprovalRequest
    from tests.test_api import FakeDevice, background_loop

    store = TaskStore(":memory:")
    task = store.create("Check me in for my flight", "chat", request="check me in for my flight", routine="skylark_check_in_flight")
    events: list = []
    bus = SimpleNamespace(publish=lambda t, **kw: events.append(t))
    approver = WebApprover(store, bus, background_loop(), task["id"], phone=FakeDevice, on_wait=lambda _: None, timeout_s=2)
    out: dict = {}
    t = threading.Thread(target=lambda: out.update(d=approver.request(ApprovalRequest(
        task["id"], "check in", "com.skylark.air", 'tap "Confirm check-in"', ["rule"], CONFIRM, origin="routine_step", target="Confirm check-in"))))
    t.start()
    t.join(3)
    assert out["d"].approved and out["d"].by == "your request"  # no waiting for a person
    rec = store.approvals(task_id=task["id"])[0]
    assert rec["status"] == "approved" and rec["decided_by"] == "your request"
    assert "approval_decided" in events and store.steps(task["id"])[0]["kind"] == "approval"

    store.set_setting("approval_rules", {"default": "always"})
    approver.rules = lambda: ApprovalRules.from_dict(store.setting("approval_rules"))
    out.clear()
    t = threading.Thread(target=lambda: out.update(d=approver.request(ApprovalRequest(
        task["id"], "check in", "com.skylark.air", 'tap "Confirm check-in"', ["rule"], CONFIRM, origin="routine_step", target="Confirm check-in"))))
    t.start()
    t.join(3)  # "always ask": it waits for a person, and with no answer nothing is approved
    assert out["d"].by == "timeout" and not out["d"].approved
