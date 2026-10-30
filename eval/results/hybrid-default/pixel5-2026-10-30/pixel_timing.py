"""Hybrid vs spark on the Pixel 5: one live first run (the agent) and one routine replay, each timed per step.

Read-only: every approval is declined (ScriptedApprover(approve=False)), the task only reads, and the routine is a search
that reports the first result. Run from ~/Desktop/Envoy-hybrid with pixel5 claimed:

  uv run --project backend python <this> facts                    the phone, and whether the app and routine are there
  uv run --project backend python <this> run <profile> <agent|routine>
  uv run --project backend python <this> report
"""
import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

REPO = Path.cwd()
sys.path.insert(0, str(REPO / "backend"))
OUT = Path(__file__).with_name("pixel_timing")
LIB = Path(os.environ.get("PIXEL_LIB", str(Path(__file__).with_name("pixel_lib"))))  # a copy: this script never changes a library
APP = os.environ.get("PIXEL_APP", "com.dd.doordash")
ROUTINE = os.environ.get("PIXEL_ROUTINE", "doordash_search_restaurants")
QUERY = os.environ.get("PIXEL_QUERY", "pizza")
GOAL = os.environ.get("PIXEL_GOAL", "Search DoorDash for tacos and tell me the name of the first restaurant in the results. Don't order anything.")


def phone():
    from devices.phone import discover
    from devices.phone import PhoneDevice
    ps = [p for p in discover() if p.get("serial") == "09031FDD4000C6"] or discover()
    if not ps:
        raise SystemExit("no phone connected")
    return PhoneDevice(ps[0]["serial"], ps[0].get("id")).connect()


def facts() -> None:
    from devices.phone import discover
    import subprocess
    print(discover())
    for p in discover():
        s = p["serial"]
        pk = subprocess.run(["adb", "-s", s, "shell", "pm", "list", "packages", APP], capture_output=True, text=True).stdout.strip()
        print(s, "app:", pk or "missing")
    from routines.store import RoutineStore
    rs = RoutineStore(LIB)
    print("routine:", ROUTINE in rs.names(), (rs.index(ROUTINE) if ROUTINE in rs.names() else {}))


async def run(profile: str, kind: str) -> None:
    os.environ["ENVOY_MODEL_PROFILE"] = profile
    from agent.loop import AgentRunner, RunConfig
    from models.adapter import ModelAdapter, active_profile
    from policy.approvals import ScriptedApprover
    assert active_profile() == profile
    dev = phone()
    adapter, approver = ModelAdapter(), ScriptedApprover(approve=False)
    tid = f"pixel-{kind}-{profile}-{time.strftime('%H%M%S')}"
    t0 = time.time()
    if kind == "agent":
        res = await AgentRunner(dev, adapter=adapter, approver=approver,
                                config=RunConfig(data_scope="real", contributor=False, max_cost_usd=0.30)).run(GOAL, task_id=tid)
        row = {"status": res.status, "result": res.result, "steps": res.steps, "calls": res.model_calls, "usd": res.cost_usd,
               "trace": res.trace_dir}
    else:
        from routines.executor import ExecConfig, RoutineExecutor
        from routines.store import RoutineStore
        routine = RoutineStore(LIB).get(ROUTINE)
        name = next(iter(routine.inputs))
        ex = RoutineExecutor(dev, adapter=adapter, approver=approver,
                             config=ExecConfig(data_scope="real", contributor=False, agent=RunConfig(data_scope="real", contributor=False, max_cost_usd=0.30)))
        out = await ex.run(routine, {name: QUERY}, task_id=tid, launch="fresh", allow_repair=True, allow_agent=False)
        row = {"status": out.status, "result": out.detail, "outputs": out.outputs, "calls": out.model_calls, "usd": out.cost_usd,
               "trace": getattr(out, "trace_dir", None)}
    row.update(profile=profile, kind=kind, task_id=tid, wall_s=round(time.time() - t0, 1))
    OUT.mkdir(exist_ok=True)
    (OUT / f"{tid}.json").write_text(json.dumps(row, indent=1, default=str))
    print(json.dumps({k: row[k] for k in ("profile", "kind", "status", "result", "calls", "usd", "wall_s")}, default=str))


def steps_of(trace: str | None) -> list[dict]:
    if not trace or not (Path(trace) / "steps.jsonl").exists():
        return []
    return [json.loads(l) for l in (Path(trace) / "steps.jsonl").read_text().splitlines() if l.strip()]


def report() -> None:
    rows = [json.loads(p.read_text()) for p in sorted(OUT.glob("*.json"))]
    print("| Run | Profile | Status | Steps | Calls | Cost | Wall | Per step: model | observe | act+settle | total |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in rows:
        acts = [s for s in steps_of(r.get("trace")) if s.get("kind") in ("action", "routine_step") and s.get("timings_ms")]
        tm = [s["timings_ms"] for s in acts]
        med = lambda key: statistics.median([t.get(key, 0) for t in tm]) / 1000 if tm else 0  # noqa: E731
        act = statistics.median([t.get("act", 0) + t.get("settle", 0) + t.get("post", 0) + t.get("wait", 0) for t in tm]) / 1000 if tm else 0
        tot = statistics.median([sum(t.values()) for t in tm]) / 1000 if tm else 0
        print(f"| {r['kind']} | {r['profile']} | {r['status']} | {len(acts)} | {r['calls']} | ${r['usd']:.3f} | {r['wall_s']:.0f} s | "
              f"{med('model'):.1f} s | {med('observe'):.1f} s | {act:.1f} s | {tot:.1f} s |")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "facts"
    if cmd == "facts":
        facts()
    elif cmd == "run":
        asyncio.run(run(sys.argv[2], sys.argv[3]))
    else:
        report()
