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

AI agents over MCP (phone-layer plan, contract 2) have keys of their own, checked by `agent_for`, never by `check`: an
agent key is not a session or a device token, so it opens /mcp and nothing else. `MCP_BEARER_TOKEN` from .env is
Muse's, with every tool. Every other agent's key is a `device_tokens` row with scope `agent:<name>` and the tool groups
it was given (Settings › Agents, api/agents.py), stored hashed like every other token.

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
from contextvars import ContextVar
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
  user_agent TEXT, tools TEXT
);
"""


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---- agents over MCP (contract 2) ----------------------------------------------------------------

MUSE = "Muse"  # who holds MCP_BEARER_TOKEN: the connector in Muse
AGENT = "agent:"  # an agent key's scope is agent:<name>
TOOL_GROUPS: dict[str, frozenset[str]] = {
    "read": frozenset({"get_task", "list_routines", "memory_search", "memory_get", "phone_updates", "list_phones"}),
    "run": frozenset({"run_task", "run_routine"}),  # and every learned routine's own tool: see group_of
    "memory": frozenset({"memory_note"}),
    "files": frozenset({"send_to_phone", "get_file"}),
    "triggers": frozenset({"create_trigger"}),
}
DEFAULT_GROUPS = ("read", "run")


@dataclass(frozen=True)
class Agent:
    """An AI client calling over MCP. `tools` is what it may use: tool groups (TOOL_GROUPS' names) and single tools by
    name; None is every tool (Muse). `id` is its device_tokens row (None for Muse's key in .env)."""
    name: str
    tools: frozenset[str] | None = None
    id: str | None = None


current_agent: ContextVar[Agent | None] = ContextVar("current_agent", default=None)  # set for each MCP call (api/agents.py)


def group_of(tool: str) -> str:
    """The group a tool is in. A tool no group names is a learned routine's own tool (phone-layer contract 1), so `run`:
    it starts a task like run_routine."""
    return next((g for g, names in TOOL_GROUPS.items() if tool in names), "run")


def allowed(agent: Agent | None, tool: str) -> bool:
    return agent is not None and (agent.tools is None or tool in agent.tools or group_of(tool) in agent.tools)


def agent_name() -> str:
    """Who is calling over MCP right now, for what Envoy tells the user ("Claude wants to set this up"); Muse outside a call."""
    agent = current_agent.get()
    return agent.name if agent is not None else MUSE


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
    def __init__(self, store: TaskStore, owner_token: str, clock: Any = time.time, mcp_token: str = "") -> None:
        self.store, self.owner_token, self.clock = store, owner_token, clock
        self.mcp_token = mcp_token  # MCP_BEARER_TOKEN: Muse's key, with every tool
        self._codes: dict[str, dict[str, Any]] = {}  # code → {expires, tries}
        self._lock = threading.Lock()
        self._seen: dict[str, float] = {}
        with store.lock:
            store.db.executescript(SCHEMA)
            if "tools" not in {r[1] for r in store.db.execute("PRAGMA table_info(device_tokens)")}:  # from before agent keys
                store.db.execute("ALTER TABLE device_tokens ADD COLUMN tools TEXT")
            store.db.commit()

    # ---- checking a token ------------------------------------------------------------------------

    def check(self, token: str | None) -> Caller | None:
        if not token:
            return None
        if hmac.compare_digest(token, self.owner_token):
            return Caller("owner", "session", name="this Mac")
        with self.store.lock:
            row = self.store.db.execute("SELECT * FROM device_tokens WHERE token_hash=? AND revoked_at IS NULL AND scope NOT LIKE 'agent:%'",
                                        (_hash(token),)).fetchone()
        if row is None:
            return None
        self._saw(row["id"])
        return Caller("device" if row["scope"] == "session" else "token", row["scope"], row["id"], row["name"] or "")

    def _saw(self, did: str) -> None:
        now = self.clock()
        if now - self._seen.get(did, 0) > 60:  # last seen, at most once a minute
            self._seen[did] = now
            with self.store.lock:
                if did == "muse":
                    self.store.set_setting("mcp_muse_last_seen", now)
                else:
                    self.store.db.execute("UPDATE device_tokens SET last_seen=? WHERE id=?", (now, did))
                    self.store.db.commit()

    def agent_for(self, token: str | None) -> Agent | None:
        """The agent an MCP key belongs to (contract 2): Muse for MCP_BEARER_TOKEN, else a live agent key's row. Nothing
        else is an agent: not your session, a paired device or a Shortcut's token."""
        if not token:
            return None
        if self.mcp_token and hmac.compare_digest(token.encode(), self.mcp_token.encode()):
            self._saw("muse")
            return Agent(MUSE)
        with self.store.lock:
            row = self.store.db.execute("SELECT id, scope, tools FROM device_tokens WHERE token_hash=? AND revoked_at IS NULL AND scope LIKE 'agent:%'",
                                        (_hash(token),)).fetchone()
        if row is None:
            return None
        self._saw(row["id"])
        return Agent(row["scope"].removeprefix(AGENT), frozenset(json.loads(row["tools"] or "[]")), row["id"])

    # ---- agent keys (Settings › Agents) ------------------------------------------------------------

    def agents(self) -> list[dict[str, Any]]:
        with self.store.lock:
            rows = self.store.db.execute("SELECT id, scope, tools, created_at, last_seen FROM device_tokens "
                                         "WHERE revoked_at IS NULL AND scope LIKE 'agent:%' ORDER BY created_at").fetchall()
        return [{"id": r["id"], "name": r["scope"].removeprefix(AGENT), "tools": sorted(json.loads(r["tools"] or "[]")),
                 "created_at": r["created_at"], "last_seen": r["last_seen"]} for r in rows]

    def muse_last_seen(self) -> float | None:
        return self.store.setting("mcp_muse_last_seen")

    def issue_agent(self, name: str, tools: list[str] | tuple[str, ...]) -> tuple[dict[str, Any], str]:
        """A new agent's key, shown once: (its row, the key). `name` is checked by the caller (api/agents.py)."""
        token = "envoy_agent_" + secrets.token_urlsafe(32)
        aid = f"agt-{secrets.token_hex(4)}"
        with self.store.lock:
            self.store.db.execute("INSERT INTO device_tokens (id, name, scope, token_hash, created_at, tools) VALUES (?,?,?,?,?,?)",
                                  (aid, name, AGENT + name, _hash(token), self.clock(), json.dumps(sorted(set(tools)))))
            self.store.db.commit()
        return self._agent_row(aid), token

    def rotate_agent(self, aid: str) -> str | None:
        """A new key for the agent; its old key stops working at once. None if there is no such live agent."""
        token = "envoy_agent_" + secrets.token_urlsafe(32)
        with self.store.lock:
            cur = self.store.db.execute("UPDATE device_tokens SET token_hash=?, created_at=?, last_seen=NULL "
                                        "WHERE id=? AND revoked_at IS NULL AND scope LIKE 'agent:%'", (_hash(token), self.clock(), aid))
            self.store.db.commit()
        self._seen.pop(aid, None)
        return token if cur.rowcount else None

    def set_agent_tools(self, aid: str, tools: list[str] | tuple[str, ...]) -> dict[str, Any] | None:
        with self.store.lock:
            self.store.db.execute("UPDATE device_tokens SET tools=? WHERE id=? AND revoked_at IS NULL AND scope LIKE 'agent:%'",
                                  (json.dumps(sorted(set(tools))), aid))
            self.store.db.commit()
        return self._agent_row(aid)

    def revoke_agent(self, aid: str) -> bool:
        with self.store.lock:
            cur = self.store.db.execute("UPDATE device_tokens SET revoked_at=? WHERE id=? AND revoked_at IS NULL AND scope LIKE 'agent:%'",
                                        (self.clock(), aid))
            self.store.db.commit()
        return cur.rowcount > 0

    def _agent_row(self, aid: str) -> dict[str, Any] | None:
        return next((a for a in self.agents() if a["id"] == aid), None)

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
                                         "WHERE revoked_at IS NULL AND scope NOT LIKE 'agent:%' ORDER BY created_at").fetchall()
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
        status = json.loads(out or "{}")
        web, funnel = status.get("Web") or {}, status.get("AllowFunnel") or {}
    except Exception:  # noqa: BLE001 - no Tailscale: local only
        return None
    for hostport, cfg in web.items():
        if funnel.get(hostport):  # a port open to the internet (Muse's /mcp, MCP_PERMANENT_URL) is never the app's address
            continue
        for handler in (cfg.get("Handlers") or {}).values():
            if handler.get("Proxy", "").rstrip("/") in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                return "https://" + hostport.removesuffix(":443")
    return None


def public_url(port: int) -> str:
    """The address links point at (approval pages in pushes and MCP results): ENVOY_PUBLIC_URL, else the tailnet address,
    else this Mac only."""
    return (os.environ.get("ENVOY_PUBLIC_URL") or tailnet_url(port) or f"http://127.0.0.1:{port}").rstrip("/")


def tunnel_hosts(url_file: Path) -> set[str]:
    """Public hosts where an AI client such as Muse reaches Envoy's MCP server, and nothing else is served: the permanent
    one in MCP_PERMANENT_URL (Tailscale Funnel on a port of its own), and a quick tunnel's only while
    `scripts/start_muse_test.sh` runs (it writes the URL to this file and removes it on exit)."""
    urls = [os.environ.get("MCP_PERMANENT_URL", "").strip()]
    try:
        urls.append(url_file.read_text().strip())
    except OSError:
        pass
    hosts: set[str] = set()
    for url in urls:
        host = url.split("://", 1)[-1].split("/", 1)[0]
        if url.startswith("https://") and host:
            hosts |= {host} if ":" in host else {host, f"{host}:443"}
    return hosts


def allowed_hosts(port: int, public: str) -> set[str]:
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}", "127.0.0.1", "localhost"}
    for url in (public, os.environ.get("MCP_PUBLIC_URL", "")):
        if url.startswith("https://") or url.startswith("http://"):
            host = url.split("://", 1)[1].split("/", 1)[0]
            hosts |= {host, host if ":" in host else f"{host}:443"}
    hosts |= {h.strip() for h in os.environ.get("ENVOY_ALLOWED_HOSTS", "").split(",") if h.strip()}
    return hosts
