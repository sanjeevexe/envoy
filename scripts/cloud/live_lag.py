"""The cloud copy's live view, measured from this Mac: frame lag, and a takeover's input → ack and input → new frame.

  uv run --project backend python scripts/cloud/live_lag.py --base http://127.0.0.1:8745 --name forward
  uv run --project backend python scripts/cloud/live_lag.py --base https://envoy-cloud.<tailnet>.ts.net:8443 --name tailnet

The same WebSocket the web app and the iPhone use (`WS /api/live/{avd}`), measured as eval/run_phase6.py `live` does
(capture → received, with the clock offset from ping/pong), but every screen change is made by the VM's own adb over
SSH: never this Mac's adb, whose emulator-5554 is the Mac's envoy-test. Then a takeover: a swipe that pulls the notification
shade down alternates with Back (it closes), nothing typed; each input's ack and the first frame captured
after it are timed; then hand back. The cloud copy's
session token is read over SSH into this process and never printed. Results: eval/results/cloud/live-<name>.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import ssl
import statistics
import struct
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import websockets

REPO = Path(__file__).resolve().parents[2]
RUN = str(REPO / "scripts" / "cloud" / "run.sh")
SHADE = {"type": "swipe", "x1": 0.5, "y1": 0.005, "x2": 0.5, "y2": 0.6, "ms": 150}  # pulls the notification shade down


def vm(cmd: str, timeout: float = 120) -> str:
    return subprocess.run([RUN, "bash", "-c", cmd], capture_output=True, text=True, timeout=timeout).stdout


def med(xs: list[float]) -> float | None:
    return round(statistics.median(xs), 1) if xs else None


def post(base: str, path: str, token: str) -> dict:
    req = urllib.request.Request(base + path, data=b"{}", method="POST", headers={
        "Authorization": f"Bearer {token}", "X-Envoy": "1", "Content-Type": "application/json", "Origin": base})
    with urllib.request.urlopen(req, timeout=20, context=ssl.create_default_context()) as r:
        return json.loads(r.read() or b"{}")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8745")
    ap.add_argument("--avd", default="envoy-test")
    ap.add_argument("--serial", default="emulator-5554", help="the device's serial on the VM")
    ap.add_argument("--taps", type=int, default=10)
    ap.add_argument("--name", default="forward")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    token = vm("cat ~/envoy-state/api/session_token").strip()
    if not token:
        raise SystemExit("no session token from the VM")
    vm(f"adb -s {args.serial} shell am start -W -n com.skylark.air/.MainActivity >/dev/null")

    url = base.replace("https://", "wss://").replace("http://", "ws://") + f"/api/live/{args.avd}?fps=10&width=720&quality=60"
    kw = {"ssl": ssl.create_default_context()} if url.startswith("wss://") else {}
    out: dict = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "base": base, "avd": args.avd}
    async with websockets.connect(url, additional_headers={"Authorization": f"Bearer {token}", "Origin": base}, max_size=None, **kw) as ws:
        out["hello"] = json.loads(await ws.recv())
        rtts, offset = [], 0.0
        for _ in range(5):
            t = time.time()
            await ws.send(json.dumps({"type": "ping", "t": t * 1000}))
            while True:
                m = await ws.recv()
                if isinstance(m, str) and json.loads(m).get("type") == "pong":
                    back = time.time()
                    rtts.append((back - t) * 1000)
                    offset = json.loads(m)["server"] - (t + back) / 2
                    break

        # 1. Frames while the VM's adb opens and closes the notification shade (one SSH session for all ten changes).
        changer = asyncio.create_task(asyncio.to_thread(vm, f"for i in 1 2 3 4 5; do adb -s {args.serial} shell cmd statusbar "
                                                            "expand-notifications; sleep 0.8; adb -s {args.serial} shell cmd statusbar collapse; sleep 0.8; done"
                                                            .replace("{args.serial}", args.serial)))
        lat, sizes = [], []
        t0 = time.time()
        while not changer.done() or time.time() - t0 < 4:
            try:
                m = await asyncio.wait_for(ws.recv(), 1)
            except asyncio.TimeoutError:
                continue
            if isinstance(m, bytes):
                lat.append((time.time() + offset - struct.unpack(">d", m[:8])[0]) * 1000)
                sizes.append(len(m))
            elif json.loads(m).get("type") == "stats":
                out["server_stats"] = json.loads(m)  # the VM's own capture and encode time per frame
        await changer
        out["frames"] = {"n": len(lat), "capture_to_received_ms_p50": med(lat), "max_ms": round(max(lat)) if lat else None,
                         "rtt_ms_p50": med(rtts), "kb_per_frame": round(statistics.median(sizes) / 1024, 1) if sizes else None}

        # 2. A takeover: input → ack, and input → the first frame captured after it (what the person sees).
        post(base, f"/api/devices/{args.avd}/takeover", token)
        acks, seen = [], []
        try:
            for i in range(args.taps):
                while True:  # drain anything queued, so the next frame is the tap's
                    try:
                        await asyncio.wait_for(ws.recv(), 0.4)
                    except asyncio.TimeoutError:
                        break
                msg = SHADE if i % 2 == 0 else {"type": "key", "key": "Back"}
                sent = time.time()
                await ws.send(json.dumps({**msg, "id": i}))
                got_ack = got_frame = None
                while time.time() - sent < 5 and (got_ack is None or got_frame is None):
                    try:
                        m = await asyncio.wait_for(ws.recv(), 1)
                    except asyncio.TimeoutError:
                        continue
                    now = time.time()
                    if isinstance(m, str):
                        j = json.loads(m)
                        if j.get("type") == "ack" and j.get("id") == i:
                            got_ack = (now - sent) * 1000
                    elif struct.unpack(">d", m[:8])[0] - offset > sent:
                        got_frame = (now - sent) * 1000
                if got_ack is not None:
                    acks.append(got_ack)
                if got_frame is not None:
                    seen.append(got_frame)
        finally:
            post(base, f"/api/devices/{args.avd}/handback", token)
        out["takeover"] = {"inputs": args.taps, "ack_ms_p50": med(acks), "ack_ms_max": round(max(acks)) if acks else None,
                           "input_to_new_frame_ms_p50": med(seen), "input_to_new_frame_ms_max": round(max(seen)) if seen else None,
                           "frames_seen": len(seen)}
    print(json.dumps(out, indent=1))
    path = REPO / "eval" / "results" / "cloud" / f"live-{args.name}.json"
    path.write_text(json.dumps(out, indent=1))
    print("saved", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
