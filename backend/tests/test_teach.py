"""Teach mode (api/teach.py): a demonstration through the live view becomes a trace in the agent's format, and the
compiler turns it into a routine. The phone is a scripted SkyLark Air (real screens from tests/screens) and the person is
a list of live-view messages sent through live.py itself. No device and no model.

Privacy is proved here too: a normal takeover stores nothing, and teach mode stores nothing on sign-in or secure screens
and never what is typed into a password field."""

from __future__ import annotations

import asyncio
import gzip
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient
from PIL import Image

import api.teach as teach
from agent.trace import TraceWriter
from api.devices import DevicePool
from api.events import EventBus
from api.live import live_view
from api.teach import Recorder, Teacher, drag_action, element_at, on_keyboard, private_reason
from devices.screen import build_state
from devices.types import Capabilities
from models.schemas import CompiledRoutine
from routines.compiler import clean, compile_trace, load_trace
from routines.screens import load_tree

SCREENS = Path(__file__).parent / "screens"
W, H = 1080, 2400
PKG = "com.skylark.air"


@pytest.fixture(autouse=True)
def _quick_settle(monkeypatch):
    monkeypatch.setattr(teach, "QUIET_MS", 40)


class Phone:
    """SkyLark on a scripted phone: taps move between real captured screens, typing fills the focused field."""

    MOVES = {("home", "card_next_trip"): "trip", ("home", "nav_trips"): "trips", ("signin", "btn_sign_in"): "home",
             ("trip", "btn_save_ktn"): "trip"}

    def __init__(self, start: str = "home") -> None:
        self.name, self.texts, self.focus = start, {}, None
        self.secure, self.black = False, False
        self.capabilities = Capabilities(real_phone=False, has_sim=False, can_snapshot=True, width=W, height=H, density=420)
        self.stream = self
        self.observes, self.got = 0, []

    def screen(self):
        root = ET.fromstring((SCREENS / f"skylark_{self.name}.xml").read_text().split("?>", 1)[-1])
        for n in root.iter("node"):
            rid = n.get("resource-id")
            if rid in self.texts.get(self.name, {}):
                n.set("text", self.texts[self.name][rid])
            n.set("focused", "true" if rid and rid == self.focus else "false")
        return build_state(ET.tostring(root, encoding="unicode"), PKG, f"{PKG}.MainActivity", W, H, secure=self.secure)

    async def observe(self, screenshot: bool = False):
        self.observes += 1
        return self.screen()

    async def wait_until_settled(self, timeout_s: float = 5):
        return self.screen()

    async def launch(self, app: str, fresh: bool = False) -> None:
        self.name, self.focus = "home", None

    def frame(self, width: int, timeout: float = 5):
        return Image.new("RGB", (width, width * 2), (0, 0, 0) if self.black else (250, 250, 245))

    # the live view's input (the emulator's gRPC stream)
    def tap(self, x: int, y: int) -> None:
        self.got.append(("tap", x, y))
        el = element_at(self.screen(), x, y)
        if el is None:
            return
        if el.editable:
            self.focus = el.resource_id
            return
        self.focus = None
        self.name = self.MOVES.get((self.name, el.resource_id), self.name)

    def swipe(self, x1, y1, x2, y2, duration_s=0.3) -> None:
        self.got.append(("swipe", x1, y1, x2, y2))

    def text(self, t: str) -> None:
        self.got.append(("text", t))
        if self.focus:
            fields = self.texts.setdefault(self.name, {})
            fields[self.focus] = fields.get(self.focus, "") + t

    def key(self, k: str) -> None:
        self.got.append(("key", k))
        if k == "GoBack":
            self.name, self.focus = ("home", None) if self.name != "home" else (self.name, self.focus)
        elif k == "Backspace" and self.focus:
            fields = self.texts.setdefault(self.name, {})
            fields[self.focus] = fields.get(self.focus, "")[:-1]


class Socket:
    """The web app's live-view socket: a person's inputs, with pauses (seconds) between them."""

    def __init__(self, msgs: list) -> None:
        self.msgs, self.sent = list(msgs), []

    async def accept(self) -> None: ...
    async def close(self, code: int = 1000) -> None: ...
    async def send_bytes(self, b: bytes) -> None: ...

    async def send_text(self, t: str) -> None:
        self.sent.append(json.loads(t))

    async def receive_text(self) -> str:
        while self.msgs and isinstance(self.msgs[0], (int, float)):
            await asyncio.sleep(self.msgs.pop(0))
        if not self.msgs:
            raise WebSocketDisconnect()
        return json.dumps(self.msgs.pop(0))


def at(phone: Phone, rid: str, screen: str | None = None) -> dict:
    """A tap in the middle of the element, in the live view's fractions."""
    name, phone.name = phone.name, screen or phone.name
    e = next(e for e in phone.screen().numbered if e.resource_id == rid)
    phone.name = name
    x, y = e.center
    return {"type": "tap", "x": x / W, "y": y / H}


def pool_with(phone: Phone) -> DevicePool:
    pool = DevicePool(EventBus())
    pool._devices["envoy-test"] = phone
    return pool


def files_text(folder: Path) -> str:
    """Everything stored under a folder, gzip trees opened."""
    out = []
    for p in folder.rglob("*"):
        if p.is_file():
            out.append(gzip.decompress(p.read_bytes()).decode() if p.suffix == ".gz" else p.read_bytes().decode("utf-8", "replace"))
    return "\n".join(out)


async def demonstrate(phone: Phone, msgs: list, tmp: Path, *, goal: str = "Add my known traveler number 55501234 to my Chicago trip",
                      answer: str = "") -> tuple[Recorder, Path]:
    pool = pool_with(phone)
    rec = Recorder("teach-test", goal, phone, root=tmp)
    pool.recorders["envoy-test"] = rec
    pool.take_over("envoy-test", "teaching", by="teach")
    await live_view(Socket(msgs), "envoy-test", pool, fps=20)
    del pool.recorders["envoy-test"]
    return rec, await rec.finish(answer)


def ktn_demo(phone: Phone) -> list:
    return [at(phone, "nav_trips"), 0.15, {"type": "key", "key": "Back"}, 0.15,  # a look at My Trips and back: a back-track
            at(phone, "card_next_trip"), 0.15, at(phone, "field_ktn", "trip"), 0.1,
            {"type": "text", "text": "5550"}, {"type": "text", "text": "12x"}, {"type": "key", "key": "Backspace"},
            {"type": "text", "text": "34"}, 0.1, at(phone, "btn_save_ktn", "trip"), 0.15]


def records(trace: Path) -> list[dict]:
    return [json.loads(x) for x in (trace / "steps.jsonl").read_text().splitlines() if x.strip()]


# ---- mapping a person's input onto the screen ------------------------------------------------------

def screen(name: str):
    return build_state((SCREENS / f"{name}.xml").read_text(), PKG, f"{PKG}.MainActivity", W, H)


def test_a_tap_is_the_smallest_clickable_element_under_the_finger():
    home = screen("skylark_home")
    card = next(e for e in home.numbered if e.resource_id == "card_next_trip")
    assert element_at(home, *card.center).resource_id == "card_next_trip"
    assert element_at(home, card.bounds[0] + 3, card.bounds[3] - 3).resource_id == "card_next_trip"  # its corner, not its centre
    dismiss = next(e for e in home.numbered if e.resource_id == "btn_dismiss_promo")
    assert element_at(home, *dismiss.center).resource_id == "btn_dismiss_promo"
    greeting = next(e for e in home.numbered if e.resource_id == "text_greeting")
    assert element_at(home, *greeting.center) is None  # text that isn't clickable: a coordinate tap
    trip = screen("skylark_trip")
    ktn = next(e for e in trip.numbered if e.resource_id == "field_ktn")
    assert element_at(trip, *ktn.center).editable


CAL = "com.google.android.calendar"


def node(cls: str, bounds: str, kids: str = "", **attrs: str) -> str:
    extra = "".join(f' {k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    return f'<node class="android.widget.{cls}" package="{CAL}" bounds="{bounds}"{extra}>{kids}</node>'


# Google Calendar's event editor (from a teach recording, Oct 31): the sheet is drawn over the calendar, whose toolbar
# stays in the tree; its "Open Tasks" sits under the sheet's Save.
EDITOR = "<hierarchy>" + node("FrameLayout", "[0,0][1080,2400]", (
    node("LinearLayout", "[0,128][1080,296]", node("Button", "[806,148][933,274]", resource_id=f"{CAL}:id/action_tasks",
                                                   content_desc="Open Tasks", clickable="true"))
    + node("ListView", "[0,296][1080,2400]", node("Button", "[0,400][1080,600]", content_desc="Halloween", clickable="true"),
           resource_id=f"{CAL}:id/main_pane", scrollable="true")
    + node("FrameLayout", "[0,128][1080,2400]", (
        node("FrameLayout", "[0,128][1080,2400]", resource_id=f"{CAL}:id/editor_sheet_click_target", clickable="true")
        + node("RelativeLayout", "[0,128][1080,296]", node("Button", "[807,149][1038,275]", resource_id=f"{CAL}:id/save",
                                                           text="Save", clickable="true"))
        + node("RecyclerView", "[0,296][1080,2400]", node("EditText", "[42,320][1038,460]", resource_id=f"{CAL}:id/title",
                                                          text="Dentist", clickable="true"),
               resource_id=f"{CAL}:id/expanded_recycler", scrollable="true")),
        resource_id=f"{CAL}:id/event_editor_sheet"))) + "</hierarchy>"


def test_a_tap_goes_to_what_is_on_top_not_to_what_a_sheet_covers():
    editor = build_state(EDITOR, CAL, "x", W, H)
    tasks = next(e for e in editor.numbered if e.label == "Open Tasks")
    assert element_at(editor, 922, 212).label == "Save"  # Save's centre is inside the covered Open Tasks, which is smaller
    assert element_at(editor, *tasks.center).label == "Save"
    assert element_at(editor, 540, 500) is None  # the sheet's list, not the calendar's "Halloween" row under it
    action, box = drag_action(editor, 540, 2000, 540, 1000)
    assert action.kind == "scroll" and box.resource_id.endswith("expanded_recycler")  # not the calendar under the sheet
    # A dialog's window over the app: the smaller window is on top, whichever order the dump lists them in
    app = node("FrameLayout", "[0,0][1080,2400]", node("ImageButton", "[700,1150][800,1200]", content_desc="Today", clickable="true"))
    dialog = node("FrameLayout", "[100,900][980,1500]", node("Button", "[600,1100][900,1250]", text="OK", clickable="true"))
    for windows in (app + dialog, dialog + app):
        assert element_at(build_state(f"<hierarchy>{windows}</hierarchy>", CAL, "x", W, H), 750, 1175).label == "OK"


def test_a_drag_in_a_list_is_a_scroll_and_any_other_drag_a_swipe():
    store = build_state((SCREENS / "playstore_free.xml").read_text(), "com.android.vending", "x", W, H)
    action, box = drag_action(store, 540, 2000, 540, 1000)  # finger up: reveal what is further down
    assert action.kind == "scroll" and action.direction == "down" and box is not None and box.scrollable and action.element == box.number
    assert drag_action(store, 540, 1000, 540, 2000)[0].direction == "up"
    action, box = drag_action(store, 900, 1050, 200, 1060)  # sideways in a horizontal list
    assert action.kind == "scroll" and action.direction == "right" and "Horizontal" in box.cls
    action, box = drag_action(store, 900, 1500, 200, 1510)  # sideways in a vertical list: a swipe (dismissing a row, say)
    assert action.kind == "swipe" and box is None and (action.x, action.y, action.x2, action.y2) == (900, 1500, 200, 1510)
    action, _ = drag_action(screen("skylark_home"), 540, 1500, 540, 900)  # no list under the finger
    assert action.kind == "swipe"


def test_a_tap_on_the_on_screen_keyboard_is_found_from_its_window():
    xml = ('<hierarchy><node class="android.widget.FrameLayout" package="com.skylark.air" bounds="[0,0][1080,2400]" visible-to-user="true">'
           '<node class="android.widget.EditText" resource-id="field_ktn" package="com.skylark.air" clickable="true" focused="true" '
           'bounds="[42,300][1038,460]" visible-to-user="true" text=""/></node>'
           '<node class="android.widget.FrameLayout" package="com.google.android.inputmethod.latin" bounds="[0,1600][1080,2400]" '
           'visible-to-user="true"/></hierarchy>')
    s = build_state(xml, PKG, "x", W, H)
    assert on_keyboard(s, 540, 2000) and not on_keyboard(s, 540, 380)


def test_private_screens_sign_in_secure_and_black():
    assert private_reason(screen("skylark_signin")).startswith("a sign-in screen")
    assert private_reason(screen("skylark_home")) is None
    secure = build_state((SCREENS / "skylark_home.xml").read_text(), PKG, "x", W, H, secure=True)
    assert private_reason(secure) == "a secure screen"
    assert private_reason(screen("skylark_home"), Image.new("RGB", (54, 120))) == "a protected screen"  # black: a phone's secure window
    assert private_reason(screen("skylark_home"), Image.new("RGB", (54, 120), (240, 240, 240))) is None


# ---- a demonstration becomes a trace the compiler reads --------------------------------------------

def test_a_demonstration_is_a_trace_in_the_agents_format(tmp_path):
    phone = Phone()
    rec, trace = asyncio.run(demonstrate(phone, ktn_demo(phone), tmp_path))
    assert phone.texts["trip"]["field_ktn"] == "55501234"  # every input reached the phone
    run = json.loads((trace / "run.json").read_text())
    assert run["status"] == "done" and run["source"] == "taught" and run["model_calls"] == 0 and run["plan"] == {"app": PKG}
    rows = records(trace)
    acts = [r for r in rows if r.get("device_action")]
    kinds = [(r["device_action"]["kind"], (r.get("target") or {}).get("resource_id")) for r in acts]
    # The tap that only focused the field is folded into the typing (as the agent's type step taps the field itself).
    assert kinds == [("tap", "nav_trips"), ("back", None), ("tap", "card_next_trip"), ("type", "field_ktn"), ("tap", "btn_save_ktn")]
    typed = next(r for r in acts if r["device_action"]["kind"] == "type")
    assert typed["device_action"]["text"] == "55501234"  # read back from the field: the typo and Backspace come out right
    for r in acts:
        assert r["taught"] and r["decision"]["reason"] == "" and r["result"]["ok"]
        assert (trace / r["tree_before"]).exists() and (trace / r["tree_after"]).exists() and (trace / r["screenshot_before"]).exists()
        before = load_tree(trace / r["tree_before"])
        if r["device_action"].get("element"):
            assert before.numbered[r["device_action"]["element"] - 1].resource_id == r["target"]["resource_id"]
    assert next(r for r in acts if (r.get("target") or {}).get("resource_id") == "btn_save_ktn")["risk"]["level"] == "reversible"
    done = rows[-1]
    assert done["decision"]["action"]["type"] == "done" and (trace / done["tree_before"]).exists()

    run, recs = load_trace(trace)  # a taught run is done and checked by you: it loads like a verified one
    steps, dropped = clean(trace, recs)
    assert [(s.kind, s.target.resource_id if s.target else None) for s in steps] == [("tap", "card_next_trip"), ("type", "field_ktn"), ("tap", "btn_save_ktn")]
    assert any("back-track" in why for _, why in dropped)


def test_a_dead_tap_and_a_coordinate_tap_are_cleaned_like_an_agents(tmp_path):
    phone = Phone()
    greet = next(e for e in phone.screen().numbered if e.resource_id == "text_greeting")
    msgs = [{"type": "tap", "x": greet.center[0] / W, "y": greet.center[1] / H}, 0.12, at(phone, "card_next_trip"), 0.12]
    rec, trace = asyncio.run(demonstrate(phone, msgs, tmp_path))
    acts = [r for r in records(trace) if r.get("device_action")]
    assert acts[0]["device_action"]["kind"] == "tap_point" and acts[0]["changed"] is False
    steps, dropped = clean(trace, load_trace(trace)[1])
    assert [s.kind for s in steps] == ["tap"] and "no visible change" in dropped[0][1]
    assert any("as a point" in n for n in rec.notes)


SPEC = {
    "name": "skylark_add_known_traveler_number", "intent": "Add a known traveler number to the next SkyLark trip",
    "description": "Open the next trip, type the known traveler number and save it.",
    "patterns": ["add my known traveler number", "save my KTN to my trip", "put my known traveler number on my trip"],
    "inputs": [{"name": "known_traveler_number", "type": "text", "description": "The known traveler number", "from_memory": "user.known_traveler_number",
                "example": "55501234"}],
    "steps": [{"step": 1, "id": "open_next_trip", "intent": "Open the next trip", "target_fixed_text": "Next trip", "choice_input": None},
              {"step": 2, "id": "type_ktn", "intent": "Type {{known_traveler_number}} into Known traveler number", "target_fixed_text": "Known traveler number",
               "choice_input": None},
              {"step": 3, "id": "save_ktn", "intent": "Tap Save", "target_fixed_text": "Save", "choice_input": None}],
    "outputs": [], "data_values": ["SL 482", "Fri, Oct 30, 2026", "KX7Q2M", "B12", "14C"],
}


def test_a_taught_trace_compiles_into_a_routine_marked_taught(tmp_path):
    phone = Phone()
    _, trace = asyncio.run(demonstrate(phone, ktn_demo(phone), tmp_path))
    routine, report = asyncio.run(compile_trace(trace, confirmed=True, spec=CompiledRoutine.model_validate(SPEC)))
    assert routine.app == PKG and routine.compiled_from["source"] == "taught"
    assert [s.id for s in routine.steps] == ["open_next_trip", "type_ktn", "save_ktn"]
    assert routine.steps[1].action.kind == "type" and routine.steps[1].action.value == "{{known_traveler_number}}"
    assert routine.steps[0].action.target.resource_id == "card_next_trip" and routine.steps[2].action.target.text == "Save"
    assert routine.inputs["known_traveler_number"].example == "55501234"
    assert all(s.post for s in routine.steps)


def test_the_compile_prompt_says_a_person_did_the_steps(tmp_path):
    from routines.compiler import describe_steps
    phone = Phone()
    _, trace = asyncio.run(demonstrate(phone, ktn_demo(phone), tmp_path))
    text = describe_steps(clean(trace, load_trace(trace)[1])[0])
    assert "Agent's reason" not in text and text.count("Done by the user") == 3


# ---- privacy -----------------------------------------------------------------------------------------

def test_a_normal_takeover_stores_nothing_and_reads_no_screen(tmp_path, monkeypatch):
    """live.py's promise: takeover input goes straight to the phone, never logged, stored or shown to a model."""
    monkeypatch.setattr(TraceWriter, "__init__", lambda *a, **k: pytest.fail("a takeover must not write a trace"))
    phone = Phone("signin")
    pool = pool_with(phone)
    pool.take_over("envoy-test", "sign-in needed")
    msgs = [at(phone, "field_email"), {"type": "text", "text": "maya@example.com"}, at(phone, "field_password"),
            {"type": "text", "text": "hunter2-secret"}, {"type": "key", "key": "Enter"}, at(phone, "btn_sign_in"), 0.1]
    sock = Socket(msgs)
    asyncio.run(live_view(sock, "envoy-test", pool, fps=20))
    assert ("text", "hunter2-secret") in phone.got and phone.name == "home"  # it all reached the phone
    assert phone.observes == 0  # and no screen was read for it
    assert not any(tmp_path.iterdir()) and pool.recorders == {}
    assert all(m.get("control", {}).get("teach") is None for m in sock.sent if m.get("type") in ("hello", "control"))


def test_teach_mode_stores_nothing_on_a_sign_in_screen_and_never_a_password(tmp_path):
    phone = Phone("signin")
    msgs = [at(phone, "field_email"), 0.1, {"type": "text", "text": "maya@example.com"}, at(phone, "field_password"), 0.1,
            {"type": "text", "text": "hunter2-secret"}, {"type": "key", "key": "Backspace"}, {"type": "key", "key": "Enter"}, 0.1,
            at(phone, "btn_sign_in"), 0.15, at(phone, "card_next_trip", "home"), 0.15]
    rec, trace = asyncio.run(demonstrate(phone, msgs, tmp_path))
    stored = files_text(trace)
    assert "hunter2" not in stored and "maya@example.com" not in stored and "field_password" not in stored and "Sign in to SkyLark" not in stored
    acts = [r for r in records(trace) if r.get("device_action")]
    assert [(r["device_action"]["kind"], r["target"]["resource_id"]) for r in acts] == [("tap", "card_next_trip")]
    assert rec.pauses >= 5 and rec.paused is None  # paused on the sign-in screen, recording again at home
    assert len(list((trace / "screens").glob("*_before.png"))) == 1


def test_teach_mode_pauses_on_secure_and_black_screens(tmp_path):
    phone = Phone()

    async def go():
        pool = pool_with(phone)
        rec = Recorder("teach-secure", "open my trip", phone, root=tmp_path)
        pool.recorders["envoy-test"] = rec
        pool.take_over("envoy-test", "teaching")
        phone.secure = True
        await rec.before(at(phone, "nav_trips"), W, H)
        assert rec.paused == "a secure screen" and rec._pending is None
        phone.secure, phone.black = False, True
        await rec.before(at(phone, "nav_trips"), W, H)
        assert rec.paused == "a protected screen" and rec._pending is None
        phone.black = False
        await rec.before(at(phone, "card_next_trip"), W, H)
        assert rec.paused is None and rec._pending is not None
        return rec, await rec.finish()

    rec, trace = asyncio.run(go())
    assert len([r for r in records(trace) if r.get("device_action")]) == 1 and rec.pauses == 2


def test_typing_into_a_password_field_is_never_recorded_even_off_a_sign_in_form(tmp_path):
    """A password field on a screen sign_in_reason would miss still pauses: the field itself is checked."""
    phone = Phone("trip")
    xml = (SCREENS / "skylark_trip.xml").read_text().replace('resource-id="field_ktn" class="android.widget.EditText" package="com.skylark.air" '
                                                             'content-desc="" checkable="false" checked="false" clickable="true" enabled="true" '
                                                             'focusable="true" focused="false" scrollable="false" long-clickable="true" password="false"',
                                                             'resource-id="field_ktn" class="android.widget.EditText" package="com.skylark.air" '
                                                             'content-desc="" checkable="false" checked="false" clickable="true" enabled="true" '
                                                             'focusable="true" focused="true" scrollable="false" long-clickable="true" password="true"')
    assert 'password="true"' in xml
    pw = build_state(xml, PKG, f"{PKG}.MainActivity", W, H)
    field = next(e for e in pw.numbered if e.resource_id == "field_ktn")

    async def go():
        rec = Recorder("teach-pw", "save my number", SimpleNamespace(observe=lambda: _ret(pw)), root=tmp_path, screenshots=False)
        rec._start_typing(pw, None)
        assert rec._typing is None and rec.paused
        await rec.before({"type": "text", "text": "s3cret-pin"}, W, H)
        assert rec._typing is None
        return await rec.finish()

    trace = asyncio.run(go())
    assert "s3cret" not in files_text(trace) and field.password


async def _ret(x):
    return x


def test_cancel_and_it_didnt_work_keep_nothing(tmp_path):
    phone = Phone()

    async def go(ok: bool):
        pool = pool_with(phone)
        t = Teacher(pool, SimpleNamespace(), EventBus(), SimpleNamespace(), SimpleNamespace(), root=tmp_path)
        s = await t.start("envoy-test", "open my next trip", app=PKG)
        rec = pool.recorders["envoy-test"]
        assert pool.leases["envoy-test"].user_control and pool.leases["envoy-test"].teach["recording"] == "on"
        assert pool.leases["envoy-test"].run_lock.locked()
        await rec.before(at(phone, "card_next_trip"), W, H)
        phone.tap(*next(e for e in phone.screen().numbered if e.resource_id == "card_next_trip").center)
        await rec.after({})
        out = await (t.finish("envoy-test", ok=False) if not ok else t.cancel("envoy-test"))
        lease = pool.leases["envoy-test"]
        assert out["status"] == "discarded" and not lease.user_control and lease.teach is None and not lease.run_lock.locked()
        assert pool.recorders == {}
        return s["id"]

    for ok in (False, True):
        tid = asyncio.run(go(ok))
        assert not (tmp_path / tid).exists()
    assert not any(tmp_path.iterdir())


# ---- the API: start, finish, cancel ---------------------------------------------------------------

@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_BEARER_TOKEN", "mcp-test-token")
    monkeypatch.setenv("ENVOY_PUBLIC_URL", "https://envoy-mac.example.ts.net:8443")
    monkeypatch.setenv("ENVOY_ALLOWED_HOSTS", "testserver")
    monkeypatch.setattr("api.app.API_DIR", tmp_path)
    monkeypatch.setattr("api.push.LOG", tmp_path / "push.jsonl")
    from api.app import build, session_token
    from api.store import TaskStore
    from memory.store import MemoryStore
    from routines.store import RoutineStore
    spec = CompiledRoutine.model_validate(SPEC)
    adapter = SimpleNamespace(call=lambda job, *a, **k: SimpleNamespace(model="muse-wonder-test", cost_usd=0.04, cost_at_standard_usd=0.04,
                                                                        parsed=spec, text="", usage={}))
    app, ctx = build("demo", memory=MemoryStore(":memory:"), tasks=TaskStore(":memory:"), routines=RoutineStore(tmp_path / "routines"),
                     adapter=adapter)  # type: ignore[arg-type]
    phone = Phone()
    ctx.pool._devices["envoy-test"] = phone
    ctx.teacher.root = tmp_path / "runs"
    (tmp_path / "runs").mkdir()
    return ctx, phone, {"Authorization": f"Bearer {session_token()}", "X-Envoy": "1"}


def test_the_teach_endpoints_need_your_session_and_keep_the_phone_until_the_end(api):
    ctx, phone, me = api
    with TestClient(ctx.asgi) as c:
        assert c.post("/api/teach/start", json={"device": "envoy-test", "goal": "x"}).status_code == 401
        assert c.post("/api/teach/start", json={"device": "envoy-test", "goal": " "}, headers=me).status_code == 400
        assert c.post("/api/teach/start", json={"device": "nope", "goal": "x"}, headers=me).status_code == 404
        r = c.post("/api/teach/start", json={"device": "envoy-test", "goal": "Add my known traveler number 55501234", "app": PKG}, headers=me)
        assert r.status_code == 200 and r.json()["status"] == "recording" and r.json()["recording"] == "on"
        state = c.get("/api/devices", headers=me).json()
        test = next(d for d in state if d["avd"] == "envoy-test")
        assert test["user_control"] and test["teach"]["goal"].startswith("Add my known") and test["teach"]["recording"] == "on"
        assert c.post("/api/devices/envoy-test/handback", headers=me).status_code == 409  # finish or cancel, not hand back
        assert c.post("/api/teach/start", json={"device": "envoy-test", "goal": "again"}, headers=me).status_code == 409
        assert c.post("/api/teach/cancel", json={"device": "envoy-test"}, headers=me).json()["status"] == "discarded"
        assert c.post("/api/teach/cancel", json={"device": "envoy-test"}, headers=me).status_code == 409
        assert c.get("/api/teach/envoy-test", headers=me).json()["status"] == "discarded"
        assert not ctx.pool.leases["envoy-test"].user_control and not ctx.pool.leases["envoy-test"].run_lock.locked()


async def _show(ctx, phone) -> dict:
    """The person shows the known-traveler-number task through the live view and finishes; returns the session's status."""
    t = ctx.teacher
    await t.start("envoy-test", "Add my known traveler number 55501234 to my Chicago trip", app=PKG)
    rec = ctx.pool.recorders["envoy-test"]
    sock = Socket(ktn_demo(phone))
    await live_view(sock, "envoy-test", ctx.pool, fps=20)
    assert any((m.get("control") or {}).get("teach", {}).get("recording") == "on" for m in sock.sent if m.get("type") == "hello")
    out = await t.finish("envoy-test", ok=True)
    assert out["status"] == "compiling" and not ctx.pool.leases["envoy-test"].user_control and rec.closed
    await t.jobs["envoy-test"]
    return t.status("envoy-test")


def _clean_replay(monkeypatch, replays: list | None = None) -> None:
    async def replay(self, s, routine):
        if replays is not None:
            replays.append((routine.routine, self.pool.leases[s.avd].user_control))
        return SimpleNamespace(status="done", detail="all steps and checks passed", duration_s=6.2, model_calls=0, outputs={},
                               steps=[], cost_at_standard_usd=0.0)

    monkeypatch.setattr(Teacher, "_replay", replay)


def test_finishing_compiles_replays_once_and_saves_it_as_taught(api, monkeypatch):
    ctx, phone, me = api
    replays = []
    _clean_replay(monkeypatch, replays)
    out = asyncio.run(_show(ctx, phone))
    assert out["status"] == "saved" and out["routine"] == "skylark_add_known_traveler_number" and out["version"] == 1, out
    assert replays == [("skylark_add_known_traveler_number", False)]  # replayed after the hand back
    r = ctx.routines.get("skylark_add_known_traveler_number")
    assert r.compiled_from["source"] == "taught" and r.status == "active"
    idx = ctx.routines.index(r.routine)
    assert idx["versions"][0]["verification"]["by"] == "teach" and idx["versions"][0]["verification"]["cases"][0]["passed"]
    assert out["cost_usd"] == 0.04 and not ctx.pool.leases["envoy-test"].run_lock.locked()

    from api import routine_view
    view = routine_view.detail(ctx.routines, r.routine, ctx.tasks, runs_dir=ctx.teacher.root)
    assert view["taught"] and view["versions"][0]["compiled"]["taught"]


@pytest.mark.parametrize("status, calls, active", [("done", 0, 2), ("agent_done", 3, 1)], ids=["runs-clean", "needs-help"])
def test_a_taught_routine_named_like_one_in_the_library_goes_on_trial(api, monkeypatch, status, calls, active):
    """Backlog #43 (the user's call, Nov 1): showing a task whose routine is already in the library (a tuned demo routine)
    must not replace it untested. The taught version goes on trial: the active one stays in use, the next run uses the
    trial, and it becomes active only if that run finishes on its own; otherwise it's set aside and the old one stays."""
    from routines.executor import RunOutcome
    from routines.lifecycle import after_run, version_for_run
    from routines.model import Routine, Step, StepAction
    ctx, phone, me = api
    name = "skylark_add_known_traveler_number"
    ctx.routines.add(Routine(routine=name, app=PKG, intent="Add my known traveler number",
                             steps=[Step(id="tuned", intent="The tuned way", action=StepAction(kind="back"))]))
    _clean_replay(monkeypatch)
    out = asyncio.run(_show(ctx, phone))
    assert out["status"] == "saved" and out["version"] == 2 and "v1 stays in use until v2" in out["detail"], out
    idx = ctx.routines.index(name)
    assert idx["active"] == 1 and [v["status"] for v in idx["versions"]] == ["active", "trial"]
    assert idx["versions"][1]["verification"]["by"] == "teach" and ctx.routines.get(name).steps[0].id == "tuned"
    trial = version_for_run(ctx.routines, name)
    assert trial.version == 2 and trial.compiled_from["source"] == "taught"
    life = after_run(ctx.routines, trial, RunOutcome(routine=name, version=2, task_id="task-next", status=status, model_calls=calls))
    assert life == {"trial": 2, "result": "activated" if active == 2 else "rejected"}
    assert ctx.routines.index(name)["active"] == active and ctx.routines.get(name).version == active


def test_a_replay_that_fails_saves_nothing(api, monkeypatch):
    ctx, phone, me = api

    async def replay(self, s, routine):
        return SimpleNamespace(status="failed", detail="post-check failed", duration_s=4.0, model_calls=0, outputs={},
                               steps=[SimpleNamespace(id="open_next_trip", status="done", detail=""),
                                      SimpleNamespace(id="type_ktn", status="failed", detail="field not found")], cost_at_standard_usd=0.0)

    monkeypatch.setattr(Teacher, "_replay", replay)

    async def show():
        t = ctx.teacher
        await t.start("envoy-test", "Add my known traveler number 55501234 to my Chicago trip", app=PKG)
        await live_view(Socket(ktn_demo(phone)), "envoy-test", ctx.pool, fps=20)
        await t.finish("envoy-test", ok=True)
        await t.jobs["envoy-test"]
        return t.status("envoy-test")

    out = asyncio.run(show())
    assert out["status"] == "failed" and "type_ktn" in out["detail"] and ctx.routines.names() == []
    assert (Path(ctx.teacher.root) / out["id"] / "routine.yaml").exists()  # the draft stays with the recording


def test_a_forgotten_recording_is_cancelled_and_gives_the_phone_back(tmp_path, monkeypatch):
    monkeypatch.setattr(teach, "IDLE_S", 0.2)
    monkeypatch.setattr(teach, "IDLE_CHECK_S", 0.1)
    phone = Phone()

    async def go():
        pool = pool_with(phone)
        t = Teacher(pool, SimpleNamespace(), EventBus(), SimpleNamespace(), SimpleNamespace(), root=tmp_path)
        s = await t.start("envoy-test", "open my next trip", app=PKG)
        await asyncio.sleep(0.6)
        lease = pool.leases["envoy-test"]
        assert not lease.user_control and not lease.run_lock.locked() and pool.recorders == {}
        return t.status("envoy-test"), s["id"]

    out, tid = asyncio.run(go())
    assert out["status"] == "discarded" and "Nothing happened" in out["detail"] and not (tmp_path / tid).exists()
