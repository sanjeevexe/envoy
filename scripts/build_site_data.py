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


MAIN = HOME / "Desktop/Envoy"  # the main checkout: its gitignored run traces and the demo world's memory
LOOP_B = HOME / "Desktop/Envoy/.claude/worktrees/funny-goldwasser-65190c"  # loop B's checkout (new apps, Oct 30)

# One answer frame per real app for the grid: the last frame of a first run. Each was looked at for private data.
# Not here, on purpose: DoorDash (addresses), Lyft and Uber (the user's own accounts), Instagram (the Pixel's account).
APP_FRAMES = {
    "amazon_search_price": ("amazon", LOOP_A_API / "shots", "task-1030-145757-b70d", "loop-a"),
    "youtube_search_first_video": ("youtube", LOOP_A_API / "shots", "task-1030-162656-3e9e", "loop-a"),
    "play_app_rating": ("play", LOOP_A_API / "shots", "task-1030-164831-6b9e", "loop-a"),
    "chipotle_item_price": ("chipotle", LOOP_A_API / "shots", "task-1030-161523-ec65", "loop-a"),
    "gmail_search_subject": ("gmail", LOOP_A_API / "shots", "task-1030-180655-0535", "loop-a"),
    "starbucks_drink_calories": ("starbucks", LOOP_A_API / "shots", "task-1030-155711-51c2", "loop-a"),
    "clock_set_alarm": ("clock", LOOP_B / "data/api-loopb/shots", "task-1030-141911-98d6", "loop-b"),
    "chrome_get_cheapest_flight_price": ("flights", LOOP_B / "data/api-loopb/shots", "task-1030-214314-a891", "loop-b"),
}


def import_app_frames() -> dict:
    out = {}
    for routine, (name, shots, task_id, loop) in APP_FRAMES.items():
        last = sorted((shots / task_id).glob("*.jpg"))[-1]
        out[routine] = {"frame": _frame(last, f"app-{name}"), "task_id": task_id, "loop": loop,
                        "taken_et": datetime.fromtimestamp(int(last.stem) / 1000, ET).strftime("%Y-%m-%d %H:%M")}
    return out


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
    for name, fn in [("app-frames", import_app_frames), ("starbucks-repair", import_repair_call), ("planted", import_planted),
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
                      "call_src": src("site/data/recordings/starbucks-repair.json", "loop A's cost log")},
    }


# The grid's rows in eval/results/real-apps/table.md: (app column starts with, task column contains), first run and replay.
APP_ROWS = {
    "amazon_search_price": ("Amazon", ("Amazon (envoy-real)", "AA batteries")),
    "youtube_search_first_video": ("YouTube", ("YouTube (envoy-real)", "lofi")),
    "play_app_rating": ("Play Store", ("Play Store (envoy-real)", "Duolingo")),
    "starbucks_drink_calories": ("Starbucks", ("Starbucks (envoy-real)", "Grande"), ("Starbucks (envoy-real), v4", "Grande")),
    "chipotle_item_price": ("Chipotle", ("Chipotle (envoy-real)", "Guacamole")),
    "gmail_search_subject": ("Gmail", ("Gmail (envoy-real), after the routing fix", "DoorDash")),
    "doordash_order_meal": ("DoorDash", ("DoorDash (envoy-real), the user's real usual, v7 and the note-learner fix", "usual")),
    "clock_set_alarm": ("Clock", ("Clock (loop B)", "alarm")),
    "chrome_get_cheapest_flight_price": ("Google Flights in Chrome", ("Chrome / Google Flights by URL (loop B)", "cheapest"),
                                         ("Chrome / Google Flights by URL (loop B) — v4", "cheapest")),
    "lyft_get_ride_fare": ("Lyft", ("Lyft (loop B, envoy-real, the user's own account) — gate", "fare")),
    "instagram_post_reel": ("Instagram", ("Instagram (Pixel 5)", "reel")),
}
APP_NOTES = {
    "lyft_get_ride_fare": "On the user's own Lyft account, so the site shows numbers only: no screens and no routine steps. Fares only; never requested a ride.",
    "instagram_post_reel": "On the Pixel 5. Share was declined every time; nothing was posted. No screens shown here (the phone's account).",
    "doordash_order_meal": "Stops at the payment sheet; Place Order always asks first. No screens shown here (addresses).",
}


def apps() -> dict:
    rows = md_tables((REPO / "eval/results/real-apps/table.md").read_text())[0]

    def find(app: str, task: str) -> dict:
        hit = [r for r in rows if r["app"] == app and task.lower() in r["task"].lower()]
        assert len(hit) == 1, (app, task, len(hit))
        return hit[0]

    frames = json.loads((REC / "app-frames.json").read_text())
    cards = []
    for routine, (name, first_key, *replay_key) in APP_ROWS.items():
        first = find(*first_key)
        rep = find(*replay_key[0]) if replay_key else first
        ix = json.loads((REPO / f"data/routines/{routine}/index.json").read_text())
        y = yaml.safe_load((REPO / f"data/routines/{routine}/v{ix['active']}.yaml").read_text())
        when = re.search(r"\b(Oct \d+)", rep["notes"]) or re.search(r"\b(Oct \d+)", first["notes"])
        commit = re.search(r"main ([0-9a-f]{7})", rep["notes"])
        cards.append({
            "routine": routine, "name": name, "task": plain(first["task"]),
            "first": {"runs": plain(first["first runs (x/3)"]), "cost": plain(first["first-run s / $"])},
            "replay": {"runs": plain(rep["replays (x/N)"]), "cost": plain(rep["replay s / $"])},
            "when": when.group(1) if when else "", "commit": commit.group(1) if commit else "",
            "notes": plain(rep["notes"]) + ("" if rep is first else " — First runs: " + plain(first["notes"])),
            "version": ix["active"], "steps": len(y["steps"]), "inputs": list((y.get("inputs") or {}).keys()),
            "hand_fixed": any(not v.get("source_task") and v["version"] > 1 for v in ix["versions"]),
            "frame": frames.get(routine), "private": APP_NOTES.get(routine),
            "src": src("eval/results/real-apps/table.md", first["app"]),
            "routine_src": src(f"data/routines/{routine}/index.json"),
        })
    skylark = sorted(p.parent.name for p in (REPO / "data/routines").glob("skylark_*/index.json"))
    return {"cards": cards, "skylark": skylark, "src": src("eval/results/real-apps/table.md")}


def memory() -> dict:
    md = (REPO / "eval/results/final/memory.md").read_text()
    t = md_tables(md)
    m = re.search(r"\*\*(\d+) labeled items: (\d+)/(\d+) \((\d+)%\) of attributes right, (\d+) wrong values\.\*\*", md)
    stale = re.search(r"\*\*Stale facts served without a warning: (\d+) of (\d+)\.\*\*", md)
    run = re.search(r"Run (\d+) on `(\w+)`[^,]*, (\d{4}-\d\d-\d\d)", md)
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
    s_run = re.search(r"Run (\d+) on `(\w+)`[^,]*, (\d{4}-\d\d-\d\d)", s_md)
    i_run = re.search(r"Run (\d+) on `(\w+)`[^,]*, (\d{4}-\d\d-\d\d)", i_md)
    agent = re.search(r"Agent: (\d+) of (\d+) runs still did the task right[^;]*; it asked to do something else in (\d+)", i_md)
    routines = re.search(r"Routines: (\d+) of (\d+)", i_md)
    planted = dict(re.findall(r"- \*\*(\w+)\*\*: “(.+?)”", i_md))
    inbox = re.search(r"Injected values stored: \*\*(\d+)\*\*; instructions stored as facts: \*\*(\d+)\*\*", i_md)
    return {
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
        "approval_src": src("site/data/recordings/approval.json", "loop A's API copy, read only"),
    }


def models() -> dict:
    vision = json.loads((REPO / "eval/results/phase6/vision.json").read_text())
    p5 = (REPO / "docs/phase-5-results.md").read_text()
    voice = next(r for r in md_tables(p5)[1] if r and "Voice, scripted" in next(iter(r.values())))
    first = json.loads((REC / "starbucks-first.json").read_text())
    replay = json.loads((REC / "starbucks-replay.json").read_text())
    return {
        "vision": vision["summary"]["all"], "vision_canvas": vision["summary"]["skylark-canvas"],
        "vision_src": src("eval/results/phase6/vision.json"),
        "sam": json.loads((REC / "sam.json").read_text()),
        "sam_src": src("site/data/recordings/sam.json", "from data/runs/p6-canvas-src"),
        "phase6_src": src("docs/phase-6-results.md", "Results"),
        "voice": plain(list(voice.values())[1]), "voice_src": src("docs/phase-5-results.md", "Voice, scripted"),
        "wonder_calls": [c for c in first["calls"] if c["model"].startswith("muse-wonder")],
        "spark_calls": [c for c in first["calls"] if c["model"].startswith("muse-spark")],
        "replay_calls": replay["calls"],
    }


def proof() -> dict:
    rep = (REPO / "eval/results/final/report.md").read_text()
    t = md_tables(rep)
    suites = [{"suite": plain(r["Suite"]), "result": plain(r["Result"]), "ran_on": plain(r["Ran on"])} for r in t[0]]
    targets = [{k: plain(v) for k, v in r.items()} for r in t[1]]
    charts = {n: image(REPO / f"eval/results/final/charts/{n}.png", f"chart-{n}", 1600) for n in
              ["cost_and_time_over_repeated_runs", "success_by_system_and_layout", "recovery_by_injected_change", "real_apps_stages"]}
    aw = (REPO / "docs/androidworld-results.md").read_text()
    head = re.search(r"\*\*Headline\.\*\* (.+)", aw).group(1)
    held = re.search(r"\*\*Held-out half:\*\* (.+)", aw)
    sizes = json.loads((REPO / "eval/results/final/sizes.json").read_text())
    phone = sizes["devices"]["phone"]
    rows = phone.get("rows", phone) if isinstance(phone, dict) else phone
    rows = rows if isinstance(rows, list) else list(rows.values())
    ok = [r for r in rows if r.get("passed")]
    secs = sorted(r.get("duration_s") or 0 for r in rows)
    tests, files = 0, 0
    import ast
    for p in sorted((REPO / "backend/tests").rglob("test_*.py")):
        files += 1
        tests += sum(1 for n in ast.walk(ast.parse(p.read_text())) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                     and n.name.startswith("test"))
    return {
        "suites": suites, "targets": targets, "charts": charts, "src": src("eval/results/final/report.md"),
        "charts_src": src("eval/results/final/charts"),
        "aw": {"headline": plain(head), "held_out": plain(held.group(1)) if held else "",
               "src": src("docs/androidworld-results.md", "Headline")},
        "phone": {"passed": len(ok), "runs": len(rows), "calls": sum(r.get("calls") or 0 for r in rows),
                  "median_s": secs[len(secs) // 2] if secs else None, "commit": sizes["meta"]["code"]["short"],
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


def agents() -> dict:
    """Agents calling Envoy: the Spark agent's cross-post (four routine tools at once, on Envoy's phone), Muse's captures from
    the Oct 29 link sitting, and Claude Code's tasks on the live API (task rows read read-only)."""
    cc = json.loads((SPARK / "claude-code/task-rows.json").read_text())
    muse = REPO / "eval/results/muse-link"
    return {
        "crosspost": spark_run(SPARK / "crosspost/run2-four-posts.json"),
        "crosspost_src": src(rel(SPARK / "crosspost/run2-four-posts.json"), "the Spark agent page's event log"),
        "crosspost_readme": src(rel(SPARK / "crosspost/README.md")),
        "run1": {k: v for k, v in spark_run(SPARK / "crosspost/run1-three-posts.json").items() if k != "rows"},
        "run1_src": src(rel(SPARK / "crosspost/run1-three-posts.json")),
        "shots": {"asks": image(SPARK / "crosspost/run2-four-phone-asks.png", "agents-spark-four-asks", 1600),
                  "declined": image(SPARK / "crosspost/run2-all-declined.png", "agents-spark-all-declined", 1600)},
        "muse": {"mac": image(muse / "e3-mac-moves-clip-and-sidecar.jpg", "muse-mac-outbox", crop=(85, 38, 740, 476)),
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
        "report_src": src("prompts/agent-door-report.md"),
    }


# The app-only posts: each tool (a routine in the library), its app, and what it posts.
SHOWCASE = {
    "instagram_reel_song": ("Instagram", "A Reel set to a song from Instagram's music library"),
    "instagram_story_poll": ("Instagram", "A Story with a poll sticker"),
    "tiktok_post_sound": ("TikTok", "A TikTok with a sound from TikTok's library"),
    "youtube_short_sound": ("YouTube", "A YouTube Short with a sound from YouTube's library"),
}


def showcase() -> dict:
    """The four app-only routines: each one's first run and its replays (runs.md, rows copied), its active version in the
    library, and what happened when the user had it post for real (showcase's report, the result cell's first sentence)."""
    runs = md_tables((REPO / "eval/results/showcase/runs/runs.md").read_text())[0]
    report = (REPO / "prompts/showcase-report.md").read_text()
    posts = next(t for t in md_tables(report) if t and {"Post", "Task", "Routine", "Result"} <= set(t[0]))
    cards = []
    for name, (app, what) in SHOWCASE.items():
        lib = REPO / f"data/routines/{name}"
        ix = json.loads((lib / "index.json").read_text())
        active = next(v for v in ix["versions"] if v["version"] == ix["active"])
        y = routine_yaml(lib / f"v{ix['active']}.yaml")
        source = re.search(r"task-(\d\d)(\d\d)-(\d\d)(\d\d)(\d\d)-\w{4}", ix["versions"][0]["changes"][0])
        when = datetime(2026, *(int(source.group(i)) for i in range(1, 6)))
        # runs.md times the row from the runner's own clock, up to a second before the task's id
        first = next(r for r in runs if r["mode"] == "first" and abs((datetime.fromisoformat(r["when"]) - when).total_seconds()) <= 5)
        # Replays of the active version: rows from after it was compiled that name it, or name no version (the agent
        # finished the run). Earlier rows may name the same version number for a hand-tuned candidate tried that night.
        compiled = yaml.safe_load((lib / f"v{ix['active']}.yaml").read_text())["compiled_from"]["compiled_at"]
        mark, since = f"(routine {name} v{ix['active']})", compiled.replace(" ", "T")
        reps = [r for r in runs if r["mode"] == "replay" and r["routine"] == name and r["when"] >= since
                and (mark in r["approvals"] or "(routine " not in r["approvals"])]
        row = lambda r: {"when": r["when"], "ok": r["ok"] == "yes", "asked": r["asked at"], "to_ask": r["start → post asked"],
                         "calls": int(r["calls"]), "usd": float(r["$"])}
        real = []
        for p in posts:
            if f"`{name}`" in p["Routine"]:
                first_sentence = re.split(r"(?<=[.;])\s", plain(p["Result"]), maxsplit=1)[0]
                real.append({"post": plain(p["Post"]), "task": plain(p["Task"]), "routine": plain(p["Routine"]),
                             # test accounts' handles stay off the site
                             "result": re.sub(r" as @?[\w.-]+(?=[,;])", "", first_sentence)})
        cards.append({
            "name": name, "app": app, "what": what, "version": ix["active"], "steps": len(y["steps"]),
            "inputs": list(y["inputs"].keys()), "outputs": y["outputs"], "made": active["changes"][0], "compiled": compiled,
            "first": row(first) | {"task": source.group(0)}, "replays": [row(r) for r in reps], "real": real,
            "src": src(f"data/routines/{name}/index.json"), "yaml_src": src(f"data/routines/{name}/v{ix['active']}.yaml"),
        })
    return {"cards": cards, "runs_src": src("eval/results/showcase/runs/runs.md"),
            "report_src": src("prompts/showcase-report.md", "The real posts"), "doc_src": src("docs/demo-showcase.md"),
            "p3_src": src("eval/results/showcase/p3.md"),
            "poll": image(REPO / "eval/results/showcase/recon/20-ig-story-with-poll.png", "showcase-story-poll", 540),
            "poll_src": src("eval/results/showcase/recon/20-ig-story-with-poll.png")}


def watches() -> dict:
    """Watching the phone: the trigger kinds (from the scheduler's code) and the Nov 2 live check of notification triggers
    on Envoy's phone with real comments (phone-watch's report, its table copied)."""
    kinds = re.search(r"^KINDS = \(([^)]*)\)", (REPO / "backend/api/scheduler.py").read_text(), re.M).group(1)
    md = (REPO / "prompts/phone-watch-report.md").read_text()
    # The report's table is indented under a list item; read it with the indent taken off.
    table = next(t for t in md_tables("\n".join(l.strip() for l in md.splitlines()))
                 if t and "Landed on the Pixel" in t[0])
    return {"kinds": re.findall(r'"(\w+)"', kinds), "kinds_src": src("backend/api/scheduler.py", "KINDS"),
            "live": [{k: plain(v) for k, v in r.items()} for r in table],
            "src": src("prompts/phone-watch-report.md", "Stage 2, the live API and the Pixel"),
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
            "doc_src": src("docs/agents.md"), "report_src": src("prompts/agent-keys-report.md")}


def numbers(data: dict) -> dict:
    """Every headline number the site shows, with where it came from and whether it is from the eval-final tag yet."""
    st = data["eval"]
    rows = [{"what": s["suite"], "value": s["result"], "commit": s["ran_on"], "final": "eval-final" in s["ran_on"],
             "src": st["src"]["path"]} for s in data["proof"]["suites"]]
    p = data["proof"]["phone"]
    rows.append({"what": "Pixel 5: the 10 core routines on 3 new bookings each", "value": f"{p['passed']}/{p['runs']}, {p['calls']} model calls",
                 "commit": p["commit"], "final": False, "src": p["src"]["path"]})
    rows.append({"what": "AndroidWorld", "value": data["proof"]["aw"]["headline"][:160], "commit": "androidworld branch",
                 "final": False, "src": data["proof"]["aw"]["src"]["path"]})
    return {"eval_final": st, "rows": rows}


def build() -> dict:
    data = {
        "meta": {"repo_url": REPO_URL},
        "eval": eval_status(),
        "agents": agents(),
        "tools": tools(),
        "showcase": showcase(),
        "watches": watches(),
        "keys": keys(),
        "first_run": first_run(),
        "learned": learned(),
        "repair": repair(),
        "apps": apps(),
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
