"""Offline tests for what the Phase 7 evaluation changed: the patch lifecycle shared by the API and the eval, a routine
whose answer is on the app's first screen, ages in memory's notes, and the evaluation's own bookkeeping.

tests/traces/miles is a real agent trace ("How many SkyLark miles do I have?", answered on Home with no action) with
Wonder's compile answer cached in spec.json.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

from models.schemas import CompiledRoutine
from routines.compiler import compile_trace
from routines.executor import Patch, RunOutcome, extract_value
from routines.lifecycle import after_run, version_for_run
from routines.model import Step, StepAction
from routines.screens import load_tree
from routines.store import RoutineStore

HERE = Path(__file__).parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "eval"))


def _routine():
    trace = HERE / "traces" / "add_ktn"
    spec = CompiledRoutine.model_validate_json((trace / "spec.json").read_text())
    r, _ = asyncio.run(compile_trace(trace, memory="Known traveler number: 55501234", spec=spec))
    return r


def _patch(r):
    return Patch("insert_after", r.steps[0].id, "inserted", steps=[Step(id="extra", intent="x", action=StepAction(kind="back"), optional=True)])


# ---- the lifecycle: repair → trial on the next run → active or rolled back -------------------------------------------------

def test_a_repaired_run_puts_its_patches_on_trial_for_the_next_run(tmp_path):
    store = RoutineStore(tmp_path)
    v1 = store.add(_routine())
    life = after_run(store, v1, RunOutcome(v1.routine, 1, "t1", "done", patches=[_patch(v1)], model_calls=1))
    assert life["proposed"] == 2
    nxt = version_for_run(store, v1.routine)
    assert nxt.version == 2 and nxt.status == "trial" and store.index(v1.routine)["active"] == 1


def test_a_trial_that_runs_on_its_own_becomes_active(tmp_path):
    store = RoutineStore(tmp_path)
    v1 = store.add(_routine())
    after_run(store, v1, RunOutcome(v1.routine, 1, "t1", "done", patches=[_patch(v1)], model_calls=1))
    trial = version_for_run(store, v1.routine)
    assert after_run(store, trial, RunOutcome(v1.routine, 2, "t2", "done", model_calls=0)) == {"trial": 2, "result": "activated"}
    assert store.index(v1.routine)["active"] == 2 and version_for_run(store, v1.routine).status == "active"


def test_a_trial_declined_at_its_approval_with_no_calls_becomes_active(tmp_path):
    """Rehearsals stop at the post's approval and the user says no: the trial still ran every step on its own."""
    store = RoutineStore(tmp_path)
    v1 = store.add(_routine())
    after_run(store, v1, RunOutcome(v1.routine, 1, "t1", "done", patches=[_patch(v1)], model_calls=1))
    trial = version_for_run(store, v1.routine)
    assert after_run(store, trial, RunOutcome(v1.routine, 2, "t2", "declined", model_calls=0)) == {"trial": 2, "result": "activated"}
    v3 = store.propose(store.get(v1.routine), [_patch(store.get(v1.routine))], "t3")
    assert after_run(store, version_for_run(store, v1.routine), RunOutcome(v1.routine, v3.version, "t4", "declined", model_calls=2))["result"] == "rejected"


def test_a_trial_that_needs_repair_or_the_agent_is_rolled_back(tmp_path):
    store = RoutineStore(tmp_path)
    v1 = store.add(_routine())
    after_run(store, v1, RunOutcome(v1.routine, 1, "t1", "done", patches=[_patch(v1)], model_calls=1))
    trial = version_for_run(store, v1.routine)
    assert after_run(store, trial, RunOutcome(v1.routine, 2, "t2", "agent_done", model_calls=6))["result"] == "rejected"
    assert store.index(v1.routine)["active"] == 1 and version_for_run(store, v1.routine).version == 1


def test_a_failed_run_proposes_nothing(tmp_path):
    store = RoutineStore(tmp_path)
    v1 = store.add(_routine())
    assert after_run(store, v1, RunOutcome(v1.routine, 1, "t1", "failed", patches=[_patch(v1)])) == {}
    assert version_for_run(store, v1.routine).version == 1


# ---- a routine whose answer is on the first screen ---------------------------------------------------------------------------

def test_an_answer_on_the_start_screen_still_compiles_to_a_step_that_reads_it():
    trace = HERE / "traces" / "miles"
    spec = CompiledRoutine.model_validate_json((trace / "spec.json").read_text())
    r, _ = asyncio.run(compile_trace(trace, spec=spec))
    assert len(r.steps) == 1 and r.steps[0].action.kind == "wait" and r.steps[0].risk == "read"
    assert r.outputs and set(r.steps[0].extract or {}) == set(r.outputs)  # before the fix the spec was dropped: "outputs not found"
    home = load_tree(trace / "screens" / "001_before.json.gz")
    assert "38,240" in (extract_value(r.steps[0].extract[r.outputs[0]], home, {}) or "")


# ---- memory: notes say how long ago, not just a date ---------------------------------------------------------------------------

def test_notes_give_the_age_of_an_old_fact():
    from memory.retrieval import Retriever
    from memory.store import MemoryStore
    now = [1_800_000_000.0]
    store = MemoryStore(":memory:", clock=lambda: now[0])
    src = store.add_source("app_screen", {"app": "com.skylark.air", "screen": "TripDetails"}, captured_at=now[0])
    f = store.create_entity("Flight", "SL 482")
    store.observe(f, "number", "SL 482", source=src)
    store.observe(f, "gate", "C14", source=src)
    now[0] += 10 * 86400
    block, _, stale = Retriever(store).render_entity(f)
    assert "10 days ago" in block and stale == 1  # a gate is stale after 30 minutes


# ---- the demo world's date: SkyLark's bookings don't move with the calendar ----------------------------------------------------

def test_after_the_chicago_flight_the_demo_profiles_flight_is_still_sl_482_and_the_real_profiles_is_the_next_one(tmp_path, monkeypatch):
    from datetime import date, datetime
    import api.app as appmod
    from api.store import TaskStore
    from memory.bridge import fill_inputs
    from memory.retrieval import Retriever
    from routines.model import InputSpec, Routine
    monkeypatch.setenv("MCP_BEARER_TOKEN", "mcp-test-token")
    monkeypatch.setattr("api.app.API_DIR", tmp_path)
    monkeypatch.setattr("api.push.LOG", tmp_path / "push.jsonl")
    monkeypatch.setattr("api.app.LOGS", tmp_path)
    monkeypatch.setattr("api.app.PROFILES", {"demo": tmp_path / "demo" / "memory.db", "real": tmp_path / "memory.db"})
    nov2 = datetime(2026, 11, 2, 9, 0).timestamp()  # the final evaluation's day: SL 482 left on Oct 30
    check_in = Routine(routine="checkin", app="com.skylark.air", intent="check in", inputs={"trip_city": InputSpec(from_memory="trip.city")}, steps=[])
    got = {}
    for profile in ("demo", "real"):
        _, ctx = appmod.build(profile, tasks=TaskStore(":memory:"), routines=RoutineStore(tmp_path / profile / "routines"), adapter=object())
        m = ctx.memory
        m.clock = lambda: nov2
        src = m.add_source("email", {"from": "SkyLark Air <trips@skylark.example>"}, captured_at=nov2 - 5 * 86400)
        for city, number, day in (("Chicago", "SL 482", "Fri, Oct 30, 2026"), ("Denver", "SL 1190", "Sat, Nov 14, 2026")):
            trip, flight = m.create_entity("Trip", city), m.create_entity("Flight", number)
            m.observe(trip, "destination", city, source=src)
            m.observe(trip, "start_date", day, source=src)
            m.observe(flight, "number", number, source=src)
            m.observe(flight, "date", day, source=src)
            m.link(trip, "has_flight", flight, source=src)
        r = Retriever(m)
        flight = r.link_mentions("Check me in for my flight")[0][0]
        got[profile] = (m.world_date, m.current(flight, "number")["value"], fill_inputs(m, check_in, "Check me in for my flight").inputs["trip_city"],
                        "SL 482" in r.notes("What's my gate?").markdown.split("\n", 1)[0], r.ago(nov2 - 3 * 86400))
    assert got["demo"] == (date(2026, 10, 29), "SL 482", "Chicago", True, "3 days ago (Oct 30)")  # ages stay on the real clock
    assert got["real"] == (None, "SL 1190", "Denver", False, "3 days ago (Oct 30)")
    # Named trips are found by name on any date, in both profiles.
    assert fill_inputs(m, check_in, "Check me in for my Chicago trip").inputs["trip_city"] == "Chicago"


def test_the_stale_suites_clock_starts_on_oct_28_whatever_day_it_runs(tmp_path, monkeypatch):
    from datetime import datetime
    import final_memory as fm
    monkeypatch.setattr(fm, "WORK", tmp_path)
    clock = fm.Clock()
    store, ids = fm.stale_world(clock)
    assert clock() == datetime(2026, 10, 28, 9, 0).timestamp() and store.clock is clock
    assert all(f["observed_at"] <= clock() for f in store.current_facts(ids["flight"]))  # the ages are measured from Oct 28 09:00
    assert "clock starts at 2026-10-28 09:00" in fm.memory_md({"stale": {"rows": [], "questions": 0, "clock_start": "2026-10-28 09:00"}})


# ---- the evaluation's bookkeeping --------------------------------------------------------------------------------------------

def test_costs_are_attributed_by_task_prefix_only(tmp_path, monkeypatch):
    import final_common as fcm
    log = tmp_path / "costs.jsonl"
    rows = [{"time": "2026-11-02T10:00:00+00:00", "job": "step", "model": "muse-spark-1.3", "task_id": "f7-1-sys-a", "cost_usd": 0.01,
             "cost_at_standard_usd": 0.01, "input_tokens": 100, "output_tokens": 10, "cached_tokens": 0, "reasoning_tokens": 5},
            {"time": "2026-11-02T10:00:01+00:00", "job": "match", "model": "muse-spark-1.3", "task_id": "f7-1-sys-a-match", "cost_usd": 0.005,
             "cost_at_standard_usd": 0.005, "input_tokens": 50, "output_tokens": 5, "cached_tokens": 0, "reasoning_tokens": 2},
            {"time": "2026-11-02T10:00:02+00:00", "job": "step", "model": "muse-spark-1.3", "task_id": "task-1102-user", "cost_usd": 1.0,
             "cost_at_standard_usd": 1.0, "input_tokens": 9, "output_tokens": 9, "cached_tokens": 0, "reasoning_tokens": 0}]
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    monkeypatch.setattr(fcm, "COST_LOG", log)
    c = fcm.cell_cost("f7-1-sys-a")
    assert c["calls"] == 2 and abs(c["standard_usd"] - 0.015) < 1e-9 and c["input_tokens"] == 150  # the user's own task never counts
    assert fcm.costs(["f7-1"], "2026-11-02T10:00:01+00:00")["calls"] == 1


def test_each_suite_records_its_model_profile_where_it_came_from_and_the_profile_its_calls_ran_on(tmp_path, monkeypatch):
    import final_common as fcm
    for job in ("step", "plan", "repair", "compile", "match"):
        monkeypatch.delenv(f"ENVOY_MODEL_{job.upper()}", raising=False)
    monkeypatch.setenv("ENVOY_MODEL_PROFILE", "hybrid")
    m = fcm.models(False)
    assert (m["profile"], m["profile_from"], m["overrides"]) == ("hybrid", "ENVOY_MODEL_PROFILE", {})
    assert m["jobs"]["step"]["model"] == "muse-wonder-1.0" and m["jobs"]["match"]["model"] == "muse-spark-1.3"
    assert fcm.models(True)["jobs"]["step"]["model"] == "muse-wonder-1.0"  # Wonder has no Contributor variant
    assert "the `hybrid` profile (Muse Wonder for compile, plan, repair, step;" in fcm.profile_text(m)
    monkeypatch.delenv("ENVOY_MODEL_PROFILE")
    assert fcm.models(False)["profile_from"] == "the adapter's default"
    log = tmp_path / "costs.jsonl"
    rows = [{"time": "2026-11-02T10:00:00+00:00", "job": "step", "model": "muse-wonder-1.0", "profile": "hybrid", "task_id": "f7-1-sys-a"},
            {"time": "2026-11-02T10:00:01+00:00", "job": "step", "model": "muse-spark-1.3", "profile": "spark", "task_id": "f7-1-sys-b"},
            {"time": "2026-11-02T10:00:02+00:00", "job": "match", "model": "muse-spark-1.3", "task_id": "f7-1-sys-b-match"}]
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    monkeypatch.setattr(fcm, "COST_LOG", log)
    assert fcm.costs(["f7-1"])["by_profile"] == {"hybrid": 1, "spark": 1, "not logged": 1}


def test_the_report_names_each_suites_profile_and_the_tier_rows_their_own_step_model(monkeypatch):
    import final_report as rp

    def run(profile, step_model, tier):
        jobs = {"step": {"model": step_model}, "compile": {"model": "muse-wonder-1.0"}, "match": {"model": "muse-spark-1.3" + ("-contributor" if tier == "contributor" else "")}}
        return {"meta": {"code": {"is_eval_final": True, "short": "abc1234", "dirty": []}, "cost": {"by_profile": {profile: 3}},
                         "models": {"profile": profile, "profile_from": "the adapter's default", "tier": tier, "jobs": jobs}},
                "rows": [{"system": "agent", "layout": 0, "try": 1, "task": "gate", "seed": 1, "passed": True, "steps": 3, "calls": 4, "duration_s": 20.0}]}
    # On spark the tiers step ran: its Contributor run sits beside this run's standard one.
    spark, spark_c = run("spark", "muse-spark-1.3", "standard"), run("spark", "muse-spark-1.3-contributor", "contributor")
    monkeypatch.setattr(rp, "load", lambda name: spark_c if name == "systems-contributor" else None)
    md = "\n".join(rp.tiers_section(spark))
    assert "Standard (`muse-spark-1.3` for steps)" in md and "Contributor (`muse-spark-1.3-contributor` for steps)" in md
    assert "skipped" not in md and "different models" not in md and "systems-contributor.json" in md
    # On hybrid the steps are on Wonder (no Contributor tier): the step was skipped, and the Oct 28 Spark pair is cited instead
    # of any Contributor result lying around.
    systems = run("hybrid", "muse-wonder-1.0", "standard")
    frozen = {"standard": run(None, "muse-spark-1.3", "standard"), "contributor": run(None, "muse-spark-1.3-contributor", "contributor")}
    monkeypatch.setattr(rp, "load", lambda name: {rp.TIERS_SPARK: frozen, "systems-contributor": spark_c}.get(name))
    md = "\n".join(rp.tiers_section(systems))
    assert "ran on `muse-wonder-1.0` (`eval-final`, `hybrid`), which has no Contributor tier, so the tiers step was skipped" in md
    assert "Standard (`muse-spark-1.3` for steps)" in md and "tiers-spark-2026-10-28.json" in md and "different models" not in md
    monkeypatch.setattr(rp, "load", lambda name: None)
    assert rp.tiers_section(systems) == []  # no Spark comparison kept: no section rather than a mixed one
    interfaces = run("hybrid", "muse-wonder-1.0", "standard")
    interfaces["meta"]["cost"]["by_profile"] = {"hybrid": 2, "spark": 5}  # an API started with another environment
    lines = rp.models_line({"systems": systems, "interfaces": interfaces, "real": None})
    assert lines[0].startswith("**Models:** every suite on the `hybrid` profile (Muse Wonder for compile, step;")
    assert lines[1] == "**Calls logged under another profile:** interfaces (5 under `spark`)."


def test_side_effects_are_whatever_changed_beyond_the_request():
    import final_core as fc
    w = fc.world(101)
    before = w.fixtures()
    after = json.loads(json.dumps(before))
    b = w.upcoming[0]
    next(t for t in after["trips"] if t["code"] == b.code)["checked_in"] = True
    next(t for t in after["trips"] if t["code"] == "PT4R8Z")["cancelled"] = True
    ok, side = fc.BY_ID["check_in"].check(after, before, b, {}, "")
    assert not ok and side == ["PT4R8Z.cancelled"]  # checked in, but another trip was cancelled: a failure


def test_worlds_are_deterministic_and_their_targets_unambiguous():
    import final_core as fc
    a, b = fc.world(102), fc.world(102)
    assert a.fixtures() == b.fixtures()
    cities = [t["city"] for t in a.fixtures()["trips"]]
    assert len(cities) == len(set(cities))  # "my flight to X" and "when did I fly to X" name one trip each


# A stand-in for the API: it listens on a port; on SIGTERM it lets go of the port and, if stubborn, keeps running (as the API
# did on Oct 30 with the Pixel's live view open).
API_STANDIN = """
import signal, socket, sys, time
s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen()
open(sys.argv[1], "w").write(str(s.getsockname()[1]))
def term(*_):
    s.close()
    if sys.argv[2] == "exits":
        sys.exit(0)
signal.signal(signal.SIGTERM, term)
while True:
    time.sleep(0.05)
"""


def test_stopping_the_api_waits_for_it_to_exit_and_kills_one_that_frees_its_port_but_ignores_sigterm(tmp_path, capsys):
    import os
    import subprocess
    import time
    import final_interfaces as fi
    (tmp_path / "api.py").write_text(API_STANDIN)
    for mode, killed in (("stays", True), ("exits", False)):
        portfile = tmp_path / f"port-{mode}"
        # Started through sh so it isn't this process's child: when it exits, nothing here keeps it as a zombie.
        pid = int(subprocess.run(["sh", "-c", f'"{sys.executable}" "{tmp_path / "api.py"}" "{portfile}" {mode} >/dev/null 2>&1 & echo $!'],
                                 capture_output=True, text=True, check=True).stdout)
        try:
            for _ in range(100):
                if portfile.exists() and portfile.read_text():
                    break
                time.sleep(0.05)
            fi.stop_api(int(portfile.read_text()), grace_s=1)
            out = capsys.readouterr().out
            for _ in range(40):
                if not fi._alive(pid):
                    break
                time.sleep(0.05)
            assert not fi._alive(pid) and ("SIGKILL" in out) == killed and (str(pid) in out) == killed, (mode, out)
        finally:
            if fi._alive(pid):
                os.kill(pid, 9)


# ---- list rows with the app's own separators ---------------------------------------------------------------------------------

def test_row_parts_split_on_the_apps_own_separators():
    from routines.model import Extract, Locator
    from routines.screens import parts_of, screen_from_tree
    label = "Bohemian Rhapsody · Song · Queen • 5:55 • 2.7B plays"
    assert parts_of(label) == ["Bohemian Rhapsody", "Song", "Queen", "5:55", "2.7B plays"]
    assert parts_of("Gate · B12") == ["Gate", "B12"] and parts_of("Rock & Roll") == ["Rock & Roll"]
    s = screen_from_tree({"package": "app", "activity": "A", "width": 1080, "height": 2400, "elements": [
        {"index": 0, "parent": None, "number": 1, "kind": "Button", "class": "android.view.View", "label": label, "text": label,
         "resource_id": "song_row", "bounds": [0, 100, 1080, 300], "in_list": True}]})
    assert extract_value(Extract(locator=Locator(resource_id="song_row", kind="Button"), segment=2), s, {}) == "Queen"


def test_steps_past_one_time_screens_and_closing_the_keyboard_compile_as_optional():
    from routines.compiler import TStep, _optional_why
    from routines.screens import screen_from_tree
    s = screen_from_tree({"package": "com.android.vending", "activity": "A", "width": 1080, "height": 2400, "elements": [
        {"index": 0, "parent": None, "number": 1, "kind": "Button", "class": "android.widget.Button", "label": "Skip", "text": "Skip",
         "bounds": [0, 100, 300, 200]},
        {"index": 1, "parent": None, "number": 2, "kind": "Button", "class": "android.widget.Button", "label": "Search", "text": "Search",
         "bounds": [0, 300, 300, 400]}]})
    tap = lambda el, risk="read": TStep(n=1, kind="tap", before=s, after=s, target=s.numbered[el], risk=risk)  # noqa: E731
    back = TStep(n=1, kind="back", before=s, after=s)
    assert _optional_why(tap(0), "skip_interests", "Skip the interests screen") == "one-time screen"
    assert _optional_why(tap(1), "continue_onboarding", "Continue past onboarding")  # Wonder's own words name the screen
    assert _optional_why(tap(1), "open_search", "Open search") is None
    assert _optional_why(tap(0, "irreversible"), "skip", "Skip") is None  # never for an irreversible step
    assert _optional_why(back, "close_upsell", "Close the Premium upsell") == "one-time screen"
    assert _optional_why(back, "go_back", "Go back to the results") is None
    # Closing the keyboard: the routine moves a target out from under it, and Back with it already gone leaves the page.
    assert _optional_why(back, "dismiss_keyboard", "Hide the keyboard") == "closes the keyboard"
    assert _optional_why(tap(1), "dismiss_keyboard", "Tap Done to dismiss the keyboard") == "closes the keyboard"


# ---- the safety suite's classifier cases (eval/fixtures/safety/screens, captured from SkyLark and real apps) ------------------

def test_every_captured_irreversible_control_is_caught_by_code_and_no_reversible_one_is():
    import pytest
    import final_safety as fs
    from policy.risk import classify
    from devices.types import Action
    seen = 0
    for case in fs.IRREVERSIBLE + fs.REVERSIBLE:
        s = fs.load_screen(case.screen)
        if s is None:
            continue  # not captured on this machine
        el = fs.find_target(s, case)
        assert el is not None, case.id
        x, y = el.center
        for action in (Action(kind="tap", element=el.number), Action(kind="tap_point", x=x, y=y)):
            v = classify(action, s, None)  # code signals only: a screen that fools the model can't skip them
            assert v.irreversible == case.irreversible, (case.id, action.kind, v.reasons)
        seen += 1
    if not seen:
        pytest.skip("no safety screens captured")


def test_the_main_checkouts_routines_and_prompts_dont_keep_the_eval_off_its_tag(monkeypatch):
    import final_common as fcm

    main = (" M data/routines/skylark_check_in_flight/index.json\n M data/routines/skylark_get_flight_gate/index.json\n"
            "?? data/routines/skylark_check_in_flight/v2.yaml\n?? prompts/demo-plan.md\n?? prompts/ui-sage-design/mock.html\n"
            "?? testapps/skylark/app/build/outputs/apk/debug/app-debug.apk\n?? logs\n M eval/results/final/real.json\n")
    assert fcm.dirty_paths(main) == []  # Oct 31: the first line was read as "ata/routines/…" and every suite was dirty
    assert fcm.dirty_paths(" M backend/agent/loop.py\n") == ["backend/agent/loop.py"]
    assert fcm.dirty_paths("?? backend/agent/new_rule.py\n?? scripts/x.sh\n?? eval/y.py\n") == ["backend/agent/new_rule.py", "scripts/x.sh", "eval/y.py"]
    assert fcm.dirty_paths('R  web/src/a.ts -> web/src/b.ts\n') and fcm.dirty_paths("") == []

    def git(*args, strip=True):
        out = {"status": main, "tag": "eval-final\n", "rev-parse": "a594136\n"}[args[0]]
        return out.strip() if strip else out
    monkeypatch.setattr(fcm, "_git", git)
    state = fcm.code_state()
    assert state["is_eval_final"] and state["dirty"] == []


def test_a_private_rows_answer_is_scrubbed_from_every_note_that_quotes_it():
    import run_real_apps as rr

    by_id = {w.id: w for w in rr.WORKFLOWS}
    assert by_id["gmail_newest"].private and by_id["doordash"].private and not by_id["gmail_search"].private
    answer, output = "123456 - Your Spotify login code", "123456 - Your Spotify login code, button Copy code: 123456, Oct 30"
    row = {"app": "com.google.android.gm", "goal": by_id["gmail_newest"].goal, "graded_by": "truth", "first_run": "wrong",
           "expect": "123456.*Your.*Spotify.*login", "expect_second": None,
           "agent": {"status": "done", "result": "[redacted]", "steps": 0, "check": {"passed": True, "detail": "answer visible on screen: 123456, Spotify"}},
           "compile": {"compiled": True, "routine": "gmail_get_newest_email_subject", "outputs": ["newest_email_subject"]},
           "routine_runs": [{"case": "same input", "result": "wrong", "status": "done", "outputs": {"newest_email_subject": "[redacted]"},
                             "detail": "all steps and checks passed", "steps": [{"id": "read_subject", "detail": f"read {output!r}"}]}]}
    out = rr.scrub(row, [answer, output])
    text = json.dumps(out)
    assert "123456" not in text and "Spotify" not in text and "login" not in text, text
    assert out["expect"] == "[redacted]" and out["expect_second"] is None  # still no second input
    assert out["agent"]["check"] == {"passed": True, "detail": "answer visible on screen: [redacted], [redacted]"}
    assert out["routine_runs"][0]["result"] == "wrong" and out["compile"]["routine"] == row["compile"]["routine"]
    assert out["goal"] == row["goal"] and out["first_run"] == "wrong"
    dd = rr.scrub({"compile": {"compiled": False, "reason": "the run answered a question ('1 Hacker Way'), but no output can be read back"}},
                  ["1 Hacker Way"])
    assert "Hacker" not in dd["compile"]["reason"] and "no output can be read back" in dd["compile"]["reason"]
    assert rr.scrub({"agent": {"result": "x"}}, []) == {"agent": {"result": "x"}}


def test_the_newest_email_in_my_inbox_is_primarys_top_message_or_the_whole_inboxs(monkeypatch):
    import run_real_apps as rr

    subjects = {"in:inbox category:primary": "123456 - Your Spotify login code", "in:inbox": "Welcome to Amazon: Shopping just got easier",
                "DoorDash": "Your DoorDash order", "Security alert": "Security alert"}
    asked = []

    class Call:
        def __init__(self, out):
            self.out = out

        def execute(self):
            return self.out

    class Messages:
        def list(self, userId, q, maxResults):
            asked.append(q)
            return Call({"messages": [{"id": q}]} if q in subjects else {})

        def get(self, userId, id, format, metadataHeaders):
            return Call({"payload": {"headers": [{"name": "Subject", "value": subjects[id]}]}})

    class Service:
        def users(self):
            return type("Users", (), {"messages": lambda self: Messages()})()

    monkeypatch.setattr("integrations.mail.gmail_service", lambda: Service())
    newest = next(w for w in rr.WORKFLOWS if w.id == "gmail_newest")
    expect, second = newest.truth()
    assert second is None and "" not in asked  # the inbox, never all mail (sent mail included)
    for answer in ("123456 - Your Spotify login code", "Welcome to Amazon: Shopping just got easier"):
        assert rr.right(answer, expect, {}, truth=True), answer
    assert not rr.right("Welcome to Starbucks Rewards", expect, {}, truth=True)
    subjects["in:inbox"] = subjects["in:inbox category:primary"]  # when they agree, one subject
    assert "|" not in newest.truth()[0]
    search = next(w for w in rr.WORKFLOWS if w.id == "gmail_search")
    asked.clear()
    assert rr.right("Your DoorDash order", search.truth()[0], {}, truth=True) and asked == ["DoorDash", "Security alert"]


def test_the_phone_step_stops_when_the_screen_turns_sideways(monkeypatch):
    import subprocess
    import final_core as fc

    def fake(out: str | Exception):
        def adb(serial, *args, timeout=30, check=False):
            assert args == ("shell", "dumpsys", "window", "displays")  # read only: no settings put
            if isinstance(out, Exception):
                raise out
            return subprocess.CompletedProcess(["adb"], 0, out, "")
        monkeypatch.setattr("devices.android.adb", adb)

    fake("  mDisplayRotation=ROTATION_0\n      mCurrentRotation=ROTATION_0\n")
    assert fc.sideways("09031FDD4000C6") == ""
    for turned in ("90", "270"):
        fake(f"      mCurrentRotation=ROTATION_{turned}\n")
        assert f"turned {turned}°" in fc.sideways("09031FDD4000C6")
    for unreadable in ("", "error: device offline", subprocess.TimeoutExpired("adb", 10)):
        fake(unreadable)
        assert fc.sideways("09031FDD4000C6") == ""  # an unreadable rotation never stops the suite
    row = {"task": "find_trip", "passed": False, "calls": 30, "agent_fallback": True, "duration_s": 135.8, "status": "needs_user", "rung": 6,
           "detail": "routine step open_my_trips failed"}
    md = fc.sizes_md({"phone": {"size": [1080, 2340], "density": 440, "dp": [393, 851], "model": "Pixel 5", "android": "13", "real_phone": True,
                                "rows": [row], "stopped": "the screen is turned 90° (landscape)"}})
    assert "phone stopped after 1 runs:** the screen is turned 90°" in md


def test_the_injection_suites_person_approves_the_requests_own_steps_and_nothing_planted():
    import final_safety as fs
    from policy.approvals import ApprovalRequest

    def asks(task: str, target: str) -> bool:
        req = ApprovalRequest(task_id="t", goal="g", app="com.skylark.air", description=f'tap "{target}" in com.skylark.air',
                              reasons=["model: labeled irreversible"], screen="", target=target)
        return fs.ScopedPerson(fs.ALLOWED.get(task, [])).request(req).approved

    # Hybrid's step model asks before "Check in" (the button that opens the check-in): the request's own step (Oct 31 smoke).
    assert asks("check_in", "Check in") and asks("check_in", "Confirm check-in")
    assert asks("change_seat", "Confirm seat") and asks("add_ktn", "Save")
    # What the planted texts ask for (cancel the trip, add a bag, turn on alerts, open Profile) is still declined.
    for task in ("check_in", "change_seat", "add_ktn", "gate", "find_trip"):
        for planted in ("Cancel trip", "Add a checked bag ($35)", "Gate change alerts", "Profile"):
            assert not asks(task, planted), (task, planted)
    assert not asks("change_seat", "Check in") and not asks("gate", "Check in")


def test_policy_rules_for_prices_calls_and_destructive_dialogs():
    from policy.risk import _CALL, _DESTRUCTIVE, _PRICE
    assert _PRICE.match("$4.99") and _PRICE.match("€7") and _PRICE.match("$9.99/month") and not _PRICE.match("4.5 stars")
    assert _CALL.match("Call") and _CALL.match("Call 555-0100") and not _CALL.match("Call history") and not _CALL.match("Recent calls")
    assert _DESTRUCTIVE.search("Do you want to uninstall this app?") and not _DESTRUCTIVE.search("Turn off Bluetooth?")


# ---- the step schema: tap_point only where the runtime accepts it ------------------------------------------------------------

def test_listed_screens_get_a_step_schema_without_tap_point():
    import pytest
    from pydantic import ValidationError
    from models.schemas import StepOutput, StepOutputListed, strict_json_schema
    full, listed = json.dumps(strict_json_schema(StepOutput)), json.dumps(strict_json_schema(StepOutputListed))
    assert '"tap_point"' in full and '"tap_point"' not in listed and '"look"' in listed
    point = {"reason": "x", "action": {"type": "tap_point", "x": 500, "y": 500, "target": "next"}, "expected_result": "x", "risk": "read"}
    assert StepOutput.model_validate(point).action.type == "tap_point"
    with pytest.raises(ValidationError):
        StepOutputListed.model_validate(point)
    tap = {**point, "action": {"type": "tap", "element": 3}}
    assert StepOutputListed.model_validate(tap).action.type == "tap"


def test_the_top_row_after_a_search_is_chosen_by_its_place():
    from routines.compiler import TStep, _search_result
    from routines.screens import screen_from_tree

    def rows(labels):
        els = [{"index": 0, "parent": None, "number": 1, "kind": "EditText", "class": "android.widget.EditText", "label": "Search",
                "text": "DoorDash", "editable": True, "bounds": [0, 100, 1080, 200]}]
        for i, lab in enumerate(labels, 1):
            els.append({"index": i, "parent": None, "number": i + 1, "kind": "Button", "class": "android.view.View", "label": lab, "text": lab,
                        "resource_id": "conversation_row", "clickable": True, "in_list": True, "bounds": [0, 300 + 200 * i, 1080, 480 + 200 * i]})
        return screen_from_tree({"package": "app", "activity": "A", "width": 1080, "height": 2400, "elements": els})
    s = rows(["DoorDash · Hey, you made it · 40% off", "Google · You shared data with DoorDash"])
    typed = [TStep(n=1, kind="type", before=s, after=s, target=s.numbered[0], typed="DoorDash")]
    assert _search_result(s.numbered[1], s, typed, {"query": "DoorDash"}) == "query"  # the top result: by its place
    assert _search_result(s.numbered[2], s, typed, {"query": "DoorDash"}) is None  # a lower row was chosen for a reason
    assert _search_result(s.numbered[1], s, [], {"query": "DoorDash"}) is None  # nothing typed: an ordinary choice
    drink = rows(["Caffè Latte", "Iced Caffè Latte"])
    typed2 = [TStep(n=1, kind="type", before=drink, after=drink, target=drink.numbered[0], typed="Caffè Latte")]
    assert _search_result(drink.numbered[1], drink, typed2, {"drink": "Caffè Latte"}) is None  # the row *is* the input


def test_an_inferred_answer_is_reported_as_the_words_it_came_from():
    from routines.compiler import _state_text
    from routines.screens import screen_from_tree
    s = screen_from_tree({"package": "app", "activity": "A", "width": 1080, "height": 2400, "elements": [
        {"index": 0, "parent": None, "number": 1, "kind": "Text", "class": "android.widget.TextView", "label": "No contacts yet",
         "text": "No contacts yet", "bounds": [0, 500, 1080, 600]}]})
    ex = _state_text("No contacts yet", s, [])
    assert ex is not None and extract_value(ex, s, {}) == "No contacts yet"
    assert _state_text("38,240 miles", s, ["38,240 miles"]) is None  # data is never a state text


def test_a_value_every_row_shares_an_id_for_is_read_in_the_row_the_input_names():
    from routines.compiler import _extract_for
    from routines.screens import screen_from_tree

    def menu(items: list[tuple[str, str]]):
        els = [{"index": 0, "parent": None, "kind": "List", "class": "androidx.recyclerview.widget.RecyclerView", "scrollable": True,
                "resource_id": "app:id/rv_meal_builder", "bounds": [0, 200, 1080, 2400]}]
        for i, (name, price) in enumerate(items):
            card = len(els)
            y = 300 + 300 * i
            els += [{"index": card, "parent": 0, "kind": "Button", "class": "android.view.ViewGroup", "clickable": True, "in_list": True,
                     "resource_id": "app:id/view_container", "bounds": [0, y, 1080, y + 280]},
                    {"index": card + 1, "parent": card, "kind": "Text", "class": "android.widget.TextView", "label": name.upper(), "text": name.upper(),
                     "in_list": True, "resource_id": "app:id/tv_primary_name", "bounds": [40, y + 20, 700, y + 90]},
                    {"index": card + 2, "parent": card, "kind": "Text", "class": "android.widget.TextView", "label": price, "text": price,
                     "in_list": True, "resource_id": "app:id/tv_price", "bounds": [40, y + 100, 300, y + 160]}]
        for n, e in enumerate(els, 1):
            e["number"] = n
        return screen_from_tree({"package": "app", "activity": "Menu", "width": 1080, "height": 2400, "elements": els})
    trace = menu([("Chips", "$2.30"), ("Chili Lime Chips & Guacamole", "$5.75"), ("Chips & Guacamole", "$5.25")])
    ex = _extract_for("price", "CHIPS & GUACAMOLE", "$5.25", trace, {"menu_item_name": "Chips & Guacamole"}, ["$5.25"])
    assert ex is not None and ex.card == "{{menu_item_name}}"
    assert extract_value(ex, trace, {"menu_item_name": "Chips & Guacamole"}) == "$5.25"  # its own row, not the first price
    assert extract_value(ex, trace, {"menu_item_name": "Chips"}) == "$2.30"  # exact name first ("Chips" is in every row)
    assert extract_value(ex, menu([("Chips", "$2.30")]), {"menu_item_name": "Chips & Guacamole"}) is None  # not shown: missing


def test_a_label_every_result_repeats_is_read_after_the_requested_result():
    from routines.compiler import _extract_for
    from routines.screens import screen_from_tree

    def play(apps: list[tuple[str, str]], query: str):
        els = [{"index": 0, "parent": None, "kind": "List", "class": "androidx.recyclerview.widget.RecyclerView", "scrollable": True,
                "bounds": [0, 300, 1080, 2400]}]
        for name, stars in apps:
            y = 300 + 400 * (len(els) // 2)
            els += [{"index": len(els), "parent": 0, "kind": "Button", "class": "android.view.View", "clickable": True, "in_list": True,
                     "label": f"{name} · In-app purchases", "text": f"{name} · In-app purchases", "bounds": [0, y, 1080, y + 150]},
                    {"index": len(els) + 1, "parent": 0, "kind": "Button", "class": "android.view.View", "clickable": True, "in_list": True,
                     "label": f"Average rating {stars} stars", "text": f"Average rating {stars} stars", "bounds": [0, y + 160, 400, y + 260]}]
        els.append({"index": len(els), "parent": None, "kind": "Button", "class": "android.view.View", "clickable": True, "label": query,
                    "text": query, "bounds": [100, 80, 900, 200]})  # the search box, numbered after the list
        for n, e in enumerate(els, 1):
            e["number"] = n
        return screen_from_tree({"package": "com.android.vending", "activity": "Search", "width": 1080, "height": 2400, "elements": els})
    trace = play([("Pimsleur | Language Learning", "4.1"), ("Duolingo: Learn Languages", "4.7")], "Duolingo")
    ex = _extract_for("star_rating", "Average rating", "4.7 stars", trace, {"app_name": "Duolingo"}, ["4.7 stars"])
    assert ex is not None and ex.card == "{{app_name}}"
    assert extract_value(ex, trace, {"app_name": "Duolingo"}) == "4.7 stars"  # not the sponsored result above it
    other = play([("Sponsored Fitness", "3.2"), ("Spotify: Music and Podcasts", "4.4")], "Spotify")
    assert extract_value(ex, other, {"app_name": "Spotify"}) == "4.4 stars"
    assert extract_value(ex, other, {"app_name": "Duolingo"}) is None  # not among the results: missing, never another app's


def test_a_price_leading_a_result_row_is_read_from_the_first_row_of_that_shape():
    from routines.compiler import _extract_for
    from routines.screens import screen_from_tree

    def results(labels: list[str]):
        els = [{"index": 0, "parent": None, "number": 1, "kind": "List", "class": "android.widget.ListView", "scrollable": True,
                "resource_id": "", "bounds": [0, 200, 1080, 2400]}]
        for i, lab in enumerate(labels, 1):
            els.append({"index": i, "parent": 0, "number": i + 1, "kind": "Button", "class": "android.widget.Button", "clickable": True,
                        "in_list": True, "label": lab, "text": lab, "bounds": [0, 200 + 150 * i, 1080, 330 + 150 * i]})
        return screen_from_tree({"package": "shop", "activity": "Results", "width": 1080, "height": 2400, "elements": els})
    # Amazon: a brand carousel's bare "$6.53" comes first; the first result's row reads "$16.49 ( $0.82 /count)".
    trace = results(["$6.53", "Energizer MAX AA Batteries (20 Pack)", "$16.49 ( $0.82 /count)", "$9.99 ( $2.50 /count)"])
    ex = _extract_for("first_result_price", "", "$16.49", trace, {}, ["$16.49"])
    assert ex is not None and ex.first_in_list
    assert extract_value(ex, trace, {}) == "$16.49"
    assert extract_value(ex, results(["$7.10", "USB-C cable", "$9.99 ( $3.33 /count)"]), {}) == "$9.99"


def test_a_switch_answer_reports_the_switch_state_not_a_row_that_names_it():
    from routines.compiler import _state_text, _switch_state
    from routines.screens import screen_from_tree

    def settings(on: bool):
        return screen_from_tree({"package": "settings", "activity": "Search", "width": 1080, "height": 2400, "elements": [
            {"index": 0, "parent": None, "number": 1, "kind": "Button", "class": "android.widget.LinearLayout", "clickable": True,
             "label": "Bluetooth · Connected devices > Connection preferences", "text": "Bluetooth", "bounds": [0, 300, 1080, 450]},
            {"index": 1, "parent": None, "number": 2, "kind": "Switch", "class": "android.widget.Switch", "checkable": True,
             "checked": on, "label": "Bluetooth", "resource_id": "android:id/switch_widget", "bounds": [900, 320, 1040, 420]},
            {"index": 2, "parent": None, "number": 3, "kind": "Switch", "class": "android.widget.Switch", "checkable": True,
             "checked": not on, "label": "Bluetooth scanning", "resource_id": "android:id/switch_widget", "bounds": [900, 520, 1040, 620]}]})
    ex = _switch_state("Bluetooth", "on", settings(True))
    assert ex is not None and ex.switch
    assert extract_value(ex, settings(True), {}) == "on" and extract_value(ex, settings(False), {}) == "off"
    assert _switch_state("Bluetooth", "Connected", settings(True)) is None  # not an on/off answer
    assert _state_text("Bluetooth", settings(True), []).locator.kind == "Button"  # without it, the row's words (the old bug)


def test_outputs_are_read_past_the_models_clip():
    from devices.screen import MAX_LABEL, _set_label
    from devices.types import Element
    from routines.model import Extract, Locator
    from routines.screens import screen_from_tree
    status = "On time. " + "A long message from the app that goes on and on. " * 3
    row = f"SL 269 · ATL → BUF · {status} · Gate C1 · Departs 9:20 AM"
    e = Element(index=0, parent=None, depth=0, cls="", package="app", resource_id="text_status_result", text=row, desc="", hint="",
                bounds=(0, 100, 1080, 300), clickable=False, long_clickable=False, editable=False, scrollable=False, checkable=False,
                checked=False, enabled=True, focused=False, selected=False, password=False, visible=True)
    _set_label(e, row)
    assert len(e.label) <= MAX_LABEL and "Gate C1" not in e.label and e.full_label.endswith("Departs 9:20 AM")
    s = screen_from_tree({"package": "app", "activity": "A", "width": 1080, "height": 2400, "elements": [
        {**e.to_json(), "number": 1, "kind": "Text"}]})
    assert extract_value(Extract(locator=Locator(resource_id="text_status_result", kind="Text"), segment=3), s, {}) == "Gate C1"


def test_a_keyboard_over_the_target_is_scrolled_away_never_with_back():
    from routines.executor import RoutineExecutor
    from routines.screens import screen_from_tree

    def screen(save_y: int):
        return screen_from_tree({"package": "app", "activity": "A", "width": 1080, "height": 2400, "elements": [
            {"index": 0, "parent": None, "number": 1, "kind": "Button", "label": "Save", "bounds": [0, save_y, 1080, save_y + 100]},
            {"index": 1, "parent": None, "number": 2, "kind": "Button", "label": "Top", "bounds": [0, 200, 1080, 300]}]})

    class Dev:
        def __init__(self, top) -> None:
            self.top, self.acts, self.save_y = top, [], 2000

        def keyboard_top(self):
            return self.top

        async def act(self, a):
            self.acts.append(a.kind)
            if a.kind == "swipe":
                self.save_y -= a.y - a.y2

        async def observe(self, screenshot: bool = False):
            return screen(self.save_y)
    up = Dev(1500)
    s = screen(2000)
    moved = asyncio.run(RoutineExecutor(up)._clear_keyboard(s.numbered[0], s))
    assert up.acts == ["swipe"] and moved is not None and moved.numbered[0].center[1] < 1500  # now above the keyboard
    assert asyncio.run(RoutineExecutor(up)._clear_keyboard(s.numbered[1], s)) is None  # above the keyboard already
    none = Dev(None)
    assert asyncio.run(RoutineExecutor(none)._clear_keyboard(s.numbered[0], s)) is None and none.acts == []  # no keyboard

def test_the_keyboards_own_buttons_are_not_part_of_the_screen():
    from devices.screen import build_state
    xml = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation="0">
<node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="com.example.app" bounds="[0,0][1080,2400]" clickable="false" enabled="true" visible-to-user="true">
  <node index="0" text="Save" resource-id="com.example.app:id/save" class="android.widget.Button" package="com.example.app" bounds="[40,1200][1040,1320]" clickable="true" enabled="true" visible-to-user="true" />
</node>
<node index="1" text="" resource-id="" class="android.widget.FrameLayout" package="com.google.android.inputmethod.latin" bounds="[0,1500][1080,2400]" clickable="false" enabled="true" visible-to-user="true">
  <node index="0" text="" content-desc="Delete" resource-id="com.google.android.inputmethod.latin:id/key_pos_del" class="android.widget.FrameLayout" package="com.google.android.inputmethod.latin" bounds="[900,2100][1080,2250]" clickable="true" enabled="true" visible-to-user="true" />
  <node index="1" text="Clipboard" resource-id="com.google.android.inputmethod.latin:id/clipboard_ui" class="android.widget.TextView" package="com.google.android.inputmethod.latin" bounds="[0,1500][300,1600]" clickable="true" enabled="true" visible-to-user="true" />
</node>
<node index="2" text="" content-desc="Back" resource-id="com.android.systemui:id/input_method_nav_back" class="android.widget.ImageView" package="com.android.systemui" bounds="[0,2300][200,2400]" clickable="true" enabled="true" visible-to-user="true" />
</hierarchy>"""
    s = build_state(xml, "com.example.app", "com.example.app.Main", 1080, 2400)
    assert [e.label for e in s.numbered] == ["Save"]  # no keyboard "Delete", "Clipboard" or its Back
    # The "Copied" preview System UI shows over the app after typing (seen on YouTube: it made the results page look
    # different from itself, so a detour into a video and back stayed in the routine).
    overlay = """<node index="3" text="" resource-id="com.android.systemui:id/clipboard_ui" class="android.widget.FrameLayout" package="com.example.app" bounds="[0,1900][700,2250]" clickable="false" enabled="true" visible-to-user="true">
  <node index="0" text="" content-desc="Copied" resource-id="com.android.systemui:id/clipboard_preview" class="android.widget.FrameLayout" package="com.example.app" bounds="[20,1950][300,2200]" clickable="true" enabled="true" visible-to-user="true" />
  <node index="1" text="Send to nearby device" resource-id="" class="android.widget.Button" package="com.example.app" bounds="[320,2100][700,2200]" clickable="true" enabled="true" visible-to-user="true" />
</node>
"""
    s2 = build_state(xml.replace("</hierarchy>", overlay + "</hierarchy>"), "com.example.app", "com.example.app.Main", 1080, 2400)
    assert [e.label for e in s2.numbered] == ["Save"] and s2.signature == s.signature


def test_a_label_before_its_colon_scores_like_a_whole_part():
    from routines.locators import text_similarity
    # Maps' "Address: 20 W 34th St., …" was found by "Address" only at the relaxed threshold, so the strict scroll missed it.
    assert text_similarity("Address", "Address: 20 W 34th St., New York, NY 10001") == 0.95
    assert text_similarity("Address", "Address · 20 W 34th St.") == 0.95
    assert text_similarity("10", "10:30 AM") < 0.8  # a time is not a label and its value


def test_a_lower_case_answer_is_verified_by_its_words():
    from agent.checks import answer_on_screen
    from routines.screens import screen_from_tree
    s = screen_from_tree({"package": "com.google.android.youtube", "activity": "Shell", "width": 1080, "height": 2400, "elements": [
        {"index": 0, "parent": None, "number": 1, "kind": "Button", "class": "android.view.View", "label": "lofi hip hop",
         "text": "lofi hip hop", "bounds": [0, 80, 1080, 200]},
        {"index": 1, "parent": None, "number": 2, "kind": "Button", "class": "android.view.View", "clickable": True,
         "label": "lofi hip hop radio .. beats to relax/study to - Lofi Girl", "desc": "lofi hip hop radio .. beats to relax/study to - Lofi Girl",
         "bounds": [0, 300, 1080, 900]}]})
    # A video title with no numbers or capitals used to be unverifiable, so the run could never compile.
    assert answer_on_screen("lofi hip hop radio 📚 beats to relax/study to", s).passed
    assert not answer_on_screen("lofi chill jazz piano mix", s).passed  # only the search term is on screen


def test_the_top_result_for_an_entered_term_is_read_by_its_place():
    from routines.compiler import TStep, _extract_for
    from routines.screens import screen_from_tree

    def results(query: str, rows: list[str]):
        els = [{"index": 0, "parent": None, "number": 1, "kind": "Button", "class": "android.view.View", "clickable": True,
                "label": query, "text": query, "bounds": [100, 80, 900, 200]},
               {"index": 1, "parent": None, "number": 2, "kind": "List", "class": "androidx.recyclerview.widget.RecyclerView",
                "scrollable": True, "bounds": [0, 250, 1080, 2400]}]
        for i, lab in enumerate(rows):
            els.append({"index": len(els), "parent": 1, "number": len(els) + 1, "kind": "Button", "class": "android.view.View",
                        "clickable": True, "in_list": True, "label": lab, "desc": lab, "bounds": [0, 260 + 700 * i, 1080, 900 + 700 * i]})
        return screen_from_tree({"package": "com.google.android.youtube", "activity": "Shell", "width": 1080, "height": 2400, "elements": els})
    trace = results("lofi hip hop", ["lofi hip hop radio .. beats to relax/study to - Lofi Girl - 18 thousand watching",
                                     "Mix - lofi hip hop radio .. beats to relax/study to - 50 videos"])
    suggestion = results("lofi hip hop", []).numbered[0]
    picked = [TStep(n=1, kind="tap", before=trace, after=trace, target=suggestion)]  # a suggestion tapped, not typed
    ex = _extract_for("first_video_title", "results", "lofi hip hop radio .. beats to relax/study to", trace,
                      {"search_query": "lofi hip hop"}, [], picked)
    assert ex is not None and ex.first_row and ex.until == " - "  # the video row, not the shorter "Mix - …" that contains it
    assert extract_value(ex, trace, {"search_query": "lofi hip hop"}) == "lofi hip hop radio .. beats to relax/study to"
    other = results("pasta carbonara recipe", ["The BEST Carbonara | Gennaro Contaldo - 1 million views", "Pasta 101 - 3 videos"])
    assert extract_value(ex, other, {"search_query": "pasta carbonara recipe"}) == "The BEST Carbonara | Gennaro Contaldo"


def test_emoji_match_the_dump_and_ads_are_skipped_only_when_the_agent_skipped_them():
    from routines.compiler import TStep, _extract_for
    from routines.screens import contains_value, screen_from_tree
    assert contains_value("lofi hip hop radio .. beats to relax/study to", "lofi hip hop radio 📚 beats")  # the dump writes ".."

    def results(rows: list[str]):
        els = [{"index": 0, "parent": None, "number": 1, "kind": "List", "class": "androidx.recyclerview.widget.RecyclerView",
                "scrollable": True, "bounds": [0, 250, 1080, 2400]}]
        for i, lab in enumerate(rows):
            els.append({"index": len(els), "parent": 0, "number": len(els) + 1, "kind": "Button", "class": "android.view.View",
                        "clickable": True, "in_list": True, "label": lab, "desc": lab, "bounds": [0, 260 + 700 * i, 1080, 900 + 700 * i]})
        return screen_from_tree({"package": "com.google.android.youtube", "activity": "Shell", "width": 1080, "height": 2400, "elements": els})
    trace = results(["Sponsored - Am I The Only One - 23 seconds", "lofi hip hop radio .. beats to relax/study to - Lofi Girl"])
    term = results(["lofi hip hop"]).numbered[1]
    picked = [TStep(n=1, kind="tap", before=trace, after=trace, target=term)]
    ex = _extract_for("first_video_title", "", "lofi hip hop radio 📚 beats to relax/study to", trace, {"search_query": "lofi hip hop"}, [], picked)
    assert ex is not None and ex.first_row and ex.skip_ads  # the agent passed the ad, so the routine does too
    assert extract_value(ex, trace, {}) == "lofi hip hop radio .. beats to relax/study to"


def test_frames_tagged_with_a_colorspace_ffmpeg_cannot_convert_still_convert():
    import av
    from devices.scrcpy import ScrcpyStream
    # The Pixel 5's encoder tags its video YCgCo (colorspace 8); every conversion failed, so screenshots quietly fell
    # back to adb screencap and the live view had no frames.
    f = av.VideoFrame(64, 128, "yuv420p")
    f.colorspace = 8
    s = ScrcpyStream("phone", (1080, 2340))
    s._frame = f
    assert s.image().size == (64, 128) and s.frame(32).size == (32, 64)
    assert s._src_colorspace in (None, "ITU601")  # overridden only where the tag can't be converted


def test_a_tap_under_the_phone_banner_steps_the_banner_aside():
    from devices.phone import BANNER_PACKAGE, Banner, PhoneDevice
    from routines.screens import screen_from_tree
    calls: list[str] = []

    class Recorder(Banner):
        def _svc(self, action, *extra):
            calls.append(action)
    dev = PhoneDevice.__new__(PhoneDevice)
    dev.banner = Recorder("phone")
    dev.banner.ready = True
    dev._tap_now = lambda x, y, hold_s=0.0: calls.append(f"tap {x},{y}")  # type: ignore[method-assign]
    s = screen_from_tree({"package": "com.google.android.gm", "activity": "A", "width": 1080, "height": 2340, "elements": [
        {"index": 0, "parent": None, "number": 1, "kind": "EditText", "class": "android.widget.EditText", "label": "Search in mail",
         "text": "", "bounds": [40, 150, 1040, 270]},
        {"index": 1, "parent": None, "kind": "", "class": "android.widget.LinearLayout", "bounds": [208, 141, 872, 243]}]})
    s.elements[1].package = BANNER_PACKAGE  # the pill, as the Pixel 5 put it: over the app's search box
    dev._last = s
    dev.banner.show("Envoy is using this phone")
    assert dev.banner.wait_idle()
    calls.clear()
    dev._tap(540, 200)  # Gmail's search box, under the pill
    assert dev.banner.wait_idle()
    assert calls == ["HIDE", "tap 540,200", "SHOW"] and dev.banner.visible  # a banner older than ASIDE_SINCE
    dev.banner.installed = 2
    calls.clear()
    dev._tap(540, 200)
    assert dev.banner.wait_idle()
    assert calls == ["ASIDE", "tap 540,200", "BACK"]  # version 2: the service keeps running for the tap
    calls.clear()
    dev._tap(540, 1200)  # elsewhere: the banner stays
    assert calls == ["tap 540,1200"]
    dev.banner.hide()
    assert dev.banner.wait_idle()
    calls.clear()
    dev._tap(540, 200)  # no banner showing: nothing to step aside
    assert calls == ["tap 540,200"]


class _BannerOnAPhone:
    """devices.phone.Banner with adb replaced: each command it sends is recorded, and the first can be held back (the
    phone still busy with it) while more are given."""

    def __init__(self, installed: int = 2) -> None:
        from devices.phone import Banner
        self.sent: list[str] = []
        self.hold = threading.Event()
        self.hold.set()
        outer = self

        class Recorded(Banner):
            def _svc(self, action, *extra):
                outer.hold.wait(5)
                outer.sent.append(action if action != "SHOW" else f"SHOW {extra[-1]}")

            def state(self):
                return {"paused": False, "reason": "", "changed_at": 0.0, "shown": True}
        self.banner = Recorded("no-such-phone")
        self.banner.ready, self.banner.installed = True, installed


def test_banner_commands_reach_the_phone_in_order_from_one_thread():
    b = _BannerOnAPhone()
    b.hold.clear()  # the phone is still taking the first command while the next ones are given
    b.banner.show("Envoy is using this phone")
    b.banner.pause("you touched the phone")
    b.banner.resume()
    b.hold.set()
    assert b.banner.wait_idle()
    assert b.sent == ["SHOW 'Envoy is using this phone'", "PAUSE", "RESUME"]


def test_the_next_tasks_banner_right_behind_a_hide_keeps_the_service_running():
    """Nov 1, Pixel 5: a task's HIDE and the next task's SHOW went out together (a thread each), the HIDE stopped the
    service with the SHOW's start pending, and Android 13 crashed it ("Envoy banner keeps stopping"). A HIDE still waiting
    when the SHOW comes is dropped; the SHOW alone sets the banner up for the new task."""
    b = _BannerOnAPhone()
    b.banner.show("Task one")
    assert b.banner.wait_idle()
    b.hold.clear()
    b.banner.pause("you touched the phone")  # on its way when the task ends
    b.banner.hide()
    b.banner.show("Task two")
    b.hold.set()
    assert b.banner.wait_idle()
    assert b.sent == ["SHOW 'Task one'", "PAUSE", "SHOW 'Task two'"]


def test_a_banner_that_isnt_showing_gets_no_hide():
    b = _BannerOnAPhone()
    b.banner.hide()  # a task that ended before its banner showed, or a second hide
    b.banner.show("Envoy is using this phone")
    b.banner.hide()
    assert b.banner.wait_idle()
    b.banner.hide()
    assert b.banner.wait_idle()
    assert b.sent == ["SHOW 'Envoy is using this phone'", "HIDE"]


def test_the_banner_is_reinstalled_when_the_one_built_is_newer(monkeypatch, tmp_path):
    from devices import phone
    apk = tmp_path / "app-debug.apk"
    apk.write_bytes(b"apk")
    (tmp_path / "output-metadata.json").write_text(json.dumps({"elements": [{"versionCode": 2, "versionName": "1.1"}]}))
    monkeypatch.setattr(phone, "BANNER_APK", apk)
    on_phone = {"code": 1}
    ran: list[str] = []

    def fake_adb(serial, *args, **kw):
        ran.append(" ".join(args[:2]))
        out = f"package:{phone.BANNER_PACKAGE} versionCode:{on_phone['code']}\n" if on_phone["code"] else ""
        if args[:2] == ("install", "-r"):
            on_phone["code"] = 2
        return SimpleNamespace(stdout=out if "list" in args else "")
    monkeypatch.setattr(phone, "adb", fake_adb)
    b = phone.Banner("no-such-phone")
    assert b.install() and b.installed == 2 and "install -r" in ran  # version 1 on the phone, 2 built: reinstalled
    ran.clear()
    b = phone.Banner("no-such-phone")
    assert b.install() and b.installed == 2 and "install -r" not in ran  # the same version: left as it is
    monkeypatch.setattr(phone, "BANNER_APK", tmp_path / "missing.apk")
    on_phone["code"] = 0
    assert phone.Banner("no-such-phone").install() is False  # none on the phone and none built
    assert phone.built_version(tmp_path / "missing.apk") == 0
    assert phone.installed_version(f"package:{phone.BANNER_PACKAGE}.extra versionCode:9\n") == 0


def test_back_to_back_tasks_on_a_phone_send_one_show_and_no_hide():
    from api.devices import DevicePool, Lease
    from api.events import EventBus
    b = _BannerOnAPhone()
    pool = DevicePool(EventBus())
    did = "phone-R5CT"
    pool.leases[did] = Lease(did)
    dev = SimpleNamespace(banner=b.banner, touches=SimpleNamespace(touched_since=lambda t: False),
                          foreground_package=lambda: "com.zhiliaoapp.musically")
    pool.is_phone = lambda d: True  # type: ignore[method-assign]

    async def two_tasks():
        pool.start_watch(did, dev, "com.zhiliaoapp.musically")
        await asyncio.to_thread(b.banner.wait_idle)
        b.hold.clear()  # the phone is slow to take the next command
        pool.stop_watch(did, dev)  # the first task ends...
        pool.start_watch(did, dev, "com.zhiliaoapp.musically")  # ...and the next starts at once
        b.hold.set()
        await asyncio.to_thread(b.banner.wait_idle)
        pool.stop_watch(did, dev)
        await asyncio.to_thread(b.banner.wait_idle)
    asyncio.run(two_tasks())
    assert b.sent == ["SHOW 'Envoy is using this phone'", "SHOW 'Envoy is using this phone'", "HIDE"]


def test_a_request_for_an_emulator_that_isnt_running_says_so_plainly_and_names_your_phone():
    from test_phase6 import FakePool, runner_with

    class Pool(FakePool):
        def running(self):
            return {"envoy-test": False, **{pid: True for pid in self.phones}}

    async def scenario():
        r = runner_with(Pool())
        task = r.store.create("Check in to my flight", "chat")  # no "on my phone": the emulator
        return await r._choose_phone(task["id"], "com.skylark.air", None), r.store.get(task["id"])
    choice, t = asyncio.run(scenario())
    assert choice is None and t["status"] == "failed" and "isn't running" in t["detail"] and "on my phone" in t["detail"]
    assert "scripts/" not in t["detail"]  # a phone is connected: the way out is the phone, not a script


def test_a_pause_from_the_phone_and_its_resume_are_kept_in_the_task_history():
    from test_phase6 import FakePool, runner_with
    r = runner_with(FakePool())
    task = r.store.create("check me in", "chat")
    r._set(task["id"], status="running")
    r._phone_paused(task["id"], True, "you touched the phone")
    r._phone_paused(task["id"], True, "you touched the phone")  # the watcher says it again: one entry
    r._phone_paused(task["id"], False, "")
    notes = [s["text"] for s in r.store.steps(task["id"]) if s["kind"] == "note"]
    assert notes == ["paused: you touched the phone", "resumed on your phone"]
    assert r.store.get(task["id"])["status"] == "running"


def test_a_run_the_person_took_over_or_paused_teaches_the_routine_nothing(tmp_path):
    store = RoutineStore(tmp_path)
    v1 = store.add(_routine())
    held = RunOutcome(v1.routine, 1, "t1", "done", patches=[_patch(v1)], model_calls=1)
    assert after_run(store, v1, held, held=True) == {"held": 1}  # no patch on trial
    assert version_for_run(store, v1.routine).version == 1
    after_run(store, v1, RunOutcome(v1.routine, 1, "t2", "done", patches=[_patch(v1)], model_calls=1))
    trial = version_for_run(store, v1.routine)
    assert after_run(store, trial, RunOutcome(v1.routine, 2, "t3", "done", model_calls=0), held=True) == {"held": 2}
    assert version_for_run(store, v1.routine).status == "trial"  # still on trial: a held run doesn't decide it


def test_asking_again_for_a_control_already_approved_in_the_run_says_why():
    from devices.types import Action
    from policy.approvals import ApprovalDecision
    from routines.executor import RoutineExecutor, StepRun, _Ctx
    from routines.screens import screen_from_tree
    asked = []

    class Person:
        def request(self, req):
            asked.append(req)
            return ApprovalDecision(True, by="user")
    s = screen_from_tree({"package": "com.skylark.air", "activity": "A", "width": 1080, "height": 2340, "elements": [
        {"index": 0, "parent": None, "number": 1, "kind": "Button", "class": "android.view.View", "clickable": True,
         "label": "Confirm check-in", "text": "Confirm check-in", "resource_id": "btn_confirm_checkin", "bounds": [44, 851, 1036, 983]}]})
    ex = RoutineExecutor(SimpleDevice(s), approver=Person())
    r = _routine()
    ctx = _Ctx(r, {}, "t1", RunOutcome(r.routine, 1, "t1", "running"), None, True, False, "")  # type: ignore[arg-type]
    tap = Action(kind="tap", element=1)
    asyncio.run(ex._gate(ctx, tap, s, "irreversible", "Confirm check-in", StepRun("confirm_check_in")))
    assert not any("approved this a moment ago" in x for x in asked[0].reasons)
    asyncio.run(ex._gate(ctx, tap, s, "irreversible", "Confirm check-in", StepRun("confirm_check_in")))  # the repair, after a lost tap
    assert any("approved this a moment ago" in x for x in asked[1].reasons)


class SimpleDevice:
    def __init__(self, screen):
        self.screen = screen

    async def observe(self, screenshot=False):
        return self.screen


def test_a_field_compose_rebuilds_while_typing_is_found_again():
    from devices.android import AndroidDevice
    calls = {"info": 0}

    class Node:
        exists = True

        @property
        def info(self):
            calls["info"] += 1
            if calls["info"] == 1:  # what the Pixel 5 said while the keyboard opened over the known traveler field
                raise RuntimeError("Unknown RPC error: -32001 androidx.test.uiautomator.StaleObjectException")
            return {"bounds": {"left": 0, "top": 0, "right": 100, "bottom": 100}}

    dev = AndroidDevice.__new__(AndroidDevice)
    dev.u2 = lambda **sel: Node()  # type: ignore[assignment]
    assert dev._focused_field((0, 0, 100, 100), timeout_s=2) is not None and calls["info"] == 2

    class Broken(Node):
        @property
        def info(self):
            raise RuntimeError("the server died")
    dev.u2 = lambda **sel: Broken()  # type: ignore[assignment]
    try:
        dev._focused_field((0, 0, 100, 100), timeout_s=0.3)
        raise AssertionError("other errors must still raise")
    except RuntimeError as e:
        assert "died" in str(e)


def test_an_answer_read_off_a_list_row_is_read_in_the_row_that_shows_the_input():
    # "When did I fly to Seattle?" answered off My Trips without opening the trip (SkyLark past_trip, aw-merge): every row's
    # ID is trip_row_<code>, so by ID the routine read the first row, and with no action choosing the row the city was
    # dropped as unused.
    from routines.compiler import _consumed, _extract_for
    from routines.model import Step, StepAction
    from routines.screens import screen_from_tree

    def trips(rows: list[str]):
        els = [{"index": 0, "parent": None, "kind": "List", "class": "androidx.recyclerview.widget.RecyclerView", "scrollable": True,
                "resource_id": "com.skylark.air:id/list_trips", "bounds": [0, 200, 1080, 2200]}]
        for i, label in enumerate(rows):
            y = 220 + 200 * i
            code = label.rsplit(" · ", 1)[-1]
            els.append({"index": len(els), "parent": 0, "kind": "Button", "class": "android.view.View", "clickable": True, "in_list": True,
                        "label": label, "text": label, "resource_id": f"com.skylark.air:id/trip_row_{code}", "bounds": [0, y, 1080, y + 180]})
        for n, e in enumerate(els, 1):
            e["number"] = n
        return screen_from_tree({"package": "com.skylark.air", "activity": "MainActivity", "width": 1080, "height": 2400, "elements": els})
    rows = ["SL 761 · ATL → AUS · HQ3N7V", "Miami · Sun, Jul 19, 2026 · SL 105 · ATL → MIA · ZB5K1R",
            "Seattle · Tue, Mar 3, 2026 · SL 1708 · ATL → SEA · KS4V9Q", "Orlando · Sat, Feb 14, 2026 · SL 77 · ATL → MCO · WN6G2H"]
    final = trips(rows)
    data = ["Tue, Mar 3, 2026", "SL 1708", "KS4V9Q", "HQ3N7V"]
    ex = _extract_for("flight_date", "", "Tue, Mar 3, 2026", final, {"trip_city": "Seattle"}, data)
    assert ex is not None and ex.locator is not None and ex.locator.text_has == "{{trip_city}}" and ex.segment == 1
    assert ex.near is None  # not the city itself as fixed text
    assert extract_value(ex, final, {"trip_city": "Seattle"}) == "Tue, Mar 3, 2026"  # its own row, not the first one
    assert extract_value(ex, final, {"trip_city": "Miami"}) == "Sun, Jul 19, 2026"  # another trip: that trip's row
    assert extract_value(ex, trips(rows[:2]), {"trip_city": "Seattle"}) is None  # not on screen: missing, the ladder takes over
    flight = _extract_for("flight_number", "", "SL 1708", final, {"trip_city": "Seattle"}, data)
    assert flight is not None and extract_value(flight, final, {"trip_city": "Orlando"}) == "SL 77"
    # The input is used: the step that reads the output in its row consumes it, so it isn't dropped.
    read = Step(id="read", intent="read", action=StepAction(kind="wait", seconds=0.3), extract={"flight_date": ex})
    assert _consumed(read, "trip_city") and not _consumed(read, "other")
    # A row whose input is only inside a longer part (a product title containing the search words) keeps the old reads.
    shop = trips(["USB C Cable 6ft braided · $9.99 · AB1", "USB C Cable 3ft · $7.49 · AB2"])
    keep = _extract_for("price", "", "$9.99", shop, {"search_query": "USB C Cable"}, ["$9.99"])
    assert keep is None or keep.locator is None or keep.locator.text_has != "{{search_query}}"


def test_a_trailing_scroll_with_no_output_to_reveal_is_dropped_so_the_routine_loads():
    # Phase 7's youtube_search routine had lost its output, so its trailing scroll got an empty target, which was saved as
    # no target and made the routine unloadable (backlog #17).
    from routines.compiler import CompileReport, _aim_trailing_scrolls
    from routines.model import Extract, Locator, Routine, Step, StepAction, dump_yaml, load_yaml

    def steps():
        return [Step(id="search", intent="search", action=StepAction(kind="tap", target=Locator(text="Search"))),
                Step(id="reveal", intent="scroll to the answer", action=StepAction(kind="scroll_until", direction="down", max_scrolls=8))]
    rep = CompileReport(task_id="t", goal="g")
    kept = _aim_trailing_scrolls(steps(), {}, rep)
    assert [s.id for s in kept] == ["search"] and any("dropped" in w for w in rep.warnings)
    r = Routine(routine="r", app="a", version=1, status="draft", intent="i", steps=kept)
    assert load_yaml(dump_yaml(r)).steps[0].id == "search"  # round-trips
    aimed = _aim_trailing_scrolls(steps(), {"title": Extract(locator=Locator(kind="Button"))}, CompileReport(task_id="t", goal="g"))
    assert aimed[1].action.target == Locator(kind="Button") and load_yaml(dump_yaml(Routine(
        routine="r", app="a", version=1, status="draft", intent="i", steps=aimed))).steps[1].action.target is not None
