"""Loop A (prompts/loop-reliability.md): first runs against replays on the apps Envoy supports, through an API copy, the
way the web app sends a task. Hybrid profile (the default).

  uv run --project backend python eval/run_loop.py run <task> --mode first --n 3     # routine switched off: the agent
  uv run --project backend python eval/run_loop.py compile <task> <api task id>      # its trace becomes the routine
  uv run --project backend python eval/run_loop.py run <task> --mode replay --n 8    # routine on: the matcher picks it
  uv run --project backend python eval/run_loop.py row <task>                        # the table row, from runs.jsonl
  uv run --project backend python eval/run_loop.py spend                             # this loop's dollars so far

Every run: the task is POSTed to the copy (--api, default :8750, with --api-dir's session token, never data/api), its
approvals are declined (SkyLark, our own test app, is the one exception: its check-in is approved), a hand-off (sign-in,
bot check) stops the task and counts as skipped, and the answer is graded against the real-app suite's ground truth
(eval/run_real_apps.py: adb, the Gmail API, published facts) or SkyLark's own state. Time is wall-clock from the POST to
the task's end; calls and dollars are every model call logged under the task's id (logs/model_costs.jsonl, real
dollars), app notes and memory included. Results: eval/results/real-apps/loop-a/runs.jsonl.

Claim the device first (coord/devices.sh). envoy-real is never snapshot-restored: a run starts the app fresh.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "eval"))
sys.path.insert(0, str(REPO / "scripts"))

import run_real_apps as rr  # noqa: E402
from models.adapter import COST_LOG  # noqa: E402

OUT = REPO / "eval" / "results" / "real-apps" / "loop-a"
RUNS_FILE = OUT / "runs.jsonl"
API = "http://127.0.0.1:8750"
ENDED = ("done", "failed", "declined", "stopped")
OWNER = "loop-a"


@dataclass
class Task:
    key: str
    goal: str
    device: str  # the AVD (or "pixel5")
    routines: list[str] = field(default_factory=list)  # the library routines a first run switches off
    workflow: str | None = None  # run_real_apps workflow id: its expect pattern and ground truth
    approve: bool = False  # only SkyLark, our own test app
    prep: Callable[[], dict[str, Any]] | None = None
    grade: Callable[[dict[str, Any], dict[str, Any]], tuple[bool, str]] | None = None
    chat: bool = False  # sent as a chat message (POST /api/chat), the way the demo asks; else POST /api/tasks
    tell: str = ""  # a chat message sent once before the runs (DoorDash: the usual)
    hand_off_ok: bool = False  # a hand-off at the end is the finish line (DoorDash's payment sheet on the test account)
    after: Callable[[], str] | None = None  # cleanup after every run (DoorDash: empty the cart)


# ---- SkyLark (envoy-test) -------------------------------------------------------------------------------------------


def _skylark_prep() -> dict[str, Any]:
    from demo_setup import demo_fixtures
    from testapps.skylark import SkyLark
    fx = demo_fixtures(signed_in=True)
    SkyLark("emulator-5554").prepare(fixtures=fx, variant=0)
    code = next(t["code"] for t in fx["trips"] if t["flight"]["to"] == "ORD" or "Chicago" in json.dumps(t))
    return {"code": code}


def _skylark_grade(task: dict[str, Any], prep: dict[str, Any]) -> tuple[bool, str]:
    from testapps.skylark import SkyLark
    trip = SkyLark("emulator-5554").trip(prep["code"])
    return bool(trip.get("checked_in")) and task["status"] == "done", f"checked_in={trip.get('checked_in')}"


# ---- real apps (envoy-real) -----------------------------------------------------------------------------------------


def _real_grade(wf_id: str) -> Callable[[dict[str, Any], dict[str, Any]], tuple[bool, str]]:
    wf = next(w for w in rr.WORKFLOWS if w.id == wf_id)

    def grade(task: dict[str, Any], prep: dict[str, Any]) -> tuple[bool, str]:
        expect = wf.expect
        if wf.truth is not None:
            expect = wf.truth()[0]
        text = task.get("result") or ""
        truth = wf.graded_by == "truth"
        ok = task["status"] == "done" and (rr.right(text, expect, {}, truth) or rr.right(text, rr.in_sentence(expect), {}, truth))
        return ok, f"expect /{expect}/"
    return grade


def _chrome_blank() -> dict[str, Any]:
    """Chrome reopens its last tab on a fresh launch, so a run after a run would start on the article it found (Oct 30: the
    second first run did, and its trace compiled into a routine that only read the start screen). A blank page first."""
    rr.adb("shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", "about:blank", "-p", "com.android.chrome")
    time.sleep(2)
    return {"chrome": "about:blank first"}


def _real(key: str, wf_id: str, routine: str, device: str = "envoy-real") -> Task:
    wf = next(w for w in rr.WORKFLOWS if w.id == wf_id)
    return Task(key, wf.goal, device, routines=[routine], workflow=wf_id, grade=_real_grade(wf_id),
                prep=_chrome_blank if wf.app == "com.android.chrome" else None)


# ---- DoorDash "order my usual" (envoy-real; the demo's opener, routine doordash_order_meal) ---------------------------

DD = "com.dd.doordash"
USUAL = "My usual from Chick-fil-A is a Chick-fil-A Deluxe Meal with American cheese, Waffle Potato Fries and a Frosted Lemonade, on DoorDash"
DD_END = re.compile(r"select payment method", re.I)  # the sheet the cart's Continue opens on the test account (no payment method)


def _labels(screen: Any) -> list[str]:
    return [e.label or "" for e in screen.numbered]


def _dd_grade(task: dict[str, Any], prep: dict[str, Any]) -> tuple[bool, str]:
    """Reached checkout (the routine ends done at Continue; the agent hands off at the payment sheet) with the usual in the
    cart. The cart is read, and emptied, by `_dd_clear` right after; this looks only at the screen the run left."""
    import asyncio
    from devices.emulator import EmulatorDevice
    s = asyncio.run(EmulatorDevice("envoy-real").connect().observe())
    at_end = s.package == DD and any(DD_END.search(x.strip()) for x in _labels(s))
    prep["end_screen"] = [x for x in _labels(s) if x][:12]
    ok = task["status"] in ("done", "needs_you") and at_end  # the coordinator: "reached checkout" = the payment sheet appeared
    return ok, f"end screen at checkout={at_end}"


def _dd_clear() -> str:
    """Empty DoorDash's cart (our test cart; reversible) and leave DoorDash on its home screen. Screens through Envoy's
    own parser (password fields masked). From doordash-usual's clear_cart.py. Returns what it removed."""
    import asyncio
    from devices.emulator import EmulatorDevice
    from devices.types import Action

    def find(s: Any, *, label: str | None = None, rid: str | None = None, kind: str | None = None) -> Any:
        for e in s.numbered:
            if label and label.casefold() not in (e.label or "").casefold():
                continue
            if rid and rid not in (e.resource_id or ""):
                continue
            if kind and e.kind != kind:
                continue
            return e
        return None

    async def go() -> str:
        d = EmulatorDevice("envoy-real").connect()
        seen: list[str] = []
        for _ in range(12):
            s = await d.wait_until_settled()
            tap = lambda e: d.act(Action(kind="tap", element=s.numbered.index(e) + 1))  # noqa: E731
            if s.package != DD:
                await d.launch(DD, fresh=True)
                continue
            if find(s, label="Select Payment Method"):
                await d.act(Action(kind="back"))
                continue
            if (e := find(s, label="Remove item", kind="Button")):
                await tap(e)
                continue
            if find(s, label="Your cart from"):
                seen.append(" | ".join(x for x in _labels(s) if re.search(r"meal|fries|lemonade|deluxe", x, re.I))[:200])
                trash = find(s, rid="delete") or find(s, rid="trash") or find(s, label="Remove", kind="Button") \
                    or find(s, label="Delete", kind="Button")
                if trash is None:
                    return "CART NOT EMPTIED: no remove button on the cart page"
                await tap(trash)
                continue
            if (cart := find(s, rid="button_orderCart")):
                await tap(cart)
                continue
            await d.launch(DD, fresh=True)
            home = await d.wait_until_settled()
            return f"cart empty (removed: {seen or 'nothing'}); home={bool(find(home, rid='coordinatorLayout_homepage'))}"
        return f"CART NOT EMPTIED after 12 screens (removed: {seen})"
    return asyncio.run(go())


TASKS: dict[str, Task] = {
    "doordash_usual": Task("doordash_usual", "Hey Envoy, I've had such a long day. Order me my usual from Chick-fil-A.", "envoy-real",
                           routines=["doordash_order_meal"], chat=True, tell=USUAL, hand_off_ok=True, grade=_dd_grade,
                           prep=lambda: {"before": _dd_clear()}, after=_dd_clear),
    "skylark_checkin": Task("skylark_checkin", "Check me in for my flight", "envoy-test",
                            routines=["skylark_check_in_flight", "skylark_air_check_in_flight"], approve=True,
                            prep=_skylark_prep, grade=_skylark_grade),
}
# The routine each first run is compiled into, named app_task like the library's own (loop A's first ones were loop_<task>).
for _k, _w, _r in [("amazon", "amazon", "amazon_search_price"), ("starbucks", "starbucks", "starbucks_drink_calories"),
                   ("chipotle", "chipotle", "chipotle_item_price"), ("target", "target_search", "target_search_price"),
                   ("doordash_search", "doordash_search", "doordash_search_first_restaurant"),
                   ("youtube", "youtube_search", "youtube_search_first_video"), ("ytmusic", "ytmusic_artist", "ytmusic_song_artist"),
                   ("chrome", "chrome_wikipedia", "chrome_wikipedia_opened_year"), ("maps", "maps_address", "maps_place_address"),
                   ("play", "play_rating", "play_app_rating"), ("gmail", "gmail_search", "gmail_search_subject"),
                   ("settings", "settings_bluetooth", "settings_bluetooth_state"), ("calendar", "calendar_today", "calendar_events_today"),
                   ("contacts", "contacts_count", "contacts_count")]:
    TASKS[_k] = _real(_k, _w, _r)
# Gmail: the suite's own goal ("...search my mail for DoorDash...") and its second term as a new input for the same routine.
# Before main b1f3c9a the first routed to DoorDash (app_for took the first APP_NAMES hit; those rows are marked spoiled).
_gmail_truth = next(w for w in rr.WORKFLOWS if w.id == "gmail_search").truth


def _gmail_second(task: dict[str, Any], prep: dict[str, Any]) -> tuple[bool, str]:
    expect = _gmail_truth()[1]  # the subject of the newest "Security alert" message, from the Gmail API
    text = task.get("result") or ""
    return task["status"] == "done" and (rr.right(text, expect, {}, True) or rr.right(text, rr.in_sentence(expect), {}, True)), f"expect /{expect}/"


def _ytm_top(task: dict[str, Any], prep: dict[str, Any]) -> tuple[bool, str]:
    text = task.get("result") or ""
    return task["status"] == "done" and re.search(r"\bqueen\b", text, re.I) is not None, "expect Queen (the top result's artist)"


# YouTube Music worded so the screen's answer is the true one (the coordinator: "who sings X" answered by the first Songs
# row read a cover on Oct 30): the top result, title and artist.
TASKS["ytmusic_top"] = Task("ytmusic_top", "In the YouTube Music app, search for Bohemian Rhapsody and tell me the title and artist of "
                            "the top result.", "envoy-real", routines=["ytmusic_top_result"], workflow="ytmusic_artist", grade=_ytm_top)


def _second(key: str) -> Task:
    """The workflow's second input (eval/run_real_apps.py `second`), replayed with the routine the first input compiled: does
    it carry over to a new value? Graded by `expect_second` (else `expect`)."""
    t = TASKS[key]
    wf = next(w for w in rr.WORKFLOWS if w.id == t.workflow)
    old, new = next(iter(wf.second.items()))
    expect = wf.expect_second or wf.expect

    def grade(task: dict[str, Any], prep: dict[str, Any]) -> tuple[bool, str]:
        text = task.get("result") or ""
        truth = wf.graded_by == "truth"
        ok = task["status"] == "done" and (rr.right(text, expect, {"q": new}, truth) or rr.right(text, rr.in_sentence(expect), {"q": new}, truth))
        return ok, f"expect /{expect}/ for {new!r}"
    return Task(f"{key}2", t.goal.replace(old, new), t.device, routines=t.routines, grade=grade)


for _k in ("amazon", "starbucks", "chipotle", "youtube", "play"):
    TASKS[f"{_k}2"] = _second(_k)


TASKS["gmail_security"] = Task("gmail_security", TASKS["gmail"].goal.replace("DoorDash", "Security alert"), "envoy-real",
                               routines=["gmail_search_subject"], grade=_gmail_second)


# ---- the API copy ---------------------------------------------------------------------------------------------------


class Copy:
    def __init__(self, base: str, api_dir: Path) -> None:
        if api_dir.resolve() == (REPO / "data" / "api").resolve():
            sys.exit("--api-dir must be the copy's own data dir, never data/api")
        token = (api_dir / "session_token").read_text().strip()
        self.http = httpx.Client(base_url=base, headers={"Authorization": f"Bearer {token}"}, timeout=30)

    def get(self, path: str, **params: Any) -> Any:
        r = self.http.get(path, params=params)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        r = self.http.post(path, json=body or {})
        r.raise_for_status()
        return r.json()

    def decide(self, aid: str, approve: bool) -> None:
        nonce = self.get(f"/api/approvals/{aid}").get("nonce") or ""
        self.post(f"/api/approvals/{aid}", {"decision": "approve" if approve else "decline", "nonce": nonce})


def spent(tid: str) -> dict[str, Any]:
    """Every model call logged under this task's id (its traces, match, notes, memory), in real dollars."""
    calls, usd = 0, 0.0
    jobs: dict[str, int] = {}
    with COST_LOG.open() as f:
        for line in f:
            if tid not in line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if str(r.get("task_id") or "").startswith(tid):
                calls += 1
                usd += float(r.get("cost_usd") or 0)
                jobs[str(r.get("job"))] = jobs.get(str(r.get("job")), 0) + 1
    return {"calls": calls, "usd": round(usd, 4), "jobs": jobs}


def main_commit() -> str:
    """main's commit now (a skip-ahead fix may land mid-loop), and this checkout's."""
    def rev(ref: str) -> str:
        return subprocess.run(["git", "rev-parse", "--short", ref], cwd=REPO, capture_output=True, text=True).stdout.strip()
    return f"main {rev('main')}, here {rev('HEAD')}"


def switch(names: list[str], on: bool) -> dict[str, Any]:
    from routines.store import RoutineStore
    store, got = RoutineStore(), {}
    for n in names:
        try:
            got[n] = store.switch(n, on)
        except KeyError:
            got[n] = "absent"
    return got


def run_once(api: Copy, t: Task, mode: str, n: int) -> dict[str, Any]:
    prep = t.prep() if t.prep else {}
    t0 = time.time()
    if t.chat:
        said = api.post("/api/chat", {"message": t.goal, "source": "chat"})
        if not said.get("task"):
            print(f"  [{mode} {n}] chat made no task: {said.get('kind')} {str(said.get('reply'))[:120]!r}", flush=True)
            return {"task": t.key, "mode": mode, "n": n, "ok": False, "skipped": False, "status": "no task"}
        task = said["task"]
    else:
        task = api.post("/api/tasks", {"goal": t.goal})
    tid = task["id"]
    print(f"  [{mode} {n}] {tid}: {t.goal}", flush=True)
    decided: dict[str, str] = {}
    handoff_since = None
    handed: str | None = None
    end = None
    while time.time() - t0 < 900:
        got = api.get(f"/api/tasks/{tid}")
        task = got["task"]
        for a in got["approvals"]:
            if a["status"] == "pending" and a["id"] not in decided:
                api.decide(a["id"], t.approve)
                decided[a["id"]] = "approved" if t.approve else "declined"
                print(f"    approval {decided[a['id']]}: {a.get('description')}", flush=True)
        if task["status"] in ENDED:
            end = time.time()
            break
        if task["status"] in ("needs_you", "taken_over") or task.get("waiting_for") == "takeover":
            handoff_since = handoff_since or time.time()
            if time.time() - handoff_since > 3:  # a sign-in, a bot check or the ask to use your phone: this loop never answers one
                handed = task.get("detail") or task.get("waiting_for") or task["status"]
                api.post(f"/api/tasks/{tid}/stop")
                end = time.time()
                task = {**task, "status": "needs_you"}
                break
        else:
            handoff_since = None
        time.sleep(0.5)
    secs = round((end or time.time()) - t0, 1)
    time.sleep(12)  # memory and app notes are written after the phone work
    got = api.get(f"/api/tasks/{tid}")
    final = got["task"] if got["task"]["status"] in ENDED else task
    if handed and final["status"] == "stopped":  # this loop stopped it at the hand-off: grade it as the hand-off it was
        final = {**final, "status": "needs_you"}
    ok, why = t.grade(final, prep) if t.grade else (final["status"] == "done", "")
    steps = got["steps"]
    handoff = bool(handed) or final["status"] == "needs_you" or any("bot check" in (s.get("text") or "").lower() for s in steps)
    cleanup = t.after() if t.after else None
    cost = spent(tid)
    row = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "task": t.key, "mode": mode, "n": n, "task_id": tid,
           "status": final["status"], "ok": ok, "skipped": bool(handoff and not ok and not t.hand_off_ok),
           "answer": (final.get("result") or "")[:300], "goal": final.get("goal"), "prep": prep, "cleanup": cleanup,
           "detail": (final.get("detail") or "")[:300], "grade": why, "routine": final.get("routine"),
           "kind": final.get("kind"), "seconds": secs, "calls": cost["calls"], "usd": cost["usd"], "jobs": cost["jobs"],
           "approvals": decided, "handed_off": handed, "commit": main_commit()}
    note = next((s.get("text") for s in steps if (s.get("text") or "").startswith("using routine")), None)
    if note:
        row["routine_note"] = note[:200]
    OUT.mkdir(parents=True, exist_ok=True)
    with RUNS_FILE.open("a") as f:
        f.write(json.dumps(row) + "\n")
    print(f"    -> {'PASS' if ok else ('SKIP' if row['skipped'] else 'FAIL')} {final['status']} {secs}s {cost['calls']} calls "
          f"${cost['usd']} {row['kind']}{' ' + str(row['routine']) if row['routine'] else ''}: {row['answer'][:120]!r}", flush=True)
    return row


def cmd_run(args: argparse.Namespace) -> int:
    t = TASKS[args.task]
    api = Copy(args.api, Path(args.api_dir))
    if t.routines:
        print(f"routines {'off' if args.mode == 'first' else 'on'}: {switch(t.routines, args.mode != 'first')}")
    if t.tell:
        said = api.post("/api/chat", {"message": t.tell, "source": "chat"})
        print(f"told: {str(said.get('reply'))[:160]!r}")
    rows = []
    for i in range(1, args.n + 1):
        rows.append(run_once(api, t, args.mode, i))
        if args.pause:
            time.sleep(args.pause)
    good = sum(r["ok"] for r in rows)
    print(f"{t.key} {args.mode}: {good}/{len(rows) - sum(r['skipped'] for r in rows)} (skipped {sum(r['skipped'] for r in rows)})")
    return 0


def cmd_compile(args: argparse.Namespace) -> int:
    """The first run's trace (data/runs/<api task id>-r1) compiled into routine loop_<task>, added to the library."""
    import asyncio
    from agent.trace import RUNS
    from routines.compiler import compile_trace
    from routines.model import dump_yaml
    from routines.store import RoutineStore
    t = TASKS[args.task]
    trace = RUNS / f"{args.task_id}-r1"
    t0 = time.time()
    # A run the grader found right against ground truth (eval/run_real_apps.py: adb, the Gmail API, a published fact) is
    # confirmed even when the agent's own end check couldn't see the answer on its last screen (Chrome: "1889" scrolled away).
    routine, report = asyncio.run(compile_trace(trace, memory=args.memory, confirmed=getattr(args, "confirmed", False)))
    routine.routine = t.routines[0] if t.routines else routine.routine
    added = RoutineStore().add(routine, verification={"by": OWNER, "from": trace.name, "checked": "replays in runs.jsonl"})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "compiled").mkdir(exist_ok=True)
    (OUT / "compiled" / f"{added.routine}-v{added.version}.yaml").write_text(dump_yaml(added))
    rec = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "task": t.key, "mode": "compile", "task_id": args.task_id,
           "routine": added.routine, "version": added.version, "steps": len(added.steps), "inputs": list(added.inputs),
           "seconds": round(time.time() - t0, 1), "usd": round(float(getattr(report, "cost_usd", 0) or 0), 4),
           "usd_standard": report.cost_at_standard_usd, "dropped": report.dropped, "warnings": report.warnings, "commit": main_commit()}
    with RUNS_FILE.open("a") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    print(dump_yaml(added))
    print(json.dumps({k: rec[k] for k in ("routine", "version", "steps", "inputs", "seconds", "usd_standard", "warnings")}, default=str))
    return 0


def cmd_cycle(args: argparse.Namespace) -> int:
    """One app's pass: first runs, the first passing trace compiled (only real apps: their routine is loop_<task>), then
    replays. Stops early on a hand-off (a bot check is never retried: Target) or when every first run fails."""
    t = TASKS[args.task]
    args.mode, args.n = "first", args.first
    api = Copy(args.api, Path(args.api_dir))
    print(f"routines off: {switch(t.routines, False)}")
    if t.tell:
        said = api.post("/api/chat", {"message": t.tell, "source": "chat"})
        print(f"told: {str(said.get('reply'))[:160]!r}")
    firsts = []
    for i in range(1, args.first + 1):
        firsts.append(run_once(api, t, "first", i))
        if firsts[-1].get("skipped"):
            print(f"{t.key}: hand-off (bot check or sign-in): stopping this app for now")
            return 1
    good = next((r for r in firsts if r["ok"]), None)
    if good is None:
        print(f"{t.key}: no first run passed; nothing to compile")
        return 1
    if t.workflow:  # SkyLark, Instagram and DoorDash replay the library's own routine
        try:
            wf = next(w for w in rr.WORKFLOWS if w.id == t.workflow)
            cmd_compile(argparse.Namespace(task=t.key, task_id=good["task_id"], memory="", confirmed=wf.graded_by == "truth"))
        except Exception as e:  # noqa: BLE001 - recorded, and the replays are skipped
            with RUNS_FILE.open("a") as f:
                f.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "task": t.key, "mode": "compile",
                                    "task_id": good["task_id"], "error": f"{type(e).__name__}: {e}"[:400], "commit": main_commit()}) + "\n")
            print(f"{t.key}: compile failed: {type(e).__name__}: {e}")
            return 1
    print(f"routines on: {switch(t.routines, True)}")
    for i in range(1, args.replay + 1):
        r = run_once(api, t, "replay", i)
        if r.get("skipped"):
            break
    return cmd_row(args)


def rows_for(key: str) -> list[dict[str, Any]]:
    return [r for r in map(json.loads, RUNS_FILE.read_text().splitlines()) if r.get("task") == key] if RUNS_FILE.exists() else []


def alone_ok(r: dict[str, Any]) -> bool:
    """A right replay the routine did by itself (repairs allowed): no plan or step calls, so the agent never took over."""
    return bool(r.get("ok")) and r.get("kind") == "routine" and not ({"plan", "step"} & set(r.get("jobs") or {}))


def _stats(rs: list[dict[str, Any]]) -> tuple[str, str]:
    counted = [r for r in rs if not r.get("skipped") and not r.get("spoiled")]
    ok = [r for r in counted if r["ok"]]
    med = lambda xs: sorted(xs)[len(xs) // 2] if xs else None  # noqa: E731
    s, usd = med([r["seconds"] for r in ok]), med([r["usd"] for r in ok])
    return f"{len(ok)}/{len(counted)}", (f"{s:.0f} s / ${usd:.3f}" if ok else "–")


def cmd_row(args: argparse.Namespace) -> int:
    rs = rows_for(args.task)
    first = [r for r in rs if r["mode"] == "first" and not r.get("spoiled")]
    rep = [r for r in rs if r["mode"] == "replay" and not r.get("spoiled")]
    (f, fs), (p, ps) = _stats(first), _stats(rep)
    skipped = sum(r.get("skipped", False) for r in rs if r["mode"] in ("first", "replay"))
    alone = [r for r in rep if alone_ok(r)]
    t = TASKS[args.task]
    print(f"| {t.key} | {t.goal} | {f} | {fs} | {p} | {ps} | medians of passing runs; routine alone (no agent) "
          f"{len(alone)}/{len([r for r in rep if not r.get('skipped')])}; {skipped} skipped |")
    for r in rs:
        print(f"  {r['mode']:8} {r.get('n', ''):>2} {r.get('status', ''):9} ok={r.get('ok', '')!s:5} {r.get('seconds')}s "
              f"{r.get('calls', '')} calls ${r.get('usd')} {r.get('routine') or ''} {r.get('answer', '')[:80]!r}")
    return 0


def cmd_spend(args: argparse.Namespace) -> int:
    ids = {r["task_id"] for r in map(json.loads, RUNS_FILE.read_text().splitlines()) if r.get("mode") != "compile"} if RUNS_FILE.exists() else set()
    runs = sum(spent(i)["usd"] for i in ids)
    comp = sum(float(r.get("usd") or 0) for r in map(json.loads, RUNS_FILE.read_text().splitlines()) if r.get("mode") == "compile") \
        if RUNS_FILE.exists() else 0
    print(f"loop-a runs ${runs:.3f} over {len(ids)} tasks, compiles ${comp:.3f}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default=API)
    ap.add_argument("--api-dir", default=os.environ.get("ENVOY_API_DIR") or "")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("task", choices=sorted(TASKS))
    p.add_argument("--mode", choices=["first", "replay"], required=True)
    p.add_argument("--n", type=int, default=1)
    p.add_argument("--pause", type=float, default=0)
    p = sub.add_parser("cycle")
    p.add_argument("task", choices=sorted(TASKS))
    p.add_argument("--first", type=int, default=3)
    p.add_argument("--replay", type=int, default=8)
    p = sub.add_parser("compile")
    p.add_argument("task", choices=sorted(TASKS))
    p.add_argument("task_id")
    p.add_argument("--memory", default="")
    p.add_argument("--confirmed", action="store_true", help="the grader found it right against ground truth")
    p = sub.add_parser("row")
    p.add_argument("task", choices=sorted(TASKS))
    sub.add_parser("spend")
    args = ap.parse_args()
    if args.cmd in ("run", "cycle") and not args.api_dir:
        sys.exit("--api-dir (or ENVOY_API_DIR): the copy's data dir")
    return {"run": cmd_run, "cycle": cmd_cycle, "compile": cmd_compile, "row": cmd_row, "spend": cmd_spend}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
