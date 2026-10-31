"""Build the showcase site's data (site/data/) from what the repo records. No model calls, no devices.

  uv run --project backend python scripts/build_site_data.py           # rebuild site/data/ from the repo
  uv run --project backend python scripts/build_site_data.py import    # re-import the recorded runs, then rebuild

The default build reads only files committed in this repo: eval/results/, data/routines/, docs/ and the recordings already
imported into site/data/recordings/. It is deterministic: the same checkout gives the same files, byte for byte. After the
Nov 2 eval, `eval/run_final.py report` rewrites eval/results/final/; run the default build and the site's numbers follow.

`import` copies a few recorded runs into site/data/recordings/ from where they were recorded (run traces and phone frames are
gitignored, so they live in the checkout and API copy that ran them). Every frame it copies was looked at by hand for
private data first (site/README.md has the checklist). It needs those source folders; the build after it does not.
"""

from __future__ import annotations

import gzip
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "site"
DATA = SITE / "data"
IMG = DATA / "img"
REC = DATA / "recordings"
ET = ZoneInfo("America/New_York")

# The repo goes public later, on the user's click. Until then source links are relative to site/ (they work from a checkout).
REPO_URL = ""  # e.g. "https://github.com/<owner>/<repo>/blob/main/" once public

# ---------------------------------------------------------------------------------------------------------------------------
# import: recorded runs from outside the repo
# ---------------------------------------------------------------------------------------------------------------------------

HOME = Path.home()
LOOP_A = HOME / "Desktop/Envoy/.claude/worktrees/loop-reliability-b4a982"  # loop A's checkout (Oct 30 reliability loop)
LOOP_A_API = Path("/private/tmp/claude-501/-Users-sanjeevvarma-Desktop-Envoy--claude-worktrees-loop-reliability-b4a982/"
                  "ee90bfe5-618d-4f75-a73e-0d9f0316cf50/scratchpad/api8750")  # loop A's API copy on :8750 (its frames)

# Each recording: where its trace, frames and model-call log are. Frames are looked at before they are listed here.
RECORDINGS = {
    "starbucks-first": {
        "kind": "agent",
        "app": "Starbucks",
        "task_id": "task-1030-155711-51c2",
        "trace": LOOP_A / "data/runs/task-1030-155711-51c2-r1",
        "api": LOOP_A_API,
        "costs": LOOP_A / "logs/model_costs.jsonl",
        "device": "envoy-real, an Android emulator signed in to Google's Play Store; no Starbucks account",
        "where": "loop A (prompts/loop-reliability.md), Oct 30",
    },
    "starbucks-replay": {
        "kind": "routine",
        "app": "Starbucks",
        "task_id": "task-1030-204136-b8d5",
        "trace": LOOP_A / "data/runs/task-1030-204136-b8d5-r1",
        "api": LOOP_A_API,
        "costs": LOOP_A / "logs/model_costs.jsonl",
        "device": "envoy-real, an Android emulator; no Starbucks account",
        "where": "loop A (prompts/loop-reliability.md), Oct 30, after the emulator's cold reboot",
    },
}


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _tree(trace: Path, rel: str) -> dict:
    with gzip.open(trace / rel) as f:
        return json.load(f)


def _calls(costs: Path, task_id: str) -> list[dict]:
    """The model calls a task made, from the checkout's cost log (one line per call, its job and model)."""
    out = []
    for r in _read_jsonl(costs):
        if (r.get("task_id") or "").startswith(task_id) and r["job"] != "compile":  # compiling is its own step, after the run
            end = datetime.fromisoformat(r["time"]).timestamp()
            out.append({"job": r["job"], "model": r["model"], "ms": round(r["latency_ms"]), "usd": round(r["cost_usd"], 6),
                        "end": round(end, 3)})
    return sorted(out, key=lambda c: c["end"])


def _frame(src: Path, name: str) -> str:
    """Copy one recorded phone frame as webp. The pixels are the recording's own; only the encoding changes."""
    IMG.mkdir(parents=True, exist_ok=True)
    out = IMG / f"{name}.webp"
    Image.open(src).convert("RGB").save(out, "WEBP", quality=82, method=6)
    return f"img/{out.name}"


def import_agent(name: str, cfg: dict) -> dict:
    trace, api, task_id = cfg["trace"], cfg["api"], cfg["task_id"]
    db = sqlite3.connect(f"file:{api / 'envoy.db'}?mode=ro", uri=True)  # read only; never TaskStore() on an API's db
    created, device = db.execute("select created_at, device from tasks where id=?", (task_id,)).fetchone()
    shots = [json.loads(d)["shot"] for (d,) in db.execute(
        "select data from steps where task_id=? order by seq", (task_id,)) if json.loads(d).get("kind") == "action"]
    db.close()
    calls = _calls(cfg["costs"], task_id)
    trace_steps = _read_jsonl(trace / "steps.jsonl")
    run = json.loads((trace / "run.json").read_text())
    plan = next(s for s in trace_steps if s["kind"] == "plan")
    actions = [s for s in trace_steps if s["kind"] == "action"]
    assert len(actions) == len(shots), (len(actions), len(shots))

    steps = []
    for i, s in enumerate(actions):
        act = s["decision"]["action"]
        tree = _tree(trace, s["tree_before"])
        box, box_kind, frame = None, None, None
        if act["type"] == "done":
            # The answer screen: its own frame, and the element whose text the answer was read from.
            frame = _frame(api / "shots" / shots[i], f"{name}-{i + 1:02d}")
            hit = [e for e in tree["elements"] if e["text"] and e["text"] == act.get("result")]
            if hit:
                box, box_kind = hit[0]["bounds"], "read"
        else:
            # A frame is saved after each action, so the screen this step acted on is the previous step's frame.
            if i > 0:
                frame = _frame(api / "shots" / shots[i - 1], f"{name}-{i + 1:02d}")
            hit = [e for e in tree["elements"] if e.get("number") == act.get("element")]
            if hit:
                box, box_kind = hit[0]["bounds"], "tap"
        compact = s["screen_before"]["compact"]
        steps.append({
            "n": i + 1,
            "t": round(s["time"] - created, 1),
            "action": act,
            "text": None,
            "reason": s["decision"]["reason"],
            "expected": s["decision"].get("expected_result"),
            "risk": (s.get("risk") or {}).get("level"),
            "frame": frame,
            "box": box,
            "box_kind": box_kind,
            "screen": [tree["width"], tree["height"]],
            "model_ms": s["timings_ms"].get("model"),
            "usd": round(s["cost_usd"], 6),
            "compact": compact,
        })
    # The action's own words, as the API showed them ("tap \"Order\"").
    db = sqlite3.connect(f"file:{api / 'envoy.db'}?mode=ro", uri=True)
    texts = [json.loads(d)["text"] for (d,) in db.execute(
        "select data from steps where task_id=? order by seq", (task_id,)) if json.loads(d).get("kind") == "action"]
    finish = [json.loads(d) for (d,) in db.execute(
        "select data from steps where task_id=? order by seq", (task_id,)) if json.loads(d).get("kind") in ("finish", "app_notes")]
    db.close()
    for st, txt in zip(steps, texts):
        st["text"] = txt
    for st in steps:  # model calls and dollars so far, from the cost log, at the moment each step was decided
        st["calls_so_far"] = sum(1 for c in calls if c["end"] <= created + st["t"] + 0.5)
        st["usd_so_far"] = round(sum(c["usd"] for c in calls if c["end"] <= created + st["t"] + 0.5), 6)
    notes = next((f for f in finish if f["kind"] == "app_notes"), None)
    return {
        "id": name, "kind": "agent", "app": cfg["app"], "package": run.get("plan", {}).get("app") and _package(trace),
        "task_id": task_id, "device": device, "device_note": cfg["device"], "where": cfg["where"],
        "started_et": datetime.fromtimestamp(created, ET).strftime("%Y-%m-%d %H:%M:%S"),
        "goal": run["goal"], "answer": run["result"], "status": run["status"],
        "plan": {"subgoals": plan["plan"]["subgoals"], "usd": round(plan["cost_usd"], 6), "model_ms": plan["model_ms"],
                 "t": round(plan["time"] - created, 1)},
        "steps": steps,
        "calls": [{k: c[k] for k in ("job", "model", "ms", "usd")} | {"t": round(c["end"] - created, 1)} for c in calls],
        "app_notes": [a["text"] for a in (notes or {}).get("applied", [])],
        "check": run.get("check"),
    }


def _package(trace: Path) -> str:
    for s in _read_jsonl(trace / "steps.jsonl"):
        if s.get("screen_before"):
            return s["screen_before"]["package"]
    return ""


def import_routine(name: str, cfg: dict) -> dict:
    trace, api, task_id = cfg["trace"], cfg["api"], cfg["task_id"]
    db = sqlite3.connect(f"file:{api / 'envoy.db'}?mode=ro", uri=True)
    created, device, routine = db.execute("select created_at, device, routine from tasks where id=?", (task_id,)).fetchone()
    db.close()
    run = json.loads((trace / "run.json").read_text())
    calls = _calls(cfg["costs"], task_id)
    steps = []
    for s in _read_jsonl(trace / "steps.jsonl"):
        if s.get("kind") != "routine_step":
            continue
        steps.append({"n": s["step"], "id": s["id"], "status": s["status"], "rung": s["rung"], "rungs": s["rungs"],
                      "ms": s["timings_ms"], "t": round(s["time"] - created, 2), "detail": s["detail"],
                      "repairs": len(s["repairs"])})
    return {
        "id": name, "kind": "routine", "app": cfg["app"], "task_id": task_id, "device": device, "device_note": cfg["device"],
        "where": cfg["where"], "started_et": datetime.fromtimestamp(created, ET).strftime("%Y-%m-%d %H:%M:%S"),
        "routine": run["routine"], "version": run["version"], "status": run["status"], "outputs": run["outputs"],
        "routine_s": run["duration_s"], "routine_calls": run["model_calls"], "steps": steps,
        "calls": [{k: c[k] for k in ("job", "model", "ms", "usd")} | {"t": round(c["end"] - created, 1)} for c in calls],
    }


def do_import() -> None:
    REC.mkdir(parents=True, exist_ok=True)
    for name, cfg in RECORDINGS.items():
        rec = import_agent(name, cfg) if cfg["kind"] == "agent" else import_routine(name, cfg)
        (REC / f"{name}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n")
        print(f"imported {name}: {len(rec['steps'])} steps")


# ---------------------------------------------------------------------------------------------------------------------------
# build: everything below reads only the repo
# ---------------------------------------------------------------------------------------------------------------------------

def rel(path: Path | str) -> str:
    return str(path if isinstance(path, str) else path.relative_to(REPO))


def src(path: str, note: str = "") -> dict:
    return {"path": path, "note": note} if note else {"path": path}


def loop_a_runs() -> dict[str, dict]:
    """Loop A's runs by task id (first runs and replays; a compile row shares its source run's id, so it is left out)."""
    return {r["task_id"]: r for r in _read_jsonl(REPO / "eval/results/real-apps/loop-a/runs.jsonl")
            if r.get("task_id") and r.get("mode") != "compile"}


def claim() -> dict:
    """The claim and 'what is actually new', from the design doc's Overview."""
    doc = (REPO / "docs/technical-design.md").read_text()
    overview = doc.split("## Overview", 1)[1].split("\n## ", 1)[0]
    lead = re.search(r"\*\*(Envoy gives AI agents a phone layer[^*]+)\*\*", overview).group(1)
    pitch = re.search(r"\*\*Pitch:\*\* \*(.+?)\*", overview).group(1)
    new_block = overview.split("**What is actually new.**", 1)[1]
    prior = new_block.split("\n", 1)[0].strip()
    items = re.findall(r"^\d\. \*\*(.+?)\*\* (.+)$", new_block, re.M)
    return {"lead": lead, "pitch": pitch, "prior": prior, "new": [{"title": t.rstrip("."), "text": x} for t, x in items],
            "src": src("docs/technical-design.md", "Overview")}


def routine_yaml(path: Path) -> dict:
    r = yaml.safe_load(path.read_text())
    steps = []
    for s in r["steps"]:
        action = s.get("action", {})
        kind = next(iter(action)) if action else "?"
        steps.append({"id": s["id"], "intent": s.get("intent", ""), "optional": bool(s.get("optional")),
                      "risk": s.get("risk"), "pre": [_check(c) for c in s.get("pre", [])],
                      "action": _action(kind, action.get(kind)), "post": [_check(c) for c in s.get("post", [])],
                      "extract": list((s.get("extract") or {}).keys())})
    return {"routine": r["routine"], "app": r["app"], "version": r["version"], "intent": r.get("intent"),
            "inputs": {k: {"type": v.get("type"), "example": v.get("example")} for k, v in (r.get("inputs") or {}).items()},
            "outputs": r.get("outputs", []), "steps": steps}


def _check(c) -> str:
    """One before/after check, in a line a person can read. Checks are code; this only prints them."""
    if isinstance(c, str):
        return c
    (k, v), = c.items()
    if k == "app_foreground":
        return f"app in front: {v}"
    if k == "screen_changed":
        return "the screen changed"
    if k in ("element_present", "element_absent"):
        label = v.get("text") or v.get("text_has") or v.get("desc")
        what = f"“{label}”" if label else f"id {v.get('resource_id')}"
        kind = (v.get("kind") or "element").lower()
        rid = f" (id {v['resource_id']})" if label and v.get("resource_id") else ""
        return f"{what} {kind}{rid} {'is on screen' if k == 'element_present' else 'is gone'}"
    if k == "screen_has":
        return f"screen shows: {v.get('text') if isinstance(v, dict) else v}"
    return f"{k}: {json.dumps(v, ensure_ascii=False)}"


def _action(kind: str, v) -> str:
    if kind == "tap" and isinstance(v, dict):
        who = v.get("text") or v.get("text_has") or v.get("desc") or v.get("resource_id") or "element"
        return f"tap {who!s}"
    if kind == "scroll_until" and isinstance(v, dict):
        t = v.get("target", {})
        return f"scroll {v.get('direction', 'down')} until {t.get('text_has') or t.get('text')} (max {v.get('max_scrolls')})"
    if kind == "type" and isinstance(v, dict):
        return f"type {v.get('value')}"
    return kind


def first_run() -> dict:
    rec = json.loads((REC / "starbucks-first.json").read_text())
    runs = loop_a_runs()
    row = runs[rec["task_id"]]
    rec["total"] = {"seconds": row["seconds"], "calls": row["calls"], "usd": row["usd"], "jobs": row["jobs"],
                    "commit": row["commit"], "src": src("eval/results/real-apps/loop-a/runs.jsonl", rec["task_id"])}
    rec["src"] = src("site/data/recordings/starbucks-first.json", "imported from loop A's trace and API copy")
    return rec


def learned() -> dict:
    runs = loop_a_runs()
    first = runs["task-1030-155711-51c2"]
    compile_row = next(r for r in _read_jsonl(REPO / "eval/results/real-apps/loop-a/runs.jsonl")
                       if r.get("mode") == "compile" and r.get("task_id") == "task-1030-155711-51c2")
    replay = json.loads((REC / "starbucks-replay.json").read_text())
    rrow = runs[replay["task_id"]]
    new_input = runs["task-1030-201551-c3b9"]
    lib = REPO / "data/routines/starbucks_drink_calories"
    index = json.loads((lib / "index.json").read_text())
    compiled = routine_yaml(REPO / "eval/results/real-apps/loop-a/compiled/loop_starbucks-v1.yaml")
    active = routine_yaml(lib / f"v{index['active']}.yaml")

    def counters(r: dict) -> dict:
        return {"seconds": r["seconds"], "calls": r["calls"], "usd": r["usd"], "jobs": r["jobs"], "commit": r["commit"],
                "task_id": r["task_id"], "answer": r.get("answer"), "goal": r.get("goal"),
                "src": src("eval/results/real-apps/loop-a/runs.jsonl", r["task_id"])}

    return {
        "compiled": compiled | {"src": src("eval/results/real-apps/loop-a/compiled/loop_starbucks-v1.yaml")},
        "active": active | {"src": src(f"data/routines/starbucks_drink_calories/v{index['active']}.yaml")},
        "versions": [{"version": v["version"], "status": v["status"], "created": v["created"], "changes": v["changes"],
                      "by": "self-repair" if v.get("source_task") else (v.get("verification") or {}).get("by", ""),
                      "trial": v.get("trial")} for v in index["versions"]],
        "versions_src": src("data/routines/starbucks_drink_calories/index.json"),
        "compile": {"seconds": compile_row["seconds"], "usd": compile_row["usd"], "steps": compile_row["steps"],
                    "inputs": compile_row["inputs"], "warnings": compile_row.get("warnings", []),
                    "commit": compile_row["commit"], "src": src("eval/results/real-apps/loop-a/runs.jsonl", "mode compile")},
        "first": counters(first),
        "replay": counters(rrow) | {"routine_s": replay["routine_s"], "routine_calls": replay["routine_calls"],
                                    "version": replay["version"]},
        "replay_steps": replay["steps"],
        "replay_calls": replay["calls"],
        "replay_src": src("site/data/recordings/starbucks-replay.json", "imported from loop A's trace"),
        "new_input": counters(new_input),
        "table_src": src("eval/results/real-apps/table.md", "Starbucks rows"),
    }


def build() -> dict:
    data = {
        "meta": {"repo_url": REPO_URL},
        "claim": claim(),
        "first_run": first_run(),
        "learned": learned(),
    }
    DATA.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=1, ensure_ascii=False, sort_keys=False)
    (DATA / "site-data.json").write_text(text + "\n")
    # A script, not fetched JSON, so the page also works when opened from file://.
    (DATA / "site-data.js").write_text("window.ENVOY = " + text + ";\n")
    return data


if __name__ == "__main__":
    if sys.argv[1:] == ["import"]:
        do_import()
    elif sys.argv[1:]:
        sys.exit(__doc__)
    d = build()
    print(f"built site/data/site-data.js ({len(json.dumps(d)) // 1024} KB)")
