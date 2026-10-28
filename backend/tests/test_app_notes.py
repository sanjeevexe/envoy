"""App notes (memory/app_notes.py): written from runs, merged, filtered, capped, read into prompts, never facts about you."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.loop import AgentRunner, RunConfig
from devices.screen import build_state
from devices.types import ActionResult
from memory.app_notes import NOTE_TYPE, AppNotes, personal_reason, read_trace
from memory.retrieval import Retriever
from memory.store import MemoryStore
from models.prompts import plan_input, repair_input, step_input
from models.schemas import AppNoteOutput, Plan, StepOutput
from policy.approvals import ScriptedApprover

SKYLARK, STARBUCKS = "com.skylark.air", "com.starbucks.mobilecard"
SCREENS = Path(__file__).parent / "screens"
REF = {"task_id": "t1", "step": 2, "outcome": "done"}


def notes_store() -> tuple[MemoryStore, AppNotes]:
    store = MemoryStore(":memory:")
    return store, AppNotes(store)


class NotesAdapter:
    """Returns the app-note operations it is given; records what each call was asked."""

    def __init__(self, ops: list[dict] | None = None) -> None:
        self.ops, self.calls = ops or [], []

    def call(self, job, content, **kw):
        self.calls.append({"job": job, "content": content, **kw})
        parsed = AppNoteOutput.model_validate({"ops": [{"note_id": "", "text": "", "step": 0, "reason": "r", **o} for o in self.ops]})
        return SimpleNamespace(parsed=parsed, cost_usd=0.0005, cost_at_standard_usd=0.0005, usage={})


def write_trace(root: Path, app: str = SKYLARK) -> Path:
    d = root / "run1"
    (d / "screens").mkdir(parents=True)
    rows = [
        {"kind": "plan", "step": 0, "plan": {"subgoals": ["open the trip"]}},
        {"kind": "action", "step": 1, "screen_before": {"package": app, "compact": f'App: {app} · Screen: MainActivity · settled 50 ms\n[1] Text "My trips"'},
         "decision": {"reason": "open trips", "action": {"type": "tap", "element": 1}}, "target": {"label": "My trips"}, "changed": True,
         "screen_after": {"compact": f'App: {app} · Screen: MainActivity\n[1] Text "Gate · B12" (id: row_gate)'}, "screenshot_before": "screens/001_before.png"},
        {"kind": "action", "step": 2, "screen_before": {"package": app, "compact": f'App: {app} · Screen: MainActivity\n[1] Text "Gate · B12"'},
         "decision": {"reason": "answer", "action": {"type": "done", "result": "Gate B12"}}},
    ]
    (d / "steps.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    (d / "run.json").write_text(json.dumps({"task_id": "run1", "goal": "What gate does my Chicago flight leave from?", "status": "done", "result": "Gate B12"}))
    return d


# ---- writing: proposed, merged, deduplicated ----------------------------------------------------------

def test_notes_are_added_confirmed_and_merged():
    store, notes = notes_store()
    rep = notes.apply(SKYLARK, [{"op": "add", "text": "The gate is on the trip detail screen, under Flight."}], REF)
    nid = rep.applied[0]["note"]
    assert [n.text for n in notes.list(SKYLARK)] == ["The gate is on the trip detail screen, under Flight."]
    # The same observation in other words is a confirmation, not a second note.
    rep2 = notes.apply(SKYLARK, [{"op": "add", "text": "The gate shows on the trip detail screen under the Flight section."}], {**REF, "task_id": "t2"})
    assert rep2.applied[0]["op"] == "confirm" and rep2.applied[0].get("merged")
    notes.apply(SKYLARK, [{"op": "confirm", "note_id": nid}], {**REF, "task_id": "t3"})
    n = notes.get(nid)
    assert n is not None and n.confirmations == 3 and len(notes.list(SKYLARK)) == 1
    assert {s["task_id"] for s in n.sources} == {"t1", "t2", "t3"} and n.last_confirmed >= n.first_seen


def test_update_keeps_history_and_retire_hides_it():
    store, notes = notes_store()
    nid = notes.add(SKYLARK, "Check-in is under the Trips tab.", REF)
    notes.apply(SKYLARK, [{"op": "update", "note_id": nid, "text": "Check-in is on the trip detail screen, not the Trips tab."}], REF)
    assert notes.get(nid).text.startswith("Check-in is on the trip detail")  # type: ignore[union-attr]
    assert [f["value"] for f in store.history(nid, "text")][0] == "Check-in is under the Trips tab."
    notes.apply(SKYLARK, [{"op": "retire", "note_id": nid}], REF)
    assert notes.list(SKYLARK) == [] and notes.list(SKYLARK, include_retired=True)[0].status == "retired"
    assert notes.for_prompt(SKYLARK).text == ""
    # An operation on a note of another app (or one that doesn't exist) is dropped.
    other = notes.add(STARBUCKS, "A store must be chosen before prices show.", REF)
    rep = notes.apply(SKYLARK, [{"op": "retire", "note_id": other}], REF)
    assert rep.dropped and notes.get(other).status == "active"  # type: ignore[union-attr]


# ---- personal data ---------------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Your gate is B12 on the trip detail screen.",
    "Confirmation KX7Q2M is listed first.",
    "The flight departs at 6:10 AM from the home screen.",
    "Trips on Oct 30 appear at the top.",
    "Deliveries go to 1 Hacker Way Road by default.",
    "Email maya.patel@example.com appears on the profile.",
    "The latte costs $5.45 after a store is chosen.",
    "The account shows 38240 miles on the home screen.",
])
def test_personal_and_run_data_is_never_kept(text):
    assert personal_reason(text) is not None


def test_values_from_memory_and_the_run_are_filtered():
    store, notes = notes_store()
    p = store.create_entity("Person", "Maya Patel")
    store.observe(p, "name", "Maya Patel", source=None)
    rep = notes.apply(SKYLARK, [{"op": "add", "text": "The greeting on the home screen says Maya Patel."},
                                {"op": "add", "text": "The Chicago trip is listed above the others."},
                                {"op": "add", "text": "Past trips are listed under Trip history in the Profile tab."}], REF, forbidden={"Chicago"})
    assert [a["text"] for a in rep.applied] == ["Past trips are listed under Trip history in the Profile tab."]
    assert [d["text"][:12] for d in rep.dropped] == ["The greeting", "The Chicago "]


def test_the_cap_holds():
    store = MemoryStore(":memory:")
    notes = AppNotes(store, max_per_app=3)
    texts = ["Search sits at the top of the Order tab.", "Menu categories scroll sideways above the list.",
             "Rewards live behind the star icon.", "Store hours appear on the store detail sheet.", "The cart icon sits bottom right."]
    for i, t in enumerate(texts):
        nid = notes.add(STARBUCKS, t, {**REF, "task_id": f"t{i}"})
        if i == 0:
            notes.confirm(nid, {**REF, "task_id": "again"})  # the most confirmed survives
        notes.enforce_cap(STARBUCKS)
    kept = [n.text for n in notes.list(STARBUCKS)]
    assert len(kept) == 3 and texts[0] in kept


# ---- reading ---------------------------------------------------------------------------------------

def test_prompts_get_the_right_apps_notes_only():
    store, notes = notes_store()
    notes.add(SKYLARK, "The gate is on the trip detail screen, under Flight.", REF)
    notes.add(STARBUCKS, "A store must be chosen before prices show.", REF)
    sky = notes.for_prompt(SKYLARK)
    assert "trip detail" in sky.text and "store" not in sky.text and len(sky.ids) == 1
    assert notes.for_prompt("com.dd.doordash").text == ""
    assert "APP NOTES" in step_input("g", "s", app_notes=sky.text) and "APP NOTES" not in step_input("g", "s")
    assert "APP NOTES" in plan_input("g", "s", app_notes=sky.text) and "APP NOTES" in repair_input("g", "st", "", "", "s", app_notes=sky.text)


def test_notes_switch_off(monkeypatch):
    store, notes = notes_store()
    notes.add(SKYLARK, "The gate is on the trip detail screen, under Flight.", REF)
    monkeypatch.setenv("ENVOY_APP_NOTES", "off")
    assert notes.for_prompt(SKYLARK).text == ""


class OneScreenDevice:
    def __init__(self, package: str) -> None:
        xml = (SCREENS / "skylark_trip.xml").read_text()
        self.state = build_state(xml, package, f"{package}.MainActivity", 1080, 2400)

    async def wait_until_settled(self, *a, **k):
        return self.state

    async def observe(self, *a, **k):
        return self.state

    async def act(self, action):
        return ActionResult(ok=True)


class StepAdapter:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def call(self, job, content, **kw):
        text = content[0]["text"] if isinstance(content, list) else content
        self.prompts.append(text)
        if job == "plan":
            parsed = Plan.model_validate({"app": SKYLARK, "subgoals": ["read the gate"], "success_check": {"kind": "info", "value": "", "field_hint": ""}})
        else:
            parsed = StepOutput.model_validate({"reason": "r", "action": {"type": "done", "result": "Gate B12"}, "expected_result": "x", "risk": "read"})
        return SimpleNamespace(parsed=parsed, cost_usd=0.001, cost_at_standard_usd=0.001, usage={})


def test_the_agent_reads_notes_for_the_app_on_screen_and_records_them(tmp_path, monkeypatch):
    monkeypatch.setattr("agent.trace.RUNS", tmp_path)
    store, notes = notes_store()
    sky = notes.add(SKYLARK, "The gate is on the trip detail screen, under Flight.", REF)
    notes.add(STARBUCKS, "A store must be chosen before prices show.", REF)
    adapter = StepAdapter()
    runner = AgentRunner(OneScreenDevice(SKYLARK), adapter, ScriptedApprover(approve=False), RunConfig(), app_notes=notes)  # type: ignore[arg-type]
    res = asyncio.run(runner.run("What gate does my Chicago flight leave from?", task_id="notes-run"))
    assert res.status == "done"
    assert all("trip detail screen" in p and "store must be chosen" not in p for p in adapter.prompts)
    steps = [json.loads(l) for l in (Path(res.trace_dir) / "steps.jsonl").read_text().splitlines()]
    assert all(s.get("app_notes") == [sky] for s in steps if s["kind"] in ("plan", "action"))
    # Without notes, the prompt has no APP NOTES section at all.
    bare = StepAdapter()
    asyncio.run(AgentRunner(OneScreenDevice(SKYLARK), bare, ScriptedApprover(approve=False), RunConfig()).run("gate?", task_id="bare-run"))  # type: ignore[arg-type]
    assert all("APP NOTES" not in p for p in bare.prompts)


# ---- not facts about you ----------------------------------------------------------------------------

def test_notes_never_appear_in_memory_answers():
    store, notes = notes_store()
    notes.add(SKYLARK, "The gate is on the trip detail screen, under Flight.", REF)
    f = store.create_entity("Flight", "SL 482")
    store.observe(f, "number", "SL 482", source=store.add_source("app_screen", {"app": SKYLARK}))
    store.observe(f, "gate", "B12", source=store.add_source("app_screen", {"app": SKYLARK}))
    md = Retriever(store).notes("what's my gate on the trip detail screen in SkyLark").markdown
    assert "trip detail" not in md and NOTE_TYPE not in md and "B12" in md
    assert store.entities(NOTE_TYPE)


def test_a_note_change_is_not_a_change_alert():
    from api.alerts import ChangeAlerts
    from api.store import TaskStore
    store, notes = notes_store()
    tasks = TaskStore(":memory:")
    alerts = ChangeAlerts(tasks, store, SimpleNamespace(notify=lambda *a, **k: []), SimpleNamespace(publish=lambda *a, **k: None), flush_after_s=None)
    store.subscribe(alerts.on_memory)
    nid = notes.add(SKYLARK, "Check-in is under the Trips tab.", REF)
    notes.update(nid, "Check-in is on the trip detail screen.", REF)
    assert alerts.pending == {}  # the update came from a task's trace, so without the type check it would wait to be pushed
    assert tasks.db.execute("select count(*) from change_alerts").fetchone()[0] == 0


# ---- learning from a trace --------------------------------------------------------------------------

def test_learn_reads_the_trace_and_writes_filtered_notes(tmp_path):
    store = MemoryStore(":memory:")
    adapter = NotesAdapter([{"op": "add", "text": "The gate is on the trip detail screen, under Flight.", "step": 1},
                            {"op": "add", "text": "Gate B12 is shown for the Chicago trip.", "step": 2}])
    notes = AppNotes(store, adapter)  # type: ignore[arg-type]
    trace = write_trace(tmp_path)
    rep = asyncio.run(notes.learn(trace, task_id="task-9", data_scope="test_app", contributor=True))
    assert rep.app == SKYLARK and rep.model_calls == 1 and len(rep.applied) == 1 and len(rep.dropped) == 1
    n = notes.list(SKYLARK)[0]
    assert n.sources[0]["task_id"] == "task-9" and n.sources[0]["screenshot"].endswith("001_before.png") and n.sources[0]["step"] == 1
    call = adapter.calls[0]
    assert call["job"] == "app_note" and call["data_scope"] == "test_app" and call["contributor"] is True
    assert "My trips" in call["content"] and "LAST SCREEN" in call["content"]


def test_real_app_traces_never_go_to_the_contributor_tier(tmp_path):
    adapter = NotesAdapter([])
    notes = AppNotes(MemoryStore(":memory:"), adapter)  # type: ignore[arg-type]
    asyncio.run(notes.learn(write_trace(tmp_path, STARBUCKS), data_scope="real", contributor=True))
    assert adapter.calls[0]["contributor"] is False and adapter.calls[0]["data_scope"] == "real"
    # And the adapter itself refuses a real-data Contributor call.
    from models.adapter import ContributorNotAllowed, CostMeter, ModelAdapter
    with pytest.raises(ContributorNotAllowed):
        ModelAdapter(api_key="x", meter=CostMeter(path=tmp_path / "c.jsonl")).build_request("app_note", "x", data_scope="real", contributor=True)


def test_learn_does_nothing_when_off(tmp_path, monkeypatch):
    monkeypatch.setenv("ENVOY_APP_NOTES", "off")
    adapter = NotesAdapter([{"op": "add", "text": "The gate is on the trip detail screen, under Flight."}])
    rep = asyncio.run(AppNotes(MemoryStore(":memory:"), adapter).learn(write_trace(tmp_path)))  # type: ignore[arg-type]
    assert rep.skipped and not adapter.calls


def test_read_trace_marks_routine_repairs(tmp_path):
    d = tmp_path / "r"
    d.mkdir()
    (d / "steps.jsonl").write_text(json.dumps({"kind": "routine_step", "step": 3, "id": "select_recent_search_result", "status": "repaired", "rung": 4,
                                               "repairs": [{"model": True, "decision": {"reason": "type the drink name", "action": {"type": "type"}},
                                                            "target": "Search", "screen_before": {"package": STARBUCKS, "compact": "App: x · Screen: Search\n[1] Text \"Recent\""}}]}) + "\n")
    t = read_trace(d)
    assert t["kind"] == "routine" and t["app"] == STARBUCKS and "repair:" in t["text"]


def test_ui_words_from_the_answer_are_not_mistaken_for_run_data():
    from memory.app_notes import run_names
    names = run_names("Check me in for my flight to Chicago.", "Checked in. Status: On time", app=SKYLARK)
    assert names == {"Chicago"}
    assert personal_reason("Tapping a trip opens details with the Check in button and the flight status.", set(), names) is None
    assert personal_reason("The Chicago trip is listed first.", set(), names) is not None
