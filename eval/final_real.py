"""A4 real apps: the real-app test set (eval/run_real_apps.py) on envoy-real, all 18 read-only workflows, with fresh agent
runs on this commit and fresh compiles, scored at the four places learning can break.

Standard tier only (real apps). Every approval is declined by the script, sign-ins hand off, nothing is typed into a password
field, and outputs holding personal data are redacted. envoy-real is never snapshot-restored; a "reset" is a fresh launch.
"""

from __future__ import annotations

from typing import Any

from final_common import OUT, REPO, Suite, cell_cost

import run_real_apps as rr  # noqa: E402
from devices.emulator import EmulatorDevice  # noqa: E402
from models.adapter import ModelAdapter  # noqa: E402
from policy.approvals import ScriptedApprover  # noqa: E402


class _Args:
    rerun_agent, reuse_spec, regression = True, False, False


def stages(rows: dict[str, Any]) -> dict[str, Any]:
    n = len(rows)
    second = [r for r in rows.values() if r.get("expect_second")]
    bots = sorted({k for k, r in rows.items() if "bot check" in (r.get("first_run"), rr.stage(r, "same input"), rr.stage(r, "new input"))})
    return {"n": n, "first_run": sum(r.get("first_run") == "pass" for r in rows.values()),
            "compiled": sum(bool(r.get("compile", {}).get("compiled")) for r in rows.values()),
            "same_input": sum(rr.stage(r, "same input") == "pass" for r in rows.values()),
            "same_input_with_repair": sum(rr.stage(r, "same input") in ("pass", "pass after repair") for r in rows.values()),
            "n_second": len(second), "new_input": sum(rr.stage(r, "new input") == "pass" for r in second), "bot_checks": bots}


def real_md(rows: dict[str, Any], st: dict[str, Any]) -> str:
    md = ["| Stage | Passed |", "| --- | --- |",
          f"| 1. First run: the agent gives a right answer | {st['first_run']}/{st['n']} |",
          f"| 2. Compile: the trace becomes a verified routine | {st['compiled']}/{st['n']} |",
          f"| 3. Same input: the routine reruns right with no model call | {st['same_input']}/{st['n']} ({st['same_input_with_repair']} counting a repair) |",
          f"| 4. New input: right with a second input, no model call | {st['new_input']}/{st['n_second']} |",
          f"| Blocked by a bot check | {len(st['bot_checks'])} ({', '.join(st['bot_checks']) or 'none'}) |", "",
          "| Workflow | App | Graded by | 1. First run | Agent | 2. Compiled | 3. Same input | 4. New input | Routine (same input) |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for k, r in rows.items():
        a, c = r.get("agent") or {}, r.get("compile") or {}
        same = next((x for x in reversed(r.get("routine_runs", [])) if x["case"] == "same input"), {})
        md.append(f"| {k} | {r['app'].split('.')[-2] if '.' in r['app'] else r['app']} | {r['graded_by']} | {r.get('first_run', '–')} | "
                  f"{a.get('steps', '–')} actions, {a.get('model_calls', '–')} calls, {a.get('duration_s', '–')} s | "
                  f"{('✅ ' + str(c.get('steps')) + ' steps') if c.get('compiled') else ('❌ ' + c.get('reason', '')[:50] if c else '–')} | "
                  f"{rr.stage(r, 'same input')} | {rr.stage(r, 'new input') if r.get('expect_second') else 'n/a'} | "
                  f"{(str(same.get('duration_s')) + ' s, ' + str(same.get('model_calls')) + ' calls') if same.get('duration_s') is not None else '–'} |")
    md += ["", "Why each miss happened:", ""]
    for k, r in rows.items():
        notes = []
        if r.get("first_run") not in ("pass", None):
            notes.append(f"first run {r.get('first_run')}: {str((r.get('agent') or {}).get('result'))[:150]}")
        if r.get("compile") and not r["compile"].get("compiled"):
            notes.append(f"not compiled: {r['compile'].get('reason', '')[:150]}")
        for case in ("same input", "new input"):
            x = next((x for x in reversed(r.get("routine_runs", [])) if x["case"] == case), None)
            if x and x.get("result") != "pass":
                notes.append(f"{case}: {x.get('result')} ({str(x.get('outputs', ''))[:70]}; {x.get('detail', '')[:110]})")
        if notes:
            md.append(f"- **{k}**: " + " · ".join(notes).replace("|", "/"))
    return "\n".join(md) + "\n"


async def cmd_real(args: Any) -> None:
    s = Suite("real", contributor=False, devices=["emulator-5556"], label="Real apps (envoy-real, read-only)")
    rr.TASK_PREFIX = s.tid("real")
    rr.SPEC_DIR = OUT / "real_compiled"
    rr.PRIVATE_DIR = REPO / "data" / "final" / "real_routines"
    device = EmulatorDevice("envoy-real").connect()
    adapter = ModelAdapter()
    approver = ScriptedApprover(approve=False)  # real apps: every approval is declined; nothing irreversible runs
    prev = {} if not args.only else ((rr_load() or {}).get("workflows") or {})
    rows: dict[str, Any] = dict(prev)
    for wf in rr.WORKFLOWS:
        if args.only and wf.id not in args.only.split(","):
            continue
        try:
            row = await rr.run_one(wf, _Args(), device, adapter, approver)
        except Exception as e:  # noqa: BLE001 - one app's failure must not stop the suite
            row = {"app": wf.app, "category": wf.category, "goal": wf.goal, "graded_by": wf.graded_by, "first_run": "error",
                   "error": f"{type(e).__name__}: {e}"[:300]}
            print(f"error    {wf.id:18s} {type(e).__name__}: {e}", flush=True)
        row["cost"] = cell_cost(f"{rr.TASK_PREFIX}-{wf.id}")
        rows[wf.id] = row
        order = [w.id for w in rr.WORKFLOWS]
        rows = dict(sorted(rows.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else 99))
        st = stages(rows)
        s.save({"workflows": rows, "stages": st}, real_md(rows, st))


def rr_load() -> dict[str, Any] | None:
    from final_common import load
    return load("real")

