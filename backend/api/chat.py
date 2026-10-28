"""Envoy's own assistant on Muse Spark (design doc, Web app › Chat; route 1 of the Path into Muse).

One Spark call reads the message and decides: a question memory can answer, a task for a phone app, or a plain reply.
Memory questions are answered from memory's notes only (with where and when each fact was seen, and a warning when
it may be out of date); if memory doesn't have it, the matching task is started instead. The assistant has no way to
approve anything: approvals come only from the user's approval screen.
"""

from __future__ import annotations

import asyncio
from typing import Any

from memory.retrieval import Retriever
from models.prompts import CHAT_INSTRUCTIONS

from api.crossapp import lead, may_span_apps


async def chat(message: str, *, adapter: Any, memory: Any, runner: Any, routines: Any, source: str = "chat") -> dict[str, Any]:
    """`source` is "chat" (typed) or "voice" (spoken): either way your own words, which the approval rules honor.
    `spoken` is the short line a voice reply reads aloud.
    A request that needs two or more apps becomes a cross-app task first (api/crossapp.py); the rest is unchanged."""
    lead_calls, lead_cost = 0, 0.0
    cross = getattr(runner, "crossapp", None)
    if cross is not None and may_span_apps(message):
        try:
            split, lead_cost = await lead(message, adapter, routines)
            lead_calls = 1
        except Exception:  # noqa: BLE001 - the lead is an extra step: chat goes on as before
            split = None
        if split is not None:
            task = cross.start(message, split, source)
            names = " and ".join(dict.fromkeys(p.name for p in split.parts))
            return {"kind": "task", "model_calls": 1, "cost_usd": round(lead_cost, 5), "task": task, "parts": [p.label for p in split.parts],
                    "reply": f"Checking {names} at once: " + "; ".join(p.label for p in split.parts) + ". You can follow each one here.",
                    "spoken": f"Checking {names}."}
    apps = sorted({f"{r.app}: {r.intent}" for r in routines.active()})
    content = f"REQUEST: {message}\n\nAPPS (learned routines):\n" + "\n".join(f"- {a}" for a in apps) + "\n"
    res = await asyncio.to_thread(adapter.call, "chat", content, instructions=CHAT_INSTRUCTIONS, data_scope="real", task_id="chat")
    route = res.parsed
    out: dict[str, Any] = {"kind": route.kind, "model_calls": 1 + lead_calls, "cost_usd": round(res.cost_at_standard_usd + lead_cost, 5)}
    if route.kind == "memory":
        ans = await Retriever(memory).answer(message, adapter, data_scope="real", task_id="chat-answer")
        out["model_calls"] += 1
        if ans.found and ans.supported:
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
        out.update(reply=f"On it: {route.goal or message}. You can follow it here; anything that costs money, or that you didn't ask for, waits for your OK.",
                   spoken=f"On it: {route.goal or message}.", task=task)
        return out
    out["reply"] = route.reply or "I can answer from what I remember, or do things in your phone apps."
    out["spoken"] = out["reply"]
    return out
