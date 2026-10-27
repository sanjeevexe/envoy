"""Memory ↔ routines and the agent (design doc, Shared memory › What is new: "routine inputs come from facts,
and routine outputs become new facts").

- `notes_for(goal)`: the agent's NOTES and the matcher's notes, from retrieval.
- `fill_inputs`: a routine's inputs from memory through their `from_memory` hints (trip.city, user.last_name…):
  the entity named in the request, else the next upcoming trip or flight, else the user.
- `remember_run`: a routine's outputs (and inputs) written back as facts, with the run as their source.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from devices.types import ScreenState
from memory.retrieval import Retriever
from memory.service import IngestReport, MemoryService
from memory.store import MemoryStore
from memory.types import MEMORY_PATHS
from routines.model import Routine


@dataclass
class Filled:
    inputs: dict[str, str]
    sources: dict[str, str] = field(default_factory=dict)  # input → "Trip Denver · … (confirmation): email from SkyLark Air, Oct 12"
    missing: list[str] = field(default_factory=list)


def notes_for(store: MemoryStore, goal: str, budget_chars: int = 4000) -> str:
    return Retriever(store).notes(goal, budget_chars=budget_chars).markdown


def _entity_for(store: MemoryStore, r: Retriever, type_: str, request: str) -> str | None:
    for eid, _ in r.link_mentions(request):
        e = store.entity(eid)
        if e and e["type"] == type_:
            return eid
        for n in store.neighbors(eid):  # "my Denver trip" names the Trip; its Flight is one link away
            ne = store.entity(n)
            if ne and ne["type"] == type_:
                return n
    if type_ in ("Trip", "Flight"):
        return r.next_upcoming(type_)
    people = store.entities(type_)
    return max(people, key=lambda p: len(store.current_facts(p["id"])))["id"] if people else None


def fill_inputs(store: MemoryStore, routine: Routine, request: str, given: dict[str, str] | None = None) -> Filled:
    r = Retriever(store)
    out = Filled(dict(given or {}))
    for name, spec in routine.inputs.items():
        if out.inputs.get(name):
            continue
        path = MEMORY_PATHS.get(spec.from_memory or "")
        if path is None:
            out.missing.append(name)
            continue
        type_, attr = path
        eid = _entity_for(store, r, type_, request)
        fact = store.current(eid, attr) if eid else None
        if fact is None and type_ == "Trip" and attr == "destination" and eid:
            # A trip seen only as a flight: its arrival city may be on the Flight ("to") as a code; keep it missing.
            fact = None
        if fact is None:
            out.missing.append(name)
            continue
        out.inputs[name] = fact["value"]
        e = store.entity(eid) or {}
        out.sources[name] = f"{e.get('type')} {e.get('name')} ({attr}): {r.where(fact['source'])}"
    return out


async def remember_run(service: MemoryService, routine: Routine, inputs: dict[str, str], outputs: dict[str, str | None], *,
                       task_id: str, final_screen: ScreenState | None = None) -> tuple[IngestReport, IngestReport | None]:
    """Write a routine run into memory: its final screen (if given) is read first, and anchors the outputs."""
    screen_rep = await service.ingest_screen(final_screen, task_id=task_id) if final_screen is not None else None
    about = {r.type: r.entity for r in screen_rep.resolved} if screen_rep else None
    rep = await service.ingest_routine(routine, inputs, outputs, task_id=task_id, app=routine.app, about=about)
    return rep, screen_rep
