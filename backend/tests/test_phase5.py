"""Offline tests for Phase 5 (the iPhone companion and voice): pairing and device tokens, host checks, Web Push through a
fake push service that decrypts what it gets, photo upload with the Mac's own OCR and a scripted model (and the image
deleted), the voice relay against a fake Transcribe socket, and that no new path can approve anything."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont, ImageStat

from api.auth import Auth
from api.store import TaskStore
from memory.store import MemoryStore
from models.adapter import CostMeter
from models.schemas import ExtractionOutput
from test_api import FakeDevice, approver_for, ask, pending
from test_handoff import MP4


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_BEARER_TOKEN", "mcp-test-token")
    monkeypatch.setenv("ENVOY_PUBLIC_URL", "https://envoy-mac.example.ts.net:8443")
    monkeypatch.setenv("ENVOY_ALLOWED_HOSTS", "testserver")
    monkeypatch.setattr("api.app.API_DIR", tmp_path)
    monkeypatch.setattr("api.push.LOG", tmp_path / "push.jsonl")
    monkeypatch.setattr("api.app.LOGS", tmp_path)
    from api.app import build, session_token
    from routines.store import RoutineStore
    adapter = SimpleNamespace(api_key="meta-test-key", meter=CostMeter(tmp_path / "costs.jsonl", daily_cap_usd=5), calls=[])
    memory = MemoryStore(":memory:")
    app, ctx = build("demo", memory=memory, tasks=TaskStore(":memory:"), routines=RoutineStore(tmp_path / "routines"), adapter=adapter)
    return SimpleNamespace(app=app, ctx=ctx, token=session_token(), adapter=adapter, memory=memory, tmp=tmp_path)


def me(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---- pairing and device tokens ------------------------------------------------------------------------


def test_pairing_code_is_single_use_short_lived_and_limited():
    now = [1000.0]
    auth = Auth(TaskStore(":memory:"), "owner-token", clock=lambda: now[0])
    code = auth.start_pairing()["code"]
    assert len(code) == 6 and code.isdigit()
    for _ in range(5):
        assert auth.finish_pairing("000000" if code != "000000" else "111111", "iPhone") is None
    assert auth.finish_pairing(code, "iPhone") is None  # five wrong tries kill the code
    code = auth.start_pairing()["code"]
    now[0] += 301
    assert auth.finish_pairing(code, "iPhone") is None  # five minutes
    code = auth.start_pairing()["code"]
    tok = auth.finish_pairing(code, "Maya's iPhone")
    assert tok and auth.finish_pairing(code, "again") is None  # one use
    c = auth.check(tok)
    assert c.kind == "device" and c.is_session and c.name == "Maya's iPhone"
    assert auth.check("owner-token").kind == "owner"
    assert auth.revoke(c.device_id) and auth.check(tok) is None


def test_pairing_over_http_and_what_each_credential_can_do(env):
    with TestClient(env.ctx.asgi) as c:
        assert c.post("/api/pair/start", headers={**me("nope"), "X-Envoy": "1"}).status_code == 403
        code = c.post("/api/pair/start", headers=me(env.token)).json()["code"]
        phone = TestClient(env.ctx.asgi, base_url="https://testserver")
        assert phone.post("/api/pair", json={"code": code, "name": "iPhone"}).status_code == 403  # no X-Envoy
        r = phone.post("/api/pair", json={"code": code, "name": "iPhone"}, headers={"X-Envoy": "1"})
        assert r.status_code == 200
        cookie = r.headers["set-cookie"].lower()
        assert "httponly" in cookie and "secure" in cookie and "samesite=strict" in cookie
        assert phone.get("/api/state").status_code == 200  # the paired iPhone is a session
        assert phone.post("/api/pair/start", headers={"X-Envoy": "1"}).status_code == 403  # new devices only from the Mac
        shortcut = phone.post("/api/tokens", json={"scope": "photos"}, headers={"X-Envoy": "1"}).json()["token"]
        assert phone.post("/api/tokens", json={"scope": "session"}, headers={"X-Envoy": "1"}).status_code == 400
        # The Shortcut's token can upload images and nothing else.
        assert c.get("/api/state", headers=me(shortcut)).status_code == 401
        assert c.get("/api/approvals", headers=me(shortcut)).status_code == 401
        assert c.post("/api/tasks", json={"goal": "check me in"}, headers=me(shortcut)).status_code == 401
        assert c.post("/api/chat", json={"message": "hi"}, headers=me(shortcut)).status_code == 401
        assert c.post("/api/photos", content=b"x", headers=me(shortcut)).status_code == 403  # photos are off by default
        with pytest.raises(Exception):
            with c.websocket_connect("/api/events", headers=me(shortcut)) as ws:
                ws.receive_json()
        devices = c.get("/api/paired", headers=me(env.token)).json()["devices"]
        iphone = next(d for d in devices if d["scope"] == "session")
        assert c.delete(f"/api/paired/{iphone['id']}", headers=me(env.token)).json()["revoked"]
        assert phone.get("/api/state").status_code == 401


def test_only_known_hosts_and_origins(env):
    with TestClient(env.ctx.asgi, base_url="https://envoy-mac.example.ts.net:8443") as c:
        assert c.get("/healthz", headers={"Host": "evil.example"}).status_code == 421  # DNS rebinding: another name that points here
        assert c.get("/healthz").status_code == 200  # the tailnet name
        with pytest.raises(Exception):
            with c.websocket_connect("/api/events", headers={**me(env.token), "Origin": "https://evil.example"}) as ws:
                ws.receive_json()
        with c.websocket_connect("/api/events", headers={**me(env.token), "Origin": "https://envoy-mac.example.ts.net:8443"}):
            pass


# ---- push --------------------------------------------------------------------------------------------


class FakePushService:
    """Stands in for Apple's push service: checks the VAPID signature and decrypts the payload with the subscriber's key."""

    def __init__(self) -> None:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.auth = os.urandom(16)
        self.p256dh = b64(self.key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
        self.received: list[dict] = []
        svc = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # noqa: ANN002
                pass

            def do_POST(self) -> None:  # noqa: N802
                import http_ece
                import jwt
                from cryptography.hazmat.primitives.asymmetric import ec as ec_
                body = self.rfile.read(int(self.headers["Content-Length"]))
                if self.path.endswith("/gone"):
                    self.send_response(410)
                    self.end_headers()
                    return
                vapid = dict(p.strip().split("=", 1) for p in self.headers["Authorization"].removeprefix("vapid ").split(","))
                pub = ec_.EllipticCurvePublicKey.from_encoded_point(ec_.SECP256R1(), base64.urlsafe_b64decode(vapid["k"] + "=="))
                claims = jwt.decode(vapid["t"], pub, algorithms=["ES256"], audience=f"http://127.0.0.1:{svc.port}")
                plain = http_ece.decrypt(body, private_key=svc.key, auth_secret=svc.auth, version="aes128gcm")
                svc.received.append({"payload": json.loads(plain), "claims": claims, "encoding": self.headers["Content-Encoding"],
                                     "urgency": self.headers.get("Urgency"), "ttl": self.headers.get("TTL")})
                self.send_response(201)
                self.end_headers()

        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def subscription(self, path: str = "/push/sub1") -> dict:
        return {"endpoint": f"http://127.0.0.1:{self.port}{path}", "keys": {"p256dh": self.p256dh, "auth": b64(self.auth)}}

    def wait(self, n: int, timeout: float = 5) -> list[dict]:
        t0 = time.time()
        while len(self.received) < n and time.time() - t0 < timeout:
            time.sleep(0.02)
        return self.received


def test_an_approval_request_pushes_and_the_push_cannot_approve(env):
    svc = FakePushService()
    store, pusher = env.ctx.tasks, env.ctx.pusher
    with TestClient(env.ctx.asgi) as c:
        assert c.post("/api/push/subscribe", json={"subscription": {"endpoint": "ftp://x", "keys": {}}}, headers=me(env.token)).status_code == 400
        assert c.post("/api/push/subscribe", json={"subscription": svc.subscription()}, headers=me(env.token)).status_code == 200
        c.post("/api/settings/approvals", json={"default": "always"}, headers=me(env.token))
        task = store.create("Check me in for my flight", "web", request="Check me in for my flight")
        device = FakeDevice()
        approver, bus, _ = approver_for(store, device)
        approver.task_id, approver.bus = task["id"], env.ctx.bus
        approver.rules = lambda: __import__("policy.approval_rules", fromlist=["ApprovalRules"]).ApprovalRules.from_dict(store.setting("approval_rules"))
        env.ctx.runner.approvers[task["id"]] = approver
        out = ask(approver)
        rec = pending(store)
        got = svc.wait(1)
        assert len(got) == 1
        p = got[0]["payload"]
        assert p["kind"] == "approval" and p["url"] == f"/approve/?id={rec['id']}" and got[0]["encoding"] == "aes128gcm"
        assert got[0]["urgency"] == "high" and got[0]["claims"]["sub"].startswith(("mailto:", "https://"))
        assert rec["nonce"] not in json.dumps(p)  # a push can't decide anything
        assert store.approval(rec["id"])["status"] == "pending"
        r = c.post("/api/push/receipt", json={"id": p["id"], "shown_at": time.time() * 1000}, headers=me(env.token)).json()
        assert r["receipt"]["delivery_ms"] >= 0
        assert store.approval(rec["id"])["status"] == "pending"  # neither the push nor its receipt approved anything
        approver.decide(rec["id"], True)
        out["thread"].join(3)


def test_no_push_when_your_request_already_approved(env):
    svc = FakePushService()
    store = env.ctx.tasks
    env.ctx.pusher.subscribe(svc.subscription(), None)
    task = store.create("Check me in for my flight", "chat", request="Check me in for my flight")
    approver, _, _ = approver_for(store, FakeDevice())
    approver.task_id, approver.bus = task["id"], env.ctx.bus
    from policy.approvals import ApprovalRequest
    out: dict = {}
    t = threading.Thread(target=lambda: out.update(d=approver.request(ApprovalRequest(
        task["id"], "check in", "com.skylark.air", 'tap "Confirm check-in"', ["rule: confirm"], "SL 482 · ATL → ORD",
        origin="routine_step", target="Confirm check-in"))))
    t.start()  # default rules: "ask unless I asked for it", and the request named the action
    t.join(3)
    assert out["d"].approved and out["d"].by == "your request"
    time.sleep(0.3)
    assert svc.received == []


def test_takeover_and_finished_tasks_push_and_dead_subscriptions_are_dropped(env):
    svc = FakePushService()
    pusher, store, bus = env.ctx.pusher, env.ctx.tasks, env.ctx.bus
    pusher.subscribe(svc.subscription(), None)
    pusher.subscribe(svc.subscription("/push/gone"), None)
    bus.publish("takeover_requested", avd="envoy-test", task_id="t1", reason="sign-in needed: password field")
    done = store.create("Check me in for my flight", "web")
    store.update(done["id"], status="done", result="seat: 14C; gate: B12")
    bus.publish("task_finished", task_id=done["id"])
    quiet = store.create("What's my gate?", "trigger:watch gate")
    store.update(quiet["id"], status="done", result="B12")
    bus.publish("task_finished", task_id=quiet["id"])
    got = svc.wait(2)
    time.sleep(0.3)
    kinds = [(g["payload"]["kind"], g["payload"]["title"]) for g in got]
    assert ("takeover", "Envoy needs you to take over") in kinds
    assert ("task", "Done: Check me in for my flight") in kinds
    # A watcher's routine finishing "done" doesn't buzz the phone; it pushes only when its run changed a remembered fact
    # it watches ("Gate changed: B12 → C14", tests/test_alerts.py), and this run changed nothing.
    assert ("task", "Done: What's my gate?") not in kinds and len(got) == 2
    assert [s["endpoint"].endswith("/sub1") for s in pusher.subscriptions()] == [True]  # 410 → forgotten


# ---- photos -------------------------------------------------------------------------------------------


def boarding_pass_png(card: bool = False) -> bytes:
    img = Image.new("RGB", (1080, 1500), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 46)
    except OSError:
        font = ImageFont.load_default()
    rows = [("Boarding pass", ""), ("Maya Patel", ""), ("Flight", "SL 482 · ATL → ORD"), ("Date", "Fri, Oct 30, 2026"),
            ("Seat", "14C"), ("Gate", "B12"), ("Boarding", "5:30 AM · Group 3")]
    if card:
        rows.append(("Paid with card", "4111 1111 1111 1111"))
    for i, (label, value) in enumerate(rows):
        d.text((60, 80 + i * 150), label, fill="black", font=font)
        if value:
            d.text((560, 80 + i * 150), value, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def scripted_extraction(adapter, facts: dict[str, dict[str, str]]):
    def call(job, content, instructions=None, data_scope="real", task_id=None, **kw):
        adapter.calls.append({"job": job, "content": content, "data_scope": data_scope})
        ents = [{"ref": f"e{i}", "type": t, "facts": [{"attribute": a, "value": v, "evidence": None} for a, v in fs.items()]}
                for i, (t, fs) in enumerate(facts.items())]
        links = [{"from_ref": "e1", "relation": "includes", "to_ref": "e0"}] if len(ents) > 1 else []
        return SimpleNamespace(parsed=ExtractionOutput.model_validate({"entities": ents, "links": links}), cost_at_standard_usd=0.004)
    adapter.call = call


def seed_trip(mem: MemoryStore) -> tuple[str, str]:
    trip, flight = mem.create_entity("Trip"), mem.create_entity("Flight")
    src = mem.add_source("email", {"subject": "Your SkyLark trip", "from": "SkyLark Air"})
    mem.observe(trip, "confirmation_code", "KX7Q2M", source=src)
    mem.observe(trip, "destination", "Chicago", source=src)
    mem.observe(flight, "number", "SL 482", source=src)
    mem.observe(flight, "date", "Fri, Oct 30, 2026", source=src)
    mem.link(trip, "includes", flight, src)
    mem.refresh_keys(trip)
    mem.refresh_keys(flight)
    mem.commit()
    return trip, flight


def test_a_boarding_pass_screenshot_becomes_facts_on_the_known_flight_and_is_deleted(env):
    trip, flight = seed_trip(env.memory)
    scripted_extraction(env.adapter, {"Flight": {"number": "SL 482", "date": "Fri, Oct 30, 2026", "seat": "14C", "gate": "B12",
                                                 "terminal": "T9"},  # T9 isn't in the image: dropped
                                      "Trip": {"destination": "Chicago"}})
    with TestClient(env.ctx.asgi) as c:
        token = c.post("/api/tokens", json={"scope": "photos"}, headers=me(env.token)).json()["token"]
        assert c.post("/api/photos", content=boarding_pass_png(), headers=me(token)).status_code == 403  # off by default
        c.post("/api/settings/photos", json={"enabled": True}, headers=me(env.token))
        r = c.post("/api/photos", content=boarding_pass_png(card=True), headers={**me(token), "Content-Type": "image/png"})
    assert r.status_code == 200, r.text
    res = r.json()["results"][0]
    assert res["deleted"] and list((env.tmp / "photos").iterdir()) == []  # the image is gone
    assert flight in res["entities"]
    assert len(env.memory.entities("Flight")) == 1 and len(env.memory.entities("Trip")) == 1  # merged, not new
    cur = {f["attribute"]: f for f in env.memory.current_facts(flight)}
    assert cur["seat"]["value"] == "14C" and cur["gate"]["value"] == "B12" and "terminal" not in cur
    assert any("terminal" in d for d in res["dropped"])
    src = env.memory.source(cur["seat"]["source"])
    assert src["kind"] == "photo" and src["reference"]["origin"] == "shortcut"
    assert "[card number]" in src["snapshot"] and "4111" not in src["snapshot"]  # kept text is redacted
    assert res["redacted_lines"] >= 1
    sent = env.adapter.calls[-1]
    assert sent["data_scope"] == "real" and "4111" not in json.dumps(sent["content"][1])
    img = Image.open(io.BytesIO(base64.b64decode(sent["content"][0]["image_url"].split(",", 1)[1]))).convert("L")
    w, h = img.size
    band = img.crop((int(w * 0.55), int(h * (80 + 7 * 150) / 1500), int(w * 0.95), int(h * (80 + 7 * 150 + 40) / 1500)))
    assert ImageStat.Stat(band).mean[0] < 40  # the card number was blacked out before it left the Mac


def test_the_photo_picker_uses_your_session(env):
    seed_trip(env.memory)
    scripted_extraction(env.adapter, {"Flight": {"number": "SL 482", "date": "Fri, Oct 30, 2026", "seat": "14C"}})
    with TestClient(env.ctx.asgi) as c:
        c.post("/api/settings/photos", json={"enabled": True}, headers=me(env.token))
        r = c.post("/api/photos", files={"file": ("bp.png", boarding_pass_png(), "image/png")}, headers=me(env.token))
        assert r.status_code == 200 and r.json()["results"][0]["deleted"]
        assert c.post("/api/photos", content=b"not an image", headers=me(env.token)).status_code == 400
    assert list((env.tmp / "photos").iterdir()) == []


# ---- voice ---------------------------------------------------------------------------------------------


class FakeTranscribe:
    """Muse Voice Transcribe's realtime protocol, as documented: handshake → {sessionId}; PCM; endStream → final; close."""

    def __init__(self, text: str = "check me in for my flight") -> None:
        import websockets
        self.text, self.handshake, self.audio = text, None, 0
        self.loop = asyncio.new_event_loop()
        ready = threading.Event()

        async def handler(ws) -> None:  # noqa: ANN001
            self.handshake = json.loads(await ws.recv())
            await ws.send(json.dumps({"sessionId": "sess-1"}))
            async for m in ws:
                if isinstance(m, bytes):
                    self.audio += len(m)
                    await ws.send(json.dumps({"type": "transcript", "transcript": "check me", "final": False}))
                elif json.loads(m).get("type") == "endStream":
                    await ws.send(json.dumps({"type": "transcript", "transcript": self.text, "final": True}))
                    await ws.close(1000)
                    return

        async def main() -> None:
            self.server = await websockets.serve(handler, "127.0.0.1", 0)
            self.port = self.server.sockets[0].getsockname()[1]
            ready.set()
            await asyncio.Future()

        threading.Thread(target=lambda: self.loop.run_until_complete(main()), daemon=True).start()
        ready.wait(5)
        self.url = f"ws://127.0.0.1:{self.port}"


def test_voice_relays_audio_to_transcribe_and_keeps_the_key_on_the_server(env, monkeypatch):
    fake = FakeTranscribe()
    monkeypatch.setattr("api.voice.ASR_URL", fake.url)
    with TestClient(env.ctx.asgi) as c:
        with c.websocket_connect("/api/voice", headers=me(env.token)) as ws:
            ws.send_json({"type": "start"})
            for _ in range(13):  # about a second of 24 kHz PCM in 80 ms chunks
                ws.send_bytes(b"\x00\x01" * 1920)
            msgs = []
            while True:
                m = ws.receive_json()
                msgs.append(m)
                if m["type"] == "ready":
                    ws.send_json({"type": "stop"})
                if m["type"] in ("final", "error"):
                    break
    final = msgs[-1]
    assert final["type"] == "final" and final["text"] == "check me in for my flight", msgs
    assert fake.handshake["authorization"]["accessToken"] == "Bearer meta-test-key"  # the key goes from the server only
    assert fake.handshake["mode"] == "PUSH_TO_TALK" and fake.handshake["audioEncoding"] == "PCM_24KHZ"
    assert fake.audio == 13 * 3840 and final["audio_ms"] == 1040
    costs = [json.loads(x) for x in (env.tmp / "costs.jsonl").read_text().splitlines()]
    assert costs[-1]["job"] == "voice" and costs[-1]["audio_s"] == 1.04 and costs[-1]["cost_usd"] == pytest.approx(1 / 3600 * 0.18)
    with pytest.raises(Exception):
        with TestClient(env.ctx.asgi).websocket_connect("/api/voice") as ws:  # no session, no microphone relay
            ws.receive_json()


def test_a_spoken_request_is_your_own_words(env, monkeypatch):
    started = []
    monkeypatch.setattr(env.ctx.runner, "start", lambda goal, source, **kw: started.append((goal, source, kw)) or {"id": "t1", "goal": goal, "status": "queued"})
    from models.schemas import ChatRoute
    env.adapter.call = lambda *a, **k: SimpleNamespace(parsed=ChatRoute(kind="task", goal="Check me in for my flight", reply=""), cost_at_standard_usd=0.001)
    with TestClient(env.ctx.asgi) as c:
        r = c.post("/api/chat", json={"message": "check me in for my flight", "source": "voice"}, headers=me(env.token)).json()
        c.post("/api/chat", json={"message": "check me in for my flight", "source": "mcp"}, headers=me(env.token))
    assert started[0][1] == "voice" and started[0][2]["request"] == "check me in for my flight"
    assert started[1][1] == "chat"  # a client can't claim another source
    assert r["spoken"] == "On it: Check me in for my flight."
    from policy.approval_rules import DIRECT_SOURCES
    assert "voice" in DIRECT_SOURCES


# ---- nothing new can approve --------------------------------------------------------------------------


def test_no_new_path_approves(env):
    store = env.ctx.tasks
    task = store.create("check in", "web")
    approver, _, _ = approver_for(store, FakeDevice())
    approver.task_id = task["id"]
    approver.rules = lambda: __import__("policy.approval_rules", fromlist=["ApprovalRules"]).ApprovalRules(default="always")
    env.ctx.runner.approvers[task["id"]] = approver
    out = ask(approver)
    rec = pending(store)
    body = {"decision": "approve", "nonce": rec["nonce"]}
    with TestClient(env.ctx.asgi) as c:
        photos = c.post("/api/tokens", json={"scope": "photos"}, headers=me(env.token)).json()["token"]
        codes = c.post("/api/tokens", json={"scope": "code_test"}, headers=me(env.token)).json()["token"]
        for tok in (photos, codes, "mcp-test-token"):
            assert c.post(f"/api/approvals/{rec['id']}", json=body, headers=me(tok)).status_code == 401
            assert c.get(f"/api/approvals/{rec['id']}", headers=me(tok)).status_code == 401  # can't even read the nonce
        c.post("/api/push/receipt", json={"id": rec["id"]}, headers=me(env.token))
        c.post("/api/metrics", json={"kind": "live", "approve": rec["id"]}, headers=me(env.token))
        c.post("/api/codes/test", content=b"Your code is 123456", headers=me(codes))
        assert c.get(f"/approve/?id={rec['id']}").status_code in (200, 404)  # opening the page decides nothing
        assert store.approval(rec["id"])["status"] == "pending"
        # Your paired iPhone is you: it approves the same way the Mac does (session + nonce + POST).
        code = c.post("/api/pair/start", headers=me(env.token)).json()["code"]
        phone = TestClient(env.ctx.asgi)
        phone.post("/api/pair", json={"code": code, "name": "iPhone"}, headers={"X-Envoy": "1"})
        assert phone.post(f"/api/approvals/{rec['id']}", json=body).status_code == 403  # a cookie needs X-Envoy
        assert phone.post(f"/api/approvals/{rec['id']}", json=body, headers={"X-Envoy": "1"}).json()["status"] == "approved"
    out["thread"].join(3)
    assert out["d"].approved
    rec = json.loads((env.tmp / "code_test.jsonl").read_text())
    assert rec["has_code_word"] and "123456" not in json.dumps(rec)  # only that a message came, never its text or code


def test_a_stalled_microphone_is_padded_with_silence_to_real_time(env, monkeypatch):
    """Found on the iPhone: with no audio from the microphone, Transcribe closed the stream ("Ingress audio slower than
    real-time"). The relay now keeps the stream at real time with silence."""
    fake = FakeTranscribe("")
    monkeypatch.setattr("api.voice.ASR_URL", fake.url)
    with TestClient(env.ctx.asgi) as c:
        with c.websocket_connect("/api/voice", headers=me(env.token)) as ws:
            ws.send_json({"type": "start"})
            assert ws.receive_json()["type"] == "ready"
            time.sleep(1.2)  # the microphone sends nothing
            ws.send_json({"type": "stop"})
            final = ws.receive_json()
            while final["type"] == "partial":
                final = ws.receive_json()
    assert final["type"] == "final" and final["text"] == ""
    assert fake.audio >= 0.8 * 48000 and final["silence_ms"] >= 800  # silence kept the stream at real time


def test_a_public_tunnel_reaches_mcp_only(env):
    """Muse needs a public address for Envoy's MCP server (route 2). The tunnel's host is accepted for /mcp alone, and
    the outbox's door under it (/mcp/outbox, backlog #48) with the same key; the web app, the API and the approval pages
    are never served there."""
    (env.tmp / "mcp_public_url").write_text("https://quiet-river-1234.trycloudflare.com")
    tunnel = {"Host": "quiet-river-1234.trycloudflare.com"}
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    hdr = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json", "MCP-Protocol-Version": "2025-11-25"}
    key = {"Authorization": "Bearer mcp-test-token"}
    clip = {"file": ("clip.mp4", MP4, "video/mp4")}
    with TestClient(env.ctx.asgi) as c:
        r = c.post("/mcp", json=body, headers={**hdr, **tunnel, **key})
        assert r.status_code == 200 and "run_task" in r.text
        assert c.post("/mcp", json=body, headers={**hdr, **tunnel}).status_code == 401  # still needs its token
        door = c.post("/mcp/outbox", files=clip, headers={**tunnel, **key})
        assert door.status_code == 200 and door.json()["name"] == "clip.mp4"
        assert c.post("/mcp/outbox", files=clip, headers=tunnel).status_code == 401  # the same key, and only it
        assert c.post("/mcp/outbox", files=clip, headers={**tunnel, **me(env.token)}).status_code == 401
        for path in ("/", "/api/state", "/approve/", "/login?k=x", "/api/pair", "/api/handoff", "/outbox", "/api/handoff/x/send"):
            assert c.get(path, headers={**tunnel, **me(env.token)}).status_code == 421
        (env.tmp / "mcp_public_url").unlink()  # the tunnel script stopped
        assert c.post("/mcp", json=body, headers={**hdr, **tunnel, **key}).status_code == 421
        assert c.post("/mcp/outbox", files=clip, headers={**tunnel, **key}).status_code == 421


def test_a_permanent_public_address_reaches_mcp_only(env, monkeypatch):
    """Muse's connector set up once (Nov 1): MCP_PERMANENT_URL, Tailscale Funnel on a port of its own, is accepted for /mcp
    alone, like a quick tunnel's but with no script running. Anything Tailscale marks as from the internet gets nothing
    but /mcp on that address, even under the tailnet's own name; under /mcp that includes the outbox's door (backlog #48),
    which Funnel's /mcp path already serves."""
    monkeypatch.setenv("MCP_PERMANENT_URL", "https://envoy-mac.example.ts.net:10000/mcp")
    funnel = {"Host": "envoy-mac.example.ts.net:10000", "Tailscale-Funnel-Request": "?1"}
    app_host = {"Host": "envoy-mac.example.ts.net:8443"}  # ENVOY_PUBLIC_URL: the tailnet-only address of the whole app
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    hdr = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json", "MCP-Protocol-Version": "2025-11-25"}
    key = {"Authorization": "Bearer mcp-test-token"}
    with TestClient(env.ctx.asgi) as c:
        clip = {"file": ("clip.mp4", MP4, "video/mp4")}
        r = c.post("/mcp", json=body, headers={**hdr, **funnel, **key})
        assert r.status_code == 200 and "run_task" in r.text
        assert c.post("/mcp", json=body, headers={**hdr, **funnel}).status_code == 401  # still needs its token
        assert c.get("/mcp/outbox", headers={**funnel, **key}).status_code == 200  # the forwarder's hello
        door = c.post("/mcp/outbox", files=clip, headers={**funnel, **key})
        assert door.status_code == 200 and door.json()["name"] == "clip.mp4"
        assert c.post("/mcp/outbox", files=clip, headers=funnel).status_code == 401
        assert c.post("/mcp/outbox", files=clip, headers={**funnel, **me(env.token)}).status_code == 401  # a session isn't its key
        for path in ("/", "/healthz", "/api/state", "/approve/", "/login?k=x", "/api/pair", "/api/handoff", "/api/settings/handoff"):
            assert c.get(path, headers={**funnel, **me(env.token)}).status_code == 421
        assert c.post("/api/handoff/x/send", headers={**funnel, **me(env.token), "X-Envoy": "1"}).status_code == 421
        assert c.get("/healthz", headers=app_host).status_code == 200
        from_internet = {**app_host, "Tailscale-Funnel-Request": "?1"}  # a funneled port under the app's own name
        assert c.get("/healthz", headers=from_internet).status_code == 421
        assert c.post("/mcp", json=body, headers={**hdr, **from_internet, **key}).status_code == 421
        assert c.post("/mcp/outbox", files=clip, headers={**from_internet, **key}).status_code == 421
        assert c.post("/mcp/outbox", files=clip, headers={**app_host, **key}).status_code == 200  # on the tailnet, the door is there too
        monkeypatch.delenv("MCP_PERMANENT_URL")
        assert c.post("/mcp", json=body, headers={**hdr, **funnel, **key}).status_code == 421
        assert c.post("/mcp/outbox", files=clip, headers={**funnel, **key}).status_code == 421


def test_a_funneled_port_is_never_taken_for_the_apps_address(monkeypatch):
    """The API finds its tailnet address in `tailscale serve status`. A port open to the internet that proxies to the API
    (Funnel for Muse) must not become that address: every host it allows gets the whole app."""
    from api import auth
    status = {"Web": {"mac.example.ts.net:10000": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:8700"}}},
                      "mac.example.ts.net:8443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:8700"}}}},
              "AllowFunnel": {"mac.example.ts.net:10000": True}}
    monkeypatch.setattr(auth.subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout=json.dumps(status)))
    assert auth.tailnet_url(8700) == "https://mac.example.ts.net:8443"
    status["Web"].pop("mac.example.ts.net:8443")
    assert auth.tailnet_url(8700) is None


def test_muse_gets_envoys_icon_with_the_server_info(env):
    """Muse's connector card shows the server's icon, and through the tunnel it can fetch nothing but /mcp: so the icon
    comes inside `initialize` as data: URIs, Envoy's mark (web/public/icons/mark.svg and the PNG rendered from it)."""
    (env.tmp / "mcp_public_url").write_text("https://quiet-river-1234.trycloudflare.com")
    hdr = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json", "MCP-Protocol-Version": "2025-11-25",
           "Host": "quiet-river-1234.trycloudflare.com", "Authorization": "Bearer mcp-test-token"}
    body = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "muse", "version": "1"}}}
    with TestClient(env.ctx.asgi) as c:
        r = c.post("/mcp", json=body, headers=hdr)
    assert r.status_code == 200
    info = r.json()["result"]["serverInfo"]
    assert info["name"] == "envoy" and info["title"] == "Envoy"
    png, svg = info["icons"]
    assert png["mimeType"] == "image/png" and png["sizes"] == ["192x192"] and png["src"].startswith("data:image/png;base64,")
    img = Image.open(io.BytesIO(base64.b64decode(png["src"].split(",", 1)[1]))).convert("RGBA")
    assert img.size == (192, 192)
    assert img.getpixel((96, 96))[:3] == (0xF6, 0xF3, 0xEC)  # the cream face
    assert img.getpixel((96, 12))[:3] == (0x3E, 0x7C, 0x5C)  # on the sage tile
    assert img.getpixel((0, 0))[3] == 0  # rounded corners
    assert svg["mimeType"] == "image/svg+xml" and svg["src"].startswith("data:image/svg+xml;base64,")
    mark = base64.b64decode(svg["src"].split(",", 1)[1]).decode()
    assert mark == (Path(__file__).resolve().parents[2] / "web" / "public" / "icons" / "mark.svg").read_text() and "<script" not in mark


def test_codes_read_from_images_tolerate_ocr_confusions_only():
    """Found on SkyLark's Savannah trip: Spark read 3J8N0D from the screenshot, Vision's text said 3J8NOD, and the code was
    dropped. O/0 and I/l/1 now count as the same glyph in codes that mix letters and digits; nothing else does."""
    from memory.extract import _present
    assert _present("3J8N0D", "Confirmation · 3J8NOD")
    assert _present("KX7Q2M", "Confirmation · KX7Q2M")
    assert not _present("3J8N0E", "Confirmation · 3J8NOD")  # a different code
    assert not _present("B12", "Gate · 812")  # short values: exact only
    assert not _present("Denver", "Dallas")
