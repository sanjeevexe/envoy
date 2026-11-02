"""Runs tasks: picks a routine (or the agent), leases the phone, hands sign-ins to the user, asks for approvals through
the web app, and writes what it learned into memory (design doc, One task, end to end).

1. **Plan.** A named routine, or the matcher's pick with inputs filled from memory; otherwise the agent with memory's
   notes. Answer-only questions don't come here: chat answers them from memory. Then **Before I start**: one `preflight`
   step says what to expect (api/preflight.py: the phone, a sign-in seen before, approvals, the routine's usual time).
2. **Phone.** `api/routing.py` picks it: SkyLark on envoy-test and real apps on envoy-real by default, your Android
   phone when you ask for it (or the app needs it). The real phone is used only after you say yes; while the task runs
   there its banner shows, and a touch, Pause or another app coming to the front hands the phone to you. One task per
   phone at a time. An app that shows a bot check on an emulator blocks emulators: from then on it runs on your phone
   (set in Settings › Phones, where you can undo it), and this task moves there too if you say yes.
   **The app.** On an emulator, an app the task names that isn't installed is installed from the Play Store first
   (`api/install.py`): free apps only; a paid one asks you, and Envoy never pays.
3. **Sign-in first.** If the app opens on a sign-in screen, the user is asked to take over; the run waits for hand back.
   With saved logins on for that kind of phone (off by default), the phone's password manager fills it first and Envoy
   presses the app's sign-in button after your yes (api/autofill.py); anything else is handed to you as before.
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

from agent.loop import TASK_CAP_USD, WONDER_TASK_CAP_USD, AgentRunner, RunConfig
from agent.trace import TraceWriter
from memory.app_notes import AppNotes
from memory.bridge import fill_inputs, notes_for, remember_run
from memory.service import MemoryService
from memory.store import MemoryStore
from memory.usual import Usual, resolve as resolve_usual, with_usual
from models.adapter import ModelAdapter, profile_models
from policy.approval_rules import ApprovalRules
from policy.approvals import ApprovalRequest
from policy.botcheck import bot_check_reason, is_bot_check_handoff
from policy.signin import sign_in_reason
from routines.executor import ExecConfig, RoutineExecutor
from routines.lifecycle import after_run, version_for_run
from routines.matcher import RoutineMatcher
from routines.model import Routine
from routines.screens import norm
from routines.store import RoutineStore

from api import autofill
from api.approvals import WebApprover
from api.devices import NAMES, SKYLARK, DevicePool, phone_ref
from api.install import Installer, app_named_in
from api.preflight import check as preflight_check
from api.routing import (BLOCKS_EMULATOR, Choice, app_label, app_names as blocking_app_names, asks_for_phone, blocks_emulator, choose,
                         needs_real_phone, strip_phone_words)
from api.store import API_DIR, TaskStore
from testapps.skylark import SkyLark

SHOTS = API_DIR / "shots"

# Apps a goal can name, for agent tasks with no routine (routines carry their own app).
APP_NAMES = {
    "skylark": SKYLARK, "amazon": "com.amazon.mShop.android.shopping", "target": "com.target.ui", "starbucks": "com.starbucks.mobilecard",
    "chipotle": "com.chipotle.ordering", "doordash": "com.dd.doordash", "gmail": "com.google.android.gm", "google maps": "com.google.android.apps.maps",
    "youtube music": "com.google.android.apps.youtube.music", "youtube": "com.google.android.youtube", "play store": "com.android.vending",
    "chrome": "com.android.chrome", "settings": "com.android.settings", "calendar": "com.google.android.calendar", "contacts": "com.google.android.contacts",
    "instagram": "com.instagram.android", "tiktok": "com.zhiliaoapp.musically",
}
TRAVEL = re.compile(r"\b(flight|trip|gate|check(ed)?[ -]?in|boarding|seat|airline|known traveler)\b", re.I)
# What comes before an app's name when a goal names it as the app it's about: "on DoorDash", "in YouTube Music",
# "open Gmail and ...", "using Chrome", "with Lyft" ("in the Gmail app" and "In Gmail, ..." are app_named_in's).
AS_APP = re.compile(r"\b(?:in|on|open|launch|use|using|with|via)\s+(?:the\s+|my\s+)?$")
# A bot check in a browser is a website's, not the browser's: it doesn't mean the browser blocks emulators.
BROWSERS = {"com.android.chrome", "org.mozilla.firefox", "com.brave.browser", "com.microsoft.emmx", "com.sec.android.app.sbrowser",
            "com.duckduckgo.mobile.android", "com.opera.browser"}
FRESH_INSTALL = ("{name} was just installed from the Play Store, so its first-run screens (welcome, onboarding, permissions) may "
                 "come first: get past them with their own Skip, Next, Forward or Continue buttons. Don't press Back on them: in a new app "
                 "that can close it (seen on Wikipedia). Don't sign in or create an account unless the task needs it.")


def app_for(goal: str, learned: dict[str, str] | None = None) -> str | None:
    """The app a goal is about: one Envoy knows by name (APP_NAMES, the apps that block emulators), one it installed
    before when the goal names it as an app (`learned`: name → package), else SkyLark for travel words. A goal naming
    more than one is about the one it names as the app ("In the Gmail app, search my mail for DoorDash" is Gmail's),
    else the one it names first; the longer name where two start at the same place ("YouTube Music", not "YouTube")."""
    g = goal.lower()
    known = {**APP_NAMES, **blocking_app_names()}
    named = app_named_in(goal)
    # A learned app counts only when named as an app ("in the Weather app"), so it doesn't take every question about the weather.
    if named is not None and (pkg := known.get(norm(named)) or (learned or {}).get(norm(named))):
        return pkg
    # Loop A, Oct 30: the first name in APP_NAMES's order won, so a Gmail search for DoorDash fresh-launched DoorDash.
    places = [(AS_APP.search(g[:m.start()]) is None, m.start(), -len(name), pkg)
              for name, pkg in known.items() for m in re.finditer(rf"\b{re.escape(name)}\b", g)]
    if places:
        return min(places)[-1]
    if named is not None:  # one Envoy doesn't know yet is an app to install, not SkyLark because of travel words ("in the Expedia app, my flight")
        return None
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
        self.jobs: dict[str, Any] = {}  # asyncio tasks, or concurrent futures when started from another thread
        self.loop: asyncio.AbstractEventLoop | None = None  # the API's loop (set at startup)
        self.devices: dict[str, Any] = {}  # task id → raw device (for step screenshots)
        self.pending_steps: dict[str, asyncio.Task] = {}  # task id → its latest step still taking its picture
        self.phone_asks: dict[str, asyncio.Future] = {}  # task id → your answer to "use your Android phone?"
        self.phone_allowed: dict[str, str] = {}  # task id → the phone you said yes to (it moved off an emulator, or start's phone_ok)
        self.moved: set[str] = set()  # tasks that moved to your phone (their runs there get their own trace ids)
        self.install_apps = True  # install an app the task names that the emulator doesn't have (api/install.py)
        self.on_final: list[Any] = []  # called with (task id, final screen, routine outputs) after a run's last look (api/crossapp.py)
        self.crossapp: Any = None  # cross-app answers (api/crossapp.py), set by the app
        self.app_notes = AppNotes(memory, self.adapter)  # what Envoy has learned about each app (memory/app_notes.py)
        TraceWriter.listeners.append(self._on_trace)

    # ---- starting and stopping -----------------------------------------------------------------

    def start(self, goal: str, source: str, *, routine: str | None = None, inputs: dict[str, str] | None = None,
              app: str | None = None, request: str | None = None, phone: str | None = None, parent: str | None = None,
              phone_ok: str | None = None) -> dict[str, Any]:
        """`request` is the user's own words when the goal was rephrased (chat): approvals are matched against it.
        `phone`: "phone", "emulator", a device id, or None (routing decides, including "… on my phone" in the words).
        `parent`: the cross-app task this one is a part of.
        `phone_ok`: the phone your yes already covers (you accepted an offer that named it), so it isn't asked for again.
        Any other phone routing picks still asks."""
        if asks_for_phone(goal) or asks_for_phone(request or ""):
            phone = phone or "phone"
            goal = strip_phone_words(goal)
        request = request or goal
        usual = self._usual(goal, request)
        if usual is not None:  # "my usual from <place>": the order you told me, spelled out for the matcher and the agent
            goal = with_usual(goal, usual, add_app=not app and not routine and app_for(goal, self._learned_names()) is None)
        task = self.store.create(goal, source, routine=routine, inputs=inputs or {}, app=app, request=request, models=profile_models(),
                                 **({"parent": parent} if parent else {}))
        if usual is not None:
            task["usual"] = {"place": usual.place, "order": usual.order, "app": usual.app}  # for chat's reply; Before I start shows it
        if phone_ok:
            self.phone_allowed[task["id"]] = phone_ok  # before the run is scheduled: _choose_phone reads it
        self.bus.publish("task", task=task)
        coro = self._run_task(task["id"], goal, routine, inputs or {}, app, phone)
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:  # MCP tools and approvers call in from worker threads
            running = None
        if running is not None and (self.loop is None or running is self.loop):
            self.jobs[task["id"]] = running.create_task(coro)
        elif self.loop is not None:
            self.jobs[task["id"]] = asyncio.run_coroutine_threadsafe(coro, self.loop)  # type: ignore[assignment]
        else:
            coro.close()
            raise RuntimeError("the task runner has no event loop yet")
        return task

    def _usual(self, goal: str, request: str) -> Usual | None:
        try:
            return resolve_usual(self.memory, f"{goal}\n{request}")
        except Exception:  # noqa: BLE001 - a usual that can't be read leaves the goal as you said it
            return None

    def app_names(self) -> list[str]:
        """Every app name a request can use: the ones Envoy knows, the ones that block emulators, and the ones it installed."""
        return [*APP_NAMES, *blocking_app_names(), *self._learned_names()]

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

    async def _run_task(self, tid: str, goal: str, routine_name: str | None, inputs: dict[str, str], app: str | None,
                        phone: str | None) -> None:
        """The task where routing puts it; then once more on your phone if it moved there (the app blocks emulators)."""
        try:
            moved = await self._run(tid, goal, routine_name, inputs, app, phone)
            if moved:
                task = self.store.get(tid) or {}
                await self._run(tid, goal, task.get("routine") or routine_name, task.get("inputs") or inputs, task.get("app") or app, moved)
        finally:
            self.phone_allowed.pop(tid, None)  # a yes covers this task only (unused when it ran on an emulator)

    async def _plan(self, tid: str, goal: str, routine_name: str | None, inputs: dict[str, str], app: str | None
                    ) -> tuple[Routine | None, dict[str, str], str | None, dict[str, str], int]:
        """(routine or None for the agent, inputs, app, where each input came from, model calls)."""
        calls = 0
        routine: Routine | None = None
        if routine_name:
            try:
                routine = self.routines.get(routine_name)
            except KeyError:  # named by an offer's template, but switched off (no active version) or not in this library
                self._step(tid, {"kind": "note", "text": f"routine {routine_name} isn't active: the agent does it instead"})
        else:
            scope = "test_app" if (app or app_for(goal, self._learned_names())) == SKYLARK else "real"
            m = await RoutineMatcher(self.routines, self.adapter, data_scope=scope).match(goal, notes_for(self.memory, goal), task_id=f"{tid}-match")
            calls += m.model_calls
            if getattr(m, "ambiguous", None):
                self._step(tid, {"kind": "note", "text": f"routines {' and '.join(m.ambiguous)} both fit and the request doesn't say "
                                 "which: the agent does it instead (name what you want back, e.g. the price, to use a routine)"})
            if m.routine:
                routine, inputs = m.routine, {**m.inputs, **inputs}
        if routine is None:
            return None, inputs, app or app_for(goal, self._learned_names()), {}, calls
        routine = version_for_run(self.routines, routine.routine)  # a patched version on trial is decided by this run
        filled = fill_inputs(self.memory, routine, goal, inputs)
        if filled.missing:
            self._step(tid, {"kind": "note", "text": f"routine {routine.routine} needs {', '.join(filled.missing)}: the agent does it instead"})
            return None, inputs, routine.app, {}, calls
        return routine, filled.inputs, routine.app, filled.sources, calls

    async def _run(self, tid: str, goal: str, routine_name: str | None, inputs: dict[str, str], app: str | None,
                   phone: str | None = None) -> str | None:
        """One run of the task. Returns your phone's id when the task should move there (the emulator can't run the app
        and you said yes), else None."""
        t0 = time.time()
        calls, cost = 0, 0.0
        avd, done, final, outputs, scope, routine = None, False, None, {}, "real", None
        learn: list[str] = []  # traces the app notes learn from once the phone is free
        announced = False
        try:
            self._set(tid, status="running")
            routine, inputs, app, sources, calls = await self._plan(tid, goal, routine_name, inputs, app)
            await self._preflight(tid, goal, routine, app, phone)
            kind = "routine" if routine else "agent"
            self._set(tid, kind=kind, routine=routine.routine if routine else None, inputs=inputs, app=app)
            if routine:
                self._step(tid, {"kind": "note", "text": f"using routine {routine.routine} v{routine.version}"
                                 + (f" with {', '.join(f'{k} = {v}' for k, v in inputs.items())}" if inputs else ""),
                                 "sources": sources})
            named = None if app else app_named_in(goal)  # an app Envoy doesn't know yet ("in the Wikipedia app")
            choice = await self._choose_phone(tid, app, phone, named=named)
            if choice is None:
                return None
            avd = choice.device
            assert avd is not None
            device = await self.pool.device(avd)
            if choice.real_phone:
                await self._ensure_app(tid, device, app)
            lease = self.pool.leases[avd]
            if lease.run_lock.locked():
                self._step(tid, {"kind": "note", "text": f"waiting for {avd}: another task is using it"})
            async with lease.run_lock:
                lease.task_id = tid
                self.devices[tid] = device
                self._set(tid, device=avd)
                self.pool.start_watch(avd, device, app, on_change=lambda paused, why: self._phone_paused(tid, paused, why))
                gated = self.pool.gated(avd, device)
                loop = asyncio.get_running_loop()
                approver = WebApprover(self.store, self.bus, loop, tid, phone=lambda: device, timeout_s=self.approval_timeout_s,
                                       rules=lambda: ApprovalRules.from_dict(self.store.setting("approval_rules")),
                                       on_wait=lambda aid: self._set(tid, status="waiting_approval" if aid else "running", waiting_for=aid))
                self.approvers[tid] = approver
                skylark = app == SKYLARK
                scope = "test_app" if skylark else "real"
                status, result, outputs, final = "failed", "", {}, None
                moved, installed, end = None, None, None
                if not choice.real_phone and (app or named):
                    app, installed, moved, end = await self._install_missing(tid, avd, gated, approver, app, named, goal)
                    if end is not None:
                        status, result = end
                for attempt in range(1, 1 if end or moved else 4):  # nothing to run when the app can't be had here
                    if attempt == 1 and app:
                        await gated.launch(app, fresh=True)
                        screen = await gated.wait_until_settled()
                        if not choice.real_phone and (bot := bot_check_reason(screen)) is not None:
                            moved, reason = await self._bot_check(tid, avd, app, screen, bot)
                            if moved or not await self._wait_for_user(tid, avd, reason):
                                status, result = "needs_you", reason
                                break
                            screen = await gated.wait_until_settled()
                        if (why := sign_in_reason(screen)) is not None \
                                and not await self._saved_login(tid, gated, approver, app, goal, choice.real_phone) \
                                and not await self._wait_for_user(tid, avd, f"sign-in needed: {why}"):
                            status, result = "needs_you", "waiting for you to sign in timed out"
                            break
                    trace_id = f"{tid}-r{attempt}" + ("-phone" if tid in self.moved else "")
                    self.trace_task[trace_id] = tid
                    notes = notes_for(self.memory, goal)
                    if installed:
                        notes = f"{notes}\n{FRESH_INSTALL.format(name=installed)}".strip()
                    if routine:
                        ex = RoutineExecutor(gated, adapter=self.adapter, approver=approver,
                                             config=ExecConfig(data_scope=scope, contributor=skylark,
                                                               agent=RunConfig(data_scope=scope, contributor=skylark, max_cost_usd=TASK_CAP_USD,
                                                                               max_cost_usd_wonder=WONDER_TASK_CAP_USD)),
                                             app_notes=self.app_notes)
                        out = await ex.run(routine, inputs, task_id=trace_id, launch="if_needed", allow_repair=True, allow_agent=True, memory=notes,
                                           request=goal)
                        held = any(s.get("kind") == "note" and (s.get("text") or "").startswith(("taken over", "paused:")) for s in self.store.steps(tid))
                        life = after_run(self.routines, routine, out, held=held) or {}  # repairs become a version on trial; a trial is activated or rolled back
                        if "held" in life:
                            self._step(tid, {"kind": "note", "text": f"routine {routine.routine}: nothing learned from this run (you took over or paused it)"})
                        elif life and "unchanged" not in life:  # a patch that changed nothing is logged in the library, not shown
                            self._step(tid, {"kind": "note", "text": (f"routine {routine.routine}: patched version v{life['proposed']} on trial for the next run"
                                                                      if "proposed" in life else f"routine {routine.routine} v{life['trial']}: trial {life['result']}")})
                        status, result, outputs = out.status, out.detail, out.outputs
                        calls += out.model_calls
                        cost += out.cost_at_standard_usd
                        if out.model_calls:  # a repair or the fallback agent: what broke and what worked is worth a note
                            learn += [d for d in (getattr(out, "trace_dir", None), (getattr(out, "agent", None) or {}).get("trace_dir")) if d]
                    else:
                        res = await AgentRunner(gated, adapter=self.adapter, approver=approver,
                                                config=RunConfig(data_scope=scope, contributor=skylark, max_cost_usd=TASK_CAP_USD,
                                                                 max_cost_usd_wonder=WONDER_TASK_CAP_USD),
                                                app_notes=self.app_notes).run(goal, task_id=trace_id, memory=notes)
                        status, result = res.status, res.result
                        calls += res.model_calls
                        cost += res.cost_at_standard_usd
                        if getattr(res, "trace_dir", None):
                            learn.append(res.trace_dir)
                    if status == "handoff":
                        reason, bot = result or "the agent needs you", None
                        if not choice.real_phone:  # a bot check the agent (or routine) stopped at: the app may block emulators
                            screen = await device.observe()
                            bot = bot_check_reason(screen) or (result if is_bot_check_handoff(result) else None)
                            if bot is not None:
                                moved, reason = await self._bot_check(tid, avd, app, screen, bot)
                                if moved:
                                    break
                        if (reason.startswith("sign-in needed") and await self._saved_login(tid, gated, approver, app, goal, choice.real_phone)) \
                                or await self._wait_for_user(tid, avd, reason):
                            continue
                        status, result = "needs_you", reason if bot else "waiting for you timed out"
                    break
                await self._steps_written(tid)
                if moved:
                    self._step(tid, {"kind": "note", "text": f"moving this task to {phone_ref(self.pool.phones.get(moved))}"})
                    announced = True  # its run on your phone says when it's finished
                    return moved
                final = await device.observe()
                for hook in list(self.on_final):
                    try:
                        hook(tid, final, outputs)
                    except Exception:  # noqa: BLE001 - a listener never breaks a run
                        pass
                done = status in ("done", "agent_done", "done_unverified")
                text = result
                if routine and outputs:
                    text = "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in outputs.items() if v) or result
                end = "done" if done else ("declined" if status == "declined" else ("needs_you" if status in ("needs_you", "needs_user") else "failed"))
                # Done as soon as the phone work is: memory is written afterwards, with the phone already free.
                self.pool.stop_watch(avd, device)  # the phone is free: the banner goes, and touches are yours again
                self._set(tid, status=end, result=text, detail=result, model_calls=calls, cost_usd=round(cost, 4), waiting_for=None)
                lease.task_id = None
                # Finished as far as you're concerned: the "Done" push goes now, not after memory is written (~10 s later).
                self.bus.publish("task_finished", task_id=tid, duration_s=round(time.time() - t0, 1))
                announced = True
            if done:
                self._step(tid, {"kind": "note", "text": "saving what it saw to memory"})
                memory = await self._remember(tid, routine, inputs, outputs, final, scope)
                self._set(tid, memory=memory)
            if learn:
                await self._learn_notes(tid, learn, app, goal, status, result, inputs, outputs, scope)
        except asyncio.CancelledError:
            self._set(tid, status="stopped", detail="stopped by you", waiting_for=None)
            raise
        except Exception as e:  # noqa: BLE001 - a task failure is reported, never crashes the server
            self._set(tid, status="failed", detail=f"{type(e).__name__}: {e}"[:400], waiting_for=None)
        finally:
            if avd:
                lease = self.pool.leases[avd]
                self.pool.stop_watch(avd, self.devices.get(tid))
                if lease.task_id == tid:
                    lease.task_id = None
                if lease.user_control:
                    self.pool.hand_back(avd, by="task ended")
            self.phone_asks.pop(tid, None)
            self.approvers.pop(tid, None)
            self.devices.pop(tid, None)
            if not announced:  # failures, stops and early returns
                self.bus.publish("task_finished", task_id=tid, duration_s=round(time.time() - t0, 1))
        return None

    async def _preflight(self, tid: str, goal: str, routine: Routine | None, app: str | None, phone: str | None) -> None:
        """Before I start (api/preflight.py): what to expect, as one `preflight` step, once per task (a task that moves to
        your phone runs `_run` again). No model call, no device action; if it fails there is no step and the run goes on."""
        try:
            if any(s.get("kind") == "preflight" for s in self.store.steps(tid)):
                return
            task = self.store.get(tid) or {}
            args = dict(request=task.get("request"), source=task.get("source"), app=app, routine=routine, phone=phone,
                        phone_ok=self.phone_allowed.get(tid))
            lines = preflight_check(self, goal, **args)
            if any(ln["kind"] in ("blocked", "device") for ln in lines) and not getattr(self.pool, "phones", None):
                # About your phone, and none seen yet (a fresh API): look once, so "it isn't connected" is true.
                await asyncio.to_thread(self.pool.refresh_phones)
                lines = preflight_check(self, goal, **args)
        except Exception:  # noqa: BLE001 - a heads-up never breaks the run
            return
        self._step(tid, {"kind": "preflight", "text": "before I start: " + (" · ".join(ln["text"] for ln in lines) or "nothing to flag"),
                         "lines": lines})

    # ---- which phone, and asking before your own -----------------------------------------------

    async def _choose_phone(self, tid: str, app: str | None, asked: str | None, named: str | None = None) -> Choice | None:
        """The phone for this task (api/routing.py); for your real phone, only after you say yes. None: the task ended."""
        await asyncio.to_thread(self.pool.refresh_phones)
        rules = self.store.setting("phone_apps", []) or []
        learned = self._learned()
        choice = choose(app, asked=asked, phone_apps=rules, phones=list(self.pool.phones.values()), learned=learned, named=named)
        if choice.device is None:
            self._set(tid, status="failed", detail=choice.error or "no phone can run this", waiting_for=None)
            self._step(tid, {"kind": "error", "text": choice.error or "no phone can run this"})
            return None
        if not choice.real_phone:
            running = getattr(self.pool, "running", None)
            if running is not None and not (await asyncio.to_thread(running)).get(choice.device, True):
                # Said plainly, not as the device layer's error ("envoy-test is not running (scripts/...)"), and with the
                # phone you have connected as the other way: it is used only when you ask for it.
                phone = next((p for p in self.pool.phones.values() if p.get("state") == "device"), None)
                why = f"The emulator for this app ({NAMES.get(choice.device, choice.device)}) isn't running right now. " + (
                    f"Ask again with \"on my phone\" to use {phone_ref(phone)}, or start the emulator and ask again."
                    if phone else f"Start it (scripts/start_emulator.sh {choice.device}) and ask again.")
                self._set(tid, status="failed", detail=why, waiting_for=None)
                self._step(tid, {"kind": "error", "text": why})
                return None
            if asked or choice.reason.startswith("set to run"):
                self._step(tid, {"kind": "note", "text": f"phone: {NAMES.get(choice.device, choice.device)} ({choice.reason})"})  # "Test phone", not its id
            return choice
        ref = phone_ref(self.pool.phones.get(choice.device))  # "your Pixel 5", or the name you gave it in Settings › Phones
        if self.phone_allowed.pop(tid, None) == choice.device:  # you said yes already (the task moved off the emulator, or an offer)
            self._step(tid, {"kind": "note", "text": f"phone: {ref} (you said yes)"})
            return choice
        self._step(tid, {"kind": "note", "text": f"phone: {ref} ({choice.reason})"})
        blocked = blocks_emulator(app, rules, learned)
        allow, by = await self._ask_for_phone(tid, choice.device, ref, why=f"{app_label(app, learned)} blocks emulators" if blocked else None)
        if not allow:
            if blocked is not None:
                self._set(tid, status="declined", detail=f"you kept your phone for yourself ({app_label(app, learned)} blocks emulators)",
                          waiting_for=None)
                return None
            if by == "no answer":
                # Silence is no choice of the emulator (Nov 2: Muse's Story ask went unanswered for 15 min, moved to envoy-real,
                # and opened the Play Store for Instagram). Only your "no" sends a task to the emulator (backlog #63).
                self._set(tid, status="declined", detail=f"not done: no answer about using {ref}", waiting_for=None)
                return None
            emulator = self.pool.avd_for(app)
            self._step(tid, {"kind": "note", "text": f"running on the emulator ({emulator}) instead"})
            return Choice(emulator, "you chose the emulator")
        return choice

    async def _ask_for_phone(self, tid: str, did: str, ref: str, why: str | None = None) -> tuple[bool, str]:
        """Wait for your answer to "Use your Android phone for this task?": (yes?, who answered, or "no answer"). No answer
        is never a yes. `why`: said with it ("Target blocks emulators")."""
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self.phone_asks[tid] = fut
        self._set(tid, status="needs_you", waiting_for="phone", detail=(f"{why}: " if why else "") + f"Envoy wants to use {ref} for this task")
        model = (self.pool.phones.get(did) or {}).get("model") or "Android phone"
        self.bus.publish("phone_requested", task_id=tid, device=did, model=model, ref=ref, reason=why)
        try:
            allow, by = await asyncio.wait_for(fut, timeout=self.approval_timeout_s)
        except asyncio.TimeoutError:
            allow, by = False, "no answer"
        finally:
            self.phone_asks.pop(tid, None)
        self._step(tid, {"kind": "note", "text": f"{ref}: " + (f"allowed by {by}" if allow else f"not used ({by})")})
        self._set(tid, status="running", waiting_for=None, detail=None)
        return allow, by

    def answer_phone(self, tid: str, allow: bool, by: str) -> bool:
        """Your answer, from the web app or the iPhone (session only). False if nothing is waiting."""
        fut = self.phone_asks.get(tid)
        if fut is None or fut.done():
            return False
        loop = self.loop or asyncio.get_event_loop()
        loop.call_soon_threadsafe(lambda: fut.done() or fut.set_result((allow, by)))
        return True

    async def _ensure_app(self, tid: str, device: Any, app: str | None) -> None:
        """The app must be on the phone. SkyLark, our own test app, is installed from its build; real apps come from
        the Play Store, which needs your Google account on the phone."""
        if not app:
            return
        listed = await asyncio.to_thread(device.adb.shell, f"pm list packages {app}")
        if f"package:{app}" in listed:
            return
        if app == SKYLARK:
            self._step(tid, {"kind": "note", "text": "installing SkyLark (our test app) on your phone"})
            await asyncio.to_thread(SkyLark(device.serial).install)
            return
        raise RuntimeError(f"{app} isn't installed on your phone (install it from the Play Store)")

    # ---- apps that block emulators, and apps the emulator doesn't have yet ------------------------

    def _learned(self) -> dict[str, Any]:
        """Apps Envoy found blocking emulators: package → {name, why, at, task, device} (Settings › Phones shows them)."""
        return self.store.setting("phone_apps_learned", {}) or {}

    def _learned_names(self) -> dict[str, str]:
        """Apps Envoy installed (or found) by the name a request gave: that name → package."""
        return {n: pkg for pkg, a in (self.store.setting("apps_installed", {}) or {}).items() for n in a.get("names", [])}

    def _name(self, app: str | None) -> str:
        """The app's name, for what the task says."""
        if app in BLOCKS_EMULATOR or app in self._learned():
            return app_label(app, self._learned())
        if (got := (self.store.setting("apps_installed", {}) or {}).get(app or "")) is not None:
            return got.get("name") or app or "the app"
        name = next((n for n, p in APP_NAMES.items() if p == app), None) or (app or "the app").rsplit(".", 1)[-1]
        return name[:1].upper() + name[1:]

    def _learn_blocked(self, tid: str, avd: str, app: str, name: str, why: str) -> None:
        """From now on `app` runs on your phone: it is set to your phone in Settings › Phones (where unticking it undoes
        this), and why is kept beside it. Apps on the starting list (api/emulator_blocked.json) are there already."""
        if app in BLOCKS_EMULATOR:
            return
        rules = list(self.store.setting("phone_apps", []) or [])
        if app not in rules:
            rules.append(app)
            self.store.set_setting("phone_apps", rules)
        learned = {**self._learned(), app: {"name": name, "why": why, "at": round(time.time()), "task": tid, "device": avd}}
        self.store.set_setting("phone_apps_learned", learned)
        self.bus.publish("settings", phone_apps=rules, phone_apps_learned=learned)
        self._step(tid, {"kind": "note", "text": f"{name} {why}, so it blocks emulators: from now on it runs on your Android phone "
                                                  "(Settings › Phones; untick it there to undo)"})

    async def _offer_phone(self, tid: str, name: str) -> str | None:
        """Ask to move this task to your phone, when one is connected. Its id if you said yes."""
        await asyncio.to_thread(self.pool.refresh_phones)
        phone = next((p for p in self.pool.phones.values() if p.get("state") == "device"), None)
        if phone is None or not (await self._ask_for_phone(tid, phone["id"], phone_ref(phone), why=f"{name} blocks emulators"))[0]:
            return None
        self.phone_allowed[tid] = phone["id"]
        self.moved.add(tid)
        return phone["id"]

    async def _bot_check(self, tid: str, avd: str, app: str | None, screen: Any, bot: str) -> tuple[str | None, str]:
        """A bot check on an emulator. Envoy never tries to get past one. When the app itself shows it, the app blocks
        emulators: it is set to your phone from now on, and this task moves there if your phone is connected and you say
        yes. Returns (the phone to move to, or None; what the hand-off here says)."""
        name = self._name(app)
        if not app or screen.package != app or app in BROWSERS:
            return None, f"{bot}: clear it yourself"  # a website's check, or no app to route: an ordinary hand-off
        self._learn_blocked(tid, avd, app, name, f"showed a {bot} on the emulator")
        moved = await self._offer_phone(tid, name)
        if moved:
            return moved, ""
        return None, f"{needs_real_phone(app, self._learned(), name=name)} You can also try clearing the {bot} on {avd} yourself"

    async def _install_missing(self, tid: str, avd: str, gated: Any, approver: Any, app: str | None, named: str | None,
                               goal: str) -> tuple[str | None, str | None, str | None, tuple[str, str] | None]:
        """On an emulator: the app, installed from the Play Store if it isn't there yet (api/install.py). Returns (the
        app's package, its name if it was installed just now, your phone's id if the task moves there, and (status,
        what to say) when the task ends here)."""
        if app == SKYLARK or not self.install_apps or getattr(gated, "adb", None) is None:  # a phone without adb can't be asked
            return app, None, None, None
        inst = Installer(gated, step=lambda d: self._step(tid, d), approver=approver, task_id=tid, goal=goal,
                         hand_off=lambda why: self._wait_for_user(tid, avd, why))
        got = await inst.ensure(app, named if not app else self._name(app))
        name = got.title or named or self._name(app)
        if got.ok and got.package:
            if not app or got.status != "already":
                self._remember_app(got.package, name, named)
            if got.package != app:
                self._set(tid, app=got.package)
            if got.status == "already" and not app:
                self._step(tid, {"kind": "note", "text": f"{named} is already on {avd} ({got.package})"})
            return got.package, (name if got.status != "already" else None), None, None
        if got.status == "incompatible":
            if app:
                self._learn_blocked(tid, avd, app, name, "can't be installed on an emulator (the Play Store says it isn't compatible)")
                if (moved := await self._offer_phone(tid, name)) is not None:
                    return app, None, moved, None
            return app, None, None, ("failed", needs_real_phone(app, self._learned(), name=name))
        if got.status == "declined":
            return app, None, None, ("declined", got.detail)
        if got.status == "no_account":
            return app, None, None, ("needs_you", f"Envoy can't install apps on {avd}: its Play Store has no Google account signed in. "
                                                  "Sign in there (take over in the live view), then ask again.")
        return app, None, None, ("failed", f"Couldn't install {name}: {got.detail or got.status}")

    def _remember_app(self, package: str, title: str, named: str | None) -> None:
        """The next request that names this app goes straight to it: what you called it, and its short Play Store name."""
        apps = dict(self.store.setting("apps_installed", {}) or {})
        entry = dict(apps.get(package) or {"name": title, "names": [], "at": round(time.time())})
        short = re.split(r"\s*[:–—]\s+|\s+-\s+", title or "")[0]
        for n in (named, short):
            if n and len(norm(n)) >= 3 and norm(n) not in entry["names"]:
                entry["names"].append(norm(n))
        apps[package] = entry
        self.store.set_setting("apps_installed", apps)

    def _phone_paused(self, tid: str, paused: bool, why: str) -> None:
        """Your real phone paused or resumed the task (a touch, Pause, Resume): the task says so while it is running."""
        task = self.store.get(tid) or {}
        if task.get("status") in ("running", "taken_over", "needs_you", "waiting_approval"):
            if paused != (task.get("status") == "taken_over"):  # a change, kept in the task's history (Pixel 5: it wasn't)
                self._step(tid, {"kind": "note", "text": (why if why.startswith("paused") else f"paused: {why}") if paused else "resumed on your phone"})
            self._set(tid, status="taken_over" if paused else "running", detail=why or None)

    async def _saved_login(self, tid: str, device: Any, approver: Any, app: str | None, goal: str, real_phone: bool) -> bool:
        """A sign-in screen, before it is handed to you: with saved logins on for this kind of phone (Settings › Phones),
        the phone's password manager fills it and, after your yes, Envoy presses the app's sign-in button
        (api/autofill.py). False: it is handed to you as before."""
        if not autofill.enabled(self.store, real_phone):
            return False

        async def ask(description: str, screen: Any) -> bool:
            # No button named (target ""), so the request's words never approve it: every sign-in asks you.
            req = ApprovalRequest(task_id=tid, goal=goal, app=app or "", description=description, screen=screen.compact,
                                  reasons=["Envoy signs in as you here, so it asks every time",
                                           "your phone's password manager filled the password: Envoy never saw it"],
                                  origin="signin", target="")
            return (await asyncio.to_thread(approver.request, req)).approved

        try:
            return await autofill.sign_in(device, app=app, name=self._name(app), ask=ask, step=lambda d: self._step(tid, d))
        except Exception as e:  # noqa: BLE001 - anything unexpected: hand it to you as before
            self._step(tid, {"kind": "note", "text": f"saved login: {type(e).__name__}: {e}"[:200]})
            return False

    async def _wait_for_user(self, tid: str, avd: str, reason: str) -> bool:
        self._set(tid, status="needs_you", waiting_for="takeover", detail=reason)
        self._step(tid, {"kind": "handoff", "text": f"{reason}: take over, then hand back"})
        self.pool.request_takeover(avd, reason)
        ok = await self.pool.wait_for_hand_back(avd, self.takeover_timeout_s)
        if ok:
            self._step(tid, {"kind": "note", "text": "handed back: the agent looks at the screen again"})
            self._set(tid, status="running", waiting_for=None)
        return ok

    async def _learn_notes(self, tid: str, traces: list[str], app: str | None, goal: str, status: str, result: str,
                           inputs: dict[str, str], outputs: dict[str, Any], scope: str) -> None:
        """After a run: what it shows about the app becomes, confirms or retires an app note (a run that didn't finish can only retire one)."""
        for trace in traces:
            try:
                rep = await self.app_notes.learn(trace, app=app, goal=goal, status=status, result=result, inputs=inputs, outputs=outputs,
                                                 task_id=tid, data_scope=scope, contributor=scope == "test_app")  # type: ignore[arg-type]
            except Exception as e:  # noqa: BLE001 - notes never fail a task
                self._step(tid, {"kind": "error", "text": f"app notes: {type(e).__name__}: {e}"[:300]})
                continue
            if rep.applied:
                self._step(tid, {"kind": "app_notes", "text": "app notes: " + ", ".join(f"{a['op']} {a.get('text') or a['note']}"[:90] for a in rep.applied),
                                 "applied": rep.applied, "dropped": rep.dropped})

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
        ents = sorted({f"{x.type} {(self.memory.entity(x.entity) or {}).get('name') or x.entity}" for r in reps for x in r.resolved})
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
        wants_shot = data["kind"] in ("action", "routine_step") and not data.get("secure")
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # called from a worker thread: the frame can be taken right here
            loop = None
        if loop is None:
            shot = self._thumbnail(tid) if wants_shot else None
            if shot:
                data["shot"] = shot
            self._step(tid, data)
            return
        # On the loop, the frame is taken in a thread, so a task on another phone never waits on this one's screenshots.
        # Steps keep their order: each is written after the one before it.
        grab = loop.run_in_executor(None, self._thumbnail, tid) if wants_shot else None
        before = self.pending_steps.get(tid)
        if grab is None and before is None:
            self._step(tid, data)
            return
        self.pending_steps[tid] = loop.create_task(self._step_after(tid, data, grab, before))

    async def _step_after(self, tid: str, data: dict[str, Any], grab: Any, before: asyncio.Task | None) -> None:
        try:
            shot = await grab if grab is not None else None
        except Exception:  # noqa: BLE001 - a step is written without its picture
            shot = None
        if before is not None:
            await asyncio.wait([before])
        if shot:
            data["shot"] = shot
        self._step(tid, data)
        if self.pending_steps.get(tid) is asyncio.current_task():
            self.pending_steps.pop(tid, None)

    async def _steps_written(self, tid: str) -> None:
        """Wait for steps still taking their picture, so a task's steps are all there when it finishes."""
        pending = self.pending_steps.get(tid)
        if pending is not None:
            await asyncio.wait([pending], timeout=5)

    def _thumbnail(self, tid: str) -> str | None:
        """A small picture of the screen after a step, never of a secure screen."""
        device = self.devices.get(tid)
        if device is None or getattr(getattr(device, "_last", None), "secure", False):
            return None
        try:
            img = device.frame(360, timeout=2)
            folder = SHOTS / tid
            folder.mkdir(parents=True, exist_ok=True)
            name = f"{int(time.time() * 1000)}.jpg"
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=60)
            (folder / name).write_bytes(buf.getvalue())
            return f"{tid}/{name}"
        except Exception:  # noqa: BLE001
            return None
