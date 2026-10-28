"""Which phone runs a task (design doc, Device layer › Choosing which phone runs a task).

| Situation | Phone used |
| --- | --- |
| Default | an emulator: SkyLark (our test app) on envoy-test, real apps on envoy-real |
| You asked for your phone ("… on my phone", or the phone picked in the app) | your Android phone |
| The app is set to run on your phone (Settings › Phones) | your Android phone |
| The app refuses to run on an emulator (device integrity checks) | your Android phone |
| Your phone is needed but not connected | the emulator if the app works there; otherwise you're told, and nothing runs |

Using the real phone always waits for your yes first (the runner asks); this module only decides where.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

SKYLARK = "com.skylark.air"
TEST_EMULATOR, REAL_EMULATOR = "envoy-test", "envoy-real"

# Apps that refuse to run on an emulator (Phase 0: Uber Eats won't install: "your device isn't compatible").
EMULATOR_REFUSED = {"com.ubercab.eats": "Uber Eats"}

_ON_MY_PHONE = re.compile(r"\b(?:on|using|use|with)\s+my\s+(?:android(?:\s+phone)?|real\s+phone|phone|pixel|galaxy)\b", re.I)


def asks_for_phone(text: str) -> bool:
    """The request names the user's own phone ("check me in on my phone")."""
    return bool(_ON_MY_PHONE.search(text or ""))


def strip_phone_words(goal: str) -> str:
    """The goal without "on my phone", so routine matching and the agent see only the task."""
    return re.sub(r"\s{2,}", " ", _ON_MY_PHONE.sub("", goal)).strip(" ,.") or goal


@dataclass
class Choice:
    device: str | None  # a device id from the pool, or None when nothing can run
    reason: str
    real_phone: bool = False
    error: str | None = None  # why nothing runs


def choose(app: str | None, *, request: str = "", asked: str | None = None, phone_apps: list[str] | None = None,
           phones: list[dict[str, Any]] | None = None) -> Choice:
    """`asked`: "phone", "emulator", "auto"/None, or a device id, from the request itself. `phones`: connected phones
    from the pool ({id, model, state}); only state "device" can be used."""
    phones = phones or []
    usable = [p for p in phones if p.get("state") == "device"]
    unauthorized = [p for p in phones if p.get("state") == "unauthorized"]
    emulator = TEST_EMULATOR if not app or app == SKYLARK else REAL_EMULATOR
    if asked and asked not in ("phone", "emulator", "auto"):  # a specific device id
        is_phone = asked.startswith("phone-")
        if is_phone and not any(p["id"] == asked for p in usable):
            return Choice(None, "you picked that phone", error=_not_connected(unauthorized))
        return Choice(asked, "you picked it", real_phone=is_phone)
    if asked == "emulator":
        return Choice(emulator, "you asked for an emulator")

    why = None
    if asked == "phone" or asks_for_phone(request):
        why = "you asked for your phone"
    elif app and app in (phone_apps or []):
        why = "set to run on your phone"
    elif app in EMULATOR_REFUSED:
        why = f"{EMULATOR_REFUSED[app]} doesn't run on an emulator"
    if why is None:
        return Choice(emulator, "the default: an emulator keeps your phone free")
    if usable:
        p = usable[0]
        return Choice(p["id"], f"{why} ({p.get('model') or 'Android phone'})", real_phone=True)
    if why.startswith("set to run"):
        return Choice(emulator, f"{why}, but it isn't connected: using the emulator")
    return Choice(None, why, error=_not_connected(unauthorized))


def _not_connected(unauthorized: list[dict[str, Any]]) -> str:
    if unauthorized:
        return "Your phone is connected but hasn't allowed USB debugging yet: unlock it and tap Allow."
    return "Your Android phone isn't connected: plug it in (or pair it for wireless debugging) and try again."
