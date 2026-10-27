"""Offline tests for memory: email parsing, schema.org markup, redaction, the service's resolving, retrieval and the
routine bridge. The model is replaced by a scripted adapter, so no API call is made."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from integrations.mail import LocalMailbox, parse_message
from memory import extract
from memory.bridge import fill_inputs
from memory.redact import redact_text
from memory.retrieval import Retriever
from memory.service import MemoryService
from memory.store import MemoryStore
from models.schemas import ExtractedEntityOut, ExtractedFactOut, ExtractedLinkOut, ExtractionOutput, MemoryAnswer, SameEntityOutput
from routines.model import InputSpec, Routine, Step, StepAction

MAIL = Path(__file__).parent / "mail"


class ScriptedAdapter:
    """Answers extract/same_entity/answer calls from a script instead of the API."""

    def __init__(self, extraction: ExtractionOutput | None = None, same: bool = False, answer: str = "") -> None:
        self.extraction, self.same, self.answer_text, self.calls = extraction, same, answer, []

    def call(self, job, content, **kw):
        self.calls.append(job)
        parsed = {"extract": self.extraction or ExtractionOutput(entities=[], links=[]),
                  "same_entity": SameEntityOutput(same=self.same, reason="scripted"),
                  "answer": MemoryAnswer(answer=self.answer_text, found=bool(self.answer_text), stale=False)}[job]
        return SimpleNamespace(parsed=parsed, cost_at_standard_usd=0.0)


def clock_at(y: int, m: int, d: int, h: int = 9):
    t = datetime(y, m, d, h).timestamp()
    return lambda: t


def chicago_extraction() -> ExtractionOutput:
    facts = lambda **kv: [ExtractedFactOut(attribute=k, value=v, evidence=None) for k, v in kv.items()]  # noqa: E731
    return ExtractionOutput(entities=[
        ExtractedEntityOut(ref="t", type="Trip", facts=facts(confirmation_code="KX7Q2M", destination="Chicago")),
        ExtractedEntityOut(ref="f", type="Flight", facts=facts(number="SL 482", date="Fri, Oct 30, 2026", seat="14C", gate="B99")),
    ], links=[ExtractedLinkOut(from_ref="t", relation="includes", to_ref="f")])


def test_markup_is_parsed_without_a_model():
    mail = parse_message((MAIL / "markup_denver.eml").read_bytes(), "m1")
    ex = extract.from_markup(mail)
    assert ex is not None and ex.method == "markup"
    trip = next(e for e in ex.entities if e.type == "Trip")
    flight = next(e for e in ex.entities if e.type == "Flight")
    assert trip.get("confirmation_code") == "PT4R8Z" and trip.get("destination") == "Denver" and trip.get("start_date") == "Sat, Nov 14, 2026"
    assert flight.get("number") == "SL 1190" and flight.get("depart_time") == "2:45 PM" and flight.get("seat") == "22F"
    assert ("includes", flight.local_id) in trip.links


def test_local_mailbox_reads_eml_and_html_text():
    mails, cursor = LocalMailbox(MAIL).fetch(None)
    assert len(mails) == 3 and cursor.endswith(".eml")
    assert LocalMailbox(MAIL).fetch(cursor)[0] == []
    assert any("Confirmation code: KX7Q2M" in m.text for m in mails)


def test_model_values_must_appear_in_the_source():
    mail = parse_message((MAIL / "plain_chicago.eml").read_bytes(), "m2")
    ents, dropped = extract._from_output(chicago_extraction(), mail.text, None)
    flight = next(e for e in ents if e.type == "Flight")
    assert flight.get("seat") == "14C" and flight.get("gate") is None  # B99 is not in the email: dropped, never stored
    assert any("gate" in d for d in dropped)


def test_redaction():
    assert "[card number]" in redact_text("Card 4242 4242 4242 4242")
    assert "482913" not in redact_text("Your verification code is 482913")
    assert "98765432" in redact_text("Known traveler number 98765432")  # not a card (fails Luhn): kept


def test_email_and_app_merge_into_one_trip_and_answer_from_memory():
    store = MemoryStore(":memory:", clock=clock_at(2026, 10, 27))
    svc = MemoryService(store, ScriptedAdapter(chicago_extraction()), data_scope="test_app")
    plain = parse_message((MAIL / "plain_chicago.eml").read_bytes(), "plain")
    rep = asyncio.run(svc.ingest_email(plain))
    assert [r.how for r in rep.resolved] == ["new", "new"]
    # The routine reads the gate in the app: same trip (by flight number and date), now with a gate from the app.
    routine = Routine(routine="gate", app="com.skylark.air", intent="get gate", inputs={"trip_city": InputSpec(from_memory="trip.city")},
                      steps=[Step(id="s", intent="x", action=StepAction(kind="back"))])
    rep2 = asyncio.run(svc.ingest_routine(routine, {"trip_city": "Chicago"}, {"gate": "B12", "flight_number": "SL 482",
                                                                          "date": "Fri, Oct 30, 2026"}, task_id="t1"))
    assert all(r.how in ("key", "link") for r in rep2.resolved) or rep2.merged
    assert len(store.entities("Trip")) == 1 and len(store.entities("Flight")) == 1
    r = Retriever(store)
    assert r.next_upcoming("Flight") == store.entities("Flight")[0]["id"]
    notes = r.notes("What's my gate?")
    assert "Gate: B12" in notes.markdown and "SkyLark app" in notes.markdown and "email from SkyLark Air" in notes.markdown
    ans = asyncio.run(r.answer("What's my gate?", ScriptedAdapter(answer="Gate B12, from the SkyLark app just now")))
    assert ans.found and ans.supported
    bad = asyncio.run(r.answer("What's my gate?", ScriptedAdapter(answer="Gate D40")))
    assert not bad.supported and not bad.found  # an answer whose specifics are not in the notes is not trusted


def test_promo_and_two_trips_to_one_city_stay_apart():
    store = MemoryStore(":memory:", clock=clock_at(2026, 10, 27))
    facts = lambda **kv: [ExtractedFactOut(attribute=k, value=v, evidence=None) for k, v in kv.items()]  # noqa: E731
    first = ExtractionOutput(entities=[ExtractedEntityOut(ref="t", type="Trip", facts=facts(destination="Denver", start_date="Sat, Nov 14, 2026"))], links=[])
    second = ExtractionOutput(entities=[ExtractedEntityOut(ref="t", type="Trip", facts=facts(destination="Denver", start_date="Fri, Dec 4, 2026"))], links=[])
    for ex in (first, second):
        ents, _ = extract._from_output(ex, "Denver Sat, Nov 14, 2026 Fri, Dec 4, 2026", None)
        asyncio.run(MemoryService(store, ScriptedAdapter(same=True))._apply(extract.Extraction(ents, "model"), None, store.clock(), "email"))
    assert len(store.entities("Trip")) == 2  # different dates are a distinguishing conflict: no model call can merge them


def test_fill_inputs_from_memory_uses_the_next_trip_or_the_named_one():
    store = MemoryStore(":memory:", clock=clock_at(2026, 10, 27))
    for city, d in (("Chicago", "Fri, Oct 30, 2026"), ("Denver", "Sat, Nov 14, 2026"), ("Boston", "Sat, Sep 12, 2026")):
        t = store.create_entity("Trip")
        store.observe(t, "destination", city, source=store.add_source("email", {}))
        store.observe(t, "start_date", d, source=None)
    routine = Routine(routine="checkin", app="com.skylark.air", intent="check in",
                      inputs={"trip_city": InputSpec(from_memory="trip.city"), "seat": InputSpec()}, steps=[])
    f = fill_inputs(store, routine, "Check me in")
    assert f.inputs["trip_city"] == "Chicago" and f.missing == ["seat"] and "email" in f.sources["trip_city"]  # Boston is past
    assert fill_inputs(store, routine, "Check me in for my Denver trip").inputs["trip_city"] == "Denver"
