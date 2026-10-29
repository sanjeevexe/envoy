"""Bot-check detection: a screen that asks the person to prove they're human (design doc, Safety › Hand-offs).

Envoy never tries to get past one: it hands the phone to the person. On an emulator a bot check usually means the app
blocks emulators, so the runner also moves the app to the person's own phone (api/routing.py). Phase 2 saw Target open
on HUMAN Security's "press and hold" screen (`HSBlockActivity`, an empty tree) on most fresh launches on envoy-real.
"""

from __future__ import annotations

import re

from devices.types import ScreenState

_WORDS = re.compile(r"press (&|and) hold|verify (that )?you('re| are) (a )?human|not a robot|captcha|are you a robot|unusual traffic", re.I)
_ACTIVITY = re.compile(r"(HSBlock|captcha|challenge)", re.I)
# How the agent (or a routine's hand-off) words one: "bot check (press and hold)", "human verification", "CAPTCHA".
_HANDOFF = re.compile(r"\bbot[ -]?check|\bbot detection|human verification|captcha|press (&|and) hold|not a robot|are you a robot", re.I)


def bot_check_reason(screen: ScreenState | None) -> str | None:
    """Why this screen is a bot check, or None: a known blocking activity, or a short screen that is mostly the
    challenge's words (a place page whose reviews mention "unusual traffic" is not one)."""
    if screen is None:
        return None
    if _ACTIVITY.search(screen.activity or ""):
        return f"bot check ({screen.activity.rsplit('.', 1)[-1]})"
    if len(screen.numbered) <= 15:
        hit = next((m for e in screen.numbered if (m := _WORDS.search(e.label or ""))), None)
        if hit is not None:
            return f"bot check ({hit.group(0).lower()})"
    return None


def is_bot_check_handoff(reason: str | None) -> bool:
    """A hand-off whose reason is a bot check (the agent's words, or this module's)."""
    return bool(reason and _HANDOFF.search(reason))
