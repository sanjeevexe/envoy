"""Offline tests for the routine detail view (api/routine_view.py and its read-only endpoints): a routine compiled from an
agent run, repaired by a local repair (a version on trial that becomes active), then a second repair whose trial fails
(rolled back). No phone and no model."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from api.routine_view import detail, evidence_path
from api.store import TaskStore
from memory.store import MemoryStore
from routines.executor import Patch, RunOutcome, StepRun
from routines.lifecycle import after_run, version_for_run
from routines.model import Check, Locator, Routine, Step, StepAction
from routines.store import RoutineStore

NAME = "skylark_change_seat"


def routine() -> Routine:
    title = Locator(resource_id="screen_title", text="My Trips", kind="Text")
    return Routine(
        routine=NAME, app="com.skylark.air", intent="Change my seat", compiled_from={"task_id": "src-1", "cost_usd": 0.04},
        steps=[
            Step(id="open_trips", intent="Open My Trips", pre=[Check(kind="app_foreground", package="com.skylark.air")],
                 action=StepAction(kind="tap", target=Locator(resource_id="nav_trips", text="My Trips", kind="Button")),
                 post=[Check(kind="screen_changed"), Check(kind="element_present", locator=title)], risk="reversible"),
            Step(id="tap_change_seat", intent="Tap Change seat",
                 action=StepAction(kind="tap", target=Locator(resource_id="btn_change_seat", text="Change seat", kind="Button")),
                 post=[Check(kind="text_visible", text="Choose a seat")], risk="reversible"),
            Step(id="confirm", intent="Confirm the seat", action=StepAction(kind="tap", target=Locator(text="Confirm", kind="Button")),
                 post=[Check(kind="text_visible", text="Seat changed")], risk="irreversible"),
        ])


def outcome(r: Routine, task_id: str, *, calls: int = 0, rung: int = 0, status: str = "done", patches: list[Patch] | None = None) -> RunOutcome:
    return RunOutcome(routine=NAME, version=r.version, task_id=task_id, status=status, model_calls=calls, duration_s=2.5,  # type: ignore[arg-type]
                      steps=[StepRun(id="tap_change_seat", status="done", rung=rung)], patches=patches or [])


@pytest.fixture()
def library(tmp_path):
    store = RoutineStore(tmp_path / "routines")
    runs = tmp_path / "runs"
    (runs / "src-1").mkdir(parents=True)
    (runs / "src-1" / "run.json").write_text(json.dumps({"goal": "Change my seat to 21C", "status": "done", "steps": 3, "model_calls": 5,
                                                         "duration_s": 12.0, "cost_at_standard_usd": 0.01}))
    tasks = TaskStore(":memory:")
    t1 = tasks.create("Change my seat", "web")
    tasks.update(t1["id"], device="envoy-test")
    shots = []
    for n in ("before", "after"):
        p = tmp_path / f"repair_04_1_{n}.png"
        Image.new("RGB", (4, 8)).save(p)
        shots.append(str(p))

    store.add(routine(), verification={"cases": [{"case": "same-inputs", "passed": True, "duration_s": 1.5, "inputs": {}}]})
    # Run 1 (v1): the button was renamed; a local repair (one model call) finds it, and the fix goes on trial as v2.
    seats = Locator(resource_id="btn_change_seat", text="Seats", alt_texts=["Change seat"], kind="Button")
    fix = Patch("locator", "tap_change_seat", "step 'tap_change_seat': the element moved or changed; new locator {text='Seats'}",
                locator=seats, evidence={"reasons": ["Seats is the renamed Change seat"], "screenshots": shots})
    v1 = version_for_run(store, NAME)
    assert after_run(store, v1, outcome(v1, f"{t1['id']}-r1", calls=1, rung=4, patches=[fix])) == {"proposed": 2, "changes": [fix.description]}
    # Run 2 runs the trial on its own: v2 becomes active.
    v2 = version_for_run(store, NAME)
    assert after_run(store, v2, outcome(v2, "eval-2")) == {"trial": 2, "result": "activated"}
    # Run 3 (v2): an after-check matched only relaxed (no model call): v3 on trial ...
    check = Patch("check", "open_trips", "step 'open_trips': after-check 1 matched only relaxed; updated to {text='Trips'}", check_index=1,
                  check=Check(kind="element_present", locator=Locator(resource_id="screen_title", text="Trips", kind="Text")))
    v2 = version_for_run(store, NAME)
    assert after_run(store, v2, outcome(v2, "eval-3", rung=2, patches=[check]))["proposed"] == 3
    # ... and run 4 needs help again, so v3 is rolled back and v2 stays active.
    v3 = version_for_run(store, NAME)
    assert after_run(store, v3, outcome(v3, "eval-4", calls=2, rung=5, status="failed")) == {"trial": 3, "result": "rejected"}
    return store, tasks, runs, t1["id"]


def test_versions_show_what_each_patch_changed_and_its_fate(library):
    store, tasks, runs, _ = library
    d = detail(store, NAME, tasks, runs)
    assert d["active"] == 2 and d["trial"] is None
    v1, v2, v3 = d["versions"]
    assert (v1["status"], v1["origin"], v1["replaced_by"]) == ("retired", "compiled", 2)
    assert v1["compiled"]["source"] == {"task_id": "src-1", "goal": "Change my seat to 21C", "status": "done", "steps": 3, "model_calls": 5,
                                        "duration_s": 12.0, "usd": 0.01}
    assert v1["compiled"]["verification"][0]["passed"] is True

    assert (v2["status"], v2["origin"], v2["trial"]["passed"]) == ("active", "repaired", True)
    assert v2["repair"]["how"] == "local repair" and v2["repair"]["model_calls"] == 1
    (change,) = v2["changes"]
    assert change["kind"] == "locator" and change["step"] == "tap_change_seat"
    assert change["before"]["text"] == "Change seat" and change["after"]["text"] == "Seats" and change["after"]["alt_texts"] == ["Change seat"]
    assert change["reasons"] == ["Seats is the renamed Change seat"] and "local repair" in change["why"]
    assert [set(s) for s in v2["shots"]] == [{"label", "before", "after"}] and v2["shots"][0]["label"] == "screen 4"

    assert (v3["status"], v3["trial"]["passed"], v3["trial"]["model_calls"]) == ("rejected", False, 2)
    (check,) = v3["changes"]
    assert check["what"] == "After-check 2" and check["before"]["text"] == "Shows “My Trips” text" and check["after"]["text"] == "Shows “Trips” text"
    assert "relaxed threshold" in check["why"]


def test_steps_are_the_active_version_with_their_repairs_marked(library):
    store, tasks, runs, _ = library
    steps = {s["id"]: s for s in detail(store, NAME, tasks, runs)["steps"]}
    assert steps["tap_change_seat"]["action"]["target"]["text"] == "Seats"  # v2, not the rolled-back v3
    assert steps["tap_change_seat"]["changed_in"] == [{"version": 2, "kind": "locator"}]
    assert steps["open_trips"]["changed_in"] == []
    assert steps["open_trips"]["pre"][0]["text"] == "The app com.skylark.air is in front"
    assert [c["text"] for c in steps["open_trips"]["post"]] == ["The screen changed", "Shows “My Trips” text"]
    assert steps["confirm"]["risk"] == "irreversible" and steps["confirm"]["optional"] is False


def test_runs_are_measured_against_the_agent_run(library):
    store, tasks, runs, tid = library
    d = detail(store, NAME, tasks, runs)
    first, trial, third, failed = d["runs"]
    assert first["device"] == "envoy-test" and first["app_task"] == tid  # the phone comes from the API's task
    assert first["event"] == {"kind": "repaired", "version": 2} and trial["event"] == {"kind": "trial", "version": 2, "passed": True}
    assert first["usd"] == 0.002 and first["usd_estimated"]  # 1 call at the agent run's $0.002 per call
    assert first["saved"] == {"calls": 4, "seconds": 9.5, "usd": 0.008}
    assert trial["saved"] == {"calls": 5, "seconds": 9.5, "usd": 0.01} and trial["device"] is None
    assert failed["ok"] is False and failed["saved"] is None
    s = d["savings"]
    assert (s["runs"], s["finished"], s["failed"], s["model_calls"]) == (4, 3, 1, 3)
    assert s["saved"] == {"calls": 14, "seconds": 28.5, "usd": 0.028} and s["compile_usd"] == 0.04 and s["net_usd"] == -0.012
    assert s["paid_back_after"] is None


@pytest.fixture()
def client(library, tmp_path, monkeypatch):
    store, tasks, runs, _ = library
    monkeypatch.setenv("MCP_BEARER_TOKEN", "mcp-test-token")
    monkeypatch.setenv("ENVOY_ALLOWED_HOSTS", "testserver")
    monkeypatch.setattr("api.app.API_DIR", tmp_path)
    monkeypatch.setattr("api.push.LOG", tmp_path / "push.jsonl")
    monkeypatch.setattr("api.routine_view.RUNS", runs)
    from api.app import build, session_token
    _, ctx = build("demo", memory=MemoryStore(":memory:"), tasks=tasks, routines=store, adapter=SimpleNamespace())
    with TestClient(ctx.asgi) as c:
        yield c, {"Authorization": f"Bearer {session_token()}"}


def test_detail_endpoint_is_read_only_and_needs_a_session(client):
    c, me = client
    assert c.get(f"/api/routines/{NAME}/detail").status_code == 401
    r = c.get(f"/api/routines/{NAME}/detail", headers=me)
    assert r.status_code == 200 and [v["status"] for v in r.json()["versions"]] == ["retired", "active", "rejected"]
    assert r.json()["savings"]["source"]["model_calls"] == 5  # the agent run, read from the traces
    assert c.get("/api/routines/nope/detail", headers=me).status_code == 404
    assert c.post(f"/api/routines/{NAME}/detail", headers={**me, "X-Envoy": "1"}).status_code == 405


def test_only_listed_repair_screenshots_are_served(client, library):
    c, me = client
    store = library[0]
    url = detail(store, NAME, None, library[2])["versions"][1]["shots"][0]["before"]
    assert c.get(url).status_code == 401
    r = c.get(url, headers=me)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    for bad in ("index.json", "patches.json", "..%2Findex.json", "repair_09_1_before.png"):
        assert c.get(f"/api/routines/{NAME}/history/2/{bad}", headers=me).status_code == 404
    assert evidence_path(store, "../routines", 2, "repair_04_1_before.png") is None
    assert evidence_path(store, NAME, 3, "repair_04_1_before.png") is None  # listed for v2 only
