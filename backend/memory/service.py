"""The memory service: the only writer (design doc, Shared memory › Recognizing the same thing twice, Staying in sync).

Ingest = extract → resolve each extracted entity → write its facts and links. Resolving, in order:
  1. exact natural keys (a reservation's confirmation code; a flight's number and date)
  2. links in the same source (a boarding pass's flight is already linked to a trip: that trip)
  3. keyword candidates of the same type: agreeing values and no conflicting key → the same entity; when
     the evidence is thin, one Muse Spark call decides
  4. otherwise a new entity
After writing, an entity whose new key already belongs to another entity is merged into it (merges are
reversible: MemoryStore.split).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from devices.types import ScreenState
from integrations.mail import Email
from memory import extract
from memory.redact import allowed, redact_text, screen_text
from memory.store import MemoryStore
from memory.types import SOURCE_RELIABILITY, TYPES, ExtractedEntity, normalize_key_value
from models.adapter import DataScope, ModelAdapter
from models.prompts import SAME_ENTITY_INSTRUCTIONS

# Attributes that tell two entities apart when both have them and they differ.
DISTINGUISHING = {"confirmation_code", "number", "date", "start_date", "order_number", "email", "member_number"}


@dataclass
class Resolved:
    local_id: str
    type: str
    entity: str
    how: str  # key, link, rule, model, new


@dataclass
class IngestReport:
    source: str | None
    method: str
    resolved: list[Resolved] = field(default_factory=list)
    facts: dict[str, int] = field(default_factory=dict)  # new / same / replaced / history / conflict
    merged: list[tuple[str, str]] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    skipped: str = ""
    model_calls: int = 0
    cost_usd: float = 0.0
    extracted: list[ExtractedEntity] = field(default_factory=list)  # what the extractor read, before resolving


class MemoryService:
    def __init__(self, store: MemoryStore | None = None, adapter: ModelAdapter | None = None, *, data_scope: DataScope = "real",
                 allow_apps: set[str] | None = None) -> None:
        self.store = store or MemoryStore()
        self.adapter = adapter or ModelAdapter()
        self.data_scope = data_scope
        self.allow_apps = allow_apps or set()

    # ---- sources ----------------------------------------------------------------------------

    async def ingest_email(self, mail: Email, task_id: str | None = None) -> IngestReport:
        ex = await extract.from_email(mail, self.adapter, data_scope=self.data_scope, task_id=task_id)
        kind = "email_markup" if ex.method == "markup" else "email"
        src = self.store.add_source(kind, {"email_id": mail.id, "subject": redact_text(mail.subject), "from": mail.sender},
                                    captured_at=mail.date, snapshot=redact_text(mail.text)[:4000])
        return await self._apply(ex, src, mail.date, kind)

    async def ingest_screen(self, screen: ScreenState, *, task_id: str | None = None, step: int | None = None,
                            observed_at: float | None = None) -> IngestReport:
        if not allowed(screen.package, self.allow_apps):
            return IngestReport(None, "blocked", skipped=f"{screen.package} is blocked from memory")
        if screen.secure or screen.has_password_field:
            return IngestReport(None, "skipped", skipped="secure or sign-in screen")
        ex = await extract.from_screen(screen, self.adapter, data_scope=self.data_scope, task_id=task_id)
        when = observed_at or screen.timestamp or self.store.clock()
        src = self.store.add_source("app_screen", {"app": screen.package, "screen": screen.activity.rsplit(".", 1)[-1], "task_id": task_id,
                                                   "step": step, "signature": screen.signature}, captured_at=when, snapshot=screen_text(screen))
        return await self._apply(ex, src, when, "app_screen")

    async def ingest_routine(self, routine: Any, inputs: dict[str, str], outputs: dict[str, str | None], *, task_id: str,
                             app: str | None = None, observed_at: float | None = None, about: dict[str, str] | None = None) -> IngestReport:
        """`about` anchors the run's entities by type (from its final screen, read in the same run): a city alone
        can't tell two trips to Denver apart, the screen's confirmation code can."""
        if app and not allowed(app, self.allow_apps):
            return IngestReport(None, "blocked", skipped=f"{app} is blocked from memory")
        paths = {n: s.from_memory for n, s in routine.inputs.items()}
        ex = extract.from_routine(inputs, outputs, paths)
        when = observed_at or self.store.clock()
        src = self.store.add_source("routine_run", {"routine": routine.routine, "version": routine.version, "task_id": task_id,
                                                    "app": app or routine.app}, captured_at=when)
        return await self._apply(ex, src, when, "routine_run", about=about)

    def note(self, text: str, author: str = "user", links: list[str] | None = None) -> str:
        """A note (from the user, or an AI client through MCP, recorded as its author)."""
        eid = self.store.create_entity("Note", name=text[:60])
        src = self.store.add_source("user" if author == "user" else "client", {"author": author})
        self.store.observe(eid, "body", text, source=src, confidence=1.0 if author == "user" else SOURCE_RELIABILITY["client"],
                           author="user" if author == "user" else f"client:{author}")
        for other in links or []:
            self.store.link(eid, "about", other, src)
        return eid

    # ---- resolving and writing -------------------------------------------------------------

    async def _apply(self, ex: extract.Extraction, source: str | None, observed_at: float, kind: str,
                     about: dict[str, str] | None = None) -> IngestReport:
        rep = IngestReport(source, ex.method, dropped=ex.dropped, model_calls=ex.model_calls, cost_usd=ex.cost_usd, extracted=ex.entities)
        mapped: dict[str, str] = {}
        ents = sorted(ex.entities, key=lambda e: -len(e.key_values()))  # keyed entities first, so links can follow them
        for e in ents:
            if about and e.type in about and not self._conflicts(e, self.store.resolve(about[e.type])):
                mapped[e.local_id] = self.store.resolve(about[e.type])
                rep.resolved.append(Resolved(e.local_id, e.type, mapped[e.local_id], "anchor"))
        for e in ents:
            if e.local_id in mapped:
                continue
            how_eid = self._by_key(e)
            if how_eid:
                mapped[e.local_id] = how_eid
                rep.resolved.append(Resolved(e.local_id, e.type, how_eid, "key"))
        for e in ents:
            if e.local_id in mapped:
                continue
            eid = self._by_link(e, ents, mapped)
            how = "link"
            if eid is None:
                eid, how = await self._by_candidates(e, rep)
            if eid is None:
                eid, how = self.store.create_entity(e.type), "new"
            mapped[e.local_id] = eid
            rep.resolved.append(Resolved(e.local_id, e.type, eid, how))
        confidence = SOURCE_RELIABILITY.get(kind, 0.8)
        for e in ents:
            eid = mapped[e.local_id]
            for o in e.observations:
                r = self.store.observe(eid, o.attribute, o.value, source=source, observed_at=observed_at, confidence=confidence)
                rep.facts[r.kind] = rep.facts.get(r.kind, 0) + 1
            for relation, other in e.links:
                if other in mapped:
                    self.store.link(eid, relation, mapped[other], source)
        # A key that now belongs to two entities means they are one: merge into the older.
        for e in ents:
            eid = self.store.resolve(mapped[e.local_id])
            for key in self.store.refresh_keys(eid):
                owner = self.store.find_by_key(e.type, key)
                if owner and owner != eid:
                    keep, other = sorted([owner, eid], key=lambda x: (self.store.entity(x) or {}).get("created_at") or 0)
                    self.store.merge(keep, other, f"same natural key {key}")
                    rep.merged.append((keep, other))
        self.store.commit()
        return rep

    def _key_string(self, e: ExtractedEntity, key_values: tuple[str, ...]) -> str | None:
        spec = TYPES.get(e.type)
        for key in spec.keys if spec else ():
            vals = [e.get(a) for a in key]
            if all(vals) and tuple(normalize_key_value(a, v) for a, v in zip(key, vals)) == key_values:  # type: ignore[arg-type]
                return ",".join(key) + "=" + "|".join(key_values)
        return None

    def _by_key(self, e: ExtractedEntity) -> str | None:
        for kv in e.key_values():
            k = self._key_string(e, kv)
            if k and (eid := self.store.find_by_key(e.type, k)):
                return eid
        return None

    def _by_link(self, e: ExtractedEntity, ents: list[ExtractedEntity], mapped: dict[str, str]) -> str | None:
        """An entity linked in this source to one we already know: its known neighbor of the same type and relation."""
        for other in ents:
            if other.local_id not in mapped:
                continue
            rels = [r for r, to in other.links if to == e.local_id]  # other → e
            rels_in = [r for r, to in e.links if to == other.local_id]  # e → other
            known = self.store.resolve(mapped[other.local_id])
            for edge in self.store.edges_of(known):
                for r in rels:
                    if edge["relation"] == r and self.store.resolve(edge["from_entity"]) == known:
                        cand = self.store.resolve(edge["to_entity"])
                        if (self.store.entity(cand) or {}).get("type") == e.type and not self._conflicts(e, cand):
                            return cand
                for r in rels_in:
                    if edge["relation"] == r and self.store.resolve(edge["to_entity"]) == known:
                        cand = self.store.resolve(edge["from_entity"])
                        if (self.store.entity(cand) or {}).get("type") == e.type and not self._conflicts(e, cand):
                            return cand
        return None

    def _conflicts(self, e: ExtractedEntity, eid: str) -> bool:
        cur = {f["attribute"]: f["value"] for f in self.store.current_facts(eid)}
        return any(o.attribute in DISTINGUISHING and o.attribute in cur and
                   normalize_key_value(o.attribute, cur[o.attribute]) != normalize_key_value(o.attribute, o.value) for o in e.observations)

    def _agreement(self, e: ExtractedEntity, eid: str) -> tuple[int, int]:
        cur = {f["attribute"]: f["value"] for f in self.store.current_facts(eid)}
        agree = conflict = 0
        for o in e.observations:
            if o.attribute in cur:
                if normalize_key_value(o.attribute, cur[o.attribute]) == normalize_key_value(o.attribute, o.value):
                    agree += 1
                elif o.attribute in DISTINGUISHING:
                    conflict += 1
        return agree, conflict

    async def _by_candidates(self, e: ExtractedEntity, rep: IngestReport) -> tuple[str | None, str]:
        if e.type == "Person":
            # Memory is one user's: a person whose names agree with the one person already known is that person.
            people = self.store.entities("Person")
            if len(people) == 1 and not self._conflicts(e, people[0]["id"]):
                known = " ".join(f["value"] for f in self.store.current_facts(people[0]["id"]) if f["attribute"] in ("name", "first_name", "last_name"))
                if any(normalize_key_value("name", o.value).split()[0] in normalize_key_value("name", known).split()
                       for o in e.observations if o.attribute in ("name", "first_name", "last_name") and o.value.strip()):
                    return people[0]["id"], "rule"
        query = " ".join(o.value for o in e.observations)
        cands = []
        for eid, _ in self.store.search(query, types=[e.type], limit=5):
            agree, conflict = self._agreement(e, eid)
            if conflict == 0 and agree >= 1:
                cands.append((agree, eid))
        if not cands:
            return None, "new"
        cands.sort(key=lambda t: -t[0])
        agree, best = cands[0]
        has_distinguishing = any(o.attribute in DISTINGUISHING for o in e.observations)
        if agree >= 3 and (len(cands) == 1 or cands[1][0] < agree):
            return best, "rule"
        if agree >= 2 and not has_distinguishing and len(cands) == 1:
            return best, "rule"
        # Thin evidence: let the model decide between this description and the best candidate.
        a = "; ".join(f"{o.attribute}: {o.value}" for o in e.observations)
        b = "; ".join(f"{f['attribute']}: {f['value']}" for f in self.store.current_facts(best))
        res = await asyncio.to_thread(self.adapter.call, "same_entity", f"TYPE: {e.type}\n\nA (new source): {a}\n\nB (in memory): {b}\n",
                                      instructions=SAME_ENTITY_INSTRUCTIONS, data_scope=self.data_scope)
        rep.model_calls += 1
        rep.cost_usd += res.cost_at_standard_usd
        return (best, "model") if res.parsed and res.parsed.same else (None, "new")  # type: ignore[union-attr]
