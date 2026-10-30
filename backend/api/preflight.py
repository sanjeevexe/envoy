"""Before I start: what to expect from a task, said before Envoy starts it (docs/preflight-and-autofill.md).

    "Target blocks emulators: I'll ask to use your Pixel 5."
    "DoorDash asked you to sign in on envoy-real last time (Oct 27)."
    "The payment step will need your OK."
    "Using routine skylark_check_in_flight v3: usually 9 s, no model calls."

`check()` reads only what Envoy already knows: routing and the per-app phone settings (`api/routing.py`), the apps
that block emulators, the apps Envoy installed, the task history (sign-in hand-offs, install steps), the routine's
recorded runs, app notes, and the approval rules. It makes no model call, takes no device action and never raises, so
it is cheap enough for every task (the runner's `preflight` step), every offer's card before Yes, and MCP's
`heads_up` for Muse.

Each line is {kind, text, level}: kind is device, blocked, memory (your usual, memory/usual.py), install, signin, approval,
routine or app_note; level is info, warn or stop. At most five, the most important first. A stop line changes nothing
about the run: the runner already handles a missing phone; the line only says so up front.
"""

from __future__ import annotations

import re
import statistics
import time
from typing import Any

from api.devices import phone_ref
from api.install import app_named_in
from api.routing import SKYLARK, asks_for_phone, blocks_emulator, choose
from policy.approval_rules import DIRECT_SOURCES, ApprovalRules, involves_money, names_action

MAX_LINES = 5
LEVELS = ("stop", "warn", "info")
KINDS = ("blocked", "device", "memory", "signin", "install", "approval", "routine", "app_note")
OK = ("done", "agent_done", "done_unverified")

# A goal that buys something: its payment step will ask, whatever the mode (approval_rules: money always asks).
_BUYS = re.compile(r"\b(order|buy|purchase|pay for|book|reserve|subscribe to|donate)\s+(a|an|the|my|me|some|one|two|\d)\b", re.I)
# A goal that does something that can't be taken back (for an agent task, whose steps aren't known before it runs).
_ACTS = re.compile(r"\b(post|share|publish|send|submit|confirm|check (me )?in|book|cancel|delete|remove|order|pay|buy|reserve|"
                   r"reply|message|transfer|donate|subscribe)\b", re.I)
# App notes that predict an obstacle: a pop-up, a prompt, a bot check, a sign-in, an ad in the way, a slow screen.
_OBSTACLE = re.compile(r"(pop-?up|dialog|prompt|banner|modal|overlay|interstitial|bottom sheet|\bads?\b|sponsored|location|"
                       r"permission|bot check|captcha|human|verif|sign[ -]?in|log[ -]?in|onboarding|welcome|tutorial|cookie|consent|"
                       r"must (be )?(choose|chosen|pick|select)|choose a store|asks? (you |for |to )|blocks?\b|slow|takes? (a while|\d)|"
                       r"loading|spinner|update)", re.I)
# Verbs a button label starts with, said as what Envoy will be doing: "Confirm check-in" → "Confirming check-in".
_VERBS = {"confirm", "place", "pay", "buy", "purchase", "submit", "send", "post", "share", "publish", "book", "reserve", "cancel",
          "delete", "remove", "check", "complete", "order", "subscribe", "donate", "transfer", "uninstall", "erase", "reset", "clear",
          "call", "accept", "agree", "apply", "save", "add", "change", "update", "request", "schedule", "finish", "start", "reply",
          "sign", "get", "make", "upgrade", "join", "follow", "unfollow", "block", "report", "archive", "approve", "decline"}
_DOUBLE = {"submit", "commit", "admit", "permit", "omit", "regret"}


def check(runner: Any, goal: str, *, request: str | None = None, source: str | None = None, app: str | None = None,
          routine: Any = None, inputs: dict[str, str] | None = None, phone: str | None = None,
          phone_ok: str | None = None) -> list[dict[str, str]]:
    """What to expect from this task, before it starts. `runner` is the API's TaskRunner. `routine` is a routine's name
    (or the Routine itself, as the runner has it). `phone` is as `runner.start` takes it; `phone_ok` the phone your yes
    already covers (an accepted offer). Never raises: whatever was worked out before a failure is returned."""
    lines: list[dict[str, str]] = []
    try:
        _check(lines, runner, goal or "", request=request, source=source, app=app, routine=routine, phone=phone, phone_ok=phone_ok)
    except Exception:  # noqa: BLE001 - a heads-up never breaks what it is about
        pass
    return _ranked(lines)


def _ranked(lines: list[dict[str, str]]) -> list[dict[str, str]]:
    seen, out = set(), []
    for ln in sorted(lines, key=lambda x: (LEVELS.index(x["level"]), KINDS.index(x["kind"]))):
        if ln["text"] not in seen:
            seen.add(ln["text"])
            out.append(ln)
    return out[:MAX_LINES]


def _line(lines: list[dict[str, str]], kind: str, text: str, level: str = "info") -> None:
    lines.append({"kind": kind, "text": text, "level": level})


def _check(lines: list[dict[str, str]], runner: Any, goal: str, *, request: str | None, source: str | None, app: str | None,
           routine: Any, phone: str | None, phone_ok: str | None) -> None:
    store = runner.store
    learned = _call(runner, "_learned", {})
    names = _call(runner, "_learned_names", {})
    rt = _routine(runner, routine)
    if rt is not None:
        app = app or rt.app
    if not app:
        from api.runner import app_for  # here, not at the top: the runner imports this module
        app = app_for(goal, names)
    named = None if app else app_named_in(goal)
    if asks_for_phone(goal) or asks_for_phone(request or ""):
        phone = phone or "phone"
    rules = store.setting("phone_apps", []) or []
    phones = list((getattr(runner.pool, "phones", None) or {}).values())
    choice = choose(app, asked=phone, phone_apps=rules, phones=phones, learned=learned, named=named)
    label = _label(runner, app) if app else (named or "the app")
    blocked = blocks_emulator(app, rules, learned)

    for section in (_device, _usual, _signin, _install, _approval, _routine_line, _app_notes):
        try:
            section(lines, runner=runner, goal=goal, request=request, source=source, app=app, routine=rt, phone=phone,
                    phone_ok=phone_ok, choice=choice, label=label, blocked=blocked, phones=phones, named=named, names=names)
        except Exception:  # noqa: BLE001 - one part failing costs only its own line
            continue


# ---- what it took from memory ---------------------------------------------------------------------


def _usual(lines: list[dict[str, str]], *, runner: Any, goal: str, request: str | None, **_: Any) -> None:
    """"My usual from <place>": the order you told Envoy (memory/usual.py), so you see what it will order."""
    from memory.usual import resolve
    u = resolve(runner.memory, f"{goal}\n{request or ''}")
    if u is not None:
        _line(lines, "memory", f"Your usual from {u.place}: {u.order}" + (f", on {u.app}" if u.app else "") + ".")


# ---- where it runs ------------------------------------------------------------------------------


def _device(lines: list[dict[str, str]], *, runner: Any, app: str | None, phone: str | None, phone_ok: str | None, choice: Any,
            label: str, blocked: str | None, phones: list[dict[str, Any]], **_: Any) -> None:
    unauthorized = any(p.get("state") == "unauthorized" for p in phones)
    if choice.device is None:
        who = f"{label} needs your Android phone" if blocked else "You asked for your phone"
        _line(lines, "blocked", f"{who}, but it hasn't allowed USB debugging yet." if unauthorized else f"{who}, and it isn't connected.", "stop")
        return
    if not choice.real_phone:
        if choice.reason.startswith("set to run"):  # set to your phone, which isn't connected: the emulator instead
            _line(lines, "device", f"{label} is set to run on your phone, which isn't connected: I'll use {choice.device} instead.")
        return
    ref = phone_ref(next((p for p in phones if p.get("id") == choice.device), None))  # "your Pixel 5", or the name you gave it
    if phone_ok and phone_ok == choice.device:
        _line(lines, "device", f"{label} blocks emulators, so I'll use {ref} (you said yes)." if blocked
              else f"I'll use {ref} (you said yes).")
    elif blocked:
        _line(lines, "device", f"{label} blocks emulators: I'll ask to use {ref}.", "warn")
    elif phone == "phone":
        _line(lines, "device", f"You asked for your phone: I'll check with you before using {ref}.", "warn")
    elif choice.reason.startswith("set to run"):
        _line(lines, "device", f"{label} is set to run on your phone: I'll ask before using {ref}.", "warn")
    else:
        _line(lines, "device", f"I'll ask before using {ref}.", "warn")


# ---- sign-ins and installs, from the task history ------------------------------------------------


def _history(store: Any, app: str, device: str, limit: int = 1) -> list[dict[str, Any]]:
    """The latest tasks of `app` that ran on `device`, newest first: with whether each was handed to you for the app's
    sign-in (not the Play Store's), whether the app was missing, and whether it was installed then."""
    q = """SELECT t.id, t.created_at, t.status,
             EXISTS(SELECT 1 FROM steps s WHERE s.task_id = t.id AND json_extract(s.data, '$.kind') = 'handoff'
                    AND json_extract(s.data, '$.text') LIKE 'sign-in needed%' AND json_extract(s.data, '$.text') NOT LIKE '%Play Store%') AS signin,
             EXISTS(SELECT 1 FROM steps s WHERE s.task_id = t.id AND json_extract(s.data, '$.kind') = 'note'
                    AND json_extract(s.data, '$.text') LIKE '%isn''t on this phone%') AS missing,
             EXISTS(SELECT 1 FROM steps s WHERE s.task_id = t.id AND json_extract(s.data, '$.kind') = 'note'
                    AND json_extract(s.data, '$.text') LIKE 'installed %') AS installed
           FROM tasks t WHERE t.app = ? AND t.device = ? ORDER BY t.created_at DESC LIMIT ?"""
    with store.lock:
        return [dict(r) for r in store.db.execute(q, (app, device, limit)).fetchall()]


def _where(device: str, phones: list[dict[str, Any]]) -> str:
    if device.startswith("phone-"):
        p = next((p for p in phones if p.get("id") == device), None)
        return phone_ref(p) if p else "your phone"
    return device


def _day(ts: float) -> str:
    t = time.localtime(ts)
    return f"{time.strftime('%b', t)} {t.tm_mday}"


def _signin(lines: list[dict[str, str]], *, runner: Any, app: str | None, choice: Any, label: str, phones: list[dict[str, Any]],
            **_: Any) -> None:
    if not app or choice.device is None:
        return
    last = _history(runner.store, app, choice.device)
    if last and last[0]["signin"]:  # the last run there needed you to sign in; a run since that didn't means you're signed in
        _line(lines, "signin", f"{label} asked you to sign in on {_where(choice.device, phones)} last time ({_day(last[0]['created_at'])}).", "warn")


def _install(lines: list[dict[str, str]], *, runner: Any, app: str | None, choice: Any, label: str, named: str | None,
             names: dict[str, str], **_: Any) -> None:
    """Only on an emulator (on your phone, you install apps yourself), and only when Envoy knows without asking the phone:
    the last run there found the app missing and didn't install it, or the request names an app Envoy has never used."""
    if choice.device is None or choice.real_phone or not getattr(runner, "install_apps", True) or app == SKYLARK:
        return
    if app:
        last = _history(runner.store, app, choice.device)
        if last and last[0]["missing"] and not last[0]["installed"]:
            _line(lines, "install", f"{label} wasn't on {choice.device} last time: I'll install it from the Play Store (free apps only).")
    elif named:
        _line(lines, "install", f"I haven't used {named} on {choice.device} before: if it isn't there, I'll install it from the Play Store "
                                "(free apps only).")


# ---- approvals ----------------------------------------------------------------------------------


def _doing(label: str) -> str:
    """A button label as what Envoy will be doing: "Confirm check-in" → "Confirming check-in"; else "Tapping “OK”"."""
    words = label.strip().split()
    if not words or words[0].lower() not in _VERBS:
        return f"Tapping “{label.strip()}”"
    w = words[0].lower()
    if w.endswith("ie"):
        g = w[:-2] + "ying"
    elif w.endswith("e") and not w.endswith(("ee", "ye", "oe")):
        g = w[:-1] + "ing"
    elif w in _DOUBLE or re.fullmatch(r"[^aeiou]*[aeiou][bdgmnprt]", w):
        g = w + w[-1] + "ing"
    else:
        g = w + "ing"
    rest = [x if (x.isupper() and len(x) > 1) or any(c.isdigit() for c in x) else x.lower() for x in words[1:]]
    return " ".join([g.capitalize(), *rest])


def _step_label(step: Any) -> str:
    t = step.action.target
    return ((t.text or t.text_has or t.desc or t.hint) if t is not None else None) or step.intent


def _approval(lines: list[dict[str, str]], *, runner: Any, goal: str, request: str | None, source: str | None, app: str | None,
              routine: Any, **_: Any) -> None:
    """What approvals/approval_rules.decide() will do with the irreversible steps, as far as it can be known before the
    screens are seen: money always asks; then the mode; then who asked and whether their words name the step."""
    words = request or goal
    rules = ApprovalRules.from_dict(runner.store.setting("approval_rules"))
    mode = rules.mode_for(app, routine.routine if routine is not None else None)
    steps = [_step_label(s) for s in (routine.steps if routine is not None else []) if s.risk == "irreversible"]
    if involves_money(goal, "") or any(involves_money(s, "") for s in steps):
        _line(lines, "approval", "The payment step will need your OK.")
    elif routine is None and _BUYS.search(goal):
        _line(lines, "approval", "Any payment will need your OK.")
    said = 0
    for s in dict.fromkeys(steps):
        if involves_money(s, "") or said == 2:
            continue
        said += 1
        doing = _doing(s)
        if mode == "always":
            _line(lines, "approval", f"{doing} will need your OK.")
        elif mode == "never":
            _line(lines, "approval", f"{doing} will go ahead: you set this routine to run without asking.")
        elif source not in DIRECT_SOURCES:
            _line(lines, "approval", f"{doing} will wait for your OK.")
        elif names_action(words, s):
            _line(lines, "approval", f"{doing} will go ahead: you asked for it.")
        else:
            _line(lines, "approval", f"{doing} will need your OK.")
    if routine is None and source not in DIRECT_SOURCES and source is not None and _ACTS.search(goal):
        _line(lines, "approval", "Anything that can't be undone will wait for your OK.")


# ---- the routine, and what Envoy knows about the app -----------------------------------------------


def _routine(runner: Any, routine: Any) -> Any:
    if routine is None or routine == "":
        return None
    if not isinstance(routine, str):
        return routine
    from routines.lifecycle import version_for_run
    try:
        return version_for_run(runner.routines, routine)
    except Exception:  # noqa: BLE001 - an unknown routine: the runner says so when it plans
        return None


def _secs(s: float) -> str:
    return f"{s:.0f} s" if s >= 2 else f"{s:.1f} s"


def _routine_line(lines: list[dict[str, str]], *, runner: Any, routine: Any, **_: Any) -> None:
    if routine is None:
        return
    head = f"Using routine {routine.routine} v{routine.version}"
    idx = runner.routines.index(routine.routine)
    runs = [r for r in idx.get("runs", []) if r.get("status") in OK and r.get("duration_s") is not None][-10:]
    if runs:
        secs = statistics.median(r["duration_s"] for r in runs)
        calls = statistics.median(r.get("model_calls") or 0 for r in runs)
        said = "no model calls" if calls == 0 else ("about 1 model call" if calls <= 1 else f"about {calls:.0f} model calls")
        _line(lines, "routine", f"{head}: usually {_secs(secs)}, {said}.")
        return
    cases = [c for v in idx.get("versions", []) if v.get("version") == routine.version
             for c in ((v.get("verification") or {}).get("cases") or []) if c.get("passed") and c.get("duration_s") is not None]
    if cases:
        _line(lines, "routine", f"{head}: {_secs(cases[0]['duration_s'])} when I tested it, no model calls.")
    else:
        _line(lines, "routine", f"{head}.")


def _app_notes(lines: list[dict[str, str]], *, runner: Any, app: str | None, **_: Any) -> None:
    """The one or two notes that predict an obstacle (a pop-up, a location prompt, a bot check), most confirmed first."""
    from memory.app_notes import enabled
    notes = getattr(runner, "app_notes", None)
    if not app or notes is None or not enabled():
        return
    for n in [n for n in notes.list(app) if _OBSTACLE.search(n.text)][:2]:
        _line(lines, "app_note", f"From earlier runs: {n.text}")


# ---- helpers ------------------------------------------------------------------------------------------


def _call(runner: Any, name: str, default: Any) -> Any:
    fn = getattr(runner, name, None)
    try:
        return fn() if fn is not None else default
    except Exception:  # noqa: BLE001
        return default


def _label(runner: Any, app: str) -> str:
    """The app's name: as cross-app answers say it ("Google Maps", "DoorDash"), else as the runner does."""
    from api.crossapp import NAMES  # here: crossapp imports the runner, which imports this module
    if app in NAMES:
        return NAMES[app]
    name = getattr(runner, "_name", None)
    return name(app) if name is not None else app.rsplit(".", 1)[-1].capitalize()
