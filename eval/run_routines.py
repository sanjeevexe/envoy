"""Phase 2 routines evaluation on SkyLark Air.

  uv run --project backend python eval/run_routines.py record              # agent runs that routines compile from
  uv run --project backend python eval/run_routines.py compile             # compile, verify by replay, add to the library
  uv run --project backend python eval/run_routines.py new-inputs --k 5    # routines on bookings they have never seen
  uv run --project backend python eval/run_routines.py variants            # injected UI changes: repair, patch, trial, rerun
  uv run --project backend python eval/run_routines.py baselines           # full agent and fixed replay on the same cells
  uv run --project backend python eval/run_routines.py report              # tables in eval/results/phase2/report.md

Every run starts from a known SkyLark state (fixtures + layout variant + cold launch); compile
verification and patch trials also restore the emulator snapshot first, as the design says. Success
is a code check on SkyLark's real state (the right trip changed, no other trip touched) or on the
returned outputs, never a model's judgment.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.loop import AgentRunner, RunConfig
from agent.trace import RUNS
from devices.emulator import EmulatorDevice
from models.adapter import ModelAdapter
from policy.approvals import ScriptedApprover
from models.schemas import CompiledRoutine
from routines.compiler import VerifyCase, compile_trace, verify
from routines.executor import ExecConfig, RoutineExecutor, RunOutcome
from routines.model import Routine, dump_yaml
from routines.screens import norm, screen_text
from routines.store import RoutineStore
from skylark_routines import BY_ID, FAMILIES, Booking, Family, chicago_booking, compile_booking, fixtures, generate
from testapps.skylark import SkyLark

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "eval" / "results" / "phase2"
LIB = REPO / "data" / "routines"
EXP_LIB = OUT / "library"
SNAPSHOT = "skylark-p2"
COMPILE_EXTRA_SEED = 7  # bookings shown in the list during the source runs (not used as targets)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save(name: str, payload: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(payload, indent=1, default=str, ensure_ascii=False))


def load(name: str) -> Any:
    return json.loads((OUT / f"{name}.json").read_text())


class Env:
    def __init__(self, contributor: bool = False) -> None:
        self.device = EmulatorDevice("envoy-test").connect()
        self.app = SkyLark(self.device.serial)
        if not self.app.installed():
            self.app.install()
        self.adapter = ModelAdapter()
        self.contributor = contributor
        self.approver = ScriptedApprover(approve=True)  # our own test app: irreversible steps are approved by the script, and logged

    async def reset(self, extra: list[Booking], variant: int = 0, snapshot: bool = False) -> dict[str, Any]:
        if snapshot:
            await self.device.snapshot_load(SNAPSHOT)
        self.app.prepare(fixtures=fixtures(extra), variant=variant)
        return self.app.state()

    def executor(self) -> RoutineExecutor:
        return RoutineExecutor(self.device, adapter=self.adapter, approver=self.approver,
                               config=ExecConfig(data_scope="test_app", contributor=self.contributor,
                                                 agent=RunConfig(data_scope="test_app", contributor=self.contributor)))

    def agent(self) -> AgentRunner:
        return AgentRunner(self.device, adapter=self.adapter, approver=self.approver, config=RunConfig(data_scope="test_app", contributor=self.contributor))


def compile_extra() -> list[Booking]:
    return generate(COMPILE_EXTRA_SEED, 3)


def inputs_for(routine: Routine, src: Booking, b: Booking) -> dict[str, str]:
    """The routine's inputs for booking b: each input is bound to the source booking's field with the same value."""
    src_fields, out = src.fields(), {}
    for name, spec in routine.inputs.items():
        ex = norm(spec.example)
        field_name = next((k for k, v in src_fields.items() if v and norm(v) == ex), None)
        out[name] = b.fields()[field_name] if field_name else (spec.example or "")
    return out


def answer_of(outcome: RunOutcome) -> str:
    return " · ".join(f"{k}: {v}" for k, v in outcome.outputs.items() if v)


# ---- record + compile ---------------------------------------------------------------------------


async def cmd_record(env: Env, args: argparse.Namespace) -> None:
    src = compile_booking()
    rows = []
    for fam in [BY_ID[f] for f in args.families.split(",")] if args.families else FAMILIES:
        await env.reset(compile_extra())
        task_id = f"p2-src-{fam.id}"
        res = await env.agent().run(fam.goal(src), task_id=task_id, memory=fam.memory(src))
        state = env.app.state()
        ok = fam.check(state, state, src, {}, res.result) and res.status == "done"
        print(f"{'PASS' if ok else 'FAIL'} {fam.id:14s} {res.status:12s} {res.steps} steps {res.model_calls} calls ${res.cost_usd:.4f} {res.duration_s}s  {res.result[:80]!r}", flush=True)
        rows.append({"family": fam.id, "task_id": task_id, "passed": ok, "status": res.status, "steps": res.steps, "model_calls": res.model_calls,
                     "cost_usd": res.cost_usd, "cost_at_standard_usd": res.cost_at_standard_usd, "duration_s": res.duration_s, "result": res.result})
    prev = load("record")["rows"] if (OUT / "record.json").exists() and args.families else []
    keep = [r for r in prev if r["family"] not in {x["family"] for x in rows}]
    save("record", {"time": now(), "rows": keep + rows})


async def cmd_compile(env: Env, args: argparse.Namespace) -> None:
    src = compile_booking()
    second = generate(args.verify_seed, 2)
    store = RoutineStore(LIB)
    rows = []
    old = load("compile")["rows"] if (OUT / "compile.json").exists() else []
    prev_cost = {r["family"]: r.get("compile_cost_usd", 0.0) for r in old}
    prev_lat = {r["family"]: r.get("compile_latency_s", 0.0) for r in old}
    for fam in [BY_ID[f] for f in args.families.split(",")] if args.families else FAMILIES:
        trace = RUNS / f"p2-src-{fam.id}"
        spec_file = OUT / "compiled" / f"{fam.id}.spec.json"
        cached = CompiledRoutine.model_validate_json(spec_file.read_text()) if args.reuse_spec and spec_file.exists() else None
        try:
            routine, report = await compile_trace(trace, adapter=env.adapter, memory=fam.memory(src), effort=args.effort, spec=cached)
        except Exception as e:  # noqa: BLE001
            print(f"SKIP {fam.id}: {e}")
            rows.append({"family": fam.id, "compiled": False, "error": str(e)})
            continue
        ex = env.executor()

        def case(name: str, b: Booking, extra: list[Booking]) -> VerifyCase:
            held: dict[str, Any] = {}

            async def reset() -> None:
                held["before"] = await env.reset(extra, snapshot=True)

            async def success(outcome: RunOutcome) -> bool:
                return fam.check(env.app.state(), held["before"], b, outcome.outputs, answer_of(outcome))
            return VerifyCase(name, inputs_for(routine, src, b), reset, success)

        # Same inputs (the source booking), then a second set: a booking the source run never saw.
        cases = [case("same-inputs", src, compile_extra()), case("second-inputs", second[0], second)]
        v = await verify(routine, ex, cases)
        status = "added" if v.passed else "rejected"
        if v.passed:
            routine = store.add(routine, {"cases": v.cases})
        (OUT / "compiled").mkdir(parents=True, exist_ok=True)
        (OUT / "compiled" / f"{fam.id}.yaml").write_text(dump_yaml(routine))
        if cached is None and report.wonder:
            spec_file.write_text(json.dumps(report.wonder, indent=1, ensure_ascii=False))
        print(f"{status.upper():8s} {fam.id:14s} {routine.routine} v{routine.version}: {len(routine.steps)} steps, inputs {list(routine.inputs)}, "
              f"outputs {routine.outputs}, ${report.cost_at_standard_usd:.3f}, {report.latency_s}s; verify: "
              + ", ".join(f"{c['case']}={'ok' if c['passed'] else c['status'] + ' ' + c['detail'][:80]}" for c in v.cases), flush=True)
        for w in report.warnings:
            print(f"    warning: {w}")
        rows.append({"family": fam.id, "compiled": True, "routine": routine.routine, "version": routine.version, "status": status,
                     "steps": len(routine.steps), "inputs": {k: s.model_dump() for k, s in routine.inputs.items()}, "outputs": routine.outputs,
                     "dropped": report.dropped, "kept": report.kept, "warnings": report.warnings, "compiler": report.model,
                     "compile_cost_usd": report.cost_at_standard_usd if cached is None else prev_cost.get(fam.id, 0.0),
                     "compile_latency_s": report.latency_s if cached is None else prev_lat.get(fam.id, 0.0), "verify": v.cases})
    prev = load("compile")["rows"] if (OUT / "compile.json").exists() and args.families else []
    keep = [r for r in prev if r["family"] not in {x["family"] for x in rows}]
    save("compile", {"time": now(), "rows": keep + rows})


def routine_for(store: RoutineStore, fam: Family) -> Routine:
    name = next(r["routine"] for r in load("compile")["rows"] if r["family"] == fam.id and r.get("status") == "added")
    return store.get(name, 1)


def outcome_row(kind: str, fam: Family, b: Booking, variant: int, outcome: RunOutcome, ok: bool, **extra: Any) -> dict[str, Any]:
    return {"kind": kind, "family": fam.id, "booking": b.code, "city": b.city, "variant": variant, "passed": ok, "status": outcome.status,
            "detail": outcome.detail, "outputs": outcome.outputs, "rung": outcome.rung, "model_calls": outcome.model_calls,
            "cost_usd": round(outcome.cost_at_standard_usd, 5), "billed_usd": round(outcome.cost_usd, 5), "duration_s": outcome.duration_s,
            "steps": [{"id": s.id, "status": s.status, "rung": s.rung, "rungs": s.rungs, "score": s.score,
                       "ms": round(s.wait_ms + s.act_ms + s.post_ms)} for s in outcome.steps],
            "patches": [{"kind": p.kind, "step": p.step_id, "description": p.description} for p in outcome.patches],
            "approvals": len(outcome.approvals), "popups": outcome.popups, "agent": outcome.agent, "task_id": outcome.task_id, **extra}


async def run_routine(env: Env, routine: Routine, fam: Family, src: Booking, b: Booking, extra: list[Booking], variant: int, *,
                      kind: str, allow_repair: bool = True, allow_agent: bool = True, snapshot: bool = False, tag: str = "") -> tuple[dict, RunOutcome]:
    before = await env.reset(extra, variant, snapshot=snapshot)
    outcome = await env.executor().run(routine, inputs_for(routine, src, b), task_id=f"p2-{kind}-{fam.id}-v{variant}-{b.code}{tag}",
                                       launch="never", allow_repair=allow_repair, allow_agent=allow_agent, memory=fam.memory(b))
    ok = outcome.succeeded and fam.check(env.app.state(), before, b, outcome.outputs, answer_of(outcome))
    print(f"{'PASS' if ok else 'FAIL'} {kind:10s} {fam.id:14s} v{variant} {b.city:12s} {outcome.status:11s} rung={outcome.rung} "
          f"calls={outcome.model_calls} ${outcome.cost_at_standard_usd:.4f} {outcome.duration_s:5.1f}s  {answer_of(outcome)[:60]!r} {outcome.detail[:80]}", flush=True)
    return outcome_row(kind, fam, b, variant, outcome, ok, routine=routine.routine, version=routine.version), outcome


async def cmd_new_inputs(env: Env, args: argparse.Namespace) -> None:
    store = RoutineStore(LIB)
    src = compile_booking()
    rows = []
    for k in range(args.k):
        extra = generate(args.seed + k, 4)
        for fam in [BY_ID[f] for f in args.families.split(",")] if args.families else FAMILIES:
            routine = routine_for(store, fam)
            target = extra[k % len(extra)] if k % 5 != 4 else chicago_booking()  # mostly new bookings; sometimes the next trip
            row, outcome = await run_routine(env, routine, fam, src, target, extra, 0, kind="newinput")
            store.record_run(routine.routine, outcome)
            rows.append(row)
    save(args.name or "new_inputs", {"time": now(), "rows": rows})


async def cmd_variants(env: Env, args: argparse.Namespace) -> None:
    src = compile_booking()
    main = RoutineStore(LIB)
    rows = []
    variants = [int(v) for v in args.variants.split(",")]
    for fam in [BY_ID[f] for f in args.families.split(",")] if args.families else FAMILIES:
        base = routine_for(main, fam)
        for variant in variants:
            bookings = generate(args.seed + 100 * variant, 4)
            a, b, c, d = bookings
            lib = RoutineStore(EXP_LIB / f"{fam.id}-v{variant}")
            if not lib.names():
                lib.add(base.model_copy(update={"changes": [f"v1 compiled from {base.compiled_from.get('task_id')}"]}))
            v1 = lib.get(base.routine, 1)
            exp: dict[str, Any] = {"family": fam.id, "variant": variant, "routine": base.routine}
            # 1. The original routine meets the changed app (with repair and the agent allowed).
            row, outcome = await run_routine(env, v1, fam, src, a, bookings, variant, kind="changed")
            exp["first"] = row
            lib.record_run(base.routine, outcome)
            # 2. Patches from the repair become a trial version, replayed right away from a reset snapshot.
            exp["trial"] = None
            if outcome.patches and outcome.succeeded:
                trial = lib.propose(v1, outcome.patches, outcome.task_id)
                if trial is not None:
                    trow, toutcome = await run_routine(env, trial, fam, src, b, bookings, variant, kind="trial", allow_repair=False,
                                                       allow_agent=False, snapshot=True)
                    verdict = {"passed": trow["passed"], "task_id": toutcome.task_id, "status": toutcome.status, "duration_s": toutcome.duration_s}
                    (lib.activate if trow["passed"] else lib.reject)(base.routine, trial.version, verdict)
                    exp["trial"] = {"version": trial.version, "changes": trial.changes, **trow}
            # 3. The active version on a third booking, repairs allowed: does it now succeed on its own (no model calls)?
            active = lib.get(base.routine)
            arow, aoutcome = await run_routine(env, active, fam, src, c, bookings, variant, kind="after")
            lib.record_run(base.routine, aoutcome)
            exp["after"] = arow
            # 4. The patched version back on the original layout (patches must not break it).
            if active.version != 1:
                orow, _ = await run_routine(env, active, fam, src, d, bookings, 0, kind="backcompat", allow_repair=False, allow_agent=False)
                exp["backcompat"] = orow
            rows.append(exp)
            save(args.name or "variants", {"time": now(), "experiments": rows})


# ---- baselines ----------------------------------------------------------------------------------


async def run_agent_baseline(env: Env, fam: Family, b: Booking, extra: list[Booking], variant: int) -> dict:
    before = await env.reset(extra, variant)
    res = await env.agent().run(fam.goal(b), task_id=f"p2-agent-{fam.id}-v{variant}-{b.code}", memory=fam.memory(b))
    ok = res.succeeded and fam.check(env.app.state(), before, b, {}, res.result)
    print(f"{'PASS' if ok else 'FAIL'} agent      {fam.id:14s} v{variant} {b.city:12s} {res.status:11s} calls={res.model_calls} "
          f"${res.cost_at_standard_usd:.4f} {res.duration_s:5.1f}s {res.result[:60]!r}", flush=True)
    return {"kind": "agent", "family": fam.id, "booking": b.code, "variant": variant, "passed": ok, "status": res.status, "model_calls": res.model_calls,
            "cost_usd": round(res.cost_at_standard_usd, 5), "duration_s": res.duration_s, "steps": res.steps, "result": res.result, "task_id": res.task_id}


async def run_fixed_baseline(env: Env, fam: Family, src: Booking, b: Booking, extra: list[Booking], variant: int) -> dict:
    """Fixed replay (like Mobilerun macros): the recorded taps at their recorded coordinates and the recorded
    text, each after a screen-similarity check; a mismatch hands the rest of the task to the full agent."""
    from baselines import fixed_replay
    before = await env.reset(extra, variant)
    res = await fixed_replay(env.device, RUNS / f"p2-src-{fam.id}", env.agent(), fam.goal(b), fam.memory(b),
                             task_id=f"p2-fixed-{fam.id}-v{variant}-{b.code}")
    screen = await env.device.observe()
    answer = res["result"] or screen_text(screen)
    ok = res["status"] in ("done", "replayed") and fam.check(env.app.state(), before, b, {}, answer)
    print(f"{'PASS' if ok else 'FAIL'} fixed      {fam.id:14s} v{variant} {b.city:12s} {res['status']:11s} calls={res['model_calls']} "
          f"${res['cost_usd']:.4f} {res['duration_s']:5.1f}s handoff={res['handoff_at']}", flush=True)
    return {"kind": "fixed", "family": fam.id, "booking": b.code, "variant": variant, "passed": ok, **{k: v for k, v in res.items() if k != "result"}}


async def cmd_baselines(env: Env, args: argparse.Namespace) -> None:
    src = compile_booking()
    rows = []
    systems = args.systems.split(",")
    for fam in [BY_ID[f] for f in args.families.split(",")] if args.families else FAMILIES:
        for variant in [int(v) for v in args.variants.split(",")]:
            bookings = generate(args.seed + 100 * variant, 4)
            a = bookings[0]
            if variant == 0:
                a = generate(args.seed, 4)[0]
            if "agent" in systems:
                rows.append(await run_agent_baseline(env, fam, a, bookings if variant else generate(args.seed, 4), variant))
            if "fixed" in systems:
                rows.append(await run_fixed_baseline(env, fam, src, a, bookings if variant else generate(args.seed, 4), variant))
            if "routine" in systems and variant == 0:
                routine = routine_for(RoutineStore(LIB), fam)
                row, _ = await run_routine(env, routine, fam, src, a, generate(args.seed, 4), 0, kind="routine-v0")
                rows.append(row)
            save(args.name or "baselines", {"time": now(), "rows": rows})


# ---- main ---------------------------------------------------------------------------------------


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["record", "compile", "new-inputs", "variants", "baselines", "snapshot"])
    ap.add_argument("--families", default="")
    ap.add_argument("--variants", default="1,2,3")
    ap.add_argument("--systems", default="agent,fixed,routine")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--seed", type=int, default=1000)
    ap.add_argument("--verify-seed", type=int, default=42)
    ap.add_argument("--effort", default=None)
    ap.add_argument("--reuse-spec", action="store_true", help="reuse the cached Wonder answer per family (no model cost)")
    ap.add_argument("--name", default=None)
    ap.add_argument("--contributor", action="store_true", help="Contributor tier for model calls (our test app only)")
    args = ap.parse_args()
    env = Env(contributor=args.contributor)
    t0 = time.time()
    if args.cmd == "snapshot":
        env.app.prepare(fixtures=fixtures(compile_extra()))
        await env.device.snapshot_save(SNAPSHOT)
        print(f"saved snapshot {SNAPSHOT}")
    else:
        await {"record": cmd_record, "compile": cmd_compile, "new-inputs": cmd_new_inputs, "variants": cmd_variants,
               "baselines": cmd_baselines}[args.cmd](env, args)
    env.app.prepare()
    print(f"{time.time() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
