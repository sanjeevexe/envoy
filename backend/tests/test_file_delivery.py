"""File delivery wherever Envoy runs (backlog #48): the outbox's door (`/mcp/outbox`), the Mac's forwarder
(api/forwarder.py), send_to_phone waiting for a file on its way, and list_phones. The public-host rule for the door is
in test_phase5.py, beside /mcp's."""

from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from api.forwarder import Forwarder, KeyRefused, door_url, main as forwarder_main, remote_host
from api.handoff import DOOR, HANDOFF_TEMPLATES, HandoffError, door_name
from test_handoff import MP4, POSTING, Clock
from test_mcp_link import HDR, call, make, me

KEY = {"Authorization": "Bearer mcp-test-token"}
SIDE = {"app": "instagram", "caption": "Golden hour at the pier"}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    e = make(tmp_path, monkeypatch)
    e.ctx.handoff.run_in_background = lambda: None  # the tests look at the outbox themselves, never beside a watcher of the API's
    e.ctx.handoff.settle_s = 0
    e.ctx.handoff.scan()  # the first look, at an empty outbox
    return e


def upload(c, name="clip.mp4", body=MP4, sidecar=None, key=None, headers=KEY):
    data = {**({"sidecar": json.dumps(sidecar)} if sidecar is not None else {}), **({"key": key} if key else {})}
    return c.post(DOOR, data=data, files={"file": (name, body, "video/mp4")}, headers=headers)


def offers(env) -> list[dict]:
    return env.ctx.offers.list("all")


# ---- the door ---------------------------------------------------------------------------------------


def test_the_door_takes_the_mcp_key_and_nothing_else(env):
    with TestClient(env.ctx.asgi) as c:
        assert upload(c, headers={}).status_code == 401
        assert upload(c, headers=me(env.token)).status_code == 401  # the user's own session isn't the door's key
        assert upload(c, headers={"Authorization": "Bearer mcp-test-tokenX"}).status_code == 401
        assert c.get(DOOR).status_code == 401
        hello = c.get(DOOR, headers=KEY)
        assert hello.status_code == 200 and hello.json()["max_bytes"] == env.ctx.handoff.max_bytes
        assert c.get("/api/handoff", headers=KEY).status_code == 401  # and the key opens nothing of the user's
        r = upload(c)
        assert r.status_code == 200 and r.json()["name"] == "clip.mp4"
    assert (env.box / "clip.mp4").read_bytes() == MP4
    log = (env.tmp / "door.jsonl").read_text()
    assert [json.loads(line)["status"] for line in log.splitlines()] == [401, 401, 401, 401, 200, 200]
    assert "mcp-test-token" not in log and env.token not in log


def test_the_door_checks_size_and_type_and_cleans_names(env):
    h = env.ctx.handoff
    h.max_bytes = 1000
    with TestClient(env.ctx.asgi) as c:
        r = upload(c, body=MP4 + b"\0" * 2000)  # past the limit while it streams in
        assert r.status_code == 413 and "over" in r.json()["detail"]
        assert upload(c, body=MP4 + b"\0" * 300_000).status_code == 413  # past it by its Content-Length, never read
        assert c.post(DOOR, content=iter([b"--x\r\n"]), headers={**KEY, "Content-Type": "multipart/form-data; boundary=x"}).status_code == 411
        assert c.post(DOOR, data={"name": "clip.mp4", "sidecar": "x" * 200_000}, headers=KEY).status_code == 413  # a form without a file is small
        assert upload(c, name="notes.pdf", body=b"%PDF-1.4").status_code == 415
        assert upload(c, name="clip.mp4", body=b"%PDF-1.4 renamed").status_code == 415  # a video by its bytes
        assert upload(c, name="photo.jpg", body=MP4).status_code == 415
        assert upload(c, name="clip.mp4", body=b"").status_code == 415
        assert list(h.outbox().iterdir()) == []  # nothing half-written is left
        assert upload(c, name="../../etc/.evil\u202e4pm.mp4").json()["name"] == "evil4pm.mp4"
        assert upload(c, name="~/.ssh/key.mov").json()["name"] == "key.mov"
        assert upload(c, name="C:\\clips\\x.m4v").json()["name"] == "x.m4v"
        assert upload(c, name="Golden hour at the pier.mp4").json()["name"] == "Golden hour at the pier.mp4"  # as sent, so Muse's name finds it
    assert sorted(p.name for p in h.outbox().iterdir()) == ["Golden hour at the pier.mp4", "evil4pm.mp4", "key.mov", "x.m4v"]
    assert len(door_name("a" * 300 + ".mp4").encode()) <= 200 and door_name("a" * 300 + ".mp4").endswith("a.mp4")
    for bad in ("..", ".mp4", "~", "clip", "clip.mp4.json", "\x00"):
        with pytest.raises(HandoffError):
            door_name(bad)


def test_a_clip_through_the_door_gets_the_same_offer_as_one_dropped_in_the_outbox(env, monkeypatch):
    """Envoy on the Mac: Muse for Mac drops here.mp4 and here.json in the outbox. Envoy in the cloud: the forwarder sends
    there.mp4 and its sidecar through the door. The offer, the task after it and the phone are the same."""
    monkeypatch.setitem(HANDOFF_TEMPLATES, "instagram", POSTING)
    env.ctx.tasks.set_setting("phone_apps", ["com.instagram.android"])
    h = env.ctx.handoff
    with TestClient(env.ctx.asgi) as c:
        (env.box / "here.mp4").write_bytes(MP4)
        (env.box / "here.json").write_text(json.dumps(SIDE))
        h.scan()
        [local] = h.scan()  # recorded once its size has held (settle_s 0 here)
        r = upload(c, name="there.mp4", sidecar=SIDE).json()
        assert env.adb.calls == []  # nothing moves without the user's yes
        pushed = h.send(r["handoff_id"])  # the user's yes, later: the very file that came through the door goes on the phone
    assert r["status"] == "offered" and r["text"] == 'Envoy has there.mp4 and is asking you in its app: "Put there.mp4 on your Pixel 5 and post it to Instagram?"'
    a, b = env.ctx.offers.get(h.item(local["id"])["offer_id"]), env.ctx.offers.get(r["offer_id"])
    assert (a["kind"], a["source"]) == (b["kind"], b["source"]) == ("handoff", "outbox")
    assert b["title"] == a["title"].replace("here.mp4", "there.mp4") and b["body"] == a["body"] == "Golden hour at the pier"
    assert b["action"]["then"] == a["action"]["then"] and b["action"]["device"] == a["action"]["device"] == "phone-0A1B"
    assert b["preflight"] == a["preflight"]
    item = h.item(r["handoff_id"])
    assert (item["origin"], item["app"], item["caption"]) == ("outbox", "instagram", "Golden hour at the pier")
    assert json.loads((env.box / "there.mp4.json").read_text()) == SIDE
    assert pushed["status"] == "sent" and env.adb.files["/sdcard/Movies/Envoy/there.mp4"][:8] == MP4[:8]


def test_a_sidecar_that_comes_late_through_the_door_counts_as_it_does_in_the_outbox(env, monkeypatch):
    monkeypatch.setitem(HANDOFF_TEMPLATES, "instagram", POSTING)
    env.ctx.tasks.set_setting("phone_apps", ["com.instagram.android"])
    h = env.ctx.handoff
    with TestClient(env.ctx.asgi) as c:
        r = upload(c, name="pier.mp4").json()
        assert r["status"] == "waiting" and r["offer_id"] is None
        assert r["text"].startswith("Envoy has pier.mp4 and asks you in its app when its sidecar comes, or in ")
        late = c.post(DOOR, data={"name": "pier.mp4", "sidecar": json.dumps(SIDE)}, headers=KEY)
        assert late.status_code == 200 and late.json()["text"] == "Envoy has the sidecar for pier.mp4 and asks with it in a few seconds."
        assert c.post(DOOR, data={"name": "gone.mp4", "sidecar": json.dumps(SIDE)}, headers=KEY).status_code == 404
        assert c.post(DOOR, data={"name": "pier.mp4", "sidecar": "{not json"}, headers=KEY).status_code == 400
        assert c.post(DOOR, data={"name": "pier.mp4", "sidecar": "[1]"}, headers=KEY).status_code == 400
        assert c.post(DOOR, data={"name": "pier.mp4"}, headers=KEY).status_code == 400
        h.scan()  # the watcher's next look reads it, as it reads a late sidecar in the outbox
    item = h.item(r["handoff_id"])
    assert item["status"] == "offered" and item["app"] == "instagram"
    assert env.ctx.offers.get(item["offer_id"])["title"] == "Put pier.mp4 on your Pixel 5 and post it to Instagram?"
    assert len(offers(env)) == 1


def test_a_retry_is_the_same_file_and_a_new_one_of_the_same_name_replaces_it(env):
    h = env.ctx.handoff
    with TestClient(env.ctx.asgi) as c:
        first = upload(c, key="k1", sidecar={"app": "gallery", "caption": "one"}).json()
        again = upload(c, key="k1", sidecar={"app": "gallery", "caption": "one"}).json()
        assert first["status"] == "offered" and again["handoff_id"] == first["handoff_id"] and again["again"]
        assert again["text"].startswith("It was already there (a retry). ") and len(offers(env)) == 1
        newer = upload(c, key="k2", body=MP4 + b"newer").json()
    old = h.item(first["handoff_id"])
    assert old["status"] == "failed" and "newer file of the same name" in old["error"]
    assert env.ctx.offers.get(first["offer_id"])["status"] == "withdrawn"  # nobody is asked about a file that's gone
    assert (env.box / "clip.mp4").read_bytes() == MP4 + b"newer" and not (env.box / "clip.mp4.json").exists()  # its sidecar went too
    assert h.item(newer["handoff_id"])["status"] == "waiting"


def test_on_a_server_without_a_phone_an_instagram_clip_waits_and_says_why(env, monkeypatch):
    """The cloud copy has no phone over USB, and Instagram's handoff asks for the user's real phone: the clip waits in
    the outbox, and the door says so plainly (posting from a cloud phone isn't wired yet: docs/demo-creator-workflow.md)."""
    monkeypatch.setitem(HANDOFF_TEMPLATES, "instagram", {**POSTING, "device_pref": "phone"})
    env.ctx.pool.phones.clear()
    with TestClient(env.ctx.asgi) as c:
        r = upload(c, name="pier.mp4", sidecar=SIDE).json()
    assert r["status"] == "waiting" and r["offer_id"] is None and r["device"] is None
    assert r["text"].startswith("Envoy has pier.mp4 but can't offer it: Your Android phone isn't connected")


# ---- send_to_phone, wherever Envoy runs -------------------------------------------------------------------


def test_send_to_phone_waits_for_a_file_on_its_way(env, monkeypatch):
    h = env.ctx.handoff
    start = time.monotonic()
    with pytest.raises(HandoffError, match="there's no late.mp4"):  # Envoy on the Mac: said at once, as before
        h.arrived("late.mp4", wait_s=5)
    assert time.monotonic() - start < 1
    part = env.box / ".late.mp4.part"
    part.write_bytes(MP4[:10])

    def finish(name: str, part=None) -> None:
        time.sleep(0.3)
        (env.box / name).write_bytes(MP4)
        if part is not None:
            part.unlink()
    threading.Thread(target=finish, args=("late.mp4", part)).start()
    assert h.arrived("late.mp4", wait_s=5, every_s=0.05) == env.box / "late.mp4"  # it was coming through the door
    (env.box / ".slow.mp4.part").write_bytes(b"x")
    with pytest.raises(HandoffError, match="still on its way from the Mac"):
        h.arrived("slow.mp4", wait_s=0.2, every_s=0.05)
    monkeypatch.setattr("api.handoff.NOT_YET_S", 1.0)
    h.hello()  # the forwarder is in touch: a name not here yet may still be settling on the Mac
    threading.Thread(target=finish, args=("soon.mp4",)).start()
    assert h.arrived("soon.mp4", every_s=0.05).name == "soon.mp4"
    start = time.monotonic()
    with pytest.raises(HandoffError, match="there's no typo.mp4"):
        h.arrived("typo.mp4", every_s=0.05)
    assert 0.9 < time.monotonic() - start < 3


# ---- the forwarder ---------------------------------------------------------------------------------


class FakeDoor:
    """The other Envoy's door as the forwarder reaches it: answers `status`, or isn't there at all (`offline`)."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.offline = False
        self.status = 200

    def request(self, method, url, headers=None, data=None, files=None):
        if self.offline:
            raise httpx.ConnectError("no route to host")
        call = {"method": method, "url": url, "auth": (headers or {}).get("Authorization"), "data": dict(data or {}), "file": None}
        if files:
            name, f, _ = files["file"]
            call["file"] = (name, f.read())
        self.calls.append(call)
        name = call["file"][0] if call["file"] else call["data"].get("name")
        text = "Envoy has the sidecar for it." if method == "POST" and not files else f'Envoy has {name} and is asking you in its app:\n\x1b"Put {name} on …?"'  # printed as one plain line
        body = {"detail": "nope"} if self.status != 200 else {"name": name, "text": text} if method == "POST" else {"max_bytes": 1}
        return httpx.Response(self.status, json=body)

    def posts(self) -> list[dict]:
        return [c for c in self.calls if c["method"] == "POST"]


@pytest.fixture()
def fwd(tmp_path):
    box = tmp_path / "Envoy Outbox"
    box.mkdir()
    door, clock, lines = FakeDoor(), Clock(), []
    f = Forwarder(box, "https://envoy-cloud.example.ts.net:8443/mcp/outbox", "cloud-key", client=door, clock=clock, say=lines.append)
    f.tick()  # the first look: an empty outbox
    return SimpleNamespace(f=f, box=box, door=door, clock=clock, lines=lines, tmp=tmp_path)


def look(env, seconds: float = 2.5) -> list[dict]:
    env.f.tick()
    env.clock.t += seconds
    return env.f.tick()


def test_the_forwarder_does_nothing_when_envoy_runs_on_this_mac(tmp_path, monkeypatch, capsys):
    mac = {"127.0.0.1", "localhost", "my-mac.tail1234.ts.net"}
    for url in (None, "", "http://127.0.0.1:8700/mcp", "https://localhost:8700", "https://my-mac.tail1234.ts.net:10000/mcp"):
        assert remote_host(url, mac) is None
    assert remote_host("https://envoy-cloud.tail1234.ts.net:8443/mcp", mac) == "envoy-cloud.tail1234.ts.net"
    assert door_url("https://envoy-cloud.tail1234.ts.net:8443/mcp") == "https://envoy-cloud.tail1234.ts.net:8443/mcp/outbox"
    assert door_url("https://quiet-river.trycloudflare.com/") == "https://quiet-river.trycloudflare.com/mcp/outbox"
    box = tmp_path / "outbox"
    box.mkdir()
    (box / "clip.mp4").write_bytes(MP4)
    args = ["--outbox", str(box)]
    assert forwarder_main([*args, "--remote", ""], here=mac, env_file=None) == 0
    assert "Envoy runs on this Mac (ENVOY_REMOTE_URL isn't set)" in capsys.readouterr().out
    assert forwarder_main([*args, "--remote", "https://my-mac.tail1234.ts.net:10000/mcp"], here=mac, env_file=None) == 0
    assert "is this Mac" in capsys.readouterr().out
    assert sorted(p.name for p in box.iterdir()) == ["clip.mp4"]  # nothing touched
    cloud = ["--remote", "https://envoy-cloud.tail1234.ts.net:8443/mcp"]
    monkeypatch.delenv("ENVOY_REMOTE_TOKEN", raising=False)
    assert forwarder_main([*args, *cloud], here=mac, local_envoy=lambda: None, env_file=None) == 2
    assert "ENVOY_REMOTE_TOKEN isn't set" in capsys.readouterr().err
    monkeypatch.setenv("ENVOY_REMOTE_TOKEN", "cloud-key")
    assert forwarder_main([*args, *cloud], here=mac, local_envoy=lambda: 8700, env_file=None) == 2  # both would offer every clip
    assert "offered twice" in capsys.readouterr().err
    assert forwarder_main([*args, "--remote", "http://envoy-cloud.tail1234.ts.net:8700/mcp"], here=mac, local_envoy=lambda: None, env_file=None) == 2
    assert "only over https" in capsys.readouterr().err


def test_a_clip_goes_with_its_sidecar_and_moves_aside(fwd):
    (fwd.box / "pier.mp4").write_bytes(MP4)
    (fwd.box / "pier.json").write_text(json.dumps(SIDE))
    [got] = look(fwd)
    [post] = fwd.door.posts()
    assert post["url"] == "https://envoy-cloud.example.ts.net:8443/mcp/outbox" and post["auth"] == "Bearer cloud-key"
    assert post["file"] == ("pier.mp4", MP4) and json.loads(post["data"]["sidecar"]) == SIDE and len(post["data"]["key"]) == 32
    assert sorted(p.name for p in fwd.box.iterdir()) == ["Sent"]
    assert (fwd.box / "Sent" / "pier.mp4").read_bytes() == MP4 and json.loads((fwd.box / "Sent" / "pier.json").read_text()) == SIDE
    assert fwd.lines[-1] == ('Sent pier.mp4 (1 KB) with pier.json to Envoy at envoy-cloud.example.ts.net. Envoy has pier.mp4 and is asking '
                             'you in its app: "Put pier.mp4 on …?" Moved to Sent/pier.mp4.')
    (fwd.box / "pier.mp4").write_bytes(MP4 + b"take 2")  # the next take under the same name: nothing in Sent/ is overwritten
    (fwd.box / "pier.json").write_text(json.dumps({**SIDE, "caption": "take 2"}))
    look(fwd)
    assert sorted(p.name for p in (fwd.box / "Sent").iterdir()) == ["pier-2.json", "pier-2.mp4", "pier.json", "pier.mp4"]
    assert (fwd.box / "Sent" / "pier.mp4").read_bytes() == MP4 and len(fwd.door.posts()) == 2
    for _ in range(3):
        look(fwd)
    assert len(fwd.door.posts()) == 2  # each went once


def test_a_sidecar_that_comes_late_follows_its_clip(fwd):
    (fwd.box / "pier.mp4").write_bytes(MP4)
    look(fwd)
    [clip] = fwd.door.posts()
    assert "sidecar" not in clip["data"] and (fwd.box / "Sent" / "pier.mp4").exists()
    fwd.clock.t += 20  # Muse for Mac's permission prompt (Oct 29: 23 s)
    (fwd.box / "pier.json").write_text(json.dumps(SIDE))
    look(fwd)
    late = fwd.door.posts()[1]
    assert late["file"] is None and late["data"]["name"] == "pier.mp4" and json.loads(late["data"]["sidecar"]) == SIDE
    assert sorted(p.name for p in (fwd.box / "Sent").iterdir()) == ["pier.json", "pier.mp4"] and not (fwd.box / "pier.json").exists()
    assert fwd.lines[-1].startswith("Sent pier.json, the sidecar for pier.mp4 (2") and fwd.lines[-1].endswith("Moved to Sent/pier.json.")


def test_a_clip_waits_for_a_sidecar_still_being_written_and_one_written_first(fwd):
    (fwd.box / "a.mp4").write_bytes(MP4)
    fwd.f.tick()
    fwd.clock.t += 2.5
    (fwd.box / "a.json").write_text('{"app": "instagram", ')  # being written as the clip settles
    fwd.f.tick()
    assert fwd.door.posts() == []
    (fwd.box / "a.json").write_text(json.dumps(SIDE))
    look(fwd)
    assert [json.loads(p["data"]["sidecar"]) for p in fwd.door.posts()] == [SIDE]
    (fwd.box / "b.json").write_text(json.dumps(SIDE))  # the sidecar first, then its clip (docs: drag them in together)
    look(fwd, 5)
    assert len(fwd.door.posts()) == 1
    (fwd.box / "b.mp4").write_bytes(MP4)
    look(fwd)
    assert [(p["file"][0], "sidecar" in p["data"]) for p in fwd.door.posts()] == [("a.mp4", True), ("b.mp4", True)]


def test_offline_the_clip_stays_and_goes_when_envoy_is_back(fwd):
    fwd.door.offline = True
    (fwd.box / "pier.mp4").write_bytes(MP4)
    assert look(fwd) == []
    assert (fwd.box / "pier.mp4").exists() and not (fwd.box / "Sent").exists()
    assert fwd.lines[-1] == ("Envoy at envoy-cloud.example.ts.net isn't reachable (ConnectError): anything new stays in the outbox; "
                             "trying again in 5 s, then less often.")
    said = len(fwd.lines)
    fwd.clock.t += 6
    assert fwd.f.tick() == [] and fwd.f.retry_at - fwd.clock.t == 10  # tried again, then waits longer
    fwd.door.offline, fwd.door.status = False, 503  # back, but Envoy is restarting
    fwd.clock.t += 11
    assert fwd.f.tick() == [] and len(fwd.lines) == said  # said once for the whole outage
    fwd.door.status = 200
    fwd.clock.t += 31
    [got] = fwd.f.tick()
    assert fwd.lines[said] == "Envoy at envoy-cloud.example.ts.net is reachable again." and fwd.lines[-1].startswith("Sent pier.mp4 (1 KB)")
    assert (fwd.box / "Sent" / "pier.mp4").exists() and fwd.f.retry_at == 0


def test_what_envoy_refuses_stays_and_a_refused_key_stops_the_forwarder(fwd):
    (fwd.box / "notes.mp4").write_bytes(b"%PDF-1.4")  # not a video by its bytes: not even sent
    look(fwd)
    assert fwd.door.posts() == [] and fwd.lines[-1] == "notes.mp4 stays in the outbox: it isn't a video by its contents."
    fwd.door.status = 413
    (fwd.box / "big.mp4").write_bytes(MP4)
    look(fwd)
    assert fwd.lines[-1] == "big.mp4 stays in the outbox: Envoy at envoy-cloud.example.ts.net refused it (nope)."
    for _ in range(3):
        look(fwd)
    assert len(fwd.door.posts()) == 1 and (fwd.box / "big.mp4").exists()  # said once, tried once, left where it is
    fwd.door.status = 401
    (fwd.box / "next.mp4").write_bytes(MP4)
    fwd.f.tick()
    fwd.clock.t += 2.5
    with pytest.raises(KeyRefused, match="refused the key"):
        fwd.f.tick()


def test_what_was_in_the_outbox_at_start_stays_unless_asked(tmp_path):
    box = tmp_path / "outbox"
    box.mkdir()
    (box / "old.mp4").write_bytes(MP4)
    for waiting, sent in ((False, 0), (True, 1)):
        door, clock, lines = FakeDoor(), Clock(), []
        f = Forwarder(box, "https://envoy-cloud.example.ts.net/mcp/outbox", "k", client=door, clock=clock, say=lines.append, send_waiting=waiting)
        f.tick()
        clock.t += 2.5
        f.tick()
        clock.t += 2.5
        f.tick()
        assert len(door.posts()) == sent
        if not waiting:
            assert lines[0].startswith("Left 1 file(s) that were already in the outbox (old.mp4): only new ones go.")


def test_the_forwarder_and_the_door_together(env, tmp_path):
    """The whole way: a clip on the Mac, the forwarder, the door, the offer in the other Envoy, and Muse's
    send_to_phone with the Mac's file name."""
    mac = tmp_path / "Mac outbox"
    mac.mkdir()
    clock, lines = Clock(), []
    h = env.ctx.handoff
    with TestClient(env.ctx.asgi) as c:
        f = Forwarder(mac, "http://testserver/mcp/outbox", "mcp-test-token", client=c, clock=clock, say=lines.append)
        f.tick()
        (mac / "pier.mp4").write_bytes(MP4)
        f.tick()
        clock.t += 2.5
        [got] = f.tick()
        assert got["answer"]["status"] == "waiting" and (env.box / "pier.mp4").read_bytes() == MP4
        (mac / "pier.json").write_text(json.dumps({"app": "gallery", "caption": "Golden hour"}))
        f.tick()
        clock.t += 2.5
        [late] = f.tick()
        assert late["answer"]["text"] == "Envoy has the sidecar for pier.mp4 and asks with it in a few seconds."
        h.scan()
        item = h.item(got["answer"]["handoff_id"])
        assert env.ctx.offers.get(item["offer_id"])["title"] == "Put pier.mp4 on the Test phone (an emulator)?"
        sent = call(c, "send_to_phone", file="pier.mp4", device="emulator")  # Muse names the file as it was on the Mac
        (mac / "Café à la plage.mp4").write_bytes(MP4)  # any script in a name
        f.tick()
        clock.t += 2.5
        [other] = f.tick()
    assert other["answer"]["name"] == "Café à la plage.mp4" and (env.box / "Café à la plage.mp4").is_file()
    assert sent["status"] == "sent" and sent["handoff_id"] == item["id"]
    assert sorted(p.name for p in (mac / "Sent").iterdir()) == ["Café à la plage.mp4", "pier.json", "pier.mp4"]
    assert lines[-2].startswith("Sent pier.json, the sidecar for pier.mp4") and "testserver" in lines[-2]



# ---- list_phones ------------------------------------------------------------------------------------


def test_list_phones_says_each_phones_kind_whether_its_online_and_its_apps(env, monkeypatch):
    env.ctx.tasks.set_setting("phone_apps", ["com.instagram.android"])
    env.ctx.tasks.set_setting("phone_names", {"phone-0A1B": "Envoy's phone", "phone-9Z9Z": "Old phone"})
    env.ctx.pool.phones["phone-0A1B"] = {**env.ctx.pool.phones["phone-0A1B"], "name": "Envoy's phone"}  # a copy: PIXEL is shared
    monkeypatch.setattr(env.ctx.pool, "running", lambda: {"envoy-test": True, "envoy-real": False, "phone-0A1B": True})
    monkeypatch.setenv("ENVOY_HOST", "mac")
    with TestClient(env.ctx.asgi) as c:
        tools = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}, headers=HDR).json()["result"]["tools"]
        got = call(c, "list_phones")
        monkeypatch.setenv("ENVOY_HOST", "cloud")
        env.ctx.pool.phones.clear()  # the cloud copy: no phone over USB
        cloud = call(c, "list_phones")
    assert next(t for t in tools if t["name"] == "list_phones")["annotations"]["readOnlyHint"] is True
    assert got["envoy_runs_on"] == "the user's Mac"
    by = {p["id"]: p for p in got["phones"]}
    assert list(by) == ["envoy-test", "envoy-real", "phone-0A1B", "phone-9Z9Z"]
    assert by["envoy-test"] == {"id": "envoy-test", "name": "Test phone", "kind": "emulator", "online": True, "apps": ["Skylark"]}
    real_app = by["envoy-real"]
    assert real_app["kind"] == "emulator" and real_app["online"] is False and {"Doordash", "Amazon", "Starbucks"} <= set(real_app["apps"])
    assert "Instagram" not in real_app["apps"] and "Target" not in real_app["apps"] and "Skylark" not in real_app["apps"]
    pixel = by["phone-0A1B"]
    assert (pixel["name"], pixel["kind"], pixel["online"], pixel["model"]) == ("Envoy's phone", "real", True, "Pixel 5")
    assert {"Instagram", "Target"} <= set(pixel["apps"]) and "Doordash" not in pixel["apps"]  # set to it, and an app that blocks emulators
    assert by["phone-9Z9Z"] == {"id": "phone-9Z9Z", "name": "Old phone", "kind": "real", "online": False, "apps": pixel["apps"], "note": "not connected"}
    assert cloud["envoy_runs_on"] == "Envoy's cloud server"
    by = {p["id"]: p for p in cloud["phones"]}
    assert by["envoy-test"]["kind"] == by["envoy-real"]["kind"] == "cloud"
    assert "Instagram" in by["envoy-real"]["apps"] and "Target" not in by["envoy-real"]["apps"]  # with no phone, routing's fallback; Target can't
