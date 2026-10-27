"""Getting facts in (design doc, Shared memory › Getting facts in).

- Emails with schema.org markup (`FlightReservation`, `LodgingReservation`, `Order`) are parsed in code,
  with no model call.
- Other emails and app screens go to Muse Spark with the entity types (structured output). Every value
  must appear in the source as written, so a value the model made up is dropped, not stored.
- Routine outputs (seat, gate, boarding time) are written directly: the routine's checks already proved
  where they were read.
Screens and emails are redacted first; their text is data, never instructions.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from devices.types import ScreenState
from integrations.mail import Email
from memory.redact import redact_text, screen_text
from memory.types import TYPES, ExtractedEntity, Observation, canonical_attribute, memory_path
from models.adapter import DataScope, ModelAdapter
from models.prompts import extract_input, extract_instructions
from models.schemas import ExtractionOutput
from routines.screens import norm

_LD = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)
MAX_SOURCE_CHARS = 6000


@dataclass
class Extraction:
    entities: list[ExtractedEntity]
    method: str  # markup, model, outputs
    dropped: list[str] = field(default_factory=list)  # values not found in the source
    model_calls: int = 0
    cost_usd: float = 0.0


def type_catalog(types: tuple[str, ...] = ("Trip", "Flight", "Person", "Loyalty program", "Reservation", "Order", "Item", "Place")) -> str:
    return "\n".join(f"  - {t}: {', '.join(TYPES[t].attributes)}" for t in types)


# ---- schema.org markup --------------------------------------------------------------------------


def _app_date(iso: str) -> tuple[str, str]:
    """ISO datetime → ('Fri, Oct 30, 2026', '6:10 AM'), the way the app writes them."""
    dt = datetime.fromisoformat(iso)
    return f"{dt:%a, %b} {dt.day}, {dt.year}", f"{dt.hour % 12 or 12}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def _obs(e: ExtractedEntity, attribute: str, value: Any, evidence: str) -> None:
    if value not in (None, ""):
        e.observations.append(Observation(attribute, str(value), evidence))


def from_markup(mail: Email) -> Extraction | None:
    blocks = []
    for raw in _LD.findall(mail.html or ""):
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        blocks += data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
    out: list[ExtractedEntity] = []
    n = 0
    for b in blocks:
        kind = str(b.get("@type", ""))
        if kind == "FlightReservation":
            f = b.get("reservationFor") or {}
            airline = (f.get("airline") or {}).get("iataCode") or ""
            n += 1
            trip, flight = ExtractedEntity("Trip", local_id=f"t{n}"), ExtractedEntity("Flight", local_id=f"f{n}")
            status = str(b.get("reservationStatus", "")).rsplit("/", 1)[-1].replace("Reservation", "").lower()
            arr = f.get("arrivalAirport") or {}
            dep = f.get("departureAirport") or {}
            day, dep_time = _app_date(f["departureTime"]) if f.get("departureTime") else ("", "")
            _, arr_time = _app_date(f["arrivalTime"]) if f.get("arrivalTime") else ("", "")
            _obs(trip, "confirmation_code", b.get("reservationNumber"), "reservationNumber")
            _obs(trip, "destination", (arr.get("address") or {}).get("addressLocality") or arr.get("name"), "arrivalAirport")
            _obs(trip, "origin", dep.get("name"), "departureAirport.name")
            _obs(trip, "start_date", day, "departureTime")
            _obs(trip, "airline", (f.get("airline") or {}).get("name"), "airline.name")
            _obs(trip, "status", {"confirmed": "upcoming", "cancelled": "cancelled"}.get(status), "reservationStatus")
            _obs(flight, "number", f"{airline} {f.get('flightNumber', '')}".strip(), "flightNumber")
            _obs(flight, "date", day, "departureTime")
            _obs(flight, "from", dep.get("iataCode"), "departureAirport.iataCode")
            _obs(flight, "to", arr.get("iataCode"), "arrivalAirport.iataCode")
            _obs(flight, "depart_time", dep_time, "departureTime")
            _obs(flight, "arrive_time", arr_time, "arrivalTime")
            _obs(flight, "seat", b.get("airplaneSeat"), "airplaneSeat")
            _obs(flight, "boarding_group", b.get("boardingGroup"), "boardingGroup")
            _obs(flight, "confirmation_code", b.get("reservationNumber"), "reservationNumber")
            trip.links.append(("includes", flight.local_id))
            out += [trip, flight]
            person = b.get("underName") or {}
            if person.get("name") or person.get("email"):
                p = ExtractedEntity("Person", local_id=f"p{n}")
                _obs(p, "name", person.get("name"), "underName.name")
                _obs(p, "email", person.get("email"), "underName.email")
                p.links.append(("travels_on", trip.local_id))
                out.append(p)
        elif kind == "Order":
            n += 1
            o = ExtractedEntity("Order", local_id=f"o{n}")
            _obs(o, "merchant", (b.get("merchant") or b.get("seller") or {}).get("name"), "merchant.name")
            _obs(o, "order_number", b.get("orderNumber"), "orderNumber")
            _obs(o, "status", str(b.get("orderStatus", "")).rsplit("/", 1)[-1], "orderStatus")
            out.append(o)
        elif kind == "LodgingReservation":
            n += 1
            r = ExtractedEntity("Reservation", local_id=f"r{n}")
            _obs(r, "kind", "hotel", "@type")
            _obs(r, "name", (b.get("reservationFor") or {}).get("name"), "reservationFor.name")
            _obs(r, "confirmation_code", b.get("reservationNumber"), "reservationNumber")
            _obs(r, "start_date", b.get("checkinDate") or b.get("checkinTime"), "checkinDate")
            out.append(r)
    return Extraction(out, "markup") if out else None


# ---- the model (screens and plain emails) -------------------------------------------------------


def _present(value: str, text: str) -> bool:
    v, t = norm(value), norm(text)
    if not v:
        return False
    if v in t:
        return True
    squeeze = lambda s: re.sub(r"[^0-9a-z]", "", s)  # noqa: E731 - "SL1190" vs "SL 1190", "6:10AM" vs "6:10 AM"
    if len(squeeze(v)) >= 2 and squeeze(v) in squeeze(t):
        return True
    # Codes mixing letters and digits (3J8N0D): text read from an image (OCR) confuses O/0 and I/l/1, so those count as
    # the same glyph. The model's reading is what is stored; the image's text only has to agree up to that.
    if re.fullmatch(r"(?=.*\d)(?=.*[a-z])[0-9a-z]{5,}", squeeze(v)):
        glyph = str.maketrans("oil", "011")
        return squeeze(v).translate(glyph) in squeeze(t).translate(glyph)
    return False


def _from_output(out: ExtractionOutput, text: str, screen: ScreenState | None) -> tuple[list[ExtractedEntity], list[str]]:
    ents: list[ExtractedEntity] = []
    dropped: list[str] = []
    for e in out.entities:
        if e.type not in TYPES:
            continue
        ent = ExtractedEntity(e.type, local_id=e.ref)
        allowed = set(TYPES[e.type].attributes)
        for f in e.facts:
            attr = canonical_attribute(f.attribute)
            if attr not in allowed or not f.value.strip():
                continue
            if not _present(f.value, text):
                dropped.append(f"{e.type}.{attr}={f.value!r}")
                continue
            evidence = ""
            if screen is not None and f.evidence and f.evidence.strip().isdigit():
                k = int(f.evidence.strip())
                if 1 <= k <= len(screen.numbered):
                    el = screen.numbered[k - 1]
                    evidence = f"[{k}] {el.label[:80]}" + (f" (id: {el.resource_id.split('/')[-1]})" if el.resource_id else "")
            ent.observations.append(Observation(attr, f.value.strip(), evidence))
        if ent.observations:
            ents.append(ent)
    refs = {e.local_id: e for e in ents}
    for link in out.links:
        if link.from_ref in refs and link.to_ref in refs:
            refs[link.from_ref].links.append((link.relation, link.to_ref))
    return ents, dropped


async def from_model(kind: str, header: str, body: str, adapter: ModelAdapter, *, data_scope: DataScope, task_id: str | None = None,
                     screen: ScreenState | None = None, contributor: bool = False) -> Extraction:
    text = body[:MAX_SOURCE_CHARS]
    res = await asyncio.to_thread(adapter.call, "extract", extract_input(kind, header, text), instructions=extract_instructions(type_catalog()),
                                  data_scope=data_scope, contributor=contributor, task_id=task_id)
    ents, dropped = _from_output(res.parsed, header + "\n" + text, screen)  # type: ignore[arg-type]
    return Extraction(ents, "model", dropped, 1, res.cost_at_standard_usd)


async def from_email(mail: Email, adapter: ModelAdapter, *, data_scope: DataScope, task_id: str | None = None) -> Extraction:
    marked = from_markup(mail)
    if marked is not None:
        return marked
    body = redact_text(mail.text)
    return await from_model("email", f"From: {mail.sender} · Subject: {redact_text(mail.subject)}", body, adapter, data_scope=data_scope, task_id=task_id)


async def from_screen(screen: ScreenState, adapter: ModelAdapter, *, data_scope: DataScope, task_id: str | None = None) -> Extraction:
    text = screen_text(screen)
    header, _, body = text.partition("\n")
    return await from_model("app screen", header, body, adapter, data_scope=data_scope, task_id=task_id, screen=screen)


# ---- routine outputs ----------------------------------------------------------------------------

FLIGHT_ATTRS = set(TYPES["Flight"].attributes)
TRIP_ATTRS = set(TYPES["Trip"].attributes)
PERSON_ATTRS = set(TYPES["Person"].attributes)


def from_routine(inputs: dict[str, str], outputs: dict[str, str | None], input_paths: dict[str, str | None]) -> Extraction:
    """Routine inputs say which trip it was about; outputs are facts about it. Attribute names go through synonyms."""
    trip, flight, person = ExtractedEntity("Trip", local_id="t"), ExtractedEntity("Flight", local_id="f"), ExtractedEntity("Person", local_id="p")
    for name, value in list(inputs.items()) + list(outputs.items()):
        if not value:
            continue
        path = input_paths.get(name) or ""
        if not path and name in inputs and (mp := memory_path(None, name)):
            path = f"{mp[0].lower().replace('person', 'user')}.{mp[1]}"
        attr = canonical_attribute(path.split(".")[-1] if path else name)
        target = {"trip": trip, "flight": flight, "user": person}.get(path.split(".")[0]) if path else None
        if attr == "destination" or (target is trip and attr in TRIP_ATTRS):
            _obs(trip, attr if attr in TRIP_ATTRS else "destination", value, f"routine {'input' if name in inputs else 'output'} {name}")
        elif attr in FLIGHT_ATTRS and target in (None, flight):
            v = value
            if attr == "boarding_time" and " · " in v:  # "5:30 AM · Group 3"
                v, group = [x.strip() for x in v.split(" · ", 1)]
                _obs(flight, "boarding_group", group.removeprefix("Group ").strip(), f"routine output {name}")
            _obs(flight, attr, v, f"routine {'input' if name in inputs else 'output'} {name}")
        elif attr in PERSON_ATTRS:
            _obs(person, attr, value, f"routine {'input' if name in inputs else 'output'} {name}")
        elif attr in TRIP_ATTRS:
            _obs(trip, attr, value, f"routine output {name}")
    ents = [e for e in (trip, flight, person) if e.observations]
    if trip.observations and flight.observations:
        trip.links.append(("includes", "f"))
    return Extraction(ents, "outputs")
