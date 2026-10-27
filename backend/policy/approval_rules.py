"""When Envoy may take an irreversible step without asking (design doc, Safety › Approvals).

Three modes, set by the user for everything, per app, or per routine (the most specific wins):

- `always`: ask before every irreversible step.
- `unless_requested` (the default): don't ask when the step is what the user asked for. "Check me in" is the
  permission to tap "Confirm check-in" for that trip, so Envoy does it and says so afterwards.
- `never` (routines only): a standing approval. The routine's own irreversible steps run without asking, whoever
  started it (a trigger, an MCP client): "check me in automatically 24 hours before every flight".

Whatever the mode, Envoy still asks when:
- **money is involved** (pay, buy, order, subscribe, a price on the button, a card or total on the screen);
- the step is **not what was asked**: the button's own words (minus "confirm", "continue"…) must be in the request,
  so "Cancel trip" during a check-in asks;
- the **details differ**: names, codes and numbers in the request (Denver, SL 1190, 21C) must be on the screen or in
  the task's inputs;
- the request **didn't come from the user directly** (a trigger, an email, an AI client over MCP), unless a standing
  approval covers the routine.
All of this is decided by rules, not by a model, so a screen that tricks the model can't approve anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from routines.screens import contains_value, fold

MODES = ("always", "unless_requested", "never")
DEFAULT_MODE = "unless_requested"
# Where a request comes straight from the user: their own words in the web app, chat, voice or the iPhone.
DIRECT_SOURCES = {"web", "chat", "voice", "iphone"}

_MONEY_WORDS = re.compile(
    r"\b(pay|pay now|place (your )?order|order now|purchase|buy( now)?|checkout|check out now|transfer|donate|tip|"
    r"subscribe|sign up and pay|add to (cart|bag)|upgrade for|pagar|comprar|payer|acheter|bezahlen|kaufen|支付|购买)\b", re.I)
_PRICE = re.compile(r"[$€£¥₹]\s?\d|\b\d+[.,]\d{2}\s?(usd|eur|gbp)\b", re.I)
_MONEY_SCREEN = re.compile(r"(card ending|will be charged|order total|payment method|total due|billing address|amount due)", re.I)
# Words that say "go ahead" but not *what*: they don't count as naming the action.
_GENERIC = {"confirm", "continue", "submit", "yes", "ok", "okay", "done", "now", "next", "finish", "complete", "proceed", "go",
            "apply", "save", "agree", "accept", "i", "my", "me", "the", "a", "an", "to", "for", "and", "of", "on", "in", "it",
            "this", "that", "your", "please", "all"}
_DETAIL = re.compile(r"\b([A-Z]{2,3}\s?\d{2,5}|\d{1,3}[A-Z]\b|[A-Z]\d{1,3}\b|\d{1,2}/\d{1,2}(?:/\d{2,4})?|[A-Z][a-z]{2,}(?:\s[A-Z][a-z]{2,})*)")
_NOT_DETAILS = {"check", "please", "can", "could", "would", "will", "the", "my", "what", "when", "where", "add", "change", "book",
                "cancel", "send", "find", "get", "show", "tell", "look", "skylark", "amazon", "target", "starbucks", "chipotle",
                "doordash", "gmail", "google", "maps", "chrome", "youtube", "envoy", "muse", "i"}


@dataclass
class ApprovalRules:
    default: str = DEFAULT_MODE
    apps: dict[str, str] = field(default_factory=dict)  # package → mode
    routines: dict[str, str] = field(default_factory=dict)  # routine name → mode

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "ApprovalRules":
        d = d or {}
        ok = lambda m, allow_never: m in MODES and (allow_never or m != "never")  # noqa: E731
        return cls(default=d.get("default") if ok(d.get("default"), False) else DEFAULT_MODE,
                   apps={k: v for k, v in (d.get("apps") or {}).items() if ok(v, False)},
                   routines={k: v for k, v in (d.get("routines") or {}).items() if ok(v, True)})

    def to_dict(self) -> dict[str, Any]:
        return {"default": self.default, "apps": self.apps, "routines": self.routines}

    def mode_for(self, app: str | None, routine: str | None) -> str:
        if routine and routine in self.routines:
            return self.routines[routine]
        if app and app in self.apps:
            return self.apps[app]
        return self.default


@dataclass
class AutoApproval:
    by: str  # "your request" or "standing approval"
    why: str


def _words(s: str) -> set[str]:
    s = fold(s).lower().replace("check-in", "check in").replace("checkin", "check in")
    return {w[:-1] if len(w) > 4 and w.endswith("s") else w for w in re.findall(r"[a-z0-9]+", s)}


def involves_money(target: str, screen_text: str) -> bool:
    return bool(_MONEY_WORDS.search(target) or _PRICE.search(target) or _MONEY_SCREEN.search(screen_text))


def names_action(request: str, target: str) -> bool:
    """The button's own words (beyond 'confirm', 'continue'…) all appear in the request."""
    action = _words(target) - _GENERIC
    return bool(action) and action <= _words(request)


def details_missing(request: str, context: str) -> list[str]:
    """Names, codes and numbers the request gives that the screen (or the task's inputs) doesn't show."""
    first = request.strip().split(" ", 1)[0]
    out = []
    for m in _DETAIL.finditer(request):
        d = m.group(1).strip()
        if d == first or d.lower() in _NOT_DETAILS or all(w.lower() in _NOT_DETAILS for w in d.split()):
            continue
        if not contains_value(context, d):
            out.append(d)
    return out


def decide(rules: ApprovalRules, *, goal: str, source: str, app: str | None, routine: str | None, origin: str,
           target: str, screen_text: str, inputs: dict[str, str] | None = None) -> AutoApproval | None:
    """An approval the user already gave (by asking, or by a standing approval), or None: ask them."""
    if involves_money(target, screen_text):
        return None
    mode = rules.mode_for(app, routine)
    if mode == "always":
        return None
    if mode == "never" and routine and origin == "routine_step":
        return AutoApproval("standing approval", f"you set routine {routine} to run without asking")
    if source not in DIRECT_SOURCES:
        return None
    if not names_action(goal, target):
        return None
    if details_missing(goal, screen_text + " " + " ".join((inputs or {}).values())):
        return None
    return AutoApproval("your request", f'you asked: "{goal}"')
