"""Scripted smoke test of SkyLark Air through Envoy's device layer (no model).

Checks that every flow the eval tasks need works, in all four layout variants, and that the
state hook sees the result. Usage: uv run --project backend python scripts/skylark_smoke.py
"""

from __future__ import annotations

import asyncio
import sys
import time

from devices.emulator import EmulatorDevice
from devices.types import Action, ScreenState
from testapps.skylark import SkyLark

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


class Driver:
    def __init__(self, d: EmulatorDevice) -> None:
        self.d = d
        self.s: ScreenState | None = None

    async def look(self) -> ScreenState:
        self.s = await self.d.wait_until_settled(6)
        return self.s

    def find(self, rid: str | None = None, label: str | None = None):
        assert self.s is not None
        for e in self.s.numbered:
            if rid and e.resource_id == rid:
                return e
            if label and e.label.startswith(label):
                return e
        return None

    async def tap(self, rid: str | None = None, label: str | None = None, scrolls: int = 6) -> None:
        await self.look()
        for _ in range(scrolls + 1):
            el = self.find(rid, label)
            if el:
                await self.d.act(Action(kind="tap", element=el.number))
                await self.look()
                return
            await self.d.act(Action(kind="scroll", direction="down"))
            await self.look()
        raise LookupError(f"not found: {rid or label}\n{self.s.compact if self.s else ''}")

    async def type(self, rid: str, text: str) -> None:
        await self.look()
        el = self.find(rid)
        assert el, f"no field {rid}"
        r = await self.d.act(Action(kind="type", element=el.number, text=text))
        assert r.ok, r.error
        await self.look()


async def main() -> int:
    d = EmulatorDevice("envoy-test").connect()
    app = SkyLark(d.serial)
    drv = Driver(d)

    for variant in (0, 1, 2, 3):
        app.prepare(variant=variant)
        await drv.look()
        # Check in through trip details (variant 1 moves the button to a bottom bar).
        await drv.tap(rid="card_next_trip")
        await drv.tap(rid="btn_checkin")
        await drv.tap(rid="cb_passenger_0")
        await drv.tap(rid="btn_continue")
        await drv.tap(rid="cb_hazmat")
        await drv.tap(rid="btn_continue")
        if variant == 3:
            await drv.tap(rid="btn_looks_good")
        await drv.tap(rid="btn_confirm_checkin")
        ok = app.trip("KX7Q2M")["checked_in"] and drv.find(rid="text_checked_in") is not None
        check(f"v{variant} check-in", ok, f"button label: {'Check-in now' if variant == 2 else 'Check in'}")

    app.prepare()
    await drv.tap(rid="card_next_trip")
    await drv.tap(rid="btn_change_seat")
    await drv.tap(rid="seat_12C")
    await drv.tap(rid="btn_confirm_seat")
    check("change seat to 12C", app.trip("KX7Q2M")["flight"]["seat"] == "12C")

    app.prepare()
    await drv.tap(rid="card_next_trip")
    await drv.type("field_ktn", "98765432")
    await drv.tap(rid="btn_save_ktn")
    check("save known traveler number", app.trip("KX7Q2M")["ktn"] == "98765432")

    app.prepare()
    await drv.tap(rid="nav_status")
    await drv.type("field_flight_number", "SL 1190")
    await drv.tap(rid="btn_search_status")
    res = drv.find(rid="text_status_result")
    check("flight status SL 1190", bool(res and "Delayed 25 min" in res.label), res.label if res else "")

    app.prepare()
    await drv.tap(rid="nav_profile")
    await drv.tap(rid="switch_gate_alerts")
    check("gate alerts on", app.state()["profile"]["gate_alerts"] is True)

    app.prepare()
    await drv.tap(rid="nav_trips")
    await drv.type("field_confirmation", "PT4R8Z")
    await drv.type("field_last_name", "Patel")
    await drv.tap(rid="btn_find_trip")
    title = drv.find(rid="screen_title")
    check("find trip PT4R8Z", bool(title and "Denver" in title.label), title.label if title else "")

    app.prepare()
    await drv.tap(rid="nav_trips")
    await drv.tap(rid="trip_row_KS4V9Q", scrolls=8)
    date = drv.find(rid="row_date")
    check("past trip to Seattle (needs scrolling)", bool(date and "Mar 3" in date.label), date.label if date else "")

    app.prepare(fixtures=None)
    app.sign_out()
    app.stop(); app.launch()
    s = await drv.look()
    check("signed-out start shows a password field", s.has_password_field, s.activity)

    app.prepare()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    t = time.time()
    code = asyncio.run(main())
    print(f"{time.time() - t:.0f} s")
    sys.exit(code)
