"""Phase 0 B1: real-app compatibility on envoy-real.

  uv run --project backend python scripts/real_app_check.py install <package>   # Play Store page → Install → wait
  uv run --project backend python scripts/real_app_check.py probe <package> [--step NAME]
      # launch (or use the current screen with --here), record the screen, secure flag,
      # password fields, and whether gRPC / screencap / scrcpy frames are black

Never run `probe` while the user is typing a password: the agent takes screenshots.
Results append to logs/real_apps.jsonl; thumbnails go to eval/results/phase0/real_apps/ (pre-sign-in screens only).
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from secure_screen_check import scrcpy_frame  # noqa: E402

from devices.emulator import EmulatorDevice  # noqa: E402
from devices.emulator_grpc import black_fraction  # noqa: E402
from devices.types import Action  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
THUMBS = REPO / "eval" / "results" / "phase0" / "real_apps"
LOG = REPO / "logs" / "real_apps.jsonl"
BLACK = 0.98
BLOCK_WORDS = re.compile(
    r"not supported|unsupported|isn.t compatible|not compatible|integrity|rooted|emulator|"
    r"something went wrong|try again later|security|tamper|update required",
    re.I,
)


def log(entry: dict) -> None:
    LOG.parent.mkdir(exist_ok=True)
    entry = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry}
    with LOG.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(json.dumps(entry, indent=1, ensure_ascii=False))


def installed(d: EmulatorDevice, pkg: str) -> bool:
    return f"package:{pkg}" in d.adb.shell(f"pm list packages {pkg}").split()


async def install(d: EmulatorDevice, pkg: str, timeout_s: int = 600) -> None:
    if installed(d, pkg):
        log({"package": pkg, "step": "install", "result": "already installed"})
        return
    d.adb.shell(f"am start -a android.intent.action.VIEW -d market://details?id={pkg} -p com.android.vending")
    s = await d.wait_until_settled(10)
    # Play Store merges the button's description and caption: "Install · Install".
    button = next((e for e in s.numbered if re.fullmatch(r"(Install|Get)( · (Install|Get))?", e.label) and e.enabled), None)
    if button is None:
        log({"package": pkg, "step": "install", "result": "no Install button", "screen": s.compact})
        return
    t0 = time.time()
    await d.act(Action(kind="tap", element=button.number))
    while time.time() - t0 < timeout_s:
        if installed(d, pkg):
            log({"package": pkg, "step": "install", "result": "installed", "seconds": round(time.time() - t0)})
            return
        await asyncio.sleep(3)
    s = await d.observe()
    log({"package": pkg, "step": "install", "result": "timed out", "screen": s.compact})


async def probe(d: EmulatorDevice, pkg: str, step: str, here: bool, thumbs: bool) -> None:
    if not here:
        d.adb.shell(f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1")
        await asyncio.sleep(2)
    s = await d.wait_until_settled(15)
    pid = d.adb.shell(f"pidof {pkg}").strip()
    grpc_img = d.grpc.image()
    try:
        cap_img = Image.open(io.BytesIO(d.screencap_png()))
    except Exception:
        cap_img = None
    scr_img = scrcpy_frame(d.serial, seconds=3)
    frames = {
        "grpc": round(black_fraction(grpc_img), 3),
        "screencap": round(black_fraction(cap_img), 3) if cap_img else None,
        "scrcpy": round(black_fraction(scr_img), 3) if scr_img else None,
    }
    entry = {
        "package": pkg,
        "step": step,
        "foreground": s.package,
        "activity": s.activity,
        "running": bool(pid),
        "secure": s.secure,
        "password_field": s.has_password_field,
        "tree_nodes": len(s.elements),
        "tree_readable": len(s.numbered) > 0,
        "black": {k: (v is not None and v >= BLACK) for k, v in frames.items()},
        "black_fraction": frames,
        "blocking_words": sorted({m.group(0).lower() for m in BLOCK_WORDS.finditer(s.compact)}),
        "screen": s.compact,
    }
    if thumbs and not s.has_password_field:
        folder = THUMBS / pkg
        folder.mkdir(parents=True, exist_ok=True)
        for name, img in (("grpc", grpc_img), ("screencap", cap_img), ("scrcpy", scr_img)):
            if img is not None:
                img.convert("RGB").resize((270, 600)).save(folder / f"{step}_{name}.png")
    log(entry)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["install", "probe"])
    ap.add_argument("package")
    ap.add_argument("--step", default="launch")
    ap.add_argument("--here", action="store_true", help="probe the current screen instead of launching")
    ap.add_argument("--no-thumbs", action="store_true")
    args = ap.parse_args()
    d = EmulatorDevice("envoy-real").connect()
    if args.cmd == "install":
        await install(d, args.package)
    else:
        await probe(d, args.package, args.step, args.here, not args.no_thumbs)


if __name__ == "__main__":
    asyncio.run(main())
