"""Routine compiler: one successful agent trace → an app routine (design doc, App routines › Compiling).

1. Confirm success: only runs that ended `done` with a passed success check (or that the user
   confirmed) are compiled. A taught trace (api/teach.py) is your own demonstration in the same
   format, confirmed by you; its routine is marked `source: taught`.
2. Clean up: drop pop-up dismissals (the shared handler covers them), looks, rejected or failed
   actions, steps with no visible effect, and back-tracks (a stretch of steps that ends on exactly
   the screen it started from). Recorded scrolls before a list tap become `scroll_until`.
3. Generalize: Muse Wonder names the inputs and decides what stays fixed (Spark at high effort if
   Wonder fails). Values that equal an input become {{slots}} in typed text, locators and checks;
   a list row chosen because it shows an input becomes an input-based locator (`text_has`); booking
   data that is not an input is removed so the routine doesn't expect it. A locator that then fits several look-alikes on
   its recorded screen is told apart by the inputs it shows, else by its place in its list, else reported (`disambiguate`).
4. Add checks: each step's before and after trees are diffed (routines/checks.py).
5. Verify by replay (`verify`): replay from a reset with the same inputs and with a second set of
   inputs; only routines that pass go into the library (routines/store.py).
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from devices.types import Element, ScreenState
from models.adapter import ModelAdapter, ModelResult
from models.prompts import COMPILE_INSTRUCTIONS, compile_input
from models.schemas import CompiledRoutine
from routines import checks as chk
from routines import locators
from routines import screen_read
from routines.model import FIELD, Check, Extract, InputSpec, Locator, Routine, Step, StepAction, has_slot, render_str, slot_names
from routines.screens import contains_value, fold, jaccard, load_tree, norm, parts_of, short_id, signature_keys, usable_id
from routines.visual import encode as encode_png

_DIGIT = re.compile(r"\d")
_SLUG = re.compile(r"[^a-z0-9]+")
_IDENT = re.compile(r"[a-z]+(_[a-z]+)+")
_DATA_SEGMENT = re.compile(r"^(?=.*\d)[A-Za-z0-9]+$|^[A-Z0-9]{5,}$")
_POPUP_TITLE = re.compile(r"^PopupWindow:[0-9a-f]+$")


class NotCompilable(ValueError):
    """The run did not reach its goal (or can't be confirmed), so it must not become a routine."""


@dataclass
class TStep:
    """One trace step, cleaned up: what was done to which element, with both screens."""

    n: int
    kind: str  # tap, long_press, type, scroll, scroll_until, back, launch, wait
    before: ScreenState
    after: ScreenState
    target: Element | None = None
    typed: str | None = None
    submit: bool = False
    direction: str | None = None
    container: Element | None = None
    reason: str = ""
    expected: str = ""
    risk: str = "read"
    scrolls: int = 0
    swipe: tuple[int, int, int, int] | None = None  # recorded swipe start and end, device pixels
    vision: dict[str, Any] | None = None  # a tap_point's target as the agent saw it (Phase 6): description, box, crop
    trace_dir: Path | None = None
    moved: str = ""  # why it comes later than in the trace (typing done during a round trip)


# Screens an app shows once (onboarding, a welcome tour, "what's new", a promo): a step that only gets past one is kept
# optional, since on the next run the screen is gone and the routine would wait for it forever (Play Store's interests
# onboarding, Calendar's welcome pages in the real-app test set).
_ONE_TIME_LABEL = re.compile(r"^(skip|skip for now|not now|no,? thanks|maybe later|later|got it|dismiss|close|i'?ll do (it|this) later|"
                             r"continue without.*|use without.*)$", re.I)
_ONE_TIME_INTENT = re.compile(r"onboard|welcome|intro\b|tutorial|first[ _-]?(run|launch|time)|what'?s[ _-]?new|dismiss|promo|upsell|"
                              r"premium|offer\b", re.I)


def _optional_why(s: "TStep", sid: str, intent: str) -> str | None:
    """Why a step may be skipped at run time, or None: a one-time screen, or closing the keyboard."""
    if s.risk == "irreversible" or s.kind not in ("tap", "back"):
        return None
    if re.search(r"keyboard", f"{sid} {intent}", re.I) and not (s.kind == "back" and s.before.activity != s.after.activity):
        # The routine moves a target out from under the keyboard itself, so closing it is never needed; done blind it
        # can hurt (Back with the keyboard already gone leaves the screen; its keys are not part of the screen). A Back that
        # left the screen did more than that, whatever the agent called it: in Markor it leaves the editor, saving the note.
        return "closes the keyboard"
    if s.kind == "back":  # Back that closes an upsell or a tour (Wonder's own words for the step say so)
        return "one-time screen" if _ONE_TIME_INTENT.search(f"{sid} {intent}") else None
    if s.target is None:
        return None
    one = _ONE_TIME_LABEL.match((s.target.label or s.target.desc or "").strip()) or _ONE_TIME_INTENT.search(f"{sid} {intent}")
    return "one-time screen" if one else None


@dataclass
class CompileReport:
    task_id: str
    goal: str
    kept: list[int] = field(default_factory=list)
    dropped: list[tuple[int, str]] = field(default_factory=list)
    model: str = ""
    model_calls: int = 0
    cost_usd: float = 0.0
    cost_at_standard_usd: float = 0.0
    latency_s: float = 0.0
    warnings: list[str] = field(default_factory=list)
    wonder: dict[str, Any] | None = None
    # Steps whose target still matches several elements on the recorded screen (nothing in the run tells them apart): on a
    # rerun they fall back on the ladder. {"step": id, "trace_step": n, "matches": k, "locator": ...}
    ambiguous: list[dict[str, Any]] = field(default_factory=list)


# ---- 1 + 2: load and clean up -----------------------------------------------------------------


def _app_text(s: ScreenState | None) -> bool:
    return s is not None and any(e.label.strip() and not e.status_bar for e in s.numbered)


def screen_only(trace_dir: Path, run: dict, records: list[dict] | None = None) -> bool:
    """An unverified run whose answer couldn't be checked only because its last screen has no accessibility tree (a page
    Chrome draws without one): the screenshot holds the answer. The compiler then reads it from the recorded screenshot
    and keeps it only if that read passes screen_read.accept, the check every rerun passes too."""
    check = run.get("check") or {}
    if run.get("status") != "done_unverified" or "visible on the current screen" not in (check.get("detail") or ""):
        return False
    if records is None:
        records = [json.loads(line) for line in (trace_dir / "steps.jsonl").read_text().splitlines() if line.strip()]
    return not _app_text(_done_screen(trace_dir, records) or _final_screen(trace_dir, records)) and _last_png(trace_dir) is not None


def _last_png(trace_dir: Path) -> Path | None:
    pngs = sorted((trace_dir / "screens").glob("*_before.png"))
    return pngs[-1] if pngs else None


def load_trace(trace_dir: Path, *, confirmed: bool = False) -> tuple[dict, list[dict]]:
    run = json.loads((trace_dir / "run.json").read_text())
    check = run.get("check") or {}
    if not confirmed and not (run.get("status") == "done" and check.get("passed")) and not screen_only(trace_dir, run):
        raise NotCompilable(f"run ended {run.get('status')!r} with check {check.get('detail')!r}; only verified runs are compiled")
    records = [json.loads(line) for line in (trace_dir / "steps.jsonl").read_text().splitlines() if line.strip()]
    return run, records


def _toward_goal(stretch: list[TStep], goal: str) -> bool:
    """Whether a stretch made an element of a screen it passes through show, when seen again, something the goal asks for
    that it didn't show before (TikTok's editor: "Music · Add sound", then "Music · golden hour")."""
    first: dict[tuple[str, str], str] = {}  # (activity, ID) -> its label the first time the stretch shows it
    for screen in [stretch[0].before, *(t.after for t in stretch)]:
        for e in screen.numbered:
            if e.in_list or e.status_bar or not e.label or not usable_id(e.resource_id):
                continue
            old = first.setdefault((screen.activity, short_id(e.resource_id)), e.label)
            if e.label != old and any(len(p) >= 3 and contains_value(goal, p) and not contains_value(old, p) for p in parts_of(e.label)):
                return True
    return False


def _moved_typing(stretch: list[TStep], later: list[TStep]) -> dict[int, list[TStep]] | None:
    """The typing a round trip did, each with the steps after it on the same screen (closing the keyboard), keyed by the
    later step whose after-screen is that screen again: it is done there instead. None if the stretch has another effect
    (an irreversible step, a toggle), a screen it typed on doesn't come back, or the stretch left the typed screen's
    activity (a document's editor, whose leaving saves it: then the round trip was the save)."""
    moved: dict[int, list[TStep]] = {}
    k = 0
    while k < len(stretch):
        t = stretch[k]
        if t.risk == "irreversible" or (t.target is not None and t.target.checkable):
            return None
        k += 1
        if t.kind != "type":
            continue
        group, screen = [t], {t.before.signature, t.after.signature}
        while k < len(stretch) and stretch[k].kind != "type" and {stretch[k].before.signature, stretch[k].after.signature} <= screen:
            group.append(stretch[k])
            k += 1
        if k < len(stretch) and stretch[k].after.activity != t.before.activity:
            return None  # leaving its activity is what kept the typing (Markor saves a note as you leave its editor)
        q = next((q for q, x in enumerate(later) if x.after.signature == t.before.signature), None)
        if q is None:
            return None
        moved.setdefault(q, []).extend(group)
    return moved


def clean(trace_dir: Path, records: list[dict], goal: str = "") -> tuple[list[TStep], list[tuple[int, str]]]:
    steps: list[TStep] = []
    dropped: list[tuple[int, str]] = []
    app = ""
    for r in records:
        n = r.get("step", 0)
        k = r.get("kind")
        if k == "popup":
            dropped.append((n, f"pop-up ({r.get('handler')}): the shared handler covers it"))
            continue
        if k != "action":
            continue
        act = (r.get("decision") or {}).get("action", {}).get("type")
        dev = r.get("device_action")
        if dev is None:
            if act not in ("done", "fail", "handoff", "ask_user"):
                dropped.append((n, f"{act}: not a device action" + (f" ({r['error']})" if r.get("error") else "")))
            continue
        if r.get("approval") and not r["approval"].get("approved"):
            dropped.append((n, "declined at the approval gate"))
            continue
        if not (r.get("result") or {}).get("ok"):
            dropped.append((n, f"action failed: {(r.get('result') or {}).get('error')}"))
            continue
        if not r.get("changed", True) and dev["kind"] != "scroll":
            dropped.append((n, "no visible change (a retry or a dead tap)"))
            continue
        before = load_tree(trace_dir / r["tree_before"])
        after = load_tree(trace_dir / r["tree_after"])
        for screen in (before, after):
            # Traces recorded before the device told an app's popup menu from the app: the menu's window was taken for
            # the app ("PopupWindow:51b096d"), and every check written from it failed. The app is the one before it.
            if _POPUP_TITLE.match(screen.package) and app:
                screen.package = app
            elif screen.package:
                app = screen.package
        target = None
        if r.get("target") and r["target"].get("index") is not None and r["target"]["index"] < len(before.elements):
            target = before.elements[r["target"]["index"]]
        container = None
        if dev["kind"] == "scroll" and dev.get("element"):
            container = target
            target = None
        if dev["kind"] == "scroll" and not r.get("changed", True):
            dropped.append((n, "scroll with no new content (end of list)"))
            continue
        steps.append(TStep(
            n=n, kind=dev["kind"], before=before, after=after, target=target, typed=dev.get("text"), submit=dev.get("submit", False),
            direction=dev.get("direction"), container=container, reason=(r.get("decision") or {}).get("reason", ""),
            swipe=(dev["x"], dev["y"], dev["x2"], dev["y2"]) if dev["kind"] == "swipe" and dev.get("x") is not None else None,
            vision=r.get("vision") if dev["kind"] == "tap_point" else None, trace_dir=trace_dir,
            expected=(r.get("decision") or {}).get("expected_result", ""), risk=(r.get("risk") or {}).get("level", "read"),
        ))

    # Back-tracks: a stretch of navigation that ends on exactly the screen it started from (same labels and the
    # same layout) changed nothing that lasts. A stretch with an effect (an approved or irreversible action,
    # typing, a toggle) is never a back-track, even if it ends where it began: checking in and returning to
    # Home looks like a round trip, but the trip is checked in.
    def effectful(t: TStep) -> bool:
        return t.risk == "irreversible" or t.kind == "type" or (t.target is not None and t.target.checkable)

    # Two exceptions (Nov 2, TikTok's sound: the agent's first try left no sound; it went back from the post screen, added
    # it, and came back): a stretch on whose way a screen came to show what the goal asks for is a correction, not a round
    # trip; and typing in a round trip (the caption, typed before the correction) is done where its screen comes back.
    changed = True
    while changed:
        changed = False
        for i in range(len(steps)):
            for j in range(len(steps) - 1, i, -1):
                a, b = steps[i].before, steps[j].after
                if not (a.signature == b.signature and _layout_key(a) == _layout_key(b)) or _toward_goal(steps[i:j + 1], goal):
                    continue
                moved = _moved_typing(steps[i:j + 1], steps[j + 1:]) if any(effectful(t) for t in steps[i:j + 1]) else {}
                if moved is None:
                    continue
                kept = {t.n for group in moved.values() for t in group}
                for s in steps[i:j + 1]:
                    if s.n not in kept:
                        dropped.append((s.n, f"back-track: steps {steps[i].n}–{steps[j].n} returned to the same screen"))
                later = []
                for q, t in enumerate(steps[j + 1:]):
                    later.append(t)
                    for m in moved.get(q, []):
                        m.moved = f"moved after trace step {t.n}: typed during the round trip {steps[i].n}–{steps[j].n}"
                        later.append(m)
                steps[i:] = later
                changed = True
                break
            if changed:
                break

    # Recorded scrolls followed by a tap on a list element become one scroll_until step.
    out: list[TStep] = []
    i = 0
    while i < len(steps):
        s = steps[i]
        if s.kind == "scroll":
            j = i
            while j < len(steps) and steps[j].kind == "scroll":
                j += 1
            nxt = steps[j] if j < len(steps) else None
            if nxt is not None and nxt.target is not None and nxt.target.in_list:
                out.append(TStep(n=s.n, kind="scroll_until", before=s.before, after=steps[j - 1].after, target=nxt.target,
                                 direction=s.direction or "down", container=s.container, reason=f"scroll to: {nxt.reason}",
                                 scrolls=j - i))
                out[-1].before_for_target = nxt.before  # type: ignore[attr-defined]
            else:
                # Trailing scrolls (an answer further down a list): kept as scroll_until on the answer, set later.
                out.append(TStep(n=s.n, kind="scroll_until", before=s.before, after=steps[j - 1].after, target=None,
                                 direction=s.direction or "down", container=s.container, reason=s.reason, scrolls=j - i))
            i = j
            continue
        out.append(s)
        i += 1
    return out, dropped


# ---- 1b: a run with nothing to do -------------------------------------------------------------
# A run can succeed on an instance where the task asked for nothing: no recipe used that ingredient, so it deleted nothing;
# brightness was already at its maximum. A routine compiled from it learns "look, do nothing" and passes its own checks on
# every other instance while doing nothing there either. Verbs are matched where a clause starts ("Delete the …", ", then
# send …"), so "the following text" or "in order" in a goal isn't taken for one.
_CLAUSE = r"(?:^|[.;:,!?]\s*|\b(?:and|then|please|also)\s+)"
_IRREVERSIBLE_GOAL = re.compile(_CLAUSE + r"(delete|remove|erase|send|text|reply|share|forward|pay|buy|purchase|submit|cancel)\b", re.I)
_STATE_GOAL = re.compile(_CLAUSE + r"(?:(turn|switch|set)\b[^.;!?]*?\b(?:on|off|max(?:imum)?|min(?:imum)?|highest|lowest)\b"
                         r"|(enable|disable|activate|deactivate|mute|unmute)\b)", re.I)
_ALREADY = re.compile(r"\balready\b", re.I)


def _effect(s: TStep) -> bool:
    """A step that changes something beyond which screen is shown: typing, a drag (a slider), an irreversible action, or a
    switch or check box that flips (tapped itself, or through its row: "Use Bluetooth")."""
    if s.risk == "irreversible" or s.kind in ("type", "swipe", "tap_point", "long_press") or (s.target is not None and s.target.checkable):
        return True
    if s.before.activity != s.after.activity:
        return False  # another screen's switches are other switches (Settings' "Internet" page under "Network & internet")
    before = {(e.resource_id, e.label, e.bounds): e.checked for e in s.before.numbered if e.checkable}
    return any(e.checkable and before.get((e.resource_id, e.label, e.bounds), e.checked) != e.checked for e in s.after.numbered)


def degenerate(goal: str, answer: str, steps: list[TStep], records: list[dict]) -> str | None:
    """Why the run can't teach a routine because its instance asked for nothing (None: it can)."""
    approved = any((r.get("approval") or {}).get("approved") for r in records if r.get("kind") == "action")
    if (m := _IRREVERSIBLE_GOAL.search(goal or "")) and not approved and not any(s.risk == "irreversible" for s in steps):
        return (f"the goal asks to {m.group(1).lower()}, but the run took no irreversible step: on this instance there was nothing "
                f"to {m.group(1).lower()}, and a routine learned from it would do nothing on any other")
    if any(_effect(s) for s in steps):
        return None
    if _ALREADY.search(answer or ""):
        return f"the run changed nothing (its answer: {answer[:80]!r}): a routine learned from it would change nothing either"
    if (m := _STATE_GOAL.search(goal or "")) is not None:
        return (f"the goal asks to {(m.group(1) or m.group(2)).lower()} something, but the run changed nothing (no switch, slider, "
                f"typing or irreversible step): it was already so on this instance")
    return None


def _layout_key(s: ScreenState) -> str:
    """Labels, states and positions of the listed elements: a bottom sheet dragged up has the same labels but not the same bounds.
    Enabled states too: leaving an editor and opening the file again saves it (Markor's Save and Undo go from enabled to
    disabled), so that round trip is the step that saves the text, not a back-track."""
    return "\n".join(f"{e.label}|{e.kind}|{e.checked}|{e.enabled}|{e.bounds}" for e in s.numbered)


# ---- 3: generalize ----------------------------------------------------------------------------


def _title(s: ScreenState) -> str:
    t = next((e.label for e in s.numbered if e.resource_id.endswith("title") and e.label), "")
    return t or next((e.label for e in s.numbered if e.kind == "Text" and e.label), "")


def describe_steps(steps: list[TStep]) -> str:
    lines = []
    for i, s in enumerate(steps, 1):
        tgt = ""
        if s.target is not None:
            e = s.target
            tgt = f' {e.kind} "{e.label}"' + (f" (id: {short_id(e.resource_id)})" if e.resource_id else "") + (" [in a list]" if e.in_list else "")
        extra = f' typed "{s.typed}"' if s.kind == "type" else ""
        if s.kind == "scroll_until":
            extra = f" ({s.scrolls} scroll(s) {s.direction})"
        # A taught trace (api/teach.py) has no reasons: a person did the step.
        why = f"Agent's reason: {s.reason}" if s.reason else "Done by the user, who showed the task."
        lines.append(f"{i}. {s.kind}{tgt}{extra} — on screen {_title(s.before)!r} → {_title(s.after)!r}. {why}")
    return "\n".join(lines)


def _call_compiler(adapter: ModelAdapter, content: str, task_id: str, effort: str | None) -> ModelResult:
    try:
        return adapter.call("compile", content, instructions=COMPILE_INSTRUCTIONS, task_id=task_id,
                            **({"effort": effort} if effort else {}))
    except Exception as e:  # noqa: BLE001 - Wonder is a preview model; fall back to Spark at high effort
        res = adapter.call("compile", content, instructions=COMPILE_INSTRUCTIONS, task_id=task_id, model="muse-spark-1.3", effort="high")
        res.text = f"(Wonder failed: {type(e).__name__}) " + res.text
        return res


def _replace_value(s: str, value: str, repl: str) -> str:
    """Replace `value` on word boundaries, ignoring case and accents ("Caffe Latte" in "Grande Caffè Latte")."""
    pattern = rf"(?<![0-9A-Za-z]){re.escape(fold(value))}(?![0-9A-Za-z])"
    folded = fold(s)
    if len(folded) != len(s):  # decomposed input: fall back to an exact (case-insensitive) match
        return re.sub(rf"(?<![0-9A-Za-z]){re.escape(value)}(?![0-9A-Za-z])", repl, s, flags=re.I)
    out, last = [], 0
    for m in re.finditer(pattern, folded, flags=re.I):
        out += [s[last:m.start()], repl]
        last = m.end()
    return "".join(out) + s[last:]


def bind_inputs(s: str | None, examples: dict[str, str]) -> str | None:
    """Replace every input's example value in `s` with its {{slot}} (longest values first)."""
    if not s:
        return s
    for name, value in sorted(examples.items(), key=lambda kv: -len(kv[1])):
        if value and contains_value(s, value):
            s = _replace_value(s, value, "{{" + name + "}}")
    return s


def _data_free(s: str | None, data_values: list[str]) -> bool:
    """No booking data left outside {{slots}}: no listed data value and no digits."""
    if not s:
        return True
    bare = re.sub(r"\{\{[^}]+\}\}", "", s)
    if _DIGIT.search(bare):
        return False
    return not any(v and contains_value(bare, v) for v in data_values)


def _glob_id(rid: str | None, examples: dict[str, str], data_values: list[str]) -> str | None:
    """Template input values in a resource ID (seat_12C → seat_{{seat}}); booking data becomes * (trip_row_*)."""
    if not rid:
        return rid
    out = rid
    for name, value in examples.items():
        if value and value.replace(" ", "") and value.replace(" ", "").casefold() in out.casefold():
            out = re.sub(re.escape(value.replace(" ", "")), "{{" + name + "}}", out, flags=re.I)
    for v in data_values:
        vv = v.replace(" ", "")
        if len(vv) >= 2 and vv.casefold() in out.casefold() and "{{" not in vv:
            out = re.sub(re.escape(vv), "*", out, flags=re.I)
    return out


def _glob_data_segments(rid: str | None) -> str | None:
    """trip_row_PT4R8Z → trip_row_*: in list rows and input-chosen elements, ID parts that look like data
    (codes with digits, long upper-case codes) differ per item, so they can't be part of the locator."""
    if not rid or "{{" in rid:
        return rid
    parts = rid.split("_")
    if len(parts) < 2:
        return rid
    return "_".join("*" if _DATA_SEGMENT.match(p) else p for p in parts)


def generalize_locator(loc: Locator, examples: dict[str, str], data_values: list[str], fixed_text: str | None,
                       choice_input: str | None) -> Locator:
    upd: dict[str, Any] = {"resource_id": _glob_id(loc.resource_id, examples, data_values),
                           "hint": None if any(v and contains_value(loc.hint, v) for v in data_values) else loc.hint}
    label = loc.text or ""

    def shows(v: str) -> bool:
        return contains_value(label, v) or contains_value(loc.desc, v)

    bound = choice_input if choice_input in examples else next((n for n, v in examples.items() if v and shows(v)), None)
    # An element that shows nothing of the input itself (a row's delete icon) is chosen by the row that shows it.
    row_bound = None
    if loc.row and (bound is None or not shows(examples[bound])):
        row_bound = next((n for n in [*([bound] if bound else []), *examples] if examples.get(n)
                          and any(contains_value(t, examples[n]) for t in loc.row)), None)
        if row_bound is not None:
            bound = None
    if bound or loc.in_list or row_bound:
        upd["resource_id"] = _glob_data_segments(upd["resource_id"])
    if bound:
        upd.update(text_has="{{" + bound + "}}", siblings=[], position=None, desc=None, row=[],
                   parent=loc.parent if _data_free(loc.parent, data_values) else None,
                   text=fixed_text if fixed_text and _data_free(fixed_text, data_values) else None)
    else:
        upd["row_has"] = "{{" + row_bound + "}}" if row_bound else None
        upd["row"] = [t for t in loc.row if _data_free(t, data_values) and not any(v and contains_value(t, v) for v in examples.values())]
        text = bind_inputs(label, examples)
        if not _data_free(text, data_values):
            text = fixed_text if fixed_text and _data_free(fixed_text, data_values) else None
        upd["text"] = text
        upd["desc"] = loc.desc if _data_free(loc.desc, data_values) else None
        upd["parent"] = loc.parent if _data_free(loc.parent, data_values) else None
        upd["siblings"] = [s for s in loc.siblings if _data_free(s, data_values)]
    return loc.model_copy(update=upd)


_WHOLE_SLOT = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
_ORDINAL = ("first", "second", "third", "fourth", "fifth")


def _input_texts(e: Element, examples: dict[str, str], data_values: list[str]) -> list[str]:
    """What of an input the element shows, as `text_has` values, most specific first: the stretch from its first input to
    its last ("{{song_title}} by {{song_artist}}" in "Select track golden hour by JVKE,3:29"), then each input alone."""
    out: list[str] = []
    examples = {k: v for k, v in examples.items() if ":" not in k and v}  # whole inputs, not a date's parts
    for label in dict.fromkeys(t for t in (e.full_label or e.label, e.desc) if t):
        bound = bind_inputs(label, examples) or ""
        slots = [m for m in _WHOLE_SLOT.finditer(bound) if m.group(1) in examples]
        if not slots:
            continue
        span = bound[slots[0].start():slots[-1].end()]
        between = _WHOLE_SLOT.sub("", span)
        if len(slots) > 1 and len(between) <= 24 and _data_free(span, data_values):
            out.append(span)
        out += [m.group(0) for m in sorted(slots, key=lambda m: -len(examples[m.group(1)]))]
    return list(dict.fromkeys(out))


def disambiguate(loc: Locator, target: Element, screen: ScreenState, examples: dict[str, str], data_values: list[str], *,
                 scrolled: bool = False) -> tuple[Locator, list[Check], str | None, int]:
    """A step's locator made to pick exactly the element the run acted on, when on the recorded screen it matches several
    look-alikes (every gallery thumbnail reads "Video thumbnail created on <date>"; every track row of a search has a
    catalogue ID and, once its words are cut out as data, nothing else). A locator that already picks it is returned as is.

    In order: (a) the input the element shows, as `text_has` (the track "{{song_title}} by {{song_artist}}"); (b) one of a
    uniform list or grid that starts with a fixed item (the gallery's camera tile): its place among the look-alikes (`nth`),
    with a before-check on that item (the list is shown, at its start), so a scrolled gallery matches nothing, not another clip.
    Not for a target reached by scrolling, whose place depends on how far the list went. (c) otherwise unchanged, and
    reported ambiguous. Returns the locator, before-checks to add, what was done ("text_has", "nth", "ambiguous" or None)
    and how many elements the step's locator matched."""
    from routines.executor import list_choice  # the executor imports this module

    def picks(cand: Locator) -> bool:
        m = list_choice(cand, screen, examples, locators.STRICT)
        return m.element is not None and m.element.index == target.index

    if picks(loc):
        return loc, [], None, 1
    hits = locators.all_matching(loc, screen, examples)
    if len(hits) < 2:
        return loc, [], None, len(hits)  # too weak to find anything: not this case
    if target.index not in {e.index for e in hits}:
        return loc, [], "ambiguous", len(hits)
    # A text field's words are what it holds (another run's field is empty, or holds another value): not what chooses it.
    for text in [] if target.editable else _input_texts(target, examples, data_values):
        cand = loc.model_copy(update={"text_has": text})
        if picks(cand):
            return cand, [], "text_has", len(hits)
    if not scrolled:
        base = loc.model_copy(update={"position": None})
        alike = locators.in_order(locators.tied(base, screen, examples), screen)
        head = locators.list_head(alike, screen) if alike and len(alike) > 1 else None
        if alike and head is not None and target.index in {e.index for e in alike}:
            cand = base.model_copy(update={"nth": [e.index for e in alike].index(target.index)})
            # The list is shown, at its start, while its fixed first item is: without it the place means nothing. (Not the
            # list node itself: it is on screen only while it can scroll, and Instagram's grid of six clips can't.)
            start = generalize_check(Check(kind="element_present", locator=chk.anchor_locator(head, screen)), examples, data_values)
            if start is not None and picks(cand) and chk.evaluate(start, screen, examples).passed:
                return cand, [start], "nth", len(hits)
    return loc, [], "ambiguous", len(hits)


# A list's scroll indicator: the date or letter label of a fast scroller, a scroll bar's thumb. Apps show it only while the
# list moves (Instagram's gallery shows "Today" for a moment as it opens), so a check on it holds by chance.
_SCROLL_INDICATOR = re.compile(r"fast_?scroll|scroll_?(?:bar|indicator|thumb|bubble|label|handle)|scrubber|section_?index", re.I)
# System UI drawn over the app: a heads-up notification (Nov 2, Amazon's start screen had CapCut's "An amazing template for
# you!" over it, and the routine waited for it on every rerun). Traces keep the element IDs, not each element's package.
_SYSTEM_UI = "com.android.systemui:"


def _passing(c: Check, screen: ScreenState, nxt: ScreenState | None, examples: dict[str, str]) -> str | None:
    """Why a check on `screen` names something only passing through it (None: it doesn't): a scroll indicator, a system
    notification drawn over the app, or something the same screen no longer shows when the next step starts (`nxt`, its
    before-screen). On Nov 1 a story replay scrolled the gallery to find Instagram's fast-scroll "Today" (it shows while the
    grid moves), and the next step took the wrong clip."""
    if c.kind not in ("element_present", "text_visible"):
        return None
    o = chk.evaluate(c, screen, examples)
    if not o.passed:
        return None
    k: int | None = o.element.index if o.element is not None else None
    for depth in range(64):  # the element and its ancestors
        if k is None or not 0 <= k < len(screen.elements):
            break
        x = screen.elements[k]
        if depth < 6 and (_SCROLL_INDICATOR.search(short_id(x.resource_id) or "") or _SCROLL_INDICATOR.search(x.cls.rsplit(".", 1)[-1])):
            return "a scroll indicator"
        if x.resource_id.startswith(_SYSTEM_UI):
            return "a system notification drawn over the app"
        k = x.parent
    if nxt is not None and nxt.activity == screen.activity and jaccard(signature_keys(nxt), signature_keys(screen)) >= 0.6 \
            and not chk.evaluate(c, nxt, examples).passed:
        return "gone from the same screen when the next step starts"
    return None


def _before_typed(c: Check, step: int, typed_at: dict[str, int]) -> bool:
    """A check that names an input before the step that types it (search history: "aa batteries · delete")."""
    loc = c.locator
    text = " ".join(x or "" for x in ((loc.text, loc.text_has, loc.resource_id) if loc else ()) ) + " " + (c.text or "")
    return any("{{" + n + "}}" in text and step < k for n, k in typed_at.items())


_ON_OFF = {"on", "off", "enabled", "disabled", "true", "false", "yes", "no", "checked", "unchecked"}


def _read_back(ex: Extract, screen: ScreenState, examples: dict[str, str], specs: dict[str, Extract] | None = None) -> str:
    from routines.executor import extract_value  # the executor imports this module
    return extract_value(ex, screen, examples, specs) or ""


def _switch_state(near: str | None, example: str, final: ScreenState) -> Extract | None:
    """An answer that is a switch's state ("Bluetooth is on"): read the on/off state of the switch labelled `near`."""
    if not near or norm(example) not in _ON_OFF:
        return None
    switches = [e for e in final.numbered if e.checkable and e.label]
    el = next((e for e in switches if norm(e.label) == norm(near)), None)
    if el is None:
        return None
    return Extract(locator=Locator(text=el.label, kind=el.kind), switch=True)


def _effect_checks(post: list[Check], before: ScreenState, examples: dict[str, str]) -> tuple[list[Check], list[Check]]:
    """The after-checks that show the step's effect, and the ones that already held on the step's own before screen. Those say
    nothing about what the step did, and at run time they make it look done before it runs: YouTube Music's "Songs" chip is
    there whether or not it's selected, so on Oct 31 the routine skipped the filter and read the unfiltered results' first
    artist (and Lyft's airline Skip "passed" without being taken, Oct 30)."""
    keep, held = [], []
    for c in post:
        specific = c.kind not in ("screen_changed", "screen_like", "app_foreground")
        (held if specific and chk.evaluate(c, before, examples).passed else keep).append(c)
    return keep, held


def _state_text(near: str | None, final: ScreenState, data_values: list[str]) -> Extract | None:
    """The short fixed text an inferred answer was read from ("No contacts yet", "Nothing planned"), as an output that
    reports it whole: on another run it is there or it isn't, and the routine says so rather than inventing a value."""
    if not near or len(near) > 60 or not _data_free(near, data_values):
        return None
    words = [e for e in final.numbered if not (e.checkable or e.editable)]  # a switch's state is on/off, not its words
    el = next((e for e in words if norm(e.label) == norm(near)), None) or \
        next((e for e in words if norm(near) in norm(e.label) and len(e.label) <= 80 and _data_free(e.label, data_values)), None)
    if el is None:
        return None
    return Extract(locator=Locator(text=el.label, kind=el.kind))


def _search_result(el: Element, screen: ScreenState, earlier: list["TStep"], examples: dict[str, str], skip_ads: bool = False) -> str | None:
    """The input name if `el` is the top row of a list showing results for a value entered earlier in the run (typed, or a
    suggestion tapped), and the row shows more than that value (a row that *is* the value, "Caffè Latte", was chosen by it)."""
    if not el.in_list:
        return None
    # Entered: typed, or a suggestion tapped that is the term itself (YouTube's "lofi hip hop" under the search box).
    typed = {n for n, v in examples.items() if v and any((t.typed and contains_value(t.typed, v))
                                                         or (t.kind == "tap" and t.target is not None and norm(t.target.label) == norm(v))
                                                         for t in earlier)}
    shown = [n for n in typed if contains_value(el.label, examples[n]) and norm(el.label) != norm(examples[n])]
    if not shown:
        return None
    rows = [e for e in screen.numbered if e.in_list and e.kind == el.kind and e.clickable and e.area > el.area / 3
            and not (skip_ads and is_ad(e))]
    top = min(rows, key=lambda e: e.bounds[1], default=None)
    return shown[0] if top is not None and top.index == el.index else None


_AD = re.compile(r"^\W*(sponsored|ad)\b|\bsponsored ad\b", re.I)


def is_ad(e: Element) -> bool:
    """A result row that is an ad ("Sponsored - …" on YouTube)."""
    return bool(_AD.search(e.full_label or e.label or ""))


def generalize_check(c: Check, examples: dict[str, str], data_values: list[str]) -> Check | None:
    """Template inputs into a check, and drop booking data it can't depend on (None: drop the check)."""
    if c.kind in ("text_visible", "text_absent"):
        t = bind_inputs(c.text, examples)
        return c.model_copy(update={"text": t}) if _data_free(t, data_values) and norm(t) else None
    if c.locator is None:
        return c
    loc = c.locator
    text = bind_inputs(loc.text, examples)
    rid = _glob_id(loc.resource_id, examples, data_values)
    if not _data_free(text, data_values):
        if not (rid and usable_id(rid)):
            return None
        text = None
    desc = loc.desc if _data_free(loc.desc, data_values) else None
    value = bind_inputs(c.value, examples) if c.kind == "field_equals" else c.value
    upd = {"text": text, "resource_id": rid, "desc": desc}
    if loc.text_has and not has_slot(loc.text_has):  # an input the check names (checks._with_input): its {{slot}}
        upd["text_has"] = bind_inputs(loc.text_has, examples) if has_slot(bind_inputs(loc.text_has, examples)) else None
    new_loc = loc.model_copy(update=upd)
    if not (new_loc.text or new_loc.desc or (new_loc.resource_id and usable_id(new_loc.resource_id)) or new_loc.hint):
        return None
    return c.model_copy(update={"locator": new_loc, "value": value})


def _slug(s: str, fallback: str) -> str:
    out = _SLUG.sub("_", s.casefold()).strip("_")[:40]
    return out or fallback


def _shape(example: str) -> str:
    """A regex for values shaped like the example: digit runs become \\d+ ("$13.49" → \\$\\d+\\.\\d+)."""
    return re.sub(r"(\\\d)+|\d+", r"\\d+", re.escape(example.strip()))


def _numeric(example: str) -> bool:
    """A value that is a number, with at most one word ("190 calories", "$13.49", "2:05 PM", "8am open", "3/4 cup"; of
    "2:05 PM · Group 5", its first part): on another run it is a number too, so a placeholder ("- calories") is not the value
    yet. An address that starts with one ("100 Main St Chicago") is not: another event's location is "Virtual"."""
    tokens = (parts_of(example) or [""])[0].split()
    return bool(tokens) and bool(re.match(r"[$€£]?\d", tokens[0])) and sum(bool(re.search(r"[A-Za-z]", t)) for t in tokens[1:]) <= 1


_YES_NO = {"true": "false", "false": "true", "yes": "no", "no": "yes"}


def _opposite(example: str) -> str | None:
    """The other answer to a yes/no question, written like the example ("True" → "False"); None if it isn't one."""
    e = example.strip()
    o = _YES_NO.get(e.casefold())
    if o is None:
        return None
    return o.upper() if e.isupper() and len(e) > 1 else o.capitalize() if e[:1].isupper() else o


def _plural(name: str, example: str) -> bool:
    """An output that can hold several values: a list in the example ("Game night, Product demo"), or a plural name
    ("event_titles"), the question asking for all of them even when the run had one."""
    last = name.rsplit("_", 1)[-1].casefold()
    return ", " in example or (len(last) > 3 and last.endswith("s") and not last.endswith(("ss", "us", "is")))


def _items(value: str | None) -> list[str]:
    return [norm(x) for x in (value or "").split(", ") if x.strip()]


def _same_answer(got: str | None, example: str, every: bool) -> bool:
    if every:  # a list answer: the same items, in any order
        return sorted(_items(got)) == sorted(_items(example))
    return contains_value(got or "", example)


def _part_examples(examples: dict[str, str], names: set[str] | None = None, parts: tuple[str, ...] | None = None) -> dict[str, str]:
    """The parts of date and time inputs as their own examples, keyed "name:part" so that binding writes {{name:part}}:
    "October 28" gives event_date:day "28" and event_date:month "October" (routines/dates.py)."""
    from routines.dates import parts as date_parts
    out: dict[str, str] = {}
    for n, v in examples.items():
        if (names is None or n in names) and ":" not in n:
            out.update({f"{n}:{p}": f for p, f in date_parts(v).items() if parts is None or p in parts})
    return out


def _every_rows(example: str, final: ScreenState, examples: dict[str, str]) -> Extract | None:
    """A plural answer read as every row of a list ("Game night, Product demo, Date night": each event's title on the day
    asked about). Each value must lead a row of the same ID or type. When the list holds other rows too, the input every
    answer row shows and no other does picks them ("20:00" for "what is on at 8pm": {{schedule_time:time24}})."""
    items = [x.strip() for x in example.split(", ") if x.strip()]
    rows: list[Element] = []
    for item in items:
        el = next((e for e in final.numbered if e.in_list and e.index not in {r.index for r in rows}
                   and parts_of(e.full_label or e.label) and norm(parts_of(e.full_label or e.label)[0]) == norm(item)), None)
        if el is None:
            return None
        rows.append(el)
    rid = short_id(rows[0].resource_id)
    if any(short_id(e.resource_id) != rid or e.kind != rows[0].kind for e in rows):
        return None
    segment = 0 if any(len(parts_of(e.full_label or e.label)) > 1 for e in rows) else None
    base = Locator(resource_id=rid if usable_id(rid) else None, kind=rows[0].kind)
    from routines.executor import extract_value  # the executor imports this module
    ex = Extract(locator=base, segment=segment, every=True)
    if _same_answer(extract_value(ex, final, examples), example, True):
        return ex
    for name, v in sorted(examples.items(), key=lambda kv: -len(kv[1])):
        if v and all(contains_value(e.full_label or e.label, v) for e in rows):
            anchored = ex.model_copy(update={"locator": base.model_copy(update={"text_has": "{{" + name + "}}"})})
            if _same_answer(extract_value(anchored, final, examples), example, True):
                return anchored
    return None


def _extract_for(name: str, near: str, example: str, final: ScreenState, examples: dict[str, str],
                 data_values: list[str], steps: list["TStep"] | None = None) -> Extract | None:
    """Where an output can be read on the final screen: the element showing the example value
    (outside lists first, then the one whose label starts with `near`, then the shortest)."""
    found = [e for e in final.numbered if contains_value(e.label, example)]
    if not found:
        return None
    # Outside lists first, then the element labelled `near`, then one the value starts (a video row starts with its title; a
    # "Mix - <title> - …" row only contains it), then the shortest.
    found.sort(key=lambda e: (e.in_list, not (near and norm(e.label).startswith(norm(near))), not norm(e.label).startswith(norm(example)),
                              len(e.label)))
    el = found[0]
    letters = sum(ch.isalpha() for ch in example)
    if el.in_list and not usable_id(el.resource_id) and norm(el.label) == norm(example) and len(example) <= 24 \
            and any(ch.isdigit() for ch in example) and letters <= len(example) / 2:
        # A bare, number-like value in a list ("$13.49" in search results): read the first list element with that shape.
        first = next((e for e in final.numbered if e.in_list and re.fullmatch(_shape(example), e.label.strip())), None)
        if first is not None and first.index == el.index:
            return Extract(pattern=_shape(example), first_in_list=True)
    label = " ".join(el.label.split())
    rest = label[len(" ".join(example.split())):]
    if el.in_list and not usable_id(el.resource_id) and norm(label).startswith(norm(example)) and norm(label) != norm(example) \
            and len(example) <= 24 and any(ch.isdigit() for ch in example) and letters <= len(example) / 2 \
            and not any(v and contains_value(rest, v) for v in examples.values()):
        # A number-like value leading a list element, then fixed words around other numbers ("$16.49 ( $0.82 /count)", a
        # result's price): the first list element of that whole shape, its leading value. (Words that name an input, "3/4 cup
        # spirulina" for "how much spirulina", anchor on the input below instead.)
        if any(ch.isalpha() for ch in rest) and _data_free(re.sub(r"\d", "", rest), data_values):
            shape = rf"(?P<v>{_shape(example)})\s*{_shape(rest)}"
            shaped = [e for e in final.numbered if e.in_list and re.fullmatch(shape, " ".join(e.label.split()))]
            if len(shaped) < 2 and not _DIGIT.search(rest):
                # Words with no number among them that no other row repeats are this item's own ("25 individuals were
                # present", a note's sentence; another note says "80 participants attended"): the first list element that
                # starts with a number of that shape. Words around another number are the app's ("$9.99 ( $0.83 /count)",
                # even when it is the only such row on screen).
                shape = rf"(?P<v>{_shape(example)})(?:\s+\D.*)?"
                shaped = [e for e in final.numbered if e.in_list and re.fullmatch(shape, " ".join(e.label.split()))]
            if shaped and shaped[0].index == el.index:
                return Extract(pattern=shape, first_in_list=True)
    if not usable_id(el.resource_id) and norm(el.label) == norm(example) and el.number and el.number > 1:
        # The value is its own element after its label ("Seat", then "22F"; "Today", "10/27", "8am open"): read the
        # element that many places after the label, stepping back over other values to the nearest fixed text.
        for offset in range(1, min(4, el.number)):
            prev = final.numbered[el.number - 1 - offset]
            label = bind_inputs(prev.label, examples) or ""  # the label may be the input itself ("Caffè Latte", then "190 calories")
            if not label or not _data_free(label, data_values):
                continue  # another value between the label and this one ("10/27")
            named = near and (norm(prev.label) == norm(near) or norm(near) in norm(prev.label))
            if len(label) <= 40 and (named or (offset == 1 and not near)):
                return Extract(near=label, next_element=True, offset=offset if offset > 1 else None)
            break
    if el.in_list and not usable_id(el.resource_id) and norm(el.label).startswith(norm(example)) and norm(el.label) != norm(example):
        # A list row read aloud as "name, details" ("Mountain Mike's Pizza, 9.2 mi away, Estimated time …", the
        # content description Android apps give rows): read the first row of that shape. The first detail, with its
        # numbers generalized, is the row's signature; it must be fixed text, not booking data ("mi away", not "Nov").
        rest = " ".join(el.label.split())[len(" ".join(example.split())):]
        m = re.match(r",\s*([^,]+)", rest)
        words = re.sub(r"\d+(?:\.\d+)?", " ", m.group(1)).strip() if m else ""
        if words and any(ch.isalpha() for ch in words) and _data_free(words, data_values) \
                and not any(v and contains_value(v, words) for v in data_values):
            sig = re.sub(r"\d+(?:\\\.\d+)?", r"\\d+(?:\\.\\d+)?", re.escape(m.group(1).strip()))
            return Extract(pattern=rf"(?P<v>[^,]+?),\s*{sig}(?:,.*)?", first_in_list=True)
    skip_ads = None
    if steps and el.in_list and norm(label).startswith(norm(example)) and norm(label) != norm(example):
        skip_ads = False if _search_result(el, final, steps, examples) is not None else \
            (True if _search_result(el, final, steps, examples, skip_ads=True) is not None else None)
    if skip_ads is not None:
        # The top result for a term entered in the run ("the first video for lofi hip hop"): read by its place, not by
        # showing the term (another search's first video doesn't), up to the separator after the value; past the ads
        # above it if the agent passed them.
        rest = label[len(" ".join(fold(example).split())):] if norm(label).startswith(norm(example)) else ""
        until = next((sep for sep in (" - ", " · ", " • ", " | ", ", ") if rest.startswith(sep)), None)
        return Extract(locator=Locator(kind=el.kind), first_row=True, until=until, skip_ads=skip_ads)
    loc = None
    card = None
    row_input = next((n for n, v in examples.items() if v and el.in_list
                      and any(norm(p) == norm(v) and not contains_value(p, example) for p in parts_of(el.label))), None)
    if row_input:
        # A list row that shows one of the inputs as a part of its own ("Seattle · Tue, Mar 3, 2026 · SL 1708 · …" for "When
        # did I fly to Seattle?", answered off the list): read in the row that shows {{input}}. By its ID (trip_row_<code>,
        # which every row shares) the routine would read whichever row comes first, and with no action choosing the row the
        # input was dropped as unused.
        loc = Locator(text_has="{{" + row_input + "}}", kind=el.kind)
    elif usable_id(el.resource_id):
        loc = Locator(resource_id=_glob_id(short_id(el.resource_id), examples, data_values), kind=el.kind)
        card = _card_of(el, final, examples, near, data_values)
    else:
        # No ID: an input shown in the same element is the anchor ("SL 1190 · ATL → DEN · …" for flight {{flight_number}}).
        bound = next((n for n, v in examples.items() if v and contains_value(el.label, v)), None)
        if bound:
            loc = Locator(text_has="{{" + bound + "}}", kind=el.kind)
    # Several values in one element ("Boarding · 5:30 AM · Group 3"): remember which part holds this one.
    parts = parts_of(el.label)
    segment = next((i for i, p in enumerate(parts) if contains_value(p, example)), None) if len(parts) > 1 else None
    part = parts[segment] if segment is not None else el.label
    near_text = None
    pos = norm(part).find(norm(example))
    if norm(part) == norm(example):
        near_text = None  # the output is the whole text (a message such as "Known traveler number saved")
    elif near and norm(part).startswith(norm(near)) and _data_free(near, data_values):
        near_text = near
    elif pos > 0:
        prefix = part[:pos].strip(" ·:,")  # "Departs 2:45 PM" → near "Departs"
        near_text = prefix if prefix and _data_free(prefix, data_values) else None
    if near_text is None and segment and not row_input and _data_free(parts[0], data_values):
        near_text = parts[0]  # "Choose a seat · SL 1190": the element is found by its first part (no ID needed)
    after = part[pos + len(example):].strip() if pos >= 0 else ""
    after = bind_inputs(after, examples) or ""  # "3/4 cup spirulina": the value ends where the ingredient asked about starts
    after_text = after if after and _data_free(after, data_values) and len(after) > 1 else None
    if loc is None and near_text is None and segment is None and norm(part) == norm(example) and len(example) >= 12 \
            and _data_free(example, others := [v for v in data_values if norm(v) != norm(example)]) \
            and not any(v and contains_value(example, v) for v in others):
        # A fixed message that is the answer itself ("Nothing planned. Tap to create."): found by its own words. On a
        # run where the app shows something else, the output is missing and the ladder takes over.
        loc = Locator(text=el.label, kind=el.kind)
    if loc is None and near_text is None and segment is None and pos == 0 and after_text and not has_slot(after_text) \
            and sum(ch.isalpha() for ch in after_text) >= 3:
        # The value leads its element and fixed words follow it ("Thursday 29 October 2026, Open Day View", the day heading a
        # calendar reads aloud): the first element of that shape. The read-back on the run's own screen confirms it is the
        # one the agent answered from.
        return Extract(pattern=rf"(?P<v>.+?)\s*{re.escape(after_text)}")
    if loc is None and near_text is None:
        return None  # nothing to find it by on another run (no ID, no label, no input in it, no list shape)
    if card is None and loc is None and near_text and sum(norm(e.label).startswith(norm(near_text)) for e in final.numbered) > 1:
        card = _card_before(el, final, examples, near_text)
    return Extract(near=near_text, locator=loc, segment=segment, after=after_text, card=card)


def _rows(extract: dict[str, Extract], outs: list, final: ScreenState | None, examples: dict[str, str], report: "CompileReport") -> None:
    """A value found by its shape as the first one in the list ("the first result's price"), next to an output that names
    the row ("the first result's product"): read it in that row instead. Results differ in shape (a deal's row says
    "Limited time deal $8.49"), so the first price in the list can belong to the row above."""
    if final is None:
        return
    from routines.executor import extract_value, in_row  # the executor imports this module
    example = {o.name: o.example for o in outs}
    near = {o.name: o.near for o in outs}
    for name, ex in list(extract.items()):
        # A result named by its heading ("Results") that reads something else on the run's own screen (a suggestion
        # above it): the first row under that heading, wherever the list starts.
        if ex.pattern or ex.switch or contains_value(extract_value(ex, final, examples) or "", example.get(name, "")):
            continue
        heading = next((e for e in final.numbered if near.get(name) and norm(e.label) == norm(near[name])), None)
        shown = next((e for e in final.numbered if e.in_list and e.clickable and contains_value(e.full_label or e.label, example.get(name, ""))
                      and heading is not None and e.bounds[1] >= heading.bounds[3] - 1), None)
        if shown is None:
            continue
        skip = list(dict.fromkeys(e.label for e in final.numbered if e.in_list and e.clickable and e.label
                                  and heading.bounds[3] - 1 <= e.bounds[1] < shown.bounds[1]))
        row = Extract(first_row=True, below=heading.label, skip_labels=skip, locator=Locator(kind=shown.kind))
        if contains_value(extract_value(row, final, examples) or "", example[name]):
            extract[name] = row
            report.warnings.append(f"output {name!r}: the first row under {heading.label!r}")
    for name, ex in list(extract.items()):
        # A value after a label that every result repeats ("Average rating"): the one after the row that names the input
        # (a search shows the asked-for app's rating among sponsored apps' ones).
        if ex.near and ex.locator is None and not ex.card and not ex.next_element and not ex.pattern:
            for slot, v in examples.items():
                row = Extract(near=ex.near, card="{{%s}}" % slot, expect_digits=ex.expect_digits)
                if v and contains_value(extract_value(row, final, examples) or "", example.get(name, "")):
                    extract[name] = row
                    report.warnings.append(f"output {name!r}: the {ex.near!r} after the row that names {{{{{slot}}}}}")
                    break
    for name, ex in list(extract.items()):
        if not (ex.pattern and ex.first_in_list):
            continue
        core = re.match(r"[$€£]?\d+(?:[.,]\d+)*", example.get(name, "").strip())
        if core is None:
            continue
        shape = _shape(core.group())
        for anchor, aex in extract.items():
            if anchor == name or aex.pattern or aex.row_of or not (shown := extract_value(aex, final, examples)):
                continue
            got = in_row(shown, shape, final)
            if got and contains_value(example[name], got):
                extract[name] = ex.model_copy(update={"pattern": shape, "first_in_list": False, "row_of": anchor})
                report.warnings.append(f"output {name!r}: read in the row of {anchor!r} ({got!r}), not the list's first match")
                break


async def _screenshot_extract(o: Any, trace_dir: Path, examples: dict[str, str], adapter: ModelAdapter, task_id: str,
                              report: "CompileReport") -> Extract | None:
    """An output read from the run's last screenshot (no tree): kept only if the read passes screen_read.accept and
    gives the agent's answer, the verification each rerun repeats."""
    png = _last_png(trace_dir)
    shape = screen_read.shape_of(o.example)
    question = bind_inputs(f"{o.near}: what does the page say? ({o.name.replace('_', ' ')})", examples) or o.name
    if png is None:
        return None
    got = await asyncio.to_thread(screen_read.read, adapter, png.read_bytes(), render_str(question, examples), shape, examples, task_id=f"{task_id}-compile-read")
    report.model_calls += 1
    report.cost_usd += got.cost_usd
    report.cost_at_standard_usd += got.cost_usd
    same = got.value and (contains_value(got.value, o.example) or contains_value(o.example, got.value)
                          or bool(shape and (a := re.search(shape, o.example)) and (b := re.search(shape, got.value)) and a.group() == b.group()))
    if not same:
        report.warnings.append(f"output {o.name!r}: the recorded screenshot read {got.value!r} ({got.detail}), not {o.example!r}; dropped")
        return None
    report.warnings.append(f"output {o.name!r}: not in the tree; read from the screenshot ({got.value!r}) and checked by shape {shape!r}")
    return Extract(near=question, from_screenshot=shape or ".+")


def _card_before(el: Element, screen: ScreenState, examples: dict[str, str], near: str) -> str | None:
    """For a label every result repeats ("Average rating" on each app in Play's results): the input shown between the
    previous such label and this one (the app's own name, "{{app_name}}"), so the value is read after that app, not the
    sponsored one above it."""
    prev = max((e.number or 0 for e in screen.numbered if (e.number or 0) < (el.number or 0) and norm(e.label).startswith(norm(near))), default=0)
    for name, v in examples.items():
        if v and any(prev < (e.number or 0) < (el.number or 0) and contains_value(e.label, v) and norm(e.label) != norm(v)
                     for e in screen.numbered):
            return "{{" + name + "}}"
    return None


def _card_of(el: Element, screen: ScreenState, examples: dict[str, str], near: str | None, data_values: list[str]) -> str | None:
    """For a value whose ID repeats down a list (every menu item has a `tv_price`): what tells its own row apart, an
    input shown in the row ("{{menu_item_name}}"), else Wonder's fixed label for it. None when the ID is unique."""
    if el.parent is None or sum(e.resource_id == el.resource_id for e in screen.numbered) < 2:
        return None
    mates = [e.label or e.text or e.desc or "" for e in screen.elements if e.parent == el.parent and e.index != el.index]
    for exact in (True, False):
        for name, v in examples.items():
            if v and any((norm(m) == norm(v)) if exact else contains_value(m, v) for m in mates):
                return "{{" + name + "}}"
    if near and _data_free(near, data_values) and any(norm(m) == norm(near) for m in mates):
        return near
    return None


# ---- the compiler -----------------------------------------------------------------------------


async def compile_trace(trace_dir: Path, *, adapter: ModelAdapter | None = None, memory: str = "", confirmed: bool = False,
                        effort: str | None = None, spec: CompiledRoutine | None = None) -> tuple[Routine, CompileReport]:
    """`spec` reuses an earlier Wonder answer for this trace (re-running the deterministic parts at no cost)."""
    adapter = adapter or ModelAdapter()
    run, records = load_trace(trace_dir, confirmed=confirmed)
    report = CompileReport(task_id=run["task_id"], goal=run["goal"])
    steps, dropped = clean(trace_dir, records, run.get("goal", ""))
    if (why := degenerate(run.get("goal", ""), run.get("result", ""), steps, records)) is not None:
        raise NotCompilable(why)  # before the model call: nothing to pay for
    report.dropped = dropped
    report.kept = [s.n for s in steps]
    report.warnings += [f"trace step {s.n}: {s.moved}" for s in steps if s.moved]
    # The screen the agent answered from (its done step) is the most up to date: content can load after a step settles.
    final = _done_screen(trace_dir, records) or (steps[-1].after if steps else _final_screen(trace_dir, records))
    answer = run.get("result", "")

    # Ask Wonder to name inputs, steps and outputs, and to classify the run's values.
    content = compile_input(run["goal"], memory, describe_steps(steps) or "(no actions: the answer was on the first screen)",
                            final.compact if final else "", answer)
    compiler_model = "cached"
    if spec is None:
        t0 = time.perf_counter()
        res = await asyncio.to_thread(_call_compiler, adapter, content, run["task_id"], effort)
        report.latency_s = round(time.perf_counter() - t0, 2)
        report.model, report.model_calls = res.model, 1
        report.cost_usd, report.cost_at_standard_usd = res.cost_usd, res.cost_at_standard_usd
        spec = res.parsed  # type: ignore[assignment]
        compiler_model = res.model
    else:
        report.model = "cached"
    assert spec is not None
    report.wonder = spec.model_dump()

    run_text = "\n".join([run["goal"], memory, answer] + [s.typed or "" for s in steps]
                         + [(s.target.label + " " + s.target.resource_id) for s in steps if s.target is not None])
    examples: dict[str, str] = {}
    inputs: dict[str, InputSpec] = {}
    renames: dict[str, str] = {}
    for inp in spec.inputs:
        name = _slug(inp.name, "value")
        renames[inp.name] = name
        if inp.example and not contains_value(run["goal"], inp.example) and not any(s.typed and contains_value(s.typed, inp.example) for s in steps):
            # Named by the user more briefly than the screen shows it ("Duolingo" for "Duolingo: Learn Languages"): the
            # input is what the user says, so another app ("Spotify") matches its own listing title too.
            head = re.split(r"\s*[:|]\s+|\s+[-–—]\s+", inp.example, maxsplit=1)[0]
            if head != inp.example and len(head) >= 3 and contains_value(run["goal"], head):
                report.warnings.append(f"input {inp.name!r}: example {inp.example!r} shortened to the user's {head!r}")
                inp = inp.model_copy(update={"example": head})
        if not inp.example or not contains_value(run_text, inp.example):
            report.warnings.append(f"input {inp.name!r}: example {inp.example!r} is not in the run; dropped")
            continue
        examples[name] = inp.example
        from_memory = inp.from_memory or (inp.name if "." in inp.name else None)
        inputs[name] = InputSpec(type=inp.type, description=inp.description, from_memory=from_memory, example=inp.example)
    # Values the routine reads (its outputs) differ from run to run too, so checks must not expect them.
    # (Field names such as "flight_number" instead of values are ignored.)
    data_values = [v for v in spec.data_values + [o.example for o in spec.outputs]
                   if v and not _IDENT.fullmatch(v) and not any(norm(v) == norm(x) for x in examples.values())]
    # Wonder sometimes numbers steps from 0; STEPS are numbered from 1.
    shift = 1 if spec.steps and min(m.step for m in spec.steps) == 0 else 0
    per_step = {m.step + shift: m for m in spec.steps}
    for meta in spec.steps:  # Wonder sometimes writes {{trip.city}} for the memory path; use the slot name
        for old, new in renames.items():
            meta.intent = meta.intent.replace("{{" + old + "}}", "{{" + new + "}}")
        if meta.choice_input in renames:
            meta.choice_input = renames[meta.choice_input]

    out_steps: list[Step] = []
    used_ids: set[str] = set()
    # Where each input is first typed: before then, the input on screen can only be history (a recent search), so no check
    # may expect it there.
    typed_at = {n: k for n, v in examples.items() if v
                and (k := next((k for k, t in enumerate(steps, 1) if t.kind == "type" and t.typed and contains_value(t.typed, v)), 0))}
    for i, s in enumerate(steps, 1):
        meta = per_step.get(i)
        sid = _slug(meta.id if meta else s.reason, f"step_{i}")
        while sid in used_ids:
            sid += "_2"
        used_ids.add(sid)
        intent = (meta.intent if meta else s.reason) or s.kind
        target_screen = getattr(s, "before_for_target", s.before)
        # A date the step picks shows on screen only in parts (the "28" of a month grid under "October" for "October 28"):
        # for the step whose intent names it, or that Wonder says chose by it, its parts bind as {{event_date:day}}.
        named = {n for n in examples if n in slot_names(intent) or (meta and meta.choice_input == n)}
        step_examples = {**examples, **_part_examples(examples, named)}
        loc = None
        if s.target is not None:
            choice = meta.choice_input if meta else None
            def shown(v: str) -> bool:
                return contains_value(s.target.full_label or s.target.label, v) or contains_value(s.target.desc, v)
            if choice in examples and not shown(examples[choice]) \
                    and any(k.startswith(choice + ":") and shown(v) for k, v in step_examples.items()):
                choice = None  # the target shows only a part of it (a month grid's "28"): bound by that part below
            ex = step_examples
            if (searched := _search_result(s.target, target_screen, steps[: i - 1], examples)) is not None:
                # The top row of results for a term typed in this run: "the first result", chosen by its place, not by
                # showing the term (Gmail: the first row *containing* "DoorDash" was another email). Its slot picks it.
                choice, ex = None, {k: v for k, v in step_examples.items() if k != searched and not k.startswith(searched + ":")}
                report.warnings.append(f"step {i}: the first result for {{{{{searched}}}}}: chosen by its place in the list")
            loc = generalize_locator(locators.build(s.target, target_screen), ex, data_values,
                                     meta.target_fixed_text if meta else None, choice)
            if searched is not None:  # a result's words are that result's: only its place (and ID, type) say "first"
                loc = loc.model_copy(update={"text": None, "desc": None, "siblings": [], "text_has": None, "alt_texts": [],
                                             "row": [], "row_has": None})
        extra_pre: list[Check] = []
        if loc is not None and s.target is not None and s.kind in ("tap", "long_press", "type", "scroll_until"):
            # A locator that fits several look-alikes on the recorded screen picks whichever comes up first on a rerun.
            scrolled = s.kind == "scroll_until" or (i >= 2 and steps[i - 2].kind == "scroll_until")
            loc, extra_pre, how, n = disambiguate(loc, s.target, target_screen, step_examples, data_values, scrolled=scrolled)
            if how == "text_has":
                report.warnings.append(f"step {i}: its target matched {n} look-alikes on the recorded screen; now the one that "
                                       f"shows {loc.text_has}")
            elif how == "nth":
                place = _ORDINAL[loc.nth] if (loc.nth or 0) < len(_ORDINAL) else f"#{(loc.nth or 0) + 1}"
                report.warnings.append(f"step {i}: its target matched {n} look-alikes on the recorded screen; now the {place} of "
                                       f"them in its list, which must show {extra_pre[-1].locator.describe()} (the list's start)")
            elif how == "ambiguous":
                report.ambiguous.append({"step": sid, "trace_step": s.n, "matches": n, "locator": loc.describe()})
                report.warnings.append(f"step {i}: ambiguous: its target matches {n} elements on the recorded screen and nothing "
                                       f"in the run tells them apart; a rerun falls back on the ladder there")
        if s.kind in ("tap", "long_press"):
            action = StepAction(kind=s.kind, target=loc)
        elif s.kind == "type":
            value = bind_inputs(s.typed or "", step_examples)
            if (prior := _prior_text(s)) is not None:
                # The agent typed the field's text back around the input (a line added to the top of a note): the routine
                # keeps whatever the field holds on its run ({{_field}}), never this note's words.
                value = bind_inputs(s.typed or "", {**step_examples, FIELD: prior})
                if loc is not None and norm(loc.hint) == norm(prior):
                    loc = loc.model_copy(update={"hint": None})
                report.warnings.append(f"step {i}: typed around the field's own text; kept as {{{{{FIELD}}}}}")
            if not has_slot(value) and s.typed and not _data_free(s.typed, []):
                report.warnings.append(f"step {i}: typed {s.typed!r} is not an input; kept as a fixed value")
            action = StepAction(kind="type", target=loc, value=value, submit=s.submit)
        elif s.kind == "scroll_until":
            action = StepAction(kind="scroll_until", target=loc, direction=s.direction or "down", max_scrolls=max(8, 2 * s.scrolls + 2),
                                container=chk.anchor_locator(s.container, s.before) if s.container is not None else None)
        elif s.kind == "back":
            action = StepAction(kind="back")
        elif s.kind == "swipe" and s.swipe is not None:
            # A drag (a bottom sheet, a carousel) anchored on the element under the finger, as a vector in screen fractions.
            x, y, x2, y2 = s.swipe
            w, h = s.before.width or 1080, s.before.height or 2400
            under = min((e for e in s.before.numbered if e.bounds[0] <= x <= e.bounds[2] and e.bounds[1] <= y <= e.bounds[3]),
                        key=lambda e: e.area, default=None)
            anchor = generalize_locator(locators.build(under, s.before), examples, data_values, None, None) if under is not None else None
            # Where the finger went down inside that element: a slider dragged from its thumb at the left ends at the right
            # end, where a drag from the element's centre by the same vector stops short (brightness 51915, not the max).
            grip = None
            if under is not None and under.bounds[2] > under.bounds[0] and under.bounds[3] > under.bounds[1]:
                ux1, uy1, ux2, uy2 = under.bounds
                grip = (round((x - ux1) / (ux2 - ux1), 3), round((y - uy1) / (uy2 - uy1), 3))
            action = StepAction(kind="swipe", target=anchor, vector=(round((x2 - x) / w, 3), round((y2 - y) / h, 3)),
                                start=(round(x / w, 3), round(y / h, 3)), grip=grip)
        elif s.kind == "launch":
            # The app that came up: the model may have named it ("Broccoli") rather than given its package.
            action = StepAction(kind="launch", package=s.after.package)
        elif s.kind == "tap_point" and s.vision and s.vision.get("box") and s.vision.get("target"):
            # Phase 6: a target drawn on screen (no node in the tree), kept as what it looks like plus its picture.
            v = s.vision
            w, h = v.get("size") or [s.before.width or 1080, s.before.height or 2400]
            x1, y1, x2, y2 = v["box"]
            visual = bind_inputs(v["target"], step_examples)
            # The picture shows the recorded value (seat 10C): keep it only when the target doesn't change with the inputs.
            crop = (s.trace_dir / v["crop"]).read_bytes() if (s.trace_dir and v.get("crop") and not has_slot(visual)
                                                               and (s.trace_dir / v["crop"]).exists()) else None
            action = StepAction(kind="tap", target=Locator(visual=visual, crop=encode_png(crop) if crop else None,
                                                           region=(round(x1 / w, 4), round(y1 / h, 4), round(x2 / w, 4), round(y2 / h, 4)),
                                                           density=v.get("density")))
        else:
            report.warnings.append(f"step {i}: {s.kind} is not supported in routines; dropped")
            continue

        pre = chk.derive_pre(s.before, s.target, examples, first=not out_steps)
        if s.kind == "scroll_until":
            post = [Check(kind="element_present", locator=loc)] if loc is not None else []
        else:
            post = chk.derive_post(s.before, s.after, s.kind, s.target, s.typed, examples, submit=s.submit)
        pre = [g for c in pre if (g := chk_generalize(c, examples, data_values)) is not None and not _before_typed(g, i, typed_at)]
        post = [g for c in post if (g := chk_generalize(c, examples, data_values)) is not None and not _before_typed(g, i, typed_at)]
        # A check on something only passing through the screen holds by chance (a scroll indicator, a label gone a moment later).
        nxt_before = steps[i].before if i < len(steps) else None
        derived = [(pre, s.before, None)] + ([(post, s.after, nxt_before)] if s.kind != "scroll_until" else [])
        for checks, screen, nxt in derived:
            for c in list(checks):
                if (why := _passing(c, screen, nxt, examples)) is not None:
                    checks.remove(c)
                    report.warnings.append(f"step {i}: check {c.describe()} names {why}; dropped")
        pre += extra_pre
        if s.kind == "type" and (prior := _prior_text(s)) is not None:
            post = [c.model_copy(update={"value": bind_inputs(c.value, {FIELD: prior})}) if c.kind == "field_equals" else c for c in post]
        post, held = _effect_checks(post, s.before, examples)
        for c in held:
            report.warnings.append(f"step {i}: after-check {c.describe()} already held before the step; dropped")
        if not post:
            post = [Check(kind="screen_changed")]
        out_steps.append(Step(id=sid, intent=intent, pre=pre, action=action, post=post,
                              risk=s.risk if s.risk in ("read", "reversible", "irreversible") else "read",
                              optional=(why := _optional_why(s, sid, intent)) is not None,
                              note=f"trace step {s.n}" + (f" (+{s.scrolls} scrolls)" if s.scrolls else "")
                              + (f" · {why}: optional" if why else "") + (f" · {s.moved}" if s.moved else "")))

    # A list row chosen by an input may sit further down for another value: reveal it first.
    with_scrolls: list[Step] = []
    for st in out_steps:
        tgt = st.action.target
        if st.action.kind in ("tap", "long_press", "type") and tgt is not None and tgt.in_list and tgt.text_has \
                and not (with_scrolls and with_scrolls[-1].action.kind == "scroll_until"):
            with_scrolls.append(Step(
                id=f"find_{st.id}"[:44], intent=f"Scroll to {tgt.text_has} if it is not on screen",
                action=StepAction(kind="scroll_until", target=tgt, direction="down", max_scrolls=8),
                post=[Check(kind="element_present", locator=tgt)], risk="read", note="added: input-based list choice"))
        with_scrolls.append(st)
    out_steps = with_scrolls

    # Outputs: where each value is read on the final screen.
    outputs: list[str] = []
    extract: dict[str, Extract] = {}
    shot_only = screen_only(trace_dir, run, records) and not _app_text(final)
    if shot_only:
        for o in spec.outputs:
            ex = await _screenshot_extract(o, trace_dir, examples, adapter, run["task_id"], report)
            if ex is not None:
                outputs.append(o.name)
                extract[o.name] = ex
    elif final is not None:
        # An hour or a date asked about, as the screen writes it ("8:00pm" is "20:00" in a day's list).
        out_examples = {**examples, **_part_examples(examples, parts=("time24", "iso"))}
        stated: set[str] = set()
        for o in spec.outputs:
            ex = _switch_state(o.near, o.example, final)
            if ex is None and _plural(o.name, o.example):
                ex = _every_rows(o.example, final, out_examples)
            ex = ex or _extract_for(o.name, o.near, o.example, final, examples, data_values, steps)
            state = bool(ex and ex.switch)
            # Wonder sometimes lists the words an inferred answer was read from among the run's data ("No contacts yet" for
            # "0", about 1 compile in 4 on Oct 31). When the answer quotes them and its value is nowhere on the screen, they
            # are the screen's own words.
            inferred = bool(o.near) and contains_value(answer, o.near) and not any(contains_value(e.label, o.example) for e in final.numbered)
            state_data = [v for v in data_values if norm(v) != norm(o.near)] if inferred else data_values
            if ex is None and (ex := _state_text(o.near, final, state_data)) is not None:
                state = True
                if (no := _opposite(o.example)) is not None:
                    # A yes/no question answered from what the screen offers ("Convert to note" in a to-do's menu): the
                    # answer is whether that is on screen, never its words.
                    ex = ex.model_copy(update={"answers": [o.example.strip(), no]})
                    report.warnings.append(f"output {o.name!r}: {o.example.strip()!r} when {o.near!r} is on screen, else {no!r}")
                else:
                    # An answer the agent inferred ("0" from "No contacts yet"): the routine reports the words it was read from.
                    report.warnings.append(f"output {o.name!r}: {o.example!r} was inferred from {o.near!r}; the routine reports that text")
            if ex is None:
                report.warnings.append(f"output {o.name!r}: {o.example!r} is not on the final screen, or nothing anchors it; dropped")
                continue
            outputs.append(o.name)
            if state:
                stated.add(o.name)
            # A value recorded as a number ("190 calories", "$13.49", "2:05 PM") must be one at run time too.
            extract[o.name] = ex.model_copy(update={"expect_digits": not state and not ex.every and _numeric(o.example)})
    _rows(extract, spec.outputs, final, examples, report)
    if final is not None and not shot_only:
        for o in spec.outputs:
            if o.name not in extract or o.name in stated or extract[o.name].row_of:
                continue  # (a value read in another output's row was read back there by _rows)
            ex = extract[o.name]
            if not _same_answer(got := _read_back(ex, final, examples, extract), o.example, ex.every):
                # Read back from the screen the agent answered from, it gives another value: on the next run it would answer
                # with that one (the first event of the day, not the one at 8pm). No answer is better than a wrong one.
                del extract[o.name]
                outputs.remove(o.name)
                report.warnings.append(f"output {o.name!r} reads {got!r} on the run's own final screen, not {o.example!r}; dropped")
    # "… and tell me the artist of the first result" asks a question too (Oct 31: YouTube Music's routine compiled with no
    # output and answered nothing).
    question = bool(re.search(r"\?\s*$|^(what|how|when|where|which|who|is|are|do|does|did|can)\b|"
                              r"\btell me (the|its|their|what|who|which|how|when|where|if|whether)\b", (run.get("goal") or "").strip(), re.I))
    if not extract and final is not None and question and answer:
        # A question answered from what the screen says rather than a value on it ("No events today" from "Nothing planned"),
        # with no output named: report the screen text the answer quotes, word for word.
        quoted = [e for e in final.numbered if len(e.label) >= 12 and not (e.checkable or e.editable)
                  and e.label.casefold() in answer.casefold() and _data_free(e.label, data_values)]
        if quoted:
            el = max(quoted, key=lambda e: len(e.label))
            outputs.append("answer")
            extract["answer"] = Extract(locator=Locator(text=el.label, kind=el.kind))
            report.warnings.append(f"no output named; the routine reports the screen text the answer quoted: {el.label!r}")
    if question and answer and not extract:
        # A question the routine could run every step of and still not answer ("what is my next event?": the first event
        # after now, which no fixed place on the screen holds): the agent answers it, not a routine.
        raise NotCompilable(f"the run answered a question ({answer[:60]!r}), but no output can be read back from its own final "
                            f"screen: {'; '.join(w for w in report.warnings if w.startswith('output')) or 'none was named'}")
    if extract and all(e.from_screenshot for e in extract.values()):
        # Read from the screenshot: the read scrolls until the answer is on screen, so a trailing scroll toward it (which
        # has nothing in the tree to stop at) goes.
        while out_steps and out_steps[-1].action.kind == "scroll_until":
            out_steps.pop()
    out_steps = _aim_trailing_scrolls(out_steps, extract, report)
    if extract:
        if not out_steps:
            # The answer is on the screen the app opens to ("How many miles do I have?"): outputs are read by steps, so a
            # routine with none would promise outputs it can never read. One read-only step carries them.
            # Its before-check waits for the app to be in front: read straight after a fresh launch, a slow app's first screen
            # (Calendar's agenda) isn't up yet, and the answer was reported missing.
            out_steps.append(Step(id="read_answer", intent="Read the answer on the app's first screen",
                                  pre=[Check(kind="app_foreground", package=final.package)] if final is not None and final.package else [],
                                  action=StepAction(kind="wait", seconds=0.3), risk="read", note="added: the answer is on the start screen"))
        out_steps[-1].extract = extract
    # After the outputs: an output read in the row an input names (a menu item's price) uses that input.
    limits = _add_witnesses(out_steps, steps, examples, inputs, report, start=steps[0].before if steps else final)

    # Safety net: the run's irreversible action must survive cleanup, or the routine would "succeed" without doing the job.
    if any(r.get("approval", {}).get("approved") for r in records if r.get("kind") == "action") and \
            not any(st.risk == "irreversible" for st in out_steps):
        raise NotCompilable("cleanup removed the run's approved irreversible step; refusing to compile a routine that would skip it")
    done = _done_checks(run, examples, data_values, final)
    # The app the run worked in: where its first step started (Settings' search screen belongs to another package, and a
    # routine launched as that one never starts), else the plan's app, else the final screen's.
    app = (steps[0].before.package if steps else "") or (run.get("plan") or {}).get("app") or (final.package if final else "") or ""
    routine = Routine(
        routine=_slug(spec.name, "routine"), app=app, version=1, status="draft", intent=spec.intent,
        description=" ".join([spec.description, *limits]),
        patterns=spec.patterns, inputs=inputs, outputs=outputs, steps=out_steps, done=done,
        compiled_from={"task_id": run["task_id"], "goal": run["goal"], "compiler": compiler_model, "compiled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "trace_steps_kept": report.kept, "trace_steps_dropped": len(dropped), "cost_usd": round(report.cost_at_standard_usd, 4),
                       **({"source": "taught"} if run.get("source") == "taught" else {})},
    )
    return routine, report


def _aim_trailing_scrolls(out_steps: list[Step], extract: dict[str, Extract], report: CompileReport) -> list[Step]:
    """A trailing scroll toward an answer reveals the first output's element. With no output left to reveal (every one was
    dropped), it has nothing to stop at: an empty target was saved as no target at all, and the routine could not be
    loaded back (Phase 7's youtube_search, backlog #17). Such a scroll is dropped."""
    first = next(iter(extract.values()), None)
    reveal = first.locator if first and first.locator else (Locator(text=first.near) if first and first.near else None)
    kept: list[Step] = []
    for st in out_steps:
        if st.action.kind == "scroll_until" and st.action.target is None:
            if reveal is None:
                report.warnings.append(f"step {st.id!r}: a trailing scroll with no output to reveal; dropped")
                continue
            st.action.target = reveal
            st.post = [Check(kind="element_present", locator=reveal)]
        kept.append(st)
    return kept


def _consumed(step: Step, name: str) -> bool:
    """Whether the step uses the input, whole or by a part ({{event_date:day}})."""
    a = step.action
    return name in slot_names(a.value) or (a.target is not None and name in slot_names(a.target.model_dump_json())) \
        or any(name in slot_names(x.card) or (x.locator is not None and name in slot_names(x.locator.model_dump_json()))
               for x in (step.extract or {}).values())  # the row an output is read in


def _prior_text(s: TStep) -> str | None:
    """The text a field held before the step typed it back with more around it ("Hello, World!\\n<the note>"), else None."""
    e = s.target
    prior = (e.text or "").strip() if e is not None and e.editable else ""
    if not prior or not s.typed or prior == (e.hint or "").strip() or norm(prior) == norm(s.typed):
        return None
    return prior if contains_value(s.typed, prior) else None


def _add_witnesses(out_steps: list[Step], steps: list[TStep], examples: dict[str, str], inputs: dict[str, InputSpec],
                   report: CompileReport, start: ScreenState | None = None) -> list[str]:
    """An input that no action uses must at least be visible before the step that depends on it.

    Example: an agent checked in through Home's "Check in" button, which always means the next trip.
    The routine's input (the trip's city) then appears only on the Home card. Requiring that card to show
    {{trip_city}} before the tap means a request for another trip fails the check and climbs the
    fallback ladder, instead of quietly checking in the wrong trip."""
    by_trace = {s.n: s for s in steps}
    limits: list[str] = []
    for name, value in list(examples.items()):
        if any(_consumed(st, name) for st in out_steps):
            continue
        placed = False
        for st in out_steps:
            n = int(st.note.split()[2]) if st.note and st.note.startswith("trace step") else None
            ts = by_trace.get(n) if n is not None else None
            # The step added to read an answer the app opens to reads the run's first screen (Nov 2, Chrome reopened on the
            # Eiffel Tower article: its heading is where the topic shows, and without a check any topic got 1889).
            screen = ts.before if ts is not None else (start if st.id == "read_answer" else None)
            if screen is None:
                continue
            el = next((e for e in screen.numbered if contains_value(e.label, value)), None)
            if el is None:
                continue
            loc = Locator(resource_id=short_id(el.resource_id) if usable_id(el.resource_id) else None, text_has="{{" + name + "}}",
                          kind=el.kind)
            st.pre.append(Check(kind="element_present", locator=loc))
            report.warnings.append(f"input {name!r} is not used by any action: step {st.id!r} now requires the screen to show it "
                                   f"({el.kind} {el.label[:50]!r}); other values need a repair or a recompile")
            limits.append(f"Only works when {name} is the one already shown on {el.label.split(' · ')[0]!r}.")
            placed = True
            break
        if not placed:
            report.warnings.append(f"input {name!r} is never used or shown; dropped")
            examples.pop(name)
            inputs.pop(name, None)
    return limits


def chk_generalize(c: Check, examples: dict[str, str], data_values: list[str]) -> Check | None:
    return generalize_check(c, examples, data_values)


def _done_screen(trace_dir: Path, records: list[dict]) -> ScreenState | None:
    for r in reversed(records):
        if r.get("kind") == "action" and (r.get("decision") or {}).get("action", {}).get("type") == "done" and r.get("tree_before"):
            return load_tree(trace_dir / r["tree_before"])
    return None


def _final_screen(trace_dir: Path, records: list[dict]) -> ScreenState | None:
    for r in reversed(records):
        if r.get("tree_after"):
            return load_tree(trace_dir / r["tree_after"])
        if r.get("tree_before"):
            return load_tree(trace_dir / r["tree_before"])
    return None


def _done_checks(run: dict, examples: dict[str, str], data_values: list[str], final: ScreenState | None) -> list[Check]:
    sc = (run.get("plan") or {}).get("success_check") or {}
    kind, value, hint = sc.get("kind"), sc.get("value") or "", sc.get("field_hint")
    c: Check | None = None
    if kind == "text_visible":
        c = Check(kind="text_visible", text=value)
    elif kind == "element_present":
        c = Check(kind="element_present", locator=Locator(text=value))
    elif kind == "field_equals" and hint:
        if final is not None and any(e.checkable and hint.casefold() in e.label.casefold() for e in final.numbered):
            el = next(e for e in final.numbered if e.checkable and hint.casefold() in e.label.casefold())
            c = Check(kind="toggle_is", locator=chk.anchor_locator(el, final), value="on" if value.casefold() in ("on", "true", "yes") else "off")
        else:
            c = Check(kind="field_equals", locator=Locator(hint=hint, kind="EditText"), value=value)
    if c is None:
        return []
    g = generalize_check(c, examples, data_values)
    if g is None or (final is not None and not chk.evaluate(g, final, examples).passed):
        return []  # a done-check that doesn't even hold on the recorded final screen is useless
    return [g]


# ---- 5: verify by replay ----------------------------------------------------------------------


@dataclass
class VerifyCase:
    """One replay: reset the app to a known state, run with these inputs, check the outcome in code."""

    name: str
    inputs: dict[str, str]
    reset: Callable[[], Awaitable[None]]
    success: Callable[[Any], Awaitable[bool]]  # gets the executor's RunOutcome


@dataclass
class VerifyResult:
    passed: bool
    cases: list[dict[str, Any]]


async def verify(routine: Routine, executor: Any, cases: list[VerifyCase]) -> VerifyResult:
    """Replay the routine for each case. A case passes only if the routine finished on its own (no repair,
    no agent) and the code check on the app's state holds."""
    rows = []
    for case in cases:
        await case.reset()
        outcome = await executor.run(routine, case.inputs, task_id=f"verify-{routine.routine}-v{routine.version}-{case.name}",
                                     allow_repair=False, allow_agent=False)
        ok = outcome.status == "done" and await case.success(outcome)
        rows.append({"case": case.name, "inputs": case.inputs, "passed": ok, "status": outcome.status, "detail": outcome.detail,
                     "duration_s": outcome.duration_s, "outputs": outcome.outputs})
    return VerifyResult(all(r["passed"] for r in rows) and bool(rows), rows)

