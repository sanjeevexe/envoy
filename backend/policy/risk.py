"""Risk classification: every action is labeled read / reversible / irreversible before it runs.

Three independent signals vote (design doc, Safety). Any one saying "irreversible" pauses the run:
  1. rules: the target's text or resource ID matches an irreversible verb (pay, place order, confirm, share/post/publish, …)
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
    r"uninstall|erase( all)?( data)?|factory reset|wipe|reset (settings|all|phone|device|apps?|app preferences|network)|"
    r"remove (account|device|card|payment method)|clear (all )?(data|storage|history|browsing data)|"
    r"pagar|comprar|confirmar|enviar|eliminar|payer|acheter|confirmer|envoyer|supprimer|"
    r"bezahlen|kaufen|bestätigen|senden|löschen|支付|购买|确认|发送|删除"
    r")\b",
    re.IGNORECASE,
)
# Resource-ID fragments that mean the same, for buttons without readable text.
_IRREVERSIBLE_ID = re.compile(r"(^|[_-])(pay|purchase|checkout|confirm|submit|send|delete|place[_-]order|buy|book|cancel[_-](trip|order|booking))([_-]|$)", re.I)
# A label that says nothing about what it does ("Submit", "OK"): web forms label every button that way (Amazon's Add to Cart
# and Buy Now are both "Submit"), so an ID that plainly names a reversible action speaks for it instead.
_GENERIC = re.compile(r"^(submit|ok|okay|continue|go|done)$", re.I)
_REVERSIBLE_ID = re.compile(r"(^|[_-])(add[_-]to[_-](cart|bag|basket|list|wishlist)|wishlist|save[_-]for[_-]later|search|filter)([_-]|$)", re.I)
# A button that is only a price ("$4.99", "€7"): it buys something.
_PRICE = re.compile(r"^\s*(US\s?)?[$€£¥₹]\s?\d[\d,]*(\.\d{1,2})?(\s*/\s*(mo|month|yr|year|wk|week))?\s*$", re.I)
# A dialog or page asking to confirm something that can't be taken back: its positive button (often a bare "OK") is the act.
_DESTRUCTIVE = re.compile(
    r"((do you|are you sure you) want to|want to) (uninstall|delete|remove|erase|reset|unsubscribe|cancel)|"
    r"will (permanently )?(delete|erase|remove|be deleted|be erased|be removed)|(data|everything|all .{0,30}) will be (deleted|erased|lost|removed)|"
    r"permanently (delete|remove|erase)|factory reset|can.?t be undone|cannot be undone|can.?t undo|cannot undo|"
    r"this will (reset|erase|delete|remove|wipe)",
    re.IGNORECASE,
)
# A button that places a phone call (the dialer's dial button, "Call store"): it reaches a person outside the phone.
_CALL = re.compile(r"^(call|dial|voice call|video call|call now|place (a )?call|call (the )?(store|restaurant|driver|support|us|back)|"
                   r"call \+?[\d\s().-]{5,})$", re.I)
# A button whose whole label publishes something for others to see ("Share" on Instagram's last screen, "Post", "Publish"):
# a public post can't be taken back. Whole labels only, so "Share your feedback" or a "Posts" tab don't count; a Share that
# only opens a share sheet (YouTube) is asked about too, which errs on the safe side.
_PUBLISH = re.compile(r"^(share|post|publish)( (now|it|post|reel|story|to (your )?(feed|story)))?$", re.I)
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


def _under(screen: ScreenState, x: int | None, y: int | None) -> Element | None:
    """The listed element under a point (the smallest that contains it): a tap at a point is judged like a tap on it."""
    if x is None or y is None:
        return None
    hits = [e for e in screen.numbered if e.bounds[0] <= x <= e.bounds[2] and e.bounds[1] <= y <= e.bounds[3]]
    return min(hits, key=lambda e: e.area, default=None)


def _main_button(screen: ScreenState) -> Element | None:
    """The screen's likely primary action: the lowest enabled, labeled button."""
    buttons = [e for e in screen.numbered if e.kind == "Button" and e.enabled and e.label]
    return max(buttons, key=lambda e: e.bounds[1], default=None)


def classify(action: Action, screen: ScreenState, model_risk: Risk | None) -> RiskVerdict:
    reasons: list[str] = []
    level: Risk = "read" if action.kind in _READ_KINDS else "reversible"
    screen_text = " ".join(_target_text(e) for e in screen.numbered)
    checkout = bool(_CHECKOUT.search(screen_text))
    destructive = bool(_DESTRUCTIVE.search(screen_text))

    target: Element | None = None
    if action.element is not None and 1 <= action.element <= len(screen.numbered):
        target = screen.numbered[action.element - 1]
    if action.kind == "tap_point":
        # A point instead of an element number: whatever is under it is what gets tapped (drawn screens have nothing).
        target = _under(screen, action.x, action.y)
    if action.kind == "type" and action.submit:
        # Pressing Enter can place an order or send a message: judge by the screen's main button.
        target = _main_button(screen) or target

    if target is not None and action.kind in ("tap", "long_press", "type", "tap_point"):
        text = _target_text(target)
        if action.kind != "type" or action.submit:
            rid = target.resource_id.split("/")[-1]
            named_reversible = _GENERIC.match(target.label.strip()) and _REVERSIBLE_ID.search(rid) and not _IRREVERSIBLE_ID.search(rid)
            if _IRREVERSIBLE.search(text) and not _SAFE.match(target.label.strip()) and not named_reversible:
                reasons.append(f"rule: target says {target.label!r}")
            elif _IRREVERSIBLE_ID.search(rid):
                reasons.append(f"rule: target id {target.resource_id!r}")
            elif _PRICE.match(target.label or ""):
                reasons.append(f"rule: target is a price {target.label!r}")
            elif any(_CALL.match(x.strip()) for x in (target.label, target.desc) if x) and not target.editable:
                reasons.append(f"rule: target places a call {target.label or target.desc!r}")
            elif any(_PUBLISH.match(x.strip()) for x in (target.label, target.desc) if x) and not target.editable:
                reasons.append(f"rule: target publishes {target.label or target.desc!r}")
            if checkout and target.kind == "Button" and not _SAFE.match(target.label.strip()):
                reasons.append("screen: payment or final-confirmation step")
            elif destructive and target.kind == "Button" and not _SAFE.match(target.label.strip()):
                reasons.append("screen: confirming something that can't be taken back")
    if model_risk == "irreversible":
        reasons.append("model: labeled irreversible")
    if model_risk == "reversible" and level == "read":
        level = "reversible"
    if reasons:
        level = "irreversible"
    return RiskVerdict(level, reasons)
