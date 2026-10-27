"""The agent loop (design doc, Agent runtime): plan, then observe → decide → check policy → act → verify → record.

One model call per step (Muse Spark 1.3, low effort, structured output). Pop-ups, sign-in screens,
stuck detection, limits and success checks are handled in code, so the model only does what needs
judgment. Every step goes to a trace (agent/trace.py) that the routine compiler will read.
"""

from __future__ import annotations

import asyncio
import io
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from PIL import Image

from agent.checks import CheckResult, evaluate
from agent.popups import match_popup
from agent.trace import TraceWriter, element_record, screen_record
from devices.types import Action, Device, InvalidElement, ScreenState
from models.adapter import DataScope, ModelAdapter, image_part
from models.prompts import PLAN_INSTRUCTIONS, STEP_INSTRUCTIONS, plan_input, step_input
from models.schemas import Plan, StepOutput
from models.translate import to_device_action
from policy.approvals import ApprovalRequest, Approver, TerminalApprover
from policy.risk import classify
from policy.signin import sign_in_reason

Status = Literal["done", "done_unverified", "failed", "handoff", "needs_user", "step_limit", "cost_limit", "error"]

SCREENSHOT_WIDTH = 540  # a full 1080x2400 frame costs ~3,200 input tokens (Phase 0); half width costs ~4x less
HISTORY_STEPS = 5


@dataclass
class RunConfig:
    max_steps: int = 25
    max_cost_usd: float = 0.15
    data_scope: DataScope = "real"
    contributor: bool = False
    step_effort: str = "low"
    plan_effort: str = "low"
    plan: bool = True
    screenshots: Literal["auto", "never", "always"] = "auto"
    max_done_rejections: int = 2


@dataclass
class RunResult:
    task_id: str
    goal: str
    status: Status
    result: str
    steps: int = 0
    model_calls: int = 0
    cost_usd: float = 0.0
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    duration_s: float = 0.0
    approvals: list[dict[str, Any]] = field(default_factory=list)
    popups: list[str] = field(default_factory=list)
    plan: dict[str, Any] | None = None
    check: dict[str, Any] | None = None
    trace_dir: str = ""

    @property
    def succeeded(self) -> bool:
        return self.status in ("done", "done_unverified")


def _body(compact: str) -> str:
    """The compact screen without its header line (which carries the settle time)."""
    return compact.split("\n", 1)[1] if "\n" in compact else ""


def _where(s: ScreenState) -> str:
    title = next((e.label for e in s.numbered if e.resource_id.endswith("title") and e.label), None)
    title = title or next((e.label for e in s.numbered if e.kind == "Text" and e.label), "")
    return f"{s.activity.rsplit('.', 1)[-1] or s.package} · {title[:60]!r}"


def _describe(a: StepOutput, screen: ScreenState) -> str:
    act = a.action
    el = getattr(act, "element", None)
    target = ""
    if isinstance(el, int) and 1 <= el <= len(screen.numbered):
        e = screen.numbered[el - 1]
        target = f' [{el}] {e.kind} "{e.label}"' + (f" (id: {e.resource_id})" if e.resource_id else "")
    extra = ""
    if act.type == "type":
        extra = f' = "{act.text}"' + (" + Enter" if act.submit else "")
    elif act.type == "scroll":
        extra = f" {act.direction}"
    elif act.type in ("done", "fail", "handoff", "ask_user"):
        extra = f": {getattr(act, 'result', None) or getattr(act, 'reason', None) or getattr(act, 'question', '')}"
    elif act.type == "launch":
        extra = f" {act.app}"
    return f"{act.type}{target}{extra}"


class AgentRunner:
    def __init__(self, device: Device, adapter: ModelAdapter | None = None, approver: Approver | None = None,
                 config: RunConfig | None = None) -> None:
        self.device = device
        self.adapter = adapter or ModelAdapter()
        self.approver = approver or TerminalApprover()
        self.config = config or RunConfig()

    # ---- model calls ------------------------------------------------------------------------

    def _call(self, job: str, content: list[dict[str, Any]], instructions: str, effort: str, task_id: str):
        return self.adapter.call(job, content, instructions=instructions, data_scope=self.config.data_scope,
                                 contributor=self.config.contributor, task_id=task_id, effort=effort)

    async def _screenshot(self) -> bytes:
        png = await self.device.screenshot()
        img = Image.open(io.BytesIO(png))
        if img.width > SCREENSHOT_WIDTH:
            img = img.resize((SCREENSHOT_WIDTH, round(img.height * SCREENSHOT_WIDTH / img.width)))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    # ---- the loop ---------------------------------------------------------------------------

    async def run(self, goal: str, *, task_id: str | None = None, memory: str = "") -> RunResult:
        task_id = task_id or "task_" + uuid.uuid4().hex[:8]
        trace = TraceWriter(task_id)
        out = RunResult(task_id=task_id, goal=goal, status="error", result="", trace_dir=str(trace.dir))
        started = time.time()
        history: list[str] = []
        feedback = ""
        want_screenshot = self.config.screenshots == "always"
        rejections = 0
        no_change_streak = 0
        stuck_recoveries = 0
        plan: Plan | None = None
        last_bodies: list[str] = []
        visits: dict[str, int] = {}  # screen signature -> times seen
        names: dict[str, str] = {}  # screen signature -> readable name
        replans = 0
        prev_sig = ""

        def account(res) -> None:
            out.model_calls += 1
            out.cost_usd += res.cost_usd
            out.input_tokens += res.usage.get("input_tokens", 0)
            out.cached_tokens += res.usage.get("cached_tokens", 0)
            out.output_tokens += res.usage.get("output_tokens", 0)
            out.reasoning_tokens += res.usage.get("reasoning_tokens", 0)

        def finish(status: Status, result: str, check: CheckResult | None = None) -> RunResult:
            out.status, out.result = status, result
            out.duration_s = round(time.time() - started, 2)
            if check is not None:
                out.check = {"passed": check.passed, "evaluable": check.evaluable, "detail": check.detail}
            trace.finish({k: v for k, v in out.__dict__.items()})
            return out

        try:
            async def make_plan(current: ScreenState, tried: str = "", step_no: int = 0) -> Plan | None:
                t0 = time.perf_counter()
                res = await asyncio.to_thread(self._call, "plan", [{"type": "input_text", "text": plan_input(goal, current.compact, memory, tried)}],
                                              PLAN_INSTRUCTIONS, self.config.plan_effort, task_id)
                account(res)
                new_plan: Plan | None = res.parsed  # type: ignore[assignment]
                trace.step({"step": step_no, "kind": "replan" if tried else "plan", "plan": new_plan.model_dump() if new_plan else None,
                            "tried": tried or None, "model_ms": round((time.perf_counter() - t0) * 1000), "usage": res.usage, "cost_usd": res.cost_usd})
                return new_plan

            def visited_text() -> str:
                return " · ".join(f"{names[k]} ×{n}" for k, n in visits.items())

            screen = await self.device.wait_until_settled()
            if self.config.plan:
                plan = await make_plan(screen)
                out.plan = plan.model_dump() if plan else None
            plan_text = "\n".join(f"{i}. {s}" for i, s in enumerate(plan.subgoals, 1)) if plan else ""

            step = 0
            while True:
                step += 1
                if step > self.config.max_steps:
                    return finish("step_limit", f"stopped after {self.config.max_steps} steps")
                if out.cost_usd >= self.config.max_cost_usd:
                    return finish("cost_limit", f"stopped at ${out.cost_usd:.3f}")

                t_obs = time.perf_counter()
                screen = await self.device.wait_until_settled()
                observe_ms = (time.perf_counter() - t_obs) * 1000

                # 1. Sign-in screens belong to the user.
                if (why := sign_in_reason(screen)) is not None:
                    trace.step({"step": step, "kind": "handoff", "reason": why, "screen": screen_record(screen),
                                "tree": trace.save_tree(step, "before", screen)})
                    return finish("handoff", f"sign-in needed: {why}")

                # 2. Known pop-ups, without a model call.
                if (pop := match_popup(screen, goal)) is not None:
                    r = await self.device.act(Action(kind="tap", element=pop.element.number))
                    out.steps += 1
                    out.popups.append(pop.handler)
                    history.append(f"(runtime) dismissed a pop-up: {pop.handler} → tapped \"{pop.element.label}\"")
                    trace.step({"step": step, "kind": "popup", "handler": pop.handler, "target": element_record(pop.element, screen),
                                "ok": r.ok, "screen": screen_record(screen)})
                    continue

                # 3. Stuck detection: the same screen three times with no effect.
                body = _body(screen.compact)
                last_bodies = (last_bodies + [body])[-3:]
                if len(last_bodies) == 3 and len(set(last_bodies)) == 1 and no_change_streak >= 2:
                    stuck_recoveries += 1
                    if stuck_recoveries == 1:
                        feedback = "You are stuck: the last actions did not change the screen. Try a different element, scroll, or go back."
                    elif stuck_recoveries == 2:
                        await self.device.act(Action(kind="back"))
                        out.steps += 1
                        history.append("(runtime) stuck on the same screen: pressed back")
                        last_bodies, no_change_streak = [], 0
                        continue
                    else:
                        return finish("failed", "stuck on the same screen after two recoveries")

                # 3b. Cycle detection: coming back to a screen for the 4th time means the plan is not working.
                sig = screen.signature
                names.setdefault(sig, _where(screen).split(" · ", 1)[-1].strip("'\"") or screen.activity.rsplit(".", 1)[-1])
                visits[sig] = visits.get(sig, 0) + 1
                if sig != prev_sig and visits[sig] >= 4 + 3 * replans and self.config.plan and replans < 2:
                    replans += 1
                    tried = f"Screens visited so far, with counts: {visited_text()}"
                    new_plan = await make_plan(screen, tried, step)
                    if new_plan is not None:
                        plan = new_plan
                        plan_text = "\n".join(f"{i}. {x}" for i, x in enumerate(plan.subgoals, 1))
                        out.plan = plan.model_dump()
                    feedback = "You were going in circles, so the plan was rewritten. Follow the new PLAN and avoid screens that did not help."
                    history.append(f"(runtime) going in circles ({names[sig]} visited {visits[sig]} times): replanned")
                prev_sig = sig

                # 4. Decide.
                png = None
                if not screen.secure and self.config.screenshots != "never":
                    if want_screenshot or len(screen.numbered) < 3:
                        png = await self._screenshot()
                content = [{"type": "input_text", "text": step_input(goal, screen.compact, plan=plan_text,
                                                                      history="\n".join(history[-HISTORY_STEPS:]),
                                                                      memory=memory, feedback=feedback, visited=visited_text())}]
                if png:
                    content.append(image_part(png))
                t_model = time.perf_counter()
                try:
                    res = await asyncio.to_thread(self._call, "step", content, STEP_INSTRUCTIONS, self.config.step_effort, task_id)
                except ValueError as e:  # unparseable output even after recovery: ask once more
                    history.append(f"step {step}: (runtime) the model's reply was not valid JSON; asked again")
                    trace.step({"step": step, "kind": "model_error", "error": str(e)[:300]})
                    res = await asyncio.to_thread(self._call, "step", content, STEP_INSTRUCTIONS, self.config.step_effort, task_id)
                model_ms = (time.perf_counter() - t_model) * 1000
                account(res)
                decision: StepOutput = res.parsed  # type: ignore[assignment]
                feedback, want_screenshot = "", self.config.screenshots == "always"
                record: dict[str, Any] = {
                    "step": step, "kind": "action", "screen_before": screen_record(screen),
                    "tree_before": trace.save_tree(step, "before", screen),
                    "screenshot_before": trace.save_png(step, "before", png) if png else None,
                    "decision": decision.model_dump(), "usage": res.usage, "cost_usd": res.cost_usd,
                    "timings_ms": {"observe": round(observe_ms), "model": round(model_ms)},
                }
                desc = _describe(decision, screen)
                kind = decision.action.type

                # 5. Actions the runtime handles itself.
                if kind == "look":
                    want_screenshot = True
                    history.append(f"step {step}: look → a screenshot comes with the next step")
                    trace.step(record)
                    continue
                if kind in ("done", "fail", "handoff", "ask_user"):
                    trace.step(record)
                    if kind == "fail":
                        return finish("failed", decision.action.reason)  # type: ignore[union-attr]
                    if kind == "handoff":
                        return finish("handoff", decision.action.reason)  # type: ignore[union-attr]
                    if kind == "ask_user":
                        return finish("needs_user", decision.action.question)  # type: ignore[union-attr]
                    result = decision.action.result  # type: ignore[union-attr]
                    field_value = None
                    if plan and plan.success_check.kind == "field_equals" and plan.success_check.field_hint:
                        hint = plan.success_check.field_hint.casefold()
                        f = next((e for e in screen.numbered if (e.editable or e.checkable) and hint in e.label.casefold()), None)
                        if f is not None:
                            field_value = ("On" if f.checked else "Off") if f.checkable else f.text
                    chk = evaluate(plan.success_check if plan else None, screen, result, field_value)
                    if chk.passed or not chk.evaluable:
                        return finish("done" if chk.passed else "done_unverified", result, chk)
                    rejections += 1
                    if rejections > self.config.max_done_rejections:
                        return finish("done_unverified", result, chk)
                    feedback = (f"Your done was rejected: {chk.detail}. If the goal is really done, get to the screen that shows it "
                                f"(or state the answer exactly as the screen shows it); otherwise keep going.")
                    history.append(f"step {step}: done rejected by the success check ({chk.detail})")
                    continue

                # 6. Device action: validate the element, check policy, act.
                try:
                    action = to_device_action(decision.action, screen)
                    if action is not None and action.element is not None:
                        screen.element(action.element)
                except InvalidElement as e:
                    feedback = f"{e}. Choose a number from the current SCREEN."
                    history.append(f"step {step}: {desc} → invalid element, not executed")
                    record["error"] = str(e)
                    trace.step(record)
                    continue
                if action is None:
                    trace.step(record)
                    continue
                if action.kind == "tap_point" and png is None and len(screen.numbered) >= 3:
                    # Design: tap_point is only for screens with no usable tree, with coordinates from a screenshot.
                    feedback = ("tap_point is only for screens without usable elements, using coordinates read from a screenshot. "
                                "This screen has numbered elements: tap one of them (or use look first if you need to see the screen).")
                    history.append(f"step {step}: {desc} → rejected: blind tap_point while elements are listed")
                    record["error"] = "tap_point rejected: elements available and no screenshot"
                    trace.step(record)
                    continue

                verdict = classify(action, screen, decision.risk)
                record["risk"] = {"level": verdict.level, "reasons": verdict.reasons, "model": decision.risk}
                if verdict.irreversible:
                    target = screen.numbered[action.element - 1] if action.element else None
                    req = ApprovalRequest(task_id=task_id, goal=goal, app=screen.package,
                                          description=f'{action.kind} "{target.label if target else action.kind}" in {screen.package}',
                                          reasons=verdict.reasons, screen=screen.compact)
                    decision_ = await asyncio.to_thread(self.approver.request, req)
                    out.approvals.append({"step": step, "description": req.description, "reasons": req.reasons,
                                          "approved": decision_.approved, "by": decision_.by})
                    record["approval"] = {"approved": decision_.approved, "by": decision_.by}
                    if not decision_.approved:
                        history.append(f"step {step}: {desc} → the user DECLINED this action. Do not retry it.")
                        trace.step(record)
                        continue

                t_act = time.perf_counter()
                result_ = await self.device.act(action)
                out.steps += 1
                act_ms = (time.perf_counter() - t_act) * 1000
                after = await self.device.wait_until_settled()
                changed = _body(after.compact) != body
                no_change_streak = 0 if changed else no_change_streak + 1
                record.update({
                    "device_action": action.model_dump(), "result": result_.model_dump(),
                    "target": element_record(screen.numbered[action.element - 1], screen) if action.element else None,
                    "screen_after": screen_record(after), "tree_after": trace.save_tree(step, "after", after),
                    "changed": changed,
                })
                record["timings_ms"].update({"act": round(act_ms), "settle": round(after.settle_ms or 0)})
                trace.step(record)

                if not result_.ok:
                    history.append(f"step {step}: {desc} → FAILED: {result_.error}")
                elif changed:
                    history.append(f"step {step}: {desc} → screen changed, now {_where(after)} (expected: {decision.expected_result})")
                else:
                    want_screenshot = self.config.screenshots != "never"
                    history.append(f"step {step}: {desc} → NO VISIBLE CHANGE (expected: {decision.expected_result})")
        except Exception as e:  # noqa: BLE001 - a failed run keeps its trace
            return finish("error", f"{type(e).__name__}: {e}")
