"""The AndroidWorld half of the adapter (run_aw.EnvoyAgent), offline, in AndroidWorld's venv:

  eval/androidworld/aw.sh -m pytest -q eval/androidworld/test_run_aw.py   (or: aw.sh test_run_aw.py)

EnvoyAgent gets only the goal from AndroidWorld's episode runner (its `step(goal)`) and the budget (`set_max_steps`);
the payload it hands Envoy holds nothing else; Envoy's answer reaches AndroidWorld's answer channel through
`execute_action(answer)`; done follows Envoy's own ending; later steps do nothing; the forwarder is parked and restored.
"""

from __future__ import annotations

import sys

import pytest
from android_world.agents import base_agent
from android_world.env import json_action

import aw_env
import run_aw


class FakeEnv:
    def __init__(self) -> None:
        self.actions: list[json_action.JSONAction] = []
        self.resets: list[bool] = []
        self.interaction_cache = ""
        self.automation_ui_hidden = 0

    def hide_automation_ui(self) -> None:
        self.automation_ui_hidden += 1

    def reset(self, go_home: bool = False):
        self.resets.append(go_home)
        self.interaction_cache = ""

    def execute_action(self, action: json_action.JSONAction) -> None:
        self.actions.append(action)
        if action.action_type == json_action.ANSWER:
            self.interaction_cache = action.text


@pytest.fixture
def agent(monkeypatch):
    calls = []
    monkeypatch.setattr(aw_env, "park_forwarder", lambda: calls.append("park"))
    monkeypatch.setattr(aw_env, "restore_forwarder", lambda env: calls.append("restore") or 0.1)
    monkeypatch.setattr(aw_env, "crash_dialog", lambda: "")
    a = run_aw.EnvoyAgent(FakeEnv(), "test")
    a.calls = calls
    return a


def _envoy(record):
    seen = []

    def fake(payload):
        seen.append(payload)
        return {"run_id": payload["run_id"], **record}

    return fake, seen


def test_envoy_gets_only_the_goal_and_the_budget(agent):
    fake, seen = _envoy({"status": "done", "result": "Board meeting", "done": True, "answer": "Board meeting"})
    agent.run_envoy = fake
    agent.reset(go_home=True)
    agent.set_max_steps(10)
    out = agent.step("What is my next upcoming event in Simple Calendar Pro?")
    assert set(seen[0]) == {"goal", "max_steps", "run_id", "config"}
    assert seen[0]["goal"] == "What is my next upcoming event in Simple Calendar Pro?" and seen[0]["max_steps"] == 10
    assert seen[0]["config"] == {} and "SimpleCalendar" not in seen[0]["run_id"]  # the run id names no task
    assert isinstance(out, base_agent.AgentInteractionResult) and out.done
    assert agent.env.interaction_cache == "Board meeting"  # AndroidWorld's answer channel
    assert agent.calls == ["park", "restore"]  # forwarder parked during the episode, restored before scoring
    assert agent.env.resets == [True]


def test_a_step_limit_is_not_done_and_later_steps_idle(agent):
    fake, seen = _envoy({"status": "step_limit", "result": "stopped after 12 steps", "done": False, "answer": None})
    agent.run_envoy = fake
    agent.reset(go_home=True)
    agent.set_max_steps(12)
    assert agent.step("Turn bluetooth on.").done is False
    assert agent.env.actions == []  # no answer without a done
    for _ in range(11):  # AndroidWorld's loop runs out its budget: nothing more happens
        assert agent.step("Turn bluetooth on.").done is False
    assert len(seen) == 1 and agent.env.actions == []


def test_each_episode_runs_envoy_once(agent):
    fake, seen = _envoy({"status": "done", "result": "ok", "done": True, "answer": "ok"})
    agent.run_envoy = fake
    for goal in ("a", "b"):
        agent.reset(go_home=True)
        agent.set_max_steps(10)
        agent.step(goal)
    assert [p["goal"] for p in seen] == ["a", "b"] and len({p["run_id"] for p in seen}) == 2
    assert agent.env.automation_ui_hidden == 2  # pointer location off before every episode, as AndroidWorld's agents do


def test_an_outage_before_acting_waits_and_runs_the_episode_again(agent, monkeypatch):
    waits = []
    monkeypatch.setattr(run_aw, "wait_for_api", lambda: waits.append(1) or True)
    outcomes = iter([{"status": "error", "result": "APIConnectionError: Connection error.", "done": False, "answer": None,
                      "steps_device": 0},
                     {"status": "done", "result": "ok", "done": True, "answer": "ok", "steps_device": 4}])
    seen = []
    agent.run_envoy = lambda payload: seen.append(payload) or {"run_id": payload["run_id"], **next(outcomes)}
    agent.reset(go_home=True)
    agent.set_max_steps(10)
    assert agent.step("Turn bluetooth on.").done
    assert len(seen) == 2 and seen[0]["run_id"] != seen[1]["run_id"] and len(waits) == 1
    assert agent.last["harness"]["api_outage_retries"] == 1


def test_an_outage_after_acting_is_recorded_as_it_happened(agent, monkeypatch):
    monkeypatch.setattr(run_aw, "wait_for_api", lambda: True)
    fake, seen = _envoy({"status": "error", "result": "APIConnectionError: Connection error.", "done": False,
                         "answer": None, "steps_device": 3})
    agent.run_envoy = fake
    agent.reset(go_home=True)
    agent.set_max_steps(10)
    assert agent.step("Turn bluetooth on.").done is False
    assert len(seen) == 1 and agent.last["harness"]["api_lost_mid_episode"] is True


def test_the_noop_agent_never_acts():
    env = FakeEnv()
    a = run_aw.NoopAgent(env)
    assert a.step("Turn bluetooth on.").done and env.actions == []


def test_envoys_subprocess_never_sees_androidworlds_python(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/x/third_party/android_world:/x/eval/androidworld")
    monkeypatch.setenv("VIRTUAL_ENV", "/x/third_party/aw-venv")
    monkeypatch.setenv("PATH", "/x/third_party/aw-venv/bin:/usr/bin")
    env = run_aw._envoy_env()
    assert "PYTHONPATH" not in env and "VIRTUAL_ENV" not in env and "aw-venv" not in env["PATH"]


if __name__ == "__main__":
    sys.exit(pytest.main(["-q", __file__]))


def test_android_env_never_restarts_the_shared_adb_server(monkeypatch):
    # android_env answers a failed adb command with `adb kill-server` + `start-server`; on Oct 28 that took down Phase 7's
    # SkyLark suites, which share the server. aw_env replaces the restart with a wait, and refuses server commands.
    import subprocess
    from android_env.components import adb_controller, config_classes
    calls: list[list[str]] = []

    def check_output(cmd, **kw):
        calls.append(cmd)
        if cmd[-1] == "whoami":  # the device command fails every time
            raise subprocess.CalledProcessError(1, cmd)
        return b""

    monkeypatch.setattr(adb_controller.subprocess, "check_output", check_output)
    monkeypatch.setattr(adb_controller.time, "sleep", lambda s: None)
    monkeypatch.setattr(aw_env.time, "sleep", lambda s: None)
    monkeypatch.setenv("ANDROID_HOME", "/tmp")  # AdbController deletes it; monkeypatch puts it back
    ctl = adb_controller.AdbController(config_classes.AdbControllerConfig(adb_path="adb", device_name=aw_env.SERIAL))
    with pytest.raises(Exception):
        ctl.execute_command(["shell", "whoami"])
    assert calls and not any(c in cmd for cmd in calls for c in ("kill-server", "start-server"))
    assert any(cmd[-1] == "devices" for cmd in calls)  # it waited and looked instead
    with pytest.raises(RuntimeError, match="refused"):
        ctl.execute_command(["kill-server"], device_specific=False)


def test_the_answer_format_benchmark_note_is_added_by_the_adapter_once():
    # coord rule 7: what only AndroidWorld's checker needs lives in the adapter, appended to this process's step
    # instructions; Envoy's own prompt never says it.
    import types
    import envoy_episode as ee
    loop = types.SimpleNamespace(STEP_INSTRUCTIONS="You are Envoy's phone agent.\n")
    ee.adapt_step_instructions(loop)
    ee.adapt_step_instructions(loop)
    assert loop.STEP_INSTRUCTIONS.count("AndroidWorld benchmark") == 1
    assert loop.STEP_INSTRUCTIONS.endswith(ee.ANSWER_FORMAT)
    assert ee.make_payload("Is it a todo? Respond with True or False.", 10, "r1", {"answer_format": False})["config"] == {"answer_format": False}
