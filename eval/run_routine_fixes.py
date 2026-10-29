"""The routine-fix measurement (Oct 28): eval/run_real_pass.py on the rows the fixes touch (amazon, play_rating,
chrome_wikipedia), then the same rows again with a second input no pass has used (never learned, never tried).

  uv run --project backend python eval/run_routine_fixes.py [--out eval/results/routine_fixes_2026-10-28]

Writes <out>/pass/ (the usual real_pass.json and .md, second input as Phase 7 set it) and <out>/unseen/ (the same, with
the unseen inputs below). The frozen results and real_pass_2026-10-28 stay as they are. Same rules as run_real_pass:
envoy-real, every approval declined, no sign-ins.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

import run_real_apps as rr
import run_real_pass as rp
from final_common import REPO

ROWS = "amazon,play_rating,chrome_wikipedia"
UNSEEN = {"amazon": ({"AA batteries": "wireless mouse", "aa batteries": "wireless mouse"}, None),
          "play_rating": ({"Duolingo": "Pinterest"}, None),
          "chrome_wikipedia": ({"Eiffel Tower": "Golden Gate Bridge"}, r"\b1937\b")}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO / "eval" / "results" / f"routine_fixes_{time.strftime('%Y-%m-%d')}"))
    ap.add_argument("--part", choices=["pass", "unseen", "both"], default="both")
    args = ap.parse_args()
    out = Path(args.out)
    for part in (["pass", "unseen"] if args.part == "both" else [args.part]):
        if part == "unseen":
            for wf in rr.WORKFLOWS:
                if wf.id in UNSEEN:
                    wf.second, expect = UNSEEN[wf.id]
                    wf.expect_second = expect
        if part == "unseen" and args.part == "both":
            time.sleep(61)  # a new minute: a new task prefix, so the reruns keep their own traces
        sys.argv = ["run_real_pass.py", "--out", str(out / part), "--only", ROWS]
        await rp.main()


if __name__ == "__main__":
    asyncio.run(main())
