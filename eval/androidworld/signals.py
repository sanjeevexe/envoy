"""Mechanism signals per episode, measured from Envoy's trace digests, to support (not replace) reading each failure.

  python3 eval/androidworld/signals.py baseline dev            # table + eval/results/androidworld/<stage>/signals_<half>.json

Signals:
- placeholder: decisions whose reason or expected result calls the action a placeholder / wrong / required by the schema
- echo: decisions whose expected_result repeats an earlier step's verbatim (the model copying its own history)
- launcher_steps: actions taken on the home screen or app drawer (finding an app)
- bad_launch: launch actions that failed (package not installed)
- false_change: no-op actions (back on the home screen) the runtime reported as "screen changed"
- done_rejected: done decisions the runtime's success check rejected (the episode went on after them)
- first_done_step: the step of the first done decision
- looks, approvals (with what was approved)
- actions, back: decisions carried out, and how many were back (the old schema's trap: see docs/androidworld-results.md)
- launch_by_name: launches by an app's name (not a package) that opened something
- asked_again: actions the model called a placeholder, which the loop asked again instead of carrying out
"""

from __future__ import annotations

import gzip
import json
import re
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[2] / "eval" / "results" / "androidworld"
LAUNCHER = re.compile(r"^App: \S*launcher", re.I)  # the home screen / app drawer app, not an activity named *Launcher
PLACEHOLDER = re.compile(r"placeholder|schema requires|required by (the )?schema|comply with (the )?schema|wrong action|this is wrong|incorrect but", re.I)


def signals(ep: dict) -> dict:
    e = ep.get("envoy") or {}
    out = {"task": ep["task"], "score": ep.get("score"), "status": e.get("status"), "steps": e.get("iterations"),
           "budget": e.get("max_steps"), "placeholder": 0, "echo": 0, "launcher_steps": 0, "bad_launch": 0, "false_change": 0,
           "done_rejected": 0, "first_done_step": None, "looks": e.get("looks", 0), "actions": 0, "back": 0,
           "launch_by_name": 0, "asked_again": 0,
           "approvals": [a.get("description") for a in e.get("approvals") or []]}
    dig = RESULTS.parents[2] / e["trace_digest"] if e.get("trace_digest") else None
    if not dig or not dig.exists():
        return out
    rows = [json.loads(l) for l in gzip.open(dig, "rt")]
    seen_expected: set[str] = set()
    actions = [r for r in rows if r.get("kind") == "action"]
    for i, r in enumerate(actions):
        d = r.get("decision") or {}
        a = (d.get("action") or {}).get("type")
        text = f"{d.get('reason', '')} {d.get('expected_result', '')}"
        out["placeholder"] += bool(PLACEHOLDER.search(text))
        out["asked_again"] += bool(r.get("placeholder"))
        out["actions"] += 1
        out["back"] += a == "back"
        app = (d.get("action") or {}).get("app") or ""
        if a == "launch" and (r.get("result") or {}).get("ok") and "." not in app:
            out["launch_by_name"] += 1
        exp = (d.get("expected_result") or "").strip()
        if exp and exp in seen_expected and len(exp) > 15:
            out["echo"] += 1
        seen_expected.add(exp)
        head = (r.get("screen") or "").split("\n", 1)[0]
        if LAUNCHER.search(head) and a not in ("done", "fail"):
            out["launcher_steps"] += 1
            if a == "back" and r.get("changed"):
                out["false_change"] += 1
        if a == "launch" and (r.get("result") or {}).get("ok") is False:
            out["bad_launch"] += 1
        if a == "done":
            out["first_done_step"] = out["first_done_step"] or r.get("step")
            if i < len(actions) - 1:
                out["done_rejected"] += 1
    return out


def main() -> None:
    stage, half = sys.argv[1], sys.argv[2]
    sp = json.loads((RESULTS / "split.json").read_text())
    names = set(sp[half]) if half != "all" else set(sp["tasks"])
    rows = []
    for p in sorted((RESULTS / stage / "episodes").glob("*.json")):
        ep = json.loads(p.read_text())
        if ep["task"] in names:
            rows.append(signals(ep))
    (RESULTS / stage / f"signals_{half}.json").write_text(json.dumps(rows, indent=1))
    keys = ["placeholder", "echo", "launcher_steps", "bad_launch", "false_change", "done_rejected", "looks"]
    print(f"{'task':42} score status          steps " + " ".join(f"{k[:9]:>9}" for k in keys) + "  first_done approvals")
    for r in rows:
        print(f"{r['task'][:42]:42} {r['score']:<5} {str(r['status']):15} {r['steps']}/{r['budget']:<4} "
              + " ".join(f"{r[k]:>9}" for k in keys) + f"  {str(r['first_done_step']):>10} {len(r['approvals'])}")
    tot = {k: sum(r[k] for r in rows) for k in keys + ["actions", "back", "launch_by_name", "asked_again"]}
    print(f"\nAll {len(rows)} episodes: {tot['actions']} actions, back {tot['back']} ({100 * tot['back'] / max(1, tot['actions']):.0f}%), "
          f"on the launcher {tot['launcher_steps']}, placeholder reasons {tot['placeholder']}, asked again {tot['asked_again']}, "
          f"launches by name {tot['launch_by_name']}, failed launches {tot['bad_launch']}, false changes {tot['false_change']}")
    fails = [r for r in rows if (r["score"] or 0) < 0.5]
    print(f"\n{len(rows)} episodes, {len(fails)} failures. Among failures:")
    for k in keys:
        n = sum(1 for r in fails if r[k])
        print(f"  {k:15} in {n:3} failures (total {sum(r[k] for r in fails)})")


if __name__ == "__main__":
    main()
