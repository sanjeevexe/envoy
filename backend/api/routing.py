"""Which phone runs a task (design doc, Device layer › Choosing which phone runs a task).

| Situation | Phone used |
| --- | --- |
| Default | an emulator: SkyLark (our test app) on envoy-test, real apps on envoy-real (also one Envoy doesn't know yet, named in the request) |
| You asked for your phone ("… on my phone", or the phone picked in the app) | your Android phone |
| The app is set to run on your phone (Settings › Phones) | your Android phone |
| The app blocks emulators: known to (`emulator_blocked.json`), or Envoy found out (a bot check on the emulator) | your Android phone |
| Your phone is needed but not connected | the emulator if the app works there; otherwise you're told, and nothing runs |

Using the real phone always waits for your yes first (the runner asks); this module only decides where.

Apps that block emulators come from two places. `emulator_blocked.json` is the starting list (Target, Uber Eats, common
banking and payment apps). The rest Envoy learns: when an app shows a bot check on an emulator, or the Play Store says the
emulator isn't compatible, the runner sets the app to your phone in Settings › Phones (`phone_apps`) and notes why
(`phone_apps_learned`). A learned app counts as blocking only while it is still set to your phone: unticking it in
Settings undoes it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SKYLARK = "com.skylark.air"
TEST_EMULATOR, REAL_EMULATOR = "envoy-test", "envoy-real"

# Apps known to block emulators: package → {name, names (how a request says it), why}. Data, not code: add an app there.
BLOCKS_EMULATOR: dict[str, dict[str, Any]] = json.loads(Path(__file__).with_name("emulator_blocked.json").read_text())["apps"]
EMULATOR_REFUSED = {pkg: a["name"] for pkg, a in BLOCKS_EMULATOR.items()}  # package → name (Settings shows them as always on your phone)
NEEDS_REAL_PHONE = "blocks emulators; it needs a real Android phone"

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


def app_names() -> dict[str, str]:
    """How a request names an app on the starting list ("bank of america") → its package."""
    return {n: pkg for pkg, a in BLOCKS_EMULATOR.items() for n in a.get("names", [])}


def blocks_emulator(app: str | None, phone_apps: list[str] | None = None, learned: dict[str, Any] | None = None) -> str | None:
    """Why `app` can't run on an emulator, or None: on the starting list, or learned and still set to your phone."""
    if not app:
        return None
    if app in BLOCKS_EMULATOR:
        return BLOCKS_EMULATOR[app]["why"]
    if app in (learned or {}) and app in (phone_apps or []):
        return (learned or {})[app].get("why") or "it blocked the emulator"
    return None


def app_label(app: str | None, learned: dict[str, Any] | None = None) -> str:
    """The app's name for messages: from the starting list, or what Envoy saw when it learned it."""
    if app in BLOCKS_EMULATOR:
        return BLOCKS_EMULATOR[app]["name"]
    return ((learned or {}).get(app or "") or {}).get("name") or "This app"


def needs_real_phone(app: str | None, learned: dict[str, Any] | None = None, unauthorized: bool = False, name: str | None = None) -> str:
    """Said plainly when an app that blocks emulators has no phone to run on."""
    label = name if name and app_label(app, learned) == "This app" else app_label(app, learned)
    return f"{label} {NEEDS_REAL_PHONE}. " + (
        "Your phone is connected but hasn't allowed USB debugging yet: unlock it and tap Allow." if unauthorized
        else "Connect your Android phone (USB, or wireless debugging) and ask again.")


def choose(app: str | None, *, request: str = "", asked: str | None = None, phone_apps: list[str] | None = None,
           phones: list[dict[str, Any]] | None = None, learned: dict[str, Any] | None = None, named: str | None = None) -> Choice:
    """`asked`: "phone", "emulator", "auto"/None, or a device id, from the request itself. `phones`: connected phones
    from the pool ({id, model, state}); only state "device" can be used. `learned`: apps Envoy found blocking emulators
    (settings `phone_apps_learned`: package → {name, why, ...}). `named`: an app the request names that Envoy doesn't
    know yet ("in the Wikipedia app"): a real app, so the real-app emulator, where it can be installed."""
    phones = phones or []
    usable = [p for p in phones if p.get("state") == "device"]
    unauthorized = [p for p in phones if p.get("state") == "unauthorized"]
    emulator = TEST_EMULATOR if (not app and not named) or app == SKYLARK else REAL_EMULATOR
    if asked and asked not in ("phone", "emulator", "auto"):  # a specific device id
        is_phone = asked.startswith("phone-")
        if is_phone and not any(p["id"] == asked for p in usable):
            return Choice(None, "you picked that phone", error=_not_connected(unauthorized))
        return Choice(asked, "you picked it", real_phone=is_phone)
    if asked == "emulator":
        return Choice(emulator, "you asked for an emulator")

    why, blocked = None, blocks_emulator(app, phone_apps, learned)
    if asked == "phone" or asks_for_phone(request):
        why = "you asked for your phone"
    elif blocked is not None:  # before the plain setting: an app that blocks emulators never falls back to one
        why = f"{app_label(app, learned)} blocks emulators"
    elif app and app in (phone_apps or []):
        why = "set to run on your phone"
    if why is None:
        return Choice(emulator, "the default: an emulator keeps your phone free")
    if usable:
        p = usable[0]
        return Choice(p["id"], f"{why} ({p.get('model') or 'Android phone'})", real_phone=True)
    if why.startswith("set to run"):
        return Choice(emulator, f"{why}, but it isn't connected: using the emulator")
    if blocked is not None:
        return Choice(None, why, error=needs_real_phone(app, learned, unauthorized=bool(unauthorized)))
    return Choice(None, why, error=_not_connected(unauthorized))


def _not_connected(unauthorized: list[dict[str, Any]]) -> str:
    if unauthorized:
        return "Your phone is connected but hasn't allowed USB debugging yet: unlock it and tap Allow."
    return "Your Android phone isn't connected: plug it in (or pair it for wireless debugging) and try again."
