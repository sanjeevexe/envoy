"""Phase 0 Meta Model API check. Spends real credits (estimate printed first; must be under --max-cost).

Usage (from the repo root):
  uv run --project backend python scripts/meta_api_check.py --dry-run     # print requests, send nothing
  uv run --project backend python scripts/meta_api_check.py               # run all checks
  uv run --project backend python scripts/meta_api_check.py --only 1,7    # run some checks

Checks:
  1. GATE: Muse Spark 1.3 reads the live envoy-test screen (Settings home, restored from snapshot
     phase0-gate) and returns a valid action; the action is executed on the emulator and verified.
  2. Latency over 10 runs at `minimal` and 10 at `low` reasoning effort.
  3. Output tokens per step, including reasoning tokens (from check 2).
  4. Grounding accuracy on the tall 1080x2400 screenshots (known boxes from the fixtures).
  5. Prompt caching: cached-token counts on repeated calls with the same prefix.
  6. One SAM 3.1 call on a screenshot with the prompt "button".
  7. Whether muse-wonder-1.0 is accessible (model list + one tiny call).

Results: logs/meta_api_check.json (and every call in logs/model_costs.jsonl). See docs/meta-api-test-plan.md.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

FIX = REPO / "eval" / "fixtures" / "phase0"
GATE_SNAPSHOT = "phase0-gate"
GATE_GOAL = "Open the Battery settings"
LATENCY_RUNS = 10

# Rough token sizes used for the cost estimate (refined after the first real run).
EST_INSTR_TOKENS = 1100  # STEP_INSTRUCTIONS
EST_SCHEMA_TOKENS = 1300  # step JSON schema, if it is counted as input
EST_SCREEN_TOKENS = 450  # step_input with the Settings compact screen
EST_IMAGE_TOKENS = 1500  # one 1080x2400 screenshot (Meta: ~1,300-1,500 for ~1280 px)


def p90(values: list[float]) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, round(0.9 * (len(s) - 1)))]


def fixture(name: str) -> dict:
    folder = FIX / name
    return {
        "meta": json.loads((folder / "meta.json").read_text()),
        "compact": (folder / "compact.txt").read_text().strip(),
        "png": (folder / "screen.png").read_bytes(),
    }


def short(req: dict) -> dict:
    """Request with image data and the long schema elided, for printing."""

    def walk(o):
        if isinstance(o, dict):
            out = {}
            for k, v in o.items():
                if k == "image_url" and isinstance(v, str) and v.startswith("data:"):
                    out[k] = v[:40] + f"...<{len(v)} chars>"
                elif k == "schema":
                    out[k] = f"<json schema, {len(json.dumps(v))} chars>"
                elif k == "instructions":
                    out[k] = v[:80] + f"...<{len(v)} chars>"
                else:
                    out[k] = walk(v)
            return out
        if isinstance(o, list):
            return [walk(x) for x in o]
        return o

    return walk(req)


class Check:
    def __init__(self, args) -> None:
        from models.adapter import JOBS, ModelAdapter

        self.args = args
        self.adapter = ModelAdapter()
        self.jobs = JOBS
        self.results: dict[str, dict] = {}
        self.planned: list[tuple[str, dict, float, float]] = []  # (check, request, expected $, worst $)

    # ---- helpers ----------------------------------------------------------------------------

    def price(self, model: str):
        from models.adapter import TOKEN_PRICES

        return TOKEN_PRICES.get(model, {"input": 0, "cached_input": 0, "output": 0})

    def estimate(self, req: dict, in_tokens: int, out_expected: int) -> tuple[float, float]:
        p = self.price(req["model"])
        worst_out = req.get("max_output_tokens") or 8000
        exp = (in_tokens * p["input"] + out_expected * p["output"]) / 1e6
        worst = (in_tokens * p["input"] + worst_out * p["output"]) / 1e6
        return exp, worst

    def plan(self, check: str, req: dict, in_tokens: int, out_expected: int) -> None:
        exp, worst = self.estimate(req, in_tokens, out_expected)
        self.planned.append((check, req, exp, worst))

    def send(self, job_name: str, req: dict, **kw):
        from dataclasses import replace

        cfg = self.jobs[job_name] if job_name in self.jobs else None
        if cfg is None:
            from models.adapter import JobConfig

            cfg = JobConfig(job_name, req["model"], None)
        if "reasoning" in req:
            cfg = replace(cfg, effort=req["reasoning"]["effort"])
        return self.adapter.send(cfg, req, data_scope="real", **kw)

    def step_request(self, compact: str, effort: str = "low", images: list[bytes] | None = None) -> dict:
        from models.adapter import image_part
        from models.prompts import STEP_INSTRUCTIONS, step_input

        content = [{"type": "input_text", "text": step_input(GATE_GOAL, compact)}]
        for png in images or []:
            content.append(image_part(png))
        return self.adapter.build_request("step", content, instructions=STEP_INSTRUCTIONS, data_scope="real", effort=effort)

    # ---- checks -----------------------------------------------------------------------------

    def build_all(self) -> None:
        from models.adapter import image_part
        from models.prompts import GROUNDING_PROMPT

        home = fixture("settings_home")
        step_in = EST_INSTR_TOKENS + EST_SCHEMA_TOKENS + EST_SCREEN_TOKENS
        if self.want(1):
            self.plan("1 gate (live screen)", self.step_request(home["compact"]), step_in, 600)
        if self.want(2) or self.want(3) or self.want(5):
            for effort in ("minimal", "low"):
                for _ in range(LATENCY_RUNS):
                    self.plan(f"2 latency ({effort})", self.step_request(home["compact"], effort), step_in, 500)
        if self.want(5):
            img_req = self.step_request(home["compact"], "low", images=[home["png"]])
            for _ in range(2):
                self.plan("5 caching (with screenshot)", img_req, step_in + EST_IMAGE_TOKENS, 600)
        if self.want(4):
            for name in ("settings_home", "settings_network_tall"):
                f = fixture(name)
                for key in ("grounding_target", "grounding_target_row"):
                    t = f["meta"].get(key)
                    if not t:
                        continue
                    req = self.adapter.build_request(
                        "grounding",
                        [{"type": "input_text", "text": GROUNDING_PROMPT.format(targets=json.dumps(t["description"]))},
                         image_part(f["png"])],
                        data_scope="real",
                    )
                    req["_target"] = {"fixture": name, **t}
                    self.plan("4 grounding", req, EST_IMAGE_TOKENS + 300, 800)
        if self.want(6):
            sam = {
                "model": "sam-3.1",
                "input": [{"type": "message", "role": "user", "content": [
                    {"type": "input_text", "text": "button"}, image_part(home["png"])]}],
                "metadata": {"include_confidence": "true"},
            }
            self.planned.append(("6 SAM 3.1", sam, 2.5 / 1000, 2.5 / 1000))
        if self.want(7):
            wonder = {
                "model": "muse-wonder-1.0",
                "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Reply with the single word OK."}]}],
                "reasoning": {"effort": "minimal"},
                "max_output_tokens": 300,
                "store": False,
            }
            self.plan("7 Wonder access", wonder, 30, 100)

    def want(self, n: int) -> bool:
        return not self.args.only or n in self.args.only

    def print_plan(self) -> tuple[float, float]:
        exp = sum(p[2] for p in self.planned)
        worst = sum(p[3] for p in self.planned)
        by_check: dict[str, list] = {}
        for c, _, e, w in self.planned:
            by_check.setdefault(c, []).append((e, w))
        print("Planned calls and estimated cost (standard tier):")
        for c, v in by_check.items():
            print(f"  {c:32s} {len(v):3d} calls   expected ${sum(x[0] for x in v):.3f}   worst case ${sum(x[1] for x in v):.3f}")
        print(f"  {'TOTAL':32s} {len(self.planned):3d} calls   expected ${exp:.3f}   worst case ${worst:.3f}  (limit ${self.args.max_cost:.2f})")
        return exp, worst

    async def run_gate(self) -> None:
        """Check 1: live screen → model → action → executed on envoy-test → verified."""
        from devices.emulator import EmulatorDevice
        from models.schemas import StepOutput
        from models.translate import to_device_action

        d = EmulatorDevice("envoy-test").connect()
        await d.snapshot_load(GATE_SNAPSHOT)
        before = await d.wait_until_settled()
        req = self.step_request(before.compact)
        res = self.send("step", req, task_id="phase0-gate")
        step: StepOutput = res.parsed  # type: ignore[assignment]
        action = to_device_action(step.action, before)
        out = {"model_output": json.loads(res.text), "latency_ms": round(res.latency_ms), "usage": res.usage,
               "cost_usd": res.cost_usd, "screen_before": before.compact}
        if action is None:
            out.update(passed=False, why=f"model returned a non-device action: {step.action.type}")
        else:
            result = await d.act(action)
            after = await d.wait_until_settled()
            changed = after.signature != before.signature
            battery_open = "battery" in (after.activity + after.compact).lower() and changed
            out.update(executed=result.model_dump(), screen_after=after.compact, screen_changed=changed,
                       passed=bool(result.ok and battery_open),
                       why="Battery settings opened" if battery_open else "action ran but Battery settings not shown")
        self.results["1_gate"] = out
        print(f"[1] GATE {'PASS' if out['passed'] else 'FAIL'}: {out.get('why')}  action={step.action.model_dump()}")

    def run_latency(self) -> None:
        home = fixture("settings_home")
        per_effort: dict[str, list] = {}
        for effort in ("minimal", "low"):
            rows = []
            for i in range(LATENCY_RUNS):
                res = self.send("step", self.step_request(home["compact"], effort), task_id=f"phase0-latency-{effort}")
                rows.append({"latency_ms": res.latency_ms, **res.usage, "cost_usd": res.cost_usd,
                             "action": res.parsed.action.model_dump() if res.parsed else None})
                print(f"[2] {effort:7s} run {i + 1:2d}: {res.latency_ms:7.0f} ms  out {res.usage.get('output_tokens')}  "
                      f"reasoning {res.usage.get('reasoning_tokens')}  cached {res.usage.get('cached_tokens')}")
            per_effort[effort] = rows
        self.results["2_latency"] = {
            e: {"median_ms": round(statistics.median(r["latency_ms"] for r in rows)),
                "p90_ms": round(p90([r["latency_ms"] for r in rows])),
                "runs": len(rows),
                "correct_action_rate": sum(1 for r in rows if (r["action"] or {}).get("element") == fixture("settings_home")["meta"]["task"]["expected_action"]["element"]) / len(rows)}
            for e, rows in per_effort.items()
        }
        self.results["3_output_tokens"] = {
            e: {"output_median": statistics.median(r.get("output_tokens", 0) for r in rows),
                "output_p90": p90([r.get("output_tokens", 0) for r in rows]),
                "reasoning_median": statistics.median(r.get("reasoning_tokens", 0) for r in rows),
                "input_median": statistics.median(r.get("input_tokens", 0) for r in rows),
                "cost_per_step_median_usd": statistics.median(r["cost_usd"] for r in rows)}
            for e, rows in per_effort.items()
        }
        self._latency_rows = per_effort

    def run_caching(self) -> None:
        rows = [r for rows in getattr(self, "_latency_rows", {}).values() for r in rows]
        home = fixture("settings_home")
        img_rows = []
        req = self.step_request(home["compact"], "low", images=[home["png"]])
        for _ in range(2):
            res = self.send("step", req, task_id="phase0-cache-image")
            img_rows.append(res.usage)
        self.results["5_caching"] = {
            "text_calls": [{k: r.get(k) for k in ("input_tokens", "cached_tokens")} for r in rows],
            "text_cache_hit_calls": sum(1 for r in rows if r.get("cached_tokens")),
            "image_calls": img_rows,
            "works": any(r.get("cached_tokens") for r in rows + img_rows),
        }
        print(f"[5] caching: {self.results['5_caching']['text_cache_hit_calls']}/{len(rows)} text calls had cached tokens; "
              f"image calls cached: {[u.get('cached_tokens') for u in img_rows]}")

    def run_grounding(self) -> None:
        out = []
        for check, req, _, _ in self.planned:
            if check != "4 grounding":
                continue
            target = req.pop("_target")
            res = self.send("grounding", req, task_id="phase0-grounding")
            boxes = res.parsed.objects if res.parsed else []
            tb = target["bbox_1000"]
            row = {"target": target["description"], "fixture": target["fixture"], "truth_1000": tb, "latency_ms": round(res.latency_ms),
                   "usage": res.usage}
            if boxes:
                b = boxes[0]
                pb = [min(1000, max(0, v)) for v in (b.x_min, b.y_min, b.x_max, b.y_max)]
                ix = max(0, min(pb[2], tb[2]) - max(pb[0], tb[0]))
                iy = max(0, min(pb[3], tb[3]) - max(pb[1], tb[1]))
                inter = ix * iy
                union = (pb[2] - pb[0]) * (pb[3] - pb[1]) + (tb[2] - tb[0]) * (tb[3] - tb[1]) - inter
                cx, cy = (pb[0] + pb[2]) / 2, (pb[1] + pb[3]) / 2
                row.update(pred_1000=pb, iou=round(inter / union, 3) if union else 0.0,
                           center_inside=tb[0] <= cx <= tb[2] and tb[1] <= cy <= tb[3],
                           center_error_px=[round((cx - (tb[0] + tb[2]) / 2) * 1080 / 1000), round((cy - (tb[1] + tb[3]) / 2) * 2400 / 1000)])
            else:
                row.update(pred_1000=None, iou=0.0, center_inside=False)
            out.append(row)
            print(f"[4] {row['target']:30s} IoU {row['iou']}  center inside: {row['center_inside']}")
        self.results["4_grounding"] = {"targets": out, "hit_rate": sum(r["center_inside"] for r in out) / max(1, len(out))}

    def run_sam(self) -> None:
        req = next(r for c, r, _, _ in self.planned if c == "6 SAM 3.1")
        res = self.send("sam", req, task_id="phase0-sam")
        boxes = re.findall(r"<\|box;([^|]*)\|>", res.text)
        self.results["6_sam"] = {"latency_ms": round(res.latency_ms), "objects": len(boxes), "boxes": boxes[:40],
                                 "usage": res.usage, "cost_usd": res.cost_usd, "raw_chars": len(res.text)}
        print(f"[6] SAM 3.1 'button': {len(boxes)} objects in {res.latency_ms:.0f} ms")

    def run_wonder(self) -> None:
        out: dict = {}
        try:
            models = self.adapter.list_models()
            out["models_listed"] = models
            out["wonder_listed"] = "muse-wonder-1.0" in models
        except Exception as e:
            out["models_error"] = f"{type(e).__name__}: {e}"
        req = next(r for c, r, _, _ in self.planned if c == "7 Wonder access")
        try:
            res = self.send("compile", req, task_id="phase0-wonder")
            out.update(call_ok=True, text=res.text[:100], usage=res.usage, latency_ms=round(res.latency_ms), cost_usd=res.cost_usd)
        except Exception as e:
            status = getattr(e, "status_code", None)
            out.update(call_ok=False, status=status, error=f"{type(e).__name__}: {e}"[:400])
        self.results["7_wonder"] = out
        print(f"[7] muse-wonder-1.0: listed={out.get('wonder_listed')} call_ok={out.get('call_ok')} {out.get('error', '')[:120]}")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print the requests and the cost estimate; send nothing")
    ap.add_argument("--only", type=lambda s: [int(x) for x in s.split(",")], default=None)
    ap.add_argument("--max-cost", type=float, default=2.0, help="refuse to run if the worst-case estimate is higher")
    ap.add_argument("--yes", action="store_true", help="do not ask for confirmation after the estimate")
    args = ap.parse_args()

    if not args.dry_run and not os.environ.get("META_API_KEY"):
        print("META_API_KEY is not set (add it to .env). Nothing was sent.", file=sys.stderr)
        return 2

    c = Check(args)
    c.build_all()
    exp, worst = c.print_plan()

    if args.dry_run:
        print("\nDRY RUN: requests that would be sent (one per distinct shape):")
        seen = set()
        for check, req, _, _ in c.planned:
            key = (check, req.get("model"), json.dumps(req.get("reasoning")))
            if key in seen:
                continue
            seen.add(key)
            print(f"\n--- {check} → POST {os.environ.get('META_API_BASE_URL', 'https://api.meta.ai/v1')}/responses")
            print(json.dumps(short({k: v for k, v in req.items() if not k.startswith("_")}), indent=1, ensure_ascii=False)[:2500])
        if c.want(1):
            print(f"\n(check 1 would first restore envoy-test snapshot '{GATE_SNAPSHOT}', observe the live screen, "
                  "send it as above, then execute the returned action on the emulator)")
        if c.want(7):
            print("(check 7 also calls GET /v1/models, which generates no tokens)")
        print("\nDry run finished: nothing was sent.")
        return 0

    if worst > args.max_cost:
        print(f"Worst-case estimate ${worst:.2f} is above --max-cost ${args.max_cost:.2f}; not running.", file=sys.stderr)
        return 3
    if not args.yes and input(f"Send {len(c.planned)} requests (expected ${exp:.2f})? [y/N] ").strip().lower() != "y":
        return 1

    started = time.time()
    if c.want(1):
        await c.run_gate()
    if c.want(2) or c.want(3) or c.want(5):
        c.run_latency()
    if c.want(5):
        c.run_caching()
    if c.want(4):
        c.run_grounding()
    if c.want(6):
        c.run_sam()
    if c.want(7):
        c.run_wonder()

    spent = sum(r.get("cost_usd", 0) for r in map(json.loads, (REPO / "logs" / "model_costs.jsonl").read_text().splitlines())
                if r.get("time", "") >= datetime.fromtimestamp(started, timezone.utc).isoformat())
    c.results["summary"] = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            "estimated_usd": round(exp, 4), "spent_usd": round(spent, 4),
                            "gate_passed": c.results.get("1_gate", {}).get("passed")}
    (REPO / "logs" / "meta_api_check.json").write_text(json.dumps(c.results, indent=2, ensure_ascii=False, default=str))
    print(f"\nSpent ${spent:.4f} (estimated ${exp:.4f}). Results: logs/meta_api_check.json")
    return 0 if c.results["summary"]["gate_passed"] in (True, None) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
