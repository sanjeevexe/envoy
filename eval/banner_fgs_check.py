"""Does the phone banner (android/banner) crash under rapid show and hide? Backlog #58, on an emulator only.

"Envoy banner keeps stopping" (Pixel 5, Android 13, Nov 1) was ForegroundServiceDidNotStartInTimeException: a HIDE
stopped the service while the next SHOW's start still owed startForeground(). This installs a banner APK on an
emulator and sends it --cycles cycles (10) each of: HIDE and SHOW back to back; HIDE and SHOW from two threads at once
(as the API used to); ASIDE/BACK (version 2); and a task's commands through the API's own Banner class. It reads the
crash buffer after each. Give --old-apk to run the first two on an older banner first: the crash it fixes, a race.

    uv run --project backend python eval/banner_fgs_check.py --serial emulator-5554 --old-apk <v1 app-debug.apk>

It refuses anything but an emulator: the real phone gets a new banner only through the API (devices/phone.py).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from devices.phone import BANNER_APK, BANNER_PACKAGE, Banner  # noqa: E402

SVC = f"{BANNER_PACKAGE}/.BannerService"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--serial", default="emulator-5554")
    p.add_argument("--old-apk", type=Path, help="an older banner to run first (the crash it fixes)")
    p.add_argument("--apk", type=Path, default=BANNER_APK, help="the banner to check (default: the one built here)")
    p.add_argument("--cycles", type=int, default=10, help="cycles of each kind (the crash is a race: more find it)")
    p.add_argument("--out", type=Path, help="write the results here as JSON")
    args = p.parse_args()
    if not args.serial.startswith("emulator-"):
        sys.exit("an emulator only (emulator-NNNN): the real phone gets its banner through the API")

    def adb(*a: str, timeout: float = 60) -> str:
        return subprocess.run(["adb", "-s", args.serial, *a], capture_output=True, text=True, timeout=timeout).stdout

    def am(action: str, *extra: str) -> str:
        return f"am start-foreground-service -n {SVC} -a {BANNER_PACKAGE}.{action} {' '.join(extra)}".strip()

    def version() -> str:
        return adb("shell", "pm", "list", "packages", "--show-versioncode", BANNER_PACKAGE).strip()

    def crashes() -> dict:
        log = adb("logcat", "-b", "crash", "-d")
        ours = [ln for ln in log.splitlines() if BANNER_PACKAGE in ln or "ForegroundService" in ln or "FATAL" in ln]
        fgs = [ln for ln in log.splitlines() if "ForegroundServiceDidNotStartInTime" in ln]
        return {"crash_lines": len(ours), "fgs_exceptions": len(fgs), "first": ours[:3]}

    def install(apk: Path, downgrade: bool = False) -> str:
        adb("install", "-r", *(["-d"] if downgrade else []), "-g", str(apk), timeout=180)
        adb("shell", "appops", "set", BANNER_PACKAGE, "SYSTEM_ALERT_WINDOW", "allow")
        return version()

    def cycles() -> dict:
        out = {}
        adb("logcat", "-b", "crash", "-c")
        show = am("SHOW", "--es", "text", "check")
        for _ in range(args.cycles):  # back to back: the next task's SHOW right behind a HIDE
            adb("shell", f"{show}; {am('HIDE')}; {show}; {am('HIDE')}")
        time.sleep(3)
        out["back_to_back"] = crashes()
        adb("logcat", "-b", "crash", "-c")
        for _ in range(args.cycles):  # a thread per command, as the API sent them before: HIDE and SHOW at once
            adb("shell", show)
            ts = [threading.Thread(target=adb, args=("shell", c)) for c in (am("HIDE"), show)]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
        adb("shell", am("HIDE"))
        time.sleep(3)
        out["concurrent"] = crashes()
        return out

    res: dict = {"cycles": args.cycles, "serial": args.serial, "avd": (adb("emu", "avd", "name").split() or [""])[0],
                 "sdk": adb("shell", "getprop", "ro.build.version.sdk").strip(), "before": version()}
    if args.old_apk:
        res["old"] = {"version": install(args.old_apk, downgrade=True), **cycles()}
    res["new"] = {"version": install(args.apk), **cycles()}
    adb("logcat", "-b", "crash", "-c")
    for _ in range(args.cycles):  # a tap under the pill: ASIDE then BACK, the service running throughout
        adb("shell", am("SHOW", "--es", "text", "check"))
        adb("shell", f"{am('ASIDE')}; {am('BACK')}")
    adb("shell", am("HIDE"))
    time.sleep(3)
    res["new"]["aside_back"] = crashes()
    b = Banner(args.serial)
    adb("logcat", "-b", "crash", "-c")
    for i in range(args.cycles):  # the API's own Banner: a task, a tap under the pill, its end, the next at once
        b.show(f"Envoy check {i}")
        b.step_aside()
        b.step_back()
        b.pause("check")
        b.resume()
        b.hide()
    b.show("Envoy check end")
    b.wait_idle(60)
    shown = b.state()
    b.hide()
    b.wait_idle(60)
    time.sleep(3)
    hidden = not b.state()["shown"]
    res["new"]["api_banner"] = {**crashes(), "installed": b.installed, "shown": shown["shown"], "hidden": hidden}
    res["after"] = version()
    text = json.dumps(res, indent=1)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
