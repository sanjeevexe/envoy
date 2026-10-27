"""Runs tasks: picks a routine (or the agent), leases the phone, hands sign-ins to the user, asks for approvals through
the web app, and writes what it learned into memory (design doc, One task, end to end).

1. **Plan.** A named routine, or the matcher's pick with inputs filled from memory; otherwise the agent with memory's
   notes. Answer-only questions don't come here: chat answers them from memory.
2. **Phone.** SkyLark runs on envoy-test, real apps on envoy-real; one task per phone at a time.
3. **Sign-in first.** If the app opens on a sign-in screen, the user is asked to take over; the run waits for hand back.
   A sign-in that appears mid-run (the agent or routine hands off) is handled the same way, then the run goes again.
4. **Run** through a `GatedDevice` (it waits while the user is in control) with the web approver.
5. **Remember.** A routine's outputs and final screen, or the agent's final screen, are written to memory.

Every trace step becomes a task step with a small screenshot (none on secure screens) and a live event.
"""

from __future__ import annotations

import asyncio
import io
import re
import time
from typing import Any

from agent.loop import AgentRunner, RunConfig
from agent.trace import TraceWriter
from memory.bridge import fill_inputs, notes_for, remember_run
from memory.service import MemoryService
from memory.store import MemoryStore
from models.adapter import ModelAdapter
from policy.signin import sign_in_reason
from routines.executor import ExecConfig, RoutineExecutor
from routines.matcher import RoutineMatcher
from routines.model import Routine
from routines.store import RoutineStore

from api.approvals import WebApprover
from api.devices import SKYLARK, DevicePool
from api.store import API_DIR, TaskStore

SHOTS = API_DIR / "shots"

# Apps a goal can name, for agent tasks with no routine (routines carry their own app).
APP_NAMES = {
    "skylark": SKYLARK, "amazon": "com.amazon.mShop.android.shopping", "target": "com.target.ui", "starbucks": "com.starbucks.mobilecard",
    "chipotle": "com.chipotle.ordering", "doordash": "com.dd.doordash", "gmail": "com.google.android.gm", "google maps": "com.google.android.apps.maps",
    "youtube music": "com.google.android.apps.youtube.music", "youtube": "com.google.android.youtube", "play store": "com.android.vending",
    "chrome": "com.android.chrome", "settings": "com.android.settings", "calendar": "com.google.android.calendar", "contacts": "com.google.android.contacts",
}
TRAVEL = re.compile(r"\b(flight|trip|gate|check(ed)?[ -]?in|boarding|seat|airline|known traveler)\b", re.I)


def app_for(goal: str) -> str | None:
    g = goal.lower()
    for name, pkg in APP_NAMES.items():
        if re.search(rf"\b{re.escape(name)}\b", g):
            return pkg
    return SKYLARK if TRAVEL.search(goal) else None  # the demo's airline is SkyLark


def describe(record: dict[str, Any]) -> dict[str, Any] | None:
    """A trace record as a task step: what was done, why, and its risk. Only what the task view shows."""
    kind = record.get("kind")
    if kind in ("plan", "replan"):
        plan = record.get("plan") or {}
        return {"kind": kind, "text": "; ".join(plan.get("subgoals") or []) or "planning", "app": plan.get("app")}
    if kind == "action":
        d = record.get("decision") or {}
        act = d.get("action") or {}
        target = (record.get("target") or {}).get("label") or ""
        what = act.get("type", "?") + (f' "{target}"' if target else "") + (f' "{act.get("text")}"' if act.get("text") and act.get("type") == "type" else "")
        secure = bool((record.get("screen_before") or {}).get("secure") or (record.get("screen_after") or {}).get("secure"))
        if secure and act.get("type") == "type":
            what = act.get("type", "?") + (f' "{target}"' if target else "") + " (text hidden: secure screen)"
        return {"kind": "action", "text": what, "reason": d.get("reason"), "risk": (record.get("risk") or {}).get("level"),
                "approval": record.get("approval"), "error": record.get("error"), "secure": secure}
    if kind == "handoff":
        return {"kind": "handoff", "text": record.get("reason")}
    if kind == "popup":
        return {"kind": "popup", "text": f"dismissed a pop-up ({record.get('handler')})"}
    if kind == "routine_step":
        return {"kind": "routine_step", "text": record.get("id"), "status": record.get("status"), "rung": record.get("rung"),
                "detail": record.get("detail"), "risk": None}
    if kind == "finish":
        return {"kind": "finish", "text": str(record.get("result") or record.get("detail") or record.get("status")), "status": record.get("status")}
    if kind == "model_error":
        return {"kind": "error", "text": record.get("error")}
    return None


class TaskRunner:
    def __init__(self, store: TaskStore, bus: Any, pool: DevicePool, memory: MemoryStore, routines: RoutineStore,
                 adapter: ModelAdapter | None = None, *, takeover_timeout_s: float = 1800, approval_timeout_s: float = 900) -> None:
        self.store, self.bus, self.pool, self.memory, self.routines = store, bus, pool, memory, routines
        self.adapter = adapter or ModelAdapter()
        self.takeover_timeout_s, self.approval_timeout_s = takeover_timeout_s, approval_timeout_s
        self.approvers: dict[str, WebApprover] = {}  # task id → its approver (the POST handler decides through it)
        self.trace_task: dict[str, str] = {}  # trace id → task id
        self.jobs: dict[str, asyncio.Task] = {}
        self.devices: dict[str, Any] = {}  # task id → raw device (for step screenshots)
        TraceWriter.listeners.append(self._on_trace)

    # ---- starting and stopping -----------------------------------------------------------------

    def start(self, goal: str, source: str, *, routine: str | None = None, inputs: dict[str, str] | None = None,
              app: str | None = None) -> dict[str, Any]:
        task = self.store.create(goal, source, routine=routine, inputs=inputs or {}, app=app)
        self.bus.publish("task", task=task)
        self.jobs[task["id"]] = asyncio.get_running_loop().create_task(self._run(task["id"], goal, routine, inputs or {}, app))
        return task

    def stop(self, tid: str) -> bool:
        job = self.jobs.get(tid)
        if job and not job.done():
            job.cancel()
            return True
        return False

    def _set(self, tid: str, **fields: Any) -> dict[str, Any] | None:
        task = self.store.update(tid, **fields)
        if task:
            self.bus.publish("task", task=task)
        return task

    # ---- the run -------------------------------------------------------------------------------

    async def _plan(self, tid: str, goal: str, routine_name: str | None, inputs: dict[str, str], app: str | None
                    ) -> tuple[Routine | None, dict[str, str], str | None, dict[str, str], int]:
        """(routine or None for the agent, inputs, app, where each input came from, model calls)."""
        calls = 0
        routine: Routine | None = None
        if routine_name:
            routine = self.routines.get(routine_name)
        else:
            scope = "test_app" if (app or app_for(goal)) == SKYLARK else "real"
            m = await RoutineMatcher(self.routines, self.adapter, data_scope=scope).match(goal, notes_for(self.memory, goal), task_id=f"{tid}-match")
            calls += m.model_calls
            if m.routine:
                routine, inputs = m.routine, {**m.inputs, **inputs}
        if routine is None:
            return None, inputs, app or app_for(goal), {}, calls
        filled = fill_inputs(self.memory, routine, goal, inputs)
        if filled.missing:
            self._step(tid, {"kind": "note", "text": f"routine {routine.routine} needs {', '.join(filled.missing)}: the agent does it instead"})
            return None, inputs, routine.app, {}, calls
        return routine, filled.inputs, routine.app, filled.sources, calls

    async def _run(self, tid: str, goal: str, routine_name: str | None, inputs: dict[str, str], app: str | None) -> None:
        t0 = time.time()
        calls, cost = 0, 0.0
        avd = None
        try:
            self._set(tid, status="running")
            routine, inputs, app, sources, calls = await self._plan(tid, goal, routine_name, inputs, app)
            kind = "routine" if routine else "agent"
            self._set(tid, kind=kind, routine=routine.routine if routine else None, inputs=inputs, app=app)
            if routine:
                self._step(tid, {"kind": "note", "text": f"using routine {routine.routine} v{routine.version}"
                                 + (f" with {', '.join(f'{k} = {v}' for k, v in inputs.items())}" if inputs else ""),
                                 "sources": sources})
            avd = self.pool.avd_for(app)
            device = await self.pool.device(avd)
            lease = self.pool.leases[avd]
            if lease.run_lock.locked():
                self._step(tid, {"kind": "note", "text": f"waiting for {avd}: another task is using it"})
            async with lease.run_lock:
                lease.task_id = tid
                self.devices[tid] = device
                self._set(tid, device=avd)
                gated = self.pool.gated(avd, device)
                loop = asyncio.get_running_loop()
                approver = WebApprover(self.store, self.bus, loop, tid, phone=lambda: device, timeout_s=self.approval_timeout_s,
                                       on_wait=lambda aid: self._set(tid, status="waiting_approval" if aid else "running", waiting_for=aid))
                self.approvers[tid] = approver
                skylark = app == SKYLARK
                scope = "test_app" if skylark else "real"
                status, result, outputs, final = "failed", "", {}, None
                for attempt in range(1, 4):
                    if attempt == 1 and app:
                        await gated.launch(app, fresh=True)
                        screen = await gated.wait_until_settled()
                        if (why := sign_in_reason(screen)) is not None and not await self._wait_for_user(tid, avd, f"sign-in needed: {why}"):
                            status, result = "needs_you", "waiting for you to sign in timed out"
                            break
                    trace_id = f"{tid}-r{attempt}"
                    self.trace_task[trace_id] = tid
                    notes = notes_for(self.memory, goal)
                    if routine:
                        ex = RoutineExecutor(gated, adapter=self.adapter, approver=approver,
                                             config=ExecConfig(data_scope=scope, contributor=skylark,
                                                               agent=RunConfig(data_scope=scope, contributor=skylark, max_cost_usd=0.25)))
                        out = await ex.run(routine, inputs, task_id=trace_id, launch="if_needed", allow_repair=True, allow_agent=True, memory=notes)
                        status, result, outputs = out.status, out.detail, out.outputs
                        calls += out.model_calls
                        cost += out.cost_at_standard_usd
                    else:
                        res = await AgentRunner(gated, adapter=self.adapter, approver=approver,
                                                config=RunConfig(data_scope=scope, contributor=skylark, max_cost_usd=0.25)).run(goal, task_id=trace_id, memory=notes)
                        status, result = res.status, res.result
                        calls += res.model_calls
                        cost += res.cost_at_standard_usd
                    if status == "handoff":
                        if await self._wait_for_user(tid, avd, result or "the agent needs you"):
                            continue
                        status, result = "needs_you", "waiting for you timed out"
                    break
                final = await device.observe()
                done = status in ("done", "agent_done", "done_unverified")
                memory = await self._remember(tid, routine, inputs, outputs, final, scope) if done else None
                text = result
                if routine and outputs:
                    text = "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in outputs.items() if v) or result
                end = "done" if done else ("declined" if status == "declined" else ("needs_you" if status in ("needs_you", "needs_user") else "failed"))
                self._set(tid, status=end, result=text, detail=result, model_calls=calls, cost_usd=round(cost, 4),
                          memory=memory, waiting_for=None)
        except asyncio.CancelledError:
            self._set(tid, status="stopped", detail="stopped by you", waiting_for=None)
            raise
        except Exception as e:  # noqa: BLE001 - a task failure is reported, never crashes the server
            self._set(tid, status="failed", detail=f"{type(e).__name__}: {e}"[:400], waiting_for=None)
        finally:
            if avd:
                lease = self.pool.leases[avd]
                if lease.task_id == tid:
                    lease.task_id = None
                if lease.user_control:
                    self.pool.hand_back(avd, by="task ended")
            self.approvers.pop(tid, None)
            self.devices.pop(tid, None)
            self.bus.publish("task_finished", task_id=tid, duration_s=round(time.time() - t0, 1))

    async def _wait_for_user(self, tid: str, avd: str, reason: str) -> bool:
        self._set(tid, status="needs_you", waiting_for="takeover", detail=reason)
        self._step(tid, {"kind": "handoff", "text": f"{reason}: take over, then hand back"})
        self.pool.request_takeover(avd, reason)
        ok = await self.pool.wait_for_hand_back(avd, self.takeover_timeout_s)
        if ok:
            self._step(tid, {"kind": "note", "text": "handed back: the agent looks at the screen again"})
            self._set(tid, status="running", waiting_for=None)
        return ok

    async def _remember(self, tid: str, routine: Routine | None, inputs: dict[str, str], outputs: dict[str, Any],
                        final: Any, scope: str) -> dict[str, Any] | None:
        svc = MemoryService(self.memory, self.adapter, data_scope=scope)  # type: ignore[arg-type]
        try:
            if routine:
                rep, screen_rep = await remember_run(svc, routine, inputs, outputs, task_id=tid, final_screen=final)
                reps = [r for r in (screen_rep, rep) if r is not None]
            else:
                reps = [await svc.ingest_screen(final, task_id=tid)]
        except Exception as e:  # noqa: BLE001
            self._step(tid, {"kind": "error", "text": f"memory: {type(e).__name__}: {e}"[:300]})
            return None
        facts: dict[str, int] = {}
        for r in reps:
            for k, v in r.facts.items():
                facts[k] = facts.get(k, 0) + v
        ents = sorted({f"{x.type} {x.entity}" for r in reps for x in r.resolved})
        summary = {"facts": facts, "entities": ents}
        self._step(tid, {"kind": "memory", "text": "memory updated: " + (", ".join(f"{v} {k}" for k, v in facts.items() if v) or "nothing new"),
                         "entities": ents})
        return summary

    # ---- steps and live events ------------------------------------------------------------------

    def _step(self, tid: str, data: dict[str, Any]) -> None:
        seq = self.store.add_step(tid, data)
        self.bus.publish("step", task_id=tid, step={"seq": seq, "time": time.time(), **data})

    def _on_trace(self, trace_id: str, record: dict[str, Any]) -> None:
        tid = self.trace_task.get(trace_id) or next((t for k, t in self.trace_task.items() if trace_id.startswith(k)), None)
        if tid is None:
            return
        data = describe(record)
        if data is None:
            return
        if data["kind"] in ("action", "routine_step") and not data.get("secure"):
            shot = self._thumbnail(tid)
            if shot:
                data["shot"] = shot
        self._step(tid, data)

    def _thumbnail(self, tid: str) -> str | None:
        """A small picture of the screen after a step, never of a secure screen."""
        device = self.devices.get(tid)
        if device is None or getattr(getattr(device, "_last", None), "secure", False):
            return None
        try:
            img = device.grpc.frame(360, timeout=2)
            folder = SHOTS / tid
            folder.mkdir(parents=True, exist_ok=True)
            name = f"{int(time.time() * 1000)}.jpg"
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=60)
            (folder / name).write_bytes(buf.getvalue())
            return f"{tid}/{name}"
        except Exception:  # noqa: BLE001
            return None
