"""PhoneDevice: the Device interface on a real Android phone (design doc, Device layer › Backend 2: a real Android phone).

Same uiautomator2 + adb core as emulators (`devices/android.py`), with what a real phone lacks and needs:
- **No gRPC.** Frames and input come from a scrcpy session (`devices/scrcpy.py`); the agent's screenshots are the
  latest decoded frame (milliseconds) instead of `adb screencap` (0.5 to 2.6 s). Taps are injected through scrcpy's
  control socket (uiautomator2 as the fallback).
- **The banner** (`android/banner`, `ai.envoy.banner`): a pill at the top of the screen while Envoy works, with a
  Pause button whose state the Mac reads over adb.
- **Physical touches.** `getevent` streams the phone's own input devices. Everything Envoy does (uiautomator2,
  scrcpy) is injected and never appears there, so any touch or key it reports is you: the run pauses.
- **Secure screens are black** in scrcpy and screencap on a real phone: no screenshot is taken of them at all.

`discover()` lists connected phones (not emulators). `ENVOY_TEST_PHONE=<serial>` treats an emulator as a phone, so this
code path is exercised before a real phone is connected.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from devices.android import AndroidDevice, _adb_path, adb
from devices.scrcpy import ScrcpyStream
from devices.screen import BANNER_PACKAGE

REPO = Path(__file__).resolve().parents[2]
TAP_LOG = REPO / "logs" / "phone_taps.jsonl"  # where every tap on a real phone went (no screen content: points only)
BANNER_APK = REPO / "android" / "banner" / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
_ROW = re.compile(r"paused=(\d), reason=(.*?), changed_at=(\d+), shown=(\d)")


def phone_id(serialno: str) -> str:
    return "phone-" + re.sub(r"[^A-Za-z0-9]+", "-", serialno).strip("-")


def discover() -> list[dict[str, Any]]:
    """Connected phones: {id, serial, model, android, state}. Unauthorized phones are listed so the user can be told
    to allow USB debugging; emulators are left out unless named in ENVOY_TEST_PHONE."""
    try:
        out = subprocess.run([_adb_path(), "devices", "-l"], capture_output=True, text=True, timeout=10).stdout
    except Exception:  # noqa: BLE001 - no adb: no phones
        return []
    test = {s.strip() for s in os.environ.get("ENVOY_TEST_PHONE", "").split(",") if s.strip()}
    phones = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        if serial.startswith("emulator-") and serial not in test:
            continue
        info = dict(p.split(":", 1) for p in parts[2:] if ":" in p)
        model = info.get("model", "").replace("_", " ")
        serialno, android = serial, ""
        if state == "device":
            try:
                serialno = adb(serial, "shell", "getprop", "ro.serialno", timeout=5).stdout.strip() or serial
                android = adb(serial, "shell", "getprop", "ro.build.version.release", timeout=5).stdout.strip()
            except Exception:  # noqa: BLE001
                pass
        phones.append({"id": phone_id(serialno), "serial": serial, "model": model or "Android phone", "android": android, "state": state})
    return phones


class TouchWatcher:
    """Physical input on the phone, from `adb shell getevent -l`: a finger down on the touchscreen, or a key pressed."""

    def __init__(self, serial: str) -> None:
        self.serial = serial
        self.last_touch = 0.0
        self.count = 0
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._proc = subprocess.Popen([_adb_path(), "-s", self.serial, "shell", "getevent", "-l"],
                                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        self._thread = threading.Thread(target=self._read, name=f"getevent-{self.serial}", daemon=True)
        self._thread.start()

    def _read(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        for line in self._proc.stdout:
            if is_physical_input(line):
                self.last_touch = time.time()
                self.count += 1

    def stop(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
        self._proc = None

    def touched_since(self, t: float) -> bool:
        return self.last_touch > t


def is_physical_input(line: str) -> bool:
    """A finger going down (a new tracking id, or BTN_TOUCH DOWN) or a key pressed down (EV_KEY … DOWN)."""
    parts = line.split()
    if len(parts) < 4:
        return False
    kind, code, value = parts[-3], parts[-2], parts[-1]
    if code == "ABS_MT_TRACKING_ID":
        return value.lower() != "ffffffff"
    return kind == "EV_KEY" and value == "DOWN"


class Banner:
    """The pill on the phone's screen while Envoy works on it (android/banner)."""

    def __init__(self, serial: str) -> None:
        self.serial = serial
        self.ready = False
        self.visible = False  # shown by Envoy and not hidden since
        self.text = "Envoy is using this phone"

    def _svc(self, action: str, *extra: str) -> None:
        adb(self.serial, "shell", "am", "start-foreground-service", "-n", f"{BANNER_PACKAGE}/.BannerService",
            "-a", f"{BANNER_PACKAGE}.{action}", *extra, timeout=15)

    def install(self) -> bool:
        """Install the banner if it isn't (or is older), and allow its overlay. False if the APK hasn't been built."""
        if self.ready:
            return True
        listed = adb(self.serial, "shell", "pm", "list", "packages", BANNER_PACKAGE, timeout=10).stdout
        if f"package:{BANNER_PACKAGE}" not in listed:
            if not BANNER_APK.exists():
                return False
            adb(self.serial, "install", "-r", "-g", str(BANNER_APK), timeout=120, check=True)
        adb(self.serial, "shell", "appops", "set", BANNER_PACKAGE, "SYSTEM_ALERT_WINDOW", "allow", timeout=10)
        self.ready = True
        return True

    def show(self, text: str) -> None:
        if self.install():
            self.text, self.visible = text, True
            self._svc("SHOW", "--es", "text", _shell_quote(text[:60]))

    def pause(self, reason: str) -> None:
        if self.ready:
            self._svc("PAUSE", "--es", "reason", _shell_quote(reason[:80]))

    def resume(self) -> None:
        if self.ready:
            self._svc("RESUME")

    def hide(self) -> None:
        if self.ready:
            self.visible = False
            self._svc("HIDE")

    def state(self) -> dict[str, Any]:
        """{paused, reason, changed_at (s), shown}; paused False if the banner can't be read."""
        if not self.ready:
            return {"paused": False, "reason": "", "changed_at": 0.0, "shown": False}
        out = adb(self.serial, "shell", "content", "query", "--uri", f"content://{BANNER_PACKAGE}/state", timeout=10).stdout
        m = _ROW.search(out)
        if not m:
            return {"paused": False, "reason": "", "changed_at": 0.0, "shown": False}
        return {"paused": m.group(1) == "1", "reason": m.group(2), "changed_at": int(m.group(3)) / 1000, "shown": m.group(4) == "1"}


def _shell_quote(text: str) -> str:
    """`adb shell` joins its arguments into one remote command line: quote the text for the phone's shell."""
    return "'" + text.replace("'", "'\\''") + "'"


class PhoneDevice(AndroidDevice):
    def __init__(self, serial: str, device_id: str | None = None) -> None:
        super().__init__(serial, device_id=device_id)
        self._stream: ScrcpyStream | None = None
        self.banner = Banner(serial)
        self.touches = TouchWatcher(serial)

    def connect(self) -> "PhoneDevice":
        super().connect()
        self.touches.start()
        return self

    @property
    def stream(self) -> ScrcpyStream:  # type: ignore[override]
        """The scrcpy session, started on first use and restarted if it stopped."""
        if self._stream is None:
            self._stream = ScrcpyStream(self.serial, (self.capabilities.width, self.capabilities.height))
        if not self._stream.running:
            self._stream.start()
        return self._stream

    @stream.setter
    def stream(self, value: Any) -> None:  # AndroidDevice.__init__ assigns None
        pass

    def close(self) -> None:
        if self._stream is not None:
            self._stream.stop()
        self.touches.stop()

    # ---- act --------------------------------------------------------------------------------

    def _tap(self, x: int, y: int, hold_s: float = 0.0) -> None:
        """A tap under the banner would land on the banner, not the app: it is a window of its own above the app, and on
        its Pause button an injected tap paused the run as if you had pressed it (Pixel 5, where the pill sits over the
        app's top bar, the search box of many apps). The banner steps aside for that tap and comes back."""
        rect = self._banner_rect()
        stepped = rect is not None and rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]
        if stepped:
            self.banner.hide()
            time.sleep(0.15)
        try:
            path = self._tap_now(x, y, hold_s)
        finally:
            if stepped:
                self.banner.show(self.banner.text)
        self._log_tap(x, y, hold_s, path, stepped)

    def _log_tap(self, x: int, y: int, hold_s: float, path: str, stepped: bool) -> None:
        """One line per tap: the point, the input path, and how long the stream had been up (an approved tap on the Pixel 5
        once didn't take effect after a takeover; this says which path it went through)."""
        try:
            st = self._stream
            row = {"time": round(time.time(), 3), "serial": self.serial, "x": x, "y": y, "hold_s": hold_s, "path": path, "banner_stepped": stepped,
                   "stream_age_s": round(time.time() - st.started_at, 2) if st is not None and st.started_at else None,
                   "frames": getattr(st, "frames", None)}
            TAP_LOG.parent.mkdir(parents=True, exist_ok=True)
            with TAP_LOG.open("a") as f:
                f.write(json.dumps(row) + "\n")
        except Exception:  # noqa: BLE001 - a log line never stops a tap
            pass

    def _banner_rect(self, pad: int = 12) -> tuple[int, int, int, int] | None:
        """The banner's pill on the screen read last (its own window, left out of what Envoy reads), padded a little."""
        if not self.banner.visible or self._last is None:
            return None
        pills = [e.bounds for e in self._last.elements if e.package == BANNER_PACKAGE and e.bounds[2] > e.bounds[0]]
        if not pills:
            return None
        x1, y1, x2, y2 = max(pills, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
        return x1 - pad, y1 - pad, x2 + pad, y2 + pad

    def _tap_now(self, x: int, y: int, hold_s: float = 0.0) -> str:
        """scrcpy's control socket (milliseconds), uiautomator2 (~150 ms) as the fallback; both are injected, so the
        touch watcher never mistakes them for you."""
        try:
            if hold_s:
                self.stream.swipe(x, y, x, y, hold_s, steps=4)
            else:
                self.stream.tap(x, y)
            return "scrcpy"
        except Exception as e:  # noqa: BLE001
            super()._tap(x, y, hold_s)
            return f"uiautomator2 ({type(e).__name__})"

    # ---- screenshots ------------------------------------------------------------------------

    def _screenshot_sync(self) -> bytes:
        try:
            return self.stream.png()
        except Exception:  # noqa: BLE001
            return self.screencap_png()
