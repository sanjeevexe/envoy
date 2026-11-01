"""Notifications on Envoy's phone as a trigger source (phone-layer plan §5 phone-watch, contracts 3 and 6): reading
`dumpsys notification --noredact` (a fake sample written here, fake content only, in Android 13's and Android 15's
layouts), redaction, the trigger kind, the watcher (only enabled triggers on watched apps, only their phone, once per
notification, nothing from before it was watched, unplug and replug, the phone's clock), the push, ask mode, and the
routes and MCP proposal."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.events import EventBus
from api.notifications import (NotificationWatcher, PhoneGone, Shown, check_spec, command, describe, matches, parse, redact,
                               report, update_line)
from api.offers import Offers
from api.push import Pusher
from api.scheduler import Scheduler
from api.store import TaskStore
from memory.store import MemoryStore
from test_mcp_link import call, make, me
from test_offers import starter

IG, TT, YT, SHELL = "com.instagram.android", "com.zhiliaoapp.musically", "com.google.android.youtube", "com.android.shell"
T0 = 1_793_500_000.0  # the Mac's clock in these tests (Nov 2026)


# ---- a fake dump ------------------------------------------------------------------------------------------


def record(pkg: str, nid: int, title: str | None, text: str | None, posted_ms: int, *, tag: str = "null", flags: str = "0",
           android: int = 15, big: str | None = None, typed: str = "String", redacted: bool = False, alerted_ms: int | None = None) -> str:
    """One NotificationRecord as dumpsys prints it. Android 15 names flags (`GROUP_SUMMARY|LOCAL_ONLY`) and prints
    `when=a/b`; Android 13 prints flags in hex and `when=a`."""
    key = f"0|{pkg}|{nid}|{tag}|10123"
    when = f"{posted_ms - 5}/{posted_ms - 5}" if android >= 14 else f"{posted_ms - 5}"

    def extra(name: str, v: str | None) -> str:
        if v is None:
            return f"                {name}=null"
        return f"                {name}={typed} [length={len(v)}]" if redacted else f"                {name}={typed} ({v})"
    lines = [
        f"    NotificationRecord(0x0abc{nid:04x}: pkg={pkg} user=UserHandle{{0}} id={nid} tag={tag} importance=3 key={key}: "
        f"Notification(channel=fake shortcut=null contentView=null vibrate=null sound=null defaults=0 flags={flags} color=0x00000000 vis=PRIVATE))",
        "      uid=10123 userId=0", f"      opPkg={pkg}", f"      flags={flags}", f"      originalFlags={flags}", "      pri=0", f"      key={key}",
        "      seen=false", f"      groupKey={key}", "      notification=", "            contentIntent=null", f"            when={when}",
        "            tickerText=null", "            extras={", extra("android.title", title),
        "                android.reduced.images=Boolean (true)", extra("android.text", text)]
    if big is not None:
        lines.append(extra("android.bigText", big))
    lines += ["                android.appInfo=ApplicationInfo (ApplicationInfo{1234abc fake})", "            }",
              "      publicNotification=", "            None", "      stats=SingleNotificationStats{posttimeElapsedMs=10}",
              f"      mCreationTimeMs={posted_ms - 1000}", "      mVisibleSinceMs=0", f"      mUpdateTimeMs={posted_ms}",
              f"      mInterruptionTimeMs={alerted_ms if alerted_ms is not None else posted_ms + 3}", "      mAdjustments=[]"]
    return "\n".join(lines)


def dump(*records: str, enqueued: tuple[str, ...] = ()) -> str:
    return "\n".join(["Current Notification Manager state:", "  Notification List:", *records, "  ",
                      "  mMaxPackageEnqueueRate=5.0", "  mArchive=Archive (0 notifications)", "  Enqueued Notification List:", *enqueued, "  ",
                      "  Snoozed notifications:", "  Ranking Config:", "    defaultImportance=3", "  Notification listeners:", ""])


FAKE = dump(
    record(IG, 101, "envoy_test_acct", "fake_viewer_1 commented: love this sunset", 1_793_499_990_000),
    record(IG, 102, "Instagram", "Your Instagram code is 482913. Don't share it.", 1_793_499_991_000),
    record(IG, 0, None, None, 1_793_499_992_000, flags="GROUP_SUMMARY|LOCAL_ONLY"),  # the group's summary: its children carry the words
    record(TT, 7, "TikTok", "fake_viewer_2 commented: first line\nsecond line of the comment", 1_793_499_993_000, typed="SpannableString"),
    record(YT, 9, "New comment", "@fake_viewer_3: where is this?", 1_793_499_994_000, big="@fake_viewer_3: where is this? I want to go"),
    record(TT, 8, "Uploading", "57%", 1_793_499_995_000, flags="ONGOING_EVENT|NO_CLEAR|FOREGROUND_SERVICE"),
    enqueued=(record(IG, 103, "not posted yet", "enqueued only", 1_793_499_996_000),),
)
FAKE_A13 = dump(
    record(IG, 201, "envoy_test_acct", "fake_viewer_4 commented: nice", 1_793_499_990_000, android=13, flags="0x10"),
    record(IG, 0, None, None, 1_793_499_990_500, android=13, flags="0x210"),  # GROUP_SUMMARY | AUTO_CANCEL
    record(TT, 5, "TikTok", "fake_viewer_5 liked your video", 1_793_499_991_000, android=13, flags="0x2"),  # ongoing
)


# ---- reading a dump ----------------------------------------------------------------------------------------


def test_parse_reads_the_shade_on_android_15():
    shown = {s.key: s for s in parse(FAKE)}
    assert len(shown) == 6  # the enqueued one isn't in the shade yet
    ig = shown[f"0|{IG}|101|null|10123"]
    assert (ig.package, ig.title, ig.text, ig.posted_ms, ig.quiet) == (IG, "envoy_test_acct", "fake_viewer_1 commented: love this sunset", 1_793_499_990_000, False)
    tt = shown[f"0|{TT}|7|null|10123"]
    assert tt.text == "fake_viewer_2 commented: first line\nsecond line of the comment"  # a value over two lines, a SpannableString
    assert shown[f"0|{YT}|9|null|10123"].text.endswith("I want to go")  # the long form when there is one
    assert shown[f"0|{IG}|0|null|10123"].quiet and shown[f"0|{TT}|8|null|10123"].quiet  # a summary, a foreground upload
    assert all(f"0|{IG}|103" not in k for k in shown)


def test_parse_reads_android_13_and_several_dumps_in_one_string():
    a13 = {s.key: s for s in parse(FAKE_A13)}
    assert a13[f"0|{IG}|201|null|10123"].title == "envoy_test_acct" and not a13[f"0|{IG}|201|null|10123"].quiet
    assert a13[f"0|{IG}|0|null|10123"].quiet and a13[f"0|{TT}|5|null|10123"].quiet  # 0x200 and 0x2 in hex
    both = parse(FAKE + "\n" + FAKE)  # one dump per package in one adb call: the same key once
    assert len(both) == 6


def test_a_dump_without_noredact_gives_no_words_and_says_so():
    d = dump(record(IG, 1, "secret", "secret", 1_793_499_990_000, redacted=True))
    assert [(s.title, s.text) for s in parse(d)] == [("", "")]
    assert report(d)["packages"][IG]["redacted"] == 1


def test_the_p2_report_counts_and_never_prints_words():
    out = report(FAKE, "15")
    assert out["packages"][IG] == {"count": 3, "key": 3, "title": 2, "text": 2, "posted": 3, "quiet": 1, "redacted": 0}
    assert out["packages"][TT]["quiet"] == 1 and out["packages"][YT]["text"] == 1
    printed = json.dumps(out)
    for word in ("fake_viewer", "sunset", "482913", "commented", "Uploading", "envoy_test_acct"):
        assert word not in printed


def test_one_shell_command_per_poll_with_the_phone_clock_and_only_real_package_names():
    assert command([IG, TT]) == f"date +%s%3N; dumpsys notification --noredact p {IG}; dumpsys notification --noredact p {TT}"
    assert "rm" not in command([IG, "com.x; rm -rf /sdcard", "$(reboot)"])


# ---- redaction ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("raw, stored", [
    ("Your Instagram code is 482913. Don't share it.", "Your Instagram code [hidden]"),
    ("482913 is your verification number", "•••• is your verification number"),
    ("Use 123 456 to sign in", "Use •••• to sign in"),
    ("Your OTP: 9921", "Your OTP [hidden]"),
    ("PIN 4410 for pickup", "PIN [hidden]"),
    ("fake_viewer_1 commented: love this sunset", "fake_viewer_1 commented: love this sunset"),
    ("12 new likes and 3 comments", "12 new likes and 3 comments"),
    ("line one\nline two‮\x07", "line one line two"),
])
def test_redact(raw, stored):
    assert redact(raw) == stored


def test_redact_caps_the_length():
    assert len(redact("a" * 1000, 300)) == 300


# ---- the trigger kind --------------------------------------------------------------------------------------


def test_check_spec():
    spec = {"package": [IG, TT, IG], "contains": " comment ", "title_contains": "", "phone": "phone-0A1B"}
    check_spec(spec)
    assert spec == {"package": [IG, TT], "contains": "comment", "phone": "phone-0A1B"}
    for bad in ({}, {"package": ""}, {"package": "com.x; reboot"}, {"package": [IG, 3]}, {"package": [IG] * 6 + [TT] * 0 + ["a.b", "c.d", "e.f", "g.h", "i.j"]},
                {"package": IG, "contains": "x\ny"}, {"package": IG, "phone": "../../etc"}, {"package": IG, "push": "yes"}):
        with pytest.raises(ValueError):
            check_spec(dict(bad))


def test_a_notification_trigger_may_only_tell_you_but_other_kinds_still_run_something():
    store = TaskStore(":memory:")
    sched = Scheduler(store, MemoryStore(":memory:"), lambda *a, **k: None, EventBus())
    t = sched.add("notification", "Comments", {"package": IG, "contains": "commented"}, {})
    assert t["kind"] == "notification" and t["action"] == {} and t["enabled"]
    with pytest.raises(ValueError):
        sched.add("time", "x", {"daily_at": "08:00"}, {})
    with pytest.raises(ValueError):
        sched.add("notification", "x", {"package": "not a package"}, {})
    assert sched.tick() == [] and sched.next_runs(t) == []  # the watcher fires it, not the loop


def test_matches_and_describe():
    s = Shown("k", IG, "envoy_test_acct", "fake_viewer_1 Commented: nice", 1, frozenset())
    assert matches({"package": IG}, s) and matches({"package": [TT, IG], "contains": "commented"}, s)
    assert matches({"package": IG, "title_contains": "ENVOY", "text_contains": "nice"}, s)
    assert not matches({"package": TT}, s) and not matches({"package": IG, "title_contains": "commented"}, s)
    assert describe({"package": [IG, TT, YT], "contains": "comment"}) == "when Instagram, TikTok or YouTube notifies Envoy’s phone with “comment”"
    assert describe({"package": IG, "title_contains": "a", "text_contains": "b"}, "the test phone") == \
        "when Instagram notifies the test phone titled “a” and saying “b”"
    assert update_line({"app": "Instagram", "title": "envoy_test_acct", "text": "fake_viewer_1 commented: nice"}) == \
        'Instagram on Envoy\'s phone: "envoy_test_acct: fake_viewer_1 commented: nice"'


# ---- the watcher -------------------------------------------------------------------------------------------


class Phone:
    """A fake phone behind `read`: its clock (ms) and what its shade shows; `gone` makes adb fail as when unplugged."""

    def __init__(self, clock_ms: float) -> None:
        self.clock_ms, self.records, self.gone, self.reads = clock_ms, {}, False, []

    def post(self, pkg: str, nid: int, title: str, text: str, *, at_ms: float | None = None, flags: str = "0", silent: bool = False) -> None:
        """`silent`: an update that doesn't alert you again (Android keeps the last alert's time)."""
        at = int(at_ms if at_ms is not None else self.clock_ms)
        self.alerted = getattr(self, "alerted", {})
        if not silent or (pkg, nid) not in self.alerted:
            self.alerted[(pkg, nid)] = at + 3
        self.records[(pkg, nid)] = record(pkg, nid, title, text, at, flags=flags, alerted_ms=self.alerted[(pkg, nid)])

    def read(self, serial: str, packages: list[str]) -> str:
        self.reads.append((serial, tuple(packages)))
        if self.gone:
            raise PhoneGone("adb: device 'FAKE01' not found")
        mine = [r for (pkg, _), r in self.records.items() if pkg in packages]
        return f"{int(self.clock_ms)}\n" + dump(*mine)


def world(skew_s: float = 0.0, proactivity: str | None = None):
    """A watcher on its own stores: a fake clock, a fake Pixel ("phone-FAKE01", its clock `skew_s` behind) and envoy-test."""
    now = [T0]
    store, bus = TaskStore(":memory:"), EventBus()
    started: list = []
    runner = SimpleNamespace(start=starter(store, started))
    sched = Scheduler(store, MemoryStore(":memory:"), runner.start, bus, clock=lambda: now[0])
    offers = Offers(store, bus, runner, sched, clock=lambda: now[0])
    sched.offers = offers
    if proactivity:
        store.set_setting("proactivity", proactivity)
    pixel, emu = Phone((T0 - skew_s) * 1000), Phone(T0 * 1000)
    phones = {"FAKE01": pixel, "emulator-5554": emu}
    pool = SimpleNamespace(phones={"phone-FAKE01": {"id": "phone-FAKE01", "serial": "FAKE01", "model": "Pixel 5", "state": "device", "name": "Envoy's phone"}},
                           refresh_phones=lambda: None)
    logs: list = []
    w = NotificationWatcher(store, pool, sched, bus, read=lambda serial, pkgs: phones[serial].read(serial, pkgs), clock=lambda: now[0], log=logs.append)
    events: list = []
    bus.listeners.append(events.append)

    def tick(s: float = 3.0) -> list:
        now[0] += s
        pixel.clock_ms += s * 1000
        emu.clock_ms += s * 1000
        return w.poll()
    return SimpleNamespace(now=now, store=store, bus=bus, sched=sched, offers=offers, started=started, w=w, pixel=pixel, emu=emu, pool=pool,
                           logs=logs, events=events, tick=tick)


def matched(u) -> list:
    return [e for e in u.events if e["type"] == "notification_matched"]


def test_nothing_is_read_until_a_trigger_is_on_and_its_app_watched():
    u = world()
    u.pixel.post(IG, 1, "a", "b")
    trig = u.sched.add("notification", "Comments", {"package": IG}, {}, enabled=False)
    assert u.tick() == [] and u.pixel.reads == []  # switched off
    u.store.update_trigger(trig["id"], enabled=1)
    assert u.tick() == [] and u.pixel.reads == []  # on, but you haven't let Envoy watch Instagram
    u.w.set_apps([IG, "com.x; reboot"])
    assert u.w.apps_on() == [IG]
    u.tick()
    assert u.pixel.reads == [("FAKE01", (IG,))] and u.emu.reads == []  # one call, only its phone, only its app


def test_one_event_per_notification_and_nothing_from_before_it_was_watched():
    u = world()
    u.w.set_apps([IG, TT])
    u.pixel.post(IG, 1, "envoy_test_acct", "fake_viewer_1 commented: old one")  # already in the shade
    trig = u.sched.add("notification", "Comments", {"package": [IG, TT], "contains": "commented"}, {})
    assert u.tick() == []
    u.pixel.post(IG, 2, "envoy_test_acct", "fake_viewer_2 commented: love it")
    u.pixel.post(TT, 3, "TikTok", "fake_viewer_3 liked your video")  # doesn't say "commented"
    got = u.tick()
    assert [(e["package"], e["text"]) for e in got] == [(IG, "fake_viewer_2 commented: love it")]
    assert u.tick() == [] and u.tick() == []  # still in the shade: once
    u.pixel.post(IG, 2, "envoy_test_acct", "fake_viewer_2 commented: love it", silent=True)  # the app re-posts it quietly
    assert u.tick() == []
    u.pixel.post(IG, 2, "envoy_test_acct", "fake_viewer_2 and 1 other commented", silent=True)  # an update: new words
    assert len(u.tick()) == 1
    u.pixel.post(IG, 2, "envoy_test_acct", "fake_viewer_2 and 1 other commented")  # the same words, but it buzzed again: new to the app
    assert len(u.tick()) == 1
    stored = u.store.trigger(trig["id"])
    assert len(stored["fired"]) == 3 and all(k.startswith("n") and "fake" not in k for k in stored["fired"])
    rows = u.w.events()
    assert [r["text"] for r in rows] == ["fake_viewer_2 and 1 other commented"] * 2 + ["fake_viewer_2 commented: love it"]
    assert set(rows[0]) == {"id", "time", "phone", "package", "app", "title", "text", "trigger_id"}  # contract 3, exactly
    assert rows[0]["phone"] == "phone-FAKE01" and rows[0]["app"] == "Instagram" and rows[0]["trigger_id"] == trig["id"]


def test_codes_are_redacted_before_they_are_stored_and_no_words_reach_the_log():
    u = world()
    u.w.set_apps([IG])
    u.sched.add("notification", "Instagram", {"package": IG, "text_contains": "code"}, {})
    u.tick()
    u.pixel.post(IG, 5, "Instagram", "Your Instagram code is 482913. Don't share it.")
    u.tick()
    assert [(r["title"], r["text"]) for r in u.w.events()] == [("Instagram", "Your Instagram code [hidden]")]  # matched on the words, stored without the code
    logged = json.dumps(u.logs)
    assert "482913" not in logged and "Instagram code" not in logged and "Don't share" not in logged
    assert "482913" not in json.dumps(matched(u))


def test_the_push_says_the_app_and_title_and_opens_the_trigger():
    u = world()
    sent: list = []
    store = u.store
    pusher = Pusher(store, SimpleNamespace(public_key="k"), "https://envoy.example", send=lambda info, data, **kw: sent.append(json.loads(data)) or SimpleNamespace(status_code=201))
    pusher.subscribe({"endpoint": "http://127.0.0.1:9/fake", "keys": {"p256dh": "x", "auth": "y"}}, None)
    u.bus.listeners.append(pusher.on_event)
    u.w.set_apps([IG])
    trig = u.sched.add("notification", "Comments", {"package": IG}, {})
    u.tick()
    u.pixel.post(IG, 2, "envoy_test_acct", "fake_viewer_2 commented: love it")
    ev = u.tick()[0]
    pusher.pool.shutdown(wait=True)
    assert len(sent) == 1
    p = sent[0]
    assert (p["kind"], p["title"], p["body"], p["url"]) == ("notification", "Instagram: envoy_test_acct", "fake_viewer_2 commented: love it", f"/?trigger={trig['id']}")
    assert p["id"] == f"push-{ev['id']}"
    assert matched(u)[0]["phone_name"] == "Envoy's phone"


def test_a_trigger_set_not_to_push_still_tells_the_agents():
    u = world()
    u.w.set_apps([IG])
    u.sched.add("notification", "Quiet", {"package": IG, "push": False}, {})
    u.tick()
    u.pixel.post(IG, 2, "a", "b")
    assert len(u.tick()) == 1 and matched(u)[0]["push"] is False and len(u.w.events()) == 1


def test_ask_mode_raises_one_offer_and_that_is_the_one_push():
    u = world()
    u.w.set_apps([IG])
    trig = u.sched.add("notification", "Reply to comments", {"package": IG, "contains": "commented"},
                       {"goal": "Open the comments on my latest Instagram post", "ask": True})
    u.tick()
    u.pixel.post(IG, 2, "envoy_test_acct", "fake_viewer_2 commented: love it")
    u.tick()
    offers = u.offers.pending()
    assert len(offers) == 1 and offers[0]["title"] == "Should I open the comments on your latest Instagram post?"
    assert offers[0]["origin"] == {"trigger_id": trig["id"]} and offers[0]["expires_at"] == pytest.approx(u.now[0] + 6 * 3600)
    assert u.started == [] and matched(u)[0]["push"] is False  # the offer pushes; not two buzzes for one comment
    assert len(u.w.events()) == 1  # agents hear it either way


def test_ask_mode_with_proactivity_off_pushes_the_notification_instead():
    u = world(proactivity="off")
    u.w.set_apps([IG])
    u.sched.add("notification", "Ask", {"package": IG}, {"goal": "Open the comments", "ask": True})
    u.tick()
    u.pixel.post(IG, 2, "a", "b")
    u.tick()
    assert len(u.offers.pending()) == 1 and matched(u)[0]["push"] is True


def test_a_routine_runs_through_the_scheduler_with_the_notification_as_values():
    u = world()
    u.w.set_apps([TT])
    u.sched.add("notification", "TikTok comments", {"package": TT}, {"routine": "tiktok_open_comments", "goal": "Read me the new comment from {notification.app}",
                                                                      "inputs_from": {"source": "notification.app"}})
    u.tick()
    u.pixel.post(TT, 2, "TikTok", "fake_viewer_2 commented: 1234 times")
    u.tick()
    goal, source, kw = u.started[0]
    assert goal == "Read me the new comment from TikTok" and source == "trigger:TikTok comments"
    assert kw["routine"] == "tiktok_open_comments" and kw["inputs"] == {"source": "TikTok"}
    assert [e for e in u.logs if e["event"] == "matched"][0]["started"]


def test_only_its_phone_is_read():
    u = world()
    u.w.set_apps([SHELL, IG])
    u.sched.add("notification", "Test", {"package": SHELL, "phone": "envoy-test"}, {})
    u.tick()
    u.emu.post(SHELL, 2020, "Fake Title", "fake text")
    u.pixel.post(SHELL, 2020, "Fake Title", "fake text")
    got = u.tick()
    assert [e["phone"] for e in got] == ["envoy-test"] and u.pixel.reads == []
    assert {s for s, _ in u.emu.reads} == {"emulator-5554"}


def test_unplugging_backs_off_and_what_landed_meanwhile_fires_on_replug():
    u = world()
    u.w.set_apps([IG])
    u.sched.add("notification", "Comments", {"package": IG}, {})
    u.tick()
    u.pixel.gone = True
    assert u.tick() == []
    status = u.w.status()[0]
    assert status["online"] is False and "not found" in status["error"]
    reads = len(u.pixel.reads)
    u.tick(1.0)
    assert len(u.pixel.reads) == reads  # backing off, not hammering adb
    u.pixel.post(IG, 2, "envoy_test_acct", "fake_viewer_2 commented while unplugged")
    u.tick(5.0)  # still gone: the backoff doubles
    u.pixel.gone = False
    for _ in range(5):
        if got := u.tick():
            break
    assert [e["text"] for e in got] == ["fake_viewer_2 commented while unplugged"]
    assert u.w.status()[0]["online"] is True
    assert [e["event"] for e in u.logs if e["event"] in ("offline", "online")] == ["online", "offline", "online"]


def test_the_phone_clock_is_read_in_the_same_call():
    u = world(skew_s=120)  # the phone's clock is two minutes behind the Mac's
    u.w.set_apps([IG])
    u.sched.add("notification", "Comments", {"package": IG}, {})
    u.tick()
    u.pixel.post(IG, 2, "a", "posted after the trigger was on")  # its post time, on the phone's clock, is before T0
    got = u.tick()
    assert len(got) == 1
    lat = got[0]["latency"]
    assert lat["offset_ms"] == pytest.approx(120_000, abs=1) and 0 <= lat["seen_ms"] <= 3000


def test_pausing_doesnt_replay_what_landed_meanwhile():
    u = world()
    u.w.set_apps([IG])
    trig = u.sched.add("notification", "Comments", {"package": IG}, {})
    u.tick()
    u.store.update_trigger(trig["id"], enabled=0)
    u.tick()
    u.pixel.post(IG, 2, "a", "while paused")
    u.tick()
    u.store.update_trigger(trig["id"], enabled=1)
    assert u.tick() == []  # watched again from now
    u.pixel.post(IG, 3, "a", "after resuming")
    assert [e["text"] for e in u.tick()] == ["after resuming"]


def test_latency_is_recorded_for_every_event():
    u = world()
    u.w.set_apps([IG])
    u.sched.add("notification", "Comments", {"package": IG}, {})
    u.tick()
    u.pixel.post(IG, 2, "a", "b", at_ms=(u.now[0] + 1.0) * 1000)  # lands 1 s into the next 3 s wait
    u.tick()
    rec = [e for e in u.logs if e["event"] == "matched"][0]
    assert rec["seen_ms"] == 2000 and rec["stored_ms"] == 2000 and rec["push_ms"] == 2000 and rec["pushed"] is True
    assert set(rec) >= {"id", "phone", "package", "trigger", "posted_at", "poll_ms", "offset_ms"}


# ---- the API and MCP ------------------------------------------------------------------------------------


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setattr("api.notifications.LOG", tmp_path / "notifications.jsonl")
    env = make(tmp_path, monkeypatch)
    phone = Phone(time.time() * 1000)
    env.ctx.notifications.read = phone.read  # no real adb in tests
    env.phone = phone
    return env


def test_settings_list_the_apps_all_off_and_only_your_session_changes_them(api):
    with TestClient(api.ctx.asgi) as c:
        assert c.get("/api/settings/notifications").status_code == 401
        assert c.get("/api/settings/notifications", headers={"Authorization": "Bearer mcp-test-token"}).status_code == 401
        got = c.get("/api/settings/notifications", headers=me(api.token)).json()
        assert {a["package"] for a in got["apps"]} >= {IG, TT, YT} and not any(a["on"] for a in got["apps"])
        assert {a["name"] for a in got["apps"] if a["package"] in (IG, TT, YT)} == {"Instagram", "TikTok", "YouTube"}
        assert c.post("/api/settings/notifications", json={"apps": [IG, "bad; reboot"]}, headers=me(api.token)).json() == {"on": [IG]}
        got = c.get("/api/settings/notifications", headers=me(api.token)).json()
        assert [a["package"] for a in got["apps"] if a["on"]] == [IG]
        assert c.post("/api/settings/notifications", json={"apps": "all"}, headers=me(api.token)).status_code == 400


def test_a_notification_trigger_from_the_web_app_and_its_events(api):
    with TestClient(api.ctx.asgi) as c:
        r = c.post("/api/triggers", json={"kind": "notification", "name": "Comments", "spec": {"package": IG, "contains": "commented"}, "action": {}},
                   headers=me(api.token))
        assert r.status_code == 200 and r.json()["spec"] == {"package": IG, "contains": "commented"}
        assert c.post("/api/triggers", json={"kind": "notification", "name": "x", "spec": {"package": "nope"}, "action": {}},
                      headers=me(api.token)).status_code == 400
        assert c.get("/api/notifications", headers=me(api.token)).json()["events"] == []
        assert c.get("/api/notifications").status_code == 401


def test_muse_can_propose_one_switched_off(api):
    with TestClient(api.ctx.asgi) as c:
        out = call(c, "create_trigger", kind="notification", name="Comments on my posts",
                   spec={"package": [IG, TT, YT], "contains": "comment"}, action={})
        assert "error" not in out and out["enabled"] is False
        offer = api.ctx.offers.get(out["offer_id"])
        assert offer["title"] == ("Muse wants to set this up: when Instagram, TikTok or YouTube notifies Envoy’s phone with “comment”, "
                                  "tell you and Muse. Turn it on?")
        assert "error" in call(c, "create_trigger", kind="notification", name="x", spec={"package": "com.x;reboot"}, action={})
    # Even switched on, it reads nothing until the user lets Envoy watch those apps.
    api.ctx.tasks.update_trigger(out["trigger_id"], enabled=1)
    api.ctx.notifications.poll()
    assert api.phone.reads == []


def test_a_title_that_is_just_the_app_name_isnt_said_twice():
    sent: list = []
    store = TaskStore(":memory:")
    pusher = Pusher(store, SimpleNamespace(public_key="k"), "https://envoy.example", send=lambda info, data, **kw: sent.append(json.loads(data)) or SimpleNamespace(status_code=201))
    pusher.subscribe({"endpoint": "http://127.0.0.1:9/fake", "keys": {"p256dh": "x", "auth": "y"}}, None)
    pusher.on_event({"type": "notification_matched", "push": True, "event": {"id": "notif-1", "app": "TikTok", "title": "TikTok", "text": "", "trigger_id": "trig-1"},
                     "phone_name": "Envoy's phone"})
    pusher.on_event({"type": "notification_matched", "push": False, "event": {"id": "notif-2", "app": "TikTok", "title": "x", "text": "y", "trigger_id": "trig-1"}})
    pusher.pool.shutdown(wait=True)
    assert [(p["title"], p["body"]) for p in sent] == [("TikTok", "On Envoy's phone")]
