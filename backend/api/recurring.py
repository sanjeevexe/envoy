"""Chat sets up recurring jobs: "Every Friday at 6 PM, order my usual from Thai Basil" becomes a trigger, switched off,
with an offer asking "Set this up? Every Friday at 6:00 PM: order your usual from Thai Basil".

1. **Code first.** Only a message with schedule words ("every", "each", "daily", "weekly", "whenever", "when … changes",
   "remind me", "before my …", "on Fridays") goes further (`may_schedule`, no model call). Every other message takes
   chat's path exactly as before.
2. **One Muse Spark call** (standard tier, structured output, its own prompt here) drafts the job: is it recurring, its
   kind, when, and the goal. Not recurring: chat goes on as before.
3. **Code checks the draft.** The goal must be the user's own words: every word of it is in the message (a few small
   words aside), or nothing is set up. An email trigger's sender and subject words must be in the message too. The
   schedule goes through `scheduler.add`'s own validation. The model never decides what runs beyond the words you typed.
4. **Nothing runs until you say yes.** The trigger is created switched off (`enabled=False`) and in ask mode, so even once
   it's on, each run asks you first ("Should I order your usual from Thai Basil?"), the way an AI client's
   `create_trigger` and a learned habit do. The offer (kind `trigger_request`, action `enable_trigger`) shows when and
   what, verbatim; only your yes in Envoy's own app turns it on.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Any, Literal

from models.adapter import JobConfig
from models.schemas import _Strict
from pydantic import Field

from api.alerts import label
from api.scheduler import DAYS, _should_i, _to_you, parse_clock

SCHEDULE = re.compile(
    r"\b(every|each|daily|weekly|nightly|hourly|weekdays|weekends|whenever|remind me"
    r"|on (?:mondays|tuesdays|wednesdays|thursdays|fridays|saturdays|sundays))\b"
    r"|\bwhen\b[^.?!]{0,80}\bchanges?\b|\bbefore (?:my|each|every|all) \w+", re.I)
DAY_NAMES = {"mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday", "fri": "Friday", "sat": "Saturday", "sun": "Sunday"}
ATTRIBUTES = ("gate", "depart_time", "arrive_time", "boarding_time", "seat", "terminal", "status")
# Words a goal may add to the message's own: "check me in before every flight" → "Check me in for my flight".
SMALL = {"a", "an", "the", "my", "me", "i", "to", "for", "of", "on", "in", "at", "and", "it", "is", "its", "please", "s"}
MIN_EVERY = 15  # minutes: a job that asks you each time shouldn't ask more often than this


def may_schedule(message: str) -> bool:
    """Code only, no model call: does the message talk about doing something again and again?"""
    return SCHEDULE.search(message or "") is not None


class Draft(_Strict):
    recurring: bool = Field(description="True only if the message asks Envoy to do something again and again: on a schedule, before every flight, "
                                        "whenever an email arrives, or whenever a flight detail changes")
    kind: Literal["time", "before_fact", "email", "fact_changed"] = Field(description="What starts it each time")
    name: str = Field(description="A short name for the job, from the message, at most 6 words; empty if not recurring")
    days: list[Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]] = Field(description="time: the weekdays it names; empty for every day")
    time_of_day: str = Field(description="time: 24-hour HH:MM, e.g. 18:00; empty if every_minutes or not time")
    every_minutes: int = Field(description="time: only for 'every N minutes/hours' (2 hours = 120); else 0")
    minutes_before: int = Field(description="before_fact: minutes before each flight departs (24 hours = 1440; 1440 if not said); else 0")
    sender_contains: str = Field(description="email: a word from the message the sender must contain, e.g. skylark; else empty")
    subject_contains: str = Field(description="email: words from the message the subject must contain; else empty")
    attribute: str = Field(description=f"fact_changed: one of {', '.join(ATTRIBUTES)}; else empty")
    goal: str = Field(description="What to do each time: one instruction in the user's own words, copied from the message without the schedule words")


RECURRING_JOB = JobConfig("recurring", "muse-spark-1.3", "low", Draft, max_output_tokens=2000)
RECURRING_INSTRUCTIONS = """You turn a chat message into a draft of a recurring job for Envoy, an assistant that does tasks in the user's phone apps.

Set recurring=true only if the message asks Envoy to do something again and again: on a schedule (every day, every Friday at 6 PM, every 2 hours), before every flight, whenever an email arrives from someone, or whenever a remembered flight detail changes. A one-time request (even "before my flight tomorrow"), a question, or anything that isn't a task in a phone app: recurring=false, and leave the other fields empty.

kind:
- time: on a schedule. days: the weekdays it names (empty for every day; mon-fri for weekdays). time_of_day: 24-hour HH:MM ("6 PM" is 18:00, "morning" with no time is 08:00). every_minutes: only for "every N minutes" or "every N hours", else 0.
- before_fact: before every flight. minutes_before: how long before departure (1440 if not said).
- email: whenever an email arrives. sender_contains and subject_contains: words copied from the message.
- fact_changed: whenever a flight detail changes. attribute: the detail.

goal: what to do each time, as one instruction in the user's own words, copied from the message without the schedule words: "Order my usual from Thai Basil" from "Every Friday at 6 PM, order my usual from Thai Basil". Never add apps, amounts, names or details the message doesn't say.
name: a short name for the job, from the message.
Fields that don't apply: empty string, empty list or 0."""


def _words(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (s or "").lower().replace("’", "'").replace("'", " ")))


def own_words(goal: str, message: str) -> bool:
    """Every word of the goal is in the message (a few small words aside): the model only cut the schedule away."""
    extra = _words(goal) - _words(message) - SMALL
    return bool(_words(goal) - SMALL) and not extra


def _clock(at: str) -> str:
    h, m = parse_clock(at) or (0, 0)
    return f"{(h % 12) or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def when(kind: str, spec: dict[str, Any]) -> str:
    """When a trigger runs, in words: "every Friday at 6:00 PM", "24 h before every flight"."""
    if kind == "time":
        if spec.get("every_minutes"):
            n = int(spec["every_minutes"])
            return "every hour" if n == 60 else f"every {n // 60} hours" if n % 60 == 0 else f"every {n} minutes"
        if w := spec.get("weekly_on"):
            days = w["days"]
            names = "weekday" if days == ["mon", "tue", "wed", "thu", "fri"] else " and ".join(DAY_NAMES[d] for d in days)
            return f"every {names} at {_clock(w['at'])}"
        return f"every day at {_clock(spec.get('daily_at', ''))}"
    if kind == "before_fact":
        m = int(spec.get("minutes_before", 1440))
        return f"{m // 60} h before every flight" if m % 60 == 0 else f"{m} minutes before every flight"
    if kind == "email":
        who = f" from “{spec['sender_contains']}”" if spec.get("sender_contains") else ""
        about = f" about “{spec['subject_contains']}”" if spec.get("subject_contains") else ""
        return f"whenever an email{who}{about} arrives"
    if kind == "fact_changed":
        return f"whenever your flight's {' or '.join(label(a).lower() for a in spec.get('attributes') or [])} changes"
    return kind


class Recurring:
    def __init__(self, offers: Any, scheduler: Any, adapter: Any, clock: Any = None) -> None:
        self.offers, self.scheduler, self.adapter = offers, scheduler, adapter
        self.clock = clock or (lambda: datetime.now())

    async def propose(self, message: str, source: str = "chat") -> tuple[dict[str, Any] | None, int, float]:
        """(chat's reply, or None to go on as before; model calls; their cost at standard prices). One Spark call."""
        now = self.clock()
        content = f"REQUEST: {message}\n\nNOW: {now.strftime('%A %Y-%m-%d %H:%M')}\n"
        res = await asyncio.to_thread(self.adapter.call, RECURRING_JOB, content, instructions=RECURRING_INSTRUCTIONS, data_scope="real",
                                      task_id="chat-recurring")
        cost = float(getattr(res, "cost_at_standard_usd", 0) or 0)
        d: Draft | None = res.parsed
        if d is None or not d.recurring:
            return None, 1, cost
        out = {"kind": "trigger_request", "model_calls": 1, "cost_usd": round(cost, 5)}
        goal = re.sub(r"\s+", " ", d.goal or "").strip().rstrip(".")
        if not own_words(goal, message):
            why = "I couldn't tell exactly what to do each time"
            out.update(reply=f"{why}. Try it like this: “Every Friday at 6 PM, order my usual from Thai Basil.”", spoken=f"{why}.", draft_rejected="goal")
            return out, 1, cost
        try:
            kind, spec = self.spec(d, message)
            trig = self.scheduler.add(kind, _name(d.name, goal), spec, {"goal": goal, "ask": True}, enabled=False)
        except (ValueError, KeyError) as e:
            out.update(reply=f"I couldn't set that up: {e}.", spoken="I couldn't set that up.", draft_rejected=str(e)[:200])
            return out, 1, cost
        w, what = when(trig["kind"], trig["spec"]), _to_you(goal)
        offer = self.offers.make(
            kind="trigger_request", title=f"Set this up? {w[:1].upper()}{w[1:]}: {what}",
            body="It stays off until you say yes, and each time it runs I'll ask you first.", source=source, key=f"trigger_request:{trig['id']}",
            action={"type": "enable_trigger", "trigger_id": trig["id"], "summary": f"{w[:1].upper()}{w[1:]}, I'll ask you: “{_should_i(goal)}”",
                    "setup": f"asks you {w}"})
        out.update(reply=f"I can do that: {w}, {what}. It's off until you say yes below, and each time it runs I'll ask you first.",
                   spoken="I've drafted it. Say yes on the card to turn it on.", offer=offer, trigger=trig)
        return out, 1, cost

    def spec(self, d: Draft, message: str) -> tuple[str, dict[str, Any]]:
        """The draft as a trigger spec; scheduler.add validates the rest."""
        if d.kind == "time":
            if d.every_minutes:
                if d.every_minutes < MIN_EVERY:
                    raise ValueError(f"that's more often than every {MIN_EVERY} minutes")
                return "time", {"every_minutes": int(d.every_minutes)}
            if parse_clock(d.time_of_day) is None:
                raise ValueError("it needs a time of day")
            hm = parse_clock(d.time_of_day)
            at = f"{hm[0]:02d}:{hm[1]:02d}"  # type: ignore[index]
            if d.days and set(d.days) != set(DAYS):
                return "time", {"weekly_on": {"days": list(d.days), "at": at}}
            return "time", {"daily_at": at}
        if d.kind == "before_fact":
            return "before_fact", {"entity_type": "Flight", "date_attr": "date", "time_attr": "depart_time", "minutes_before": int(d.minutes_before or 1440)}
        if d.kind == "email":
            spec = {k: v.strip() for k, v in (("sender_contains", d.sender_contains), ("subject_contains", d.subject_contains)) if v and v.strip()}
            if not spec:
                raise ValueError("it needs who the email is from, or what it's about")
            for v in spec.values():
                if v.lower() not in message.lower():
                    raise ValueError(f"“{v}” isn't in what you wrote")
            return "email", spec
        if d.kind == "fact_changed":
            if d.attribute not in ATTRIBUTES:
                raise ValueError("it needs which flight detail to watch")
            return "fact_changed", {"entity_type": "Flight", "attributes": [d.attribute]}
        raise ValueError(f"unknown kind {d.kind!r}")


def _name(name: str, goal: str) -> str:
    n = re.sub(r"[\r\n\t{}<>]", " ", name or "").strip()[:60]
    return n or goal[:60]


__all__ = ["Recurring", "may_schedule", "own_words", "when", "RECURRING_JOB", "Draft"]
