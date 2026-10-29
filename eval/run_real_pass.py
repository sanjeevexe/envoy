"""A fresh routine pass over the Phase 7 real-app set (eval/final_real.py) on envoy-real, written to a dated folder: the
frozen results in eval/results/final/ (real.json, real_compiled/) and their traces in data/runs/ stay as they are.

  META_DAILY_COST_CAP_USD=... uv run --project backend python eval/run_real_pass.py [--only starbucks,amazon]

Per workflow, the way Phase 7 reran routines (run_real_apps.run_one with --regression): no agent run; the Phase 7 agent
trace is compiled again on this commit with Wonder's cached answer (0 model calls), then rerun with the same input and a
second input, strict first and with repair only if that fails. The traces are copied to a new task prefix first, so
the reruns don't replace Phase 7's. Target is left out (off limits). The hand-repaired Starbucks routine
(real_compiled/starbucks.yaml, v2) runs as an extra row, as it is the version the product uses.

Every approval is declined; nothing is typed into a password field; envoy-real is never snapshot-restored. Results:
<out>/real_pass.json and real_pass.md, compared row by row with eval/results/final/real.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from final_common import REPO, cell_cost

import run_real_apps as rr  # noqa: E402
from devices.emulator import EmulatorDevice  # noqa: E402
import final_real  # noqa: E402
from final_real import real_md, stages  # noqa: E402
from models.adapter import ModelAdapter  # noqa: E402
from policy.approvals import ScriptedApprover  # noqa: E402
from routines.executor import ExecConfig, RoutineExecutor  # noqa: E402
from routines.model import load_yaml  # noqa: E402

FINAL = REPO / "eval" / "results" / "final"
SKIP = {"target": "Target is off limits (bot check; ground rules)", "target_search": "Target is off limits (bot check; ground rules)"}


class _Args:
    rerun_agent, reuse_spec, regression = False, False, True


def stage_of(r: dict[str, Any], st: str) -> str:
    return (r.get("first_run") or "–") if st == "first run" else rr.stage(r, st)


async def repaired_starbucks(device: Any, prefix: str) -> dict[str, Any]:
    """The hand-repaired Starbucks routine (v2), same and second input, strict then repair: graded like run_one."""
    wf = next(w for w in rr.WORKFLOWS if w.id == "starbucks")
    routine = load_yaml((FINAL / "real_compiled" / "starbucks.yaml").read_text())
    ex = RoutineExecutor(device, adapter=ModelAdapter(), approver=ScriptedApprover(approve=False), config=ExecConfig(data_scope="real"))
    runs = []
    for name, inputs, pattern in (("same input", {"drink_name": "Caffè Latte"}, wf.expect), ("new input", {"drink_name": "Caramel Macchiato"}, wf.expect_second)):
        for allow_repair in (False, True):
            tid = f"{prefix}-starbucks_v2-{name.replace(' ', '-')}-{'repair' if allow_repair else 'strict'}"
            out = await ex.run(routine, inputs, task_id=tid, launch="fresh", allow_repair=allow_repair, allow_agent=False)
            text = " | ".join(v for v in out.outputs.values() if v)
            result = "fail" if out.status != "done" else (("pass" if not allow_repair and out.model_calls == 0 else "pass after repair")
                                                          if rr.right(text, pattern, inputs, True) else "wrong")
            runs.append({"case": name, "inputs": inputs, "repair_allowed": allow_repair, "status": out.status, "result": result,
                         "detail": out.detail[:300], "outputs": out.outputs, "rung": out.rung, "model_calls": out.model_calls,
                         "cost_usd": round(out.cost_at_standard_usd, 4), "duration_s": out.duration_s, "steps": rr.step_rows(out)})
            print(f"routine  starbucks_v2       {name:10s} {'repair' if allow_repair else 'strict'}: {result:17s} calls={out.model_calls} "
                  f"{out.duration_s:5.1f}s {out.outputs} {out.detail[:60]}", flush=True)
            if out.status == "done":
                break
    return {"app": wf.app, "category": wf.category, "goal": wf.goal, "graded_by": "truth", "first_run": "n/a (hand-repaired routine)",
            "expect_second": wf.expect_second, "compile": {"compiled": True, "routine": routine.routine, "steps": len(routine.steps),
                                                          "note": "hand-repaired v2, not recompiled"}, "routine_runs": runs}


def compare(new: dict[str, Any], old: dict[str, Any]) -> list[dict[str, Any]]:
    """Each stage before (Phase 7) and now; a pass a person read as the wrong value says so."""
    checks = final_real.hand_checks()

    def cell(k: str, r: dict[str, Any], st: str) -> str:
        return "wrong value (by hand)" if final_real.verdict(k, r, st, checks) == "wrong" else stage_of(r, st)
    out = []
    for k in old:
        o, n = old[k], new.get(k)
        row = {"workflow": k}
        for st in ("same input", "new input"):
            row[st] = {"before": cell(k, o, st), "now": cell(k, n, st) if n else "skipped"}
        row["compiled"] = {"before": bool((o.get("compile") or {}).get("compiled")), "now": bool(((n or {}).get("compile") or {}).get("compiled"))}
        out.append(row)
    return out


def use_hand_checks(out: Path) -> None:
    """Verdicts read for this pass's answers live in <out>/hand_checks.json, beside Phase 7's (which stay as they are)."""
    frozen = final_real.hand_checks
    local = out / "hand_checks.json"
    final_real.hand_checks = lambda: {**frozen(), **(json.loads(local.read_text()) if local.exists() else {})}


def md(rows: dict[str, Any], cmp: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    st = stages({k: v for k, v in rows.items() if not k.endswith("_v2")})
    head = [f"# Real-app routine pass, {meta['date']}", "",
            f"On `{meta['commit']}` (main with the repair fixes), envoy-real, standard tier, {meta['minutes']} min, "
            f"{meta['calls']} model calls, ${meta['usd']:.4f} at standard prices. Method: Phase 7's routine reruns "
            "(`run_real_apps.run_one --regression`): each Phase 7 agent trace compiled again on this commit with Wonder's cached "
            "answer, then rerun on the same input and a second input. Target was left out (off limits). Frozen Phase 7 results: "
            "`eval/results/final/real.md`.", "",
            "| Workflow | Same input: Phase 7 | Same input: now | New input: Phase 7 | New input: now |", "| --- | --- | --- | --- | --- |"]
    for c in cmp:
        head.append(f"| {c['workflow']} | {c['same input']['before']} | {c['same input']['now']} | {c['new input']['before']} | {c['new input']['now']} |")
    if "starbucks_v2" in rows:
        r = rows["starbucks_v2"]
        head.append(f"| starbucks (repaired v2) | – | {rr.stage(r, 'same input')} | – | {rr.stage(r, 'new input')} |")
    head += ["", "## The full table (Phase 7's format)", ""]
    return "\n".join(head) + "\n" + real_md({k: v for k, v in rows.items() if not k.endswith("_v2")}, st)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO / "eval" / "results" / f"real_pass_{time.strftime('%Y-%m-%d')}"))
    ap.add_argument("--only", default="")
    ap.add_argument("--report", action="store_true", help="rebuild real_pass.md from real_pass.json (after reading answers by hand)")
    args = ap.parse_args()
    out = Path(args.out)
    use_hand_checks(out)
    if args.report:
        d = json.loads((out / "real_pass.json").read_text())
        d["compare"] = compare(d["workflows"], json.loads((FINAL / "real.json").read_text())["workflows"])
        d["stages"] = stages({k: v for k, v in d["workflows"].items() if not k.endswith("_v2")})
        (out / "real_pass.json").write_text(json.dumps(d, indent=1, ensure_ascii=False, default=str))
        (out / "real_pass.md").write_text(md(d["workflows"], d["compare"], d["meta"]))
        return
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    (out / "compiled").mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%m%d%H%M")
    prefix = f"rp{stamp}-real"
    rr.TASK_PREFIX, rr.SPEC_DIR, rr.PRIVATE_DIR = prefix, out / "compiled", REPO / "data" / f"real_routines_{out.name}"
    rr.PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    frozen = json.loads((FINAL / "real.json").read_text())["workflows"]
    prev = json.loads((out / "real_pass.json").read_text())["workflows"] if args.only and (out / "real_pass.json").exists() else {}
    device = EmulatorDevice("envoy-real").connect()
    adapter = ModelAdapter()
    approver = ScriptedApprover(approve=False)
    t0 = time.time()
    rows: dict[str, Any] = dict(prev)
    for wf in rr.WORKFLOWS:
        if args.only and wf.id not in args.only.split(","):
            continue
        if wf.id in SKIP:
            rows[wf.id] = {"app": wf.app, "category": wf.category, "goal": wf.goal, "graded_by": wf.graded_by, "first_run": "skipped", "note": SKIP[wf.id]}
            continue
        src = frozen.get(wf.id, {}).get("run", {}).get("run_id")
        src_dir, dst_dir = rr.RUNS / f"f7-{src}-real-{wf.id}", rr.RUNS / f"{prefix}-{wf.id}"
        if not dst_dir.exists():
            shutil.copytree(src_dir, dst_dir)  # the Phase 7 agent trace, under this pass's prefix
        for name in (f"{wf.id}.spec.json",):  # Wonder's cached answer for that trace
            for d in (FINAL / "real_compiled", REPO / "data" / "final" / "real_routines"):
                dst = (rr.PRIVATE_DIR if wf.private else rr.SPEC_DIR) / name
                if (d / name).exists() and not dst.exists():
                    shutil.copy2(d / name, dst)
        try:
            row = await rr.run_one(wf, _Args(), device, adapter, approver)
        except Exception as e:  # noqa: BLE001 - one app's failure must not stop the pass
            row = {"app": wf.app, "category": wf.category, "goal": wf.goal, "graded_by": wf.graded_by, "first_run": "error",
                   "error": f"{type(e).__name__}: {e}"[:300]}
        finally:
            for cmd in (["am", "force-stop", wf.app], ["input", "keyevent", "KEYCODE_HOME"]):
                try:
                    device.adb.shell(cmd)
                except Exception:  # noqa: BLE001
                    pass
        row["source_trace"] = f"f7-{src}-real-{wf.id}"
        row["cost"] = cell_cost(f"{prefix}-{wf.id}")
        rows[wf.id] = row
    if not args.only or "starbucks" in args.only.split(","):
        rows["starbucks_v2"] = await repaired_starbucks(device, prefix)
        rows["starbucks_v2"]["cost"] = cell_cost(f"{prefix}-starbucks_v2")
        device.adb.shell(["am", "force-stop", "com.starbucks.mobilecard"])
        device.adb.shell(["input", "keyevent", "KEYCODE_HOME"])
    calls = sum((r.get("cost") or {}).get("calls", 0) for r in rows.values())
    usd = sum((r.get("cost") or {}).get("standard_usd", 0.0) for r in rows.values())
    meta = {"date": time.strftime("%Y-%m-%d %H:%M %Z"), "commit": commit,  # the code this process loaded
            "minutes": round((time.time() - t0) / 60, 1), "prefix": prefix, "calls": calls, "usd": round(usd, 4)}
    order = [w.id for w in rr.WORKFLOWS] + ["starbucks_v2"]
    rows = dict(sorted(rows.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else 99))
    cmp = compare(rows, frozen)
    (out / "real_pass.json").write_text(json.dumps({"meta": meta, "workflows": rows, "compare": cmp,
                                                    "stages": stages({k: v for k, v in rows.items() if not k.endswith("_v2")})},
                                                   indent=1, ensure_ascii=False, default=str))
    (out / "real_pass.md").write_text(md(rows, cmp, meta))
    print(json.dumps(meta), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
