"""Before I start (api/preflight.py), and the two runner changes the final features build on: `runner.start(...,
phone_ok=)`, so an offer you accepted for your phone isn't asked again, and Instagram as an app a goal can name."""

from __future__ import annotations

import asyncio
import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_phase6 import PHONE, SHOP, BLOCKED, AppPhone, RoutePool, finish, route_runner

import api.runner as runner_mod
from api.crossapp import apps_in
from api.devices import Lease
from api.events import EventBus
from api.preflight import _doing, check
from api.runner import APP_NAMES, TaskRunner, app_for
from api.store import TaskStore
from memory.store import MemoryStore
from routines.store import RoutineStore

INSTAGRAM = "com.instagram.android"
TARGET, DOORDASH, AMAZON, SKYLARK = "com.target.ui", "com.dd.doordash", "com.amazon.mShop.android.shopping", "com.skylark.air"
LIBRARY = Path(__file__).resolve().parents[2] / "data" / "routines"
CHECK_IN = "skylark_check_in_flight"
PIXEL = {"id": "phone-0A1B", "serial": "0A1B", "model": "Pixel 5", "state": "device"}

# ---- phone_ok: your yes to an offer covers the phone it named ----------------------------------------


def _asks(r) -> list[dict]:
    asked: list[dict] = []
    r.bus.listeners.append(lambda ev: asked.append(ev) if ev["type"] == "phone_requested" else None)
    return asked


def test_phone_ok_runs_on_that_phone_without_asking_again(monkeypatch):
    r = route_runner(monkeypatch, RoutePool(AppPhone({}, {SHOP}), AppPhone({}, {SHOP})))
    asked = _asks(r)
    done = asyncio.run(finish(r, "find a lamp", app=SHOP, phone=PHONE["id"], phone_ok=PHONE["id"]))
    assert done["status"] == "done" and done["device"] == PHONE["id"]
    assert asked == [] and "phone: your Galaxy S22 (you said yes)" in done["steps"]
    assert r.phone_allowed == {}  # the yes covered this task only


def test_without_phone_ok_the_phone_is_asked_for_as_before(monkeypatch):
    r = route_runner(monkeypatch, RoutePool(AppPhone({}, {SHOP}), AppPhone({}, {SHOP})))
    asked = _asks(r)
    done = asyncio.run(finish(r, "find a lamp", app=SHOP, phone=PHONE["id"], answer_phone=True))
    assert done["status"] == "done" and done["device"] == PHONE["id"]
    assert [a["device"] for a in asked] == [PHONE["id"]]
    assert "your Galaxy S22: allowed by you" in done["steps"] and "phone: your Galaxy S22 (you said yes)" not in done["steps"]


def test_phone_ok_for_another_phone_still_asks(monkeypatch):
    r = route_runner(monkeypatch, RoutePool(AppPhone({}, {SHOP}), AppPhone({}, {SHOP})))
    asked = _asks(r)
    done = asyncio.run(finish(r, "find a lamp", app=SHOP, phone=PHONE["id"], phone_ok="phone-SOMEOTHER", answer_phone=False))
    assert [a["device"] for a in asked] == [PHONE["id"]]  # routing picked your Galaxy; the yes named another phone
    assert done["device"] == "envoy-real" and "running on the emulator (envoy-real) instead" in done["steps"]
    assert r.phone_allowed == {}


def test_phone_ok_is_unused_and_dropped_when_the_task_runs_on_an_emulator(monkeypatch):
    r = route_runner(monkeypatch, RoutePool(AppPhone({}, {SHOP}), AppPhone({}, {SHOP})))
    asked = _asks(r)
    done = asyncio.run(finish(r, "find a lamp", app=SHOP, phone_ok=PHONE["id"]))
    assert done["status"] == "done" and done["device"] == "envoy-real" and asked == []
    assert r.phone_allowed == {}


# ---- Instagram is an app a goal can name ---------------------------------------------------------


def test_instagram_is_a_known_app_and_nothing_else_moves():
    assert APP_NAMES["instagram"] == INSTAGRAM
    assert app_for("Post the newest video in my phone's gallery to Instagram as a reel") == INSTAGRAM
    assert app_for("check the comments on my instagram post") == INSTAGRAM
    assert apps_in("post it on Instagram") == {INSTAGRAM}
    # Goals that only look like it don't resolve to it; the apps they named before are unchanged.
    assert app_for("send the instagrammable photo to Mom") is None
    assert app_for("find a lamp on Amazon") == APP_NAMES["amazon"] and app_for("check my flight to Denver") == "com.skylark.air"
    assert app_for("In the Wikipedia app, look up Paris", {"wikipedia": "org.wikipedia"}) == "org.wikipedia"


# ---- Before I start: check() -----------------------------------------------------------------------


class Pool:
    """Phones as last seen (check() never looks again), and the emulators' leases."""

    def __init__(self, *phones: dict) -> None:
        self.phones = {p["id"]: p for p in phones}
        self.leases = {d: Lease(d) for d in ("envoy-test", "envoy-real", *self.phones)}

    def refresh_phones(self):
        return list(self.phones.values())


@pytest.fixture
def lib(tmp_path) -> RoutineStore:
    """A routine library with SkyLark's check-in (v1, its irreversible step is "Confirm check-in") and no runs yet."""
    shutil.copytree(LIBRARY / CHECK_IN, tmp_path / "routines" / CHECK_IN)
    return RoutineStore(tmp_path / "routines")


def make_runner(lib: RoutineStore | None = None, *phones: dict) -> TaskRunner:
    return TaskRunner(TaskStore(":memory:"), EventBus(), Pool(*phones), MemoryStore(":memory:"), lib or SimpleNamespace(),
                      adapter=SimpleNamespace())


def past(r: TaskRunner, app: str, device: str, *steps: dict, when: str = "2026-10-27 18:00") -> dict:
    """A task that ran earlier, with the steps it wrote."""
    t = r.store.create("an earlier task", "web", app=app, device=device, status="done")
    for s in steps:
        r.store.add_step(t["id"], s)
    r.store.db.execute("UPDATE tasks SET created_at=? WHERE id=?", (datetime.strptime(when, "%Y-%m-%d %H:%M").timestamp(), t["id"]))
    return t


SIGN_IN = {"kind": "handoff", "text": "sign-in needed: password field on screen: take over, then hand back"}


def texts(lines: list[dict], kind: str | None = None) -> list[str]:
    return [ln["text"] for ln in lines if kind is None or ln["kind"] == kind]


def test_an_app_that_blocks_emulators_with_and_without_your_phone():
    with_phone = check(make_runner(None, PIXEL), "check the price of AirPods at Target")
    assert {"kind": "device", "text": "Target blocks emulators: I'll ask to use your Pixel 5.", "level": "warn"} in with_phone
    covered = check(make_runner(None, PIXEL), "check the price of AirPods at Target", phone_ok=PIXEL["id"])
    assert texts(covered, "device") == ["Target blocks emulators, so I'll use your Pixel 5 (you said yes)."]
    assert covered[0]["level"] == "info"
    without = check(make_runner(), "check the price of AirPods at Target")
    assert without[0] == {"kind": "blocked", "text": "Target needs your Android phone, and it isn't connected.", "level": "stop"}
    locked = check(make_runner(None, {**PIXEL, "state": "unauthorized"}), "price of AirPods at Target")
    assert texts(locked, "blocked") == ["Target needs your Android phone, but it hasn't allowed USB debugging yet."]


def test_your_phone_asked_for_set_for_the_app_or_not_there():
    r = make_runner(None, PIXEL)
    assert texts(check(r, "check me in on my phone"), "device") == ["You asked for your phone: I'll check with you before using your Pixel 5."]
    assert texts(check(make_runner(), "check me in on my phone"), "blocked") == ["You asked for your phone, and it isn't connected."]
    r.store.set_setting("phone_apps", [INSTAGRAM])
    assert texts(check(r, "post my reel to Instagram"), "device") == ["Instagram is set to run on your phone: I'll ask before using your Pixel 5."]
    alone = make_runner()
    alone.store.set_setting("phone_apps", [INSTAGRAM])
    assert texts(check(alone, "post my reel to Instagram"), "device") == [
        "Instagram is set to run on your phone, which isn't connected: I'll use envoy-real instead."]
    assert texts(check(r, "post my reel to Instagram", phone=PIXEL["id"], phone_ok=PIXEL["id"]), "device") == ["I'll use your Pixel 5 (you said yes)."]
    # The default (an emulator) says nothing about where it runs.
    assert texts(check(r, "find a lamp on Amazon"), "device") == [] and texts(check(r, "find a lamp on Amazon"), "blocked") == []


def test_a_sign_in_seen_last_time_on_that_phone_is_said_and_one_since_is_not():
    r = make_runner()
    past(r, DOORDASH, "envoy-real", {"kind": "note", "text": "phone: envoy-real"}, SIGN_IN)
    assert {"kind": "signin", "text": "DoorDash asked you to sign in on envoy-real last time (Oct 27).", "level": "warn"} in check(
        r, "Get my usual from Thai Basil on DoorDash")
    past(r, DOORDASH, "envoy-real", {"kind": "finish", "text": "done"}, when="2026-10-28 09:00")  # signed in since: no ask then
    assert texts(check(r, "Get my usual from Thai Basil on DoorDash"), "signin") == []
    # Only that phone's history, and only the app's own sign-in (not the Play Store's).
    past(r, AMAZON, "envoy-real", {"kind": "handoff", "text": "sign-in needed: the Play Store asks you to sign in: take over, then hand back"})
    past(r, SKYLARK, "envoy-real", SIGN_IN)
    assert texts(check(r, "find a lamp on Amazon"), "signin") == [] and texts(check(r, "what's my gate?"), "signin") == []
    past(r, SKYLARK, "envoy-test", {"kind": "handoff", "text": "sign-in needed: password field on screen"}, when="2026-10-28 20:00")
    assert texts(check(r, "what's my gate?"), "signin") == ["SkyLark asked you to sign in on envoy-test last time (Oct 28)."]


def test_a_sign_in_on_your_phone_names_your_phone():
    r = make_runner(None, PIXEL)
    past(r, TARGET, PIXEL["id"], SIGN_IN)
    assert "Target asked you to sign in on your Pixel 5 last time (Oct 27)." in texts(check(r, "price of AirPods at Target"), "signin")


def test_install_only_when_envoy_knows_without_asking_the_phone():
    r = make_runner()
    assert texts(check(r, "find a lamp on Amazon"), "install") == []  # known, never seen missing: nothing to say
    past(r, AMAZON, "envoy-real", {"kind": "note", "text": "Amazon isn't on this phone: opening it in the Play Store"},
         {"kind": "note", "text": "the Play Store asked to finish account setup (a payment method): skipped"})
    assert texts(check(r, "find a lamp on Amazon"), "install") == [
        "Amazon wasn't on envoy-real last time: I'll install it from the Play Store (free apps only)."]
    past(r, AMAZON, "envoy-real", {"kind": "note", "text": "Amazon isn't on this phone: opening it in the Play Store"},
         {"kind": "note", "text": "installed Amazon Shopping in 41 s (finding it 6 s, downloading 35 s)"}, when="2026-10-28 10:00")
    assert texts(check(r, "find a lamp on Amazon"), "install") == []
    assert texts(check(r, "In the Wikipedia app, look up Paris"), "install") == [
        "I haven't used Wikipedia on envoy-real before: if it isn't there, I'll install it from the Play Store (free apps only)."]
    r.store.set_setting("apps_installed", {"org.wikipedia": {"name": "Wikipedia", "names": ["wikipedia"], "at": 1}})
    assert texts(check(r, "In the Wikipedia app, look up Paris"), "install") == []
    r.install_apps = False
    assert texts(check(r, "In the Duolingo app, start a lesson"), "install") == []


def test_money_always_asks_and_other_goals_say_nothing_they_cant_know():
    r = make_runner()
    assert texts(check(r, "Buy the $24.99 desk lamp on Amazon"), "approval") == ["The payment step will need your OK."]
    assert texts(check(r, "Order my usual latte from Starbucks"), "approval") == ["Any payment will need your OK."]
    assert texts(check(r, "find a lamp on Amazon", source="web"), "approval") == []
    assert texts(check(r, "check my order status on Amazon", source="web"), "approval") == []
    # An agent task from Muse or a trigger: anything irreversible waits for you (the rules, whatever the steps turn out to be).
    assert texts(check(r, "Post the newest video to Instagram as a reel", source="mcp"), "approval") == [
        "Anything that can't be undone will wait for your OK."]
    assert texts(check(r, "what's on my calendar today?", source="mcp"), "approval") == []


def test_a_routines_irreversible_step_as_the_approval_rules_will_see_it(lib):
    r = make_runner(lib)
    goal = "Check me in for my flight to Chicago"
    line = lambda **kw: texts(check(r, goal, routine=CHECK_IN, **kw), "approval")  # noqa: E731
    assert line(source="web") == ["Confirming check-in will go ahead: you asked for it."]
    assert line(source="iphone", request="check me in") == ["Confirming check-in will go ahead: you asked for it."]
    assert line(source="mcp") == ["Confirming check-in will wait for your OK."]
    assert line(source="trigger:check in 24h before") == ["Confirming check-in will wait for your OK."]
    assert line(source="web", request="what's my gate?") == ["Confirming check-in will need your OK."]  # not what you asked
    r.store.set_setting("approval_rules", {"routines": {CHECK_IN: "always"}})
    assert line(source="web") == ["Confirming check-in will need your OK."]
    r.store.set_setting("approval_rules", {"routines": {CHECK_IN: "never"}})
    assert line(source="trigger:check in 24h before") == ["Confirming check-in will go ahead: you set this routine to run without asking."]


def test_a_routine_step_that_pays_or_publishes(lib):
    r = make_runner(lib)
    rt = lib.get(CHECK_IN)
    rt.steps[-1].action.target.text = "Place order"
    assert texts(check(r, "Get my usual", routine=rt, source="web"), "approval") == ["The payment step will need your OK."]
    rt.steps[-1].action.target.text = "Share"  # a "Share" button under a "Post…" request: the request doesn't name it
    assert texts(check(r, "Post my video as a reel", routine=rt, source="web", request="Post my video as a reel with this caption:"),
                 "approval") == ["Sharing will need your OK."]


def test_button_labels_are_said_as_what_envoy_will_be_doing():
    assert [_doing(x) for x in ("Confirm check-in", "Place order", "Submit", "Share", "Post reel", "Pay $18.42", "OK", "Book SL 482")] == [
        "Confirming check-in", "Placing order", "Submitting", "Sharing", "Posting reel", "Paying $18.42", "Tapping “OK”", "Booking SL 482"]


def test_a_routine_says_its_usual_time_and_model_calls(lib):
    r = make_runner(lib)
    said = f"Using your routine “{lib.get(CHECK_IN).intent}”"  # its name in words: no id, no version
    idx = lib.index(CHECK_IN)
    idx["runs"] = []  # no runs yet: it gives the time from its checking replay
    lib._write_index(CHECK_IN, idx)
    assert texts(check(r, "check me in", routine=CHECK_IN), "routine") == [f"{said}: 3 s when I tested it, no model calls."]
    run = {"time": "2026-10-28 17:29:21", "kind": "run", "version": 1, "status": "done", "rung": 0, "patches": 0}
    idx["runs"] = [{**run, "task_id": f"t{i}-r1", "duration_s": d, "model_calls": 0} for i, d in enumerate((8.7, 9.2, 30.0, 9.1))]
    idx["runs"].append({**run, "task_id": "tx-r1", "status": "failed", "duration_s": 300.0, "model_calls": 4})  # failures don't count
    lib._write_index(CHECK_IN, idx)
    assert texts(check(r, "check me in", routine=CHECK_IN), "routine") == [f"{said}: usually 9 s, no model calls."]
    idx["runs"] = [{**run, "task_id": f"t{i}-r1", "duration_s": 12.0, "model_calls": c} for i, c in enumerate((1, 1, 0))]
    lib._write_index(CHECK_IN, idx)
    assert texts(check(r, "check me in", routine=CHECK_IN), "routine") == [f"{said}: usually 12 s, about 1 model call."]
    assert texts(check(r, "check me in", routine="no_such_routine"), "routine") == []


def test_only_app_notes_that_predict_an_obstacle(monkeypatch):
    monkeypatch.delenv("ENVOY_APP_NOTES", raising=False)
    r = make_runner()
    ref = {"task": "t1", "step": 3}
    r.app_notes.add(DOORDASH, "A location permission prompt appears on the first launch", ref)
    r.app_notes.add(DOORDASH, "Search results list stores by delivery time", ref)
    r.app_notes.add(DOORDASH, "The first result can be an ad labeled Sponsored", ref)
    r.app_notes.add(DOORDASH, "A pop-up offering DashPass shows after the cart", ref)
    r.app_notes.add(AMAZON, "A bot check can appear after many searches", ref)
    got = texts(check(r, "Get my usual from Thai Basil on DoorDash"), "app_note")
    assert len(got) == 2 and all(t.startswith("From earlier runs: ") for t in got)
    assert not any("delivery time" in t for t in got) and not any("bot check" in t for t in got)  # another app's note isn't shown
    monkeypatch.setenv("ENVOY_APP_NOTES", "off")
    assert texts(check(r, "Get my usual from Thai Basil on DoorDash"), "app_note") == []


def test_at_most_five_lines_the_most_important_first(lib):
    r = make_runner(lib)
    past(r, SKYLARK, PIXEL["id"], SIGN_IN)
    for text in ("A location prompt appears on first launch", "A pop-up about seat upgrades can appear"):
        r.app_notes.add(SKYLARK, text, {"task": "t1"})
    lines = check(r, "Check me in for my flight to Chicago on my phone", routine=CHECK_IN, source="mcp")
    assert [ln["kind"] for ln in lines] == ["blocked", "approval", "routine", "app_note", "app_note"]
    assert [ln["level"] for ln in lines] == ["stop", "info", "info", "info", "info"]
    assert all(set(ln) == {"kind", "text", "level"} for ln in lines)


def test_check_is_fast_on_a_long_history(lib):
    r = make_runner(lib, PIXEL)
    now = time.time()
    with r.store.lock:  # 1,500 earlier tasks of 8 steps each, a sign-in in every seventh
        r.store.db.executemany("INSERT INTO tasks (id, goal, source, status, created_at, app, device) VALUES (?,?,?,?,?,?,?)",
                               [(f"t{i}", f"task {i}", "web", "done", now - 60 * i, (DOORDASH, AMAZON, SKYLARK, TARGET)[i % 4],
                                 ("envoy-real", "envoy-real", "envoy-test", PIXEL["id"])[i % 4]) for i in range(1500)])
        r.store.db.executemany("INSERT INTO steps VALUES (?,?,?,?)",
                               [(f"t{i}", j, now, json.dumps(SIGN_IN if j == 3 and i % 7 == 0 else {"kind": "note", "text": f"step {j}"}))
                                for i in range(1500) for j in range(8)])
        r.store.db.commit()
    for i in range(15):
        for app in (DOORDASH, AMAZON, SKYLARK):
            r.app_notes.add(app, f"A pop-up number {i} can appear on the home screen", {"task": f"t{i}"})
    worst = 0.0
    for goal, kw in (("Get my usual on DoorDash", {}), ("price of AirPods at Target", {}), ("check me in", {"routine": CHECK_IN})):
        t0 = time.perf_counter()
        check(r, goal, source="web", **kw)
        worst = max(worst, time.perf_counter() - t0)
    assert worst < 0.05, f"{worst * 1000:.0f} ms"


def test_check_never_raises():
    assert check(SimpleNamespace(), "check me in") == []
    assert check(None, None) == []  # type: ignore[arg-type]
    r = make_runner()
    r.store.db.close()  # nothing can be read: no lines, and no error
    assert check(r, "check the price of AirPods at Target") == []
    broken = make_runner(None, PIXEL)
    broken.app_notes = SimpleNamespace(list=lambda app: 1 / 0)
    assert texts(check(broken, "price of AirPods at Target"), "device") == ["Target blocks emulators: I'll ask to use your Pixel 5."]


# ---- the runner's preflight step --------------------------------------------------------------------


def preflight_steps(task: dict, r: TaskRunner) -> list[dict]:
    return [s for s in r.store.steps(task["id"]) if s["kind"] == "preflight"]


def test_every_task_gets_one_preflight_step_before_it_runs(monkeypatch):
    r = route_runner(monkeypatch, RoutePool(AppPhone({}, {SHOP})))
    past(r, SHOP, "envoy-real", SIGN_IN)
    done = asyncio.run(finish(r, "find a lamp", app=SHOP))
    steps = r.store.steps(done["id"])
    pre = [s for s in steps if s["kind"] == "preflight"]
    assert done["status"] == "done" and len(pre) == 1 and steps[0]["kind"] == "preflight"
    assert pre[0]["lines"] == [{"kind": "signin", "text": "Shop asked you to sign in on envoy-real last time (Oct 27).", "level": "warn"}]
    assert pre[0]["text"] == "before I start: Shop asked you to sign in on envoy-real last time (Oct 27)."


def test_a_task_that_moves_to_your_phone_keeps_its_one_preflight_step(monkeypatch):
    r = route_runner(monkeypatch, RoutePool(AppPhone({SHOP: BLOCKED}, {SHOP}), AppPhone({}, {SHOP})))
    moved = asyncio.run(finish(r, "find a lamp", app=SHOP, answer_phone=True))
    assert moved["status"] == "done" and moved["device"] == PHONE["id"]
    assert len([s for s in r.store.steps(moved["id"]) if s["kind"] == "preflight"]) == 1


def test_a_failing_check_leaves_no_step_and_the_run_goes_on(monkeypatch):
    r = route_runner(monkeypatch, RoutePool(AppPhone({}, {SHOP})))
    monkeypatch.setattr(runner_mod, "preflight_check", lambda *a, **k: 1 / 0)
    done = asyncio.run(finish(r, "find a lamp", app=SHOP))
    assert done["status"] == "done" and not any(s["kind"] == "preflight" for s in r.store.steps(done["id"]))


def test_the_step_passes_the_tasks_own_source_and_request(monkeypatch):
    r = route_runner(monkeypatch, RoutePool(AppPhone({}, {SHOP})))
    seen: list[dict] = []
    monkeypatch.setattr(runner_mod, "preflight_check", lambda runner, goal, **kw: seen.append({"goal": goal, **kw}) or [])

    async def scenario():
        r.loop = asyncio.get_running_loop()
        task = r.start("find a lamp", "mcp", app=SHOP, request="find me a lamp")
        await r.jobs[task["id"]]
    asyncio.run(scenario())
    assert seen and seen[0]["source"] == "mcp" and seen[0]["request"] == "find me a lamp" and seen[0]["app"] == SHOP
