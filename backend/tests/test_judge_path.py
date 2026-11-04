"""What a fresh clone hits first (a clean-clone test of the README, Nov 4): chat with no key, and a route that doesn't parse."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from api.chat import NO_KEY, NOT_CAUGHT, chat
from models.schemas import ChatRoute


class _Adapter:
    def __init__(self, *parsed, api_key: str = "a-key"):
        self.api_key, self.parsed, self.calls = api_key, list(parsed), 0

    def call(self, *a, **kw):
        self.calls += 1
        return SimpleNamespace(parsed=self.parsed.pop(0), cost_at_standard_usd=0.001)


def _chat(adapter):
    runner = SimpleNamespace(crossapp=None, recurring=None, pool=None)
    return asyncio.run(chat("Hello there", adapter=adapter, memory=None, runner=runner, routines=SimpleNamespace(active=lambda: []), source="test"))


def test_chat_with_no_key_says_so_and_calls_nothing():
    adapter = _Adapter(api_key="")
    out = _chat(adapter)
    assert out["reply"] == NO_KEY and out["kind"] == "reply" and adapter.calls == 0


def test_a_route_that_doesnt_parse_is_asked_once_more():
    adapter = _Adapter(None, ChatRoute(kind="reply", goal="", reply="Hi."))
    out = _chat(adapter)
    assert out["reply"] == "Hi." and out["model_calls"] == 2 and adapter.calls == 2


def test_two_routes_that_dont_parse_get_a_plain_reply_not_a_500():
    adapter = _Adapter(None, None)
    out = _chat(adapter)
    assert out["reply"] == NOT_CAUGHT and out["kind"] == "reply" and adapter.calls == 2
