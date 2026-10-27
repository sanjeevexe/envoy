"""Emulator screenshots and touch over the emulator's gRPC API (enabled with -grpc <port> -grpc-use-token).

The token is per launch and is read from the emulator's discovery file
(~/Library/Caches/TemporaryItems/avd/running/pid_<pid>.ini on macOS, key grpc.token).
Raw RGB888 frames are ~10x faster to fetch than PNG; PNG is encoded here only when asked.
"""

from __future__ import annotations

import io
import os
import platform
from pathlib import Path

import grpc
from PIL import Image

from devices.grpc_gen import emulator_controller_pb2 as pb
from devices.grpc_gen import emulator_controller_pb2_grpc as pb_grpc


def discovery_dir() -> Path:
    if platform.system() == "Darwin":
        return Path.home() / "Library/Caches/TemporaryItems/avd/running"
    return Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "avd/running"


def read_discovery(grpc_port: int) -> dict[str, str]:
    """Key-value pairs of the running emulator that serves gRPC on `grpc_port`."""
    for f in discovery_dir().glob("pid_*.ini"):
        kv = dict(line.split("=", 1) for line in f.read_text().splitlines() if "=" in line)
        if kv.get("grpc.port") == str(grpc_port):
            return kv
    raise RuntimeError(f"no running emulator with gRPC port {grpc_port}")


class EmulatorGrpc:
    def __init__(self, grpc_port: int, host: str = "127.0.0.1") -> None:
        self.grpc_port = grpc_port
        self.host = host
        self._channel: grpc.Channel | None = None
        self._stub: pb_grpc.EmulatorControllerStub | None = None
        self._metadata: list[tuple[str, str]] = []

    def connect(self) -> None:
        token = read_discovery(self.grpc_port).get("grpc.token", "").strip()
        self._metadata = [("authorization", f"Bearer {token}")] if token else []
        self._channel = grpc.insecure_channel(
            f"{self.host}:{self.grpc_port}", options=[("grpc.max_receive_message_length", 64 * 1024 * 1024)]
        )
        self._stub = pb_grpc.EmulatorControllerStub(self._channel)

    def close(self) -> None:
        if self._channel is not None:
            self._channel.close()
        self._channel = self._stub = None

    def _call(self, fmt: int, timeout: float) -> pb.Image:
        if self._stub is None:
            self.connect()
        assert self._stub is not None
        return self._stub.getScreenshot(pb.ImageFormat(format=fmt), timeout=timeout, metadata=self._metadata)

    def touch(self, x: int, y: int, pressure: int, timeout: float = 5) -> None:
        """One touch event on the virtual touchscreen: pressure 1 = finger down, 0 = finger up."""
        if self._stub is None:
            self.connect()
        assert self._stub is not None
        event = pb.TouchEvent(touches=[pb.Touch(x=x, y=y, identifier=0, pressure=pressure)])
        self._stub.sendTouch(event, timeout=timeout, metadata=self._metadata)

    def tap(self, x: int, y: int, timeout: float = 5) -> None:
        """Tap via the emulator's virtual touchscreen: press, then release (emulators only)."""
        self.touch(x, y, 1, timeout)
        self.touch(x, y, 0, timeout)

    def frame(self, width: int, timeout: float = 5) -> Image.Image:
        """A frame scaled by the emulator to `width` pixels wide (the live view: less to copy and encode)."""
        if self._stub is None:
            self.connect()
        assert self._stub is not None
        img = self._stub.getScreenshot(pb.ImageFormat(format=pb.ImageFormat.RGB888, width=width), timeout=timeout, metadata=self._metadata)
        return Image.frombytes("RGB", (img.format.width, img.format.height), img.image)

    def key(self, key: str, timeout: float = 5) -> None:
        """Press one named key ("Backspace", "Enter", "Tab", "GoBack", "GoHome", "AppSwitch")."""
        if self._stub is None:
            self.connect()
        assert self._stub is not None
        self._stub.sendKey(pb.KeyboardEvent(eventType=pb.KeyboardEvent.keypress, key=key), timeout=timeout, metadata=self._metadata)

    def text(self, text: str, timeout: float = 5) -> None:
        """Type text into the focused field, as a keyboard would."""
        if self._stub is None:
            self.connect()
        assert self._stub is not None
        self._stub.sendKey(pb.KeyboardEvent(text=text), timeout=timeout, metadata=self._metadata)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_s: float = 0.3, steps: int = 12) -> None:
        """A finger drag from (x1, y1) to (x2, y2)."""
        import time as _time
        self.touch(x1, y1, 1)
        for i in range(1, steps + 1):
            _time.sleep(duration_s / steps)
            self.touch(round(x1 + (x2 - x1) * i / steps), round(y1 + (y2 - y1) * i / steps), 1)
        self.touch(x2, y2, 0)

    def image(self, timeout: float = 10) -> Image.Image:
        """Current frame as a Pillow image (raw RGB888 transfer)."""
        img = self._call(pb.ImageFormat.RGB888, timeout)
        return Image.frombytes("RGB", (img.format.width, img.format.height), img.image)

    def png(self, timeout: float = 10, *, encode_locally: bool = True) -> bytes:
        """Current frame as PNG bytes. Encoding locally from RGB888 is usually faster than asking for PNG."""
        if encode_locally:
            buf = io.BytesIO()
            self.image(timeout).save(buf, format="PNG", compress_level=1)
            return buf.getvalue()
        return self._call(pb.ImageFormat.PNG, timeout).image


def black_fraction(img: Image.Image, threshold: int = 8) -> float:
    """Share of pixels that are (near) black; used to detect FLAG_SECURE frames."""
    gray = img.convert("L").resize((108, 240))
    pixels = gray.tobytes()
    return sum(1 for p in pixels if p <= threshold) / len(pixels)
