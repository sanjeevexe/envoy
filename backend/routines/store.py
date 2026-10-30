"""The routine library: versions, candidate patches on trial, rollback, run history (design doc,
App routines › Patching and versions).

  data/routines/<name>/
    index.json        active version, every version's status and changes, recent runs
    v1.yaml, v2.yaml  each version in full
    history/v2/       the evidence for a patched version: before/after screenshots of the repair

- A successful repair becomes a candidate patch, saved as a new version marked "trial".
- The trial is replayed right away from a reset (test apps) and becomes active if it passes on its
  own; otherwise it is rejected and the previous version stays active (rollback).
- If a routine fails more than half of its recent runs, it is flagged for recompiling from a fresh
  full-agent run.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from routines.executor import Patch, RunOutcome
from routines.model import Routine, dump_yaml, load_yaml

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / "data" / "routines"
RECENT_RUNS = 6
MIN_RUNS_FOR_RECOMPILE = 4


def apply_patches(base: Routine, patches: list[Patch]) -> tuple[Routine, list[str]]:
    """A new routine with the patches applied (the caller assigns the version). Returns it and the change list."""
    r = base.model_copy(deep=True)
    changes: list[str] = []
    latest: dict[tuple[str, str, int | None], Patch] = {}
    for p in patches:  # one patch per step and kind: the latest wins
        latest[(p.step_id, p.kind, p.check_index)] = p
    order = {"locator": 0, "check": 1, "post": 1, "remove": 2, "replace": 3, "insert_before": 4, "insert_after": 5}
    for p in sorted(latest.values(), key=lambda p: order[p.kind]):
        try:
            i = r.step_index(p.step_id)
        except StopIteration:
            continue
        step = r.steps[i]
        if p.kind == "locator" and p.locator is not None:
            step.action.target = p.locator
            for c in step.post:  # a post-check that pointed at the same element follows it
                if c.locator is not None and c.locator.resource_id and c.locator.resource_id == (base.steps[i].action.target or p.locator).resource_id:
                    c.locator = c.locator.model_copy(update={"text": p.locator.text})
        elif p.kind == "check" and p.check is not None and p.check_index is not None and p.check_index < len(step.post):
            step.post[p.check_index] = p.check
        elif p.kind == "post" and p.checks:
            step.post = p.checks
        elif p.kind == "remove":
            # The screen this step handled no longer appears: what used to follow it now follows the step before, and
            # the step becomes optional (skipped when its screen doesn't come, used if it ever does) rather than
            # deleted, so the patched routine still runs on the old layout.
            if i > 0 and r.steps[i].post and any(c.kind != "screen_changed" for c in r.steps[i].post):
                r.steps[i - 1].post = [c.model_copy(deep=True) for c in r.steps[i].post]
            r.steps[i].optional = True
        elif p.kind == "replace" and p.steps:
            r.steps[i:i + 1] = p.steps
        elif p.kind == "insert_before" and p.steps:
            r.steps[i:i] = p.steps
        elif p.kind == "insert_after" and p.steps:
            r.steps[i + 1:i + 1] = p.steps
        else:
            continue
        changes.append(p.description)
    return r, changes


VERSION_FIELDS = {"version", "status", "parent_version", "changes"}  # a version's own bookkeeping, not what it runs


def same_program(a: Routine, b: Routine) -> bool:
    """Two routines that run the same way: every field but the version's bookkeeping is equal, as saved (the YAML round
    trip leaves out defaults and turns tuples into lists, which don't change how a routine runs)."""
    def saved(r: Routine) -> dict[str, Any]:
        return load_yaml(dump_yaml(r)).model_dump(exclude=VERSION_FIELDS)
    return saved(a) == saved(b)


class RoutineStore:
    def __init__(self, root: Path = LIBRARY) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    # ---- reading ----------------------------------------------------------------------------

    def _dir(self, name: str) -> Path:
        return self.root / name

    def index(self, name: str) -> dict[str, Any]:
        p = self._dir(name) / "index.json"
        return json.loads(p.read_text()) if p.exists() else {"name": name, "active": None, "versions": [], "runs": [], "needs_recompile": False}

    def _write_index(self, name: str, idx: dict[str, Any]) -> None:
        (self._dir(name) / "index.json").write_text(json.dumps(idx, indent=1, ensure_ascii=False, default=str))

    def names(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir() if (p / "index.json").exists())

    def get(self, name: str, version: int | None = None) -> Routine:
        idx = self.index(name)
        v = version or idx["active"]
        if v is None:
            raise KeyError(f"{name} has no active version")
        return load_yaml((self._dir(name) / f"v{v}.yaml").read_text())

    def active(self) -> list[Routine]:
        out = []
        for n in self.names():
            if self.index(n).get("active"):
                out.append(self.get(n))
        return out

    def _next_version(self, name: str) -> int:
        return max((v["version"] for v in self.index(name)["versions"]), default=0) + 1

    def _save(self, r: Routine) -> None:
        d = self._dir(r.routine)
        d.mkdir(parents=True, exist_ok=True)
        (d / f"v{r.version}.yaml").write_text(dump_yaml(r))

    def _set_status(self, name: str, version: int, status: str, **extra: Any) -> None:
        idx = self.index(name)
        for v in idx["versions"]:
            if v["version"] == version:
                v["status"] = status
                v.update(extra)
        self._write_index(name, idx)
        r = self.get(name, version)
        r.status = status  # type: ignore[assignment]
        self._save(r)

    # ---- writing ----------------------------------------------------------------------------

    def add(self, routine: Routine, verification: dict[str, Any] | None = None) -> Routine:
        """A newly compiled (and verified) routine becomes the next version and is active at once."""
        r = routine.model_copy(deep=True)
        r.version = self._next_version(r.routine)
        r.status = "active"
        idx = self.index(r.routine)
        prev = idx.get("active")
        if prev is not None:
            r.parent_version = prev
            r.changes = r.changes or [f"recompiled from {r.compiled_from.get('task_id')}"]
        self._save(r)
        idx.update(name=r.routine, app=r.app, active=r.version, needs_recompile=False)
        for v in idx["versions"]:
            if v["status"] == "active":
                v["status"] = "retired"
        idx["versions"].append({"version": r.version, "status": "active", "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                                "parent": r.parent_version, "changes": r.changes or ["compiled from " + str(r.compiled_from.get("task_id"))],
                                "verification": verification})
        self._write_index(r.routine, idx)
        return r

    def switch(self, name: str, on: bool) -> int | None:
        """Switch a routine off (no version is active, so the matcher skips it and an offer that names it runs the agent;
        its versions and runs stay) or back on (the version that was active). Returns the active version afterwards."""
        idx = self.index(name)
        if not idx["versions"]:
            raise KeyError(f"no routine {name}")
        if on:
            off = idx.pop("off", None)
            if idx.get("active") is None and off:
                idx["active"] = off["version"]
        elif idx.get("active") is not None:
            idx["off"] = {"version": idx["active"], "since": time.strftime("%Y-%m-%d %H:%M:%S")}
            idx["active"] = None
        self._write_index(name, idx)
        return idx.get("active")

    def propose(self, base: Routine, patches: list[Patch], source_task: str) -> Routine | None:
        """Apply candidate patches to `base` as a new version on trial. None if nothing applied, or if the patched routine
        runs exactly like `base` (a relaxed match that rewrote a locator to what it already was): that attempt is logged
        in the index (`patch_attempts`), and no version or trial is made."""
        r, changes = apply_patches(base, patches)
        if not changes:
            return None
        if same_program(r, base):
            idx = self.index(base.routine)
            idx.setdefault("patch_attempts", []).append({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "version": base.version,
                                                         "source_task": source_task, "result": "unchanged", "changes": changes})
            self._write_index(base.routine, idx)
            return None
        r.version = self._next_version(base.routine)
        r.status = "trial"
        r.parent_version = base.version
        r.changes = changes
        self._save(r)
        hist = self._dir(r.routine) / "history" / f"v{r.version}"
        hist.mkdir(parents=True, exist_ok=True)
        shots = []
        for p in patches:
            for src in p.evidence.get("screenshots", []):
                sp = Path(src)
                if sp.exists():
                    dst = hist / sp.name
                    shutil.copy2(sp, dst)
                    shots.append(str(dst.relative_to(self._dir(r.routine))))
        (hist / "patches.json").write_text(json.dumps(
            [{"kind": p.kind, "step": p.step_id, "description": p.description, "evidence": p.evidence} for p in patches],
            indent=1, ensure_ascii=False, default=str))
        idx = self.index(r.routine)
        idx["versions"].append({"version": r.version, "status": "trial", "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                                "parent": base.version, "changes": changes, "source_task": source_task, "screenshots": shots})
        self._write_index(r.routine, idx)
        return r

    def activate(self, name: str, version: int, trial: dict[str, Any]) -> None:
        idx = self.index(name)
        prev = idx.get("active")
        for v in idx["versions"]:
            if v["version"] == prev and v["status"] == "active":
                v["status"] = "retired"
            if v["version"] == version:
                v["status"] = "active"
                v["trial"] = trial
        idx["active"] = version
        self._write_index(name, idx)
        r = self.get(name, version)
        r.status = "active"
        self._save(r)
        if prev is not None and prev != version:
            p = self.get(name, prev)
            p.status = "retired"
            self._save(p)

    def reject(self, name: str, version: int, trial: dict[str, Any]) -> None:
        """Rollback: the trial version is rejected and the active version stays as it was."""
        self._set_status(name, version, "rejected", trial=trial)

    def record_run(self, name: str, outcome: RunOutcome, kind: str = "run") -> bool:
        """Log a run; returns True when the routine now fails more than half of its recent runs."""
        idx = self.index(name)
        idx["runs"].append({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind, "version": outcome.version, "task_id": outcome.task_id,
                            "status": outcome.status, "rung": outcome.rung, "model_calls": outcome.model_calls,
                            "duration_s": outcome.duration_s, "patches": len(outcome.patches)})
        recent = [r for r in idx["runs"] if r["kind"] == "run"][-RECENT_RUNS:]
        failures = sum(1 for r in recent if r["status"] != "done")
        idx["needs_recompile"] = len(recent) >= MIN_RUNS_FOR_RECOMPILE and failures > len(recent) / 2
        self._write_index(name, idx)
        return idx["needs_recompile"]
