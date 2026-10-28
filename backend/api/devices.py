"""Phones, who controls each one, and takeover (design doc, Live view: "Take over and hand back").

Each phone has a lease. A task holds it while it runs; **Take over** moves control to the user: the agent's next look at
the screen (or action) waits until **Hand back**, so its loop is paused and no screenshots go to a model, while the
user's taps and typing go straight to the phone through the live view, unlogged. After hand back the agent's next call
reads the screen fresh.

The agent never sees this module: it gets a `GatedDevice`, which behaves like the phone but waits whenever the user is
in control.

Phase 6: the pool holds the emulators and any connected Android phone (`devices/phone.py`). While a task uses a real
phone, `watch()` runs beside it: a physical touch (getevent), Pause on the phone's banner, or another app coming to
the front without an action of Envoy's moves control to you, exactly like Take over; Resume on the banner, or Hand
back in the app, gives it back.
"""

from __future__ import annotations

import asyncio
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from devices.emulator import AVDS, EmulatorDevice
from devices.phone import PhoneDevice, discover

SKYLARK = "com.skylark.air"
NAMES = {"envoy-test": "Test phone", "envoy-real": "Real-app phone", "envoy-small": "Small test phone"}
# Apps that may come to the front on their own without it being you: Envoy's banner, the launcher Envoy itself opens.
BENIGN_FRONT = {"ai.envoy.banner", "com.android.systemui"}


@dataclass
class Lease:
    avd: str
    task_id: str | None = None  # the task running on this phone
    user_control: bool = False
    since: float = 0.0
    reason: str = ""  # why the user was asked to take over ("sign-in needed: password field")
    requested_at: float = 0.0  # when the agent last asked the user to take over
    handed_back_at: float = 0.0
    last_agent_call: float = 0.0  # when the agent last acted (a foreground change soon after is its own doing)
    agent_turn: asyncio.Event = field(default_factory=asyncio.Event)  # set while the agent may use the phone
    run_lock: asyncio.Lock = field(default_factory=asyncio.Lock)  # one task at a time per phone

    def __post_init__(self) -> None:
        self.agent_turn.set()

    def state(self) -> dict[str, Any]:
        return {"avd": self.avd, "task_id": self.task_id, "user_control": self.user_control, "since": self.since, "reason": self.reason}


class GatedDevice:
    """The phone as the agent sees it: every call first waits while the user is in control."""

    GATED = {"observe", "act", "launch", "wait_until_settled", "screenshot", "read_field", "snapshot_load", "snapshot_save"}

    def __init__(self, device: Any, lease: Lease) -> None:
        self._device, self._lease = device, lease

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._device, name)
        if name not in self.GATED or not callable(attr):
            return attr

        async def gated(*args: Any, **kwargs: Any) -> Any:
            await self._lease.agent_turn.wait()
            try:
                return await attr(*args, **kwargs)
            finally:
                if name in ("act", "launch"):
                    self._lease.last_agent_call = time.time()
        return gated


class DevicePool:
    def __init__(self, bus: Any) -> None:
        self.bus = bus
        self.leases = {avd: Lease(avd) for avd in AVDS if avd != "envoy-small"}
        self._devices: dict[str, Any] = {}
        self._connect_lock = asyncio.Lock()
        self.phones: dict[str, dict[str, Any]] = {}  # id → {id, serial, model, android, state}, from the last discovery
        self._watchers: dict[str, asyncio.Task] = {}

    @staticmethod
    def avd_for(app: str | None) -> str:
        """SkyLark (our test app) runs on envoy-test; real apps on envoy-real (api/routing.py decides the rest)."""
        return "envoy-test" if not app or app == SKYLARK else "envoy-real"

    def refresh_phones(self) -> list[dict[str, Any]]:
        """Connected Android phones (adb); each gets a lease the first time it is seen, and keeps it."""
        found = discover()
        self.phones = {p["id"]: p for p in found}
        for p in found:
            self.leases.setdefault(p["id"], Lease(p["id"]))
        return found

    def running(self) -> dict[str, bool]:
        try:
            out = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=10).stdout
        except Exception:  # noqa: BLE001
            out = ""
        run = {avd: f"{cfg['serial']}\tdevice" in out for avd, cfg in AVDS.items()}
        run.update({pid: p["state"] == "device" for pid, p in self.phones.items()})
        return run

    def is_phone(self, did: str) -> bool:
        return did.startswith("phone-")

    async def device(self, did: str) -> Any:
        async with self._connect_lock:
            if did not in self._devices:
                if self.is_phone(did):
                    await asyncio.to_thread(self.refresh_phones)
                    p = self.phones.get(did)
                    if p is None or p["state"] != "device":
                        raise RuntimeError("your Android phone isn't connected" if p is None else "your phone hasn't allowed USB debugging yet")
                    self._devices[did] = await asyncio.to_thread(PhoneDevice(p["serial"], did).connect)
                else:
                    if not self.running().get(did):
                        raise RuntimeError(f"{did} is not running (scripts/start_emulator.sh {did})")
                    self._devices[did] = await asyncio.to_thread(EmulatorDevice(did).connect)
            return self._devices[did]

    def gated(self, avd: str, device: Any) -> GatedDevice:
        return GatedDevice(device, self.leases[avd])

    def status(self) -> list[dict[str, Any]]:
        self.refresh_phones()
        run = self.running()
        out = []
        for did, lease in self.leases.items():
            p = self.phones.get(did)
            row = {**lease.state(), "running": run.get(did, False), "connected": did in self._devices,
                   "kind": "phone" if self.is_phone(did) else "emulator", "name": NAMES.get(did, did)}
            if self.is_phone(did):
                row.update(name=(p or {}).get("model") or "Android phone", android=(p or {}).get("android", ""),
                           state=(p or {}).get("state", "disconnected"))
            out.append(row)
        return out

    # ---- a task on a real phone ------------------------------------------------------------------

    def _background(self, fn: Any, *args: Any) -> None:
        """adb calls to the phone's banner (~100 ms) off the event loop; failures only cost the banner."""
        def run() -> None:
            try:
                fn(*args)
            except Exception:  # noqa: BLE001
                pass
        threading.Thread(target=run, daemon=True).start()

    def start_watch(self, did: str, device: Any, app: str | None, banner_text: str = "Envoy is using this phone") -> None:
        if not self.is_phone(did):
            return
        self._background(device.banner.show, banner_text)
        self.stop_watch(did)
        self._watchers[did] = asyncio.get_running_loop().create_task(self.watch(did, device, app))

    def stop_watch(self, did: str, device: Any = None) -> None:
        task = self._watchers.pop(did, None)
        if task is not None:
            task.cancel()
        if device is not None and self.is_phone(did):
            self._background(device.banner.hide)

    async def watch(self, did: str, device: Any, app: str | None, every_s: float = 0.5) -> None:
        """While a task uses the real phone: hand it to you the moment you touch it, press Pause, or another app comes
        to the front without an action of Envoy's; give it back when you press Resume on the phone."""
        lease = self.leases[did]
        started = time.time()
        last_pkg = app or ""
        while True:
            await asyncio.sleep(every_s)
            try:
                banner = await asyncio.to_thread(device.banner.state)
                if lease.user_control:
                    if banner["shown"] and not banner["paused"] and banner["changed_at"] > lease.since:
                        self.hand_back(did, by="you, on the phone")
                    continue
                if banner["paused"]:
                    self.take_over(did, f"paused: {banner['reason'] or 'you pressed Pause on the phone'}", by="phone")
                    continue
                if device.touches.touched_since(max(started, lease.handed_back_at + 1.0)):
                    self.take_over(did, "paused: you touched the phone", by="phone")
                    continue
                pkg = await asyncio.to_thread(device.foreground_package)
                if pkg and pkg != last_pkg and pkg not in BENIGN_FRONT:
                    if time.time() - lease.last_agent_call > 3:
                        self.take_over(did, f"paused: {pkg} came to the front on its own", by="phone")
                        continue
                    last_pkg = pkg
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a missed check is retried on the next tick
                continue

    # ---- takeover ------------------------------------------------------------------------------

    def take_over(self, avd: str, reason: str = "", by: str = "user") -> Lease:
        lease = self.leases[avd]
        if not lease.user_control:
            lease.user_control, lease.since, lease.reason = True, time.time(), reason or lease.reason
            lease.agent_turn.clear()
            self.bus.publish("takeover", avd=avd, task_id=lease.task_id, by=by, reason=lease.reason)
            if by != "phone" and (d := self._devices.get(avd)) is not None and self.is_phone(avd) and lease.task_id:
                self._background(d.banner.pause, "you took over")
        return lease

    def hand_back(self, avd: str, by: str = "user") -> Lease:
        lease = self.leases[avd]
        if lease.user_control:
            lease.user_control, lease.reason, lease.handed_back_at = False, "", time.time()
            lease.agent_turn.set()
            self.bus.publish("hand_back", avd=avd, task_id=lease.task_id, by=by, held_s=round(time.time() - lease.since, 1))
            if (d := self._devices.get(avd)) is not None and self.is_phone(avd) and lease.task_id:
                self._background(d.banner.resume)
        return lease

    def request_takeover(self, avd: str, reason: str) -> None:
        """The agent asks the user to take over (a sign-in, a bot check): the run waits for a hand back. On a real
        phone the banner says so; you do it on the phone itself and press Resume there."""
        lease = self.leases[avd]
        lease.reason, lease.requested_at = reason, time.time()
        self.bus.publish("takeover_requested", avd=avd, task_id=lease.task_id, reason=reason)
        if (d := self._devices.get(avd)) is not None and self.is_phone(avd):
            self._background(d.banner.pause, reason)

    async def wait_for_hand_back(self, avd: str, timeout_s: float) -> bool:
        """After a takeover request: wait for the user to take over and hand back (or for the phone to be free again)."""
        lease = self.leases[avd]
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if not lease.user_control and lease.handed_back_at > lease.requested_at:
                return True
            await asyncio.sleep(0.25)
        return False
