"""AndroidDevice: the Device interface on any Android device over adb + uiautomator2 (design doc, Device layer).

Emulators (`devices/emulator.py`) and real phones (`devices/phone.py`) both build on this: uiautomator2 reads the tree
(31 ms on the emulator, Phase 0) and acts; typing is accessibility set-text, never the clipboard. What differs is how
the screen is seen and touched outside the agent's tree: an emulator has its gRPC API (6 ms frames, taps under 1 ms),
a real phone has scrcpy. Each subclass sets `stream`, an object with `frame(width)`, `tap`, `swipe`, `text` and `key`,
which the live view, approval screenshots and step thumbnails use without knowing which phone it is.

uiautomator2 is synchronous, so every call runs in a worker thread. Calls on one device are serialized by a lock
(Android allows a single automation session anyway).
"""

from __future__ import annotations

import asyncio
import io
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import adbutils
import uiautomator2 as u2
from PIL import Image

from devices.screen import build_state, content_hash, has_app_content, parse_hierarchy
from devices.types import Action, ActionResult, Capabilities, ScreenState, StreamHandle

_FOCUS = re.compile(r"mCurrentFocus=Window\{(\S+) \S+ ([^/\s}]+)/?([^\s}]*)\}")


def _adb_path() -> str:
    home = os.environ.get("ANDROID_HOME", str(Path.home() / "Library/Android/sdk"))
    return str(Path(home) / "platform-tools" / "adb")


def adb(serial: str, *args: str, timeout: float = 30, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run([_adb_path(), "-s", serial, *args], capture_output=True, text=True, timeout=timeout, check=check)


def _stale(e: Exception) -> bool:
    """uiautomator2's node went stale between finding it and using it: Compose rebuilt it (the Pixel 5, typing a known
    traveler number while the keyboard opened). Looking it up again finds the new one."""
    return "StaleObjectException" in str(e)


class AndroidDevice:
    def __init__(self, serial: str, device_id: str | None = None) -> None:
        self.id = device_id or serial
        self.serial = serial
        self._lock = asyncio.Lock()
        self._last: ScreenState | None = None
        self._actions = 0  # actions run on the phone (taps, typing, scrolls): lets tests prove an answer touched nothing
        self.adb: adbutils.AdbDevice
        self.u2: u2.Device
        self.capabilities: Capabilities
        self.model = ""  # "Pixel 8" on a real phone
        self.android = ""  # Android release, e.g. "15"
        self.stream: Any = None  # frames and input for the live view (set by subclasses)
        self._launchers: dict[str, str] = {}  # package → its launcher activity

    # ---- connection -------------------------------------------------------------------------

    def _connect_u2(self) -> dict:
        self.adb = adbutils.adb.device(self.serial)
        self.u2 = u2.connect(self.serial)
        for attempt in range(3):  # the server sometimes restarts when a new client connects (seen in Phase 0)
            try:
                info = self.u2.info  # starts the uiautomator2 server if needed
                self.u2.dump_hierarchy()  # and proves it answers
                return info
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(1.5)
        raise AssertionError("unreachable")

    def prop(self, name: str) -> str:
        return self.adb.shell(f"getprop {name}").strip()

    def connect(self) -> "AndroidDevice":
        info = self._connect_u2()
        density = int(re.search(r"(\d+)", self.adb.shell("wm density")).group(1))  # type: ignore[union-attr]
        qemu = self.prop("ro.kernel.qemu") == "1" or self.prop("ro.boot.qemu") == "1"
        sim = self.prop("gsm.sim.state").upper()  # "READY,ABSENT" on a dual-SIM phone with one card
        self.model = self.prop("ro.product.model")
        self.android = self.prop("ro.build.version.release")
        self.capabilities = Capabilities(
            real_phone=not qemu,
            has_sim=any(s in ("READY", "LOADED") for s in sim.split(",")),
            can_snapshot=False,
            width=info["displayWidth"],
            height=info["displayHeight"],
            density=density,
        )
        return self

    # ---- observe ----------------------------------------------------------------------------

    def _dump(self, attempts: int = 3) -> str:
        """Read the tree; if the automation server stopped, reconnect with backoff (design doc: up to 3 times)."""
        for attempt in range(attempts + 1):
            try:
                return self.u2.dump_hierarchy()
            except Exception:
                if attempt == attempts:
                    raise
                time.sleep(0.5 * 2**attempt)
                self.u2 = u2.connect(self.serial)
        raise AssertionError("unreachable")

    def _foreground(self) -> tuple[str, str, bool]:
        """Focused app, activity, and whether its window is FLAG_SECURE (one dumpsys call, ~25 ms).

        The emulator's gRPC screenshot still captures secure windows (scrcpy and screencap are black),
        so secure screens must be detected from the window flag, not from black frames.
        """
        out = self.adb.shell("dumpsys window | grep -E '^  Window #|mCurrentFocus|^      fl='")
        m = _FOCUS.search(out)
        if not m:
            return "", "", False
        token, pkg, act = m.group(1), m.group(2), m.group(3)
        if act.startswith("."):
            act = pkg + act
        secure = False
        lines = out.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("  Window #") and f"Window{{{token} " in line:
                flags = next((l for l in lines[i + 1 : i + 3] if l.strip().startswith("fl=")), "")
                secure = "SECURE" in flags.split()
                break
        return pkg, act, secure

    def foreground_package(self) -> str:
        return self._foreground()[0]

    def _observe_sync(self, screenshot: bool, settle_ms: float | None = None) -> ScreenState:
        t0 = time.perf_counter()
        xml = self._dump()
        read_ms = (time.perf_counter() - t0) * 1000
        pkg, act, secure = self._foreground()
        state = build_state(
            xml,
            pkg,
            act,
            self.capabilities.width,
            self.capabilities.height,
            settle_ms=settle_ms,
            read_ms=read_ms,
            secure=secure,
        )
        if screenshot and not (secure and self.capabilities.real_phone):  # a phone shows secure screens black anyway
            state.screenshot_png = self._screenshot_sync()
        self._last = state
        return state

    async def observe(self, screenshot: bool = False) -> ScreenState:
        async with self._lock:
            return await asyncio.to_thread(self._observe_sync, screenshot)

    def _settle_sync(self, timeout_s: float, quiet_ms: float = 250, poll_ms: float = 60) -> ScreenState:
        """Poll the tree until nothing visible has changed for `quiet_ms` and app content is present.
        settle_ms = time until the last change."""
        start = time.perf_counter()
        last_hash = None
        last_change = start
        while True:
            xml = self._dump()
            now = time.perf_counter()
            elements = parse_hierarchy(xml, self.capabilities.height)
            h = content_hash(elements)
            if h != last_hash:
                last_hash, last_change = h, now
            elif (now - last_change) * 1000 >= quiet_ms and has_app_content(elements):
                break
            if now - start >= timeout_s:
                break
            time.sleep(poll_ms / 1000)
        return self._observe_sync(False, settle_ms=(last_change - start) * 1000)

    async def wait_until_settled(self, timeout_s: float = 5) -> ScreenState:
        async with self._lock:
            return await asyncio.to_thread(self._settle_sync, timeout_s)

    # ---- act --------------------------------------------------------------------------------

    def keyboard_top(self) -> int | None:
        """Where the on-screen keyboard starts (screen pixels), or None when none is shown. The tree still lists what's under
        it. From the input method window's frame and its content inset (a hardware keyboard leaves only a thin strip)."""
        try:
            if "mInputShown=true" not in self.adb.shell("dumpsys input_method | grep mInputShown"):
                return None
            out = self.adb.shell("dumpsys window InputMethod")
        except Exception:  # noqa: BLE001 - unknown means "don't touch it"
            return None
        frame = re.search(r"\bframe=\[\d+,(\d+)\]\[\d+,(\d+)\]", out)
        inset = re.search(r"mGivenContentInsets=\[\d+,(\d+)\]", out)
        if not frame or not inset:
            return None
        top = int(frame.group(1)) + int(inset.group(1))
        return top if top < int(frame.group(2)) else None

    def _tap(self, x: int, y: int, hold_s: float = 0.0) -> None:
        """uiautomator2 injects the touch (~150 ms). Subclasses use faster paths when they have one."""
        if hold_s:
            self.u2.long_click(x, y, duration=hold_s)
        else:
            self.u2.click(x, y)

    def _swipe(self, x1: int, y1: int, x2: int, y2: int, duration_s: float) -> None:
        self.u2.swipe(x1, y1, x2, y2, duration=duration_s)

    def _focused_field(self, bounds: tuple[int, int, int, int], timeout_s: float = 2.0):
        """The focused node once it is the field at `bounds` (focus moves a moment after the tap)."""
        x1, y1, x2, y2 = bounds
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                node = self.u2(focused=True)
                if node.exists:
                    b = node.info.get("bounds", {})
                    if b.get("left", -1) <= cx <= b.get("right", -1) and b.get("top", -1) <= cy <= b.get("bottom", -1):
                        return node
            except Exception as e:  # noqa: BLE001
                if not _stale(e):
                    raise
            time.sleep(0.1)
        return None

    def _type_into(self, el, text: str) -> None:
        """Accessibility set-text (ACTION_SET_TEXT) into the field: any language and emoji, replacing its text.

        uiautomator2's send_keys pastes through the clipboard, which would leak typed text into the
        clipboard and the keyboard's clipboard history (measured in Phase 0), so it is only a fallback.
        The tap that focuses the field takes effect a moment later, so wait for focus before setting text,
        and read the field back (get_text keeps emoji, which the XML dump garbles).
        """
        node = None if not el.focused else self._focused_field(el.bounds, 0.3)
        if node is None:
            self._tap(*el.center)
            node = self._focused_field(el.bounds)
        if node is None:
            self.u2.send_keys(text, clear=True)
            self.u2.set_clipboard("")
            return
        def norm(v: str) -> str:
            return "".join(v.split()).casefold()

        for _ in range(3):
            try:
                node.set_text(text)
                time.sleep(0.15)
                if norm(node.get_text() or "") == norm(text):
                    return
            except Exception as e:  # noqa: BLE001
                if not _stale(e):
                    raise
                time.sleep(0.15)
                node = self._focused_field(el.bounds) or node
        # Fields may reformat input (upper-casing a code, dropping symbols); the next observation shows the result.

    def _act_sync(self, a: Action) -> ActionResult:
        self._actions += 1
        t0 = time.perf_counter()
        target = None
        try:
            if a.kind in ("tap", "long_press", "type") or (a.kind == "scroll" and a.element is not None):
                if self._last is None:
                    self._observe_sync(False)
                assert self._last is not None
                el = self._last.element(a.element or 0)
                target = el.to_json()
            if a.kind == "tap":
                self._tap(*el.center)
            elif a.kind == "long_press":
                self._tap(*el.center, hold_s=0.8)
            elif a.kind == "type":
                self._type_into(el, a.text or "")
                if a.submit:
                    # A plain Enter key. uiautomator2's send_action() would install and switch to its own IME
                    # (seen in Phase 0), replacing the keyboard the user sees during a takeover.
                    self.u2.press("enter")
            elif a.kind == "scroll":
                x1, y1, x2, y2 = el.bounds if a.element is not None else (0, 0, self.capabilities.width, self.capabilities.height)
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                dx, dy = int((x2 - x1) * 0.3), int((y2 - y1) * 0.3)
                # "scroll down" = reveal content further down = finger moves up.
                start, end = {
                    "down": ((cx, cy + dy), (cx, cy - dy)),
                    "up": ((cx, cy - dy), (cx, cy + dy)),
                    "right": ((cx + dx, cy), (cx - dx, cy)),
                    "left": ((cx - dx, cy), (cx + dx, cy)),
                }[a.direction or "down"]
                self.u2.swipe(*start, *end, duration=0.25)
            elif a.kind == "swipe":
                self._swipe(a.x or 0, a.y or 0, a.x2 or 0, a.y2 or 0, 0.3)
            elif a.kind == "back":
                self.u2.press("back")
            elif a.kind == "home":
                self.u2.press("home")
            elif a.kind == "launch":
                self._launch(a.package or "")
            elif a.kind == "tap_point":
                self._tap(a.x or 0, a.y or 0)
            elif a.kind == "wait":
                time.sleep(a.seconds or 1.0)
            self._last = None  # any action may change the screen
            return ActionResult(ok=True, duration_ms=(time.perf_counter() - t0) * 1000, target=target)
        except Exception as e:  # reported to the runtime, which decides whether to retry
            return ActionResult(ok=False, error=f"{type(e).__name__}: {e}", duration_ms=(time.perf_counter() - t0) * 1000, target=target)

    async def act(self, action: Action) -> ActionResult:
        async with self._lock:
            return await asyncio.to_thread(self._act_sync, action)

    def _launch(self, package: str) -> None:
        """Start the app's launcher activity with `am start`. uiautomator2's app_start without an activity runs
        `monkey … 1`, which took ~11 s on a fresh device and injects one random event (it opened the app drawer in
        Phase 6): never acceptable on someone's real phone."""
        comp = self._launchers.get(package)
        if comp is None:
            out = self.adb.shell(f"cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.LAUNCHER {package}")
            last = out.strip().splitlines()[-1].strip() if out.strip() else ""
            comp = last if "/" in last else ""
            if comp:
                self._launchers[package] = comp
        if not comp:
            raise RuntimeError(f"{package} has no launcher activity (is it installed?)")
        self.adb.shell(["am", "start", "-n", comp])  # an argument list: a launcher like ".Shell$HomeActivity" must not meet the shell

    async def launch(self, package: str, fresh: bool = False) -> None:
        """Bring an app to the front; `fresh` force-stops it first (a routine's start on real apps)."""
        if fresh:
            async with self._lock:
                await asyncio.to_thread(self.u2.app_stop, package)
                self._last = None
        result = await self.act(Action(kind="launch", package=package))
        if not result.ok:
            raise RuntimeError(result.error)

    def _read_field_sync(self, el) -> str | None:
        """A field's text through the accessibility object API (get_text keeps emoji; the XML dump shows '..')."""
        if self._last is None:
            return None
        same = [e for e in self._last.elements if e.cls == el.cls]
        try:
            k = next(i for i, e in enumerate(same) if e.index == el.index)
        except StopIteration:
            return None
        node = self.u2(className=el.cls, instance=k)
        if not node.exists:
            return None
        b = node.info.get("bounds", {})
        cx, cy = el.center
        if not (b.get("left", -1) <= cx <= b.get("right", -1) and b.get("top", -1) <= cy <= b.get("bottom", -1)):
            return None
        return node.get_text()

    async def read_field(self, el) -> str | None:
        async with self._lock:
            return await asyncio.to_thread(self._read_field_sync, el)

    # ---- snapshots (emulators only) ---------------------------------------------------------

    async def snapshot_save(self, name: str) -> None:
        raise PermissionError(f"{self.id} has no snapshots")

    async def snapshot_load(self, name: str) -> None:
        raise PermissionError(f"{self.id} has no snapshots")

    # ---- screenshots ------------------------------------------------------------------------

    def screencap_png(self) -> bytes:
        """Screenshot via `adb exec-out screencap -p` (0.5 to 2.6 s on phones, 142 ms on the emulator)."""
        out = subprocess.run(
            [_adb_path(), "-s", self.serial, "exec-out", "screencap", "-p"], capture_output=True, timeout=30
        )
        if out.returncode != 0 or not out.stdout.startswith(b"\x89PNG"):
            raise RuntimeError(f"screencap failed: {out.stderr.decode(errors='replace')}")
        return out.stdout

    def _screenshot_sync(self) -> bytes:
        return self.screencap_png()

    async def screenshot(self) -> bytes:
        return await asyncio.to_thread(self._screenshot_sync)

    def screenshot_image(self) -> Image.Image:
        return Image.open(io.BytesIO(self._screenshot_sync())).convert("RGB")

    def frame(self, width: int, timeout: float = 5) -> Image.Image:
        """A frame `width` pixels wide, for thumbnails and approval cards."""
        img = self.stream.frame(width, timeout=timeout)
        return img if img.width <= width else img.resize((width, round(img.height * width / img.width)))

    def video_stream(self) -> StreamHandle:
        raise NotImplementedError("the live view streams through `stream` (api/live.py)")
