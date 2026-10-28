"""AndroidWorld's environment on Envoy's AndroidWorld emulator (runs in AndroidWorld's own Python 3.11 venv).

AndroidWorld connects to an existing emulator through android_env: adb on the console port and the emulator's gRPC API
for screenshots. Its defaults (console 5554, gRPC 8554) belong to Envoy's envoy-test, so everything here uses
console 5560 and gRPC 8560 (eval/androidworld/emulator.sh).

The emulator runs with -grpc-use-token, which binds gRPC to 127.0.0.1 and requires the per-launch token as
"authorization: Bearer <token>" metadata. android_env opens its channel with grpc.secure_channel(local credentials)
and no token, so `connect()` wraps that one channel with an interceptor that adds the token. Nothing in AndroidWorld or
android_env is modified; the plain, unauthenticated gRPC port is never opened.
"""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

import grpc

CONSOLE_PORT = 5560
GRPC_PORT = 8560
SERIAL = f"emulator-{CONSOLE_PORT}"
ADB = str(Path(os.environ.get("ANDROID_HOME", Path.home() / "Library/Android/sdk")) / "platform-tools" / "adb")
AW_DIR = Path(__file__).resolve().parents[2] / "third_party" / "android_world"


def grpc_token(port: int = GRPC_PORT) -> str:
    """The running emulator's gRPC token, from its discovery file (same lookup as backend/devices/emulator_grpc.py)."""
    base = (Path.home() / "Library/Caches/TemporaryItems/avd/running" if platform.system() == "Darwin"
            else Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "avd/running")
    for f in base.glob("pid_*.ini"):
        kv = dict(line.split("=", 1) for line in f.read_text().splitlines() if "=" in line)
        if kv.get("grpc.port") == str(port):
            return kv.get("grpc.token", "").strip()
    raise RuntimeError(f"no running emulator with gRPC port {port} (start it with eval/androidworld/emulator.sh start)")


class _Token(grpc.UnaryUnaryClientInterceptor, grpc.UnaryStreamClientInterceptor,
             grpc.StreamUnaryClientInterceptor, grpc.StreamStreamClientInterceptor):
    def __init__(self, token: str) -> None:
        self._md = ("authorization", f"Bearer {token}")

    def _details(self, d):
        md = list(d.metadata or []) + [self._md]
        return d._replace(metadata=md) if hasattr(d, "_replace") else _Details(d, md)

    def intercept_unary_unary(self, cont, d, req):
        return cont(self._details(d), req)

    def intercept_unary_stream(self, cont, d, req):
        return cont(self._details(d), req)

    def intercept_stream_unary(self, cont, d, it):
        return cont(self._details(d), it)

    def intercept_stream_stream(self, cont, d, it):
        return cont(self._details(d), it)


class _Details(grpc.ClientCallDetails):
    def __init__(self, d, metadata) -> None:
        self.method, self.timeout, self.credentials = d.method, d.timeout, d.credentials
        self.wait_for_ready, self.compression = getattr(d, "wait_for_ready", None), getattr(d, "compression", None)
        self.metadata = metadata


def _install_token(port: int) -> None:
    token = grpc_token(port)
    if not token:
        return
    original = grpc.secure_channel
    if getattr(original, "_envoy_token", False):
        return

    def secure_channel(target, credentials, options=None, compression=None):
        ch = original(target, credentials, options=options, compression=compression)
        if target.endswith(f":{port}"):
            return grpc.intercept_channel(ch, _Token(token))
        return ch

    secure_channel._envoy_token = True  # type: ignore[attr-defined]
    grpc.secure_channel = secure_channel


def connect(emulator_setup: bool = False, freeze_datetime: bool = True):
    """AndroidWorld's AsyncEnv on our emulator: env_launcher.load_and_setup_env with our ports and the gRPC token."""
    _install_token(GRPC_PORT)
    from android_world.env import env_launcher

    return env_launcher.load_and_setup_env(console_port=CONSOLE_PORT, emulator_setup=emulator_setup,
                                           freeze_datetime=freeze_datetime, adb_path=ADB, grpc_port=GRPC_PORT)


def aw_commit() -> str:
    return subprocess.run(["git", "-C", str(AW_DIR), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


# ---- AndroidWorld's accessibility forwarder vs Envoy's uiautomator2 ---------------------------------------------------
# uiautomator2 runs a UiAutomation session, which suppresses (unbinds) accessibility services. AndroidWorld's forwarder
# then crashes on its own polling thread (NullPointerException in AccessibilityService.getWindows) and Android shows a
# "keeps stopping" dialog over the app, a harness artifact official agents never see (they don't start UiAutomation).
# So while Envoy works, the forwarder is parked (disabled and stopped), and before AndroidWorld scores it is restored
# with android_env's own setup calls (enable the service, send it the host gRPC port, turn on tree logs).

FORWARDER = "com.google.androidenv.accessibilityforwarder"


def adb_shell(*args: str, timeout: float = 30) -> str:
    out = subprocess.run([ADB, "-s", SERIAL, "shell", *args], capture_output=True, text=True, timeout=timeout)
    return out.stdout.strip()


def crash_dialog() -> str:
    """The focused window when it is a crash / not-responding dialog, else ""."""
    focus = adb_shell("dumpsys window | grep mCurrentFocus")
    return focus if ("Application Error" in focus or "Not Responding" in focus) else ""


def park_forwarder() -> None:
    adb_shell("settings", "put", "secure", "enabled_accessibility_services", "null")
    adb_shell("am", "force-stop", FORWARDER)


def _send_grpc_port(wrapper) -> None:
    """The one part of android_env's `_configure_grpc` the forwarder needs after a restart: the host server's port.
    `_configure_grpc` itself also calls `attempt_enable_networking()` (airplane mode off, `svc wifi enable`), which would
    undo an agent's work on Wi-Fi tasks: the pilot's SystemWifiTurnOff was scored with Wi-Fi switched back on."""
    from android_env.proto import adb_pb2

    wrapper.execute_adb_call(adb_pb2.AdbRequest(send_broadcast=adb_pb2.AdbRequest.SendBroadcast(
        action=f'accessibility_forwarder.intent.action.SET_GRPC --ei "port" {wrapper.get_port()}',
        component=f"{FORWARDER}/{FORWARDER}.FlagsBroadcastReceiver")))


def restore_forwarder(env, timeout_s: float = 30) -> float:
    """Re-enable the forwarder and give it the host port and tree logging, with no other change to the phone, then wait
    until AndroidWorld reads a real screen: the forwarder's first tree after a restart is empty (measured: 0 elements,
    then 18 a few seconds later), and AndroidWorld's screen-based checks would score that empty screen.
    Returns seconds until two successive reads are non-empty; raises if that doesn't happen in time."""
    import time

    from android_world.env import android_world_controller, representation_utils

    def read() -> list:
        forest = android_world_controller.get_a11y_tree(wrapper, max_retries=1, sleep_duration=0.5)
        return representation_utils.forest_to_ui_elements(forest, exclude_invisible_elements=True)

    t0 = time.time()
    last = "no tree yet"
    wrapper = env.controller.env  # android_env's A11yGrpcWrapper
    wrapper._start_a11y_services()  # noqa: SLF001 - android_env's own setup steps, unchanged
    for attempt in range(2):
        time.sleep(1.0)
        _send_grpc_port(wrapper)
        wrapper._enable_a11y_tree_logs()  # noqa: SLF001
        deadline = time.time() + timeout_s / 2
        prev = None
        while time.time() < deadline:
            try:  # AndroidWorld's own tree read, without the controller's fallback (refresh_env re-enables networking)
                els = read()
                if els and prev:  # two non-empty reads in a row (a running stopwatch never reads the same twice)
                    return time.time() - t0
                prev = els or None
                last = f"{len(els)} elements"
            except Exception as e:  # noqa: BLE001 - not ready yet
                last = f"{type(e).__name__}: {e}"
            time.sleep(0.5)
    raise RuntimeError(f"AndroidWorld's accessibility forwarder did not come back in {timeout_s:.0f} s ({last})")


# ---- AndroidWorld's app snapshots don't survive a reboot -------------------------------------------------------------
# AndroidWorld saves each app's post-setup data under /data/data/android_world/snapshots and restores it before and
# after every task. On API 33, Android's boot-time reconcileAppsData deletes that directory (no package owns it):
# measured Oct 28 with a marker file. Without it AndroidWorld only warns "Skipping app snapshot loading" and apps carry
# state from task to task. So after every boot, AndroidWorld's setup runs again (it clears each app and re-saves its
# snapshot), followed by the two onboarding steps its setup misses on this image.

SNAPSHOTS = "/data/data/android_world/snapshots"
EXPECTED_SNAPSHOTS = 20  # AndroidWorld saved 24 app snapshots in its setup on this image (Oct 28); 0 after any reboot


def snapshot_count() -> int:
    out = adb_shell(f"ls {SNAPSHOTS} 2>/dev/null")
    return len([l for l in out.split() if "." in l])


def finish_setup(env) -> None:
    """The two steps AndroidWorld's setup misses here (see aw_fix_setup.py), then their snapshots are re-saved."""
    import time

    from android_world.env import adb_utils, tools
    from android_world.utils import app_snapshot

    adb_utils.launch_app("contacts", env.controller)
    time.sleep(3)
    try:  # Android 13 says "Don’t allow" (U+2019); AndroidWorld's setup looks for "Don't allow"
        tools.AndroidToolController(env=env.controller).click_element("Don’t allow")
        time.sleep(1.5)
    except ValueError:
        pass  # no prompt: nothing to dismiss
    adb_utils.close_app("contacts", env.controller)
    adb_utils.launch_app("activity tracker", env.controller)
    time.sleep(3)
    adb_utils.close_app("activity tracker", env.controller)
    for app in ("contacts", "open tracks sports tracker"):
        app_snapshot.save_snapshot(app, env.controller)
    adb_utils.press_home_button(env.controller)


def ensure_setup(env, log=print) -> bool:
    """Run AndroidWorld's setup again if its snapshots are missing (after a reboot). Returns True if it ran."""
    n = snapshot_count()
    if n >= EXPECTED_SNAPSHOTS:
        return False
    from android_world.env import env_launcher

    log(f"AndroidWorld's app snapshots are missing ({n} found): running its setup again")
    env_launcher.setup_env(env, emulator_setup=True, freeze_datetime=True)
    finish_setup(env)
    n = snapshot_count()
    if n < EXPECTED_SNAPSHOTS:
        raise RuntimeError(f"AndroidWorld setup left {n} app snapshots (expected {EXPECTED_SNAPSHOTS})")
    log(f"AndroidWorld setup done: {n} app snapshots")
    return True
