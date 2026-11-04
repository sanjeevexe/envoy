"""Envoy's own assistant on Muse Spark (design doc, Web app › Chat; route 1 of the Path into Muse).

One Spark call reads the message and decides: a question memory can answer, a task for a phone app, or a plain reply.
Memory questions are answered from memory's notes only (with where and when each fact was seen, and a warning when
it may be out of date); if memory doesn't have it, the matching task is started instead. Past a fact's freshness window
(a gate seen more than 30 min ago) the app is checked first; memory answers alone only when no phone can run that
check, and then says how old the answer is. The assistant has no way to
approve anything: approvals come only from the user's approval screen.

A message with schedule words ("every Friday at 6 PM, order my usual") may set up a recurring job (api/recurring.py): a
trigger created switched off, and a card asking you to turn it on. Every other message goes on exactly as before.

"My usual from <place> is <order>" (typed or spoken in Envoy's own app) is stored as your usual, with you as its source
(memory/usual.py), in code and with no model call; a later "order my usual from <place>" spells it out in the task.
"""

from __future__ import annotations

import asyncio
from typing import Any

from memory.retrieval import Retriever
from memory.usual import VIA, Usual, remember, said
from models.prompts import CHAT_INSTRUCTIONS

from api.crossapp import lead, may_span_apps
from api.recurring import may_schedule


NO_KEY = "Chat needs a Meta Model API key: set META_API_KEY in .env and restart. Saved routines still run without one."
NOT_CAUGHT = "Sorry, I didn't catch that. Please try again."


async def chat(message: str, *, adapter: Any, memory: Any, runner: Any, routines: Any, source: str = "chat") -> dict[str, Any]:
    """`source` is "chat" (typed) or "voice" (spoken): either way your own words, which the approval rules honor.
    `spoken` is the short line a voice reply reads aloud.
    A request that needs two or more apps becomes a cross-app task first (api/crossapp.py); one that asks for something
    again and again may set up a recurring job (api/recurring.py); the rest is unchanged."""
    if source in VIA and (usual := said(message, _app_names(runner))) is not None:
        return told(memory, usual, source)
    if not getattr(adapter, "api_key", True):  # a fresh checkout with no key: say so, instead of a 500
        return {"kind": "reply", "model_calls": 0, "cost_usd": 0.0, "reply": NO_KEY, "spoken": NO_KEY}
    lead_calls, lead_cost = 0, 0.0
    recurring = getattr(runner, "recurring", None)
    if recurring is not None and may_schedule(message):
        try:
            got, lead_calls, lead_cost = await recurring.propose(message, source)
        except Exception:  # noqa: BLE001 - setting up a recurring job is an extra step: chat goes on as before
            got = None
        if got is not None:
            return got
    cross = getattr(runner, "crossapp", None)
    if cross is not None and may_span_apps(message):
        try:
            split, cost = await lead(message, adapter, routines)
            lead_calls, lead_cost = lead_calls + 1, lead_cost + cost
        except Exception:  # noqa: BLE001 - the lead is an extra step: chat goes on as before
            split = None
        if split is not None:
            task = cross.start(message, split, source)
            names = " and ".join(dict.fromkeys(p.name for p in split.parts))
            return {"kind": "task", "model_calls": lead_calls, "cost_usd": round(lead_cost, 5), "task": task, "parts": [p.label for p in split.parts],
                    "reply": f"Checking {names} at once: " + "; ".join(p.label for p in split.parts) + ". You can follow each one here.",
                    "spoken": f"Checking {names}."}
    apps = sorted({f"{r.app}: {r.intent}" for r in routines.active()})
    content = f"REQUEST: {message}\n\nAPPS (learned routines):\n" + "\n".join(f"- {a}" for a in apps) + "\n"
    res = await asyncio.to_thread(adapter.call, "chat", content, instructions=CHAT_INSTRUCTIONS, data_scope="real", task_id="chat")
    route = res.parsed
    if route is None:  # now and then the reply doesn't parse (a clean-clone test, Nov 4: a 500 on 1 chat in 4): ask once more
        lead_calls, lead_cost = lead_calls + 1, lead_cost + res.cost_at_standard_usd
        res = await asyncio.to_thread(adapter.call, "chat", content, instructions=CHAT_INSTRUCTIONS, data_scope="real", task_id="chat")
        route = res.parsed
    if route is None:
        return {"kind": "reply", "model_calls": 1 + lead_calls, "cost_usd": round(res.cost_at_standard_usd + lead_cost, 5),
                "reply": NOT_CAUGHT, "spoken": NOT_CAUGHT}
    out: dict[str, Any] = {"kind": route.kind, "model_calls": 1 + lead_calls, "cost_usd": round(res.cost_at_standard_usd + lead_cost, 5)}
    if route.kind == "memory":
        ans = await Retriever(memory).answer(message, adapter, data_scope="real", task_id="chat-answer")
        out["model_calls"] += 1
        stale_since = Retriever(memory).stale_since(ans.notes, ans.answer) if ans.found else None
        if stale_since is not None and route.goal and phone_ready(runner, route.goal):
            task = runner.start(route.goal, source, request=message)
            ago = Retriever(memory).ago(stale_since)
            out.update(kind="task", reply=f"Memory says: {ans.answer.rstrip('.')} (seen {ago}, which may be out of date). Checking the app: {route.goal}.",
                       spoken="That may have changed. I'm checking the app.", task=task, stale=True, notes=ans.notes.markdown)
            return out
        if ans.found and ans.supported:
            if stale_since is not None:
                ans.answer = f"{ans.answer} (from {Retriever(memory).ago(stale_since)}; no phone is free to check it now)"
            out.update(reply=ans.answer, spoken=ans.answer, stale=ans.stale, notes=ans.notes.markdown, from_memory=True)
            return out
        if route.goal:
            task = runner.start(route.goal, source, request=message)
            out.update(kind="task", reply=f"Memory doesn't have that yet, so I'm checking: {route.goal}.", spoken="I don't know yet. I'm checking.", task=task)
            return out
        out.update(reply=ans.answer or "Memory doesn't have that yet.", spoken=ans.answer or "I don't know that yet.", from_memory=True)
        return out
    if route.kind == "task":
        task = runner.start(route.goal or message, source, request=message)
        usual = task.get("usual") if isinstance(task, dict) else None
        out.update(reply=f"On it: {task['goal'] if usual else route.goal or message}. You can follow it here; anything that costs money, or that you "
                         "didn't ask for, waits for your OK.",
                   spoken=f"On it: your usual from {usual['place']}, {usual['order']}." if usual else f"On it: {route.goal or message}.", task=task)
        return out
    out["reply"] = route.reply or "I can answer from what I remember, or do things in your phone apps."
    out["spoken"] = out["reply"]
    return out


def told(memory: Any, usual: Usual, source: str) -> dict[str, Any]:
    """You said what your usual is: stored, and said back. Without an app (and with a place that isn't one), asks for it:
    a task needs to know where to order."""
    eid, known = remember(memory, usual, via=VIA[source])
    app = (memory.current(eid, "app") or {}).get("value")
    what = f"your usual from {usual.place} is {usual.order}" + (f", on {app}" if app else "")
    reply = f"Got it: {what}." + (" (It replaces the one I had.)" if known else "") + f' Ask for "my usual from {usual.place}" any time.'
    from api.runner import app_for  # here, not at the top, as in phone_ready
    if not app and app_for(usual.place) is None:
        reply += f' Which app do you order it on? Say it again with the app, like "… on <app>", and I\'ll order it there.'
    return {"kind": "reply", "model_calls": 0, "cost_usd": 0.0, "reply": reply, "spoken": f"Got it: {what}.",
            "remembered": {"entity": eid, "place": usual.place, "order": usual.order, "app": app}}


def _app_names(runner: Any) -> list[str]:
    names = getattr(runner, "app_names", None)
    if callable(names):
        return names()
    from api.runner import APP_NAMES
    return list(APP_NAMES)


def phone_ready(runner: Any, goal: str) -> bool:
    """A phone that could run the check now: the app's emulator is up, or your Android phone is connected."""
    pool = getattr(runner, "pool", None)
    if pool is None:
        return False
    try:
        from api.runner import app_for
        running = pool.running()
        return bool(running.get(pool.avd_for(app_for(goal)))) or any(p.get("state") == "device" for p in pool.phones.values())
    except Exception:  # noqa: BLE001 - no way to tell: answer from memory, saying how old it is
        return False
