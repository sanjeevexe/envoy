"""Drive an Envoy emulator by hand through the device layer (for exploration and Phase 0 checks).

  uv run --project backend python scripts/drive.py <avd> show
  uv run --project backend python scripts/drive.py <avd> tap "<label prefix>" | tap <number>
  uv run --project backend python scripts/drive.py <avd> back | home | scroll [down|up]

Prints the compact screen after each action. Taps never type anything.
"""

from __future__ import annotations

import asyncio
import sys

from devices.emulator import EmulatorDevice
from devices.types import Action


async def main() -> None:
    avd, cmd, *rest = sys.argv[1:]
    d = EmulatorDevice(avd).connect()
    s = await d.observe()
    if cmd == "tap":
        arg = " ".join(rest)
        el = s.element(int(arg)) if arg.isdigit() else next(
            (e for e in s.numbered if e.label.lower().startswith(arg.lower())), None
        )
        if el is None:
            print(f"no element starting with {arg!r}\n{s.compact}")
            return
        r = await d.act(Action(kind="tap", element=el.number))
        print(f"tapped [{el.number}] {el.label!r}: {'ok' if r.ok else r.error}")
    elif cmd in ("back", "home"):
        await d.act(Action(kind=cmd))
    elif cmd == "scroll":
        await d.act(Action(kind="scroll", direction=(rest[0] if rest else "down")))
    s = await d.wait_until_settled(10)
    print(f"secure={s.secure} password_field={s.has_password_field}")
    print(s.compact)


if __name__ == "__main__":
    asyncio.run(main())
