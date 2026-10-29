"""Files from the Mac to the phone (final-features plan, contract 3): the outbox, `push_file`, and the handoff record.

Muse for Mac and Envoy's backend run on the same Mac, so a folder both can reach is the handoff that works whatever
Muse's connector supports:

- **The outbox** is a folder on the Mac, watched every few seconds: the `handoff.outbox` setting, else `$ENVOY_OUTBOX`,
  else `~/Envoy Outbox` (only the live API uses that one). On start, what's already there is recorded as seen, so a
  leftover clip never turns into anything after a restart. A media file counts once its size has held for 2 s. Hidden
  files, partial downloads, symlinks, sidecars, anything that isn't an image or video by its bytes, and anything over
  500 MB are ignored.
- **A sidecar** `<same name>.json` (`clip.json` or `clip.mp4.json`) gives typed values only: `{"app", "caption"}`, where
  `app` must be a key of `HANDOFF_TEMPLATES` and the caption is cleaned and capped. Like an email trigger's values, it
  never supplies the goal or the plan: the goal is the template's, and the caption only fills its slot.
- **`push_file(device, path)`** copies an image to `Pictures/Envoy/` or a video to `Movies/Envoy/` on a phone from the
  pool (`envoy-test`, `phone-…`; never an adb serial) and makes it the gallery's newest item: the copy's own dates (an
  MP4's creation time, a JPEG's EXIF dates, which the media store reads as "date taken") and its file date are now, and
  the media scanner is asked for it until its row is no longer pending (Android 15 leaves a file adb wrote pending,
  which galleries hide, until it is scanned).
- **Nothing goes to a real phone without the user's yes.** A new outbox file raises an offer (contract 1, kind
  `handoff`): "Put clip.mp4 on your Pixel 5 and post it to Instagram?", or just "Put clip.mp4 on your Pixel 5?" when no
  sidecar names an app (it waits a few seconds for one). Accepting it, in Envoy's own app, pushes the file and starts
  the template's task (the goal filled with the caption, the request the template's fixed words), with the phone your yes
  covered (`phone_ok`, so no second "Use your phone?"). The user can also send a file from their own session
  (`POST /api/handoff/{id}/send`). MCP's `send_to_phone` pushes to an emulator at once; for the real phone it raises the
  same offer. Only files that arrive while Envoy runs raise offers.

Statuses: waiting → offered → sent → posted (the task after it finished) | failed. A declined or expired offer puts the
file back to waiting.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urljoin, urlsplit

from api.routing import TEST_EMULATOR, choose
from api.store import TaskStore, new_id

try:  # contract 2: the "Before I start" lines on a handoff offer's card
    from api.preflight import check as preflight_check
except ImportError:  # pragma: no cover - depends on what's merged
    preflight_check = None

MAX_BYTES = 500 * 1024 * 1024
SETTLE_S = 2.0  # a file counts once its size has held this long
IMAGES = {".jpg", ".jpeg", ".png", ".heic", ".webp"}
VIDEOS = {".mp4", ".mov", ".m4v"}
PARTIAL = {".part", ".crdownload", ".download"}
DIRS = {"image": "Pictures/Envoy", "video": "Movies/Envoy"}  # under /sdcard, so the gallery's own folders show them
MEDIA = {"image": "content://media/external/images/media", "video": "content://media/external/video/media"}
CONTENT_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/heic": ".heic", "image/heif": ".heic", "image/webp": ".webp",
                 "video/mp4": ".mp4", "video/quicktime": ".mov", "video/x-m4v": ".m4v"}
SIDECAR_MAX = 64 * 1024
# How long a new file waits for its sidecar before its offer is made without one. Muse for Mac wrote one 23 s after
# moving the video (a permission prompt between, Oct 29); a sidecar that comes later still replaces the offer (scan).
SIDECAR_GRACE_S = 30.0

SCHEMA = """
CREATE TABLE IF NOT EXISTS handoffs (
  id TEXT PRIMARY KEY, name TEXT, size INTEGER, kind TEXT, app TEXT, caption TEXT, status TEXT, device TEXT,
  remote_path TEXT, media_uri TEXT, offer_id TEXT, task_id TEXT, created_at REAL, updated_at REAL, error TEXT,
  note TEXT, origin TEXT, mtime REAL
);
CREATE INDEX IF NOT EXISTS handoffs_name ON handoffs(name, size);
"""

# What a file from the Mac becomes on the phone, by app (lowercase key, as a sidecar's `app` names it).
# - `goal`: what the agent works from, with typed slots ({caption}); `request`: `handoff_request(goal)`, the same words
#   with every slot left empty and no publishing words, which is all the approval rules read (contract 1). The caption
#   fills the goal and the routine's inputs, never the request; and since the request never names Share or Post, the
#   step that publishes always asks.
# - `title`: the offer's question, with {file} and {device}. `device_pref`: "phone" asks for the real phone the way
#   "on my phone" does; "emulator" leaves it to routing (the per-app "use my phone" setting, apps that block emulators).
# - optionally `routine` and `inputs` (routine input → sidecar field).
# This one only puts the file in the gallery; creator-workflow adds Instagram's entry.
HANDOFF_TEMPLATES: dict[str, dict[str, Any]] = {
    "gallery": {"label": "the phone's gallery", "package": None, "goal": None, "request": None, "caption_limit": 2200,
                "device_pref": "emulator", "title": "Put {file} on {device}?"},
}


class HandoffError(ValueError):
    """Said to the caller as it is: a file that isn't allowed, a phone that isn't there."""


# ---- what counts as a file to send ------------------------------------------------------------------


def kind_of(name: str) -> str | None:
    ext = Path(name).suffix.lower()
    return "image" if ext in IMAGES else "video" if ext in VIDEOS else None


def sniff(path: Path) -> str | None:
    """The file's kind from its first bytes, so a renamed document isn't sent as a photo."""
    try:
        with path.open("rb") as f:
            head = f.read(16)
    except OSError:
        return None
    if head.startswith(b"\xff\xd8\xff") or head.startswith(b"\x89PNG\r\n\x1a\n") or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"):
        return "image"
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        return "image" if brand in (b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1") else "video"
    if head[4:8] in (b"moov", b"mdat", b"wide", b"free", b"skip"):  # QuickTime files without an ftyp box
        return "video"
    return None


def ignored(path: Path) -> bool:
    name = path.name
    return name.startswith(".") or path.suffix.lower() in PARTIAL or path.suffix.lower() == ".json" or kind_of(name) is None


def clean_caption(text: Any, limit: int) -> str:
    """Typed text only: control and direction-override characters out, line breaks kept, capped."""
    s = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    s = "".join(ch for ch in s if ch == "\n" or (unicodedata.category(ch) != "Cc" and not 0x202A <= ord(ch) <= 0x202E
                                                and not 0x2066 <= ord(ch) <= 0x2069))
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s[:limit].rstrip()


def read_sidecar(media: Path) -> tuple[str | None, str | None, str | None]:
    """(app, caption, note) from `<stem>.json` or `<name>.json` next to the file. Anything but those two typed values is
    dropped; an app that isn't a template key is dropped, and the note says so."""
    for p in (media.with_suffix(".json"), media.with_name(media.name + ".json")):
        try:
            if p.is_symlink() or not p.is_file() or p.stat().st_size > SIDECAR_MAX:
                continue
            data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            return None, None, f"{p.name} isn't readable JSON"
        if not isinstance(data, dict):
            return None, None, f"{p.name} isn't a JSON object"
        app = data.get("app")
        app = app.strip().lower() if isinstance(app, str) else None
        note = None
        if app and app not in HANDOFF_TEMPLATES:
            note, app = f"{p.name} names an app Envoy has no template for", None
        limit = HANDOFF_TEMPLATES[app or "gallery"]["caption_limit"]
        caption = clean_caption(data["caption"], limit) if isinstance(data.get("caption"), str) else None
        return app, caption or None, note
    return None, None, None


# ---- dating a copy now, so "the newest video in my gallery" is this one ----------------------------------

MP4_EPOCH = 2082844800  # an MP4's clock counts seconds from 1904; Unix time from 1970


def _boxes(f: Any, start: int, end: int) -> Any:
    """(type, start, header size, end) of each ISO BMFF box (MP4, MOV, M4V, HEIC) between start and end."""
    pos = start
    while pos + 8 <= end:
        f.seek(pos)
        size, typ = struct.unpack(">I4s", f.read(8))
        head = 8
        if size == 1:
            size, head = struct.unpack(">Q", f.read(8))[0], 16
        elif size == 0:
            size = end - pos
        if size < head:
            return
        yield typ, pos, head, min(pos + size, end)
        pos += size


def redate_video(path: Path, now: float) -> int:
    """Set the movie's, tracks' and media's creation and modification times to now, in place. Returns how many."""
    t = int(now) + MP4_EPOCH
    n = 0
    with path.open("r+b") as f:
        def walk(start: int, stop: int) -> None:
            nonlocal n
            for typ, pos, head, end in _boxes(f, start, stop):
                if typ in (b"moov", b"trak", b"mdia"):
                    walk(pos + head, end)
                elif typ in (b"mvhd", b"tkhd", b"mdhd") and end - pos >= head + 20:
                    f.seek(pos + head)
                    version = f.read(1)[0]
                    f.seek(pos + head + 4)
                    f.write(struct.pack(">QQ", t, t) if version == 1 else struct.pack(">II", t & 0xFFFFFFFF, t & 0xFFFFFFFF))
                    n += 1
        walk(0, f.seek(0, 2))
    return n


def redate_jpeg(path: Path, now: float) -> int:
    """Set the EXIF DateTime, DateTimeOriginal and DateTimeDigitized to now, in place (the image itself isn't
    re-encoded). Returns how many."""
    stamp = time.strftime("%Y:%m:%d %H:%M:%S", time.localtime(now)).encode()
    n = 0
    with path.open("r+b") as f:
        data = f.read(1 << 20)  # the EXIF block comes first, and is at most 64 KB
        pos = 2
        while pos + 4 <= len(data) and data[pos] == 0xFF and data[pos + 1] not in (0xDA, 0xD9):
            length = struct.unpack(">H", data[pos + 2:pos + 4])[0]
            if data[pos + 1] == 0xE1 and data[pos + 4:pos + 10] == b"Exif\0\0":
                tiff = pos + 10
                bo = "<" if data[tiff:tiff + 2] == b"II" else ">"
                ifds, seen = [struct.unpack(bo + "I", data[tiff + 4:tiff + 8])[0]], set()
                while ifds:
                    off = ifds.pop()
                    if off in seen or tiff + off + 2 > len(data):
                        continue
                    seen.add(off)
                    count = struct.unpack(bo + "H", data[tiff + off:tiff + off + 2])[0]
                    for i in range(count):
                        e = tiff + off + 2 + 12 * i
                        if e + 12 > len(data):
                            break
                        tag, typ, cnt, val = struct.unpack(bo + "HHII", data[e:e + 12])
                        if tag == 0x8769:  # the Exif sub-IFD, where the original and digitized dates are
                            ifds.append(val)
                        elif tag in (0x0132, 0x9003, 0x9004) and typ == 2 and cnt == 20 and tiff + val + 19 <= len(data):
                            f.seek(tiff + val)
                            f.write(stamp)
                            n += 1
                return n
            pos += 2 + length
    return n


def dated_now(src: Path, kind: str, folder: Path, now: float) -> Path:
    """A copy of the file in `folder` whose own dates say now; the file on the Mac is left as it is. A file whose
    structure can't be read is copied unchanged."""
    copy = folder / src.name
    shutil.copyfile(src, copy)
    try:
        if kind == "video":
            redate_video(copy, now)
        elif src.suffix.lower() in (".jpg", ".jpeg"):
            redate_jpeg(copy, now)
    except (OSError, struct.error, IndexError, ValueError):
        shutil.copyfile(src, copy)
    return copy


def safe_name(name: str) -> str:
    """A file name the phone's shell and media store take as it is: letters, digits, dot, dash, underscore."""
    p = Path(name)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", unicodedata.normalize("NFKD", p.stem).encode("ascii", "ignore").decode()).strip("-.") or "file"
    return stem[:80] + p.suffix.lower()


def fill(template: str, values: dict[str, str]) -> str:
    """A template's {slots} filled with typed values, one pass (a value with braces in it fills nothing)."""
    return re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), ""), template)


# Words that publish or send something for others to see. The task an accepted handoff offer starts has a direct
# source, and the approval rules (policy/approval_rules.py) let a step through without asking when the request names
# all of its button's words; so a handoff's request never says these, and Share, Post, Publish or Send is always the
# user's to approve on the screen itself.
PUBLISHING = re.compile(r"\b(share|shares|sharing|post|posts|posting|publish|publishes|publishing|send|sends|sending|submit|submits|"
                        r"upload|uploads|uploading|tweet|tweets|reply|replies)\b", re.I)


def handoff_request(goal: str) -> str:
    """A handoff template's request: its goal with every slot left empty and no publishing words ("Post the newest
    video … with this caption: {caption}" → "the newest video … with this caption")."""
    return re.sub(r"\s{2,}", " ", PUBLISHING.sub(" ", without_slots(goal))).strip(" :,")


def without_slots(template: str) -> str:
    """The template with every slot left empty: the fixed words a person wrote (contract 1's `request`)."""
    return re.sub(r"\s{2,}", " ", re.sub(r"[\"“]?\{\w+\}[\"”]?", "", template)).strip(" :,")  # a quoted slot goes with its quotes


# ---- the handoff record, the outbox, and the phone ----------------------------------------------------


def _adb(serial: str, args: list[str], timeout: float) -> subprocess.CompletedProcess:
    from devices.android import _adb_path  # the same adb binary the device layer uses
    return subprocess.run([_adb_path(), "-s", serial, *args], capture_output=True, text=True, timeout=timeout)


class Handoff:
    """`adb(serial, args, timeout)` runs one adb command on one phone (a fake in tests). `resolve_ip(host)` is DNS for
    downloads (tests stub it). No module-level state: each `build()` gets its own."""

    def __init__(self, tasks: TaskStore, pool: Any, bus: Any, *, adb: Callable[..., subprocess.CompletedProcess] = _adb,
                 clock: Callable[[], float] = time.time, settle_s: float = SETTLE_S, every_s: float = 3.0, max_bytes: int = MAX_BYTES,
                 resolve_ip: Callable[[str], list[str]] | None = None, offers: Any = None, runner: Any = None,
                 public_ip: Callable[[Any], bool] | None = None) -> None:
        """`offers` (api/offers.py) and `runner`: with them, new files raise offers and an accepted one starts its task."""
        self.tasks, self.pool, self.bus, self.adb, self.clock = tasks, pool, bus, adb, clock
        self.offers, self.runner = offers, runner
        self._fresh: set[str] = set()  # items this watcher recorded that have no offer yet
        self.settle_s, self.every_s, self.max_bytes = settle_s, every_s, max_bytes
        self.resolve_ip = resolve_ip or _resolve
        self.public_ip = public_ip or (lambda ip: ip.is_global and not ip.is_multicast)  # where a download may connect
        self.index_wait_s = 10.0  # how long the gallery gets to pick a file up
        self._folder: Path | None = None  # the folder the seen list below belongs to
        self._seen: dict[str, float] = {}  # name → mtime when the watcher started on this folder
        self._sizes: dict[str, tuple[int, float, float]] = {}  # name → (size, mtime, since when it has had them)
        self._task: asyncio.Task | None = None
        with tasks.lock:
            tasks.db.executescript(SCHEMA)
            tasks.db.commit()
        if offers is not None:
            offers.register("handoff", self.accept)
        if isinstance(getattr(bus, "listeners", None), list):
            bus.listeners.append(self.on_event)

    # ---- the outbox folder --------------------------------------------------------------------

    def outbox(self) -> Path:
        configured = (self.tasks.setting("handoff", {}) or {}).get("outbox") or os.environ.get("ENVOY_OUTBOX")
        folder = Path(configured).expanduser() if configured else Path.home() / "Envoy Outbox"
        folder.mkdir(parents=True, exist_ok=True)
        return folder.resolve()

    def set_outbox(self, path: str) -> Path:
        p = Path(str(path or "")).expanduser()
        if not p.is_absolute():
            raise HandoffError("the outbox is a full path to a folder on this Mac")
        if p.exists() and not p.is_dir():
            raise HandoffError(f"{p} is a file, not a folder")
        self.tasks.set_setting("handoff", {**(self.tasks.setting("handoff", {}) or {}), "outbox": str(p)})
        return self.outbox()

    def outbox_file(self, name: str) -> Path:
        """A file named inside the outbox, never a path: no folders, `..`, `~` or absolute paths, no symlinks."""
        name = str(name or "").strip()
        if not name or "/" in name or "\\" in name or name in (".", "..") or name.startswith(("~", ".")) or "\x00" in name:
            raise HandoffError("give the name of a file in Envoy's outbox (no folders or paths), or an https URL")
        folder = self.outbox()
        p = folder / name
        if p.is_symlink() or p.resolve().parent != folder:
            raise HandoffError("that file isn't in Envoy's outbox")
        if not p.is_file():
            raise HandoffError(f"there's no {name} in Envoy's outbox")
        self._check_file(p)
        return p

    def _check_file(self, p: Path) -> str:
        kind = kind_of(p.name)
        if kind is None:
            raise HandoffError("only photos and videos (jpg, jpeg, png, heic, webp, mp4, mov, m4v) go to the phone")
        if p.stat().st_size > self.max_bytes:
            raise HandoffError(f"{p.name} is over {self.max_bytes // (1024 * 1024)} MB")
        if sniff(p) != kind:
            raise HandoffError(f"{p.name} isn't a {kind} file by its contents")
        return kind

    # ---- watching the outbox ------------------------------------------------------------------

    def run_in_background(self) -> None:
        self._task = asyncio.get_running_loop().create_task(self._loop())

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self.scan)
            except Exception as e:  # noqa: BLE001 - a bad file must not stop the watcher
                self.bus.publish("handoff_error", error=f"{type(e).__name__}: {e}"[:300])
            await asyncio.sleep(self.every_s)

    def scan(self) -> list[dict[str, Any]]:
        """One look at the outbox. The first look at a folder only records what's there; later ones record each new file
        once its size has held for `settle_s`. Returns the items recorded."""
        folder = self.outbox()
        now = self.clock()
        files = {}
        for p in folder.iterdir():
            try:
                if p.is_symlink() or not p.is_file() or ignored(p) or p.resolve().parent != folder:
                    continue
                st = p.stat()
            except OSError:
                continue
            files[p.name] = (st.st_size, st.st_mtime)
        if folder != self._folder:  # first look (or the outbox moved): what's already there is old
            self._folder, self._seen, self._sizes = folder, {n: m for n, (_, m) in files.items()}, {}
            return []
        new = []
        for name, (size, mtime) in files.items():
            if self._seen.get(name) == mtime:
                continue
            was = self._sizes.get(name)
            if was is None or was[:2] != (size, mtime):  # still being written
                self._sizes[name] = (size, mtime, now)
                continue
            if now - was[2] < self.settle_s:
                continue
            self._seen[name] = mtime
            self._sizes.pop(name, None)
            if size > self.max_bytes or self._known(name, size, mtime):
                continue
            try:
                kind = self._check_file(folder / name)
            except (HandoffError, OSError):
                continue
            item = self._record(folder / name, kind, origin="outbox")
            self._fresh.add(item["id"])
            new.append(item)
        for name in list(self._sizes):
            if name not in files:
                self._sizes.pop(name)
        # A sidecar written after its video still counts while the file waits, and replaces an offer made without it.
        for item in self.items(status="waiting") + self.items(status="offered"):
            if item["name"] in files and item["origin"] in ("outbox", "mcp", "url"):
                app, caption, note = read_sidecar(folder / item["name"])
                if (app, caption) != (item["app"], item["caption"]) and (app or caption):
                    device = self.default_device(app) if app != item["app"] and item["origin"] == "outbox" else (item["device"], note)
                    self._update(item["id"], app=app, caption=caption, device=device[0], note=note or device[1])
                    if item["status"] == "offered" and item["offer_id"] and self.offers is not None:
                        self.reoffer(item, "A caption file for it arrived from your Mac: asking again with it")
        # Its offer: at once when a sidecar named the app, else once the sidecar has had its chance.
        for hid in list(self._fresh):
            item = self.item(hid)
            if item is None or item["status"] != "waiting" or item["offer_id"]:
                self._fresh.discard(hid)
            elif item["app"] or now - item["created_at"] >= SIDECAR_GRACE_S:
                self._fresh.discard(hid)
                self.offer(hid, "outbox")
        return new

    def _known(self, name: str, size: int, mtime: float) -> bool:
        with self.tasks.lock:
            return self.tasks.db.execute("SELECT 1 FROM handoffs WHERE name=? AND size=? AND mtime=?", (name, size, mtime)).fetchone() is not None

    def _record(self, path: Path, kind: str, origin: str, device: str | None = None) -> dict[str, Any]:
        app, caption, note = read_sidecar(path)
        st = path.stat()
        hid = new_id("handoff")
        now = self.clock()
        if device is None:
            device, why = self.default_device(app)
            note = note or why
        with self.tasks.lock:
            self.tasks.db.execute("INSERT INTO handoffs (id, name, size, kind, app, caption, status, device, created_at, updated_at, note, origin, mtime) "
                                  "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                  (hid, path.name, st.st_size, kind, app, caption, "waiting", device, now, now, note, origin, st.st_mtime))
            self.tasks.db.commit()
        item = self.item(hid)
        self.bus.publish("handoff", item=item)
        return item  # type: ignore[return-value]

    def _update(self, hid: str, **fields: Any) -> dict[str, Any] | None:
        fields["updated_at"] = self.clock()
        with self.tasks.lock:
            self.tasks.db.execute(f"UPDATE handoffs SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?", (*fields.values(), hid))
            self.tasks.db.commit()
        item = self.item(hid)
        if item:
            self.bus.publish("handoff", item=item)
        return item

    def item(self, hid: str) -> dict[str, Any] | None:
        with self.tasks.lock:
            row = self.tasks.db.execute("SELECT * FROM handoffs WHERE id=?", (hid,)).fetchone()
        return self._view(dict(row)) if row else None

    def items(self, limit: int = 50, status: str | None = None, since: float | None = None) -> list[dict[str, Any]]:
        q, args = "SELECT * FROM handoffs WHERE 1=1", []
        if status:
            q, args = q + " AND status=?", [*args, status]
        if since is not None:
            q, args = q + " AND updated_at>?", [*args, since]
        with self.tasks.lock:
            rows = self.tasks.db.execute(q + " ORDER BY created_at DESC LIMIT ?", (*args, limit)).fetchall()
        return [self._view(dict(r)) for r in rows]

    def _view(self, row: dict[str, Any]) -> dict[str, Any]:
        row.pop("mtime", None)
        row["device_name"] = self.device_name(row.get("device"))
        return row

    # ---- which phone -------------------------------------------------------------------------

    def device_name(self, did: str | None) -> str | None:
        if not did:
            return None
        if did.startswith("phone-"):
            return (getattr(self.pool, "phones", {}).get(did) or {}).get("model") or "Android phone"
        from api.devices import NAMES
        return NAMES.get(did, did)

    def default_device(self, app: str | None) -> tuple[str | None, str | None]:
        """The phone routing picks for the template's app (the per-app "use my phone" setting, apps that block
        emulators); with no app, the default emulator. (pool id or None, why not)."""
        tpl = HANDOFF_TEMPLATES[app or "gallery"]
        if not tpl.get("package") and tpl.get("device_pref") != "phone":
            return TEST_EMULATOR, None
        try:
            self.pool.refresh_phones()
        except Exception:  # noqa: BLE001 - no adb: only the emulators
            pass
        c = choose(tpl.get("package"), asked="phone" if tpl.get("device_pref") == "phone" else None,
                   phone_apps=self.tasks.setting("phone_apps", []) or [], phones=list(getattr(self.pool, "phones", {}).values()),
                   learned=self.tasks.setting("phone_apps_learned", {}) or {})
        return c.device, c.error

    def pick(self, device: str | None, app: str | None = None) -> str:
        """A pool id from what a caller asked for: a pool id, "phone", "emulator", or None (routing decides)."""
        if device in (None, "", "auto"):
            did, why = self.default_device(app)
        elif device == "emulator":
            did, why = TEST_EMULATOR, None
        elif device == "phone":
            try:
                self.pool.refresh_phones()
            except Exception:  # noqa: BLE001
                pass
            usable = [p for p in getattr(self.pool, "phones", {}).values() if p.get("state") == "device"]
            did, why = (usable[0]["id"], None) if usable else (None, "the user's Android phone isn't connected")
        else:
            did, why = device, None
        if not did:
            raise HandoffError(why or "no phone can take this file")
        if not did.startswith("phone-") and did not in getattr(self.pool, "leases", {}):
            raise HandoffError(f"there's no phone called {did}; the phones are {', '.join(sorted(getattr(self.pool, 'leases', {})))}")
        return did

    def serial(self, did: str) -> str:
        """The adb serial behind a pool id, found here so callers never name one."""
        if did.startswith("phone-"):
            if did not in getattr(self.pool, "phones", {}):
                try:
                    self.pool.refresh_phones()
                except Exception:  # noqa: BLE001
                    pass
            p = getattr(self.pool, "phones", {}).get(did)
            if p is None:
                raise HandoffError("the user's Android phone isn't connected")
            if p.get("state") != "device":
                raise HandoffError("the phone is connected but hasn't allowed USB debugging yet")
            return p["serial"]
        from devices.emulator import AVDS
        if did not in AVDS:
            raise HandoffError(f"there's no phone called {did}")
        return AVDS[did]["serial"]

    # ---- putting a file on a phone --------------------------------------------------------------

    def push_file(self, device: str, local_path: str | Path) -> dict[str, Any]:
        """Copy an image or video into the phone's shared media and make the gallery see it as the newest item.
        Returns {device, remote_path, media_uri}."""
        src = Path(local_path)
        if src.is_symlink() or not src.is_file():
            raise HandoffError(f"{src.name} isn't a file")
        kind = self._check_file(src)
        serial = self.serial(device)
        state = self.adb(serial, ["get-state"], timeout=10)
        if state.returncode != 0 or state.stdout.strip() != "device":  # said plainly, not as adb's "device 'emulator-5554' not found"
            raise HandoffError(f"the {self.device_name(device)} ({device}) isn't running" if not device.startswith("phone-")
                               else "the user's Android phone isn't connected")
        folder = f"/sdcard/{DIRS[kind]}"
        self._sh(serial, f"mkdir -p {folder}")
        name = self._free_name(serial, folder, safe_name(src.name))
        remote = f"{folder}/{name}"
        with tempfile.TemporaryDirectory(prefix="envoy-handoff-") as tmp:
            out = self.adb(serial, ["push", str(dated_now(src, kind, Path(tmp), time.time())), remote], timeout=600)
        if out.returncode != 0:
            raise HandoffError(f"adb push failed: {(out.stderr or out.stdout).strip()[:200]}")
        # adb push keeps the Mac's modified time; the gallery sorts by date, so this copy is dated now.
        self._sh(serial, f"touch {remote}")
        uri = self._indexed(serial, kind, remote, self.index_wait_s)
        return {"device": device, "remote_path": remote, "media_uri": uri}

    def _sh(self, serial: str, cmd: str, timeout: float = 30) -> str:
        out = self.adb(serial, ["shell", cmd], timeout=timeout)
        if out.returncode != 0:
            raise HandoffError(f"on the phone, {cmd.split()[0]} failed: {(out.stderr or out.stdout).strip()[:200]}")
        return out.stdout

    def _free_name(self, serial: str, folder: str, name: str) -> str:
        """A name not already in the folder, so the media store adds a new item (dated now) instead of updating one."""
        have = set(self.adb(serial, ["shell", f"ls {folder}"], timeout=30).stdout.split())
        stem, ext, n = Path(name).stem, Path(name).suffix, 2
        while name in have:
            name, n = f"{stem}-{n}{ext}", n + 1
        return name

    def _indexed(self, serial: str, kind: str, remote: str, wait_s: float = 10) -> str:
        """The file's media store row once the gallery can see it. A write through /sdcard makes a row that stays
        pending (hidden from galleries, Android 15) until the media scanner reads the file, so it is always asked."""
        rel, name = remote.removeprefix("/sdcard/").rsplit("/", 1)
        where = f"relative_path='{rel}/' AND _display_name='{name}'"
        query = f'content query --uri {MEDIA[kind]} --projection _id:is_pending --where "{where}"'  # safe_name(): no quotes
        scan = f"am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file://{remote}"
        start = time.monotonic()
        self.adb(serial, ["shell", scan], timeout=30)
        asked_again = False
        while True:
            row = re.search(r"_id=(\d+), is_pending=0", self.adb(serial, ["shell", query], timeout=30).stdout)
            if row:
                return f"{MEDIA[kind]}/{row.group(1)}"
            if not asked_again and time.monotonic() - start > wait_s / 2:
                self.adb(serial, ["shell", scan], timeout=30)
                asked_again = True
            if time.monotonic() - start > wait_s:
                raise HandoffError(f"{name} was copied to the phone but its gallery hasn't picked it up")
            time.sleep(0.5)

    def send(self, hid: str, device: str | None = None, *, withdraw_why: str | None = None) -> dict[str, Any]:
        """Push an item from the outbox to its phone (or the one given). Callers decide whether they may: the user's own
        session for any phone; MCP only for an emulator. `withdraw_why`: once the file is on the phone, its offer, if
        still pending, is withdrawn with that reason ("Muse already sent it to your phone"), so nobody is asked about a
        file that has already gone. Accepting the offer itself passes none: that yes is the offer's answer (and
        withdrawing from inside it would wait on the decision's own lock)."""
        item = self.item(hid)
        if item is None:
            raise HandoffError(f"no handoff {hid}")
        if item["status"] not in ("sent", "posted"):
            did = self.pick(device or item["device"], item["app"])
            try:
                path = self.outbox_file(item["name"])
                got = self.push_file(did, path)
            except (HandoffError, OSError, subprocess.TimeoutExpired) as e:
                return self._update(hid, status="failed", device=did, error=str(e)[:300])  # type: ignore[return-value]
            item = self._update(hid, status="sent", device=did, remote_path=got["remote_path"], media_uri=got["media_uri"], error=None, note=None)  # type: ignore[assignment]
        if withdraw_why and item["offer_id"] and self.offers is not None:
            self.offers.withdraw(item["offer_id"], withdraw_why)  # a no-op once the offer was answered
        return item

    def add(self, name: str, origin: str, device: str | None = None) -> dict[str, Any]:
        """The item for a file in the outbox: the waiting one if the watcher already has it, the one already on that
        phone (asking again doesn't put a second copy in its gallery), else a new one."""
        path = self.outbox_file(name)
        st = path.stat()
        with self.tasks.lock:
            row = self.tasks.db.execute("SELECT id FROM handoffs WHERE name=? AND size=? AND mtime=? AND status IN ('waiting','offered') "
                                        "ORDER BY created_at DESC LIMIT 1", (path.name, st.st_size, st.st_mtime)).fetchone()
            done = self.tasks.db.execute("SELECT id FROM handoffs WHERE name=? AND size=? AND mtime=? AND status IN ('sent','posted') AND device=? "
                                         "ORDER BY created_at DESC LIMIT 1", (path.name, st.st_size, st.st_mtime, device)).fetchone() if device else None
        if row:
            return self._update(row["id"], **({"device": device} if device else {}))  # type: ignore[return-value]
        if done:
            return self.item(done["id"])  # type: ignore[return-value]
        self._seen[path.name] = st.st_mtime  # the watcher doesn't record it a second time
        return self._record(path, self._check_file(path), origin=origin, device=device)

    # ---- offers: the user's yes, in Envoy ------------------------------------------------------------

    def where(self, did: str | None) -> str:
        """The phone as the offer says it: "your Pixel 5", "the Test phone (an emulator)"."""
        name = self.device_name(did) or "phone"
        return f"your {name}" if (did or "").startswith("phone-") else f"the {name} (an emulator)"

    def then_for(self, item: dict[str, Any]) -> dict[str, Any] | None:
        """The task after the push, from the template: the goal filled with the typed caption, the request the template's
        fixed words, the caption also in the routine's inputs. None for a push-only template."""
        tpl = HANDOFF_TEMPLATES[item["app"] or "gallery"]
        if not tpl.get("goal"):
            return None
        values = {"caption": item["caption"] or ""}
        goal = fill(tpl["goal"], values)
        if not values["caption"]:
            goal = re.sub(r"[\s:,]+$", "", goal)  # "… with this caption:" and nothing after it
        then = {"goal": re.sub(r"\s+", " ", goal).strip(), "request": handoff_request(tpl["request"] or tpl["goal"]), "app": tpl["package"],
                "inputs": {k: values[v] for k, v in (tpl.get("inputs") or {}).items() if values.get(v)}}
        if tpl.get("routine"):
            then["routine"] = tpl["routine"]
        return then

    def offer(self, hid: str, source: str) -> dict[str, Any] | None:
        """"Put clip.mp4 on your Pixel 5 and post it to Instagram?" for a waiting file. None without offers, for a file
        that isn't waiting, or when an offer for it was already made."""
        item = self.item(hid)
        if self.offers is None or item is None or item["status"] != "waiting" or not item["device"]:
            return None
        tpl = HANDOFF_TEMPLATES[item["app"] or "gallery"]
        then = self.then_for(item)
        name = re.sub(r"[\x00-\x1f\x7f\u202a-\u202e\u2066-\u2069]", "", item["name"])[:60]
        action = {"type": "handoff", "handoff_id": hid, "file": item["name"], "device": item["device"], "then": then}
        offer = self.offers.make(kind="handoff", title=fill(tpl["title"], {"file": name, "device": self.where(item["device"])}),
                                 body=(item["caption"] or "").split("\n", 1)[0][:200], action=action, source=source, key=f"handoff:{hid}",
                                 preflight=self.heads_up(then, item["device"]) if then else None)
        if offer is not None:
            self._update(hid, status="offered", offer_id=offer["id"])
        return offer

    def heads_up(self, then: dict[str, Any], did: str) -> list[dict[str, str]] | None:
        """The "Before I start" lines for the task after the push, as it will run once the user says yes: from Envoy's own
        app, on that phone, which the yes covers."""
        if preflight_check is None or self.runner is None:
            return None
        try:
            lines = preflight_check(self.runner, then["goal"], request=then["request"], source="web", app=then.get("app"),
                                    routine=then.get("routine"), inputs=then.get("inputs") or {}, phone=did,
                                    phone_ok=did if did.startswith("phone-") else None)
        except Exception:  # noqa: BLE001 - an offer without the lines is still an offer
            return None
        return [{k: str(x.get(k) or "") for k in ("kind", "text", "level")} for x in lines or []][:8] or None

    def reoffer(self, item: dict[str, Any], why: str) -> dict[str, Any] | None:
        """Withdraw the file's pending offer and ask again with what's now known (its sidecar). Nothing happens if the
        offer was answered meanwhile."""
        withdrawn = self.offers.withdraw(item["offer_id"], why)
        if (withdrawn or {}).get("status") != "withdrawn":
            return None
        self._update(item["id"], status="waiting", offer_id=None)
        return self.offer(item["id"], "outbox" if item["origin"] == "outbox" else "mcp")

    def accept(self, offer: dict[str, Any], source: str) -> dict[str, Any]:
        """The `handoff` action, run by api/offers.py when the user says yes in Envoy (never from MCP): push the file, to
        the real phone too, then start the template's task on that phone with the user's yes covering it."""
        a = offer["action"]
        item = self.item(str(a.get("handoff_id") or ""))
        if item is None or item["name"] != a.get("file"):
            raise LookupError("that file is no longer in Envoy's outbox list")
        did = str(a.get("device") or item["device"] or "")
        sent = self.send(item["id"], did or None)
        if sent["status"] not in ("sent", "posted"):
            raise RuntimeError(sent.get("error") or "the file couldn't be put on the phone")
        then = a.get("then")
        if not then:
            return {"handoff_id": item["id"]}
        if self.runner is None:
            raise RuntimeError("the task runner isn't available")
        did = sent["device"]
        task = self.runner.start(then["goal"], source, request=handoff_request(then.get("request") or ""), routine=then.get("routine") or None,
                                 inputs=then.get("inputs") or {}, app=then.get("app") or None, phone=did,
                                 **({"phone_ok": did} if did.startswith("phone-") else {}))
        self._update(item["id"], task_id=task["id"])
        return {"task_id": task["id"], "handoff_id": item["id"]}

    def on_event(self, ev: dict[str, Any]) -> None:
        """A bus listener: the task after a push finishing (posted), and a declined or expired offer (back to waiting)."""
        if ev.get("type") == "task":
            t = ev.get("task") or {}
            if t.get("status") in ("done", "failed", "declined", "stopped"):
                with self.tasks.lock:
                    row = self.tasks.db.execute("SELECT id FROM handoffs WHERE task_id=? AND status='sent'", (t.get("id"),)).fetchone()
                if row:
                    self._update(row["id"], **({"status": "posted"} if t["status"] == "done" else {"error": f"the task after it: {t['status']}"}))
        elif ev.get("type") == "offer" and ev.get("change") in ("declined", "expired"):
            o = ev.get("offer") or {}
            if (o.get("action") or {}).get("type") == "handoff":
                item = self.item(str(o["action"].get("handoff_id") or ""))
                if item and item["status"] == "offered" and item["offer_id"] == o.get("id"):
                    self._update(item["id"], status="waiting", note="you said not now" if ev["change"] == "declined" else "the offer expired")

    # ---- a file from the web --------------------------------------------------------------------

    def download(self, url: str, *, verify: Any = True, max_redirects: int = 5) -> Path:
        """An https URL into the outbox: https all the way (redirects too), public addresses only, an image or video by
        its content type, and at most `max_bytes`. Returns the file's path in the outbox."""
        import httpx
        try:
            return self._download(url, httpx, verify, max_redirects)
        except httpx.HTTPError as e:
            raise HandoffError(f"the download failed ({type(e).__name__})") from e

    def _download(self, url: str, httpx: Any, verify: Any, max_redirects: int) -> Path:
        folder = self.outbox()
        with httpx.Client(follow_redirects=False, timeout=httpx.Timeout(30, read=120), verify=verify) as client:
            for _ in range(max_redirects + 1):
                ip = self._check_url(url)
                # Connect to the address just checked, so a name that resolves differently a moment later (DNS rebinding)
                # can't send the request elsewhere; the name still goes in SNI, the certificate check and the Host header.
                u = urlsplit(url)
                pinned = u._replace(netloc=(f"[{ip}]" if ":" in ip else ip) + (f":{u.port}" if u.port else "")).geturl()
                with client.stream("GET", pinned, headers={"Accept": "image/*, video/*", "Host": u.netloc},
                                   extensions={"sni_hostname": u.hostname}) as r:
                    if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                        url = urljoin(url, r.headers["location"])
                        continue
                    if r.status_code != 200:
                        raise HandoffError(f"the download answered {r.status_code}")
                    ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
                    ext = CONTENT_TYPES.get(ctype)
                    if ext is None:
                        raise HandoffError(f"that URL isn't a photo or video (it's {ctype or 'of no stated type'})")
                    if int(r.headers.get("content-length") or 0) > self.max_bytes:
                        raise HandoffError(f"that file is over {self.max_bytes // (1024 * 1024)} MB")
                    name = safe_name(unquote(Path(urlsplit(url).path).name) or "download")
                    if kind_of(name) != kind_of("x" + ext):
                        name = Path(name).stem + ext
                    name = _unique(folder, name)
                    part = folder / f".{name}.part"
                    got = 0
                    try:
                        with part.open("wb") as f:
                            for chunk in r.iter_bytes(1 << 16):
                                got += len(chunk)
                                if got > self.max_bytes:
                                    raise HandoffError(f"that file is over {self.max_bytes // (1024 * 1024)} MB")
                                f.write(chunk)
                        dest = folder / name
                        part.rename(dest)
                    finally:
                        part.unlink(missing_ok=True)
                    try:
                        self._check_file(dest)
                    except HandoffError:
                        dest.unlink(missing_ok=True)
                        raise
                    return dest
        raise HandoffError("too many redirects")

    def _check_url(self, url: str) -> str:
        """The address to connect to: https, no credentials, and every address the name resolves to is public."""
        u = urlsplit(url)
        if u.scheme != "https" or not u.hostname:
            raise HandoffError("only https URLs (redirects included)")
        if u.username or u.password:
            raise HandoffError("no user names or passwords in the URL")
        try:
            addrs = self.resolve_ip(u.hostname)
        except OSError as e:
            raise HandoffError(f"can't find {u.hostname}") from e
        if not addrs:
            raise HandoffError(f"can't find {u.hostname}")
        for a in addrs:
            if not self.public_ip(ipaddress.ip_address(a)):
                raise HandoffError("that URL points inside this network, not to the web")
        return addrs[0]


def _resolve(host: str) -> list[str]:
    return sorted({ai[4][0] for ai in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)})


def _unique(folder: Path, name: str) -> str:
    stem, ext, n = Path(name).stem, Path(name).suffix, 2
    while (folder / name).exists() or (folder / f".{name}.part").exists():
        name, n = f"{stem}-{n}{ext}", n + 1
    return name


# ---- the web app's routes ---------------------------------------------------------------------------


def handoff_router(ctx: Any, session: Callable[..., None], caller: Callable[..., Any]) -> Any:
    """`session` and `caller` are build()'s auth closures. Only the user's own session sees or sends anything here."""
    from fastapi import APIRouter, Body, Depends, HTTPException

    router = APIRouter()
    h: Handoff = ctx.handoff

    @router.get("/api/handoff", dependencies=[Depends(session)])
    def list_handoffs(limit: int = 50) -> dict[str, Any]:
        return {"outbox": str(h.outbox()), "items": h.items(min(limit, 200)),
                "templates": {k: {"label": t["label"], "package": t["package"]} for k, t in HANDOFF_TEMPLATES.items()}}

    @router.post("/api/handoff/{hid}/send", dependencies=[Depends(session)])
    async def send(hid: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        """Your yes: push this file to its phone (the real phone too)."""
        try:
            return await asyncio.to_thread(lambda: h.send(hid, body.get("device") or None, withdraw_why="Sent to your phone"))
        except HandoffError as e:
            raise HTTPException(404 if str(e).startswith("no handoff") else 400, str(e)) from e

    @router.get("/api/settings/handoff", dependencies=[Depends(session)])
    def get_settings() -> dict[str, Any]:
        return {"outbox": str(h.outbox())}

    @router.post("/api/settings/handoff", dependencies=[Depends(session)])
    def set_settings(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            return {"outbox": str(h.set_outbox(str(body.get("outbox") or "")))}
        except HandoffError as e:
            raise HTTPException(400, str(e)) from e

    return router
