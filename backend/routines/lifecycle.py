"""A routine's versions across its runs (design doc, App routines › Patching and versions).

A run that succeeded after a local repair leaves patches; they become a new version **on trial**. The next run of the
routine uses the trial version, and decides it: if that run finishes on its own (no repair, no agent, no model call) the
trial becomes active; otherwise it is rejected and the active version stays (rollback). The run itself still climbs the
ladder as usual, so a failed trial never fails the user's task.

The API's runner and the evaluation use these two functions, so the product and the measurements behave the same.
"""

from __future__ import annotations

from typing import Any

from routines.executor import RunOutcome
from routines.model import Routine
from routines.store import RoutineStore


def version_for_run(store: RoutineStore, name: str) -> Routine:
    """The version the next run should use: a pending trial if there is one, else the active version."""
    trials = [v["version"] for v in store.index(name).get("versions", []) if v.get("status") == "trial"]
    return store.get(name, max(trials)) if trials else store.get(name)


def after_run(store: RoutineStore, routine: Routine, outcome: RunOutcome, kind: str = "run", held: bool = False) -> dict[str, Any]:
    """Record the run, decide a trial it was, or put its patches on trial. Returns what happened, for the record.
    `held`: the person took over or paused the run. What the screens did was then partly their doing, so the run teaches
    nothing: no patch is proposed and a trial isn't decided (on the Pixel 5 an approved tap after a takeover didn't go
    through, and the repair that tapped again became "an extra screen appeared" on trial)."""
    store.record_run(routine.routine, outcome, kind=kind)
    if held:
        return {"held": routine.version} if routine.status == "trial" or outcome.patches else {}
    if routine.status == "trial":
        passed = outcome.status == "done" and outcome.model_calls == 0
        verdict = {"passed": passed, "task_id": outcome.task_id, "status": outcome.status, "model_calls": outcome.model_calls,
                   "duration_s": outcome.duration_s}
        (store.activate if passed else store.reject)(routine.routine, routine.version, verdict)
        return {"trial": routine.version, "result": "activated" if passed else "rejected"}
    if outcome.succeeded and outcome.patches:
        trial = store.propose(routine, outcome.patches, outcome.task_id)
        if trial is not None:
            return {"proposed": trial.version, "changes": trial.changes}
        if (store.index(routine.routine).get("patch_attempts") or [{}])[-1].get("source_task") == outcome.task_id:
            return {"unchanged": routine.version}  # the patches left the routine as it was: logged, no new version
    return {}
