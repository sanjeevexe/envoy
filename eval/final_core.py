"""Phase 7 on SkyLark Air: the core set's routines, the three systems, first run vs later runs, routines under change,
and routines on three screen sizes and the real phone.

The core set is Phase 1's 10 tasks, parameterized so each can be asked about a booking the routine has never seen:

  check_in, change_seat, add_ktn, gate, flight_status, find_trip   (Phase 2's families, about an upcoming booking)
  seat                                                              (Phase 1's "seat", about an upcoming booking)
  past_trip                                                         (Phase 1's "past_trip", about a past trip)
  miles, gate_alerts                                                (about the profile: the balance varies by seed)

A *world* is one seed's SkyLark state: 4 new upcoming bookings below Home's next trip (so a routine that silently used
"the first card" acts on the wrong trip and the state check catches it), 3 new past trips spread through the past list,
and a new miles balance. Every check is code on SkyLark's real state or on the answer, and every run also fails if
anything changed in the app that the task didn't ask for (a side effect).
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import shutil
import string
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable

from final_common import OUT, REPO, Suite, cell_cost, load, med, pct

from agent.loop import AgentRunner, RunConfig  # noqa: E402
from agent.trace import RUNS  # noqa: E402
from devices.emulator import EmulatorDevice  # noqa: E402
from models.adapter import ModelAdapter  # noqa: E402
from models.schemas import CompiledRoutine  # noqa: E402
from policy.approvals import ScriptedApprover  # noqa: E402
from routines.compiler import NotCompilable, VerifyCase, compile_trace, verify  # noqa: E402
from routines.executor import ExecConfig, RoutineExecutor, RunOutcome  # noqa: E402
from routines.lifecycle import after_run, version_for_run  # noqa: E402
from routines.matcher import RoutineMatcher  # noqa: E402
from routines.model import Routine, dump_yaml  # noqa: E402
from routines.screens import contains_value, norm, screen_text  # noqa: E402
from routines.store import RoutineStore  # noqa: E402
from skylark_routines import Booking, booking_from_trip, compile_booking, generate  # noqa: E402
from skylark_routines import fixtures as booking_fixtures  # noqa: E402
from testapps.skylark import SkyLark, default_fixtures  # noqa: E402

LIB_COMPILED = OUT / "library" / "compiled"  # the 10 routines as compiled (v1), copied before each experiment
LAYOUTS = {0: "original", 1: "moved button", 2: "renamed labels", 3: "extra screen", 4: "hidden IDs", 5: "renamed labels + hidden IDs"}

# ---- targets and worlds ----------------------------------------------------------------------------------------------

_PAST_CITIES = [("Honolulu", "HNL"), ("Anchorage", "ANC"), ("Kansas City", "MCI"), ("Detroit", "DTW"), ("Cleveland", "CLE"),
                ("Baltimore", "BWI"), ("Salt Lake City", "SLC"), ("Las Vegas", "LAS"), ("St. Louis", "STL"), ("Indianapolis", "IND"),
                ("Columbus", "CMH"), ("Milwaukee", "MKE"), ("Cincinnati", "CVG"), ("Oklahoma City", "OKC"), ("Hartford", "BDL")]


@dataclass
class PastTrip:
    code: str
    city: str
    airport: str
    number: str
    date: str
    seat: str

    def trip(self) -> dict[str, Any]:
        return {"code": self.code, "city": self.city, "upcoming": False, "checkin_open": False, "checked_in": True, "cancelled": False,
                "ktn": "", "bags": 0, "flight": {"number": self.number, "from": "ATL", "to": self.airport, "date": self.date,
                                                 "depart": "9:00 AM", "arrive": "11:00 AM", "gate": "C1", "seat": self.seat,
                                                 "boarding": "8:20 AM", "group": "2", "status": "Landed"}}

    def fields(self) -> dict[str, str]:
        return {"city": self.city, "code": self.code, "number": self.number, "airport": self.airport, "date": self.date, "seat": self.seat}


@dataclass
class Profile:
    miles: int

    def fields(self) -> dict[str, str]:
        return {"miles": f"{self.miles:,}", "miles_raw": str(self.miles)}


@dataclass
class World:
    """One seed's SkyLark state and the targets in it."""

    seed: int
    upcoming: list[Booking]
    past: list[PastTrip] = field(default_factory=list)  # new past trips, listed by date among the old ones
    miles: int = 38240

    def fixtures(self) -> dict[str, Any]:
        fx = booking_fixtures(self.upcoming)  # Denver's check-in opened; new upcoming bookings after Denver
        upcoming = [t for t in fx["trips"] if t["upcoming"]]
        past = [t for t in fx["trips"] if not t["upcoming"]] + [p.trip() for p in self.past]
        past.sort(key=lambda t: datetime.strptime(t["flight"]["date"], "%a, %b %d, %Y"), reverse=True)  # newest first, as apps list them
        fx["trips"] = upcoming + past
        fx["profile"]["miles"] = self.miles
        return fx


def _past_trips(rng: random.Random, n: int, taken_codes: set[str], taken_cities: set[str]) -> list[PastTrip]:
    out, used_dates = [], {t["flight"]["date"] for t in default_fixtures()["trips"]}
    for city, airport in rng.sample([c for c in _PAST_CITIES if c[0] not in taken_cities], n):
        code = ""
        while not code or code in taken_codes or not any(c.isalpha() for c in code):
            code = "".join(rng.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        taken_codes.add(code)
        d = ""
        while not d or d in used_dates:
            day = date(2026, 1, 5) + timedelta(days=rng.randint(0, 270))
            d = f"{day:%a}, {day:%b} {day.day}, {day.year}"
        used_dates.add(d)
        out.append(PastTrip(code=code, city=city, airport=airport, number=f"SL {rng.randint(100, 1999)}", date=d,
                            seat=f"{rng.randint(10, 24)}{rng.choice('ABCDEF')}"))
    return out


def world(seed: int, n_upcoming: int = 4, n_past: int = 3) -> World:
    """A deterministic world for a seed: new bookings, new past trips at different depths of the list, a new balance."""
    up = generate(seed, n_upcoming)
    rng = random.Random(seed * 7919 + 13)
    codes = {t["code"] for t in default_fixtures()["trips"]} | {b.code for b in up}
    cities = {t["city"] for t in default_fixtures()["trips"]} | {b.city for b in up}
    past = _past_trips(rng, n_past, codes, cities)
    return World(seed=seed, upcoming=up, past=past, miles=rng.randint(12000, 98000))


def compile_world() -> World:
    """Where routines are recorded and compiled: Phase 2's setup (Denver's check-in open, 3 extra bookings from seed 7)."""
    return World(seed=7, upcoming=generate(7, 3))


SEATTLE = booking_from_trip(next(t for t in default_fixtures()["trips"] if t["city"] == "Seattle"))


def seattle() -> PastTrip:
    return PastTrip(code=SEATTLE.code, city=SEATTLE.city, airport=SEATTLE.airport, number=SEATTLE.number, date=SEATTLE.date, seat=SEATTLE.seat)


# ---- the 10 core tasks ----------------------------------------------------------------------------------------------

def _trip(state: dict[str, Any], code: str) -> dict[str, Any]:
    return next(t for t in state["trips"] if t["code"] == code)


def _text(answer: str, outputs: dict[str, str | None]) -> str:
    return answer + " · " + " · ".join(v or "" for v in outputs.values())


def _has(answer: str, outputs: dict[str, str | None], *needles: str) -> bool:
    text = _text(answer, outputs)
    return all(contains_value(text, n) for n in needles)


def _month_day(d: str) -> list[str]:
    """'Tue, Mar 3, 2026' → ['Mar 3', 'March 3']"""
    m = re.search(r"([A-Z][a-z]{2}) (\d{1,2})", d)
    if not m:
        return [d]
    full = {"Jan": "January", "Feb": "February", "Mar": "March", "Apr": "April", "May": "May", "Jun": "June", "Jul": "July",
            "Aug": "August", "Sep": "September", "Oct": "October", "Nov": "November", "Dec": "December"}[m.group(1)]
    return [f"{m.group(1)} {m.group(2)}", f"{full} {m.group(2)}"]


def changes(before: dict[str, Any], after: dict[str, Any]) -> set[tuple[str, str]]:
    """What changed in SkyLark's state: (trip code or 'profile' or 'app', field)."""
    out: set[tuple[str, str]] = set()
    b_trips = {t["code"]: t for t in before["trips"]}
    for t in after["trips"]:
        b = b_trips.get(t["code"])
        if b is None:
            out.add((t["code"], "added"))
            continue
        for k in ("checked_in", "cancelled", "ktn", "bags", "checkin_open"):
            if t.get(k) != b.get(k):
                out.add((t["code"], k))
        for k in ("seat", "gate", "status"):
            if t["flight"].get(k) != b["flight"].get(k):
                out.add((t["code"], f"flight.{k}"))
    for k, v in after["profile"].items():
        if before["profile"].get(k) != v:
            out.add(("profile", k))
    if after.get("signed_in") != before.get("signed_in"):
        out.add(("app", "signed_in"))
    return out


@dataclass
class CoreTask:
    id: str
    kind: str  # "upcoming" (a booking), "past" (a past trip) or "profile"
    goal: Callable[[Any], str]
    ok: Callable[[dict[str, Any], dict[str, Any], Any, dict[str, str | None], str], bool]  # (state, before, target, outputs, answer)
    allowed: Callable[[Any], set[tuple[str, str]]] = lambda t: set()  # the changes the task asks for
    memory: Callable[[Any], str] = lambda t: ""
    phase1: str = ""  # Phase 1's fixed-goal version

    def pick(self, w: World, i: int) -> Any:
        if self.kind == "upcoming":
            return w.upcoming[i % len(w.upcoming)]
        if self.kind == "past":
            return w.past[i % len(w.past)]
        return Profile(w.miles)

    def source(self) -> Any:
        return {"upcoming": compile_booking, "past": seattle, "profile": lambda: Profile(38240)}[self.kind]()

    def check(self, state: dict[str, Any], before: dict[str, Any], t: Any, outputs: dict[str, str | None], answer: str
              ) -> tuple[bool, list[str]]:
        """(passed, side effects): right result in code, and nothing else changed in the app."""
        side = sorted(f"{a}.{b}" for a, b in changes(before, state) - self.allowed(t))
        return bool(self.ok(state, before, t, outputs, answer)) and not side, side


def _miles_ok(answer: str, outputs: dict[str, str | None], miles: int) -> bool:
    digits = re.sub(r"(?<=\d)[,\s](?=\d{3}\b)", "", _text(answer, outputs))
    return re.search(rf"(?<!\d){miles}(?!\d)", digits) is not None


TASKS: list[CoreTask] = [
    CoreTask("check_in", "upcoming", lambda b: f"Check me in for my flight to {b.city}.",
             lambda s, s0, b, o, a: _trip(s, b.code)["checked_in"], allowed=lambda b: {(b.code, "checked_in")}, phase1="checkin"),
    CoreTask("change_seat", "upcoming", lambda b: f"Change my seat on my {b.city} flight to {b.new_seat}.",
             lambda s, s0, b, o, a: _trip(s, b.code)["flight"]["seat"] == b.new_seat, allowed=lambda b: {(b.code, "flight.seat")},
             phase1="change_seat"),
    CoreTask("add_ktn", "upcoming", lambda b: f"Add my known traveler number to my {b.city} trip.",
             lambda s, s0, b, o, a: _trip(s, b.code)["ktn"] == b.ktn, allowed=lambda b: {(b.code, "ktn")},
             memory=lambda b: f"Known traveler number: {b.ktn}", phase1="ktn"),
    CoreTask("gate", "upcoming", lambda b: f"What gate does my {b.city} flight leave from?",
             lambda s, s0, b, o, a: _has(a, o, b.gate), phase1="gate"),
    CoreTask("seat", "upcoming", lambda b: f"What seat do I have on my flight to {b.city}?",
             lambda s, s0, b, o, a: _has(a, o, b.seat), phase1="seat"),
    CoreTask("flight_status", "upcoming", lambda b: f"What's the status of SkyLark flight {b.number}?",
             lambda s, s0, b, o, a: _has(a, o, b.status) and (_has(a, o, b.number) or _has(a, o, b.airport)), phase1="flight_status"),
    CoreTask("miles", "profile", lambda p: "How many SkyLark miles do I have?",
             lambda s, s0, p, o, a: _miles_ok(a, o, p.miles), phase1="miles"),
    CoreTask("find_trip", "upcoming", lambda b: f"Look up my trip with confirmation code {b.code} and tell me where it goes.",
             lambda s, s0, b, o, a: _has(a, o, b.city) or _has(a, o, b.airport), memory=lambda b: "Last name: Patel", phase1="find_trip"),
    CoreTask("past_trip", "past", lambda p: f"When did I fly to {p.city}?",
             lambda s, s0, p, o, a: any(_has(a, o, x) for x in _month_day(p.date)), phase1="past_trip"),
    CoreTask("gate_alerts", "profile", lambda p: "Turn on gate change alerts.",
             lambda s, s0, p, o, a: s["profile"]["gate_alerts"] is True, allowed=lambda p: {("profile", "gate_alerts")}, phase1="gate_alerts"),
]
BY_ID = {t.id: t for t in TASKS}
NEW_ROUTINES = ["seat", "miles", "past_trip", "gate_alerts"]  # core tasks with no routine before Phase 7


def tasks(arg: str) -> list[CoreTask]:
    return [BY_ID[x] for x in arg.split(",")] if arg else TASKS


def inputs_for(routine: Routine, src: Any, t: Any) -> dict[str, str]:
    """Bind each routine input to the target's field that held the same value in the source run."""
    src_fields, out = src.fields(), {}
    for name, spec in routine.inputs.items():
        ex = norm(spec.example)
        key = next((k for k, v in src_fields.items() if v and norm(v) == ex), None)
        out[name] = t.fields().get(key, spec.example or "") if key else (spec.example or "")
    return out


# ---- the environment ------------------------------------------------------------------------------------------------

class Env:
    def __init__(self, device: Any = None, contributor: bool = False) -> None:
        self.device = device or EmulatorDevice("envoy-test").connect()
        self.app = SkyLark(self.device.serial)
        if not self.app.installed():
            self.app.install()
        self.adapter = ModelAdapter()
        self.contributor = contributor
        self.approver = ScriptedApprover(approve=True)  # our own test app: the scripted person approves, and every request is logged

    async def reset(self, w: World, layout: int = 0) -> dict[str, Any]:
        """A known state: SkyLark reseeded through its fixture hook (all app state), the layout set, a cold launch on Home.
        (Snapshot restores hung the emulator after dozens in Phase 2; the hook resets everything the checks read.)"""
        await asyncio.to_thread(self.app.prepare, fixtures=w.fixtures(), variant=layout)
        return await asyncio.to_thread(self.app.state)

    def run_config(self) -> RunConfig:
        return RunConfig(data_scope="test_app", contributor=self.contributor)

    def agent(self) -> AgentRunner:
        return AgentRunner(self.device, adapter=self.adapter, approver=self.approver, config=self.run_config())

    def executor(self) -> RoutineExecutor:
        return RoutineExecutor(self.device, adapter=self.adapter, approver=self.approver,
                               config=ExecConfig(data_scope="test_app", contributor=self.contributor, agent=self.run_config()))

    def state(self) -> dict[str, Any]:
        return self.app.state()


def fresh_library(name: str) -> RoutineStore:
    """A copy of the compiled library (each routine's v1), so every experiment starts from the same routines."""
    dst = OUT / "library" / name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(LIB_COMPILED, dst)
    return RoutineStore(dst)


def compiled() -> dict[str, Any]:
    d = load("compile")
    if not d:
        raise SystemExit("no compiled routines yet: run `eval/run_final.py compile` first")
    return {r["task"]: r for r in d["rows"] if r.get("status") == "added"}


def routine_of(store: RoutineStore, task: CoreTask) -> Routine | None:
    row = compiled().get(task.id)
    return store.get(row["routine"]) if row else None


def answer_of(outcome: RunOutcome) -> str:
    return " · ".join(f"{k}: {v}" for k, v in outcome.outputs.items() if v)


# ---- 0. compile: the source runs, compiled and verified ---------------------------------------------------------------

async def cmd_compile(args: Any) -> None:
    """Record each core task once with the agent on the compile booking, compile it with Muse Wonder, verify by replay on
    the same booking and on one it has never seen. A rejected compile is compiled once more from the same run (Wonder's
    answers vary), then from one new run; every attempt is recorded."""
    env = Env(contributor=args.contributor)
    s = Suite("compile", contributor=args.contributor, devices=[env.device.serial], label="Compiling the core set's routines")
    if LIB_COMPILED.exists() and not args.tasks:
        shutil.rmtree(LIB_COMPILED)
    store = RoutineStore(LIB_COMPILED)
    prev = {r["task"]: r for r in (load("compile") or {}).get("rows", [])} if args.tasks else {}
    rows = []
    cw = compile_world()
    vw = world(42, n_upcoming=2, n_past=1)
    for task in tasks(args.tasks):
        src, second = task.source(), task.pick(vw, 0)
        row: dict[str, Any] = {"task": task.id, "new_in_phase7": task.id in NEW_ROUTINES, "attempts": []}
        for attempt in range(1, 4):
            # attempt 1: a new source run (or the earlier one with --reuse); 2: compile the same run again (Wonder's answers
            # vary), or a new run if the last one failed; 3: a new run
            src_ok = bool(row.get("source", {}).get("passed"))
            new_run = (attempt == 1 and not (args.reuse and prev.get(task.id))) or attempt == 3 or not src_ok and attempt == 2
            if new_run:
                tid = s.tid("src", task.id, f"a{attempt}")
                before = await env.reset(cw)
                res = await env.agent().run(task.goal(src), task_id=tid, memory=task.memory(src))
                ok, side = task.check(env.state(), before, src, {}, res.result)
                ok = ok and res.status == "done"
                rec = {"task_id": tid, "passed": ok, "status": res.status, "steps": res.steps, "duration_s": res.duration_s,
                       "result": res.result, "side_effects": side, **cell_cost(tid)}
                print(f"{'PASS' if ok else 'FAIL'} source  {task.id:13s} {res.status:9s} {res.steps:2d} steps {rec['calls']:2d} calls "
                      f"${rec['standard_usd']:.4f} {res.duration_s:5.1f}s {res.result[:70]!r}", flush=True)
                row["source"] = rec
                if not ok:
                    row["attempts"].append({"attempt": attempt, "stage": "source run", "status": res.status})
                    continue
            elif "source" not in row:
                row["source"] = prev[task.id]["source"]
            trace = RUNS / row["source"]["task_id"]
            spec_file = OUT / "compiled" / f"{task.id}.spec.json"
            cached = CompiledRoutine.model_validate_json(spec_file.read_text()) if args.reuse and attempt == 1 and spec_file.exists() else None
            t0 = time.time()
            try:
                routine, report = await compile_trace(trace, adapter=env.adapter, memory=task.memory(src), spec=cached)
            except NotCompilable as e:
                row["attempts"].append({"attempt": attempt, "stage": "compile", "error": str(e)[:300]})
                print(f"NOTCOMP {task.id:13s} {str(e)[:120]}", flush=True)
                continue
            compile_s = round(time.time() - t0, 1)

            def case(name: str, t: Any, w: World) -> VerifyCase:
                held: dict[str, Any] = {}

                async def reset() -> None:
                    held["before"] = await env.reset(w)

                async def success(outcome: RunOutcome) -> bool:
                    return task.check(env.state(), held["before"], t, outcome.outputs, answer_of(outcome))[0]
                return VerifyCase(name, inputs_for(routine, src, t), reset, success)
            v = await verify(routine, env.executor(), [case("same-inputs", src, cw), case("second-inputs", second, vw)])
            verify_s = round(sum(c.get("duration_s") or 0 for c in v.cases), 1)
            row["attempts"].append({"attempt": attempt, "stage": "verify", "passed": v.passed, "cases": v.cases,
                                    "compile_cost_usd": round(report.cost_at_standard_usd, 4) if cached is None else 0.0,
                                    "compile_s": compile_s, "verify_s": verify_s, "warnings": report.warnings})
            print(f"{'ADDED' if v.passed else 'REJECT'}  {task.id:13s} {routine.routine}: {len(routine.steps)} steps, inputs "
                  f"{list(routine.inputs)}, outputs {routine.outputs}; ${report.cost_at_standard_usd:.3f} {compile_s}s; verify "
                  + ", ".join(f"{c['case']}={'ok' if c['passed'] else c['status'] + ' ' + c['detail'][:60]}" for c in v.cases), flush=True)
            (OUT / "compiled").mkdir(parents=True, exist_ok=True)
            (OUT / "compiled" / f"{task.id}.yaml").write_text(dump_yaml(routine))
            if cached is None and report.wonder:
                spec_file.write_text(json.dumps(report.wonder, indent=1, ensure_ascii=False))
            if v.passed:
                store.add(routine, {"cases": v.cases})
                row.update(status="added", routine=routine.routine, steps=len(routine.steps), inputs={k: x.model_dump() for k, x in routine.inputs.items()},
                           outputs=routine.outputs, compile_cost_usd=sum(a.get("compile_cost_usd", 0) for a in row["attempts"]),
                           compile_s=compile_s, verify_s=verify_s, dropped=report.dropped)
                break
        else:
            row["status"] = "rejected"
        rows.append(row)
    keep = [r for t, r in prev.items() if t not in {x["task"] for x in rows}]
    payload = {"world": {"compile": cw.seed, "verify": vw.seed}, "rows": keep + rows}
    md = ["| Task | New | Source run | Compile attempts | Routine | Steps | Inputs | Outputs |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in payload["rows"]:
        src = r.get("source", {})
        md.append(f"| {r['task']} | {'yes' if r.get('new_in_phase7') else ''} | {src.get('steps', '–')} actions, {src.get('calls', '–')} calls, "
                  f"{src.get('duration_s', '–')} s | {len([a for a in r['attempts'] if a['stage'] in ('verify', 'compile')])} | "
                  f"{r.get('routine', '❌ ' + r.get('status', ''))} | {r.get('steps', '–')} | {', '.join(r.get('inputs', {})) or '–'} | "
                  f"{', '.join(r.get('outputs', [])) or '–'} |")
    s.save(payload, "\n".join(md) + "\n")


# ---- running one request with each system ------------------------------------------------------------------------------

async def run_agent(env: Env, task: CoreTask, t: Any, w: World, layout: int, tid: str) -> dict[str, Any]:
    before = await env.reset(w, layout)
    res = await env.agent().run(task.goal(t), task_id=tid, memory=task.memory(t))
    ok, side = task.check(env.state(), before, t, {}, res.result)
    ok = ok and res.succeeded
    return {"passed": ok, "status": res.status, "answer": res.result[:200], "steps": res.steps, "approvals": len(res.approvals),
            "interventions": int(res.status in ("handoff", "needs_user")), "duration_s": res.duration_s, "side_effects": side}


async def run_fixed(env: Env, task: CoreTask, t: Any, w: World, layout: int, tid: str, source_tid: str) -> dict[str, Any]:
    from baselines import fixed_replay
    before = await env.reset(w, layout)
    res = await fixed_replay(env.device, RUNS / source_tid, env.agent(), task.goal(t), task.memory(t), task_id=tid)
    answer = res.get("result") or screen_text(await env.device.observe())
    ok, side = task.check(env.state(), before, t, {}, answer)
    ok = ok and res["status"] in ("done", "done_unverified", "replayed")
    return {"passed": ok, "status": res["status"], "answer": (res.get("result") or "")[:200], "steps": res["replayed"] + res.get("agent_steps", 0),
            "approvals": res.get("approvals", 0), "interventions": int(res["status"] in ("handoff", "needs_user")),
            "duration_s": res["duration_s"], "handoff_at": res["handoff_at"], "side_effects": side}


async def run_routine_system(env: Env, lib: RoutineStore, task: CoreTask, t: Any, w: World, layout: int, tid: str) -> dict[str, Any]:
    """The product's path (api/runner.py): the matcher picks a routine and fills its inputs from the request and the notes
    (one model call), the executor runs the version the lifecycle picks (a pending trial, else the active one) with repair
    and the agent behind it; then the lifecycle records it (a trial decided, or new patches put on trial). No routine, or
    an input the matcher couldn't fill: the agent does it."""
    before = await env.reset(w, layout)
    goal, notes = task.goal(t), task.memory(t)
    t0 = time.time()
    m = await RoutineMatcher(lib, env.adapter, data_scope="test_app", contributor=env.contributor).match(goal, notes, task_id=f"{tid}-match")
    row: dict[str, Any] = {"match": m.stage, "matched": m.routine.routine if m.routine else None, "missing": m.missing}
    if m.routine is None or m.missing:
        res = await env.agent().run(goal, task_id=f"{tid}-agent", memory=notes)
        ok, side = task.check(env.state(), before, t, {}, res.result)
        row.update(passed=ok and res.succeeded, status=f"agent {res.status}", answer=res.result[:200], steps=res.steps, approvals=len(res.approvals),
                   interventions=int(res.status in ("handoff", "needs_user")), rung=None, agent_fallback=True, side_effects=side)
    else:
        routine = version_for_run(lib, m.routine.routine)
        out = await env.executor().run(routine, m.inputs, task_id=tid, launch="never", allow_repair=True, allow_agent=True, memory=notes,
                                       request=goal)
        ok, side = task.check(env.state(), before, t, out.outputs, answer_of(out) or (out.agent or {}).get("result", ""))
        life = after_run(lib, routine, out)
        row.update(passed=ok and out.succeeded, status=out.status, answer=answer_of(out)[:200], steps=len(out.steps) + ((out.agent or {}).get("steps") or 0),
                   approvals=len(out.approvals), interventions=int(out.status in ("handoff", "needs_user")), rung=out.rung,
                   agent_fallback=bool(out.agent), version=routine.version, trial=routine.status == "trial", lifecycle=life,
                   patches=[p.kind for p in out.patches], inputs=m.inputs, side_effects=side)
    row["duration_s"] = round(time.time() - t0, 2)  # the matcher's call included
    return row


def _try_row(system: str, task: CoreTask, w: World, layout: int, attempt: int, tid: str, r: dict[str, Any]) -> dict[str, Any]:
    return {"system": system, "task": task.id, "layout": layout, "seed": w.seed, "try": attempt, "task_id": tid, **r, **cell_cost(tid)}


def _print(row: dict[str, Any]) -> None:
    print(f"{'PASS' if row['passed'] else 'FAIL'} {row['system']:7s} {row['task']:13s} L{row['layout']} s{row['seed']} t{row['try']} "
          f"{str(row['status'])[:14]:14s} {row['calls']:2d} calls ${row['standard_usd']:.4f} {row['duration_s']:5.1f}s "
          f"{'side:' + ','.join(row['side_effects']) if row.get('side_effects') else ''} {str(row.get('answer', ''))[:60]!r}", flush=True)


# ---- A1. the three systems -----------------------------------------------------------------------------------------

SYSTEM_SEEDS = [101, 102, 103]


async def cmd_systems(args: Any) -> None:
    env = Env(contributor=args.contributor)
    name = args.name or "systems"
    s = Suite(name, contributor=args.contributor, devices=[env.device.serial], label="Three systems on SkyLark's core set")
    comp = compiled()
    systems = args.systems.split(",")
    layouts = [int(x) for x in args.layouts.split(",")]
    seeds = SYSTEM_SEEDS[: args.seeds]
    prev = (load(name) or {}).get("rows", []) if args.append else []
    rows: list[dict[str, Any]] = []
    sel = tasks(args.tasks)
    for layout in layouts:
        lib = fresh_library(f"systems-L{layout}") if "routine" in systems else None
        for i, seed in enumerate(seeds):
            w = world(seed)
            for task in sel:
                t = task.pick(w, i)
                for system in systems:
                    for attempt in range(1, args.tries + 1):
                        tid = s.tid(system[:3], task.id, f"L{layout}", f"s{seed}", f"t{attempt}")
                        if system == "agent":
                            r = await run_agent(env, task, t, w, layout, tid)
                        elif system == "fixed":
                            src = comp.get(task.id, {}).get("source", {}).get("task_id")
                            if not src:
                                break
                            r = await run_fixed(env, task, t, w, layout, tid, src)
                        else:
                            r = await run_routine_system(env, lib, task, t, w, layout, tid)  # type: ignore[arg-type]
                        row = _try_row(system, task, w, layout, attempt, tid, r)
                        _print(row)
                        rows.append(row)
                        if row["passed"]:
                            break
                        if system == "fixed" and row["status"] == "replayed":
                            row["deterministic"] = True  # a replay with no takeover repeats exactly: its first try stands for all three
                            break
                s.save({"seeds": seeds, "layouts": layouts, "rows": prev + rows}, systems_md(prev + rows))
    await env.reset(compile_world())


def systems_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per system and layout: first-try and within-3 success over cells, and medians over every try."""
    out: dict[str, Any] = {}
    cells: dict[tuple, list[dict[str, Any]]] = {}
    for r in rows:
        cells.setdefault((r["system"], r["layout"], r["task"], r["seed"]), []).append(r)
    for key in sorted({(k[0], k[1]) for k in cells}):
        cs = [sorted(v, key=lambda r: r["try"]) for k, v in cells.items() if (k[0], k[1]) == key]
        firsts = [c[0] for c in cs]
        tries = [r for c in cs for r in c]
        out[f"{key[0]}|{key[1]}"] = {
            "system": key[0], "layout": key[1], "cells": len(cs),
            "first_try": sum(c[0]["passed"] for c in cs), "within_3": sum(any(r["passed"] for r in c[:3]) for c in cs),
            "median_calls": med([r["calls"] for r in firsts], 1), "median_s": med([r["duration_s"] for r in firsts], 1),
            "median_usd": med([r["standard_usd"] for r in firsts], 5), "median_steps": med([r["steps"] for r in firsts], 1),
            "mean_usd": round(sum(r["standard_usd"] for r in firsts) / len(firsts), 5),
            "median_tokens": int(med([r["input_tokens"] + r["output_tokens"] for r in firsts], 0) or 0),
            "calls_total": sum(r["calls"] for r in tries), "usd_total": round(sum(r["standard_usd"] for r in tries), 4),
            "interventions": sum(r.get("interventions", 0) for r in tries), "approvals": sum(r.get("approvals", 0) for r in tries),
            "zero_call_first_tries": sum(r["calls"] == 0 for r in firsts),
            "side_effects": sum(bool(r.get("side_effects")) for r in tries),
        }
    return out


def systems_md(rows: list[dict[str, Any]]) -> str:
    sm = systems_summary(rows)
    names = {"agent": "Full agent", "fixed": "Fixed replay", "routine": "Envoy routines"}
    md = ["Success over cells (task × seed); medians over first tries. Calls, tokens and dollars include the routine "
          "matcher's call; dollars are at standard prices.", "",
          "| System | Layout | First try | Within 3 | Median calls | Median tokens | Median $ | Median s | Median steps | Interventions | Approvals | Side effects |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for v in sm.values():
        md.append(f"| {names.get(v['system'], v['system'])} | {v['layout']}: {LAYOUTS[v['layout']]} | {pct(v['first_try'], v['cells'])} | "
                  f"{pct(v['within_3'], v['cells'])} | {v['median_calls']} | {v['median_tokens']} | ${v['median_usd']} | {v['median_s']} | "
                  f"{v['median_steps']} | {v['interventions']} | {v['approvals']} | {v['side_effects']} |")
    fails = [r for r in rows if not r["passed"]]
    if fails:
        groups: dict[tuple, list[dict[str, Any]]] = {}
        for r in fails:
            why = "acted on another booking" if any(not x.startswith(("profile", "app")) for x in r.get("side_effects") or []) else (
                "changed something else" if r.get("side_effects") else ("wrong answer" if r["status"] in ("replayed", "done", "done_unverified") else r["status"]))
            groups.setdefault((names.get(r["system"], r["system"]), r["task"], why), []).append(r)
        md += ["", "Failed tries, by kind (layouts and tries counted):", "", "| System | Task | What went wrong | Tries | Layouts |", "| --- | --- | --- | --- | --- |"]
        for (sysn, task, why), rs in sorted(groups.items()):
            md.append(f"| {sysn} | {task} | {why} | {len(rs)} | {', '.join(str(x) for x in sorted({r['layout'] for r in rs}))} |")
    return "\n".join(md) + "\n"


# ---- A2. first run vs later runs ---------------------------------------------------------------------------------------

REPEAT_SEED0 = 500


async def cmd_repeats(args: Any) -> None:
    """Request 1 of each task is its source run (the agent) plus the compile and its verification; requests 2–10 are the
    product's routine path on new bookings."""
    env = Env(contributor=args.contributor)
    s = Suite("repeats", contributor=args.contributor, devices=[env.device.serial], label="First run vs later runs")
    comp = compiled()
    sel = {t.id for t in tasks(args.tasks)}
    rows = [r for r in (load("repeats") or {}).get("rows", []) if r["task"] not in sel] if args.tasks else []  # a rerun of some tasks
    lib = fresh_library("repeats")
    for task in tasks(args.tasks):
        c = comp.get(task.id)
        if not c:
            continue
        a = c["source"]
        rows.append({"task": task.id, "n": 1, "kind": "agent + compile", "calls": a["calls"] + 1, "standard_usd": round(a["standard_usd"] + c["compile_cost_usd"], 5),
                     "agent_usd": a["standard_usd"], "compile_usd": c["compile_cost_usd"], "duration_s": round(a["duration_s"] + c["compile_s"] + c["verify_s"], 1),
                     "agent_s": a["duration_s"], "compile_s": c["compile_s"], "verify_s": c["verify_s"], "passed": True})
        for n in range(2, args.n + 1):
            w = world(REPEAT_SEED0 + n)
            t = task.pick(w, n)
            tid = s.tid("rep", task.id, f"n{n}")
            r = await run_routine_system(env, lib, task, t, w, 0, tid)
            row = {"task": task.id, "n": n, "kind": "routine" if not r.get("agent_fallback") else "agent (no routine)", "task_id": tid, **r, **cell_cost(tid)}
            print(f"{'PASS' if row['passed'] else 'FAIL'} repeat  {task.id:13s} n{n:<2d} {row['calls']} calls ${row['standard_usd']:.4f} {row['duration_s']:5.1f}s", flush=True)
            rows.append(row)
        s.save({"n": args.n, "rows": rows}, repeats_md(rows))


def repeats_md(rows: list[dict[str, Any]]) -> str:
    md = ["Request 1 is the agent's run plus the compile (Muse Wonder) and its verification; requests 2+ are the routine "
          "through the matcher on new bookings. Dollars at standard prices.", "",
          "| Request | Tasks | Passed | Median calls | Median $ | Median s |", "| --- | --- | --- | --- | --- | --- |"]
    for n in sorted({r["n"] for r in rows}):
        rs = [r for r in rows if r["n"] == n]
        md.append(f"| {n} | {len(rs)} | {sum(r['passed'] for r in rs)} | {med([r['calls'] for r in rs])} | ${med([r['standard_usd'] for r in rs], 4)} | "
                  f"{med([r['duration_s'] for r in rs])} |")
    return "\n".join(md) + "\n"


# ---- A3. routines under change: new inputs and injected UI changes --------------------------------------------------------

async def run_direct(env: Env, routine: Routine, task: CoreTask, t: Any, w: World, layout: int, tid: str, *, allow_repair: bool = True,
                     allow_agent: bool = True) -> tuple[dict[str, Any], RunOutcome]:
    """A routine with inputs bound from the target directly (no matcher), to measure the routine alone."""
    before = await env.reset(w, layout)
    out = await env.executor().run(routine, inputs_for(routine, task.source(), t), task_id=tid, launch="never",
                                   allow_repair=allow_repair, allow_agent=allow_agent, memory=task.memory(t))
    ok, side = task.check(env.state(), before, t, out.outputs, answer_of(out) or (out.agent or {}).get("result", ""))
    row = {"task": task.id, "layout": layout, "seed": w.seed, "target": getattr(t, "code", getattr(t, "miles", "")), "passed": ok and out.succeeded,
           "status": out.status, "rung": out.rung, "agent_fallback": bool(out.agent), "outputs": out.outputs, "detail": out.detail[:200],
           "version": routine.version, "patches": [{"kind": p.kind, "step": p.step_id, "description": p.description} for p in out.patches],
           "steps": [{"id": x.id, "status": x.status, "rung": x.rung} for x in out.steps], "duration_s": out.duration_s, "side_effects": side,
           "task_id": tid, **cell_cost(tid)}
    print(f"{'PASS' if row['passed'] else 'FAIL'} {tid.split('-', 2)[-1][:28]:28s} {out.status:10s} rung={out.rung} {row['calls']} calls "
          f"{out.duration_s:5.1f}s {answer_of(out)[:50]!r} {out.detail[:60]}", flush=True)
    return row, out


async def cmd_change(args: Any) -> None:
    env = Env(contributor=args.contributor)
    s = Suite("change", contributor=args.contributor, devices=[env.device.serial], label="Routines under change")
    base = RoutineStore(LIB_COMPILED)
    sel = tasks(args.tasks)
    prev = load("change") or {} if args.tasks else {}
    ids = {t.id for t in sel}
    new_inputs = [r for r in prev.get("new_inputs", []) if r["task"] not in ids or "inputs" not in args.parts]
    experiments = [e for e in prev.get("experiments", []) if e["task"] not in ids or "variants" not in args.parts]
    if "inputs" in args.parts:
        for k in range(args.k):
            w = world(800 + k)
            for task in sel:
                r = routine_of(base, task)
                if r is None:
                    continue
                row, _ = await run_direct(env, r, task, task.pick(w, k), w, 0, s.tid("new", task.id, f"k{k}"))
                new_inputs.append(row)
    if "variants" in args.parts:
        for layout in [int(x) for x in args.layouts.split(",")]:
            w = world(850 + layout)  # four upcoming bookings, three past trips: a, b, c, d
            for task in sel:
                r0 = routine_of(base, task)
                if r0 is None:
                    continue
                lib_dir = OUT / "library" / "change" / f"{task.id}-L{layout}"
                if lib_dir.exists():
                    shutil.rmtree(lib_dir)
                lib = RoutineStore(lib_dir)
                v1 = lib.add(r0.model_copy(update={"changes": [f"v1 compiled from {r0.compiled_from.get('task_id')}"]}))
                exp: dict[str, Any] = {"task": task.id, "layout": layout, "routine": r0.routine}
                first, out = await run_direct(env, v1, task, task.pick(w, 0), w, layout, s.tid("chg", task.id, f"L{layout}", "first"))
                exp["first"] = first
                exp["trial"] = None
                if out.patches and out.succeeded:
                    trial = lib.propose(v1, out.patches, out.task_id)
                    if trial is not None:
                        tr, _ = await run_direct(env, trial, task, task.pick(w, 1), w, layout, s.tid("chg", task.id, f"L{layout}", "trial"),
                                                 allow_repair=False, allow_agent=False)
                        verdict = {"passed": tr["passed"], "task_id": tr["task_id"], "status": tr["status"]}
                        (lib.activate if tr["passed"] else lib.reject)(r0.routine, trial.version, verdict)
                        exp["trial"] = {"version": trial.version, "changes": trial.changes, **tr}
                active = lib.get(r0.routine)
                exp["after"], _ = await run_direct(env, active, task, task.pick(w, 2), w, layout, s.tid("chg", task.id, f"L{layout}", "after"))
                if active.version != 1:
                    exp["backcompat"], _ = await run_direct(env, active, task, task.pick(w, 3), w, 0, s.tid("chg", task.id, f"L{layout}", "back"),
                                                            allow_repair=False, allow_agent=False)
                experiments.append(exp)
                s.save({"new_inputs": new_inputs, "experiments": experiments}, change_md(new_inputs, experiments))
    s.save({"new_inputs": new_inputs, "experiments": experiments}, change_md(new_inputs, experiments))
    await env.reset(compile_world())


def saved_by(r: dict[str, Any]) -> str:
    if not r["passed"]:
        return "failed"
    if r.get("agent_fallback"):
        return "the agent"
    return {0: "nothing needed", 1: "waiting", 2: "relaxed match or scroll", 3: "pop-up handler", 4: "local repair"}.get(r["rung"] or 0, f"rung {r['rung']}")


def change_md(new_inputs: list[dict[str, Any]], experiments: list[dict[str, Any]]) -> str:
    md = []
    if new_inputs:
        md += ["## New inputs", "", "| Task | Runs | Passed | No model call | Median s |", "| --- | --- | --- | --- | --- |"]
        for t in dict.fromkeys(r["task"] for r in new_inputs):
            rs = [r for r in new_inputs if r["task"] == t]
            md.append(f"| {t} | {len(rs)} | {sum(r['passed'] for r in rs)} | {sum(r['calls'] == 0 and r['passed'] for r in rs)} | {med([r['duration_s'] for r in rs])} |")
        md.append(f"| **All** | {len(new_inputs)} | **{sum(r['passed'] for r in new_inputs)}** | {sum(r['calls'] == 0 and r['passed'] for r in new_inputs)} | "
                  f"{med([r['duration_s'] for r in new_inputs])} |")
    if experiments:
        md += ["", "## Injected UI changes", "",
               "First: the compiled routine meets the changed layout (repair and the agent allowed). Trial: its patches as a new version, "
               "no repair or agent. After: the active version on another booking. Back: the patched version on the original layout.", "",
               "| Layout | Experiments | Recovered | Saved by | Model calls (first) | Patched | Trial passed | After, no model call | Back on original |",
               "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for layout in sorted({e["layout"] for e in experiments}):
            es = [e for e in experiments if e["layout"] == layout]
            by: dict[str, int] = {}
            for e in es:
                by[saved_by(e["first"])] = by.get(saved_by(e["first"]), 0) + 1
            trials = [e["trial"] for e in es if e.get("trial")]
            backs = [e["backcompat"] for e in es if e.get("backcompat")]
            md.append(f"| {layout}: {LAYOUTS[layout]} | {len(es)} | **{sum(e['first']['passed'] for e in es)}/{len(es)}** | "
                      + ", ".join(f"{k} ×{v}" for k, v in sorted(by.items(), key=lambda kv: -kv[1])) + f" | {sum(e['first']['calls'] for e in es)} | "
                      f"{len(trials)} | {sum(t['passed'] for t in trials)}/{len(trials)} | "
                      f"{sum(e['after']['passed'] and e['after']['calls'] == 0 for e in es)}/{len(es)} | {sum(b['passed'] for b in backs)}/{len(backs)} |")
        fails = [(e, k) for e in experiments for k in ("first", "after") if not e[k]["passed"]]
        if fails:
            md += ["", "Failures:", ""] + [f"- {e['task']} · layout {e['layout']} · {k}: {e[k]['status']} · {e[k]['detail'][:120]}" for e, k in fails]
    return "\n".join(md) + "\n"


# ---- A3. screen sizes and the real phone -------------------------------------------------------------------------------

def open_device(name: str) -> Any:
    if name == "phone" or name.startswith("phone-"):
        from devices.phone import PhoneDevice, discover
        phones = [p for p in discover() if p["state"] == "device" and (name == "phone" or p["id"] == name)]
        if not phones:
            raise SystemExit("no Android phone connected (adb devices)")
        return PhoneDevice(phones[0]["serial"], phones[0]["id"]).connect()
    return EmulatorDevice(name).connect()


async def cmd_sizes(args: Any) -> None:
    """All 10 routines, compiled on envoy-test, unchanged on another device, on bookings they have never seen. Results for
    each device accumulate in sizes.json (one device per invocation, so only one emulator runs at a time)."""
    dev = open_device(args.device)
    env = Env(device=dev, contributor=args.contributor)
    caps = dev.capabilities
    s = Suite("sizes", contributor=args.contributor, devices=[dev.serial], label="Routines on three screen sizes and the real phone")
    prev = load("sizes") or {"devices": {}}
    base = RoutineStore(LIB_COMPILED)
    rows = []
    print(f"   {args.device}: {caps.width}x{caps.height} @ {caps.density} dpi ({getattr(dev, 'model', '')}, Android {getattr(dev, 'android', '')})", flush=True)
    for k in range(args.k):
        w = world(900 + k)
        for task in tasks(args.tasks):
            r = routine_of(base, task)
            if r is None:
                continue
            row, _ = await run_direct(env, r, task, task.pick(w, k), w, 0, s.tid("size", args.device, task.id, f"k{k}"))
            rows.append(row)
    devices = prev.get("devices", {})
    devices[args.device] = {"size": [caps.width, caps.height], "density": caps.density, "dp": [round(caps.width * 160 / caps.density), round(caps.height * 160 / caps.density)],
                            "model": getattr(dev, "model", ""), "android": getattr(dev, "android", ""), "real_phone": caps.real_phone,
                            "run_id": s.rid, "code": s.code["short"], "rows": rows}
    s.save({"devices": devices}, sizes_md(devices))
    if hasattr(dev, "close"):
        dev.close()


def sizes_md(devices: dict[str, Any]) -> str:
    md = ["| Device | Screen | dp | Runs | Passed | No model call | Agent fallbacks | Median s |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, d in devices.items():
        rs = d["rows"]
        md.append(f"| {name}{' (real phone: ' + d['model'] + ', Android ' + str(d['android']) + ')' if d.get('real_phone') else ''} | "
                  f"{d['size'][0]}×{d['size'][1]} at {d['density']} dpi | {d['dp'][0]}×{d['dp'][1]} | {len(rs)} | **{sum(r['passed'] for r in rs)}** | "
                  f"{sum(r['passed'] and r['calls'] == 0 for r in rs)} | {sum(r['agent_fallback'] for r in rs)} | {med([r['duration_s'] for r in rs])} |")
    fails = [(n, r) for n, d in devices.items() for r in d["rows"] if not r["passed"] or r["calls"]]
    if fails:
        md += ["", "Not clean (failed, or needed a model call):", ""] + [f"- {n} · {r['task']}: {r['status']} rung {r['rung']}, {r['calls']} calls · {r['detail'][:120]}" for n, r in fails]
    return "\n".join(md) + "\n"
