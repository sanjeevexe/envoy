"""Phase 6 offline tests: the real-phone device layer, routing between phones, asking before using your phone, pausing
when you touch it, and screens with no accessibility tree (grounding, SAM 3.1, routines that replay drawn targets).
Also apps that block emulators (a bot check sets "use my phone" for the app) and installing a missing app from the Play
Store, on real Play Store screens captured from envoy-real (tests/screens/playstore_*.xml)."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import struct
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageDraw

import api.devices as devices_mod
import api.runner as runner_mod
from agent.vision import Vision, mark, parse_sam
from api.devices import DevicePool, Lease
from api.events import EventBus
from api.install import Installer, app_named_in, card_listing, card_title, guess_installed, pick_result, read_listing
from api.routing import BLOCKS_EMULATOR, EMULATOR_REFUSED, Choice, app_names, asks_for_phone, blocks_emulator, choose, strip_phone_words
from api.runner import FRESH_INSTALL, TaskRunner, app_for
from api.store import TaskStore
from devices import phone as phone_mod
from devices.phone import is_physical_input, phone_id
from devices.scrcpy import DOWN, MSG_TOUCH, UP, key_msg, text_msg, touch_msg
from devices.screen import build_state
from memory.store import MemoryStore
from policy.approvals import ApprovalDecision
from policy.botcheck import bot_check_reason, is_bot_check_handoff
from routines.visual import match_crop, ncc

# ---- the scrcpy control protocol -----------------------------------------------------------------


def test_scrcpy_control_messages_have_scrcpys_byte_layout():
    m = touch_msg(DOWN, 300, 640, 576, 1280)
    assert len(m) == 32
    kind, action, pointer, x, y, w, h, pressure, action_button, buttons = struct.unpack(">BBqIIHHHII", m)
    assert (kind, action, x, y, w, h, pressure) == (MSG_TOUCH, DOWN, 300, 640, 576, 1280, 0xFFFF)
    assert struct.unpack(">BBqIIHHHII", touch_msg(UP, 1, 2, 576, 1280, 0.0))[7] == 0  # finger up: no pressure
    k = key_msg(0, 4)
    assert len(k) == 14 and struct.unpack(">BBIII", k) == (0, 0, 4, 0, 0)
    t = text_msg("héllo")
    assert t[0] == 1 and struct.unpack(">I", t[1:5])[0] == len("héllo".encode()) and t[5:] == "héllo".encode()


# ---- finding phones, and telling your touches from Envoy's -----------------------------------------


def test_physical_input_is_a_finger_down_or_a_key_press_never_a_release():
    assert is_physical_input("/dev/input/event1: EV_ABS       ABS_MT_TRACKING_ID   00000000")
    assert not is_physical_input("/dev/input/event1: EV_ABS       ABS_MT_TRACKING_ID   ffffffff")  # finger lifted
    assert is_physical_input("/dev/input/event0: EV_KEY       KEY_VOLUMEDOWN       DOWN")
    assert not is_physical_input("/dev/input/event0: EV_KEY       KEY_VOLUMEDOWN       UP")
    assert not is_physical_input("/dev/input/event1: EV_ABS       ABS_MT_POSITION_X    000059b7")
    assert not is_physical_input("add device 1: /dev/input/event1")


def test_discover_lists_phones_not_emulators(monkeypatch):
    out = ("List of devices attached\n"
           "emulator-5554          device product:sdk_gphone64_arm64 model:sdk_gphone64_arm64 device:emu64a transport_id:9\n"
           "R5CT30ABCDE            device usb:1-1 product:o1q model:SM_S901U device:o1q transport_id:12\n"
           "192.168.4.20:41233     unauthorized transport_id:13\n")

    def fake_run(cmd, **kw):
        if cmd[-2:] == ["devices", "-l"]:
            return SimpleNamespace(stdout=out, returncode=0)
        return SimpleNamespace(stdout="", returncode=0)

    def fake_adb(serial, *args, **kw):
        props = {"ro.serialno": "R5CT30ABCDE", "ro.build.version.release": "15"}
        return SimpleNamespace(stdout=props.get(args[-1], ""), returncode=0)

    monkeypatch.setattr(phone_mod.subprocess, "run", fake_run)
    monkeypatch.setattr(phone_mod, "adb", fake_adb)
    monkeypatch.delenv("ENVOY_TEST_PHONE", raising=False)
    found = phone_mod.discover()
    assert [p["serial"] for p in found] == ["R5CT30ABCDE", "192.168.4.20:41233"]
    assert found[0] == {"id": "phone-R5CT30ABCDE", "serial": "R5CT30ABCDE", "model": "SM S901U", "android": "15", "state": "device"}
    assert found[1]["state"] == "unauthorized"
    monkeypatch.setenv("ENVOY_TEST_PHONE", "emulator-5554")  # an emulator can stand in for a phone in tests
    assert "emulator-5554" in [p["serial"] for p in phone_mod.discover()]
    assert phone_id("adb-R5CT._adb-tls-connect._tcp") == "phone-adb-R5CT-adb-tls-connect-tcp"


# ---- routing -------------------------------------------------------------------------------------

PHONE = {"id": "phone-R5CT", "serial": "R5CT", "model": "Galaxy S22", "state": "device"}


def test_routing_follows_the_design_table():
    assert choose("com.skylark.air").device == "envoy-test"
    assert choose("com.amazon.mShop.android.shopping").device == "envoy-real"
    c = choose("com.skylark.air", request="check me in on my phone", phones=[PHONE])
    assert c.device == "phone-R5CT" and c.real_phone and "you asked" in c.reason
    assert choose("com.skylark.air", asked="phone", phones=[PHONE]).real_phone
    assert choose("com.skylark.air", phone_apps=["com.skylark.air"], phones=[PHONE]).real_phone  # set to run on your phone
    assert choose("com.ubercab.eats", phones=[PHONE]).real_phone  # refuses emulators
    # Your phone is needed but not there: never silently somewhere else when you asked for it.
    missing = choose("com.skylark.air", request="on my phone")
    assert missing.device is None and "isn't connected" in (missing.error or "")
    assert "allowed USB debugging" in (choose("com.ubercab.eats", phones=[{**PHONE, "state": "unauthorized"}]).error or "")
    # A setting falls back to the emulator (the app works there); an explicit choice wins.
    assert choose("com.skylark.air", phone_apps=["com.skylark.air"]).device == "envoy-test"
    assert choose("com.skylark.air", asked="emulator", phones=[PHONE]).device == "envoy-test"
    assert choose("com.skylark.air", phones=[PHONE]).device == "envoy-test"  # a connected phone isn't used by default


def test_on_my_phone_is_recognized_and_removed_from_the_goal():
    assert asks_for_phone("Check me in on my phone") and asks_for_phone("use my android phone to order")
    assert not asks_for_phone("what's my phone number?") and not asks_for_phone("call my phone")
    assert strip_phone_words("Check me in for my flight on my phone") == "Check me in for my flight"


# ---- asking before using your phone ---------------------------------------------------------------


class FakePool:
    def __init__(self) -> None:
        self.phones = {PHONE["id"]: PHONE}
        self.leases = {"envoy-test": Lease("envoy-test"), PHONE["id"]: Lease(PHONE["id"])}

    def refresh_phones(self):
        return list(self.phones.values())

    @staticmethod
    def avd_for(app):
        return "envoy-test"


def runner_with(pool) -> TaskRunner:
    bus = EventBus()
    r = TaskRunner(TaskStore(":memory:"), bus, pool, MemoryStore(":memory:"), SimpleNamespace(), adapter=SimpleNamespace())
    return r


def test_no_answer_is_never_a_yes_for_your_phone():
    async def scenario():
        r = runner_with(FakePool())
        r.approval_timeout_s = 0.2
        task = r.store.create("check in", "web")
        choice = await r._choose_phone(task["id"], "com.skylark.air", "phone")
        return r, task, choice
    r, task, choice = asyncio.run(scenario())
    assert choice == Choice("envoy-test", "you chose the emulator")  # SkyLark works on the emulator: it runs there instead
    steps = [s["text"] for s in r.store.steps(task["id"])]
    assert any("not used (no answer)" in s for s in steps)


def test_your_yes_lets_envoy_use_the_phone():
    async def scenario():
        r = runner_with(FakePool())
        r.loop = asyncio.get_running_loop()
        task = r.store.create("check in", "web")
        waiting = asyncio.create_task(r._choose_phone(task["id"], "com.skylark.air", "phone"))
        for _ in range(50):
            await asyncio.sleep(0.01)
            if r.store.get(task["id"])["waiting_for"] == "phone":
                break
        assert r.store.get(task["id"])["status"] == "needs_you"
        assert r.answer_phone(task["id"], True, "you on iPhone")
        return await waiting, r, task
    choice, r, task = asyncio.run(scenario())
    assert choice.device == "phone-R5CT" and choice.real_phone
    assert r.answer_phone(task["id"], True, "you") is False  # nothing is waiting any more


def test_a_phone_that_refuses_emulators_is_declined_not_rerouted():
    async def scenario():
        r = runner_with(FakePool())
        r.approval_timeout_s = 0.1
        task = r.store.create("order lunch", "web")
        return await r._choose_phone(task["id"], "com.ubercab.eats", None), r.store.get(task["id"])
    choice, task = asyncio.run(scenario())
    assert choice is None and task["status"] == "declined"


# ---- pausing when you touch the phone ------------------------------------------------------------


class FakeBanner:
    def __init__(self) -> None:
        self.st = {"paused": False, "reason": "", "changed_at": 0.0, "shown": True}
        self.calls: list[str] = []

    def state(self):
        return dict(self.st)

    def pause(self, reason):
        self.calls.append(f"pause:{reason}")
        self.st.update(paused=True, reason=reason, changed_at=time.time())

    def resume(self):
        self.calls.append("resume")
        self.st.update(paused=False, changed_at=time.time())

    def show(self, text):
        self.calls.append("show")

    def hide(self):
        self.calls.append("hide")


class FakePhone:
    def __init__(self) -> None:
        self.banner = FakeBanner()
        self.touches = SimpleNamespace(last_touch=0.0, touched_since=lambda t: self.touches.last_touch > t)
        self.front = "com.skylark.air"

    def foreground_package(self):
        return self.front

    async def launch(self, package, fresh=False):
        self.front = package


def test_a_touch_pause_or_another_app_hands_the_phone_to_you():
    async def scenario():
        bus = EventBus()
        bus.bind(asyncio.get_running_loop())
        pool = DevicePool(bus)
        did = "phone-R5CT"
        pool.leases[did] = Lease(did, task_id="task-1")
        dev = FakePhone()
        pool._devices[did] = dev
        watcher = asyncio.create_task(pool.watch(did, dev, "com.skylark.air", every_s=0.02))
        lease = pool.leases[did]
        await asyncio.sleep(0.1)
        assert not lease.user_control
        dev.touches.last_touch = time.time()  # you touch the phone
        await asyncio.sleep(0.1)
        touched = (lease.user_control, lease.reason, lease.agent_turn.is_set())
        dev.banner.resume()  # Resume on the phone's banner
        await asyncio.sleep(0.1)
        resumed = lease.user_control
        dev.banner.st.update(paused=True, reason="you pressed Pause on the phone", changed_at=time.time())
        await asyncio.sleep(0.1)
        paused = (lease.user_control, lease.reason)
        dev.banner.resume()
        await asyncio.sleep(0.1)
        lease.last_agent_call = time.time() - 10
        dev.front = "com.android.dialer"  # a call comes in: not something Envoy did
        await asyncio.sleep(0.1)
        other_app = (lease.user_control, lease.reason)
        pool.hand_back(did)  # you hand back with the call still on screen: the agent goes on from there
        await asyncio.sleep(0.15)
        after_hand_back = lease.user_control
        watcher.cancel()
        assert after_hand_back is False
        return touched, resumed, paused, other_app
    touched, resumed, paused, other_app = asyncio.run(scenario())
    assert touched == (True, "paused: you touched the phone", False)  # the agent's next call waits
    assert resumed is False
    assert paused == (True, "paused: you pressed Pause on the phone")
    assert other_app == (True, "paused: com.android.dialer came to the front on its own")


def test_the_agents_own_app_switch_does_not_pause():
    async def scenario():
        pool = DevicePool(EventBus())
        did = "phone-R5CT"
        pool.leases[did] = Lease(did, task_id="task-1")
        dev = FakePhone()
        pool._devices[did] = dev
        lease = pool.leases[did]
        watcher = asyncio.create_task(pool.watch(did, dev, "com.skylark.air", every_s=0.02))
        await asyncio.sleep(0.05)  # the watcher has seen SkyLark in front
        lease.last_agent_call = time.time()  # Envoy just tapped something that opens the browser
        dev.front = "com.android.chrome"
        await asyncio.sleep(0.15)
        watcher.cancel()
        return lease.user_control
    assert asyncio.run(scenario()) is False


LAUNCHER = "com.google.android.apps.nexuslauncher"


class Clock:
    """api.devices' clock, moved on by hand: "4 s later" without waiting 4 s."""

    def __init__(self) -> None:
        self.now = 1_800_000_000.0

    def time(self) -> float:
        return self.now


def _watch(monkeypatch, front: str, app: str | None, after_4s) -> tuple[bool, str]:
    """A task on `app` starts while `front` is in front of the phone; 4 s later (a model call before the agent's first
    step) `after_4s(dev, gated)` plays what happens next. Returns how the watcher left the phone: (yours?, why)."""
    clock = Clock()
    monkeypatch.setattr(devices_mod, "time", clock)

    async def scenario():
        pool = DevicePool(EventBus())
        did = "phone-R5CT"
        pool.leases[did] = Lease(did, task_id="task-1")
        dev = FakePhone()
        dev.front = front
        pool._devices[did] = dev
        lease = pool.leases[did]
        watcher = asyncio.create_task(pool.watch(did, dev, app, every_s=0.02))
        await asyncio.sleep(0.1)
        clock.now += 4
        await asyncio.sleep(0.1)
        if not lease.user_control:  # a paused phone holds the agent's next call until you hand it back
            await asyncio.wait_for(after_4s(dev, pool.gated(did, dev)), 1)
            await asyncio.sleep(0.1)
        watcher.cancel()
        return lease.user_control, lease.reason
    return asyncio.run(scenario())


def test_the_home_screen_in_front_when_envoy_starts_is_not_a_change(monkeypatch):
    """Found on the Pixel 5 (Oct 30, task-1030-155330-0eb0): the watcher expected the task's app from the start, so the
    home screen Envoy found paused the task ~2 s after you allowed it, before the agent's first action."""
    async def first_step(dev, gated):
        await gated.launch("com.ubercab", fresh=True)
    assert _watch(monkeypatch, LAUNCHER, "com.ubercab", first_step) == (False, "")


def test_an_app_envoy_has_no_name_for_already_in_front_is_not_a_change(monkeypatch):
    """task-1030-155655-7387: Uber, installed by hand on the phone, was in front; with no app to expect, it paused."""
    async def nothing(dev, gated):
        pass
    assert _watch(monkeypatch, "com.ubercab", None, nothing) == (False, "")


def test_another_app_coming_to_the_front_on_its_own_still_pauses(monkeypatch):
    async def a_call(dev, gated):
        dev.front = "com.android.dialer"  # not something Envoy did
    assert _watch(monkeypatch, "com.ubercab", "com.ubercab", a_call) \
        == (True, "paused: com.android.dialer came to the front on its own")


def test_an_app_replacing_the_home_screen_on_its_own_still_pauses(monkeypatch):
    async def a_message(dev, gated):
        dev.front = "com.whatsapp"
    assert _watch(monkeypatch, LAUNCHER, "com.ubercab", a_message) \
        == (True, "paused: com.whatsapp came to the front on its own")


# ---- screens with no tree ------------------------------------------------------------------------


def test_sam_output_is_parsed_into_boxes():
    text = ("<0f>0<|box;x1=161;y1=1022;x2=212;y2=1055;w=540;h=1200;c=0.75|><|mask;x=0;y=0;c=0.75;data=34,52,~!!|>,"
            "1<|box;x1=430;y1=313;x2=481;y2=365;w=540;h=1200;c=0.81|><|box;x1=5;y1=5;x2=5;y2=9;w=540;h=1200|>")
    boxes = parse_sam(text)
    assert len(boxes) == 2  # the empty box is dropped
    assert boxes[0][:2] == pytest.approx((161 / 540, 1022 / 1200)) and boxes[1][4] == pytest.approx(0.81)
    assert parse_sam("") == []


def _screen(seats: dict[str, tuple[int, int]], size=(720, 1280)) -> bytes:
    img = Image.new("RGB", size, (250, 248, 252))
    d = ImageDraw.Draw(img)
    for i, (label, (x, y)) in enumerate(seats.items()):
        d.rounded_rectangle((x, y, x + 80, y + 80), 8, fill=(220, 232, 245) if i % 2 else (189, 189, 189))
        d.text((x + 34, y + 30), label, fill=(0, 0, 0))
    d.ellipse((600, 1100, 680, 1180), fill=(200, 30, 60))  # one unique mark: a red pin
    d.line((610, 1140, 670, 1140), fill=(255, 255, 255), width=6)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _crop(png: bytes, box) -> str:
    img = Image.open(io.BytesIO(png)).crop(box)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def test_a_recorded_picture_is_found_only_when_it_is_unique():
    png = _screen({"A": (100, 400), "B": (200, 400), "C": (300, 400), "A ": (100, 600), "B ": (200, 600)})
    point, best, _ = match_crop(png, _crop(png, (594, 1094, 686, 1186)), (720, 1280))
    assert point is not None and abs(point[0] - 640) <= 4 and abs(point[1] - 1140) <= 4 and best > 0.95
    # Two identical-looking seats: no guess, so the executor asks grounding instead.
    twin = _screen({"A": (100, 400), "B": (200, 400), "A ": (100, 600)})  # same letter, same color
    point, best, second = match_crop(twin, _crop(twin, (96, 396, 184, 484)), (720, 1280))
    assert point is None and best - second < 0.04


def test_a_picture_recorded_on_another_phone_is_scaled_by_density():
    big = _screen({"x": (10, 10)}, size=(1080, 1920))  # recorded at 480 dpi
    crop = _crop(big, (594, 1094, 686, 1186))  # the red pin
    small = Image.open(io.BytesIO(big)).resize((720, 1280))  # the same screen on a 320 dpi phone
    buf = io.BytesIO()
    small.save(buf, format="PNG")
    point, best, _ = match_crop(buf.getvalue(), crop, (720, 1280), scale=320 / 480)
    assert point is not None and abs(point[0] - 427) <= 6 and abs(point[1] - 760) <= 6


def test_ncc_is_one_at_an_exact_copy():
    rng = np.random.default_rng(1)
    img = rng.random((60, 80)).astype(np.float32)
    s = ncc(img, img[20:30, 40:55].copy())
    assert s.shape == (51, 66) and np.unravel_index(int(np.argmax(s)), s.shape) == (20, 40) and s.max() == pytest.approx(1, abs=1e-3)


class FakeAdapter:
    """Grounding returns a box on the 0–1000 grid; the box-choosing call picks a number."""

    def __init__(self, box=(100, 300, 200, 400), pick=2):
        self.box, self.pick, self.calls = box, pick, []

    def call(self, job, content, **kw):
        self.calls.append(job)
        from models.schemas import ChooseOutput, GroundedBox, GroundingResult
        parsed = (GroundingResult(objects=[GroundedBox(object_name="t", x_min=self.box[0], y_min=self.box[1], x_max=self.box[2], y_max=self.box[3])])
                  if job == "grounding" else ChooseOutput(number=self.pick))
        return SimpleNamespace(parsed=parsed, cost_usd=0.001, cost_at_standard_usd=0.002, text="")

    def send(self, cfg, req, **kw):
        self.calls.append("sam")
        return SimpleNamespace(text="<|box;x1=10;y1=10;x2=60;y2=60;w=720;h=1280;c=0.9|><|box;x1=300;y1=500;x2=380;y2=580;w=720;h=1280;c=0.8|>",
                               cost_usd=0.0025, cost_at_standard_usd=0.0025)


def test_grounding_and_sam_return_device_pixels():
    png = _screen({"A": (100, 400)})
    g = Vision(FakeAdapter()).ground(png, "seat 10A", (1080, 2400))
    assert g.box == (108, 720, 216, 960) and g.point == (162, 840) and g.calls == 1
    s = Vision(FakeAdapter(pick=2)).sam_choose(png, "seat 10A", (1080, 2400), ("square button",))
    assert s.candidates == 2 and s.box == (450, 938, 570, 1088) and s.calls == 2  # one SAM phrase + the choice
    none = Vision(FakeAdapter(pick=0)).sam_choose(png, "seat 10A", (1080, 2400), ("square button",))
    assert none.box is None and "none" in none.detail
    assert Image.open(io.BytesIO(mark(Image.open(io.BytesIO(png)), parse_sam("<|box;x1=1;y1=1;x2=9;y2=9;w=10;h=10|>")))).size == (720, 1280)


def test_a_routine_step_on_a_drawn_target_replays_from_its_picture_then_grounding():
    from routines.executor import ExecConfig, RoutineExecutor
    from routines.model import Locator, Routine, Step, StepAction
    from devices.types import Action, ActionResult, Capabilities, ScreenState

    png = _screen({"A": (100, 400), "B": (200, 400)})

    class Dev:
        capabilities = Capabilities(False, False, True, 720, 1280, 320)

        def __init__(self):
            self.acts: list[Action] = []

        async def screenshot(self):
            return png

        async def act(self, a):
            self.acts.append(a)
            return ActionResult(ok=True, duration_ms=1)

    screen = ScreenState(package="com.skylark.air", activity="", elements=[], numbered=[], signature="", compact="", timestamp=0,
                         width=720, height=1280)
    step_pin = Step(id="pin", intent="tap the pin", pre=[], post=[], action=StepAction(kind="tap", target=Locator(
        visual="the red pin", crop=_crop(png, (594, 1094, 686, 1186)), density=320)))
    step_seat = Step(id="seat", intent="pick a seat", pre=[], post=[], action=StepAction(kind="tap", target=Locator(visual="seat {{seat}}")))
    dev, adapter = Dev(), FakeAdapter(box=(100, 300, 200, 400), pick=0)  # SAM's boxes aren't it: grounding finds it
    ex = RoutineExecutor(dev, adapter=adapter, config=ExecConfig(data_scope="test_app", contributor=True))  # type: ignore[arg-type]
    routine = Routine(routine="r", app="com.skylark.air", intent="x", steps=[step_pin, step_seat])
    ctx = SimpleNamespace(inputs={"seat": "10A"}, task_id="t", out=SimpleNamespace(model_calls=0, cost_usd=0.0, cost_at_standard_usd=0.0,
                                                                                   status="", approvals=[], patches=[]), routine=routine)
    sr = SimpleNamespace(rungs=[], climb=lambda *a: None, status="", detail="")
    assert asyncio.run(ex._visual_point(ctx, step_pin, screen, sr)) is not None and ctx.out.model_calls == 0  # its picture, no call
    point = asyncio.run(ex._visual_point(ctx, step_seat, screen, sr))
    assert point == (108, 448) and adapter.calls == ["sam", "sam", "choose", "grounding"] and ctx.out.model_calls == 4
    assert "looked for 'seat 10A' (sam→grounding" in sr.rungs[-1]
    # A picture of the recorded value (the red pin standing in for seat 10C) is never used for "seat {{seat}}".
    slotted = Step(id="seat2", intent="pick a seat", pre=[], post=[], action=StepAction(kind="tap", target=Locator(
        visual="seat {{seat}}", crop=_crop(png, (594, 1094, 686, 1186)), density=320)))
    adapter.calls.clear()
    assert asyncio.run(ex._visual_point(ctx, slotted, screen, sr)) == (108, 448) and adapter.calls[-1] == "grounding"
    secure = ScreenState(**{**screen.__dict__, "secure": True})
    assert asyncio.run(ex._visual_point(ctx, step_seat, secure, sr)) is None  # never a picture of a secure screen


def test_a_touch_stops_the_very_next_action():
    """Found on the stand-in phone: with only the 0.5 s watch loop, two routine steps (the last one irreversible) ran
    after the touch. The gated phone checks the touch watcher before each call."""
    async def scenario():
        pool = DevicePool(EventBus())
        did = "phone-R5CT"
        pool.leases[did] = Lease(did, task_id="task-1")
        dev = FakePhone()
        acted: list[str] = []

        async def act(a):
            acted.append(a)
            return "ok"
        dev.act = act  # type: ignore[attr-defined]
        pool._devices[did] = dev
        pool.start_watch(did, dev, "com.skylark.air")
        gated = pool.gated(did, dev)
        await gated.act("tap 1")
        dev.touches.last_touch = time.time() + 0.001  # your finger, a moment later
        blocked = asyncio.create_task(gated.act("Confirm check-in"))
        await asyncio.sleep(0.05)  # well inside the watch loop's 0.5 s
        waiting = not blocked.done() and acted == ["tap 1"] and pool.leases[did].user_control
        pool.hand_back(did)
        await asyncio.wait_for(blocked, 1)
        pool.stop_watch(did)
        return waiting, acted
    waiting, acted = asyncio.run(scenario())
    assert waiting and acted == ["tap 1", "Confirm check-in"]


def test_asking_for_your_phone_is_pushed_to_the_iphone(tmp_path):
    from api.push import Pusher, VapidKeys
    store = TaskStore(":memory:")
    task = store.create("Check me in for my flight", "web")
    pusher = Pusher(store, VapidKeys(tmp_path), "https://envoy-mac.example.ts.net:8443", send=lambda *a, **k: None)
    sent = []
    pusher.notify = lambda kind, title, body, path, **kw: sent.append((kind, title, body, path, kw.get("urgency")))  # type: ignore[method-assign]
    pusher.on_event({"type": "phone_requested", "task_id": task["id"], "device": "phone-R5CT", "model": "Galaxy S22"})
    assert sent == [("phone", "Use your Galaxy S22?", "Check me in for my flight", f"/?task={task['id']}", "high")]


# ---- apps that block emulators: the starting list, and Envoy setting "use my phone" after a bot check ----------------

SHOP = "com.example.shop"


def test_apps_known_to_block_emulators_are_data_and_go_to_your_phone():
    data = json.loads((Path(runner_mod.__file__).with_name("emulator_blocked.json")).read_text())["apps"]
    assert data == BLOCKS_EMULATOR and {"com.target.ui", "com.ubercab.eats", "com.chase.sig.android", "com.infonow.bofa"} <= set(data)
    assert EMULATOR_REFUSED["com.target.ui"] == "Target" and app_names()["bank of america"] == "com.infonow.bofa"
    assert app_for("What's my balance in Bank of America?") == "com.infonow.bofa"
    c = choose("com.target.ui", phones=[PHONE])
    assert c.real_phone and c.reason.startswith("Target blocks emulators")
    # No phone: said plainly, and nothing runs on an emulator.
    none = choose("com.chase.sig.android")
    assert none.device is None and none.error.startswith("Chase blocks emulators; it needs a real Android phone. Connect")
    # Asking for the emulator still wins: you may want to try it there.
    assert choose("com.target.ui", asked="emulator").device == "envoy-real"


def test_a_learned_block_counts_only_while_the_app_is_set_to_your_phone():
    learned = {SHOP: {"name": "Shop", "why": "showed a bot check (HSBlockActivity) on the emulator"}}
    c = choose(SHOP, phone_apps=[SHOP], learned=learned)
    assert c.device is None and c.error.startswith("Shop blocks emulators; it needs a real Android phone")  # no emulator fallback
    assert choose(SHOP, phone_apps=[SHOP], learned=learned, phones=[PHONE]).real_phone
    assert choose(SHOP, phone_apps=[], learned=learned).device == "envoy-real"  # unticked in Settings: undone
    assert blocks_emulator(SHOP, [], learned) is None
    assert choose(SHOP, phone_apps=[SHOP]).device == "envoy-real"  # a plain setting still falls back to the emulator


def test_an_app_envoy_does_not_know_yet_goes_to_the_real_app_emulator():
    assert choose(None, named="Wikipedia").device == "envoy-real"  # today it went to SkyLark's envoy-test
    assert choose(None).device == "envoy-test"
    assert app_for("In the Expedia app, check my flight to Denver") is None  # an app to install, not SkyLark for "flight"
    assert app_for("check my flight to Denver") == "com.skylark.air"
    assert app_for("In the Wikipedia app, look up Paris", {"wikipedia": "org.wikipedia"}) == "org.wikipedia"


def test_bot_checks_are_recognized_on_screen_and_in_hand_offs():
    def scr(activity, *labels):
        return SimpleNamespace(activity=activity, package=activity.rsplit(".", 1)[0], numbered=[SimpleNamespace(label=x) for x in labels])
    assert bot_check_reason(scr("com.target.ui.HSBlockActivity")) == "bot check (HSBlockActivity)"  # Target: an empty tree
    assert bot_check_reason(scr("com.shop.Main", "Press & Hold", "to confirm you are a human")) == "bot check (press & hold)"
    reviews = scr("com.google.android.apps.maps.Place", *[f"review {i}" for i in range(20)], "I saw unusual traffic here")
    assert bot_check_reason(reviews) is None and bot_check_reason(None) is None
    assert is_bot_check_handoff("bot check (CAPTCHA): press and hold") and is_bot_check_handoff("Human verification needed")
    assert not is_bot_check_handoff("sign-in needed: password field on screen") and not is_bot_check_handoff(None)


def page(activity: str, package: str, *labels: str) -> SimpleNamespace:
    """A screen as the runner reads it (bot checks, sign-ins, approvals)."""
    els = [SimpleNamespace(label=x, kind="Text", editable=False, visible=True, status_bar=False, package=package) for x in labels]
    return SimpleNamespace(package=package, activity=activity, numbered=els, elements=els, secure=False, has_password_field=False,
                           compact="\n".join(labels), signature=activity)


class AppPhone:
    """An emulator or phone with apps on it: `front` says what an app shows when it opens."""

    def __init__(self, front: dict[str, SimpleNamespace], packages: set[str]) -> None:
        self.front, self.packages = front, set(packages)
        self.screen = page("launcher.Home", "com.google.android.apps.nexuslauncher")
        self.adb = SimpleNamespace(shell=lambda cmd: "\n".join(f"package:{p}" for p in sorted(self.packages)
                                                                if p == str(cmd).split()[-1]))

    async def launch(self, app, fresh=False):
        self.screen = self.front.get(app) or page(f"{app}.Main", app, "Home")

    async def wait_until_settled(self):
        return self.screen

    async def observe(self, screenshot=False):
        return self.screen

    def frame(self, width, timeout=5):
        return Image.new("RGB", (width, width * 2))


class RoutePool:
    """envoy-real, and your phone when `phones` has it; nobody takes over (a hand-off times out)."""

    def __init__(self, emulator: AppPhone, phone: AppPhone | None = None) -> None:
        self.devs = {"envoy-real": emulator, **({PHONE["id"]: phone} if phone else {})}
        self.phones = {PHONE["id"]: PHONE} if phone else {}
        self.leases = {d: Lease(d) for d in self.devs}
        self.takeovers: list[str] = []

    def refresh_phones(self):
        return list(self.phones.values())

    def running(self):
        return {d: True for d in self.devs}

    async def device(self, did):
        return self.devs[did]

    def gated(self, did, device):
        return device

    def start_watch(self, *a, **k):
        pass

    def stop_watch(self, *a, **k):
        pass

    def hand_back(self, *a, **k):
        pass

    def request_takeover(self, avd, reason):
        self.takeovers.append(reason)

    async def wait_for_hand_back(self, avd, timeout_s):
        await asyncio.sleep(min(timeout_s, 0.05))
        return False

    @staticmethod
    def avd_for(app):
        return "envoy-real"


class FakeAgent:
    runs: list[dict] = []

    def __init__(self, device, **kw):
        self.device = device

    async def run(self, goal, *, task_id, memory=""):
        FakeAgent.runs.append({"task_id": task_id, "memory": memory, "device": self.device})
        return SimpleNamespace(status="done", result="1889", model_calls=1, cost_at_standard_usd=0.001)


async def _no_match(*a, **k):
    return SimpleNamespace(routine=None, inputs={}, model_calls=0)


def route_runner(monkeypatch, pool) -> TaskRunner:
    monkeypatch.setattr(runner_mod, "AgentRunner", FakeAgent)
    monkeypatch.setattr(runner_mod, "RoutineMatcher", lambda *a, **k: SimpleNamespace(match=_no_match))
    FakeAgent.runs = []
    r = TaskRunner(TaskStore(":memory:"), EventBus(), pool, MemoryStore(":memory:"), SimpleNamespace(), adapter=SimpleNamespace(),
                   takeover_timeout_s=0.05, approval_timeout_s=2)

    async def no_memory(*a, **k):
        return None
    r._remember = no_memory  # type: ignore[method-assign]
    return r


async def finish(r: TaskRunner, goal: str, *, answer_phone: bool | None = None, **kw) -> dict:
    """Start a task and wait for it, answering "use your phone?" the way you would."""
    r.loop = asyncio.get_running_loop()
    task = r.start(goal, "web", **kw)
    job = r.jobs[task["id"]]
    while not job.done():
        await asyncio.sleep(0.01)
        t = r.store.get(task["id"])
        if answer_phone is not None and t["waiting_for"] == "phone":
            r.answer_phone(task["id"], answer_phone, "you")
    await job
    return r.store.get(task["id"]) | {"steps": [s.get("text") or "" for s in r.store.steps(task["id"])]}


BLOCKED = page("com.example.shop.HSBlockActivity", SHOP)


def test_a_bot_check_on_the_emulator_sets_the_app_to_your_phone_and_says_so_plainly(monkeypatch):
    pool = RoutePool(AppPhone({SHOP: BLOCKED}, {SHOP}))
    r = route_runner(monkeypatch, pool)

    async def scenario():
        first = await finish(r, "find a lamp", app=SHOP)
        second = await finish(r, "find a desk", app=SHOP)
        return first, second
    first, second = asyncio.run(scenario())
    assert first["status"] == "needs_you" and first["result"].startswith("Shop blocks emulators; it needs a real Android phone")
    assert any("from now on it runs on your Android phone" in s for s in first["steps"])
    assert pool.takeovers and "it needs a real Android phone" in pool.takeovers[0]  # you can still try clearing it there
    assert r.store.setting("phone_apps") == [SHOP]  # Settings › Phones, set by Envoy
    learned = r.store.setting("phone_apps_learned")[SHOP]
    assert learned["why"] == "showed a bot check (HSBlockActivity) on the emulator" and learned["task"] == first["id"]
    # The next task doesn't try the emulator again: with no phone connected it says so and doesn't run.
    assert second["status"] == "failed" and second["detail"].startswith("Shop blocks emulators; it needs a real Android phone")
    assert FakeAgent.runs == []


def test_after_a_bot_check_the_task_moves_to_your_phone_when_you_say_yes(monkeypatch):
    phone = AppPhone({}, {SHOP})
    pool = RoutePool(AppPhone({SHOP: BLOCKED}, {SHOP}), phone)
    r = route_runner(monkeypatch, pool)
    asked: list[dict] = []
    r.bus.listeners.append(lambda ev: asked.append(ev) if ev["type"] == "phone_requested" else None)

    async def scenario():
        moved = await finish(r, "find a lamp", app=SHOP, answer_phone=True)
        later = await finish(r, "find a desk", app=SHOP, answer_phone=True)
        return moved, later
    moved, later = asyncio.run(scenario())
    assert moved["status"] == "done" and moved["device"] == PHONE["id"] and moved["result"] == "1889"
    assert "moving this task to your Galaxy S22" in moved["steps"] and "phone: your Galaxy S22 (you said yes)" in moved["steps"]
    assert [a["reason"] for a in asked] == ["Shop blocks emulators", "Shop blocks emulators"]  # one ask per task, never two
    assert FakeAgent.runs[0]["device"] is phone and FakeAgent.runs[0]["task_id"].endswith("-r1-phone")  # its own trace
    # The next task goes straight to your phone, still asking first; no answer would mean no.
    assert later["device"] == PHONE["id"] and any("Shop blocks emulators" in s for s in later["steps"])


def test_a_hand_off_for_a_bot_check_learns_but_a_websites_check_in_a_browser_does_not(monkeypatch):
    chrome = "com.android.chrome"

    class HandsOff(FakeAgent):
        async def run(self, goal, *, task_id, memory=""):
            return SimpleNamespace(status="handoff", result="bot check (CAPTCHA): the user must solve it", model_calls=2, cost_at_standard_usd=0.002)

    pool = RoutePool(AppPhone({SHOP: page("com.example.shop.Main", SHOP, "Deals"), chrome: page("com.android.chrome.Main", chrome, "x")}, {SHOP, chrome}))
    r = route_runner(monkeypatch, pool)
    monkeypatch.setattr(runner_mod, "AgentRunner", HandsOff)

    async def scenario():
        return await finish(r, "find a lamp", app=SHOP), await finish(r, "search the web in Chrome", app=chrome)
    shop, web = asyncio.run(scenario())
    assert "it needs a real Android phone" in shop["result"] and r.store.setting("phone_apps") == [SHOP]
    assert web["status"] == "needs_you" and chrome not in r.store.setting("phone_apps")  # Chrome itself doesn't block emulators


def test_settings_show_what_envoy_set_and_unticking_undoes_it(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("MCP_BEARER_TOKEN", "mcp-test-token")
    monkeypatch.setenv("ENVOY_ALLOWED_HOSTS", "testserver")
    monkeypatch.setattr("api.app.API_DIR", tmp_path)
    monkeypatch.setattr("api.push.LOG", tmp_path / "push.jsonl")
    monkeypatch.setattr("api.app.LOGS", tmp_path)
    monkeypatch.setattr("api.devices.discover", lambda: [])  # never looks at a real phone
    monkeypatch.setattr(DevicePool, "running", lambda self: {})
    from api.app import build, session_token
    from routines.store import RoutineStore
    tasks = TaskStore(":memory:")
    tasks.set_setting("phone_apps", [SHOP])
    tasks.set_setting("phone_apps_learned", {SHOP: {"name": "Shop", "why": "showed a bot check (press & hold) on the emulator"}})
    app, ctx = build("demo", memory=MemoryStore(":memory:"), tasks=tasks, routines=RoutineStore(tmp_path / "routines"),
                     adapter=SimpleNamespace(api_key="k", calls=[]))
    me = {"Authorization": f"Bearer {session_token()}"}
    with TestClient(ctx.asgi) as c:
        got = c.get("/api/settings/phones", headers=me).json()
        assert SHOP in got["apps"] and got["learned"][SHOP]["why"].startswith("showed a bot check") and got["names"][SHOP] == "Shop"
        assert got["emulator_refused"]["com.target.ui"] == "Target"
        assert c.post("/api/settings/phones", json={"phone_apps": []}, headers=me).json() == {"phone_apps": [], "learned": {}}
        assert tasks.setting("phone_apps_learned") == {}
        # Only your own session answers "use your phone?": not MCP's token.
        t = tasks.create("find a lamp", "web")
        assert c.post(f"/api/tasks/{t['id']}/phone", json={"allow": True}, headers={"Authorization": "Bearer mcp-test-token"}).status_code == 401


# ---- installing an app the emulator doesn't have, from the Play Store -------------------------------------------------

STORE_SCREENS = Path(__file__).parent / "screens"
WIKI = "org.wikipedia"


def store_page(name: str):
    return build_state((STORE_SCREENS / f"playstore_{name}.xml").read_text(), "com.android.vending",
                       "com.android.vending.AssetBrowserActivity", 1080, 2400)


def test_play_store_pages_are_read_without_a_model():
    free, paid, have, busy, nope, search = (read_listing(store_page(n)) for n in ("free", "paid", "installed", "installing", "incompatible", "search"))
    assert (free.state, free.title, free.button.label) == ("free", "Wikipedia", "Install")
    assert (paid.state, paid.price, paid.button) == ("paid", "$6.99", None)  # the price button is never a target
    assert (have.state, busy.state) == ("installed", "installing")
    assert nope.state == "incompatible" and nope.detail == "Your device isn't compatible with this version."
    card = pick_result(store_page("search"), "wikipedia")
    assert card.label.startswith("Wikipedia Wikimedia Foundation") and card.in_list  # not the search box that repeats it
    assert pick_result(store_page("search"), "Spotify") is None
    assert guess_installed("Wikipedia", {WIKI, "com.android.chrome"}) == WIKI and guess_installed("Maps", {"a.maps", "b.maps"}) is None
    assert guess_installed("Messages", {"com.google.android.apps.messaging"}) == "com.google.android.apps.messaging"  # not a search


def test_the_app_a_request_names():
    assert app_named_in("In the Wikipedia app, search for Eiffel Tower") == "Wikipedia"
    assert app_named_in("In AccuWeather, what's tomorrow's high?") == "AccuWeather"
    assert app_named_in("install Duolingo") == "Duolingo" and app_named_in("Download Spotify and play some jazz") == "Spotify"
    assert app_named_in("in the Google Translate app, translate hello") == "Google Translate"
    for g in ("in my banking app, check my balance", "how do I install a ceiling fan?", "In general, what is x", "what's on my calendar"):
        assert app_named_in(g) is None, g


class PlayPhone:
    """envoy-real with the Play Store: real captured pages; Install makes the package appear a few looks later."""

    def __init__(self, *, packages=(), account=True, paid=False, incompatible=False, after=2, search="search", installs=None):
        self.packages, self.account, self.after = set(packages) | {"com.android.vending"}, account, after
        self.details = "paid" if paid else "incompatible" if incompatible else "free"
        self.search = search
        self.installs = installs or {}  # an Install button's bounds → the package it installs (search results)
        self.screen, self.taps, self.opened, self.target, self.looks = page("launcher.Home", "launcher"), [], [], None, 0
        self.adb = SimpleNamespace(shell=self.shell)

    def shell(self, cmd):
        c = cmd if isinstance(cmd, str) else " ".join(cmd)
        if c.startswith("pm list packages"):
            want = c[len("pm list packages"):].strip()
            return "\n".join(f"package:{p}" for p in sorted(self.packages) if not want or p == want)
        if c.startswith("dumpsys account"):
            return "2" if self.account else "0"
        if c.startswith("cmd package query-activities"):
            return "\n".join(f"  {p}/.Main" for p in sorted(self.packages))
        if c.startswith("am start"):
            uri = cmd[cmd.index("-d") + 1]
            self.opened.append(uri)
            self.screen = store_page(self.search if "search?" in uri else self.details)
        return ""

    async def wait_until_settled(self):
        if self.target and self.target not in self.packages:
            self.looks += 1
            if self.looks >= self.after:
                self.packages.add(self.target)
                self.screen = store_page("installed")
        return self.screen

    observe = wait_until_settled

    async def act(self, a):
        if a.kind == "tap_point":  # a result's name: its page opens
            self.taps.append(f"point {a.x},{a.y}")
            self.screen = store_page(self.details)
            return SimpleNamespace(ok=True)
        e = self.screen.element(a.element)
        label = e.label
        self.taps.append(label)
        if label == "Install":
            self.target = self.installs.get(e.bounds, WIKI)
            self.screen = store_page("installing")
        elif label.startswith("Wikipedia"):
            self.screen = store_page("free")
        return SimpleNamespace(ok=True)

    async def launch(self, app, fresh=False):
        self.screen = page(f"{app}.Main", app, "Search Wikipedia")

    def frame(self, width, timeout=5):
        return Image.new("RGB", (width, width * 2))


def installer(dev, *, approve=False, handed_back=False, also=None):
    steps, asked, hand_offs = [], [], []

    class Approver:
        def request(self, req):
            asked.append(req)
            return ApprovalDecision(approve, by="you")

    async def hand_off(why):
        hand_offs.append(why)
        if also:
            also()
        return handed_back
    inst = Installer(dev, step=steps.append, approver=Approver(), hand_off=hand_off, task_id="t1", goal="g", poll_s=0, wait_s=0, timeout_s=5)
    return inst, SimpleNamespace(steps=steps, asked=asked, hand_offs=hand_offs)


def test_a_free_app_is_installed_by_its_package_or_by_the_name_the_request_gives():
    dev = PlayPhone()
    inst, log = installer(dev)
    got = asyncio.run(inst.ensure(WIKI, "Wikipedia"))
    assert (got.status, got.package, got.title) == ("installed", WIKI, "Wikipedia") and dev.taps == ["Install"]
    assert dev.opened == [f"market://details?id={WIKI}"] and any(s["text"].startswith("installed Wikipedia in") for s in log.steps)
    dev = PlayPhone()
    got = asyncio.run(installer(dev)[0].ensure(None, "Wikipedia"))  # by name: the result's own Install, then what arrived
    assert (got.status, got.package, got.title) == ("installed", WIKI, "Wikipedia") and dev.taps == ["Install"]
    assert dev.opened == ["market://search?q=Wikipedia&c=apps"]
    # Already there: nothing opens.
    dev = PlayPhone(packages={WIKI})
    assert asyncio.run(installer(dev)[0].ensure(WIKI)).status == "already" and asyncio.run(installer(dev)[0].ensure(None, "Wikipedia")).package == WIKI
    assert dev.opened == []


def test_a_sponsored_look_alike_is_never_installed():
    """envoy-real, Oct 28: searching "Google Translate" showed a sponsored translator first, with its own Install button.
    The first build tapped it. Only the result that is the app counts, and only its own button."""
    ads = store_page("search_ads")
    assert read_listing(ads).state == "unknown"  # a results page is not an app's page: no Install to take from it
    for q in ("Google Translate", "Translate"):
        card = pick_result(ads, q)
        assert card_title(ads, card) == "Google Translate" and card_listing(ads, card).button.bounds == (831, 1033, 1017, 1159)
    ad, real = (831, 405, 1017, 531), (831, 1033, 1017, 1159)
    translate, look_alike = "com.google.android.apps.translate", "com.newgeneration.translator"
    dev = PlayPhone(search="search_ads", installs={ad: look_alike, real: translate})
    got = asyncio.run(installer(dev)[0].ensure(None, "Google Translate"))
    assert (got.status, got.package, got.title) == ("installed", translate, "Google Translate") and look_alike not in dev.packages
    assert dev.opened == ["market://search?q=Google%20Translate&c=apps"]


def test_a_result_without_its_own_button_is_opened_by_its_name():
    dev = PlayPhone()
    bare = store_page("search")
    bare.numbered[2].label = ""  # the Wikipedia result's Install, as for a result the Play Store shows collapsed
    real_open = PlayPhone.shell

    def shell(self, cmd):
        out = real_open(self, cmd)
        if "search?" in " ".join(cmd if isinstance(cmd, list) else [cmd]):
            self.screen = bare
        return out
    dev.shell = shell.__get__(dev)  # type: ignore[method-assign]
    dev.adb = SimpleNamespace(shell=dev.shell)
    got = asyncio.run(installer(dev)[0].ensure(None, "Wikipedia"))
    x1, y1, x2, y2 = bare.numbered[1].bounds
    assert dev.taps == [f"point {x1 + (x2 - x1) // 4},{y1 + 60}", "Install"]  # its name, never its middle (a question box)
    assert (got.status, got.package, got.title) == ("installed", WIKI, "Wikipedia")


def test_a_paid_app_asks_first_and_envoy_never_pays():
    dev = PlayPhone(paid=True)
    inst, log = installer(dev)
    got = asyncio.run(inst.ensure("com.mojang.minecraftpe"))
    assert got.status == "declined" and "$6.99" in got.detail and dev.taps == []  # the price is never tapped
    assert log.asked[0].description == "Minecraft: Dream it, Build it! costs $6.99 on the Play Store: buy it yourself?" and log.asked[0].origin == "install"
    # A yes hands the phone to you to buy it; Envoy carries on once it's there.
    dev = PlayPhone(paid=True)
    inst, log = installer(dev, approve=True, handed_back=True, also=lambda: dev.packages.add("com.mojang.minecraftpe"))
    got = asyncio.run(inst.ensure("com.mojang.minecraftpe"))
    assert got.status == "bought" and log.hand_offs == ["buy Minecraft: Dream it, Build it! ($6.99) in the Play Store yourself"]
    assert dev.taps == []


def test_an_app_the_emulator_cant_have_or_no_google_account_stops_and_says_why():
    got = asyncio.run(installer(PlayPhone(incompatible=True))[0].ensure("com.ubercab.eats"))
    assert got.status == "incompatible" and "isn't compatible" in got.detail
    dev = PlayPhone(account=False)
    inst, log = installer(dev)
    got = asyncio.run(inst.ensure(WIKI))
    assert got.status == "no_account" and log.hand_offs[0] == "sign-in needed: the Play Store has no Google account on this phone" and dev.opened == []


def test_a_task_naming_an_app_the_emulator_lacks_installs_it_and_carries_on(monkeypatch):
    dev = PlayPhone()
    r = route_runner(monkeypatch, RoutePool(AppPhone({}, set())))
    r.pool.devs["envoy-real"] = dev
    real_init = Installer.__init__
    monkeypatch.setattr(Installer, "__init__", lambda self, *a, **k: real_init(self, *a, **{**k, "poll_s": 0, "wait_s": 0}))
    goal = "In the Wikipedia app, search for Eiffel Tower and tell me the year it opened."

    async def scenario():
        return await finish(r, goal), await finish(r, goal)
    first, second = asyncio.run(scenario())
    assert first["status"] == "done" and first["app"] == WIKI and first["device"] == "envoy-real"
    assert "Wikipedia isn't on this phone: looking for it in the Play Store" in first["steps"]
    assert FRESH_INSTALL.format(name="Wikipedia") in FakeAgent.runs[0]["memory"]  # the agent knows to expect first-run screens
    assert r.store.setting("apps_installed")[WIKI]["names"] == ["wikipedia"]
    # The next request that names it goes straight to it: no search, no install.
    assert second["status"] == "done" and second["app"] == WIKI and len(dev.opened) == 1
    assert FRESH_INSTALL.format(name="Wikipedia") not in FakeAgent.runs[1]["memory"]


def test_a_paid_app_ends_the_task_declined_when_you_say_no(monkeypatch):
    dev = PlayPhone(paid=True)
    r = route_runner(monkeypatch, RoutePool(dev))
    r.approval_timeout_s = 0.3  # no answer is a no

    async def scenario():
        return await finish(r, "how many worlds can I make?", app="com.mojang.minecraftpe")
    task = asyncio.run(scenario())
    assert task["status"] == "declined" and "costs $6.99; Envoy installs only free apps (no answer)" in task["detail"]
    assert FakeAgent.runs == [] and dev.taps == []
    assert r.store.approvals(task_id=task["id"])[0]["status"] == "expired"
