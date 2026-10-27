"""Screenshot → facts accuracy (Phase 5): SkyLark screens captured as real screenshots, read by Envoy's photo pipeline
(on-device OCR, redaction, Muse Spark vision, every value checked against the OCR text) into a copy of the demo memory.

  uv run --project backend python eval/run_photos.py

Ground truth comes from SkyLark's own fixtures (the values the app draws). For each screen: which of the values it
shows were extracted right, wrong or missed, and whether its trip and flight merged into the ones memory already
knows (natural keys) instead of creating new entities. Standard tier (photos are treated as your data).
Results: eval/results/phase5/photos.json. SkyLark is left signed in with Chicago not checked in.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from demo_setup import demo_fixtures  # noqa: E402
from devices.emulator import EmulatorDevice  # noqa: E402
from devices.types import Action  # noqa: E402
from memory.photos import ingest_photo  # noqa: E402
from memory.service import MemoryService  # noqa: E402
from memory.store import MemoryStore  # noqa: E402
from memory.types import normalize_key_value  # noqa: E402
from models.adapter import ModelAdapter  # noqa: E402
from testapps.skylark import SkyLark  # noqa: E402

OUT = REPO / "eval" / "results" / "phase5" / "photos.json"
WORK = REPO / "data" / "eval_photos"
CHECKED_IN = {"KX7Q2M", "PT4R8Z", "3J8N0D"}


def truth(t: dict[str, Any], screen: str, profile: dict[str, Any]) -> dict[str, str]:
    f = t["flight"]
    base = {"number": f["number"], "date": f["date"], "from": f["from"], "to": f["to"]}
    if screen == "home":
        return {**base, "depart_time": f["depart"], "arrive_time": f["arrive"], "destination": t["city"]}
    if screen == "details":
        return {**base, "depart_time": f["depart"], "arrive_time": f["arrive"], "confirmation_code": t["code"], "gate": f["gate"],
                "seat": f["seat"], "boarding_time": f["boarding"], "boarding_group": f["group"], "status": f["status"], "destination": t["city"]}
    if screen == "boarding_pass":
        return {**base, "seat": f["seat"], "gate": f["gate"], "boarding_time": f["boarding"], "boarding_group": f["group"],
                "name": f"{profile['first_name']} {profile['last_name']}"}
    if screen == "status":
        return {**base, "status": f["status"], "gate": f["gate"], "depart_time": f["depart"]}
    raise ValueError(screen)


def same(attr: str, a: str, b: str) -> bool:
    a, b = a.strip(), b.strip()
    if attr == "boarding_group":
        a, b = a.removeprefix("Group ").strip(), b.removeprefix("Group ").strip()
    return normalize_key_value(attr, a) == normalize_key_value(attr, b)


class Phone:
    def __init__(self) -> None:
        self.d = EmulatorDevice("envoy-test").connect()

    async def tap(self, prefix: str) -> None:
        for _ in range(3):
            s = await self.d.observe()
            el = next((e for e in s.numbered if e.label.lower().startswith(prefix.lower())), None)
            if el is not None:
                await self.d.act(Action(kind="tap", element=el.number))
                await self.d.wait_until_settled(10)
                return
            await self.d.act(Action(kind="scroll", direction="down"))
        raise RuntimeError(f"no element starting with {prefix!r}")

    async def type_into(self, prefix: str, text: str) -> None:
        s = await self.d.observe()
        el = next(e for e in s.numbered if e.editable and e.label.lower().startswith(prefix.lower()))
        await self.d.act(Action(kind="type", element=el.number, text=text, submit=False))
        await self.d.wait_until_settled(5)

    def shot(self, name: str) -> Path:
        path = WORK / f"{name}.png"
        path.write_bytes(subprocess.run(["adb", "-s", "emulator-5554", "exec-out", "screencap", "-p"], capture_output=True, timeout=30, check=True).stdout)
        return path


async def capture(app: SkyLark, fx: dict[str, Any]) -> list[tuple[str, str, Path]]:
    """(trip code, screen kind, screenshot) for each screen in the set."""
    phone = Phone()
    shots: list[tuple[str, str, Path]] = []
    app.launch()
    await phone.d.wait_until_settled(10)
    shots.append(("KX7Q2M", "home", phone.shot("home_chicago")))
    await phone.tap("Next trip")
    shots.append(("KX7Q2M", "details", phone.shot("details_chicago")))
    await phone.tap("View boarding pass")
    shots.append(("KX7Q2M", "boarding_pass", phone.shot("bp_chicago")))
    for code, city in (("PT4R8Z", "Denver"), ("3J8N0D", "Savannah")):
        await phone.tap("Done")
        await phone.tap("My Trips")
        t = next(x for x in fx["trips"] if x["code"] == code)
        await phone.tap(f"{city}")
        shots.append((code, "details", phone.shot(f"details_{city.lower()}")))
        await phone.tap("View boarding pass")
        shots.append((code, "boarding_pass", phone.shot(f"bp_{city.lower()}")))
        assert t
    await phone.tap("Done")
    await phone.tap("Flight status")
    await phone.type_into("Flight number", "SL 1213")
    await phone.tap("Search")
    shots.append(("0Q8P5W", "status", phone.shot("status_louisville")))
    return shots


async def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    app = SkyLark("emulator-5554")
    fx = demo_fixtures(signed_in=True)
    for t in fx["trips"]:
        if t["code"] in CHECKED_IN:
            t["checked_in"] = True
    app.prepare(fixtures=fx, variant=0)
    shots = await capture(app, fx)
    db = WORK / "memory.db"
    shutil.copy(REPO / "data" / "demo" / "memory.db", db)
    store = MemoryStore(db)
    svc = MemoryService(store, ModelAdapter(), data_scope="real")
    rows, tot = [], {"expected": 0, "right": 0, "wrong": 0, "missed": 0, "dropped": 0, "new_flights": 0, "new_trips": 0, "cost": 0.0}
    for code, kind, path in shots:
        t = next(x for x in fx["trips"] if x["code"] == code)
        exp = truth(t, kind, fx["profile"])
        flights, trips = len(store.entities("Flight")), len(store.entities("Trip"))
        copy = WORK / f"upload_{path.name}"
        shutil.copy(path, copy)
        t0 = time.time()
        res = await ingest_photo(svc, copy, photo_id=f"eval-{path.stem}", origin="eval")
        took = time.time() - t0
        got: dict[str, list[str]] = {}
        for e in res.report.extracted if res.report else []:
            for o in e.observations:
                got.setdefault(o.attribute, []).append(o.value)
        right = [a for a, v in exp.items() if any(same(a, v, g) for g in got.get(a, []))]
        wrong = [f"{a}: {got[a]} (expected {v})" for a, v in exp.items() if a in got and a not in right]
        missed = [a for a in exp if a not in got]
        nf, nt = len(store.entities("Flight")) - flights, len(store.entities("Trip")) - trips
        rows.append({"screen": path.stem, "kind": kind, "expected": len(exp), "right": len(right), "wrong": wrong, "missed": missed,
                     "extra": sorted(set(got) - set(exp)), "dropped": res.report.dropped if res.report else [], "new_flights": nf, "new_trips": nt,
                     "resolved": [f"{r.type}:{r.how}" for r in res.report.resolved] if res.report else [], "deleted": res.deleted,
                     "redacted_lines": res.redacted_lines, "ocr_ms": res.ocr_ms, "model_ms": res.model_ms, "total_s": round(took, 2),
                     "cost_usd": round(res.report.cost_usd, 5) if res.report else 0})
        for k, v in (("expected", len(exp)), ("right", len(right)), ("wrong", len(wrong)), ("missed", len(missed)),
                     ("dropped", len(rows[-1]["dropped"])), ("new_flights", nf), ("new_trips", nt), ("cost", rows[-1]["cost_usd"])):
            tot[k] += v
        print(f"{path.stem:20} {len(right)}/{len(exp)} right; wrong={wrong} missed={missed} new F/T={nf}/{nt} "
              f"resolved={rows[-1]['resolved']} {took:.1f}s", flush=True)
    summary = {**tot, "accuracy": f"{tot['right']}/{tot['expected']}", "screens": len(rows), "cost": round(tot["cost"], 4),
               "ocr_ms_median": sorted(r["ocr_ms"] for r in rows)[len(rows) // 2], "model_ms_median": sorted(r["model_ms"] for r in rows)[len(rows) // 2],
               "all_deleted": all(r["deleted"] for r in rows)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "summary": summary, "screens": rows}, indent=1))
    print(json.dumps(summary))
    app.prepare(fixtures=demo_fixtures(signed_in=True), variant=0)  # back to the gate's starting point
    shutil.rmtree(WORK)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
