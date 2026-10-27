"""SkyLark Air, Envoy's test airline app (testapps/skylark), driven through its debug hooks.

Every eval run starts from a known state: `reset()` (bundled fixtures) or `seed()` (custom fixtures),
a layout `variant` (0 original, 1 moved button, 2 renamed labels, 3 extra confirmation screen),
then a cold launch. `state()` reads the whole app state, so success checks are exact.
"""

from __future__ import annotations

import base64
import copy
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from devices.emulator import _adb_path

PACKAGE = "com.skylark.air"
REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / "testapps" / "skylark"
APK = PROJECT / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
FIXTURES = PROJECT / "app" / "src" / "main" / "assets" / "fixtures.json"
RECEIVER = f"{PACKAGE}/.DebugReceiver"
STATE_URI = "content://com.skylark.air.debug/state"

VARIANTS = {0: "original", 1: "moved button", 2: "renamed labels", 3: "extra confirmation screen"}


def default_fixtures() -> dict[str, Any]:
    return json.loads(FIXTURES.read_text())


class SkyLark:
    def __init__(self, serial: str) -> None:
        self.serial = serial

    def _adb(self, *args: str, timeout: float = 60) -> str:
        out = subprocess.run([_adb_path(), "-s", self.serial, *args], capture_output=True, text=True, timeout=timeout)
        if out.returncode != 0:
            raise RuntimeError(f"adb {' '.join(args[:3])}… failed: {out.stderr.strip() or out.stdout.strip()}")
        return out.stdout

    def _broadcast(self, action: str, *extras: str) -> None:
        out = self._adb("shell", "am", "broadcast", "-n", RECEIVER, "-a", f"{PACKAGE}.{action}", *extras)
        if 'result=0' not in out:
            raise RuntimeError(f"SkyLark {action} failed: {out.strip()}")

    # ---- install and state -----------------------------------------------------------------

    def installed(self) -> bool:
        return f"package:{PACKAGE}" in self._adb("shell", "pm", "list", "packages", PACKAGE).split()

    def install(self, build: bool = False) -> None:
        if build or not APK.exists():
            subprocess.run(["./gradlew", ":app:assembleDebug", "-q"], cwd=PROJECT, check=True, timeout=900)
        self._adb("install", "-r", str(APK), timeout=180)

    def reset(self) -> None:
        self._broadcast("RESET")

    def seed(self, fixtures: dict[str, Any]) -> None:
        b64 = base64.b64encode(json.dumps(fixtures).encode()).decode()
        self._broadcast("SEED", "--es", "json_b64", b64)

    def set_variant(self, variant: int) -> None:
        self._broadcast("VARIANT", "--ei", "variant", str(variant))

    def set_gate(self, code: str, gate: str) -> None:
        self._broadcast("SET_GATE", "--es", "code", code, "--es", "gate", gate)

    def sign_out(self) -> None:
        self._broadcast("SIGN_OUT")

    def state(self) -> dict[str, Any]:
        return json.loads(self._adb("shell", "content", "read", "--uri", STATE_URI))

    def trip(self, code: str) -> dict[str, Any]:
        return next(t for t in self.state()["trips"] if t["code"] == code)

    # ---- app lifecycle ---------------------------------------------------------------------

    def stop(self) -> None:
        self._adb("shell", "am", "force-stop", PACKAGE)

    def launch(self) -> None:
        self._adb("shell", "am", "start", "-W", "-n", f"{PACKAGE}/.MainActivity")

    def prepare(self, fixtures: dict[str, Any] | None = None, variant: int = 0) -> None:
        """Known starting point for a task: app stopped, state seeded, variant set, cold launch on Home."""
        self.stop()
        if fixtures is None:
            self.reset()
        else:
            self.seed(fixtures)
        self.set_variant(variant)
        self.stop()  # the broadcasts start the app process; restart it so the UI begins fresh
        self.launch()
        time.sleep(0.5)


def fixtures_with(**changes: Any) -> dict[str, Any]:
    """Default fixtures with top-level keys replaced, e.g. fixtures_with(signed_in=False)."""
    f = copy.deepcopy(default_fixtures())
    f.update(changes)
    return f
