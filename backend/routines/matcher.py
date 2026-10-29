"""Matching a request to a routine (design doc, App routines › Running a routine).

Four filters: the app, the intent patterns, similarity of descriptions, then one model call (Muse
Spark, low effort) that confirms the best candidates and fills the routine's inputs from the request
and the notes. Values the model returns are kept only if they really appear in the request or the
notes, so a guessed input can't send a routine to the wrong booking. A date or time the request
implies ("tomorrow", "at 17h ... for 30 mins") is worked out in code from the phone's date
(routines/dates.py), and a value found there is kept too.

Close calls: when the runner-up scores within CLOSE_GAP of the pick and the request says no word that sets the pick
apart from it ("a Caffè Latte on DoorDash" says neither "price" nor "first restaurant"), no routine runs: the result
names both (`ambiguous`), and the caller asks the user or hands the request to the agent.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import date

from models.adapter import DataScope, ModelAdapter
from models.prompts import MATCH_INSTRUCTIONS, match_input
from models.schemas import MatchOutput
from routines.dates import facts
from routines.model import InputSpec, Routine
from routines.screens import contains_value, norm, tokens
from routines.store import RoutineStore

_STOP = {"the", "a", "an", "my", "me", "to", "for", "on", "of", "in", "and", "is", "what", "whats", "s", "i", "it", "from", "with", "do", "does", "please"}
SHORTLIST_FLOOR = 0.12
FALLBACK_K = 5
CLOSE_GAP = 0.15  # candidates this close on words are told apart only by a word the request says
# Examples shown to the model as a format ("16", "2023-10-29", "14:00"): dates, times and small numbers, never a code.
_FORMAT_EXAMPLE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}(:\d{2})?\s*(h|am|pm)?|\d{1,2}/\d{1,2}(/\d{2,4})?", re.I)


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
    ambiguous: list[str] = field(default_factory=list)  # the close candidates, when the request doesn't pick one


def _what(r: Routine) -> set[str]:
    """The words that say what a routine does and returns, without its example inputs ("pizza")."""
    examples = set().union(*(_words(s.example or "") for s in r.inputs.values())) if r.inputs else set()
    return _words(" ".join([r.intent, r.description, *r.patterns])) - examples


def close_call(request: str, chosen: Routine, cands: list[tuple[Routine, float]]) -> Routine | None:
    """The runner-up when the request names nothing the pick does beyond its app ("a Caffè Latte on DoorDash": no
    "price", no "restaurant") and the two report different things; else None. Words decide only when they matched at
    all: below the shortlist floor the request is a paraphrase ("is it on time"), and the model's pick stands."""
    score = dict((r.routine, sc) for r, sc in cands)
    req = _words(request)
    mine = score.get(chosen.routine, 0.0)
    if mine < SHORTLIST_FLOOR or req & (_what(chosen) - _words(chosen.app.replace(".", " "))):
        return None
    for r, sc in cands:
        if r.routine != chosen.routine and sc >= mine - CLOSE_GAP and {norm(o) for o in r.outputs} != {norm(o) for o in chosen.outputs}:
            return r
    return None


class RoutineMatcher:
    def __init__(self, store: RoutineStore, adapter: ModelAdapter | None = None, *, data_scope: DataScope = "real",
                 contributor: bool = False) -> None:
        self.store = store
        self.adapter = adapter or ModelAdapter()
        self.data_scope = data_scope
        self.contributor = contributor

    def shortlist(self, request: str, app: str | None = None, k: int = 3) -> list[tuple[Routine, float]]:
        """Filters 1–3 in code: app, intent patterns, description similarity. Words can't see paraphrases
        ("is it on time" = status), so when nothing passes, the model sees the best few anyway."""
        req = _words(request)
        scored = []
        for r in self.store.active():
            if app and r.app != app:
                continue
            pattern = max((_overlap(_words(p), req) for p in r.patterns), default=0.0)  # how much of a pattern the request says
            desc = _overlap(req, _words(r.intent + " " + r.description))  # how much of the request the routine covers
            scored.append((r, round(0.6 * pattern + 0.4 * desc, 3)))
        scored.sort(key=lambda t: -t[1])
        passed = [t for t in scored if t[1] >= SHORTLIST_FLOOR]
        return passed[:k] if passed else scored[:FALLBACK_K]

    async def match(self, request: str, memory: str = "", app: str | None = None, task_id: str | None = None,
                    today: date | None = None) -> MatchResult:
        """`today` is the phone's date (an emulator's can differ from this Mac's); this Mac's when not given."""
        cands = self.shortlist(request, app)
        res = MatchResult(None, candidates=[(r.routine, s) for r, s in cands])
        if not cands:
            res.stage = "no routine for this app"
            return res
        lines = []
        for r, _ in cands:
            ins = "; ".join(f"{n} ({_describe(s)})" for n, s in r.inputs.items())
            lines.append(f"- {r.routine}: {r.intent}. {r.description} Inputs: {ins or 'none'}")
        computed = "\n".join(facts(request, today or date.today()))
        out = await asyncio.to_thread(self.adapter.call, "match", match_input(request, memory, "\n".join(lines), computed),
                                      instructions=MATCH_INSTRUCTIONS, data_scope=self.data_scope, contributor=self.contributor,
                                      task_id=task_id)
        res.model_calls, res.cost_usd = 1, out.cost_at_standard_usd
        m: MatchOutput = out.parsed  # type: ignore[assignment]
        chosen = next((r for r, _ in cands if r.routine == m.routine), None)
        if chosen is None or not m.confident:
            res.stage = f"model: no confident match ({m.routine})"
            return res
        if (other := close_call(request, chosen, cands)) is not None:
            res.ambiguous = [chosen.routine, other.routine]
            res.stage = f"close call: {chosen.routine} or {other.routine}; the request says nothing that tells them apart"
            return res
        res.routine, res.stage = chosen, "model confirmed"
        given = {v.name: v for v in m.inputs}
        for name in chosen.inputs:
            v = given.get(name)
            value = (v.value or "").strip() if v else ""
            source_text = {"request": request, "notes": memory, "computed": computed}.get(v.source, "") if v else ""
            # A computed value must be a whole word of a fact: the facts are full of digits ("5" is not in "2023-10-15").
            loose = v is not None and v.source != "computed" and norm(value) in norm(source_text)
            if value and (contains_value(source_text, value) or loose):
                res.inputs[name] = value
            else:
                res.missing.append(name)
        return res


def _describe(s: InputSpec) -> str:
    out = f"{s.type}: {s.description}"
    if s.example and _FORMAT_EXAMPLE.fullmatch(s.example.strip()):
        out += f", written like {s.example.strip()!r}"
    if s.from_memory:
        out += f", memory: {s.from_memory}"
    return out
