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


def test_the_history_shows_what_happened_not_the_models_prose(tmp_path, monkeypatch):
    monkeypatch.setattr(TraceWriter.__init__, "__defaults__", (tmp_path,))
    model = Model(BACK)
    asyncio.run(AgentRunner(TickingHome(), model, ScriptedApprover(True), RunConfig(max_steps=3, data_scope="test_app"))
                .run("Open the file manager", task_id="echo", memory=""))
    assert len(model.prompts) >= 2 and not any("Incorrect but required placeholder" in p for p in model.prompts)


def test_volatile_lines():
    a, b = home("00:01"), home("00:02")
    assert _volatile(a, b) == {0}
    assert _masked(a.compact, {0}) == _masked(b.compact, {0}) and _masked(a.compact, set()) != _masked(b.compact, set())

def node(text: str, pkg: str = "com.example.app", cls: str = "android.widget.TextView", clickable: str = "false",
         bounds: str = "[0,400][1080,500]", rid: str = "") -> str:
    return (f'<node index="0" text="{text}" resource-id="{rid}" class="{cls}" package="{pkg}" clickable="{clickable}" '
            f'{ATTRS} bounds="{bounds}" />')


def screen_of(*nodes: str, pkg: str = "com.example.app"):
    xml = (f'<?xml version="1.0" encoding="UTF-8"?><hierarchy rotation="0"><node index="0" text="" resource-id="" '
           f'class="android.widget.FrameLayout" package="{pkg}" clickable="false" {ATTRS} bounds="[0,0][1080,2400]">'
           f'{"".join(nodes)}</node></hierarchy>')
    return build_state(xml, pkg, f"{pkg}.Main", 1080, 2400)


def test_the_screen_says_when_the_keyboard_is_open():
    key = node("q", pkg="com.google.android.inputmethod.latin", clickable="true", bounds="[0,1800][100,1900]", rid="key_pos_0_0")
    up = screen_of(node("Title"), key)
    assert "(the on-screen keyboard is open" in up.compact and '"q"' not in up.compact
    assert "keyboard" not in screen_of(node("Title")).compact


class Phone(TickingHome):
    """A home screen that stays the same, with a date, recording the actions it gets."""

    def _read(self):
        return home("Sun, Oct 15")

    async def local_time(self) -> str:
        return "Sunday, October 15 2023, 15:34"


class Seq:
    """A model that answers the plan, then step outputs in order (the last one repeats)."""

    def __init__(self, *steps: dict) -> None:
        self.steps, self.prompts, self.plan_prompts = list(steps), [], []

    def call(self, job, content, **kw):
        if job == "plan":
            self.plan_prompts.append(content[0]["text"])
            parsed = Plan(app=None, subgoals=["Open the app"], success_check=SuccessCheck(kind="text_visible", value="Saved", field_hint=None))
        else:
            self.prompts.append(content[0]["text"])
            parsed = StepOutput.model_validate(self.steps.pop(0) if len(self.steps) > 1 else self.steps[0])
        return SimpleNamespace(parsed=parsed, usage={}, cost_usd=0.0, cost_at_standard_usd=0.0)


def step(action: dict, reason: str = "Open it") -> dict:
    return {"reason": reason, "action": action, "expected_result": "something", "risk": "read"}


def test_a_placeholder_action_is_asked_again_not_carried_out(tmp_path, monkeypatch):
    monkeypatch.setattr(TraceWriter.__init__, "__defaults__", (tmp_path,))
    phone = Phone()
    model = Seq(step({"type": "back"}, "Placeholder to comply with schema"), step({"type": "tap", "element": 2}), step({"type": "done", "result": "ok"}))
    asyncio.run(AgentRunner(phone, model, ScriptedApprover(True), RunConfig(max_steps=3, data_scope="test_app"))
                .run("Open Gmail", task_id="ph", memory=""))
    assert [a.kind for a in phone.actions][:1] == ["tap"]  # the back was never carried out
    assert "your reason called it a placeholder" in model.prompts[1]


def test_a_second_done_is_accepted_when_the_plans_check_disagrees(tmp_path, monkeypatch):
    monkeypatch.setattr(TraceWriter.__init__, "__defaults__", (tmp_path,))
    model = Seq(step({"type": "done", "result": "Stopwatch paused"}))  # the plan's check wants "Saved", never on screen
    res = asyncio.run(AgentRunner(Phone(), model, ScriptedApprover(True), RunConfig(max_steps=5, data_scope="test_app"))
                      .run("Pause the stopwatch", task_id="dn", memory=""))
    assert res.status == "done_unverified" and len(model.prompts) == 2
    assert "answer done again now and it will be accepted" in model.prompts[1]
