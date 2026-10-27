"""Offline tests for the model adapter (no API calls)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from models.adapter import ContributorNotAllowed, ModelAdapter, CostMeter, parse_structured, token_cost
from models.schemas import StepOutput

VALID = '{"reason": "r", "action": {"type": "tap", "element": 3}, "expected_result": "x", "risk": "read"}'


def test_parse_direct():
    p, how = parse_structured(StepOutput, SimpleNamespace(output=[]), VALID)
    assert how == "direct" and p.action.element == 3


def test_parse_recovers_from_a_preamble():
    # Seen in Phase 1: a sentence before the schema JSON.
    p, how = parse_structured(StepOutput, SimpleNamespace(output=[]), "Found your trip history list. " + VALID)
    assert how == "embedded_json" and p.action.type == "tap"


def test_parse_prefers_the_last_message_part():
    resp = SimpleNamespace(output=[
        SimpleNamespace(type="reasoning"),
        SimpleNamespace(type="message", content=[SimpleNamespace(text="Thinking out loud."), SimpleNamespace(text=VALID)]),
    ])
    p, how = parse_structured(StepOutput, resp, "Thinking out loud." + VALID)
    assert how == "last_message_part"


def test_parse_still_fails_on_garbage():
    with pytest.raises(ValueError):
        parse_structured(StepOutput, SimpleNamespace(output=[]), "no json here")


def test_contributor_tier_only_for_test_apps(tmp_path, monkeypatch):
    monkeypatch.setenv("META_CONTRIBUTOR_TIER", "true")
    a = ModelAdapter(api_key="x", meter=CostMeter(path=tmp_path / "c.jsonl"))
    assert a.build_request("step", "hi", data_scope="test_app", contributor=True)["model"] == "muse-spark-1.3-contributor"
    with pytest.raises(ContributorNotAllowed):
        a.build_request("step", "hi", data_scope="real", contributor=True)


def test_token_cost_uses_cached_price():
    usage = {"input_tokens": 2000, "cached_tokens": 1900, "output_tokens": 144}
    assert round(token_cost("muse-spark-1.3", usage), 6) == round((100 * 1.25 + 1900 * 0.15 + 144 * 4.25) / 1e6, 6)
