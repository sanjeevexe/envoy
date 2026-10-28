"""App notes: short facts about how an app works, written and kept up by Envoy from its own runs.

"SkyLark: the gate is on the trip detail screen, under Flight." "DoorDash: the first result can be an ad labeled
Sponsored." A note is about the app, never the user: no names, bookings, orders, addresses or account details.

Notes live in the memory graph as `App note` entities linked `about` → the app's `App` entity, so they use memory's own
provenance and replacement:
- every run that saw a note is a `task_trace` source (task, step, screenshot, outcome) on the note's `text` fact, so
  confirmations = the fact's sources, last confirmed = its `observed_at`, first seen = the entity's creation;
- an updated note is a new `text` value (the old one stays as history); retiring sets `status` to `retired`.
Retrieval, memory answers, the Memory graph and change alerts skip them: they are not facts about you.

Writing: after a task (or a routine run that needed a repair) ends, one Muse Spark call (job `app_note`) reads a compact
trace with the app's current notes and proposes 0-3 operations (add, confirm, update, retire). Code then drops anything
personal or specific to this run, turns near-duplicates into confirmations and caps each app at MAX_PER_APP notes.
Reading: the agent's plan and step prompts and routine repairs get the app's top notes (`for_prompt`), and each trace
step records which notes it saw.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from memory.redact import redact_text
from memory.store import MemoryStore
from memory.types import normalize_key_value
from models.adapter import DataScope, ModelAdapter

NOTE_TYPE = "App note"
SOURCE_KIND = "task_trace"
MAX_PER_APP = 15
MAX_OPS = 3
PROMPT_TOP = 6
PROMPT_CHARS = 600
MAX_TEXT = 160
DUPLICATE_OVERLAP = 0.6
# Entity types whose values are the user's own data: never allowed in a note.
PERSONAL_TYPES = ("Person", "Trip", "Flight", "Reservation", "Order", "Item", "Place", "Account", "Loyalty program", "Subscription", "Event")

_STOP = {"the", "a", "an", "is", "are", "to", "of", "on", "in", "and", "or", "for", "it", "its", "be", "can", "must", "before", "after",
         "with", "from", "that", "this", "as", "at", "by", "when", "then", "there", "first", "screen", "app", "shows", "show", "tap"}
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
_PHONE = re.compile(r"\+?\d[\d\s().-]{6,}\d")
_PRICE = re.compile(r"[$€£]\s?\d|\b\d+[.,]\d{2}\b")
_TIME = re.compile(r"\b\d{1,2}:\d{2}\b|\b\d{1,2}\s?(am|pm)\b", re.I)
_DATE = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2}\b", re.I)
_ADDRESS = re.compile(r"\b\d+\s+\w+(\s\w+)?\s+(st|street|ave|avenue|rd|road|blvd|boulevard|dr|drive|way|ln|lane|ct|court|pl|place)\b", re.I)
_MIXED = re.compile(r"\b(?=[A-Za-z]*\d)(?=\d*[A-Za-z])[A-Za-z0-9]{3,}\b")  # codes, gates, seats, flight numbers: KX7Q2M, B12, 14C
_NUMBER = re.compile(r"\d{2,}")


def enabled() -> bool:
    return os.environ.get("ENVOY_APP_NOTES", "on").strip().lower() not in ("off", "0", "false", "no")


@dataclass
class AppNote:
    id: str
    app: str
    text: str
    status: str
    confirmations: int
    first_seen: float
    last_confirmed: float
    sources: list[dict[str, Any]] = field(default_factory=list)  # each sighting: task, step, screenshot, outcome

    def to_json(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class PromptNotes:
    text: str  # the APP NOTES section, or "" when the app has none
    ids: list[str] = field(default_factory=list)


@dataclass
class LearnReport:
    app: str
    proposed: list[dict[str, Any]] = field(default_factory=list)  # what the model returned
    applied: list[dict[str, Any]] = field(default_factory=list)  # what was written: {op, note, text}
    dropped: list[dict[str, Any]] = field(default_factory=list)  # {text, why}
    model_calls: int = 0
    cost_usd: float = 0.0
    skipped: str = ""


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.casefold()) if len(w) > 2 and w not in _STOP}


def overlap(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    return len(wa & wb) / max(1, min(len(wa), len(wb))) if wa and wb else 0.0


def personal_reason(text: str, forbidden: set[str] | None = None, exact: set[str] | None = None) -> str | None:
    """Why a proposed note can't be kept (personal data, or a value from this one run), or None.
    `forbidden`: values (memory's, the run's inputs and outputs) matched in any case; `exact`: names from the request or
    answer ("Chicago"), matched as written, so a note may still say "status" when an answer said "Status: On time"."""
    if redact_text(text) != text:
        return "redacted content (a code, card or ID number)"
    for name, rx in (("an email address", _EMAIL), ("a phone number", _PHONE), ("a price", _PRICE), ("a time", _TIME), ("a date", _DATE),
                     ("an address", _ADDRESS), ("a code or number from the run", _MIXED), ("a number from the run", _NUMBER)):
        if rx.search(text):
            return f"contains {name}"
    folded = f" {normalize_key_value('name', text)} "
    for v in forbidden or set():
        nv = normalize_key_value("name", v)
        if len(nv) >= 3 and re.search(rf"(?<![0-9a-z]){re.escape(nv)}(?![0-9a-z])", folded):
            return f"contains a value from this run or from memory ({v!r})"
    for v in exact or set():
        if re.search(rf"(?<![0-9A-Za-z]){re.escape(v)}(?![0-9A-Za-z])", text):
            return f"contains a name from this run ({v!r})"
    return None


def _app_words(app: str, name: str = "") -> set[str]:
    words = {w.casefold() for w in re.split(r"[.\s_-]+", app) if w}
    return words | {w.casefold() for w in name.split()}


def run_names(*texts: str, app: str = "", app_name: str = "") -> set[str]:
    """Names in a request or answer ("Chicago", "Caffè Latte"): capitalized words that don't start a sentence, except the
    app's own name. Numbers and codes are caught by the patterns already."""
    skip = _app_words(app, app_name)
    out: set[str] = set()
    for t in texts:
        for m in re.finditer(r"(?<![.!?:]\s)\b([A-Z][a-zà-ÿ]{2,})\b", t or ""):
            word = m.group(1)
            if word.casefold() not in skip and t[: m.start()].strip():  # not the first word
                out.add(word)
    return out


class AppNotes:
    """The notes of every app, kept in the memory graph."""

    def __init__(self, store: MemoryStore, adapter: ModelAdapter | None = None, *, max_per_app: int = MAX_PER_APP) -> None:
        self.store = store
        self.adapter = adapter
        self.max_per_app = max_per_app

    # ---- the app and its notes -------------------------------------------------------------------

    def _app_entity(self, app: str, create: bool = True) -> str | None:
        key = normalize_key_value("package", app)
        eid = self.store.find_by_key("App", key)
        if eid is None and create:
            eid = self.store.create_entity("App", name=app)
            self.store.observe(eid, "package", app, source=None, confidence=1.0, author="envoy")
            self.store.add_key(eid, "App", key)
        return eid

    def _note(self, eid: str) -> AppNote | None:
        e = self.store.entity(eid)
        if e is None or e["type"] != NOTE_TYPE:
            return None
        cur = {f["attribute"]: f for f in self.store.current_facts(eid)}
        text = cur.get("text")
        if text is None:
            return None
        sources = []
        for s in self.store.sources_of(text["id"]):
            src = self.store.source(s["source"]) or {}
            sources.append({"source": s["source"], "observed_at": s["observed_at"], **(src.get("reference") or {})})
        return AppNote(id=eid, app=(cur.get("app") or {}).get("value", ""), text=text["value"],
                       status=(cur.get("status") or {}).get("value", "active"), confirmations=max(1, len(sources)),
                       first_seen=e["created_at"] or 0.0, last_confirmed=text["observed_at"] or 0.0, sources=sources)

    def list(self, app: str | None = None, include_retired: bool = False) -> list[AppNote]:
        out = []
        for e in self.store.entities(NOTE_TYPE):
            if e.get("merged_into"):
                continue
            n = self._note(e["id"])
            if n is None or (app and n.app != app) or (n.status != "active" and not include_retired):
                continue
            out.append(n)
        out.sort(key=lambda n: (-n.confirmations, -n.last_confirmed))
        return out

    def apps(self) -> list[str]:
        return sorted({n.app for n in self.list(include_retired=True)})

    def get(self, nid: str) -> AppNote | None:
        return self._note(nid)

    def _source(self, ref: dict[str, Any]) -> str:
        return self.store.add_source(SOURCE_KIND, ref)

    def add(self, app: str, text: str, ref: dict[str, Any]) -> str:
        eid = self.store.create_entity(NOTE_TYPE, name=text[:60])
        src = self._source({**ref, "app": app})
        self.store.observe(eid, "app", app, source=src, confidence=1.0, author="envoy")
        self.store.observe(eid, "text", text, source=src, confidence=0.8, author="envoy")
        self.store.observe(eid, "status", "active", source=src, confidence=1.0, author="envoy")
        if (aid := self._app_entity(app)) is not None:
            self.store.link(eid, "about", aid, src)
        self.store.commit()
        return eid

    def confirm(self, nid: str, ref: dict[str, Any]) -> None:
        n = self._note(nid)
        if n is None:
            return
        self.store.observe(nid, "text", n.text, source=self._source({**ref, "app": n.app}), confidence=0.9, author="envoy")
        self.store.commit()

    def update(self, nid: str, text: str, ref: dict[str, Any]) -> None:
        n = self._note(nid)
        if n is None:
            return
        self.store.observe(nid, "text", text, source=self._source({**ref, "app": n.app}), confidence=0.8, author="envoy")
        self.store.db.execute("update entities set name = ? where id = ?", (text[:60], nid))
        self.store.commit()

    def retire(self, nid: str, reason: str = "", by: str = "envoy", ref: dict[str, Any] | None = None) -> bool:
        n = self._note(nid)
        if n is None or n.status == "retired":
            return False
        src = self._source({**(ref or {}), "app": n.app, "retired_by": by, "reason": reason})
        self.store.observe(nid, "status", "retired", source=src, confidence=1.0, author="user" if by == "user" else "envoy")
        self.store.commit()
        return True

    def enforce_cap(self, app: str) -> list[str]:
        """Over the cap: retire the least confirmed (the longest unconfirmed first among equals)."""
        notes = self.list(app)
        dropped = []
        for n in sorted(notes, key=lambda n: (n.confirmations, n.last_confirmed))[: max(0, len(notes) - self.max_per_app)]:
            self.retire(n.id, f"over the cap of {self.max_per_app} notes for the app")
            dropped.append(n.id)
        return dropped

    # ---- reading ---------------------------------------------------------------------------------

    def for_prompt(self, app: str | None, top: int = PROMPT_TOP, max_chars: int = PROMPT_CHARS) -> PromptNotes:
        if not app or not enabled():
            return PromptNotes("")
        lines, ids, used = [], [], 0
        for n in self.list(app)[:top]:
            line = f"- {n.text}" + (f" (seen {n.confirmations}×)" if n.confirmations > 1 else "")
            if used + len(line) > max_chars and lines:
                break
            lines.append(line)
            ids.append(n.id)
            used += len(line)
        if not lines:
            return PromptNotes("")
        return PromptNotes(f"Learned by Envoy from earlier runs in {app} (about the app, not the user; may be out of date):\n" + "\n".join(lines), ids)

    # ---- writing ---------------------------------------------------------------------------------

    def forbidden(self) -> set[str]:
        """Every value memory holds about the user: none may appear in a note."""
        out: set[str] = set()
        for t in PERSONAL_TYPES:
            for e in self.store.entities(t):
                for f in self.store.current_facts(e["id"]):
                    if len(f["value"] or "") >= 3:
                        out.add(f["value"])
        return out

    def apply(self, app: str, ops: list[dict[str, Any]], ref: dict[str, Any], forbidden: set[str] | None = None,
              report: LearnReport | None = None, exact: set[str] | None = None) -> LearnReport:
        """Proposed operations → notes, after the personal-data filter, merging and the cap."""
        rep = report or LearnReport(app)
        bad = (forbidden or set()) | self.forbidden()
        current = {n.id: n for n in self.list(app)}
        for op in ops[:MAX_OPS]:
            kind, nid = op.get("op"), op.get("note_id") or ""
            text = " ".join((op.get("text") or "").split())[:MAX_TEXT]
            sref = {**ref, "step": op.get("step") or ref.get("step")}
            if kind in ("confirm", "retire", "update") and nid not in current:
                rep.dropped.append({"op": kind, "note_id": nid, "why": "no such active note for this app"})
                continue
            if kind == "confirm":
                self.confirm(nid, sref)
                rep.applied.append({"op": "confirm", "note": nid})
                continue
            if kind == "retire":
                self.retire(nid, op.get("reason") or "contradicted by a later run", ref=sref)
                rep.applied.append({"op": "retire", "note": nid})
                current.pop(nid, None)
                continue
            if kind not in ("add", "update") or len(text) < 8:
                rep.dropped.append({"op": kind, "text": text, "why": "empty or unknown operation"})
                continue
            if (why := personal_reason(text, bad, exact)) is not None:
                rep.dropped.append({"op": kind, "text": text, "why": why})
                continue
            if kind == "update":
                self.update(nid, text, sref)
                rep.applied.append({"op": "update", "note": nid, "text": text})
                current[nid].text = text
                continue
            dup = max(current.values(), key=lambda n: overlap(n.text, text), default=None)
            if dup is not None and overlap(dup.text, text) >= DUPLICATE_OVERLAP:
                self.confirm(dup.id, sref)
                rep.applied.append({"op": "confirm", "note": dup.id, "text": text, "merged": True})
                continue
            new = self.add(app, text, sref)
            current[new] = self._note(new)  # type: ignore[assignment]
            rep.applied.append({"op": "add", "note": new, "text": text})
        for nid in self.enforce_cap(app):
            rep.applied.append({"op": "retire", "note": nid, "why": "cap"})
        return rep

    async def learn(self, trace_dir: str | Path, *, app: str | None = None, goal: str = "", status: str = "", result: str = "",
                    inputs: dict[str, str] | None = None, outputs: dict[str, Any] | None = None, task_id: str | None = None,
                    data_scope: DataScope = "real", contributor: bool = False) -> LearnReport:
        """Read a finished run's trace and write what it teaches about the app. One Spark call; nothing if notes are off."""
        from models.prompts import APP_NOTE_INSTRUCTIONS, app_note_input
        trace = read_trace(Path(trace_dir))
        app = app or trace.get("app") or ""
        rep = LearnReport(app)
        if not enabled():
            rep.skipped = "app notes are off"
            return rep
        if not app or not trace["steps"]:
            rep.skipped = "no app or no steps in the trace"
            return rep
        adapter = self.adapter or ModelAdapter()
        current = self.list(app)
        notes_text = "\n".join(f"- {n.id}: {n.text} (seen {n.confirmations}×)" for n in current) or "(none yet)"
        content = app_note_input(app, goal or trace.get("goal", ""), f"{status or trace.get('status', '')}: {result or trace.get('result', '')}",
                                 trace["text"], notes_text)
        # The Contributor tier only ever sees our own test apps (the adapter refuses anything else).
        res = await asyncio.to_thread(adapter.call, "app_note", content, instructions=APP_NOTE_INSTRUCTIONS, data_scope=data_scope,
                                      contributor=contributor and data_scope == "test_app", task_id=f"{task_id or trace.get('task_id', 'run')}-notes")
        rep.model_calls, rep.cost_usd = 1, res.cost_at_standard_usd
        ops = [o.model_dump() for o in (res.parsed.ops if res.parsed else [])]  # type: ignore[union-attr]
        rep.proposed = ops
        values = {*(inputs or {}).values(), *[str(v) for v in (outputs or {}).values() if v]}
        names = run_names(goal or trace.get("goal", ""), result or trace.get("result", ""), app=app)
        ref = {"task_id": task_id or trace.get("task_id"), "trace": str(trace_dir), "outcome": status or trace.get("status"),
               "kind": trace.get("kind")}
        shots = trace.get("screenshots", {})
        for o in ops[:MAX_OPS]:  # one at a time, so each sighting keeps its own step's screenshot
            self.apply(app, [o], {**ref, "screenshot": shots.get(o.get("step") or 0)}, values, rep, names)
        return rep


# ---- traces → compact text --------------------------------------------------------------------------

def _screen_name(compact: str) -> str:
    lines = compact.splitlines()
    head = lines[0].split("·")[1].strip() if lines and "·" in lines[0] else ""
    first = next((re.sub(r"^\[\d+\]\s*", "", l)[:70] for l in lines[1:] if '"' in l), "")
    return f"{head} {first}".strip()


def _clip(s: Any, n: int = 90) -> str:
    s = str(s or "")
    return s if len(s) <= n else s[: n - 1] + "…"


def read_trace(trace_dir: Path, final_chars: int = 1500) -> dict[str, Any]:
    """A trace as the note writer reads it: one line per step (screen, action, effect), repairs, and the last screen."""
    out: dict[str, Any] = {"steps": [], "text": "", "screenshots": {}, "app": "", "kind": "agent"}
    run = trace_dir / "run.json"
    if run.exists():
        try:
            r = json.loads(run.read_text())
            out.update(goal=r.get("goal", ""), status=r.get("status", ""), result=r.get("result", ""), task_id=r.get("task_id"))
        except ValueError:
            pass
    path = trace_dir / "steps.jsonl"
    if not path.exists():
        return out
    lines, last_screen = [], ""
    apps: dict[str, int] = {}
    for raw in path.read_text().splitlines():
        try:
            r = json.loads(raw)
        except ValueError:
            continue
        kind, n = r.get("kind"), r.get("step")
        if kind == "action":
            sb = r.get("screen_before") or {}
            if sb.get("secure"):
                lines.append(f"{n}. (secure screen: not shown)")
                continue
            apps[sb.get("package", "")] = apps.get(sb.get("package", ""), 0) + 1
            d = r.get("decision") or {}
            act = d.get("action") or {}
            target = (r.get("target") or {}).get("label") or ""
            what = act.get("type", "?") + (f' "{_clip(target, 60)}"' if target else "") + (f' text="{_clip(act.get("text"), 40)}"' if act.get("type") == "type" else "")
            if act.get("type") in ("done", "fail"):
                what += f": {_clip(act.get('result') or act.get('reason'), 80)}"
            effect = "" if "changed" not in r else (" → changed" if r.get("changed") else " → NO CHANGE")
            if r.get("error"):
                effect = f" → rejected: {_clip(r['error'], 60)}"
            if r.get("approval") and not r["approval"].get("approved"):
                effect = " → declined by the user"
            lines.append(f"{n}. on {_clip(_screen_name(sb.get('compact', '')), 80)}: {what}{effect} (why: {_clip(d.get('reason'), 70)})")
            last_screen = (r.get("screen_after") or sb).get("compact", "") or last_screen
            if r.get("screenshot_before"):
                out["screenshots"][n] = str(trace_dir / r["screenshot_before"])
        elif kind == "routine_step":
            out["kind"] = "routine"
            line = f"{n}. routine step {r.get('id')}: {r.get('status')}" + (f" (fallback: {r.get('rung')})" if r.get("rung") else "")
            if r.get("detail"):
                line += f" — {_clip(r['detail'], 90)}"
            lines.append(line)
            for rep in r.get("repairs") or []:
                if rep.get("model"):
                    dec = rep.get("decision") or {}
                    act = dec.get("action") or {}
                    sb = rep.get("screen_before") or {}
                    lines.append(f"   repair: on {_clip(_screen_name(sb.get('compact', '')), 70)}: {act.get('type')} "
                                 f"\"{_clip(rep.get('target'), 50)}\" (why: {_clip(dec.get('reason'), 80)})")
                    if sb.get("package"):
                        apps[sb["package"]] = apps.get(sb["package"], 0) + 1
                    last_screen = (rep.get("screen_after") or {}).get("compact", "") or last_screen
        elif kind in ("popup", "handoff"):
            lines.append(f"{n}. (runtime) {kind}: {r.get('handler') or r.get('reason')}")
        elif kind == "replan":
            lines.append(f"{n}. (runtime) replanned: {_clip('; '.join((r.get('plan') or {}).get('subgoals') or []), 120)}")
    out["steps"] = lines
    out["app"] = max(apps, key=apps.get) if apps else ""  # type: ignore[arg-type]
    final = redact_text(last_screen)[:final_chars]
    out["text"] = "\n".join(lines[-40:]) + (f"\n\nLAST SCREEN:\n{final}" if final else "")
    return out
