"""Before I start (api/preflight.py), and the two runner changes the final features build on: `runner.start(...,
phone_ok=)`, so an offer you accepted for your phone isn't asked again, and Instagram as an app a goal can name."""

from __future__ import annotations

import asyncio

from test_phase6 import PHONE, SHOP, AppPhone, RoutePool, finish, route_runner

from api.crossapp import apps_in
from api.runner import APP_NAMES, app_for

INSTAGRAM = "com.instagram.android"

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
