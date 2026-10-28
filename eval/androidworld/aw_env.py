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
