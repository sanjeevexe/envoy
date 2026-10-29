"""Is the Meta API key in .env usable? One tiny call to each model Envoy uses (Muse Spark, Muse Wonder), about $0.001 in all.

Run it after changing the key, before restarting the API or starting a run (on Oct 29 every call failed with
"402 Billing verification failed" until the account was replaced). It never prints the key.

  uv run --project backend python scripts/check_model_key.py        # exit 0 if both models answer
"""

from __future__ import annotations

import sys
import time

from pydantic import ValidationError

from models.adapter import JobConfig, ModelAdapter
from models.schemas import MemoryAnswer

PROBES = [
    JobConfig("keycheck", "muse-spark-1.3", "low", MemoryAnswer, max_output_tokens=300),
    JobConfig("keycheck", "muse-wonder-1.0", "low", MemoryAnswer, max_output_tokens=300),
]


def main() -> int:
    adapter = ModelAdapter()
    ok = True
    for cfg in PROBES:
        try:
            res = adapter.call(cfg, "QUESTION: What is 2 + 2?\n\nNOTES:\n(none)\n", instructions="Answer the question briefly.",
                               data_scope="test_app", task_id=f"keycheck-{time.strftime('%m%d-%H%M%S')}")
            print(f"ok    {cfg.model:16s} {res.latency_ms:6.0f} ms  ${res.cost_at_standard_usd:.5f}")
        except ValidationError as e:
            # The model answered, only not in the probe's shape: the key and the account work (seen on Oct 29).
            print(f"ok    {cfg.model:16s} answered (reply outside the probe's schema: {str(e).splitlines()[0][:80]})")
        except Exception as e:  # noqa: BLE001 - report every failure kind, without the request (it carries no key, but stay terse)
            ok = False
            print(f"FAIL  {cfg.model:16s} {type(e).__name__}: {str(e)[:160]}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
