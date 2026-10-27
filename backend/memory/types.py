"""Entity types, their attributes and natural keys, freshness, and source reliability (design doc, Shared memory).

Types are declared up front so extraction, matching and retrieval all agree on names. Natural keys
recognize the same thing twice without a model (a reservation's confirmation code; a flight's airline,
number and date). Freshness says how long an observed value can be served without re-checking.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

ENTITY_TYPES = (
    "Person", "Trip", "Flight", "Reservation", "Order", "Item", "Place", "App", "Account", "Loyalty program",
    "Subscription", "Event", "Preference", "Note", "Routine", "Task",
)


@dataclass(frozen=True)
class TypeSpec:
    name: str
    attributes: tuple[str, ...]
    keys: tuple[tuple[str, ...], ...] = ()  # each tuple is one natural key (all its attributes must agree)
    title: tuple[str, ...] = ()  # attributes that make the entity's display name, in order


TYPES: dict[str, TypeSpec] = {t.name: t for t in [
    TypeSpec("Trip", ("destination", "origin", "start_date", "end_date", "confirmation_code", "status", "checked_in", "airline"),
             keys=(("confirmation_code",),), title=("destination", "start_date")),
    TypeSpec("Flight", ("airline", "number", "date", "from", "to", "depart_time", "arrive_time", "gate", "seat", "boarding_time",
                        "boarding_group", "status", "terminal", "confirmation_code"),
             keys=(("number", "date"),), title=("number", "date")),
    TypeSpec("Person", ("name", "first_name", "last_name", "email", "phone", "known_traveler_number"),
             keys=(("email",),), title=("name",)),
    TypeSpec("Loyalty program", ("program", "member_number", "tier", "miles"), keys=(("program", "member_number"),), title=("program",)),
    TypeSpec("Reservation", ("kind", "name", "confirmation_code", "start_date", "end_date", "address", "status"),
             keys=(("confirmation_code",),), title=("name", "start_date")),
    TypeSpec("Order", ("merchant", "order_number", "total", "status", "delivery_eta", "placed_at"),
             keys=(("merchant", "order_number"),), title=("merchant", "order_number")),
    TypeSpec("Item", ("name", "price", "merchant"), title=("name",)),
    TypeSpec("Place", ("name", "address", "city"), title=("name",)),
    TypeSpec("App", ("name", "package"), keys=(("package",),), title=("name",)),
    TypeSpec("Account", ("service", "username"), title=("service",)),
    TypeSpec("Subscription", ("service", "plan", "renews_at", "price"), title=("service",)),
    TypeSpec("Event", ("title", "start", "end", "location"), title=("title", "start")),
    TypeSpec("Preference", ("text",), title=("text",)),
    TypeSpec("Note", ("body",), title=("body",)),
    TypeSpec("Routine", ("name", "app", "version"), keys=(("name",),), title=("name",)),
    TypeSpec("Task", ("goal", "status"), title=("goal",)),
]}

# Freshness: how long an observed value may be served as current (seconds). None = until replaced.
FRESHNESS: dict[tuple[str, str], int] = {
    ("Flight", "gate"): 30 * 60,
    ("Flight", "status"): 30 * 60,
    ("Flight", "boarding_time"): 6 * 3600,
    ("Order", "delivery_eta"): 10 * 60,
    ("Order", "status"): 30 * 60,
    ("Loyalty program", "miles"): 7 * 86400,
}

# How much a source kind is trusted (an app screen ranks above an email, which ranks above a photo's text).
SOURCE_RELIABILITY = {"user": 1.0, "app_screen": 0.95, "routine_run": 0.95, "email_markup": 0.9, "calendar": 0.9,
                      "email": 0.8, "agent_answer": 0.85, "client": 0.8, "photo": 0.7}

# Output and input names that mean an attribute (routine outputs: "departure_gate" → gate).
ATTRIBUTE_SYNONYMS = {
    "departure_gate": "gate", "gate_number": "gate", "seat_number": "seat", "new_seat": "seat", "desired_seat": "seat",
    "boarding": "boarding_time", "boarding_group_number": "boarding_group", "flight_status": "status", "flight_number": "number",
    "departure_time": "depart_time", "arrival_time": "arrive_time", "destination_city": "destination", "trip_city": "destination",
    "city": "destination", "confirmation": "confirmation_code", "trip_confirmation_code": "confirmation_code",
    "user_known_traveler_number": "known_traveler_number", "ktn": "known_traveler_number", "check_in_status": "checked_in",
}

# Where routine inputs come from (`from_memory` hints) → (entity type, attribute).
MEMORY_PATHS = {
    "trip.city": ("Trip", "destination"), "trip.destination": ("Trip", "destination"), "trip.confirmation_code": ("Trip", "confirmation_code"),
    "flight.number": ("Flight", "number"), "flight.flight_number": ("Flight", "number"), "trip.flight_number": ("Flight", "number"),
    "user.last_name": ("Person", "last_name"), "user.first_name": ("Person", "first_name"), "user.name": ("Person", "name"),
    "user.known_traveler_number": ("Person", "known_traveler_number"), "user.ktn": ("Person", "known_traveler_number"),
}


def canonical_attribute(name: str) -> str:
    n = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
    return ATTRIBUTE_SYNONYMS.get(n, n)


# ---- normalizing values for keys ----------------------------------------------------------------

_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def parse_date(s: str | None, default_year: int = 2026) -> date | None:
    """Dates as apps and emails write them: 'Sat, Nov 14, 2026', 'Nov 14', '2026-11-14', '11/14/2026', ISO datetimes."""
    if not s:
        return None
    t = s.strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", t)
    if m:
        y = int(m.group(3))
        return date(y + 2000 if y < 100 else y, int(m.group(1)), int(m.group(2)))
    m = re.search(r"\b([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2})(?!\d)(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?", t)
    if m and m.group(1).casefold() in _MONTHS:
        return date(int(m.group(3) or default_year), _MONTHS[m.group(1).casefold()], int(m.group(2)))
    m = re.search(r"\b(\d{1,2})\s+([A-Za-z]{3})[a-z]*\.?(?:\s+(\d{4}))?", t)
    if m and m.group(2).casefold() in _MONTHS:
        return date(int(m.group(3) or default_year), _MONTHS[m.group(2).casefold()], int(m.group(1)))
    return None


def normalize_key_value(attribute: str, value: str) -> str:
    """A form of the value that compares equal across sources ('SL1190' = 'SL 1190'; 'Sat, Nov 14, 2026' = '2026-11-14')."""
    v = (value or "").strip()
    if attribute in ("date", "start_date", "end_date"):
        d = parse_date(v)
        return d.isoformat() if d else v.casefold()
    if attribute in ("number", "confirmation_code", "order_number", "member_number"):
        return re.sub(r"[^0-9A-Za-z]", "", v).upper()
    if attribute == "email":
        return v.casefold()
    if attribute in ("from", "to"):
        m = re.search(r"\(([A-Z]{3})\)|^([A-Z]{3})$", v)  # "Atlanta (ATL)" = "ATL"
        if m:
            return (m.group(1) or m.group(2)).upper()
    if attribute.endswith("_time"):
        m = re.match(r"(\d{1,2}):(\d{2})\s*([AaPp])\.?[Mm]?", v)
        if m:
            h = int(m.group(1)) % 12 + (12 if m.group(3).lower() == "p" else 0)
            return f"{h:02d}:{m.group(2)}"
    return " ".join(v.split()).casefold()


def to_epoch(dt: datetime | date | float | None) -> float | None:
    if dt is None:
        return None
    if isinstance(dt, (int, float)):
        return float(dt)
    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime(dt.year, dt.month, dt.day)
    return dt.timestamp()


@dataclass
class Observation:
    """One attribute value seen in one source, before it is stored."""

    attribute: str
    value: str
    evidence: str = ""  # where in the source it was read (an element's label, a markup path)


@dataclass
class ExtractedEntity:
    """An entity as one source describes it: its type, attribute values and links to others in the same source."""

    type: str
    observations: list[Observation] = field(default_factory=list)
    local_id: str = ""
    links: list[tuple[str, str]] = field(default_factory=list)  # (relation, other local_id)

    def get(self, attribute: str) -> str | None:
        return next((o.value for o in self.observations if o.attribute == attribute and o.value), None)

    def key_values(self) -> list[tuple[str, ...]]:
        spec = TYPES.get(self.type)
        out = []
        for key in spec.keys if spec else ():
            vals = [self.get(a) for a in key]
            if all(vals):
                out.append(tuple(normalize_key_value(a, v) for a, v in zip(key, vals)))  # type: ignore[arg-type]
        return out
