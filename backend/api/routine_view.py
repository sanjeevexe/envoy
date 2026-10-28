"""A routine as the web app's detail view shows it (read only; routines/store.py stays the only writer):

- its steps: how each target is found (the locator), the checks before and after, the risk, optional steps;
- its versions as a timeline: v1 and the agent run it was compiled from, then each patched version with what the patch
  changed (the step's locator or check before and after), the run that repaired it and its fate (on trial, active,
  replaced, rolled back);
- its runs: time, phone, outcome, model calls and seconds, and what each saved against the agent run it was learned from
  (calls, seconds, dollars at standard prices).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agent.trace import RUNS
from routines.executor import RUNG_NAMES
from routines.model import Check, Locator, Routine, Step, StepAction, load_yaml
from routines.store import RoutineStore

OK = ("done", "agent_done", "done_unverified")
_SAFE = re.compile(r"[\w.-]+")
_SHOT = re.compile(r"[\w.-]+\.png")
_LOC_KEYS = ("visual", "text_has", "text", "alt_texts", "desc", "hint", "resource_id", "kind", "cls", "parent", "siblings", "in_list")
_KIND_WORD = {"EditText": "field", "Text": "text", "Toggle": "toggle", "Switch": "switch", "Button": "button", "Tab": "tab",
              "List": "list", "Image": "image", "CheckBox": "checkbox"}


# ---- steps ----------------------------------------------------------------------------------


def locator_view(loc: Locator | None) -> dict[str, Any] | None:
    """The attributes a locator scores, without the noise (no coordinates, no picture bytes)."""
    if loc is None:
        return None
    out: dict[str, Any] = {k: v for k in _LOC_KEYS if (v := getattr(loc, k)) not in (None, "", [], False)}
    if loc.crop:
        out["picture"] = True  # found by its recorded picture first, then by Muse grounding
    return out


def thing(loc: Locator | None) -> str:
    """A short name for the element a check looks at: “Check in” button, the cb_passenger_0 toggle."""
    if loc is None:
        return "an element"
    kind = _KIND_WORD.get(loc.kind or "", (loc.kind or "element").lower())
    if loc.visual:
        return f"the picture of “{loc.visual}”"
    if loc.text_has:
        return f"a {kind} with “{loc.text_has}”"
    label = loc.text or loc.desc or loc.hint
    if label:  # with its ID, so two checks on the same words (a title and a tab) read apart
        return f"“{label}” {kind}" + (f" ({loc.resource_id})" if loc.resource_id else "")
    return f"the {loc.resource_id} {kind}" if loc.resource_id else f"a {kind}"


def check_view(c: Check) -> dict[str, Any]:
    k = c.kind
    if k == "app_foreground":
        text = f"the app {c.package} is in front"
    elif k == "element_present":
        text = f"Shows {thing(c.locator)}"
    elif k == "element_absent":
        text = f"No longer shows {thing(c.locator)}"
    elif k == "text_visible":
        text = f"The words “{c.text}” are on screen"
    elif k == "text_absent":
        text = f"The words “{c.text}” are gone"
    elif k == "field_equals":
        text = f"{thing(c.locator)} holds “{c.value}”"
    elif k == "toggle_is":
        text = f"{thing(c.locator)} is {c.value}"
    elif k == "screen_changed":
        text = "The screen changed"
    else:
        text = f"The screen looks like the recorded one (similarity ≥ {c.min_similarity or 0:g})"
    return {"kind": k, "text": text[:1].upper() + text[1:], "locator": locator_view(c.locator)}


def action_view(a: StepAction) -> dict[str, Any]:
    verb = {"tap": "Tap", "long_press": "Long-press", "type": "Type", "scroll_until": "Scroll until it shows", "swipe": "Swipe",
            "back": "Press Back", "launch": "Open the app", "wait": "Wait"}[a.kind]
    out: dict[str, Any] = {"kind": a.kind, "verb": verb, "target": locator_view(a.target)}
    if a.kind == "type":
        out["value"], out["submit"] = a.value, a.submit
    elif a.kind == "scroll_until":
        out["detail"] = f"scrolling {a.direction or 'down'}" + (f", at most {a.max_scrolls} times" if a.max_scrolls else "")
    elif a.kind == "launch":
        out["detail"] = a.package
    elif a.kind == "wait":
        out["detail"] = f"{a.seconds or 0:g} s"
    elif a.kind == "swipe" and a.vector:
        dx, dy = a.vector
        out["detail"] = ("left" if dx < 0 else "right") if abs(dx) > abs(dy) else ("up" if dy < 0 else "down")
    return out


def step_view(s: Step) -> dict[str, Any]:
    return {"id": s.id, "intent": s.intent, "risk": s.risk, "optional": s.optional, "note": s.note, "action": action_view(s.action),
            "pre": [check_view(c) for c in s.pre], "post": [check_view(c) for c in s.post], "outputs": sorted(s.extract or {})}


# ---- versions -------------------------------------------------------------------------------


def diff(parent: Routine, child: Routine) -> list[dict[str, Any]]:
    """What a version changed against its parent, step by step, with each changed part before and after."""
    old = {s.id: s for s in parent.steps}
    after = {a.id: b.id for a, b in zip(parent.steps, parent.steps[1:])}  # removing a step moves its checks to the one before
    out: list[dict[str, Any]] = []
    for i, s in enumerate(child.steps):
        base = {"step": s.id, "intent": s.intent}
        p = old.get(s.id)
        if p is None:
            out.append({**base, "kind": "inserted", "what": "New step", "before": None, "after": step_view(s),
                        "follows": child.steps[i - 1].intent if i else None})
            continue
        if p.action.model_dump(exclude={"target"}) != s.action.model_dump(exclude={"target"}):
            out.append({**base, "kind": "action", "what": "What it does", "before": action_view(p.action), "after": action_view(s.action)})
        elif locator_view(p.action.target) != locator_view(s.action.target):
            out.append({**base, "kind": "locator", "what": "How its target is found",
                        "before": locator_view(p.action.target), "after": locator_view(s.action.target)})
        for which, a, b in (("Before", p.pre, s.pre), ("After", p.post, s.post)):
            for j in range(max(len(a), len(b))):
                ca, cb = (a[j] if j < len(a) else None), (b[j] if j < len(b) else None)
                if ca != cb:
                    out.append({**base, "kind": "check", "what": f"{which}-check {j + 1}", "index": j, "post": which == "After", "next": after.get(s.id),
                                "before": check_view(ca) if ca else None, "after": check_view(cb) if cb else None})
        if s.optional and not p.optional:
            out.append({**base, "kind": "optional", "what": "Now optional: skipped when its screen doesn't appear", "before": None, "after": None})
        if s.risk != p.risk:
            out.append({**base, "kind": "risk", "what": "Risk", "before": p.risk, "after": s.risk})
    ids = {s.id for s in child.steps}
    out += [{"step": s.id, "intent": s.intent, "kind": "removed", "what": "Step removed", "before": step_view(s), "after": None}
            for s in parent.steps if s.id not in ids]
    return out


_WHY = {
    "locator": "Found only by a relaxed match, so its locator now describes what the app shows.",
    "check": "This check matched only at the relaxed threshold; it now describes what the app shows.",
    "post": "Its after-checks failed but the next step was ready; they were rewritten from what happened.",
    "remove": "Its screen no longer appeared, so the step is skipped when the screen doesn't come.",
    "insert_after": "An extra screen appeared; a local repair handled it with a new step.",
    "insert_before": "The screen needed an extra action first; a local repair added it.",
    "replace": "A local repair replaced the step.",
}
_COMPATIBLE = {"locator": ("locator",), "check": ("check", "post", "locator", "remove"), "optional": ("remove",), "removed": ("replace", "remove"),
               "action": ("replace", "locator"), "inserted": ("insert_after", "insert_before", "replace")}


def _why(change: dict[str, Any], patches: list[dict[str, Any]]) -> None:
    """Attach the patch behind a change: why it was made and its evidence (match score, the model's reason)."""
    hit = None
    sid = change["step"]
    m = re.fullmatch(r"(.+?)_(?:(extra|pre)_)?\d+", sid) if change["kind"] == "inserted" else None
    anchor = {"extra": "insert_after", "pre": "insert_before", None: "replace"}[m.group(2)] if m else None
    for kind in _COMPATIBLE.get(change["kind"], ()):  # in order of preference: the patch of the same kind first
        if change["kind"] == "inserted":
            mine = [p for p in patches if p.get("kind") == kind and ((kind == anchor and p.get("step") == m.group(1)) or sid in p.get("description", ""))]
        elif change["kind"] == "check" and kind == "remove":
            mine = [p for p in patches if p.get("kind") == kind and p.get("step") in (sid, change.get("next"))]
        else:
            mine = [p for p in patches if p.get("kind") == kind and p.get("step") == sid]
        if kind == "check" and change.get("post"):  # "after-check 1" in a patch is the step's post[1]
            mine = [p for p in mine if f"after-check {change['index']} " in p.get("description", "")]
        if mine:
            hit = mine[-1]  # one patch per step and kind: the latest wins (routines/store.py)
            break
    if hit is None:
        return
    ev = hit.get("evidence") if isinstance(hit.get("evidence"), dict) else {}
    why = _WHY.get(hit.get("kind", ""), "")
    if hit.get("kind") == "locator" and ev.get("reasons"):
        why = "The element moved or changed; a local repair found it again."
    change["why"] = why
    change["patch"] = hit.get("description", "")
    if isinstance(ev.get("score"), (int, float)):
        change["score"] = round(ev["score"], 2)
    if ev.get("reasons"):
        change["reasons"] = [str(r) for r in ev["reasons"]][:3]


def _shots(name: str, version: int, rel: list[str], ran: Routine | None) -> list[dict[str, Any]]:
    """Before/after screenshots of a repair, paired. repair_08_2_before.png: step 8 of the version that ran, its second
    repair action."""
    pairs: dict[str, dict[str, Any]] = {}
    for r in rel:
        f = Path(r).name
        m = re.fullmatch(r"(.*?)_?(before|after)\.png", f)
        if not m or not _SHOT.fullmatch(f):
            continue
        key = m.group(1)
        n = re.fullmatch(r"repair_(\d+)_(\d+)", key)
        pair = pairs.setdefault(key, {"label": key, "step": int(n.group(1)) if n else None, "action": int(n.group(2)) if n else None})
        pair[m.group(2)] = f"/api/routines/{name}/history/{version}/{f}"
    out = list(pairs.values())
    for p in out:
        if p["step"] is not None:
            several = sum(1 for q in out if q["step"] == p["step"]) > 1
            p["label"] = f"step {p['step']}" + (f", action {p['action']}" if several else "")
            if ran is not None and 0 < p["step"] <= len(ran.steps):
                p["intent"] = ran.steps[p["step"] - 1].intent
    return out


def _source_run(task_id: str | None, runs_dir: Path) -> dict[str, Any] | None:
    """The agent run a routine was compiled from, from its trace (data/runs/<task_id>/run.json)."""
    if not task_id or not _SAFE.fullmatch(task_id):
        return None
    p = runs_dir / task_id / "run.json"
    try:
        d = json.loads(p.read_text())
    except (OSError, ValueError):
        return None
    usd = d.get("cost_at_standard_usd", d.get("cost_usd"))
    return {"task_id": task_id, "goal": d.get("goal"), "status": d.get("status"), "steps": d.get("steps"),
            "model_calls": d.get("model_calls"), "duration_s": d.get("duration_s"), "usd": round(usd, 5) if isinstance(usd, (int, float)) else None}


# ---- the whole view -------------------------------------------------------------------------


def detail(store: RoutineStore, name: str, tasks: Any = None, runs_dir: Path | None = None) -> dict[str, Any]:
    """The detail view of one routine. `tasks` (the API's TaskStore) names the phone each run used; `runs_dir` holds the
    agent runs' traces (data/runs)."""
    runs_dir = runs_dir or RUNS
    idx = store.index(name)
    entries = sorted(idx.get("versions", []), key=lambda v: v["version"])
    loaded: dict[int, Routine] = {}
    for v in entries:
        try:
            loaded[v["version"]] = store.get(name, v["version"])
        except Exception:  # noqa: BLE001 - a missing or broken file costs that version's details, not the view
            pass
    active_v = idx.get("active")
    status = {v["version"]: v.get("status") for v in entries}
    shown = loaded.get(active_v) or next((loaded[n] for n in sorted(loaded, reverse=True) if status.get(n) in ("active", "retired")), None) \
        or (loaded[max(loaded)] if loaded else None)
    if shown is None:
        raise KeyError(f"{name} has no readable version")
    runs = idx.get("runs", [])
    by_task = {r.get("task_id"): r for r in runs}

    # Versions: where each came from, what it changed, and how its trial went.
    versions: list[dict[str, Any]] = []
    root: dict[int, int] = {}  # version → the compiled version it descends from (whose agent run the savings compare to)
    sources: dict[int, dict[str, Any] | None] = {}
    for v in entries:
        n = v["version"]
        r = loaded.get(n)
        parent = v.get("parent") if v.get("parent") is not None else (r.parent_version if r else None)
        repaired = bool(v.get("source_task"))
        view: dict[str, Any] = {"version": n, "status": v.get("status"), "created": v.get("created"), "parent": parent,
                                "notes": v.get("changes") or [], "changes": [], "shots": _shots(name, n, v.get("screenshots") or [], loaded.get(parent))}
        if repaired:
            view["origin"] = "repaired"
            root[n] = root.get(parent, parent) if parent is not None else n
            src_run = by_task.get(v["source_task"])
            ev_dir = store.root / name / "history" / f"v{n}" / "patches.json"
            try:
                patches = json.loads(ev_dir.read_text())
            except (OSError, ValueError):
                patches = []
            patches = [p for p in patches if isinstance(p, dict)] if isinstance(patches, list) else []
            for p in patches:
                if not isinstance(p.get("evidence"), dict):
                    p["evidence"] = {}
            # Patches come from rung 2 (relaxed match) or 4 (local repair, Muse's reasons); the run may have climbed higher later.
            local = any(p["evidence"].get("reasons") for p in patches)
            rung = (4 if local else 2) if patches else (src_run.get("rung") if src_run else None)
            view["repair"] = {"task_id": v["source_task"], "rung": rung, "how": RUNG_NAMES.get(rung) if rung is not None else None,
                              "model_calls": src_run.get("model_calls") if src_run else None, "run_rung": src_run.get("rung") if src_run else None,
                              "duration_s": src_run.get("duration_s") if src_run else None, "time": src_run.get("time") if src_run else None}
            view["diffable"] = r is not None and parent in loaded
            if view["diffable"]:
                view["changes"] = diff(loaded[parent], r)
                for c in view["changes"]:
                    _why(c, patches)
        else:
            view["origin"] = "recompiled" if parent is not None else "compiled"
            root[n] = n
            cf = r.compiled_from if r else {}
            sources[n] = _source_run(cf.get("task_id"), runs_dir)
            view["compiled"] = {"task_id": cf.get("task_id"), "goal": cf.get("goal"), "compiler": cf.get("compiler"),
                                "at": cf.get("compiled_at"), "usd": cf.get("cost_usd"), "source": sources[n],
                                "verification": [{"case": c.get("case"), "passed": c.get("passed"), "duration_s": c.get("duration_s"),
                                                  "inputs": c.get("inputs") or {}}
                                                 for c in ((v.get("verification") or {}).get("cases") or [])]}
        if v.get("trial"):
            t = v["trial"]
            view["trial"] = {k: t.get(k) for k in ("passed", "task_id", "status", "model_calls", "duration_s")}
        if v.get("status") == "retired":
            view["replaced_by"] = next((w["version"] for w in entries if w["version"] > n and w.get("status") in ("active", "retired")), None)
        versions.append(view)

    # Which repairs changed each step of the version shown (back to its compile), for the step list's badges.
    changed: dict[str, list[dict[str, Any]]] = {}
    lineage, n = [], shown.version
    while n is not None and n not in lineage:
        lineage.append(n)
        n = next((v["parent"] for v in versions if v["version"] == n and v["origin"] == "repaired"), None)
    for v in versions:
        if v["version"] in lineage:
            for c in v["changes"]:
                kinds = changed.setdefault(c["step"], [])
                if not any(x["version"] == v["version"] for x in kinds):
                    kinds.append({"version": v["version"], "kind": c["kind"]})

    # Runs, each against the agent run its version was compiled from.
    proposed = {v["repair"]["task_id"]: v["version"] for v in versions if v.get("repair")}
    trials = {v["trial"]["task_id"]: (v["version"], v["trial"].get("passed")) for v in versions if v.get("trial")}
    out_runs: list[dict[str, Any]] = []
    for r in runs:
        tid = str(r.get("task_id") or "")
        src = sources.get(root.get(r.get("version"), -1))  # never another compile's agent run
        calls, secs = r.get("model_calls") or 0, r.get("duration_s")
        usd, estimated = 0.0, False
        if calls:  # runs record calls, not dollars: price them at the agent run's standard cost per call
            usd = round(calls * src["usd"] / src["model_calls"], 5) if src and src.get("usd") and src.get("model_calls") else None
            estimated = True
        task = None
        if tasks is not None:
            try:
                task = tasks.get(re.sub(r"-r\d+$", "", tid))
            except Exception:  # noqa: BLE001
                task = None
        ok = r.get("status") in OK
        saved = None
        if ok and src and src.get("model_calls") is not None and secs is not None:
            saved = {"calls": src["model_calls"] - calls, "seconds": round((src.get("duration_s") or 0) - secs, 2),
                     "usd": round(src["usd"] - usd, 5) if src.get("usd") is not None and usd is not None else None}
        event = None
        if tid in proposed:
            event = {"kind": "repaired", "version": proposed[tid]}
        elif tid in trials:
            event = {"kind": "trial", "version": trials[tid][0], "passed": trials[tid][1]}
        out_runs.append({"time": r.get("time"), "kind": r.get("kind", "run"), "version": r.get("version"), "task_id": tid,
                         "status": r.get("status"), "ok": ok, "rung": r.get("rung") or 0, "how": RUNG_NAMES.get(r.get("rung") or 0),
                         "model_calls": calls, "duration_s": secs, "usd": usd, "usd_estimated": estimated, "patches": r.get("patches") or 0,
                         "device": (task or {}).get("device"), "app_task": (task or {}).get("id"), "saved": saved, "event": event})

    # Savings over the runs that finished and have an agent run to compare with, and when they paid back the compile.
    done = [r for r in out_runs if r["saved"]]
    finished = [r for r in out_runs if r["ok"] and r["duration_s"] is not None]
    compile_usd = sum(v["compiled"]["usd"] or 0 for v in versions if v.get("compiled"))
    total = {"calls": sum(r["saved"]["calls"] for r in done), "seconds": round(sum(r["saved"]["seconds"] for r in done), 1),
             "usd": round(sum(r["saved"]["usd"] or 0 for r in done), 4)}
    paid_back, acc = None, 0.0
    for i, r in enumerate(done, 1):
        acc += r["saved"]["usd"] or 0
        if paid_back is None and compile_usd and acc >= compile_usd:
            paid_back = i
    src0 = sources.get(root.get(shown.version, -1))
    savings = {"source": src0, "runs": len(out_runs), "finished": sum(1 for r in out_runs if r["ok"]), "compared": len(done),
               "failed": sum(1 for r in out_runs if not r["ok"]),
               "model_calls": sum(r["model_calls"] for r in out_runs), "saved": total, "compile_usd": round(compile_usd, 4) or None,
               "net_usd": round(total["usd"] - compile_usd, 4) if compile_usd else None, "paid_back_after": paid_back,
               "median_s": sorted(r["duration_s"] for r in finished)[len(finished) // 2] if finished else None}

    trial = next((v["version"] for v in reversed(versions) if v["status"] == "trial"), None)
    return {"name": name, "app": shown.app, "intent": shown.intent, "description": shown.description, "start": shown.start,
            "inputs": {k: {"type": s.type, "description": s.description, "example": s.example, "from_memory": s.from_memory}
                       for k, s in shown.inputs.items()},
            "outputs": shown.outputs, "active": active_v, "shown": shown.version, "shown_status": status.get(shown.version), "trial": trial, "needs_recompile": bool(idx.get("needs_recompile")),
            "steps": [{**step_view(s), "changed_in": changed.get(s.id, [])} for s in shown.steps],
            "done": [check_view(c) for c in shown.done], "versions": versions, "runs": out_runs, "savings": savings}


def evidence_path(store: RoutineStore, name: str, version: int, file: str) -> Path | None:
    """A repair screenshot, only if the version's record lists it (no other file under the library is served)."""
    if name not in store.names() or not _SHOT.fullmatch(file):
        return None
    rel = f"history/v{version}/{file}"
    for v in store.index(name).get("versions", []):
        if v.get("version") == version and rel in (v.get("screenshots") or []):
            p = store.root / name / rel
            return p if p.is_file() else None
    return None
