"""Capture Phase 0 fixtures from built-in apps on envoy-test into eval/fixtures/phase0/<name>/.

Each fixture has tree.json (normalized accessibility tree), compact.txt (what the model sees),
screen.png (full 1080x2400 gRPC screenshot) and meta.json (app, screen, signature, and for the
grounding fixture a known target with its bounding box in pixels and on Meta's 0-1000 grid).

Usage: uv run --project backend python scripts/capture_fixtures.py
Also saves the envoy-test snapshot "phase0-gate" (Settings home) used by scripts/meta_api_check.py.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from devices.emulator import EmulatorDevice
from devices.types import Action, Element, ScreenState

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "eval" / "fixtures" / "phase0"
GATE_SNAPSHOT = "phase0-gate"


def to_grid(bounds: tuple[int, int, int, int], w: int, h: int) -> list[int]:
    x1, y1, x2, y2 = bounds
    return [round(x1 * 1000 / w), round(y1 * 1000 / h), round(x2 * 1000 / w), round(y2 * 1000 / h)]


def find(s: ScreenState, *, rid: str | None = None, label: str | None = None) -> Element:
    for e in s.numbered:
        if rid and e.resource_id.endswith(rid):
            return e
        if label and e.label.lower().startswith(label.lower()):
            return e
    raise LookupError(f"no element rid={rid} label={label} on {s.activity}:\n{s.compact}")


def save(d: EmulatorDevice, name: str, s: ScreenState, extra: dict | None = None) -> None:
    folder = OUT / name
    folder.mkdir(parents=True, exist_ok=True)
    png = d.grpc.png()
    (folder / "screen.png").write_bytes(png)
    (folder / "tree.json").write_text(json.dumps(s.tree_json(), indent=1, ensure_ascii=False))
    (folder / "compact.txt").write_text(s.compact + "\n")
    meta = {
        "name": name,
        "package": s.package,
        "activity": s.activity,
        "signature": s.signature,
        "width": s.width,
        "height": s.height,
        "elements_total": len(s.elements),
        "elements_numbered": len(s.numbered),
        "compact_chars": len(s.compact),
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "device": "envoy-test (Pixel 6 profile, API 35 Google Play arm64)",
        **(extra or {}),
    }
    (folder / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print(f"--- {name}: {len(s.numbered)} numbered of {len(s.elements)} nodes, {len(s.compact)} chars")
    print(s.compact)


def target(e: Element, s: ScreenState, description: str) -> dict:
    return {
        "description": description,
        "element_number": e.number,
        "resource_id": e.resource_id,
        "bbox_px": list(e.bounds),
        "bbox_1000": to_grid(e.bounds, s.width, s.height),
        "center_px": list(e.center),
    }


async def fresh(d: EmulatorDevice, package: str) -> ScreenState:
    await d.act(Action(kind="home"))
    if package == "com.android.settings":  # Settings search runs in its own package and survives a Settings stop
        d.adb.shell("am force-stop com.google.android.settings.intelligence")
    await asyncio.to_thread(d.u2.app_start, package, stop=True)
    return await d.wait_until_settled(8)


async def main() -> None:
    d = EmulatorDevice("envoy-test").connect()

    # 1. Settings home (also the gate screen): goal "Open the Battery settings".
    s = await fresh(d, "com.android.settings")
    battery = find(s, label="Battery")
    save(d, "settings_home", s, {
        "task": {"goal": "Open the Battery settings", "expected_action": {"type": "tap", "element": battery.number}},
        "grounding_target": target(battery, s, "the Battery row"),
    })
    await d.snapshot_save(GATE_SNAPSHOT)
    print(f"saved snapshot {GATE_SNAPSHOT}")

    # 2. Tall screen with a small known target: Network & internet → Airplane mode switch.
    await d.act(Action(kind="tap", element=find(s, label="Network & internet").number))
    s = await d.wait_until_settled(8)
    switch = next(e for e in s.numbered if e.kind == "Switch" or (e.checkable and "irplane" in e.label))
    airplane_row = find(s, label="Airplane mode")
    save(d, "settings_network_tall", s, {
        "task": {"goal": "Turn on Airplane mode", "expected_action": {"type": "tap", "element": switch.number}},
        "grounding_target": target(switch, s, "the Airplane mode switch"),
        "grounding_target_row": target(airplane_row, s, "the Airplane mode row"),
    })

    # 3. Contacts (no account signed in).
    s = await fresh(d, "com.google.android.contacts")
    save(d, "contacts_home", s, {"task": {"goal": "Start creating a new contact"}})

    # 4. Chrome (first run, no account).
    s = await fresh(d, "com.android.chrome")
    save(d, "chrome_first_run", s, {"task": {"goal": "Continue without signing in"}})

    # 5. Clock (icon + label tabs; opens on its last tab).
    s = await fresh(d, "com.google.android.deskclock")
    save(d, "clock_home", s, {"task": {"goal": "Open the Timer tab"}})

    await d.act(Action(kind="home"))


if __name__ == "__main__":
    asyncio.run(main())
