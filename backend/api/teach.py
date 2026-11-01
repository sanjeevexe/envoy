"""Teach mode: you do a task once through the live view, and Envoy learns it as a routine (design doc, App routines ›
Taught routines).

Routines used to come only from the agent's successful runs, so an app the agent can't do never got one. In teach mode
you take over the phone with a goal in your words ("Add a Calendar event called Dentist tomorrow at 3pm") and do it
yourself. Each live-view input is recorded with the screen before it and the screen once it settles, as a trace in the
agent's own format (agent/trace.py), and the same compiler (routines/compiler.py) turns it into a routine. Your "it
worked" is the verification, as an agent run's success check is; then the routine is replayed once, strictly (no
repair, no agent), on the same phone, and only a replay that passes goes into the library, marked taught.

What a demonstration becomes:
- A tap is the smallest clickable element under your finger (a coordinate tap when there is none). A tap on the
  on-screen keyboard is typing, and typing is one `type` step into the field in focus, with the text the field shows
  at the end (so Backspace and edits come out right); Enter after it submits.
- A drag inside a list is a scroll (the compiler turns scrolls before a list tap into `scroll_until`); any other drag is
  a swipe. Back is back. Taps on the home screen, Home and Recents only find the app: the routine launches it itself.
- Risk comes from the same rules the agent's actions get (policy/risk.py `classify`); there is no model and no reason.

Privacy (live.py: takeover input is never logged, stored or shown to a model):
- Nothing is recorded outside an explicit teach mode, which you start, and which the live view shows as Recording.
- On a sign-in or secure screen (policy/signin.py `sign_in_reason`, a password field, FLAG_SECURE, a black frame from a
  real phone) recording pauses and stores nothing: no tree, no picture, no input. It resumes on the next ordinary screen.
- Text typed into a password field is never recorded. Cancel deletes everything recorded; so does "it didn't work".
"""

from __future__ import annotations

import asyncio
import io
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.trace import RUNS, TraceWriter, element_record, screen_record
from devices.screen import _KEYBOARD_PACKAGES, content_hash, has_app_content
from devices.types import Action, Element, ScreenState
from policy.risk import classify
from policy.signin import sign_in_reason

from api.store import new_id

# The home screen and the system's own windows (the notification shade, Recents): taps there only find the app.
_LAUNCHER = re.compile(r"launcher|trebuchet|com\.android\.systemui$", re.I)
_HORIZONTAL = re.compile(r"horizontal|pager|carousel", re.I)
SETTLE_S = 4.0  # a screen still changing after this is taken as it is (a spinner, a clock)
IDLE_S = 20 * 60  # a teach session with no input for this long is cancelled: it would hold the phone from every task
IDLE_CHECK_S = 30
QUIET_MS = 300  # settled: nothing visible changed for this long
MIN_DRAG = 0.02  # of the screen's width: a shorter swipe is a tap (LivePhone sends taps under this)


def private_reason(screen: ScreenState, frame: Any = None) -> str | None:
    """Why nothing may be recorded on this screen, or None."""
    if screen.secure:
        return "a secure screen"
    if (why := sign_in_reason(screen)) is not None:
        return f"a sign-in screen ({why})"
    if frame is not None and _black(frame):
        return "a protected screen"  # a real phone's secure window, as scrcpy shows it
    return None


def _black(img: Any) -> bool:
    try:
        return img.convert("L").getextrema()[1] < 12
    except Exception:  # noqa: BLE001
        return False


def _contains(e: Element, x: int, y: int) -> bool:
    return e.bounds[0] <= x <= e.bounds[2] and e.bounds[1] <= y <= e.bounds[3]


def _under_finger(screen: ScreenState, x: int, y: int) -> list[Element]:
    """What a finger at (x, y) reaches: the topmost interactive element there and the elements it sits in. Android hands
    a touch to the view drawn on top, so an element another one covers (the calendar under an event editor sheet) is
    not reached. In one window the later element in tree order is drawn on top; of two windows the smaller one is (a
    dialog or menu over the app), as dumps list windows in no fixed order."""
    by_index = {e.index: e for e in screen.elements}

    def window(e: Element) -> Element:
        while e.parent is not None and e.parent in by_index:
            e = by_index[e.parent]
        return e

    under = [e for e in screen.elements if e.visible and not e.status_bar and _contains(e, x, y)
             and (e.clickable or e.long_clickable or e.editable or e.checkable or e.scrollable)]
    top = min(under, key=lambda e: (window(e).area, -e.index), default=None)
    reached = []
    while top is not None:
        reached.append(top)
        top = by_index.get(top.parent) if top.parent is not None else None
    return reached


def element_at(screen: ScreenState, x: int, y: int, long: bool = False) -> Element | None:
    """The element a tap at (x, y) lands on: the smallest listed clickable element under the finger that nothing covers
    (for a long press, a long-clickable one first). None means a coordinate tap."""
    hits = [e for e in _under_finger(screen, x, y) if e.number is not None
            and (e.clickable or e.long_clickable or e.editable or e.checkable)]
    if long and (held := [e for e in hits if e.long_clickable]):
        hits = held
    return min(hits, key=lambda e: e.area, default=None)


def on_keyboard(screen: ScreenState, x: int, y: int) -> bool:
    """The point is on the on-screen keyboard (its own window, which the tree lists but the screen leaves out)."""
    return any(e.visible and _KEYBOARD_PACKAGES.search(e.package) and _contains(e, x, y) for e in screen.elements)


def drag_action(screen: ScreenState, x1: int, y1: int, x2: int, y2: int) -> tuple[Action, Element | None]:
    """A drag inside a list is a scroll of that list ("down" reveals what is further down: the finger moves up); any other
    drag (a slider, a bottom sheet, a carousel that isn't a list) is a swipe. A list something covers isn't dragged."""
    dx, dy = x2 - x1, y2 - y1
    vertical = abs(dy) >= abs(dx)
    lists = [e for e in _under_finger(screen, x1, y1) if e.scrollable and e.number is not None]
    if not vertical:
        lists = [e for e in lists if _HORIZONTAL.search(e.cls) or _HORIZONTAL.search(e.resource_id)]
    box = min(lists, key=lambda e: e.area, default=None)
    if box is None:
        return Action(kind="swipe", x=x1, y=y1, x2=x2, y2=y2), None
    direction = ("down" if dy < 0 else "up") if vertical else ("right" if dx < 0 else "left")
    return Action(kind="scroll", element=box.number, direction=direction), box


def _same_field(a: Element, b: Element) -> bool:
    return a.editable and b.editable and a.resource_id == b.resource_id and a.bounds == b.bounds


def _find_field(screen: ScreenState, like: Element | None) -> Element | None:
    fields = [e for e in screen.numbered if e.editable]
    if like is not None:
        same = [e for e in fields if _same_field(e, like)] or [e for e in fields if like.resource_id and e.resource_id == like.resource_id]
        if same:
            return same[0]
    return next((e for e in fields if e.focused), None)


def _field_text(f: Element | None) -> str:
    """What a field holds: an empty field reports its hint as its text."""
    if f is None or f.password or not f.text or f.text == f.hint:
        return ""
    return f.text


@dataclass
class _Step:
    action: Action
    before: ScreenState
    target: Element | None
    started: float
    frame: Any = None


@dataclass
class _Typing:
    before: ScreenState
    field: Element
    typed: str = ""  # what you typed here (Backspace applied), used when the field's own text can't be read
    submit: bool = False
    keyboard_taps: int = 0
    started: float = 0.0
    frame: Any = None


class Recorder:
    """Records one demonstration as a trace (`data/runs/<teach id>/`). live.py calls `before` and `after` around every
    input while teach mode is on, one input at a time (`lock`)."""

    def __init__(self, teach_id: str, goal: str, device: Any, *, root: Path = RUNS, on_change: Any = None,
                 screenshots: bool = True) -> None:
        self.id, self.goal, self.device = teach_id, goal, device
        self.trace = TraceWriter(teach_id, root)
        self.lock = asyncio.Lock()
        self.on_change = on_change or (lambda: None)  # the live view's Recording line follows `state()`
        self.screenshots = screenshots
        self.started = self.last_input = time.time()
        self.n = 0  # steps written
        self.paused: str | None = None  # why recording is paused right now
        self.pauses = 0  # inputs not recorded because the screen was private
        self.notes: list[str] = []  # what was left out, and why (shown with the result)
        self.app = ""  # the app the demonstration happened in: the first recorded screen's
        self.last_after: ScreenState | None = None
        self._pending: _Step | None = None
        self._typing: _Typing | None = None
        self._last_screen: ScreenState | None = None
        self._settle_task: asyncio.Task | None = None
        self._interrupt = asyncio.Event()
        self._last_field: Element | None = None  # the last field you tapped: where typing goes when nothing says focused
        self._held_tap: tuple[_Step, ScreenState] | None = None  # a tap on a field, until we know whether typing follows
        self.closed = False

    def state(self) -> dict[str, Any]:
        return {"recording": "paused" if self.paused else "on", "why": self.paused or "", "steps": self.n + (self._pending is not None)
                + (self._typing is not None), "paused_inputs": self.pauses}

    # ---- around each input ------------------------------------------------------------------

    async def before(self, msg: dict[str, Any], w: int, h: int) -> None:
        """Called before the input goes to the phone. A failure here costs the step, never the input."""
        self.last_input = time.time()
        try:
            await self._before(msg, w, h)
        except Exception as e:  # noqa: BLE001
            self._pending = None
            self._note(f"a step couldn't be recorded ({type(e).__name__})")

    async def after(self, msg: dict[str, Any]) -> None:
        """The input has reached the phone: wait for the screen to settle (in the background; your next input ends the
        wait, and the screen it starts from is this step's result)."""
        typing_enter = self._typing is not None and self._typing.submit
        if self._pending is None and not typing_enter:
            return
        self._interrupt = asyncio.Event()
        self._settle_task = asyncio.get_running_loop().create_task(self._settle(self._interrupt))
        self.on_change()

    async def _before(self, msg: dict[str, Any], w: int, h: int) -> None:
        kind = msg.get("type")
        key = msg.get("key") if kind == "key" else None
        px = lambda fx, fy: (max(0, min(w - 1, round(float(fx) * w))), max(0, min(h - 1, round(float(fy) * h))))  # noqa: E731
        t = self._typing
        if t is not None and not t.submit:  # more typing into the same field: forwarded at once, read from the field at the end
            if kind == "text" and isinstance(msg.get("text"), str):
                t.typed += msg["text"][:500]
                return
            if key == "Backspace":
                t.typed = t.typed[:-1]
                return
            if kind == "tap" and self._last_screen is not None and on_keyboard(self._last_screen, *px(msg["x"], msg["y"])):
                t.keyboard_taps += 1
                return
            if key == "Enter":
                t.submit = True
                return
        settled = await self._wait_settle(interrupt=True)
        screen = await self._fresh()
        self._close(settled or screen)
        frame = await self._frame(screen)
        if (why := private_reason(screen, frame)) is not None:
            self._pause(why)
            return
        self._resume()
        if screen.package and _LAUNCHER.search(screen.package):
            self._note("on the home screen: finding the app isn't part of the routine (it launches the app itself)")
            return
        now = time.time()
        if kind in ("tap", "long_press"):
            x, y = px(msg["x"], msg["y"])
            if kind == "tap" and on_keyboard(screen, x, y):
                self._start_typing(screen, frame, keyboard=True)
                return
            el = element_at(screen, x, y, long=kind == "long_press")
            if el is not None and el.editable:
                self._last_field = el
            if el is None:
                action = Action(kind="tap_point", x=x, y=y)
                self._note(f"step {self.n + 1}: a tap where no element is listed is kept as a point, which a routine can't replay")
            else:
                action = Action(kind=kind, element=el.number)
            self._pending = _Step(action, screen, el, now, frame)
        elif kind == "swipe":
            (x1, y1), (x2, y2) = px(msg["x1"], msg["y1"]), px(msg["x2"], msg["y2"])
            if max(abs(x2 - x1), abs(y2 - y1)) < MIN_DRAG * w:
                return
            action, box = drag_action(screen, x1, y1, x2, y2)
            self._pending = _Step(action, screen, box, now, frame)
        elif kind == "text" and isinstance(msg.get("text"), str):
            if self._start_typing(screen, frame):
                self._typing.typed = msg["text"][:500]  # type: ignore[union-attr]
        elif key == "Backspace":
            self._start_typing(screen, frame)
        elif key == "Enter":
            if self._start_typing(screen, frame):  # Enter in a field: the field's text, submitted
                self._typing.submit = True  # type: ignore[union-attr]
        elif key == "Back":
            self._pending = _Step(Action(kind="back"), screen, None, now, frame)
        elif key in ("Home", "Recents"):
            self._note(f"{key} isn't part of the routine (it launches the app itself)")
        elif key == "Tab":
            self._note("Tab isn't recorded: tap the next field instead")

    # ---- finishing ----------------------------------------------------------------------------

    async def finish(self, answer: str = "") -> Path:
        """The last step's result, the screen the task ended on (the done step, as the agent's), and run.json."""
        async with self.lock:
            settled = await self._wait_settle() or await self._settle(asyncio.Event())
            screen = settled or await self._fresh()
            self._close(screen)
            self._flush_held()
            final = screen if private_reason(screen, await self._frame(screen)) is None else self.last_after
            if private_reason(screen) is not None:
                self._note("the last screen was a sign-in or secure screen: the routine ends at the screen before it")
            done = self.n + 1
            record: dict[str, Any] = {"step": done, "kind": "action", "taught": True,
                                      "decision": {"action": {"type": "done", "result": answer}, "reason": ""}}
            if final is not None:
                record.update(screen_before=screen_record(final), tree_before=self.trace.save_tree(done, "before", final))
            self.trace.step(record)
            self.trace.finish({
                "task_id": self.id, "goal": self.goal, "status": "done", "result": answer, "source": "taught", "taught": True,
                "check": {"passed": True, "evaluable": False, "detail": "you showed it and said it worked"},
                "plan": {"app": self.app} if self.app else None, "steps": self.n, "model_calls": 0, "cost_usd": 0.0,
                "cost_at_standard_usd": 0.0, "duration_s": round(time.time() - self.started, 1), "paused_inputs": self.pauses,
                "notes": self.notes,
            })
            self.closed = True
            return self.trace.dir

    async def discard(self) -> None:
        """Cancel: everything recorded is deleted."""
        async with self.lock:
            await self._wait_settle(interrupt=True)
            self._pending = self._typing = None
            self.closed = True
            try:
                self.trace._steps.close()
            except Exception:  # noqa: BLE001
                pass
            shutil.rmtree(self.trace.dir, ignore_errors=True)

    # ---- inside ---------------------------------------------------------------------------------

    async def _fresh(self) -> ScreenState:
        s = await self.device.observe()
        self._last_screen = s
        return s

    async def _frame(self, screen: ScreenState) -> Any:
        """A small picture of the screen (never of a secure one); None when there is none."""
        if not self.screenshots or screen.secure or not hasattr(self.device, "frame"):
            return None
        try:
            return await asyncio.to_thread(self.device.frame, 540, 3)
        except Exception:  # noqa: BLE001 - a step is recorded without its picture
            return None

    async def _settle(self, stop: asyncio.Event, poll_s: float = 0.06) -> ScreenState | None:
        """Read the screen until nothing visible changes for QUIET_MS (or `stop` is set: you acted again first)."""
        quiet_ms = QUIET_MS
        start = time.perf_counter()
        last_hash, last_change, screen = None, start, None
        while not stop.is_set():
            try:
                screen = await self.device.observe()
            except Exception:  # noqa: BLE001 - the next input reads the screen afresh
                return None
            now = time.perf_counter()
            h = content_hash(screen.elements)
            if h != last_hash:
                last_hash, last_change = h, now
            elif (now - last_change) * 1000 >= quiet_ms and has_app_content(screen.elements):
                break
            if now - start >= SETTLE_S:
                break
            await asyncio.sleep(poll_s)
        else:
            return None
        screen.settle_ms = round((last_change - start) * 1000)
        self._last_screen = screen
        if private_reason(screen) is not None:  # the Recording line says so at once, not at your next input
            self._pause(private_reason(screen) or "")
        return screen

    async def _wait_settle(self, interrupt: bool = False) -> ScreenState | None:
        task, self._settle_task = self._settle_task, None
        if task is None:
            return None
        if interrupt:
            self._interrupt.set()
        try:
            return await task
        except Exception:  # noqa: BLE001
            return None

    def _close(self, after: ScreenState) -> None:
        """Write the step (or typing) waiting for its result: the settled screen, or the one your next input started from."""
        if self._typing is not None:
            t, self._typing = self._typing, None
            self._write_typing(t, after)
        if self._pending is not None:
            p, self._pending = self._pending, None
            self._write(p, after)

    def _start_typing(self, screen: ScreenState, frame: Any, keyboard: bool = False) -> bool:
        f = next((e for e in screen.numbered if e.editable and e.focused), None) or _find_field(screen, self._last_field)
        if f is None:
            self._note("typing with no text field in focus isn't recorded")
            return False
        if f.password:  # sign_in_reason pauses on any password field; this is the field itself
            self._pause("a password field")
            return False
        self._typing = _Typing(screen, f, started=time.time(), frame=frame, keyboard_taps=int(keyboard))
        return True

    def _write(self, p: _Step, after: ScreenState) -> None:
        if (why := private_reason(after)) is not None:
            self._pause(why)  # the step that opened a sign-in is left out with it: replays start signed in
            return
        if p.target is not None and p.target.editable and p.action.kind == "tap":
            # A tap that only focused a field: the type step that follows focuses it itself, so it is kept only if no
            # typing into that field comes next (see _write_typing).
            self._held_tap = (p, after)
            return
        self._flush_held()
        self._emit(p.action, p.before, after, p.target, p.started, p.frame)

    def _flush_held(self) -> None:
        if self._held_tap is not None:
            p, after = self._held_tap
            self._held_tap = None
            self._emit(p.action, p.before, after, p.target, p.started, p.frame)

    def _write_typing(self, t: _Typing, after: ScreenState) -> None:
        if (why := private_reason(after)) is not None or t.field.password:
            self._pause(why or "a password field")
            self._held_tap = None
            return
        f = _find_field(after, t.field)
        if f is not None and f.password:
            self._pause("a password field")
            self._held_tap = None
            return
        value = _field_text(f) or (t.typed if not t.keyboard_taps else "")
        if not value:
            self._note("typing that left the field empty isn't recorded")
            self._flush_held()
            return
        if self._held_tap is not None and self._held_tap[0].target is not None and _same_field(self._held_tap[0].target, t.field):
            self._held_tap = None  # the tap only focused this field: typing focuses it itself
        self._flush_held()
        self._emit(Action(kind="type", element=t.field.number, text=value, submit=t.submit), t.before, after, t.field, t.started, t.frame)

    def _emit(self, action: Action, before: ScreenState, after: ScreenState, target: Element | None, started: float, frame: Any) -> None:
        self.n += 1
        n = self.n
        if not self.app and before.package:
            self.app = before.package
        verdict = classify(action, before, None)
        changed = action.kind == "type" or content_hash(before.elements) != content_hash(after.elements) \
            or before.signature != after.signature
        self.trace.step({
            "step": n, "kind": "action", "taught": True,
            "screen_before": screen_record(before), "tree_before": self.trace.save_tree(n, "before", before),
            "screenshot_before": self._save_png(n, frame),
            "decision": {"action": {"type": action.kind}, "reason": ""},  # no model: you did it
            "risk": {"level": verdict.level, "reasons": verdict.reasons, "model": None},
            "device_action": action.model_dump(),
            "result": {"ok": True, "error": None, "duration_ms": round((time.time() - started) * 1000), "target": None},
            "target": element_record(target, before) if target is not None else None,
            "screen_after": screen_record(after), "tree_after": self.trace.save_tree(n, "after", after),
            "changed": changed,
            "timings_ms": {"settle": round(after.settle_ms or 0)},
        })
        self.last_after = after
        self.on_change()

    def _save_png(self, n: int, frame: Any) -> str | None:
        if frame is None:
            return None
        buf = io.BytesIO()
        frame.convert("RGB").save(buf, format="PNG", optimize=True)
        return self.trace.save_png(n, "before", buf.getvalue())

    def _pause(self, why: str) -> None:
        self.pauses += 1
        if self.paused != why:
            self.paused = why
            self.on_change()

    def _resume(self) -> None:
        if self.paused is not None:
            self.paused = None
            self.on_change()

    def _note(self, text: str) -> None:
        if text not in self.notes:
            self.notes.append(text)


# ---- sessions: start, finish, cancel -------------------------------------------------------------


@dataclass
class Session:
    id: str
    avd: str
    goal: str
    app: str | None
    recorder: Recorder
    status: str = "recording"  # recording → compiling → replaying → saved | failed; or discarded
    detail: str = ""
    started: float = field(default_factory=time.time)
    routine: str | None = None
    version: int | None = None
    steps: int = 0
    report: dict[str, Any] = field(default_factory=dict)
    replay: dict[str, Any] | None = None
    replay_task: str | None = None
    cost_usd: float = 0.0
    trace_dir: str = ""

    def view(self) -> dict[str, Any]:
        out = {"id": self.id, "device": self.avd, "goal": self.goal, "app": self.app, "status": self.status, "detail": self.detail,
               "started": self.started, "routine": self.routine, "version": self.version, "steps": self.steps,
               "notes": self.recorder.notes, "replay": self.replay, "replay_task": self.replay_task, "cost_usd": round(self.cost_usd, 4),
               "warnings": self.report.get("warnings", []), "dropped": self.report.get("dropped", [])}
        if self.status == "recording":
            out.update(self.recorder.state())
        return out


class Teacher:
    """Teach sessions, one per phone. A session holds the phone's run lock from start to the end of its replay, so no
    task starts on the phone in between; while recording, the phone is in a takeover (devices.py) like any other."""

    def __init__(self, pool: Any, tasks: Any, bus: Any, routines: Any, adapter: Any, runner: Any = None, *, root: Path = RUNS,
                 screenshots: bool = True) -> None:
        self.pool, self.tasks, self.bus, self.routines, self.adapter, self.runner = pool, tasks, bus, routines, adapter, runner
        self.root, self.screenshots = root, screenshots
        self.sessions: dict[str, Session] = {}  # device → its latest session
        self.jobs: dict[str, asyncio.Task] = {}  # device → the compile and replay after Finish
        self.idlers: dict[str, asyncio.Task] = {}  # device → the watch that cancels a forgotten recording

    def _sweep(self) -> None:
        """A recording the API stopped in the middle of (no run.json, untouched for an hour) is never kept."""
        live = {s.recorder.trace.dir for s in self.sessions.values()}
        for d in self.root.glob("teach-*"):
            try:
                if d.is_dir() and d not in live and not (d / "run.json").exists() and time.time() - d.stat().st_mtime > 3600:
                    shutil.rmtree(d, ignore_errors=True)
            except OSError:
                continue

    def status(self, avd: str) -> dict[str, Any] | None:
        s = self.sessions.get(avd)
        return s.view() if s else None

    def _changed(self, s: Session) -> None:
        lease = self.pool.leases.get(s.avd)
        if lease is not None:
            lease.teach = {"id": s.id, "goal": s.goal, "status": s.status, **(s.recorder.state() if s.status == "recording" else {}),
                           **({"routine": s.routine} if s.routine else {})}
        self.bus.publish("teach", teach=s.view())

    async def start(self, avd: str, goal: str, app: str | None = None) -> dict[str, Any]:
        goal = " ".join((goal or "").split())
        if not goal:
            raise TeachError(400, "say what you're going to show (the goal, in your words)")
        lease = self.pool.leases.get(avd)
        if lease is None:
            raise TeachError(404, f"no phone {avd}")
        if (s := self.sessions.get(avd)) is not None and s.status in ("recording", "compiling", "replaying"):
            raise TeachError(409, "this phone is already being taught")
        if lease.task_id or lease.run_lock.locked():
            raise TeachError(409, "Envoy is using this phone: wait for its task to end, or stop it")
        try:
            device = await self.pool.device(avd)
        except Exception as e:  # noqa: BLE001
            raise TeachError(409, str(e)) from e
        if lease.task_id or lease.run_lock.locked():  # taken while the phone was being connected
            raise TeachError(409, "Envoy is using this phone: wait for its task to end, or stop it")
        await lease.run_lock.acquire()
        try:
            self._sweep()
            if app is None and self.runner is not None:
                try:
                    from api.runner import app_for
                    app = app_for(goal, self.runner._learned_names())
                except Exception:  # noqa: BLE001 - you open the app yourself
                    app = None
            if app:  # start where an agent run starts: the app, freshly opened
                try:
                    await device.launch(app, fresh=True)
                    await device.wait_until_settled()
                except Exception:  # noqa: BLE001 - you open it yourself
                    pass
            tid = new_id("teach")
            holder: dict[str, Session] = {}
            rec = Recorder(tid, goal, device, root=self.root, screenshots=self.screenshots,
                           on_change=lambda: holder.get("s") and self._changed(holder["s"]))
            s = holder["s"] = Session(tid, avd, goal, app, rec, trace_dir=str(rec.trace.dir))
            self.sessions[avd] = s
            self.pool.recorders[avd] = rec
            self.pool.take_over(avd, f"teaching: {goal}", by="teach")
            self._changed(s)
            self.idlers[avd] = asyncio.get_running_loop().create_task(self._idle(s))
            return s.view()
        except BaseException:
            self.pool.recorders.pop(avd, None)
            lease.run_lock.release()
            raise

    async def _idle(self, s: Session) -> None:
        """Cancel a recording nobody is using (the tab was closed, you walked away), so tasks get the phone back."""
        while s.status == "recording":
            await asyncio.sleep(IDLE_CHECK_S)
            if s.status == "recording" and time.time() - s.recorder.last_input > IDLE_S and self.sessions.get(s.avd) is s:
                await self.cancel(s.avd)
                s.detail = f"Nothing happened for {IDLE_S // 60} minutes, so the recording was stopped and deleted."
                self._changed(s)

    def _recording(self, avd: str) -> Session:
        s = self.sessions.get(avd)
        if s is None or s.status != "recording":
            raise TeachError(409, "this phone isn't being taught")
        return s

    async def cancel(self, avd: str) -> dict[str, Any]:
        s = self._recording(avd)
        self.pool.recorders.pop(avd, None)
        try:
            await s.recorder.discard()
        finally:
            s.status, s.detail = "discarded", "You cancelled, so what you did was deleted."
            self._end(s)
        return s.view()

    async def finish(self, avd: str, ok: bool, answer: str = "") -> dict[str, Any]:
        """`ok`: you say the task worked; without it nothing is kept. With it the recording ends, the phone is handed
        back, and the compile and the replay run in the background (`status` follows them)."""
        s = self._recording(avd)
        if not ok:
            self.pool.recorders.pop(avd, None)
            try:
                await s.recorder.discard()
            finally:
                s.status, s.detail = "discarded", "You said it didn't work, so what you did was deleted."
                self._end(s)
            return s.view()
        self.pool.recorders.pop(avd, None)
        try:
            trace = await s.recorder.finish((answer or "").strip())
        except Exception as e:  # noqa: BLE001
            s.status, s.detail = "failed", f"recording: {type(e).__name__}: {e}"[:300]
            self._end(s)
            return s.view()
        s.steps, s.trace_dir = s.recorder.n, str(trace)
        if self.pool.leases[avd].user_control:
            self.pool.hand_back(avd, by="teach")
        if s.recorder.n == 0:
            shutil.rmtree(trace, ignore_errors=True)
            s.status, s.detail = "failed", "Nothing was recorded: no step happened outside sign-in screens and the home screen."
            self._end(s)
            return s.view()
        s.status, s.detail = "compiling", "turning what you showed into a routine"
        self._changed(s)
        self.jobs[avd] = asyncio.get_running_loop().create_task(self._learn(s, trace))
        return s.view()

    def _end(self, s: Session) -> None:
        lease = self.pool.leases[s.avd]
        if lease.user_control:
            self.pool.hand_back(s.avd, by="teach")
        if lease.run_lock.locked():
            lease.run_lock.release()
        self._changed(s)
        lease.teach = None  # the phone is free; the result stays in `status`

    async def _learn(self, s: Session, trace: Path) -> None:
        from routines.compiler import NotCompilable, compile_trace
        try:
            try:
                routine, report = await compile_trace(trace, adapter=self.adapter, confirmed=True)
            except NotCompilable as e:
                s.status, s.detail = "failed", f"can't become a routine: {e}"
                return
            s.cost_usd += report.cost_at_standard_usd
            s.report = {"warnings": report.warnings, "dropped": [list(d) for d in report.dropped], "kept": report.kept,
                        "model": report.model, "cost_usd": report.cost_at_standard_usd}
            s.routine = routine.routine
            (trace / "routine.yaml").write_text(_dump(routine))
            s.status, s.detail = "replaying", f"running {routine.routine} once, on its own, to show it works"
            self._changed(s)
            out = await self._replay(s, routine)
            s.replay = {"status": out.status, "detail": out.detail, "duration_s": out.duration_s, "model_calls": out.model_calls,
                        "outputs": out.outputs, "steps": [{"id": st.id, "status": st.status, "detail": st.detail} for st in out.steps]}
            if out.status != "done":
                failed = next((st for st in out.steps if st.status not in ("done", "skipped")), None)
                s.status = "failed"
                s.detail = (f"the replay stopped at {failed.id}: {failed.detail or out.detail}" if failed else f"the replay {out.status}: {out.detail}")[:400]
                return
            inputs = {k: v.example or "" for k, v in routine.inputs.items()}
            # A name already in the library goes on trial, so a showing never replaces a tuned routine untested (#43).
            added = self.routines.add_trial(routine, verification={"by": "teach", "from": s.id, "cases": [
                {"case": "replay", "passed": True, "inputs": inputs, "duration_s": out.duration_s, "status": out.status}]})
            s.version, s.status = added.version, "saved"
            s.detail = f"Saved as {added.routine} (v{added.version}). It ran once on its own, with no model, in {out.duration_s:.0f} s."
            if added.status == "trial":
                s.detail += (f" v{added.parent_version} stays in use until v{added.version} runs a real task on its own; "
                             "if it can't, it's set aside.")
        except asyncio.CancelledError:
            s.status, s.detail = "failed", "stopped"
            raise
        except Exception as e:  # noqa: BLE001 - reported, never crashes the server
            s.status, s.detail = "failed", f"{type(e).__name__}: {e}"[:400]
        finally:
            self._end(s)

    async def _replay(self, s: Session, routine: Any) -> Any:
        """One strict replay on the same phone (no repair, no agent), as a task you can watch and approve steps of."""
        from api.approvals import WebApprover
        from policy.approval_rules import ApprovalRules
        from routines.executor import ExecConfig, RoutineExecutor
        avd = s.avd
        lease = self.pool.leases[avd]
        device = await self.pool.device(avd)
        inputs = {k: v.example or "" for k, v in routine.inputs.items()}
        task = self.tasks.create(s.goal, "teach", kind="routine", routine=routine.routine, inputs=inputs, app=routine.app, device=avd)
        tid = task["id"]
        s.replay_task = tid
        set_ = self.runner._set if self.runner is not None else (lambda t, **f: self.tasks.update(t, **f))
        set_(tid, status="running", detail="replaying what you showed, once, with no model")
        trace_id = f"{tid}-replay"
        if self.runner is not None:
            self.runner.trace_task[trace_id] = tid
            self.runner.devices[tid] = device
        approver = WebApprover(self.tasks, self.bus, asyncio.get_running_loop(), tid, phone=lambda: device,
                               on_wait=lambda aid: set_(tid, status="waiting_approval" if aid else "running", waiting_for=aid),
                               rules=lambda: ApprovalRules.from_dict(self.tasks.setting("approval_rules")))
        if self.runner is not None:
            self.runner.approvers[tid] = approver
        lease.task_id = tid
        skylark = routine.app == "com.skylark.air"
        try:
            ex = RoutineExecutor(self.pool.gated(avd, device), adapter=self.adapter, approver=approver,
                                 config=ExecConfig(data_scope="test_app" if skylark else "real", contributor=skylark, patch_screenshots=False))
            out = await ex.run(routine, inputs, task_id=trace_id, launch="fresh", allow_repair=False, allow_agent=False)
            s.cost_usd += out.cost_at_standard_usd
            set_(tid, status="done" if out.status == "done" else "failed", result=out.detail, detail=out.detail,
                 model_calls=out.model_calls, cost_usd=round(out.cost_at_standard_usd, 4), waiting_for=None)
            self.bus.publish("task_finished", task_id=tid, duration_s=out.duration_s)
            return out
        except BaseException:
            set_(tid, status="failed", detail="the replay stopped", waiting_for=None)
            raise
        finally:
            lease.task_id = None
            if self.runner is not None:
                self.runner.approvers.pop(tid, None)
                self.runner.devices.pop(tid, None)


class TeachError(Exception):
    def __init__(self, code: int, detail: str) -> None:
        super().__init__(detail)
        self.code, self.detail = code, detail


def _dump(routine: Any) -> str:
    from routines.model import dump_yaml
    return dump_yaml(routine)
