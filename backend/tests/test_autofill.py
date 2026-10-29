"""Saved logins through the phone's password manager (api/autofill.py), on screens recorded from Wikipedia's login on
envoy-real and the Pixel 5 during the experiment of Oct 29 (tests/screens/autofill_*.xml, a throwaway account; the
password in them is a made-up stand-in). Off by default per phone kind; only taps, never types; every sign-in asks you
first."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from test_phase6 import RoutePool, route_runner

from api import autofill
from api.store import TaskStore
from devices.screen import build_state
from devices.types import Action, ActionResult
from policy.approval_rules import ApprovalRules, decide
from policy.botcheck import bot_check_reason
from policy.signin import sign_in_reason

SCREENS = Path(__file__).parent / "screens"
WIKI = "org.wikipedia"
STAND_IN = "stand1n9"  # the recorded password's stand-in: it must never be typed or read anywhere


def recorded(name: str, *, secure: bool = False):
    activity = "org.wikipedia.DefaultIcon" if name == "signed_in" else "org.wikipedia.login.LoginActivity"
    return build_state((SCREENS / f"autofill_{name}.xml").read_text(), WIKI, activity, 1080, 2400, secure=secure)


class LoginPhone:
    """Wikipedia's login as recorded: tapping Username brings up the saved-login sheet (or nothing, with no saved login),
    tapping a saved account fills the form, and Log in signs in (or doesn't, when `fails`; or brings up the hCaptcha the
    Pixel 5 met, when `captcha`)."""

    def __init__(self, *, saved: bool = True, fails: bool = False, captcha: bool = False, secure: bool = False,
                 start: str = "login") -> None:
        self.saved, self.fails, self.captcha, self.secure = saved, fails, captcha, secure
        self.state = start
        self.actions: list[Action] = []
        self.screenshots = 0
        self.adb = None  # no Play Store installs here
        self._last = None

    async def observe(self, screenshot: bool = False):
        assert not screenshot, "a sign-in screen is never photographed by the feature"
        self._last = recorded(self.state, secure=self.secure)
        return self._last

    async def wait_until_settled(self):
        return await self.observe()

    async def launch(self, app, fresh=False):
        self.state = "login"

    def frame(self, width, timeout=5):
        self.screenshots += 1
        return Image.new("RGB", (width, width * 2))

    async def act(self, action: Action) -> ActionResult:
        self.actions.append(action)
        el = next((e for e in self._last.numbered if e.number == action.element), None) if action.element else None
        label = (el.label if el else "") or ""
        if action.kind == "tap" and el is not None:
            if el.editable and not el.password and self.state == "login":
                self.state = "suggestion" if self.saved else "no_suggestion"
            elif self.state == "suggestion" and el.package == "com.google.android.gms" and label.casefold() == "envoytest":
                self.state = "filled"
            elif self.state == "filled" and label == "Log in":
                self.state = "filled" if self.fails else "captcha" if self.captcha else "signed_in"
        return ActionResult(ok=True, duration_ms=1.0)


def run(phone: LoginPhone, answer: bool = True):
    asked: list[str] = []
    steps: list[dict] = []

    async def ask(description, screen):
        asked.append(description)
        return answer
    ok = asyncio.run(autofill.sign_in(phone, app=WIKI, name="Wikipedia", ask=ask, step=steps.append, wait_s=0.2, offer_s=0.2))
    return ok, asked, [s["text"] for s in steps]


def kinds(phone: LoginPhone) -> list[str]:
    return [a.kind for a in phone.actions]


# ---- the recorded screens, as the feature reads them ---------------------------------------------------------


def test_the_recorded_screens_read_as_expected():
    login, sheet, filled = recorded("login"), recorded("suggestion"), recorded("filled")
    assert sign_in_reason(login) is not None and sign_in_reason(recorded("signed_in")) is None
    assert autofill.username_field(login, WIKI).hint == "Username" and autofill.password_field(login, WIKI).hint == "Password"
    assert not autofill.filled(login, WIKI) and autofill.suggestions(login, WIKI) == []
    found = autofill.suggestions(sheet, WIKI)
    assert [s.username for s in found] == ["Envoytest", "envoytest"]  # one account, saved under both spellings
    assert autofill.filled(filled, WIKI) and autofill.suggestions(filled, WIKI) == []
    assert autofill.sign_in_button(login, WIKI) is None  # disabled until the form is filled
    assert autofill.sign_in_button(filled, WIKI).label == "Log in"
    assert autofill.suggestions(recorded("no_suggestion"), WIKI) == []  # the keyboard alone isn't a suggestion
    # The screen layer shows the filled password only as dots (devices/screen.py masks it): never the stand-in.
    pw = autofill.password_field(filled, WIKI)
    assert STAND_IN not in filled.compact and STAND_IN not in (pw.text + pw.label) and pw.text.startswith("••••")


def test_filled_means_both_fields_and_an_empty_password_still_reads_empty():
    login, filled = recorded("login"), recorded("filled")
    pw = autofill.password_field(login, WIKI)
    assert pw.text == pw.hint == "Password" and "(password, empty)" in login.compact  # not masked into dots (main 53ab459)
    half = recorded("filled")  # the username filled, the password not
    pw = autofill.password_field(half, WIKI)
    pw.text = pw.hint
    assert autofill.filled(filled, WIKI) and not autofill.filled(half, WIKI)


# ---- signing in ------------------------------------------------------------------------------------------------


def test_a_saved_login_signs_in_after_your_yes_with_taps_only():
    phone = LoginPhone()
    ok, asked, steps = run(phone)
    assert ok and phone.state == "signed_in"
    assert asked == ["Sign in to Wikipedia as Envoytest with your saved login?"]
    assert steps == [autofill.SIGNED_IN]
    assert kinds(phone) == ["tap", "tap", "tap"]  # the username field, the saved login, Log in


def test_a_password_is_never_typed_or_read_whatever_happens():
    for phone, answer in ((LoginPhone(), True), (LoginPhone(), False), (LoginPhone(saved=False), True), (LoginPhone(fails=True), True),
                          (LoginPhone(captcha=True), True)):
        _, asked, steps = run(phone, answer)
        assert "type" not in kinds(phone) and all(a.text is None for a in phone.actions)
        assert not any(STAND_IN in s for s in [*asked, *steps])
        assert phone.screenshots == 0


def test_log_in_waits_for_your_ok_and_a_no_hands_it_to_you():
    phone = LoginPhone()
    ok, asked, steps = run(phone, answer=False)
    assert not ok and len(asked) == 1 and phone.state == "filled"  # filled, but Log in never pressed
    assert kinds(phone) == ["tap", "tap"]
    assert steps == ["saved login: you didn't OK signing in with it"]


def test_no_saved_login_hands_it_to_you_without_asking():
    phone = LoginPhone(saved=False)
    ok, asked, steps = run(phone)
    assert not ok and asked == [] and phone.state == "no_suggestion"
    assert steps == ["saved login: your phone's password manager offered no saved login for Wikipedia"]


def test_a_sign_in_that_fails_afterwards_hands_it_to_you():
    phone = LoginPhone(fails=True)
    ok, asked, steps = run(phone)
    assert not ok and len(asked) == 1 and steps == ["saved login: Wikipedia still shows its sign-in after Log in"]


def test_a_captcha_after_log_in_is_not_a_sign_in_and_hands_it_to_you():
    captcha = recorded("captcha")  # the hCaptcha over Wikipedia's form on the Pixel 5: no password field shows
    assert sign_in_reason(captcha) is None and bot_check_reason(captcha) is not None
    phone = LoginPhone(captcha=True)
    ok, asked, steps = run(phone)
    assert not ok and len(asked) == 1 and phone.state == "captcha"
    assert steps == ["saved login: Wikipedia asked you to prove you're human after Log in: that's yours to do"]
    assert kinds(phone) == ["tap", "tap", "tap"]  # nothing tapped on the captcha


def test_a_secure_sign_in_screen_works_the_same_and_is_never_photographed():
    phone = LoginPhone(secure=True)
    ok, _, _ = run(phone)
    assert ok and phone.screenshots == 0 and recorded("login", secure=True).secure


def test_two_different_saved_accounts_are_yours_to_choose():
    phone = LoginPhone()
    sheet = recorded("suggestion")
    for e in sheet.elements:
        if e.text == "envoytest":
            e.text = e.label = "someoneelse"

    async def observe(screenshot=False):
        phone._last = sheet if phone.state == "suggestion" else recorded(phone.state)
        return phone._last
    phone.observe = observe  # type: ignore[method-assign]
    ok, asked, steps = run(phone)
    assert not ok and asked == [] and steps == ["saved login: your phone has more than one saved login for Wikipedia: you choose"]


# ---- the setting ---------------------------------------------------------------------------------------------


def test_off_by_default_and_set_per_kind_of_phone():
    store = TaskStore(":memory:")
    assert autofill.setting(store) == {"emulator": False, "phone": False}
    assert not autofill.enabled(store, real_phone=False) and not autofill.enabled(store, real_phone=True)
    app = FastAPI()
    app.include_router(autofill.signin_router(store, lambda: None))
    with TestClient(app) as c:
        assert c.get("/api/settings/signin").json() == {"autofill": {"emulator": False, "phone": False}}
        got = c.post("/api/settings/signin", json={"autofill": {"emulator": True, "phone": "yes", "other": True}}).json()
        assert got == {"autofill": {"emulator": True, "phone": False}}  # only booleans, only the two kinds
    assert autofill.enabled(store, real_phone=False) and not autofill.enabled(store, real_phone=True)


# ---- in the runner -----------------------------------------------------------------------------------------------


class WikiPool(RoutePool):
    def __init__(self, phone: LoginPhone) -> None:
        super().__init__(phone)  # type: ignore[arg-type]


async def until(r, tid: str, pred, seconds: float = 5.0):
    for _ in range(int(seconds / 0.01)):
        t = r.store.get(tid)
        if pred(t):
            return t
        await asyncio.sleep(0.01)
    raise AssertionError(f"timed out: {r.store.get(tid)}")


def test_in_a_task_the_sign_in_asks_even_when_your_words_name_it(monkeypatch):
    phone = LoginPhone()
    r = route_runner(monkeypatch, WikiPool(phone))
    r.store.set_setting("signin.autofill", {"emulator": True, "phone": False})
    words = "sign in to wikipedia as envoytest with my saved login, then look up paris"  # nothing capitalized: no detail to miss
    # The rules would let a direct request approve a button it names; the sign-in names none, so they can't.
    assert decide(ApprovalRules(), goal=words, source="web", app=WIKI, routine=None, origin="signin", target="", screen_text="") is None

    async def scenario():
        r.loop = asyncio.get_running_loop()
        task = r.start(words, "web", app=WIKI)
        t = await until(r, task["id"], lambda t: t["status"] == "waiting_approval")
        pending = r.store.approvals("pending", task_id=task["id"])
        assert [a["description"] for a in pending] == ["Sign in to Wikipedia as Envoytest with your saved login?"]
        r.approvers[task["id"]].decide(t["waiting_for"], True, "you")
        await r.jobs[task["id"]]
        return r.store.get(task["id"]), [s.get("text") for s in r.store.steps(task["id"])]
    done, steps = asyncio.run(scenario())
    assert done["status"] == "done" and phone.state == "signed_in" and autofill.SIGNED_IN in steps
    assert "type" not in kinds(phone)
    assert not any(a["status"] == "approved" and a["decided_by"] == "your request" for a in r.store.approvals(task_id=done["id"]))


def test_with_the_setting_off_a_sign_in_is_handed_to_you_as_before(monkeypatch):
    phone = LoginPhone()
    pool = WikiPool(phone)
    r = route_runner(monkeypatch, pool)
    r.store.set_setting("signin.autofill", {"emulator": False, "phone": True})  # on for your phone only: not this emulator

    async def scenario():
        r.loop = asyncio.get_running_loop()
        task = r.start("look up Paris in Wikipedia", "web", app=WIKI)
        await r.jobs[task["id"]]
        return r.store.get(task["id"])
    done = asyncio.run(scenario())
    assert phone.actions == [] and pool.takeovers == ["sign-in needed: password field on screen"]
    assert done["status"] == "needs_you" and r.store.approvals(task_id=done["id"]) == []
