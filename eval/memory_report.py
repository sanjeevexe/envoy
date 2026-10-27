"""Build eval/results/phase3/report.md from run_memory.py's JSON results.

  uv run --project backend python eval/memory_report.py
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "eval" / "results" / "phase3"


def load(name: str) -> dict | None:
    p = OUT / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def main() -> int:
    md = ["# Phase 3 evaluation: the shared memory graph on SkyLark Air", ""]
    e = load("emails")
    if e:
        s = e["summary"]
        md += ["## The test inbox: extraction and matching (no phone)", "",
               f"{s['emails']} emails for 7 bookings (Chicago, Denver, four new bookings, a second Denver trip on another date): confirmations "
               "with schema.org markup or as plain text, forwards, a seat change, a cancellation, two promotions and a receipt. "
               f"{s['model_calls']} model calls, ${s['cost_usd']}.", "",
               "| Measure | Result |", "| --- | --- |",
               f"| Attributes extracted right (recall) | {s['attributes']['found']}/{sum(s['attributes'].values())} ({s['recall']:.0%}) |",
               f"| Extracted values that were right (precision) | {s['precision']:.0%} ({s['attributes']['wrong']} wrong) |",
               f"| Markup emails (no model) | {s['by_method']['markup']['found']}/{sum(s['by_method']['markup'].values())} attributes |",
               f"| Plain emails (Muse Spark) | {s['by_method']['model']['found']}/{sum(s['by_method']['model'].values())} attributes |",
               f"| Bookings → exactly one Trip and one Flight | {s['bookings_one_trip_one_flight']} |",
               f"| Trips created from promotions | {len(s['trips_without_a_booking'])} |",
               f"| Cancellation applied to its trip | {'yes' if s['cancelled_marked'] else 'no'} |",
               f"| Two trips to Denver kept apart | {'yes' if s['denver_trips_kept_apart'] else 'no'} |",
               f"| Facts traceable to a source | {'100%' if s['traceable'] else 'no'} |", "",
               "| Email | Kind | Read by | Resolved as | Found | Wrong | Missing |", "| --- | --- | --- | --- | --- | --- | --- |"]
        md += [f"| {r['email']} | {r['kind']} | {r['method']} | {', '.join(f'{t} {h}' for t, h in r['resolved']) or '–'} | {r['found']} | {r['wrong']} | {r['missing']} |"
               for r in e["rows"]]
        md.append("")
    g = load("gate")
    if g:
        s = g["summary"]
        md += ["## The gate on the phone", "", f"**{'Passed' if s['passed'] else 'Not passed'}** ({s['steps_ok']} steps, {s['duration_s']} s). "
               f"Memory at the end: {s['entities']}, {s['facts']} facts, {s['events']} events.", "",
               "| Step | OK | Detail |", "| --- | --- | --- |"]
        for st in g["steps"]:
            detail = {k: v for k, v in st.items() if k not in ("step", "ok", "notes")}
            text = "; ".join(f"{k}: {v}" for k, v in detail.items())
            md.append(f"| {st['step']} | {'✅' if st['ok'] else '❌'} | {text[:400].replace('|', '/')} |")
        notes = next((st.get("notes") for st in g["steps"] if st.get("notes")), None)
        if notes:
            md += ["", "Notes the answer was given from (retrieval output):", "", "```markdown", notes, "```"]
        md.append("")
    (OUT / "report.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
