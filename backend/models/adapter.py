"""The one module every Meta model call goes through.

- Per-job config: model, reasoning effort, output schema, token cap.
- Cost meter: tokens and dollars per call to logs/model_costs.jsonl, with a daily cap.
- Timeouts and retries: 30 s per call, 2 retries with backoff on 429/5xx (Retry-After honored).
- Contributor tier (Meta may train on what is sent): only for our own test apps, never real data.
- Model profiles: `ENVOY_MODEL_PROFILE=spark|hybrid|wonder` moves jobs between Muse Spark and Muse Wonder all at once;
  `ENVOY_MODEL_<JOB>=<model>` overrides one job. Resolved on every call, and written to the cost log.

API shapes follow dev.meta.ai/docs as read on Oct 26, 2026 (Responses API through the OpenAI SDK):
  reasoning={"effort": ...}; text={"format": {"type": "json_schema", ...}}; usage.input_tokens_details.cached_tokens;
  usage.output_tokens_details.reasoning_tokens; prompt caching is automatic, prompt_cache_key is a routing hint,
  prompt_cache_retention="24h" asks for longer retention; Contributor is a separate model ID ("-contributor").
"""

from __future__ import annotations

import base64
import json
import os
import random
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel

from models.schemas import (AppNoteOutput, ChatRoute, ChooseOutput, CompiledRoutine, ExtractionOutput, GroundingResult, MatchOutput, MemoryAnswer, Plan, SameEntityOutput,
                            StepOutput, strict_json_schema)

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

COST_LOG = REPO_ROOT / "logs" / "model_costs.jsonl"
BASE_URL = os.environ.get("META_API_BASE_URL", "https://api.meta.ai/v1")

Effort = Literal["minimal", "low", "medium", "high", "xhigh", "max"]
DataScope = Literal["test_app", "real"]

# USD per 1M tokens, from https://dev.meta.ai/docs/pricing-rate-limits/ (Oct 26, 2026).
TOKEN_PRICES: dict[str, dict[str, float]] = {
    "muse-spark-1.3": {"input": 1.25, "cached_input": 0.15, "output": 4.25},
    "muse-spark-1.2": {"input": 1.25, "cached_input": 0.15, "output": 4.25},
    "muse-spark-1.1": {"input": 1.25, "cached_input": 0.15, "output": 4.25},
    "muse-spark-1.3-contributor": {"input": 0.10, "cached_input": 0.002, "output": 0.20},
    "muse-spark-1.2-contributor": {"input": 0.10, "cached_input": 0.002, "output": 0.20},
    "muse-wonder-1.0": {"input": 4.00, "cached_input": 0.20, "output": 20.00},
}
SAM_PRICE_PER_IMAGE = 2.50 / 1000
VOICE_PRICE_PER_HOUR = 0.18
CONTRIBUTOR_MODELS = {"muse-spark-1.3": "muse-spark-1.3-contributor", "muse-spark-1.2": "muse-spark-1.2-contributor"}
SPARK, WONDER = "muse-spark-1.3", "muse-wonder-1.0"


@dataclass(frozen=True)
class JobConfig:
    name: str
    model: str
    effort: Effort | None
    schema: type[BaseModel] | None = None
    max_output_tokens: int | None = None
    timeout_s: float = 30
    retries: int = 2
    cache_key: str | None = "envoy-v0"  # routing hint so calls sharing a prompt prefix land together
    cache_retention: Literal["in_memory", "24h"] | None = "24h"


JOBS: dict[str, JobConfig] = {
    "step": JobConfig("step", "muse-spark-1.3", "low", StepOutput, max_output_tokens=4000),
    "plan": JobConfig("plan", "muse-spark-1.3", "medium", Plan, max_output_tokens=8000),
    "repair": JobConfig("repair", "muse-spark-1.3", "medium", StepOutput, max_output_tokens=8000),
    "grounding": JobConfig("grounding", "muse-spark-1.3", "low", GroundingResult, max_output_tokens=4000),
    "choose": JobConfig("choose", "muse-spark-1.3", "low", ChooseOutput, max_output_tokens=2000),
    "extract": JobConfig("extract", "muse-spark-1.3", "low", ExtractionOutput, max_output_tokens=6000),
    "same_entity": JobConfig("same_entity", "muse-spark-1.3", "low", SameEntityOutput, max_output_tokens=2000),
    "answer": JobConfig("answer", "muse-spark-1.3", "low", MemoryAnswer, max_output_tokens=2000),
    "compile": JobConfig("compile", "muse-wonder-1.0", "medium", CompiledRoutine, max_output_tokens=32000, timeout_s=120),
    "match": JobConfig("match", "muse-spark-1.3", "low", MatchOutput, max_output_tokens=4000),
    "chat": JobConfig("chat", "muse-spark-1.3", "low", ChatRoute, max_output_tokens=2000),
    "app_note": JobConfig("app_note", "muse-spark-1.3", "low", AppNoteOutput, max_output_tokens=3000),
}


# Which jobs run on Wonder. `spark` is each job's own model (compile is on Wonder there too); `hybrid` adds the jobs that
# act on a task the agent hasn't seen (plan, step, repair); `wonder` is everything, as the upper bound.
PROFILES: dict[str, dict[str, str]] = {
    "spark": {},
    "hybrid": {"plan": WONDER, "step": WONDER, "repair": WONDER, "compile": WONDER},
    "wonder": {name: WONDER for name in JOBS},
}
DEFAULT_PROFILE = "spark"
WONDER_TIMEOUT_S = 120  # Wonder answers in 10-15 s at medium effort (Phase 2), with a long tail
WONDER_MIN_OUTPUT_TOKENS = 8000  # its reasoning counts against max_output_tokens


def active_profile() -> str:
    name = (os.environ.get("ENVOY_MODEL_PROFILE") or DEFAULT_PROFILE).strip().lower()
    if name not in PROFILES:
        raise ValueError(f"unknown ENVOY_MODEL_PROFILE {name!r} (use one of {', '.join(PROFILES)})")
    return name


def model_for(job: str, profile: str | None = None) -> str:
    """The model a job runs on: its ENVOY_MODEL_<JOB> override, else the profile's choice, else the job's own model."""
    override = os.environ.get(f"ENVOY_MODEL_{job.upper()}", "").strip()
    if override:
        return override
    return PROFILES[profile or active_profile()].get(job) or JOBS[job].model


def job_config(job: JobConfig | str, profile: str | None = None) -> JobConfig:
    """A job's config with the profile applied. A config whose model was set by hand (not the job's default) is kept."""
    cfg = JOBS[job] if isinstance(job, str) else job
    base = JOBS.get(cfg.name)
    if base is not None and cfg.model == base.model:
        cfg = replace(cfg, model=model_for(cfg.name, profile))
    if cfg.model.startswith("muse-wonder"):
        cfg = replace(cfg, timeout_s=max(cfg.timeout_s, WONDER_TIMEOUT_S),
                      max_output_tokens=max(cfg.max_output_tokens or 0, WONDER_MIN_OUTPUT_TOKENS))
    return cfg


def profile_models(profile: str | None = None) -> dict[str, Any]:
    """What a task record says about its models: the profile and each job's model."""
    name = profile or active_profile()
    return {"profile": name, "jobs": {job: model_for(job, name) for job in JOBS}}


def step_cost_scale(profile: str | None = None) -> float:
    """How much an agent step costs against Spark (Wonder ~3x): per-task cost caps were set for Spark steps."""
    model = model_for("step", profile)
    return max(1.0, TOKEN_PRICES.get(model, TOKEN_PRICES[SPARK])["input"] / TOKEN_PRICES[SPARK]["input"])


class CostCapExceeded(RuntimeError):
    pass


class ContributorNotAllowed(RuntimeError):
    pass


@dataclass
class ModelResult:
    job: str
    model: str
    text: str
    parsed: BaseModel | None
    usage: dict[str, int]
    cost_usd: float
    cost_at_standard_usd: float
    latency_ms: float
    attempts: int
    response_id: str | None = None
    raw: Any = field(default=None, repr=False)


def image_part(png: bytes, mime: str = "image/png", detail: str | None = None) -> dict[str, Any]:
    part: dict[str, Any] = {"type": "input_image", "image_url": f"data:{mime};base64,{base64.b64encode(png).decode()}"}
    if detail:
        part["detail"] = detail  # in Meta's schema, but its effect is undocumented
    return part


def token_cost(model: str, usage: dict[str, int]) -> float:
    p = TOKEN_PRICES.get(model)
    if p is None:
        return 0.0
    cached = usage.get("cached_tokens", 0)
    fresh = max(0, usage.get("input_tokens", 0) - cached)
    return (fresh * p["input"] + cached * p["cached_input"] + usage.get("output_tokens", 0) * p["output"]) / 1e6


def standard_model(model: str) -> str:
    return model.removesuffix("-contributor")


def usage_dict(resp: Any) -> dict[str, int]:
    """Flatten Responses API usage; *_details may be missing (Meta's sample responses omit them)."""
    u = getattr(resp, "usage", None)
    if u is None:
        return {}
    in_d = getattr(u, "input_tokens_details", None)
    out_d = getattr(u, "output_tokens_details", None)
    out = {
        "input_tokens": getattr(u, "input_tokens", 0) or 0,
        "cached_tokens": (getattr(in_d, "cached_tokens", 0) or 0) if in_d else 0,
        "output_tokens": getattr(u, "output_tokens", 0) or 0,
        "reasoning_tokens": (getattr(out_d, "reasoning_tokens", 0) or 0) if out_d else 0,
        "total_tokens": getattr(u, "total_tokens", 0) or 0,
    }
    extra = getattr(u, "model_extra", None) or {}
    if "images_processed" in extra:
        out["images_processed"] = extra["images_processed"]
    return out


def parse_structured(schema: type[BaseModel], resp: Any, text: str) -> tuple[BaseModel, str]:
    """Parse schema-constrained output. Normally the whole text is the JSON; if a model adds a sentence
    before it, take the last message item's text, then the last JSON object in the text that validates."""
    try:
        return schema.model_validate_json(text), "direct"
    except ValueError:
        pass
    for item in reversed(getattr(resp, "output", []) or []):
        if getattr(item, "type", "") == "message":
            for part in reversed(getattr(item, "content", []) or []):
                t = getattr(part, "text", "") or ""
                try:
                    return schema.model_validate_json(t), "last_message_part"
                except ValueError:
                    continue
    decoder = json.JSONDecoder()
    candidates = []
    for i, ch in enumerate(text):
        if ch == "{":
            try:
                obj, _ = decoder.raw_decode(text[i:])
                candidates.append(obj)
            except ValueError:
                continue
    for obj in reversed(candidates):
        try:
            return schema.model_validate(obj), "embedded_json"
        except ValueError:
            continue
    return schema.model_validate_json(text), "direct"  # raises with the original error


class CostMeter:
    def __init__(self, path: Path = COST_LOG, daily_cap_usd: float | None = None) -> None:
        self.path = path
        self.daily_cap_usd = daily_cap_usd if daily_cap_usd is not None else float(os.environ.get("META_DAILY_COST_CAP_USD", "10"))

    def spent_today(self) -> float:
        if not self.path.exists():
            return 0.0
        today = datetime.now(timezone.utc).date().isoformat()
        total = 0.0
        for line in self.path.read_text().splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("time", "").startswith(today):
                total += r.get("cost_usd", 0.0)
        return total

    def check(self) -> None:
        spent = self.spent_today()
        if spent >= self.daily_cap_usd:
            raise CostCapExceeded(f"daily cap ${self.daily_cap_usd:.2f} reached (spent ${spent:.4f} today)")

    def record(self, entry: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(entry) + "\n")


def _profile_or_none() -> str | None:
    try:
        return active_profile()
    except ValueError:
        return None


class ModelAdapter:
    def __init__(self, *, api_key: str | None = None, meter: CostMeter | None = None) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("META_API_KEY", "")
        self.meter = meter or CostMeter()
        self.contributor_enabled = os.environ.get("META_CONTRIBUTOR_TIER", "false").lower() == "true"
        self._client = None

    @property
    def client(self):
        if self._client is None:
            if not self.api_key:
                raise RuntimeError("META_API_KEY is not set")
            from openai import OpenAI

            # Retries are done here (to log attempts and respect Meta's no-retry list), not by the SDK.
            self._client = OpenAI(api_key=self.api_key, base_url=BASE_URL, max_retries=0)
        return self._client

    # ---- request building (also used by --dry-run) ---------------------------------------------

    def resolve_model(self, job: JobConfig, data_scope: DataScope, contributor: bool) -> str:
        if not contributor:
            return job.model
        if data_scope != "test_app":
            raise ContributorNotAllowed("Contributor tier is only for our own test apps, never real screens or data")
        if not self.contributor_enabled:
            raise ContributorNotAllowed("META_CONTRIBUTOR_TIER is not true in .env")
        # A model with no Contributor variant (Wonder) runs on the standard tier: the stricter one, never the other way.
        return CONTRIBUTOR_MODELS.get(job.model, job.model)

    def build_request(
        self,
        job: JobConfig | str,
        content: list[dict[str, Any]] | str,
        *,
        instructions: str | None = None,
        data_scope: DataScope = "real",
        contributor: bool = False,
        **overrides: Any,
    ) -> dict[str, Any]:
        cfg = job_config(job)
        if overrides:
            cfg = replace(cfg, **{k: v for k, v in overrides.items() if k in JobConfig.__dataclass_fields__})
        if isinstance(content, str):
            content = [{"type": "input_text", "text": content}]
        req: dict[str, Any] = {
            "model": self.resolve_model(cfg, data_scope, contributor),
            "input": [{"type": "message", "role": "user", "content": content}],
            "store": False,  # nothing kept server-side; we never use previous_response_id
        }
        if instructions:
            req["instructions"] = instructions
        if cfg.effort:
            req["reasoning"] = {"effort": cfg.effort}
        if cfg.schema is not None:
            req["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": cfg.schema.__name__,
                    "schema": strict_json_schema(cfg.schema),
                    "strict": True,
                }
            }
        if cfg.max_output_tokens:
            req["max_output_tokens"] = cfg.max_output_tokens
        if cfg.cache_key:
            req["prompt_cache_key"] = cfg.cache_key
        if cfg.cache_retention:
            req["prompt_cache_retention"] = cfg.cache_retention
        return req

    # ---- calling ------------------------------------------------------------------------------

    def call(
        self,
        job: JobConfig | str,
        content: list[dict[str, Any]] | str,
        *,
        instructions: str | None = None,
        data_scope: DataScope = "real",
        contributor: bool = False,
        task_id: str | None = None,
        **overrides: Any,
    ) -> ModelResult:
        cfg = job_config(job)
        if overrides:
            cfg = replace(cfg, **{k: v for k, v in overrides.items() if k in JobConfig.__dataclass_fields__})
        req = self.build_request(cfg, content, instructions=instructions, data_scope=data_scope, contributor=contributor)
        return self.send(cfg, req, task_id=task_id, data_scope=data_scope)

    def send(self, cfg: JobConfig, req: dict[str, Any], *, task_id: str | None = None, data_scope: DataScope = "real") -> ModelResult:
        import openai

        self.meter.check()
        attempts = 0
        start = time.perf_counter()
        last_error: Exception | None = None
        resp = None
        while attempts <= cfg.retries:
            attempts += 1
            try:
                resp = self.client.responses.create(**req, timeout=cfg.timeout_s)
                break
            except openai.APIStatusError as e:
                last_error = e
                # Meta: retry 429/500/503 with backoff; never retry 4xx; 504 → use background/streaming instead.
                if e.status_code not in (429, 500, 502, 503) or attempts > cfg.retries:
                    break
                retry_after = e.response.headers.get("retry-after") if e.response is not None else None
                delay = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else 0.75 * 2 ** (attempts - 1)
                time.sleep(min(delay, 60) + random.uniform(0, 1))
            except (openai.APITimeoutError, openai.APIConnectionError) as e:
                last_error = e
                if attempts > cfg.retries:
                    break
                time.sleep(0.75 * 2 ** (attempts - 1) + random.uniform(0, 1))
        latency_ms = (time.perf_counter() - start) * 1000

        usage = usage_dict(resp) if resp is not None else {}
        model = req["model"]
        cost = token_cost(model, usage)
        cost_std = token_cost(standard_model(model), usage)
        if model == "sam-3.1":
            cost = cost_std = usage.get("images_processed", 1) * SAM_PRICE_PER_IMAGE
        self.meter.record(
            {
                "time": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "job": cfg.name,
                "model": model,
                "effort": req.get("reasoning", {}).get("effort"),
                "data_scope": data_scope,
                "profile": _profile_or_none(),
                "task_id": task_id,
                "ok": resp is not None,
                "error": None if resp is not None else f"{type(last_error).__name__}: {last_error}",
                "attempts": attempts,
                "latency_ms": round(latency_ms, 1),
                **usage,
                "cost_usd": round(cost, 6),
                "cost_at_standard_usd": round(cost_std, 6),
            }
        )
        if resp is None:
            raise last_error or RuntimeError("model call failed")

        text = getattr(resp, "output_text", "") or ""
        parsed = None
        if cfg.schema is not None and text:
            parsed, how = parse_structured(cfg.schema, resp, text)
            if how != "direct":
                # Seen in Phase 1 (2 of ~60 calls): a sentence of preamble before the schema JSON.
                self.meter.record({"time": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "job": cfg.name,
                                   "event": "structured_output_recovered", "how": how, "text_head": text[:120],
                                   "output_items": [getattr(i, "type", "?") for i in getattr(resp, "output", []) or []],
                                   "cost_usd": 0.0})
        return ModelResult(
            job=cfg.name,
            model=model,
            text=text,
            parsed=parsed,
            usage=usage,
            cost_usd=cost,
            cost_at_standard_usd=cost_std,
            latency_ms=latency_ms,
            attempts=attempts,
            response_id=getattr(resp, "id", None),
            raw=resp,
        )

    def list_models(self) -> list[str]:
        """GET /v1/models (no tokens generated)."""
        return [m.id for m in self.client.models.list().data]
