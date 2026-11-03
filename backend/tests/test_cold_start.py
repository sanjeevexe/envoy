"""A run that opened its app from the home screen and found its answer only in the screenshot (Nov 2's rehearsal on the
Pixel: "how much is an Uber from where the phone is to Piedmont Park", run done but unverified).

Compiled, it came out wrong three ways:
- its app was the launcher, with the launch as its first step and a before-check for the home screen;
- it had no output: Uber's price screen shows the fares to the screenshot only (the tree holds a "Tap for savings
  details" tip and the status bar), and a screenshot read was compiled only for a final screen with no app text at all;
- its tap on the result matched four rows that all name the destination ("Piedmont Park, 1320 Monroe Dr NE, …",
  "Piedmont Park Active Oval, …"), each under the 0.80 bar, so it failed on the run's own screen.

The screens are small made-up ones in Uber's shape (the run's own trees and screenshot show the pickup address).
"""

from __future__ import annotations

import asyncio
import gzip
import json
from pathlib import Path

from devices.types import ActionResult
from models.schemas import CompiledRoutine
from policy.approvals import ScriptedApprover
from routines import compiler as C
from routines import locators, screen_read
from routines.executor import RoutineExecutor
from routines.model import dump_yaml, load_yaml
from routines.screens import screen_from_tree

LAUNCHER, UBER, SYSTEM_UI = "com.google.android.apps.nexuslauncher", "com.ubercab", "com.android.systemui"
GOAL = ("Open the Uber app on Envoy's phone, check the current UberX price from the phone's current location to Piedmont Park, "
        "and report that price. Do NOT request, book, or confirm a ride. Stop at the price screen.")
PLACES = ["{0}, 1320 Monroe Dr NE, Atlanta, GA", "{0} Active Oval, 400 Park Dr NE, Atlanta, GA", "{0}, 400 Park Dr NE, Atlanta, GA",
          "{0} Community Center, 1071 Piedmont Ave NE, Atlanta, GA"]


def _el(i: int, label: str, kind: str = "Button", cls: str = "android.widget.Button", rid: str = "", parent: int | None = None,
        number: int | None = None, bounds=(0, 0, 1080, 100), **kw) -> dict:
    return {"index": i, "parent": parent, "number": number, "resource_id": rid, "label": label, "text": kw.pop("text", label),
            "kind": kind, "class": cls, "bounds": list(bounds), "clickable": kind in ("Button", "EditText"), **kw}


def _tree(package: str, signature: str, elements: list[dict]) -> dict:
    return {"package": package, "activity": "RootActivity" if package == UBER else "", "signature": signature,
            "width": 1080, "height": 2340, "elements": elements}


def screens(destination: str = "Piedmont Park") -> dict[str, dict]:
    home = _tree(LAUNCHER, "home", [
        _el(0, "", "List", "android.widget.ScrollView", f"{LAUNCHER}:id/workspace", number=1, scrollable=True, bounds=(0, 136, 1080, 2000)),
        _el(1, "Uber", "Text", "android.widget.TextView", parent=0, number=2, clickable=True, bounds=(40, 1600, 240, 1800))])
    uber = _tree(UBER, "uber", [
        _el(0, "", "List", "android.widget.ScrollView", f"{UBER}:id/content_frame", number=1, scrollable=True, bounds=(0, 136, 1080, 2200)),
        _el(1, "", "View", "android.view.View", parent=0, bounds=(44, 414, 1036, 579)),
        _el(2, "Where to?", "Button", "android.view.View", parent=1, number=2, in_list=True, text="", bounds=(44, 414, 1036, 579)),
        _el(3, "Ride", "Button", "android.view.View", parent=0, number=3, in_list=True, bounds=(44, 700, 300, 900))])
    def editor(typed: str, results: bool) -> dict:
        els = [_el(0, "Sheet height controller", rid=f"{UBER}:id/location_editor_bottom_sheet_view", number=1, bounds=(0, 300, 1080, 340)),
               _el(1, "For me", rid=f"{UBER}:id/pill_button_guest", number=2, desc="Rider: For me. Switch rider", bounds=(40, 360, 300, 440)),
               _el(2, "", "View", "android.widget.LinearLayout", f"{UBER}:id/vertical_layout", bounds=(100, 600, 1000, 800)),
               _el(3, f"Where to?: {typed}" if typed else "Where to?", "EditText", "android.widget.EditText", f"{UBER}:id/edit_text",
                   parent=2, number=3, text=typed or "Where to?", hint="Where to?", editable=True, bounds=(172, 707, 811, 773)),
               _el(4, "", "View", "android.widget.FrameLayout", bounds=(0, 835, 1080, 1415))]
        if results:
            for k, place in enumerate(PLACES):
                y = 835 + 145 * k
                els.append(_el(5 + 2 * k, "", "View", "android.widget.FrameLayout", parent=4, bounds=(0, y, 1080, y + 145)))
                els.append(_el(6 + 2 * k, place.format(destination), parent=5 + 2 * k, number=4 + k, text="",
                               desc=place.format(destination), bounds=(0, y, 1080, y + 145)))
        return _tree(UBER, f"editor-{bool(typed)}-{results}", els)
    # The price screen: the fares are drawn without a tree; a tip over them and the status bar are all it has.
    prices = _tree(SYSTEM_UI, "prices", [
        _el(0, "", "View", "android.widget.FrameLayout", "android:id/content", bounds=(255, 941, 825, 1163)),
        _el(1, "Tap for savings details", parent=0, number=1, bounds=(299, 1002, 781, 1136)),
        _el(2, "8:27", "Text", "android.widget.TextView", f"{SYSTEM_UI}:id/clock", number=2, status_bar=True, bounds=(167, 6, 257, 136))])
    return {"home": home, "uber": uber, "editor": editor("", False), "results": editor(destination, True), "prices": prices}


def write_trace(trace: Path) -> None:
    sc = screens()
    (trace / "screens").mkdir(parents=True)
    files = [("001_before", "home"), ("001_after", "uber"), ("002_before", "uber"), ("002_after", "editor"), ("003_before", "editor"),
             ("003_after", "results"), ("004_before", "results"), ("004_after", "prices"), ("005_before", "prices")]
    for name, key in files:
        with gzip.open(trace / "screens" / f"{name}.json.gz", "wt") as f:
            json.dump(sc[key], f)
    (trace / "screens" / "005_before.png").write_bytes(b"\x89PNG\r\n\x1a\n")  # read by a stub below
    def act(n: int, kind: str, target: dict | None, settle: float, **dev) -> dict:
        return {"step": n, "kind": "action", "tree_before": f"screens/{n:03d}_before.json.gz", "tree_after": f"screens/{n:03d}_after.json.gz",
                "decision": {"reason": kind, "action": {"type": kind}}, "device_action": {"kind": kind, **dev}, "changed": True,
                "result": {"ok": True}, "target": target, "screen_after": {"settle_ms": settle}}
    records = [act(1, "launch", None, 2440.0, package="Uber"),
               act(2, "tap", {"index": 2}, 4620.0),
               act(3, "type", {"index": 3}, 946.0, text="Piedmont Park", submit=False),
               act(4, "tap", {"index": 6}, 4168.0),
               {"step": 5, "kind": "action", "tree_before": "screens/005_before.json.gz", "screenshot_before": "screens/005_before.png",
                "decision": {"reason": "the price screen shows UberX", "action": {"type": "done", "result": "$9.94"}}}]
    (trace / "steps.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    (trace / "run.json").write_text(json.dumps({
        "task_id": "t-uber", "goal": GOAL, "status": "done_unverified", "result": "UberX to Piedmont Park is $9.94. No ride was requested.",
        "plan": {"app": "Uber", "success_check": {"kind": "info", "value": "UberX price"}},
        "check": {"passed": False, "evaluable": True, "detail": "none of ['UberX', 'Piedmont', 'Park'] is visible on the current screen"}}))


SPEC = CompiledRoutine.model_validate({
    "name": "uber_check_ride_price", "intent": "Check the UberX price to a destination", "description": "", "patterns": [],
    "inputs": [{"name": "destination", "type": "text", "description": "", "from_memory": None, "example": "Piedmont Park"}],
    "steps": [{"step": 1, "id": "launch_uber", "intent": "Launch the Uber app", "target_fixed_text": "Uber", "choice_input": None},
              {"step": 2, "id": "tap_where_to", "intent": "Tap Where to?", "target_fixed_text": "Where to?", "choice_input": None},
              {"step": 3, "id": "type_destination", "intent": "Type {{destination}}", "target_fixed_text": "Where to?", "choice_input": None},
              {"step": 4, "id": "tap_destination_result", "intent": "Tap the result for {{destination}}", "target_fixed_text": None,
               "choice_input": "destination"}],
    "outputs": [{"name": "uberx_price", "near": "UberX", "example": "$9.94"}], "data_values": []})


def _compile(tmp_path: Path, monkeypatch, read: str = "$9.94"):
    trace = tmp_path / "trace"
    write_trace(trace)
    asked: list[str] = []
    def fake_read(adapter, png, question, shape, inputs, **kw):
        asked.append(question)
        return screen_read.Read(read, "stub", 0.0)
    monkeypatch.setattr(screen_read, "read", fake_read)
    routine, report = asyncio.run(C.compile_trace(trace, confirmed=True, spec=SPEC))
    return routine, report, asked


def test_a_run_that_opened_its_app_itself_starts_with_that_app(tmp_path, monkeypatch):
    routine, report, _ = _compile(tmp_path, monkeypatch)
    assert routine.app == UBER and routine.start == "fresh_launch"
    assert [s.id for s in routine.steps][:3] == ["tap_where_to", "type_destination", "tap_destination_result"]
    assert all(s.action.kind != "launch" for s in routine.steps)
    assert not any(c.package == LAUNCHER for s in routine.steps for c in s.pre)
    assert any("opened com.ubercab itself" in w for w in report.warnings)


def test_an_answer_the_tree_never_shows_is_read_from_the_screenshot_after_the_screen_settles(tmp_path, monkeypatch):
    routine, report, asked = _compile(tmp_path, monkeypatch)
    assert routine.outputs == ["uberx_price"]
    read = routine.steps[-1]
    assert read.id == "wait_for_answer" and read.action.kind == "wait" and read.action.seconds == 4.2
    assert read.extract["uberx_price"].from_screenshot == r"\$\d+\.\d+" and asked and "UberX" in asked[0]
    assert not read.pre  # the price screen's tree is System UI's: nothing to wait for there


def test_a_screenshot_that_reads_another_value_compiles_no_output(tmp_path, monkeypatch):
    routine, report, _ = _compile(tmp_path, monkeypatch, read="$12.40")
    assert routine.outputs == [] and all(not s.extract for s in routine.steps)


def test_the_first_of_several_rows_that_name_the_destination_is_tapped(tmp_path, monkeypatch):
    routine, report, _ = _compile(tmp_path, monkeypatch)
    tap = routine.steps[2].action.target
    assert tap.text_has == "{{destination}}" and tap.nth == 0
    for place in ("Piedmont Park", "Atlanta Botanical Garden"):
        results = screen_from_tree(screens(place)["results"])
        m = locators.locate(tap, results, {"destination": place})
        assert m.element is not None and m.element.label == PLACES[0].format(place)
    # Without the place, the four rows tie under the bar on the run's own screen.
    loose = tap.model_copy(update={"nth": None})
    assert locators.locate(loose, screen_from_tree(screens()["results"]), {"destination": "Piedmont Park"}).element is None
    # The rows must still name it: the edit field ("Where to?: …") and the other rows don't count.
    other = screen_from_tree(screens("Piedmont Park")["results"])
    assert locators.locate(tap, other, {"destination": "Atlanta Botanical Garden"}).element is None


def test_the_routine_replays_on_a_new_destination(tmp_path, monkeypatch):
    routine, _, _ = _compile(tmp_path, monkeypatch)
    routine = load_yaml(dump_yaml(routine))
    place = "Atlanta Botanical Garden"
    sc = {k: screen_from_tree(v) for k, v in screens(place).items()}
    flow = {("uber", "tap"): "editor", ("editor", "type"): "results", ("results", "tap"): "prices"}

    class Phone:
        state, taps = "home", []
        async def observe(self, screenshot=False):
            return sc[self.state]
        async def launch(self, package, fresh=False):
            self.state = "uber" if package == UBER else self.state
        async def act(self, a):
            if a.kind == "tap":
                self.taps.append(next(e.label for e in sc[self.state].numbered if e.number == a.element))
            self.state = flow.get((self.state, a.kind), self.state)
            return ActionResult(ok=True, duration_ms=1.0)
        async def screenshot(self):
            return b"\x89PNG\r\n\x1a\n"

    class NoModel:
        def call(self, *a, **k):
            raise AssertionError("no model call but the screenshot read")

    phone = Phone()
    out = asyncio.run(RoutineExecutor(phone, adapter=NoModel(), approver=ScriptedApprover(approve=False)).run(
        routine, {"destination": place}, launch="fresh", allow_repair=False, allow_agent=False))
    assert out.status == "done", out.detail
    assert out.outputs == {"uberx_price": "$9.94"} and out.model_calls == 1
    assert phone.taps == ["Where to?", PLACES[0].format(place)]


def test_a_run_that_starts_in_its_app_keeps_its_first_step(tmp_path, monkeypatch):
    # The launch is the start only as the run's first step; a run recorded in the app already is unchanged.
    trace = tmp_path / "trace"
    write_trace(trace)
    lines = (trace / "steps.jsonl").read_text().splitlines()[1:]
    (trace / "steps.jsonl").write_text("\n".join(lines) + "\n")
    monkeypatch.setattr(screen_read, "read", lambda *a, **k: screen_read.Read("$9.94", "stub", 0.0))
    spec = SPEC.model_copy(update={"steps": [m.model_copy(update={"step": m.step - 1}) for m in SPEC.steps[1:]]})
    routine, report = asyncio.run(C.compile_trace(trace, confirmed=True, spec=spec))
    assert routine.app == UBER and routine.steps[0].id == "tap_where_to"
    assert not any("itself" in w for w in report.warnings)
