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
  pool (`envoy-test`, `phone-…`; never an adb serial), dates it now, and checks the media store has it, so the gallery
  shows it as the newest item.
- **Nothing goes to a real phone without the user's yes.** Outbox items wait (status `waiting`) until the user sends one
  from their own session (`POST /api/handoff/{id}/send`). MCP's `send_to_phone` pushes to an emulator at once, and for
  the real phone only records the item and says it waits for the user in Envoy.

Statuses: waiting → (offered) → sent → (posted) | failed.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
import socket
import subprocess
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urljoin, urlsplit

from api.routing import TEST_EMULATOR, choose
from api.store import TaskStore, new_id

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

SCHEMA = """
CREATE TABLE IF NOT EXISTS handoffs (
  id TEXT PRIMARY KEY, name TEXT, size INTEGER, kind TEXT, app TEXT, caption TEXT, status TEXT, device TEXT,
  remote_path TEXT, media_uri TEXT, offer_id TEXT, task_id TEXT, created_at REAL, updated_at REAL, error TEXT,
  note TEXT, origin TEXT, mtime REAL
);
CREATE INDEX IF NOT EXISTS handoffs_name ON handoffs(name, size);
"""

# What a file from the Mac becomes on the phone, by app (lowercase key, as a sidecar's `app` names it).
# - `goal`: what the agent works from, with typed slots ({caption}); `request`: the same words with every slot left
#   empty, which is all the approval rules read (contract 1). The caption fills the goal and the routine's inputs, never
#   the request.
# - `title`: the offer's question, with {file} and {device}. `device_pref`: "phone" asks for the real phone the way
#   "on my phone" does; "emulator" leaves it to routing (the per-app "use my phone" setting, apps that block emulators).
# - optionally `routine` and `inputs` (routine input → sidecar field).
# This one only puts the file in the gallery; creator-workflow adds Instagram's entry.
HANDOFF_TEMPLATES: dict[str, dict[str, Any]] = {
    "gallery": {"label": "the phone's gallery", "package": None, "goal": None, "request": None, "caption_limit": 2200,
                "device_pref": "emulator", "title": "Put {file} on your {device}?"},
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


def safe_name(name: str) -> str:
    """A file name the phone's shell and media store take as it is: letters, digits, dot, dash, underscore."""
    p = Path(name)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", unicodedata.normalize("NFKD", p.stem).encode("ascii", "ignore").decode()).strip("-.") or "file"
    return stem[:80] + p.suffix.lower()


def fill(template: str, values: dict[str, str]) -> str:
    """A template's {slots} filled with typed values, one pass (a value with braces in it fills nothing)."""
    return re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), ""), template)


def without_slots(template: str) -> str:
    """The template with every slot left empty: the fixed words a person wrote (contract 1's `request`)."""
    return re.sub(r"\s{2,}", " ", re.sub(r"\{\w+\}", "", template)).strip(" :,")


# ---- the handoff record, the outbox, and the phone ----------------------------------------------------


def _adb(serial: str, args: list[str], timeout: float) -> subprocess.CompletedProcess:
    from devices.android import _adb_path  # the same adb binary the device layer uses
    return subprocess.run([_adb_path(), "-s", serial, *args], capture_output=True, text=True, timeout=timeout)


class Handoff:
    """`adb(serial, args, timeout)` runs one adb command on one phone (a fake in tests). `resolve_ip(host)` is DNS for
    downloads (tests stub it). No module-level state: each `build()` gets its own."""

    def __init__(self, tasks: TaskStore, pool: Any, bus: Any, *, adb: Callable[..., subprocess.CompletedProcess] = _adb,
                 clock: Callable[[], float] = time.time, settle_s: float = SETTLE_S, every_s: float = 3.0, max_bytes: int = MAX_BYTES,
                 resolve_ip: Callable[[str], list[str]] | None = None) -> None:
        self.tasks, self.pool, self.bus, self.adb, self.clock = tasks, pool, bus, adb, clock
        self.settle_s, self.every_s, self.max_bytes = settle_s, every_s, max_bytes
        self.resolve_ip = resolve_ip or _resolve
        self._folder: Path | None = None  # the folder the seen list below belongs to
        self._seen: dict[str, float] = {}  # name → mtime when the watcher started on this folder
        self._sizes: dict[str, tuple[int, float, float]] = {}  # name → (size, mtime, since when it has had them)
        self._task: asyncio.Task | None = None
        with tasks.lock:
            tasks.db.executescript(SCHEMA)
            tasks.db.commit()

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
            new.append(self._record(folder / name, kind, origin="outbox"))
        for name in list(self._sizes):
            if name not in files:
                self._sizes.pop(name)
        # A sidecar written after its video still counts while the item waits.
        for item in self.items(status="waiting"):
            if item["name"] in files and item["origin"] in ("outbox", "mcp", "url"):
                app, caption, note = read_sidecar(folder / item["name"])
                if (app, caption) != (item["app"], item["caption"]) and (app or caption):
                    device = self.default_device(app) if app != item["app"] and item["origin"] == "outbox" else (item["device"], note)
                    self._update(item["id"], app=app, caption=caption, device=device[0], note=note or device[1])
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
        folder = f"/sdcard/{DIRS[kind]}"
        self._sh(serial, f"mkdir -p {folder}")
        name = self._free_name(serial, folder, safe_name(src.name))
        remote = f"{folder}/{name}"
        out = self.adb(serial, ["push", str(src), remote], timeout=600)
        if out.returncode != 0:
            raise HandoffError(f"adb push failed: {(out.stderr or out.stdout).strip()[:200]}")
        # adb push keeps the Mac's modified time; the gallery sorts by date, so this copy is dated now.
        self._sh(serial, f"touch {remote}")
        uri = self._indexed(serial, kind, remote)
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

    def _indexed(self, serial: str, kind: str, remote: str, wait_s: float = 8) -> str:
        """The file's media store row, after asking the media scanner for it: on Android 11 and later the write through
        /sdcard is indexed by the media provider itself, and the scan request covers the rest."""
        rel, name = remote.removeprefix("/sdcard/").rsplit("/", 1)
        where = f"relative_path='{rel}/' AND _display_name='{name}'"
        query = f'content query --uri {MEDIA[kind]} --projection _id:date_added:date_modified --where "{where}"'  # safe_name(): no quotes
        scanned = False
        deadline = time.monotonic() + wait_s
        while True:
            row = re.search(r"_id=(\d+)", self.adb(serial, ["shell", query], timeout=30).stdout)
            if row:
                return f"{MEDIA[kind]}/{row.group(1)}"
            if not scanned:
                self.adb(serial, ["shell", f"am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file://{remote}"], timeout=30)
                scanned = True
            if time.monotonic() > deadline:
                raise HandoffError(f"{name} was copied to the phone but its gallery hasn't picked it up")
            time.sleep(0.5)

    def send(self, hid: str, device: str | None = None) -> dict[str, Any]:
        """Push an item from the outbox to its phone (or the one given). Callers decide whether they may: the user's own
        session for any phone; MCP only for an emulator."""
        item = self.item(hid)
        if item is None:
            raise HandoffError(f"no handoff {hid}")
        if item["status"] in ("sent", "posted"):
            return item
        did = self.pick(device or item["device"], item["app"])
        try:
            path = self.outbox_file(item["name"])
            got = self.push_file(did, path)
        except (HandoffError, OSError, subprocess.TimeoutExpired) as e:
            return self._update(hid, status="failed", device=did, error=str(e)[:300])  # type: ignore[return-value]
        return self._update(hid, status="sent", device=did, remote_path=got["remote_path"], media_uri=got["media_uri"], error=None)  # type: ignore[return-value]

    def add(self, name: str, origin: str, device: str | None = None) -> dict[str, Any]:
        """The item for a file in the outbox: the waiting one if the watcher already has it, else a new one."""
        path = self.outbox_file(name)
        st = path.stat()
        with self.tasks.lock:
            row = self.tasks.db.execute("SELECT id FROM handoffs WHERE name=? AND size=? AND mtime=? AND status IN ('waiting','offered') "
                                        "ORDER BY created_at DESC LIMIT 1", (path.name, st.st_size, st.st_mtime)).fetchone()
        if row:
            return self._update(row["id"], **({"device": device} if device else {}))  # type: ignore[return-value]
        self._seen[path.name] = st.st_mtime  # the watcher doesn't record it a second time
        return self._record(path, self._check_file(path), origin=origin, device=device)

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
                self._check_url(url)
                with client.stream("GET", url, headers={"Accept": "image/*, video/*"}) as r:
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

    def _check_url(self, url: str) -> None:
        u = urlsplit(url)
        if u.scheme != "https" or not u.hostname:
            raise HandoffError("only https URLs (redirects included)")
        if u.username or u.password:
            raise HandoffError("no user names or passwords in the URL")
        try:
            addrs = self.resolve_ip(u.hostname)
        except OSError as e:
            raise HandoffError(f"can't find {u.hostname}") from e
        for a in addrs:
            ip = ipaddress.ip_address(a)
            if not ip.is_global or ip.is_multicast:
                raise HandoffError("that URL points inside this network, not to the web")


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
            return await asyncio.to_thread(h.send, hid, body.get("device") or None)
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
