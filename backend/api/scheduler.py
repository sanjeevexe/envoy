"""Scheduled and event-triggered tasks (design doc, Scheduled and event-triggered tasks).

Six kinds of trigger. The first five are checked every few seconds here:

- **time**: every N minutes, daily at a time, weekly on some days at a time (`weekly_on: {"days": ["fri"], "at": "18:00"}`),
  or once at a moment.
- **before_fact**: a time derived from memory, e.g. 24 hours before any flight departs. It is computed again on every
  check, so when the departure changes (a delay), the trigger moves with it; each departure fires once.
- **watch**: rerun a read-only routine every N minutes (for example, the gate) until a moment.
- **email**: a new email from a sender (and subject) starts a routine.
- **fact_changed**: a remembered fact changes (memory's `fact_replaced`: a new value superseding an old one, not a first
  sighting and not your own edit), e.g. a flight's departure time. Each change fires once; several changes to the same
  fact between two checks fire once, from the first old value to the last new one (none if it went back). Changes made
  while the trigger is paused are skipped, not replayed. A change made by a task this same trigger started doesn't fire
  it again.

The sixth, **notification**, is driven from outside: a notification on Envoy's phone from an app you let Envoy watch
(`spec.package`, words it contains). api/notifications.py reads the phone and calls `fire()` once per notification; its
action may be left out, and then it only tells you (a push) and the agents (phone_updates).

Email and fact-changed triggers read memory from a cursor (an email's row, an event's seq) that counts rows in one memory
database, while the triggers live with the tasks, which both profiles share. So each cursor names its database
(`spec.memory_db`). After a restart on the other profile, or on a rebuilt database, the trigger starts again from the end of
that database's log: nothing from before is replayed, and nothing new waits for the count to catch up.

A watcher's run pushes when it changed a remembered fact it watches (`spec.alert`, on by default for watchers;
`spec.alert_on`, by default what its routine reads); the sending is in api/alerts.py.

What a trigger runs is fixed when you create it: a goal written by you, or a routine. Memory, emails and changes only
supply typed values: `{trip.destination}` in a goal template, `{change.old}` and `{change.new}`, or a routine input mapped
to `Trip.destination`. They never
supply the goal or the plan, and values are cut to one short line. Triggered tasks go through the same policy as any
other: an irreversible step still needs your approval.

**Ask mode** (`action.ask`): a firing raises an offer (api/offers.py, kind `trigger`) instead of starting the task: "Check in
for SL 482?" with the filled goal on the card, and the task starts only on your yes. Its key is the trigger and the
occasion (`2026-10-31`, `<flight>@<departure>`, `mail<row>`, `chg<seq>`), never the values, so one "Not now" doesn't
block the next Friday. The offer's request is the goal's template with every slot left empty: values never put words
into what the approval rules read. A check-in offer expires at departure.

A trigger can be created switched off (`add(..., enabled=False)`): an AI client's `create_trigger` does that, so nothing
fires before you say yes.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from memory.store import MemoryStore
from memory.types import NOT_ABOUT_YOU, TYPES, normalize_key_value, parse_date

from api.store import TaskStore

KINDS = ("time", "before_fact", "watch", "email", "fact_changed", "notification")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")  # weekly_on's days, as datetime.weekday() counts them
CURSORS = {"email": "after_rowid", "fact_changed": "after_seq"}  # kind → its cursor in the memory database


def memory_db_id(memory: MemoryStore) -> str:
    """Which memory database a cursor counts in: its file and that file's inode, hashed. scripts/demo_setup.py deletes
    and rebuilds the demo database at the same path, which starts its log over."""
    if not isinstance(memory.path, Path):
        return f"mem-{id(memory.db):x}"  # an in-memory database is a new one every time
    try:
        ino = memory.path.stat().st_ino
    except OSError:
        ino = 0
    return hashlib.sha256(f"{memory.path.resolve()}#{ino}".encode()).hexdigest()[:12]


def check_alert(spec: dict[str, Any]) -> None:
    """A trigger's alert settings (api/alerts.py): `alert` on or off, `alert_on` a list of attributes."""
    if "alert" in spec and not isinstance(spec["alert"], bool):
        raise ValueError("alert is on or off (true or false)")
    if spec.get("alert_on") is not None and not (isinstance(spec["alert_on"], list) and all(isinstance(a, str) for a in spec["alert_on"])):
        raise ValueError("alert_on is a list of attributes")


def _clean(v: Any) -> str:
    """A memory value as a typed input: one short line, nothing that reads like an instruction's structure."""
    return re.sub(r"[\r\n\t{}<>]", " ", str(v or "")).strip()[:80]


def check_ask(kind: str, action: dict[str, Any]) -> None:
    """Ask mode's settings: `ask` on or off, `offer_title` a short template ("Check in for {number}?")."""
    if "ask" in action and not isinstance(action["ask"], bool):
        raise ValueError("ask is on or off (true or false)")
    title = action.get("offer_title")
    if title is not None and not (isinstance(title, str) and 0 < len(title.strip()) <= 120 and "\n" not in title):
        raise ValueError("offer_title is one short line")


def check_weekly(spec: dict[str, Any]) -> None:
    """`weekly_on`: {"days": ["mon", "fri"], "at": "18:00"}, normalized in place (days in week order, lowercase)."""
    w = spec.get("weekly_on")
    if w is None:
        return
    if not isinstance(w, dict) or not isinstance(w.get("days"), list) or not w["days"]:
        raise ValueError('weekly_on is {"days": ["fri"], "at": "18:00"}')
    days = {str(d).strip().lower()[:3] for d in w["days"]}
    if bad := sorted(days - set(DAYS)):
        raise ValueError(f"weekly_on: unknown day {bad[0]!r} (mon … sun)")
    if parse_clock(str(w.get("at") or "")) is None:
        raise ValueError("weekly_on needs a time (at), e.g. 18:00")
    spec["weekly_on"] = {"days": [d for d in DAYS if d in days], "at": str(w["at"]).strip()}


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
        self.memory_db = memory_db_id(memory)
        self.offers: Any = None  # api/offers.py, set by the app: ask-mode triggers raise offers through it
        self.repeats: Any = None  # api/repeats.py, set by the app: looks for habits once a day

    # ---- creating ------------------------------------------------------------------------------

    def add(self, kind: str, name: str, spec: dict[str, Any], action: dict[str, Any], enabled: bool = True) -> dict[str, Any]:
        """A new trigger. `enabled=False` creates it switched off: nothing fires until it's turned on."""
        if kind not in KINDS:
            raise ValueError(f"unknown trigger kind {kind!r}")
        if not (action.get("goal") or action.get("routine")) and kind != "notification":  # a notification can just tell you
            raise ValueError("a trigger runs a goal you wrote or a routine")
        if kind == "notification":
            from api.notifications import check_spec
            check_spec(spec)
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
            if type_ not in TYPES or type_ in NOT_ABOUT_YOU:
                raise ValueError(f"unknown entity type {type_!r}")
            attrs = spec.get("attributes") or ([spec["attribute"]] if spec.get("attribute") else [])
            if not attrs or not all(isinstance(a, str) for a in attrs):
                raise ValueError("a fact-changed trigger names the attribute it watches")
            if bad := [a for a in attrs if a not in TYPES[type_].attributes]:
                raise ValueError(f"{type_} has no attribute {bad[0]!r}")
            spec["attributes"] = attrs
            spec.setdefault("after_seq", self._last_event_seq())  # only changes from now on
        if kind in CURSORS:
            spec["memory_db"] = self.memory_db  # the database that cursor counts in
        check_alert(spec)
        check_ask(kind, action)
        if kind == "time":
            check_weekly(spec)
        if enabled:
            return self.store.add_trigger(kind, name, spec, action)
        with self.store.lock:  # switched off before any tick can see it
            trig = self.store.add_trigger(kind, name, spec, action)
            self.store.update_trigger(trig["id"], enabled=0)
        return self.store.trigger(trig["id"]) or trig

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
        if self.offers is not None:
            self.offers.sweep()  # a check-in offer nobody answered expires at departure
        if self.repeats is not None:
            self.repeats.daily()  # learning from repeats, once a day (and after each task that finishes)
        for trig in self.store.triggers():
            if trig["kind"] in CURSORS:
                self._rebaseline(trig)
            if not trig["enabled"]:
                if trig["kind"] == "fact_changed" and (last := self._last_event_seq()) > trig["spec"].get("after_seq", 0):
                    self._advance(trig["id"], last)  # paused: what changes meanwhile isn't replayed on resume
                continue
            for key, values in self.due(trig, now):
                task = self._fire(trig, values, key)
                fired = (trig["fired"] + [key])[-200:]
                self.store.update_trigger(trig["id"], last_fired=now, fired=fired)
                trig["fired"] = fired
                if task is not None:
                    started.append(task)
            if (upto := self._scanned.pop(trig["id"], None)) is not None and upto > trig["spec"].get("after_seq", 0):
                self._advance(trig["id"], upto)  # keeps each check short
        return started

    def _rebaseline(self, trig: dict[str, Any]) -> None:
        """A cursor taken in another memory database (the other profile, or this one before a rebuild) means nothing here:
        start from the end of this one's log. Its fired keys go too, since they are row numbers in that other log."""
        field = CURSORS[trig["kind"]]
        end = self._last_event_seq() if trig["kind"] == "fact_changed" else self._last_email_rowid()
        if trig["spec"].get("memory_db") == self.memory_db and trig["spec"].get(field, 0) <= end:
            return  # the same database (past its end only if its log started over)
        cur = self.store.trigger(trig["id"]) or trig
        trig["spec"], trig["fired"] = {**cur["spec"], field: end, "memory_db": self.memory_db}, []
        self.store.update_trigger(trig["id"], spec=trig["spec"], fired=[])

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
            elif (spec.get("daily_at") or spec.get("weekly_on")) and (hm := parse_clock(spec.get("daily_at") or spec["weekly_on"].get("at"))):
                today = datetime.fromtimestamp(now).replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
                key = today.strftime("%Y-%m-%d")
                on_day = not spec.get("weekly_on") or DAYS[today.weekday()] in spec["weekly_on"]["days"]
                if on_day and now >= today.timestamp() and key not in fired and now - today.timestamp() < 3600:
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
        if spec.get("weekly_on") and (hm := parse_clock(spec["weekly_on"].get("at"))):
            t = datetime.fromtimestamp(now).replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
            runs = [t + timedelta(days=i) for i in range(15) if DAYS[(t + timedelta(days=i)).weekday()] in spec["weekly_on"]["days"]]
            return [{"at": r.timestamp()} for r in runs if r.timestamp() > now][:3]
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
        if task and task.get("source") == f"trigger:{trig['name']}":
            return True
        # a task started from this trigger's offer (you said yes, so its source is where you tapped)
        return bool(task and self.offers is not None and self.offers.trigger_of(task["id"]) == trig["id"])

    # ---- firing --------------------------------------------------------------------------------

    def fire(self, trig: dict[str, Any], key: str, values: dict[str, str]) -> dict[str, Any] | None:
        """An occasion found outside the loop (a notification): run the trigger's action, once per key. Returns the task,
        the offer (ask mode), or None (already fired, or a trigger that only tells you)."""
        cur = self.store.trigger(trig["id"]) or trig
        if key in cur["fired"]:
            return None
        act = cur["action"] or {}
        out = self._fire(cur, values, key) if (act.get("goal") or act.get("routine")) else None
        self.store.update_trigger(cur["id"], last_fired=self.clock(), fired=(cur["fired"] + [key])[-200:])
        return out

    def _fire(self, trig: dict[str, Any], values: dict[str, str], key: str = "") -> dict[str, Any] | None:
        action = trig["action"]
        src = f"trigger:{trig['name']}"
        lower = {k.lower(): _clean(v) for k, v in values.items()}
        if action.get("ask"):
            return self._ask(trig, lower, key)
        if action.get("routine"):
            inputs = self._inputs(action, lower)
            goal = action.get("goal") or f"run routine {action['routine']}"
            task = self.start_task(_fill(goal, lower), src, routine=action["routine"], inputs=inputs)
        else:
            task = self.start_task(_fill(action["goal"], lower), src)
        self.bus.publish("trigger_fired", trigger=trig["id"], name=trig["name"], task_id=task["id"])
        return task

    def _inputs(self, action: dict[str, Any], lower: dict[str, str]) -> dict[str, str]:
        inputs = dict(action.get("inputs") or {})
        for name, path in (action.get("inputs_from") or {}).items():  # input → "Trip.destination" / "trip.destination"
            if (v := lower.get(path.lower())) is not None:
                inputs[name] = v
        return inputs

    def goal_template(self, action: dict[str, Any]) -> str:
        """What an ask-mode trigger's card says it will do: your goal, else the routine's own intent."""
        if action.get("goal"):
            return str(action["goal"])
        try:
            return self.routines.get(action["routine"]).intent if self.routines is not None else f"run routine {action['routine']}"
        except Exception:  # noqa: BLE001 - a routine that can't be read: its name
            return f"run routine {action['routine']}"

    def _ask(self, trig: dict[str, Any], lower: dict[str, str], key: str) -> dict[str, Any] | None:
        """Ask mode: an offer instead of the task. Nothing starts until you say yes."""
        action = trig["action"]
        if self.offers is None:  # never start it silently instead
            self.bus.publish("trigger_error", trigger=trig["id"], error="ask mode needs offers, which aren't set up here")
            return None
        template = self.goal_template(action)
        goal, request = _fill(template, lower), _fill(template, {})  # the request: every slot left empty
        title = _fill(action["offer_title"], lower) if action.get("offer_title") else _should_i(goal)
        when = None
        if trig["kind"] == "before_fact" and "@" in key:
            when = float(key.rsplit("@", 1)[1])  # the departure: a check-in offer is no use after it
        elif trig["spec"].get("every_minutes"):
            when = self.clock() + trig["spec"]["every_minutes"] * 60  # the next one replaces it
        elif trig["kind"] == "time" and (trig["spec"].get("daily_at") or trig["spec"].get("weekly_on")):
            when = self.clock() + 86400
        elif trig["kind"] == "notification":
            when = self.clock() + 6 * 3600  # "Should I…?" about a comment is stale by evening; each one has its own card
        offer = self.offers.make(
            kind="trigger", title=title, body=f"From your trigger “{trig['name']}”, which asks you first.",
            action={"type": "task", "goal": goal, "request": request, "routine": action.get("routine"),
                    "inputs": self._inputs(action, lower) if action.get("routine") else {}, "app": action.get("app"), "phone": action.get("phone")},
            source=f"trigger:{trig['name']}", key=f"{trig['id']}:{key}", expires_at=when, origin={"trigger_id": trig["id"]})
        self.bus.publish("trigger_fired", trigger=trig["id"], name=trig["name"], offer_id=(offer or {}).get("id"))
        return offer


def _to_you(goal: str) -> str:
    """'Check me in for my flight' as Envoy says it back: 'check you in for your flight'."""
    swap = {"me": "you", "my": "your", "mine": "yours", "i": "you", "i'm": "you're", "myself": "yourself"}
    out = re.sub(r"\b(me|my|mine|I|I'm|myself)\b", lambda m: swap[m.group(1).lower()], goal.rstrip(".?! "))
    return out[:1].lower() + out[1:]


def _should_i(goal: str) -> str:
    """An ask-mode offer's title when the trigger has none: "Should I check you in for your flight to Chicago?"."""
    said = _to_you(goal)
    if goal.rstrip().endswith("?") or re.match(r"(?i)(what|when|where|which|who|how|is|are|does|do|did|has|have|can)\b", goal.strip()):
        return f"Should I look this up: {said}?"
    return f"Should I {said}?"


def _fill(template: str, values: dict[str, str]) -> str:
    """'Check me in for my flight to {trip.destination}' with typed values; unknown fields are left out."""
    return re.sub(r"\{([\w.]+)\}", lambda m: values.get(m.group(1).lower(), ""), template).replace("  ", " ").strip()
