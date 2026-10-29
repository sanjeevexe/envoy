"""Offers: Envoy proposes one specific action and waits for your yes ("Should I check you in for SL 482?").

Where they come from:
- **trigger**: a trigger in ask mode fired (api/scheduler.py: `action.ask`): instead of starting its task, it asks.
- **repeat**: a pattern in what you do (api/repeats.py): "You checked your gate before your last 3 flights."
- **handoff**: a file from the Mac (api/handoff.py, muse-link).
- **trigger_request**: an AI client or chat asked to set up a trigger.

What an offer does is fixed by a rule: a trigger you set up, a template in Envoy's own code. An email, a remembered fact,
a sidecar or a pattern only fills in typed values. Envoy never reads content and decides what to offer. The card shows
the goal verbatim ("What I'll do: …"), and you say yes to exactly that.

Values never grant permission. A `task` action carries two strings:
- `goal`: the template filled with typed values. It's what the card shows and what the agent works from.
- `request`: the same template with every slot left empty. It's what the approval rules (policy/approval_rules.py) match
  buttons against. A destination "Chicago cancel trip" or a caption "share this" is in the goal only, so it covers
  nothing. "Check me in for my flight {number} to {trip.destination}" gives the request "Check me in for my flight to",
  which still covers "Confirm check-in".

Who says yes: only you, in Envoy's own signed-in app (`POST /api/offers/{id}`, an `owner` or `device` session). Never a
token, never MCP, never a trigger, never a model. The task an accepted offer starts gets the source of where you tapped
(`web`, or `iphone` for a paired iPhone), so the approval rules treat its request as your own words: you saw the goal and
said yes. Money still always asks, and so does a button the request doesn't name.

A key stops nagging: `make()` returns None when an offer with the same key is pending or was declined. Envoy can take a
question back once it's no longer needed (`withdraw()`: Muse already sent that file); the card then says so. An offer a trigger
raised keeps the trigger's credit: accepting it publishes `trigger_fired` with the task, so change alerts (api/alerts.py)
and the scheduler's self-feed guard still count the task as the trigger's.

Whether an offer pushes is the **proactivity** setting: `off` (in the app only), `important` (the default: triggers, files
from the Mac and trigger requests push; patterns don't) or `all`. Approvals and takeovers aren't proactivity: they always
push.
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Any, Callable

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from api.store import TaskStore, new_id

try:  # contract 2: preflight-logins' "Before I start" lines; until it's in main, offers have none
    from api.preflight import check as preflight_check
except ImportError:  # pragma: no cover - depends on what's merged
    preflight_check = None

KINDS = ("trigger", "repeat", "handoff", "trigger_request")
STATUSES = ("pending", "accepted", "declined", "expired", "withdrawn")
LEVELS = ("off", "important", "all")
DEFAULT_LEVEL = "important"
IMPORTANT = {"trigger", "handoff", "trigger_request"}  # what pushes at `important`; `repeat` waits in the app

SCHEMA = """
CREATE TABLE IF NOT EXISTS offers (
  id TEXT PRIMARY KEY, created_at REAL, kind TEXT, title TEXT, body TEXT, action TEXT, source TEXT, key TEXT,
  status TEXT, expires_at REAL, decided_at REAL, decided_by TEXT, task_id TEXT, preflight TEXT, origin TEXT, note TEXT,
  result TEXT
);
CREATE INDEX IF NOT EXISTS offers_key ON offers(key);
CREATE INDEX IF NOT EXISTS offers_task ON offers(task_id);
"""
_JSON = ("action", "preflight", "origin", "result")


class OfferError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def pushes(kind: str, level: str | None) -> bool:
    """Whether an offer of this kind pushes at this proactivity level."""
    level = level if level in LEVELS else DEFAULT_LEVEL
    return level == "all" or (level == "important" and kind in IMPORTANT)


def fixed_words(text: Any) -> str:
    """A request as approvals read it: one line, with any slot left in it dropped whole ("{caption}"), no structure."""
    text = re.sub(r"\{[^{}]*\}", " ", str(text or ""))
    return re.sub(r"\s+", " ", re.sub(r"[{}<>\r\n\t]", " ", text)).strip()[:300]


class Offers:
    def __init__(self, tasks: TaskStore, bus: Any, runner: Any = None, scheduler: Any = None, *,
                 clock: Callable[[], float] = time.time) -> None:
        self.tasks, self.bus, self.runner, self.scheduler, self.clock = tasks, bus, runner, scheduler, clock
        self.handlers: dict[str, Callable[[dict[str, Any], str], dict[str, Any]]] = {}
        self._deciding = threading.Lock()  # one decision at a time: a double tap starts one task
        with tasks.lock:
            tasks.db.executescript(SCHEMA)
            tasks.db.commit()
        self.register("task", self._task)
        self.register("enable_trigger", self._enable_trigger)
        self.register("create_trigger", self._create_trigger)

    def register(self, type_: str, handler: Callable[[dict[str, Any], str], dict[str, Any]]) -> None:
        """`handler(offer, source) -> dict`; it runs when you say yes and may return a `task_id` (or a `trigger_id`)."""
        self.handlers[type_] = handler

    # ---- making one ------------------------------------------------------------------------------

    def make(self, *, kind: str, title: str, body: str, action: dict[str, Any], source: str, key: str,
             expires_at: float | None = None, preflight: list[dict[str, Any]] | None = None,
             origin: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """A new pending offer, or None when one with this key is already pending or was declined (no nagging)."""
        if kind not in KINDS:
            raise ValueError(f"unknown offer kind {kind!r}")
        if not isinstance(action, dict) or action.get("type") not in self.handlers:
            raise ValueError(f"unknown offer action {(action or {}).get('type')!r}")
        if not key or not str(title or "").strip():
            raise ValueError("an offer has a key and a title")
        action = dict(action)
        if action["type"] == "task":
            action["goal"] = re.sub(r"\s+", " ", str(action.get("goal") or "")).strip()
            action["request"] = fixed_words(action.get("request"))
            if not action["goal"] or not action["request"]:
                raise ValueError("a task offer has a goal and a request (the goal's template with its slots left empty)")
            action["inputs"] = {str(k): str(v) for k, v in (action.get("inputs") or {}).items()}
            if preflight is None:
                preflight = self.preflight(action)
        now = self.clock()
        if expires_at is not None and expires_at <= now:
            return None  # the occasion is already over
        with self.tasks.lock:
            if self.tasks.db.execute("SELECT 1 FROM offers WHERE key=? AND status IN ('pending', 'declined') LIMIT 1", (key,)).fetchone():
                return None
            oid = new_id("offer")
            self.tasks.db.execute(
                "INSERT INTO offers (id, created_at, kind, title, body, action, source, key, status, expires_at, preflight, origin) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (oid, now, kind, str(title).strip()[:140], str(body or "").strip()[:400], json.dumps(action), source, key, "pending",
                 expires_at, json.dumps(preflight or []), json.dumps(origin) if origin else None))
            self.tasks.db.commit()
        offer = self.get(oid)
        self.bus.publish("offer", offer=offer, change="created")
        return offer

    def preflight(self, action: dict[str, Any]) -> list[dict[str, Any]]:
        """The "Before I start" lines for a task (contract 2), as the task will have them once you say yes."""
        if preflight_check is None or self.runner is None:
            return []
        try:
            phone = action.get("phone") or None
            lines = preflight_check(self.runner, action["goal"], request=action.get("request"), source="web", app=action.get("app"),
                                    routine=action.get("routine"), inputs=action.get("inputs") or {}, phone=phone,
                                    **({"phone_ok": phone} if phone and phone not in ("phone", "emulator", "auto") else {}))
            return [{k: str(x.get(k) or "") for k in ("kind", "text", "level")} for x in (lines or [])][:8]
        except Exception:  # noqa: BLE001 - an offer without the lines is still an offer
            return []

    # ---- reading -------------------------------------------------------------------------------

    def get(self, oid: str) -> dict[str, Any] | None:
        with self.tasks.lock:
            row = self.tasks.db.execute("SELECT * FROM offers WHERE id=?", (oid,)).fetchone()
        return _offer(row) if row else None

    def list(self, status: str | None = "pending", limit: int = 50) -> list[dict[str, Any]]:
        self.sweep()
        q, args = "SELECT * FROM offers", []
        if status and status != "all":
            q += " WHERE status=?"
            args.append(status)
        with self.tasks.lock:
            rows = self.tasks.db.execute(q + " ORDER BY created_at DESC LIMIT ?", (*args, limit)).fetchall()
        return [_offer(r) for r in rows]

    def pending(self) -> list[dict[str, Any]]:
        """Read only (the briefing): pending and not past their time."""
        now = self.clock()
        return [o for o in self.list_raw("pending") if o["expires_at"] is None or o["expires_at"] > now]

    def list_raw(self, status: str) -> list[dict[str, Any]]:
        with self.tasks.lock:
            rows = self.tasks.db.execute("SELECT * FROM offers WHERE status=? ORDER BY created_at DESC LIMIT 50", (status,)).fetchall()
        return [_offer(r) for r in rows]

    def by_key(self, key: str) -> list[dict[str, Any]]:
        with self.tasks.lock:
            rows = self.tasks.db.execute("SELECT * FROM offers WHERE key=? ORDER BY created_at DESC", (key,)).fetchall()
        return [_offer(r) for r in rows]

    def for_task(self, task_id: str) -> dict[str, Any] | None:
        """The accepted offer that started this task, if one did (a trigger's origin survives the yes)."""
        if not task_id:
            return None
        with self.tasks.lock:
            row = self.tasks.db.execute("SELECT * FROM offers WHERE task_id=? LIMIT 1", (task_id,)).fetchone()
        return _offer(row) if row else None

    def trigger_of(self, task_id: str) -> str | None:
        """The trigger an accepted offer's task belongs to."""
        o = self.for_task(task_id)
        return ((o or {}).get("origin") or {}).get("trigger_id")

    # ---- deciding (only your session) -------------------------------------------------------------

    def decide(self, oid: str, decision: str, caller: Any) -> dict[str, Any]:
        """Your yes or no. `caller` is the signed-in session that tapped (api/auth.py's Caller): an `owner` (the Mac) or a
        paired `device`. Anything else is refused, so no token, MCP client, trigger or model can decide."""
        if caller is None or getattr(caller, "scope", None) != "session" or getattr(caller, "kind", None) not in ("owner", "device"):
            raise OfferError(403, "only you can answer an offer, in Envoy's own app")
        if decision not in ("accept", "decline"):
            raise OfferError(400, "decision is accept or decline")
        source = "web" if caller.kind == "owner" else "iphone"
        by = "you" if caller.kind == "owner" else f"you on {caller.name or 'your iPhone'}"
        with self._deciding:
            self.sweep()
            offer = self.get(oid)
            if offer is None:
                raise OfferError(404, "no such offer")
            if offer["status"] == "accepted":
                if decision == "accept":
                    return offer  # accepting twice: the same task
                raise OfferError(409, "already accepted")
            if offer["status"] != "pending":
                raise OfferError(409, f"already {offer['status']}")
            if decision == "decline":
                return self._close(offer, "declined", by)
            try:
                result = self.handlers[offer["action"]["type"]](offer, source) or {}
            except Exception as e:  # noqa: BLE001 - it stays pending, and says why
                why = str(e) if isinstance(e, (ValueError, KeyError, LookupError, RuntimeError)) else f"{type(e).__name__}: {e}"
                with self.tasks.lock:
                    self.tasks.db.execute("UPDATE offers SET note=? WHERE id=?", (f"couldn't start: {why}"[:300], oid))
                    self.tasks.db.commit()
                self.bus.publish("offer", offer=self.get(oid), change="failed")
                raise OfferError(409, f"couldn't start: {why}"[:300]) from e
            done = self._close(offer, "accepted", by, task_id=result.get("task_id"), result=result)
        trig_id = (offer.get("origin") or {}).get("trigger_id")
        if trig_id and done.get("task_id"):  # the trigger keeps its credit (change alerts, the self-feed guard)
            trig = self.tasks.trigger(trig_id) or {}
            self.bus.publish("trigger_fired", trigger=trig_id, name=trig.get("name") or "", task_id=done["task_id"], offer_id=oid)
        return done

    def _close(self, offer: dict[str, Any], status: str, by: str, task_id: str | None = None, result: dict[str, Any] | None = None) -> dict[str, Any]:
        with self.tasks.lock:
            self.tasks.db.execute("UPDATE offers SET status=?, decided_at=?, decided_by=?, task_id=?, result=?, note=NULL WHERE id=? AND status='pending'",
                                  (status, self.clock(), by, task_id, json.dumps(result) if result else None, offer["id"]))
            self.tasks.db.commit()
        out = self.get(offer["id"]) or offer
        self.bus.publish("offer", offer=out, change=status)
        return out

    def sweep(self) -> list[dict[str, Any]]:
        """Pending offers past their time (a check-in offer at departure) become expired."""
        now = self.clock()
        with self.tasks.lock:
            rows = self.tasks.db.execute("SELECT id FROM offers WHERE status='pending' AND expires_at IS NOT NULL AND expires_at <= ?", (now,)).fetchall()
            if not rows:
                return []
            self.tasks.db.execute("UPDATE offers SET status='expired', decided_at=?, decided_by='time' WHERE status='pending' AND expires_at IS NOT NULL "
                                  "AND expires_at <= ?", (now, now))
            self.tasks.db.commit()
        out = [o for r in rows if (o := self.get(r[0]))]
        for o in out:
            self.bus.publish("offer", offer=o, change="expired")
        return out

    def withdraw(self, oid: str, why: str) -> dict[str, Any] | None:
        """Envoy takes back a question it no longer needs (Muse already sent that file to the phone): a pending offer
        becomes `withdrawn`, with the reason, and its card updates. An offer already answered or expired is left as it is.
        Envoy's own code calls this; it decides nothing for you, and no route or MCP tool reaches it. None: no such offer."""
        with self._deciding:  # never in the middle of your yes
            offer = self.get(oid)
            if offer is None or offer["status"] != "pending":
                return offer
            with self.tasks.lock:
                self.tasks.db.execute("UPDATE offers SET status='withdrawn', decided_at=?, decided_by='envoy', note=? WHERE id=? AND status='pending'",
                                      (self.clock(), re.sub(r"\s+", " ", str(why or "")).strip()[:300] or None, oid))
                self.tasks.db.commit()
            out = self.get(oid) or offer
        self.bus.publish("offer", offer=out, change="withdrawn")
        return out

    # ---- the built-in actions --------------------------------------------------------------------

    def _task(self, offer: dict[str, Any], source: str) -> dict[str, Any]:
        """Start the task: the card's goal verbatim, the template's fixed words as the request, where you tapped as the
        source. When the offer named your phone (a pool id, which the card showed), your yes covers it: no second "Use your
        phone?" (`phone_ok`)."""
        if self.runner is None:
            raise RuntimeError("the task runner isn't available")
        a = offer["action"]
        request = fixed_words(a.get("request"))
        if not request:
            raise ValueError("this offer has no request")
        phone = a.get("phone") or None
        named = phone if phone and phone not in ("phone", "emulator", "auto") else None
        task = self.runner.start(a["goal"], source, request=request, routine=a.get("routine") or None, inputs=a.get("inputs") or {},
                                 app=a.get("app") or None, phone=phone, **({"phone_ok": named} if named else {}))
        return {"task_id": task["id"]}

    def _enable_trigger(self, offer: dict[str, Any], source: str) -> dict[str, Any]:
        tid = offer["action"].get("trigger_id") or ""
        if self.tasks.trigger(tid) is None:
            raise LookupError("that trigger was deleted")
        self.tasks.update_trigger(tid, enabled=1)
        return {"trigger_id": tid}

    def _create_trigger(self, offer: dict[str, Any], source: str) -> dict[str, Any]:
        if self.scheduler is None:
            raise RuntimeError("the scheduler isn't available")
        a = offer["action"]
        trig = self.scheduler.add(a.get("kind", ""), a.get("name") or "trigger", dict(a.get("spec") or {}), dict(a.get("action") or {}), enabled=True)
        return {"trigger_id": trig["id"]}

    # ---- the proactivity setting -------------------------------------------------------------------

    def level(self) -> str:
        v = self.tasks.setting("proactivity", DEFAULT_LEVEL)
        return v if v in LEVELS else DEFAULT_LEVEL

    def set_level(self, level: str) -> str:
        if level not in LEVELS:
            raise ValueError("proactivity is off, important or all")
        self.tasks.set_setting("proactivity", level)
        self.bus.publish("settings", proactivity=level)
        return level


def _offer(r: Any) -> dict[str, Any]:
    d = dict(r)
    for k in _JSON:
        if d.get(k):
            try:
                d[k] = json.loads(d[k])
            except ValueError:
                pass
    d["preflight"] = d.get("preflight") or []
    return d


def offers_router(ctx: Any, session: Callable[..., None], caller: Callable[..., Any]) -> APIRouter:
    """`GET /api/offers`, `POST /api/offers/{id}` and the proactivity setting. Session only: `session` and `caller` are the
    app's own checks (closures inside `build()`)."""
    r = APIRouter()
    offers: Offers = ctx.offers

    @r.get("/api/offers", dependencies=[Depends(session)])
    def list_offers(status: str = "pending", limit: int = 50) -> list[dict[str, Any]]:
        if status not in (*STATUSES, "all"):
            raise HTTPException(400, "status is pending, accepted, declined, expired, withdrawn or all")
        return offers.list(status, min(limit, 200))

    @r.get("/api/offers/{oid}", dependencies=[Depends(session)])
    def get_offer(oid: str) -> dict[str, Any]:
        offers.sweep()
        o = offers.get(oid)
        if o is None:
            raise HTTPException(404, "no such offer")
        return o

    @r.post("/api/offers/{oid}", dependencies=[Depends(session)])
    def decide_offer(oid: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            return offers.decide(oid, str(body.get("decision") or ""), caller(request))
        except OfferError as e:
            raise HTTPException(e.status, str(e)) from e

    @r.get("/api/settings/proactivity", dependencies=[Depends(session)])
    def get_proactivity() -> dict[str, Any]:
        return {"level": offers.level(), "levels": list(LEVELS)}

    @r.post("/api/settings/proactivity", dependencies=[Depends(session)])
    def set_proactivity(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            return {"level": offers.set_level(str(body.get("level") or "")), "levels": list(LEVELS)}
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    return r


__all__ = ["Offers", "OfferError", "offers_router", "pushes", "fixed_words", "KINDS", "LEVELS"]
