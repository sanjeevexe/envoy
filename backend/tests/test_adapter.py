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


# ---- model profiles -------------------------------------------------------------------------------

def _adapter(tmp_path):
    return ModelAdapter(api_key="x", meter=CostMeter(path=tmp_path / "c.jsonl"))


def test_spark_profile_is_todays_split(monkeypatch):
    from models.adapter import JOBS, model_for
    monkeypatch.delenv("ENVOY_MODEL_PROFILE", raising=False)
    assert model_for("step") == "muse-spark-1.3" and model_for("compile") == "muse-wonder-1.0"
    assert all(model_for(j) == JOBS[j].model for j in JOBS)


def test_hybrid_profile_moves_plan_step_repair_to_wonder(monkeypatch, tmp_path):
    from models.adapter import model_for
    monkeypatch.setenv("ENVOY_MODEL_PROFILE", "hybrid")
    wonder = {j for j in ("plan", "step", "repair", "compile", "match", "chat", "choose", "extract", "same_entity", "answer", "grounding")
              if model_for(j) == "muse-wonder-1.0"}
    assert wonder == {"plan", "step", "repair", "compile"}
    req = _adapter(tmp_path).build_request("step", "hi")
    assert req["model"] == "muse-wonder-1.0" and req["max_output_tokens"] >= 8000
    assert _adapter(tmp_path).build_request("match", "hi")["model"] == "muse-spark-1.3"


def test_wonder_profile_is_everything(monkeypatch):
    from models.adapter import JOBS, model_for
    monkeypatch.setenv("ENVOY_MODEL_PROFILE", "wonder")
    assert {model_for(j) for j in JOBS} == {"muse-wonder-1.0"}


def test_per_job_override_wins_over_the_profile(monkeypatch, tmp_path):
    from models.adapter import model_for
    monkeypatch.setenv("ENVOY_MODEL_PROFILE", "hybrid")
    monkeypatch.setenv("ENVOY_MODEL_STEP", "muse-spark-1.3")
    monkeypatch.setenv("ENVOY_MODEL_GROUNDING", "muse-wonder-1.0")
    assert model_for("step") == "muse-spark-1.3" and model_for("grounding") == "muse-wonder-1.0" and model_for("plan") == "muse-wonder-1.0"
    assert _adapter(tmp_path).build_request("step", "hi")["model"] == "muse-spark-1.3"


def test_unknown_profile_is_an_error(monkeypatch):
    from models.adapter import active_profile
    monkeypatch.setenv("ENVOY_MODEL_PROFILE", "turbo")
    with pytest.raises(ValueError):
        active_profile()


def test_wonder_jobs_get_a_longer_timeout(monkeypatch):
    from models.adapter import job_config
    monkeypatch.setenv("ENVOY_MODEL_PROFILE", "hybrid")
    assert job_config("step").timeout_s >= 120 and job_config("match").timeout_s == 30


def test_wonder_never_runs_on_contributor_and_real_data_never_does(monkeypatch, tmp_path):
    monkeypatch.setenv("META_CONTRIBUTOR_TIER", "true")
    monkeypatch.setenv("ENVOY_MODEL_PROFILE", "hybrid")
    a = _adapter(tmp_path)
    # A test-app step on Wonder: no Contributor variant, so the standard tier (stricter), not an error.
    assert a.build_request("step", "hi", data_scope="test_app", contributor=True)["model"] == "muse-wonder-1.0"
    # Spark jobs still use Contributor for test apps...
    assert a.build_request("match", "hi", data_scope="test_app", contributor=True)["model"] == "muse-spark-1.3-contributor"
    # ...and nothing real ever does, whatever the profile.
    for job in ("step", "match"):
        with pytest.raises(ContributorNotAllowed):
            a.build_request(job, "hi", data_scope="real", contributor=True)


def test_cost_uses_the_resolved_models_prices(monkeypatch, tmp_path):
    from types import SimpleNamespace as NS
    import json
    monkeypatch.setenv("ENVOY_MODEL_PROFILE", "hybrid")
    a = _adapter(tmp_path)
    usage = NS(input_tokens=1000, output_tokens=100, total_tokens=1100, input_tokens_details=NS(cached_tokens=0),
               output_tokens_details=NS(reasoning_tokens=50), model_extra={})
    sent = []

    class Resp:
        def create(self, **req):
            sent.append(req["model"])
            return NS(usage=usage, output_text=VALID, output=[], id="r1")
    a._client = NS(responses=Resp())
    step = a.call("step", "hi", task_id="t1")
    match_cost = token_cost("muse-spark-1.3", {"input_tokens": 1000, "output_tokens": 100})
    assert step.model == "muse-wonder-1.0" and round(step.cost_usd, 6) == round((1000 * 4.0 + 100 * 20.0) / 1e6, 6)
    assert round(step.cost_usd / match_cost, 1) > 3
    entry = json.loads((tmp_path / "c.jsonl").read_text().splitlines()[0])
    assert entry["profile"] == "hybrid" and entry["model"] == "muse-wonder-1.0"


def test_profile_models_and_cost_scale(monkeypatch):
    from models.adapter import profile_models, step_cost_scale
    monkeypatch.setenv("ENVOY_MODEL_PROFILE", "hybrid")
    pm = profile_models()
    assert pm["profile"] == "hybrid" and pm["jobs"]["step"] == "muse-wonder-1.0" and pm["jobs"]["chat"] == "muse-spark-1.3"
    assert step_cost_scale() == 3.2 and step_cost_scale("spark") == 1.0
