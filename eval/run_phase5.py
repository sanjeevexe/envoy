"""Phase 5 checks, scripted: push approvals, a boarding-pass screenshot into memory, voice, and the live view over HTTPS.

  uv run --project backend python scripts/demo_setup.py          # SkyLark signed out, fresh demo memory (API stopped)
  uv run --project backend python -m api --profile demo           # with scripts/serve_tailnet.sh on
  uv run --project backend python eval/run_phase5.py [push photo voice live]   # all four by default

1. **push**: a local fake push service (it checks the VAPID signature and decrypts each push with the subscriber's
   key, the way Apple's service and the iPhone would) is subscribed through the API. "Check me in for my flight" runs
   with "always ask"; the sign-in hand-off, the approval request and the finished task each arrive as a push; the
   approval push opens the approval page and carries no nonce; the scripted person approves through the API with the
   session (never the push); the check-in finishes in SkyLark.
2. **photo**: the boarding pass now on SkyLark's screen is captured from the emulator and uploaded through
   /api/photos with a Shortcut token (upload-only); its facts land on the existing SL 482 flight with a photo source,
   no trip or flight is created, and the image file is gone. The token can't read anything.
3. **voice**: a spoken question (macOS `say`, 24 kHz PCM, paced in real time) goes through /api/voice to the real
   Muse Voice Transcribe; the transcript goes to chat as source "voice"; latency and cost are recorded.
4. **live**: the live view through the tailnet HTTPS address (TLS and Tailscale on the path), frame latency against the
   server clock.

Results: eval/results/phase5/gate.json.
"""

from __future__ import annotations

import asyncio
import json
import os
import ssl
import struct
import subprocess
import sys
import time
import wave
from pathlib import Path
from typing import Any

import httpx
import websockets

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "backend" / "tests"))
from demo_setup import demo_fixtures  # noqa: E402
from test_phase5 import FakePushService  # noqa: E402
from testapps.skylark import SkyLark  # noqa: E402

BASE = "http://127.0.0.1:8700"
OUT = REPO / "eval" / "results" / "phase5"
TOKEN = (REPO / "data" / "api" / "session_token").read_text().strip()
H = {"Authorization": f"Bearer {TOKEN}"}
SCRATCH = Path(os.environ.get("TMPDIR", "/tmp")) / "envoy-phase5"
steps: list[dict[str, Any]] = []
T0 = time.time()


def log(name: str, ok: bool, **kw: Any) -> None:
    steps.append({"step": name, "ok": ok, "t": round(time.time() - T0, 1), **kw})
    print(f"{'OK ' if ok else 'BAD'} {name}: " + ", ".join(f"{k}={v}" for k, v in kw.items())[:400], flush=True)


async def wait_for(svc: FakePushService, kind: str, after: int, timeout: float = 30) -> tuple[dict[str, Any] | None, float]:
    t = time.time()
    while time.time() - t < timeout:
        for g in svc.received[after:]:
            if g["payload"]["kind"] == kind:
                return g, g.get("at", time.time())
        await asyncio.sleep(0.05)
    return None, time.time()


# ---- 1. push approvals and the check-in ----------------------------------------------------------------


async def push_and_checkin(c: httpx.AsyncClient) -> None:
    app = SkyLark("emulator-5554")
    await asyncio.to_thread(app.prepare, demo_fixtures(signed_in=False), 0)
    svc = FakePushService()
    orig = svc.server.RequestHandlerClass.do_POST

    def stamped(handler: Any) -> None:  # note when each push arrives
        n = len(svc.received)
        orig(handler)
        if len(svc.received) > n:
            svc.received[-1]["at"] = time.time()
    svc.server.RequestHandlerClass.do_POST = stamped
    sub = await c.post(f"{BASE}/api/push/subscribe", json={"subscription": svc.subscription("/push/eval")}, headers=H)
    log("fake push service subscribed", sub.status_code == 200, service=sub.json())
    before = (await c.get(f"{BASE}/api/settings/approvals", headers=H)).json()["rules"]
    await c.post(f"{BASE}/api/settings/approvals", json={**before, "default": "always", "apps": {}, "routines": {}}, headers=H)
    try:
        async with websockets.connect("ws://127.0.0.1:8700/api/events", additional_headers=H, max_size=None) as ev:
            tid = (await c.post(f"{BASE}/api/tasks", json={"goal": "Check me in for my flight"}, headers=H)).json()["id"]
            requested_at: dict[str, float] = {}
            final = None
            deadline = time.time() + 420
            while time.time() < deadline:
                try:
                    e = json.loads(await asyncio.wait_for(ev.recv(), timeout=deadline - time.time()))
                except asyncio.TimeoutError:
                    break
                if e.get("task_id") != tid and (e.get("task") or {}).get("id") != tid:
                    continue
                if e["type"] == "takeover_requested":
                    requested_at["takeover"] = e["time"]
                    got, at = await wait_for(svc, "takeover", 0)
                    log("takeover request → push", bool(got), push_ms=round((at - e["time"]) * 1000) if got else None,
                        title=got and got["payload"]["title"], url=got and got["payload"]["url"])
                    await c.post(f"{BASE}/api/devices/envoy-test/takeover", headers=H)
                    await asyncio.sleep(1.0)
                    await asyncio.to_thread(app.seed, demo_fixtures(signed_in=True))  # the scripted person signs in (test hook)
                    await asyncio.sleep(1.5)
                    await c.post(f"{BASE}/api/devices/envoy-test/handback", headers=H)
                elif e["type"] == "approval_requested":
                    a = e["approval"]
                    n = len(svc.received)
                    got, at = await wait_for(svc, "approval", 0)
                    full = (await c.get(f"{BASE}/api/approvals/{a['id']}", headers=H)).json()
                    payload = got["payload"] if got else {}
                    log("approval request → push", bool(got) and payload.get("url") == f"/approve/?id={a['id']}" and full["nonce"] not in json.dumps(payload)
                        and full["status"] == "pending", push_ms=round((at - e["time"]) * 1000) if got else None, title=payload.get("title"),
                        body=payload.get("body"), url=payload.get("url"), encrypted=got and got["encoding"], urgency=got and got["urgency"],
                        no_nonce_in_push=full["nonce"] not in json.dumps(payload), still_pending=full["status"] == "pending")
                    d = await c.post(f"{BASE}/api/approvals/{a['id']}", json={"decision": "approve", "nonce": full["nonce"]}, headers=H)
                    log("approved by the person (session + nonce), not by the push", d.status_code == 200, pushes_before=n)
                elif e["type"] == "task" and e["task"]["status"] in ("done", "failed", "declined", "stopped"):
                    final = e["task"]
                    break
            got, at = await wait_for(svc, "task", 0, timeout=10)
            checked = (await asyncio.to_thread(app.trip, "KX7Q2M"))["checked_in"]
            log("check-in done; finished task → push", bool(final) and final["status"] == "done" and checked and bool(got),
                status=(final or {}).get("status"), result=(final or {}).get("result"), checked_in=checked,
                push_title=got and got["payload"]["title"], pushes=[g["payload"]["kind"] for g in svc.received])
    finally:
        await c.post(f"{BASE}/api/settings/approvals", json=before, headers=H)
        await c.post(f"{BASE}/api/push/unsubscribe", json={"endpoint": svc.subscription("/push/eval")["endpoint"]}, headers=H)


# ---- 2. the boarding pass screenshot → memory ----------------------------------------------------------------


async def graph_counts(c: httpx.AsyncClient) -> dict[str, int]:
    g = (await c.get(f"{BASE}/api/memory/graph", headers=H)).json()
    out: dict[str, int] = {}
    for n in g["nodes"]:
        out[n["type"]] = out.get(n["type"], 0) + 1
    return out


async def photo(c: httpx.AsyncClient) -> None:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    shot = SCRATCH / "boarding_pass.png"
    drive = ["uv", "run", "--project", str(REPO / "backend"), "python", str(REPO / "scripts" / "drive.py"), "envoy-test"]
    screen = subprocess.run([*drive, "show"], capture_output=True, text=True, timeout=60).stdout
    if "Boarding pass" not in screen:  # open it from the trip if the app isn't showing it
        subprocess.run([*drive, "tap", "View boarding pass"], capture_output=True, timeout=60)
    shot.write_bytes(subprocess.run(["adb", "-s", "emulator-5554", "exec-out", "screencap", "-p"], capture_output=True, timeout=30).stdout)
    await c.post(f"{BASE}/api/settings/photos", json={"enabled": True, "scope": "screenshots"}, headers=H)
    tok = (await c.post(f"{BASE}/api/tokens", json={"scope": "photos", "name": "eval Shortcut"}, headers=H)).json()["token"]
    T = {"Authorization": f"Bearer {tok}"}
    can_read = (await c.get(f"{BASE}/api/state", headers=T)).status_code
    before = await graph_counts(c)
    t = time.time()
    r = await c.post(f"{BASE}/api/photos", content=shot.read_bytes(), headers={**T, "Content-Type": "image/png"}, timeout=120)
    took = round(time.time() - t, 2)
    res = r.json()["results"][0] if r.status_code == 200 else {"error": r.text}
    after = await graph_counts(c)
    left = [p.name for p in (REPO / "data" / "api" / "photos").glob("*")]
    flight = None
    for n in (await c.get(f"{BASE}/api/memory/graph", headers=H)).json()["nodes"]:
        if n["type"] == "Flight" and "SL 482" in n["name"]:
            flight = n["id"]
    ent = (await c.get(f"{BASE}/api/memory/entity/{flight}", headers=H)).json() if flight else {"facts": []}
    photo_facts = {f["attribute"]: f["value"] for f in ent["facts"] if f["current"] and any("screenshot" in s["where"] for s in f["sources"])}
    expected = {"seat": "14C", "gate": "B12", "boarding_time": "5:30 AM", "number": "SL 482", "date": "Fri, Oct 30, 2026", "from": "ATL", "to": "ORD"}
    from memory.types import normalize_key_value
    right = {k: v for k, v in expected.items() if k in photo_facts and normalize_key_value(k, photo_facts[k]) == normalize_key_value(k, v)}
    ok = (r.status_code == 200 and flight in res.get("entities", []) and before.get("Flight") == after.get("Flight")
          and before.get("Trip") == after.get("Trip") and res.get("deleted") and not left and len(right) >= 5 and can_read == 401)
    log("boarding-pass screenshot → facts on SL 482 (photo source), image deleted", ok, summary=res.get("summary"), facts=res.get("facts"),
        dropped=res.get("dropped"), photo_facts=photo_facts, accuracy=f"{len(right)}/{len(expected)}", flights=f"{before.get('Flight')}→{after.get('Flight')}",
        trips=f"{before.get('Trip')}→{after.get('Trip')}", deleted=res.get("deleted"), files_left=left, token_can_read=can_read != 401,
        ocr_ms=res.get("ocr_ms"), model_ms=res.get("model_ms"), round_trip_s=took, cost_usd=res.get("cost_usd"))
    shot.unlink(missing_ok=True)
    for d in (await c.get(f"{BASE}/api/paired", headers=H)).json()["devices"]:  # the eval's token goes away with it
        if d["name"] == "eval Shortcut":
            await c.delete(f"{BASE}/api/paired/{d['id']}", headers=H)


# ---- 3. voice ---------------------------------------------------------------------------------------------


def say(text: str) -> bytes:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    aiff, wav = SCRATCH / "say.aiff", SCRATCH / "say.wav"
    subprocess.run(["say", "-v", "Samantha", "-o", str(aiff), text], check=True)
    subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@24000", "-c", "1", str(aiff), str(wav)], check=True)
    with wave.open(str(wav)) as w:
        pcm = w.readframes(w.getnframes())
    return pcm + b"\x00\x00" * (24000 // 2)  # half a second of silence, as a person pauses before letting go


async def voice(c: httpx.AsyncClient, text: str = "What's my gate for my Chicago flight?") -> None:
    pcm = say(text)
    chunk = 3840  # 80 ms
    async with websockets.connect("ws://127.0.0.1:8700/api/voice", additional_headers=H, max_size=None) as ws:
        t_press = time.time()
        await ws.send(json.dumps({"type": "start"}))
        partials, ready_ms = 0, None

        async def reader() -> dict[str, Any]:
            nonlocal partials, ready_ms
            async for m in ws:
                msg = json.loads(m)
                if msg["type"] == "ready":
                    ready_ms = round((time.time() - t_press) * 1000)
                elif msg["type"] == "partial":
                    partials += 1
                elif msg["type"] in ("final", "error"):
                    return msg
            return {"type": "error", "error": "closed"}
        rd = asyncio.create_task(reader())
        for i in range(0, len(pcm), chunk):
            await ws.send(pcm[i:i + chunk])
            await asyncio.sleep(0.08)
        t_release = time.time()
        await ws.send(json.dumps({"type": "stop"}))
        final = await asyncio.wait_for(rd, 30)
        t_text = time.time()
    reply, t_reply = {}, t_text
    if final.get("type") == "final":
        reply = (await c.post(f"{BASE}/api/chat", json={"message": final["text"], "source": "voice"}, headers=H, timeout=60)).json()
        t_reply = time.time()
    words = lambda s: set(s.lower().replace("?", "").replace("'", "").split())  # noqa: E731
    heard = final.get("text", "")
    log("voice → Muse Voice Transcribe → chat", final.get("type") == "final" and len(words(text) & words(heard)) >= len(words(text)) - 1 and bool(reply.get("reply")),
        said=text, heard=heard, partials=partials, connect_ms=final.get("connect_ms"), ready_ms=ready_ms, audio_ms=final.get("audio_ms"),
        release_to_text_ms=round((t_text - t_release) * 1000), chat_ms=round((t_reply - t_text) * 1000),
        release_to_reply_ms=round((t_reply - t_release) * 1000), cost_usd=final.get("cost_usd"), reply=reply.get("reply"), spoken=reply.get("spoken"),
        reply_kind=reply.get("kind"))


# ---- 4. the live view over the tailnet ----------------------------------------------------------------------


async def live() -> None:
    state = httpx.get(f"{BASE}/api/state", headers=H).json()
    public = state.get("public_url", "")
    if not public.startswith("https://"):
        log("live view over the tailnet", False, error="Envoy isn't served on the tailnet (scripts/serve_tailnet.sh on)")
        return
    url = public.replace("https://", "wss://") + "/api/live/envoy-test?fps=10&width=720&quality=60"
    origin = public
    lat, rtts, sizes, offset = [], [], [], 0.0
    async with websockets.connect(url, additional_headers={**H, "Origin": origin}, max_size=None, ssl=ssl.create_default_context()) as ws:
        hello = json.loads(await ws.recv())
        for _ in range(5):
            t = time.time()
            await ws.send(json.dumps({"type": "ping", "t": t * 1000}))
            while True:
                m = await ws.recv()
                if isinstance(m, str) and json.loads(m).get("type") == "pong":
                    now = time.time()
                    rtts.append((now - t) * 1000)
                    offset = json.loads(m)["server"] - (t + now) / 2
                    break
        async def change_screen() -> None:  # open and close the notification shade: new frames to time
            for i in range(8):
                cmd = "expand-notifications" if i % 2 == 0 else "collapse"
                await asyncio.to_thread(subprocess.run, ["adb", "-s", "emulator-5554", "shell", "cmd", "statusbar", cmd], timeout=20)
                await asyncio.sleep(0.8)
        changer = asyncio.create_task(change_screen())
        t0 = time.time()
        while time.time() - t0 < 8:
            try:
                m = await asyncio.wait_for(ws.recv(), 2)
            except asyncio.TimeoutError:
                continue
            if isinstance(m, bytes):
                lat.append((time.time() + offset - struct.unpack(">d", m[:8])[0]) * 1000)
                sizes.append(len(m))
        await changer
    med = lambda xs: round(sorted(xs)[len(xs) // 2]) if xs else None  # noqa: E731
    log("live view over the tailnet (HTTPS + Tailscale, from this Mac)", bool(lat), host=public, device=f"{hello['width']}x{hello['height']}",
        frames=len(lat), frame_ms_p50=med(lat), frame_ms_max=round(max(lat)) if lat else None, rtt_ms_p50=med(rtts), kb_per_frame=med([s / 1024 for s in sizes]))


async def main(parts: list[str]) -> int:
    async with httpx.AsyncClient(timeout=60) as c:
        if "push" in parts:
            await push_and_checkin(c)
        if "photo" in parts:
            await photo(c)
        if "voice" in parts:
            await voice(c)
        if "live" in parts:
            await live()
    passed = all(s["ok"] for s in steps)
    summary = {"passed": passed, "steps_ok": f"{sum(s['ok'] for s in steps)}/{len(steps)}", "duration_s": round(time.time() - T0, 1), "parts": parts}
    OUT.mkdir(parents=True, exist_ok=True)
    name = "gate.json" if parts == ["push", "photo", "voice", "live"] else f"run_{'_'.join(parts)}.json"
    (OUT / name).write_text(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "summary": summary, "steps": steps}, indent=1, default=str))
    print(json.dumps(summary))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:] or ["push", "photo", "voice", "live"])))
