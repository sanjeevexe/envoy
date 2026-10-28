"""The Envoy half of the AndroidWorld adapter (eval/androidworld/envoy_episode.py), offline.

What Envoy is told about a task is exactly the goal, the step budget, a run id and the run's configuration; AndroidWorld's
step budget is Envoy's max_steps (one loop iteration = one step); only a `done` carries an answer; an episode the agent
ended itself is "done" for AndroidWorld, a step limit or a crash is not. The real agent loop runs here against saved
screens and a scripted model.
"""

from __future__ import annotations

import asyncio
import gzip
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from agent.loop import AgentRunner, RunConfig
from agent.trace import TraceWriter
from devices.screen import build_state
from devices.types import ActionResult
from models.schemas import Plan, StepOutput, SuccessCheck
from policy.approvals import ScriptedApprover

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "eval" / "androidworld"))
import envoy_episode as ee  # noqa: E402

SCREENS = Path(__file__).parent / "screens"


def test_payload_is_only_the_goal_the_budget_a_run_id_and_the_config():
    p = ee.make_payload("Turn bluetooth on.", 10, "aw-test-1")
    assert set(p) == ee.PAYLOAD_KEYS == {"goal", "max_steps", "run_id", "config"}
    assert p == {"goal": "Turn bluetooth on.", "max_steps": 10, "run_id": "aw-test-1", "config": {}}
    with pytest.raises(ValueError):
        ee.make_payload("x", 10, "r", {"task_name": "SystemBluetoothTurnOn"})  # nothing about the task beyond the goal
    with pytest.raises(ValueError):
        ee.make_payload("x", 10, "r", {"params": {"seed": 30}})
    with pytest.raises(ValueError):
        ee.make_payload("", 10, "r")
    with pytest.raises(ValueError):
        ee.make_payload("x", 0, "r")


def test_a_payload_carrying_task_internals_is_refused(tmp_path, monkeypatch):
    bad = tmp_path / "p.json"
    bad.write_text(json.dumps({**ee.make_payload("x", 10, "r"), "expected_answer": "Board meeting"}))
    monkeypatch.setattr(sys, "argv", ["envoy_episode.py", "--payload", str(bad), "--out", str(tmp_path / "o.json")])
    with pytest.raises(SystemExit, match="payload must have exactly"):
        ee.main()
    assert not (tmp_path / "o.json").exists()


@pytest.mark.parametrize("status,result,done,answer", [
    ("done", "Board meeting", True, "Board meeting"),
    ("done_unverified", "3", True, "3"),
    ("failed", "could not find the event 3", True, None),  # the agent ended it, but a failure reason is never an answer
    ("handoff", "sign-in needed", True, None),
    ("needs_user", "which contact?", True, None),
    ("step_limit", "stopped after 10 steps", False, None),
    ("cost_limit", "stopped at $0.150", False, None),
    ("error", "RuntimeError: adb", False, None),
    ("done", "", True, None),
])
def test_status_maps_onto_androidworlds_done_and_answer(status, result, done, answer):
    assert ee.to_androidworld(status, result) == {"done": done, "answer": answer}


# ---- the real loop, a saved screen, a scripted model -------------------------------------------------------------------

class FakeDevice:
    def __init__(self) -> None:
        self.screen = build_state((SCREENS / "skylark_trip.xml").read_text(), "com.skylark.air", "com.skylark.air.MainActivity", 1080, 2400)
        self.actions: list = []

    async def wait_until_settled(self, timeout_s: float = 5):
        return self.screen

    async def act(self, action):
        self.actions.append(action)
        return ActionResult(ok=True, duration_ms=1.0)

    async def screenshot(self) -> bytes:  # asked for after an action with no visible change
        buf = io.BytesIO()
        Image.new("RGB", (1080, 2400), "white").save(buf, format="PNG")
        return buf.getvalue()


class ScriptedModel:
    def __init__(self, steps: list[dict]) -> None:
        self.steps, self.jobs = list(steps), []

    def call(self, job, content, **kw):
        self.jobs.append(job)
        if job == "plan":
            parsed = Plan(app=None, subgoals=["Open the trip", "Read the gate"], success_check=SuccessCheck(kind="info", value="gate", field_hint=None))
        else:
            parsed = StepOutput.model_validate(self.steps.pop(0) if len(self.steps) > 1 else self.steps[0])
        return SimpleNamespace(parsed=parsed, usage={"input_tokens": 100, "output_tokens": 10}, cost_usd=0.0001, cost_at_standard_usd=0.001)


SCROLL = {"reason": "look further", "action": {"type": "scroll", "direction": "down", "element": None}, "expected_result": "more", "risk": "read"}


def _run(tmp_path, monkeypatch, steps, max_steps):
    monkeypatch.setattr(TraceWriter.__init__, "__defaults__", (tmp_path,))
    runner = AgentRunner(FakeDevice(), ScriptedModel(steps), ScriptedApprover(True),
                         RunConfig(max_steps=max_steps, data_scope="test_app", contributor=True))
    return asyncio.run(runner.run("What gate does my flight leave from?", task_id="aw-test", memory=""))


def test_androidworlds_step_budget_is_envoys_max_steps(tmp_path, monkeypatch):
    res = _run(tmp_path, monkeypatch, [SCROLL], max_steps=4)
    assert res.status == "step_limit"
    counts = ee.summarize_trace(Path(res.trace_dir))
    # 3 scrolls with no effect, then the runtime's stuck recoveries (a hint, then Back) use up the 4th step
    assert counts["iterations"] == 4 and counts["actions"] == {"scroll": 3} and counts["stuck_recoveries"] == 2
    assert ee.to_androidworld(res.status, res.result) == {"done": False, "answer": None}  # a task not ended by the agent never counts


def test_done_answer_reaches_the_record_and_the_digest_keeps_no_trees(tmp_path, monkeypatch):
    gate = next(e.label for e in FakeDevice().screen.numbered if "B12" in e.label)
    done = {"reason": "the gate is on screen", "action": {"type": "done", "result": "B12"}, "expected_result": "", "risk": "read"}
    res = _run(tmp_path, monkeypatch, [done], max_steps=10)
    assert res.status == "done" and res.result == "B12" and "B12" in gate  # Envoy's own check: the answer is visible
    assert ee.to_androidworld(res.status, res.result) == {"done": True, "answer": "B12"}
    dest = tmp_path / "digest.jsonl.gz"
    ee.write_digest(Path(res.trace_dir), dest)
    rows = [json.loads(l) for l in gzip.open(dest, "rt")]
    assert [r["kind"] for r in rows] == ["plan", "action"]
    assert "B12" in rows[1]["screen"] and not any("tree_before" in r or "screenshot_before" in r for r in rows)
