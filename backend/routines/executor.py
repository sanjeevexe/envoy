"""Routine executor (design doc, App routines › Running a routine).

For each step: wait for its before-checks (up to 5 s), find the element, act through the same policy
gate as the agent (irreversible steps always ask for approval, even in routines), then wait for its
after-checks. Settling is done on the after-checks themselves rather than a generic quiet window,
and no model is called while checks pass.

When a check fails, the fallback ladder climbs one rung at a time:
  1. wait and retry (slow loading)
  2. relaxed matching (the lower locator threshold); then, if the target may be off screen (a shorter phone than the
     one the routine was learned on), scrolling the screen's list to reveal it, with no model call
  3. the shared pop-up handler (agent/popups.py)
  4. local repair: one model call at a time with the step's intent, checks and the current screen,
     proposing an action toward the after-checks; at most 2 per step and 5 per run
  5. the full agent takes over the rest of the task from the current screen
  6. the user is asked
Every rung that saved a step is recorded, and rungs 2 and 4 leave candidate patches (a new locator,
inserted steps, a removed step) for routines/store.py to try as a new version.
"""

from __future__ import annotations

import asyncio
import io
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from PIL import Image

from agent.loop import AgentRunner, RunConfig
from agent.popups import match_popup
from agent.trace import TraceWriter, screen_record
from agent.vision import Vision
from devices.types import Action, Device, Element, InvalidElement, ScreenState
from models.adapter import DataScope, ModelAdapter
from models.prompts import REPAIR_INSTRUCTIONS, repair_input
from models.schemas import StepOutput
from models.translate import to_device_action
from policy.approvals import ApprovalRequest, Approver, TerminalApprover
from policy.risk import classify
from policy.signin import sign_in_reason
from routines import checks as chk
from routines import locators
from routines.compiler import bind_inputs, chk_generalize, generalize_locator
from routines.model import Check, Extract, Locator, Routine, Step, StepAction, has_slot, render, render_str
from routines.screens import body, contains_value, norm, parts_of, short_id, usable_id
from routines.visual import match_crop

RUNG_NAMES = {0: "none", 1: "wait and retry", 2: "relaxed match", 3: "pop-up handler", 4: "local repair", 5: "full agent", 6: "ask the user"}
Status = Literal["done", "failed", "declined", "handoff", "needs_user", "agent_done", "agent_failed"]
SCREENSHOT_WIDTH = 540


@dataclass
class ExecConfig:
    pre_timeout_s: float = 5.0  # design: wait up to 5 s for before-checks
    post_timeout_s: float = 5.0
    poll_s: float = 0.04
    stable_s: float = 1.0  # a screen unchanged this long won't fix itself: try the next rung early
    max_repairs_step: int = 2
    max_repairs_run: int = 5
    max_popups_step: int = 3
    data_scope: DataScope = "real"
    contributor: bool = False
    repair_effort: str = "medium"
    patch_screenshots: bool = True
    agent: RunConfig | None = None


@dataclass
class RepairAction:
    reason: str
    action: dict[str, Any]
    element: Element | None
    before: ScreenState
    after: ScreenState | None
    risk: str
    screenshot_before: str | None = None
    screenshot_after: str | None = None


@dataclass
class Patch:
    """A candidate change to a routine, from a step that needed rung 2 or 4."""

    kind: Literal["locator", "check", "post", "insert_before", "insert_after", "replace", "remove"]
    step_id: str
    description: str
    locator: Locator | None = None  # kind=locator: the step's new target
    check_index: int | None = None  # kind=check: which post-check (index into step.post)
    check: Check | None = None
    steps: list[Step] = field(default_factory=list)  # inserted or replacing steps
    checks: list[Check] = field(default_factory=list)  # kind=post: the step's new after-checks
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class StepRun:
    id: str
    status: str = "pending"  # done, skipped, failed, declined, handoff, agent
    rung: int = 0
    rungs: list[str] = field(default_factory=list)
    score: float | None = None
    wait_ms: float = 0.0
    act_ms: float = 0.0
    post_ms: float = 0.0
    detail: str = ""
    repairs: list[dict[str, Any]] = field(default_factory=list)

    def climb(self, rung: int, note: str) -> None:
        self.rung = max(self.rung, rung)
        self.rungs.append(f"{RUNG_NAMES[rung]}: {note}")


@dataclass
class RunOutcome:
    routine: str
    version: int
    task_id: str
    status: Status
    detail: str = ""
    outputs: dict[str, str | None] = field(default_factory=dict)
    steps: list[StepRun] = field(default_factory=list)
    patches: list[Patch] = field(default_factory=list)
    model_calls: int = 0
    cost_usd: float = 0.0
    cost_at_standard_usd: float = 0.0
    duration_s: float = 0.0
    approvals: list[dict[str, Any]] = field(default_factory=list)
    popups: list[str] = field(default_factory=list)
    agent: dict[str, Any] | None = None
    trace_dir: str = ""

    @property
    def rung(self) -> int:
        return max((s.rung for s in self.steps), default=0)

    @property
    def succeeded(self) -> bool:
        return self.status in ("done", "agent_done")


@dataclass
class _Ready:
    kind: Literal["ok", "skip", "not_ready", "handoff"]
    screen: ScreenState
    element: Element | None = None
    relaxed: bool = False
    why: str = ""
    removed: bool = False  # skipped because the screen it expected never came (a candidate "remove" patch)


@dataclass
class _Ctx:
    routine: Routine
    inputs: dict[str, str]
    task_id: str
    out: RunOutcome
    trace: TraceWriter
    allow_repair: bool
    allow_agent: bool
    memory: str
    request: str = ""  # the user's own words, when the caller has them: what a fallback agent should finish
    repairs_run: int = 0
    started: float = 0.0
    jump_to: int | None = None  # set when the app skipped ahead to a later step's screen


class RoutineExecutor:
    def __init__(self, device: Device, adapter: ModelAdapter | None = None, approver: Approver | None = None,
                 config: ExecConfig | None = None) -> None:
        self.device = device
        self.adapter = adapter or ModelAdapter()
        self.approver = approver or TerminalApprover()
        self.config = config or ExecConfig()

    # ---- observing --------------------------------------------------------------------------

    async def _observe(self) -> ScreenState:
        return await self.device.observe()

    async def _screenshot(self, ctx: _Ctx, name: str) -> str | None:
        if not self.config.patch_screenshots:
            return None
        try:
            png = await self.device.screenshot()
            img = Image.open(io.BytesIO(png))
            if img.width > SCREENSHOT_WIDTH:
                img = img.resize((SCREENSHOT_WIDTH, round(img.height * SCREENSHOT_WIDTH / img.width)))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="PNG", optimize=True)
            path = ctx.trace.dir / "screens" / f"{name}.png"
            path.write_bytes(buf.getvalue())
            return str(path)
        except Exception:  # noqa: BLE001 - screenshots are evidence only
            return None

    async def _field_values(self, checks: list[Check], screen: ScreenState, inputs: dict[str, str]) -> dict[int, str]:
        """get_text for fields whose expected value the XML dump can't show (emoji, Phase 0)."""
        if not chk.needs_field_read(checks, inputs) or not hasattr(self.device, "read_field"):
            return {}
        out: dict[int, str] = {}
        for c in checks:
            if c.kind == "field_equals" and c.locator is not None:
                m = locators.locate(render(c.locator, inputs), screen, threshold=locators.RELAXED, margin=0.0)
                if m.element is not None:
                    v = await self.device.read_field(m.element)  # type: ignore[attr-defined]
                    if v is not None:
                        out[m.element.index] = v
        return out

    def _check(self, checks: list[Check], screen: ScreenState, inputs: dict[str, str], *, before: ScreenState | None = None,
               relaxed: bool = False, field_text: dict[int, str] | None = None) -> tuple[bool, list[chk.CheckOutcome]]:
        outs = chk.evaluate_all(checks, screen, inputs, before=before, relaxed=relaxed, field_text=field_text)
        return all(o.passed for o in outs), outs

    @staticmethod
    def _specific(checks: list[Check]) -> list[Check]:
        """Checks that say something about this step's effect (not just 'the screen changed')."""
        return [c for c in checks if c.kind not in ("screen_changed", "screen_like", "app_foreground")]

    def _target(self, step: Step, screen: ScreenState, inputs: dict[str, str], relaxed: bool = False) -> locators.Match | None:
        if step.action.kind not in ("tap", "long_press", "type") or step.action.target is None or step.action.target.visual:
            return None  # a drawn target (no node in the tree) is found by looking, when the step acts
        th = locators.RELAXED if relaxed else locators.STRICT
        return locators.locate(step.action.target, screen, inputs, threshold=th)

    @staticmethod
    def _next_required(ctx: "_Ctx", idx: int) -> Step | None:
        """The first step after `idx` that isn't optional (one-time screens often come in a row: skip, then continue)."""
        return next((s for s in ctx.routine.steps[idx + 1:] if not s.optional), None)

    def _ready_now(self, step: Step, screen: ScreenState, inputs: dict[str, str]) -> bool:
        """Strictly ready: before-checks pass and the target is found."""
        ok, _ = self._check(step.pre, screen, inputs)
        if not ok:
            return False
        m = self._target(step, screen, inputs)
        return m is None or m.ok

    # ---- the run ----------------------------------------------------------------------------

    async def run(self, routine: Routine, inputs: dict[str, str], *, task_id: str | None = None, launch: Literal["fresh", "if_needed", "never"] = "if_needed",
                  allow_repair: bool = True, allow_agent: bool = True, memory: str = "", request: str = "") -> RunOutcome:
        task_id = task_id or f"routine-{routine.routine}-{uuid.uuid4().hex[:6]}"
        trace = TraceWriter(task_id)
        out = RunOutcome(routine=routine.routine, version=routine.version, task_id=task_id, status="failed", trace_dir=str(trace.dir))
        ctx = _Ctx(routine, {k: str(v) for k, v in inputs.items()}, task_id, out, trace, allow_repair, allow_agent, memory, request,
                   started=time.time())
        try:
            missing = routine.missing_inputs(ctx.inputs)
            if missing:
                return self._finish(ctx, "needs_user", f"missing inputs: {', '.join(missing)}")
            if launch == "fresh" and hasattr(self.device, "launch"):
                await self.device.launch(routine.app, fresh=True)  # type: ignore[call-arg]
            elif launch == "if_needed":
                s = await self._observe()
                if s.package != routine.app:
                    await self.device.launch(routine.app)

            i = 0
            while i < len(routine.steps):
                step = routine.steps[i]
                sr = StepRun(step.id)
                out.steps.append(sr)
                t0 = time.perf_counter()
                verdict = await self._run_step(ctx, i, sr)
                trace.step({"kind": "routine_step", "step": i + 1, "id": step.id, "status": sr.status, "rung": sr.rung, "rungs": sr.rungs,
                            "score": sr.score, "timings_ms": {"wait": round(sr.wait_ms), "act": round(sr.act_ms), "post": round(sr.post_ms),
                                                              "total": round((time.perf_counter() - t0) * 1000)},
                            "detail": sr.detail, "repairs": sr.repairs})
                if verdict == "next":
                    i = ctx.jump_to if ctx.jump_to is not None else i + 1
                    ctx.jump_to = None
                    continue
                if verdict == "finished":  # the full agent took over (rung 5) and ended the task
                    return self._finish(ctx, out.status, out.detail)
                return self._finish(ctx, out.status, sr.detail)

            # End of routine: done-checks and outputs.
            screen = await self._observe()
            ok, outs = self._check(routine.done, screen, ctx.inputs)
            if not ok:
                deadline = time.perf_counter() + self.config.post_timeout_s
                while not ok and time.perf_counter() < deadline:
                    await asyncio.sleep(self.config.poll_s)
                    screen = await self._observe()
                    ok, outs = self._check(routine.done, screen, ctx.inputs)
            if not ok and (seen := await self._reveal_checks(ctx, routine.done, None)) is not None:
                ok, screen = True, seen  # the proof is on the page, past the edge of the screen (a smaller screen, a banner above)
            if not ok:
                return self._finish(ctx, "failed", "done-check failed: " + "; ".join(o.detail for o in outs if not o.passed))
            missing_out = [n for n in routine.outputs if not out.outputs.get(n)]
            if missing_out:  # content can load after the last check passes (search results): keep reading for a while
                specs = {n: e for st in routine.steps for n, e in (st.extract or {}).items()}
                deadline = time.perf_counter() + self.config.post_timeout_s
                while missing_out and time.perf_counter() < deadline:
                    await asyncio.sleep(0.2)
                    screen = await self._observe()
                    for n in missing_out:
                        if n in specs:
                            out.outputs[n] = extract_value(specs[n], screen, ctx.inputs)
                    missing_out = [n for n in routine.outputs if not out.outputs.get(n)]
            if missing_out:  # on a shorter screen an output can be scrolled away (Phase 6): look up the list, then down
                missing_out = await self._read_scrolled(ctx, specs, missing_out)
            if missing_out:
                return self._finish(ctx, "failed", f"outputs not found: {', '.join(missing_out)}")
            return self._finish(ctx, "done", "all steps and checks passed")
        except Exception as e:  # noqa: BLE001 - a failed run keeps its trace
            return self._finish(ctx, "failed", f"{type(e).__name__}: {e}")

    def _finish(self, ctx: _Ctx, status: Status, detail: str) -> RunOutcome:
        out = ctx.out
        out.status, out.detail = status, detail
        out.duration_s = round(time.time() - ctx.started, 2)
        ctx.trace.finish({"routine": out.routine, "version": out.version, "task_id": out.task_id, "status": status, "detail": detail,
                          "outputs": out.outputs, "rung": out.rung, "model_calls": out.model_calls, "cost_usd": out.cost_usd,
                          "duration_s": out.duration_s, "patches": [p.description for p in out.patches], "approvals": out.approvals})
        return out

    # ---- one step ---------------------------------------------------------------------------

    async def _run_step(self, ctx: _Ctx, idx: int, sr: StepRun) -> Literal["next", "stop", "finished"]:
        step = ctx.routine.steps[idx]
        t0 = time.perf_counter()
        ready = await self._ready(ctx, idx, sr)
        sr.wait_ms = (time.perf_counter() - t0) * 1000
        if ready.kind == "handoff":
            sr.status, sr.detail = "handoff", ready.why
            ctx.out.status = "handoff"
            return "stop"
        if ready.kind == "skip":
            sr.status, sr.detail = "skipped", ready.why
            if ready.removed:
                ctx.out.patches.append(Patch("remove", step.id, f"step {step.id!r} skipped: its screen never appeared and {ready.why}"))
            await self._extract(ctx, step, ready.screen)
            return "next"
        if ready.kind == "not_ready":
            rep = await self._repair(ctx, idx, sr, phase="before", screen=ready.screen, why=ready.why)
            if rep == "post_ok":
                sr.status = "done"
                await self._extract(ctx, step, await self._observe())
                return "next"
            if isinstance(rep, _Ready):
                ready = rep
            else:
                return await self._escalate(ctx, idx, sr, ready.why if rep == "gave_up" else rep)

        # Act through the policy gate.
        before = ready.screen
        if ready.relaxed and ready.element is not None and step.action.target is not None:
            new_loc = locators.updated(step.action.target, ready.element, before)
            ctx.out.patches.append(Patch("locator", step.id, f"step {step.id!r}: target found only by relaxed match; locator updated to "
                                         f"{new_loc.describe()}", locator=new_loc, evidence={"score": sr.score}))
        t_act = time.perf_counter()
        verdict = await self._act(ctx, step, before, ready.element, sr)
        sr.act_ms = (time.perf_counter() - t_act) * 1000
        if verdict != "ok":
            return "stop"

        # After-checks.
        t_post = time.perf_counter()
        post = await self._wait_post(ctx, idx, sr, before)
        sr.post_ms = (time.perf_counter() - t_post) * 1000
        if post.kind in ("ok", "skip"):
            sr.status = "done"
            await self._extract(ctx, step, post.screen)
            return "next"
        if post.kind == "handoff":
            sr.status, sr.detail = "handoff", post.why
            ctx.out.status = "handoff"
            return "stop"
        rep = await self._repair(ctx, idx, sr, phase="after", screen=post.screen, why=post.why, before=before)
        if rep == "post_ok":
            sr.status = "done"
            await self._extract(ctx, step, await self._observe())
            return "next"
        return await self._escalate(ctx, idx, sr, post.why if rep in ("gave_up",) else str(rep))

    async def _ready(self, ctx: _Ctx, idx: int, sr: StepRun) -> _Ready:
        """Rungs 1–3 before acting: wait for the before-checks and the target, then relaxed matching, then pop-ups."""
        step = ctx.routine.steps[idx]
        nxt = ctx.routine.steps[idx + 1] if idx + 1 < len(ctx.routine.steps) else None
        cfg = self.config
        start = time.perf_counter()
        deadline = start + cfg.pre_timeout_s
        last_body, stable_since = None, start
        last_bounds = None
        popups = 0
        tried_relaxed = False
        tried_reveal = False
        failed_once = False  # rung 1 counts only when a check actually failed first (not the two-read stillness check)
        while True:
            s = await self._observe()
            now = time.perf_counter()
            b = body(s)
            if b != last_body:
                last_body, stable_since = b, now
            if (why := sign_in_reason(s)) is not None:
                return _Ready("handoff", s, why=f"sign-in needed: {why}")
            pre_ok, pre_outs = self._check(step.pre, s, ctx.inputs)
            m = self._target(step, s, ctx.inputs)
            if pre_ok and (m is None or m.ok):
                bounds = m.element.bounds if m is not None and m.element is not None else None
                if bounds is None or bounds == last_bounds or now >= deadline:  # the target sits still: safe to tap
                    if m is not None:
                        sr.score = round(m.score, 3)
                    if failed_once and now - start > 0.3:
                        sr.climb(1, f"ready after {now - start:.1f} s")
                    return _Ready("ok", s, m.element if m else None)
                last_bounds = bounds
                await asyncio.sleep(cfg.poll_s)
                continue
            last_bounds = None
            failed_once = True
            # Already done (the effect is there) or an optional step whose screen didn't come.
            specific = self._specific(step.post)
            if specific and self._check(specific, s, ctx.inputs)[0]:
                return _Ready("skip", s, why="its after-checks already hold")
            req = self._next_required(ctx, idx) if step.optional else None
            if step.optional and req is not None and self._ready_now(req, s, ctx.inputs):
                return _Ready("skip", s, why=f"optional, and the next required step ({req.id}) is ready")
            stable = now - stable_since >= cfg.stable_s
            if step.optional and req is None and stable:  # nothing required after it to tell us its screen was skipped
                return _Ready("skip", s, why="optional, its screen didn't come, and only optional steps are left")
            # Rung 3: a known pop-up in the way.
            if popups < cfg.max_popups_step and now - stable_since >= 0.25 and (pop := match_popup(s, ctx.routine.intent)) is not None:
                await self.device.act(Action(kind="tap", element=pop.element.number))
                popups += 1
                ctx.out.popups.append(pop.handler)
                sr.climb(3, pop.handler)
                deadline = time.perf_counter() + cfg.pre_timeout_s
                await asyncio.sleep(cfg.poll_s)
                continue
            # Rung 2: relaxed matching, once the screen has stopped changing (or time is up).
            if (stable or now >= deadline) and not tried_relaxed:
                rel_ok, _ = self._check(step.pre, s, ctx.inputs, relaxed=True)
                rm = self._target(step, s, ctx.inputs, relaxed=True)
                if rel_ok and (rm is None or rm.ok):
                    sr.climb(2, f"relaxed match {rm.summary() if rm else '(checks)'}")
                    if rm is not None:
                        sr.score = round(rm.score, 3)
                    return _Ready("ok", s, rm.element if rm else None, relaxed=rm is not None and not (m and m.ok))
                tried_relaxed = stable
            # Still rung 2: on a shorter screen the target can be below the fold (Phase 6, envoy-small).
            if tried_relaxed and not tried_reveal and step.action.target is not None and step.action.kind != "scroll_until":
                tried_reveal = True
                found = await self._reveal(ctx, step)
                if found is not None:
                    s2, m2 = found
                    sr.climb(2, f"scrolled to reveal the target {m2.summary()}")
                    sr.score = round(m2.score, 3)
                    return _Ready("ok", s2, m2.element, relaxed=m2.score < locators.STRICT)
                deadline = max(deadline, time.perf_counter() + 0.5)
                continue
            if now >= deadline:
                failed = [o.detail for o in pre_outs if not o.passed]
                why = ("before-checks failed: " + "; ".join(failed)) if failed else f"target not found: {m.summary() if m else '?'}"
                sr.climb(1, f"waited {cfg.pre_timeout_s:.0f} s")
                return _Ready("not_ready", s, why=why)
            await asyncio.sleep(cfg.poll_s)

    async def _wait_post(self, ctx: _Ctx, idx: int, sr: StepRun, before: ScreenState) -> _Ready:
        """Rungs 1–3 after acting: settle on the after-checks themselves."""
        step = ctx.routine.steps[idx]
        nxt = ctx.routine.steps[idx + 1] if idx + 1 < len(ctx.routine.steps) else None
        cfg = self.config
        start = time.perf_counter()
        deadline = start + cfg.post_timeout_s
        last_body, stable_since = None, start
        popups = 0
        passes = 0
        tried_relaxed = tried_scroll = False
        while True:
            s = await self._observe()
            now = time.perf_counter()
            b = body(s)
            if b != last_body:
                last_body, stable_since = b, now
            fields = await self._field_values(step.post, s, ctx.inputs)
            ok, outs = self._check(step.post, s, ctx.inputs, before=before, field_text=fields)
            if ok:
                passes += 1
                if passes >= 2 or now - start > 0.5:  # two reads in a row, so a passing transition frame doesn't count
                    if now - start > 1.5:
                        sr.climb(1, f"after-checks held after {now - start:.1f} s")
                    return _Ready("ok", s)
                await asyncio.sleep(cfg.poll_s)
                continue
            passes = 0
            if (why := sign_in_reason(s)) is not None:
                return _Ready("handoff", s, why=f"sign-in needed: {why}")
            # An inserted optional step (from an earlier patch) handles the screen that came instead.
            if nxt is not None and nxt.optional and now - stable_since >= 0.15 and self._ready_now(nxt, s, ctx.inputs):
                return _Ready("skip", s, why=f"the optional step {nxt.id} takes over")
            changed = body(s) != body(before) or s.signature != before.signature
            stable = now - stable_since >= cfg.stable_s
            if popups < cfg.max_popups_step and now - stable_since >= 0.25 and (pop := match_popup(s, ctx.routine.intent)) is not None:
                await self.device.act(Action(kind="tap", element=pop.element.number))
                popups += 1
                ctx.out.popups.append(pop.handler)
                sr.climb(3, pop.handler)
                deadline = time.perf_counter() + cfg.post_timeout_s
                await asyncio.sleep(cfg.poll_s)
                continue
            if (stable or now >= deadline) and not tried_relaxed:
                rel_ok, rel_outs = self._check(step.post, s, ctx.inputs, before=before, relaxed=True, field_text=fields)
                if rel_ok:
                    sr.climb(2, "after-checks held at the relaxed threshold")
                    for j, o in enumerate(rel_outs):
                        if o.relaxed and o.element is not None and o.check.locator is not None:
                            old_loc = o.check.locator
                            if old_loc.text_has or any("{{" in (x or "") for x in (old_loc.resource_id, old_loc.text)):
                                continue  # bound to an input (the row for {{code}}): this run's row is this booking's data
                            new = o.check.model_copy(update={"locator": chk.anchor_locator(o.element, s)})
                            if any(v and contains_value(new.locator.describe(), v) for v in ctx.inputs.values()):
                                continue  # a check that names this run's input value would fail on every other one
                            ctx.out.patches.append(Patch("check", step.id, f"step {step.id!r}: after-check {j} matched only relaxed; "
                                                         f"updated to {new.locator.describe() if new.locator else ''}", check_index=j, check=new))
                    return _Ready("ok", s)
                tried_relaxed = stable
            # What the step should show may be past the edge of the screen ("Known traveler number saved" under the Save
            # button, once a banner pushed the page down): scroll to look before calling it a failure. No model call.
            if stable and tried_relaxed and not tried_scroll and any(e.kind == "List" for e in s.numbered) and \
                    all(o.passed or o.check.kind in ("element_present", "text_visible", "screen_changed") for o in outs):  # a change below the fold
                tried_scroll = True
                if (seen := await self._reveal_checks(ctx, step.post, before)) is not None:
                    sr.climb(2, "after-checks held past the edge of the screen (scrolled to see them)")
                    return _Ready("ok", seen)
            # Only "where the app went" checks failed, the screen changed, and the next step is ready: the checks were
            # over-specific (something optional that didn't show this time). Accept, and patch them to what happened.
            nav_only = all(o.passed or o.check.kind in ("element_present", "element_absent", "text_visible", "screen_like") for o in outs)
            if changed and stable and nav_only and nxt is not None and not nxt.optional and self._ready_now(nxt, s, ctx.inputs):
                fresh = chk.derive_post(before, s, step.action.kind, None, None, {k: v for k, v in ctx.inputs.items() if v})
                fresh = [g for c in fresh if (g := chk_generalize(c, ctx.inputs, [])) is not None] or [Check(kind="screen_changed")]
                failed = "; ".join(o.detail for o in outs if not o.passed)
                ctx.out.patches.append(Patch("post", step.id, f"step {step.id!r}: after-checks failed ({failed[:80]}) but the next step "
                                             f"was ready; after-checks rewritten from what happened", checks=fresh))
                sr.climb(2, f"after-checks failed but the next step ({nxt.id}) is ready")
                return _Ready("ok", s)
            # A screen that changed and then sat still for a while won't fix itself.
            if (changed and stable and now - start >= cfg.stable_s + 0.5) or now >= deadline:
                # The app may have dropped the next screen: a later step is ready and the next one is not.
                later = self._skipped_ahead(ctx, idx, s)
                if later is not None:
                    removed = ctx.routine.steps[idx + 1:later]
                    for st in removed:
                        ctx.out.patches.append(Patch("remove", st.id, f"step {st.id!r} removed: its screen no longer appears after "
                                                     f"{step.id!r}; the app went straight to {ctx.routine.steps[later].id!r}"))
                    ctx.out.steps.extend(StepRun(st.id, status="skipped", detail="its screen no longer appears") for st in removed)
                    ctx.jump_to = later
                    sr.climb(2, f"the app skipped ahead to {ctx.routine.steps[later].id}")
                    return _Ready("skip", s, why=f"the app went straight to {ctx.routine.steps[later].id}")
                failed = "; ".join(o.detail for o in outs if not o.passed)
                sr.climb(1, f"waited {now - start:.1f} s")
                return _Ready("not_ready", s, why=f"after-checks failed: {failed}")
            await asyncio.sleep(cfg.poll_s)

    def _skipped_ahead(self, ctx: _Ctx, idx: int, s: ScreenState) -> int | None:
        """The index of a later step (at most two ahead) that is ready now while the steps in between are not,
        if none of those in-between steps is irreversible."""
        steps = ctx.routine.steps
        if idx + 2 >= len(steps) or self._ready_now(steps[idx + 1], s, ctx.inputs):
            return None
        for j in range(idx + 2, min(idx + 4, len(steps))):
            between = steps[idx + 1:j]
            if any(b.risk == "irreversible" for b in between):
                return None
            if self._ready_now(steps[j], s, ctx.inputs) and not any(self._ready_now(b, s, ctx.inputs) for b in between):
                return j
        return None

    # ---- acting -----------------------------------------------------------------------------

    async def _gate(self, ctx: _Ctx, action: Action, screen: ScreenState, risk: str, label: str, sr: StepRun,
                    origin: str = "routine_step") -> Action | None:
        """The same policy gate the agent uses. Irreversible always asks a person (or the test app's scripted approver).
        Returns the action to run, or None if it was declined. An approval is bound to the screen it was shown for: if
        the screen changed while waiting, the same control is found on the new screen and the person is asked again."""
        verdict = classify(action, screen, risk if risk in ("read", "reversible", "irreversible") else None)  # type: ignore[arg-type]
        if not verdict.irreversible:
            return action
        for _ in range(3):
            req = ApprovalRequest(task_id=ctx.task_id, goal=render_str(ctx.routine.intent, ctx.inputs) or "", app=screen.package,
                                  description=f'{action.kind} "{label}" in {screen.package} (routine {ctx.routine.routine} v{ctx.routine.version})',
                                  reasons=verdict.reasons, screen=screen.compact, origin=origin, target=label)
            decision = await asyncio.to_thread(self.approver.request, req)
            ctx.out.approvals.append({"step": sr.id, "description": req.description, "reasons": req.reasons, "approved": decision.approved, "by": decision.by})
            if decision.by != "screen_changed":
                return action if decision.approved else None
            screen = await self.device.observe()
            same = [e for e in screen.numbered if e.label == label]
            if action.element is not None:
                if len(same) != 1:
                    return None  # the control is gone or ambiguous: nothing irreversible runs
                action = action.model_copy(update={"element": same[0].number})
            verdict = classify(action, screen, risk if risk in ("read", "reversible", "irreversible") else None)  # type: ignore[arg-type]
            if not verdict.irreversible:
                return action
        return None

    async def _clear_keyboard(self, el: Element, screen: ScreenState) -> ScreenState | None:
        """The on-screen keyboard is up and covers the element's centre (the tree still lists it): drag the page up just
        enough to bring it above the keyboard. Back is never used for this: in some apps it also leaves the screen. Returns
        the new screen, or None if nothing needed doing."""
        top_of = getattr(self.device, "keyboard_top", None)
        top = await asyncio.to_thread(top_of) if top_of is not None else None
        if top is None or el.center[1] < top:
            return None
        w = screen.width or 1080
        dy = min(int(el.center[1] - top + 0.08 * (screen.height or 2400)), int(0.6 * top))
        y1 = int(top * 0.85)
        await self.device.act(Action(kind="swipe", x=w // 2, y=y1, x2=w // 2, y2=max(1, y1 - dy)))
        return await self._settle_quick()

    async def _act(self, ctx: _Ctx, step: Step, screen: ScreenState, el: Element | None, sr: StepRun) -> Literal["ok", "stop"]:
        """Run the step's action through the policy gate. A scroll_until that doesn't find its target returns "ok":
        its after-check (the target is visible) then fails and the fallback ladder continues from there."""
        a = step.action
        if a.kind == "scroll_until":
            found = await self._scroll_until(ctx, step, sr)
            if not found:  # the after-checks (the target is visible) fail; the ladder's next rungs take over
                sr.climb(1, f"scrolled {a.max_scrolls or 8} times without finding {a.target.describe() if a.target else '?'}")
            return "ok"
        if a.kind == "swipe":
            w, h = screen.width or 1080, screen.height or 2400
            if a.target is not None:
                m = locators.locate(a.target, screen, ctx.inputs, threshold=locators.RELAXED, margin=0.0)
                cx, cy = m.element.center if m.element is not None else (int((a.start or (0.5, 0.5))[0] * w), int((a.start or (0.5, 0.5))[1] * h))
            else:
                cx, cy = int((a.start or (0.5, 0.5))[0] * w), int((a.start or (0.5, 0.5))[1] * h)
            dx, dy = a.vector or (0.0, -0.3)
            action = Action(kind="swipe", x=cx, y=cy, x2=max(1, min(w - 1, int(cx + dx * w))), y2=max(1, min(h - 1, int(cy + dy * h))))
        elif a.kind == "back":
            action = Action(kind="back")
        elif a.kind == "launch":
            action = Action(kind="launch", package=a.package or ctx.routine.app)
        elif a.kind == "wait":
            action = Action(kind="wait", seconds=a.seconds or 1.0)
        elif a.target is not None and a.target.visual:
            point = await self._visual_point(ctx, step, screen, sr)
            if point is None:
                sr.status, sr.detail = "failed", f"couldn't see {render_str(a.target.visual, ctx.inputs)!r} on the screen"
                ctx.out.status = "failed"
                return "stop"
            action = Action(kind="tap_point", x=point[0], y=point[1])
        else:
            assert el is not None
            if a.kind in ("tap", "long_press") and (moved := await self._clear_keyboard(el, screen)) is not None:
                # Typing left the keyboard up over the target: a tap would land on a key. The page was scrolled to bring it out.
                screen = moved
                m = self._target(step, screen, ctx.inputs)
                if m is not None and m.element is not None:
                    el = m.element
                sr.rungs.append("scrolled the target out from under the on-screen keyboard")
            if a.kind == "type":
                action = Action(kind="type", element=el.number, text=render_str(a.value, ctx.inputs) or "", submit=a.submit)
            else:
                action = Action(kind=a.kind, element=el.number)
        gated = await self._gate(ctx, action, screen, step.risk, el.label if el is not None else a.kind, sr)
        if gated is None:
            sr.status, sr.detail = "declined", ("the screen changed while waiting for approval" if ctx.out.approvals and ctx.out.approvals[-1]["by"]
                                                 == "screen_changed" else "the user declined the approval")
            ctx.out.status = "declined"
            return "stop"
        action = gated
        res = await self.device.act(action)
        if not res.ok:
            sr.status, sr.detail = "failed", f"action failed: {res.error}"
            ctx.out.status = "failed"
            return "stop"
        return "ok"

    async def _scroll_until(self, ctx: _Ctx, step: Step, sr: StepRun) -> bool:
        a = step.action
        assert a.target is not None
        direction = a.direction or "down"
        flipped = False
        for k in range(2 * (a.max_scrolls or 8) + 1):
            s = await self._observe()
            m = locators.locate(a.target, s, ctx.inputs, threshold=locators.STRICT)
            if not m.ok:
                rm = locators.locate(a.target, s, ctx.inputs, threshold=locators.RELAXED)
                if rm.ok:
                    sr.climb(2, f"relaxed match while scrolling: {rm.summary()}")
                    m = rm
            if m.ok:
                sr.score = round(m.score, 3)
                return True
            if k >= (a.max_scrolls or 8) and flipped:
                return False
            container = None
            if a.container is not None:
                cm = locators.locate(a.container, s, ctx.inputs, threshold=locators.RELAXED, margin=0.0)
                container = cm.element.number if cm.element is not None else None
            if container is None:
                lists = [e for e in s.numbered if e.kind == "List"]
                container = max(lists, key=lambda e: e.area).number if lists else None
            before_body = body(s)
            await self.device.act(Action(kind="scroll", direction=direction, element=container))
            settled = await self._settle_quick()
            if body(settled) == before_body:  # the end of the list: the tree stopped changing
                if flipped:
                    return False
                direction = {"down": "up", "up": "down", "left": "right", "right": "left"}[direction]
                flipped = True
        return False

    async def _visual_point(self, ctx: _Ctx, step: Step, screen: ScreenState, sr: StepRun) -> tuple[int, int] | None:
        """A drawn target: the recorded picture if it is clearly and uniquely on screen (no model call), else Muse Spark's
        SAM 3.1 + choose, then grounding, for its description (agent/vision.py). Never on a secure screen."""
        loc = step.action.target
        assert loc is not None and loc.visual
        if screen.secure:
            return None
        png = await self.device.screenshot()
        size = (screen.width, screen.height)
        density = getattr(getattr(self.device, "capabilities", None), "density", None)
        if loc.crop and not has_slot(loc.visual):  # a picture of seat 10C is never the target "seat {{seat}}"
            scale = density / loc.density if density and loc.density else 1.0
            point, best, second = await asyncio.to_thread(match_crop, png, loc.crop, size, scale)
            if point is not None:
                sr.rungs.append(f"found its picture (match {best:.2f}, next {second:.2f})")
                return point
        desc = render_str(loc.visual, ctx.inputs) or loc.visual
        vis = Vision(self.adapter, data_scope=self.config.data_scope, contributor=self.config.contributor, task_id=ctx.task_id)
        found = await asyncio.to_thread(vis.locate, "hybrid", png, desc, size)
        ctx.out.model_calls += found.calls
        ctx.out.cost_usd += found.cost_usd
        ctx.out.cost_at_standard_usd += found.cost_at_standard_usd
        sr.rungs.append(f"looked for {desc!r} ({found.method}, {found.ms / 1000:.1f} s)" + ("" if found.point else ": not found"))
        return found.point

    async def _reveal(self, ctx: _Ctx, step: Step, max_scrolls: int = 8) -> tuple[ScreenState, locators.Match] | None:
        """Scroll the screen's largest list down (then back up) until the step's target and before-checks hold.
        None if the screen has no list or the target never shows: the ladder goes on to repair."""
        s = await self._observe()
        direction, flipped = "down", False
        for _ in range(2 * max_scrolls):
            lists = [e for e in s.numbered if e.kind == "List"]
            if not lists:
                return None
            before_body = body(s)
            await self.device.act(Action(kind="scroll", direction=direction, element=max(lists, key=lambda e: e.area).number))
            s = await self._settle_quick()
            m = self._target(step, s, ctx.inputs)
            if not m or not m.ok:
                m = self._target(step, s, ctx.inputs, relaxed=True)
            if m is not None and m.ok and self._check(step.pre, s, ctx.inputs, relaxed=True)[0]:
                return s, m
            if body(s) == before_body:  # the end of the list
                if flipped:
                    return None
                direction, flipped = "up", True
        return None

    async def _reveal_checks(self, ctx: _Ctx, checks: list[Check], before: ScreenState | None, max_scrolls: int = 4) -> ScreenState | None:
        """Scroll the largest list down, then up, until the checks hold; the screen where they did, or None."""
        s = await self._observe()
        for direction in ("down", "up"):
            for _ in range(max_scrolls):
                lists = [e for e in s.numbered if e.kind == "List"]
                if not lists:
                    return None
                before_body = body(s)
                await self.device.act(Action(kind="scroll", direction=direction, element=max(lists, key=lambda e: e.area).number))
                s = await self._settle_quick()
                if self._check(checks, s, ctx.inputs, before=before)[0]:
                    return s
                if body(s) == before_body:
                    break
        return None

    async def _read_scrolled(self, ctx: _Ctx, specs: dict[str, Any], missing: list[str], max_scrolls: int = 8) -> list[str]:
        """Read outputs that aren't on screen by scrolling the largest list up, then down. Returns what is still missing."""
        missing = [n for n in missing if n in specs]
        s = await self._observe()
        for direction in ("up", "down"):
            for _ in range(max_scrolls):
                lists = [e for e in s.numbered if e.kind == "List"]
                if not missing or not lists:
                    return [n for n in ctx.routine.outputs if not ctx.out.outputs.get(n)]
                before_body = body(s)
                await self.device.act(Action(kind="scroll", direction=direction, element=max(lists, key=lambda e: e.area).number))
                s = await self._settle_quick()
                for n in missing:
                    ctx.out.outputs[n] = ctx.out.outputs.get(n) or extract_value(specs[n], s, ctx.inputs)
                missing = [n for n in missing if not ctx.out.outputs.get(n)]
                if body(s) == before_body:
                    break
        return [n for n in ctx.routine.outputs if not ctx.out.outputs.get(n)]

    async def _settle_quick(self, quiet_s: float = 0.15, timeout_s: float = 2.0) -> ScreenState:
        """Until two reads `quiet_s` apart are the same (after a scroll's fling)."""
        start = time.perf_counter()
        prev = await self._observe()
        while time.perf_counter() - start < timeout_s:
            await asyncio.sleep(quiet_s)
            cur = await self._observe()
            if body(cur) == body(prev):
                return cur
            prev = cur
        return prev

    # ---- rung 4: local repair ---------------------------------------------------------------

    def _step_text(self, step: Step, inputs: dict[str, str]) -> str:
        r: Step = render(step, inputs)
        tgt = r.action.target.describe() if r.action.target else ""
        lines = [f"intent: {r.intent}", f"action: {r.action.kind} {tgt}".strip()]
        if r.action.kind == "type":
            lines.append(f"text to type: {r.action.value!r}")
        lines.append("AFTER-CHECKS (must hold when the step is done):")
        lines += [f"- {c.describe()}" for c in r.post] or ["- (none)"]
        return "\n".join(lines)

    async def _repair(self, ctx: _Ctx, idx: int, sr: StepRun, *, phase: Literal["before", "after"], screen: ScreenState,
                      why: str, before: ScreenState | None = None) -> str | _Ready:
        """Up to 2 model calls (5 per run), one action each, toward the step's after-checks.

        Returns "post_ok" (the step's effect now holds), a _Ready (the step itself can now run), or a reason it gave up."""
        step = ctx.routine.steps[idx]
        cfg = self.config
        if not ctx.allow_repair:
            return "gave_up"
        specific = self._specific(step.post)
        start = before or screen  # "the screen changed" is judged against where the step began, never against nothing
        actions: list[RepairAction] = []
        tried: list[str] = [f"(runtime) {why}"]
        s = screen
        while True:
            fields = await self._field_values(specific, s, ctx.inputs)
            # The app changed (that's why we're repairing), so its after-checks may only match at the relaxed threshold.
            # A step whose only after-check is "the screen changed" counts as done only after a repair action changed it.
            done = (self._check(specific, s, ctx.inputs, before=start, field_text=fields, relaxed=True)[0] if specific
                    else bool(actions) and body(s) != body(start))
            if done:
                if actions or phase == "after":
                    self._propose(ctx, idx, phase, actions, s)
                    sr.climb(4, f"{len(actions)} repair action(s) satisfied the after-checks")
                    return "post_ok"
                ctx.out.patches.append(Patch("remove", step.id, f"step {step.id!r}: its effect already held without it"))
                return "post_ok"
            if phase == "before" and actions and self._ready_now(step, s, ctx.inputs):
                self._propose(ctx, idx, "before_ready", actions, s)
                sr.climb(4, f"{len(actions)} repair action(s) reached the step's screen")
                m = self._target(step, s, ctx.inputs)
                return _Ready("ok", s, m.element if m else None)
            if len([a for a in sr.repairs if a.get("model")]) >= cfg.max_repairs_step or ctx.repairs_run >= cfg.max_repairs_run:
                return "gave_up"
            remaining = "\n".join(f"- {render_str(x.intent, ctx.inputs)}" for x in ctx.routine.steps[idx + 1:])
            content = [{"type": "input_text", "text": repair_input(render_str(ctx.routine.intent, ctx.inputs) or "",
                                                                  self._step_text(step, ctx.inputs), remaining, "\n".join(tried), s.compact)}]
            t0 = time.perf_counter()
            res = await asyncio.to_thread(self.adapter.call, "repair", content, instructions=REPAIR_INSTRUCTIONS, data_scope=cfg.data_scope,
                                          contributor=cfg.contributor, task_id=ctx.task_id, effort=cfg.repair_effort)
            ctx.repairs_run += 1
            ctx.out.model_calls += 1
            ctx.out.cost_usd += res.cost_usd
            ctx.out.cost_at_standard_usd += res.cost_at_standard_usd
            d: StepOutput = res.parsed  # type: ignore[assignment]
            rec: dict[str, Any] = {"model": True, "phase": phase, "decision": d.model_dump(), "model_ms": round((time.perf_counter() - t0) * 1000),
                                   "cost_usd": res.cost_at_standard_usd}
            sr.repairs.append(rec)
            kind = d.action.type
            if kind in ("done", "fail", "handoff", "ask_user", "look"):
                tried.append(f"model returned {kind}: {getattr(d.action, 'result', None) or getattr(d.action, 'reason', '')}")
                if kind in ("fail", "handoff", "ask_user"):
                    return f"repair gave up: {kind}"
                s = await self._observe()
                continue
            try:
                action = to_device_action(d.action, s)
                if action is not None and action.element is not None:
                    s.element(action.element)
            except InvalidElement as e:
                tried.append(f"invalid element: {e}")
                s = await self._observe()
                continue
            if action is None:
                continue
            el = s.numbered[action.element - 1] if action.element else None
            gated = await self._gate(ctx, action, s, d.risk, el.label if el else action.kind, sr, origin="repair")
            if gated is None:
                sr.status, sr.detail = "declined", "the user declined a repair action"
                ctx.out.status = "declined"
                return "declined"
            action = gated
            shot_b = await self._screenshot(ctx, f"repair_{idx + 1:02d}_{len(actions) + 1}_before")
            r = await self.device.act(action)
            after = await self._settle_after_repair(step, ctx.inputs, start)
            shot_a = await self._screenshot(ctx, f"repair_{idx + 1:02d}_{len(actions) + 1}_after")
            actions.append(RepairAction(d.reason, action.model_dump(), el, s, after, d.risk, shot_b, shot_a))
            rec.update({"action": action.model_dump(exclude_none=True), "target": el.label if el else None, "ok": r.ok,
                        "screen_before": screen_record(s), "screen_after": screen_record(after),
                        "tree_before": ctx.trace.save_tree(idx + 1, f"repair{len(actions)}_before", s),
                        "tree_after": ctx.trace.save_tree(idx + 1, f"repair{len(actions)}_after", after)})
            tried.append(f"{action.kind} on {el.label if el else ''!r} → screen now: {after.compact.splitlines()[1] if len(after.compact.splitlines()) > 1 else ''}")
            s = after

    async def _settle_after_repair(self, step: Step, inputs: dict[str, str], before: ScreenState) -> ScreenState:
        """After a repair action: until the after-checks pass, or the screen stops changing."""
        start = time.perf_counter()
        last, since = None, start
        specific = self._specific(step.post)
        while True:
            s = await self._observe()
            now = time.perf_counter()
            if specific and self._check(specific, s, inputs, before=before, relaxed=True)[0]:
                return s
            if body(s) != last:
                last, since = body(s), now
            elif now - since >= 0.6 or now - start > 4.0:
                return s
            await asyncio.sleep(self.config.poll_s)

    def _new_step(self, ctx: _Ctx, a: RepairAction, sid: str, optional: bool) -> Step:
        """A routine step from one repair action, with checks written from its before and after trees."""
        examples = {k: v for k, v in ctx.inputs.items() if v}
        kind = a.action["kind"]
        target = None
        if a.element is not None:
            target = generalize_locator(locators.build(a.element, a.before), examples, [], None, None)
        if kind == "type":
            action = StepAction(kind="type", target=target, value=bind_inputs(a.action.get("text") or "", examples), submit=a.action.get("submit", False))
        elif kind in ("tap", "long_press"):
            action = StepAction(kind=kind, target=target)
        elif kind == "back":
            action = StepAction(kind="back")
        elif kind == "scroll":
            action = StepAction(kind="scroll_until", target=target, direction=a.action.get("direction") or "down", max_scrolls=8)
        else:
            action = StepAction(kind="wait", seconds=1.0)
        post = chk.derive_post(a.before, a.after or a.before, kind, a.element, a.action.get("text"), examples,
                               submit=a.action.get("submit", False)) if a.after else [Check(kind="screen_changed")]
        post = [g for c in post if (g := chk_generalize(c, examples, [])) is not None] or [Check(kind="screen_changed")]
        pre = [Check(kind="app_foreground", package=a.before.package)]
        risk = a.risk if a.risk in ("read", "reversible", "irreversible") else "reversible"
        return Step(id=sid, intent=a.reason, pre=pre, action=action, post=post, risk=risk, optional=optional, note="added by local repair")

    def _propose(self, ctx: _Ctx, idx: int, phase: str, actions: list[RepairAction], screen: ScreenState) -> None:
        if not actions:
            return
        step = ctx.routine.steps[idx]
        ev = {"screenshots": [p for a in actions for p in (a.screenshot_before, a.screenshot_after) if p],
              "reasons": [a.reason for a in actions], "task_id": ctx.task_id}
        if phase == "after":
            new = [self._new_step(ctx, a, f"{step.id}_extra_{k + 1}", optional=True) for k, a in enumerate(actions)]
            ctx.out.patches.append(Patch("insert_after", step.id, f"after {step.id!r}, an extra screen appeared; inserted "
                                         + ", ".join(f"{s.id} ({s.action.kind} {s.action.target.text if s.action.target else ''})" for s in new),
                                         steps=new, evidence=ev))
        elif phase == "before_ready":
            new = [self._new_step(ctx, a, f"{step.id}_pre_{k + 1}", optional=True) for k, a in enumerate(actions)]
            ctx.out.patches.append(Patch("insert_before", step.id, f"before {step.id!r}, the screen needed "
                                         + ", ".join(f"{s.action.kind} {s.action.target.text if s.action.target else ''}" for s in new),
                                         steps=new, evidence=ev))
        else:  # the step's own action never ran; the repair did its job
            same_screen = len(actions) == 1 and actions[0].element is not None and step.action.kind in ("tap", "long_press", "type") \
                and actions[0].action["kind"] == step.action.kind
            if same_screen:
                a = actions[0]
                new_loc = locators.updated(step.action.target or Locator(), a.element, a.before)  # type: ignore[arg-type]
                ctx.out.patches.append(Patch("locator", step.id, f"step {step.id!r}: the element moved or changed; new locator {new_loc.describe()}",
                                             locator=new_loc, evidence=ev))
            else:
                new = [self._new_step(ctx, a, f"{step.id}_{k + 1}", optional=False) for k, a in enumerate(actions)]
                new[-1].post = new[-1].post + [c for c in step.post if c.kind != "screen_changed" and c not in new[-1].post]
                new[0].pre = step.pre + [c for c in new[0].pre if c not in step.pre]
                ctx.out.patches.append(Patch("replace", step.id, f"step {step.id!r} replaced by "
                                             + ", ".join(f"{s.action.kind} {s.action.target.text if s.action.target else ''}" for s in new),
                                             steps=new, evidence=ev))

    # ---- rungs 5 and 6 ----------------------------------------------------------------------

    async def _escalate(self, ctx: _Ctx, idx: int, sr: StepRun, why: str) -> Literal["stop", "finished"]:
        if why == "declined":
            return "stop"
        step = ctx.routine.steps[idx]
        if not ctx.allow_agent:
            sr.status, sr.detail = "failed", f"step {step.id}: {why}"
            ctx.out.status = "failed"
            return "stop"
        sr.climb(5, why)
        done = [render_str(s.intent, ctx.inputs) for s in ctx.routine.steps[:idx]]
        # The agent finishes what the user asked (their own words when we have them; the routine's intent otherwise).
        goal = (f"{ctx.request.rstrip('.')}. " if ctx.request else f"{render_str(ctx.routine.intent, ctx.inputs)}. ")
        goal = (goal
                + (f"Inputs: {', '.join(f'{k} = {v}' for k, v in ctx.inputs.items())}. " if ctx.inputs else "")
                + (f"A saved routine already did: {'; '.join(done)}. " if done else "")
                + "Finish the task from the current screen.")
        cfg = self.config.agent or RunConfig(data_scope=self.config.data_scope, contributor=self.config.contributor)
        runner = AgentRunner(self.device, adapter=self.adapter, approver=self.approver, config=cfg)
        res = await runner.run(goal, task_id=f"{ctx.task_id}-agent", memory=ctx.memory)
        ctx.out.model_calls += res.model_calls
        ctx.out.cost_usd += res.cost_usd
        ctx.out.cost_at_standard_usd += res.cost_at_standard_usd
        ctx.out.approvals += res.approvals
        ctx.out.agent = {"task_id": res.task_id, "status": res.status, "result": res.result, "steps": res.steps,
                         "model_calls": res.model_calls, "cost_usd": res.cost_usd, "trace_dir": res.trace_dir}
        sr.status, sr.detail = "agent", f"full agent took over: {res.status}"
        if res.succeeded:
            screen = await self._observe()
            for st in ctx.routine.steps[idx:]:
                await self._extract(ctx, st, screen)
            ctx.out.status, ctx.out.detail = "agent_done", f"step {step.id} failed ({why}); the full agent finished: {res.result}"
        elif res.status in ("needs_user", "handoff"):
            sr.climb(6, res.result)
            ctx.out.status, ctx.out.detail = ("needs_user" if res.status == "needs_user" else "handoff"), res.result
        else:
            sr.climb(6, f"agent {res.status}: {res.result}")
            ctx.out.status = "needs_user"
            ctx.out.detail = f"routine step {step.id} failed ({why}) and the agent could not finish ({res.status}); asking the user"
        return "finished"

    # ---- outputs ----------------------------------------------------------------------------

    async def _extract(self, ctx: _Ctx, step: Step, screen: ScreenState) -> None:
        if not step.extract:
            return
        read = False
        for name, spec in step.extract.items():
            if ctx.out.outputs.get(name):
                continue
            ctx.out.outputs[name] = extract_value(spec, screen, ctx.inputs)
            read = read or bool(ctx.out.outputs[name])
        if read:  # the screen the answer was read from (its tree, never a screenshot): evidence for checking it
            ctx.trace.save_tree(len(ctx.out.steps) + 1, f"outputs_{step.id}"[:48], screen)


def extract_value(spec: Extract, screen: ScreenState, inputs: dict[str, str]) -> str | None:
    value = _extract(spec, screen, inputs)
    if value is not None and spec.expect_digits and not any(ch.isdigit() for ch in value):
        return None  # a placeholder while the page loads ("- calories"): not the value yet
    return value


def _in_card(loc: Locator, card: str, screen: ScreenState) -> Element | None:
    """The element `loc` names inside the row (same parent) that shows `card`: "CHIPS & GUACAMOLE" before
    "CHILI LIME CHIPS & GUACAMOLE", so an exact match first."""
    want = norm(card)
    for exact in (True, False):
        for holder in [e for e in screen.elements if e.parent is not None and want
                       and (norm(e.label or e.text or e.desc) == want if exact else want in norm(e.label or e.text or e.desc))]:
            el = next((e for e in screen.numbered if e.parent == holder.parent and e.index != holder.index
                       and (not loc.resource_id or locators.id_matches(loc.resource_id, short_id(e.resource_id)))
                       and (not loc.kind or e.kind == loc.kind)), None)
            if el is not None:
                return el
    return None


def _after_card(card: str, near: str, screen: ScreenState) -> Element | None:
    """The first element labelled `near` after the one that shows `card` among other words (a result, not the search box
    that shows only the term)."""
    want = norm(card)
    shown = next((e for e in screen.numbered if want and want in norm(e.full_label or e.label) and norm(e.label) != want), None)
    if shown is None:
        return None
    return next((e for e in screen.numbered if (e.number or 0) > (shown.number or 0) and norm(e.label).startswith(near)), None)


def _extract(spec: Extract, screen: ScreenState, inputs: dict[str, str]) -> str | None:
    """The value in an element: the recorded " · " part of its label if there are several ("Gate · B12" → B12),
    with the label in front of it ("Known traveler number: 98765432" → 98765432) and fixed text after it removed.
    Without IDs it falls back to the label (`near`), then to the element that shows one of the routine's inputs."""
    spec = render(spec, inputs)
    if spec.pattern:
        for e in screen.numbered:
            label = " ".join(e.label.split())
            if (e.in_list or not spec.first_in_list) and (m := re.fullmatch(spec.pattern, label)):
                return (m.group("v") if "v" in m.groupdict() else label).strip() or None
        return None
    if spec.next_element and spec.near:
        label_el = next((e for e in screen.numbered if norm(e.label) == norm(spec.near)), None)
        at = (label_el.number + (spec.offset or 1) - 1) if label_el is not None and label_el.number else len(screen.numbered)
        if at >= len(screen.numbered):
            return None
        return " ".join(screen.numbered[at].label.split()) or None
    el = None
    loc = render(spec.locator, inputs) if spec.locator is not None else None
    ids_shown = any(usable_id(e.resource_id) for e in screen.numbered)
    if spec.card and loc is not None:
        el = _in_card(loc, spec.card, screen)
        if el is None:
            return None  # the row isn't on screen: the output is missing, and the ladder takes over
    elif loc is not None and (loc.text or loc.desc or loc.text_has or (loc.resource_id and ids_shown)):
        # An ID-only locator means nothing on a screen that shows no IDs: fall back to the label (`near`).
        el = locators.locate(loc, screen, threshold=locators.RELAXED, margin=0.0, role="check").element
        if el is not None and loc.text_has and norm(el.label) == norm(loc.text_has):
            # The element shows only the input itself (the search box, a "pizza" chip): it holds no output. Take the
            # first element of that type that shows the input among other text (a result row).
            el = next((e for e in screen.numbered if (not loc.kind or e.kind == loc.kind) and norm(e.label) != norm(loc.text_has)
                       and contains_value(e.label, loc.text_has)), None)
    near = norm(spec.near) if spec.near else ""
    if el is None and spec.card and loc is None and near:
        el = _after_card(spec.card, near, screen)
        if el is None:
            return None  # the requested result isn't on screen: missing, and the ladder takes over
    if el is None and near:
        named = [e for e in screen.numbered if norm(e.label).startswith(near)]
        if spec.segment:  # the value is part N of a row: a row with that many parts, not a page title that only says the label
            el = next((e for e in named if len(parts_of(e.full_label or e.label)) > spec.segment), None)
        el = el or (named[0] if named else None)
        if el is not None and norm(el.label) == near and el.number and el.number < len(screen.numbered):
            # The label stands alone ("Seat", then "22F"): the value is the next element (its parts shift by one, as the
            # label is no longer the first part: "Boarding · 5:30 AM · Group 3" → "5:30 AM · Group 3").
            nxt_el = screen.numbered[el.number]
            value = " ".join((nxt_el.full_label or nxt_el.label).split())
            if spec.segment:
                parts = parts_of(value)
                value = parts[spec.segment - 1] if spec.segment - 1 < len(parts) else value
            return value or None
    if el is None and loc is not None and loc.kind:
        # No ID shown and no element starting with the label: the element of that type that shows one of the routine's
        # inputs (a status line containing the flight number that was searched, with "Gate A7" inside it).
        shown = [e for e in screen.numbered if e.kind == loc.kind and any(v and contains_value(e.label, v) for v in inputs.values())]
        el = shown[0] if len(shown) == 1 else None
    if el is None:
        return None
    if spec.switch:
        return ("on" if el.checked else "off") if el.checkable else None
    label = " ".join((el.full_label or el.label).split())  # the whole text: a long row's later parts are past the model's clip
    value = label
    if spec.segment is not None:
        parts = parts_of(label)
        if spec.segment >= len(parts):
            return None
        value = parts[spec.segment]
    if near and norm(value).startswith(near) and norm(value) != near:
        value = value[len(spec.near or ""):].strip(" ·:,")
    if spec.after and norm(value).endswith(norm(spec.after)):
        value = value[: len(value) - len(spec.after)].strip(" ·:,")
    return value or None
