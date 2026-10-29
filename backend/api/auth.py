"""Who is calling, and from where (Phase 5: the iPhone companion).

Three kinds of credential, all checked here:
- **Your session on the Mac**: the token in `data/api/session_token`, set as a cookie by the printed sign-in link.
- **A paired device** (your iPhone's Home Screen app): its own session token, given in exchange for a short pairing code
  shown on the Mac. A Home Screen app keeps its own cookies, apart from Safari, so the code is typed inside the installed
  app; nobody types the long token. Device sessions are stored hashed, named, revocable, and act as you.
- **Device tokens with a scope** (Shortcuts): `photos` can only upload images; `code_test` can only report that a code
  message arrived; `siri` ("Ask Envoy", api/siri.py) can only ask what a chat message can (a question, a task, a recurring
  job drafted switched off), as a non-direct source whose irreversible steps wait for your OK. None is a session: they
  can't read, approve, decide offers or take over, and only `siri` can start tasks.

Pairing codes are 6 digits, single use, valid for 5 minutes, and dead after 5 wrong tries (a guess has a 5 in a million
chance). New devices are paired only from the Mac's own session.

Host checks: the API answers only to the names it is served on (127.0.0.1, localhost, and its Tailscale name), so a
web page on another name that resolves to this Mac (DNS rebinding) is refused; WebSockets also check their Origin.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from api.store import TaskStore

CODE_TTL_S = 300
CODE_TRIES = 5
SCOPES = {"session", "photos", "code_test", "siri"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS device_tokens (
  id TEXT PRIMARY KEY, name TEXT, scope TEXT, token_hash TEXT UNIQUE, created_at REAL, last_seen REAL, revoked_at REAL,
  user_agent TEXT
);
"""


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass
class Caller:
    kind: str  # owner | device | token
    scope: str  # session | photos | code_test | siri
    device_id: str | None = None
    name: str = ""

    @property
    def is_session(self) -> bool:
        return self.scope == "session"


class Auth:
    def __init__(self, store: TaskStore, owner_token: str, clock: Any = time.time) -> None:
        self.store, self.owner_token, self.clock = store, owner_token, clock
        self._codes: dict[str, dict[str, Any]] = {}  # code → {expires, tries}
        self._lock = threading.Lock()
        self._seen: dict[str, float] = {}
        with store.lock:
            store.db.executescript(SCHEMA)
            store.db.commit()

    # ---- checking a token ------------------------------------------------------------------------

    def check(self, token: str | None) -> Caller | None:
        if not token:
            return None
        if hmac.compare_digest(token, self.owner_token):
            return Caller("owner", "session", name="this Mac")
        with self.store.lock:
            row = self.store.db.execute("SELECT * FROM device_tokens WHERE token_hash=? AND revoked_at IS NULL", (_hash(token),)).fetchone()
        if row is None:
            return None
        now = self.clock()
        if now - self._seen.get(row["id"], 0) > 60:  # last seen, at most once a minute
            self._seen[row["id"]] = now
            with self.store.lock:
                self.store.db.execute("UPDATE device_tokens SET last_seen=? WHERE id=?", (now, row["id"]))
                self.store.db.commit()
        return Caller("device" if row["scope"] == "session" else "token", row["scope"], row["id"], row["name"] or "")

    # ---- pairing ---------------------------------------------------------------------------------

    def start_pairing(self) -> dict[str, Any]:
        """A fresh code for a new device; any earlier unused code stops working."""
        code = f"{secrets.randbelow(10**6):06d}"
        with self._lock:
            self._codes = {code: {"expires": self.clock() + CODE_TTL_S, "tries": 0}}
        return {"code": code, "expires_in": CODE_TTL_S}

    def finish_pairing(self, code: str, name: str, user_agent: str = "") -> str | None:
        """The device's new session token, or None. Every wrong code counts against the live code."""
        code = "".join(ch for ch in str(code) if ch.isdigit())
        with self._lock:
            live = {c: v for c, v in self._codes.items() if v["expires"] > self.clock() and v["tries"] < CODE_TRIES}
            self._codes = live
            if not live:
                return None
            if code not in live:
                for v in live.values():
                    v["tries"] += 1
                return None
            del self._codes[code]  # single use
        return self.issue("session", name or "Paired device", user_agent)

    def issue(self, scope: str, name: str, user_agent: str = "") -> str:
        if scope not in SCOPES:
            raise ValueError(f"unknown scope {scope}")
        token = secrets.token_urlsafe(32)
        did = f"dev-{secrets.token_hex(4)}"
        with self.store.lock:
            self.store.db.execute("INSERT INTO device_tokens (id, name, scope, token_hash, created_at, user_agent) VALUES (?,?,?,?,?,?)",
                                  (did, name[:60], scope, _hash(token), self.clock(), user_agent[:200]))
            self.store.db.commit()
        return token

    def devices(self) -> list[dict[str, Any]]:
        with self.store.lock:
            rows = self.store.db.execute("SELECT id, name, scope, created_at, last_seen, user_agent FROM device_tokens "
                                         "WHERE revoked_at IS NULL ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]

    def revoke(self, device_id: str) -> bool:
        with self.store.lock:
            cur = self.store.db.execute("UPDATE device_tokens SET revoked_at=? WHERE id=? AND revoked_at IS NULL", (self.clock(), device_id))
            self.store.db.commit()
        return cur.rowcount > 0


# ---- where the API is served ---------------------------------------------------------------------

TAILSCALE = os.environ.get("TAILSCALE", "/Applications/Tailscale.app/Contents/MacOS/Tailscale")


def tailnet_url(port: int) -> str | None:
    """The https address Tailscale Serve gives this API (scripts/serve_tailnet.sh), or None if it isn't served."""
    try:
        out = subprocess.run([TAILSCALE, "serve", "status", "--json"], capture_output=True, text=True, timeout=5).stdout
        web = (json.loads(out or "{}").get("Web") or {})
    except Exception:  # noqa: BLE001 - no Tailscale: local only
        return None
    for hostport, cfg in web.items():
        for handler in (cfg.get("Handlers") or {}).values():
            if handler.get("Proxy", "").rstrip("/") in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                return "https://" + hostport.removesuffix(":443")
    return None


def public_url(port: int) -> str:
    """The address links point at (approval pages in pushes and MCP results): ENVOY_PUBLIC_URL, else the tailnet address,
    else this Mac only."""
    return (os.environ.get("ENVOY_PUBLIC_URL") or tailnet_url(port) or f"http://127.0.0.1:{port}").rstrip("/")


def tunnel_hosts(url_file: Path) -> set[str]:
    """The public tunnel's host, only while `scripts/start_muse_test.sh` runs (it writes the URL to this file and removes
    it on exit). An AI client such as Muse reaches Envoy's MCP server through it; nothing else is served there."""
    try:
        url = url_file.read_text().strip()
    except OSError:
        return set()
    host = url.split("://", 1)[-1].split("/", 1)[0]
    return {host, f"{host}:443"} if url.startswith("https://") and host else set()


def allowed_hosts(port: int, public: str) -> set[str]:
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}", "127.0.0.1", "localhost"}
    for url in (public, os.environ.get("MCP_PUBLIC_URL", "")):
        if url.startswith("https://") or url.startswith("http://"):
            host = url.split("://", 1)[1].split("/", 1)[0]
            hosts |= {host, host if ":" in host else f"{host}:443"}
    hosts |= {h.strip() for h in os.environ.get("ENVOY_ALLOWED_HOSTS", "").split(",") if h.strip()}
    return hosts
