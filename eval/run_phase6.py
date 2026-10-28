"""Phase 6: routines on other phones, screens with no accessibility tree, the scrcpy stream, and the gate.

  uv run --project backend python eval/run_phase6.py portability [--device envoy-small] [--k 3]
      the 7 SkyLark routines compiled on envoy-test, unchanged, on another phone (a smaller emulator, or the real
      phone: --device phone), on bookings they have never seen; envoy-test runs the same cells as the control
  uv run --project backend python eval/run_phase6.py vision        grounding vs SAM 3.1 vs the step model on no-tree targets
  uv run --project backend python eval/run_phase6.py stream        the scrcpy path (frames, input latency) on a phone
  uv run --project backend python eval/run_phase6.py gate          the gate on the real phone, with the scripted person

Success is a code check on SkyLark's real state (Phase 2's checks), never a model's judgment. SkyLark is test data,
so model calls use the Contributor tier. Results: eval/results/phase6/.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "eval"))
sys.path.insert(0, str(REPO / "backend"))

import run_routines as rr  # noqa: E402
from devices.emulator import EmulatorDevice  # noqa: E402
from devices.phone import PhoneDevice, discover  # noqa: E402
from models.adapter import ModelAdapter  # noqa: E402
from policy.approvals import ScriptedApprover  # noqa: E402
from routines.store import RoutineStore  # noqa: E402
from skylark_routines import FAMILIES, chicago_booking, generate  # noqa: E402
from testapps.skylark import SkyLark  # noqa: E402

OUT = REPO / "eval" / "results" / "phase6"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save(name: str, payload: Any) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.json"
    path.write_text(json.dumps(payload, indent=1, default=str, ensure_ascii=False))
    return path


def open_device(name: str) -> Any:
    """An emulator by AVD name, or "phone" (the first connected Android phone; ENVOY_TEST_PHONE lets an emulator stand in)."""
    if name == "phone" or name.startswith("phone-"):
        phones = [p for p in discover() if p["state"] == "device" and (name == "phone" or p["id"] == name)]
        if not phones:
            raise SystemExit("no Android phone connected (adb devices)")
        return PhoneDevice(phones[0]["serial"], phones[0]["id"]).connect()
    return EmulatorDevice(name).connect()


class Env(rr.Env):
    """Phase 2's eval environment on any device."""

    def __init__(self, device: Any, contributor: bool = True) -> None:  # noqa: D107 - replaces rr.Env.__init__
        self.device = device
        self.app = SkyLark(device.serial)
        if not self.app.installed():
            self.app.install()
        self.adapter = ModelAdapter()
        self.contributor = contributor
        self.approver = ScriptedApprover(approve=True)  # our own test app: the scripted person approves, and it is logged
        self.snapshot_failures = 0


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    ok = [r for r in rows if r["passed"]]
    return {"runs": n, "passed": len(ok), "success": round(len(ok) / n, 3) if n else None,
            "no_model_calls": sum(1 for r in rows if r["model_calls"] == 0),
            "model_calls": sum(r["model_calls"] for r in rows), "cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
            "median_s": round(statistics.median(r["duration_s"] for r in rows), 1) if rows else None,
            "repairs": sum(1 for r in rows if (r.get("rung") or 0) >= 4), "agent_fallbacks": sum(1 for r in rows if r.get("agent"))}


async def cmd_portability(args: argparse.Namespace) -> None:
    store = RoutineStore(rr.LIB)
    devices = [args.device] if args.no_control else ["envoy-test", args.device]
    out: dict[str, Any] = {"time": now(), "k": args.k, "devices": {}}
    for name in devices:
        dev = open_device(name)
        env = Env(dev)
        rows = []
        caps = dev.capabilities
        print(f"== {name}: {caps.width}x{caps.height} @ {caps.density} dpi ({dev.model}, Android {dev.android})", flush=True)
        for k in range(args.k):
            extra = generate(args.seed + k, 4)
            for fam in [f for f in FAMILIES if not args.families or f.id in args.families.split(",")]:
                src = rr.src_of(fam)
                routine = rr.routine_for(store, fam)
                target = extra[k % len(extra)] if k % 5 != 4 else chicago_booking()
                row, _ = await rr.run_routine(env, routine, fam, src, target, extra, 0, kind=f"port-{name}")
                rows.append({**row, "device": name})
        out["devices"][name] = {"size": [caps.width, caps.height], "density": caps.density, "model": dev.model,
                                "android": dev.android, "real_phone": caps.real_phone, "summary": summarize(rows), "rows": rows}
        print(f"   {name}: {json.dumps(summarize(rows))}", flush=True)
        if isinstance(dev, PhoneDevice):
            dev.close()
    print("saved", save(args.name or f"portability-{args.device}", out))


# ---- vision: grounding vs SAM 3.1 vs the step model on targets the tree doesn't give ----------------------------

def seat_rects(serial: str) -> dict[str, list[int]]:
    """SkyLark variant 6 publishes the drawn seats' rectangles (screen pixels) in its state hook."""
    import subprocess
    out = subprocess.run(["adb", "-s", serial, "shell", "content", "query", "--uri", "content://com.skylark.air.debug/state"],
                         capture_output=True, text=True, timeout=15).stdout
    row = next((line for line in out.splitlines() if "key=seat_rects," in line), "")
    return json.loads(row.split("value=", 1)[1]) if row else {}


async def skylark_canvas_targets(name: str, n: int, offset: int = 0) -> list[dict[str, Any]]:
    """Seats on SkyLark's canvas seat map (variant 6), with their exact drawn boxes."""
    dev = open_device(name)
    app = SkyLark(dev.serial)
    from skylark_routines import fixtures as sk_fixtures
    app.prepare(fixtures=sk_fixtures([]), variant=6)
    from devices.types import Action
    for prefix in ("Next trip", "Change seat"):
        for _ in range(20):
            s = await dev.wait_until_settled()
            el = next((e for e in s.numbered if e.label.startswith(prefix)), None)
            if el is not None:
                await dev.act(Action(kind="tap", element=el.number))
                break
            await asyncio.sleep(0.3)
    await dev.wait_until_settled()
    await asyncio.sleep(0.8)
    png = await dev.screenshot()
    rects = seat_rects(dev.serial)
    seats = sorted(rects)
    step = max(1, len(seats) // n)
    picked = seats[offset % step::step][:n]
    size = (dev.capabilities.width, dev.capabilities.height)
    return [{"source": f"skylark-canvas@{name}", "png": png, "size": size, "description": f"seat {seat}", "truth": rects[seat],
             "scope": "test_app", "phrases": ("square button",)} for seat in picked]


def real_app_targets(per_screen: int = 2, seed: int = 6) -> list[dict[str, Any]]:
    """Screens saved from real-app runs (screenshot + its tree, same moment): the tree gives the truth, the methods see
    only the picture."""
    import gzip
    import random
    rng = random.Random(seed)
    out = []
    for png_path in sorted((REPO / "data" / "runs").glob("*/screens/*_before.png")):
        tree_path = png_path.with_name(png_path.name.replace(".png", ".json.gz"))
        if not tree_path.exists():
            continue
        t = json.loads(gzip.open(tree_path).read())
        if t.get("package") == "com.skylark.air" or t.get("secure"):
            continue
        w, h = t["width"], t["height"]
        els = [e for e in t["elements"] if e.get("number") and (e.get("clickable") or e.get("checkable")) and e.get("label")
               and len(e["label"]) <= 30 and not e.get("status_bar")]
        labels = [e["label"] for e in els]
        els = [e for e in els if labels.count(e["label"]) == 1]
        els = [e for e in els if 0.0008 * w * h <= (e["bounds"][2] - e["bounds"][0]) * (e["bounds"][3] - e["bounds"][1]) <= 0.12 * w * h]
        for e in rng.sample(els, min(per_screen, len(els))):
            kind = (e.get("kind") or "item").lower()
            out.append({"source": f"{t['package']}:{png_path.parent.parent.name}/{png_path.name}", "png": png_path.read_bytes(), "size": (w, h),
                        "description": f'the "{e["label"]}" {kind}', "truth": e["bounds"], "scope": "real", "phrases": ("icon", "square button")})
    return out


def step_model_point(adapter: ModelAdapter, t: dict[str, Any], contributor: bool) -> dict[str, Any]:
    """The Phase 1 behavior: the step model reads coordinates off its own 540 px screenshot (no element list)."""
    from agent.loop import SCREENSHOT_WIDTH
    from agent.vision import _downscale
    from models.adapter import image_part
    from models.prompts import STEP_INSTRUCTIONS, step_input
    t0 = time.perf_counter()
    _, small = _downscale(t["png"], SCREENSHOT_WIDTH)
    goal = f"Tap {t['description']}."
    screen = "SCREEN (drawn by the app; no usable elements are listed)"
    res = adapter.call("step", [{"type": "input_text", "text": step_input(goal, screen + "\n")}, image_part(small)], instructions=STEP_INSTRUCTIONS,
                       data_scope=t["scope"], contributor=contributor, task_id="p6-vision-step")
    a = res.parsed.action if res.parsed else None
    point = None
    if a is not None and getattr(a, "type", "") == "tap_point":
        w, h = t["size"]
        point = (round(min(1000, max(0, a.x)) * w / 1000), round(min(1000, max(0, a.y)) * h / 1000))
    return {"point": point, "ms": (time.perf_counter() - t0) * 1000, "cost": res.cost_at_standard_usd, "calls": 1,
            "detail": "" if point else f"answered {getattr(a, 'type', None)}"}


def run_target(adapter: ModelAdapter, t: dict[str, Any], methods: list[str]) -> dict[str, Any]:
    from agent.vision import Vision
    contributor = t["scope"] == "test_app"
    vis = Vision(adapter, data_scope=t["scope"], contributor=contributor, task_id="p6-vision")
    x1, y1, x2, y2 = t["truth"]
    row: dict[str, Any] = {"source": t["source"], "description": t["description"], "truth": list(t["truth"]), "size": list(t["size"])}
    for m in methods:
        try:
            if m == "step":
                r = step_model_point(adapter, t, contributor)
            else:
                loc = vis.locate(m, t["png"], t["description"], t["size"], t["phrases"])
                r = {"point": loc.point, "ms": loc.ms, "cost": loc.cost_at_standard_usd, "calls": loc.calls, "detail": loc.detail,
                     "candidates": loc.candidates}
        except Exception as e:  # noqa: BLE001 - one failed call is a miss, recorded
            r = {"point": None, "ms": 0, "cost": 0, "calls": 1, "detail": f"{type(e).__name__}: {e}"[:200]}
        p = r["point"]
        r["hit"] = p is not None and x1 <= p[0] <= x2 and y1 <= p[1] <= y2
        r["error_px"] = round(((p[0] - (x1 + x2) / 2) ** 2 + (p[1] - (y1 + y2) / 2) ** 2) ** 0.5) if p else None
        row[m] = r
    return row


async def cmd_vision(args: argparse.Namespace) -> None:
    from concurrent.futures import ThreadPoolExecutor
    targets: list[dict[str, Any]] = []
    for name in args.devices.split(","):
        targets += await skylark_canvas_targets(name, args.seats, args.offset)
    targets += real_app_targets(args.per_screen, args.seed)
    methods = args.methods.split(",")
    print(f"{len(targets)} targets × {methods}", flush=True)
    adapter = ModelAdapter()
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(lambda t: run_target(adapter, t, methods), targets))
    summary: dict[str, Any] = {}
    for group in ("skylark-canvas", "real", "all"):
        sel = [r for r in rows if group == "all" or r["source"].startswith(group) or (group == "real" and not r["source"].startswith("skylark"))]
        summary[group] = {m: {"targets": len(sel), "hits": sum(1 for r in sel if r[m]["hit"]),
                              "accuracy": round(sum(1 for r in sel if r[m]["hit"]) / len(sel), 3) if sel else None,
                              "median_ms": round(statistics.median(r[m]["ms"] for r in sel)) if sel else None,
                              "median_error_px": statistics.median([r[m]["error_px"] for r in sel if r[m]["error_px"] is not None] or [0]),
                              "cost_per_target": round(sum(r[m]["cost"] for r in sel) / len(sel), 5) if sel else None} for m in methods}
    for r in rows:
        print(f"{r['source'][:44]:44s} {r['description'][:28]:28s} " + " ".join(f"{m}={'✓' if r[m]['hit'] else '✗'}" for m in methods), flush=True)
    print(json.dumps(summary, indent=1))
    print("saved", save(args.name or "vision", {"time": now(), "methods": methods, "summary": summary, "rows": rows}))


# ---- a routine step on a drawn screen: learned on envoy-test's canvas seat map, replayed on both sizes ----------------

async def cmd_canvas(args: argparse.Namespace) -> None:
    from dataclasses import replace

    from agent.trace import RUNS
    from routines.compiler import compile_trace
    from routines.model import dump_yaml
    from skylark_routines import BY_ID, _free_seats, compile_booking
    from skylark_routines import fixtures as sk_fixtures
    fam = BY_ID["change_seat"]
    extra = rr.compile_extra()
    near = [x for x in _free_seats(sk_fixtures(extra), set()) if int(x[:-1]) <= 13]  # on screen on both phones
    src = replace(compile_booking(), new_seat=near[0])
    env = Env(open_device("envoy-test"))
    out: dict[str, Any] = {"time": now(), "seats": near}
    task_id = args.task or "p6-canvas-src"
    if not args.task:
        before = await env.reset(extra, 6)
        res = await env.agent().run(fam.goal(src), task_id=task_id, memory=fam.memory(src))
        ok = fam.check(env.app.state(), before, src, {}, res.result) and res.status == "done"
        print(f"{'PASS' if ok else 'FAIL'} agent on the canvas map: {res.status} {res.steps} steps {res.model_calls} calls "
              f"${res.cost_at_standard_usd:.4f} {res.duration_s}s {res.result[:80]!r}", flush=True)
        out["agent"] = {"passed": ok, "status": res.status, "steps": res.steps, "model_calls": res.model_calls,
                        "cost_usd": res.cost_at_standard_usd, "duration_s": res.duration_s, "task_id": task_id}
        if not ok:
            save("canvas", out)
            return
    routine, report = await compile_trace(RUNS / task_id, adapter=env.adapter, memory=fam.memory(src))
    (OUT / "canvas_routine.yaml").write_text(dump_yaml(routine))
    visual = [st.id for st in routine.steps if st.action.target is not None and st.action.target.visual]
    print(f"compiled {routine.routine}: {len(routine.steps)} steps, visual steps {visual}, inputs {list(routine.inputs)}, "
          f"${report.cost_at_standard_usd:.3f}", flush=True)
    out["compile"] = {"routine": routine.routine, "steps": len(routine.steps), "visual_steps": visual, "inputs": list(routine.inputs),
                      "cost_usd": report.cost_at_standard_usd, "warnings": report.warnings}
    rows = []
    for name in ("envoy-test", "envoy-small"):
        env2 = env if name == "envoy-test" else Env(open_device(name))
        for seat in near[1:1 + args.k]:
            b = replace(src, new_seat=seat)
            before = await env2.reset(extra, 6)
            outcome = await env2.executor().run(routine, rr.inputs_for(routine, src, b), task_id=f"p6-canvas-{name}-{seat}", launch="never",
                                               allow_repair=True, allow_agent=False)
            ok = outcome.succeeded and fam.check(env2.app.state(), before, b, outcome.outputs, rr.answer_of(outcome))
            how = [r for st in outcome.steps for r in st.rungs if r.startswith(("found its picture", "looked for"))]
            print(f"{'PASS' if ok else 'FAIL'} {name:11s} seat {seat}: {outcome.status} calls={outcome.model_calls} "
                  f"${outcome.cost_at_standard_usd:.4f} {outcome.duration_s}s {how} {outcome.detail[:60]}", flush=True)
            rows.append({"device": name, "seat": seat, "passed": ok, "status": outcome.status, "model_calls": outcome.model_calls,
                         "cost_usd": outcome.cost_at_standard_usd, "duration_s": outcome.duration_s, "found": how, "detail": outcome.detail})
    out["replays"] = rows
    print("saved", save("canvas", out))


# ---- the scrcpy path: frames, screenshots and input on a phone -----------------------------------------------------

async def cmd_stream(args: argparse.Namespace) -> None:
    """scrcpy on a phone (or an emulator standing in): start time, frame rate, screenshot time against adb screencap, and
    tap → visibly different frame (input + app + encode + decode), alternating two SkyLark tabs."""
    import hashlib
    from devices.scrcpy import ScrcpyStream
    from devices.types import Action
    dev = open_device(args.device)
    app = SkyLark(dev.serial)
    from skylark_routines import fixtures as sk_fixtures
    app.prepare(fixtures=sk_fixtures([]), variant=0)
    await dev.wait_until_settled()
    caps = dev.capabilities
    stream = ScrcpyStream(dev.serial, (caps.width, caps.height))
    t0 = time.perf_counter()
    stream.start()
    stream.frame(200, timeout=5)
    start_ms = (time.perf_counter() - t0) * 1000
    n0, t1 = stream.frames, time.time()
    await asyncio.sleep(3)
    fps_idle = (stream.frames - n0) / (time.time() - t1)

    def digest() -> str:
        return hashlib.blake2b(stream.frame(270).tobytes(), digest_size=8).hexdigest()

    shots_stream, shots_adb, taps = [], [], []
    for i in range(args.n):
        s = await dev.observe()
        target = next(e for e in s.numbered if e.label.startswith("My Trips" if i % 2 == 0 else "Home"))
        await asyncio.sleep(0.6)
        before = digest()
        sent = time.time()
        stream.tap(*target.center)
        changed = None
        while time.time() - sent < 3:
            if stream.wait_for_new_frame(stream.frame_time, 0.5) and digest() != before:
                changed = (stream.frame_time - sent) * 1000
                break
        taps.append(changed)
        t = time.perf_counter(); stream.png(); shots_stream.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter(); dev.screencap_png(); shots_adb.append((time.perf_counter() - t) * 1000)
    stream.stop()
    ok = [x for x in taps if x is not None]
    out = {"time": now(), "device": args.device, "model": dev.model, "android": dev.android, "real_phone": caps.real_phone,
           "frame_size": [stream._frame.width, stream._frame.height] if stream._frame else None,
           "start_ms": round(start_ms), "fps_idle": round(fps_idle, 1),
           "tap_to_frame_ms": {"n": len(taps), "seen": len(ok), "p50": round(statistics.median(ok)) if ok else None,
                               "max": round(max(ok)) if ok else None, "all": [round(x) if x else None for x in taps]},
           "screenshot_ms": {"stream_p50": round(statistics.median(shots_stream), 1), "adb_screencap_p50": round(statistics.median(shots_adb))}}
    print(json.dumps(out, indent=1))
    print("saved", save(args.name or f"stream-{args.device}", out))
    if isinstance(dev, PhoneDevice):
        dev.close()


# ---- the live view of a phone, through the API (the same WebSocket the web app and the iPhone use) ----------------

async def cmd_live(args: argparse.Namespace) -> None:
    """Frames from `WS /api/live/{id}` while the screen changes (the notification shade opening and closing):
    capture → received latency on this Mac (clock offset from ping/pong), frame size, frames per second."""
    import ssl
    import struct
    import subprocess

    import websockets
    token = Path(args.token_file).read_text().strip()
    base = args.base.rstrip("/")
    url = base.replace("https://", "wss://").replace("http://", "ws://") + f"/api/live/{args.id}?fps=10&width={args.width}&quality=60"
    hdr = {"Authorization": f"Bearer {token}", "Origin": base}
    lat, rtts, sizes, offset = [], [], [], 0.0
    kw: dict[str, Any] = {"ssl": ssl.create_default_context()} if url.startswith("wss://") else {}
    async with websockets.connect(url, additional_headers=hdr, max_size=None, **kw) as ws:
        hello = json.loads(await ws.recv())
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

        async def change_screen() -> None:
            for i in range(10):
                cmd = "expand-notifications" if i % 2 == 0 else "collapse"
                await asyncio.to_thread(subprocess.run, ["adb", "-s", args.serial, "shell", "cmd", "statusbar", cmd], timeout=20)
                await asyncio.sleep(0.8)
        changer = asyncio.create_task(change_screen())
        t0 = time.time()
        while time.time() - t0 < 9:
            try:
                m = await asyncio.wait_for(ws.recv(), 2)
            except asyncio.TimeoutError:
                continue
            if isinstance(m, bytes):
                lat.append((time.time() + offset - struct.unpack(">d", m[:8])[0]) * 1000)
                sizes.append(len(m))
        await changer
    med = lambda xs: round(statistics.median(xs)) if xs else None  # noqa: E731
    out = {"time": now(), "url": url.split("?")[0], "hello": hello, "frames": len(lat), "fps": round(len(lat) / 9, 1),
           "frame_ms_p50": med(lat), "frame_ms_max": round(max(lat)) if lat else None, "rtt_ms_p50": med(rtts),
           "kb_per_frame": round(statistics.median(sizes) / 1024, 1) if sizes else None}
    print(json.dumps(out, indent=1))
    print("saved", save(args.name or f"live-{args.id}", out))


async def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("portability")
    p.add_argument("--device", default="envoy-small")
    p.add_argument("--k", type=int, default=3)
    p.add_argument("--seed", type=int, default=600)
    p.add_argument("--no-control", action="store_true")
    p.add_argument("--families", default="", help="comma-separated family ids (default: all)")
    p.add_argument("--name", default="")
    v = sub.add_parser("vision")
    v.add_argument("--devices", default="envoy-test,envoy-small")
    v.add_argument("--seats", type=int, default=8)
    v.add_argument("--per-screen", type=int, default=2)
    v.add_argument("--methods", default="step,grounding,sam")
    v.add_argument("--offset", type=int, default=0, help="which seats (another sample of the same map)")
    v.add_argument("--seed", type=int, default=6, help="which real-app targets")
    v.add_argument("--name", default="")
    st = sub.add_parser("stream")
    st.add_argument("--device", default="phone")
    st.add_argument("--n", type=int, default=10)
    st.add_argument("--name", default="")
    lv = sub.add_parser("live")
    lv.add_argument("--base", default="http://127.0.0.1:8700")
    lv.add_argument("--id", required=True)
    lv.add_argument("--serial", required=True)
    lv.add_argument("--token-file", default=str(REPO / "data" / "api" / "session_token"))  # read here, never printed
    lv.add_argument("--width", type=int, default=720)
    lv.add_argument("--name", default="")
    c = sub.add_parser("canvas")
    c.add_argument("--k", type=int, default=3)
    c.add_argument("--task", default="", help="compile an earlier agent run instead of recording one")
    args = ap.parse_args()
    if args.cmd == "portability":
        await cmd_portability(args)
    elif args.cmd == "vision":
        await cmd_vision(args)
    elif args.cmd == "canvas":
        await cmd_canvas(args)
    elif args.cmd == "stream":
        await cmd_stream(args)
    elif args.cmd == "live":
        await cmd_live(args)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
