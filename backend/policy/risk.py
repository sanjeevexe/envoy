"""Risk classification: every action is labeled read / reversible / irreversible before it runs.

Three independent signals vote (design doc, Safety). Any one saying "irreversible" pauses the run:
  1. rules: the target's text or resource ID matches an irreversible verb (pay, place order, confirm, …)
  2. screen context: the screen looks like a payment or final-confirmation step
  3. model judgment: the risk label the step model returned with the action
Signals 1 and 2 don't depend on the model, so a screen that tricks the model can't skip the gate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from devices.types import Action, Element, ScreenState

Risk = Literal["read", "reversible", "irreversible"]

# Irreversible verbs, in several languages. Plain "Cancel" (dismiss a dialog) is deliberately not here;
# cancelling a thing ("Cancel trip", "Cancel order") is.
_IRREVERSIBLE = re.compile(
    r"\b("
    r"pay|pay now|place (your )?order|order now|purchase|buy( now)?|checkout|check out now|"
    r"confirm|confirm (and )?(pay|order|booking|purchase|check-?in|seat)|complete (check-?in|purchase|order|booking)|"
    r"submit|send|transfer|donate|book (now|it|flight|trip|room)|reserve|"
    r"delete|remove account|cancel (trip|order|booking|reservation|flight|subscription|membership)|"
    r"unsubscribe|sign up and pay|subscribe|"
    r"pagar|comprar|confirmar|enviar|eliminar|payer|acheter|confirmer|envoyer|supprimer|"
    r"bezahlen|kaufen|bestätigen|senden|löschen|支付|购买|确认|发送|删除"
    r")\b",
    re.IGNORECASE,
)
# Resource-ID fragments that mean the same, for buttons without readable text.
_IRREVERSIBLE_ID = re.compile(r"(^|_)(pay|purchase|checkout|confirm|submit|send|delete|place_order|buy|book|cancel_(trip|order|booking))(_|$)", re.I)
# Labels that are safe whatever the screen says (dismissing, going back, declining).
_SAFE = re.compile(r"^(back|navigate up|close|cancel|keep\b.*|not now|no,? thanks|don.?t allow|deny|dismiss|later|maybe later|skip|done)$", re.I)
# Screen text that means money or a final step is involved.
_CHECKOUT = re.compile(
    r"(card ending|will be charged|order total|payment method|review your order|place your order|checkout|"
    r"total due|billing address|this can.?t be undone|cannot be undone)",
    re.IGNORECASE,
)
_READ_KINDS = {"scroll", "swipe", "back", "home", "wait", "launch"}


@dataclass
class RiskVerdict:
    level: Risk
    reasons: list[str] = field(default_factory=list)

    @property
    def irreversible(self) -> bool:
        return self.level == "irreversible"


def _target_text(e: Element) -> str:
    return " ".join(x for x in (e.label, e.text, e.desc) if x)


def _main_button(screen: ScreenState) -> Element | None:
    """The screen's likely primary action: the lowest enabled, labeled button."""
    buttons = [e for e in screen.numbered if e.kind == "Button" and e.enabled and e.label]
    return max(buttons, key=lambda e: e.bounds[1], default=None)


def classify(action: Action, screen: ScreenState, model_risk: Risk | None) -> RiskVerdict:
    reasons: list[str] = []
    level: Risk = "read" if action.kind in _READ_KINDS else "reversible"
    screen_text = " ".join(_target_text(e) for e in screen.numbered)
    checkout = bool(_CHECKOUT.search(screen_text))

    target: Element | None = None
    if action.element is not None and 1 <= action.element <= len(screen.numbered):
        target = screen.numbered[action.element - 1]
    if action.kind == "type" and action.submit:
        # Pressing Enter can place an order or send a message: judge by the screen's main button.
        target = _main_button(screen) or target

    if target is not None and action.kind in ("tap", "long_press", "type"):
        text = _target_text(target)
        if action.kind != "type" or action.submit:
            if _IRREVERSIBLE.search(text) and not _SAFE.match(target.label.strip()):
                reasons.append(f"rule: target says {target.label!r}")
            elif _IRREVERSIBLE_ID.search(target.resource_id.split("/")[-1]):
                reasons.append(f"rule: target id {target.resource_id!r}")
            if checkout and target.kind == "Button" and not _SAFE.match(target.label.strip()):
                reasons.append("screen: payment or final-confirmation step")
    if model_risk == "irreversible":
        reasons.append("model: labeled irreversible")
    if model_risk == "reversible" and level == "read":
        level = "reversible"
    if reasons:
        level = "irreversible"
    return RiskVerdict(level, reasons)
