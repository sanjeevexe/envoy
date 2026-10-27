"""Sign-in detection: where the agent must stop and hand the phone to the user.

Phase 0 showed the secure-window flag alone misses most sign-ins (Target, Chipotle, DoorDash and
Google's own sign-in are not FLAG_SECURE), so three signals are combined: a secure window, a
password field, or a sign-in pattern (an email/phone/code field next to a sign-in button).
"""

from __future__ import annotations

import re

from devices.types import ScreenState

_ID_FIELD = re.compile(r"(e-?mail|phone|mobile number|username|user name|account|verification code|one-?time code|\bcode\b|\botp\b)", re.I)
_SIGNIN_BUTTON = re.compile(r"^(sign in|log ?in|continue|next|verify|send code|sign in with .*|continue with (google|apple|facebook|email))$", re.I)
_SIGNIN_TITLE = re.compile(r"(sign in|log ?in|verify it.?s you|welcome back|enter (the )?code|two-step|2-step)", re.I)


def sign_in_reason(screen: ScreenState) -> str | None:
    """Why this screen is a sign-in the user must do, or None."""
    if screen.has_password_field:
        return "password field on screen"
    if screen.secure and any(e.editable for e in screen.elements if e.visible):
        return "secure window with a text field"
    fields = [e for e in screen.numbered if e.editable and _ID_FIELD.search(e.label or e.hint or e.resource_id)]
    buttons = [e for e in screen.numbered if e.kind == "Button" and _SIGNIN_BUTTON.match(e.label.strip())]
    titled = any(_SIGNIN_TITLE.search(e.label) for e in screen.numbered if e.kind == "Text")
    if fields and buttons and titled:
        return f"sign-in form ({fields[0].label or fields[0].resource_id!r} + {buttons[0].label!r})"
    return None
