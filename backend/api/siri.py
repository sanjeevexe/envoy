"""Ask Envoy from Siri, the Action Button and Control Center (docs/siri.md).

An Apple Shortcut ("Ask Envoy", built by `scripts/make_shortcut.py --siri`) takes what you say with the phone's own
dictation, posts the text to `POST /api/siri` with a token of scope `siri`, and speaks the one `say` line it gets back:

    "On it: check me in for my flight. Confirming check-in will wait for your OK."
    "Your gate is B12."
    "That may have changed. I'm checking the app."

The request goes through chat exactly as a typed message does, with source `siri`. That source is not one of the
approval rules' direct sources (`policy/approval_rules.py`): Siri runs on a locked phone and answers anyone who says
"Hey Siri", so every irreversible step waits for your OK on Envoy's own screens, even one the request names, and money
always asks. A routine you set to run without asking still does, as for every source. The `siri` token can do only
what a chat message can start (ask, start a task, draft a recurring job that stays off until your yes in Envoy); it
can't read, approve, decide an offer, take over or open a live view.

Every answer carries `say`, errors included (a 401, a 429 for more than 6 a minute or 100 a day per token, a model
failure), so the Shortcut always has something to speak.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import unicodedata
from collections import deque
from typing import Any, Callable

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from api.chat import chat
from api.preflight import check as preflight_check

log = logging.getLogger(__name__)

MESSAGE_MAX = 400  # characters of dictated text
SAY_MAX = 200  # about 12 seconds of speech
PER_MINUTE, PER_DAY = 6, 100  # requests per token
PREFLIGHT_WAIT_S = 3.0  # how long to wait for the task's own `preflight` step (it comes after the routine is picked)

SAY_EMPTY = "I didn't catch that."
SAY_FAILED = "I couldn't do that just now. Try again in a minute."
SAY_SIGN_IN = "Envoy doesn't recognize this shortcut any more. Set up Ask Envoy again."
SAY_TOO_MANY = "That's a lot of requests. Try again in a minute."
SAY_TOO_MANY_TODAY = "That's enough requests for today. Try again tomorrow, or open Envoy."
SAY_DRAFTED = "I've drafted it. Say yes in Envoy to turn it on."


def now() -> float:
    """The limits' clock (tests replace it)."""
    return time.time()


def siri_router(ctx: Any, session: Callable[..., None], caller: Callable[..., Any], csrf: Callable[..., None]) -> APIRouter:
    """`POST /api/siri/token` (session only) and `POST /api/siri` (a `siri` token, or your session). `session`, `caller`
    and `csrf` are the app's own checks (closures inside `build()`). The per-token counters live here, one set per app."""
    r = APIRouter()
    recent: dict[str, deque[float]] = {}  # token → times of its requests in the last day

    @r.post("/api/siri/token", dependencies=[Depends(session)])
    def new_token(body: dict[str, Any] | None = Body(None)) -> dict[str, Any]:
        """The Shortcut's token: it can ask Envoy and start tasks, nothing else. Shown once; revoke it in Devices."""
        name = str((body or {}).get("name") or "Ask Envoy (Siri)")
        return {"token": ctx.auth.issue("siri", name), "scope": "siri", "ask_url": f"{ctx.public}/api/siri"}

    def over_limit(key: str) -> str | None:
        t = now()
        times = recent.setdefault(key, deque())
        while times and times[0] <= t - 86400:
            times.popleft()
        if len(times) >= PER_DAY:
            return SAY_TOO_MANY_TODAY
        if sum(1 for x in times if x > t - 60) >= PER_MINUTE:
            return SAY_TOO_MANY
        times.append(t)
        return None

    @r.post("/api/siri")
    async def ask(request: Request) -> JSONResponse:
        c = caller(request)
        if c is None or c.scope not in ("session", "siri"):
            return JSONResponse({"say": SAY_SIGN_IN, "kind": "error"}, status_code=401)
        try:
            csrf(request)
        except HTTPException as e:
            return JSONResponse({"say": SAY_FAILED, "kind": "error"}, status_code=e.status_code)
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 - not JSON: treated as nothing said
            body = None
        said = body.get("message") if isinstance(body, dict) else None
        message = re.sub(r"\s+", " ", said if isinstance(said, str) else "").strip()[:MESSAGE_MAX].strip()
        if not message:
            return JSONResponse({"say": SAY_EMPTY, "kind": "error"}, status_code=400)
        limited = over_limit(c.device_id or c.kind)
        if limited:
            return JSONResponse({"say": limited, "kind": "error"}, status_code=429)
        t0 = time.monotonic()
        try:
            out = await chat(message, adapter=ctx.adapter, memory=ctx.memory, runner=ctx.runner, routines=ctx.routines, source="siri")
        except Exception as e:  # noqa: BLE001 - a model failure, the cost cap: Siri still says something
            log.warning("siri: chat failed (%s)", type(e).__name__)  # never the message itself
            return JSONResponse({"say": SAY_FAILED, "kind": "error"})
        task_id = (out.get("task") or {}).get("id")
        ctx.bus.publish("chat", message=message, reply=out.get("reply"), kind=out.get("kind"), task_id=task_id, source="siri")
        line, waited = None, 0.0
        if task_id:
            line, waited = await heads_up(ctx, out, message)
        res: dict[str, Any] = {"say": say_for(out, line), "kind": str(out.get("kind") or "reply")}
        if task_id:
            res["task_id"] = task_id
        log.info("siri: %s in %.2f s (preflight wait %.2f s, %s model calls)", res["kind"], time.monotonic() - t0, waited, out.get("model_calls"))
        return JSONResponse(res)

    return r


# ---- what Siri says --------------------------------------------------------------------------------


async def heads_up(ctx: Any, out: dict[str, Any], message: str) -> tuple[dict[str, str] | None, float]:
    """The one Before I start line worth saying for a task, and how long it took to get. The task's own `preflight` step
    names the irreversible step ("Confirming check-in will wait for your OK"), but only once the runner has picked a
    routine, a second or two in; past `PREFLIGHT_WAIT_S`, `preflight.check()` without a routine says the general line.
    When chat's line is already two sentences ("That may have changed. I'm checking the app.") only a stop line would be
    said, and that doesn't depend on the routine, so there's no wait."""
    task = out.get("task") or {}
    tid, t0 = task.get("id"), time.monotonic()
    if len(sentences(spoken_of(out))) < 2 and not out.get("parts"):  # a cross-app task's parts have the steps, not it
        while time.monotonic() - t0 < PREFLIGHT_WAIT_S:
            for s in ctx.tasks.steps(tid):
                if s.get("kind") == "preflight":
                    return pick(s.get("lines") or []), time.monotonic() - t0
            if (ctx.tasks.get(tid) or {}).get("status") not in ("queued", "running", None):
                break  # it ended (or is waiting on you) before saying anything
            await asyncio.sleep(0.1)
    lines = preflight_check(ctx.runner, task.get("goal") or message, request=task.get("request") or message, source="siri")
    return pick(lines), time.monotonic() - t0


def pick(lines: list[dict[str, str]]) -> dict[str, str] | None:
    """The first stop line, else the first approval line that says it will wait for (or need) your OK, else the first warn."""
    for ln in lines:
        if ln.get("level") == "stop":
            return ln
    for ln in lines:
        if ln.get("kind") == "approval" and re.search(r"\b(wait for|need) your OK\b", ln.get("text") or ""):
            return ln
    for ln in lines:
        if ln.get("level") == "warn":
            return ln
    return None


def spoken_of(out: dict[str, Any]) -> str:
    return str(out.get("spoken") or out.get("reply") or "")


def say_for(out: dict[str, Any], line: dict[str, str] | None = None) -> str:
    """Chat's spoken line, plain and short, plus at most one Before I start line for a task."""
    if out.get("kind") == "trigger_request" and out.get("offer"):
        return SAY_DRAFTED  # there's no card over Siri; Siri never turns anything on
    first = sentences(plain(spoken_of(out))) or [plain(str(out.get("reply") or "")) or "Done."]
    extra = plain(line["text"]) if line else ""
    if extra and _norm(extra) in _norm(" ".join(first)):
        extra = ""
    if extra and len(first) >= 2:
        if line and line.get("level") == "stop":
            first = first[:1]  # what stops the task matters more than chat's second sentence
        else:
            extra = ""
    first = first[:2]
    if not extra:
        return fit(" ".join(first), SAY_MAX)
    room = SAY_MAX - len(extra) - 1
    if room < 30:
        return fit(" ".join(first), SAY_MAX)
    return f"{fit(' '.join(first), room)} {extra}"


_URL = re.compile(r"\b(?:https?://|www\.)\S+", re.I)
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_ID = re.compile(r"\b[a-z]+-\d{4}-\d{6}-[0-9a-f]{4}\b|\bdev-[0-9a-f]{8}\b")  # new_id() and device ids
_MARKS = re.compile(r"[*_`#>|~]+")


def plain(text: str) -> str:
    """No markdown, links, ids or emoji: just words Siri can say."""
    s = _LINK.sub(r"\1", text or "")
    s = _URL.sub("", s)
    s = _ID.sub("", s)
    s = _MARKS.sub("", s).replace("→", " to ")
    s = "".join(ch for ch in s if ch == "°" or (unicodedata.category(ch) not in ("So", "Sk", "Cs", "Co", "Cn") and ch not in "️‍"))
    s = re.sub(r"\(\s*\)|\s*\((?:from|seen) [^)]*\)", "", s)  # chat's age aside: the answer already says when it was seen
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"\s+([.,;:!?])", r"\1", s)


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"“])", text.strip())
    return [p.strip() for p in parts if p.strip()]


def fit(text: str, limit: int) -> str:
    """At most `limit` characters, cut at a sentence if one fits, else at a word."""
    if len(text) <= limit:
        return text
    kept = ""
    for s in sentences(text):
        if len(kept) + len(s) + (1 if kept else 0) > limit:
            break
        kept = f"{kept} {s}".strip()
    if kept:
        return kept
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:-– ")
    return cut + "…"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower())
