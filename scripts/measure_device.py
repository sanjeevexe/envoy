"""Phase 0 device measurements on envoy-test: median and p90 over N runs.

Usage: uv run --project backend python scripts/measure_device.py [--runs 20] [--skip-snapshot]
Needs envoy-test running (scripts/start_emulator.sh envoy-test).
Writes logs/measure_device.json and prints a Markdown table.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from devices.emulator import EmulatorDevice, _adb_path
from devices.grpc_gen import emulator_controller_pb2 as pb
from devices.types import Action

REPO = Path(__file__).resolve().parents[1]
TYPED_TEXT = "Café Ñandú 東京 Привет 😀"
SNAPSHOT = "phase0-measure"


def p90(values: list[float]) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, round(0.9 * (len(s) - 1)))]


def timed(fn, runs: int) -> list[float]:
    out = []
    for _ in range(runs):
        t = time.perf_counter()
        fn()
        out.append((time.perf_counter() - t) * 1000)
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--skip-snapshot", action="store_true")
    args = ap.parse_args()
    n = args.runs

    d = EmulatorDevice("envoy-test").connect()
    results: dict[str, dict] = {}

    def record(name: str, values: list[float], note: str = "", **extra) -> None:
        results[name] = {
            "median_ms": round(statistics.median(values), 1),
            "p90_ms": round(p90(values), 1),
            "min_ms": round(min(values), 1),
            "max_ms": round(max(values), 1),
            "runs": len(values),
            "note": note,
            **extra,
        }
        print(f"{name:42s} median {results[name]['median_ms']:8.1f} ms   p90 {results[name]['p90_ms']:8.1f} ms  ({len(values)} runs)")

    # Start from a fresh Settings home screen.
    def settings_home():
        """Back to the Settings home screen; returns its search bar element."""
        for _ in range(4):
            s = d._settle_sync(5)
            bar = next((e for e in s.numbered if e.resource_id.endswith("search_action_bar")), None)
            if bar:
                return bar
            d.u2.press("back")
        d.u2.press("home")
        d.adb.shell("am force-stop com.google.android.settings.intelligence")  # search runs in its own package
        d.u2.app_start("com.android.settings", stop=True)
        s = d._settle_sync(5)
        return next(e for e in s.numbered if e.resource_id.endswith("search_action_bar"))

    await d.act(Action(kind="home"))
    d.adb.shell("am force-stop com.google.android.settings.intelligence")
    d.u2.app_start("com.android.settings", stop=True)
    settings_home()

    # 1. Tree reads
    record("tree read (uiautomator2 dump)", timed(d.u2.dump_hierarchy, n), "raw XML from the uiautomator2 server")
    record("observe() (dump + focus + parse + compact)", timed(lambda: d._observe_sync(False), n),
           "what the agent pays per step without a screenshot")

    # 2. Screenshots
    record("gRPC screenshot, raw RGB888", timed(lambda: d.grpc._call(pb.ImageFormat.RGB888, 10), n), "1080x2400 raw frame, 7.8 MB")
    record("gRPC screenshot, PNG encoded locally", timed(lambda: d.grpc.png(encode_locally=True), n), "RGB888 + Pillow PNG (level 1)")
    record("gRPC screenshot, PNG from emulator", timed(lambda: d.grpc.png(encode_locally=False), n), "emulator encodes PNG")
    record("adb exec-out screencap -p", timed(d.screencap_png, n), "fallback path")

    # 3. Taps
    s = d._observe_sync(False)
    title = next(e for e in s.numbered if e.resource_id.endswith("homepage_title"))
    record("tap via uiautomator2 (call returns)", timed(lambda: d.u2.click(*title.center), n),
           "tap on a non-interactive title; call returns after injection")
    record("tap via emulator gRPC sendTouch", timed(lambda: d.grpc.tap(*title.center), n),
           "press + release on the virtual touchscreen (emulators only)")

    tap_to_settle = []
    for _ in range(n):
        search = settings_home()
        t = time.perf_counter()
        d._tap(*search.center)  # the device's tap path (gRPC)
        d._settle_sync(5)
        tap_to_settle.append((time.perf_counter() - t) * 1000)
    record("tap → next screen settled", tap_to_settle,
           "tap Search settings, then wait until the tree is unchanged for 250 ms (includes the 250 ms quiet window)")

    # 4. Typing non-English text into the Settings search field, through the device's `type` action
    #    (accessibility set-text). The XML dump shows emoji as "..", so the field is read back with get_text.
    d.u2.click(*settings_home().center)
    d._settle_sync(5)
    typing, correct, dump_exact = [], 0, 0
    for _ in range(n):
        s = d._observe_sync(False)
        field = next(e for e in s.numbered if e.editable)
        t = time.perf_counter()
        r = d._act_sync(Action(kind="type", element=field.number, text=TYPED_TEXT))
        typing.append((time.perf_counter() - t) * 1000)
        correct += r.ok and d.u2(focused=True).get_text() == TYPED_TEXT
        dump_exact += any(e.text == TYPED_TEXT for e in d._observe_sync(False).elements)
    record("type non-English text (set-text)", typing,
           f"text {TYPED_TEXT!r}; exact via get_text {correct}/{n}; exact in XML dump {dump_exact}/{n} (emoji shows as '..')",
           correct=correct, dump_exact=dump_exact)
    clip = d.u2.clipboard or ""
    results["clipboard after typing"] = {"empty": clip == "", "note": "set-text must not touch the clipboard"}
    adb_input = subprocess.run([_adb_path(), "-s", d.serial, "shell", "input", "text", "Café"], capture_output=True, text=True)
    results["adb input text (non-ASCII)"] = {"returncode": adb_input.returncode,
                                             "output": (adb_input.stdout + adb_input.stderr).strip()[:300]}
    settings_home()

    # 5. Snapshot restore (save once, then load N times, including reconnecting uiautomator2 and gRPC)
    if not args.skip_snapshot:
        await d.act(Action(kind="home"))
        await d.launch("com.android.settings")
        await d.wait_until_settled()
        await d.snapshot_save(SNAPSHOT)
        loads, emu_only, ok = [], [], 0
        for _ in range(n):
            t = time.perf_counter()
            await asyncio.to_thread(d._emu, "avd", "snapshot", "load", SNAPSHOT)
            t_emu = time.perf_counter()
            await asyncio.to_thread(d._reconnect)
            s = await d.observe()
            loads.append((time.perf_counter() - t) * 1000)
            emu_only.append((t_emu - t) * 1000)
            ok += s.package == "com.android.settings"
        record("snapshot restore (load + reconnect + observe)", loads, f"back on Settings after restore: {ok}/{n}", correct=ok)
        record("snapshot restore (emulator load only)", emu_only, "adb emu avd snapshot load")

    out = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "device": {"avd": d.avd, **d.capabilities.__dict__},
        "results": results,
    }
    (REPO / "logs").mkdir(exist_ok=True)
    (REPO / "logs" / "measure_device.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))

    print("\n| Measurement | Median (ms) | p90 (ms) | Runs | Note |\n| --- | --- | --- | --- | --- |")
    for name, r in results.items():
        if "median_ms" in r:
            print(f"| {name} | {r['median_ms']:.0f} | {r['p90_ms']:.0f} | {r['runs']} | {r['note']} |")
    print(f"\nadb input text with non-ASCII: {results['adb input text (non-ASCII)']}")


if __name__ == "__main__":
    asyncio.run(main())
