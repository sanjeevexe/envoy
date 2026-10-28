"""EmulatorDevice: the Device interface on an Android emulator, via uiautomator2 + adbutils + emulator gRPC.

Everything uiautomator2 and adb do is shared with real phones (`devices/android.py`). On top, the emulator's own gRPC
API takes screenshots (6 ms) and taps (under 1 ms, against ~150 ms through uiautomator2), sees secure screens that
scrcpy and screencap show black, and only emulators save and load snapshots.
"""

from __future__ import annotations

import asyncio
import subprocess
import time

import adbutils
import uiautomator2 as u2
from PIL import Image

from devices.android import AndroidDevice, _adb_path  # noqa: F401 - _adb_path is imported from here by older scripts
from devices.emulator_grpc import EmulatorGrpc
from devices.types import Capabilities

# Must match scripts/start_emulator.sh
AVDS = {
    "envoy-test": {"serial": "emulator-5554", "grpc_port": 8554, "can_snapshot": True},
    "envoy-real": {"serial": "emulator-5556", "grpc_port": 8556, "can_snapshot": False},
    "envoy-small": {"serial": "emulator-5558", "grpc_port": 8558, "can_snapshot": True},  # Phase 6: a smaller screen
}


class EmulatorDevice(AndroidDevice):
    def __init__(self, avd: str) -> None:
        cfg = AVDS[avd]
        super().__init__(cfg["serial"], device_id=avd)
        self.avd = avd
        self.grpc_port: int = cfg["grpc_port"]
        self._can_snapshot: bool = cfg["can_snapshot"]
        self._forwards: list[tuple[str, str]] = []  # (local, remote) adb forwards to restore after a snapshot load
        self.grpc = EmulatorGrpc(self.grpc_port)
        self.stream = self.grpc

    def connect(self) -> "EmulatorDevice":
        super().connect()
        c = self.capabilities
        self.capabilities = Capabilities(real_phone=False, has_sim=False, can_snapshot=self._can_snapshot,
                                         width=c.width, height=c.height, density=c.density)
        self.grpc.connect()
        return self

    def add_forward(self, local: str, remote: str) -> None:
        self.adb.forward(local, remote)
        self._forwards.append((local, remote))

    def _reconnect(self, timeout_s: float = 60) -> None:
        """After a snapshot load: wait for adb, restore forwards, restart the uiautomator2 session, reopen gRPC."""
        deadline = time.time() + timeout_s
        subprocess.run([_adb_path(), "-s", self.serial, "wait-for-device"], timeout=timeout_s, check=True)
        self.adb = adbutils.adb.device(self.serial)
        while self.adb.shell("getprop sys.boot_completed").strip() != "1":
            if time.time() > deadline:
                raise TimeoutError("device did not come back after snapshot load")
            time.sleep(0.2)
        for local, remote in self._forwards:
            self.adb.forward(local, remote)
        last_error: Exception | None = None
        while time.time() < deadline:
            try:
                self.u2 = u2.connect(self.serial)
                self.u2.dump_hierarchy()  # proves the automation server answers
                break
            except Exception as e:  # server restarting; retry
                last_error = e
                time.sleep(0.3)
        else:
            raise TimeoutError(f"uiautomator2 did not recover: {last_error}")
        self.grpc.close()
        self.grpc.connect()
        self._last = None

    # ---- act --------------------------------------------------------------------------------

    def _tap(self, x: int, y: int, hold_s: float = 0.0) -> None:
        """Emulator gRPC touch (~1 ms) with uiautomator2 (~150 ms) as the fallback."""
        try:
            if hold_s:
                self.grpc.touch(x, y, pressure=1)
                time.sleep(hold_s)
                self.grpc.touch(x, y, pressure=0)
            else:
                self.grpc.tap(x, y)
        except Exception:
            super()._tap(x, y, hold_s)

    # ---- snapshots (envoy-test and envoy-small only) ----------------------------------------

    def _emu(self, *args: str, timeout: float = 120) -> str:
        out = subprocess.run(
            [_adb_path(), "-s", self.serial, "emu", *args], capture_output=True, text=True, timeout=timeout
        )
        text = (out.stdout + out.stderr).strip()
        if out.returncode != 0 or "KO" in text.split():
            raise RuntimeError(f"adb emu {' '.join(args)} failed: {text}")
        return text

    def _check_snapshots_allowed(self) -> None:
        if not self.capabilities.can_snapshot:
            raise PermissionError(f"{self.avd} is long-lived; snapshots are never restored on it")

    async def snapshot_save(self, name: str) -> None:
        self._check_snapshots_allowed()
        async with self._lock:
            await asyncio.to_thread(self._emu, "avd", "snapshot", "save", name)

    async def snapshot_load(self, name: str) -> None:
        self._check_snapshots_allowed()
        async with self._lock:
            await asyncio.to_thread(self._emu, "avd", "snapshot", "load", name)
            await asyncio.to_thread(self._reconnect)

    # ---- screenshots ------------------------------------------------------------------------

    def _screenshot_sync(self) -> bytes:
        try:
            return self.grpc.png()
        except Exception:
            return self.screencap_png()

    def screenshot_image(self) -> Image.Image:
        try:
            return self.grpc.image()
        except Exception:
            return super().screenshot_image()
