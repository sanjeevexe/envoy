"""The VM's routine results beside the Mac's recorded ones, as Markdown (run on the Mac, after fetching the results).

  python3 scripts/cloud/compare.py                 # eval/results/cloud/{portability.json,sizes.json} vs the Mac's
  python3 scripts/cloud/compare.py --json          # the same numbers as JSON

The Mac's numbers are read from the files the earlier phases saved, never re-measured:
  portability: eval/results/phase6/portability-envoy-small.json, envoy-test (the control device)
  sizes:       eval/results/final/sizes.json, envoy-test
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLOUD = REPO / "eval" / "results" / "cloud"
SUITES = {
    "portability": {"label": "Phase 6 portability: 7 SkyLark routines, unseen bookings, k=3",
                    "mac": REPO / "eval/results/phase6/portability-envoy-small.json", "cloud": CLOUD / "portability.json",
                    "calls": "model_calls"},
    "sizes": {"label": "Phase 7 sizes: the 10 core routines, unseen bookings, k=3",
              "mac": REPO / "eval/results/final/sizes.json", "cloud": CLOUD / "sizes.json", "calls": "calls"},
}


def stats(rows: list[dict], calls: str) -> dict:
    secs = [r["duration_s"] for r in rows]
    return {"runs": len(rows), "passed": sum(1 for r in rows if r["passed"]),
            "no_model_call": sum(1 for r in rows if r["passed"] and not r[calls]), "model_calls": sum(r[calls] for r in rows),
            "median_s": round(statistics.median(secs), 1) if secs else None, "max_s": round(max(secs), 1) if secs else None}


def side(path: Path, calls: str) -> dict | None:
    if not path.exists():
        return None
    d = json.loads(path.read_text())["devices"]["envoy-test"]
    return {"device": f"{d['size'][0]}x{d['size'][1]} @ {d['density']} dpi, {d['model']}, Android {d['android']}", **stats(d["rows"], calls)}


def main() -> int:
    out = {name: {"label": s["label"], "mac": side(s["mac"], s["calls"]), "cloud": side(s["cloud"], s["calls"])} for name, s in SUITES.items()}
    if "--json" in sys.argv:
        print(json.dumps(out, indent=1))
        return 0
    print("| Suite | Where | Device | Passed | No model call | Model calls | Median s | Max s |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for name, o in out.items():
        for where in ("mac", "cloud"):
            x = o[where]
            if x is None:
                print(f"| {name} | {where} | (not run) | | | | | |")
                continue
            print(f"| {name} | {'Mac (Apple M5 Pro, arm64 image)' if where == 'mac' else 'Google Cloud n2-standard-8 (x86_64 image)'} | {x['device']} | "
                  f"**{x['passed']}/{x['runs']}** | {x['no_model_call']} | {x['model_calls']} | {x['median_s']} | {x['max_s']} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
