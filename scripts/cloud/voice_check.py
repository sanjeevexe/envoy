"""Voice on the cloud copy, from this Mac over the tailnet: dictation → Muse Voice Transcribe → chat, timed.

  uv run --project backend python scripts/cloud/voice_check.py --base https://envoy-cloud.<tailnet>.ts.net:8443

The check eval/run_phase5.py makes on the Mac (its `voice`), from outside: Phase 5's script makes its speech with
macOS's `say` and `afconvert`, which the VM doesn't have, so the speech is made here and streamed to the cloud copy's
`WS /api/voice` the way the iPhone's app does (80 ms chunks, then "stop"), then the transcript goes to `/api/chat`.
The cloud copy's session token is read over SSH into this process and never printed. A few tenths of a cent.
Results: eval/results/cloud/voice.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import ssl
import subprocess
import tempfile
import time
import wave
from pathlib import Path

import httpx
import websockets

REPO = Path(__file__).resolve().parents[2]
RUN = str(REPO / "scripts" / "cloud" / "run.sh")


def say(text: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        aiff, wav = Path(tmp) / "say.aiff", Path(tmp) / "say.wav"
        subprocess.run(["say", "-v", "Samantha", "-o", str(aiff), text], check=True)
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@24000", "-c", "1", str(aiff), str(wav)], check=True)
        with wave.open(str(wav)) as w:
            pcm = w.readframes(w.getnframes())
    return pcm + b"\x00\x00" * (24000 // 2)  # half a second of silence, as a person pauses before letting go


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--text", default="What's my gate for my Chicago flight?")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    token = subprocess.run([RUN, "bash", "-c", "cat ~/envoy-state/api/session_token"], capture_output=True, text=True, timeout=120).stdout.strip()
    if not token:
        raise SystemExit("no session token from the VM")
    H = {"Authorization": f"Bearer {token}", "X-Envoy": "1", "Origin": base}
    pcm = say(args.text)
    url = base.replace("https://", "wss://").replace("http://", "ws://") + "/api/voice"
    kw = {"ssl": ssl.create_default_context()} if url.startswith("wss://") else {}
    async with websockets.connect(url, additional_headers=H, max_size=None, **kw) as ws:
        t_press = time.time()
        await ws.send(json.dumps({"type": "start"}))
        partials, ready_ms = 0, None

        async def reader() -> dict:
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
        for i in range(0, len(pcm), 3840):  # 80 ms
            await ws.send(pcm[i:i + 3840])
            await asyncio.sleep(0.08)
        t_release = time.time()
        await ws.send(json.dumps({"type": "stop"}))
        final = await asyncio.wait_for(rd, 30)
        t_text = time.time()
    reply, t_reply = {}, t_text
    if final.get("type") == "final":
        async with httpx.AsyncClient(timeout=60) as c:
            reply = (await c.post(f"{base}/api/chat", json={"message": final["text"], "source": "voice"}, headers=H)).json()
        t_reply = time.time()
    out = {"base": base, "said": args.text, "heard": final.get("text"), "ok": final.get("type") == "final" and bool(reply.get("reply")),
           "error": final.get("error"), "partials": partials, "connect_ms": final.get("connect_ms"), "ready_ms": ready_ms,
           "audio_ms": final.get("audio_ms"), "release_to_text_ms": round((t_text - t_release) * 1000),
           "chat_ms": round((t_reply - t_text) * 1000), "release_to_reply_ms": round((t_reply - t_release) * 1000),
           "cost_usd": final.get("cost_usd"), "reply": reply.get("reply"), "reply_kind": reply.get("kind")}
    print(json.dumps(out, indent=1))
    (REPO / "eval" / "results" / "cloud" / "voice.json").write_text(json.dumps(out, indent=1))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
