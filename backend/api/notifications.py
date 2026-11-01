"""Notifications on Envoy's phone as a trigger source (phone-layer plan, contract 3: "Watches" that only a phone can do).

"Tell me when anyone comments on my post": a `notification` trigger names an app (or a few) on Envoy's phone and,
optionally, words its notification shows. While such a trigger is on, the watcher reads the phone's notifications every
few seconds (`adb shell dumpsys notification --noredact`, one adb call per phone per poll, through devices/android.py's
helper), and on a match:
1. writes a row to `notification_events` (redacted: below), which `phone_updates` (MCP) reads, so Muse hears it;
2. pushes to your iPhone ("Instagram: <title>"; push.py, kind `notification`; tapping it opens the trigger);
3. runs the trigger's action, if it has one, through the scheduler (api/scheduler.py): a goal or a routine, and in ask
   mode a "Should I…?" offer instead. With no action it only tells you and the agents.
   When ask mode raised an offer that pushes, that is the one push: not two buzzes for one comment.

**Which apps.** Watching is per app and off by default (Settings › Phones › Watch notifications from). A trigger for an
app you haven't turned on there stays quiet, and the phone isn't read for it: a trigger, or an agent proposing one,
can't widen what Envoy watches. Only enabled triggers on watched apps are polled, and only on their own phone (`spec.phone`,
a list_phones id; by default Envoy's phone, the first real phone connected).

**When it fires.** Each notification is a key plus its post time (an update to a notification is a new post time). It
fires once, and only if it was posted after the trigger started being watched (switched on, its app turned on, or the API
started): turning a trigger on doesn't replay what's already in the shade, and neither does a restart. A phone that was
unplugged catches up when it comes back: what landed meanwhile fires then. Group summaries and ongoing notifications
(progress, a foreground service) never fire. An update to one already showing fires when its words changed or it alerted
you again (Android's mInterruptionTimeMs moved); an app's silent re-post with the same words doesn't.
The phone's clock is read in the same adb call, so post times compare on the Mac's clock.

**Privacy** (contract 6). The dump is parsed in memory and dropped. Only matched notifications are stored, and their
title and text are redacted first: digit runs of 4 to 8 (and 3+3) become "••••", and everything after "code", "OTP",
"PIN" or "password" is cut. Nothing here logs a title, a text or the dump: logs/notifications.jsonl has ids, packages and
timings only. Matching (title_contains, text_contains, contains) reads the words in memory, before redaction.

Values for a trigger's goal template: `{notification.app}`, `{notification.title}` and `{notification.text}`, redacted and
cut to one short line (api/scheduler.py `_clean`). They fill a goal; they never are one, and the approval rules read the
template with its slots left empty, so a stranger's comment can't approve anything.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, Body, Depends, HTTPException

from api.store import REPO, TaskStore, new_id

LOG = REPO / "logs" / "notifications.jsonl"
SCHEMA = """
CREATE TABLE IF NOT EXISTS notification_events (
  id TEXT PRIMARY KEY, time REAL, phone TEXT, package TEXT, app TEXT, title TEXT, text TEXT, trigger_id TEXT
);
CREATE INDEX IF NOT EXISTS notification_events_time ON notification_events(time);
"""
SETTING = "notification_apps"  # the packages you let Envoy watch (Settings › Phones)
PACKAGE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")  # it goes into a shell command: nothing else gets in
PHONE = re.compile(r"^[\w.-]{1,64}$")
MAX_PACKAGES = 5  # per trigger: "anyone comments" across Instagram, TikTok and YouTube is one trigger
DEFAULT_APPS = ("com.instagram.android", "com.zhiliaoapp.musically", "com.google.android.youtube")  # listed even before the phone is read
# Names for apps Envoy doesn't otherwise know (api/routing.py's known_apps names the rest).
NAMES = {
    "com.instagram.android": "Instagram", "com.zhiliaoapp.musically": "TikTok", "com.ss.android.ugc.trill": "TikTok",
    "com.google.android.youtube": "YouTube", "com.instagram.barcelona": "Threads", "com.facebook.katana": "Facebook",
    "com.facebook.orca": "Messenger", "com.whatsapp": "WhatsApp", "com.google.android.gm": "Gmail", "com.twitter.android": "X",
    "com.snapchat.android": "Snapchat", "com.android.shell": "Test notifications (adb)",
}
HIDDEN_APPS = ("ai.envoy.", "com.github.uiautomator")  # Envoy's own helpers on the phone
QUIET_FLAGS = {"GROUP_SUMMARY": 0x200, "ONGOING_EVENT": 0x2, "FOREGROUND_SERVICE": 0x40}


# ---- reading a dump ---------------------------------------------------------------------------------

@dataclass(frozen=True)
class Shown:
    """One notification in the shade, as dumpsys shows it. Its words live only in memory."""
    key: str
    package: str
    title: str
    text: str
    posted_ms: int  # the phone's clock: when it was posted or last updated
    flags: frozenset[str]
    alerted_ms: int = 0  # when it last alerted you (sound, buzz, heads-up); 0 when dumpsys doesn't say

    @property
    def ident(self) -> str:
        return f"{self.key}@{self.posted_ms}"

    @property
    def quiet(self) -> bool:
        """A group's summary (its children carry the words) or an ongoing one (progress, a service): never an event."""
        return bool(self.flags & {"GROUP_SUMMARY", "ONGOING_EVENT", "FOREGROUND_SERVICE"})

    @property
    def words(self) -> str:
        return hashlib.sha256(f"{self.title}\x00{self.text}".encode()).hexdigest()[:16]


_RECORD = re.compile(r"^ {4}NotificationRecord\(0x[0-9a-fA-F]+: pkg=(\S+) ")
_FIELD = re.compile(r"^ {6}(key|flags|mUpdateTimeMs|mCreationTimeMs|mInterruptionTimeMs)=(.*)$")
_WHEN = re.compile(r"^\s+when=(\d+)")
_EXTRA = re.compile(r"^(\s+)(android\.[\w.]+)=(.*)$")
_TYPED = re.compile(r"^(?:String|SpannableString|SpannedString|SpannableStringBuilder|StringBuilder|CharSequence) \((.*)\)$", re.S)
_REDACTED = re.compile(r"^\w+ \[length=\d+\]$")


def _flags(raw: str) -> frozenset[str]:
    """`flags=` as Android 14+ prints it (names: `LOCAL_ONLY|GROUP_SUMMARY`) or older ones do (`0x210`, or a number)."""
    raw = raw.strip()
    try:
        n = int(raw, 16) if raw.lower().startswith("0x") else int(raw)
    except ValueError:
        return frozenset(p for p in raw.split("|") if p)
    return frozenset(name for name, bit in QUIET_FLAGS.items() if n & bit)


def _value(raw: str) -> tuple[str, bool]:
    """An extra's printed value: (its words, whether dumpsys redacted it)."""
    raw = raw.strip()
    if raw == "null":
        return "", False
    if _REDACTED.match(raw):
        return "", True  # dumpsys without --noredact prints `String [length=12]`
    m = _TYPED.match(raw)
    return (m.group(1) if m else ""), False


def parse(dump: str) -> list[Shown]:
    """The notifications in the shade ("Notification List:" sections only; not the enqueued, snoozed or archived ones),
    one per key. Several dumps in one string (one per package) are fine."""
    return [s for s, _ in _records(dump)]


def _records(dump: str) -> list[tuple[Shown, bool]]:
    out: dict[str, tuple[Shown, bool]] = {}
    in_list = False
    rec: dict[str, Any] | None = None
    extras: dict[str, list[str]] = {}
    extra_indent = cur = None

    def close() -> None:
        nonlocal rec
        if rec is None or not rec.get("key"):
            rec = None
            return
        vals = {k: _value("\n".join(v)) for k, v in extras.items()}
        title = vals.get("android.title.big", ("", False))[0] or vals.get("android.title", ("", False))[0]
        text = vals.get("android.bigText", ("", False))[0] or vals.get("android.text", ("", False))[0]
        posted = rec.get("mUpdateTimeMs") or rec.get("mCreationTimeMs") or rec.get("when") or 0
        shown = Shown(rec["key"], rec["package"], title, text, int(posted), rec.get("flags", frozenset()), rec.get("mInterruptionTimeMs", 0))
        out[shown.key] = (shown, any(r for _, r in vals.values()))
        rec = None

    for line in dump.splitlines():
        if rec is not None and extra_indent is not None:  # inside extras={ … }: first, since a value's own lines can start anywhere
            if line == extra_indent + "}":
                extra_indent = cur = None
            elif (m := _EXTRA.match(line)) and len(m.group(1)) == len(extra_indent) + 4:
                cur = m.group(2)
                extras[cur] = [m.group(3)]
            elif cur is not None:
                extras[cur].append(line)  # a value that runs over several lines (a message with line breaks)
            continue
        if line.startswith("  ") and not line.startswith("   "):  # a section of the dump (two spaces in)
            close()
            in_list = line.strip() == "Notification List:"
            continue
        if not line.startswith(" ") and line.strip():  # a new dump ("Current Notification Manager state:")
            close()
            in_list = False
            continue
        if not in_list:
            continue
        if m := _RECORD.match(line):
            close()
            rec, extras, extra_indent, cur = {"package": m.group(1)}, {}, None, None
            continue
        if rec is None:
            continue
        if line.strip() == "extras={":
            extra_indent = line[: len(line) - len(line.lstrip())]
        elif m := _FIELD.match(line):
            k, v = m.group(1), m.group(2).strip()
            if k == "flags":
                rec["flags"] = _flags(v)
            elif k == "key":
                rec["key"] = v
            elif v.isdigit():
                rec[k] = int(v)
        elif (m := _WHEN.match(line)) and "when" not in rec:
            rec["when"] = int(m.group(1))
    close()
    return list(out.values())


def report(dump: str, android: str = "") -> dict[str, Any]:
    """Pre-check P2: per package, how many notifications and how many of them have each field. Counts only: never a
    title or a text."""
    pkgs: dict[str, dict[str, int]] = {}
    for s, redacted in _records(dump):
        row = pkgs.setdefault(s.package, {"count": 0, "key": 0, "title": 0, "text": 0, "posted": 0, "quiet": 0, "redacted": 0})
        row["count"] += 1
        row["key"] += bool(s.key)
        row["title"] += bool(s.title.strip())
        row["text"] += bool(s.text.strip())
        row["posted"] += s.posted_ms > 0
        row["quiet"] += s.quiet
        row["redacted"] += redacted
    return {"android": android, "packages": dict(sorted(pkgs.items()))}


def command(packages: list[str]) -> str:
    """The one shell command a poll runs: the phone's clock, then each package's notifications. dumpsys's package filter
    matches parts of names, so `parse` still checks each record's package."""
    pkgs = [p for p in packages if PACKAGE.match(p)]
    return "date +%s%3N; " + "; ".join(f"dumpsys notification --noredact p {p}" for p in pkgs)


def _device_ms(first_line: str) -> int | None:
    m = re.match(r"\d+", first_line.strip())
    if not m:
        return None
    n = int(m.group(0))
    return n * 1000 if n < 10**11 else n  # a `date` without %N prints seconds


# ---- redaction and matching -------------------------------------------------------------------------

_AFTER = re.compile(r"(?i)\b(code|otp|pin|passcode|password)\b.*", re.S)
_DIGITS = re.compile(r"(?<!\d)(\d{3}[ -]\d{3}|\d{4,8})(?!\d)")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f‪-‮⁦-⁩]")


def redact(text: str, cap: int = 300) -> str:
    """What may be stored and shown of a notification's words: codes gone, one tidy line."""
    text = _AFTER.sub(lambda m: f"{m.group(1)} [hidden]", text or "")
    text = _DIGITS.sub("••••", text)
    text = re.sub(r"\s+", " ", _CONTROL.sub(" ", text)).strip()
    return text[: cap - 1] + "…" if len(text) > cap else text


def packages_of(spec: dict[str, Any]) -> list[str]:
    p = spec.get("package")
    return [p] if isinstance(p, str) else [x for x in p if isinstance(x, str)] if isinstance(p, list) else []


def check_spec(spec: dict[str, Any]) -> None:
    """A notification trigger's spec: `package` (one app, or a list of up to five), optional `title_contains`,
    `text_contains` or `contains` (title or text), `phone` (a list_phones id) and `push` (on by default). Normalized in place."""
    raw = spec.get("package")
    pkgs = [raw] if isinstance(raw, str) else raw if isinstance(raw, list) else []
    if not pkgs or not all(isinstance(p, str) for p in pkgs):
        raise ValueError('a notification trigger names an app: {"package": "com.instagram.android"}')
    if len(pkgs) > MAX_PACKAGES:
        raise ValueError(f"a notification trigger watches at most {MAX_PACKAGES} apps")
    if bad := [p for p in pkgs if not PACKAGE.match(p)]:
        raise ValueError(f"{bad[0][:60]!r} isn't an Android package name")
    spec["package"] = pkgs[0] if len(pkgs) == 1 else list(dict.fromkeys(pkgs))
    for k in ("title_contains", "text_contains", "contains"):
        v = spec.get(k)
        if v is None or v == "":
            spec.pop(k, None)
        elif not isinstance(v, str) or len(v.strip()) > 80 or "\n" in v:
            raise ValueError(f"{k} is a few words on one line")
        else:
            spec[k] = v.strip()
    if spec.get("phone") is not None and not (isinstance(spec["phone"], str) and PHONE.match(spec["phone"])):
        raise ValueError("phone is an id from list_phones")
    if "push" in spec and not isinstance(spec["push"], bool):
        raise ValueError("push is on or off (true or false)")


def matches(spec: dict[str, Any], n: Shown) -> bool:
    if n.package not in packages_of(spec):
        return False
    title, text = n.title.casefold(), n.text.casefold()
    for field, got in (("title_contains", title), ("text_contains", text), ("contains", f"{title}\n{text}")):
        if spec.get(field) and spec[field].casefold() not in got:
            return False
    return True


def app_name(package: str, names: dict[str, str] | None = None) -> str:
    if package in NAMES:
        return NAMES[package]
    if names and names.get(package):
        return names[package]
    tail = [p for p in package.split(".") if p not in ("com", "android", "app", "mobile", "org", "net")]
    return (tail[-1] if tail else package).replace("_", " ").title()


def describe(spec: dict[str, Any], phone_name: str | None = None, names: dict[str, str] | None = None) -> str:
    """When a notification trigger fires, in a few words (an offer's title holds 140 characters): 'when Instagram or TikTok
    notifies Envoy’s phone with “comment”'."""
    apps = [app_name(p, names) for p in packages_of(spec)]
    who = " or ".join([", ".join(apps[:-1]), apps[-1]] if len(apps) > 2 else apps) or "an app"
    about = []
    for k, word in (("contains", "with"), ("title_contains", "titled"), ("text_contains", "saying")):
        if spec.get(k):
            about.append(f"{word} “{str(spec[k])[:40]}”")
    return f"when {who} notifies {phone_name or 'Envoy’s phone'}" + (" " + " and ".join(about) if about else "")


def update_line(row: dict[str, Any], phone_name: str = "Envoy's phone") -> str:
    """Contract 3's line for phone_updates: `<App> on Envoy's phone: "<title>: <text>"` (already redacted)."""
    said = ": ".join(x for x in (row.get("title"), row.get("text")) if x)
    return f'{row.get("app") or "An app"} on {phone_name}: "{said}"' if said else f"{row.get('app') or 'An app'} on {phone_name} showed a notification"


# ---- the watcher ------------------------------------------------------------------------------------

class PhoneGone(Exception):
    """The phone didn't answer (unplugged, adb restarting, an emulator that stopped)."""


def adb_read(serial: str, packages: list[str]) -> str:
    from devices.android import adb
    r = adb(serial, "shell", command(packages), timeout=10)
    if r.returncode != 0:
        raise PhoneGone((r.stderr or "").strip().splitlines()[-1][:160] if (r.stderr or "").strip() else f"adb exited {r.returncode}")
    return r.stdout


@dataclass
class PhoneWatch:
    phone: str
    packages: list[str]
    online: bool = False
    last_ok: float | None = None
    last_error: str | None = None
    retry_at: float = 0.0
    backoff_s: float = 0.0
    poll_ms: float | None = None
    offset_s: float = 0.0  # the Mac's clock minus the phone's
    seen: dict[str, tuple[str, int]] | None = None  # key → (its words' hash, when it last alerted), as last read (None: not read yet)


class NotificationWatcher:
    """Reads notifications on the phones that have an enabled notification trigger for a watched app, every `every_s`."""

    def __init__(self, tasks: TaskStore, pool: Any, scheduler: Any, bus: Any, *, read: Callable[[str, list[str]], str] = adb_read,
                 clock: Callable[[], float] = time.time, every_s: float = 3.0, log: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.tasks, self.pool, self.scheduler, self.bus = tasks, pool, scheduler, bus
        self.read, self.clock, self.every_s = read, clock, every_s
        self.log = log or _log
        self.armed: dict[str, float] = {}  # trigger id → since when it's watched (Mac clock)
        self.phones: dict[str, PhoneWatch] = {}
        self._refreshed = 0.0
        self._names: tuple[float, dict[str, str]] | None = None
        self._task: asyncio.Task | None = None
        with tasks.lock:
            tasks.db.executescript(SCHEMA)
            tasks.db.commit()

    # ---- settings --------------------------------------------------------------------------------

    def apps_on(self) -> list[str]:
        return [p for p in self.tasks.setting(SETTING, []) or [] if isinstance(p, str) and PACKAGE.match(p)]

    def set_apps(self, apps: list[Any]) -> list[str]:
        on = list(dict.fromkeys(str(a) for a in apps if isinstance(a, str) and PACKAGE.match(a)))[:30]
        self.tasks.set_setting(SETTING, on)
        return on

    def names(self) -> dict[str, str]:
        """Apps' names Envoy knows (api/routing.py), read at most once a minute: it reads the routine library."""
        if self._names is None or time.monotonic() - self._names[0] > 60:
            try:
                from api.routing import known_apps
                got = known_apps(self.tasks, self.scheduler.routines)[1] if self.scheduler.routines is not None else {}
            except Exception:  # noqa: BLE001 - names are a nicety
                got = {}
            self._names = (time.monotonic(), got)
        return self._names[1]

    # ---- which phones, which triggers -----------------------------------------------------------------

    def default_phone(self) -> str | None:
        """Envoy's phone: the first real phone connected."""
        phones = getattr(self.pool, "phones", {}) or {}
        if not any(p.get("state") == "device" for p in phones.values()) and self.clock() - self._refreshed >= 15:
            self._refresh()
            phones = getattr(self.pool, "phones", {}) or {}
        return next((pid for pid, p in phones.items() if p.get("state") == "device"), None)

    def _refresh(self) -> None:
        self._refreshed = self.clock()
        try:
            self.pool.refresh_phones()
        except Exception:  # noqa: BLE001 - no adb: no phones
            pass

    def serial(self, phone: str) -> str | None:
        from devices.emulator import AVDS
        if phone in AVDS:
            return AVDS[phone]["serial"]
        p = (getattr(self.pool, "phones", {}) or {}).get(phone)
        if (p is None or p.get("state") != "device") and self.clock() - self._refreshed >= 5:
            self._refresh()
            p = (getattr(self.pool, "phones", {}) or {}).get(phone)
        return p["serial"] if p and p.get("state") == "device" else None

    def phone_name(self, phone: str) -> str:
        from api.devices import NAMES as EMULATORS, phone_ref
        if phone in EMULATORS:
            return f"the {EMULATORS[phone].lower()}"
        names = self.tasks.setting("phone_names", {}) or {}
        p = (getattr(self.pool, "phones", {}) or {}).get(phone) or {}
        return phone_ref({**p, "name": names.get(phone) or p.get("name")}, "your")

    def plan(self) -> dict[str, list[dict[str, Any]]]:
        """Phone → its enabled notification triggers on watched apps. Arms triggers that just started being watched."""
        now, on = self.clock(), set(self.apps_on())
        out: dict[str, list[dict[str, Any]]] = {}
        live: set[str] = set()
        for t in self.tasks.triggers():
            if t["kind"] != "notification" or not t["enabled"]:
                continue
            spec = dict(t["spec"])
            spec["package"] = [p for p in packages_of(spec) if p in on]  # an app you turned off isn't read
            if not spec["package"]:
                continue
            phone = t["spec"].get("phone") or self.default_phone()
            if not phone:
                continue
            live.add(t["id"])
            self.armed.setdefault(t["id"], now)
            out.setdefault(phone, []).append({**t, "spec": spec})
        for tid in [k for k in self.armed if k not in live]:
            del self.armed[tid]  # paused, deleted or its app turned off: watched again from when it comes back
        for phone in [k for k in self.phones if k not in out]:
            del self.phones[phone]
        return out

    # ---- one poll --------------------------------------------------------------------------------

    def read_phone(self, phone: str, packages: list[str]) -> tuple[float, float, int | None, str] | None:
        """(sent, returned, the phone's clock in ms, the dump), or None when the phone isn't there. Runs in a worker thread."""
        serial = self.serial(phone)
        if serial is None:
            raise PhoneGone("not connected")
        t0 = self.clock()
        dump = self.read(serial, packages)
        t1 = self.clock()
        first, _, rest = dump.partition("\n")
        return t0, t1, _device_ms(first), rest

    def due_phones(self, plan: dict[str, list[dict[str, Any]]]) -> list[tuple[str, list[str]]]:
        now = self.clock()
        out = []
        for phone, trigs in plan.items():
            pkgs = sorted({p for t in trigs for p in t["spec"]["package"]})
            w = self.phones.setdefault(phone, PhoneWatch(phone, pkgs))
            w.packages = pkgs
            if now >= w.retry_at:
                out.append((phone, pkgs))
        return out

    def look(self) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
        """Which phones to read, and what each one shows (or why it didn't answer). adb runs here: in a worker thread."""
        plan = self.plan()
        reads: dict[str, Any] = {}
        for phone, pkgs in self.due_phones(plan):
            try:
                reads[phone] = self.read_phone(phone, pkgs)
            except Exception as e:  # noqa: BLE001 - a phone that's gone must not stop the others
                reads[phone] = e
        return plan, reads

    def poll(self) -> list[dict[str, Any]]:
        """One pass in this thread (tests, a check from a script)."""
        return self.process(*self.look())

    async def poll_async(self) -> list[dict[str, Any]]:
        plan, reads = await asyncio.to_thread(self.look)
        return self.process(plan, reads)  # on the loop: tasks and offers start where the scheduler starts them

    def process(self, plan: dict[str, list[dict[str, Any]]], reads: dict[str, Any]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for phone, got in reads.items():
            w = self.phones[phone]
            if isinstance(got, Exception):
                self._gone(w, got)
                continue
            t0, t1, device_ms, dump = got
            try:
                shown = parse(dump)
            except Exception as e:  # noqa: BLE001 - never the dump in a log: its kind of error only
                self._gone(w, PhoneGone(f"couldn't read the notifications ({type(e).__name__})"))
                continue
            del dump
            if device_ms is not None:
                w.offset_s = (t0 + t1) / 2 - device_ms / 1000
            if not w.online:
                self.log({"time": t1, "event": "online", "phone": phone, "after_s": round(t1 - w.last_ok, 1) if w.last_ok else None})
                self.bus.publish("notification_watch", phone=phone, online=True)
            w.online, w.last_ok, w.last_error, w.backoff_s, w.retry_at = True, t1, None, 0.0, 0.0
            w.poll_ms = round((t1 - t0) * 1000, 1)
            before, w.seen = w.seen or {}, {s.key: (s.words, s.alerted_ms) for s in shown}
            for s in shown:
                if s.quiet or (s.key in before and before[s.key][0] == s.words and s.alerted_ms <= before[s.key][1]):
                    continue  # the same words, and it didn't alert you again: an app's silent re-post
                posted = s.posted_ms / 1000 + w.offset_s
                for trig in plan.get(phone, []):
                    if posted + 1.0 < self.armed.get(trig["id"], t1) or not matches(trig["spec"], s):
                        continue
                    if (ev := self._fire(trig, s, phone, posted, t1, w)) is not None:
                        events.append(ev)
        return events

    def _gone(self, w: PhoneWatch, e: Exception) -> None:
        now = self.clock()
        why = str(e) if isinstance(e, PhoneGone) else type(e).__name__
        if w.online or w.last_error is None:
            self.log({"time": now, "event": "offline", "phone": w.phone, "error": why[:160]})
            self.bus.publish("notification_watch", phone=w.phone, online=False, error=why[:160])
        w.online, w.last_error = False, why[:160]
        w.backoff_s = min(30.0, max(5.0, w.backoff_s * 2))
        w.retry_at = now + w.backoff_s

    def _fire(self, trig: dict[str, Any], s: Shown, phone: str, posted: float, seen_at: float, w: PhoneWatch) -> dict[str, Any] | None:
        key = f"n{hashlib.sha256(s.ident.encode()).hexdigest()[:12]}"  # the trigger's fired list keeps no words either
        stored = self.tasks.trigger(trig["id"])
        if stored is None or key in stored["fired"]:
            return None
        app = app_name(s.package, self.names())
        row = {"id": new_id("notif"), "time": seen_at, "phone": phone, "package": s.package, "app": app,
               "title": redact(s.title, 120), "text": redact(s.text, 300), "trigger_id": trig["id"]}
        with self.tasks.lock:
            self.tasks.db.execute("INSERT INTO notification_events (id, time, phone, package, app, title, text, trigger_id) VALUES (?,?,?,?,?,?,?,?)",
                                  tuple(row.values()))
            self.tasks.db.commit()
        stored_at = self.clock()
        values = {"notification.app": app, "notification.title": row["title"], "notification.text": row["text"]}
        action = trig["action"] or {}
        result, error = None, None
        try:
            result = self.scheduler.fire(stored, key, values)
        except Exception as e:  # noqa: BLE001 - the event still counts; the trigger's action is what failed
            error = f"{type(e).__name__}"
            self.bus.publish("trigger_error", trigger=trig["id"], error=f"notification trigger's action failed ({error})")
        asked = bool(action.get("ask") and result is not None and (action.get("goal") or action.get("routine")))
        offer_pushes = asked and self._offers_push()
        push = stored["spec"].get("push", True) is not False and not offer_pushes
        self.bus.publish("notification_matched", event=row, trigger=trig["id"], name=trig["name"], phone_name=self.phone_name(phone), push=push)
        rec = {"time": self.clock(), "event": "matched", "id": row["id"], "phone": phone, "package": s.package, "trigger": trig["id"],
               "posted_at": round(posted, 3), "seen_ms": round((seen_at - posted) * 1000), "stored_ms": round((stored_at - posted) * 1000),
               "push_ms": round((self.clock() - posted) * 1000) if push else None, "pushed": push, "asked": asked,
               "started": (result or {}).get("id") if result and not asked else None, "poll_ms": w.poll_ms, "offset_ms": round(w.offset_s * 1000),
               "error": error}
        self.log(rec)
        return {**row, "latency": rec}

    def _offers_push(self) -> bool:
        from api.offers import pushes
        return pushes("trigger", self.tasks.setting("proactivity"))

    # ---- the loop --------------------------------------------------------------------------------

    def run_in_background(self) -> None:
        self._task = asyncio.get_running_loop().create_task(self._loop())

    async def _loop(self) -> None:
        while True:
            t0 = time.monotonic()
            try:
                await self.poll_async()
            except Exception as e:  # noqa: BLE001 - a bad poll must not stop watching
                self.log({"time": self.clock(), "event": "error", "error": type(e).__name__})
            await asyncio.sleep(max(0.5, self.every_s - (time.monotonic() - t0)))

    # ---- reading back ----------------------------------------------------------------------------

    def events(self, limit: int = 30, since: float | None = None) -> list[dict[str, Any]]:
        with self.tasks.lock:
            rows = self.tasks.db.execute("SELECT * FROM notification_events WHERE time>? ORDER BY time DESC LIMIT ?",
                                         (since or 0, limit)).fetchall()
        return [dict(r) for r in rows]

    def status(self) -> list[dict[str, Any]]:
        return [{"phone": w.phone, "name": self.phone_name(w.phone), "packages": w.packages, "online": w.online, "last_ok": w.last_ok,
                 "error": w.last_error, "poll_ms": w.poll_ms} for w in list(self.phones.values())]  # a poll may change it meanwhile

    def installed(self) -> list[str]:
        """Third-party apps on Envoy's phone, for the Settings list (`pm list packages -3`, read when you open it)."""
        phone = self.default_phone()
        serial = self.serial(phone) if phone else None
        if serial is None:
            return []
        try:
            from devices.android import adb
            out = adb(serial, "shell", "pm list packages -3", timeout=10).stdout
        except Exception:  # noqa: BLE001
            return []
        return sorted({ln.split(":", 1)[1].strip() for ln in out.splitlines() if ln.startswith("package:")} - {""})


def _log(rec: dict[str, Any]) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def notifications_router(ctx: Any, session: Callable[..., None]) -> APIRouter:
    router = APIRouter()
    watcher: NotificationWatcher = ctx.notifications
    cache: dict[str, Any] = {"at": 0.0, "apps": []}

    @router.get("/api/settings/notifications", dependencies=[Depends(session)])
    def get_settings(refresh: bool = False) -> dict[str, Any]:
        """Watch notifications from: the apps on Envoy's phone, each off until you turn it on."""
        if refresh or time.time() - cache["at"] > 600:
            if installed := watcher.installed():
                cache.update(at=time.time(), apps=installed)
        on, names = watcher.apps_on(), watcher.names()
        pkgs = sorted({*cache["apps"], *DEFAULT_APPS, *on} - {p for p in cache["apps"] if p.startswith(HIDDEN_APPS)},
                      key=lambda p: app_name(p, names).lower())
        return {"apps": [{"package": p, "name": app_name(p, names), "on": p in on, "installed": p in cache["apps"]} for p in pkgs],
                "on": on, "read_from_phone": bool(cache["apps"]), "watching": watcher.status()}

    @router.post("/api/settings/notifications", dependencies=[Depends(session)])
    def set_settings(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        apps = body.get("apps")
        if not isinstance(apps, list):
            raise HTTPException(400, 'give the apps to watch: {"apps": ["com.instagram.android"]}')
        return {"on": watcher.set_apps(apps)}

    @router.get("/api/notifications", dependencies=[Depends(session)])
    def list_events(limit: int = 20) -> dict[str, Any]:
        """What notification triggers caught, newest first (redacted), and what's being watched now."""
        return {"events": watcher.events(min(max(limit, 1), 200)), "watching": watcher.status()}

    return router


def _main(argv: list[str]) -> int:
    """`python -m api.notifications report <serial>`: pre-check P2 on a phone, counts only."""
    if len(argv) != 2 or argv[0] != "report":
        print("usage: python -m api.notifications report <adb serial>")
        return 2
    from devices.android import adb
    android = adb(argv[1], "shell", "getprop ro.build.version.release", timeout=10).stdout.strip()
    r = adb(argv[1], "shell", "dumpsys notification --noredact", timeout=20)
    if r.returncode != 0:
        print(json.dumps({"error": "the phone didn't answer"}))
        return 1
    print(json.dumps(report(r.stdout, android), indent=1))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
