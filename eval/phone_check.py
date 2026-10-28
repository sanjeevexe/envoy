"""Phase 6 on the real phone: what the routine suites don't measure.

  uv run --project backend python eval/phone_check.py facts     model, Android, screen, SIM, keyboard, clock
  uv run --project backend python eval/phone_check.py device    reading, settling and typing on the phone (the bridge decision)
  uv run --project backend python eval/phone_check.py stream    scrcpy: start, tap → changed frame, screenshot from the stream
  uv run --project backend python eval/phone_check.py live --id <phone id>     the live view through the API (this Mac)
  uv run --project backend python eval/phone_check.py banner    the banner on this phone's skin, captured while it shows

Only the device layer is imported (no routines): these measure the phone itself. SkyLark is test data; Settings is the
phone's own app (no account on it). Results: eval/results/phase6/phone-*.json (and the banner's PNGs).

The bridge decision (design doc, "Envoy bridge"): build it only if waiting for the screen to settle, or setting text, is
unreliable. `device` measures exactly those two on the phone: how often a settled screen still changes in the next 1.5 s
(a premature settle), and whether set-text puts the exact text in the field, keeps the user's keyboard, and leaves the
clipboard alone.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import statistics
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "eval"))
sys.path.insert(0, str(REPO / "backend"))

from devices.phone import BANNER_PACKAGE, PhoneDevice, discover  # noqa: E402
from devices.types import Action  # noqa: E402
from skylark_routines import fixtures as sk_fixtures  # noqa: E402
from testapps.skylark import SkyLark  # noqa: E402

OUT = REPO / "eval" / "results" / "phase6"
TYPED_TEXT = "Café Ñandú 東京 Привет 😀"  # Phase 0's text: accents, CJK, Cyrillic, emoji
SETTINGS = "com.android.settings"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save(name: str, payload: Any) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.json"
    path.write_text(json.dumps(payload, indent=1, default=str, ensure_ascii=False))
    print("saved", path.relative_to(REPO))
    return path


def stats(values: list[float]) -> dict[str, Any]:
    s = sorted(values)
    return {"p50": round(statistics.median(s), 1), "p90": round(s[min(len(s) - 1, round(0.9 * (len(s) - 1)))], 1),
            "max": round(s[-1], 1), "n": len(s)}


def the_phone() -> dict[str, Any]:
    phones = [p for p in discover() if p["state"] == "device"]
    if not phones:
        raise SystemExit("no Android phone connected (adb devices): plug it in and allow USB debugging")
    return phones[0]


def shell(serial: str, *args: str, timeout: float = 20) -> str:
    return subprocess.run(["adb", "-s", serial, "shell", *args], capture_output=True, text=True, timeout=timeout).stdout.strip()


# ---- facts ---------------------------------------------------------------------------------------------------------

def cmd_facts(_: argparse.Namespace) -> None:
    p = the_phone()
    s = p["serial"]
    get = lambda k: shell(s, "getprop", k)  # noqa: E731
    out = {"time": now(), "id": p["id"], "model": get("ro.product.model"), "manufacturer": get("ro.product.manufacturer"),
           "device": get("ro.product.device"), "android": get("ro.build.version.release"), "sdk": get("ro.build.version.sdk"),
           "security_patch": get("ro.build.version.security_patch"), "build": get("ro.build.id"), "abi": get("ro.product.cpu.abi"),
           "sim": get("gsm.sim.state"), "size": shell(s, "wm", "size"), "density": shell(s, "wm", "density"),
           "keyboard": shell(s, "settings", "get", "secure", "default_input_method"),
           "clock_offset_s": round(int(shell(s, "date", "+%s")) - time.time())}
    print(json.dumps(out, indent=1))
    save("phone-facts", out)


# ---- reading, settling, typing ---------------------------------------------------------------------------------------

def _content(screen: Any) -> set[str]:
    """What the agent reads on a screen: the listed elements' labels (the status bar and the clock are left out)."""
    return {f"{e.kind}|{e.label}" for e in screen.numbered if e.label}


def _settle_case(dev: PhoneDevice, tap_label: str, expect: str, n: int, back: Any) -> dict[str, Any]:
    """Tap the element labelled `tap_label`, wait for the screen to settle, then keep watching for 1.5 s: if what the
    agent would read changes after "settled", the settle was premature, unless only numbers changed (a battery level
    ticking, "58 min left" becoming "57 min left": the world moved, not the screen). `expect` must be on the settled screen."""
    import re
    times, late, ticking, missing, notes = [], 0, 0, 0, []
    for _ in range(n):
        start = dev._settle_sync(5)
        el = next((e for e in start.numbered if e.label.startswith(tap_label)), None)
        if el is None:
            notes.append(f"no {tap_label!r} to tap")
            back()
            continue
        t = time.perf_counter()
        dev._tap(*el.center)
        settled = dev._settle_sync(5)
        times.append((time.perf_counter() - t) * 1000)
        time.sleep(1.5)
        later = dev._observe_sync(False)
        a, b = _content(settled), _content(later)
        if a != b:
            digits = lambda xs: {re.sub(r"\d+(?:[.,]\d+)?", "#", x) for x in xs}  # noqa: E731
            if digits(a) == digits(b):
                ticking += 1
            else:
                late += 1
            notes.append(f"{'numbers changed' if digits(a) == digits(b) else 'changed'} after settling: +{sorted(b - a)[:3]} -{sorted(a - b)[:3]}")
        if not any(expect in lab for lab in a):
            missing += 1
            notes.append(f"{expect!r} not on the settled screen")
        back()
    return {"tap_to_settled_ms": stats(times) if times else None, "runs": len(times), "premature": late,
            "live_values_changed": ticking, "expected_missing": missing, "notes": notes[:8]}


def _type_case(dev: PhoneDevice, field: Any, n: int) -> dict[str, Any]:
    """Accessibility set-text into one field, n times: the exact text read back (get_text keeps emoji; the XML dump
    writes them as ".."), the time, the keyboard unchanged."""
    ime = shell(dev.serial, "settings", "get", "secure", "default_input_method")
    times, exact, in_dump, copied = [], 0, 0, 0
    for _ in range(n):
        s = dev._observe_sync(False)
        f = next((e for e in s.numbered if e.editable and (e.resource_id == field.resource_id or e.bounds == field.bounds)), None) \
            or next(e for e in s.numbered if e.editable)
        t = time.perf_counter()
        r = dev._act_sync(Action(kind="type", element=f.number, text=TYPED_TEXT))
        times.append((time.perf_counter() - t) * 1000)
        got = dev.u2(focused=True).get_text() if r.ok else None
        exact += got == TYPED_TEXT
        after = dev._observe_sync(False)
        in_dump += any(TYPED_TEXT.replace("😀", "..") in (e.text or "") for e in after.elements)
        # Android 13 shows a "Copied" preview whenever anything writes the clipboard (its elements are left out of the
        # screen Envoy reads, but they are in the raw tree).
        copied += any("clipboard" in (e.resource_id or "") for e in after.elements)
    return {"type_ms": stats(times), "exact_via_get_text": exact, "shown_in_dump": in_dump, "clipboard_preview_shown": copied, "runs": n,
            "keyboard_unchanged": shell(dev.serial, "settings", "get", "secure", "default_input_method") == ime}


async def cmd_device(args: argparse.Namespace) -> None:
    p = the_phone()
    dev = PhoneDevice(p["serial"], p["id"]).connect()
    n = args.n
    app = SkyLark(dev.serial)
    if not app.installed():
        app.install()
    app.prepare(fixtures=sk_fixtures([]), variant=0)
    await dev.wait_until_settled()
    name = args.name or "phone-device"
    prev = json.loads((OUT / f"{name}.json").read_text()) if (OUT / f"{name}.json").exists() else {}
    out: dict[str, Any] = {**prev, "time": now(), "phone": {"id": p["id"], "model": dev.model, "android": dev.android,
                                                            "size": [dev.capabilities.width, dev.capabilities.height], "density": dev.capabilities.density}}
    tab = lambda rid: dev._tap(*next(e for e in dev._settle_sync(5).numbered if e.resource_id.endswith(rid)).center)  # noqa: E731
    parts = args.parts.split(",")
    if "reads" in parts:
        _reads(dev, n, out)
        save(name, out)
    if "settle" in parts:
        _settling(dev, n, out, tab, args.cases)
        save(name, out)
    if "typing" in parts:
        _typing(dev, app, n, out, tab)
        save(name, out)
    dev._act_sync(Action(kind="home"))
    dev.close()


def _reads(dev: PhoneDevice, n: int, out: dict[str, Any]) -> None:
    """1. Reading the screen."""
    def timed(fn: Any, k: int = n) -> list[float]:
        xs = []
        for _ in range(k):
            t = time.perf_counter()
            fn()
            xs.append((time.perf_counter() - t) * 1000)
        return xs
    out["tree_read_ms"] = stats(timed(dev.u2.dump_hierarchy))
    out["observe_ms"] = stats(timed(lambda: dev._observe_sync(False)))
    out["screenshot_ms"] = {"scrcpy_frame": stats(timed(dev._screenshot_sync)), "adb_screencap": stats(timed(dev.screencap_png, max(3, n // 3)))}
    print("reads", json.dumps({k: out[k] for k in ("tree_read_ms", "observe_ms", "screenshot_ms")}), flush=True)


def _settling(dev: PhoneDevice, n: int, out: dict[str, Any], tab: Any, cases: str) -> None:
    """2. Settling: SkyLark (Compose) and the phone's Settings (Android views, content that loads after the page opens)."""
    settle: dict[str, Any] = dict(out.get("settling") or {})
    want = cases.split(",") if cases else ["skylark_home_to_trips", "skylark_trips_to_home", "settings_apps", "settings_network",
                                            "settings_battery"]
    if "skylark_home_to_trips" in want:
        tab("nav_home")
        settle["skylark_home_to_trips"] = _settle_case(dev, "My Trips", "Find a trip", n, lambda: tab("nav_home"))
    if "skylark_trips_to_home" in want:
        tab("nav_trips")
        settle["skylark_trips_to_home"] = _settle_case(dev, "Home", "Next trip", n, lambda: tab("nav_trips"))
        tab("nav_home")
    if any(c.startswith("settings_") for c in want):
        dev._launch(SETTINGS)
        dev._settle_sync(5)
    back = lambda: (dev._act_sync(Action(kind="back")), dev._settle_sync(5))  # noqa: E731
    for case, label, expect in (("settings_apps", "Apps", "Apps"), ("settings_network", "Network & internet", "Internet"),
                                ("settings_battery", "Battery", "Battery")):
        if case in want:
            settle[case] = _settle_case(dev, label, expect, n, back)
    out["settling"] = settle
    print("settling", json.dumps({k: (v["tap_to_settled_ms"] or {}).get("p50") for k, v in settle.items()}),
          "premature", {k: v["premature"] for k, v in settle.items()}, flush=True)


def _typing(dev: PhoneDevice, app: SkyLark, n: int, out: dict[str, Any], tab: Any) -> None:
    """3. Typing: set-text into a Compose field (SkyLark's last name) and an Android view (Settings' search box)."""
    # Read only: uiautomator2's set_clipboard opens Android 13's share sheet on a real phone.
    try:
        clip_before = dev.u2.clipboard
    except Exception as e:  # noqa: BLE001
        clip_before = f"unreadable: {type(e).__name__}"
    typing: dict[str, Any] = {}
    app.prepare(fixtures=sk_fixtures([]), variant=0)
    tab("nav_trips")
    s = dev._settle_sync(5)
    field = next(e for e in s.numbered if e.editable and e.resource_id.endswith("field_last_name"))
    typing["skylark_last_name"] = _type_case(dev, field, n)
    dev._act_sync(Action(kind="back"))  # the keyboard
    dev._launch(SETTINGS)
    s = dev._settle_sync(5)
    bar = next((e for e in s.numbered if e.resource_id.endswith("search_action_bar")), None) or next(e for e in s.numbered if "Search" in e.label)
    dev._tap(*bar.center)
    s = dev._settle_sync(5)
    typing["settings_search"] = _type_case(dev, next(e for e in s.numbered if e.editable), n)
    # Submit with a plain Enter (the design: never the keyboard's own action, which can switch it).
    s = dev._observe_sync(False)
    f = next(e for e in s.numbered if e.editable)
    dev._act_sync(Action(kind="type", element=f.number, text="Bluetooth", submit=True))
    done = dev._settle_sync(5)
    typing["settings_search_submit"] = {"results_shown": sum("Bluetooth" in e.label for e in done.numbered if not e.editable)}
    try:
        clip_after = dev.u2.clipboard
    except Exception as e:  # noqa: BLE001
        clip_after = f"unreadable: {type(e).__name__}"
    typing["clipboard"] = {"unchanged": clip_before == clip_after, "readable": not str(clip_before).startswith("unreadable")}
    out["typing"] = typing
    print("typing", json.dumps(typing, ensure_ascii=False), flush=True)


# ---- scrcpy ----------------------------------------------------------------------------------------------------------

async def cmd_stream(args: argparse.Namespace) -> None:
    """The same measurement as `run_phase6.py stream` (Phase 6's stand-in numbers), on the phone: start time, idle frame
    rate, tap → visibly different frame (input + app + encode + decode), screenshot from the stream vs adb screencap."""
    from devices.scrcpy import ScrcpyStream
    p = the_phone()
    dev = PhoneDevice(p["serial"], p["id"]).connect()
    app = SkyLark(dev.serial)
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
        t = time.perf_counter()
        stream.png()
        shots_stream.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter()
        dev.screencap_png()
        shots_adb.append((time.perf_counter() - t) * 1000)
    stream.stop()
    ok = [x for x in taps if x is not None]
    out = {"time": now(), "phone": p["id"], "model": dev.model, "android": dev.android, "real_phone": caps.real_phone,
           "frame_size": [stream._frame.width, stream._frame.height] if stream._frame else None,
           "start_ms": round(start_ms), "fps_idle": round(fps_idle, 1),
           "tap_to_frame_ms": {"n": len(taps), "seen": len(ok), "p50": round(statistics.median(ok)) if ok else None,
                               "max": round(max(ok)) if ok else None, "all": [round(x) if x else None for x in taps]},
           "screenshot_ms": {"stream_p50": round(statistics.median(shots_stream), 1), "adb_screencap_p50": round(statistics.median(shots_adb))}}
    print(json.dumps(out, indent=1))
    dev._act_sync(Action(kind="home"))
    dev.close()
    save(args.name or "phone-stream", out)


# ---- the live view through the API -----------------------------------------------------------------------------------

async def cmd_live(args: argparse.Namespace) -> None:
    """Frames from `WS /api/live/{id}` (what the web app and the iPhone use) while the screen changes (the notification
    shade opening and closing): capture → received latency on this Mac (clock offset from ping/pong), size, frame rate.
    The token is read here and never printed."""
    import ssl

    import websockets
    p = the_phone()
    token = Path(args.token_file).read_text().strip()
    base = args.base.rstrip("/")
    url = base.replace("https://", "wss://").replace("http://", "ws://") + f"/api/live/{args.id or p['id']}?fps=10&width={args.width}&quality=60"
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
                await asyncio.to_thread(shell, p["serial"], "cmd", "statusbar", "expand-notifications" if i % 2 == 0 else "collapse")
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
    save(args.name or "phone-live-mac", out)


# ---- the banner on this phone's skin ---------------------------------------------------------------------------------

def cmd_banner(args: argparse.Namespace) -> None:
    """Wait (up to --wait s) for the banner to show, then save the top of the screen in each state it reaches (working,
    then paused if a touch or Pause pauses it). Read over adb only, so it never competes with a task's own session."""
    p = the_phone()
    s = p["serial"]
    from PIL import Image
    seen: dict[str, Any] = {}
    t0 = time.time()
    while time.time() - t0 < args.wait and len(seen) < 2:
        row = shell(s, "content", "query", "--uri", f"content://{BANNER_PACKAGE}/state", timeout=10)
        shown, paused = "shown=1" in row, "paused=1" in row
        state = "paused" if paused else "working"
        if shown and state not in seen:
            png = subprocess.run(["adb", "-s", s, "exec-out", "screencap", "-p"], capture_output=True, timeout=20).stdout
            img = Image.open(io.BytesIO(png))
            top = img.crop((0, 0, img.width, round(img.height * 0.12)))
            OUT.mkdir(parents=True, exist_ok=True)
            path = OUT / f"phone-banner-{state}.png"
            top.save(path)
            bounds = [ln.strip() for ln in shell(s, "uiautomator", "dump", "/dev/tty", timeout=30).split("<node") if BANNER_PACKAGE in ln][:1]
            seen[state] = {"after_s": round(time.time() - t0, 1), "png": str(path.relative_to(REPO)), "state_row": row[-120:],
                           "banner_node": bounds[0][:300] if bounds else None}
            print(f"banner {state}: saved {path.relative_to(REPO)}", flush=True)
        time.sleep(0.5)
    save(args.name or "phone-banner", {"time": now(), "phone": p["id"], "states": seen})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("facts")
    d = sub.add_parser("device")
    d.add_argument("--n", type=int, default=10)
    d.add_argument("--parts", default="reads,settle,typing")
    d.add_argument("--cases", default="", help="settling cases to (re)run, comma-separated (default: all)")
    d.add_argument("--name", default="")
    st = sub.add_parser("stream")
    st.add_argument("--n", type=int, default=10)
    st.add_argument("--name", default="")
    lv = sub.add_parser("live")
    lv.add_argument("--base", default="http://127.0.0.1:8700")
    lv.add_argument("--id", default="")
    lv.add_argument("--token-file", default=str(REPO / "data" / "api" / "session_token"))  # read here, never printed
    lv.add_argument("--width", type=int, default=720)
    lv.add_argument("--name", default="")
    b = sub.add_parser("banner")
    b.add_argument("--wait", type=float, default=900)
    b.add_argument("--name", default="")
    args = ap.parse_args()
    if args.cmd == "facts":
        cmd_facts(args)
    elif args.cmd == "banner":
        cmd_banner(args)
    else:
        asyncio.run({"device": cmd_device, "stream": cmd_stream, "live": cmd_live}[args.cmd](args))


if __name__ == "__main__":
    main()
