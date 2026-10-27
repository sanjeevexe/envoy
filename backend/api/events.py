"""One event stream for every interface (design doc, Interfaces: "every change is pushed to all of them over one event
stream"). Task steps, approvals, takeovers and memory changes are published here and fanned out to WebSocket clients.

`publish` is safe from any thread: runs call it from the agent's event loop, approvals from worker threads.
"""

from __future__ import annotations

import asyncio
import itertools
import time
from collections import deque
from typing import Any, AsyncIterator


class EventBus:
    def __init__(self, keep: int = 1000) -> None:
        self._subs: set[asyncio.Queue] = set()
        self.recent: deque[dict[str, Any]] = deque(maxlen=keep)
        self._seq = itertools.count(1)
        self.loop: asyncio.AbstractEventLoop | None = None

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def publish(self, type_: str, **data: Any) -> dict[str, Any]:
        ev = {"seq": next(self._seq), "time": time.time(), "type": type_, **data}
        loop = self.loop
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if loop is not None and running is not loop:
            loop.call_soon_threadsafe(self._fan_out, ev)
        else:
            self._fan_out(ev)
        return ev

    def _fan_out(self, ev: dict[str, Any]) -> None:
        self.recent.append(ev)
        for q in list(self._subs):
            if q.qsize() < 500:  # a stalled client drops events rather than growing without bound
                q.put_nowait(ev)

    async def subscribe(self, after_seq: int = 0) -> AsyncIterator[dict[str, Any]]:
        q: asyncio.Queue = asyncio.Queue()
        self._subs.add(q)
        try:
            for ev in list(self.recent):  # catch up on what the client missed (reconnects)
                if ev["seq"] > after_seq:
                    yield ev
            while True:
                yield await q.get()
        finally:
            self._subs.discard(q)
