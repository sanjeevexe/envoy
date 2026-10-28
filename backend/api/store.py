"""Tasks, their steps, approvals and triggers, in SQLite (data/api/envoy.db).

A task is the shared unit of work (design doc, Tasks): every request from any interface becomes one, with its goal,
the interface it came from, its status, its steps and its approvals.
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
API_DIR = Path(os.environ.get("ENVOY_API_DIR") or REPO / "data" / "api")  # tasks, approvals, screenshots, the session token

# queued → running → (needs_you ↔ taken_over) → (waiting_approval) → done | failed | declined | stopped
ACTIVE = ("queued", "running", "needs_you", "taken_over", "waiting_approval")

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY, goal TEXT NOT NULL, source TEXT NOT NULL, status TEXT NOT NULL, created_at REAL, updated_at REAL,
  app TEXT, device TEXT, kind TEXT, routine TEXT, inputs TEXT, result TEXT, detail TEXT, waiting_for TEXT,
  model_calls INTEGER DEFAULT 0, cost_usd REAL DEFAULT 0, traces TEXT DEFAULT '[]', memory TEXT, request TEXT, parent TEXT
);
CREATE TABLE IF NOT EXISTS steps (
  task_id TEXT, seq INTEGER, time REAL, data TEXT, PRIMARY KEY (task_id, seq)
);
CREATE TABLE IF NOT EXISTS approvals (
  id TEXT PRIMARY KEY, task_id TEXT, created_at REAL, status TEXT, description TEXT, reasons TEXT, app TEXT,
  screen TEXT, screenshot TEXT, nonce TEXT, decided_at REAL, decided_by TEXT, note TEXT
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS triggers (
  id TEXT PRIMARY KEY, kind TEXT, name TEXT, spec TEXT, action TEXT, enabled INTEGER DEFAULT 1, created_at REAL,
  last_fired REAL, fired TEXT DEFAULT '[]'
);
"""


def new_id(prefix: str) -> str:
    return f"{prefix}-{time.strftime('%m%d-%H%M%S')}-{secrets.token_hex(2)}"


class TaskStore:
    def __init__(self, path: Path | str = API_DIR / "envoy.db") -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.db.executescript(SCHEMA)
            columns = {r[1] for r in self.db.execute("PRAGMA table_info(tasks)")}
            if "request" not in columns:  # databases from before approval rules
                self.db.execute("ALTER TABLE tasks ADD COLUMN request TEXT")
            if "parent" not in columns:  # databases from before cross-app answers (a part's parent task)
                self.db.execute("ALTER TABLE tasks ADD COLUMN parent TEXT")
            # A restart ends whatever was running: the runner that owned it is gone.
            self.db.execute("UPDATE tasks SET status='stopped', detail='the server restarted' WHERE status IN (%s)" % ",".join("?" * len(ACTIVE)), ACTIVE)
            self.db.execute("UPDATE approvals SET status='expired', note='the server restarted' WHERE status='pending'")
            self.db.commit()

    # ---- tasks ---------------------------------------------------------------------------------

    def create(self, goal: str, source: str, **fields: Any) -> dict[str, Any]:
        tid = new_id("task")
        now = time.time()
        with self.lock:
            self.db.execute("INSERT INTO tasks (id, goal, source, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                            (tid, goal, source, "queued", now, now))
            self.db.commit()
        if fields:
            self.update(tid, **fields)
        return self.get(tid)  # type: ignore[return-value]

    def update(self, tid: str, **fields: Any) -> dict[str, Any] | None:
        if not fields:
            return self.get(tid)
        enc = {k: json.dumps(v) if k in ("inputs", "traces", "memory") and not isinstance(v, str) else v for k, v in fields.items()}
        enc["updated_at"] = time.time()
        with self.lock:
            self.db.execute(f"UPDATE tasks SET {', '.join(f'{k}=?' for k in enc)} WHERE id=?", (*enc.values(), tid))
            self.db.commit()
        return self.get(tid)

    def get(self, tid: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.db.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
        return _task(row) if row else None

    def list(self, limit: int = 50, active_only: bool = False) -> list[dict[str, Any]]:
        q = "SELECT * FROM tasks" + (" WHERE status IN (%s)" % ",".join("?" * len(ACTIVE)) if active_only else "") + " ORDER BY created_at DESC LIMIT ?"
        with self.lock:
            rows = self.db.execute(q, (*(ACTIVE if active_only else ()), limit)).fetchall()
        return [_task(r) for r in rows]

    # ---- steps ---------------------------------------------------------------------------------

    def add_step(self, tid: str, data: dict[str, Any]) -> int:
        with self.lock:
            seq = (self.db.execute("SELECT COALESCE(MAX(seq), 0) FROM steps WHERE task_id=?", (tid,)).fetchone()[0] or 0) + 1
            self.db.execute("INSERT INTO steps VALUES (?,?,?,?)", (tid, seq, time.time(), json.dumps(data, default=str)))
            self.db.commit()
        return seq

    def set_step(self, tid: str, seq: int, data: dict[str, Any]) -> None:
        with self.lock:
            self.db.execute("UPDATE steps SET data=? WHERE task_id=? AND seq=?", (json.dumps(data, default=str), tid, seq))
            self.db.commit()

    def steps(self, tid: str) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.db.execute("SELECT * FROM steps WHERE task_id=? ORDER BY seq", (tid,)).fetchall()
        return [{"seq": r["seq"], "time": r["time"], **json.loads(r["data"])} for r in rows]

    # ---- approvals -----------------------------------------------------------------------------

    def add_approval(self, task_id: str, description: str, reasons: list[str], app: str, screen: str, screenshot: str | None) -> dict[str, Any]:
        aid = new_id("appr")
        with self.lock:
            self.db.execute("INSERT INTO approvals (id, task_id, created_at, status, description, reasons, app, screen, screenshot, nonce) "
                            "VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (aid, task_id, time.time(), "pending", description, json.dumps(reasons), app, screen, screenshot, secrets.token_urlsafe(16)))
            self.db.commit()
        return self.approval(aid)  # type: ignore[return-value]

    def approval(self, aid: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.db.execute("SELECT * FROM approvals WHERE id=?", (aid,)).fetchone()
        return _approval(row) if row else None

    def approvals(self, status: str | None = None, task_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        q, args = "SELECT * FROM approvals WHERE 1=1", []
        if status:
            q += " AND status=?"
            args.append(status)
        if task_id:
            q += " AND task_id=?"
            args.append(task_id)
        with self.lock:
            rows = self.db.execute(q + " ORDER BY created_at DESC LIMIT ?", (*args, limit)).fetchall()
        return [_approval(r) for r in rows]

    def decide_approval(self, aid: str, status: str, by: str, note: str = "") -> dict[str, Any] | None:
        with self.lock:
            cur = self.db.execute("UPDATE approvals SET status=?, decided_at=?, decided_by=?, note=? WHERE id=? AND status='pending'",
                                  (status, time.time(), by, note, aid))
            self.db.commit()
            if cur.rowcount == 0:
                return None  # already decided (or unknown): a decision is final
        return self.approval(aid)

    # ---- settings ------------------------------------------------------------------------------

    def setting(self, key: str, default: Any = None) -> Any:
        with self.lock:
            row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key: str, value: Any) -> None:
        with self.lock:
            self.db.execute("INSERT INTO settings VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))
            self.db.commit()

    # ---- triggers ------------------------------------------------------------------------------

    def add_trigger(self, kind: str, name: str, spec: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
        tid = new_id("trig")
        with self.lock:
            self.db.execute("INSERT INTO triggers (id, kind, name, spec, action, created_at) VALUES (?,?,?,?,?,?)",
                            (tid, kind, name, json.dumps(spec), json.dumps(action), time.time()))
            self.db.commit()
        return self.trigger(tid)  # type: ignore[return-value]

    def trigger(self, tid: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.db.execute("SELECT * FROM triggers WHERE id=?", (tid,)).fetchone()
        return _trigger(row) if row else None

    def triggers(self) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.db.execute("SELECT * FROM triggers ORDER BY created_at").fetchall()
        return [_trigger(r) for r in rows]

    def update_trigger(self, tid: str, **fields: Any) -> None:
        enc = {k: json.dumps(v) if k in ("spec", "action", "fired") else v for k, v in fields.items()}
        with self.lock:
            self.db.execute(f"UPDATE triggers SET {', '.join(f'{k}=?' for k in enc)} WHERE id=?", (*enc.values(), tid))
            self.db.commit()

    def delete_trigger(self, tid: str) -> None:
        with self.lock:
            self.db.execute("DELETE FROM triggers WHERE id=?", (tid,))
            self.db.commit()


def _task(r: sqlite3.Row) -> dict[str, Any]:
    d = dict(r)
    for k in ("inputs", "traces", "memory"):
        if d.get(k):
            try:
                d[k] = json.loads(d[k])
            except ValueError:
                pass
    return d


def _approval(r: sqlite3.Row) -> dict[str, Any]:
    d = dict(r)
    d["reasons"] = json.loads(d["reasons"] or "[]")
    return d


def _trigger(r: sqlite3.Row) -> dict[str, Any]:
    d = dict(r)
    for k in ("spec", "action", "fired"):
        d[k] = json.loads(d[k] or ("[]" if k == "fired" else "{}"))
    d["enabled"] = bool(d["enabled"])
    return d
