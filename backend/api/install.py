"""Installing an app on demand (design doc, Device layer › An app the phone doesn't have yet).

When a task names an app the emulator doesn't have, the runner installs it from the Play Store and carries on:

1. **Which app.** A package Envoy already knows for the request (runner.APP_NAMES, an app it installed before), or the
   name the request gives ("in the Wikipedia app"): looked for among the apps already on the phone first, then searched
   for on the Play Store.
2. **Its listing,** read in code with no model call: Install (free), a price (paid), Open (already there), "isn't
   compatible" (the app blocks emulators), "isn't available", or the Play Store asking for a Google account. Searched
   for by name, the result's own button says it (the top result carries Install, a price or Open). Only the app's own
   part of a page counts: sponsored apps and suggestions come with Install buttons of their own (on envoy-real a
   sponsored look-alike sat above Google Translate's result, Oct 28, 2026), and Envoy never taps those.
3. **Free:** Envoy taps Install, waits for the package to appear, and the task goes on. **Paid:** Envoy never pays. It
   asks through the approval flow; a yes hands the phone to you to buy it yourself, a no (or no answer) ends the task.
4. **Sign-ins are yours,** as everywhere else ("sign in as you go"): the Play Store's own (no Google account on the
   emulator) is handed to you here, the app's first sign-in screen by the runner once the app opens.

Only on emulators: the Play Store needs the emulator's Google account to be signed in already. On your own phone Envoy
asks you to install the app yourself (runner._ensure_app).
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from urllib.parse import quote
from typing import Any, Awaitable, Callable, Literal

from devices.types import Action, Element, ScreenState
from policy.approvals import ApprovalRequest
from routines.screens import norm

PLAY = "com.android.vending"

# A paid app's button: "$6.99", or "Buy for $6.99 · $6.99" (its description and its text, merged).
_PRICE = re.compile(r"^(?:buy(?: for)?\s+)?((?:US\$|CA\$|A\$|[$€£¥₹])\s?\d[\d.,]*|\d[\d.,]*\s?(?:[$€£¥₹]|USD|EUR|GBP|INR))(?:\s*·.*)?$", re.I)
_INSTALL = re.compile(r"^(install|get)$", re.I)
_INSTALLED = re.compile(r"^(open|play|uninstall|update|enable)$", re.I)
_CANCEL = re.compile(r"^cancel$", re.I)
_PROGRESS = re.compile(r"\b(pending|waiting for (download|network|wi-?fi)|installing|downloading|verifying)\b|\d+\s?% of", re.I)
_INCOMPATIBLE = re.compile(r"(isn.?t compatible|not compatible with|device isn.?t supported|"
                           r"(isn.?t|is not|not) available (for|on) (this|your) device)", re.I)
_UNAVAILABLE = re.compile(r"((isn.?t|is not|not) available in your (country|region)|item (isn.?t|is not|was not) (available|found)|"
                          r"app (isn.?t|is not) available|couldn.?t find)", re.I)
_SETUP = re.compile(r"(complete (your )?account setup|add a payment method)", re.I)
_FAILED = re.compile(r"(can.?t install|couldn.?t install|install failed|error (retrieving|downloading)|not enough (space|storage))", re.I)
_SIGN_IN = re.compile(r"^sign in$", re.I)
_SKIP = re.compile(r"^(skip|not now|no,? thanks|later)$", re.I)
# Where other apps start on a page: ads and suggestions, each with an Install button of its own.
_OTHERS = re.compile(r"^(sponsored|ads?|suggested for you|you might also like|similar apps|related apps|recommended for you)$", re.I)
# Labels on an app's page that are not its name.
_BADGE = re.compile(r"^(new!?|sponsored|ad|editors.? choice|contains ads|in-app purchases|teacher approved|premium|installed|"
                    r"pending.*|verified by play protect|ask play about this app|rate this app|tell others what you think)$", re.I)

# How a request names an app it means: "in the Wikipedia app", "install Duolingo", "In AccuWeather, ...".
_WORD = r"[A-Za-z0-9][\w&'+.!-]*"
_NAMED = [
    re.compile(rf"\b(?:in|on|use|using|with|from|open|launch|via)\s+(?:the\s+)?(?P<name>{_WORD}(?:\s+{_WORD}){{0,3}}?)\s+app\b", re.I),
    re.compile(rf"\b(?:install|download)\s+(?:the\s+)?(?P<name>{_WORD}(?:\s+{_WORD}){{0,3}}?)(?:\s+app)?(?:\s+(?:from|on)\s+the\s+play\s+store|\s*$|[,.;!?]|\s+and\b)", re.I),
    re.compile(r"^\s*(?i:in|on|open|using)\s+(?:the\s+)?(?P<name>[A-Z][\w&'+.!-]*(?:\s+[A-Z][\w&'+.!-]*){0,2})\s*,"),
]
_NOT_A_NAME = {"my", "your", "this", "that", "the", "a", "an", "same", "any", "which", "other", "another", "new", "it", "an app",
               "his", "her", "their", "our", "its", "some", "every", "each", "one"}


def app_named_in(goal: str) -> str | None:
    """The app name a request gives, when it names one as an app ("in the Wikipedia app" → "Wikipedia"), or None."""
    for pat in _NAMED:
        m = pat.search(goal or "")
        if m:
            name = m.group("name").strip(" .,'\"")
            first = name.split()[0].lower() if name else ""
            if name and first not in _NOT_A_NAME and name.lower() not in _NOT_A_NAME and name.lower() != "play store":
                return name
    return None


@dataclass
class Listing:
    """What the Play Store page in front says about the app."""

    state: Literal["free", "paid", "installed", "installing", "incompatible", "unavailable", "sign_in", "setup", "failed", "unknown"]
    title: str = ""
    price: str = ""
    button: Element | None = None  # Install, Skip or Sign in (never the price: Envoy doesn't tap it)
    detail: str = ""


def _own(screen: ScreenState) -> list[Element]:
    """The app's own part of its page: everything before the first ad or suggestion."""
    out: list[Element] = []
    for e in screen.numbered:
        if e.kind == "Text" and _OTHERS.match(e.label.strip()):
            break
        out.append(e)
    return out


def _title(own: list[Element]) -> str:
    """The app's name on its page: the last plain text before its rating ("Average rating 4.3 stars ..."), else the
    first plain text that isn't a badge ("New!"), a size or a count."""
    def plain(e: Element) -> bool:
        label = e.label.strip()
        return (e.kind == "Text" and len(label) > 1 and not _BADGE.match(label) and not _PRICE.match(label)
                and not re.search(r"\b(reviews?|downloads?|downloaded|rated|MB|GB)\b", label, re.I))
    rating = next((i for i, e in enumerate(own) if e.label.lower().startswith("average rating")), None)
    if rating is not None and (before := [e for e in own[:rating] if plain(e)]):
        return before[-1].label.strip()
    return next((e.label.strip() for e in own if plain(e)), "")


def read_listing(screen: ScreenState) -> Listing:
    """The app's page in the Play Store, read without a model call. Only the app's own part counts."""
    own = _own(screen)
    buttons = [e for e in own if e.kind == "Button" and e.label]
    text = " · ".join(e.label for e in own)
    title = _title(own)

    def button(pattern: re.Pattern[str]) -> Element | None:
        return next((e for e in buttons if pattern.match(e.label.strip())), None)

    if screen.package != PLAY:
        return Listing("unknown", title, detail=f"the Play Store isn't in front ({screen.package})")
    if _SETUP.search(text) and (b := button(_SKIP)) is not None:
        return Listing("setup", title, button=b, detail="the Play Store asks to finish account setup (a payment method): skipped")
    if _FAILED.search(text):
        return Listing("failed", title, detail=next((e.label for e in own if _FAILED.search(e.label)), "install failed"))
    if _INCOMPATIBLE.search(text):
        return Listing("incompatible", title, detail=next(e.label for e in own if _INCOMPATIBLE.search(e.label)))
    if (b := button(_INSTALL)) is not None:
        return Listing("free", title, button=b)
    if (b := next((e for e in buttons if _PRICE.match(e.label.strip())), None)) is not None:
        return Listing("paid", title, price=_PRICE.match(b.label.strip()).group(1), detail=b.label)  # type: ignore[union-attr]
    if button(_CANCEL) is not None or _PROGRESS.search(text):
        return Listing("installing", title)
    if button(_INSTALLED) is not None:
        return Listing("installed", title)
    if _UNAVAILABLE.search(text):
        return Listing("unavailable", title, detail=next(e.label for e in own if _UNAVAILABLE.search(e.label)))
    if (b := button(_SIGN_IN)) is not None:
        return Listing("sign_in", title, button=b, detail="the Play Store asks you to sign in")
    return Listing("unknown", title, detail="no Install button, price or Open on the page")


def guess_installed(name: str, packages: set[str]) -> str | None:
    """An installed app the name clearly points at: the only launcher package whose id holds the name's letters
    ("Wikipedia" → org.wikipedia, "YouTube Music" → com.google.android.apps.youtube.music). None when it's not one."""
    want = re.sub(r"[^a-z0-9]", "", name.lower())
    if len(want) < 4:
        return None
    hits = [p for p in packages if want in re.sub(r"[^a-z0-9]", "", p.lower())]
    return hits[0] if len(hits) == 1 else None


def _inside(inner: Element, outer: Element) -> bool:
    a, b = inner.bounds, outer.bounds
    return a[0] >= b[0] and a[1] >= b[1] and a[2] <= b[2] and a[3] <= b[3]


def card_title(screen: ScreenState, card: Element) -> str:
    """A search result's name: the first line of its first text ("Google Translate" in "Google Translate\\nGoogle LLC")."""
    for e in screen.elements[card.index:]:
        if e.index != card.index and not _inside(e, card):
            continue
        raw = e.desc or e.text
        if raw and raw.strip():
            return raw.strip().split("\n")[0].strip()
    return re.split(r" · ", card.label)[0].strip()


def card_action(screen: ScreenState, card: Element) -> Element | None:
    """The result's own button (Install, a price, Open): the first button after it that lies inside it."""
    for e in screen.numbered[(card.number or 0):]:
        if e.kind == "Button" and _inside(e, card):
            label = e.label.strip()
            if _INSTALL.match(label) or _PRICE.match(label) or _INSTALLED.match(label) or _CANCEL.match(label):
                return e
    return None


def card_listing(screen: ScreenState, card: Element) -> Listing:
    """What a search result says about its app, from its own button; "unknown" when it has none (its page says more)."""
    title = card_title(screen, card)
    b = card_action(screen, card)
    label = b.label.strip() if b is not None else ""
    if b is None:
        return Listing("unknown", title, detail="the result has no button of its own")
    if _INSTALL.match(label):
        return Listing("free", title, button=b)
    if (m := _PRICE.match(label)) is not None:
        return Listing("paid", title, price=m.group(1), detail=label)
    if _CANCEL.match(label):
        return Listing("installing", title)
    return Listing("installed", title, button=b)


def pick_result(screen: ScreenState, name: str) -> Element | None:
    """The search result that is the app the request names: its title is the name ("Wikipedia"), starts with it
    ("Duolingo: Language Lessons") or, failing those, contains it. The result right after "Sponsored" is an ad, and
    never picked: an ad can be a look-alike of the very app asked for."""
    want = norm(name)
    best: tuple[int, Element] | None = None
    after_ad = False
    for e in screen.numbered:
        if e.kind == "Text" and _OTHERS.match(e.label.strip()):
            after_ad = True
            continue
        if e.kind != "Button" or not e.label or not e.in_list:  # results are in the list; the search box above repeats the query
            continue
        title = norm(card_title(screen, e))
        if not title or title in ("search", "apps", "games", "install", "open", "more options", "play trailer"):
            continue
        if after_ad and e.area > 0.03 * screen.width * screen.height:  # the ad's own card
            after_ad = False
            continue
        w = re.escape(want)
        score = 3 if title == want else 2 if re.match(rf"{w}(?!\w)", title) else 1 if re.search(rf"(?<!\w){w}(?!\w)", title) else 0
        if score and (best is None or score > best[0]):
            best = (score, e)
    return best[1] if best else None


@dataclass
class Installed:
    """How an install on demand went. `status`: "installed", "already" (it was there), "bought" (you bought it),
    "declined" (a paid app, and you said no or didn't answer), "incompatible" (the emulator can't have it), "not_found",
    "unavailable", "no_account", "failed" or "timeout"."""

    status: str
    package: str | None = None
    title: str = ""
    price: str = ""
    detail: str = ""
    seconds: dict[str, float] | None = None  # find (search or page), download+install, total

    @property
    def ok(self) -> bool:
        return self.status in ("installed", "already", "bought")


class Installer:
    """Installs one app on one emulator for one task. `device` is the gated device (it waits while you're in control);
    `step` writes a task step; `approve` is the task's approver (`request(ApprovalRequest)`, blocking); `hand_off(why)`
    asks you to take over and returns whether you handed back."""

    def __init__(self, device: Any, *, step: Callable[[dict[str, Any]], None], approver: Any,
                 hand_off: Callable[[str], Awaitable[bool]], task_id: str = "", goal: str = "",
                 timeout_s: float = 300, poll_s: float = 2.0, wait_s: float = 1.0) -> None:
        self.device, self.step, self.approver, self.hand_off = device, step, approver, hand_off
        self.task_id, self.goal = task_id, goal
        self.timeout_s, self.poll_s = timeout_s, poll_s
        self.wait_s = wait_s  # how long a Play Store page takes to load after it opens

    # ---- the phone ------------------------------------------------------------------------------

    async def _shell(self, cmd: str | list[str]) -> str:
        return await asyncio.to_thread(self.device.adb.shell, cmd)

    async def packages(self) -> set[str]:
        out = await self._shell("pm list packages")
        return {line.split(":", 1)[1].strip() for line in out.splitlines() if line.startswith("package:")}

    async def installed(self, package: str) -> bool:
        return f"package:{package}" in (await self._shell(f"pm list packages {package}")).split()

    async def has_google_account(self) -> bool:
        """A Google account on the phone (the Play Store needs one). Only the account type is read, never its name."""
        out = await self._shell("dumpsys account | grep -c 'type=com.google}'")
        return out.strip().isdigit() and int(out.strip()) > 0

    async def launchers(self) -> set[str]:
        """Packages with a launcher icon (the apps a person would name)."""
        out = await self._shell("cmd package query-activities --brief -a android.intent.action.MAIN -c android.intent.category.LAUNCHER")
        return {line.strip().split("/", 1)[0] for line in out.splitlines() if "/" in line and " " not in line.strip()}

    async def _open(self, uri: str, ready: Callable[[ScreenState], bool] | None = None) -> ScreenState:
        await self.device.wait_until_settled()  # waits while you're in control, like every other call
        await self._shell(["am", "start", "-a", "android.intent.action.VIEW", "-d", uri, "-p", PLAY])
        await asyncio.sleep(1.5 * self.wait_s)  # the Play Store loads the page after the activity starts
        return await self._settled_page(ready=ready)

    async def _settled_page(self, tries: int = 6, ready: Callable[[ScreenState], bool] | None = None) -> ScreenState:
        """The Play Store page once it has loaded (its first frame is often an empty shell or a spinner)."""
        ready = ready or (lambda s: read_listing(s).state != "unknown")
        screen = await self.device.wait_until_settled()
        for _ in range(tries):
            if screen.package == PLAY and ready(screen):
                return screen
            await asyncio.sleep(self.wait_s)
            screen = await self.device.wait_until_settled()
        return screen

    async def _tap(self, e: Element) -> None:
        await self.device.act(Action(kind="tap", element=e.number))

    # ---- the flow -------------------------------------------------------------------------------

    async def ensure(self, package: str | None, name: str | None = None) -> Installed:
        """Make sure the app is on the phone: by package when known, else by the name the request gave."""
        t0 = time.perf_counter()
        secs: dict[str, float] = {}
        if package and await self.installed(package):
            return Installed("already", package, seconds={"total": 0.0})
        if not package and name and (pkg := guess_installed(name, await self.launchers())) is not None:
            return Installed("already", pkg, name, detail="already on the phone", seconds={"total": round(time.perf_counter() - t0, 1)})
        if not await self.has_google_account():
            if not await self.hand_off("sign-in needed: the Play Store has no Google account on this phone") \
                    or not await self.has_google_account():
                return Installed("no_account", package, name or "", detail="the Play Store needs a Google account on the emulator, and none is signed in")
        before = await self.packages()
        if package:
            self.step({"kind": "note", "text": f"{name or package} isn't on this phone: opening it in the Play Store"})
            screen = await self._open(f"market://details?id={package}")
        else:
            self.step({"kind": "note", "text": f"{name} isn't on this phone: looking for it in the Play Store"})
            screen = await self._open(f"market://search?q={quote(name or '')}&c=apps", ready=lambda s: pick_result(s, name or "") is not None)
            card = pick_result(screen, name or "")
            if card is None:
                return Installed("not_found", None, name or "", detail=f"no app called {name!r} in the Play Store's results")
        listing = read_listing(screen) if package else card_listing(screen, card)
        if not package and listing.state == "unknown":  # a result with no button of its own: its page says why
            x1, y1, x2, y2 = card.bounds
            await self.device.act(Action(kind="tap_point", x=x1 + (x2 - x1) // 4, y=y1 + 60))  # on its name: its middle can be a question box
            await asyncio.sleep(self.wait_s)
            screen = await self._settled_page()
            listing = read_listing(screen)
            listing.title = listing.title or card_title(screen, card)
        secs["find"] = round(time.perf_counter() - t0, 1)
        title = listing.title or name or package or "the app"
        if listing.state == "sign_in":
            if not await self.hand_off("sign-in needed: the Play Store asks you to sign in"):
                return Installed("no_account", package, title, detail=listing.detail)
            screen = await self._settled_page()
            listing = read_listing(screen)
        if listing.state == "installed":
            pkg = package or await self._open_to_learn(screen, listing.button)
            if pkg is None:
                return Installed("failed", None, title, detail="the Play Store says it's installed, but it didn't open", seconds=secs)
            return Installed("already", pkg, title, detail="the Play Store says it's installed", seconds=secs)
        if listing.state == "paid":
            return await self._paid(listing, package, title, before, secs, t0)
        if listing.state in ("incompatible", "unavailable", "failed", "unknown"):
            status = {"unknown": "failed"}.get(listing.state, listing.state)
            return Installed(status, package, title, detail=listing.detail, seconds=secs)
        tapped = None
        if listing.state == "free":
            self.step({"kind": "note", "text": f"installing {title} from the Play Store (free)"})
            tapped = listing.button
            await self._tap(tapped)  # type: ignore[arg-type]
        t_install = time.perf_counter()
        pkg = await self._wait_installed(package, before, name or title, tapped)
        secs["install"] = round(time.perf_counter() - t_install, 1)
        secs["total"] = round(time.perf_counter() - t0, 1)
        if isinstance(pkg, Installed):
            pkg.title, pkg.seconds = pkg.title or title, secs
            return pkg
        self.step({"kind": "note", "text": f"installed {title} in {secs['total']:.0f} s (finding it {secs['find']:.0f} s, "
                                            f"download and install {secs['install']:.0f} s)"})
        return Installed("installed", pkg, title, seconds=secs)

    async def _wait_installed(self, package: str | None, before: set[str], name: str, tapped: Element | None) -> str | Installed:
        """Wait until the package is there (or, searched for by name, a new one appears), answering the Play Store's
        account-setup prompt with Skip on the way. A page that says the install failed ends the wait. If the Install
        tapped is still there, unchanged, it is tapped once more: that very button, never another app's."""
        deadline = time.monotonic() + self.timeout_s
        looks = 0
        while time.monotonic() < deadline:
            if package and await self.installed(package):
                return package
            if not package:
                new = await self.packages() - before
                if new:
                    return await self._which(new, name)
            screen = await self.device.wait_until_settled()
            listing = read_listing(screen)
            looks += 1
            if listing.state == "setup" and listing.button is not None:
                self.step({"kind": "note", "text": "the Play Store asked to finish account setup (a payment method): skipped"})
                await self._tap(listing.button)
            elif listing.state == "failed":
                return Installed("failed", package, detail=listing.detail)
            elif tapped is not None and looks == 3:
                same = next((e for e in screen.numbered if e.bounds == tapped.bounds and _INSTALL.match(e.label.strip())), None)
                if same is not None:  # the tap didn't take
                    await self._tap(same)
            await asyncio.sleep(self.poll_s)
        return Installed("timeout", package, detail=f"not installed after {self.timeout_s:.0f} s")

    async def _which(self, new: set[str], name: str) -> str:
        """The package that arrived for the app searched for by name. With more than one (an app and something it
        needs): the one whose id holds the name's words, else the one with a launcher icon."""
        if len(new) == 1:
            return next(iter(new))
        words = [w for w in re.findall(r"[a-z0-9]+", name.lower()) if len(w) >= 3]
        named = [p for p in sorted(new) if words and all(w in p.lower() for w in words)]
        if named:
            return named[0]
        have = await self.launchers()
        return next((p for p in sorted(new) if p in have), sorted(new)[0])

    async def _open_to_learn(self, screen: ScreenState, button: Element | None) -> str | None:
        """An app found by name that the Play Store says is installed: Open shows which package it is."""
        b = button if button is not None and re.match(r"^(open|play)$", button.label.strip(), re.I) else \
            next((e for e in _own(screen) if e.kind == "Button" and re.match(r"^(open|play)$", e.label.strip(), re.I)), None)
        if b is None:
            return None
        await self._tap(b)
        await asyncio.sleep(2 * self.wait_s)
        front = (await self.device.wait_until_settled()).package
        return front if front and front != PLAY else None

    async def _paid(self, listing: Listing, package: str | None, title: str, before: set[str], secs: dict[str, float],
                    t0: float) -> Installed:
        """Envoy never pays: the approval asks whether you want to buy it yourself; a yes hands the phone to you."""
        screen = await self.device.wait_until_settled()
        req = ApprovalRequest(task_id=self.task_id, goal=self.goal, app=PLAY,
                              description=f"{title} costs {listing.price} on the Play Store: buy it yourself?",
                              reasons=["Envoy installs only free apps and never pays", "a yes hands the phone to you to buy it, then you hand back"],
                              screen=screen.compact, origin="install", target=f"Buy {title}")
        self.step({"kind": "note", "text": f"{title} isn't free ({listing.price}): asking you"})
        decision = await asyncio.to_thread(self.approver.request, req)
        if not decision.approved:
            why = "no answer" if decision.by == "timeout" else "you said no"
            return Installed("declined", package, title, listing.price, detail=f"{title} costs {listing.price}; Envoy installs only free apps ({why})",
                             seconds=secs)
        if not await self.hand_off(f"buy {title} ({listing.price}) in the Play Store yourself"):
            return Installed("declined", package, title, listing.price, detail="waiting for you to buy it timed out", seconds=secs)
        pkg = package if package and await self.installed(package) else next(iter(await self.packages() - before), None)
        secs["total"] = round(time.perf_counter() - t0, 1)
        if pkg is None:
            return Installed("failed", package, title, listing.price, detail="handed back, but the app isn't installed", seconds=secs)
        return Installed("bought", pkg, title, listing.price, seconds=secs)
