"""AndroidWorld model comparison: the same 20 tasks under each model profile (spark, hybrid, wonder), one run each.

  uv run --project backend python eval/model_comparison.py --aw ~/Desktop/Envoy-aw-compare --date 2026-10-28

Reads AndroidWorld's episode records from the comparison checkout (eval/results/androidworld/cmp-<profile>/episodes/)
and that checkout's own cost log (calls by model, per episode run id), and writes
eval/results/androidworld/model-comparison/<date>/{comparison.json,README.md} here. The verdict paragraph is written by
hand after reading the traces; this script fills in everything that can be counted.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
PROFILES = ("spark", "hybrid", "wonder")
FULL_SUITE = 116


def episodes(aw: Path, profile: str) -> dict[str, dict[str, Any]]:
    d = aw / "eval" / "results" / "androidworld" / f"cmp-{profile}" / "episodes"
    out = {}
    for p in sorted(d.glob("*.json")) if d.exists() else []:
        r = json.loads(p.read_text())
        out[r["task"]] = r
    return out


def calls_by_model(aw: Path) -> dict[str, dict[str, int]]:
    """run id → {model: calls}, from the comparison checkout's cost log."""
    out: dict[str, dict[str, int]] = {}
    log = aw / "logs" / "model_costs.jsonl"
    for line in log.read_text().splitlines() if log.exists() else []:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("model") and e.get("task_id"):
            m = out.setdefault(e["task_id"], {})
            m[e["model"]] = m.get(e["model"], 0) + 1
    return out


def row(r: dict[str, Any], by_model: dict[str, dict[str, int]]) -> dict[str, Any]:
    e = r.get("envoy") or {}
    return {"pass": float(r.get("score") or 0) >= 1, "status": e.get("status"), "steps": e.get("steps_device"), "max_steps": e.get("max_steps"),
            "model_calls": e.get("model_calls"), "by_model": by_model.get(e.get("run_id", ""), {}), "cost_usd": e.get("cost_usd"),
            "wall_s": e.get("wall_s") or e.get("duration_s"), "result": (e.get("result") or "")[:160], "run_id": e.get("run_id"),
            "profile": (e.get("models") or {}).get("profile")}


def build(aw: Path) -> dict[str, Any]:
    by_model = calls_by_model(aw)
    data = {p: {t: row(r, by_model) for t, r in episodes(aw, p).items()} for p in PROFILES}
    tasks = sorted(set().union(*[set(v) for v in data.values()]))
    summary = {}
    for p, rows in data.items():
        if not rows:
            continue
        n = len(rows)
        models: dict[str, int] = {}
        for r in rows.values():
            for m, c in r["by_model"].items():
                models[m] = models.get(m, 0) + c
        cost = sum(r["cost_usd"] or 0 for r in rows.values())
        summary[p] = {"tasks": n, "passed": sum(r["pass"] for r in rows.values()), "steps_mean": round(sum(r["steps"] or 0 for r in rows.values()) / n, 1),
                      "wall_s_mean": round(sum(r["wall_s"] or 0 for r in rows.values()) / n, 1), "calls": sum(r["model_calls"] or 0 for r in rows.values()),
                      "calls_by_model": models, "cost_usd": round(cost, 4), "cost_per_task": round(cost / n, 4),
                      "full_suite_estimate_usd": round(cost / n * FULL_SUITE, 2)}
    return {"tasks": tasks, "profiles": data, "summary": summary}


def markdown(doc: dict[str, Any], date: str) -> str:
    s = doc["summary"]
    ps = [p for p in PROFILES if p in s]
    lines = [f"# AndroidWorld: model profiles compared ({date})", "",
             "Same 20 tasks (6 that Envoy passed and 14 it failed in the final standard-tier run), AndroidWorld seed 30, the same "
             "harness and step budgets, standard tier, one run per task per profile, per-episode cost cap $0.60 for all.", "",
             "| Profile | Success | Mean steps | Mean wall s | Model calls (by model) | Cost | Per task | 116-task estimate |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for p in ps:
        x = s[p]
        bym = ", ".join(f"{m.replace('muse-', '')} {c}" for m, c in sorted(x["calls_by_model"].items()))
        lines.append(f"| {p} | {x['passed']}/{x['tasks']} | {x['steps_mean']} | {x['wall_s_mean']} | {x['calls']} ({bym}) | ${x['cost_usd']:.2f} | "
                     f"${x['cost_per_task']:.3f} | ${x['full_suite_estimate_usd']:.2f} |")
    lines += ["", "| Task | " + " | ".join(ps) + " |", "| --- | " + " | ".join("---" for _ in ps) + " |"]
    for t in doc["tasks"]:
        cells = []
        for p in ps:
            r = doc["profiles"][p].get(t)
            cells.append("—" if r is None else f"{'**pass**' if r['pass'] else 'fail'} ({r['status']}, {r['steps']} steps, ${r['cost_usd'] or 0:.3f})")
        lines.append(f"| {t} | " + " | ".join(cells) + " |")
    lines += ["", "Files: `comparison.json` (every number above), `traces/<profile>.md` (each episode's plan and actions with the agent's "
              "reasons), `raw/<profile>/` (AndroidWorld's episode records and Envoy's traces, copied from the comparison checkout)."]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aw", default=str(Path.home() / "Desktop" / "Envoy-aw-compare"))
    ap.add_argument("--date", required=True)
    args = ap.parse_args()
    doc = build(Path(args.aw).expanduser())
    out = REPO / "eval" / "results" / "androidworld" / "model-comparison" / args.date
    out.mkdir(parents=True, exist_ok=True)
    (out / "comparison.json").write_text(json.dumps(doc, indent=1))
    md = out / "README.md"
    verdict = md.read_text().split("## Verdict", 1)[1] if md.exists() and "## Verdict" in md.read_text() else "\n\n(to be written after reading the traces)\n"
    md.write_text(markdown(doc, args.date) + "\n## Verdict" + verdict)
    print(json.dumps(doc["summary"], indent=1))


if __name__ == "__main__":
    main()
