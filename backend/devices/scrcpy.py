"""A scrcpy session in Python: a real phone's screen and input for the live view (design doc, Live view › Streaming).

The scrcpy server (Apache-2.0, pinned to the version installed with scrcpy, 5.0.1) runs on the phone through
`app_process`, encodes the screen as H.264 and listens on a local socket that `adb forward` reaches. Envoy reads the
video socket and decodes it on the Mac with PyAV (FFmpeg), keeping the latest frame, and writes scrcpy's binary control
messages (touch, keys, text) to the control socket. This object offers the same methods as the emulator's gRPC client
(`frame`, `tap`, `swipe`, `text`, `key`), so the live view, approval screenshots and step thumbnails work on either.

The design's choice was to send the H.264 to the browser and decode it there (Tango + WebCodecs). Decoding on the Mac
reuses the JPEG protocol, touch handling and latency measurement already proven on the iPhone, and the same latest
frame gives the agent a screenshot in milliseconds instead of `adb screencap`'s 0.5 to 2.6 s.

Secure windows (FLAG_SECURE) are black in scrcpy on a real phone; callers check the window flag, never the pixels.
"""

from __future__ import annotations

import io
import os
import secrets
import socket
import struct
import subprocess
import threading
import time
from pathlib import Path

import av
from PIL import Image

from devices.android import _adb_path

SERVER = Path(os.environ.get("SCRCPY_SERVER", "/opt/homebrew/share/scrcpy/scrcpy-server"))
VERSION = os.environ.get("SCRCPY_VERSION", "5.0.1")  # must match the server file exactly
REMOTE = "/data/local/tmp/envoy-scrcpy-server.jar"

# Control message types and Android constants used here (scrcpy's control_msg.h, Android's KeyEvent/MotionEvent).
MSG_KEYCODE, MSG_TEXT, MSG_TOUCH = 0, 1, 2
DOWN, UP, MOVE = 0, 1, 2
FINGER = 0  # pointer id for our one finger
KEYCODES = {"GoBack": 4, "GoHome": 3, "Enter": 66, "Backspace": 67, "Tab": 61, "AppSwitch": 187}


def touch_msg(action: int, x: int, y: int, width: int, height: int, pressure: float = 1.0) -> bytes:
    """32 bytes: type, action, pointer id (u64), x, y (u32), screen width, height (u16), pressure (u16 fixed point),
    action button, buttons (u32). Positions are in the video frame's coordinates, with its size."""
    p = 0xFFFF if pressure >= 1 else int(pressure * 0x10000)
    return struct.pack(">BBqIIHHHII", MSG_TOUCH, action, FINGER, x, y, width, height, p, 0, 0)


def key_msg(action: int, keycode: int) -> bytes:
    """14 bytes: type, action, keycode, repeat, meta state."""
    return struct.pack(">BBIII", MSG_KEYCODE, action, keycode, 0, 0)


def text_msg(text: str) -> bytes:
    data = text.encode("utf-8")[:300]
    return struct.pack(">BI", MSG_TEXT, len(data)) + data


class ScrcpyStream:
    def __init__(self, serial: str, device_size: tuple[int, int], max_size: int = 1280, max_fps: int = 30,
                 bit_rate: int = 6_000_000) -> None:
        self.serial = serial
        self.device_w, self.device_h = device_size
        self.max_size, self.max_fps, self.bit_rate = max_size, max_fps, bit_rate
        self._proc: subprocess.Popen | None = None
        self._video: socket.socket | None = None
        self._control: socket.socket | None = None
        self._port: int | None = None
        self._frame: av.VideoFrame | None = None
        self.frame_time = 0.0  # when the latest frame was decoded (time.time())
        self.frames = 0
        self._cond = threading.Condition()
        self._send_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self.error: str | None = None
        self.started_at = 0.0

    # ---- lifecycle --------------------------------------------------------------------------

    def _adb(self, *args: str, timeout: float = 30) -> str:
        out = subprocess.run([_adb_path(), "-s", self.serial, *args], capture_output=True, text=True, timeout=timeout)
        if out.returncode != 0:
            raise RuntimeError(f"adb {' '.join(args)}: {out.stderr.strip() or out.stdout.strip()}")
        return out.stdout

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and self.error is None

    def start(self, timeout_s: float = 10) -> "ScrcpyStream":
        if self.running:
            return self
        self.stop()
        if not SERVER.exists():
            raise RuntimeError(f"scrcpy server not found at {SERVER} (brew install scrcpy, or set SCRCPY_SERVER)")
        self._adb("push", str(SERVER), REMOTE)
        scid = f"{secrets.randbits(31):08x}"
        self._port = int(self._adb("forward", "tcp:0", f"localabstract:scrcpy_{scid}").strip())
        opts = [f"scid={scid}", "log_level=warn", "tunnel_forward=true", "audio=false", "control=true", "cleanup=true",
                "video_codec=h264", f"max_size={self.max_size}", f"max_fps={self.max_fps}", f"video_bit_rate={self.bit_rate}",
                "send_device_meta=false", "send_frame_meta=false", "clipboard_autosync=false", "power_off_on_close=false"]
        self._proc = subprocess.Popen([_adb_path(), "-s", self.serial, "shell", f"CLASSPATH={REMOTE}", "app_process", "/",
                                       "com.genymobile.scrcpy.Server", VERSION, *opts],
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        # In forward mode the server sends one dummy byte on the first socket once it is really listening; before that,
        # adb accepts the connection and closes it.
        deadline = time.time() + timeout_s
        while True:
            try:
                s = socket.create_connection(("127.0.0.1", self._port), timeout=2)
                s.settimeout(2)
                if s.recv(1) == b"\x00":
                    self._video = s
                    break
                s.close()
            except OSError:
                pass
            if time.time() > deadline or (self._proc.poll() is not None):
                out = self._proc.stdout.read() if self._proc.poll() is not None and self._proc.stdout else ""
                self.stop()
                raise RuntimeError(f"scrcpy server did not start: {out.strip()[:300]}")
            time.sleep(0.1)
        self._control = socket.create_connection(("127.0.0.1", self._port), timeout=5)
        self._control.settimeout(None)
        self._video.settimeout(None)
        self.error, self.started_at = None, time.time()
        self._thread = threading.Thread(target=self._read_loop, name=f"scrcpy-{self.serial}", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        for s in (self._video, self._control):
            try:
                if s is not None:
                    s.close()
            except OSError:
                pass
        self._video = self._control = None
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
        if self._port is not None:
            subprocess.run([_adb_path(), "-s", self.serial, "forward", "--remove", f"tcp:{self._port}"], capture_output=True, timeout=10)
            self._port = None

    # ---- video ------------------------------------------------------------------------------

    def _read_loop(self) -> None:
        codec = av.CodecContext.create("h264", "r")
        codec.flags |= av.codec.context.Flags.low_delay
        sock = self._video
        assert sock is not None
        try:
            head = b""
            while len(head) < 12:  # codec id ("h264") and the initial size, then raw Annex-B H.264
                chunk = sock.recv(12 - len(head))
                if not chunk:
                    raise ConnectionError("video socket closed")
                head += chunk
            pending = b"" if head[:4] == b"h264" else head  # no codec meta: the bytes are already video
            while True:
                data = pending or sock.recv(1 << 16)
                pending = b""
                if not data:
                    raise ConnectionError("video socket closed")
                for packet in codec.parse(data):
                    for f in codec.decode(packet):
                        with self._cond:
                            self._frame, self.frame_time = f, time.time()
                            self.frames += 1
                            self._cond.notify_all()
        except Exception as e:  # noqa: BLE001 - reported through `error`; the owner restarts the session
            self.error = f"{type(e).__name__}: {e}"
            with self._cond:
                self._cond.notify_all()

    def _latest(self, timeout: float) -> av.VideoFrame:
        with self._cond:
            if self._frame is None:
                self._cond.wait_for(lambda: self._frame is not None or self.error is not None, timeout=timeout)
            if self._frame is None:
                raise TimeoutError(self.error or "no frame from scrcpy yet")
            return self._frame

    @property
    def size(self) -> tuple[int, int]:
        f = self._latest(5)
        return f.width, f.height

    def frame(self, width: int, timeout: float = 5) -> Image.Image:
        f = self._latest(timeout)
        if width >= f.width:
            return f.to_image()
        return f.reformat(width=width, height=round(f.height * width / f.width), format="rgb24").to_image()

    def image(self, timeout: float = 5) -> Image.Image:
        return self._latest(timeout).to_image()

    def png(self, timeout: float = 5) -> bytes:
        buf = io.BytesIO()
        self.image(timeout).save(buf, format="PNG", compress_level=1)
        return buf.getvalue()

    def wait_for_new_frame(self, after: float, timeout: float = 2.0) -> float | None:
        """The decode time of the first frame after `after`, or None (input-to-screen latency checks)."""
        with self._cond:
            self._cond.wait_for(lambda: self.frame_time > after or self.error is not None, timeout=timeout)
            return self.frame_time if self.frame_time > after else None

    # ---- input ------------------------------------------------------------------------------

    def _send(self, data: bytes) -> None:
        if self._control is None:
            raise ConnectionError("scrcpy is not running")
        with self._send_lock:
            self._control.sendall(data)

    def _to_frame(self, x: int, y: int) -> tuple[int, int, int, int]:
        fw, fh = self.size
        return round(x * fw / self.device_w), round(y * fh / self.device_h), fw, fh

    def touch(self, action: int, x: int, y: int) -> None:
        fx, fy, fw, fh = self._to_frame(x, y)
        self._send(touch_msg(action, fx, fy, fw, fh, 1.0 if action != UP else 0.0))

    def tap(self, x: int, y: int, timeout: float = 5) -> None:
        self.touch(DOWN, x, y)
        time.sleep(0.03)
        self.touch(UP, x, y)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_s: float = 0.3, steps: int = 12) -> None:
        self.touch(DOWN, x1, y1)
        for i in range(1, steps + 1):
            time.sleep(duration_s / steps)
            self.touch(MOVE, round(x1 + (x2 - x1) * i / steps), round(y1 + (y2 - y1) * i / steps))
        self.touch(UP, x2, y2)

    def key(self, key: str, timeout: float = 5) -> None:
        code = KEYCODES[key]
        self._send(key_msg(DOWN, code) + key_msg(UP, code))

    def text(self, text: str, timeout: float = 5) -> None:
        self._send(text_msg(text))
