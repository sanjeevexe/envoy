"""Demo history for learning from repeats (api/repeats.py): three Mondays of checking a SkyLark flight's status at about
8 AM, so "Make this a habit?" has a weekly pattern to find.

  uv run --project backend python scripts/seed_repeats.py --api-dir <the API copy's data dir>

It writes tasks only (no memory, no triggers, no routines) into that folder's envoy.db, each with source `seed` and a
detail that says it was seeded. Running it twice adds nothing new. The API finds the pattern on its next daily look or
after the next task finishes.

Run it on your own copy. Whether it goes onto the demo setup is the coordinator's call at the demo rehearsal, and it
refuses data/api while the live API is up.
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

GOAL = "Check the status of my flight SL 1190"
ROUTINE, APP, INPUTS = "skylark_check_flight_status", "com.skylark.air", {"flight_number": "SL 1190"}
RESULT = "SL 1190 · On time · Atlanta → Denver, gate C9"
DETAIL = "seeded by scripts/seed_repeats.py: demo history for learning from repeats, not a real run"
TIMES = ((8, 2, 31), (7, 56, 28), (8, 11, 34))  # (hour, minute, seconds the run took), oldest first


def live_api_up() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8700/healthz", timeout=1) as r:
            return r.status == 200
    except OSError:
        return False


def mondays(now: datetime, n: int = 3) -> list[datetime]:
    """The last n Mondays before today, oldest first."""
    d = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    while d.weekday() != 0:
        d -= timedelta(days=1)
    return [d - timedelta(weeks=i) for i in range(n)][::-1]


def seed(api_dir: Path, now: datetime | None = None) -> list[str]:
    from api.store import TaskStore
    store = TaskStore(api_dir / "envoy.db")
    with store.lock:
        have = {r[0] for r in store.db.execute("SELECT created_at FROM tasks WHERE source='seed' AND routine=?", (ROUTINE,)).fetchall()}
    made = []
    for day, (h, m, took) in zip(mondays(now or datetime.now()), TIMES):
        at = day.replace(hour=h, minute=m).timestamp()
        if at in have:
            continue
        t = store.create(GOAL, "seed", routine=ROUTINE, inputs=INPUTS, app=APP, kind="routine", status="done", result=RESULT, detail=DETAIL,
                         device="envoy-test", request=GOAL)
        with store.lock:
            store.db.execute("UPDATE tasks SET created_at=?, updated_at=? WHERE id=?", (at, at + took, t["id"]))
            store.db.commit()
        store.add_step(t["id"], {"kind": "note", "text": DETAIL})
        made.append(t["id"])
    return made


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--api-dir", required=True, help="the API copy's data dir (its envoy.db gets the tasks)")
    args = ap.parse_args()
    api_dir = Path(args.api_dir).expanduser().resolve()
    if api_dir == (REPO / "data" / "api").resolve() and live_api_up():
        print("refusing: data/api belongs to the live API, which is running on :8700", file=sys.stderr)
        return 2
    made = seed(api_dir)
    print(f"seeded {len(made)} task(s) into {api_dir / 'envoy.db'}" + ("" if made else " (they were already there)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
