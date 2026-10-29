"""Dates and times a request names without writing them: "tomorrow", "this Thursday", "in two weeks", "at 17h ... for 30 mins".

A routine's input is a value ("16", "2023-10-16", "17:30"), but a request often says when relative to the phone's date or
as a start plus a duration. The matcher keeps only values it can find in the request or the notes, so it can't take one
the model worked out itself. These facts are worked out here, in code, from the phone's date: the model sees them and
picks a value in the input's format, and the matcher keeps it because it is in a fact (routines/matcher.py).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
            "ten": 10, "eleven": 11, "twelve": 12}
_N = r"(\d{1,3}|" + "|".join(_NUMBERS) + r")"
_UNIT_DAYS = {"day": 1, "week": 7}

_FIXED = [(re.compile(r"\bday after tomorrow\b"), 2), (re.compile(r"\btomorrow\b"), 1), (re.compile(r"\byesterday\b"), -1),
          (re.compile(r"\btoday\b"), 0), (re.compile(r"\bnext week\b"), 7)]
_IN = re.compile(rf"\bin {_N} (day|week)s?\b|\b{_N} (day|week)s? (?:from (?:today|now)|later)\b")
_WEEKDAY = re.compile(r"\b(?:this|on|coming|this coming) (" + "|".join(_WEEKDAYS) + r")\b")
_START = re.compile(r"\bat (\d{1,2})(?::(\d{2}))?\s*(h\b|hrs?\b|o'?clock|[ap]\.?m\b\.?)?", re.I)
_DURATION = re.compile(rf"\b(?:lasts?|lasting|for)\s+(?:for\s+)?{_N}\s*(minutes?|mins?|hours?|hrs?)\b", re.I)


def _num(s: str) -> int:
    return int(s) if s.isdigit() else _NUMBERS[s.lower()]


def _day(phrase: str, d: date) -> str:
    return f"{phrase!r} is {d:%A}, {d:%B} {d.day}, {d.year} ({d.isoformat()}; day {d.day} of the month)"


def facts(request: str, today: date) -> list[str]:
    """Each date or time the request implies, worked out from `today` (the phone's date). The first fact is today."""
    text = " ".join(request.split()).casefold()
    out = [_day("today", today)]
    seen: set[str] = {"today"}
    for pattern, days in _FIXED:
        for m in pattern.finditer(text):
            if m.group(0) not in seen:
                seen.add(m.group(0))
                out.append(_day(m.group(0), today + timedelta(days=days)))
    for m in _IN.finditer(text):
        n, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        if m.group(0) not in seen:
            seen.add(m.group(0))
            out.append(_day(m.group(0), today + timedelta(days=_num(n) * _UNIT_DAYS[unit])))
    for m in _WEEKDAY.finditer(text):
        ahead = (_WEEKDAYS.index(m.group(1)) - today.weekday()) % 7  # the coming one; today if it is that day
        if m.group(0) not in seen:
            seen.add(m.group(0))
            out.append(_day(m.group(0), today + timedelta(days=ahead)))
    # A start time and how long it lasts: when it ends (an end-time picker needs it).
    starts, durations = list(_START.finditer(request)), list(_DURATION.finditer(request))
    if len(starts) == 1 and (starts[0].group(2) or starts[0].group(3)):  # "at 17h", "at 5 pm", "at 13:00", not "at 3 stores"
        s = starts[0]
        hour, minute, suffix = int(s.group(1)), int(s.group(2) or 0), (s.group(3) or "").lower().replace(".", "")
        if suffix.startswith("pm") and hour < 12:
            hour += 12
        elif suffix.startswith("am") and hour == 12:
            hour = 0
        if hour < 24 and minute < 60:
            start = datetime.combine(today, datetime.min.time()).replace(hour=hour, minute=minute)
            line = f"{s.group(0).strip()!r} starts at {start:%H:%M}"
            if len(durations) == 1:
                n, unit = _num(durations[0].group(1)), durations[0].group(2).lower()
                end = start + timedelta(minutes=n * (60 if unit.startswith("h") else 1))
                later = " the next day" if end.date() != start.date() else ""
                line += f" and, lasting {durations[0].group(0).split(None, 1)[-1].removeprefix('for ').strip()}, ends at {end:%H:%M}{later}"
            out.append(line)
    return out
