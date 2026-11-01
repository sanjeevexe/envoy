"""The outbox forwarder (backlog #48): this Mac's ~/Envoy Outbox, for an Envoy that runs somewhere else.

Muse for Mac (or you) puts a clip and its sidecar in ~/Envoy Outbox. When Envoy runs on this Mac, its own watcher takes
them (api/handoff.py) and the forwarder has nothing to do: it says so and stops. When Envoy runs elsewhere (the cloud
copy, docs/cloud.md), the forwarder watches the folder and sends each new clip, with its sidecar, through that Envoy's
door: `/mcp/outbox`, beside its `/mcp`, with its MCP key. There the clip lands in the outbox as if dropped in: the same
handoff, the same offer, the same yes. No phones, no models.

- **Where Envoy runs.** `ENVOY_REMOTE_URL` is the other Envoy's MCP address (what Muse's connector points at, such as
  https://envoy-cloud.<tailnet>.ts.net:8443/mcp) and `ENVOY_REMOTE_TOKEN` its MCP key (that Envoy's MCP_BEARER_TOKEN).
  Not set, or an address of this Mac, means Envoy runs here. If an Envoy answers on this Mac as well, its watcher would
  take every clip too (two offers), so the forwarder stops unless started with `--also-here`.
- **What goes.** A photo or video (by its bytes, at most 500 MB) once its size has held for 2 s; hidden files, partial
  downloads, symlinks and folders stay. What was in the outbox before the forwarder started stays too, as with the
  watcher (`--send-waiting` sends it).
- **Sidecars.** A clip goes with its sidecar if one is there, and one that comes later follows it on its own. Over there,
  Envoy's watcher gives a sidecar its 30 s as it does here, and a later one still replaces the offer.
- **After.** A sent file moves to `Sent/` in the outbox (never deleted), and a line says what went where and what Envoy is
  doing with it. Offline, or while that Envoy restarts, the file stays and is tried again after 5, 10 and 30 s, then
  every minute. A file Envoy refuses (too big, not a video by its bytes) stays, said once; a refused key stops the
  forwarder.

    uv run --project backend python -m api.forwarder        # until Ctrl-C
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import socket
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from api.handoff import DOOR, MAX_BYTES, SETTLE_S, SIDECAR_MAX, ignored, kind_of, sniff
from api.store import REPO

SENT = "Sent"
EVERY_S = 1.0
RETRY_S = (5, 10, 30, 60)
HELLO_S = 300  # how often it checks in: the other Envoy's send_to_phone waits for names on their way while it does
LATE_S = 3600  # a sidecar that comes this long after its clip went still follows it; after that it waits for a new clip
LOCAL = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


class KeyRefused(RuntimeError):
    """The other Envoy refused the key: nothing goes until it's fixed."""


def door_url(remote: str) -> str:
    """The door beside an Envoy's MCP address: https://host:8443/mcp → https://host:8443/mcp/outbox (a bare base works too)."""
    return remote.strip().rstrip("/").removesuffix("/mcp") + DOOR


def this_mac() -> set[str]:
    """Names this Mac answers to: localhost, its host name, its Tailscale name, and the addresses its own .env gives Envoy."""
    names = set(LOCAL)
    host = socket.gethostname().lower()
    names |= {host, host.removesuffix(".local"), host.removesuffix(".local") + ".local"}
    try:
        from api.auth import TAILSCALE
        status = json.loads(subprocess.run([TAILSCALE, "status", "--json"], capture_output=True, text=True, timeout=5).stdout or "{}")
        if dns := (status.get("Self") or {}).get("DNSName", "").rstrip(".").lower():
            names.add(dns)
    except Exception:  # noqa: BLE001 - no Tailscale here
        pass
    for var in ("MCP_PERMANENT_URL", "ENVOY_PUBLIC_URL", "MCP_PUBLIC_URL"):
        if h := urlsplit(os.environ.get(var, "").strip()).hostname:
            names.add(h.lower())
    return names


def remote_host(remote: str | None, here: set[str]) -> str | None:
    """The host of the Envoy to forward to, or None when Envoy runs on this Mac: no address, or one of this Mac's."""
    host = (urlsplit((remote or "").strip()).hostname or "").lower()
    return None if not host or host in here else host


def envoy_here(port: int | None = None) -> int | None:
    """The port of an Envoy answering on this Mac, if one does."""
    import httpx
    port = port or int(os.environ.get("ENVOY_PORT", "8700"))
    try:
        return port if httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=1).status_code == 200 else None
    except httpx.HTTPError:
        return None


def _plain(text: Any, cap: int = 300) -> str:
    """What the other Envoy said, as one plain line: it goes to a terminal."""
    return "".join(ch for ch in " ".join(str(text or "").split()) if unicodedata.category(ch)[0] != "C")[:cap]


def _mb(size: int) -> str:
    return f"{size / (1024 * 1024):.1f} MB" if size >= 100 * 1024 else f"{max(1, round(size / 1024))} KB"


class Forwarder:
    """`client` is an httpx.Client (a TestClient in tests), made on first use; `clock` and `say` are stubbed in tests."""

    def __init__(self, outbox: Path, door: str, token: str, *, client: Any = None, clock: Callable[[], float] = time.time,
                 say: Callable[[str], None] | None = None, send_waiting: bool = False) -> None:
        self.outbox, self.door, self.token = Path(outbox), door, token
        self.host = urlsplit(door).hostname or door
        self.client, self.clock = client, clock
        self.say = say or (lambda line: print(time.strftime("%H:%M:%S"), line, flush=True))
        self.seen: dict[str, float] | None = {} if send_waiting else None  # name → mtime of what was there at start
        self.sizes: dict[str, tuple[int, float, float]] = {}  # name → (size, mtime, since when it has had them)
        self.sent: dict[str, dict[str, Any]] = {}  # a clip's name here → {remote, at, moved}, for its late sidecar
        self.refused: dict[str, tuple[int, float]] = {}  # name → (size, mtime) that won't go, said once
        self.failures, self.retry_at, self.down = 0, 0.0, None  # down: why Envoy isn't reachable, while it isn't
        self.hello_at = -HELLO_S

    # ---- talking to the door --------------------------------------------------------------------------

    def _call(self, method: str, **kw: Any) -> tuple[int | None, dict[str, Any]]:
        import httpx
        if self.client is None:
            self.client = httpx.Client(timeout=httpx.Timeout(30, read=120, write=600))
        try:
            r = self.client.request(method, self.door, headers={"Authorization": f"Bearer {self.token}"}, **kw)
        except httpx.HTTPError as e:
            return None, {"detail": type(e).__name__}
        try:
            body = r.json()
        except ValueError:
            body = {"detail": r.text[:200]}
        return r.status_code, body if isinstance(body, dict) else {"detail": str(body)[:200]}

    def _reached(self, status: int | None, body: dict[str, Any], what: str) -> bool:
        """False while the other Envoy can't be reached (offline, restarting): `what` waits for the retry, said once."""
        if status is None or status >= 500 or status == 429:
            self.failures += 1
            delay = RETRY_S[min(self.failures, len(RETRY_S)) - 1]
            self.retry_at = self.clock() + delay
            if self.down is None:
                self.down = _plain(body.get("detail") or status, 80)
                self.say(f"Envoy at {self.host} isn't reachable ({self.down[:80]}): {what} stays in the outbox; "
                         f"trying again in {delay} s, then less often.")
            return False
        if status in (401, 403):
            raise KeyRefused(f"Envoy at {self.host} refused the key ({status}): set ENVOY_REMOTE_TOKEN to its MCP key "
                             "(that Envoy's MCP_BEARER_TOKEN).")
        if self.down is not None:
            self.say(f"Envoy at {self.host} is reachable again.")
        self.failures, self.retry_at, self.down = 0, 0.0, None
        return True

    def hello(self, first: bool = False) -> bool:
        """Check the address and the key, and keep in touch."""
        self.hello_at = self.clock()
        status, body = self._call("GET")
        if not self._reached(status, body, "anything new"):
            return False
        if first:
            self.say(f"Forwarding {self.outbox} to Envoy at {self.host} (its door answers, the key works). Sent files move to {SENT}/.")
        return True

    # ---- the outbox --------------------------------------------------------------------------------------

    def _files(self) -> dict[str, tuple[int, float]]:
        """Clips and sidecars in the outbox: name → (size, mtime)."""
        files = {}
        try:
            entries = list(self.outbox.iterdir())
        except OSError:
            return {}
        for p in entries:
            try:
                if p.is_symlink() or not p.is_file() or (ignored(p) and not (p.suffix.lower() == ".json" and not p.name.startswith("."))):
                    continue
                st = p.stat()
            except OSError:
                continue
            files[p.name] = (st.st_size, st.st_mtime)
        return files

    def tick(self) -> list[dict[str, Any]]:
        """One look at the outbox. Returns what went (and what Envoy refused) this time."""
        now = self.clock()
        files = self._files()
        if self.seen is None:  # the first look: what's already there stays, as with Envoy's own watcher
            self.seen = {n: m for n, (_, m) in files.items() if not n.lower().endswith(".json")}
            if self.seen:
                self.say(f"Left {len(self.seen)} file(s) that were already in the outbox ({', '.join(sorted(self.seen)[:5])}): only new "
                         "ones go. Copy one in again to send it, or start with --send-waiting.")
            return []
        for name in [n for n in self.sizes if n not in files]:
            self.sizes.pop(name)
        settled = set()
        for name, (size, mtime) in files.items():
            was = self.sizes.get(name)
            if was is None or was[:2] != (size, mtime):  # new, or still being written
                self.sizes[name] = (size, mtime, now)
            elif now - was[2] >= SETTLE_S:
                settled.add(name)
        if now < self.retry_at:
            return []
        if now - self.hello_at >= HELLO_S and not self.hello():
            return []
        out = []
        for name in sorted((n for n in settled if not n.lower().endswith(".json")), key=lambda n: files[n][1]):
            size, mtime = files[name]
            if self.seen.get(name) == mtime or self.refused.get(name) == (size, mtime):
                continue
            path = self.outbox / name
            kind = kind_of(name)
            if size > MAX_BYTES or sniff(path) != kind:
                self._refuse(name, size, mtime, f"it's over {MAX_BYTES // (1024 * 1024)} MB" if size > MAX_BYTES else f"it isn't a {kind} by its contents")
                continue
            side = self._sidecar_of(name, files, settled)
            if side == "wait":  # its sidecar is still being written
                continue
            got = self._send_clip(path, size, mtime, side)
            if got is None:
                return out
            out.append(got)
        files = self._files()
        for name in sorted(n for n in settled if n.lower().endswith(".json") and n in files):
            size, mtime = files[name]
            if self.refused.get(name) == (size, mtime) or self._clip_for(name, files):
                continue  # its clip is here: it goes with it
            got = self._send_late(name, size, mtime)
            if got is False:
                return out
            if got:
                out.append(got)
        return out

    def _sidecar_of(self, clip: str, files: dict[str, tuple[int, float]], settled: set[str]) -> tuple[Path, str] | str | None:
        """The clip's sidecar as read_sidecar finds it (`clip.json`, then `clip.mp4.json`): (path, its JSON), "wait"
        while it is still being written, or None."""
        for name in (Path(clip).stem + ".json", clip + ".json"):
            if name not in files:
                continue
            if name not in settled:
                return "wait"
            size, mtime = files[name]
            text = self._sidecar_text(name, size, mtime)
            return (self.outbox / name, text) if text is not None else None
        return None

    def _sidecar_text(self, name: str, size: int, mtime: float) -> str | None:
        if self.refused.get(name) == (size, mtime):
            return None
        try:
            text = (self.outbox / name).read_text(encoding="utf-8")
            ok = size <= SIDECAR_MAX and isinstance(json.loads(text), dict)
        except (OSError, ValueError):
            ok = False
        if not ok:
            self._refuse(name, size, mtime, 'it isn\'t a small JSON object like {"app": "instagram", "caption": "…"}')
            return None
        return text

    def _clip_for(self, sidecar: str, files: dict[str, tuple[int, float]]) -> str | None:
        """A clip in the outbox that this sidecar belongs to, if one is there (or still arriving)."""
        base = sidecar[:-5]
        for name in files:
            if not name.lower().endswith(".json") and (name == base or Path(name).stem == base):
                return name
        return None

    def _refuse(self, name: str, size: int, mtime: float, why: str) -> None:
        self.refused[name] = (size, mtime)
        self.say(f"{name} stays in the outbox: {why}.")

    # ---- sending -----------------------------------------------------------------------------------------

    def _send_clip(self, path: Path, size: int, mtime: float, side: tuple[Path, str] | None) -> dict[str, Any] | None:
        """One clip (and its sidecar) through the door. None while Envoy can't be reached."""
        key = hashlib.sha256(f"{path.name}\0{size}\0{mtime}".encode()).hexdigest()[:32]  # the same file again is a retry
        data = {"key": key, "name": path.name, **({"sidecar": side[1]} if side else {})}  # the name as a field: any script survives
        try:
            with path.open("rb") as f:
                status, body = self._call("POST", data=data, files={"file": (path.name, f, mimetypes.guess_type(path.name)[0] or "application/octet-stream")})
        except OSError as e:
            self._refuse(path.name, size, mtime, f"it can't be read ({e.strerror or e})")
            return {"name": path.name, "refused": "unreadable"}
        what = path.name + (f" (with {side[0].name})" if side else "")
        if not self._reached(status, body, what):
            return None
        if status != 200:
            detail = _plain(body.get("detail") or status, 160)
            self._refuse(path.name, size, mtime, f"Envoy at {self.host} refused it ({detail})")
            return {"name": path.name, "refused": detail}
        moved = self._move_aside(path, side[0] if side else None, size, mtime)
        self.sent[path.name] = {"remote": body.get("name") or path.name, "at": self.clock(), "moved": moved}
        self.say(f"Sent {path.name} ({_mb(size)})" + (f" with {side[0].name}" if side else "") + f" to Envoy at {self.host}. "
                 + _plain(body.get("text")) + (f" Moved to {SENT}/{moved.name}." if moved else ""))
        return {"name": path.name, "sidecar": side[0].name if side else None, "answer": body, "moved": moved}

    def _send_late(self, name: str, size: int, mtime: float) -> dict[str, Any] | bool | None:
        """A sidecar whose clip already went (in this run, within LATE_S): it follows on its own. None when it isn't
        one (it waits for a clip of its own); False while Envoy can't be reached."""
        base = name[:-5]
        clip = next((c for c, s in sorted(self.sent.items(), key=lambda x: -x[1]["at"])
                     if (c == base or Path(c).stem == base) and self.clock() - s["at"] < LATE_S), None)
        if clip is None:
            return None
        text = self._sidecar_text(name, size, mtime)
        if text is None:
            return None
        sent = self.sent[clip]
        status, body = self._call("POST", data={"name": sent["remote"], "sidecar": text})
        if not self._reached(status, body, name):
            return False
        if status != 200:
            self._refuse(name, size, mtime, f"Envoy at {self.host} refused it ({_plain(body.get('detail') or status, 160)})")
            return {"name": name, "refused": body.get("detail")}
        moved = None
        if sent["moved"] is not None:
            folder = sent["moved"].parent
            moved = folder / _free(folder, sent["moved"].stem + ".json" if name == Path(clip).stem + ".json" else sent["moved"].name + ".json")
            (self.outbox / name).rename(moved)
        ago = round(self.clock() - sent["at"])
        self.say(f"Sent {name}, the sidecar for {clip} ({ago} s after it), to Envoy at {self.host}. " + _plain(body.get("text"))
                 + (f" Moved to {SENT}/{moved.name}." if moved else ""))
        return {"name": name, "for": clip, "answer": body, "moved": moved}

    def _move_aside(self, path: Path, side: Path | None, size: int, mtime: float) -> Path | None:
        """Into Sent/, never deleted; a clip that changed while it went stays, to go again."""
        try:
            st = path.stat()
        except OSError:
            return None
        if (st.st_size, st.st_mtime) != (size, mtime):
            self.say(f"{path.name} changed while it was being sent: it goes again.")
            return None
        folder = self.outbox / SENT
        folder.mkdir(exist_ok=True)
        stem, ext, name, n = path.stem, path.suffix, path.name, 2

        def side_as(clip: str) -> str:
            return Path(clip).stem + ".json" if side is not None and side.name == path.stem + ".json" else clip + ".json"
        while (folder / name).exists() or (side is not None and (folder / side_as(name)).exists()):
            name, n = f"{stem}-{n}{ext}", n + 1
        path.rename(folder / name)
        if side is not None and side.exists():
            side.rename(folder / side_as(name))
        return folder / name


def _free(folder: Path, name: str) -> str:
    stem, ext, n, out = Path(name).stem, Path(name).suffix, 2, name
    while (folder / out).exists():
        out, n = f"{stem}-{n}{ext}", n + 1
    return out


def main(argv: list[str] | None = None, *, here: set[str] | None = None, local_envoy: Callable[[], int | None] = envoy_here,
         env_file: Path | None = REPO / ".env") -> int:
    if env_file is not None:
        from dotenv import load_dotenv
        load_dotenv(env_file)
    ap = argparse.ArgumentParser(prog="python -m api.forwarder", description="Send ~/Envoy Outbox to an Envoy that runs elsewhere.")
    ap.add_argument("--outbox", type=Path, default=Path(os.environ.get("ENVOY_OUTBOX") or Path.home() / "Envoy Outbox"))
    ap.add_argument("--remote", default=os.environ.get("ENVOY_REMOTE_URL", ""), help="the other Envoy's MCP address (ENVOY_REMOTE_URL)")
    ap.add_argument("--send-waiting", action="store_true", help="also send what is in the outbox already")
    ap.add_argument("--also-here", action="store_true", help="forward even though an Envoy answers on this Mac too")
    args = ap.parse_args(argv)
    outbox = args.outbox.expanduser()
    host = remote_host(args.remote, this_mac() if here is None else here)
    if host is None:
        why = "ENVOY_REMOTE_URL isn't set" if not args.remote.strip() else f"{args.remote.strip()} is this Mac"
        print(f"Envoy runs on this Mac ({why}): its own watcher takes what lands in {outbox}. Nothing to forward.")
        return 0
    if urlsplit(args.remote.strip()).scheme != "https":
        print(f"{args.remote.strip()}: the forwarder sends Envoy's key only over https.", file=sys.stderr)
        return 2
    token = os.environ.get("ENVOY_REMOTE_TOKEN", "").strip()
    if not token:
        print(f"ENVOY_REMOTE_TOKEN isn't set: it is the MCP key of the Envoy at {host} (its MCP_BEARER_TOKEN).", file=sys.stderr)
        return 2
    if not args.also_here and (port := local_envoy()):
        print(f"An Envoy also answers on this Mac (127.0.0.1:{port}), and unless you gave it another outbox its watcher takes {outbox} "
              "too: every clip would be offered twice. Stop it, or start the forwarder with --also-here.", file=sys.stderr)
        return 2
    outbox.mkdir(parents=True, exist_ok=True)
    fwd = Forwarder(outbox, door_url(args.remote), token, send_waiting=args.send_waiting)
    try:
        fwd.hello(first=True)
        while True:
            fwd.tick()
            time.sleep(EVERY_S)
    except KeyRefused as e:
        print(e, file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
