"""Offline tests for the memory store: two timelines, user precedence, merge and split, keys, search."""

from __future__ import annotations

from datetime import datetime

import pytest

from memory.store import MemoryStore
from memory.types import ExtractedEntity, Observation, normalize_key_value, parse_date


class Clock:
    def __init__(self) -> None:
        self.t = datetime(2026, 10, 27, 9, 0).timestamp()

    def __call__(self) -> float:
        return self.t

    def tick(self, s: float) -> float:
        self.t += s
        return self.t


@pytest.fixture
def mem():
    c = Clock()
    return MemoryStore(":memory:", clock=c), c


def test_new_value_replaces_the_old_and_keeps_history(mem):
    m, c = mem
    f = m.create_entity("Flight")
    src = m.add_source("app_screen", {"app": "com.skylark.air"})
    m.observe(f, "gate", "B12", source=src)
    c.tick(3600)
    r = m.observe(f, "gate", "C14", source=src)
    assert r.kind == "replaced"
    assert m.current(f, "gate")["value"] == "C14"
    hist = m.history(f, "gate")
    assert [h["value"] for h in hist] == ["B12", "C14"] and hist[0]["valid_to"] == hist[1]["valid_from"]


def test_same_value_refreshes_instead_of_duplicating(mem):
    m, c = mem
    f = m.create_entity("Flight")
    m.observe(f, "seat", "14C", source=None)
    c.tick(60)
    assert m.observe(f, "seat", "14C", source=None).kind == "same"
    assert len(m.history(f, "seat")) == 1 and m.current(f, "seat")["observed_at"] == c.t


def test_older_observation_becomes_history(mem):
    m, c = mem
    f = m.create_entity("Flight")
    m.observe(f, "seat", "12C", source=None)  # today, in the app
    r = m.observe(f, "seat", "14C", source=None, observed_at=c.t - 15 * 86400)  # the booking email, two weeks ago
    assert r.kind == "history" and m.current(f, "seat")["value"] == "12C"


def test_user_edit_outranks_extraction_and_conflicts_are_flagged(mem):
    m, c = mem
    p = m.create_entity("Preference")
    m.observe(p, "text", "window seat", source=None)
    m.user_edit(p, "text", "aisle seat")
    c.tick(60)
    r = m.observe(p, "text", "window seat", source=None)
    assert r.kind == "conflict" and m.current(p, "text")["value"] == "aisle seat" and len(m.conflicts(p)) == 1


def test_keys_find_the_same_flight_written_differently(mem):
    m, _ = mem
    f = m.create_entity("Flight")
    m.observe(f, "number", "SL 1190", source=None)
    m.observe(f, "date", "Sat, Nov 14, 2026", source=None)
    assert m.find_by_key("Flight", "number,date=SL1190|2026-11-14") == f
    assert normalize_key_value("date", "2026-11-14T14:45:00-05:00") == "2026-11-14"
    assert parse_date("14 Nov 2026").isoformat() == "2026-11-14"
    e = ExtractedEntity("Flight", [Observation("number", "SL1190"), Observation("date", "Nov 14, 2026")])
    assert e.key_values() == [("SL1190", "2026-11-14")]


def test_merge_dedupes_rechains_and_split_restores(mem):
    m, c = mem
    a = m.create_entity("Trip")
    b = m.create_entity("Trip")
    m.observe(a, "destination", "Denver", source=None)
    m.observe(a, "seat", "22F", source=None, observed_at=c.t - 100)
    m.observe(b, "destination", "Denver", source=None)
    m.observe(b, "confirmation_code", "PT4R8Z", source=None)
    m.observe(b, "seat", "21C", source=None)
    m.link(b, "includes", m.create_entity("Flight"))
    seq = m.merge(a, b, "same confirmation")
    cur = {f["attribute"]: f["value"] for f in m.current_facts(a)}
    assert cur == {"destination": "Denver", "confirmation_code": "PT4R8Z", "seat": "21C"}
    assert len([h for h in m.history(a, "destination") if h["retired_at"] is None]) == 1  # de-duplicated
    assert m.resolve(b) == a and len(m.edges_of(a)) == 1 and m.find_by_key("Trip", "confirmation_code=PT4R8Z") == a
    m.split(seq)
    assert m.resolve(b) == b
    assert {f["attribute"]: f["value"] for f in m.current_facts(a)} == {"destination": "Denver", "seat": "22F"}
    assert {f["attribute"]: f["value"] for f in m.current_facts(b)} == {"destination": "Denver", "confirmation_code": "PT4R8Z", "seat": "21C"}
    assert len(m.edges_of(b)) == 1 and m.find_by_key("Trip", "confirmation_code=PT4R8Z") == b


def test_search_and_neighbors(mem):
    m, _ = mem
    t = m.create_entity("Trip")
    f = m.create_entity("Flight")
    m.observe(t, "destination", "Denver", source=None)
    m.observe(f, "number", "SL 1190", source=None)
    m.link(t, "includes", f)
    assert m.search("my denver trip")[0][0] == t
    assert m.neighbors(t) == [f]
    assert m.entity(t)["name"].startswith("Denver")


def test_staleness_follows_freshness_rules(mem):
    m, c = mem
    f = m.create_entity("Flight")
    m.observe(f, "gate", "B12", source=None)
    m.observe(f, "seat", "14C", source=None)
    c.tick(45 * 60)
    gate, seat = m.current(f, "gate"), m.current(f, "seat")
    assert m.is_stale(gate, "Flight") and not m.is_stale(seat, "Flight")
