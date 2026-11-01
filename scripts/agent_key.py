"""Agent keys from the command line (phone-layer contract 2), for a key nobody should see on a screen: it goes into a
file only you can read, and the terminal shows the agent's name, its tool groups and the file's path, never the key.

  uv run --project backend python scripts/agent_key.py issue "Meta agent" --tools read,run,files,triggers [--out <file>]
  uv run --project backend python scripts/agent_key.py rotate "Meta agent" [--out <file>]
  uv run --project backend python scripts/agent_key.py list
  uv run --project backend python scripts/agent_key.py revoke "Meta agent"

Run it from the checkout the API runs from (~/Desktop/Envoy for :8700): it uses that checkout's data/api/envoy.db, or
ENVOY_API_DIR's, or --db. The key file is data/api/agent_keys/<name>.key by default (gitignored, mode 600); an --out
inside the repo must be gitignored too. Tool groups are api/auth.py's TOOL_GROUPS; Settings › Agents shows the same keys.

Safe while the API runs: it opens the database with sqlite3 and api/auth.py's Auth only, never TaskStore, whose start-up
stops every running task (it takes itself for a restarted API). The API checks keys in the database on every MCP call,
so a new key works at once, and a revoked or rotated one stops at once.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from api.agents import new_name, tool_groups  # noqa: E402
from api.auth import DEFAULT_GROUPS, TOOL_GROUPS, Auth  # noqa: E402
from api.store import API_DIR  # noqa: E402


class Database:
    """What Auth needs of a TaskStore (its connection and lock), without TaskStore's start-up."""

    def __init__(self, path: Path) -> None:
        self.db = sqlite3.connect(str(path), timeout=15, check_same_thread=False)  # waits out the API's own writes
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()

    def setting(self, key: str, default: Any = None) -> Any:
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default


def key_file(name: str, out: str | None) -> Path:
    """Where the key goes: --out, else <API dir>/agent_keys/<name>.key. Refused if git would commit it."""
    path = Path(out).expanduser() if out else API_DIR / "agent_keys" / f"{re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') or 'agent'}.key"
    path = path.resolve()
    if path.is_relative_to(REPO.resolve()):
        ignored = subprocess.run(["git", "-C", str(REPO), "check-ignore", "-q", str(path)], capture_output=True).returncode == 0
        if not ignored:
            raise SystemExit(f"{path} isn't gitignored, so the key could be committed. Pick another path (the default is data/api/agent_keys/).")
    return path


def write_key(path: Path, key: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key + "\n")
    os.chmod(path, 0o600)  # an older file keeps its mode through O_TRUNC


def find(auth: Auth, name: str) -> dict[str, Any]:
    got = next((a for a in auth.agents() if a["name"].casefold() == name.strip().casefold()), None)
    if got is None:
        raise SystemExit(f"No agent called {name}. `list` shows them.")
    return got


def when(t: float | None) -> str:
    return datetime.fromtimestamp(t).strftime("%b %-d %H:%M") if t else "never"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Make, list and revoke Envoy's agent keys without showing a key.")
    ap.add_argument("--db", help="the API's envoy.db (default: this checkout's, or ENVOY_API_DIR's)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    issue = sub.add_parser("issue", help="a new agent and its key")
    issue.add_argument("name")
    issue.add_argument("--tools", default=",".join(DEFAULT_GROUPS), help=f"tool groups, comma-separated: {', '.join(TOOL_GROUPS)}")
    issue.add_argument("--out", help="the file for the key (gitignored; default data/api/agent_keys/<name>.key)")
    rotate = sub.add_parser("rotate", help="a new key for an agent; its old key stops at once")
    rotate.add_argument("name")
    rotate.add_argument("--out")
    sub.add_parser("list", help="the agents, their tool groups and when each was last seen")
    revoke = sub.add_parser("revoke", help="stop an agent's key")
    revoke.add_argument("name")
    args = ap.parse_args(argv)

    db = Path(args.db).expanduser() if args.db else API_DIR / "envoy.db"
    if not db.is_file():
        raise SystemExit(f"No Envoy database at {db}. Run this from the checkout the API runs from, or pass --db.")
    auth = Auth(Database(db), owner_token="")  # type: ignore[arg-type]

    if args.cmd == "issue":
        try:
            name, groups = new_name(auth, args.name), tool_groups([g.strip() for g in args.tools.split(",") if g.strip()])
        except ValueError as e:
            raise SystemExit(str(e)) from e
        path = key_file(name, args.out)
        agent, key = auth.issue_agent(name, groups)
        try:
            write_key(path, key)
        except OSError as e:
            auth.revoke_agent(agent["id"])  # a key nobody has is no use: take it back
            raise SystemExit(f"Couldn't write {path} ({e.strerror}); no key was made.") from e
        print(f"Made a key for {name} ({', '.join(groups)}). It is in {path}, readable only by you; Envoy keeps only its hash.")
    elif args.cmd == "rotate":
        agent = find(auth, args.name)
        path = key_file(agent["name"], args.out)
        key = auth.rotate_agent(agent["id"])
        if key is None:
            raise SystemExit(f"{agent['name']}'s key was just revoked.")
        try:
            write_key(path, key)
        except OSError as e:
            raise SystemExit(f"{agent['name']}'s old key has stopped, but {path} couldn't be written ({e.strerror}). Rotate again with --out.") from e
        print(f"Made a new key for {agent['name']}: its old key has stopped working. The new one is in {path}, readable only by you.")
    elif args.cmd == "list":
        agents = auth.agents()
        for a in agents:
            print(f"{a['name']}: {', '.join(a['tools'])} · key made {when(a['created_at'])} · last seen {when(a['last_seen'])}")
        if not agents:
            print("No agent keys yet. (Muse uses MCP_BEARER_TOKEN from .env.)")
    else:
        agent = find(auth, args.name)
        auth.revoke_agent(agent["id"])
        print(f"Revoked {agent['name']}'s key: it stopped working at once.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
