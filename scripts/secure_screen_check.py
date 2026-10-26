"""Phase 0 secure-screen check (A4): is a FLAG_SECURE screen black in scrcpy video, the emulator gRPC
screenshot and `adb screencap`, and is its accessibility tree still readable?

Uses Chrome on envoy-test: a normal tab (baseline) and an incognito tab (FLAG_SECURE), no account.
Usage: uv run --project backend python scripts/secure_screen_check.py
Writes eval/fixtures/phase0/secure/<case>_<method>.png (small thumbnails) and logs/secure_screen_check.json.
"""

from __future__ import annotations

import asyncio
import io
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from PIL import Image

from devices.emulator import EmulatorDevice, _adb_path
from devices.emulator_grpc import black_fraction
from devices.types import Action, ScreenState

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "eval" / "fixtures" / "phase0" / "secure"
CHROME = "com.android.chrome"
BLACK = 0.98  # share of near-black pixels above which a frame counts as black


def thumb(img: Image.Image, name: str) -> str:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.png"
    img.convert("RGB").resize((270, 600)).save(path)
    return str(path.relative_to(REPO))


def scrcpy_frame(serial: str, seconds: int = 4) -> Image.Image | None:
    """Record a few seconds of scrcpy video headless and return the last frame."""
    tmp = Path(tempfile.mkdtemp())
    video, frame = tmp / "rec.mkv", tmp / "frame.png"
    subprocess.run(
        ["scrcpy", "-s", serial, "--no-window", "--no-audio", "--no-control", f"--record={video}",
         f"--time-limit={seconds}", "--max-size=1200"],
        capture_output=True, timeout=seconds + 30,
    )
    if not video.exists():
        return None
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-sseof", "-0.5", "-i", str(video), "-frames:v", "1", str(frame)],
                   capture_output=True, timeout=30)
    img = Image.open(frame).copy() if frame.exists() else None
    shutil.rmtree(tmp, ignore_errors=True)
    return img


def tree_summary(s: ScreenState) -> dict:
    return {
        "nodes": len(s.elements),
        "numbered": len(s.numbered),
        "readable": len(s.numbered) > 0,
        "has_password_field": s.has_password_field,
        "compact": s.compact,
    }


def measure(d: EmulatorDevice, case: str) -> dict:
    out: dict = {"case": case}
    s = d._settle_sync(5)
    out["tree"] = tree_summary(s)

    img = d.grpc.image()
    out["grpc_screenshot"] = {"black_fraction": round(black_fraction(img), 4), "file": thumb(img, f"{case}_grpc")}
    try:
        img = Image.open(io.BytesIO(d.screencap_png()))
        out["adb_screencap"] = {"black_fraction": round(black_fraction(img), 4), "file": thumb(img, f"{case}_screencap")}
    except Exception as e:
        out["adb_screencap"] = {"error": str(e)[:300]}
    img = scrcpy_frame(d.serial)
    out["scrcpy_video"] = (
        {"black_fraction": round(black_fraction(img), 4), "file": thumb(img, f"{case}_scrcpy")} if img else {"error": "no frame"}
    )
    for k in ("grpc_screenshot", "adb_screencap", "scrcpy_video"):
        if "black_fraction" in out[k]:
            out[k]["black"] = out[k]["black_fraction"] >= BLACK
    secure = subprocess.run([_adb_path(), "-s", d.serial, "shell", "dumpsys window | grep -E 'mCurrentFocus|FLAG_SECURE|fl=.*SECURE' | head -5"],
                            capture_output=True, text=True).stdout
    out["window_flags_excerpt"] = secure.strip()[:600]
    return out


def find(s: ScreenState, *labels: str, rid: str | None = None):
    for e in s.numbered:
        if rid and e.resource_id.endswith(rid):
            return e
        if any(e.label.lower().startswith(l.lower()) for l in labels):
            return e
    return None


async def get_past_first_run(d: EmulatorDevice) -> list[str]:
    """Chrome's first-run screens, taking the most private option each time (no account, no sync, no stats)."""
    steps = []
    for _ in range(8):
        s = await d.wait_until_settled(6)
        if find(s, rid="url_bar") or find(s, rid="search_box_text") or find(s, "Search or type"):
            return steps
        # Uncheck usage statistics if it is offered and on.
        stats = next((e for e in s.numbered if e.checkable and e.checked and "usage" in e.label.lower()), None)
        if stats:
            await d.act(Action(kind="tap", element=stats.number))
            steps.append("unchecked usage statistics")
            continue
        el = find(s, "Use without an account", "No thanks", "No, thanks", "Not now", "Skip", "Continue", "Accept & continue", "Got it")
        if el is None:
            steps.append("stuck: " + s.compact[:200])
            return steps
        steps.append(f"tapped {el.label!r}")
        await d.act(Action(kind="tap", element=el.number))
    return steps


async def main() -> None:
    d = EmulatorDevice("envoy-test").connect()
    results: dict = {}

    await d.act(Action(kind="home"))
    await asyncio.to_thread(d.u2.app_start, CHROME, stop=True)
    results["first_run_steps"] = await get_past_first_run(d)

    # Baseline: a normal tab on a plain page.
    await asyncio.to_thread(d.adb.shell, "am start -a android.intent.action.VIEW -d https://example.com -p " + CHROME)
    time.sleep(3)
    results["normal_tab"] = measure(d, "chrome_normal")

    # Incognito: menu → New Incognito tab.
    s = await d.wait_until_settled()
    menu = find(s, "More options", "Customize and control", rid="menu_button")
    await d.act(Action(kind="tap", element=menu.number))
    s = await d.wait_until_settled()
    item = find(s, "New Incognito tab")
    await d.act(Action(kind="tap", element=item.number))
    time.sleep(2)
    results["incognito_tab"] = measure(d, "chrome_incognito")

    (REPO / "logs").mkdir(exist_ok=True)
    (REPO / "logs" / "secure_screen_check.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(json.dumps({k: ({m: v.get(m, {}).get("black") for m in ("grpc_screenshot", "adb_screencap", "scrcpy_video")}
                          | {"tree_readable": v["tree"]["readable"], "nodes": v["tree"]["nodes"]})
                      if isinstance(v, dict) and "tree" in v else v for k, v in results.items()}, indent=2))
    print("\nIncognito tab, as the agent sees it:\n" + results["incognito_tab"]["tree"]["compact"])

    # Close incognito tabs and leave Chrome.
    await asyncio.to_thread(d.u2.app_start, CHROME, stop=True)
    await d.act(Action(kind="home"))


if __name__ == "__main__":
    asyncio.run(main())
