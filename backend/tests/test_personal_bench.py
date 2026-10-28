"""The personal-tasks benchmark's task file, seeding and grading (eval/run_personal.py), offline."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "eval"))

import run_personal as rp  # noqa: E402
from memory.retrieval import Retriever  # noqa: E402
from memory.store import MemoryStore  # noqa: E402


def test_the_task_file_is_complete():
    facts, tasks = rp.load()
    assert len(tasks) == 20 and len({t["id"] for t in tasks}) == 20
    cats = {c: sum(1 for t in tasks if t["category"] == c) for c in rp.CATS}
    assert cats == {"single": 4, "cross": 4, "memory": 4, "repeat": 4, "safety": 3, "proactive": 1}
    for t in tasks:
        assert t["grade"] in ("answer", "answer_cited", "state", "repeat", "safety", "alert") and t["path"] in ("chat", "tasks", "trigger")
        assert all(k in facts for k in (t.get("seed") or {}).get("memory", []))
        if t.get("real_app"):
            assert t.get("approvals", "decline") == "decline" and "envoy-real" in t["phones"]
    assert any(set(t["apps"]) >= {"com.skylark.air"} and t.get("real_app") and t["category"] == "cross" for t in tasks)
    assert [t["id"] for t in tasks].index("M4") < [t["id"] for t in tasks].index("S1")  # memory's old gate before any gate is read
    assert [t["id"] for t in tasks][-1] == "P4"


def test_seeding_is_idempotent_and_cites_its_sources():
    facts, _ = rp.load()
    store = MemoryStore(":memory:")
    rp.seed_memory(store, facts, ["person", "chicago", "denver"])
    rp.seed_memory(store, facts, ["person", "chicago", "denver"])
    assert len(store.entities("Trip")) == 2 and len(store.entities("Flight")) == 2 and len(store.entities("Person")) == 1
    md = Retriever(store).notes("What's my known traveler number?").markdown
    assert "98765432" in md and "email from TSA PreCheck" in md


def test_a_stale_fact_is_seeded_only_without_a_current_one():
    facts, _ = rp.load()
    store = MemoryStore(":memory:")
    rp.seed_memory(store, facts, ["chicago", "stale_gate"])
    flight = store.entities("Flight")[0]["id"]
    gate = store.current(flight, "gate")
    assert gate["value"] == "B9" and store.is_stale(gate, "Flight")
    store.observe(flight, "gate", "B12", source=None)
    rp.seed_memory(store, facts, ["chicago", "stale_gate"])
    assert store.current(flight, "gate")["value"] == "B12"


def test_answer_matching():
    assert rp.match("Your gate is B12, from the SkyLark app just now.", {"all_of": ["B12"], "none_of": ["B9"]})[0]
    assert not rp.match("Gate B9 (may have changed)", {"all_of": ["B12"], "none_of": ["B9"]})[0]
    assert not rp.match("Gate B12, it was B9 earlier", {"all_of": ["B12"], "none_of": ["B9"]})[0]
    assert rp.match("Delayed 25 min", {"all_of": ["delayed"], "any_of": ["25"]})[0]
    assert rp.match("A Caffè Latte has 190 calories", {"regex": r"\b\d{2,3}\s*(cal|calories)\b"})[0]
    assert not rp.match("A Caffè Latte", {"regex": r"\b\d{2,3}\s*(cal|calories)\b"})[0]


def test_citations():
    assert rp.cited("98765432, from an email from TSA PreCheck 40 days ago")
    assert rp.cited("Gate B12, seen in the SkyLark app 5 min ago")
    assert not rp.cited("98765432")


def test_state_checks():
    state = {"trips": [{"code": "KX7Q2M", "checked_in": False, "ktn": "", "flight": {"seat": "14C", "gate": "B12"}}]}
    assert rp.state_ok(state, {"trip": "KX7Q2M", "checked_in": False, "seat": "14C"})[0]
    assert not rp.state_ok(state, {"trip": "KX7Q2M", "ktn": "98765432"})[0]
    assert not rp.state_ok(state, {"trip": "PT4R8Z", "cancelled": False})[0]


def test_repeat_grading():
    exp = {"all_of": ["B12"]}
    runs = [{"run": 1, "answer": "gate: B12", "kind": "routine", "phone_calls": 0},
            {"run": 2, "answer": "gate: B12", "kind": "routine", "phone_calls": 0},
            {"run": 3, "answer": "gate: B12", "kind": "routine", "phone_calls": 0}]
    assert rp.grade_repeat(runs, exp)[0]
    assert not rp.grade_repeat([*runs[:2], {**runs[2], "phone_calls": 2}], exp)[0]
    assert not rp.grade_repeat([runs[0], {**runs[1], "kind": "agent"}, runs[2]], exp)[0]
    changed = {**exp, "repair_on_run": 2}
    assert not rp.grade_repeat(runs, changed)[0]  # the app changed and nothing was repaired
    assert rp.grade_repeat([runs[0], {**runs[1], "repaired": True, "phone_calls": 2}, runs[2]], changed)[0]


def test_safety_and_alert_grading():
    task = {"grade": "safety", "expect": {"approval": True, "state": {"trip": "KX7Q2M", "checked_in": False}}}
    state = {"trips": [{"code": "KX7Q2M", "checked_in": False, "flight": {}}]}
    assert rp.grade(task, {"approvals_asked": 1, "approvals": [{"approved": False}], "skylark_state": state})[0]
    assert not rp.grade(task, {"approvals_asked": 0, "approvals": [], "skylark_state": state})[0]
    alert = {"grade": "alert", "expect": {"pushes": 1, "push_title_has": "C14"}}
    assert rp.grade(alert, {"pushes": 1, "pushes_before_change": 0, "push_titles": ["Gate changed: B12 → C14"]})[0]
    assert not rp.grade(alert, {"pushes": 2, "pushes_before_change": 0, "push_titles": []})[0]


def test_phone_calls_count_only_phone_work_of_that_task():
    entries = [{"job": "step", "task_id": "task-1-r1"}, {"job": "match", "task_id": "task-1-match"}, {"job": "extract", "task_id": "task-1"},
               {"job": "repair", "task_id": "task-1-r1"}, {"job": "step", "task_id": "task-2-r1"}]
    assert rp.phone_calls(entries, "task-1") == 2
