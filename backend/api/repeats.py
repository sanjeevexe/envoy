"""Learning from repeats: "You checked your flight status on your last 3 Mondays. Make this a habit?"

Deterministic, no model call. It looks at the last 60 days of tasks that finished `done`, after each one finishes and once
a day, and groups them: a routine with the same inputs, or an agent run with the same goal (normalized). Three patterns:
- **weekly**: 3 or more on the same weekday, at a similar time (within 90 minutes either way);
- **daily**: 3 or more days in a row, at a similar time;
- **before a trip**: the same routine within 48 hours before 2 or more flights' departures (a flight's `date` and
  `depart_time`), its inputs read from each flight (`trip_city` was each trip's destination).

Each pattern raises one offer (api/offers.py, kind `repeat`) with the evidence ("on Oct 12, Oct 19 and Oct 26") and, on
your yes, sets up a trigger **in ask mode**: it asks you each time, so a learned habit never silently spends money or
does anything else on its own. Its key is stable, so a pattern you said "Not now" to never comes back, and one you
accepted isn't offered again.

Never learned from: tasks a trigger started, including ones started from a trigger's offer (you said yes to the
trigger, not to a habit), parts of a cross-app question, and anything a trigger already covers. A task that involved
money (a payment approval, an order) can still become a habit, but only one that asks, and the card says so.
"""

from __future__ import annotations

import hashlib
import json
import re
import statistics
import time
from datetime import date, datetime, timedelta
from typing import Any, Callable

from policy.approval_rules import involves_money

from api.scheduler import DAYS, _should_i, _to_you

WINDOW_DAYS = 60
SLACK_MIN = 90  # "a similar time": within 90 minutes either way
LEAD_S = 48 * 3600  # "before a trip": within 48 hours before departure
DAY_NAMES = {"mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday", "fri": "Friday", "sat": "Saturday", "sun": "Sunday"}
MONEY = re.compile(r"\$|\b(pay|payment|buy|purchase|order|subscribe|checkout|reorder)\b", re.I)
FLIGHT = {"entity_type": "Flight", "date_attr": "date", "time_attr": "depart_time"}
SLOT_WORDS = {"trip.destination": "your destination", "destination": "your destination", "number": "your flight", "flight.number": "your flight"}


def norm_goal(goal: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", goal.lower())).strip()


def _minute(t: float) -> int:
    d = datetime.fromtimestamp(t)
    return d.hour * 60 + d.minute


def _clock(minute: int) -> str:
    h, m = divmod(minute, 60)
    return f"{(h % 12) or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def _day(t: float | date) -> str:
    d = t if isinstance(t, date) else datetime.fromtimestamp(t)
    return f"{d.strftime('%b')} {d.day}"


def _dates(ts: list[float]) -> str:
    days = [_day(t) for t in sorted(ts)[-4:]]
    return ", ".join(days[:-1]) + f" and {days[-1]}" if len(days) > 1 else days[0]


def _round(minute: float, step: int = 15) -> int:
    return int(round(minute / step) * step) % (24 * 60)


def _close(part: list[tuple[float, int]]) -> list[tuple[float, int]]:
    """Drop the farthest until every one is within 90 minutes of the group's usual time (its median)."""
    part = list(part)
    while part:
        mid = statistics.median(m for _, m in part)
        far = max(part, key=lambda x: abs(x[1] - mid))
        if abs(far[1] - mid) <= SLACK_MIN:
            return part
        part.remove(far)
    return part


def _similar(items: list[tuple[float, int]], need: int = 3) -> list[tuple[float, int]] | None:
    """The largest set of (time, minute of day) all within 90 minutes of their usual time, if it has `need` or more."""
    by = sorted(items, key=lambda x: x[1])
    best: list[tuple[float, int]] = []
    for i in range(len(by)):
        j = i
        while j + 1 < len(by) and by[j + 1][1] - by[i][1] <= 2 * SLACK_MIN:
            j += 1
        if len(part := _close(by[i:j + 1])) > len(best):
            best = part
    return sorted(best) if len(best) >= need else None


class Repeats:
    def __init__(self, tasks: Any, memory: Any, offers: Any, scheduler: Any = None, routines: Any = None, *,
                 clock: Callable[[], float] = time.time) -> None:
        self.tasks, self.memory, self.offers, self.scheduler, self.routines, self.clock = tasks, memory, offers, scheduler, routines, clock
        self._scanned_on: str | None = None
        self.errors: list[str] = []

    # ---- when it looks (never raises: it runs inside the event bus and the scheduler's tick) ----

    def on_event(self, ev: dict[str, Any]) -> None:
        if ev.get("type") != "task_finished":
            return
        task = self.tasks.get(ev.get("task_id") or "") or {}
        if task.get("status") == "done":
            self.safe_scan()

    def daily(self) -> None:
        today = datetime.fromtimestamp(self.clock()).strftime("%Y-%m-%d")
        if self._scanned_on != today:
            self._scanned_on = today
            self.safe_scan()

    def safe_scan(self) -> list[dict[str, Any]]:
        try:
            return self.scan()
        except Exception as e:  # noqa: BLE001 - learning is a nicety: it never breaks a run or a tick
            self.errors = (self.errors + [f"{type(e).__name__}: {e}"[:200]])[-20:]
            return []

    # ---- what counts ------------------------------------------------------------------------------

    def history(self) -> list[dict[str, Any]]:
        """Done tasks from the last 60 days that you asked for yourself."""
        since = self.clock() - WINDOW_DAYS * 86400
        with self.tasks.lock:
            rows = self.tasks.db.execute("SELECT id FROM tasks WHERE status='done' AND created_at >= ? ORDER BY created_at", (since,)).fetchall()
        out = []
        for (tid,) in rows:
            t = self.tasks.get(tid)
            if not t or t.get("parent") or str(t.get("source") or "").startswith("trigger"):
                continue
            if self.offers is not None and self.offers.trigger_of(tid):
                continue  # started from a trigger's offer: the trigger's, not a habit
            out.append(t)
        return out

    def money(self, task: dict[str, Any]) -> bool:
        if MONEY.search(task.get("goal") or "") or MONEY.search(task.get("request") or ""):
            return True
        return any(involves_money(a.get("description") or "", a.get("screen") or "") for a in self.tasks.approvals(task_id=task["id"]))

    def covered(self, routine: str | None, goal: str) -> bool:
        """A trigger already runs this (one you set up, or one a habit set up)."""
        for trig in self.tasks.triggers():
            a = trig.get("action") or {}
            if (routine and a.get("routine") == routine) or (not routine and a.get("goal") and norm_goal(a["goal"]) == norm_goal(goal)):
                return True
        return False

    # ---- finding patterns --------------------------------------------------------------------------

    def scan(self) -> list[dict[str, Any]]:
        """Offers for the patterns found now (none for keys already pending, declined or accepted)."""
        history = self.history()
        made = []
        groups: dict[str, list[dict[str, Any]]] = {}
        by_routine: dict[str, list[dict[str, Any]]] = {}
        for t in history:
            if t.get("routine"):
                inputs = {k: str(v).strip().lower() for k, v in sorted((t.get("inputs") or {}).items())}
                groups.setdefault(json.dumps(["r", t["routine"], inputs]), []).append(t)
                by_routine.setdefault(t["routine"], []).append(t)
            else:
                groups.setdefault(json.dumps(["g", norm_goal(t["goal"])]), []).append(t)
        for routine, ts in by_routine.items():
            if (p := self.before_trips(routine, ts)) and (o := self.propose(p)):
                made.append(o)
        for key, ts in groups.items():
            if (p := self.daily_pattern(key, ts) or self.weekly_pattern(key, ts)) and (o := self.propose(p)):
                made.append(o)
        return made

    def _one_per_day(self, ts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen, out = set(), []
        for t in sorted(ts, key=lambda x: x["created_at"]):
            d = datetime.fromtimestamp(t["created_at"]).date()
            if d not in seen:
                seen.add(d)
                out.append(t)
        return out

    def weekly_pattern(self, key: str, ts: list[dict[str, Any]]) -> dict[str, Any] | None:
        days = self._one_per_day(ts)
        for wd in range(7):
            same = [(t["created_at"], _minute(t["created_at"])) for t in days if datetime.fromtimestamp(t["created_at"]).weekday() == wd]
            if hit := _similar(same):
                at = _round(statistics.median(m for _, m in hit))
                day = DAYS[wd]
                return {"pattern": "weekly", "key": key, "tasks": ts, "times": [t for t, _ in hit], "minute": at,
                        "spec": {"weekly_on": {"days": [day], "at": f"{at // 60:02d}:{at % 60:02d}"}},
                        "when": f"every {DAY_NAMES[day]} at {_clock(at)}",
                        "evidence": f"on your last {len(hit)} {DAY_NAMES[day]}s ({_dates([t for t, _ in hit])}), around {_clock(at)}"}
        return None

    def daily_pattern(self, key: str, ts: list[dict[str, Any]]) -> dict[str, Any] | None:
        days = self._one_per_day(ts)
        run: list[dict[str, Any]] = []
        best: list[tuple[float, int]] | None = None
        for t in days + [None]:  # type: ignore[list-item]
            d = datetime.fromtimestamp(t["created_at"]).date() if t else None
            if t and run and d == datetime.fromtimestamp(run[-1]["created_at"]).date() + timedelta(days=1):
                run.append(t)
                continue
            if len(run) >= 3:  # a run of consecutive days: the longest stretch at a similar time
                for i in range(len(run)):
                    for j in range(len(run), i + 2, -1):
                        part = [(x["created_at"], _minute(x["created_at"])) for x in run[i:j]]
                        if len(_close(part)) == len(part) and (best is None or len(part) > len(best)):
                            best = part
                            break
            run = [t] if t else []
        if not best:
            return None
        at = _round(statistics.median(m for _, m in best))
        times = [t for t, _ in best]
        return {"pattern": "daily", "key": key, "tasks": ts, "times": times, "minute": at, "spec": {"daily_at": f"{at // 60:02d}:{at % 60:02d}"},
                "when": f"every day at {_clock(at)}", "evidence": f"{len(best)} days in a row ({_dates(times)}), around {_clock(at)}"}

    def before_trips(self, routine: str, ts: list[dict[str, Any]]) -> dict[str, Any] | None:
        """The routine ran within 48 h before 2 or more flights, with inputs each flight's own facts can fill."""
        if self.scheduler is None:
            return None
        hits: list[tuple[dict[str, Any], float, dict[str, str]]] = []  # (task, departure, the flight's values)
        for when, _eid, values in self.scheduler.occasions(FLIGHT):
            before = [t for t in ts if when - LEAD_S <= t["created_at"] < when]
            if before:
                hits.append((max(before, key=lambda t: t["created_at"]), when, values))
        if len(hits) < 2:
            return None
        inputs_from: dict[str, str] = {}
        fixed: dict[str, str] = {}
        for name in sorted({k for t, _, _ in hits for k in (t.get("inputs") or {})}):
            vals = [str((t.get("inputs") or {}).get(name, "")).strip().lower() for t, _, _ in hits]
            paths = None
            for (t, _, values), v in zip(hits, vals):
                here = {k.lower() for k, x in values.items() if str(x).strip().lower() == v and v}
                paths = here if paths is None else paths & here
            if paths:
                inputs_from[name] = sorted(paths, key=lambda p: (p != "trip.destination", p != "number", "." in p, p))[0]
            elif len(set(vals)) == 1:
                fixed[name] = str((hits[0][0].get("inputs") or {}).get(name, ""))
            else:
                return None  # an input that changes from trip to trip with nothing in memory to fill it
        lead = _round(statistics.median((w - t["created_at"]) / 60 for t, w, _ in hits), 30) or 30
        hours = f"{lead // 60} h" if lead % 60 == 0 else f"{lead / 60:.1f} h"
        times = [t["created_at"] for t, _, _ in hits]
        latest = max(hits, key=lambda h: h[0]["created_at"])
        return {"pattern": "before_fact", "key": json.dumps(["before", routine]), "tasks": [t for t, _, _ in hits], "times": times,
                "spec": {**FLIGHT, "minutes_before": lead}, "inputs_from": inputs_from, "inputs": fixed, "values": latest[2],
                "when": f"{hours} before every flight", "evidence": f"before your last {len(hits)} flights ({_dates(times)})"}

    # ---- the offer ------------------------------------------------------------------------------

    def propose(self, p: dict[str, Any]) -> dict[str, Any] | None:
        latest = max(p["tasks"], key=lambda t: t["created_at"])
        routine = latest.get("routine")
        key = "repeat:" + hashlib.sha256(p["key"].encode()).hexdigest()[:16]
        if any(o["status"] == "accepted" for o in self.offers.by_key(key)) or self.covered(routine, latest["goal"]):
            return None
        money = any(self.money(t) for t in p["tasks"])
        if p["pattern"] == "before_fact":
            tpl = template(latest, p["inputs_from"], p["values"])
            action = {"routine": routine, "inputs_from": p["inputs_from"], **({"inputs": p["inputs"]} if p["inputs"] else {}), "ask": True,
                      **({"goal": tpl} if tpl else {})}
            said = re.sub(r"\{([\w.]+)\}", lambda m: SLOT_WORDS.get(m.group(1).lower(), "the " + m.group(1).rsplit(".", 1)[-1].replace("_", " ")),
                          tpl) if tpl else (self._intent(routine) or latest["goal"])
        else:
            action = {"goal": latest["goal"], "ask": True}
            if routine:
                action.update(routine=routine, inputs=dict(latest.get("inputs") or {}))
            said = latest["goal"]
        question = _should_i(said)
        what = _to_you(said)
        did = f"asked “{what}?”" if question.startswith("Should I look this up") else f"asked me to {what}"
        body = f"You {did} {p['evidence']}." + (" It involves money, so it will always ask you first." if money else "")
        name = f"{p['when'][:1].upper()}{p['when'][1:]}: {what}"[:80]
        return self.offers.make(
            kind="repeat", title="Make this a habit?", body=body, source="repeats", key=key,
            action={"type": "create_trigger", "kind": "before_fact" if p["pattern"] == "before_fact" else "time", "name": name, "spec": p["spec"],
                    "action": action, "summary": f"{p['when'][:1].upper()}{p['when'][1:]}, I'll ask you: “{question}”",
                    "setup": f"asks you {p['when']}", "evidence": [_day(t) for t in sorted(p["times"])], "pattern": p["pattern"]})

    def _intent(self, routine: str | None) -> str | None:
        try:
            return self.routines.get(routine).intent if (self.routines is not None and routine) else None
        except Exception:  # noqa: BLE001
            return None


def template(task: dict[str, Any], inputs_from: dict[str, str], values: dict[str, str]) -> str | None:
    """Your own words with this trip's values as slots: "What's my gate for Chicago?" → "What's my gate for
    {trip.destination}?". None when a value can't be found in the words (the routine's intent is used instead)."""
    goal = task.get("goal") or ""
    for name, path in inputs_from.items():
        v = str((task.get("inputs") or {}).get(name) or "")
        if not v or not re.search(re.escape(v), goal, re.I):
            return None
        goal = re.sub(re.escape(v), "{" + path + "}", goal, count=1, flags=re.I)
    if (n := values.get("number")) and n in goal:
        goal = goal.replace(n, "{number}")  # the flight number is this trip's, not every trip's
    return goal


__all__ = ["Repeats", "norm_goal", "template", "WINDOW_DAYS"]
