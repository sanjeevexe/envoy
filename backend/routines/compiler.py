"""Routine compiler: one successful agent trace → an app routine (design doc, App routines › Compiling).

1. Confirm success: only runs that ended `done` with a passed success check (or that the user
   confirmed) are compiled.
2. Clean up: drop pop-up dismissals (the shared handler covers them), looks, rejected or failed
   actions, steps with no visible effect, and back-tracks (a stretch of steps that ends on exactly
   the screen it started from). Recorded scrolls before a list tap become `scroll_until`.
3. Generalize: Muse Wonder names the inputs and decides what stays fixed (Spark at high effort if
   Wonder fails). Values that equal an input become {{slots}} in typed text, locators and checks;
   a list row chosen because it shows an input becomes an input-based locator (`text_has`); booking
   data that is not an input is removed so the routine doesn't expect it.
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
from routines.model import Check, Extract, InputSpec, Locator, Routine, Step, StepAction, has_slot
from routines.screens import contains_value, fold, load_tree, norm, parts_of, short_id, usable_id
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
    if re.search(r"keyboard", f"{sid} {intent}", re.I):
        # The routine moves a target out from under the keyboard itself, so closing it is never needed; done blind it
        # can hurt (Back with the keyboard already gone leaves the screen; its keys are not part of the screen).
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


# ---- 1 + 2: load and clean up -----------------------------------------------------------------


def load_trace(trace_dir: Path, *, confirmed: bool = False) -> tuple[dict, list[dict]]:
    run = json.loads((trace_dir / "run.json").read_text())
    check = run.get("check") or {}
    if not confirmed and not (run.get("status") == "done" and check.get("passed")):
        raise NotCompilable(f"run ended {run.get('status')!r} with check {check.get('detail')!r}; only verified runs are compiled")
    records = [json.loads(line) for line in (trace_dir / "steps.jsonl").read_text().splitlines() if line.strip()]
    return run, records


def clean(trace_dir: Path, records: list[dict]) -> tuple[list[TStep], list[tuple[int, str]]]:
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

    changed = True
    while changed:
        changed = False
        for i in range(len(steps)):
            for j in range(len(steps) - 1, i, -1):
                a, b = steps[i].before, steps[j].after
                if any(effectful(t) for t in steps[i:j + 1]):
                    continue
                if a.signature == b.signature and _layout_key(a) == _layout_key(b):
                    for s in steps[i:j + 1]:
                        dropped.append((s.n, f"back-track: steps {steps[i].n}–{steps[j].n} returned to the same screen"))
                    del steps[i:j + 1]
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


def _layout_key(s: ScreenState) -> str:
    """Labels, states and positions of the listed elements: a bottom sheet dragged up has the same labels but not the same bounds."""
    return "\n".join(f"{e.label}|{e.kind}|{e.checked}|{e.bounds}" for e in s.numbered)


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
        lines.append(f"{i}. {s.kind}{tgt}{extra} — on screen {_title(s.before)!r} → {_title(s.after)!r}. Agent's reason: {s.reason}")
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
    upd: dict[str, Any] = {"resource_id": _glob_id(loc.resource_id, examples, data_values)}
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


def _before_typed(c: Check, step: int, typed_at: dict[str, int]) -> bool:
    """A check that names an input before the step that types it (search history: "aa batteries · delete")."""
    loc = c.locator
    text = " ".join(x or "" for x in ((loc.text, loc.text_has, loc.resource_id) if loc else ()) ) + " " + (c.text or "")
    return any("{{" + n + "}}" in text and step < k for n, k in typed_at.items())


_ON_OFF = {"on", "off", "enabled", "disabled", "true", "false", "yes", "no", "checked", "unchecked"}


def _read_back(ex: Extract, screen: ScreenState, examples: dict[str, str]) -> str:
    from routines.executor import extract_value  # the executor imports this module
    return extract_value(ex, screen, examples) or ""


def _switch_state(near: str | None, example: str, final: ScreenState) -> Extract | None:
    """An answer that is a switch's state ("Bluetooth is on"): read the on/off state of the switch labelled `near`."""
    if not near or norm(example) not in _ON_OFF:
        return None
    switches = [e for e in final.numbered if e.checkable and e.label]
    el = next((e for e in switches if norm(e.label) == norm(near)), None)
    if el is None:
        return None
    return Extract(locator=Locator(text=el.label, kind=el.kind), switch=True)


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
    new_loc = loc.model_copy(update={"text": text, "resource_id": rid, "desc": desc})
    if not (new_loc.text or new_loc.desc or (new_loc.resource_id and usable_id(new_loc.resource_id)) or new_loc.hint):
        return None
    return c.model_copy(update={"locator": new_loc, "value": value})


def _slug(s: str, fallback: str) -> str:
    out = _SLUG.sub("_", s.casefold()).strip("_")[:40]
    return out or fallback


def _shape(example: str) -> str:
    """A regex for values shaped like the example: digit runs become \\d+ ("$13.49" → \\$\\d+\\.\\d+)."""
    return re.sub(r"(\\\d)+|\d+", r"\\d+", re.escape(example.strip()))


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
    if el.in_list and not usable_id(el.resource_id) and norm(label).startswith(norm(example)) and norm(label) != norm(example) \
            and len(example) <= 24 and any(ch.isdigit() for ch in example) and letters <= len(example) / 2:
        # A number-like value leading a list element, then fixed words around other numbers ("$16.49 ( $0.82 /count)", a
        # result's price): the first list element of that whole shape, its leading value.
        rest = label[len(" ".join(example.split())):]
        if any(ch.isalpha() for ch in rest) and _data_free(re.sub(r"\d", "", rest), data_values):
            shape = rf"(?P<v>{_shape(example)})\s*{_shape(rest)}"
            first = next((e for e in final.numbered if e.in_list and re.fullmatch(shape, " ".join(e.label.split()))), None)
            if first is not None and first.index == el.index:
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
    if usable_id(el.resource_id):
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
    if near_text is None and segment and _data_free(parts[0], data_values):
        near_text = parts[0]  # "Choose a seat · SL 1190": the element is found by its first part (no ID needed)
    after = part[pos + len(example):].strip() if pos >= 0 else ""
    after_text = after if after and _data_free(after, data_values) and len(after) > 1 else None
    if loc is None and near_text is None and segment is None and norm(part) == norm(example) and len(example) >= 12 \
            and _data_free(example, others := [v for v in data_values if norm(v) != norm(example)]) \
            and not any(v and contains_value(example, v) for v in others):
        # A fixed message that is the answer itself ("Nothing planned. Tap to create."): found by its own words. On a
        # run where the app shows something else, the output is missing and the ladder takes over.
        loc = Locator(text=el.label, kind=el.kind)
    if loc is None and near_text is None:
        return None  # nothing to find it by on another run (no ID, no label, no input in it, no list shape)
    if card is None and loc is None and near_text and sum(norm(e.label).startswith(norm(near_text)) for e in final.numbered) > 1:
        card = _card_before(el, final, examples, near_text)
    return Extract(near=near_text, locator=loc, segment=segment, after=after_text, card=card)


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
    steps, dropped = clean(trace_dir, records)
    report.dropped = dropped
    report.kept = [s.n for s in steps]
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
        loc = None
        if s.target is not None:
            choice = meta.choice_input if meta else None
            ex = examples
            if (searched := _search_result(s.target, target_screen, steps[: i - 1], examples)) is not None:
                # The top row of results for a term typed in this run: "the first result", chosen by its place, not by
                # showing the term (Gmail: the first row *containing* "DoorDash" was another email). Its slot picks it.
                choice, ex = None, {k: v for k, v in examples.items() if k != searched}
                report.warnings.append(f"step {i}: the first result for {{{{{searched}}}}}: chosen by its place in the list")
            loc = generalize_locator(locators.build(s.target, target_screen), ex, data_values,
                                     meta.target_fixed_text if meta else None, choice)
            if searched is not None:  # a result's words are that result's: only its place (and ID, type) say "first"
                loc = loc.model_copy(update={"text": None, "desc": None, "siblings": [], "text_has": None, "alt_texts": [],
                                             "row": [], "row_has": None})
        if s.kind in ("tap", "long_press"):
            action = StepAction(kind=s.kind, target=loc)
        elif s.kind == "type":
            value = bind_inputs(s.typed or "", examples)
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
            action = StepAction(kind="swipe", target=anchor, vector=(round((x2 - x) / w, 3), round((y2 - y) / h, 3)),
                                start=(round(x / w, 3), round(y / h, 3)))
        elif s.kind == "launch":
            # The app that came up: the model may have named it ("Broccoli") rather than given its package.
            action = StepAction(kind="launch", package=s.after.package)
        elif s.kind == "tap_point" and s.vision and s.vision.get("box") and s.vision.get("target"):
            # Phase 6: a target drawn on screen (no node in the tree), kept as what it looks like plus its picture.
            v = s.vision
            w, h = v.get("size") or [s.before.width or 1080, s.before.height or 2400]
            x1, y1, x2, y2 = v["box"]
            visual = bind_inputs(v["target"], examples)
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
        if not post:
            post = [Check(kind="screen_changed")]
        out_steps.append(Step(id=sid, intent=intent, pre=pre, action=action, post=post,
                              risk=s.risk if s.risk in ("read", "reversible", "irreversible") else "read",
                              optional=(why := _optional_why(s, sid, intent)) is not None,
                              note=f"trace step {s.n}" + (f" (+{s.scrolls} scrolls)" if s.scrolls else "")
                              + (f" · {why}: optional" if why else "")))

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
    if final is not None:
        for o in spec.outputs:
            ex = _switch_state(o.near, o.example, final) or _extract_for(o.name, o.near, o.example, final, examples, data_values, steps)
            state = bool(ex and ex.switch)
            if ex is None and (ex := _state_text(o.near, final, data_values)) is not None:
                # An answer the agent inferred ("0" from "No contacts yet"): the routine reports the words it was read from.
                state = True
                report.warnings.append(f"output {o.name!r}: {o.example!r} was inferred from {o.near!r}; the routine reports that text")
            if ex is None:
                report.warnings.append(f"output {o.name!r}: {o.example!r} is not on the final screen, or nothing anchors it; dropped")
                continue
            outputs.append(o.name)
            # A value recorded as a number ("190 calories", "$13.49", "2:05 PM") must be one at run time too.
            extract[o.name] = ex.model_copy(update={"expect_digits": not state and bool(re.match(r"^[$€£]?\d", o.example.strip()))})
            if not state and not contains_value(got := _read_back(extract[o.name], final, examples), o.example):
                # Read it back from the screen the agent answered from: a routine that reads something else there is wrong.
                report.warnings.append(f"output {o.name!r} reads {got!r} on the run's own final screen, not {o.example!r}")
    question = bool(re.search(r"\?\s*$|^(what|how|when|where|which|who|is|are|do|does|did|can)\b", (run.get("goal") or "").strip(), re.I))
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
    # A trailing scroll toward an answer: reveal the first output's element.
    for st in out_steps:
        if st.action.kind == "scroll_until" and st.action.target is None:
            first = next(iter(extract.values()), None)
            st.action.target = first.locator if first and first.locator else Locator(text=first.near if first else None)
            st.post = [Check(kind="element_present", locator=st.action.target)]
    if extract:
        if not out_steps:
            # The answer is on the screen the app opens to ("How many miles do I have?"): outputs are read by steps, so a
            # routine with none would promise outputs it can never read. One read-only step carries them.
            out_steps.append(Step(id="read_answer", intent="Read the answer on the app's first screen",
                                  action=StepAction(kind="wait", seconds=0.3), risk="read", note="added: the answer is on the start screen"))
        out_steps[-1].extract = extract
    # After the outputs: an output read in the row an input names (a menu item's price) uses that input.
    limits = _add_witnesses(out_steps, steps, examples, inputs, report)

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
                       "trace_steps_kept": report.kept, "trace_steps_dropped": len(dropped), "cost_usd": round(report.cost_at_standard_usd, 4)},
    )
    return routine, report


def _consumed(step: Step, name: str) -> bool:
    slot = "{{" + name + "}}"
    a = step.action
    return slot in (a.value or "") or (a.target is not None and slot in a.target.model_dump_json()) \
        or any(slot in (x.card or "") for x in (step.extract or {}).values())  # the row an output is read in


def _add_witnesses(out_steps: list[Step], steps: list[TStep], examples: dict[str, str], inputs: dict[str, InputSpec],
                   report: CompileReport) -> list[str]:
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
            if ts is None:
                continue
            el = next((e for e in ts.before.numbered if contains_value(e.label, value)), None)
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

