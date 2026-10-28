"""General agent fixes found on AndroidWorld (docs/androidworld-results.md), offline: what the runtime counts as progress,
what the model is told about the phone (its date, the keyboard, long text), and what it may do with an action or a done it
doesn't mean."""

from __future__ import annotations

import asyncio
import io
from types import SimpleNamespace

from PIL import Image

from agent.loop import AgentRunner, RunConfig, _masked, _volatile
from agent.trace import TraceWriter
from devices.screen import build_state
from devices.types import ActionResult
from models.schemas import Plan, StepOutput, SuccessCheck
from policy.approvals import ScriptedApprover

ATTRS = ('checkable="false" checked="false" enabled="true" focusable="false" focused="false" scrollable="false" '
         'long-clickable="false" password="false" selected="false" content-desc=""')


def home(clock: str):
    nodes = [("clock", clock, "false", "[0,200][1080,300]"), ("", "Gmail", "true", "[0,400][300,500]"),
             ("", "Photos", "true", "[300,400][600,500]"), ("", "Chrome", "true", "[600,400][900,500]")]
    inner = "".join(f'<node index="{i}" text="{t}" resource-id="{"com.example.home:id/" + r if r else ""}" class="android.widget.TextView" '
                    f'package="com.example.home" clickable="{c}" {ATTRS} bounds="{b}" />' for i, (r, t, c, b) in enumerate(nodes))
    xml = (f'<?xml version="1.0" encoding="UTF-8"?><hierarchy rotation="0"><node index="0" text="" resource-id="" '
           f'class="android.widget.FrameLayout" package="com.example.home" clickable="false" {ATTRS} bounds="[0,0][1080,2400]">'
           f"{inner}</node></hierarchy>")
    return build_state(xml, "com.example.home", "com.example.home.Launcher", 1080, 2400)


class TickingHome:
    """A home screen whose clock ticks on every read; actions change nothing."""

    def __init__(self) -> None:
        self.t = 0
        self.actions: list = []

    def _read(self):
        self.t += 1
        return home(f"00:{self.t:02d}")

    async def wait_until_settled(self, timeout_s: float = 5):
        return self._read()

    async def peek(self):
        return self._read()

    async def act(self, action):
        self.actions.append(action)
        return ActionResult(ok=True, duration_ms=1.0)

    async def screenshot(self) -> bytes:
        buf = io.BytesIO()
        Image.new("RGB", (1080, 2400), "white").save(buf, format="PNG")
        return buf.getvalue()


class Model:
    def __init__(self, step: dict) -> None:
        self.step, self.prompts = step, []

    def call(self, job, content, **kw):
        if job == "plan":
            parsed = Plan(app=None, subgoals=["Open the app"], success_check=SuccessCheck(kind="info", value="x", field_hint=None))
        else:
            self.prompts.append(content[0]["text"])
            parsed = StepOutput.model_validate(self.step)
        return SimpleNamespace(parsed=parsed, usage={}, cost_usd=0.0, cost_at_standard_usd=0.0)


BACK = {"reason": "Placeholder", "action": {"type": "back"}, "expected_result": "Incorrect but required placeholder", "risk": "read"}


def test_a_ticking_clock_is_not_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(TraceWriter.__init__, "__defaults__", (tmp_path,))
    model = Model(BACK)
    res = asyncio.run(AgentRunner(TickingHome(), model, ScriptedApprover(True), RunConfig(max_steps=10, data_scope="test_app"))
                      .run("Open the file manager", task_id="tick", memory=""))
    # Before: every back looked like a change (the clock), so stuck detection never fired and the run used all 10 steps.
    assert res.status == "failed" and "stuck" in res.result
    assert any("NO VISIBLE CHANGE" in p for p in model.prompts)


def test_volatile_lines():
    a, b = home("00:01"), home("00:02")
    assert _volatile(a, b) == {0}
    assert _masked(a.compact, {0}) == _masked(b.compact, {0}) and _masked(a.compact, set()) != _masked(b.compact, set())
