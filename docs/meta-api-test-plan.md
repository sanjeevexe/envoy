# Meta API test plan (Phase 0 gate)

The last step of Phase 0. Run once credits arrive. The whole check costs well under $2; the script prints its own estimate and refuses to run if the worst case is over `--max-cost` (default $2).

**The gate:** a Meta model reads a real emulator screen and returns a valid action that runs on the phone (check 1).

## Before you run it (about 5 minutes)

1. Put the key in `.env` (gitignored):
   ```
   META_API_KEY=<your key>
   ```
   Meta's docs call the variable `MODEL_API_KEY`; Envoy reads `META_API_KEY` and passes it to the SDK explicitly.
2. Start the test emulator. It must have the snapshot `phase0-gate`, which `scripts/capture_fixtures.py` created on Oct 26:
   ```bash
   scripts/start_emulator.sh envoy-test
   ```
3. Preview the requests without sending anything:
   ```bash
   uv run --project backend python scripts/meta_api_check.py --dry-run
   ```

## Run

```bash
uv run --project backend python scripts/meta_api_check.py
```

It prints the planned calls and cost, asks for confirmation, then runs the checks in order. Run a subset with `--only 1,7`. Skip the prompt with `--yes`.

Every call is logged with tokens and dollars to `logs/model_costs.jsonl`. The summary goes to `logs/meta_api_check.json`.

## The checks, expected output, and where results go

| # | Check | What it does | Expected output | Goes into `docs/phase-0-findings.md` |
| --- | --- | --- | --- | --- |
| 1 | **Gate** | Restores `phase0-gate` (Settings home) and observes the live screen. Sends the compact screen to `muse-spark-1.3` (effort `low`, `json_schema` StepOutput) with the goal "Open the Battery settings". Validates the JSON, executes the action on envoy-test, waits for the screen to settle, and checks that Battery settings opened. | `[1] GATE PASS: Battery settings opened  action={'type': 'tap', 'element': 10}` | "Meta API results → Gate"; tick the Phase 0 exit gate |
| 2 | Latency | 10 step calls at `minimal` and 10 at `low`, same screen | One line per run (ms, output, reasoning, cached tokens); median and p90 per effort in the JSON | "Meta API results → Latency"; answers open question **Speed** |
| 3 | Output tokens | From check 2: output and reasoning tokens per step, input tokens, cost per step | `3_output_tokens` in the JSON | "Models and cost" table: replace the 500-output-token estimate |
| 4 | Grounding | Sends the 1080×2400 screenshots with Meta's documented box prompt for 3 targets (Battery row; Airplane mode switch and row). Compares against fixture boxes on the 0–1000 grid. | `[4] the Airplane mode switch  IoU 0.71  center inside: True` | Open question **Grounding on phones** |
| 5 | Prompt caching | Cached-token counts across the 20 text calls (stable `instructions` prefix, `prompt_cache_key`, `prompt_cache_retention: "24h"`), plus 2 identical calls with a screenshot | `[5] caching: 19/20 text calls had cached tokens` | Open question **Limits** (minimum prompt length for caching) |
| 6 | SAM 3.1 | One `sam-3.1` call on the Settings screenshot with the prompt "button", `include_confidence: "true"` | `[6] SAM 3.1 'button': N objects in X ms` (special-token text parsed for `<\|box;…\|>` records) | Open question **Grounding on phones** (does SAM segment UI usefully) |
| 7 | Muse Wonder access | `GET /v1/models`, then one tiny `muse-wonder-1.0` call (effort `minimal`) | `[7] muse-wonder-1.0: listed=True call_ok=True`, or the 403/404 error | Open question **Credits** (do they cover Wonder) |

## If something fails

- **401:** wrong key. **402** `billing_not_configured`: credits are not attached to the key's team yet.
- **400 on the schema:** our step schema breaks Meta's strict subset.
  - Run `uv run --project backend python -c "from models.schemas import *; print(check_strict_subset(STEP_SCHEMA))"`.
  - Then retry with `strict` removed in `backend/models/adapter.py`. Meta says decoding is constrained either way.
- **400 on `prompt_cache_retention` or `store`:** delete that key in `ModelAdapter.build_request` and rerun with `--only` for the failed checks.
- **403 or 404 on Wonder:** expected if credits don't cover it. Record it; routine compiling then uses Spark at high effort (design doc fallback).
- **The gate fails because the model picked the wrong element:** look at `screen_before` and `model_output` in the JSON.
  - A wrong element number is a prompt or format issue; fix it in Phase 1.
  - An invalid JSON or schema error is an API issue: report it.

## What the dry run proves (done Oct 26)

- The script exits immediately without `META_API_KEY` (unless `--dry-run`).
- Every request builds from the fixtures, with the schema, effort, caching keys and images in the documented shapes.
- The cost estimate stays under $2 (see the findings for the numbers).
