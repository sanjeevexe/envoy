"""Live view of a phone, and the user's input during a takeover (design doc, Live view and sign-in).

On emulators the frames come from the emulator's own gRPC screenshot, scaled by the emulator and sent as JPEG over a
WebSocket. Unlike scrcpy video and `adb screencap`, this shows secure sign-in screens (Phase 0, A4), which is what lets
the user sign in from the web app. On a real phone (Phase 6) the frames and input go through the phone's scrcpy session
(`devices/scrcpy.py`), with the same messages; secure screens are black there, so the server says when the window is
secure (`{"type": "secure", "secure": true}`) and you sign in on the phone itself.

Protocol (`WS /api/live/{avd}`):
- server → client: one JSON `hello` (device size), then binary frames: 8 bytes big-endian float64 (capture time,
  seconds since the epoch) followed by a JPEG. Identical frames are skipped. A JSON `control` message whenever who
  controls the phone changes.
- client → server (JSON), only while the user is in control: `tap` {x, y}, `long_press` {x, y}, `swipe` {x1, y1, x2,
  y2, ms}, `text` {text}, `key` {key: Back | Home | Enter | Backspace | Tab}. Coordinates are fractions of the screen
  (0–1). Input is passed straight to the phone: never logged, never stored, never shown to a model. An input with an
  `id` is acknowledged with `{"type": "ack", id, ms}` once the phone has it.
- The one exception is teach mode (api/teach.py), which you start yourself with a goal and which `control` shows
  (`teach.recording`): then each input is recorded with the screens around it, to become a routine. It records nothing
  on sign-in and secure screens or in password fields, and nothing at all once you finish or cancel.
- `ping` {t} at any time → `pong` {t, server}: the client's clock offset and round trip, so it can measure capture →
  screen latency on another device (the iPhone over the tailnet) without trusting the two clocks to agree.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import struct
import time
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

KEYS = {"Back": "GoBack", "Home": "GoHome", "Enter": "Enter", "Backspace": "Backspace", "Tab": "Tab", "Recents": "AppSwitch"}


async def live_view(ws: WebSocket, avd: str, pool: Any, fps: float = 10, width: int = 540, quality: int = 70) -> None:
    await ws.accept()
    try:
        device = await pool.device(avd)
    except Exception as e:  # noqa: BLE001
        await ws.send_text(json.dumps({"type": "error", "error": str(e)}))
        await ws.close()
        return
    lease = pool.leases[avd]
    caps = device.capabilities
    stream = await asyncio.to_thread(lambda: device.stream)  # the emulator's gRPC, or the phone's scrcpy session (started on first use)
    phone = pool.is_phone(avd)
    await ws.send_text(json.dumps({"type": "hello", "avd": avd, "width": caps.width, "height": caps.height, "control": lease.state(),
                                   "kind": "phone" if phone else "emulator"}))
    stop = asyncio.Event()
    stats = {"frames": 0, "skipped": 0, "capture_ms": 0.0, "encode_ms": 0.0, "bytes": 0}

    def grab() -> tuple[float, bytes | None, str]:
        ts, t0 = time.time(), time.perf_counter()
        img = stream.frame(width, timeout=3)
        t1 = time.perf_counter()
        digest = hashlib.blake2b(img.tobytes(), digest_size=8).hexdigest()
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        stats["capture_ms"] += (t1 - t0) * 1000
        stats["encode_ms"] += (time.perf_counter() - t1) * 1000
        return ts, buf.getvalue(), digest

    async def send_frames() -> None:
        last, last_control, secure, checked = "", None, None, 0.0
        while not stop.is_set():
            t0 = time.perf_counter()
            if phone and time.time() - checked > 1.0:  # a real phone shows secure windows black: say so instead
                checked = time.time()
                try:
                    now_secure = (await asyncio.to_thread(device._foreground))[2]
                except Exception:  # noqa: BLE001
                    now_secure = secure
                if now_secure != secure:
                    secure = now_secure
                    await ws.send_text(json.dumps({"type": "secure", "secure": bool(secure)}))
                if secure:
                    await asyncio.sleep(0.5)
                    continue
            try:
                ts, jpeg, digest = await asyncio.to_thread(grab)
            except Exception as e:  # noqa: BLE001 - a missed frame is fine; keep streaming
                await ws.send_text(json.dumps({"type": "error", "error": f"frame: {type(e).__name__}"}))
                await asyncio.sleep(1)
                continue
            control = (lease.user_control, lease.task_id, lease.reason, repr(lease.teach))
            if control != last_control:
                last_control = control
                await ws.send_text(json.dumps({"type": "control", "control": lease.state()}))
            if digest != last and jpeg:
                await ws.send_bytes(struct.pack(">d", ts) + jpeg)
                last = digest
                stats["frames"] += 1
                stats["bytes"] += len(jpeg)
            else:
                stats["skipped"] += 1
            if (stats["frames"] + stats["skipped"]) % 50 == 0:
                n = max(1, stats["frames"] + stats["skipped"])
                await ws.send_text(json.dumps({"type": "stats", "capture_ms": round(stats["capture_ms"] / n, 1),
                                               "encode_ms": round(stats["encode_ms"] / n, 1), "frames": stats["frames"],
                                               "skipped": stats["skipped"], "avg_kb": round(stats["bytes"] / max(1, stats["frames"]) / 1024, 1)}))
            await asyncio.sleep(max(0.0, 1 / fps - (time.perf_counter() - t0)))

    async def receive_input() -> None:
        while not stop.is_set():
            msg = json.loads(await ws.receive_text())
            if msg.get("type") == "ping":
                await ws.send_text(json.dumps({"type": "pong", "t": msg.get("t"), "server": time.time()}))
                continue
            if not lease.user_control:
                await ws.send_text(json.dumps({"type": "error", "error": "take over first: the agent has the phone"}))
                continue
            w, h = caps.width, caps.height
            px = lambda fx, fy: (max(0, min(w - 1, round(float(fx) * w))), max(0, min(h - 1, round(float(fy) * h))))  # noqa: E731
            kind = msg.get("type")
            t0 = time.perf_counter()

            async def forward() -> None:
                if kind == "tap":
                    await asyncio.to_thread(stream.tap, *px(msg["x"], msg["y"]))
                elif kind == "long_press":
                    x, y = px(msg["x"], msg["y"])
                    await asyncio.to_thread(stream.swipe, x, y, x, y, 0.7)
                elif kind == "swipe":
                    (x1, y1), (x2, y2) = px(msg["x1"], msg["y1"]), px(msg["x2"], msg["y2"])
                    await asyncio.to_thread(stream.swipe, x1, y1, x2, y2, float(msg.get("ms", 300)) / 1000)
                elif kind == "text" and isinstance(msg.get("text"), str):
                    await asyncio.to_thread(stream.text, msg["text"][:500])
                elif kind == "key" and msg.get("key") in KEYS:
                    await asyncio.to_thread(stream.key, KEYS[msg["key"]])

            recorder = pool.recorders.get(avd)
            if recorder is None:
                await forward()
            else:  # teach mode, which you started: the screen before, the input, then the screen after (api/teach.py)
                async with recorder.lock:
                    await recorder.before(msg, w, h)
                    await forward()
                    await recorder.after(msg)
            if msg.get("id") is not None:
                await ws.send_text(json.dumps({"type": "ack", "id": msg["id"], "ms": round((time.perf_counter() - t0) * 1000, 1)}))

    sender = asyncio.create_task(send_frames())
    try:
        await receive_input()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        stop.set()
        sender.cancel()
