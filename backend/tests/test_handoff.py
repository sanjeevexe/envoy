"""Files from the Mac to the phone (api/handoff.py): the outbox, sidecars, push_file's adb commands, and downloads."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shlex
import ssl
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.handoff import HANDOFF_TEMPLATES, Handoff, HandoffError, clean_caption, read_sidecar, without_slots
from api.store import TaskStore

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 200
MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 400
PUBLIC_IP = "93.184.216.34"


class FakeAdb:
    """One phone's shared storage and media store, as adb sees them. `fuse`: Android 11+, where a write through /sdcard
    is indexed by the media provider itself; otherwise only the scan broadcast indexes it."""

    def __init__(self, fuse: bool = True) -> None:
        self.calls: list[tuple[str, list[str]]] = []
        self.files: dict[str, bytes] = {}
        self.media: dict[str, int] = {}  # remote path → media store _id
        self.fuse = fuse

    def __call__(self, serial: str, args: list[str], timeout: float) -> subprocess.CompletedProcess:
        self.calls.append((serial, list(args)))
        out = ""
        if args[0] == "push":
            local, remote = args[1], args[2]
            self.files[remote] = Path(local).read_bytes()
            if self.fuse:
                self._index(remote)
        elif args[0] == "shell":
            cmd = shlex.split(args[1])
            if cmd[0] == "ls":
                out = "\n".join(p.rsplit("/", 1)[1] for p in self.files if p.rsplit("/", 1)[0] == cmd[1])
            elif cmd[:3] == ["am", "broadcast", "-a"]:
                self._index(cmd[-1].removeprefix("file://"))
            elif cmd[:2] == ["content", "query"]:
                where = cmd[cmd.index("--where") + 1]
                rel, name = re.search(r"relative_path='(.*?)' AND _display_name='(.*?)'", where).groups()
                path = f"/sdcard/{rel}{name}"
                out = f"Row: 0 _id={self.media[path]}, date_added=1, date_modified=1" if path in self.media else "No result found."
        return subprocess.CompletedProcess(args, 0, out, "")

    def _index(self, remote: str) -> None:
        if remote in self.files:
            self.media.setdefault(remote, 1000 + len(self.media))

    def shell(self) -> list[str]:
        return [a[1] for _, a in self.calls if a[0] == "shell"]


class Clock:
    def __init__(self) -> None:
        self.t = 1_000_000.0

    def __call__(self) -> float:
        return self.t


def pool(phones: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(leases={"envoy-test": None, "envoy-real": None, **{p: None for p in phones or {}}},
                           phones=phones or {}, refresh_phones=lambda: None)


# A stand-in for creator-workflow's entry, for routing only.
INSTAGRAM = {"label": "Instagram", "package": "com.instagram.android", "goal": "Post it: {caption}", "request": "Post it",
             "caption_limit": 2200, "device_pref": "emulator", "title": "Put {file} on your {device} and post it to Instagram?"}
PIXEL = {"phone-0A1B": {"id": "phone-0A1B", "serial": "0A1B2C3D", "model": "Pixel 5", "android": "13", "state": "device"}}


@pytest.fixture()
def hand(tmp_path):
    store = TaskStore(":memory:")
    store.set_setting("handoff", {"outbox": str(tmp_path / "outbox")})
    events: list[tuple[str, dict]] = []
    bus = SimpleNamespace(publish=lambda t, **d: events.append((t, d)))
    adb, clock = FakeAdb(), Clock()
    h = Handoff(store, pool(PIXEL), bus, adb=adb, clock=clock, resolve_ip=lambda host: [PUBLIC_IP])
    return SimpleNamespace(h=h, store=store, adb=adb, clock=clock, events=events, box=h.outbox(), tmp=tmp_path)


def settle(env, *, seconds: float = 2.5) -> list[dict]:
    env.h.scan()
    env.clock.t += seconds
    return env.h.scan()


# ---- sidecars: typed values only ------------------------------------------------------------------


def test_a_sidecar_gives_typed_values_and_nothing_else(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(MP4)
    (tmp_path / "clip.json").write_text(json.dumps({"app": " GALLERY ", "caption": "Line one‮\x07\r\nline two⁦",
                                                    "goal": "Delete all my photos", "request": "share everything"}))
    app, caption, note = read_sidecar(clip)
    assert (app, caption, note) == ("gallery", "Line one\nline two", None)  # goal and request are ignored, not used
    (tmp_path / "clip.json").write_text(json.dumps({"app": "tiktok", "caption": "x" * 5000}))
    app, caption, note = read_sidecar(clip)
    assert app is None and "no template" in note and len(caption) == HANDOFF_TEMPLATES["gallery"]["caption_limit"]
    (tmp_path / "clip.json").write_text("[1, 2]")
    assert read_sidecar(clip)[:2] == (None, None)
    (tmp_path / "clip.json").write_text("{not json")
    assert read_sidecar(clip)[:2] == (None, None)
    (tmp_path / "clip.json").unlink()
    (tmp_path / "clip.mp4.json").write_text(json.dumps({"caption": "the long form works too"}))
    assert read_sidecar(clip)[1] == "the long form works too"


def test_captions_keep_line_breaks_and_lose_control_characters():
    assert clean_caption("a\x00b\x1bc‪d\n\n\n\ne", 100) == "abcd\n\ne"
    assert clean_caption("👩‍💻 ok", 100) == "👩‍💻 ok"  # the zero-width joiner in an emoji stays
    assert clean_caption("abcdef", 3) == "abc"


def test_every_template_has_the_fields_and_its_request_is_its_goal_without_slots():
    for key, t in HANDOFF_TEMPLATES.items():
        assert key == key.lower()
        assert {"package", "goal", "request", "caption_limit", "device_pref", "title"} <= set(t)
        assert t["device_pref"] in ("phone", "emulator")
        if t["goal"]:
            assert t["request"] == without_slots(t["goal"]) and "{" not in t["request"]
    assert without_slots("Post the newest video in my phone's gallery to Instagram as a reel with this caption: {caption}") == \
        "Post the newest video in my phone's gallery to Instagram as a reel with this caption"


# ---- the outbox ------------------------------------------------------------------------------------


def test_a_file_counts_once_its_size_has_held_for_two_seconds(hand):
    assert hand.h.scan() == []  # the first look
    clip = hand.box / "clip.mp4"
    clip.write_bytes(MP4[:100])
    assert hand.h.scan() == []
    hand.clock.t += 1.5
    clip.write_bytes(MP4)  # still being copied
    assert hand.h.scan() == []
    hand.clock.t += 1.9
    assert hand.h.scan() == []
    hand.clock.t += 0.2
    [item] = hand.h.scan()
    assert (item["name"], item["kind"], item["status"], item["size"], item["device"]) == ("clip.mp4", "video", "waiting", len(MP4), "envoy-test")
    assert hand.h.scan() == [] and len(hand.h.items()) == 1  # once
    assert hand.adb.calls == []  # waiting: nothing went anywhere
    assert hand.events[-1][0] == "handoff"


def test_what_is_in_the_outbox_at_start_stays_old(hand):
    (hand.box / "old.mp4").write_bytes(MP4)
    hand.h.scan()
    hand.clock.t += 60
    assert hand.h.scan() == []
    # A new watcher (a restart) records it as seen again: still nothing.
    h2 = Handoff(hand.store, pool(), hand.h.bus, adb=hand.adb, clock=hand.clock)
    h2.scan()
    hand.clock.t += 60
    assert h2.scan() == []
    os.utime(hand.box / "old.mp4", (1, 1))  # replaced by a newer file of the same name
    assert [i["name"] for i in settle(SimpleNamespace(h=h2, clock=hand.clock))] == ["old.mp4"]


def test_hidden_partial_linked_fake_and_oversized_files_are_ignored(hand):
    hand.h.max_bytes = 1000
    hand.h.scan()
    (hand.box / ".hidden.mp4").write_bytes(MP4)
    for ext in (".part", ".crdownload", ".download"):
        (hand.box / f"clip.mp4{ext}").write_bytes(MP4)
    (hand.box / "notes.txt").write_text("hello")
    (hand.box / "clip.json").write_text("{}")
    (hand.box / "report.mp4").write_text("not a video at all, just text")  # a renamed document
    (hand.box / "huge.mp4").write_bytes(MP4 + b"\x00" * 2000)
    outside = hand.tmp / "outside.jpg"
    outside.write_bytes(JPEG)
    (hand.box / "linked.jpg").symlink_to(outside)
    (hand.box / "folder.mp4").mkdir()
    assert settle(hand) == [] and hand.h.items() == []


def test_a_sidecar_written_after_its_video_still_counts_while_it_waits(hand, monkeypatch):
    monkeypatch.setitem(HANDOFF_TEMPLATES, "instagram", {**INSTAGRAM})
    hand.store.set_setting("phone_apps", ["com.instagram.android"])
    hand.h.scan()
    (hand.box / "clip.mp4").write_bytes(MP4)
    [item] = settle(hand)
    assert item["app"] is None and item["caption"] is None and item["device"] == "envoy-test"
    (hand.box / "clip.json").write_text(json.dumps({"app": "gallery", "caption": "Sunset at the pier"}))
    hand.h.scan()
    got = hand.h.item(item["id"])
    assert (got["app"], got["caption"]) == ("gallery", "Sunset at the pier")
    (hand.box / "clip.json").write_text(json.dumps({"app": "Instagram", "caption": "Sunset at the pier"}))
    hand.h.scan()
    got = hand.h.item(item["id"])
    assert (got["app"], got["device"]) == ("instagram", "phone-0A1B")  # routed again for the app the sidecar names
    assert hand.adb.calls == []


def test_the_outbox_comes_from_the_setting_then_the_environment_then_home(tmp_path, monkeypatch):
    store = TaskStore(":memory:")
    h = Handoff(store, pool(), SimpleNamespace(publish=lambda *a, **k: None))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("ENVOY_OUTBOX")
    assert h.outbox() == (tmp_path / "home" / "Envoy Outbox").resolve() and h.outbox().is_dir()  # created
    monkeypatch.setenv("ENVOY_OUTBOX", str(tmp_path / "env"))
    assert h.outbox() == (tmp_path / "env").resolve()
    assert h.set_outbox(str(tmp_path / "set")) == (tmp_path / "set").resolve()
    assert h.outbox() == (tmp_path / "set").resolve()
    with pytest.raises(HandoffError):
        h.set_outbox("relative/folder")
    (tmp_path / "afile").write_text("x")
    with pytest.raises(HandoffError):
        h.set_outbox(str(tmp_path / "afile"))


def test_a_name_in_the_outbox_is_never_a_path(hand):
    (hand.box / "clip.mp4").write_bytes(MP4)
    (hand.tmp / "secret.jpg").write_bytes(JPEG)
    (hand.box / "link.jpg").symlink_to(hand.tmp / "secret.jpg")
    assert hand.h.outbox_file("clip.mp4") == hand.box / "clip.mp4"
    for bad in ("../secret.jpg", str(hand.tmp / "secret.jpg"), "~/secret.jpg", "sub/clip.mp4", "..", ".", "", ".clip.mp4",
                "link.jpg", "missing.mp4", "clip.mp4\x00.jpg", "..\\secret.jpg"):
        with pytest.raises(HandoffError):
            hand.h.outbox_file(bad)


# ---- push_file -------------------------------------------------------------------------------------


def test_push_file_copies_into_the_gallery_folders_dates_it_now_and_checks_the_media_store(hand):
    (hand.box / "Sunset at the pier!.mp4").write_bytes(MP4)
    got = hand.h.push_file("envoy-test", hand.box / "Sunset at the pier!.mp4")
    assert got == {"device": "envoy-test", "remote_path": "/sdcard/Movies/Envoy/Sunset-at-the-pier.mp4",
                   "media_uri": "content://media/external/video/media/1000"}
    assert {s for s, _ in hand.adb.calls} == {"emulator-5554"}  # always adb -s <serial>, from the pool id
    assert hand.adb.calls[0][1] == ["shell", "mkdir -p /sdcard/Movies/Envoy"]
    assert ["push", str(hand.box / "Sunset at the pier!.mp4"), "/sdcard/Movies/Envoy/Sunset-at-the-pier.mp4"] in [a for _, a in hand.adb.calls]
    assert "touch /sdcard/Movies/Envoy/Sunset-at-the-pier.mp4" in hand.adb.shell()
    assert not any(c.startswith("am broadcast") for c in hand.adb.shell())  # Android 11+: indexed by the write itself
    query = next(c for c in hand.adb.shell() if c.startswith("content query"))
    assert "content://media/external/video/media" in query and "relative_path='Movies/Envoy/'" in query

    (hand.box / "photo.JPG").write_bytes(JPEG)
    again = hand.h.push_file("phone-0A1B", hand.box / "photo.JPG")
    assert again["remote_path"] == "/sdcard/Pictures/Envoy/photo.jpg" and again["media_uri"].startswith("content://media/external/images/media/")
    assert hand.adb.calls[-1][0] == "0A1B2C3D"
    # The same name twice is a new item (dated now), not an update of the old one.
    assert hand.h.push_file("envoy-test", hand.box / "Sunset at the pier!.mp4")["remote_path"] == "/sdcard/Movies/Envoy/Sunset-at-the-pier-2.mp4"


def test_without_the_media_provider_indexing_writes_the_scan_broadcast_does(hand):
    hand.h.adb = adb = FakeAdb(fuse=False)
    (hand.box / "clip.mp4").write_bytes(MP4)
    got = hand.h.push_file("envoy-test", hand.box / "clip.mp4")
    assert got["media_uri"].endswith("/1000")
    assert "am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/Movies/Envoy/clip.mp4" in adb.shell()


def test_push_file_refuses_what_it_cant_send(hand):
    (hand.box / "clip.mp4").write_bytes(MP4)
    (hand.box / "doc.mp4").write_text("text")
    (hand.box / "notes.txt").write_text("text")
    hand.h.pool.phones["phone-LOCKED"] = {"id": "phone-LOCKED", "serial": "LOCKED", "state": "unauthorized"}
    for device, name in (("envoy-test", "doc.mp4"), ("envoy-test", "notes.txt"), ("phone-LOCKED", "clip.mp4"),
                         ("phone-GONE", "clip.mp4"), ("emulator-5554", "clip.mp4")):
        with pytest.raises(HandoffError):
            hand.h.push_file(device, hand.box / name)
    hand.h.max_bytes = 10
    with pytest.raises(HandoffError):
        hand.h.push_file("envoy-test", hand.box / "clip.mp4")
    assert hand.adb.calls == []


def test_send_marks_the_item_and_a_failure_is_kept(hand):
    hand.h.scan()
    (hand.box / "clip.mp4").write_bytes(MP4)
    [item] = settle(hand)
    sent = hand.h.send(item["id"])
    assert (sent["status"], sent["device"], sent["remote_path"]) == ("sent", "envoy-test", "/sdcard/Movies/Envoy/clip.mp4")
    assert hand.h.send(item["id"])["status"] == "sent" and sum(a[0] == "push" for _, a in hand.adb.calls) == 1  # once
    (hand.box / "gone.mp4").write_bytes(MP4)
    [other] = settle(hand)
    (hand.box / "gone.mp4").unlink()
    failed = hand.h.send(other["id"])
    assert failed["status"] == "failed" and "no gone.mp4" in failed["error"]


def test_routing_picks_the_phone_for_an_app_set_to_it(hand, monkeypatch):
    monkeypatch.setitem(HANDOFF_TEMPLATES, "instagram", {**INSTAGRAM})
    assert hand.h.default_device("instagram") == ("envoy-real", None)  # a real app, on the real-app emulator by default
    hand.store.set_setting("phone_apps", ["com.instagram.android"])
    assert hand.h.default_device("instagram") == ("phone-0A1B", None)  # "use my phone" for Instagram
    assert hand.h.default_device(None) == ("envoy-test", None)  # no app: the default emulator
    assert hand.h.pick("phone") == "phone-0A1B" and hand.h.pick("emulator") == "envoy-test"
    with pytest.raises(HandoffError):
        hand.h.pick("emulator-5554")  # an adb serial is not a phone's id


# ---- downloads -------------------------------------------------------------------------------------


@pytest.fixture()
def https_server(tmp_path):
    """A local HTTPS server with its own certificate, so the download rules run against a real TLS server."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(1)
            .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False).sign(key, hashes.SHA256()))
    (tmp_path / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (tmp_path / "key.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    routes = {
        "/clip.mp4": (200, "video/mp4", MP4, {}), "/photo": (200, "image/jpeg; charset=binary", JPEG, {}),
        "/page.mp4": (200, "text/html", b"<html>login</html>", {}), "/lies.mp4": (200, "video/mp4", b"<html>not a video</html>", {}),
        "/big.mp4": (200, "video/mp4", MP4, {"Content-Length": str(10**10)}), "/stream.mp4": (200, "video/mp4", MP4 * 20, {"_chunked": "1"}),
        "/to-http": (302, "text/plain", b"", {"Location": "http://localhost/clip.mp4"}), "/to-clip": (302, "text/plain", b"", {"Location": "/clip.mp4"}),
        "/loop": (302, "text/plain", b"", {"Location": "/loop"}), "/missing.mp4": (404, "text/plain", b"no", {}),
    }

    class H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            code, ctype, body, headers = routes.get(self.path, (404, "text/plain", b"", {}))
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            chunked = headers.pop("_chunked", None) if "_chunked" in headers else None
            for k, v in headers.items():
                self.send_header(k, v)
            if chunked:
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                for i in range(0, len(body), 100):
                    part = body[i:i + 100]
                    self.wfile.write(f"{len(part):x}\r\n".encode() + part + b"\r\n")
                self.wfile.write(b"0\r\n\r\n")
                return
            if "Content-Length" not in headers:
                self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                pass

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(tmp_path / "cert.pem", tmp_path / "key.pem")
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    client = ssl.create_default_context(cafile=str(tmp_path / "cert.pem"))
    yield SimpleNamespace(url=f"https://localhost:{srv.server_address[1]}", verify=client)
    srv.shutdown()


def test_downloads_are_https_public_media_and_capped(hand, https_server):
    s = https_server
    got = hand.h.download(f"{s.url}/clip.mp4", verify=s.verify)
    assert got == hand.box / "clip.mp4" and got.read_bytes() == MP4
    assert hand.h.download(f"{s.url}/clip.mp4", verify=s.verify).name == "clip-2.mp4"  # never over another file
    assert hand.h.download(f"{s.url}/photo", verify=s.verify).name == "photo.jpg"  # named by its type
    assert hand.h.download(f"{s.url}/to-clip", verify=s.verify).name == "clip-3.mp4"  # an https redirect is followed
    hand.h.max_bytes = len(MP4) * 5
    for path, why in (("/page.mp4", "isn't a photo or video"), ("/lies.mp4", "by its contents"), ("/big.mp4", "over"),
                      ("/stream.mp4", "over"), ("/to-http", "only https"), ("/loop", "too many redirects"), ("/missing.mp4", "404")):
        with pytest.raises(HandoffError, match=why):
            hand.h.download(f"{s.url}{path}", verify=s.verify)
    with pytest.raises(HandoffError, match="download failed"):
        hand.h.download(f"{s.url}/clip.mp4")  # its certificate isn't trusted
    assert sorted(p.name for p in hand.box.iterdir()) == ["clip-2.mp4", "clip-3.mp4", "clip.mp4", "photo.jpg"]  # nothing left half-written


def test_downloads_never_reach_this_mac_or_its_network(hand, https_server):
    hand.h.resolve_ip = __import__("api.handoff", fromlist=["_resolve"])._resolve  # real DNS
    for url in (f"{https_server.url}/clip.mp4", "https://127.0.0.1/x.mp4", "https://10.0.0.8/x.mp4", "https://169.254.169.254/latest",
                "https://[::1]/x.mp4", "https://192.168.1.20/x.jpg", "http://example.com/x.mp4", "file:///etc/hosts",
                "https://user:pw@example.com/x.mp4", "ftp://example.com/x.mp4"):
        with pytest.raises(HandoffError):
            hand.h.download(url, verify=https_server.verify)
    assert list(hand.box.iterdir()) == []
