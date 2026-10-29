"""Saved logins: the phone's own password manager signs you in, and Envoy never sees the password
(docs/preflight-and-autofill.md, from the experiment on envoy-real, Oct 29).

Off by default, and set per kind of phone (`signin.autofill`: {"emulator": bool, "phone": bool}), so your own phone can
stay off while the emulators use it. When it's on and a task meets an app's sign-in screen, before the phone is handed
to you:

1. Envoy taps the username field.
2. If the phone's password manager offers a saved login for the app (Google's sheet "Use your saved password for
   Wikipedia?", one row per saved account, the password shown as dots), Envoy taps that row and the manager fills both
   fields. Envoy types nothing.
3. It asks you through the normal approval: "Sign in to Wikipedia as Envoytest with your saved login?". It acts as you
   there, so every sign-in waits for your yes; the words of the request never approve it (the approval names no
   button, so approval_rules has nothing to match).
4. On your yes it taps the app's own sign-in button and waits for the screen to leave sign-in.

Anything that doesn't match ends here and the phone is handed to you exactly as before: no saved login offered, two
different saved accounts, fields that don't fill, a no (or no answer), no sign-in button, or a sign-in screen or a
captcha there afterwards. Envoy never types into a password field, never reads a field's value (a filled password reads
as dots: devices/screen.py masks it), takes no screenshot of a secure window, and keeps nothing.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, Body, Depends

from devices.types import Action, Element, ScreenState
from policy.botcheck import bot_check_reason
from policy.signin import sign_in_reason

KEY = "signin.autofill"
DEFAULT = {"emulator": False, "phone": False}
SIGNED_IN = "Signed in with your saved login (your phone's password manager filled it)"

_USERNAME = re.compile(r"(e-?mail|user|login|phone|mobile|account)", re.I)
_DOTS = re.compile(r"^[•●*·•●]{4,}$")
_SIGN_IN = re.compile(r"^(sign ?in|log ?in)$", re.I)
_NEXT = re.compile(r"^(continue|next|submit)$", re.I)
_KEYBOARD = re.compile(r"(inputmethod|honeyboard|swiftkey|\.keyboard\b|gboard)", re.I)


# ---- the setting ----------------------------------------------------------------------------------------


def setting(store: Any) -> dict[str, bool]:
    got = store.setting(KEY, None) or {}
    return {k: bool(got.get(k, v)) for k, v in DEFAULT.items()}


def enabled(store: Any, real_phone: bool) -> bool:
    return setting(store)["phone" if real_phone else "emulator"]


def signin_router(store: Any, session: Callable[..., None]) -> APIRouter:
    """`GET/POST /api/settings/signin` (session only): {"autofill": {"emulator": bool, "phone": bool}}."""
    r = APIRouter()

    @r.get("/api/settings/signin", dependencies=[Depends(session)])
    def get_signin() -> dict[str, Any]:
        return {"autofill": setting(store)}

    @r.post("/api/settings/signin", dependencies=[Depends(session)])
    def set_signin(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        asked = body.get("autofill") if isinstance(body.get("autofill"), dict) else {}
        new = {k: bool(asked[k]) if isinstance(asked.get(k), bool) else v for k, v in setting(store).items()}
        store.set_setting(KEY, new)
        return {"autofill": new}

    return r


# ---- reading the sign-in screen -------------------------------------------------------------------------


def _fields(screen: ScreenState, app: str | None) -> list[Element]:
    return [e for e in screen.numbered if e.editable and e.visible and (not app or e.package == app)]


def password_field(screen: ScreenState, app: str | None) -> Element | None:
    return next((e for e in _fields(screen, app) if e.password), None)


def username_field(screen: ScreenState, app: str | None) -> Element | None:
    """The field the saved login goes into: one that says email, user or phone, else the field just above the password."""
    fields = [e for e in _fields(screen, app) if not e.password]
    named = [e for e in fields if _USERNAME.search(f"{e.hint} {e.label} {e.resource_id}")]
    if named:
        return named[0]
    pw = password_field(screen, app)
    above = [e for e in fields if pw is not None and e.bounds[3] <= pw.bounds[1]]
    return above[-1] if above else None


def filled(screen: ScreenState, app: str | None) -> bool:
    """Both fields hold something. The password only as the screen layer shows it: dots, never its value."""
    pw, user = password_field(screen, app), username_field(screen, app)
    return pw is not None and user is not None and bool(pw.text) and pw.text != pw.hint and bool(user.text) and user.text != user.hint


@dataclass
class Suggestion:
    username: str
    element: Element  # the row's username text: tapping it picks the login


def suggestions(screen: ScreenState, app: str | None) -> list[Suggestion]:
    """Saved logins the password manager offers on screen: a row outside the app with an account name beside a password
    shown only as dots. On envoy-real that is Android's autofill dialog ("Use your saved password for Wikipedia?") with
    Google's rows in it; a row isn't marked clickable, so the numbered element holding the name is tapped. The keyboard's
    own strip doesn't count: inline suggestions there aren't measured yet (the Pixel check)."""
    els = screen.elements

    def outside(e: Element) -> bool:
        return e.visible and not e.status_bar and bool(e.package) and e.package != app and e.package != "com.android.systemui" \
            and not _KEYBOARD.search(e.package)

    def below(i: int) -> list[Element]:  # an element's descendants: the ones after it, deeper, until the tree climbs back
        out = []
        for e in els[i + 1:]:
            if e.depth <= els[i].depth:
                break
            out.append(e)
        return out

    found: list[Suggestion] = []
    for dots in (e for e in els if outside(e) and _DOTS.match((e.text or "").strip())):
        row, name = dots.parent, None
        for _ in range(4):  # the nearest ancestor that also holds the account's name
            if row is None:
                break
            name = next((e for e in below(row) if outside(e) and e is not dots and (e.text or "").strip()
                         and not _DOTS.match(e.text.strip())), None)
            if name is not None:
                break
            row = els[row].parent
        if name is None:
            continue
        tap, at = None, name.index  # the name itself, or its nearest numbered container inside the row
        while at is not None and tap is None:
            tap = els[at] if els[at].number is not None else None
            at = None if at == row else els[at].parent
        if tap is not None:
            found.append(Suggestion(name.text.strip(), tap))
    return found


def sign_in_button(screen: ScreenState, app: str | None) -> Element | None:
    buttons = [e for e in screen.numbered if e.kind == "Button" and e.enabled and e.visible and (not app or e.package == app)]
    return next((e for e in buttons if _SIGN_IN.match((e.label or "").strip())), None) \
        or next((e for e in buttons if _NEXT.match((e.label or "").strip())), None)


# ---- signing in ------------------------------------------------------------------------------------------


async def _until(device: Any, ok: Callable[[ScreenState], bool], seconds: float, every: float = 0.5) -> ScreenState:
    screen = await device.observe()
    waited = 0.0
    while not ok(screen) and waited < seconds:
        await asyncio.sleep(every)
        waited += every
        screen = await device.observe()
    return screen


async def sign_in(device: Any, *, app: str | None, name: str, ask: Callable[[str, ScreenState], Awaitable[bool]],
                  step: Callable[[dict[str, Any]], None], wait_s: float = 20, offer_s: float = 4) -> bool:
    """Sign in with the saved login the phone offers, after your yes. True when the sign-in screen is gone; False hands
    the phone to you as before (each reason is said as a step). Only taps: nothing is ever typed."""
    note = lambda text: step({"kind": "note", "text": f"saved login: {text}"})  # noqa: E731
    screen = await device.observe()
    user, pw = username_field(screen, app), password_field(screen, app)
    if user is None or pw is None or user.number is None:
        note("this sign-in screen has no username and password fields to fill")
        return False
    await device.act(Action(kind="tap", element=user.number))
    screen = await _until(device, lambda s: bool(suggestions(s, app)), offer_s)
    found = suggestions(screen, app)
    if not found:
        note(f"your phone's password manager offered no saved login for {name}")
        return False
    if len({s.username.casefold() for s in found}) > 1:
        note(f"your phone has more than one saved login for {name}: you choose")
        return False
    chosen = found[0]
    await device.act(Action(kind="tap", element=chosen.element.number))
    screen = await _until(device, lambda s: filled(s, app) and not suggestions(s, app), offer_s)
    if not filled(screen, app):
        note("the saved login didn't fill the fields")
        return False
    if not await ask(f"Sign in to {name} as {chosen.username} with your saved login?", screen):
        note("you didn't OK signing in with it")
        return False
    screen = await device.observe()
    button = sign_in_button(screen, app)
    if button is None or button.number is None or not filled(screen, app):
        note("the sign-in form changed before I could press its button")
        return False
    await device.act(Action(kind="tap", element=button.number))
    screen = await _until(device, lambda s: sign_in_reason(s) is None, wait_s)
    if sign_in_reason(screen) is None:
        screen = await device.wait_until_settled()  # a captcha can cover the form a moment later
    if bot_check_reason(screen) is not None:  # Wikipedia's hCaptcha on the Pixel 5 hides the form: not signed in
        note(f"{name} asked you to prove you're human after {button.label}: that's yours to do")
        return False
    if sign_in_reason(screen) is not None:
        note(f"{name} still shows its sign-in after {button.label}")
        return False
    step({"kind": "note", "text": SIGNED_IN})
    return True
