"""Phones, who controls each one, and takeover (design doc, Live view: "Take over and hand back").

Each phone has a lease. A task holds it while it runs; **Take over** moves control to the user: the agent's next look at
the screen (or action) waits until **Hand back**, so its loop is paused and no screenshots go to a model, while the
user's taps and typing go straight to the phone through the live view, unlogged. After hand back the agent's next call
reads the screen fresh.

The agent never sees this module: it gets a `GatedDevice`, which behaves like the phone but waits whenever the user is
in control.
"""

from __future__ import annotations

import asyncio
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

from devices.emulator import AVDS, EmulatorDevice

SKYLARK = "com.skylark.air"


@dataclass
class Lease:
    avd: str
    task_id: str | None = None  # the task running on this phone
    user_control: bool = False
    since: float = 0.0
    reason: str = ""  # why the user was asked to take over ("sign-in needed: password field")
    requested_at: float = 0.0  # when the agent last asked the user to take over
    handed_back_at: float = 0.0
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
            return await attr(*args, **kwargs)
        return gated


class DevicePool:
    def __init__(self, bus: Any) -> None:
        self.bus = bus
        self.leases = {avd: Lease(avd) for avd in AVDS}
        self._devices: dict[str, EmulatorDevice] = {}
        self._connect_lock = asyncio.Lock()

    @staticmethod
    def avd_for(app: str | None) -> str:
        """SkyLark (our test app) runs on envoy-test; real apps on envoy-real (design doc, Choosing which phone runs a task)."""
        return "envoy-test" if not app or app == SKYLARK else "envoy-real"

    @staticmethod
    def running() -> dict[str, bool]:
        try:
            out = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=10).stdout
        except Exception:  # noqa: BLE001
            out = ""
        return {avd: f"{cfg['serial']}\tdevice" in out for avd, cfg in AVDS.items()}

    async def device(self, avd: str) -> EmulatorDevice:
        async with self._connect_lock:
            if avd not in self._devices:
                if not self.running().get(avd):
                    raise RuntimeError(f"{avd} is not running (scripts/start_emulator.sh {avd})")
                self._devices[avd] = await asyncio.to_thread(EmulatorDevice(avd).connect)
            return self._devices[avd]

    def gated(self, avd: str, device: Any) -> GatedDevice:
        return GatedDevice(device, self.leases[avd])

    def status(self) -> list[dict[str, Any]]:
        run = self.running()
        return [{**lease.state(), "running": run.get(avd, False), "connected": avd in self._devices} for avd, lease in self.leases.items()]

    # ---- takeover ------------------------------------------------------------------------------

    def take_over(self, avd: str, reason: str = "", by: str = "user") -> Lease:
        lease = self.leases[avd]
        if not lease.user_control:
            lease.user_control, lease.since, lease.reason = True, time.time(), reason or lease.reason
            lease.agent_turn.clear()
            self.bus.publish("takeover", avd=avd, task_id=lease.task_id, by=by, reason=lease.reason)
        return lease

    def hand_back(self, avd: str, by: str = "user") -> Lease:
        lease = self.leases[avd]
        if lease.user_control:
            lease.user_control, lease.reason, lease.handed_back_at = False, "", time.time()
            lease.agent_turn.set()
            self.bus.publish("hand_back", avd=avd, task_id=lease.task_id, by=by, held_s=round(time.time() - lease.since, 1))
        return lease

    def request_takeover(self, avd: str, reason: str) -> None:
        """The agent asks the user to take over (a sign-in, a bot check): the run waits for a hand back."""
        lease = self.leases[avd]
        lease.reason, lease.requested_at = reason, time.time()
        self.bus.publish("takeover_requested", avd=avd, task_id=lease.task_id, reason=reason)

    async def wait_for_hand_back(self, avd: str, timeout_s: float) -> bool:
        """After a takeover request: wait for the user to take over and hand back (or for the phone to be free again)."""
        lease = self.leases[avd]
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if not lease.user_control and lease.handed_back_at > lease.requested_at:
                return True
            await asyncio.sleep(0.25)
        return False
