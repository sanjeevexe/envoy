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
from models.schemas import Plan, StepOutput, StepOutputListed, SuccessCheck, strict_json_schema
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
    # a dump without the keyboard's window: the navigation bar's keyboard buttons say it is up
    nav = node("", pkg="android", rid="android:id/input_method_nav_back", clickable="true", bounds="[0,2300][150,2400]")
    assert "(the on-screen keyboard is open" in screen_of(node("Title"), nav).compact


def test_long_text_is_shown_at_length_but_rows_stay_short():
    body = " ".join(f"word{i}" for i in range(900))  # ~6,900 characters, like a note or an open file
    row = node(" ".join(f"row{i}" for i in range(60)), clickable="true", bounds="[0,300][1080,380]")
    s = screen_of(node(body, bounds="[0,400][1080,2000]"), row)
    lines = s.compact.split("\n")
    note = next(l for l in lines if "word0" in l)
    assert 3900 < len(note) < 4100  # MAX_TEXT
    assert len(next(l for l in lines if "row0" in l)) < 160  # a clickable row keeps MAX_LABEL


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


def test_the_model_knows_the_phones_date(tmp_path, monkeypatch):
    monkeypatch.setattr(TraceWriter.__init__, "__defaults__", (tmp_path,))
    model = Seq(step({"type": "done", "result": "ok"}))
    asyncio.run(AgentRunner(Phone(), model, ScriptedApprover(True), RunConfig(max_steps=3, data_scope="test_app"))
                .run("Add an event for tomorrow", task_id="date", memory=""))
    assert "TODAY: Sunday, October 15 2023, 15:34" in model.plan_prompts[0] and "TODAY: Sunday" in model.prompts[0]


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


class Moving(TickingHome):
    """Each tap changes the screen; back changes nothing."""

    def __init__(self) -> None:
        super().__init__()
        self.page = 0

    def _read(self):
        return home(f"page {self.page}")

    async def act(self, action):
        self.actions.append(action)
        if action.kind == "tap":
            self.page += 1
        return ActionResult(ok=True, duration_ms=1.0)


def test_stuck_recoveries_start_afresh_after_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(TraceWriter.__init__, "__defaults__", (tmp_path,))
    back, tap = step({"type": "back"}, "Go back"), step({"type": "tap", "element": 2})
    # stuck twice (recoveries 1 and 2), then real progress, then stuck again: before, the third recovery failed the run
    model = Seq(back, back, back, tap, tap, tap, back, back, back, step({"type": "done", "result": "ok"}))
    res = asyncio.run(AgentRunner(Moving(), model, ScriptedApprover(True), RunConfig(max_steps=30, data_scope="test_app"))
                      .run("Open Gmail", task_id="st", memory=""))
    assert res.status != "failed"


def test_the_step_is_written_in_the_order_a_person_decides_it():
    # Meta's decoder writes keys alphabetically: the names the model sees sort into reason → expected result → action →
    # risk, and in every kind of action its name ("act") sorts before its fields
    for model in (StepOutput, StepOutputListed):
        schema = strict_json_schema(model)
        assert list(schema["properties"]) == sorted(schema["properties"]) == ["0_remember", "1_reason", "2_expected_result", "3_action", "4_risk"]
        kinds = [d for d in schema["$defs"].values() if "act" in d.get("properties", {})]
        assert len(kinds) >= 14 and all(sorted(d["properties"])[0] == "act" for d in kinds)
    wire = ('{"0_remember": "", "1_reason": "open the app drawer", "2_expected_result": "the app list", "3_action": {"act": "swipe", "from_x": 500, '
            '"from_y": 900, "to_x": 500, "to_y": 200}, "4_risk": "read"}')
    out = StepOutput.model_validate_json(wire)
    assert out.action.type == "swipe" and out.reason == "open the app drawer"
    assert out.model_dump()["action"]["type"] == "swipe" and "reason" in out.model_dump()  # code and traces keep their names


def test_what_the_model_keeps_from_a_screen_comes_back_on_later_steps(tmp_path, monkeypatch):
    monkeypatch.setattr(TraceWriter.__init__, "__defaults__", (tmp_path,))
    keep = {**step({"type": "swipe", "from_x": 500, "from_y": 900, "to_x": 500, "to_y": 200}), "remember": "Recipes: Pad Thai, Tofu Bowl"}
    model = Seq(step({"type": "swipe", "from_x": 500, "from_y": 900, "to_x": 500, "to_y": 200}), keep, keep,
                step({"type": "swipe", "from_x": 500, "from_y": 900, "to_x": 500, "to_y": 200}), step({"type": "done", "result": "ok"}))
    asyncio.run(AgentRunner(Phone(), model, ScriptedApprover(True), RunConfig(max_steps=6, data_scope="test_app"))
                .run("Copy the recipes", task_id="rm", memory=""))
    assert "REMEMBERED" not in model.prompts[0] and "REMEMBERED" not in model.prompts[1]
    later = model.prompts[3]
    assert "REMEMBERED (what you kept from earlier screens of this task):\n- Recipes: Pad Thai, Tofu Bowl\n" in later
    assert later.count("Pad Thai") == 1  # kept once, though the model wrote it twice


def test_the_planner_is_told_a_button_with_one_item_acts_on_that_item():
    # SkyLark's home shows "Next trip · Chicago" with a "Check in" button beside it. Asked to check in for another trip, plans
    # offered that button 13 times in 40 (main's planner, 3 in 40), and the agent checked in the wrong flight. With this line:
    # 0 in 40, and for the next trip itself the button is still the plan's route (20 of 20).
    from models.prompts import PLAN_INSTRUCTIONS
    assert "acts on that item only; if the goal names a different item, go through the list that holds it" in PLAN_INSTRUCTIONS


def app_screen(*nodes: tuple[str, str, str]):
    """A one-app screen from (resource id, text, clickable) rows."""
    inner = "".join(f'<node index="{i}" text="{t}" resource-id="com.example.app:id/{r}" class="android.widget.TextView" '
                    f'package="com.example.app" clickable="{c}" {ATTRS} bounds="[0,{200 + 100 * i}][1080,{300 + 100 * i}]" />'
                    for i, (r, t, c) in enumerate(nodes))
    xml = (f'<?xml version="1.0" encoding="UTF-8"?><hierarchy rotation="0"><node index="0" text="" resource-id="" '
           f'class="android.widget.FrameLayout" package="com.example.app" clickable="false" {ATTRS} bounds="[0,0][1080,2400]">'
           f"{inner}</node></hierarchy>")
    return build_state(xml, "com.example.app", "com.example.app.MainActivity", 1080, 2400)


def test_a_check_for_the_button_that_opens_a_screen_passes_on_that_screen():
    from agent.checks import evaluate
    view_pass = SuccessCheck(kind="element_present", value="View boarding pass", field_hint=None)
    boarding_pass = app_screen(("text_checked_in", "You're checked in", "false"), ("btn_done", "Done", "true"),
                               ("screen_title", "Boarding pass", "false"))
    assert evaluate(view_pass, boarding_pass, "Checked in").passed
    confirm = app_screen(("btn_confirm_checkin", "Confirm check-in", "true"), ("screen_title", "Check in · SL 1190", "false"))
    assert not evaluate(view_pass, confirm, "Checked in").passed
    # the rest of the name must be a whole label: "Place order" is not the order
    cart = app_screen(("btn_place", "Place order", "true"), ("screen_title", "Cart", "false"))
    assert not evaluate(SuccessCheck(kind="element_present", value="View order", field_hint=None), cart, "Ordered").passed


def test_an_irreversible_step_must_be_for_the_goals_own_item_and_kept_text_comes_from_the_screen():
    # SkyLark's confirm screen says only "Flight · SL 482 · Fri, Oct 30, 2026". The agent had written "Flight SL 482 to
    # Pittsburgh" into 0_remember (the goal's city, never on screen), then confirmed the Chicago flight. Replayed offline:
    # the goal's city written into memory 27/40 → 14/40; wrong-flight confirms with what it really saw 50/50 → 7/50; correct
    # irreversible steps (SkyLark and AndroidWorld) still go ahead 210/210; AndroidWorld steps still keep text 88/120 (85).
    from models.prompts import STEP_INSTRUCTIONS
    assert "Copy it word for word from the screen; never add what the goal says." in STEP_INSTRUCTIONS
    assert "names the goal's own item (the flight, person, item or amount the goal names), not only a number or code" in STEP_INSTRUCTIONS
    assert "find out on the phone first: go back to the item, or the list it came from. Don't ask the user." in STEP_INSTRUCTIONS
