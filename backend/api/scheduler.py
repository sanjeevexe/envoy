"""Scheduled and event-triggered tasks (design doc, Scheduled and event-triggered tasks).

Five kinds of trigger, checked every few seconds:

- **time**: every N minutes, daily at a time, or once at a moment.
- **before_fact**: a time derived from memory, e.g. 24 hours before any flight departs. It is computed again on every
  check, so when the departure changes (a delay), the trigger moves with it; each departure fires once.
- **watch**: rerun a read-only routine every N minutes (for example, the gate) until a moment.
- **email**: a new email from a sender (and subject) starts a routine.
- **fact_changed**: a remembered fact changes (memory's `fact_replaced`: a new value superseding an old one, not a first
  sighting and not your own edit), e.g. a flight's departure time. Each change fires once; several changes to the same
  fact between two checks fire once, from the first old value to the last new one (none if it went back). Changes made
  while the trigger is paused are skipped, not replayed. A change made by a task this same trigger started doesn't fire
  it again.

A watcher's run pushes when it changed a remembered fact it watches (`spec.alert`, on by default for watchers;
`spec.alert_on`, by default what its routine reads); the sending is in api/alerts.py.

What a trigger runs is fixed when you create it: a goal written by you, or a routine. Memory, emails and changes only
supply typed values: `{trip.destination}` in a goal template, `{change.old}` and `{change.new}`, or a routine input mapped
to `Trip.destination`. They never
supply the goal or the plan, and values are cut to one short line. Triggered tasks go through the same policy as any
other: an irreversible step still needs your approval.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timedelta
from typing import Any, Callable

from memory.store import MemoryStore
from memory.types import TYPES, normalize_key_value, parse_date

from api.store import TaskStore

KINDS = ("time", "before_fact", "watch", "email", "fact_changed")


def check_alert(spec: dict[str, Any]) -> None:
    """A trigger's alert settings (api/alerts.py): `alert` on or off, `alert_on` a list of attributes."""
    if "alert" in spec and not isinstance(spec["alert"], bool):
        raise ValueError("alert is on or off (true or false)")
    if spec.get("alert_on") is not None and not (isinstance(spec["alert_on"], list) and all(isinstance(a, str) for a in spec["alert_on"])):
        raise ValueError("alert_on is a list of attributes")


def _clean(v: Any) -> str:
    """A memory value as a typed input: one short line, nothing that reads like an instruction's structure."""
    return re.sub(r"[\r\n\t{}<>]", " ", str(v or "")).strip()[:80]


def parse_clock(s: str | None) -> tuple[int, int] | None:
    m = re.search(r"(\d{1,2}):(\d{2})\s*([AaPp])?\.?[Mm]?", s or "")
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if m.group(3):
        h = h % 12 + (12 if m.group(3).lower() == "p" else 0)
    return (h, mi) if h < 24 and mi < 60 else None


class Scheduler:
    def __init__(self, store: TaskStore, memory: MemoryStore, start: Callable[..., Any], bus: Any, routines: Any = None,
                 clock: Callable[[], float] = time.time, every_s: float = 10) -> None:
        self.store, self.memory, self.start_task, self.bus, self.routines = store, memory, start, bus, routines
        self.clock, self.every_s = clock, every_s
        self._task: asyncio.Task | None = None
        self._scanned: dict[str, int] = {}  # fact_changed trigger → the last memory event seq its check read

    # ---- creating ------------------------------------------------------------------------------

    def add(self, kind: str, name: str, spec: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
        if kind not in KINDS:
            raise ValueError(f"unknown trigger kind {kind!r}")
        if not (action.get("goal") or action.get("routine")):
            raise ValueError("a trigger runs a goal you wrote or a routine")
        if kind == "watch":
            if not action.get("routine"):
                raise ValueError("a watcher reruns a routine")
            if self.routines is not None:
                r = self.routines.get(action["routine"])
                if any(s.risk == "irreversible" for s in r.steps):
                    raise ValueError("a watcher may only rerun a read-only routine")
        if kind == "email":
            spec.setdefault("after_rowid", self._last_email_rowid())  # only mail that arrives from now on
        if kind == "fact_changed":
            type_ = spec.get("entity_type")
            if type_ not in TYPES:
                raise ValueError(f"unknown entity type {type_!r}")
            attrs = spec.get("attributes") or ([spec["attribute"]] if spec.get("attribute") else [])
            if not attrs or not all(isinstance(a, str) for a in attrs):
                raise ValueError("a fact-changed trigger names the attribute it watches")
            if bad := [a for a in attrs if a not in TYPES[type_].attributes]:
                raise ValueError(f"{type_} has no attribute {bad[0]!r}")
            spec["attributes"] = attrs
            spec.setdefault("after_seq", self._last_event_seq())  # only changes from now on
        check_alert(spec)
        return self.store.add_trigger(kind, name, spec, action)

    # ---- the loop ------------------------------------------------------------------------------

    def run_in_background(self) -> None:
        self._task = asyncio.get_running_loop().create_task(self._loop())

    async def _loop(self) -> None:
        while True:
            try:
                self.tick()
            except Exception as e:  # noqa: BLE001 - a broken trigger must not stop the others
                self.bus.publish("trigger_error", error=f"{type(e).__name__}: {e}"[:300])
            await asyncio.sleep(self.every_s)

    def tick(self) -> list[dict[str, Any]]:
        """Fire every trigger that is due; returns what was started."""
        now = self.clock()
        started = []
        for trig in self.store.triggers():
            if not trig["enabled"]:
                if trig["kind"] == "fact_changed" and (last := self._last_event_seq()) > trig["spec"].get("after_seq", 0):
                    self._advance(trig["id"], last)  # paused: what changes meanwhile isn't replayed on resume
                continue
            for key, values in self.due(trig, now):
                task = self._fire(trig, values)
                fired = (trig["fired"] + [key])[-200:]
                self.store.update_trigger(trig["id"], last_fired=now, fired=fired)
                trig["fired"] = fired
                started.append(task)
            if (upto := self._scanned.pop(trig["id"], None)) is not None and upto > trig["spec"].get("after_seq", 0):
                self._advance(trig["id"], upto)  # keeps each check short
        return started

    def _advance(self, tid: str, seq: int) -> None:
        cur = self.store.trigger(tid)  # read again: an alert setting saved during this tick stays
        if cur is not None:
            self.store.update_trigger(tid, spec={**cur["spec"], "after_seq": seq})

    def due(self, trig: dict[str, Any], now: float) -> list[tuple[str, dict[str, str]]]:
        """(a key that fires once, the values it brings) for each occasion that is due now."""
        spec, kind, fired = trig["spec"], trig["kind"], set(trig["fired"])
        out: list[tuple[str, dict[str, str]]] = []
        if kind in ("time", "watch"):
            if spec.get("until") and now > spec["until"]:
                return []
            if spec.get("every_minutes"):
                last = trig["last_fired"] or trig["created_at"] - spec["every_minutes"] * 60 * (0 if spec.get("wait_first") else 1)
                if now - last >= spec["every_minutes"] * 60:
                    out.append((f"t{int(now)}", {}))
            elif spec.get("at") and now >= spec["at"] and "once" not in fired:
                out.append(("once", {}))
            elif spec.get("daily_at") and (hm := parse_clock(spec["daily_at"])):
                today = datetime.fromtimestamp(now).replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
                key = today.strftime("%Y-%m-%d")
                if now >= today.timestamp() and key not in fired and now - today.timestamp() < 3600:
                    out.append((key, {}))
        elif kind == "before_fact":
            for when, eid, values in self.occasions(spec):
                key = f"{eid}@{int(when)}"
                fire_at = when - spec.get("minutes_before", 1440) * 60
                if fire_at <= now < when and key not in fired:
                    out.append((key, values))
        elif kind == "email":
            for rowid, values in self._new_emails(spec, fired):
                out.append((f"mail{rowid}", values))
        elif kind == "fact_changed":
            for seq, values in self._changes(trig, fired):
                out.append((f"chg{seq}", values))
        return out

    def occasions(self, spec: dict[str, Any]) -> list[tuple[float, str, dict[str, str]]]:
        """For each entity of the type: when it happens (date + time facts), and its values for the action."""
        out = []
        for e in self.memory.entities(spec.get("entity_type", "Flight")):
            values = self.values(e["id"])
            d = parse_date(values.get(spec.get("date_attr", "date")))
            hm = parse_clock(values.get(spec.get("time_attr", "depart_time"))) or (0, 0)
            if d is None:
                continue
            when = datetime(d.year, d.month, d.day, hm[0], hm[1]).timestamp()
            out.append((when, e["id"], values))
        return sorted(out)

    def values(self, eid: str) -> dict[str, str]:
        """The entity's current facts ("number") and its neighbors' ("trip.destination")."""
        vals = {f["attribute"]: f["value"] for f in self.memory.current_facts(eid)}
        for n in self.memory.neighbors(eid):
            ne = self.memory.entity(n) or {}
            for f in self.memory.current_facts(n):
                vals.setdefault(f"{ne.get('type', '').lower()}.{f['attribute']}", f["value"])
        return vals

    def next_runs(self, trig: dict[str, Any], now: float | None = None) -> list[dict[str, Any]]:
        """When the trigger will fire next (for the web app)."""
        now = self.clock() if now is None else now
        spec = trig["spec"]
        if trig["kind"] == "before_fact":
            return [{"at": when - spec.get("minutes_before", 1440) * 60, "for": values.get("number") or eid}
                    for when, eid, values in self.occasions(spec) if when > now and f"{eid}@{int(when)}" not in trig["fired"]][:5]
        if spec.get("every_minutes"):
            return [{"at": (trig["last_fired"] or now) + spec["every_minutes"] * 60}]
        if spec.get("at"):
            return [] if "once" in trig["fired"] else [{"at": spec["at"]}]
        if spec.get("daily_at") and (hm := parse_clock(spec["daily_at"])):
            t = datetime.fromtimestamp(now).replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
            return [{"at": (t if t.timestamp() > now else t + timedelta(days=1)).timestamp()}]
        return []

    # ---- email triggers ------------------------------------------------------------------------

    def _last_email_rowid(self) -> int:
        row = self.memory.db.execute("select max(rowid) from sources where kind in ('email', 'email_markup')").fetchone()
        return int(row[0] or 0)

    def _new_emails(self, spec: dict[str, Any], fired: set[str]) -> list[tuple[int, dict[str, str]]]:
        rows = self.memory.db.execute("select rowid, id, reference from sources where kind in ('email', 'email_markup') and rowid > ? order by rowid",
                                      (spec.get("after_rowid", 0),)).fetchall()
        out = []
        for r in rows:
            if f"mail{r[0]}" in fired:
                continue
            ref = json.loads(r[2] or "{}")
            sender, subject = str(ref.get("sender") or ref.get("from") or ""), str(ref.get("subject") or "")
            if spec.get("sender_contains") and spec["sender_contains"].lower() not in sender.lower():
                continue
            if spec.get("subject_contains") and spec["subject_contains"].lower() not in subject.lower():
                continue
            values: dict[str, str] = {}
            for (eid,) in self.memory.db.execute(
                    "select distinct f.entity from facts f join fact_sources fs on fs.fact = f.id where fs.source = ?", (r[1],)).fetchall():
                e = self.memory.entity(eid) or {}
                for k, v in self.values(eid).items():
                    values.setdefault(f"{e.get('type', '')}.{k}", v)
            out.append((int(r[0]), values))
        return out

    # ---- fact-changed triggers ---------------------------------------------------------------

    def _last_event_seq(self) -> int:
        row = self.memory.db.execute("select max(seq) from events").fetchone()
        return int(row[0] or 0)

    def _changes(self, trig: dict[str, Any], fired: set[str]) -> list[tuple[int, dict[str, str]]]:
        """Memory's changes since the last check that match: (seq, typed values for the action)."""
        spec = trig["spec"]
        attrs = set(spec.get("attributes") or [spec.get("attribute")])
        events = self.memory.events(spec.get("after_seq", 0), kind="fact_replaced")  # read-only: memory's own log
        net: dict[tuple[str, str], dict[str, Any]] = {}  # (entity, attribute) → first old, last new, last seq
        for ev in events:
            if f"chg{ev['seq']}" in fired or ev.get("attribute") not in attrs:
                continue
            eid = self.memory.resolve(ev["entity"])
            e = self.memory.entity(eid) or {}
            if e.get("type") != spec.get("entity_type") or self._made_by(trig, ev):
                continue
            k = (eid, ev["attribute"])
            net[k] = {"type": e["type"], "old": net[k]["old"] if k in net else ev.get("old") or "", "new": ev.get("value") or "", "seq": int(ev["seq"])}
        out = []
        for (eid, attr), ch in net.items():
            if normalize_key_value(attr, ch["old"]) == normalize_key_value(attr, ch["new"]):
                continue  # it went back within one check: nothing changed
            values = self.values(eid)
            type_ = ch["type"].lower()
            for f in self.memory.current_facts(eid):
                values[f"{type_}.{f['attribute']}"] = f["value"]
            values.update({"change.attribute": attr, "change.old": ch["old"], "change.new": ch["new"]})
            out.append((ch["seq"], values))
        if events:
            self._scanned[trig["id"]] = int(events[-1]["seq"])
        return out

    def _made_by(self, trig: dict[str, Any], ev: dict[str, Any]) -> bool:
        """The change came from a task this trigger started (so "when the gate changes, read the gate" can't feed itself)."""
        row = self.memory.db.execute("select source from facts where id = ?", (ev.get("fact"),)).fetchone()
        src = self.memory.source(row[0]) if row and row[0] else None
        tid = ((src or {}).get("reference") or {}).get("task_id")
        task = self.store.get(tid) if tid else None
        return bool(task and task.get("source") == f"trigger:{trig['name']}")

    # ---- firing --------------------------------------------------------------------------------

    def _fire(self, trig: dict[str, Any], values: dict[str, str]) -> dict[str, Any]:
        action = trig["action"]
        src = f"trigger:{trig['name']}"
        lower = {k.lower(): _clean(v) for k, v in values.items()}
        if action.get("routine"):
            inputs = dict(action.get("inputs") or {})
            for name, path in (action.get("inputs_from") or {}).items():  # input → "Trip.destination" / "trip.destination"
                if (v := lower.get(path.lower())) is not None:
                    inputs[name] = v
            goal = action.get("goal") or f"run routine {action['routine']}"
            task = self.start_task(_fill(goal, lower), src, routine=action["routine"], inputs=inputs)
        else:
            task = self.start_task(_fill(action["goal"], lower), src)
        self.bus.publish("trigger_fired", trigger=trig["id"], name=trig["name"], task_id=task["id"])
        return task


def _fill(template: str, values: dict[str, str]) -> str:
    """'Check me in for my flight to {trip.destination}' with typed values; unknown fields are left out."""
    return re.sub(r"\{([\w.]+)\}", lambda m: values.get(m.group(1).lower(), ""), template).replace("  ", " ").strip()
