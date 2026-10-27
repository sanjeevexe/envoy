"""A test inbox for SkyLark bookings: the confirmation emails a real airline would send, plus noise.

Each booking gets a confirmation email, either with schema.org `FlightReservation` markup (as many airlines
send, parsed with no model call) or as plain text (read by the model). Some are forwarded, some seats
change by email, one booking is cancelled, and promotional mail mentions cities without being a booking.
Every email comes with its ground truth, taken from the same booking that seeds the app, so extraction and
matching are scored exactly.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from pathlib import Path
from typing import Any

from skylark_routines import Booking

USER_NAME, USER_EMAIL = "Maya Patel", "maya.patel@example.com"
SKYLARK = "SkyLark Air <reservations@skylark.example>"
EDT = timezone(timedelta(hours=-4))
_CITY_AIRPORT_NAME = {"ORD": "Chicago O'Hare", "DEN": "Denver International"}


@dataclass
class TestMail:
    name: str  # file stem, sorts in delivery order
    message: EmailMessage
    kind: str  # markup, plain, forward, seat_change, cancellation, promo, receipt
    booking: str | None  # confirmation code, if it is about a booking
    truth: list[dict[str, Any]] = field(default_factory=list)  # expected entities: {"type", attribute: value, ...}


def _iso(date_text: str, time_text: str) -> str:
    d = datetime.strptime(date_text, "%a, %b %d, %Y")
    t = datetime.strptime(time_text, "%I:%M %p")
    return d.replace(hour=t.hour, minute=t.minute, tzinfo=EDT).isoformat()


def _base(subject: str, sent: datetime, sender: str = SKYLARK) -> EmailMessage:
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = sender, f"{USER_NAME} <{USER_EMAIL}>", subject
    m["Date"] = format_datetime(sent)
    m["Message-ID"] = make_msgid(domain="skylark.example")
    return m


def _truth(b: Booking, seat: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    trip = {"type": "Trip", "confirmation_code": b.code, "destination": b.city, "start_date": b.date}
    flight = {"type": "Flight", "number": b.number, "date": b.date, "from": "ATL", "to": b.airport, "depart_time": b.depart}
    if seat or seat is None:
        flight["seat"] = seat or b.seat
    if status:
        trip["status"] = status
    return [trip, flight]


def plain_body(b: Booking, seat: str) -> str:
    return (f"Hi Maya,\n\nYour trip to {b.city} is booked. Thanks for flying SkyLark Air.\n\n"
            f"Confirmation code: {b.code}\nFlight: {b.number}\nFrom: Atlanta (ATL) to {b.city} ({b.airport})\n"
            f"Date: {b.date}\nDeparts: {b.depart}  Arrives: {b.arrive}\nSeat: {seat}\nPassenger: {USER_NAME}\n\n"
            "Check in opens 24 hours before departure in the SkyLark app.\n\nSkyLark Air")


def markup_email(b: Booking, sent: datetime) -> EmailMessage:
    data = {
        "@context": "http://schema.org", "@type": "FlightReservation", "reservationNumber": b.code,
        "reservationStatus": "http://schema.org/ReservationConfirmed",
        "underName": {"@type": "Person", "name": USER_NAME, "email": USER_EMAIL},
        "reservationFor": {"@type": "Flight", "flightNumber": b.number.split()[-1],
                           "airline": {"@type": "Airline", "name": "SkyLark Air", "iataCode": "SL"},
                           "departureAirport": {"@type": "Airport", "name": "Atlanta", "iataCode": "ATL"},
                           "departureTime": _iso(b.date, b.depart),
                           "arrivalAirport": {"@type": "Airport", "name": _CITY_AIRPORT_NAME.get(b.airport, b.city), "iataCode": b.airport,
                                              "address": {"@type": "PostalAddress", "addressLocality": b.city}},
                           "arrivalTime": _iso(b.date, b.arrive)},
        "airplaneSeat": b.seat, "boardingGroup": b.group,
    }
    m = _base(f"Your SkyLark trip to {b.city} is confirmed ({b.code})", sent)
    m.set_content(plain_body(b, b.seat))
    html = (f"<html><head><script type=\"application/ld+json\">{json.dumps(data)}</script></head><body>"
            f"<h1>You're going to {b.city}!</h1><p>Confirmation <b>{b.code}</b></p>"
            f"<p>{b.number} · ATL {b.depart} → {b.airport} {b.arrive} · {b.date}</p><p>Seat {b.seat}</p></body></html>")
    m.add_alternative(html, subtype="html")
    return m


def plain_email(b: Booking, sent: datetime) -> EmailMessage:
    m = _base(f"Booking confirmation {b.code}: Atlanta to {b.city}", sent)
    m.set_content(plain_body(b, b.seat))
    return m


def forwarded_email(b: Booking, sent: datetime) -> EmailMessage:
    m = _base(f"Fwd: Booking confirmation {b.code}: Atlanta to {b.city}", sent, sender=f"{USER_NAME} <{USER_EMAIL}>")
    quoted = "\n".join("> " + line for line in plain_body(b, b.seat).splitlines())
    m.set_content(f"Saving this for later.\n\n---------- Forwarded message ---------\nFrom: {SKYLARK}\n\n{quoted}")
    return m


def seat_change_email(b: Booking, sent: datetime, new_seat: str) -> EmailMessage:
    m = _base(f"Seat change confirmed for {b.number} on {b.date}", sent)
    m.set_content(f"Hi Maya,\n\nYour seat on flight {b.number} ({b.date}, ATL to {b.airport}) is now {new_seat}.\n"
                  f"Confirmation code: {b.code}\n\nSkyLark Air")
    return m


def cancellation_email(b: Booking, sent: datetime) -> EmailMessage:
    m = _base(f"Your trip {b.code} has been cancelled", sent)
    m.set_content(f"Hi Maya,\n\nAs requested, we cancelled your trip to {b.city} (confirmation code {b.code}, flight {b.number} on {b.date}).\n"
                  "A credit for the fare is in your SkyLark account.\n\nSkyLark Air")
    return m


def promo_email(city: str, sent: datetime) -> EmailMessage:
    m = _base(f"Fall fares to {city} from $99", sent, sender="SkyLark Air Deals <deals@skylark.example>")
    m.set_content(f"Fly to {city} this fall from $99 one way. Book by Nov 15 with code FALL99.\n"
                  f"Popular flights: SL 1450 and SL 1452 to {city}. Double miles on every booking.\n\nUnsubscribe")
    return m


def receipt_email(sent: datetime) -> EmailMessage:
    m = _base("Your order #448-2291 has shipped", sent, sender="Pinecone Outfitters <orders@pinecone.example>")
    m.set_content("Thanks for your order! Order #448-2291 (1 x Packable rain jacket, $89.00) shipped today and arrives Thu, Oct 29.")
    return m


def build_inbox(bookings: list[Booking], seed: int = 3) -> list[TestMail]:
    """One confirmation per booking (half with markup), plus forwards, a seat change, a cancellation and noise.
    The first booking stays plain so the model's path is always exercised."""
    rng = random.Random(seed)
    start = datetime(2026, 10, 1, 9, 0, tzinfo=EDT)
    mails: list[TestMail] = []
    t = start
    for i, b in enumerate(bookings):
        t += timedelta(hours=rng.randint(6, 30))
        if i % 2 == 0:
            mails.append(TestMail(f"{len(mails):03d}-plain-{b.code}", plain_email(b, t), "plain", b.code, _truth(b)))
        else:
            mails.append(TestMail(f"{len(mails):03d}-markup-{b.code}", markup_email(b, t), "markup", b.code, _truth(b)))
        if i % 4 == 1:
            t += timedelta(hours=2)
            mails.append(TestMail(f"{len(mails):03d}-forward-{b.code}", forwarded_email(b, t), "forward", b.code, _truth(b)))
    # A seat change by email (newer than the booking; the app may show something newer still).
    b = bookings[1]
    t += timedelta(days=1)
    mails.append(TestMail(f"{len(mails):03d}-seat-{b.code}", seat_change_email(b, t, b.new_seat), "seat_change", b.code,
                          [{"type": "Flight", "number": b.number, "date": b.date, "seat": b.new_seat}]))
    # A cancellation.
    b = bookings[-1]
    t += timedelta(hours=5)
    mails.append(TestMail(f"{len(mails):03d}-cancel-{b.code}", cancellation_email(b, t), "cancellation", b.code,
                          [{"type": "Trip", "confirmation_code": b.code, "status": "cancelled"}]))
    for city in (bookings[0].city, "Phoenix"):
        t += timedelta(hours=7)
        mails.append(TestMail(f"{len(mails):03d}-promo-{city}", promo_email(city, t), "promo", None, []))
    t += timedelta(hours=3)
    mails.append(TestMail(f"{len(mails):03d}-receipt", receipt_email(t), "receipt", None,
                          [{"type": "Order", "merchant": "Pinecone Outfitters", "order_number": "448-2291"}]))
    return mails


def write_inbox(mails: list[TestMail], folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.eml"):
        old.unlink()
    for m in mails:
        (folder / f"{m.name}.eml").write_bytes(bytes(m.message))
    (folder / "truth.json").write_text(json.dumps([{"name": m.name, "kind": m.kind, "booking": m.booking, "truth": m.truth} for m in mails], indent=1))
