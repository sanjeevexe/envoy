"""Redaction before anything is stored (design doc, Safety › Redaction before anything is stored).

Removes card numbers (pattern + Luhn checksum), sign-in and verification codes, government ID numbers
and password-field contents from screen text, email text and fact values. Also decides which apps may be
remembered at all (finance, health, messaging and password managers are blocked by default).
"""

from __future__ import annotations

import re

from devices.screen import format_line
from devices.types import ScreenState

_CARD = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CODE_CONTEXT = re.compile(r"((?:verification|security|sign[- ]?in|one[- ]?time|login|access|otp)\s*(?:code|pin|passcode)?\s*(?:is|:)?\s*)(\d{4,8})\b", re.I)
_PASSPORT = re.compile(r"(passport\s*(?:no\.?|number|#)?\s*:?\s*)([A-Z0-9]{6,9})\b", re.I)

# Blocked from memory unless the user opts in (Play Store categories map here too).
BLOCKED_PACKAGES = {
    "com.chase.sig.android", "com.wf.wellsfargomobile", "com.infonow.bofa", "com.venmo", "com.paypal.android.p2pmobile",
    "com.squareup.cash", "com.coinbase.android", "com.google.android.apps.walletnfcrel",
    "com.whatsapp", "com.google.android.apps.messaging", "org.thoughtcrime.securesms", "com.facebook.orca",
    "com.x8bit.bitwarden", "com.agilebits.onepassword", "com.google.android.apps.authenticator2",
    "com.cvs.launchers.cvs", "com.walgreens.android", "com.myfitnesspal.android",
}


def luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def redact_text(text: str) -> str:
    def card(m: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        return "[card number]" if 13 <= len(digits) <= 19 and luhn(digits) else m.group(0)

    text = _CARD.sub(card, text)
    text = _SSN.sub("[id number]", text)
    text = _CODE_CONTEXT.sub(lambda m: m.group(1) + "[code]", text)
    text = _PASSPORT.sub(lambda m: m.group(1) + "[id number]", text)
    return text


def allowed(package: str, allow: set[str] | None = None) -> bool:
    return package not in BLOCKED_PACKAGES or package in (allow or set())


def screen_text(screen: ScreenState) -> str:
    """The compact screen with password fields' contents removed and the rest redacted."""
    header = screen.compact.splitlines()[0] if screen.compact else f"App: {screen.package}"
    lines = [f"[{e.number}] {e.kind} [password field]" if e.password else format_line(e) for e in screen.numbered]
    return redact_text("\n".join([header, *lines]))
