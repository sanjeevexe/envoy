"""What every Phase 7 suite shares: where results go, what each run records about itself, and what it cost.

Every suite writes `eval/results/final/<suite>.json` (and a short `<suite>.md`) with a `meta` block: the commit and whether
it is the `eval-final` tag, uncommitted changes outside the results folder, the models, tier and model profile (and whether
`ENVOY_MODEL_PROFILE` or the adapter's default chose it), the devices, wall time, and the model calls, tokens and dollars it
caused, with the profile each call was logged under. Costs are summed from `logs/model_costs.jsonl` by the suite's
task-ID prefix, so calls from anything else on this Mac (the API, another eval) are never counted.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "eval"))
sys.path.insert(0, str(REPO / "backend"))

from models.adapter import COST_LOG, JOBS, active_profile, job_config  # noqa: E402

OUT = REPO / "eval" / "results" / "final"
TAG = "eval-final"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _git(*args: str, strip: bool = True) -> str:
    out = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True).stdout
    return out.strip() if strip else out


def dirty_paths(porcelain: str) -> list[str]:
    """What `git status --porcelain` shows that could change what a suite runs. Changes under eval/results/, data/ and logs/
    are what suites and the app write, and an untracked file counts only where code runs from (backend/, eval/, scripts/):
    the main checkout keeps untracked prompts. Each line keeps its two status columns, so nothing may strip the output (on
    Oct 31 a stripped first line read " M data/…" as "ata/…" and every suite was marked dirty, never `eval-final`)."""
    out = []
    for line in porcelain.splitlines():
        status, path = line[:2], line[3:].strip('"')
        if not path or path.startswith(("eval/results/", "data/", "logs/")):
            continue
        if status == "??" and not path.startswith(("backend/", "eval/", "scripts/")):
            continue
        out.append(path)
    return out


def code_state() -> dict[str, Any]:
    """The commit a suite ran on, and whether anything uncommitted could change it (`dirty_paths`)."""
    dirty = dirty_paths(_git("status", "--porcelain", "--untracked-files=all", strip=False))
    tags = _git("tag", "--points-at", "HEAD").split()
    return {"commit": _git("rev-parse", "HEAD"), "short": _git("rev-parse", "--short", "HEAD"), "tags": tags,
            "is_eval_final": TAG in tags and not dirty, "dirty": dirty[:20], "branch": _git("rev-parse", "--abbrev-ref", "HEAD")}


def models(contributor: bool) -> dict[str, Any]:
    """The models and efforts each job uses, as the adapter will resolve them, and the profile that chose them."""
    jobs = {k: {"model": (j.model + "-contributor") if contributor and j.model.startswith("muse-spark") else j.model, "effort": j.effort}
            for k, j in ((k, job_config(k)) for k in JOBS) if k in ("step", "plan", "repair", "match", "compile", "extract", "answer", "grounding", "choose")}
    overrides = {k: os.environ[f"ENVOY_MODEL_{k.upper()}"].strip() for k in JOBS if os.environ.get(f"ENVOY_MODEL_{k.upper()}", "").strip()}
    return {"tier": "contributor" if contributor else "standard", "profile": active_profile(),
            "profile_from": "ENVOY_MODEL_PROFILE" if os.environ.get("ENVOY_MODEL_PROFILE", "").strip() else "the adapter's default",
            "overrides": overrides, "jobs": jobs}


def profile_text(m: dict[str, Any]) -> str:
    """A run's models in words, from its meta's models block: "the `hybrid` profile (Muse Wonder for compile, plan, …)"."""
    wonder = sorted(k for k, v in (m.get("jobs") or {}).items() if str(v.get("model", "")).startswith("muse-wonder"))
    name = f"the `{m['profile']}` profile" if m.get("profile") else "a profile it didn't record"
    return f"{name} (Muse Wonder for {', '.join(wonder) or 'no job'}; Muse Spark for the rest)"


def run_id() -> str:
    """A short ID unique to one invocation; every task ID in it starts with f7-<run_id>, which is how costs are attributed."""
    return datetime.now().strftime("%m%d%H%M%S")


def costs(prefixes: Iterable[str], since: str | None = None) -> dict[str, Any]:
    """Model calls, tokens and dollars from the cost log whose task ID starts with one of `prefixes` (and, if given, logged
    at or after `since`). By job, by model and by the profile each call was logged under too."""
    pre = tuple(prefixes)
    tot: dict[str, Any] = defaultdict(float)
    by_job: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    by_model: dict[str, float] = defaultdict(float)
    by_profile: dict[str, float] = defaultdict(float)
    if not COST_LOG.exists():
        return {}
    with COST_LOG.open() as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            tid = r.get("task_id") or ""
            if not tid.startswith(pre) or (since and r.get("time", "") < since):
                continue
            for k in ("input_tokens", "cached_tokens", "output_tokens", "reasoning_tokens"):
                tot[k] += r.get(k) or 0
            tot["calls"] += 1
            tot["errors"] += 0 if r.get("ok", True) else 1
            tot["billed_usd"] += r.get("cost_usd") or 0
            tot["standard_usd"] += r.get("cost_at_standard_usd") or 0
            j = by_job[r.get("job", "?")]
            j["calls"] += 1
            j["standard_usd"] += r.get("cost_at_standard_usd") or 0
            by_model[r.get("model", "?")] += 1
            by_profile[r.get("profile") or "not logged"] += 1
    out = {k: (round(v, 4) if k.endswith("usd") else int(v)) for k, v in tot.items()}
    out["by_job"] = {k: {"calls": int(v["calls"]), "standard_usd": round(v["standard_usd"], 4)} for k, v in by_job.items()}
    out["by_model"] = {k: int(v) for k, v in by_model.items()}
    out["by_profile"] = {k: int(v) for k, v in by_profile.items()}
    return out


def cell_cost(task_id: str) -> dict[str, Any]:
    """Calls, tokens and standard-price dollars of one run: the task ID itself and everything it started (-match, -agent, …)."""
    c = costs([task_id], None)
    return {"calls": c.get("calls", 0), "input_tokens": c.get("input_tokens", 0), "cached_tokens": c.get("cached_tokens", 0),
            "output_tokens": c.get("output_tokens", 0), "reasoning_tokens": c.get("reasoning_tokens", 0),
            "standard_usd": c.get("standard_usd", 0.0), "billed_usd": c.get("billed_usd", 0.0)}


def spend_total() -> dict[str, float]:
    """Everything this checkout's log has ever billed (for the budget line in reports)."""
    billed = std = 0.0
    if COST_LOG.exists():
        for line in COST_LOG.open():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            billed += r.get("cost_usd") or 0
            std += r.get("cost_at_standard_usd") or 0
    return {"billed_usd": round(billed, 3), "standard_usd": round(std, 3)}


class Suite:
    """One suite's record: `with Suite("systems", contributor=False) as s: ...; s.save(payload, markdown)`."""

    def __init__(self, name: str, *, contributor: bool = False, devices: list[str] | None = None, label: str = "") -> None:
        self.name = name
        self.label = label or name
        self.contributor = contributor
        self.rid = run_id()
        self.prefix = f"f7-{self.rid}"
        self.devices = devices or []
        self.started = now()
        self.t0 = time.time()
        self.code = code_state()
        self.extra_prefixes: list[str] = []

    def tid(self, *parts: Any) -> str:
        """A task ID inside this suite run (costs are attributed by its prefix)."""
        return "-".join([self.prefix, *[str(p) for p in parts]])

    def __enter__(self) -> "Suite":
        tag = "eval-final" if self.code["is_eval_final"] else f"{self.code['short']}{' (dirty)' if self.code['dirty'] else ''}"
        print(f"== {self.name} on {tag} · {models(self.contributor)['tier']} tier · run {self.rid}", flush=True)
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def meta(self) -> dict[str, Any]:
        return {"suite": self.name, "run_id": self.rid, "started": self.started, "finished": now(),
                "wall_s": round(time.time() - self.t0, 1), "code": self.code, "models": models(self.contributor),
                "devices": self.devices, "cost": costs([self.prefix, *self.extra_prefixes], self.started),
                "spend_total_this_checkout": spend_total(), "host": os.uname().nodename.split(".")[0]}

    def stamp(self) -> dict[str, Any]:
        """Which run produced a part (a suite rerun in parts keeps the others' stamps)."""
        return {"run_id": self.rid, "commit": self.code["short"], "is_eval_final": self.code["is_eval_final"], "dirty": bool(self.code["dirty"]),
                "cost": costs([self.prefix], self.started)}

    def save(self, payload: dict[str, Any], markdown: str | None = None, name: str | None = None) -> Path:
        OUT.mkdir(parents=True, exist_ok=True)
        name = name or self.name
        doc = {"meta": self.meta(), **payload}
        path = OUT / f"{name}.json"
        path.write_text(json.dumps(doc, indent=1, default=str, ensure_ascii=False))
        if markdown is not None:
            (OUT / f"{name}.md").write_text(header(doc["meta"], self.label) + markdown)
        c = doc["meta"]["cost"]
        print(f"saved {path.relative_to(REPO)} · {c.get('calls', 0)} calls · ${c.get('standard_usd', 0):.3f} at standard prices "
              f"(${c.get('billed_usd', 0):.3f} billed) · {doc['meta']['wall_s']:.0f} s", flush=True)
        return path


def header(meta: dict[str, Any], title: str) -> str:
    c, code = meta.get("cost", {}), meta["code"]
    on = "`eval-final`" if code["is_eval_final"] else f"`{code['short']}`" + (" with uncommitted changes" if code["dirty"] else "")
    return (f"# {title}\n\n"
            f"Run {meta['run_id']} on {on}, {meta['started'][:16].replace('T', ' ')} UTC, {meta['wall_s'] / 60:.0f} min, "
            f"{meta['models']['tier']} tier, {profile_text(meta['models'])}. {c.get('calls', 0)} model calls, ${c.get('standard_usd', 0):.3f} at standard prices "
            f"(${c.get('billed_usd', 0):.3f} billed).\n\n")


def load(name: str) -> dict[str, Any] | None:
    p = OUT / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def pct(a: int, b: int) -> str:
    return f"{a}/{b}" + (f" ({100 * a / b:.0f}%)" if b else "")


def med(xs: list[float], nd: int = 1) -> float | None:
    import statistics
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), nd) if xs else None
