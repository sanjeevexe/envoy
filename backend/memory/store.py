"""The memory store: one SQLite database behind one writer (design doc, Shared memory).

Tables: entities, facts (two timelines), edges, sources, entity_keys (natural keys), events (append-only),
and an FTS5 index over each entity's name and current facts.

Facts over time (an idea taken from Graphiti, implemented here):
- A new value replaces the old one: the old fact's `valid_to` is set to the new one's start and it points
  to its successor. Nothing is duplicated; the history stays queryable.
- The same value seen again only refreshes `observed_at` (when it was last seen) and the confidence.
- An observation older than the current fact (an email from Oct 12 ingested after today's app screen)
  becomes history, not the current value.
- A user's own edit outranks extracted facts: a later contradicting observation is stored, flagged as a
  conflict for the user, and not applied.
Merges move one entity's facts, edges and keys into another and are reversible: the merge event records
every change, and `split` undoes it.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from memory.types import FRESHNESS, TYPES, normalize_key_value

REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "data" / "memory.db"

SCHEMA = """
create table if not exists entities (
  id text primary key, type text not null, name text not null default '', summary text default '',
  pinned integer default 0, user_edited integer default 0, created_at real, merged_into text);
create table if not exists facts (
  id text primary key, entity text not null, attribute text not null, value text not null,
  valid_from real, valid_to real, observed_at real, recorded_at real, retired_at real, retired_reason text,
  source text, confidence real, author text, superseded_by text, conflict integer default 0);
create index if not exists facts_entity on facts(entity, attribute);
create table if not exists edges (
  id text primary key, from_entity text, relation text, to_entity text, valid_from real, valid_to real,
  source text, confidence real, recorded_at real, retired_at real);
create table if not exists sources (
  id text primary key, kind text, reference text, captured_at real, snapshot text, expires_at real);
create table if not exists entity_keys (entity text, type text, key text, primary key (type, key));
create table if not exists fact_sources (fact text, source text, observed_at real, primary key (fact, source));
create table if not exists events (seq integer primary key autoincrement, time real, kind text, payload text);
create virtual table if not exists search using fts5(entity_id unindexed, type unindexed, text, tokenize='unicode61 remove_diacritics 2');
"""


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _same(attribute: str, a: str | None, b: str | None) -> bool:
    return normalize_key_value(attribute, a or "") == normalize_key_value(attribute, b or "")


@dataclass
class FactResult:
    kind: str  # new, same, replaced, history, conflict
    fact_id: str
    replaced: str | None = None  # the fact it replaced, if any


class MemoryStore:
    def __init__(self, path: Path | str = DB_PATH, clock: Callable[[], float] = time.time) -> None:
        self.path = Path(path) if str(path) != ":memory:" else path
        if isinstance(self.path, Path):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.clock = clock
        self._listeners: list[Callable[[dict], None]] = []

    # ---- events -----------------------------------------------------------------------------

    def subscribe(self, fn: Callable[[dict], None]) -> None:
        """Every change is an event (Phase 4 streams them to the web app, iPhone and MCP clients)."""
        self._listeners.append(fn)

    def _event(self, kind: str, payload: dict) -> int:
        cur = self.db.execute("insert into events(time, kind, payload) values (?,?,?)", (self.clock(), kind, json.dumps(payload, default=str)))
        ev = {"seq": cur.lastrowid, "kind": kind, **payload}
        for fn in self._listeners:
            fn(ev)
        return int(cur.lastrowid or 0)

    def events(self, after_seq: int = 0, kind: str | None = None) -> list[dict]:
        q = "select * from events where seq > ?" + (" and kind = ?" if kind else "") + " order by seq"
        rows = self.db.execute(q, (after_seq, kind) if kind else (after_seq,)).fetchall()
        return [{"seq": r["seq"], "time": r["time"], "kind": r["kind"], **json.loads(r["payload"])} for r in rows]

    # ---- sources ----------------------------------------------------------------------------

    def add_source(self, kind: str, reference: dict[str, Any], captured_at: float | None = None, snapshot: str = "") -> str:
        """Where facts came from: an app screen (app, screen, task, step), an email (id, subject, date), a routine run, the user."""
        sid = _id("src")
        self.db.execute("insert into sources values (?,?,?,?,?,?)",
                        (sid, kind, json.dumps(reference, default=str), captured_at or self.clock(), snapshot, None))
        return sid

    def source(self, sid: str) -> dict | None:
        r = self.db.execute("select * from sources where id = ?", (sid,)).fetchone()
        return {**dict(r), "reference": json.loads(r["reference"] or "{}")} if r else None

    # ---- entities ---------------------------------------------------------------------------

    def create_entity(self, type: str, name: str = "", summary: str = "") -> str:
        eid = _id(type.split()[0].lower())
        self.db.execute("insert into entities(id, type, name, summary, created_at) values (?,?,?,?,?)", (eid, type, name, summary, self.clock()))
        self._event("entity_created", {"entity": eid, "type": type, "name": name})
        self._reindex(eid)
        return eid

    def resolve(self, eid: str) -> str:
        """Follow merges to the entity that holds the facts now."""
        seen = set()
        while eid not in seen:
            seen.add(eid)
            r = self.db.execute("select merged_into from entities where id = ?", (eid,)).fetchone()
            if r is None or not r["merged_into"]:
                return eid
            eid = r["merged_into"]
        return eid

    def entity(self, eid: str) -> dict | None:
        eid = self.resolve(eid)
        r = self.db.execute("select * from entities where id = ?", (eid,)).fetchone()
        return dict(r) if r else None

    def entities(self, type: str | None = None) -> list[dict]:
        q = "select * from entities where merged_into is null" + (" and type = ?" if type else "") + " order by created_at"
        return [dict(r) for r in self.db.execute(q, (type,) if type else ()).fetchall()]

    def add_key(self, eid: str, type: str, key: str) -> None:
        self.db.execute("insert or ignore into entity_keys values (?,?,?)", (eid, type, key))

    def find_by_key(self, type: str, key: str) -> str | None:
        r = self.db.execute("select entity from entity_keys where type = ? and key = ?", (type, key)).fetchone()
        return self.resolve(r["entity"]) if r else None

    def keys_of(self, eid: str) -> list[str]:
        return [r["key"] for r in self.db.execute("select key from entity_keys where entity = ?", (eid,)).fetchall()]

    def refresh_keys(self, eid: str) -> list[str]:
        """Register the entity's natural keys from its current facts."""
        e = self.entity(eid)
        if e is None:
            return []
        spec = TYPES.get(e["type"])
        cur = {f["attribute"]: f["value"] for f in self.current_facts(eid)}
        added = []
        for key in spec.keys if spec else ():
            if all(cur.get(a) for a in key):
                k = ",".join(key) + "=" + "|".join(normalize_key_value(a, cur[a]) for a in key)
                self.add_key(eid, e["type"], k)
                added.append(k)
        return added

    def _rename(self, eid: str) -> None:
        e = self.entity(eid)
        if e is None:
            return
        spec = TYPES.get(e["type"])
        cur = {f["attribute"]: f["value"] for f in self.current_facts(eid)}
        parts = [cur[a] for a in (spec.title if spec else ()) if cur.get(a)]
        if parts:
            self.db.execute("update entities set name = ? where id = ?", (" · ".join(parts), eid))

    # ---- facts ------------------------------------------------------------------------------

    def _row(self, r: sqlite3.Row) -> dict:
        return dict(r)

    def current(self, eid: str, attribute: str) -> dict | None:
        r = self.db.execute("select * from facts where entity = ? and attribute = ? and valid_to is null and retired_at is null and conflict = 0 "
                            "order by valid_from desc limit 1", (self.resolve(eid), attribute)).fetchone()
        return dict(r) if r else None

    def current_facts(self, eid: str) -> list[dict]:
        rows = self.db.execute("select * from facts where entity = ? and valid_to is null and retired_at is null and conflict = 0 "
                               "order by attribute", (self.resolve(eid),)).fetchall()
        return [dict(r) for r in rows]

    def history(self, eid: str, attribute: str | None = None) -> list[dict]:
        q = "select * from facts where entity = ?" + (" and attribute = ?" if attribute else "") + " order by attribute, valid_from"
        return [dict(r) for r in self.db.execute(q, (self.resolve(eid), attribute) if attribute else (self.resolve(eid),)).fetchall()]

    def conflicts(self, eid: str | None = None) -> list[dict]:
        q = "select * from facts where conflict = 1 and retired_at is null" + (" and entity = ?" if eid else "")
        return [dict(r) for r in self.db.execute(q, (self.resolve(eid),) if eid else ()).fetchall()]

    def _insert_fact(self, eid: str, attribute: str, value: str, *, valid_from: float, valid_to: float | None, observed_at: float,
                     source: str | None, confidence: float, author: str, conflict: int = 0) -> str:
        fid = _id("fact")
        self.db.execute("insert into facts(id, entity, attribute, value, valid_from, valid_to, observed_at, recorded_at, source, confidence, author, conflict) "
                        "values (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (fid, eid, attribute, value, valid_from, valid_to, observed_at, self.clock(), source, confidence, author, conflict))
        if source:
            self.db.execute("insert or ignore into fact_sources values (?,?,?)", (fid, source, observed_at))
        return fid

    def sources_of(self, fid: str) -> list[dict]:
        """Every source that saw this fact, newest first (a fact seen in an email and later in the app has both)."""
        rows = self.db.execute("select source, observed_at from fact_sources where fact = ? order by observed_at desc", (fid,)).fetchall()
        return [dict(r) for r in rows]

    def observe(self, eid: str, attribute: str, value: str, *, source: str | None, observed_at: float | None = None,
                confidence: float = 0.9, author: str = "extracted") -> FactResult:
        """Record that `attribute` of the entity had `value` when the source was captured."""
        eid = self.resolve(eid)
        when = observed_at if observed_at is not None else self.clock()
        cur = self.current(eid, attribute)
        if cur is None:
            # An older value in the history? (an email ingested after the app showed a newer one)
            later = self.db.execute("select * from facts where entity = ? and attribute = ? and retired_at is null and conflict = 0 "
                                    "and valid_from > ? order by valid_from limit 1", (eid, attribute, when)).fetchone()
            fid = self._insert_fact(eid, attribute, value, valid_from=when, valid_to=later["valid_from"] if later else None,
                                    observed_at=when, source=source, confidence=confidence, author=author)
            kind = "history" if later else "new"
            self._event("fact_added", {"entity": eid, "fact": fid, "attribute": attribute, "value": value, "kind": kind, "author": author})
        elif _same(attribute, cur["value"], value):
            self.db.execute("update facts set observed_at = max(observed_at, ?), confidence = max(confidence, ?) where id = ?",
                            (when, confidence, cur["id"]))
            if source:
                self.db.execute("insert or ignore into fact_sources values (?,?,?)", (cur["id"], source, when))
            return FactResult("same", cur["id"])
        elif when < (cur["valid_from"] or 0):
            fid = self._insert_fact(eid, attribute, value, valid_from=when, valid_to=cur["valid_from"], observed_at=when, source=source,
                                    confidence=confidence, author=author)
            self._event("fact_added", {"entity": eid, "fact": fid, "attribute": attribute, "value": value, "kind": "history", "author": author})
            kind = "history"
        elif cur["author"] == "user" and author != "user":
            fid = self._insert_fact(eid, attribute, value, valid_from=when, valid_to=None, observed_at=when, source=source,
                                    confidence=confidence, author=author, conflict=1)
            self._event("fact_conflict", {"entity": eid, "fact": fid, "attribute": attribute, "value": value, "user_value": cur["value"]})
            return FactResult("conflict", fid)
        else:
            fid = self._insert_fact(eid, attribute, value, valid_from=when, valid_to=None, observed_at=when, source=source,
                                    confidence=confidence, author=author)
            self.db.execute("update facts set valid_to = ?, superseded_by = ? where id = ?", (when, fid, cur["id"]))
            self._event("fact_replaced", {"entity": eid, "fact": fid, "attribute": attribute, "value": value, "old": cur["value"], "old_fact": cur["id"]})
            self._after_change(eid)
            return FactResult("replaced", fid, cur["id"])
        self._after_change(eid)
        return FactResult(kind, fid)

    def user_edit(self, eid: str, attribute: str, value: str) -> FactResult:
        """An edit from Envoy's own interfaces: it outranks extracted facts and clears conflicts on that attribute."""
        eid = self.resolve(eid)
        src = self.add_source("user", {"via": "edit"})
        now = self.clock()
        cur = self.current(eid, attribute)
        fid = self._insert_fact(eid, attribute, value, valid_from=now, valid_to=None, observed_at=now, source=src, confidence=1.0, author="user")
        if cur is not None:
            self.db.execute("update facts set valid_to = ?, superseded_by = ? where id = ?", (now, fid, cur["id"]))
        self.db.execute("update facts set retired_at = ?, retired_reason = 'resolved by user edit' where entity = ? and attribute = ? and conflict = 1",
                        (now, eid, attribute))
        self.db.execute("update entities set user_edited = 1 where id = ?", (eid,))
        self._event("user_edit", {"entity": eid, "fact": fid, "attribute": attribute, "value": value})
        self._after_change(eid)
        return FactResult("replaced" if cur else "new", fid, cur["id"] if cur else None)

    def is_stale(self, fact: dict, entity_type: str, now: float | None = None) -> bool:
        ttl = FRESHNESS.get((entity_type, fact["attribute"]))
        return ttl is not None and (now or self.clock()) - (fact["observed_at"] or 0) > ttl

    def _after_change(self, eid: str) -> None:
        self._rename(eid)
        self.refresh_keys(eid)
        self._reindex(eid)
        self.db.commit()

    # ---- edges ------------------------------------------------------------------------------

    def link(self, a: str, relation: str, b: str, source: str | None = None, confidence: float = 0.9) -> str:
        a, b = self.resolve(a), self.resolve(b)
        r = self.db.execute("select id from edges where from_entity = ? and relation = ? and to_entity = ? and retired_at is null",
                            (a, relation, b)).fetchone()
        if r:
            return r["id"]
        eid = _id("edge")
        now = self.clock()
        self.db.execute("insert into edges values (?,?,?,?,?,?,?,?,?,?)", (eid, a, relation, b, now, None, source, confidence, now, None))
        self._event("linked", {"edge": eid, "from": a, "relation": relation, "to": b})
        self.db.commit()
        return eid

    def edges_of(self, eid: str) -> list[dict]:
        eid = self.resolve(eid)
        rows = self.db.execute("select * from edges where (from_entity = ? or to_entity = ?) and retired_at is null", (eid, eid)).fetchall()
        return [dict(r) for r in rows]

    def neighbors(self, eid: str, hops: int = 1) -> list[str]:
        seen = {self.resolve(eid)}
        frontier = set(seen)
        for _ in range(hops):
            nxt = set()
            for e in frontier:
                for edge in self.edges_of(e):
                    for other in (edge["from_entity"], edge["to_entity"]):
                        o = self.resolve(other)
                        if o not in seen:
                            nxt.add(o)
            seen |= nxt
            frontier = nxt
        seen.discard(self.resolve(eid))
        return sorted(seen)

    # ---- merge and split --------------------------------------------------------------------

    def merge(self, keep: str, other: str, reason: str = "") -> int:
        """Move `other` into `keep`. Same values are de-duplicated (within the merged entity only); different
        values are put back in time order. Every change is recorded so `split` can undo it."""
        keep, other = self.resolve(keep), self.resolve(other)
        if keep == other:
            return 0
        changes: dict[str, Any] = {"facts_moved": [], "edges_moved": [], "keys_moved": [], "fact_updates": []}
        for f in self.db.execute("select * from facts where entity = ?", (other,)).fetchall():
            changes["facts_moved"].append(f["id"])
        self.db.execute("update facts set entity = ? where entity = ?", (keep, other))
        for e in self.db.execute("select * from edges where from_entity = ? or to_entity = ?", (other, other)).fetchall():
            changes["edges_moved"].append({"id": e["id"], "from": e["from_entity"], "to": e["to_entity"]})
        self.db.execute("update edges set from_entity = ? where from_entity = ?", (keep, other))
        self.db.execute("update edges set to_entity = ? where to_entity = ?", (keep, other))
        for k in self.db.execute("select * from entity_keys where entity = ?", (other,)).fetchall():
            changes["keys_moved"].append(k["key"])
        self.db.execute("update entity_keys set entity = ? where entity = ?", (keep, other))
        self.db.execute("update entities set merged_into = ? where id = ?", (keep, other))
        attrs = {r["attribute"] for r in self.db.execute("select distinct attribute from facts where entity = ?", (keep,)).fetchall()}
        for a in attrs:
            changes["fact_updates"] += self._rechain(keep, a)
        seq = self._event("merged", {"keep": keep, "other": other, "reason": reason, "changes": changes})
        self._after_change(keep)
        self._reindex(other)
        return seq

    def _rechain(self, eid: str, attribute: str) -> list[dict]:
        """Put an attribute's facts back in time order after a merge: one current value, the rest history,
        repeats of the same value retired. Returns the previous field values of every fact it changed."""
        rows = [dict(r) for r in self.db.execute("select * from facts where entity = ? and attribute = ? and retired_at is null and conflict = 0 "
                                                 "order by valid_from, recorded_at", (eid, attribute)).fetchall()]
        updates: list[dict] = []
        kept: list[dict] = []
        user_current = next((r for r in reversed(rows) if r["author"] == "user"), None)
        for r in rows:
            if kept and _same(attribute, kept[-1]["value"], r["value"]):
                updates.append({"id": r["id"], "retired_at": r["retired_at"], "retired_reason": r["retired_reason"]})
                self.db.execute("update facts set retired_at = ?, retired_reason = 'same value as an earlier fact (merge)' where id = ?", (self.clock(), r["id"]))
                prev = kept[-1]
                if (r["observed_at"] or 0) > (prev["observed_at"] or 0):
                    updates.append({"id": prev["id"], "observed_at": prev["observed_at"]})
                    self.db.execute("update facts set observed_at = ? where id = ?", (r["observed_at"], prev["id"]))
                    prev["observed_at"] = r["observed_at"]
                continue
            kept.append(r)
        for i, r in enumerate(kept):
            nxt = kept[i + 1] if i + 1 < len(kept) else None
            if user_current is not None and r["id"] == user_current["id"]:
                new_to, new_sup = None, None  # the user's value stays current
            else:
                new_to, new_sup = (nxt["valid_from"], nxt["id"]) if nxt else (None, None)
            if user_current is not None and r["author"] != "user" and (r["valid_from"] or 0) > (user_current["valid_from"] or 0):
                updates.append({"id": r["id"], "conflict": r["conflict"], "valid_to": r["valid_to"], "superseded_by": r["superseded_by"]})
                self.db.execute("update facts set conflict = 1, valid_to = null, superseded_by = null where id = ?", (r["id"],))
                continue
            if r["valid_to"] != new_to or r["superseded_by"] != new_sup:
                updates.append({"id": r["id"], "valid_to": r["valid_to"], "superseded_by": r["superseded_by"]})
                self.db.execute("update facts set valid_to = ?, superseded_by = ? where id = ?", (new_to, new_sup, r["id"]))
        return updates

    def split(self, merge_seq: int) -> str:
        """Undo a merge: the other entity gets its facts, edges and keys back, and every rechained fact is restored."""
        ev = next((e for e in self.events(merge_seq - 1, "merged") if e["seq"] == merge_seq), None)
        if ev is None:
            raise KeyError(f"no merge event {merge_seq}")
        keep, other, ch = ev["keep"], ev["other"], ev["changes"]
        for u in reversed(ch["fact_updates"]):
            fid = u.pop("id")
            sets = ", ".join(f"{k} = ?" for k in u)
            self.db.execute(f"update facts set {sets} where id = ?", (*u.values(), fid))
        for fid in ch["facts_moved"]:
            self.db.execute("update facts set entity = ? where id = ?", (other, fid))
        for e in ch["edges_moved"]:
            self.db.execute("update edges set from_entity = ?, to_entity = ? where id = ?", (e["from"], e["to"], e["id"]))
        for k in ch["keys_moved"]:
            self.db.execute("update entity_keys set entity = ? where key = ? and entity = ?", (other, k, keep))
        self.db.execute("update entities set merged_into = null where id = ?", (other,))
        self._event("split", {"keep": keep, "other": other, "merge_seq": merge_seq})
        self._after_change(keep)
        self._after_change(other)
        return other

    def delete_source(self, sid: str) -> dict[str, int]:
        """The user deletes a source (an email, a screen): facts only it supports are retired and the history is
        re-chained; facts other sources also saw are kept, without this source."""
        retired = kept = 0
        touched: set[tuple[str, str]] = set()
        fids = {r["fact"] for r in self.db.execute("select fact from fact_sources where source = ?", (sid,)).fetchall()}
        fids |= {r["id"] for r in self.db.execute("select id from facts where source = ?", (sid,)).fetchall()}
        now = self.clock()
        for fid in fids:
            others = self.db.execute("select source from fact_sources where fact = ? and source != ?", (fid, sid)).fetchall()
            f = self.db.execute("select * from facts where id = ?", (fid,)).fetchone()
            if f is None:
                continue
            if others:
                self.db.execute("update facts set source = ? where id = ? and source = ?", (others[0]["source"], fid, sid))
                kept += 1
            else:
                self.db.execute("update facts set retired_at = ?, retired_reason = 'source deleted by the user' where id = ?", (now, fid))
                retired += 1
            touched.add((f["entity"], f["attribute"]))
        self.db.execute("delete from fact_sources where source = ?", (sid,))
        self.db.execute("update sources set snapshot = '', reference = '{}' where id = ?", (sid,))
        for eid, attr in touched:
            # The previous value becomes current again if the retired one had replaced it.
            self.db.execute("update facts set valid_to = null, superseded_by = null where entity = ? and attribute = ? and retired_at is null "
                            "and superseded_by in (select id from facts where retired_at is not null)", (eid, attr))
            self._after_change(eid)
        self._event("source_deleted", {"source": sid, "facts_retired": retired, "facts_kept": kept})
        self.db.commit()
        return {"retired": retired, "kept": kept}

    # ---- search -----------------------------------------------------------------------------

    def _reindex(self, eid: str) -> None:
        self.db.execute("delete from search where entity_id = ?", (eid,))
        e = self.db.execute("select * from entities where id = ?", (eid,)).fetchone()
        if e is None or e["merged_into"]:
            return
        text = " ".join([e["type"], e["name"] or "", e["summary"] or ""] + [f"{f['attribute']} {f['value']}" for f in self.current_facts(eid)])
        self.db.execute("insert into search values (?,?,?)", (eid, e["type"], text))

    def search(self, query: str, types: Iterable[str] | None = None, limit: int = 10) -> list[tuple[str, float]]:
        """Keyword search (FTS5, BM25). Returns (entity id, rank) with the best first."""
        words = [w for w in "".join(ch if ch.isalnum() else " " for ch in query).split() if len(w) > 1]
        if not words:
            return []
        q = " OR ".join(f'"{w}"' for w in words)
        rows = self.db.execute("select entity_id, type, bm25(search) as r from search where search match ? order by r limit ?", (q, limit * 3)).fetchall()
        allowed = set(types) if types else None
        out = [(r["entity_id"], -float(r["r"])) for r in rows if allowed is None or r["type"] in allowed]
        return out[:limit]

    def commit(self) -> None:
        self.db.commit()
