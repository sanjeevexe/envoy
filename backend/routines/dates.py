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


# ---- a date or time input as an app shows it -------------------------------------------------------
# A request names a date or time one way ("October 27 2023", "8:00pm") and an app shows its parts another (a month grid's
# "27" under "October", a day view's "20:00 - 20:15"). A routine slot can name one part: {{event_date:day}} is the day of
# the month of whatever date the input holds on this run (routines/model.py renders it with `formatted`).

_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
_MONTH = r"(" + "|".join(m[:3] + rf"(?:{m[3:]})?" for m in _MONTHS) + r")\.?"
_DATE_MDY = re.compile(rf"^(?:\w+,?\s+)??{_MONTH}\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?\b", re.I)
_DATE_DMY = re.compile(rf"^(?:\w+,?\s+)??(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTH}(?:,?\s+(\d{{4}}))?\b", re.I)
_DATE_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})\b")
_DATE_US = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})\b")
_TIME = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*(h\b|hrs?\b|o'?clock|[ap]\.?m\.?)?$", re.I)

# The parts a slot can name, most specific first (the compiler binds a longer one before a shorter one inside it).
DATE_PARTS = ("iso", "month", "mon", "year", "day")
TIME_PARTS = ("time24",)


def parse_date(value: str) -> tuple[int | None, int, int] | None:
    """(year or None, month, day) of a date written as people and apps write them, else None."""
    v = " ".join((value or "").split())
    if m := _DATE_ISO.match(v):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    elif m := _DATE_US.match(v):
        mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    elif m := _DATE_MDY.match(v):
        mo, d, y = _month(m.group(1)), int(m.group(2)), int(m.group(3)) if m.group(3) else None
    elif m := _DATE_DMY.match(v):
        d, mo, y = int(m.group(1)), _month(m.group(2)), int(m.group(3)) if m.group(3) else None
    else:
        return None
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return y, mo, d


def _month(s: str) -> int:
    return next(i for i, m in enumerate(_MONTHS, 1) if m.startswith(s.casefold()[:3]))


def parse_time(value: str) -> tuple[int, int] | None:
    """(hour, minute) of a time ("8:00pm", "8 pm", "20:00", "17h"), else None. A bare number is not a time."""
    m = _TIME.match(" ".join((value or "").split()))
    if m is None or not (m.group(2) or m.group(3)):
        return None
    hour, minute, suffix = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower().replace(".", "")
    if suffix.startswith("pm") and hour < 12:
        hour += 12
    elif suffix.startswith("am") and hour == 12:
        hour = 0
    return (hour, minute) if hour < 24 and minute < 60 else None


def formatted(value: str, part: str) -> str | None:
    """One part of a date or time input, the way apps show it: day "27", month "October", mon "Oct", year "2023", iso
    "2023-10-27", time24 "20:00". None when the value isn't a date (or time) or lacks that part."""
    if part in TIME_PARTS:
        t = parse_time(value)
        return f"{t[0]:02d}:{t[1]:02d}" if t else None
    d = parse_date(value)
    if d is None:
        return None
    y, mo, day = d
    if part == "day":
        return str(day)
    if part == "month":
        return _MONTHS[mo - 1].capitalize()
    if part == "mon":
        return _MONTHS[mo - 1][:3].capitalize()
    if part == "year":
        return str(y) if y else None
    if part == "iso":
        return f"{y:04d}-{mo:02d}-{day:02d}" if y else None
    return None


def parts(value: str) -> dict[str, str]:
    """Every part of a date or time input that `formatted` can give, keyed by part name ({} for other values)."""
    return {p: f for p in (*DATE_PARTS, *TIME_PARTS) if (f := formatted(value, p))}
