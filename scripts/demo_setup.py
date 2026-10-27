"""Put the demo in a known state: SkyLark seeded with bookings (signed out, so the check-in starts with your sign-in),
and a fresh demo memory built from the matching confirmation emails (data/demo/).

  uv run --project backend python scripts/demo_setup.py              # signed out, memory from the inbox
  uv run --project backend python scripts/demo_setup.py --signed-in  # skip the sign-in
  uv run --project backend python scripts/demo_setup.py --app-only   # reseed SkyLark, keep memory

Run it with the API stopped (it rewrites data/demo/memory.db). envoy-test must be running. SkyLark is our test app,
so its sign-in takes any email and password, then the test SMS code printed below.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "eval"))

from integrations.mail import LocalMailbox  # noqa: E402
from memory.service import MemoryService  # noqa: E402
from memory.store import MemoryStore  # noqa: E402
from models.adapter import ModelAdapter  # noqa: E402
from run_memory import bookings_for_eval  # noqa: E402
from skylark_mail import build_inbox, write_inbox  # noqa: E402
from skylark_routines import fixtures  # noqa: E402
from testapps.skylark import SkyLark  # noqa: E402

DEMO = REPO / "data" / "demo"


def demo_fixtures(signed_in: bool) -> dict:
    bookings = bookings_for_eval()
    fx = fixtures(bookings[2:])
    for t in fx["trips"]:
        if t["code"] == bookings[-1].code:
            t["cancelled"] = True  # the second Denver trip was cancelled by email
    fx["signed_in"] = signed_in
    return fx


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--signed-in", action="store_true")
    ap.add_argument("--app-only", action="store_true")
    args = ap.parse_args()
    fx = demo_fixtures(args.signed_in)
    SkyLark("emulator-5554").prepare(fixtures=fx, variant=0)
    print(f"SkyLark seeded: {len(fx['trips'])} trips, {'signed in' if args.signed_in else 'signed out'}; test SMS code {fx['sms_code']}")
    if args.app_only:
        return 0
    inbox = DEMO / "inbox"
    write_inbox(build_inbox(bookings_for_eval(), seed=3), inbox)
    db = DEMO / "memory.db"
    db.unlink(missing_ok=True)
    store = MemoryStore(db)
    svc = MemoryService(store, ModelAdapter(), data_scope="test_app")
    mails, _ = LocalMailbox(inbox).fetch(None)
    for m in mails:
        await svc.ingest_email(m, task_id="demo-inbox")
    print(f"Demo memory: {len(mails)} emails → {len(store.entities('Trip'))} trips, {len(store.entities('Flight'))} flights ({db})")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
