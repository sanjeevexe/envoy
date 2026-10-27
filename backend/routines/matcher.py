"""Matching a request to a routine (design doc, App routines › Running a routine).

Four filters: the app, the intent patterns, similarity of descriptions, then one model call (Muse
Spark, low effort) that confirms the best candidates and fills the routine's inputs from the request
and the notes. Values the model returns are kept only if they really appear in the request or the
notes, so a guessed input can't send a routine to the wrong booking.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from models.adapter import DataScope, ModelAdapter
from models.prompts import MATCH_INSTRUCTIONS, match_input
from models.schemas import MatchOutput
from routines.model import Routine
from routines.screens import contains_value, norm, tokens
from routines.store import RoutineStore

_STOP = {"the", "a", "an", "my", "me", "to", "for", "on", "of", "in", "and", "is", "what", "whats", "s", "i", "it", "from", "with", "do", "does", "please"}
SHORTLIST_FLOOR = 0.12


def _words(s: str) -> set[str]:
    return {t for t in tokens(s) if t not in _STOP and not any(ch.isdigit() for ch in t)}


def _overlap(a: set[str], b: set[str]) -> float:
    return len(a & b) / max(1, len(a)) if a and b else 0.0


@dataclass
class MatchResult:
    routine: Routine | None
    inputs: dict[str, str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    stage: str = ""  # which filter decided
    candidates: list[tuple[str, float]] = field(default_factory=list)
    model_calls: int = 0
    cost_usd: float = 0.0


class RoutineMatcher:
    def __init__(self, store: RoutineStore, adapter: ModelAdapter | None = None, *, data_scope: DataScope = "real",
                 contributor: bool = False) -> None:
        self.store = store
        self.adapter = adapter or ModelAdapter()
        self.data_scope = data_scope
        self.contributor = contributor

    def shortlist(self, request: str, app: str | None = None, k: int = 3) -> list[tuple[Routine, float]]:
        """Filters 1–3 in code: app, intent patterns, description similarity."""
        req = _words(request)
        out = []
        for r in self.store.active():
            if app and r.app != app:
                continue
            pattern = max((_overlap(_words(p), req) for p in r.patterns), default=0.0)  # how much of a pattern the request says
            desc = _overlap(req, _words(r.intent + " " + r.description))  # how much of the request the routine covers
            score = 0.6 * pattern + 0.4 * desc
            if score >= SHORTLIST_FLOOR:
                out.append((r, round(score, 3)))
        out.sort(key=lambda t: -t[1])
        return out[:k]

    async def match(self, request: str, memory: str = "", app: str | None = None, task_id: str | None = None) -> MatchResult:
        cands = self.shortlist(request, app)
        res = MatchResult(None, candidates=[(r.routine, s) for r, s in cands])
        if not cands:
            res.stage = "no candidate passed the app, pattern and description filters"
            return res
        lines = []
        for r, _ in cands:
            ins = "; ".join(f"{n} ({s.type}: {s.description}" + (f", memory: {s.from_memory}" if s.from_memory else "") + ")" for n, s in r.inputs.items())
            lines.append(f"- {r.routine}: {r.intent}. {r.description} Inputs: {ins or 'none'}")
        out = await asyncio.to_thread(self.adapter.call, "match", match_input(request, memory, "\n".join(lines)), instructions=MATCH_INSTRUCTIONS,
                                      data_scope=self.data_scope, contributor=self.contributor, task_id=task_id)
        res.model_calls, res.cost_usd = 1, out.cost_at_standard_usd
        m: MatchOutput = out.parsed  # type: ignore[assignment]
        chosen = next((r for r, _ in cands if r.routine == m.routine), None)
        if chosen is None or not m.confident:
            res.stage = f"model: no confident match ({m.routine})"
            return res
        res.routine, res.stage = chosen, "model confirmed"
        given = {v.name: v for v in m.inputs}
        for name in chosen.inputs:
            v = given.get(name)
            value = (v.value or "").strip() if v else ""
            source_text = request if v and v.source == "request" else memory if v and v.source == "notes" else ""
            if value and (contains_value(source_text, value) or norm(value) in norm(source_text)):
                res.inputs[name] = value
            else:
                res.missing.append(name)
        return res
