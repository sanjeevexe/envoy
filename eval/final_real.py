"""A4 real apps: the real-app test set (eval/run_real_apps.py) on envoy-real, all 18 read-only workflows, with fresh agent
runs on this commit and fresh compiles, scored at the four places learning can break.

Standard tier only (real apps). Every approval is declined by the script, sign-ins hand off, nothing is typed into a password
field, and outputs holding personal data are redacted. envoy-real is never snapshot-restored; a "reset" is a fresh launch.
"""

from __future__ import annotations

import json
from typing import Any

from final_common import OUT, REPO, Suite, cell_cost

import run_real_apps as rr  # noqa: E402
from devices.emulator import EmulatorDevice  # noqa: E402
from models.adapter import ModelAdapter  # noqa: E402
from policy.approvals import ScriptedApprover  # noqa: E402


class _Args:
    rerun_agent, reuse_spec, regression = True, False, False


HAND = OUT / "real_hand_checks.json"
STAGES = ("first run", "same input", "new input")


def hand_checks() -> dict[str, dict[str, str]]:
    """Verdicts a person gave on answers graded only by their shape (a price, a title): is the value the one asked for?
    Keyed by workflow, stage and the value itself, so a verdict never carries over to a different answer."""
    return json.loads(HAND.read_text()) if HAND.exists() else {}


def hand_key(wf: str, stage: str, value: Any) -> str:
    return f"{wf} | {stage} | {json.dumps(value, sort_keys=True, ensure_ascii=False)}"


def shape_value(r: dict[str, Any], stage: str) -> Any | None:
    """The answer a stage passed on by its shape alone (None: graded by ground truth, or not passed)."""
    if r.get("graded_by") == "truth":
        return None
    if stage == "first run":
        return (r.get("agent") or {}).get("result") if r.get("first_run") == "pass" else None
    x = next((x for x in reversed(r.get("routine_runs", [])) if x["case"] == stage), None)
    return x.get("outputs") if x and x.get("result") in ("pass", "pass after repair") else None


def verdict(k: str, r: dict[str, Any], stage: str, checks: dict[str, Any]) -> str | None:
    """"right", "wrong" or "unchecked" for a shape-graded pass; None when there is nothing to read by hand."""
    v = shape_value(r, stage)
    if v is None:
        return None
    c = checks.get(hand_key(k, stage, v))
    return c["verdict"] if c else "unchecked"


def pending(rows: dict[str, Any]) -> list[tuple[str, Any]]:
    checks = hand_checks()
    return [(hand_key(k, st, shape_value(r, st)), shape_value(r, st)) for k, r in rows.items() for st in STAGES
            if verdict(k, r, st, checks) == "unchecked"]


def stages(rows: dict[str, Any]) -> dict[str, Any]:
    """Each stage's count. A pass graded by shape that a person read as the wrong value is not counted."""
    checks = hand_checks()
    ok = lambda k, r, st: verdict(k, r, st, checks) != "wrong"  # noqa: E731
    n = len(rows)
    second = {k: r for k, r in rows.items() if r.get("expect_second")}
    bots = sorted({k for k, r in rows.items() if "bot check" in (r.get("first_run"), rr.stage(r, "same input"), rr.stage(r, "new input"))})
    vs = [verdict(k, r, st, checks) for k, r in rows.items() for st in STAGES]
    return {"n": n, "first_run": sum(r.get("first_run") == "pass" and ok(k, r, "first run") for k, r in rows.items()),
            "compiled": sum(bool(r.get("compile", {}).get("compiled")) for r in rows.values()),
            "same_input": sum(rr.stage(r, "same input") == "pass" and ok(k, r, "same input") for k, r in rows.items()),
            "same_input_with_repair": sum(rr.stage(r, "same input") in ("pass", "pass after repair") and ok(k, r, "same input")
                                          for k, r in rows.items()),
            "n_second": len(second), "new_input": sum(rr.stage(r, "new input") == "pass" and ok(k, r, "new input") for k, r in second.items()),
            "bot_checks": bots, "by_hand": {"right": vs.count("right"), "wrong": vs.count("wrong"), "unchecked": vs.count("unchecked")}}


def _cell(k: str, r: dict[str, Any], stage: str, checks: dict[str, Any]) -> str:
    res = r.get("first_run", "–") if stage == "first run" else rr.stage(r, stage)
    return "wrong value (by hand)" if verdict(k, r, stage, checks) == "wrong" else res


def real_md(rows: dict[str, Any], st: dict[str, Any]) -> str:
    md = ["| Stage | Passed |", "| --- | --- |",
          f"| 1. First run: the agent gives a right answer | {st['first_run']}/{st['n']} |",
          f"| 2. Compile: the trace becomes a verified routine | {st['compiled']}/{st['n']} |",
          f"| 3. Same input: the routine reruns right with no model call | {st['same_input']}/{st['n']} ({st['same_input_with_repair']} counting a repair) |",
          f"| 4. New input: right with a second input, no model call | {st['new_input']}/{st['n_second']} |",
          f"| Blocked by a bot check | {len(st['bot_checks'])} ({', '.join(st['bot_checks']) or 'none'}) |", "",
          f"Answers graded only by their shape (a price, a title) were also read by a person: {st.get('by_hand', {}).get('right', 0)} "
          f"right, {st.get('by_hand', {}).get('wrong', 0)} the wrong value (not counted above), {st.get('by_hand', {}).get('unchecked', 0)} not "
          f"read yet. Verdicts: `real_hand_checks.json`, keyed by the exact answer.", "",
          "| Workflow | App | Graded by | 1. First run | Agent | 2. Compiled | 3. Same input | 4. New input | Routine (same input) |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    checks = hand_checks()
    for k, r in rows.items():
        a, c = r.get("agent") or {}, r.get("compile") or {}
        same = next((x for x in reversed(r.get("routine_runs", [])) if x["case"] == "same input"), {})
        md.append(f"| {k} | {r['app'].split('.')[-2] if '.' in r['app'] else r['app']} | {r['graded_by']} | {_cell(k, r, 'first run', checks)} | "
                  f"{a.get('steps', '–')} actions, {a.get('model_calls', '–')} calls, {a.get('duration_s', '–')} s | "
                  f"{('✅ ' + str(c.get('steps')) + ' steps') if c.get('compiled') else ('❌ ' + c.get('reason', '')[:50] if c else '–')} | "
                  f"{_cell(k, r, 'same input', checks)} | {_cell(k, r, 'new input', checks) if r.get('expect_second') else 'n/a'} | "
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
        for st in STAGES:
            if verdict(k, r, st, checks) == "wrong":
                notes.append(f"{st}: the right shape but the wrong value, by hand: {checks[hand_key(k, st, shape_value(r, st))].get('note', '')}")
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
        finally:
            # Close the app and go home: otherwise the next workflow's Back can land in this one (Starbucks' agent backed
            # into Target's bot check, still open from the workflow before).
            for cmd in (["am", "force-stop", wf.app], ["input", "keyevent", "KEYCODE_HOME"]):
                try:
                    device.adb.shell(cmd)
                except Exception:  # noqa: BLE001 - tidying up only
                    pass
        row["cost"] = cell_cost(f"{rr.TASK_PREFIX}-{wf.id}")
        rows[wf.id] = row
        order = [w.id for w in rr.WORKFLOWS]
        rows = dict(sorted(rows.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else 99))
        st = stages(rows)
        s.save({"workflows": rows, "stages": st}, real_md(rows, st))
    for key, value in pending(rows):
        print(f"read by hand: {key}", flush=True)


def rr_load() -> dict[str, Any] | None:
    from final_common import load
    return load("real")

