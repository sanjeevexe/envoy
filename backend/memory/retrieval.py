"""Getting facts out (design doc, Shared memory › Getting facts out).

1. Link mentions: "my flight", "my gate", "next trip" mean the next upcoming Flight or Trip; codes, cities
   and flight numbers are found by keyword search.
2. Add those entities' neighbors (one or two links away).
3. Add keyword matches, combined by reciprocal rank fusion.
4. Keep only facts that are valid now; mark facts past their freshness.
5. Render Markdown notes within about 2,000 tokens; every fact line says where and when it was seen.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from agent.checks import answer_tokens
from memory.store import MemoryStore
from memory.types import TYPES, parse_date
from models.adapter import DataScope, ModelAdapter
from models.prompts import ANSWER_INSTRUCTIONS
from routines.screens import norm

BUDGET_CHARS = 8000  # about 2,000 tokens
RRF_K = 60
_GENERIC = re.compile(r"\b(my|the|next|upcoming|this)\s+(flight|gate|seat|boarding|trip|check[- ]?in|plane|departure)", re.I)
_TRIP_WORDS = re.compile(r"\b(trip|travel|check[- ]?in|booking)\b", re.I)
_APP_NAMES = {"com.skylark.air": "SkyLark app", "com.amazon.mShop.android.shopping": "Amazon app", "com.starbucks.mobilecard": "Starbucks app",
              "com.chipotle.ordering": "Chipotle app", "com.target.ui": "Target app", "com.dd.doordash": "DoorDash app"}
_LABELS = {"confirmation_code": "Confirmation", "depart_time": "Departs", "arrive_time": "Arrives", "boarding_time": "Boarding",
           "boarding_group": "Boarding group", "start_date": "Date", "known_traveler_number": "Known traveler number", "checked_in": "Checked in"}


@dataclass
class Notes:
    markdown: str
    entities: list[str] = field(default_factory=list)
    facts: int = 0
    stale: int = 0
    linked: list[tuple[str, str]] = field(default_factory=list)  # (entity, why)


@dataclass
class Answer:
    answer: str
    found: bool
    stale: bool
    supported: bool  # the answer's specifics appear in the notes
    notes: Notes
    model_calls: int = 0
    cost_usd: float = 0.0


def _app_name(pkg: str | None) -> str:
    return _APP_NAMES.get(pkg or "", f"{(pkg or 'app').rsplit('.', 1)[-1]} app")


class Retriever:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    # ---- when and where -----------------------------------------------------------------------

    def _now(self) -> float:
        return self.store.clock()

    def ago(self, t: float | None) -> str:
        if not t:
            return "at an unknown time"
        now = self._now()
        d = now - t
        then, today = datetime.fromtimestamp(t), datetime.fromtimestamp(now)
        clock = f"{then.hour % 12 or 12}:{then.minute:02d} {'AM' if then.hour < 12 else 'PM'}"
        if d < 90:
            return "just now"
        if d < 3600:
            return f"{int(d // 60)} min ago"
        if then.date() == today.date():
            return f"today {clock}"
        days = (today.date() - then.date()).days
        if days == 1:
            return f"yesterday {clock}"
        # The age itself, not only a date: a model answering "how long ago" reads a bare date against its own idea of today.
        return f"{days} days ago ({then:%b} {then.day})"

    def where(self, source_id: str | None) -> str:
        s = self.store.source(source_id) if source_id else None
        if s is None:
            return "source unknown"
        ref, kind = s["reference"], s["kind"]
        if kind == "app_screen":
            return f"{_app_name(ref.get('app'))}, {self.ago(s['captured_at'])}"
        if kind == "routine_run":
            return f"{_app_name(ref.get('app'))} (routine {ref.get('routine')}), {self.ago(s['captured_at'])}"
        if kind in ("email", "email_markup"):
            sender = re.sub(r"\s*<.*>", "", ref.get("from", "")) or "email"
            return f"email from {sender}, {self.ago(s['captured_at'])}"
        if kind == "user":
            return "your edit"
        if kind == "client":
            return f"note from {ref.get('author', 'an assistant')}"
        if kind == "photo":
            how = {"shortcut": "shared with Send to Envoy", "picker": "sent in the app"}.get(ref.get("origin", ""), "shared")
            return f"your screenshot ({how}), {self.ago(s['captured_at'])}"
        return f"{kind}, {self.ago(s['captured_at'])}"

    # ---- linking --------------------------------------------------------------------------------

    def _date_of(self, eid: str) -> date | None:
        cur = {f["attribute"]: f["value"] for f in self.store.current_facts(eid)}
        d = parse_date(cur.get("date") or cur.get("start_date"))
        if d is None:  # a trip known only through its flight's date
            dates = [self._own_date(n) for n in self.store.neighbors(eid) if (self.store.entity(n) or {}).get("type") == "Flight"]
            d = min((x for x in dates if x), default=None)
        return d

    def _own_date(self, eid: str) -> date | None:
        cur = {f["attribute"]: f["value"] for f in self.store.current_facts(eid)}
        return parse_date(cur.get("date") or cur.get("start_date"))

    def next_upcoming(self, type_: str) -> str | None:
        today = datetime.fromtimestamp(self._now()).date()
        best = None
        for e in self.store.entities(type_):
            cur = {f["attribute"]: f["value"] for f in self.store.current_facts(e["id"])}
            if norm(cur.get("status", "")) == "cancelled":
                continue
            trip = next((n for n in self.store.neighbors(e["id"]) if (self.store.entity(n) or {}).get("type") == "Trip"), None)
            if trip and norm((self.store.current(trip, "status") or {}).get("value", "")) == "cancelled":
                continue
            d = self._date_of(e["id"])
            if d is None or d < today:
                continue
            if best is None or d < best[0]:
                best = (d, e["id"])
        return best[1] if best else None

    def link_mentions(self, request: str) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        explicit = self.store.search(request, types=("Trip", "Flight", "Order", "Reservation", "Loyalty program"), limit=5)
        specific = [eid for eid, _ in explicit if self._specific_match(eid, request)]
        for eid in specific:
            out.append((eid, "named in the request"))
        if not specific and _GENERIC.search(request):
            for t in ("Flight", "Trip"):
                if (eid := self.next_upcoming(t)) is not None:
                    out.append((eid, f"the next upcoming {t.lower()}"))
        return out

    def _specific_match(self, eid: str, request: str) -> bool:
        """The request names this entity: one of its distinguishing values (city, code, number) appears in it."""
        req = norm(request)
        for f in self.store.current_facts(eid):
            if f["attribute"] in ("destination", "confirmation_code", "number", "order_number", "merchant", "name", "program") and f["value"]:
                v = norm(f["value"])
                if len(v) >= 3 and re.search(rf"(?<![0-9a-z]){re.escape(v)}(?![0-9a-z])", req):
                    return True
                if f["attribute"] == "number" and re.sub(r"\s", "", v) in re.sub(r"\s", "", req):
                    return True
        return False

    # ---- notes ----------------------------------------------------------------------------------

    def notes(self, request: str, budget_chars: int = BUDGET_CHARS, types: tuple[str, ...] | None = None) -> Notes:
        linked = self.link_mentions(request)
        lists: list[list[str]] = [[e for e, _ in linked]]
        lists.append([n for e, _ in linked for n in self.store.neighbors(e, hops=2)])
        lists.append([e for e, _ in self.store.search(request, limit=8)])
        scores: dict[str, float] = {}
        for lst in lists:
            for rank, eid in enumerate(dict.fromkeys(lst)):
                scores[eid] = scores.get(eid, 0.0) + 1.0 / (RRF_K + rank + 1)
        ordered = sorted(scores, key=lambda e: -scores[e])
        if types:
            ordered = [e for e in ordered if (self.store.entity(e) or {}).get("type") in types]
        blocks, used, out = [], 0, Notes("", linked=linked)
        why = {e: w for e, w in linked}
        for eid in ordered:
            block, n_facts, n_stale = self.render_entity(eid)
            if eid in why and block:
                head, _, rest = block.partition("\n")
                block = f"{head}  ({why[eid]})\n{rest}"
            if not n_facts:
                continue
            if used + len(block) > budget_chars and blocks:
                break
            blocks.append(block)
            used += len(block)
            out.entities.append(eid)
            out.facts += n_facts
            out.stale += n_stale
        out.markdown = "\n\n".join(blocks)
        return out

    def render_entity(self, eid: str) -> tuple[str, int, int]:
        e = self.store.entity(eid)
        if e is None:
            return "", 0, 0
        links = []
        for n in self.store.neighbors(eid):
            ne = self.store.entity(n)
            if ne and ne["type"] not in ("Note",):
                links.append(f"[[{ne['type']} {ne['name']}]]")
        head = f"## {e['type']}: {e['name'] or '(unnamed)'}" + (f"  {' '.join(links[:4])}" if links else "")
        lines, stale_n = [head], 0
        order = {a: i for i, a in enumerate(TYPES[e["type"]].attributes)} if e["type"] in TYPES else {}
        facts = sorted(self.store.current_facts(eid), key=lambda f: order.get(f["attribute"], 99))
        for f in facts:
            label = _LABELS.get(f["attribute"], f["attribute"].replace("_", " ").capitalize())
            line = f"- {label}: {f['value']}"
            prev = self.store.db.execute("select value, valid_to from facts where superseded_by = ?", (f["id"],)).fetchone()
            if prev and prev["valid_to"] and self._now() - prev["valid_to"] < 86400:
                line += f" (was {prev['value']} until {self.ago(prev['valid_to'])})"
            seen = self.store.sources_of(f["id"])
            line += f" — {self.where(seen[0]['source'] if seen else f['source'])}"
            if len(seen) > 1:
                line += f" (also {self.where(seen[-1]['source'])})"
            if self.store.is_stale(f, e["type"]):
                line += " (may be out of date: re-check before relying on it)"
                stale_n += 1
            conflict = self.store.db.execute("select value from facts where entity = ? and attribute = ? and conflict = 1 and retired_at is null",
                                             (eid, f["attribute"])).fetchone()
            if conflict:
                line += f" (you set this; a later source showed {conflict['value']})"
            lines.append(line)
        return "\n".join(lines), len(facts), stale_n

    # ---- answers --------------------------------------------------------------------------------

    async def answer(self, question: str, adapter: ModelAdapter, *, data_scope: DataScope = "real", task_id: str | None = None) -> Answer:
        notes = self.notes(question)
        if not notes.markdown:
            return Answer("Memory doesn't have that yet.", False, False, True, notes)
        now = datetime.fromtimestamp(self._now())
        res = await asyncio.to_thread(adapter.call, "answer", f"NOW: {now:%a %b} {now.day}, {now:%Y %I:%M %p}\n\nQUESTION: {question}\n\nNOTES:\n{notes.markdown}\n",
                                      instructions=ANSWER_INSTRUCTIONS,
                                      data_scope=data_scope, task_id=task_id)
        a = res.parsed
        toks = [t for t in answer_tokens(a.answer) if any(ch.isdigit() for ch in t)]  # type: ignore[union-attr]
        supported = all(norm(t) in norm(notes.markdown) for t in toks)
        return Answer(a.answer, a.found and supported, a.stale, supported, notes, 1, res.cost_at_standard_usd)  # type: ignore[union-attr]
