"""SkyLark routine task families: one goal shape, many bookings.

Routines are compiled from one agent run on one booking (the Denver trip, with check-in opened) and
then replayed on bookings they have never seen. New bookings are generated from a seed and seeded
into SkyLark through its fixtures hook, below the Home screen's "Next trip" (Chicago), so a routine
that silently used "the first card" instead of the requested trip would act on the wrong trip, and
the state check would catch it.
"""

from __future__ import annotations

import copy
import random
import string
from dataclasses import dataclass, field
from typing import Any, Callable

from testapps.skylark import default_fixtures

COMPILE_CODE = "PT4R8Z"  # Denver, SL 1190: the booking the source runs use
CHICAGO = "KX7Q2M"

_CITIES = [
    ("Dallas", "DFW"), ("Portland", "PDX"), ("Raleigh", "RDU"), ("Tampa", "TPA"), ("Minneapolis", "MSP"), ("Savannah", "SAV"),
    ("Pittsburgh", "PIT"), ("Omaha", "OMA"), ("Tucson", "TUS"), ("Boise", "BOI"), ("Richmond", "RIC"), ("Memphis", "MEM"),
    ("Albuquerque", "ABQ"), ("Spokane", "GEG"), ("Buffalo", "BUF"), ("Louisville", "SDF"), ("Sacramento", "SMF"), ("Madison", "MSN"),
]
_DATES = ["Mon, Nov 16, 2026", "Thu, Nov 19, 2026", "Sun, Nov 22, 2026", "Wed, Nov 25, 2026", "Tue, Dec 1, 2026", "Fri, Dec 4, 2026",
          "Mon, Dec 7, 2026", "Thu, Dec 10, 2026"]
_TIMES = ["6:00 AM", "7:35 AM", "9:20 AM", "11:05 AM", "12:40 PM", "2:15 PM", "3:50 PM", "5:25 PM", "7:10 PM"]


@dataclass
class Booking:
    code: str
    city: str
    airport: str
    number: str
    date: str
    depart: str
    arrive: str
    gate: str
    seat: str
    boarding: str
    group: str
    status: str = "On time"
    ktn: str = ""  # the known traveler number memory holds for this request
    new_seat: str = ""  # a free seat to change to

    def trip(self) -> dict[str, Any]:
        return {"code": self.code, "city": self.city, "upcoming": True, "checkin_open": True, "checked_in": False, "cancelled": False,
                "ktn": "", "bags": 0, "flight": {"number": self.number, "from": "ATL", "to": self.airport, "date": self.date,
                                                 "depart": self.depart, "arrive": self.arrive, "gate": self.gate, "seat": self.seat,
                                                 "boarding": self.boarding, "group": self.group, "status": self.status}}

    def fields(self) -> dict[str, str]:
        """Every value a routine input could be bound to (matched by the compiled input's example)."""
        return {"city": self.city, "code": self.code, "number": self.number, "airport": self.airport, "seat": self.seat,
                "new_seat": self.new_seat, "ktn": self.ktn, "last_name": "Patel", "gate": self.gate, "date": self.date}


def _free_seats(fx: dict[str, Any], taken: set[str]) -> list[str]:
    sm = fx["seatmap"]
    out = []
    for row in range(sm["first_row"], sm["last_row"] + 1):
        if row in sm["paid_rows"]:
            continue
        for letter in "ABCDEF":
            s = f"{row}{letter}"
            if s not in sm["occupied"] and s not in taken:
                out.append(s)
    return out


def booking_from_trip(t: dict[str, Any], ktn: str = "", new_seat: str = "") -> Booking:
    f = t["flight"]
    return Booking(code=t["code"], city=t["city"], airport=f["to"], number=f["number"], date=f["date"], depart=f["depart"], arrive=f["arrive"],
                   gate=f["gate"], seat=f["seat"], boarding=f["boarding"], group=f["group"], status=f["status"], ktn=ktn, new_seat=new_seat)


def generate(seed: int, n: int) -> list[Booking]:
    """n new bookings, deterministic for a seed, with codes, cities, flights, seats and gates SkyLark has never shown."""
    rng = random.Random(seed)
    fx = default_fixtures()
    used_codes = {t["code"] for t in fx["trips"]}
    taken = {t["flight"]["seat"] for t in fx["trips"]}
    cities = rng.sample(_CITIES, n)
    out = []
    for city, airport in cities:
        code = "".join(rng.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        while code in used_codes or not any(c.isalpha() for c in code):
            code = "".join(rng.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        used_codes.add(code)
        free = _free_seats(fx, taken)
        seat = rng.choice(free)
        taken.add(seat)
        new_seat = rng.choice([s for s in _free_seats(fx, taken) if s != seat])
        taken.add(new_seat)
        t1, t2 = sorted(rng.sample(range(len(_TIMES)), 2))
        out.append(Booking(code=code, city=city, airport=airport, number=f"SL {rng.randint(100, 1999)}", date=rng.choice(_DATES),
                           depart=_TIMES[t1], arrive=_TIMES[t2], gate=f"{rng.choice('ABCDE')}{rng.randint(1, 30)}", seat=seat,
                           boarding=_TIMES[max(0, t1 - 1)], group=str(rng.randint(1, 6)), ktn=str(rng.randint(10_000_000, 99_999_999)),
                           new_seat=new_seat))
    return out


def fixtures(extra: list[Booking] | None = None) -> dict[str, Any]:
    """Default fixtures, Denver's check-in opened, and extra upcoming bookings after Denver (below Home's next trip)."""
    fx = copy.deepcopy(default_fixtures())
    for t in fx["trips"]:
        if t["code"] == COMPILE_CODE:
            t["checkin_open"] = True
    if extra:
        i = next(k for k, t in enumerate(fx["trips"]) if t["code"] == COMPILE_CODE) + 1
        fx["trips"][i:i] = [b.trip() for b in extra]
    return fx


def compile_booking() -> Booking:
    fx = fixtures()
    t = next(t for t in fx["trips"] if t["code"] == COMPILE_CODE)
    return booking_from_trip(t, ktn="55501234", new_seat="21C")


def chicago_booking() -> Booking:
    fx = fixtures()
    t = next(t for t in fx["trips"] if t["code"] == CHICAGO)
    return booking_from_trip(t, ktn="98765432", new_seat="20B")


def _trip(state: dict[str, Any], code: str) -> dict[str, Any]:
    return next(t for t in state["trips"] if t["code"] == code)


def _others_untouched(state: dict[str, Any], code: str, key: str, before: dict[str, Any]) -> bool:
    """No other trip changed: a routine that acted on the wrong booking must fail."""
    for t in state["trips"]:
        if t["code"] != code:
            b = next(x for x in before["trips"] if x["code"] == t["code"])
            if (t.get(key) if key != "seat" else t["flight"]["seat"]) != (b.get(key) if key != "seat" else b["flight"]["seat"]):
                return False
    return True


@dataclass
class Family:
    """A kind of request whose routine takes the booking (and maybe more) as input."""

    id: str
    goal: Callable[[Booking], str]
    memory: Callable[[Booking], str]
    check: Callable[[dict[str, Any], dict[str, Any], Booking, dict[str, str | None], str], bool]  # (state, state_before, booking, outputs, answer)
    source_task: str | None = None  # an existing trace to compile instead of a fresh agent run
    outputs_expected: Callable[[Booking], dict[str, str]] = field(default=lambda b: {})


def _outputs_ok(outputs: dict[str, str | None], expected: dict[str, str]) -> bool:
    flat = " ".join(v or "" for v in outputs.values()).casefold()
    return all(v.casefold() in flat for v in expected.values())


def _answer_ok(answer: str, outputs: dict[str, str | None], needle: str) -> bool:
    return needle.casefold() in (answer + " " + " ".join(v or "" for v in outputs.values())).casefold()


FAMILIES: list[Family] = [
    Family("check_in", lambda b: f"Check me in for my flight to {b.city}.", lambda b: "",
           lambda s, s0, b, o, a: _trip(s, b.code)["checked_in"] and _others_untouched(s, b.code, "checked_in", s0)),
    Family("change_seat", lambda b: f"Change my seat on my {b.city} flight to {b.new_seat}.", lambda b: "",
           lambda s, s0, b, o, a: _trip(s, b.code)["flight"]["seat"] == b.new_seat and _others_untouched(s, b.code, "seat", s0)),
    Family("add_ktn", lambda b: f"Add my known traveler number to my {b.city} trip.", lambda b: f"Known traveler number: {b.ktn}",
           lambda s, s0, b, o, a: _trip(s, b.code)["ktn"] == b.ktn and _others_untouched(s, b.code, "ktn", s0)),
    Family("gate", lambda b: f"What gate does my {b.city} flight leave from?", lambda b: "",
           lambda s, s0, b, o, a: _answer_ok(a, o, b.gate)),
    Family("flight_status", lambda b: f"What's the status of SkyLark flight {b.number}?", lambda b: "",
           lambda s, s0, b, o, a: _answer_ok(a, o, b.status.split()[0])),
    Family("find_trip", lambda b: f"Look up my trip with confirmation code {b.code} and tell me where it goes.", lambda b: "Last name: Patel",
           lambda s, s0, b, o, a: _answer_ok(a, o, b.city) or _answer_ok(a, o, b.airport)),
]
BY_ID = {f.id: f for f in FAMILIES}
