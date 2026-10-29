"""What each change did in one stage, counted from Envoy's full traces (data/runs/<run>/steps.jsonl), so every change
proposed for `main` has its own evidence next to the stage's score.

  python3 eval/androidworld/fix_effects.py fixes1-dev                # all episodes of the stage
  python3 eval/androidworld/fix_effects.py final-standard held_out   # one half → <stage>/fix_effects_<half>.json

Per change (numbers as in docs/androidworld-results.md):
1  launches by name that opened an app; launches that failed; decisions made on the launcher
2  steps the self-changing-line mask judged "no change" although the screen text differed; decisions taken on a home
   screen with a running Clock timer's chip (the environment, not a change: it depends on what earlier tasks left)
3  decisions whose expected result repeats an earlier one word for word (the echo; history no longer feeds it)
4  screens shown with the keyboard line; actions asked again because the model called them a placeholder
5  dones the plan's check rejected, then a second done accepted (done_unverified), and how AndroidWorld scored those
7  steps that saw TODAY (from the phone)
8  screens with a line over 120 characters (shown at length; before, cut at 120)
10b back as a share of all actions; reasons that call the action a placeholder
11 steps that kept something (0_remember), and episodes that used it
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RESULTS = REPO / "eval" / "results" / "androidworld"
LAUNCHER = re.compile(r"^App: \S*launcher", re.I)
PLACEHOLDER = re.compile(r"placeholder|schema requires|required by (the )?schema|comply with (the )?schema|wrong action|this is wrong|incorrect but", re.I)
KEYBOARD = "(the on-screen keyboard is open"
TIMER_CHIP = re.compile(r'Button "-?\d+:-?\d+(:\d+)?" \(id: title_text\)')  # a running Clock timer on the home screen


def effects(ep: dict) -> Counter:
    c: Counter = Counter()
    e = ep.get("envoy") or {}
    steps_file = REPO / (e.get("trace_dir") or "missing") / "steps.jsonl"
    if not steps_file.exists():
        c["no_trace"] += 1
        return c
    recs = [json.loads(l) for l in steps_file.read_text().splitlines() if l.strip()]
    seen_expected: set[str] = set()
    acts = [r for r in recs if r.get("kind") == "action"]
    for r in acts:
        d = r.get("decision") or {}
        a = d.get("action") or {}
        t = a.get("type")
        before = (r.get("screen_before") or {}).get("compact") or ""
        after = (r.get("screen_after") or {}).get("compact") or ""
        c["actions"] += 1
        c["back"] += t == "back"
        c["placeholder_reason"] += bool(PLACEHOLDER.search(f"{d.get('reason', '')} {d.get('expected_result', '')}"))
        c["asked_again"] += bool(r.get("placeholder"))
        on_launcher = bool(LAUNCHER.search(before.split("\n", 1)[0]))
        c["on_launcher"] += on_launcher
        c["timer_chip"] += on_launcher and bool(TIMER_CHIP.search(before))
        if t == "launch":
            ok = (r.get("result") or {}).get("ok")
            c["launch_ok_by_name" if ok and "." not in (a.get("app") or "") else "launch_ok" if ok else "launch_failed"] += 1
        body = lambda compact: compact.split("\n", 1)[1] if "\n" in compact else ""  # without the header ("settled 26 ms")
        if r.get("changed") is False and after and before and body(after) != body(before) and \
                (r.get("screen_after") or {}).get("signature") == (r.get("screen_before") or {}).get("signature"):
            c["masked_no_change"] += 1
        exp = (d.get("expected_result") or "").strip()
        if len(exp) > 15 and exp in seen_expected:
            c["echoed_expectation"] += 1
        seen_expected.add(exp)
        c["keyboard_line"] += KEYBOARD in before
        c["long_line"] += any(len(line) > 160 for line in before.splitlines())  # a 120-character label plus its "[n] Kind" frame
        if (d.get("remember") or "").strip():
            c["remembered_steps"] += 1
    c["used_memory"] += c["remembered_steps"] > 0
    dones = [i for i, r in enumerate(recs) if r.get("kind") == "action" and ((r.get("decision") or {}).get("action") or {}).get("type") == "done"]
    c["done_rejected"] += sum(any(x.get("kind") in ("action", "popup") for x in recs[i + 1:]) for i in dones)
    if e.get("status") == "done_unverified":
        c["second_done_accepted"] += 1
        c["second_done_scored_1"] += (ep.get("score") or 0) >= 1
    return c


def main() -> None:
    stage = sys.argv[1]
    half = sys.argv[2] if len(sys.argv) > 2 else "all"
    split = json.loads((RESULTS / "split.json").read_text())
    names = set(split[half]) if half != "all" else set(split["tasks"])
    total: Counter = Counter()
    per_task = {}
    for p in sorted((RESULTS / stage / "episodes").glob("*.json")):
        ep = json.loads(p.read_text())
        if ep["task"] not in names:
            continue
        c = effects(ep)
        per_task[ep["task"]] = dict(c)
        total += c
        total["episodes"] += 1
    out = {"stage": stage, "half": half, "total": dict(total), "tasks": per_task}
    (RESULTS / stage / f"fix_effects_{half}.json").write_text(json.dumps(out, indent=1))
    n = max(1, total["actions"])
    print(f"{stage} ({half}): {total['episodes']} episodes, {total['actions']} actions")
    print(f"  1  launches by name ok {total['launch_ok_by_name']}, by package ok {total['launch_ok']}, failed {total['launch_failed']}; "
          f"decisions on the launcher {total['on_launcher']} ({100 * total['on_launcher'] / n:.0f}%)")
    print(f"  2  'no change' decided by the mask {total['masked_no_change']}; launcher decisions with a ticking timer on screen {total['timer_chip']}")
    print(f"  3  echoed expectations {total['echoed_expectation']}")
    print(f"  4  keyboard line shown {total['keyboard_line']}; placeholders asked again {total['asked_again']}")
    print(f"  5  dones rejected {total['done_rejected']}; second dones accepted {total['second_done_accepted']}, "
          f"AndroidWorld scored {total['second_done_scored_1']} of them 1")
    print(f"  8  screens with long text {total['long_line']}")
    print(f"  10b back {total['back']} ({100 * total['back'] / n:.0f}% of actions); placeholder reasons {total['placeholder_reason']}")
    print(f"  11 steps that kept something {total['remembered_steps']}, in {total['used_memory']} episodes")
    if total["no_trace"]:
        print(f"  ({total['no_trace']} episodes without a full trace)")


if __name__ == "__main__":
    main()
