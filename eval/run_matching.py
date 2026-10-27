"""Matching requests to routines: 12 requests (paraphrases, inputs from notes, and requests no routine covers).

  uv run --project backend python eval/run_matching.py        # writes eval/results/phase2/matching.json
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from routines.matcher import RoutineMatcher
from routines.store import RoutineStore

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "eval" / "results" / "phase2"

# (request, notes, acceptable families (one or several) or None, expected input values that must be filled).
# The library also holds a next-trip-only check-in routine: right for the next trip (Chicago), wrong for any other.
CASES = [
    ("Check me in for my Denver flight", "", "check_in", ["Denver"]),
    ("I need to check in for my trip to Tampa", "", "check_in", ["Tampa"]),
    ("Check me in", "Upcoming trip: Chicago (confirmation KX7Q2M), the next trip", ("check_in", "check_in_next"), ["Chicago"]),
    ("Move me to seat 21C on the Denver flight", "", "change_seat", ["Denver", "21C"]),
    ("Change my seat to 22A", "Upcoming trip: Tampa", "change_seat", ["Tampa", "22A"]),
    ("Add my TSA PreCheck number to my Tampa trip", "Known traveler number: 55501234", "add_ktn", ["Tampa", "55501234"]),
    ("Which gate is my Boise flight at?", "", "gate", ["Boise"]),
    ("Is SL 1190 on time?", "", "flight_status", ["SL 1190"]),
    ("Where does trip PT4R8Z go?", "Last name: Patel", "find_trip", ["PT4R8Z"]),
    ("Cancel my Denver trip", "", None, []),
    ("What seat am I in on my Denver flight?", "", None, []),
    ("How many SkyLark miles do I have?", "", None, []),
]


async def main() -> int:
    store = RoutineStore(REPO / "data" / "routines")
    compiled = json.loads((OUT / "compile.json").read_text())["rows"]
    name_of = {r["family"]: r["routine"] for r in compiled if r.get("status") == "added"}
    m = RoutineMatcher(store, data_scope="test_app")
    rows, cost = [], 0.0
    for request, notes, family, values in CASES:
        res = await m.match(request, notes, task_id="p2-match")
        cost += res.cost_usd
        fams = (family,) if isinstance(family, str) else (family or ())
        accepted = [name_of[f] for f in fams if f in name_of]
        expected = " or ".join(accepted) if accepted else None
        got = res.routine.routine if res.routine else None
        inputs_ok = all(any(v.casefold() == x.casefold() for x in res.inputs.values()) for v in values) and not res.missing
        correct = (got in accepted and inputs_ok) if accepted else got is None
        rows.append({"request": request, "notes": notes, "expected": expected, "matched": got, "inputs": res.inputs, "missing": res.missing,
                     "stage": res.stage, "shortlist": res.candidates, "model_calls": res.model_calls, "correct": correct})
        print(f"{'OK ' if correct else 'BAD'} {request!r:55} → {got} {res.inputs} {res.missing or ''} ({res.stage})", flush=True)
    ok = sum(r["correct"] for r in rows)
    summary = (f"{ok}/{len(rows)} correct (routine and every input right, or no routine when none fits); "
               f"{sum(r['model_calls'] for r in rows)} model calls, ${cost:.4f} at standard prices.")
    print(summary)
    (OUT / "matching.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
