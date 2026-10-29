"""Home's briefing (`GET /api/briefing`): what needs you, what happened today and what's next, in a few sentences.

Read only and deterministic: no model call, nothing written. Everything comes from what the stores already hold:
- **needs you**: pending approvals, offers waiting for your yes ("Should I check you in for SL 482?", api/offers.py), tasks
  asking to use your Android phone, tasks waiting on you (a sign-in, a takeover);
- **today**: remembered facts that changed in the last day (the change alerts), tasks and routine runs that finished
  since midnight;
- **next**: triggers due in the next day (not watchers: their reruns every few minutes aren't news), marked when they
  will ask you first;
- **suggestions**: your routines, the ones you run most first.

Your name appears only when memory has it: memory is one user's, so with exactly one person in it, that person's name
as written (a capitalised name, not an email's user name).
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta
from typing import Any

from memory.retrieval import Retriever

from api.alerts import label

DAY = 86400
FINISHED = ("done", "failed", "declined")
MONEY = re.compile(r"\$|\b(pay|payment|buy|purchase|order|subscribe|checkout)\b", re.I)


def user_name(memory: Any) -> str | None:
    people = memory.entities("Person")
    if len(people) != 1:
        return None
    facts = {f["attribute"]: f["value"].strip() for f in memory.current_facts(people[0]["id"])}
    for value in (facts.get("first_name"), facts.get("name")):
        first = (value or "").split(" ")[0]
        if re.fullmatch(r"[A-Z][a-zA-Z'\-]{1,30}", first) and first.lower() != "envoy":
            return first
    return None


def _source_app(where: str) -> str:
    """'SkyLark app, 2 h ago' → 'SkyLark'."""
    return where.split(",", 1)[0].removesuffix(" app").strip()


def _clock(at: float, now: float) -> str:
    t, today = datetime.fromtimestamp(at), datetime.fromtimestamp(now).date()
    hm = t.strftime("%I:%M %p").lstrip("0")
    if t.date() == today:
        return hm
    if t.date() == today + timedelta(days=1):
        return f"{hm} tomorrow"
    return f"{hm} on {t.strftime('%a')}"


def _count(n: int, one: str, many: str) -> str:
    return f"One {one}" if n == 1 else f"{n} {many}"


def build_briefing(tasks: Any, memory: Any, routines: Any, scheduler: Any, alerts: Any, now: float | None = None, offers: Any = None) -> dict[str, Any]:
    now = time.time() if now is None else now
    midnight = datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    recent = tasks.list(200)

    # ---- needs you ----
    needs: list[dict[str, Any]] = []
    pending = tasks.approvals("pending")
    waiting = {a["task_id"] for a in pending}
    for a in pending:
        t = tasks.get(a["task_id"]) or {}
        needs.append({"kind": "approval", "id": a["id"], "task_id": a["task_id"], "title": a["description"], "detail": t.get("goal") or "",
                      "app": a.get("app") or t.get("app"), "time": a["created_at"], "money": bool(MONEY.search(a["description"] or ""))})
    asking = [o for o in (offers.pending() if offers is not None else []) if o["expires_at"] is None or o["expires_at"] > now]
    for o in asking:
        a = o.get("action") or {}
        needs.append({"kind": "offer", "id": o["id"], "offer_id": o["id"], "task_id": None, "title": o["title"], "detail": o.get("body") or "",
                      "goal": a.get("goal") or "", "action": a.get("type"), "offer_kind": o["kind"], "preflight": o.get("preflight") or [],
                      "app": a.get("app"), "time": o["created_at"], "expires_at": o.get("expires_at")})
    phone_asks = [t for t in recent if t["status"] == "needs_you" and t.get("waiting_for") == "phone"]
    for t in phone_asks:
        needs.append({"kind": "phone", "id": t["id"], "task_id": t["id"], "title": t.get("detail") or "Use your Android phone for this task?",
                      "detail": t["goal"], "app": t.get("app"), "time": t["updated_at"]})
    stuck = [t for t in recent if t["status"] in ("needs_you", "waiting_approval") and t.get("waiting_for") != "phone" and t["id"] not in waiting]
    for t in stuck:
        needs.append({"kind": "task", "id": t["id"], "task_id": t["id"], "title": t["goal"], "detail": t.get("detail") or "",
                      "status": t["status"], "app": t.get("app"), "device": t.get("device"), "time": t["updated_at"]})

    # ---- today ----
    today: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    changes = [c for c in (alerts.recent(100) if alerts else []) if (c.get("time") or 0) >= now - DAY]
    where = Retriever(memory).where
    for c in changes:  # newest first; one row per fact, its latest value
        key = (c["entity"], c["attribute"])
        if key in seen:
            continue
        seen.add(key)
        today.append({"kind": "change", "id": f"change-{c['id']}", "task_id": c.get("task_id"), "title": f"{label(c['attribute'])} changed to {c['new']}",
                      "label": label(c["attribute"]), "attribute": c["attribute"], "old": c.get("old"), "new": c.get("new"),
                      "entity": c.get("entity_label") or "", "source": _source_app(where(c.get("source"))), "time": c["time"]})
    finished = [t for t in recent if t["status"] in FINISHED and t["updated_at"] >= midnight and not t.get("parent")]
    for t in finished:
        today.append({"kind": "routine" if t.get("routine") else "task", "id": t["id"], "task_id": t["id"], "title": t["goal"],
                      "result": t.get("result") or "", "status": t["status"], "app": t.get("app"), "routine": t.get("routine"),
                      "seconds": round(max(0.0, t["updated_at"] - t["created_at"]), 1), "time": t["updated_at"]})
    today.sort(key=lambda x: -x["time"])

    # ---- next ----
    upcoming: list[dict[str, Any]] = []
    if scheduler is not None:
        for trig in tasks.triggers():
            if not trig.get("enabled") or trig["kind"] == "watch":  # a watcher's every-few-minutes reruns aren't news
                continue
            try:
                runs = scheduler.next_runs(trig, now)
            except Exception:  # noqa: BLE001 - one odd trigger mustn't break Home
                continue
            for r in runs[:1]:
                if now <= r["at"] <= now + DAY:
                    upcoming.append({"id": trig["id"], "name": trig["name"], "kind": trig["kind"], "at": r["at"], "for": r.get("for"),
                                     "ask": bool((trig.get("action") or {}).get("ask"))})
    upcoming.sort(key=lambda x: x["at"])

    # ---- suggestions: your routines, most used first ----
    ranked = []
    for name in sorted(routines.names()):
        try:
            r = routines.get(name)
        except Exception:  # noqa: BLE001
            continue
        runs = routines.index(name).get("runs", [])
        ranked.append((len(runs), str(max((x.get("time") or "" for x in runs), default="")), name, r))
    ranked.sort(key=lambda x: (x[0], x[1]), reverse=True)  # most runs, then the latest run; ties stay by name
    suggestions = [{"label": r.intent, "routine": name, "app": r.app} for _, _, name, r in ranked[:4]]

    # ---- the briefing, in Envoy's words ----
    said: list[str] = []
    if changes:
        c = next(x for x in today if x["kind"] == "change")
        kind, _, rest = (c["entity"] or "").partition(" ")
        what = f"{kind.lower()} {rest}".strip() if rest else kind.lower()
        more = sum(1 for x in today if x["kind"] == "change") - 1
        said.append(f"Your {c['label'].lower()}{f' for {what}' if what else ''} changed to {c['new']}"
                    + (f", and {more} more {'thing' if more == 1 else 'things'} I remember changed today." if more else "."))
    if upcoming:
        u = upcoming[0]
        said.append(f"Next up at {_clock(u['at'], now)}: {u['name']}" + (", and I'll ask you first." if u["ask"] else "."))
    approvals = [n for n in needs if n["kind"] == "approval"]
    if approvals:
        money = all(n["money"] for n in approvals)
        said.append(f"{_count(len(approvals), 'payment is' if money else 'action is', 'payments are' if money else 'actions are')} waiting for your OK.")
    if asking:
        said.append(f"I have a question for you: {asking[0]['title']}" if len(asking) == 1 else f"I have {len(asking)} questions for you.")
    if phone_asks:
        said.append(f"{_count(len(phone_asks), 'task asks', 'tasks ask')} to use your Android phone.")
    if stuck:
        said.append(f"{_count(len(stuck), 'task needs', 'tasks need')} you on the phone.")
    done = [t for t in finished if t["status"] == "done"]
    if done and len(said) < 3:
        said.append(f"I finished {len(done)} tasks today." if len(done) > 1 else "I finished one task today.")
    if not said:
        said.append("All quiet. Nothing needs you right now.")

    return {"time": now, "name": user_name(memory), "text": " ".join(said[:3]), "needs": needs, "today": today[:8],
            "upcoming": upcoming[:5], "suggestions": suggestions}
