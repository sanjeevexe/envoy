"""Change alerts (design doc, Scheduled and event-triggered tasks: a watcher "pushes when something changed").

A task a trigger started (a watcher rerunning the gate routine, say) is quiet when it finishes. It pushes when it changed
something memory remembered: a new value superseding an old one (memory's `fact_replaced`), not a first sighting and not
the same value seen again.

- **Noticing**: memory's own events (`MemoryStore.subscribe`), read-only. A change belongs to the task whose source wrote
  it (the source's `task_id`), so a change some other writer made while the task ran isn't credited to it.
- **Reporting**: when the runner reports the task's memory step, each change becomes a `change` step in the task, and
  the run sends at most one push. Changes from a write path with no memory step are reported a few seconds later.
- **Who is told**: only for a task a trigger started, when a trigger has alerts on (`spec.alert`: on by default for
  watchers, off for the other kinds) for that attribute (`spec.alert_on`: by default what the watcher's routine reads,
  so a seat re-read from the same screen doesn't buzz the phone; `"*"` is any). That is the task's own trigger, or
  another one whose runs have read this entity: when a fact-changed follow-up or a second watcher happens to see the
  new gate first, the watcher you set up still tells you (otherwise its next run would find nothing new). A task you
  started shows the change and doesn't push: you're already looking.
- **Once**: each (entity, attribute, new value) pushes once (the `change_alerts` table, next to the tasks). A flip back
  to an earlier value is a new change and pushes again.
"""

from __future__ import annotations

import asyncio
import secrets
import threading
import time
from typing import Any, Callable

from memory.retrieval import Retriever
from memory.store import MemoryStore
from memory.types import TYPES, canonical_attribute, normalize_key_value

from api.store import TaskStore

SCHEMA = """
CREATE TABLE IF NOT EXISTS change_alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, time REAL, task_id TEXT, trigger_id TEXT, entity TEXT, entity_label TEXT,
  attribute TEXT, old TEXT, new TEXT, norm TEXT, fact TEXT, source TEXT, seen_at REAL, pushed INTEGER DEFAULT 0,
  why_not TEXT, push_id TEXT, title TEXT, body TEXT
);
CREATE INDEX IF NOT EXISTS change_alerts_key ON change_alerts(entity, attribute, id);
"""
YOU_STARTED = "you started this task"
LABELS = {"gate": "Gate", "depart_time": "Departure", "arrive_time": "Arrival", "boarding_time": "Boarding",
          "boarding_group": "Boarding group", "status": "Status", "seat": "Seat", "terminal": "Terminal",
          "delivery_eta": "Delivery", "confirmation_code": "Confirmation"}


def label(attribute: str) -> str:
    return LABELS.get(attribute, attribute.replace("_", " ").capitalize())


class ChangeAlerts:
    def __init__(self, tasks: TaskStore, memory: MemoryStore, pusher: Any, bus: Any, routines: Any = None, *,
                 flush_after_s: float | None = 15, clock: Callable[[], float] = time.time) -> None:
        self.tasks, self.memory, self.pusher, self.bus, self.routines = tasks, memory, pusher, bus, routines
        self.flush_after_s, self.clock = flush_after_s, clock
        self.pending: dict[str, list[dict[str, Any]]] = {}  # task id → changes not reported yet
        self.started_by: dict[str, str] = {}  # task id → the trigger that started it (from trigger_fired)
        self.errors: list[str] = []
        self._lock = threading.Lock()
        with tasks.lock:
            tasks.db.executescript(SCHEMA)
            tasks.db.commit()

    # ---- noticing (a memory subscriber: it runs inside MemoryStore.observe, so it never raises) ----

    def on_memory(self, ev: dict[str, Any]) -> None:
        try:
            if ev.get("kind") != "fact_replaced":
                return
            row = self.memory.db.execute("select source from facts where id = ?", (ev.get("fact"),)).fetchone()
            sid = row["source"] if row else None
            src = self.memory.source(sid) if sid else None
            tid = ((src or {}).get("reference") or {}).get("task_id")
            if not tid:
                return
            change = {"task": tid, "entity": ev["entity"], "attribute": ev["attribute"], "old": ev.get("old"),
                      "new": ev.get("value"), "fact": ev.get("fact"), "source": sid, "seq": ev.get("seq"), "seen_at": self.clock()}
            with self._lock:
                first = tid not in self.pending
                self.pending.setdefault(tid, []).append(change)
            if first:
                self._arm(tid)
        except Exception as e:  # noqa: BLE001 - memory's write must go on whatever happens here
            self.errors = (self.errors + [f"{type(e).__name__}: {e}"[:200]])[-20:]

    def _arm(self, tid: str) -> None:
        """Report anyway after a while, for writes with no memory step to follow them."""
        loop = getattr(self.bus, "loop", None)
        if loop is None or self.flush_after_s is None:
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        later = lambda: loop.call_later(self.flush_after_s, self._timer, tid, self.clock())  # noqa: E731
        later() if running is loop else loop.call_soon_threadsafe(later)

    def _timer(self, tid: str, armed_at: float) -> None:
        """The fallback: while the runner is still writing this task's memory (a slow extraction), wait for its memory
        step, up to two minutes, so one run still sends one push."""
        steps = self.tasks.steps(tid)
        saving = max((s["seq"] for s in steps if s["kind"] == "note" and str(s.get("text", "")).startswith("saving what it saw")), default=None)
        reported = any(s["kind"] in ("memory", "error") and s["seq"] > saving for s in steps) if saving is not None else True
        if not reported and self.clock() - armed_at < 120 and self.bus.loop is not None:
            self.bus.loop.call_later(self.flush_after_s, self._timer, tid, armed_at)
            return
        self.flush(tid)

    # ---- reporting (an EventBus listener, on the API's loop) -------------------------------------

    def on_event(self, ev: dict[str, Any]) -> None:
        kind = ev.get("type")
        if kind == "trigger_fired" and ev.get("task_id"):
            self.started_by[ev["task_id"]] = ev.get("trigger") or ""
            if len(self.started_by) > 1000:
                self.started_by.pop(next(iter(self.started_by)))
        elif kind == "step" and (ev.get("step") or {}).get("kind") in ("memory", "error"):
            self.flush(ev.get("task_id") or "")

    def flush(self, tid: str) -> list[dict[str, Any]]:
        """Report the task's changes: a step each, and at most one push for all of them."""
        with self._lock:
            changes = self.pending.pop(tid, [])
        if not changes:
            return []
        task = self.tasks.get(tid) or {"id": tid}
        trig = self.trigger_of(task)
        by_key: dict[tuple[str, str], dict[str, Any]] = {}
        for c in changes:  # two writes to one attribute in a run (screen, then outputs) are one change: first old → last new
            k = (c["entity"], c["attribute"])
            by_key[k] = {**c, "old": by_key[k]["old"]} if k in by_key else c
        reports, push = [], []
        for c in by_key.values():
            if normalize_key_value(c["attribute"], c["old"] or "") == normalize_key_value(c["attribute"], c["new"] or ""):
                continue
            c["entity_label"] = self.entity_label(c["entity"])
            c["where"] = Retriever(self.memory).where(c["source"])
            c["title"] = f"{label(c['attribute'])} changed: {c['old']} → {c['new']}"
            c["why_not"] = self.why_not(task, trig, c)
            reports.append(c)
            if c["why_not"] is None:
                push.append(c)
        push_id = None
        if push:
            first = push[0]
            also = "; ".join(f"{label(c['attribute'])} {c['old']} → {c['new']}" for c in push[1:])
            body = " · ".join(x for x in (first["entity_label"], f"also {also}" if also else "", first["where"]) if x)
            push_id = f"p{int(time.time() * 1000)}-{secrets.token_hex(2)}"
            futures = self.pusher.notify("change", first["title"], body, f"/?task={tid}", tag=f"change-{first['entity']}-{first['attribute']}",
                                         urgency="high", ttl=1800, push_id=push_id) if self.pusher else []
            for c in push:
                c["body"], c["sent_to"] = body, len(futures)
                if not futures:
                    c["why_not"] = "no device has notifications on"
        out = []
        for c in reports:
            pushed = c["why_not"] is None
            with self.tasks.lock:
                self.tasks.db.execute(
                    "INSERT INTO change_alerts (time, task_id, trigger_id, entity, entity_label, attribute, old, new, norm, fact, source, "
                    "seen_at, pushed, why_not, push_id, title, body) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (self.clock(), tid, (c.get("alerted_by") or trig or {}).get("id"), c["entity"], c["entity_label"], c["attribute"], c["old"], c["new"],
                     normalize_key_value(c["attribute"], c["new"] or ""), c["fact"], c["source"], c["seen_at"], int(pushed),
                     c["why_not"], push_id if pushed else None, c["title"], c.get("body")))
                self.tasks.db.commit()
            step = {"kind": "change", "text": c["title"], "entity": c["entity"], "entity_label": c["entity_label"],
                    "attribute": c["attribute"], "old": c["old"], "new": c["new"], "source": c["where"], "pushed": pushed,
                    "why_not": c["why_not"]}
            if pushed and c.get("alerted_by") and c["alerted_by"]["id"] != (trig or {}).get("id"):
                step["alerted_for"] = c["alerted_by"]["name"]  # another trigger's alert (the watcher you set up)
            seq = self.tasks.add_step(tid, step)
            self.bus.publish("step", task_id=tid, step={"seq": seq, "time": time.time(), **step})
            out.append(step)
        if out:
            self.bus.publish("fact_changed", task_id=tid, changes=[{k: s[k] for k in ("entity", "attribute", "old", "new", "pushed")} for s in out])
        return out

    # ---- who is told ---------------------------------------------------------------------------

    def trigger_of(self, task: dict[str, Any]) -> dict[str, Any] | None:
        if (trig_id := self.started_by.get(task.get("id") or "")) and (trig := self.tasks.trigger(trig_id)):
            return trig
        src = str(task.get("source") or "")
        if not src.startswith("trigger:"):
            return None
        name = src.split(":", 1)[1]
        return next((t for t in self.tasks.triggers() if t["name"] == name), None)  # a run from before a restart

    def settings(self, trig: dict[str, Any]) -> tuple[bool, list[str]]:
        """(alerts on?, the attributes that push) for a trigger, with the defaults filled in."""
        spec = trig.get("spec") or {}
        on = bool(spec.get("alert", trig.get("kind") == "watch"))
        watched = spec.get("alert_on")
        if watched is None:
            watched = self.routine_attributes((trig.get("action") or {}).get("routine")) if trig.get("kind") == "watch" else ["*"]
        return on, [canonical_attribute(a) if a != "*" else a for a in watched] or ["*"]

    def routine_attributes(self, name: str | None) -> list[str]:
        """What a routine reads, as memory attributes (`skylark_get_flight_gate` → gate)."""
        try:
            outs = list(self.routines.get(name).outputs) if (self.routines is not None and name) else []
        except Exception:  # noqa: BLE001 - a missing routine: alert on anything
            outs = []
        attrs = [canonical_attribute(o) for o in outs]
        if "boarding_time" in attrs:
            attrs.append("boarding_group")  # "5:30 AM · Group 3" is read as both
        return attrs or ["*"]

    def why_not(self, task: dict[str, Any], trig: dict[str, Any] | None, c: dict[str, Any]) -> str | None:
        """None when this change pushes (`c["alerted_by"]` is the trigger it pushes for); otherwise why it doesn't."""
        if trig is None:
            return YOU_STARTED if not str(task.get("source") or "").startswith("trigger") else "its trigger was deleted"
        by = trig if self.watches(trig, c["attribute"]) else next(self.watchers_of(c["entity"], c["attribute"], skip=trig["id"]), None)
        if by is None:
            on, watched = self.settings(trig)
            return "alerts are off for this trigger" if not on else f"this trigger alerts on {', '.join(label(a).lower() for a in watched)} only"
        c["alerted_by"] = by
        with self.tasks.lock:  # the last value you were told: pushed, or shown in a task you started
            last = self.tasks.db.execute("SELECT norm FROM change_alerts WHERE entity=? AND attribute=? AND (pushed=1 OR why_not=?) "
                                         "ORDER BY id DESC LIMIT 1", (c["entity"], c["attribute"], YOU_STARTED)).fetchone()
        if last and last["norm"] == normalize_key_value(c["attribute"], c["new"] or ""):
            return "already told you"
        return None

    def watches(self, trig: dict[str, Any], attribute: str) -> bool:
        on, watched = self.settings(trig)
        return on and ("*" in watched or attribute in watched)

    def watchers_of(self, entity: str, attribute: str, skip: str = "") -> Any:
        """Other enabled triggers with alerts on for this attribute whose own runs have read this entity."""
        for t in self.tasks.triggers():
            if t["id"] != skip and t["enabled"] and self.watches(t, attribute) and self.has_read(t, entity):
                yield t

    def has_read(self, trig: dict[str, Any], entity: str) -> bool:
        """A run of this trigger saw a fact of this entity (any attribute, the same value seen again included)."""
        with self.tasks.lock:
            ids = [r[0] for r in self.tasks.db.execute("SELECT id FROM tasks WHERE source=? ORDER BY created_at DESC LIMIT 50",
                                                       (f"trigger:{trig['name']}",)).fetchall()]
        ids += [tid for tid, t in list(self.started_by.items()) if t == trig["id"] and tid not in ids]
        if not ids:
            return False
        q = ("select 1 from fact_sources fs join sources s on s.id = fs.source join facts f on f.id = fs.fact "
             f"where f.entity = ? and json_extract(s.reference, '$.task_id') in ({','.join('?' * len(ids))}) limit 1")
        return self.memory.db.execute(q, (self.memory.resolve(entity), *ids)).fetchone() is not None

    def entity_label(self, eid: str) -> str:
        e = self.memory.entity(eid) or {}
        type_ = e.get("type") or "Entity"
        spec = TYPES.get(type_)
        title = next((f["value"] for a in (spec.title if spec else ()) if (f := self.memory.current(eid, a))), None)
        return f"{type_} {title or e.get('name') or eid}"

    # ---- for the web app -----------------------------------------------------------------------

    def recent(self, limit: int = 30) -> list[dict[str, Any]]:
        with self.tasks.lock:
            rows = self.tasks.db.execute("SELECT * FROM change_alerts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
