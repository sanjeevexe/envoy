"""Voice: push to talk, relayed to Muse Voice Transcribe (design doc, Interfaces › Voice).

The browser (web app or the iPhone's Home Screen app) streams microphone audio here; this relay holds the Meta API key
and forwards the audio to `wss://api.meta.ai/v1/asr/realtime`, so the key never reaches a browser. One press of the
button is one Transcribe session in PUSH_TO_TALK mode (dev.meta.ai/docs/speech-to-text, read Oct 27, 2026):
handshake JSON first (`authorization.accessToken`), acknowledged by `{"sessionId"}`; then binary 16-bit little-endian
mono PCM at 24 kHz, at about real time; `{"type": "endStream"}` ends the turn; a `transcript` with `final: true` follows,
then a normal close.

Protocol (`WS /api/voice`, your session only):
- client → server: `{"type": "start"}`, then binary PCM frames (24 kHz, 16-bit LE mono), then `{"type": "stop"}` when
  the button is released (or `{"type": "cancel"}`).
- server → client: `{"type": "ready"}` once Transcribe is listening (audio sent earlier is buffered, not lost),
  `{"type": "partial", "text"}` while you talk, `{"type": "final", "text", "audio_ms", "connect_ms", "finalize_ms",
  "cost_usd"}` after release, or `{"type": "error", "error"}`.
The transcript then goes to chat like typed text, with source `voice` (your own words for the approval rules).
Audio is never stored; the cost of each turn ($0.18 per audio hour, billed per whole second) goes to the cost log.

Transcribe closes a stream that falls behind real time ("Ingress audio slower than real-time", found on the iPhone when
its microphone delivered nothing), and Meta's docs say to keep sending silence on a live source. So the relay keeps the
stream at real time: whenever the browser's audio falls more than 300 ms behind (a stalled microphone, a slow network),
it fills the gap with silence.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import time
from datetime import datetime, timezone
from typing import Any

import websockets
from fastapi import WebSocket, WebSocketDisconnect

from models.adapter import VOICE_PRICE_PER_HOUR, CostCapExceeded, CostMeter

ASR_URL = os.environ.get("META_ASR_URL", "wss://api.meta.ai/v1/asr/realtime")
MODEL = "muse-voice-transcribe-1.0"
RATE = 24000
BYTES_PER_S = RATE * 2
MAX_TURN_S = 60
KEYWORDS = ["Envoy", "SkyLark", "check me in", "boarding pass", "gate", "Muse"]

STOP, CANCEL = object(), object()


def turn_cost(audio_bytes: int) -> float:
    return math.floor(audio_bytes / BYTES_PER_S) / 3600 * VOICE_PRICE_PER_HOUR


async def voice_session(ws: WebSocket, *, api_key: str, meter: CostMeter, url: str | None = None) -> dict[str, Any] | None:
    await ws.accept()
    try:
        first = json.loads(await ws.receive_text())
    except (WebSocketDisconnect, ValueError, RuntimeError):
        return None
    if first.get("type") != "start":
        await ws.close(code=4400)
        return None
    try:
        meter.check()
        if not api_key:
            raise RuntimeError("META_API_KEY is not set")
    except (CostCapExceeded, RuntimeError) as e:
        await ws.send_json({"type": "error", "error": str(e), "fallback": True})
        await ws.close()
        return None

    queue: asyncio.Queue = asyncio.Queue()
    stats: dict[str, Any] = {"audio_bytes": 0, "padded_bytes": 0, "connect_ms": None, "finalize_ms": None, "final": None, "error": None}
    t0 = time.perf_counter()
    stopped_at: list[float] = []

    async def from_client() -> None:
        try:
            while True:
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    await queue.put(CANCEL)
                    return
                if msg.get("bytes"):
                    await queue.put(msg["bytes"])
                elif msg.get("text"):
                    kind = json.loads(msg["text"]).get("type")
                    if kind in ("stop", "cancel"):
                        if kind == "stop":
                            stopped_at.append(time.perf_counter())
                        await queue.put(STOP if kind == "stop" else CANCEL)
                        return
        except (WebSocketDisconnect, RuntimeError):
            await queue.put(CANCEL)

    async def relay() -> None:
        handshake = {"authorization": {"accessToken": f"Bearer {api_key}"}, "audioEncoding": "PCM_24KHZ", "model": MODEL,
                     "mode": "PUSH_TO_TALK", "partialMode": "CUMULATIVE", "emitAudioProgress": False,
                     "languageBias": ["English"], "keywords": KEYWORDS}
        async with websockets.connect(url or ASR_URL, open_timeout=10, max_size=None) as up:
            await up.send(json.dumps(handshake))
            ack = json.loads(await asyncio.wait_for(up.recv(), 10))
            if ack.get("type") == "error" or "sessionId" not in ack:
                raise RuntimeError(ack.get("message") or f"Transcribe refused the session: {ack}")
            stats["connect_ms"] = round((time.perf_counter() - t0) * 1000)
            await ws.send_json({"type": "ready"})

            async def from_meta() -> None:
                async for raw in up:
                    if isinstance(raw, bytes):
                        continue
                    ev = json.loads(raw)
                    if ev.get("type") == "transcript":
                        if ev.get("final"):
                            stats["final"] = ev.get("transcript", "")
                        else:
                            await ws.send_json({"type": "partial", "text": ev.get("transcript", "")})
                    elif ev.get("type") == "speechComplete" and stats["final"] is None:
                        stats["final"] = ev.get("transcript", "")
                    elif ev.get("type") == "error":
                        stats["error"] = ev.get("message") or "Transcribe error"

            async def pace() -> None:  # keep the stream at real time with silence when the browser's audio stalls
                t_ready = time.perf_counter()
                while True:
                    await asyncio.sleep(0.1)
                    behind = (time.perf_counter() - t_ready) * BYTES_PER_S - stats["audio_bytes"]
                    if behind > 0.3 * BYTES_PER_S:
                        pad = int(behind - 0.1 * BYTES_PER_S) // 2 * 2
                        stats["audio_bytes"] += pad
                        stats["padded_bytes"] += pad
                        await up.send(b"\x00" * pad)

            reader = asyncio.create_task(from_meta())
            pacer = asyncio.create_task(pace())
            try:
                while True:
                    getter = asyncio.create_task(queue.get())
                    await asyncio.wait({getter, reader}, return_when=asyncio.FIRST_COMPLETED)
                    if not getter.done():  # Transcribe closed the stream early (an error, a limit)
                        getter.cancel()
                        stats["error"] = stats["error"] or "Transcribe closed the stream"
                        return
                    item = getter.result()
                    if item is CANCEL:
                        return
                    if item is STOP:
                        pacer.cancel()
                        await up.send(json.dumps({"type": "endStream"}))
                        break
                    stats["audio_bytes"] += len(item)
                    await up.send(item)
                    if stats["audio_bytes"] >= MAX_TURN_S * BYTES_PER_S:
                        pacer.cancel()
                        stopped_at.append(time.perf_counter())
                        await up.send(json.dumps({"type": "endStream"}))
                        await ws.send_json({"type": "notice", "text": f"stopped listening after {MAX_TURN_S} s"})
                        break
                await asyncio.wait_for(reader, 15)  # the final transcript, then Meta closes the stream
            finally:
                pacer.cancel()
                reader.cancel()

    listener = asyncio.create_task(from_client())
    try:
        await relay()
    except Exception as e:  # noqa: BLE001 - tell the client, which can fall back to the browser's own recognition
        stats["error"] = stats["error"] or f"{type(e).__name__}: {e}"[:200]
    finally:
        listener.cancel()
    if stopped_at and stats["final"] is not None:
        stats["finalize_ms"] = round((time.perf_counter() - stopped_at[0]) * 1000)
    cost = turn_cost(stats["audio_bytes"])
    meter.record({"time": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "job": "voice", "model": MODEL, "data_scope": "real",
                  "task_id": "voice", "ok": stats["final"] is not None, "error": stats["error"], "audio_s": round(stats["audio_bytes"] / BYTES_PER_S, 2),
                  "latency_ms": stats["finalize_ms"], "connect_ms": stats["connect_ms"], "padded_s": round(stats["padded_bytes"] / BYTES_PER_S, 2), "cost_usd": round(cost, 6), "cost_at_standard_usd": round(cost, 6)})
    try:
        if stats["final"] is not None:
            await ws.send_json({"type": "final", "text": stats["final"].strip(), "audio_ms": round(stats["audio_bytes"] / BYTES_PER_S * 1000),
                                "silence_ms": round(stats["padded_bytes"] / BYTES_PER_S * 1000),
                                "connect_ms": stats["connect_ms"], "finalize_ms": stats["finalize_ms"], "cost_usd": round(cost, 6)})
        elif stats["error"]:
            await ws.send_json({"type": "error", "error": stats["error"], "fallback": True})
        await ws.close()
    except (WebSocketDisconnect, RuntimeError):
        pass
    return stats
