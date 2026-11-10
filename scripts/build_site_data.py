"""Build the showcase site's data (site/data/) from what the repo records. No model calls, no devices.

  uv run --project backend python scripts/build_site_data.py           # rebuild site/data/ from the repo
  uv run --project backend python scripts/build_site_data.py import    # re-import the recorded runs, then rebuild

The default build reads only files committed in this repo: eval/results/, data/routines/, docs/ and the recordings already
imported into site/data/recordings/. It is deterministic: the same checkout gives the same files, byte for byte. After the
Nov 3 eval, `eval/run_final.py report` rewrites eval/results/final/; run the default build and the site's numbers follow.

`import` copies a few recorded runs into site/data/recordings/ from where they were recorded (run traces and phone frames are
gitignored, so they live in the checkout and API copy that ran them). Every frame it copies was looked at by hand for
private data first (site/README.md has the checklist). It needs those source folders; the build after it does not.
"""

from __future__ import annotations

import gzip
import json
import re
import sqlite3
import statistics
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

# Source links point at the public repo (the site is served from GitHub Pages, where ../ would leave the site). Set it to ""
# to make them relative to site/ again (they work from a checkout).
REPO_URL = "https://github.com/sanjeevexe/envoy/blob/main/"

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
        "where": "loop A, Oct 30",
    },
    "starbucks-replay": {
        "kind": "routine",
        "app": "Starbucks",
        "task_id": "task-1030-204136-b8d5",
        "trace": LOOP_A / "data/runs/task-1030-204136-b8d5-r1",
        "api": LOOP_A_API,
        "costs": LOOP_A / "logs/model_costs.jsonl",
        "device": "envoy-real, an Android emulator; no Starbucks account",
        "where": "loop A, Oct 30, after the emulator's cold reboot",
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


MAIN = HOME / "Desktop/Envoy"  # the main checkout: its gitignored run traces and the demo world's memory

def import_repair_call() -> dict:
    """The model call behind Starbucks v3's self-repair (loop A, Oct 30), from loop A's cost log."""
    calls = _calls(LOOP_A / "logs/model_costs.jsonl", "task-1030-170124-e3c3")
    rep = [c for c in calls if c["job"] == "repair"]
    return {"task_id": "task-1030-170124-e3c3", "repair_calls": [{k: c[k] for k in ("job", "model", "ms", "usd")} for c in rep]}


def import_planted() -> dict:
    """A planted instruction on SkyLark's trip screen (the injection suite, Oct 28), and what the agent did with it."""
    run = MAIN / "data/runs/f7-1028004422-inj-trip_notice-add_ktn-agent-r0"
    steps = [s for s in _read_jsonl(run / "steps.jsonl") if s.get("kind") == "action"]
    s13 = next(s for s in steps if s["step"] == 13)
    tree = _tree(run, s13["tree_before"])
    notice = [e["bounds"] for e in tree["elements"]
              if (e["text"] or "").startswith(("Message from SkyLark", "SYSTEM MESSAGE"))]
    box = [min(b[0] for b in notice), min(b[1] for b in notice), max(b[2] for b in notice), max(b[3] for b in notice)]
    mentions = [{"step": s["step"], "reason": s["decision"]["reason"]} for s in steps
                if "inject" in s["decision"]["reason"].lower()]
    r = json.loads((run / "run.json").read_text())
    taps = [s["device_action"]["kind"] for s in steps if s.get("device_action")]
    return {"run": run.name, "goal": r["goal"], "status": r["status"], "result": r["result"], "model_calls": r["model_calls"],
            "usd": round(r["cost_usd"], 4), "seconds": r["duration_s"], "steps": len(steps), "frame": _frame(run / "screens/013_before.png", "planted-trip-notice"),
            "box": box, "screen": [tree["width"], tree["height"]], "mentions": mentions,
            "risks": sorted({(s.get("risk") or {}).get("level") or "none" for s in steps}), "actions": len(taps)}


def import_approval() -> dict:
    """An approval a SkyLark routine asked for before an irreversible tap (loop A's copy, Oct 30)."""
    db = sqlite3.connect(f"file:{LOOP_A_API / 'envoy.db'}?mode=ro", uri=True)
    row = db.execute("select id, task_id, created_at, status, description, reasons, screenshot, decided_at, decided_by "
                     "from approvals where id='appr-1030-134627-2fca'").fetchone()
    db.close()
    aid, task, created, status, desc, reasons, shot, decided, by = row
    return {"id": aid, "task_id": task, "asked_et": datetime.fromtimestamp(created, ET).strftime("%Y-%m-%d %H:%M:%S"),
            "status": status, "description": desc, "reasons": json.loads(reasons), "decided_by": by,
            "wait_s": round(decided - created, 1), "frame": _frame(LOOP_A_API / "approvals" / shot, "approval-skylark")}


def import_sam() -> dict:
    """SAM 3.1 on SkyLark's drawn seat map: the box Spark picked, and where the step model alone would have tapped."""
    run = MAIN / "data/runs/p6-canvas-src"
    s = next(x for x in _read_jsonl(run / "steps.jsonl") if x.get("vision"))
    v = s["vision"]
    r = json.loads((run / "run.json").read_text())
    return {"run": run.name, "goal": r["goal"], "target": v["target"], "box": v["box"], "model_point": v["model_point"],
            "tap": [s["device_action"]["x"], s["device_action"]["y"]], "candidates": v["candidates"], "calls": v["calls"],
            "usd": round(v["cost_usd"], 5), "ms": v["ms"], "screen": v["size"], "reason": s["decision"]["reason"],
            "frame": _frame(run / s["screenshot_before"], "sam-seat-map"),
            "recorded_et": datetime.fromtimestamp(s["time"], ET).strftime("%Y-%m-%d %H:%M")}


def import_memory() -> dict:
    """A slice of the demo world's memory (SkyLark's test inbox and app; the test persona), read only with SQLite."""
    db = sqlite3.connect(f"file:{MAIN / 'data/demo/memory.db'}?mode=ro", uri=True)
    q = lambda sql, *a: db.execute(sql, a).fetchall()
    kinds = {sid: (kind, json.loads(ref or "{}")) for sid, kind, ref in q("select id, kind, reference from sources")}

    def facts(entity: str) -> list[dict]:
        out = []
        for fid, attr, val, vfrom, vto, obs, sup in q(
                "select id, attribute, value, valid_from, valid_to, observed_at, superseded_by from facts where entity=? "
                "order by attribute, observed_at", entity):
            seen = q("select source, observed_at from fact_sources where fact=? order by observed_at", fid)
            by_kind: dict[str, int] = {}
            for sid, _ in seen:
                by_kind[kinds[sid][0]] = by_kind.get(kinds[sid][0], 0) + 1
            first_sid = seen[0][0] if seen else None
            first = kinds.get(first_sid, ("", {}))
            out.append({"attribute": attr, "value": val, "current": vto is None,
                        "replaced_et": datetime.fromtimestamp(vto, ET).strftime("%Y-%m-%d %H:%M") if vto else None,
                        "sources": by_kind, "seen": len(seen),
                        "first_et": datetime.fromtimestamp(seen[0][1], ET).strftime("%Y-%m-%d %H:%M") if seen else None,
                        "last_et": datetime.fromtimestamp(seen[-1][1], ET).strftime("%Y-%m-%d %H:%M") if seen else None,
                        "first_source": {"kind": first[0], "subject": first[1].get("subject"), "app": first[1].get("app")}})
        return out

    ents = {name: eid for eid, name in q("select id, name from entities where merged_into is null")}
    pick = ["SL 482 · Fri, Oct 30, 2026", "SL 1190 · Sat, Nov 14, 2026", "Denver · Fri, Dec 4, 2026"]
    out = {"entities": [{"name": n, "type": q("select type from entities where id=?", ents[n])[0][0], "facts": facts(ents[n])}
                        for n in pick],
           "counts": {t: c for t, c in q("select type, count(*) from entities where merged_into is null group by type")},
           "sources": {k: c for k, c in q("select kind, count(*) from sources group by kind")},
           "promos": [json.loads(r)["subject"] for (r,) in q("select reference from sources where reference like '%promo%'")]}
    db.close()
    return out


TEACH = HOME / "Library/Application Support/Claude/side-session-notes/local_f74ba43d-3237-4122-ab43-ffe3c799c156/teach-recordings"


def import_teach() -> dict:
    """Teach mode's recordings (Oct 31, eval/teach_person.py): a scripted person shows a task once through the live view,
    the compiler turns it into a routine, and Envoy replays it on its own. Google Calendar on the envoy3955 test account."""
    cal = TEACH / "calendar_dentist_today"
    demo_run = json.loads((cal / "demonstration/run.json").read_text())
    demo = [s for s in _read_jsonl(cal / "demonstration/steps.jsonl") if s["decision"]["action"]["type"] != "done"]
    t0 = demo[0]["time"]
    steps = []
    for s in demo:
        tg, act = s["target"], s["device_action"]
        steps.append({"n": s["step"], "kind": act["kind"], "label": tg.get("label") or tg.get("text") or tg.get("desc"),
                      "typed": act.get("text"), "box": tg["bounds"], "t": round(s["time"] - t0, 1),
                      "frame": _frame(cal / "demonstration" / s["screenshot_before"], f"teach-shown-{s['step']:02d}")})
    rtask = json.loads((cal / "replay_task.json").read_text())
    rrun = json.loads((cal / "replay_trace/run.json").read_text())
    rsteps = [s for s in _read_jsonl(cal / "replay_trace/steps.jsonl") if s.get("kind") == "routine_step"]
    shots = [s["shot"] for s in rtask["steps"] if s.get("kind") == "routine_step"]
    replay = [{"id": s["id"], "status": s["status"], "rung": s["rung"], "rungs": s["rungs"], "ms": s["timings_ms"]["total"],
               "frame": _frame(cal / "replay_shots" / Path(shot).name, f"teach-replay-{i + 1:02d}")}
              for i, (s, shot) in enumerate(zip(rsteps, shots))]
    y = yaml.safe_load((cal / "routine_saved.yaml").read_text())
    sky = TEACH / "skylark_flight_status"
    sky_demo = json.loads((sky / "demonstration/run.json").read_text())
    sky_run = json.loads((sky / "replay_trace/run.json").read_text())
    sky_y = yaml.safe_load((sky / "routine_saved.yaml").read_text())
    return {
        "calendar": {
            "goal": demo_run["goal"], "task_id": demo_run["task_id"], "app": y["app"],
            "shown_et": datetime.fromtimestamp(t0, ET).strftime("%Y-%m-%d %H:%M"), "shown_s": demo_run["duration_s"],
            "shown_calls": demo_run["model_calls"], "steps": steps,
            "routine": {"name": y["routine"], "version": y["version"], "inputs": {k: v.get("example") for k, v in y["inputs"].items()},
                        "steps": [{"id": s["id"], "intent": s["intent"]} for s in y["steps"]],
                        "compiler": y["compiled_from"]["compiler"], "usd": y["compiled_from"]["cost_usd"]},
            "replay": {"task_id": rtask["task"]["id"], "status": rrun["status"], "seconds": rrun["duration_s"],
                       "calls": rrun["model_calls"], "steps": replay},
        },
        "skylark": {"goal": sky_demo["goal"], "shown_s": sky_demo["duration_s"], "steps": sky_demo["steps"],
                    "answer": sky_demo["result"], "routine": sky_y["routine"], "usd": sky_y["compiled_from"]["cost_usd"],
                    "replay_s": sky_run["duration_s"], "replay_calls": sky_run["model_calls"],
                    "replay_output": next(iter(sky_run["outputs"].values()), "")},
    }


def do_import() -> None:
    REC.mkdir(parents=True, exist_ok=True)
    for name, cfg in RECORDINGS.items():
        rec = import_agent(name, cfg) if cfg["kind"] == "agent" else import_routine(name, cfg)
        (REC / f"{name}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n")
        print(f"imported {name}: {len(rec['steps'])} steps")
    for name, fn in [("starbucks-repair", import_repair_call), ("planted", import_planted),
                     ("approval", import_approval), ("sam", import_sam), ("memory", import_memory), ("teach", import_teach)]:
        (REC / f"{name}.json").write_text(json.dumps(fn(), indent=1, ensure_ascii=False) + "\n")
        print(f"imported {name}")


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
    rec["src"] = src("site/data/recordings/starbucks-first.json", "imported from the run's trace")
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
        "replay_src": src("site/data/recordings/starbucks-replay.json", "imported from the run's trace"),
        "new_input": counters(new_input),
        # Every Starbucks first run and replay in the Oct 30 reliability loop, as medians with their range (rows across the
        # loop's code versions; the replay above is one of them, not the typical one).
        "loop": {mode: {"seconds": _spread([r["seconds"] for r in rows]), "calls": _spread([r["calls"] for r in rows]),
                        "commits": len({r["commit"] for r in rows})}
                 for mode in ("first", "replay")
                 for rows in [[r for r in runs.values() if r.get("task") in ("starbucks", "starbucks2") and r["mode"] == mode
                               and r.get("ok") is True]]},
        "table_src": src("eval/results/real-apps/table.md", "Starbucks rows"),
        # The replays after the last version was made: how many ran clean (2 calls: match and read the answer)
        "after_last": (lambda rows: {"n": len(rows), "clean": sum(1 for r in rows if r["calls"] <= 2), "version": index["active"]})(
            [r for r in runs.values() if r.get("task") in ("starbucks", "starbucks2") and r["mode"] == "replay"
             # the run's time is UTC; the version's is the Mac's (ET)
             and datetime.fromisoformat(r["time"]) >= datetime.fromisoformat(
                 next(v["created"] for v in index["versions"] if v["version"] == index["active"])).replace(tzinfo=ET)]),
    }


def md_tables(text: str) -> list[list[dict]]:
    """Every Markdown table in a file, as rows of {header: cell}. Cells stay as written (the site quotes them)."""
    tables, lines = [], text.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            head = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            rows, i = [], i + 2
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                rows.append(dict(zip(head, cells)))
                i += 1
            tables.append(rows)
        else:
            i += 1
    return tables


def plain(md: str) -> str:
    """Markdown cell text as plain text: links to their words, no bold or code marks."""
    md = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", md)
    return md.replace("**", "").replace("`", "")


def image(src_path: Path, name: str, width: int | None = None, crop: tuple[int, int, int, int] | None = None) -> str:
    """A repo image (chart, diagram, capture) as webp in site/data/img/. `crop` keeps one part of a capture (a window, a
    column); the pixels kept are the capture's own."""
    IMG.mkdir(parents=True, exist_ok=True)
    im = Image.open(src_path).convert("RGB")
    if crop:
        im = im.crop(crop)
    if width and im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    out = IMG / f"{name}.webp"
    im.save(out, "WEBP", quality=86, method=6)
    return f"img/{out.name}"


def eval_status() -> dict:
    """Which suites ran on the eval-final tag, from report.md's own first lines."""
    rep = (REPO / "eval/results/final/report.md").read_text()
    m = re.search(r"\*\*Ran on:\*\* (\d+) of (\d+) suites on the `eval-final` tag", rep)
    on, of = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    return {"on_tag": on, "suites": of, "final": of > 0 and on == of, "src": src("eval/results/final/report.md")}


def repair() -> dict:
    change = json.loads((REPO / "eval/results/final/change.json").read_text())
    md = (REPO / "eval/results/final/change.md").read_text()
    layouts = next(t for t in md_tables(md) if t and "Layout" in t[0])
    exp = next(e for e in change["experiments"] if e["task"] == "check_in" and e["layout"] == 3)
    lib = REPO / "eval/results/final/library/change/check_in-L3/skylark_check_in_flight"
    patch = json.loads((lib / "history/v2/patches.json").read_text())[0]
    v1 = (lib / "v1.yaml").read_text().splitlines()
    v2 = (lib / "v2.yaml").read_text().splitlines()
    import difflib
    diff = [l for l in difflib.unified_diff(v1, v2, "v1.yaml", "v2.yaml", lineterm="", n=1)]
    code = change["meta"]["code"]
    pick = lambda r: {k: r.get(k) for k in ("passed", "status", "rung", "duration_s", "calls", "standard_usd", "version")}
    skylark = {
        "task": "Check me in for my flight", "routine": exp["routine"], "layout": "3: extra screen",
        "patch": patch["description"], "reason": patch["evidence"]["reasons"][0],
        "repair_model": change["meta"]["models"]["jobs"]["repair"]["model"],
        "profile": _profile(change["meta"]["models"]["jobs"]), "tier": change["meta"]["models"]["tier"],
        "first": pick(exp["first"]), "trial": pick(exp["trial"]), "after": pick(exp["after"]), "back": pick(exp["backcompat"]),
        "steps_first": exp["first"]["steps"],
        "before": image(lib / "history/v2/repair_08_1_before.png", "repair-skylark-before"),
        "after_img": image(lib / "history/v2/repair_08_1_after.png", "repair-skylark-after"),
        "diff": diff, "commit": code["short"], "dirty": bool(code.get("dirty")), "date": change["meta"]["started"][:10],
        "src": src("eval/results/final/change.json", "check_in, layout 3"),
        "lib_src": src(rel(lib / "history/v2/patches.json")),
    }
    # Real apps: the self-repairs in the library, and what their trials decided.
    real = []
    for idx in sorted((REPO / "data/routines").glob("*/index.json")):
        ix = json.loads(idx.read_text())
        if ix["name"].startswith("skylark_"):
            continue
        for v in ix["versions"]:
            if v.get("source_task"):
                real.append({"routine": ix["name"], "version": v["version"], "status": v["status"],
                             "passed": (v.get("trial") or {}).get("passed"), "changes": v["changes"]})
    sb = json.loads((REPO / "data/routines/starbucks_drink_calories/index.json").read_text())
    v3 = next(v for v in sb["versions"] if v["version"] == 3)
    call = json.loads((REC / "starbucks-repair.json").read_text())["repair_calls"][0]
    reason = json.loads((REPO / "data/routines/starbucks_drink_calories/history/v3/patches.json").read_text())[0]["evidence"]["reasons"][0]
    return {
        "skylark": skylark,
        "layouts": [{k: plain(v) for k, v in r.items()} for r in layouts],
        "layouts_src": src("eval/results/final/change.md", "Injected UI changes"),
        "new_inputs": next((r for r in md_tables(md)[0] if "All" in r.get("Task", "")), {}),
        "real": real, "real_src": src("data/routines", "*/index.json, versions with a source_task"),
        "starbucks": {"change": v3["changes"][0], "trial": v3["trial"], "reason": reason, "call": call,
                      "src": src("data/routines/starbucks_drink_calories/index.json", "v3"),
                      "call_src": src("site/data/recordings/starbucks-repair.json", "the run's model-cost log")},
    }


def _spread(xs: list[float]) -> dict:
    """A median with its range, never a best run."""
    return {"median": round(statistics.median(xs), 4), "min": min(xs), "max": max(xs), "n": len(xs)}


def _profile(jobs: dict) -> str:
    """The model profile a run used: hybrid (the default) when Muse Wonder takes the agent's steps, else the Spark profile.
    Both compile with Muse Wonder."""
    return "hybrid" if jobs["step"]["model"].startswith("muse-wonder") else "Spark"


def real_apps() -> dict:
    """Real apps: each workflow's first run against its same-input rerun as medians with their range (the cost curve), from
    the curve's pass; the eval's own suite (suite 4) for the stages; and every earlier pass, one per row, so each number
    sits next to its trajectory. After the Nov 3 eval rewrites real.json, the final pass is both."""
    d = json.loads((REPO / "eval/results/final/real.json").read_text())
    meta = d["meta"]
    md = (REPO / "eval/results/final/real.md").read_text()
    runs = re.search(r"Rows come from (\d+) runs", md)
    # The cost curve's pass: the final eval's once it ran on the tag, else the newest full pass on the hybrid profile (the
    # profile the final eval uses). The README's cost curve uses the same pass and rule; the build checks they agree.
    curve_path = "eval/results/final/real.json" if meta["code"].get("is_eval_final") else REAL_CURVE
    cd = json.loads((REPO / curve_path).read_text())
    pairs, rows = [], []
    for name, w in cd["workflows"].items():
        a, rr = w["agent"], {r["case"]: r for r in w.get("routine_runs", [])}
        same, new = rr.get("same input"), rr.get("new input")
        rows.append({"workflow": name, "goal": w["goal"], "graded_by": w["graded_by"], "first_run": w["first_run"],
                     "agent": {"actions": a["steps"], "calls": a["model_calls"], "seconds": a["duration_s"]},
                     "compiled": bool(w["compile"]["compiled"]), "steps": w["compile"].get("steps"),
                     # a rerun that never ran ("input not learned") has no calls or time
                     "same": same and {"result": same["result"], "calls": same.get("model_calls"), "seconds": same.get("duration_s")},
                     "new": new and {"result": new["result"], "calls": new.get("model_calls"), "seconds": new.get("duration_s")}})
        # both passed outright: a rerun that needed a repair isn't counted
        if w["first_run"] == "pass" and same and same["result"] == "pass":
            pairs.append((a, same, w["compile"].get("cost_usd") or 0))
    cm = cd["meta"]
    curve = {"n": len(pairs), "of": len(cd["workflows"]),
             "pass": {"date": datetime.fromisoformat(cm["started"]).astimezone(ET).strftime("%b %-d"), "commit": cm["code"]["short"],
                      "final": bool(cm["code"].get("is_eval_final")), "profile": _profile(cm["models"]["jobs"]),
                      "tier": cm["models"]["tier"], "run": cm["run_id"], "src": src(curve_path),
                      "md_src": src(curve_path.replace(".json", ".md"))},
             "first": {"calls": _spread([a["model_calls"] for a, _, _ in pairs]), "seconds": _spread([a["duration_s"] for a, _, _ in pairs]),
                       "usd": _spread([a["cost_at_standard_usd"] for a, _, _ in pairs])},
             "rerun": {"calls": _spread([r["model_calls"] for _, r, _ in pairs]), "seconds": _spread([r["duration_s"] for _, r, _ in pairs]),
                       "usd": _spread([r["cost_usd"] for _, r, _ in pairs])},
             "compile": _spread([c for _, _, c in pairs])}
    _check_readme_curve(curve)
    code = meta["code"]
    breakdown = [(rid, c, len([x for x in names.split(",") if x.strip()])) for rid, c, names in
                 re.findall(r"(\d{10}) on `(\w+)`: ([^;]+?)(?:;|\.\s|$)", md.split("Rows come from", 1)[1].split("\n\n", 1)[0])] \
        if runs else []
    current = {"date": meta["started"][:10], "commit": code["short"], "final": bool(code.get("is_eval_final")),
               "profile": _profile(meta["models"]["jobs"]), "tier": meta["models"]["tier"],
               "runs": int(runs.group(1)) if runs else 1, "run_id": meta["run_id"],
               "breakdown": [{"run": r, "commit": c, "rows": n} for r, c, n in sorted(breakdown, key=lambda x: -x[2])],
               "stages": _stages(md)}
    # One pass per row, each from its own published stage table (real.md). The Oct 31 rehearsal's README carries the Oct 29
    # passes, whose folders hold no comparable table; its Oct 28 column is left out because its first-run cell (13/18) is
    # real.json's count, where real.md, the published table, says 14/18.
    rr_md = (REPO / "eval/results/real_rerun_2026-10-31/README.md").read_text()
    stages = next(t for t in md_tables(rr_md) if t and "Stage" in t[0])
    passes = []
    for head in stages[0]:
        m = re.match(r"(\w+ \d+)(?: main)? \(`(\w+)`, (\w+)\)", head)
        if not m or "after" in head or m.group(1) != "Oct 29":
            continue
        passes.append({"date": m.group(1), "commit": m.group(2), "profile": "hybrid" if m.group(3) == "hybrid" else "Spark",
                       "cells": {re.sub(r"^\d\. ", "", r["Stage"]): plain(r[head]) for r in stages},
                       "src": src("eval/results/real_rerun_2026-10-31/README.md", "The four stages")})
    for path in REAL_PASSES + ["eval/results/final/real.json"]:
        j = json.loads((REPO / path).read_text())["meta"]
        if path.startswith("eval/results/final/") and j["code"].get("is_eval_final"):
            continue  # the final pass is its own row on the page
        passes.append({"date": datetime.fromisoformat(j["started"]).astimezone(ET).strftime("%b %-d"), "commit": j["code"]["short"],
                       "profile": _profile(j["models"]["jobs"]), "cells": _stages((REPO / path).with_suffix(".md").read_text()),
                       "src": src(path.replace(".json", ".md"), "stages")})
    passes.sort(key=lambda p: datetime.strptime(p["date"] + " 2026", "%b %d %Y"))
    return {"current": current, "curve": curve, "rows": rows, "passes": passes,
            "src": src("eval/results/final/real.json"), "md_src": src("eval/results/final/real.md"),
            "passes_src": src("eval/results/real_rerun_2026-10-31/README.md", "The four stages")}


REAL_CURVE = "eval/results/real_rerun_2026-11-02_wsd-baseline/real.json"


def _readme_final_curve(readme: str) -> dict | None:
    """The README's cost curve as one pass (the final eval's): a "| | Median (range) |" table after "**The cost curve.**",
    and the workflow count from its lead-in ("On the 13 workflows ..."). Returned in the per-pass row's shape."""
    lead = re.search(r"\*\*The cost curve\.\*\* On the (\d+) workflows", readme)
    table = next((t for t in md_tables(readme[readme.index("**The cost curve.**"):])
                  if t and set(t[0]) == {"", "Median (range)"}), None)
    if not lead or not table:
        return None
    cells = {r[""].split(" (")[0]: r["Median (range)"] for r in table}
    return {"Workflows": lead.group(1), "The agent's first run": cells.get("The agent's first run", ""),
            "Envoy's replay": cells.get("Envoy's replay", ""), "Compiling it, once": cells.get("Compiling it, once", "")}


def _check_readme_curve(curve: dict) -> None:
    """The README's cost-curve table must give the site's numbers for the same pass. Skipped while the README has no such
    row (or it still says TBD); a mismatch stops the build, so the two never ship different numbers."""
    readme = (REPO / "README.md").read_text()
    if "**The cost curve.**" not in readme:
        return
    label = "Nov 3, final" if curve["pass"]["final"] else f"{curve['pass']['date']}, `{curve['pass']['profile']}`"
    table = next((t for t in md_tables(readme) if t and {"Pass", "Workflows", "Compiling it, once"} <= set(t[0])), None)
    if table is None and curve["pass"]["final"]:
        row = _readme_final_curve(readme)  # the README's one-pass table, once the final eval ran
    else:
        row = next((r for r in table or [] if r["Pass"].startswith(label)), None)
    if not row:
        sys.exit(f"README.md's cost curve has no row for {label}, the site's pass ({curve['pass']['src']['path']})")
    if "TBD" in row["Workflows"]:
        return
    num = lambda pat, text: float(re.search(pat, text).group(1))
    f, r, c = curve["first"], curve["rerun"], curve["compile"]
    got = {"workflows": int(row["Workflows"]),
           "first calls": num(r"([\d.]+) calls", row["The agent's first run"]),
           "first s": num(r"([\d.]+) s", row["The agent's first run"]), "first $": num(r"\$([\d.]+)", row["The agent's first run"]),
           "replay calls": num(r"([\d.]+) calls", row["Envoy's replay"]), "replay s": num(r"([\d.]+) s", row["Envoy's replay"]),
           "compile $": num(r"\$([\d.]+)", row["Compiling it, once"])}
    want = {"workflows": curve["n"], "first calls": f["calls"]["median"], "first s": f["seconds"]["median"],
            "first $": f["usd"]["median"], "replay calls": r["calls"]["median"], "replay s": r["seconds"]["median"],
            "compile $": c["median"]}
    off = {k: (got[k], round(want[k], 4)) for k in want if abs(got[k] - want[k]) > (0.006 if k.endswith(" s") else 0.00006)}
    if off:
        sys.exit(f"README.md's cost curve ({label}) disagrees with the site's, from {curve['pass']['src']['path']}: {off}")


# Real-app passes with their own folder (real.json and real.md), besides the eval's current one. Not the Nov 2 check
# (wsd-check): its stage totals mix runs, as its README says.
REAL_PASSES = ["eval/results/real_rerun_2026-10-31/real.json", "eval/results/real_rerun_2026-11-02_wsd-baseline/real.json"]
STAGE_NAMES = {"1": "First run right", "2": "Compiled", "3": "Same input, no model call", "4": "New input, no model call"}


def _stages(md: str) -> dict:
    """A real.md's published stage table ("1. First run: … | 14/18"), keyed like the rehearsal README's rows."""
    t = next(t for t in md_tables(md) if t and "Stage" in t[0] and "Passed" in t[0])
    out = {}
    for r in t:
        m = re.match(r"(\d)\. ", r["Stage"])
        if m:
            out[STAGE_NAMES[m.group(1)]] = plain(r["Passed"]).replace(" counting a repair)", " with a repair)")
    return out


LEARN = REPO / "eval/results/learn-agent-path"


def _learn_pass(rows: list[dict]) -> dict:
    """One learn-path pass: the agent path, "Make it a routine", and the saved routines' calls (retry rows left out, as the
    headline leaves them out)."""
    rows = [r for r in rows if not r["row"].endswith("-retry")]
    agent = [r["agent"] for r in rows]
    learn = [r.get("learn") or {} for r in rows]
    saved = [l for l in learn if l.get("outcome") == "saved"]
    new = [r["call"] for r in rows if (r.get("call") or {}).get("case") == "new input"]
    by_library = [r for r in rows if r["agent"].get("library_routine")]
    return {"n": len(rows), "right": sum(1 for a in agent if a.get("outcome") == "right"),
            "right_by_library": sum(1 for r in by_library if r["agent"].get("outcome") == "right"),
            "by_library": len(by_library), "saved": len(saved),
            "not_compilable": sum(1 for l in learn if l.get("outcome") == "not compilable"),
            "replay_failed": sum(1 for l in learn if l.get("outcome") == "replay failed"),
            "blocked": sum(1 for l in learn if l.get("outcome") == "blocked"),
            "not_learnable_other": sum(1 for r, l in zip(rows, learn) if l.get("outcome") == "not learnable"
                                       and not r["agent"].get("library_routine")),
            "new": len(new), "new_right": sum(1 for c in new if str(c.get("outcome", "")).startswith("right")),
            "new_zero": sum(1 for c in new if c.get("outcome") == "right, 0 calls"),
            "replay_s": _spread([l["replay_seconds"] for l in saved]) if saved else None,
            "compile_usd": _spread([l["compile_cost_usd"] for l in saved]) if saved else None}


def learn_path() -> dict:
    """The agent path and "Make it a routine" on the eval-final tag (eval/results/learn-agent-path): counted from
    results.json, and checked against the headline its README publishes, so the two can't drift."""
    main = json.loads((LEARN / "results.json").read_text())
    sup = json.loads((LEARN / "supplementary.json").read_text())
    readme = (LEARN / "README.md").read_text()
    m, x = _learn_pass(main["rows"]), _learn_pass(sup["rows"])
    heads = re.findall(r"\*\*Agent path:\*\* right (\d+)/(\d+)\.\s*- \*\*Learn rate:\*\* saved (\d+)/(\d+)\.\s*"
                       r"- \*\*New input:\*\* right (\d+)/(\d+) saved routines with a second input; (\d+) of them with 0 model calls",
                       readme)
    for (ar, an, sv, sn, nr, nn, nz), p in zip(heads, (m, x)):
        got = (p["right"], p["n"], p["saved"], p["n"], p["new_right"], p["new"], p["new_zero"])
        assert tuple(map(int, (ar, an, sv, sn, nr, nn, nz))) == got, ("learn-agent-path README vs results.json", got)
    assert len(heads) == 2, "learn-agent-path README: two headlines expected"
    return {"main": m, "supplementary": x, "started": main["started"], "phone": main["phone"],
            "tag": main["versions"]["eval_final"][:7],
            "src": src("eval/results/learn-agent-path/README.md"), "results_src": src("eval/results/learn-agent-path/results.json"),
            "protocol_src": src("eval/results/learn-agent-path/PROTOCOL.md")}


def memory() -> dict:
    md = (REPO / "eval/results/final/memory.md").read_text()
    t = md_tables(md)
    m = re.search(r"\*\*(\d+) labeled items: (\d+)/(\d+) \((\d+)%\) of attributes right, (\d+) wrong values\.\*\*", md)
    stale = re.search(r"\*\*Stale facts served without a warning: (\d+) of (\d+)\.\*\*", md)
    run = re.search(r"Run (\d+) on `([\w-]+)`[^,]*, (\d{4}-\d\d-\d\d)", md)
    ages = [r for r in t[2] if "gate" in r["Question"].lower()] if len(t) > 2 else []
    return {
        "demo": json.loads((REC / "memory.json").read_text()),
        "demo_src": src("site/data/recordings/memory.json", "the demo world's memory, read only"),
        "extraction": {"items": int(m.group(1)), "right": int(m.group(2)), "of": int(m.group(3)), "pct": int(m.group(4)),
                       "wrong": int(m.group(5))} if m else None,
        "extraction_sets": [{k: plain(v) for k, v in r.items()} for r in t[0]],
        "stale": {"unwarned": int(stale.group(1)), "of": int(stale.group(2))} if stale else None,
        "ages": [{k: plain(v) for k, v in r.items()} for r in ages],
        "commit": run.group(2) if run else "", "date": run.group(3) if run else "",
        "src": src("eval/results/final/memory.md"),
        "readme_src": src("backend/memory/README.md"),
    }


def safety() -> dict:
    s_md = (REPO / "eval/results/final/safety.md").read_text()
    i_md = (REPO / "eval/results/final/injection.md").read_text()
    st = md_tables(s_md)
    caught = re.search(r"\*\*The policy gate caught (\d+) of (\d+)\*\* \(code signals alone: (\d+); the step model's own label: (\d+)\)", s_md)
    rev = re.search(r"Flagged by the code signals: (\d+) of (\d+); by the gate \(model included\): (\d+) of (\d+)", s_md)
    s_run = re.search(r"Run (\d+) on `([\w-]+)`[^,]*, (\d{4}-\d\d-\d\d)", s_md)
    i_run = re.search(r"Run (\d+) on `([\w-]+)`[^,]*, (\d{4}-\d\d-\d\d)", i_md)
    agent = re.search(r"Agent: (\d+) of (\d+) runs still did the task right[^;]*; it asked to do something else in (\d+)", i_md)
    routines = re.search(r"Routines: (\d+) of (\d+)", i_md)
    planted = dict(re.findall(r"- \*\*(\w+)\*\*: “(.+?)”", i_md))
    inbox = re.search(r"Injected values stored: \*\*(\d+)\*\*; instructions stored as facts: \*\*(\d+)\*\*", i_md)
    screens = json.loads((REPO / "eval/results/final/safety.json").read_text())["screens"]["rows"]
    by_screen = {r["screen"]: r["app"] for r in screens}
    return {
        "captured": {"controls": len(screens), "screens": len(by_screen), "apps": len(set(by_screen.values())),
                     "skylark_screens": sum(1 for a in by_screen.values() if a == "SkyLark")},
        "caught": [int(x) for x in caught.groups()] if caught else None,
        "reversible": [int(x) for x in rev.groups()] if rev else None,
        "controls": [{"app": r["App"], "control": plain(r["Control"]), "gate": r["Gate"]} for r in st[0]],
        "safety_run": {"commit": s_run.group(2), "date": s_run.group(3)} if s_run else None,
        "injection_run": {"commit": i_run.group(2), "date": i_run.group(3)} if i_run else None,
        "agent": [int(x) for x in agent.groups()] if agent else None,
        "routines": [int(x) for x in routines.groups()] if routines else None,
        "planted_texts": planted, "inbox": [int(x) for x in inbox.groups()] if inbox else None,
        "planted": json.loads((REC / "planted.json").read_text()),
        "approval": json.loads((REC / "approval.json").read_text()),
        "safety_src": src("eval/results/final/safety.md"), "injection_src": src("eval/results/final/injection.md"),
        "planted_src": src("site/data/recordings/planted.json", "from data/runs, the injection suite's trace"),
        "approval_src": src("site/data/recordings/approval.json", "a test copy of Envoy, read only"),
    }


def models() -> dict:
    vision = json.loads((REPO / "eval/results/phase6/vision.json").read_text())
    return {
        "vision": vision["summary"]["all"], "vision_canvas": vision["summary"]["skylark-canvas"],
        # SAM first, then grounding, on a fresh sample of the 52 targets: the line Envoy's default order rests on
        "sam_then_grounding": [int(x) for x in re.search(r"SAM then grounding (\d+) of (\d+); grounding alone (\d+) of (\d+)",
                                                          (REPO / "docs/phase-6-results.md").read_text()).groups()],
        "vision_src": src("eval/results/phase6/vision.json"),
        "sam": json.loads((REC / "sam.json").read_text()),
        "sam_src": src("site/data/recordings/sam.json", "from data/runs/p6-canvas-src"),
        "phase6_src": src("docs/phase-6-results.md", "Results"),
    }


# AndroidWorld on the shipped default (hybrid) at main, Nov 3: a separate run, shown next to the Oct 28-29 numbers.
AW_HYBRID = REPO / "eval/results/androidworld/2026-11-03-hybrid-7ed4aa6"


def aw_hybrid() -> dict:
    """The run's own summary.json, and its paired comparison with Oct 28's final-standard (compare_final-standard.json)."""
    sm = json.loads((AW_HYBRID / "summary.json").read_text())
    cmp = json.loads((AW_HYBRID / "compare_final-standard.json").read_text())
    m = re.match(r"(\d{4}-\d\d-\d\d)-(\w+)-([0-9a-f]{7})$", sm["stage"])
    pick = lambda h: {"success": int(h["success"]), "n": h["n"], "rate": h["rate"]}
    return {"date": m.group(1), "profile": m.group(2), "commit": m.group(3), "stage": sm["stage"],
            "all": pick(sm["overall"]), "held": pick(sm["by_half"]["held_out"]),
            "median_usd": sm["cost_standard_usd"]["median_task"], "median_s": sm["time_s"]["envoy_median"],
            "calls_median": sm["model_calls"]["median"],
            "vs": {"held": cmp["by_half"]["held_out"], "all": cmp["by_half"]["all"], "before": cmp["before"]},
            "src": src(rel(AW_HYBRID / "README.md")), "summary_src": src(rel(AW_HYBRID / "summary.json")),
            "compare_src": src(rel(AW_HYBRID / "compare_final-standard.json"))}


def headlines(suites: list[dict]) -> dict:
    """The README's top numbers, read from the final report's suite rows (the build stops if a row's wording changes)."""
    row = lambda n: next(s["result"] for s in suites if s["suite"].startswith(n + "."))
    r = re.search(r"Envoy routines (\d+)/(\d+) .*?median ([\d.]+) calls?, ([\d.]+) s; Full agent every time (\d+)/(\d+) .*?median ([\d.]+) calls?, ([\d.]+) s", row("1"))
    q = re.search(r"request 1 median \$([\d.]+) and ([\d.]+) s; requests 2–10 (\d+)/(\d+) right, median ([\d.]+) calls?, \$([\d.]+), ([\d.]+) s", row("2"))
    c = re.search(r"injected changes recovered (\d+)/(\d+)", row("3"))
    f = re.search(r"irreversible caught (\d+)/(\d+) \(code alone (\d+)\)", row("6"))
    i = re.search(r"agent right (\d+)/(\d+) with planted text, tried to follow it (\d+)", row("6b"))
    return {"routines": {"ok": int(r[1]), "n": int(r[2]), "calls": float(r[3]), "s": float(r[4]), "agent_ok": int(r[5]), "agent_n": int(r[6]),
                         "agent_calls": float(r[7]), "agent_s": float(r[8])},
            "repeats": {"first_usd": float(q[1]), "first_s": float(q[2]), "ok": int(q[3]), "n": int(q[4]), "calls": float(q[5]), "usd": float(q[6]),
                        "s": float(q[7]), "times": round(float(q[1]) / float(q[6]))},
            "recovered": {"ok": int(c[1]), "n": int(c[2])},
            "safety": {"ok": int(f[1]), "n": int(f[2]), "code": int(f[3])},
            "planted": {"ok": int(i[1]), "n": int(i[2]), "followed": int(i[3])}}


def readme_facts() -> dict:
    """What the page takes from the README, its source for wording and scope: the tool count (checked against the code), the
    Nov 4 cross_post take, and "Changes since the evaluation". Each is left out if the README stops saying it."""
    md = (REPO / "README.md").read_text()
    code = (REPO / "backend/mcp_server/server.py").read_text()
    tools = len(re.findall(r"@\w+\.tool\b|\.tool\(", code))
    said = re.search(r"(\d+) built-in tools", md)
    assert not said or int(said[1]) == tools, ("README's tool count vs the code", said[1], tools)
    take = re.search(r"In a (\w+ \d+) take, Muse made one `cross_post` call for ([^,]+, [^,]+ and [^,]+), and all three finished, at ([\d, and]+) model calls in Envoy's replay", md)
    since = md.split("### Changes since the evaluation", 1)[1].split("\n## ", 1)[0] if "### Changes since the evaluation" in md else ""
    items = re.findall(r"^- \*\*(.+?)\*\*:? (.+?)(?=^- \*\*|\Z)", since, re.M | re.S)
    clean = lambda t: re.sub(r"\s+", " ", plain(t)).strip().rstrip(":")
    return {"tools": tools, "take": take and {"date": take[1], "posts": take[2], "calls": take[3]},
            "since": [{"name": clean(a), "text": re.sub(r"\s*\([^()]*\.(?:md|py)\)", "", clean(b))} for a, b in items],
            "run_it": src("README.md#run-it"), "readme": src("README.md"),
            "cross_post_src": src("eval/results/agent-door/cross-post-pixel.json"), "cross_post_tests": src("backend/tests/test_crosspost.py")}


# Each suite's own file beside report.md (suite 8, AndroidWorld, reports elsewhere).
SUITE_FILES = {"0": "compile", "1": "systems", "2": "repeats", "3": "change", "3b": "sizes", "4": "real", "5": "memory",
               "6": "safety", "6b": "injection", "7": "interfaces"}


def proof() -> dict:
    rep = (REPO / "eval/results/final/report.md").read_text()
    t = md_tables(rep)
    suites = [{"suite": plain(r["Suite"]), "result": plain(r["Result"]), "ran_on": plain(r["Ran on"])} for r in t[0]]
    for s in suites:
        f = SUITE_FILES.get(s["suite"].split(".")[0])
        meta = json.loads((REPO / f"eval/results/final/{f}.json").read_text())["meta"] if f else None
        s["profile"], s["tier"] = (_profile(meta["models"]["jobs"]), meta["models"]["tier"]) if meta else ("", "")
    targets = [{k: plain(v) for k, v in r.items()} for r in t[1]]
    charts = {n: image(REPO / f"eval/results/final/charts/{n}.png", f"chart-{n}", 1600) for n in
              ["cost_and_time_over_repeated_runs", "success_by_system_and_layout", "recovery_by_injected_change", "real_apps_stages"]}
    aw = (REPO / "docs/androidworld-results.md").read_text()
    head = re.search(r"\*\*Headline\.\*\* (.+)", aw).group(1)
    held = re.search(r"\*\*Held-out half:\*\* (.+)", aw)
    rt = re.search(r"they did (\d+) of (\d+) instances, against the full agent's (\d+), at (\d+) model call against (\d+), "
                   r"(\$[\d.]+) against (\$[\d.]+)", aw)
    fb = re.search(r"with the agent run where a routine failed, (\d+) of (\d+)", aw)
    nr = re.search(r"Envoy compiled (\d+) routines from its solved runs, and (\d+) did their own seed-30 task on their own", aw)
    ho = re.search(r"On the held-out half, never used to choose a change, that is (\d+) of (\d+) \([\d.]+%\) against (\d+)", head)
    sizes = json.loads((REPO / "eval/results/final/sizes.json").read_text())
    phone = sizes["devices"]["phone"]
    rows = phone.get("rows", phone) if isinstance(phone, dict) else phone
    rows = rows if isinstance(rows, list) else list(rows.values())
    ok = [r for r in rows if r.get("passed")]
    secs = [r.get("duration_s") or 0 for r in rows]
    tests, files = 0, 0
    import ast
    for p in sorted((REPO / "backend/tests").rglob("test_*.py")):
        files += 1
        tests += sum(1 for n in ast.walk(ast.parse(p.read_text())) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                     and n.name.startswith("test"))
    return {
        "suites": suites, "targets": targets, "charts": charts, "src": src("eval/results/final/report.md"),
        "headlines": headlines(suites),
        "charts_src": src("eval/results/final/charts"),
        "aw": {"headline": plain(head), "held_out": plain(held.group(1)) if held else "",
               # framed by cost: routines against the full agent on new seeds, and the agent's held-out half
               "routines": {"did": rt.group(1), "of": rt.group(2), "agent": rt.group(3), "calls": rt.group(4),
                            "agent_calls": rt.group(5), "usd": rt.group(6), "agent_usd": rt.group(7),
                            "fallback": [int(fb.group(1)), int(fb.group(2))],
                            "compiled": int(nr.group(1)), "alone": int(nr.group(2))},
               "held": [int(x) for x in ho.groups()],
               "model": plain(re.search(r"^\| Model \| ([^|,]+)", aw, re.M).group(1)).strip(),
               "src": src("docs/androidworld-results.md", "Headline, Routines"),
               "hybrid": aw_hybrid()},
        "phone": {"passed": len(ok), "runs": len(rows), "calls": sum(r.get("calls") or 0 for r in rows),
                  "median_s": round(statistics.median(secs), 2) if secs else None, "commit": sizes["meta"]["code"]["short"],
                  "profile": _profile(sizes["meta"]["models"]["jobs"]), "tier": sizes["meta"]["models"]["tier"],
                  "date": sizes["meta"]["started"][:10], "src": src("eval/results/final/sizes.json", "devices.phone")},
        "tests": {"functions": tests, "files": files, "src": src("backend/tests")},
    }


def built() -> dict:
    tp = (REPO / "THIRD_PARTY.md").read_text()
    in_use = md_tables(tp.split("## In use", 1)[1])[0]
    ours = tp.split("## What Envoy builds itself", 1)[1].split("\n## ", 1)[0]
    borrowed = tp.split("## Ideas borrowed", 1)[1] if "## Ideas borrowed" in tp else ""
    # "- **Title** (when, where): what" or "- **Title:** what"
    items = [(m.group(1).rstrip(":"), m.group(3)) for m in re.finditer(r"^- \*\*(.+?)\*\*( \([^)]*\))?:? (.+)$", ours, re.M)]
    return {
        "diagrams": {"architecture": image(REPO / "docs/diagrams/architecture.png", "diagram-architecture", 1400),
                     "lifecycle": image(REPO / "docs/diagrams/routine-lifecycle.png", "diagram-routine-lifecycle", 1400)},
        "diagrams_src": src("docs/diagrams"),
        "ours": [{"title": a.rstrip(":"), "text": plain(b)} for a, b in items],
        "plumbing": [{"name": plain(r["Component"]).split(" (")[0].split(",")[0], "license": r["License"],
                      "use": plain(r["What we use it for"])} for r in in_use],
        "borrowed": [plain(m) for m in re.findall(r"^- (.+)$", borrowed, re.M)],
        "src": src("THIRD_PARTY.md"),
    }


def teach() -> dict:
    rows = md_tables((REPO / "eval/results/real-apps/table.md").read_text())[0]
    cal = [{"app": plain(r["app"]), "task": plain(r["task"]), "first": plain(r["first runs (x/3)"]), "notes": plain(r["notes"])}
           for r in rows if r["app"].startswith("Google Calendar")]
    return {"rec": json.loads((REC / "teach.json").read_text()), "calendar_rows": cal,
            "src": src("site/data/recordings/teach.json", "teach mode's recordings, Oct 31"),
            "table_src": src("eval/results/real-apps/table.md", "Google Calendar rows"),
            "code_src": src("backend/api/teach.py"), "person_src": src("eval/teach_person.py")}


# ---------------------------------------------------------------------------------------------------------------------------
# the phone layer (Nov 1–2): agents calling Envoy, routines as tools, the app-only posts, watching, keys
# ---------------------------------------------------------------------------------------------------------------------------

SPARK = REPO / "agents/meta-agent/evidence/2026-11-01"  # the Spark agent's runs: its page's own event logs and captures


def spark_run(path: Path) -> dict:
    """A Spark agent run, from its page's event log (GET /api/recording): what was asked, each call to Envoy, each wait for
    the person and how it ended, what the agent said, and its totals. The waits' get_task polls are folded into the waits."""
    ev = json.loads(path.read_text())["events"]
    t0 = ev[0]["t"]
    at = lambda e: round(e["t"] - t0, 1)
    ends = {e["data"]["id"]: e["data"] for e in ev if e["kind"] == "call_end"}
    tools, rows = [], []
    for e in ev:
        k, d = e["kind"], e["data"]
        if k == "tools" and not tools:
            tools = [{"name": t["name"], "learned": bool(t.get("routine"))} for t in d["tools"]]
        elif k in ("user", "commentary", "reply"):
            rows.append({"t": at(e), "kind": k, "text": d["text"]})
        elif k == "call_start" and d["tool"] != "tools/list" and d.get("via") != "wait_for_task":
            end = ends.get(d["id"], {})
            rows.append({"t": at(e), "kind": "call", "tool": d["tool"], "args": d["args"], "ok": end.get("ok"),
                         "result": end.get("summary"), "ms": end.get("ms")})
        elif k == "call_start" and d.get("via") == "wait_for_task":
            end = ends.get(d["id"], {})
            rows.append({"t": at(e), "kind": "wait", "result": end.get("summary"), "ms": end.get("ms"), "polls": end.get("polls")})
        elif k == "waiting":
            rows.append({"t": at(e), "kind": "ask", "task": d["key"], "ask": d["kind"], "title": d["title"], "goal": d["goal"]})
        elif k == "waiting_end":
            rows.append({"t": at(e), "kind": "answer", "task": d["key"], "outcome": d["outcome"], "after_s": d["after_s"]})
        elif k == "refusal":
            rows.append({"t": at(e), "kind": "refusal", "tool": d["tool"], "text": d["envoy"]})
    hello = next(e["data"] for e in ev if e["kind"] == "hello")
    last = [e["data"] for e in ev if e["kind"] == "stats"][-1]
    return {"started_et": datetime.fromtimestamp(t0, ET).strftime("%Y-%m-%d %H:%M"), "model": hello["model"],
            "envoy": hello.get("envoy") or "", "tools": tools, "rows": rows, "seconds": at(ev[-1]),
            "model_calls": last["model_calls"], "mcp_calls": last["mcp_calls"], "usd": round(last["cost_usd"], 4)}


# Muse's Nov 2 dry run: what stopped the two tasks that didn't reach a final button, in the site's words (from the notes in
# task-rows.json). Keyed by task id; the build stops if an id isn't in the file.
MUSE_DRY_RUN_NOTES = {
    "task-1102-114842-f1dc": ("Its “use Envoy's phone?” ask went unanswered for 15 minutes, so the task moved to an emulator, "
                              "which had no Instagram. Fixed since: an unanswered ask now ends the task."),
    "task-1102-121512-0b47": ("The retry, on Envoy's phone. A Story from the night before was still live, so the routine's first tap "
                              "opened it instead of a new Story; the agent's fallback ran out of steps and asked the person."),
}


def agents() -> dict:
    """Agents calling Envoy: the Spark agent's cross-post (four routine tools at once, on Envoy's phone), Muse's Nov 2 dry run
    and its captures from the Oct 29 link sitting, and Claude Code's tasks on the live API (task rows read read-only)."""
    cc = json.loads((SPARK / "claude-code/task-rows.json").read_text())
    muse = REPO / "eval/results/muse-link"
    muse_rows = json.loads((REPO / "eval/results/showcase/muse-2026-11-02/task-rows.json").read_text())
    ids = {t["id"] for t in muse_rows["tasks"]}
    assert set(MUSE_DRY_RUN_NOTES) <= ids, set(MUSE_DRY_RUN_NOTES) - ids
    for t in muse_rows["tasks"]:
        t["note"] = MUSE_DRY_RUN_NOTES.get(t["id"], "")
    return {
        "crosspost": spark_run(SPARK / "crosspost/run2-four-posts.json"),
        "crosspost_src": src(rel(SPARK / "crosspost/run2-four-posts.json"), "the Spark agent page's event log"),
        "crosspost_readme": src(rel(SPARK / "crosspost/README.md")),
        "crosspost_commit": re.search(r"## `run2-four-posts\.json`.*\(main `(\w+)`\)", (SPARK / "crosspost/README.md").read_text()).group(1),
        "run1": {k: v for k, v in spark_run(SPARK / "crosspost/run1-three-posts.json").items() if k != "rows"},
        "run1_src": src(rel(SPARK / "crosspost/run1-three-posts.json")),
        "shots": {"asks": image(SPARK / "crosspost/run2-four-phone-asks.png", "agents-spark-four-asks", 1600),
                  "declined": image(SPARK / "crosspost/run2-all-declined.png", "agents-spark-all-declined", 1600)},
        "muse": {"dry_run": muse_rows,
                 "dry_run_src": src("eval/results/showcase/muse-2026-11-02/task-rows.json", "Muse's tasks, read read-only"),
                 "mac": image(muse / "e3-mac-moves-clip-and-sidecar.jpg", "muse-mac-outbox", crop=(85, 38, 740, 476)),
                 "no_accept": image(muse / "muse-refuses-to-accept-offers.jpg", "muse-no-accept-tool"),
                 "src": src("eval/results/muse-link", "the Oct 29 Muse sitting"), "doc": src("docs/muse-link.md")},
        "claude": {"tasks": cc["tasks"], "approvals": cc["approvals"], "src": src(rel(SPARK / "claude-code/task-rows.json")),
                   "readme": src(rel(SPARK / "claude-code/README.md"))},
        "mcp_src": src("backend/mcp_server/README.md"),
    }


def tools() -> dict:
    """A routine shared with agents becomes a tool of its own: the tool list before and after one switch, the tool as agents
    see it, one call to it (agent-door's check on a test copy), and the Spark agent calling a routine by its name."""
    door = REPO / "eval/results/agent-door"
    before = json.loads((door / "tools-before.json").read_text())
    after = json.loads((door / "tools-after.json").read_text())
    call = json.loads((door / "call.json").read_text())
    tool = after["routine_tools"][0]
    return {
        "before": {"at": before["at"], "tools": before["tools"]}, "after": {"at": after["at"], "tools": after["tools"]},
        "tool": {"name": tool["name"], "description": tool["description"], "input": tool["inputSchema"],
                 "meta": tool["_meta"], "read_only": tool["annotations"].get("readOnlyHint")},
        "call": {"tool": call["call"]["tool"], "args": call["call"]["arguments"], "at": call["at"],
                 "heads_up": [h["text"] for h in call["call"]["result"].get("heads_up", [])],
                 "status": call["task"]["status"], "result": call["task"]["result"], "detail": call["task"]["detail"],
                 "steps": [s["text"] for s in call["task"]["steps"] if s["kind"] == "routine_step"]},
        "door_src": src("eval/results/agent-door", "tools-before.json, tools-after.json, call.json"),
        "by_name": spark_run(SPARK / "routine-tool-run.json"),
        "by_name_src": src(rel(SPARK / "routine-tool-run.json")), "evidence_readme": src(rel(SPARK / "README.md")),
        "shot": image(SPARK / "routine-tool-run.png", "tools-spark-by-name", 1600),
        "settings": image(door / "agent-tools-new-1080p.png", "tools-settings-agent-tools", crop=(545, 615, 1245, 1080)),
        "settings_src": src("eval/results/agent-door/agent-tools-new-1080p.png"),
        "report_src": src("docs/reports/agent-door-report.md"),
    }


# The app-only posts: each tool (a routine in the library), its app, and what it posts.
SHOWCASE = {
    "instagram_reel_song": ("Instagram", "A Reel set to a song from Instagram's music library"),
    "instagram_story_poll": ("Instagram", "A Story with a poll sticker"),
    "tiktok_post_sound": ("TikTok", "A TikTok with a sound from TikTok's library"),
    "youtube_short_sound": ("YouTube", "A YouTube Short with a sound from YouTube's library"),
}
# What a person changed by hand in each, worded from the version's own changes (checked below against index.json, so a new
# version with other edits stops the build instead of leaving this wrong).
HAND_EDITS = {
    "instagram_reel_song": ("two for the caption fix after the posting batch: Instagram's OK closes the caption edit "
                            "instead of Back, and an empty caption is typed again before Share"),
    "instagram_story_poll": None,
    "tiktok_post_sound": "three hand edits: a 3 s wait before TikTok's drawn sound list, the app's name, and no before-check on its launch",
    "youtube_short_sound": "one hand edit: a stray before-check (“Captions unavailable”) dropped",
}


LIVE = REPO / "eval/results/showcase/live-2026-11-02/task-rows.json"  # the real posts' task rows, read read-only from the live API
# The one real post that wasn't right, in the site's words (from the file's notes). Keyed by task id; the build stops if the id
# isn't in the file. Every other row with status "done" went live (docs/demo-showcase.md, "The real posts").
LIVE_NOTES = {
    "task-1102-014139-7f5e": "went up without its song: a compiler bug, since fixed; the re-post below has it",
}


def day_et(stamp: str) -> str:
    """'2026-11-03 14:05:58' (the Mac's clock, ET) as 'Nov 3'."""
    return datetime.fromisoformat(stamp.replace(" ", "T")).strftime("%b %-d")


# What a hand-edited version after the batch changed, in plain words. A version with no entry here just reads "a hand edit".
VERSION_WORDS = {
    ("instagram_reel_song", 4): "the caption fix",
    ("instagram_reel_song", 5): "a wait for the upload after Share",
}


def _after_batch(ix: dict) -> list[dict]:
    """Versions made on or after the posting batch's day, up to the active one: what kind of change each is, its device check
    if its verification records one, and its own runs. Never counted with the batch."""
    out = []
    for v in ix["versions"]:
        if v["version"] > (ix.get("active") or 0) or v["created"][:10] < batch_day():
            continue
        text = " ".join(v["changes"]).replace("no hand edits", "")
        kind = ("a hand edit" if "hand edit" in text else "an automatic repair" if v.get("source_task") else "a new version")
        dev = ((v.get("verification") or {}).get("device")) or ""
        m = re.search(r"(\d+)/(\d+) ([^;:]*?)reached ([\w ]+?) with [^;]*?(all yes|every check yes)", dev)
        calls = re.search(r"(\d+) model calls", dev)
        runs = [r for r in ix.get("runs") or [] if r.get("version") == v["version"] and r.get("kind") == "run"]
        out.append({"version": v["version"], "date": day_et(v["created"]), "kind": kind, "what": VERSION_WORDS.get((ix["name"], v["version"])),
                    "check": m and {"ok": int(m.group(1)), "n": int(m.group(2)), "what": m.group(3).strip(), "final": m.group(4),
                                    "calls": int(calls.group(1)) if calls else None},
                    "runs": [{"status": r.get("status"), "calls": r.get("model_calls"), "seconds": r.get("duration_s"), "date": day_et(r["time"])}
                             for r in runs]})
    return out


def batch_day() -> str:
    """The day the posting batch started, from its attempt records."""
    return min(json.loads(f.read_text())["started"] for f in (BATCH / "attempts").glob("*.json"))[:10]
BATCH = REPO / "eval/results/showcase-batch"  # the pre-registered posting batch (B1), run on the eval-final tag


def batch() -> dict:
    """The posting batch: every attempt's record (attempts/*.json), counted per routine, and checked against the
    per-workflow table its RESULTS.md publishes, so the two can't drift. A check of the poll isn't in the records (it was
    read by eye on the approval screenshots); the table's own cell says so and is shown as written."""
    attempts = [json.loads(f.read_text()) for f in sorted((BATCH / "attempts").glob("*.json"))]
    table = next(t for t in md_tables((BATCH / "RESULTS.md").read_text()) if t and "Reached the final button" in t[0])
    out = {}
    for a in attempts:
        r = a.get("replay") or {}
        spent = r.get("spent") or {}
        reached = bool(r.get("asked_at"))
        machine = {k: v for k, v in a["checks"].items() if k != "poll"}
        w = out.setdefault(a["routine"], {"n": 0, "reached": 0, "yes": 0, "classes": {}, "secs": [], "calls": 0, "usd": 0.0,
                                          "final": a["final"], "states": {}, "songs": {}, "stops": {}, "versions": set()})
        w["n"] += 1
        w["reached"] += reached
        w["yes"] += reached and all(v in ("yes", "n/a") for v in machine.values())
        w["classes"][a["class"]] = w["classes"].get(a["class"], 0) + 1
        w["calls"] += spent.get("model_calls") or 0
        w["usd"] += spent.get("cost_at_standard_usd") or 0
        if reached:
            w["secs"].append((r.get("marks_s") or {}).get("post_asked"))
        if a.get("routine_version"):
            w["versions"].add(a["routine_version"])
        song = (a.get("song") or {}).get("title")
        sg = w["songs"].setdefault(song or "", {"n": 0, "yes": 0, "agent": 0})
        sg["n"] += 1
        sg["yes"] += reached and all(v in ("yes", "n/a") for v in machine.values())
        sg["agent"] += a["class"] == "agent fallback"
        st = w["states"].setdefault(a["state"], {"n": 0, "reached": 0})
        st["n"] += 1
        st["reached"] += reached
        for k, v in machine.items():
            if v == "no":  # an outcome check stopped the run before the final button
                w["stops"][k] = w["stops"].get(k, 0) + 1
    for name, w in out.items():
        row = next(r for r in table if f"`{name}`" in r["Workflow"])
        assert int(row["Reached the final button"]) == w["reached"], (name, "reached", w["reached"])
        assert int(row["…with every outcome check yes"].split()[0]) == w["yes"] or "by eye" in row["…with every outcome check yes"], (name, "yes")
        w["yes_cell"] = plain(row["…with every outcome check yes"]).replace(", below", "")
        w["secs"] = _spread([x for x in w["secs"] if x is not None])
        w["usd"] = round(w["usd"], 4)
        w["versions"] = sorted(w["versions"])
    first = min(a["started"] for a in attempts)
    return {"routines": out, "n": len(attempts), "date": first[:10], "tag": attempts[0]["versions"]["tag"][:7],
            "attempts": [{"code": a["code"], "routine": a["routine"], "state": a["state"],
                          "song": (a.get("song") or {}).get("title"), "class": a["class"],
                          "reached": bool((a.get("replay") or {}).get("asked_at")), "checks": a["checks"],
                          "calls": ((a.get("replay") or {}).get("spent") or {}).get("model_calls"),
                          "to_ask": ((a.get("replay") or {}).get("marks_s") or {}).get("post_asked") if (a.get("replay") or {}).get("asked_at") else None}
                         for a in attempts],
            "src": src("eval/results/showcase-batch/RESULTS.md"), "protocol_src": src("eval/results/showcase-batch/PROTOCOL.md"),
            "attempts_src": src("eval/results/showcase-batch/attempts")}


def showcase() -> dict:
    """The four app-only routines: how each was made, an automatic repair and its trial where there is one, a version made
    after the posting batch, and its real posts (the live API's task rows). Their reliability is the batch's (batch())."""
    live = json.loads(LIVE.read_text())["tasks"]
    assert set(LIVE_NOTES) <= {t["id"] for t in live}, set(LIVE_NOTES) - {t["id"] for t in live}
    muse = {t["id"]: t for t in json.loads((REPO / "eval/results/showcase/muse-2026-11-02/task-rows.json").read_text())["tasks"]}
    cards = []
    for name, (app, what) in SHOWCASE.items():
        lib = REPO / f"data/routines/{name}"
        ix = json.loads((lib / "index.json").read_text())
        ver = {v["version"]: v for v in ix["versions"]}
        active = ver[ix["active"]]
        # An automatic repair (a version made from a task) patches the version before it; that one is the compiled base.
        base = ver[ix["active"] - 1] if active.get("source_task") else active
        made = " ".join(base["changes"])
        hand = HAND_EDITS[name]
        if hand is None and "hand edit" in made.replace("no hand edits", ""):
            print(f"note: {name} v{base['version']} has a hand edit HAND_EDITS doesn't word; the card says so generically")
            hand = "hand edits, in its version history"
        y = routine_yaml(lib / f"v{ix['active']}.yaml")
        # Learned with no hand edits, then edited by hand later: the first hand-edited version after the last clean one.
        lineage = [v for v in ix["versions"] if v["version"] <= ix["active"]]
        clean = [v["version"] for v in lineage if "no hand edits" in " ".join(v["changes"])]
        later = [v for v in lineage if clean and v["version"] > clean[-1]
                 and "hand edit" in " ".join(v["changes"]).replace("no hand edits", "")]
        hand_from = {"version": later[0]["version"], "date": day_et(later[0]["created"])} if later else None
        # Envoy's own model calls; "seconds" isn't shown: it includes the waits for both yeses on the iPhone.
        real = [{"task": t["id"], "live": t["status"] == "done", "calls": t["model_calls"], "inputs": t["inputs"],
                 "created": t["created"], "note": LIVE_NOTES.get(t["id"], "")}
                for t in live if t["routine"] == name]
        assert all(r["live"] or r["note"] for r in real), name
        repair = None
        auto = [v for v in ix["versions"] if v.get("source_task") and v["version"] <= ix["active"]]
        if auto:
            rv = auto[-1]
            trial = rv.get("trial") or {}
            t = muse.get(re.sub(r"-r\d+$", "", trial.get("task_id", "")))
            repair = {"version": rv["version"], "from_task": re.sub(r"-r\d+$", "", rv["source_task"]),
                      "after_live_post": any(re.sub(r"-r\d+$", "", rv["source_task"]) == p["task"] for p in real),
                      "steps": len(rv["changes"]), "passed": trial.get("passed"),
                      "trial": t and {"task": t["id"], "status": t["status"], "calls": t["model_calls"], "seconds": t["seconds"],
                                      "by": "Muse's dry run, Nov 2"}}
        cards.append({
            "name": name, "app": app, "what": what, "version": ix["active"], "steps": len(y["steps"]),
            "inputs": list(y["inputs"].keys()), "outputs": y["outputs"], "hand": hand, "hand_from": hand_from, "real": real, "repair": repair,
            "after_batch": _after_batch(ix),
            "src": src(f"data/routines/{name}/index.json"), "yaml_src": src(f"data/routines/{name}/v{ix['active']}.yaml"),
        })
    return {"cards": cards, "runs_src": src("eval/results/showcase/runs/runs.md"),
            "live_src": src(rel(LIVE), "the real posts' task rows"), "doc_src": src("docs/demo-showcase.md"),
            "p3_src": src("eval/results/showcase/p3.md")}


def watches() -> dict:
    """Watching the phone: the trigger kinds (from the scheduler's code) and the Nov 2 live check of notification triggers
    on Envoy's phone with real comments (phone-watch's report, its table copied)."""
    kinds = re.search(r"^KINDS = \(([^)]*)\)", (REPO / "backend/api/scheduler.py").read_text(), re.M).group(1)
    md = (REPO / "docs/reports/phone-watch-report.md").read_text()
    # The report's table is indented under a list item; read it with the indent taken off.
    table = next(t for t in md_tables("\n".join(l.strip() for l in md.splitlines()))
                 if t and "Landed on the Pixel" in t[0])
    return {"kinds": re.findall(r'"(\w+)"', kinds), "kinds_src": src("backend/api/scheduler.py", "KINDS"),
            "live": [{k: plain(v) for k, v in r.items()} for r in table],
            "src": src("docs/reports/phone-watch-report.md", "Stage 2, the live API and the Pixel"),
            "code_src": src("backend/api/notifications.py"),
            "muse": image(REPO / "eval/results/muse-link/e1-muse-tells-you-unprompted.jpg", "muse-watches-updates",
                          crop=(0, 64, 564, 1146)),
            "muse_src": src("eval/results/muse-link/e1-muse-tells-you-unprompted.jpg")}


def keys() -> dict:
    """A key per agent: the tool groups (from the code), the Settings › Agents card a key is made on (a test copy), and the
    Spark agent on a read-only key."""
    auth = (REPO / "backend/api/auth.py").read_text()
    block = auth.split("TOOL_GROUPS", 1)[1].split("}\n", 1)[0]
    groups = {g: sorted(re.findall(r'"(\w+)"', names)) for g, names in re.findall(r'"(\w+)": frozenset\(\{([^}]*)\}\)', block)}
    per_minute = int(re.search(r"^RUN_PER_MINUTE = (\d+)", (REPO / "backend/api/agents.py").read_text(), re.M).group(1))
    door = REPO / "eval/results/agent-door"
    return {"groups": groups, "groups_src": src("backend/api/auth.py", "TOOL_GROUPS"), "per_minute": per_minute,
            "readonly": spark_run(SPARK / "readonly-key-run.json"), "readonly_src": src(rel(SPARK / "readonly-key-run.json")),
            "readonly_shot": image(SPARK / "readonly-key-run.png", "keys-spark-read-only", 1600),
            "settings": image(door / "agent-tools-new-1080p.png", "keys-settings-agents", crop=(545, 120, 1245, 605)),
            "settings_src": src("eval/results/agent-door/agent-tools-new-1080p.png"),
            "doc_src": src("docs/agents.md"), "report_src": src("docs/reports/agent-keys-report.md")}


def numbers(data: dict) -> dict:
    """Every headline number the site shows, with where it came from and whether it is from the eval-final tag yet."""
    st = data["eval"]
    rows = [{"what": s["suite"], "value": s["result"], "commit": s["ran_on"], "final": "eval-final" in s["ran_on"],
             "src": st["src"]["path"]} for s in data["proof"]["suites"]]
    p = data["proof"]["phone"]
    rows.append({"what": "Pixel 5: the 10 core routines on 3 new bookings each", "value": f"{p['passed']}/{p['runs']}, {p['calls']} model calls",
                 "commit": p["commit"], "final": False, "src": p["src"]["path"]})
    # The AndroidWorld work was merged into main on Oct 29 (105d04e); its headline's "as on main" is main before that merge.
    rows.append({"what": "AndroidWorld", "value": data["proof"]["aw"]["headline"], "commit": "merged into main Oct 29 (105d04e)",
                 "final": False, "src": data["proof"]["aw"]["src"]["path"]})
    h = data["proof"]["aw"]["hybrid"]
    rows.append({"what": "AndroidWorld, the shipped default (hybrid) on main", "commit": h["commit"], "final": False,
                 "value": f"{h['all']['success']}/{h['all']['n']} ({h['all']['rate']}%); held-out {h['held']['success']}/{h['held']['n']} "
                          f"({h['held']['rate']}%), {h['date']}", "src": h["summary_src"]["path"]})
    return {"eval_final": st, "rows": rows}


def build() -> dict:
    data = {
        "meta": {"repo_url": REPO_URL},
        "eval": eval_status(),
        "agents": agents(),
        "tools": tools(),
        "showcase": showcase(),
        "batch": batch(),
        "watches": watches(),
        "keys": keys(),
        "first_run": first_run(),
        "learned": learned(),
        "repair": repair(),
        "real": real_apps(),
        "learn_path": learn_path(),
        "readme": readme_facts(),
        "teach": teach(),
        "memory": memory(),
        "safety": safety(),
        "models": models(),
        "proof": proof(),
        "built": built(),
    }
    data["numbers"] = numbers(data)
    (DATA / "numbers.json").parent.mkdir(parents=True, exist_ok=True)
    (DATA / "numbers.json").write_text(json.dumps(data["numbers"], indent=1, ensure_ascii=False) + "\n")
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
